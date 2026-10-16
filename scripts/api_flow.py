"""Drive the running server end to end over HTTP: upload, answer the checklist, results, eval, one correction."""
import json, sys, time, urllib.request, uuid

BASE = "http://localhost:8000"
ANSWERS = {"state": "New York", "in_nyc": "yes, Brooklyn", "filing_status": "single", "line_of_work": "YouTube and TikTok content creator",
           "prior_fed_tax": "$18,000", "prior_fed_agi": "about 100k", "prior_ny_tax": "6500"}


BRAND_MEALS = ("LILIA", "VIA CAROTA", "CARBONE", "THE SMILE", "LE CRAFT", "SUNDAY IN BKLYN")  # Maya's real brand meetings


def _merchant_answer(field):
    return "yes, brand meeting" if any(m in field for m in BRAND_MEALS) else "no, that's personal"


def call(method, path, body=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": ctype} if data else {})
    return json.loads(urllib.request.urlopen(req, timeout=600).read())


b = uuid.uuid4().hex
zipb = open("demo/maya/upload.zip", "rb").read()
form = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"upload.zip\"\r\nContent-Type: application/zip\r\n\r\n").encode() + zipb + f"\r\n--{b}--\r\n".encode()
t = time.time()
up = call("POST", "/api/upload", raw=form, ctype=f"multipart/form-data; boundary={b}")
s = up["session"]
print(f"upload {time.time()-t:.0f}s session={s}", json.dumps({k: v for k, v in up["summary"].items() if k != "receipts"}))
print("vision:", [r["file"] for r in up["summary"]["receipts"] if r["path"] == "vision"])
q = up["next"]
while q:
    r = call("POST", "/api/answer", {"session": s, "field": q["field"], "text": ANSWERS.get(q["field"], _merchant_answer(q["field"]))})
    print(f"Q {q['field']}: ok={r['ok']} | {q['question'][:110]}")
    if not r["ok"]:
        sys.exit(f"stuck: {r}")
    q = r["next"]
res = call("GET", f"/api/results/{s}")
print("federal", json.dumps(res["federal"]), "\nny", json.dumps(res["ny"]), "\ninputs", json.dumps(res["inputs"]))
ev = call("POST", f"/api/eval/{s}")
print("eval", json.dumps({k: v for k, v in ev.items() if k != "misses"}))
for m in ev["misses"]:
    print("  miss", m)
if "--correct" in sys.argv and ev["misses"]:
    m = next(x for x in ev["misses"] if x["want"][0] == "business_expense")
    h = call("POST", "/api/correct", {"session": s, "key": f"txn:{m['id']}", "category": "business_expense",
                                     "business_pct": m["want"][1], "schedule_c_category": None, "reason": "demo: client lunch is 50% deductible"})
    print("correction history:", [(x["value"]["category"], x["value"]["business_pct"], x["by"], x["current"]) for x in h["history"]])
    res2 = call("GET", f"/api/results/{s}")
    print("deductible before/after:", res["inputs"]["deductible_expenses"], "->", res2["inputs"]["deductible_expenses"])
