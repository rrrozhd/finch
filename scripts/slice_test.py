"""Thin-slice test without UI: ingest upload.zip, answer the checklist, compute results."""
import json, os, sys, time
from datetime import date
from dotenv import load_dotenv
load_dotenv(".env")
if os.getenv("ARIZE_API_KEY"):
    from arize.otel import register
    from openinference.instrumentation.langchain import LangChainInstrumentor
    tp = register(space_id=os.environ["ARIZE_SPACE_ID"], api_key=os.environ["ARIZE_API_KEY"], project_name="taxagent")
    LangChainInstrumentor().instrument(tracer_provider=tp)
from app import pipeline

ANSWERS = {"state": "New York", "in_nyc": "yes, Brooklyn", "filing_status": "single", "line_of_work": "YouTube and TikTok content creator",
           "prior_fed_tax": "$18,000", "prior_fed_agi": "about 100k", "prior_ny_tax": "6500"}
s = f"slice-{int(time.time())}"
t = time.time()
print(json.dumps(pipeline.ingest(s, open("demo/maya/upload.zip", "rb").read()), indent=1), f"\ningest {time.time()-t:.0f}s")
asked = []
while (q := pipeline.next_question(s)):
    asked.append(q["field"]); print("Q:", q["field"], "|", q["question"])
    r = pipeline.answer(s, q["field"], ANSWERS.get(q["field"], "business"))
    if not r["ok"]:
        print("  clarify:", r); sys.exit(1)
res = pipeline.results(s, date(2026, 10, 16))
print(json.dumps({k: res[k] for k in ("inputs", "annual", "federal", "ny", "expense_by_category", "needs_review", "notes")}, indent=1))
print("session", s, "asked", asked)
if os.getenv("ARIZE_API_KEY"): tp.force_flush()
