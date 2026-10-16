"""Probe: Bedrock call traced to Arize, and SurrealDB supersede with history."""
import os, time
from dotenv import load_dotenv
load_dotenv(".env")
from arize.otel import register
from openinference.instrumentation.langchain import LangChainInstrumentor
tp = register(space_id=os.environ["ARIZE_SPACE_ID"], api_key=os.environ["ARIZE_API_KEY"], project_name="taxagent")
LangChainInstrumentor().instrument(tracer_provider=tp)
from app import facts, llm

t = time.time()
q = llm.word_question("state", "which US state you file taxes in")
print(f"bedrock ok ({time.time()-t:.1f}s, fast={llm.FAST}):", q)
a = llm.parse_answer("prior_fed_tax", "2025 federal tax in dollars", "it was about $18k")
print("parse:", a)

s = f"probe-{int(time.time())}"
facts.put(s, "txn:T1", {"category": "personal"}, "bank.csv#T1", "llm")
facts.put(s, "txn:T1", {"category": "business_expense"}, "bank.csv#T1", "user", "user: camera for videos")
print("current:", facts.current(s, "txn:")["txn:T1"]["value"])
for h in facts.history(s, "txn:T1"):
    print("history:", h["value"], h["by"], "current" if h["current"] else "superseded")
tp.force_flush()
print("arize flushed")
