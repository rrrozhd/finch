"""FastAPI server: upload zip -> questions -> results. Serves the built shadcn UI from web/dist."""
import json
import os
import threading
from contextlib import contextmanager
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

if os.getenv("ARIZE_API_KEY"):  # tracing must be registered before the LangChain models are created
    from arize.otel import register
    from openinference.instrumentation.langchain import LangChainInstrumentor
    tp = register(space_id=os.environ["ARIZE_SPACE_ID"], api_key=os.environ["ARIZE_API_KEY"], project_name="taxagent")
    LangChainInstrumentor().instrument(tracer_provider=tp)

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openinference.instrumentation import using_session
from opentelemetry import trace
from pydantic import BaseModel

from . import agent, evals, facts, pipeline, sandbox

app = FastAPI(telemetry={"tracing": False})  # its HTTP spans would become blank trace roots above ours
MAX_ZIP = 50_000_000
tracer = trace.get_tracer("taxagent")


@contextmanager
def traced(name: str, session: str, input):
    """One root span per request, so each request is one Arize trace, grouped by taxpayer session."""
    with using_session(session), tracer.start_as_current_span(
            name, attributes={"openinference.span.kind": "CHAIN", "input.value": json.dumps(input, default=str)}) as sp:
        out = {}
        yield out
        sp.set_attribute("output.value", json.dumps(out, default=str))


threading.Thread(target=sandbox.warm, daemon=True).start()  # starts the sandbox; PolicyEngine import takes ~25s


@app.post("/api/upload")
def upload(file: UploadFile):  # sync: ingest blocks for ~30s, so run it in FastAPI's threadpool, not on the event loop
    data = file.file.read(MAX_ZIP + 1)
    if len(data) > MAX_ZIP or not data.startswith(b"PK"):
        raise HTTPException(400, "Upload a .zip under 50 MB")
    session = uuid.uuid4().hex[:12]
    with traced("upload", session, dict(file=file.filename, bytes=len(data))) as out:
        out.update(session=session, summary=pipeline.ingest(session, data), next=pipeline.next_question(session))
    return out


class Answer(BaseModel):
    session: str
    field: str
    text: str


@app.post("/api/answer")
def answer(a: Answer):
    with traced("answer", a.session, a.model_dump()) as out:
        r = pipeline.answer(a.session, a.field, a.text)
        out.update(r, next=pipeline.next_question(a.session) if r["ok"] else None)
    return out


@app.get("/api/results/{session}")
def results(session: str):
    if pipeline.next_question(session):
        raise HTTPException(409, "Questions still open")
    with traced("results", session, dict(session=session)) as out:
        out.update(pipeline.results(session))
    return out


@app.get("/api/review/{session}")
def review(session: str):
    return pipeline.review(session)


class Correction(BaseModel):
    session: str
    key: str
    category: str
    business_pct: int
    schedule_c_category: str | None = None
    reason: str
    same_merchant: bool = False


@app.post("/api/correct")
def correct(c: Correction):
    if c.category not in ("income", "business_expense", "personal", "transfer", "tax_payment") or not 0 <= c.business_pct <= 100:
        raise HTTPException(400, "invalid correction")
    with traced("correct", c.session, c.model_dump()) as out:
        out.update(pipeline.correct(c.session, c.key, c.category, c.business_pct, c.schedule_c_category, c.reason, c.same_merchant))
    return out


@app.get("/api/facts/{session}")
def all_facts(session: str, prefix: str = ""):
    return facts.current(session, prefix)


@app.get("/api/history/{session}/{key}")
def history(session: str, key: str):
    return facts.history(session, key)


@app.post("/api/eval/{session}")
def run_eval(session: str):
    return evals.run(session)


class ChatIn(BaseModel):
    session: str
    text: str


class Resume(BaseModel):
    session: str
    approve: bool


@app.post("/api/chat")
def chat(c: ChatIn):
    with traced("agent.chat", c.session, c.model_dump()) as out:
        out.update(agent.chat(c.session, c.text))
    return out


@app.post("/api/chat/resume")
def chat_resume(r: Resume):
    with traced("agent.resume", r.session, r.model_dump()) as out:
        out.update(agent.resume(r.session, r.approve))
    return out


@app.get("/api/demo-zip")
def demo_zip():  # sample upload for the demo button
    return FileResponse(Path(__file__).parents[1] / "demo" / "maya" / "upload.zip", media_type="application/zip")


dist = Path(__file__).parents[1] / "web" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="web")
