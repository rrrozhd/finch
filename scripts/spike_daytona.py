"""Spike: build the sandbox image, run the worker on upload.zip, and run PolicyEngine for Maya inside Daytona."""
import json, time
from dotenv import load_dotenv
load_dotenv(".env")
from app import sandbox

t = time.time()
sb = sandbox.sandbox()
print(f"sandbox ready in {time.time()-t:.0f}s: {sb.id}")
t = time.time()
x = sandbox.process_zip(open("demo/maya/upload.zip", "rb").read(), "spike")
print(f"worker in sandbox {time.time()-t:.0f}s: {len(x['transactions'])} txns, {len(x['sheets'])} sheets")
for r in x["receipts"]:
    print(" ", r["file"], r["confidence"], r["total"], r["date"], "VISION" if r["needs_vision"] else "")

t = time.time()
r = sb.process.exec("pip install -q policyengine-us 2>&1 | tail -1", timeout=900)
print(f"pip policyengine-us in sandbox {time.time()-t:.0f}s exit={r.exit_code}")
sb.fs.upload_file(open("scripts/pe_maya.py", "rb").read(), "/home/daytona/pe_maya.py")
t = time.time()
r = sb.process.exec("python pe_maya.py", cwd="/home/daytona", timeout=600)
print(f"PE in sandbox {time.time()-t:.0f}s exit={r.exit_code}\n{r.result[-1500:]}")
