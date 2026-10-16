"""Deterministic eval of categorization against demo/maya/labels_ground_truth.csv (the agent never reads this file).

One Arize span per transaction (eval.* attributes) plus a summary span, so accuracy is visible next to the traces.
"""
import csv
from pathlib import Path

from opentelemetry import trace

from . import facts

LABELS = Path(__file__).parents[1] / "demo" / "maya" / "labels_ground_truth.csv"
tracer = trace.get_tracer("taxagent.eval")


def run(session: str) -> dict:
    labels = {r["transaction_id"]: r for r in csv.DictReader(open(LABELS))}
    got = facts.current(session, "txn:")
    rows, cat_ok, amt_ok = [], 0, 0
    with tracer.start_as_current_span("eval.categorization", attributes={"openinference.span.kind": "CHAIN"}) as root:
        for tid, lab in labels.items():
            f = got.get(f"txn:{tid}")
            if f is None:
                continue
            v = f["value"]
            c = v["category"] == lab["category"]
            a = abs(v["deductible"] - float(lab["deductible_amount"])) < 0.01
            cat_ok += c; amt_ok += a
            if not (c and a):
                rows.append(dict(id=tid, description=v["description"], amount=v["amount"], by=f["by"],
                                 got=[v["category"], v["business_pct"], v["deductible"]],
                                 want=[lab["category"], int(lab["business_pct"]), float(lab["deductible_amount"])]))
            with tracer.start_as_current_span("eval.txn", attributes={"openinference.span.kind": "EVALUATOR"}) as sp:
                sp.set_attribute("txn.id", tid); sp.set_attribute("txn.description", v["description"])
                sp.set_attribute("categorized_by", f["by"])
                sp.set_attribute("eval.category.correct", c); sp.set_attribute("eval.deductible.correct", a)
        n = sum(1 for t in labels if f"txn:{t}" in got)
        want_total = sum(float(l["deductible_amount"]) for l in labels.values())
        got_total = sum(got[f"txn:{t}"]["value"]["deductible"] for t in labels if f"txn:{t}" in got)
        out = dict(session=session, evaluated=n, category_accuracy=round(cat_ok / n, 4) if n else 0,
                   deductible_accuracy=round(amt_ok / n, 4) if n else 0,
                   deductible_total=dict(got=round(got_total, 2), want=round(want_total, 2)), misses=rows)
        for k in ("evaluated", "category_accuracy", "deductible_accuracy"):
            root.set_attribute(f"eval.{k}", out[k])
    if n == 0:
        raise ValueError("eval matched zero transactions")  # a vacuous eval must not look green
    return out
