"""Tax computation: PolicyEngine-US for annual liability + the 1040-ES / IT-2105 estimated-payment layer.

No LLM here. Inputs are validated numbers from the fact store.
Payment rules come from forms/f1040es_2026.pdf (worksheet lines 11c-15) and forms/it2105i_2026.pdf.
"""
from datetime import date

YEAR = 2026
DUE = [date(2026, 4, 15), date(2026, 6, 15), date(2026, 9, 15), date(2027, 1, 15)]  # same for IRS and NYS
_sim_cls = None


def warm():
    """Import PolicyEngine once (~25s); call at server startup."""
    global _sim_cls
    if _sim_cls is None:
        from policyengine_us import Simulation
        _sim_cls = Simulation
    return _sim_cls


def annual_liability(net_profit: float, wages: float = 0, other_income: float = 0, in_nyc: bool = True) -> dict:
    sim = warm()(situation={
        "people": {"filer": {"age": {YEAR: 35}, "self_employment_income": {YEAR: net_profit},
                             "employment_income": {YEAR: wages}, "taxable_interest_income": {YEAR: other_income}}},
        "tax_units": {"tu": {"members": ["filer"]}},
        "families": {"f": {"members": ["filer"]}},
        "spm_units": {"s": {"members": ["filer"]}},
        "marital_units": {"m": {"members": ["filer"]}},
        "households": {"h": {"members": ["filer"], "state_name": {YEAR: "NY"}, "in_nyc": {YEAR: in_nyc}}},
    })
    v = lambda name: round(float(sim.calculate(name, YEAR)[0]), 2)
    return {k: v(k) for k in ["self_employment_tax", "adjusted_gross_income", "qualified_business_income_deduction",
                              "taxable_income", "income_tax", "ny_income_tax", "nyc_income_tax"]}


def installments(total_tax: float, prior_year_tax: float, prior_high_income: bool, withholding: float,
                 paid: float, as_of: date, min_owed: float) -> dict:
    """Required annual payment (smaller of 90% current / 100%-or-110% prior) and the next installment due."""
    current_90 = 0.90 * total_tax
    prior = (1.10 if prior_high_income else 1.00) * prior_year_tax
    required = min(current_90, prior)
    still_needed = required - withholding
    if still_needed <= 0 or total_tax - withholding < min_owed:
        return dict(required=round(required, 2), method="none_required", next_due=None, next_amount=0.0,
                    current_90=round(current_90, 2), prior_safe_harbor=round(prior, 2), paid=paid)
    k = next((i for i, d in enumerate(DUE) if d >= as_of), 3)
    cumulative_due = still_needed * (k + 1) / 4  # equal-installment method
    return dict(required=round(required, 2), method="prior_year_safe_harbor" if prior <= current_90 else "90pct_current_year",
                current_90=round(current_90, 2), prior_safe_harbor=round(prior, 2), paid=round(paid, 2),
                next_due=DUE[k].isoformat(), next_amount=round(max(0.0, cumulative_due - paid), 2),
                april_balance=round(total_tax - withholding - still_needed, 2))


def compute(f: dict, as_of: date) -> dict:
    """f: typed inputs from facts (gross_income, deductible_expenses, wages, withholding, other_income,
    prior_fed_tax, prior_fed_agi, prior_ny_tax, prior_ny_agi, paid_fed, paid_ny, in_nyc)."""
    net_profit = f["gross_income"] - f["deductible_expenses"]
    a = annual_liability(net_profit, f.get("wages", 0), f.get("other_income", 0), f.get("in_nyc", True))
    fed_total = a["income_tax"] + a["self_employment_tax"]  # 1040-ES line 11c (no other taxes/credits in scope)
    ny_total = a["ny_income_tax"] + a["nyc_income_tax"]
    fed = installments(fed_total, f["prior_fed_tax"], f["prior_fed_agi"] > 150_000, f.get("withholding", 0),
                       f.get("paid_fed", 0), as_of, 1_000)
    ny = installments(ny_total, f["prior_ny_tax"], f["prior_ny_agi"] > 150_000, f.get("ny_withholding", 0),
                      f.get("paid_ny", 0), as_of, 300)
    notes = []
    if net_profit * 0.9235 > 150_000 and f.get("in_nyc", True):
        notes.append("MCTMT (0.60% on NYC self-employment earnings over $150k) applies and is not computed in this demo.")
    return dict(net_profit=round(net_profit, 2), annual=a, federal_total=round(fed_total, 2),
                ny_total=round(ny_total, 2), federal=fed, ny=ny, notes=notes)


if __name__ == "__main__":  # self-check against DEMO_EXAMPLE.md golden case (Maya)
    r = compute(dict(gross_income=120_000, deductible_expenses=25_000, prior_fed_tax=18_000, prior_fed_agi=100_000,
                     prior_ny_tax=6_500, prior_ny_agi=100_000, paid_fed=13_500, paid_ny=4_831.62), date(2026, 10, 16))
    import json; print(json.dumps(r, indent=1))
    assert r["annual"]["income_tax"] == 7417.17 and r["annual"]["self_employment_tax"] == 13423.07
    assert r["federal"]["required"] == 18_000 and r["federal"]["next_amount"] == 4_500.0
