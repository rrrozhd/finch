"""Build demo/maya/upload.zip: receipt photos (png/jpg, one degraded), brand-deal xlsx, bank CSV. Never the labels.

Run after generate.py: uv run --with pillow --with openpyxl python demo/make_zip.py
"""
import csv
import subprocess
import tempfile
import zipfile
from pathlib import Path

from openpyxl import Workbook
from PIL import Image, ImageFilter

MAYA = Path(__file__).parent / "maya"
ZIP = MAYA / "upload.zip"
DEGRADE = "receipt_20260309_bh"  # the "bad phone photo" that should trip the OCR confidence gate

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    files = []
    for i, pdf in enumerate(sorted((MAYA / "docs").glob("*.pdf"))):
        if pdf.name.startswith("invoice_MC"):
            continue  # Maya's own invoices are summarized in the xlsx instead
        png = tmp / f"{pdf.stem}.png"
        subprocess.run(["pdftoppm", "-r", "150", "-png", "-singlefile", str(pdf), str(png.with_suffix(""))], check=True)
        img = Image.open(png).convert("RGB")
        if pdf.stem == DEGRADE:
            img = img.rotate(7, expand=True, fillcolor="white").filter(ImageFilter.GaussianBlur(3.2))
            img = img.resize((img.width // 3, img.height // 3))
        out = tmp / (f"{pdf.stem}.jpg" if i % 2 else f"{pdf.stem}.png")  # mix of jpg and png like real uploads
        img.save(out, quality=70) if out.suffix == ".jpg" else img.save(out)
        files.append(out)

    wb = Workbook()
    ws = wb.active
    ws.title = "Brand deals 2026"
    ws.append(["Invoice", "Brand", "Paid date", "Amount (USD)"])
    with open(MAYA / "bank_2026_chase_4417.csv") as f:
        for r in csv.DictReader(f):
            if r["description"].startswith("ACH CREDIT"):
                inv = r["description"].split("INV ")[1]
                brand = r["description"].removeprefix("ACH CREDIT ").split(" INV")[0].title()
                ws.append([inv, brand, r["date"], float(r["amount"])])
    xlsx = tmp / "brand_deals_2026.xlsx"
    wb.save(xlsx)
    files += [xlsx, MAYA / "bank_2026_chase_4417.csv"]

    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.name)

names = zipfile.ZipFile(ZIP).namelist()
assert not any("label" in n or n.endswith(".pdf") for n in names), names
assert {Path(n).suffix for n in names} == {".png", ".jpg", ".xlsx", ".csv"}, names
print(f"{ZIP}: {len(names)} files")
for n in names:
    print(" ", n)
