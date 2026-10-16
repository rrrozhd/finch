"""Orchestration: sandbox extraction -> facts -> categorize (rules first, LLM for the rest) -> questions -> compute."""
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import date, datetime

from opentelemetry import trace

from . import facts, llm, sandbox

tracer = trace.get_tracer("taxagent")
TOOL, CHAIN = {"openinference.span.kind": "TOOL"}, {"openinference.span.kind": "CHAIN"}  # so Arize types these spans

# Rules first: (regex on bank description, category, schedule C category, business %). Anything else goes to the LLM.
RULES = [
    (r"ADSENSE|PATREON PAYOUT|^ACH CREDIT", "income", None, 0),
    (r"IRS USATAXPYMT|NYS DTF PIT", "tax_payment", None, 0),
    (r"TRANSFER TO SAVINGS", "transfer", None, 0),
    (r"ADOBE|EPIDEMIC SOUND|GOOGLE \*WORKSPACE", "business_expense", "Software / subscriptions", 100),
    (r"WEWORK", "business_expense", "Rent (coworking)", 100),
    (r"NETFLIX|EQUINOX|WHOLE FOODS|TRADER JOE|KEY FOOD|RENT$", "personal", None, 0),
]

# The fixed checklist of inputs the engine needs that files can't supply. The LLM only words and parses them.
CHECKLIST = [
    ("state", "which US state you file taxes in"),
    ("in_nyc", "whether you live in New York City (yes/no)"),
    ("filing_status", "your filing status (single, married filing jointly, ...)"),
    ("line_of_work", "what kind of work you do as a freelancer"),
    ("prior_fed_tax", "the total federal tax on your 2025 return (Form 1040 line 24), in dollars"),
    ("prior_fed_agi", "your 2025 adjusted gross income (Form 1040 line 11), in dollars"),
    ("prior_ny_tax", "your total 2025 New York State + City tax, in dollars"),
]
NUMERIC = {"prior_fed_tax", "prior_fed_agi", "prior_ny_tax"}
MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def ingest(session: str, zip_bytes: bytes) -> dict:
    with tracer.start_as_current_span("sandbox.extract", attributes=TOOL) as sp:
        x = sandbox.process_zip(zip_bytes, session)
        sp.set_attribute("transactions", len(x["transactions"]))
        sp.set_attribute("receipts", len(x["receipts"]))

    receipts = []
    for r in x["receipts"]:
        with tracer.start_as_current_span("receipt.read", attributes=TOOL) as sp:
            sp.set_attribute("file", r["file"]); sp.set_attribute("ocr.confidence", r["confidence"])
            sp.set_attribute("path", "vision" if r["needs_vision"] else "ocr")
            if r["needs_vision"]:
                img = zipfile.ZipFile(io.BytesIO(zip_bytes)).read(next(n for n in zipfile.ZipFile(io.BytesIO(zip_bytes)).namelist()
                                                                         if n.endswith(r["file"])))
                v = llm.read_receipt(img, MEDIA[r["file"][r["file"].rfind("."):].lower()])
                r.update(vendor=v.vendor, date=v.date, total=v.total, items=v.items, path="vision")
            else:
                r.update(items=_items(r["text"]), path="ocr")
            facts.put(session, f"receipt:{r['file']}", {k: r[k] for k in ("vendor", "date", "total", "items", "confidence", "path")},
                      r["file"], r["path"])
            receipts.append(r)

    for s in x["sheets"]:
        for row in s["rows"]:
            facts.put(session, f"sheet:{row['source']}", {k: v for k, v in row.items() if k != "source"}, row["source"], "intake")

    inferred = _infer_profile(session, x.get("docs", []))  # before categorizing, so line_of_work is known
    txns = x["transactions"]
    matched = _match_receipts(txns, receipts)
    unknown = defaultdict(lambda: dict(examples=[], has_receipt=False, receipt_items=None))
    for t in txns:
        rule = next((r for r in RULES if re.search(r[0], t["description"])), None)
        if rule:
            _put_txn(session, t, rule[1], rule[2], rule[3], "rules", matched.get(t["id"]))
        else:
            m = _merchant(t["description"])
            u = unknown[m]; u["examples"].append(t["amount"])
            if t["id"] in matched:
                u["has_receipt"] = True; u["receipt_items"] = matched[t["id"]]["items"]

    with tracer.start_as_current_span("categorize.llm", attributes=CHAIN) as sp:
        sp.set_attribute("merchants", len(unknown))
        cats = llm.categorize([dict(merchant=m, **v) for m, v in unknown.items()], _profile(session).get("line_of_work", "content creator"))
    for t in txns:
        m = _merchant(t["description"])
        if m in unknown:
            c = cats.get(m)
            if c is None:  # LLM gave nothing for this merchant: claim no deduction, flag for review
                _put_txn(session, t, "personal", None, 0, "llm-guess", matched.get(t["id"]), "no categorization returned")
            elif c.ask_user:  # only the user truly knows: take the best guess, flag it for review on the results page
                _put_txn(session, t, c.category, c.schedule_c_category, c.business_pct, "llm-guess", matched.get(t["id"]), c.why)
            else:
                _put_txn(session, t, c.category, c.schedule_c_category, c.business_pct, "llm", matched.get(t["id"]), c.why)
    return dict(transactions=len(txns), receipts=[{k: r[k] for k in ("file", "confidence", "path", "total", "date")} for r in receipts],
                rules=sum(1 for t in txns if _merchant(t["description"]) not in unknown), llm_merchants=len(unknown),
                documents=len(x.get("docs", [])), inferred=inferred)


