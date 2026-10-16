"""Run sandbox_worker.py on an uploaded zip, and the tax engine, inside a Daytona sandbox (network blocked, no secrets).

LOCAL_SANDBOX=1 runs the same worker as a local subprocess and the engine in-process (dev only, no isolation).
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from datetime import date
from pathlib import Path

from . import engine

WORKER = Path(__file__).with_name("sandbox_worker.py")
ENGINE = Path(engine.__file__)
CPUS = 4
NAME = "taxagent-worker-v2"  # v2: image adds PolicyEngine for the tax engine
_sandbox = None
_start_lock = threading.Lock()
_lock = threading.Lock()  # one shared interpreter context; FastAPI threads and the agent's what_if both call compute


def _image():
    from daytona import Image
    return (Image.debian_slim("3.12")
            .run_commands("apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*")
            .pip_install(["rapidocr-onnxruntime", "openpyxl", "policyengine-us==2.49.1", "policyengine-core==3.33.4"])  # pins match uv.lock
            .run_commands("python -c \"from rapidocr_onnxruntime import RapidOCR; RapidOCR()\"")  # bake OCR models into image
            .add_local_file(ENGINE, "/opt/engine/engine.py")
            .run_commands("cd /opt/engine && python engine.py"))  # golden self-check at build time; fetches any lazy data before network is cut


def sandbox():
    """One warm sandbox per server process; packages are baked into the image so no pip at demo time."""
    global _sandbox
    with _start_lock:  # warm() thread and the first request race here
        if _sandbox is None:
            from daytona import CreateSandboxFromImageParams, Daytona, DaytonaConflictError, DaytonaNotFoundError, Resources
            d = Daytona()
            try:  # reuse one named sandbox across server restarts (account CPU quota is 10)
                sb = d.get(NAME)
                if sb.state.value != "started":
                    try:
                        sb.start(timeout=120)
                    except DaytonaConflictError:  # already starting/stopping: wait for it instead
                        sb.wait_for_sandbox_start(timeout=180)
            except DaytonaNotFoundError:
                sb = d.create(CreateSandboxFromImageParams(name=NAME, image=_image(), resources=Resources(cpu=CPUS, memory=4),
                                                           auto_stop_interval=60), timeout=900,
                              on_snapshot_create_logs=lambda l: print("[daytona]", l, end=""))
            sb.fs.upload_file(WORKER.read_bytes(), "/home/daytona/sandbox_worker.py")
            sb.fs.upload_file(ENGINE.read_bytes(), "/home/daytona/engine.py")
            for w in WORKER.parent.glob("vendor/*.whl"):
                sb.fs.upload_file(w.read_bytes(), f"/home/daytona/{w.name}")
            _sandbox = sb  # only cache a sandbox that started; a failed start retries on the next call
    return _sandbox


def process_zip(zip_bytes: bytes, job: str) -> dict:
    if os.getenv("LOCAL_SANDBOX") == "1":
        with tempfile.TemporaryDirectory() as tmp:
            z = Path(tmp) / "upload.zip"
            z.write_bytes(zip_bytes)
            out = subprocess.run([sys.executable, "-I", str(WORKER), str(z), str(Path(tmp) / "files")],
                                 capture_output=True, text=True, check=True).stdout
            return json.loads(out)
    sb = sandbox()
    base = f"/home/daytona/jobs/{job}"
    sb.process.exec(f"mkdir -p {base}")
    sb.fs.upload_file(zip_bytes, f"{base}/upload.zip")
    r = sb.process.exec(f"python sandbox_worker.py {base}/upload.zip {base}/files", cwd="/home/daytona",
                        env={"OCR_THREADS": str(CPUS)}, timeout=300)
    if r.exit_code != 0:
        raise RuntimeError(f"sandbox worker failed: {r.result[-2000:]}")
    return json.loads(r.result)



def compute(inputs: dict, as_of: date) -> dict:
    """engine.compute, run in the sandbox's persistent interpreter so PolicyEngine is imported once, not per call."""
    if os.getenv("LOCAL_SANDBOX") == "1":
        return engine.compute(inputs, as_of)
    code = ("import json, sys\n"
            "if 'engine' not in globals():\n"  # context is lost if the sandbox auto-stopped and restarted
            "    sys.path.insert(0, '/home/daytona'); import engine\n"
            f"from datetime import date\nprint(json.dumps(engine.compute(json.loads({json.dumps(json.dumps(inputs))}), "
            f"date.fromisoformat({as_of.isoformat()!r}))))")
    with _lock:
        r = sandbox().code_interpreter.run_code(code, timeout=180)
    if r.error:
        raise RuntimeError(f"sandbox engine failed: {r.error.name}: {r.error.value}\n{r.error.traceback}")
    return json.loads(r.stdout.strip().splitlines()[-1])  # last line: PolicyEngine may print warnings first


def warm():
    """Start the sandbox and import PolicyEngine there (~25s) at server startup."""
    if os.getenv("LOCAL_SANDBOX") == "1":
        return engine.warm()
    with _lock:
        sandbox().code_interpreter.run_code("import sys; sys.path.insert(0, '/home/daytona'); import engine; engine.warm()",
                                            timeout=300)
