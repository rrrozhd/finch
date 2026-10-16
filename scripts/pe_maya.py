from policyengine_us import Simulation
sim = Simulation(situation={
    "people": {"maya": {"age": {2026: 30}, "self_employment_income": {2026: 95000}}},
    "tax_units": {"tu": {"members": ["maya"]}}, "families": {"f": {"members": ["maya"]}},
    "spm_units": {"s": {"members": ["maya"]}}, "marital_units": {"m": {"members": ["maya"]}},
    "households": {"h": {"members": ["maya"], "state_name": {2026: "NY"}, "in_nyc": {2026: True}}}})
golden = dict(self_employment_tax=13423.07, adjusted_gross_income=88288.46, qualified_business_income_deduction=14437.69,
              taxable_income=57750.77, income_tax=7417.17, ny_income_tax=4170.98, nyc_income_tax_before_credits=2986.98, nyc_income_tax=2986.98)
for k, g in golden.items():
    v = round(float(sim.calculate(k, 2026)[0]), 2)
    print(f"{k:36} engine {v:10,.2f}  golden {g:10,.2f}  delta {v-g:+8.2f}")