def _infer_profile(session: str, docs: list[dict]) -> list[dict]:
    """Checklist answers the documents state outright become facts (by='inferred', citing the file); the rest are asked."""
    if not docs:
        return []
    with tracer.start_as_current_span("profile.infer", attributes=CHAIN) as sp:
        found = llm.infer_profile(docs, dict(CHECKLIST))
        files = {d["file"] for d in docs}
        out = []
        for f in found:
            v = _quick_parse(f.field, f.value) if f.field != "line_of_work" else f.value.strip()
            if v is None or f.source_file not in files or (f.field == "state" and v != "NY") \
                    or (f.field == "filing_status" and v != "single"):
                continue  # unreadable, uncited or out of scope: ask the user instead
            if f.field in NUMERIC:
                v = float(v)
            facts.put(session, f"profile:{f.field}", v, f.source_file, "inferred", f.quote)
            out.append(dict(field=f.field, value=v, source=f.source_file))
        sp.set_attribute("output.value", json.dumps(out))
        return out


def _merchant(desc: str) -> str:
    return re.sub(r"[#*]?\s*\d[\d\s]*$", "", desc).strip()  # drop trailing store numbers / ids so the cache key repeats


def _items(text: str) -> list[str]:
    return [l for l in text.splitlines() if re.search(r"\$\d", l) and not l.lower().startswith("total")][:10]


def _match_receipts(txns, receipts) -> dict:
    """bank txn id -> receipt, by exact amount and date within 3 days."""
    out = {}
    for r in receipts:
        if r.get("total") is None or not r.get("date"):
            continue
        rd = date.fromisoformat(r["date"])
        for t in txns:
            if abs(-t["amount"] - r["total"]) < 0.01 and abs((date.fromisoformat(t["date"]) - rd).days) <= 3:
                out[t["id"]] = r
                break
    return out


def _put_txn(session, t, category, sched_c, pct, by, receipt=None, why=""):
    deductible = round(-t["amount"] * pct / 100, 2) if category == "business_expense" else 0.0
    src = t["source"] + (f" + {receipt['file']}" if receipt else "")
    facts.put(session, f"txn:{t['id']}", dict(date=t["date"], description=t["description"], amount=t["amount"],
              category=category, schedule_c_category=sched_c, business_pct=pct, deductible=deductible), src, by, why)


def _profile(session) -> dict:
    return {k.split(":", 1)[1]: v["value"] for k, v in facts.current(session, "profile:").items()}


def next_question(session: str):
    p = _profile(session)
    for field, hint in CHECKLIST:
        if field not in p:
            return dict(field=field, question=llm.word_question(field, hint))
    return _merchant_question(session)


MAX_MERCHANT_QUESTIONS = 3  # ask only about the biggest guesses; the rest stay flagged for review on the results page


