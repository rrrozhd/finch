"""Generate Maya's 2026 mock docs: bank CSV, invoice/receipt PDFs, and a hidden ground-truth labels CSV.

Run: uv run --with reportlab python demo/generate.py
Totals must match DEMO_EXAMPLE.md: gross income $120,000, deductible expenses $25,000.
"""
import csv
import random
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "maya"
DOCS = OUT / "docs"
random.seed(7)

MAYA = ("Maya Chen Studio", "Maya Chen", "212 Bedford Ave, Apt 4R", "Brooklyn, NY 11211")
rows = []  # (date, description, amount, label dict)


def txn(d, desc, amount, category, sched_c="", business_pct=0, deductible=0.0, doc=""):
    rows.append((d, desc, round(amount, 2), dict(category=category, schedule_c_category=sched_c,
                business_pct=business_pct, deductible_amount=round(deductible, 2), doc_ref=doc)))


def pdf(name, title, frm, to, number, d, items, note=""):
    c = canvas.Canvas(str(DOCS / name), pagesize=letter)
    y = 740
    c.setFont("Helvetica-Bold", 20); c.drawString(50, y, title)
    c.setFont("Helvetica", 10)
    c.drawString(400, y, f"No. {number}"); c.drawString(400, y - 14, f"Date: {d:%b %d, %Y}")
    y -= 50
    for label, lines in (("From", frm), ("Bill to", to)):
        c.setFont("Helvetica-Bold", 10); c.drawString(50, y, label)
        c.setFont("Helvetica", 10)
        for i, line in enumerate(lines):
            c.drawString(50, y - 14 * (i + 1), line)
        y -= 14 * (len(lines) + 2)
    c.setFont("Helvetica-Bold", 10); c.drawString(50, y, "Description"); c.drawRightString(560, y, "Amount")
    c.line(50, y - 4, 560, y - 4)
    c.setFont("Helvetica", 10)
    for desc, amt in items:
        y -= 18; c.drawString(50, y, desc); c.drawRightString(560, y, f"${amt:,.2f}")
    c.line(50, y - 8, 560, y - 8)
    c.setFont("Helvetica-Bold", 11); c.drawString(400, y - 24, "Total"); c.drawRightString(560, y - 24, f"${sum(a for _, a in items):,.2f}")
    if note:
        c.setFont("Helvetica-Oblique", 9); c.drawString(50, y - 60, note)
    c.save()


# ---- Income: $30k AdSense + $15k Patreon + $75k brand deals = $120k ----
for m in range(1, 13):
    txn(date(2026, m, 21), "GOOGLE ADSENSE PAYMT", 2500, "income", "Gross receipts")
    txn(date(2026, m, 5), "PATREON PAYOUT", 1250, "income", "Gross receipts")

deals = [  # (brand, invoice date, paid date, amount, deliverable)
    ("Lumen Coffee Co.", date(2026, 2, 3), date(2026, 3, 4), 8000, "Sponsored video integration (60s)"),
    ("Nimbus VPN", date(2026, 3, 16), date(2026, 4, 15), 12500, "Dedicated review video + 2 shorts"),
    ("Kettle & Grain", date(2026, 5, 4), date(2026, 6, 3), 6500, "Instagram reel package (3 reels)"),
    ("Arcwave Audio", date(2026, 6, 22), date(2026, 7, 22), 15000, "Product launch video + usage rights 6 mo"),
    ("Fernway Travel", date(2026, 8, 10), date(2026, 9, 9), 9000, "Travel vlog integration"),
    ("Pillar Notes App", date(2026, 9, 14), date(2026, 10, 14), 4000, "TikTok series (4 posts)"),
    ("Orbit Cameras", date(2026, 10, 26), date(2026, 11, 25), 20000, "Holiday campaign: 2 videos + whitelisting"),
]
for i, (brand, inv_d, paid_d, amt, what) in enumerate(deals, 1):
    doc = f"invoice_MC-2026-{i:03d}_{brand.split()[0].lower()}.pdf"
    pdf(doc, "INVOICE", MAYA, (brand, "Accounts Payable"), f"MC-2026-{i:03d}", inv_d,
        [(what, amt)], "Payment terms: Net 30. ACH to Chase ****4417.")
    txn(paid_d, f"ACH CREDIT {brand.upper()} INV MC-2026-{i:03d}", amt, "income", "Gross receipts", doc=doc)

# ---- Business expenses: deductible total $25,000.00 ----
def receipt(vendor, d, items, desc, sched_c, pct=100, note=""):
    total = sum(a for _, a in items)
    doc = f"receipt_{d:%Y%m%d}_{''.join(ch for ch in vendor.split()[0].lower() if ch.isalnum())}.pdf"
    pdf(doc, "RECEIPT", (vendor,), MAYA[1:2], f"{random.randint(100000, 999999)}", d, items, note)
    txn(d, desc, -total, "business_expense", sched_c, pct, total * pct / 100, doc)

receipt("B&H Photo Video", date(2026, 3, 9), [("Sony A7 IV body", 2498.00), ("Sony FE 24-70mm f/2.8 GM II", 2200.00)],
        "B&H PHOTO 800-606-6969 NY", "Depreciation / Section 179 (equipment)")
receipt("Apple Store SoHo", date(2026, 2, 14), [("MacBook Pro 14-inch M5 Pro", 3499.00)],
        "APPLE STORE #R101 NEW YORK", "Depreciation / Section 179 (equipment)")
receipt("B&H Photo Video", date(2026, 4, 20), [("Aputure Amaran lighting kit", 1150.00)],
        "B&H PHOTO 800-606-6969 NY", "Supplies")