def _merchant_question(session: str):
    if len(facts.current(session, "asked:")) >= MAX_MERCHANT_QUESTIONS:
        return None
    spend = defaultdict(list)
    for k, v in facts.current(session, "txn:").items():
        if v["by"] == "llm-guess" and v["value"]["amount"] < 0:
            spend[_merchant(v["value"]["description"])].append(v["value"])
    if not spend:
        return None
    m, rows = max(spend.items(), key=lambda kv: -sum(r["amount"] for r in kv[1]))
    guess = "business" if rows[0]["category"] == "business_expense" else "personal"
    n, total = len(rows), -sum(r["amount"] for r in rows)
    return dict(field=f"merchant:{m}", question=f"You have {n} charge{'s' if n > 1 else ''} at {m} (${total:,.2f}). "
                f"I guessed {guess}. Was it for your business? (business / personal)")


def answer(session: str, field: str, text: str) -> dict:
    if field.startswith("merchant:"):
        return _answer_merchant(session, field[9:], text)
    hint = dict(CHECKLIST)[field]
    v = _quick_parse(field, text)  # deterministic first; the LLM only sees answers rules can't read
    with tracer.start_as_current_span("answer.parse", attributes=CHAIN) as sp:
        sp.set_attribute("field", field); sp.set_attribute("path", "rules" if v is not None else "llm")
        if v is None:
            a = llm.parse_answer(field, hint, text)
            if not a.ok or a.value is None:
                return dict(ok=False, clarify=a.clarify or "Sorry, could you rephrase that?")
            v = a.value.strip()
    if field in NUMERIC:
        try:
            v = float(v.replace(",", "").replace("$", ""))
        except ValueError:
            return dict(ok=False, clarify="Please give a dollar amount.")
    if field == "state" and v.upper() != "NY":
        return dict(ok=False, unsupported=True, clarify=f"This demo only computes New York (+NYC) estimated taxes; {v} isn't supported yet.")
    if field == "filing_status" and v != "single":
        return dict(ok=False, unsupported=True, clarify="This demo only computes for single filers so far.")
    facts.put(session, f"profile:{field}", v, "chat", "user", text)
    return dict(ok=True)


def _answer_merchant(session: str, merchant: str, text: str) -> dict:
    words = re.findall(r"[a-z]+", text.lower())
    biz = bool(words) and words[0] in ("business", "b", "yes", "y", "work")
    if not words or not (biz or words[0] in ("personal", "p", "no", "n")):
        return dict(ok=False, clarify="Was it business or personal?")
    guessed = [(k, v["value"]) for k, v in facts.current(session, "txn:").items()
               if v["by"] == "llm-guess" and _merchant(v["value"]["description"]) == merchant]
    if guessed:
        k, t = guessed[0]
        pct = (t.get("business_pct") or 100) if biz else 0
        correct(session, k, "business_expense" if biz else "personal", pct, t.get("schedule_c_category"), f"user said: {text}",
                same_merchant=True)
    facts.put(session, f"asked:merchant:{merchant}", "business" if biz else "personal", "chat", "user", text)
    return dict(ok=True)


def _quick_parse(field: str, text: str):
    t = text.strip().lower()
    if field == "in_nyc":
        words = re.findall(r"[a-z]+", t)
        if words and words[0] in ("yes", "y", "yeah", "yep"):
            return "yes"
        if words and words[0] in ("no", "n", "nope"):
            return "no"
    if field in NUMERIC:
        if t in ("none", "no", "zero", "n/a"):
            return "0"
        m = re.fullmatch(r"\$?\s*([\d,]+(?:\.\d+)?)\s*(k)?", t)
        if m:
            return str(float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1))
    if field == "filing_status" and t in ("single", "head of household", "married filing jointly", "married filing separately"):
        return {"head of household": "head_of_household", "married filing jointly": "married_joint",
                "married filing separately": "married_separate"}.get(t, t)
    if field == "state" and t in ("ny", "new york", "new york state"):
        return "NY"
    return None