receipt("Sweetwater", date(2026, 5, 11), [("Shure MV7+ microphone x2", 549.00), ("Boom arm", 100.00)],
        "SWEETWATER SOUND", "Supplies")
receipt("Sony Store", date(2026, 3, 9), [("Sony NP-FZ100 batteries x4 + charger", 1400.00)],
        "SONY ELECTRONICS STORE", "Supplies")
receipt("Delta Air Lines", date(2026, 6, 18), [("JFK-LAX round trip, VidCon 2026", 486.00)],
        "DELTA AIR 0062345678901", "Travel")
receipt("Hilton Anaheim", date(2026, 6, 23), [("3 nights, VidCon 2026", 1240.00)],
        "HILTON ANAHEIM", "Travel")
receipt("Amazon.com", date(2026, 8, 2), [("Backdrop paper + stands", 312.24), ("Prop set: desk decor", 238.00)],
        "AMZN MKTP US*2K4", "Supplies")
for q, d in enumerate([date(2026, 3, 31), date(2026, 6, 30), date(2026, 9, 30), date(2026, 12, 15)], 1):
    doc = f"contractor_invoice_Q{q}_jlee.pdf"
    pdf(doc, "INVOICE", ("Jordan Lee Editing LLC", "Queens, NY"), (MAYA[0],), f"JL-{q:02d}", d,
        [(f"Video editing, Q{q} 2026 (12 videos)", 1500.00)])
    txn(d, "ZELLE TO JORDAN LEE EDITING", -1500, "business_expense", "Contract labor", 100, 1500, doc)
meals = [(date(2026, 2, 10), "LILIA BROOKLYN", 186.00), (date(2026, 4, 2), "VIA CAROTA NY", 142.00),
         (date(2026, 5, 20), "CARBONE NEW YORK", 238.00), (date(2026, 7, 9), "THE SMILE NY", 96.00),
         (date(2026, 9, 3), "LE CRAFT NEW YORK", 114.00), (date(2026, 10, 21), "SUNDAY IN BKLYN", 64.00)]
for d, desc, amt in meals:  # brand meetings: 50% deductible, no receipt (agent should ask)
    txn(d, desc, -amt, "business_expense", "Meals (50%)", 50, amt / 2)
for m in range(1, 13):
    txn(date(2026, m, 3), "ADOBE *CREATIVE CLOUD", -69.99, "business_expense", "Software / subscriptions", 100, 69.99)
    txn(date(2026, m, 8), "EPIDEMIC SOUND", -17.99, "business_expense", "Software / subscriptions", 100, 17.99)
    txn(date(2026, m, 12), "GOOGLE *WORKSPACE", -14.00, "business_expense", "Software / subscriptions", 100, 14.00)
    txn(date(2026, m, 18), "VERIZON WIRELESS", -95.00, "business_expense", "Utilities (phone, 60% business)", 60, 57.00)
for m in range(3, 13):
    txn(date(2026, m, 1), "WEWORK 115 BROADWAY", -300.00, "business_expense", "Rent (coworking)", 100, 300.00)

# ---- Personal spending (distractors, deductible 0) ----
for m in range(1, 13):
    txn(date(2026, m, 1), "ZELLE TO BEDFORD MGMT RENT", -3200, "personal")
    txn(date(2026, m, 14), "NETFLIX.COM", -17.99, "personal")
    txn(date(2026, m, 16), "EQUINOX #142", -260.00, "personal")
    txn(date(2026, m, 28), "TRANSFER TO SAVINGS ****9921", -1000, "transfer")
    for _ in range(4):
        txn(date(2026, m, random.randint(1, 28)), random.choice(["WHOLE FOODS #10234", "TRADER JOE'S #558", "KEY FOOD"]),
            -round(random.uniform(35, 140), 2), "personal")
    for _ in range(2):
        txn(date(2026, m, random.randint(1, 28)), random.choice(["UBER *TRIP", "SWEETGREEN", "AMZN MKTP US*7Q1", "DOORDASH*JOES PIZZA"]),
            -round(random.uniform(12, 90), 2), "personal")

# ---- Estimated tax payments already made (Q1-Q3) ----
for d in (date(2026, 4, 15), date(2026, 6, 15), date(2026, 9, 15)):
    txn(d, "IRS USATAXPYMT 1040ES", -4500.00, "tax_payment", "Federal estimated tax")
    txn(d, "NYS DTF PIT EST PAYMT", -1610.54, "tax_payment", "NY State + NYC estimated tax")

# ---- Write files + self-check ----
rows.sort(key=lambda r: (r[0], r[1]))
with open(OUT / "bank_2026_chase_4417.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["transaction_id", "date", "description", "amount", "account"])
    for i, (d, desc, amt, _) in enumerate(rows, 1):
        w.writerow([f"T{i:04d}", d.isoformat(), desc, f"{amt:.2f}", "Chase Total Checking ****4417"])
with open(OUT / "labels_ground_truth.csv", "w", newline="") as f:  # hidden from the agent; for Arize evals
    w = csv.writer(f)
    w.writerow(["transaction_id", "category", "schedule_c_category", "business_pct", "deductible_amount", "doc_ref"])
    for i, (_, _, _, lab) in enumerate(rows, 1):
        w.writerow([f"T{i:04d}", *lab.values()])

income = sum(a for _, _, a, l in rows if l["category"] == "income")
deductible = sum(l["deductible_amount"] for *_, l in rows)
assert round(income, 2) == 120_000.00, income
assert round(deductible, 2) == 25_000.00, deductible
print(f"{len(rows)} transactions, {len(list(DOCS.glob('*.pdf')))} PDFs, income ${income:,.2f}, deductible ${deductible:,.2f}")