def correct(session: str, txn_key: str, category: str, pct: int, sched_c: str | None, reason: str,
            same_merchant: bool = False) -> dict:
    """same_merchant: also apply to every other still-guessed transaction at this merchant."""
    txns = facts.current(session, "txn:")
    m = _merchant(txns[txn_key]["value"]["description"])
    keys = [txn_key] + [k for k, v in txns.items() if same_merchant and k != txn_key and v["by"] == "llm-guess"
                        and _merchant(v["value"]["description"]) == m]
    for k in keys:
        cur = txns[k]; old = cur["value"]
        t = dict(id=k[4:], date=old["date"], description=old["description"], amount=old["amount"], source=cur["source"])
        sc = (sched_c or old.get("schedule_c_category") or "Other business expense") if category == "business_expense" else sched_c
        _put_txn(session, t, category, sc, pct, "user", None, reason)
    return dict(history=facts.history(session, txn_key), updated=len(keys))


def _label(t: dict) -> str:
    return f'business {t["business_pct"]}%' if t["category"] == "business_expense" else t["category"].replace("_", " ")


def _guessed_rows(txns: dict) -> list[dict]:
    return [dict(key=k, source=v["source"], by=v["by"], amount=v["value"]["amount"], merchant=_merchant(v["value"]["description"]),
                 description=f'{v["value"]["description"]} · guessed {_label(v["value"])}')
            for k, v in txns.items() if v["by"] == "llm-guess"]


def review(session: str) -> dict:
    """Everything the computation will use, for the user to confirm before any tax math runs."""
    txns = facts.current(session, "txn:")
    vals = [v["value"] for v in txns.values()]
    return dict(profile=[dict(field=k.split(":", 1)[1], value=v["value"], source=v["source"], by=v["by"])
                         for k, v in facts.current(session, "profile:").items()],
                guessed=_guessed_rows(txns),
                gross_income=round(sum(t["amount"] for t in vals if t["category"] == "income"), 2),
                deductible_expenses=round(sum(t["deductible"] for t in vals if t["category"] == "business_expense"), 2),
                transactions=len(vals))


def results(session: str, as_of: date | None = None) -> dict:
    p = _profile(session)
    txns = {k: v for k, v in facts.current(session, "txn:").items()}
    by = lambda cat: [(k, v) for k, v in txns.items() if v["value"]["category"] == cat]
    income = by("income"); expenses = [(k, v) for k, v in by("business_expense") if v["value"]["deductible"] > 0]
    pay = by("tax_payment")
    paid_fed = [(k, v) for k, v in pay if "IRS" in v["value"]["description"]]
    paid_ny = [(k, v) for k, v in pay if "NYS" in v["value"]["description"]]
    s = lambda rows, f: round(sum(f(v["value"]) for _, v in rows), 2)
    inputs = dict(gross_income=s(income, lambda x: x["amount"]), deductible_expenses=s(expenses, lambda x: x["deductible"]),
                  prior_fed_tax=p["prior_fed_tax"], prior_fed_agi=p["prior_fed_agi"], prior_ny_tax=p["prior_ny_tax"],
                  prior_ny_agi=p["prior_fed_agi"],  # NYAGI ~= federal AGI for this filer profile
                  paid_fed=s(paid_fed, lambda x: -x["amount"]), paid_ny=s(paid_ny, lambda x: -x["amount"]),
                  in_nyc=str(p.get("in_nyc", "yes")).lower().startswith("y"))
    with tracer.start_as_current_span("engine.compute", attributes={**TOOL, "input.value": json.dumps(inputs)}) as sp:
        r = sandbox.compute(inputs, as_of or date.today())
        sp.set_attribute("output.value", json.dumps(r))
    src = lambda rows: [dict(key=k, source=v["source"], by=v["by"], amount=v["value"].get("deductible") or v["value"]["amount"],
                             description=v["value"]["description"]) for k, v in rows]
    by_cat = defaultdict(float)
    for _, v in expenses:
        by_cat[v["value"].get("schedule_c_category") or "Other"] += v["value"]["deductible"]
    r.update(inputs=inputs, expense_by_category={k: round(v, 2) for k, v in by_cat.items()},
             sources=dict(gross_income=src(income), deductible_expenses=src(expenses), paid_fed=src(paid_fed), paid_ny=src(paid_ny),
                          review=_guessed_rows(txns)),
             pay_links=dict(federal="https://www.irs.gov/payments/direct-pay", ny="https://www.tax.ny.gov/pay/"),
             computed_at=datetime.now().isoformat(timespec="seconds"))
    return r
