"""Synthetic P&C book for the SI² Fraud Engine.

A clean book (policies, objects, billing, claims, payments, reinsurance) with fraud scenarios seeded on top.
Every seeded scenario is recorded in `truth` so the engine's detection rate can be measured.
All names, numbers and accounts are invented.
"""
from __future__ import annotations

import datetime as dt
import random

import pandas as pd

D = dt.date
FIRST = ["James", "Maria", "Robert", "Linda", "Michael", "Patricia", "David", "Jennifer", "Carlos", "Aisha", "Wei",
         "Priya", "Daniel", "Sofia", "Kevin", "Grace", "Omar", "Elena", "Brian", "Nadia", "Luis", "Hannah", "Raj",
         "Chloe", "Tyrone", "Mei", "Victor", "Fatima", "Sean", "Lucia"]
LAST = ["Smith", "Garcia", "Johnson", "Patel", "Nguyen", "Brown", "Rodriguez", "Lee", "Williams", "Martinez", "Khan",
        "Davis", "Lopez", "Wilson", "Clark", "Singh", "Lewis", "Young", "Walker", "Hall", "Allen", "Rivera", "Moore",
        "Taylor", "Thomas", "Hernandez", "Scott", "Adams", "Baker", "Chen"]
STREETS = ["Palm Ave", "Ocean Dr", "Main St", "Oak St", "Pine Rd", "Bay Blvd", "Cedar Ln", "Lake Dr", "Hill St",
           "Park Ave", "River Rd", "Elm St", "Coral Way", "Sunset Blvd", "Harbor Dr"]
# zip, state, territory, coastal
ZIPS = [("33139", "FL", "Urban", True), ("33125", "FL", "Urban", True), ("33602", "FL", "Urban", True),
        ("32801", "FL", "Urban", False), ("34102", "FL", "Suburban", True), ("32052", "FL", "Rural", False),
        ("32066", "FL", "Rural", False), ("77002", "TX", "Urban", True), ("79843", "TX", "Rural", False),
        ("75201", "TX", "Urban", False), ("10001", "NY", "Urban", True), ("13820", "NY", "Rural", False),
        ("30303", "GA", "Urban", False), ("31512", "GA", "Rural", False), ("90012", "CA", "Urban", True),
        ("93545", "CA", "Rural", False)]
ZIP_INFO = {z: {"state": s, "territory": t, "coastal": c} for z, s, t, c in ZIPS}
INTL = {"CA": [("M5V", "ON", "Urban", False), ("K0K", "ON", "Rural", False)],
        "UK": [("E1", "LDN", "Urban", False), ("LL55", "WLS", "Rural", False)],
        "IN": [("400001", "MH", "Urban", True), ("413001", "MH", "Rural", False)]}
for c, lst in INTL.items():
    for z, s, t, co in lst:
        ZIP_INFO[z] = {"state": s, "territory": t, "coastal": co}
CCY = {"US": "USD", "CA": "CAD", "UK": "GBP", "IN": "INR"}
FX = {"USD": 1.0, "CAD": 0.73, "GBP": 1.27, "INR": 0.012}
LOB_LINE = {"HO": "Personal", "PA": "Personal", "CP": "Commercial", "CA": "Commercial", "WC": "Commercial",
            "GL": "Commercial"}
PRODUCT = {"HO": "HO-3 Homeowners", "PA": "Personal Auto", "CP": "Commercial Property", "CA": "Commercial Auto",
           "WC": "Workers Compensation", "GL": "Commercial General Liability"}
OBJECT = {"HO": "Building", "CP": "Building", "PA": "Vehicle", "CA": "Vehicle", "WC": "Location", "GL": "Location"}
CAUSES = {"HO": ["Wind", "Water", "Fire", "Theft", "Hail"], "CP": ["Wind", "Fire", "Water", "Theft"],
          "PA": ["Collision", "Theft", "Comprehensive", "Bodily Injury"], "CA": ["Collision", "Bodily Injury"],
          "WC": ["Strain", "Fall", "Laceration"], "GL": ["Slip and Fall", "Products"]}
VAL = D(2026, 9, 30)


class G:
    def __init__(self, seed=2026):
        self.r = random.Random(seed)
        self.n = {}

    def id(self, prefix, width=4):
        self.n[prefix] = self.n.get(prefix, 0) + 1
        return f"{prefix}{self.n[prefix]:0{width}d}"

    def name(self):
        return f"{self.r.choice(FIRST)} {self.r.choice(LAST)}"

    def phone(self):
        return f"({self.r.randint(201, 989)}) {self.r.randint(200, 999)}-{self.r.randint(1000, 9999)}"

    def acct(self):
        return f"****{self.r.randint(1000, 9999)}-{self.r.randint(10, 99)}"

    def addr(self, zip_):
        return f"{self.r.randint(100, 9999)} {self.r.choice(STREETS)}, {zip_}"

    def date(self, a: D, b: D) -> D:
        return a + dt.timedelta(days=self.r.randint(0, max(0, (b - a).days)))


def build(seed: int = 2026) -> dict:
    g = G(seed)
    r = g.r
    truth = []

    def label(entity, eid, fraud_id, note):
        truth.append({"entity": entity, "entity_id": eid, "fraud_id": fraud_id, "scenario": note})

    # ------------------------------------------------------------------ people and companies
    employees = []
    for role, n, auth in [("Underwriter", 6, 0), ("Adjuster", 10, 25000), ("Billing clerk", 4, 0)]:
        for _ in range(n):
            employees.append({"emp_id": g.id("E", 3), "name": g.name(), "role": role, "authority_limit": auth,
                              "phone": g.phone(), "address": g.addr(r.choice(ZIPS)[0]), "bank_acct": g.acct()})
    emp = pd.DataFrame(employees)
    uw = list(emp[emp.role == "Underwriter"].emp_id)
    adj = list(emp[emp.role == "Adjuster"].emp_id)
    clerks = list(emp[emp.role == "Billing clerk"].emp_id)

    agents = pd.DataFrame([{"agent_id": g.id("AG", 2), "name": f"{r.choice(LAST)} Insurance Agency",
                            "country": "US", "state": s, "bank_acct": g.acct()} for s in
                           ["FL", "FL", "FL", "TX", "NY", "GA", "CA", "FL"]])
    vend_types = ["Roofer", "Water mitigation", "Body shop", "Body shop", "Tow", "Medical clinic", "Medical clinic",
                  "Restoration", "Public adjuster", "Roofer", "Restoration", "Water mitigation", "Restoration"]
    vendors = pd.DataFrame([{"vendor_id": g.id("V", 2), "name": f"{r.choice(LAST)} {t}", "vendor_type": t,
                             "phone": g.phone(), "address": g.addr(r.choice(ZIPS)[0]), "bank_acct": g.acct()}
                            for t in vend_types])
    attorneys = pd.DataFrame([{"attorney_id": g.id("AT", 2), "name": g.name(), "firm": f"{r.choice(LAST)} Law"}
                              for _ in range(6)])

    # ------------------------------------------------------------------ policies and objects
    parties, policies, objects, external = [], [], [], []

    def new_party(zip_, country="US"):
        p = {"party_id": g.id("PT"), "name": g.name(), "phone": g.phone(), "email": "", "address": g.addr(zip_),
             "zip": zip_, "country": country, "bank_acct": g.acct()}
        p["email"] = p["name"].lower().replace(" ", ".") + f"{r.randint(1, 99)}@example.com"
        parties.append(p)
        return p

    lob_mix = ["HO"] * 40 + ["PA"] * 35 + ["CP"] * 10 + ["CA"] * 5 + ["WC"] * 7 + ["GL"] * 3
    for i in range(420):
        country = "US" if i < 360 else r.choice(["CA", "UK", "IN"])
        lob = r.choice(lob_mix) if country == "US" else r.choice(["HO", "PA"])
        if country == "US":
            zip_, state, _, _ = r.choice(ZIPS if lob != "HO" else [z for z in ZIPS if z[1] in ("FL", "TX", "NY", "GA", "CA")])
        else:
            zip_, state, _, _ = r.choice(INTL[country])
        p = new_party(zip_, country)
        eff = g.date(D(2025, 1, 1), D(2026, 6, 30))
        limit = {"HO": r.choice([250000, 350000, 500000]), "CP": r.choice([1000000, 2500000]),
                 "PA": r.choice([25000, 50000, 100000]), "CA": 1000000, "WC": 1000000, "GL": 1000000}[lob]
        ded = {"HO": r.choice([1000, 2500, 5000]), "CP": r.choice([5000, 10000]), "PA": r.choice([500, 1000]),
               "CA": 1000, "WC": 0, "GL": 0}[lob]
        prem = round({"HO": r.uniform(2500, 9000) if state == "FL" else r.uniform(1200, 3500),
                      "PA": r.uniform(900, 2600), "CP": r.uniform(8000, 40000), "CA": r.uniform(6000, 20000),
                      "WC": r.uniform(5000, 30000), "GL": r.uniform(3000, 15000)}[lob], 2)
        pol = {"policy_id": g.id("POL", 5), "country": country, "currency": CCY[country], "state": state,
               "line": LOB_LINE[lob], "lob": lob, "product": PRODUCT[lob], "insured_party": p["party_id"],
               "agent_id": r.choice(list(agents.agent_id)) if country == "US" else "",
               "underwriter_id": r.choice(uw), "issue_date": eff - dt.timedelta(days=r.randint(3, 30)),
               "eff_date": eff, "exp_date": eff + dt.timedelta(days=365), "premium": prem, "limit": limit,
               "deductible": ded, "aggregate_deductible": 50000 if lob == "CP" else 0,
               "risk_zip": zip_, "mailing_zip": zip_, "status": "In force", "cancel_date": None,
               "issued_by": "System", "rate_override_pct": 0.0, "usage": "Owner occupied" if lob == "HO" else "",
               "sprinkler_declared": (lob == "CP" and r.random() < 0.6), "prior_claims_declared": 0,
               "drivers": p["party_id"] if lob in ("PA", "CA") else "", "coverage_change_date": None,
               "prior_limit": None}
        policies.append(pol)
        ob = {"object_id": g.id("OBJ", 5), "policy_id": pol["policy_id"], "object_type": OBJECT[lob],
              "description": "", "value": 0, "year": 0, "zip": zip_}
        if OBJECT[lob] == "Building":
            ob["year"] = r.randint(1975, 2022)
            ob["roof_year"] = r.randint(max(ob["year"], 2000), 2024)
            ob["value"] = limit
            ob["description"] = f"{'Dwelling' if lob == 'HO' else 'Commercial building'} built {ob['year']}"
        elif OBJECT[lob] == "Vehicle":
            ob["year"] = r.randint(2012, 2026)
            ob["value"] = r.randint(8000, 60000)
            ob["description"] = f"{ob['year']} {r.choice(['Sedan', 'SUV', 'Pickup', 'Van'])} VIN …{r.randint(10000, 99999)}"
        else:
            ob["description"] = f"Operations at {zip_}"
            ob["value"] = 0
        objects.append(ob)
        external.append({"policy_id": pol["policy_id"], "str_listing_found": False,
                         "inspection_sprinkler": pol["sprinkler_declared"] if lob == "CP" else None,
                         "prior_claims_found": 0, "roof_condition_at_inspection": "Good" if lob in ("HO", "CP") else "",
                         "employer_termination_date": None})

    pol = pd.DataFrame(policies)
    obj = pd.DataFrame(objects)
    ext = pd.DataFrame(external)
    ext.index = ext.policy_id
    obj["roof_year"] = obj.get("roof_year")

    # ------------------------------------------------------------------ premium billing
    payments, refunds, bank_changes = [], [], []
    for p in policies:
        via_agent = p["agent_id"] != "" and r.random() < 0.35
        payer = next(x for x in parties if x["party_id"] == p["insured_party"])
        d0 = p["issue_date"] + dt.timedelta(days=r.randint(0, 10))
        payments.append({"payment_id": g.id("PAY", 5), "policy_id": p["policy_id"], "date": d0,
                         "amount": p["premium"], "method": r.choice(["ACH", "Card", "Check"]),
                         "payer_acct": payer["bank_acct"], "status": "Cleared",
                         "collected_by_agent": p["agent_id"] if via_agent else "",
                         "remitted_date": d0 + dt.timedelta(days=r.randint(3, 20)) if via_agent else None})

    # ------------------------------------------------------------------ cat events
    cat = pd.DataFrame([
        {"event_id": "CAT-25-HU1", "peril": "Wind", "date": D(2025, 9, 24), "zips": "33139,33125,34102,33602"},
        {"event_id": "CAT-26-HL1", "peril": "Hail", "date": D(2026, 4, 12), "zips": "75201,77002,30303"},
        {"event_id": "CAT-26-HU2", "peril": "Wind", "date": D(2026, 8, 30), "zips": "33602,34102,32801"},
    ])

    # ------------------------------------------------------------------ clean claims
    claims, cpays, invoices = [], [], []
    pol_idx = {p["policy_id"]: p for p in policies}
    obj_by_pol = {o["policy_id"]: o for o in objects}

    def add_claim(p, loss, cause, claimant=None, adjuster=None, reserve=None, attorney="", atty_date=None,
                  contents=0.0, report_lag=None, desc="", status="Open", cat_event=""):
        c = {"claim_id": g.id("CLM", 5), "policy_id": p["policy_id"], "object_id": obj_by_pol[p["policy_id"]]["object_id"],
             "country": p["country"], "currency": p["currency"], "lob": p["lob"], "loss_date": loss,
             "report_date": loss + dt.timedelta(days=report_lag if report_lag is not None else r.randint(0, 6)),
             "cause": cause, "claimant_party": claimant or p["insured_party"], "adjuster_id": adjuster or r.choice(adj),
             "reserve": reserve if reserve is not None else round(r.uniform(2000, 30000), 2),
             "attorney_id": attorney, "attorney_date": atty_date, "contents_claimed": contents,
             "adjuster_estimate": 0.0, "description": desc or f"{cause} loss", "status": status,
             "cat_event": cat_event, "driver_party": ""}
        claims.append(c)
        return c

    def pay(c, amount, payee_type="Insured", payee_id=None, acct=None, coverage="Primary", ded_applied=True,
            approved_by=None, date=None, invoice=""):
        p = pol_idx[c["policy_id"]]
        if payee_type == "Insured":
            payee_id = payee_id or c["claimant_party"]
            acct = acct or next(x for x in parties if x["party_id"] == payee_id)["bank_acct"]
        cp = {"cpay_id": g.id("CP", 5), "claim_id": c["claim_id"], "date": date or c["report_date"] + dt.timedelta(days=r.randint(10, 60)),
              "payee_type": payee_type, "payee_id": payee_id, "payee_acct": acct, "amount": round(amount, 2),
              "coverage": coverage, "deductible_applied": p["deductible"] if ded_applied else 0,
              "approved_by": approved_by or c["adjuster_id"], "invoice_no": invoice}
        cpays.append(cp)
        return cp

    clean_pols = [p for p in policies]
    r.shuffle(clean_pols)
    for p in clean_pols[:230]:
        loss = g.date(p["eff_date"] + dt.timedelta(days=20), min(p["exp_date"], VAL) - dt.timedelta(days=5))
        if loss <= p["eff_date"]:
            continue
        cause = r.choice(CAUSES[p["lob"]])
        evt = ""
        if cause in ("Wind", "Hail"):
            ev = cat[(cat.peril == cause)]
            ev = ev[ev.zips.str.contains(p["risk_zip"])]
            if len(ev):
                e = ev.iloc[r.randrange(len(ev))]
                loss, evt = e.date, e.event_id
                if not (p["eff_date"] <= loss <= p["exp_date"]):
                    cause, evt = "Water", ""
                    loss = g.date(p["eff_date"] + dt.timedelta(days=20), min(p["exp_date"], VAL) - dt.timedelta(days=5))
            else:
                cause = "Water" if p["lob"] in ("HO", "CP") else cause
        c = add_claim(p, loss, cause, cat_event=evt)
        gross = round(min(r.uniform(1500, 40000), p["limit"] * 0.5), 2)
        c["adjuster_estimate"] = gross
        net = max(gross - p["deductible"], 0)
        if net > 0 and loss < VAL - dt.timedelta(days=40):
            if p["lob"] in ("HO", "CP") and r.random() < 0.5:
                v = vendors.loc[r.choice(list(vendors[vendors.vendor_type.isin(["Roofer", "Water mitigation", "Restoration"])].index))]
                inv = f"INV-{r.randint(10000, 99999)}"
                invoices.append({"invoice_no": inv, "vendor_id": v.vendor_id, "claim_id": c["claim_id"],
                                 "amount": gross, "date": c["report_date"] + dt.timedelta(days=r.randint(5, 20))})
                pay(c, net, "Vendor", v.vendor_id, v.bank_acct, invoice=inv)
            elif p["lob"] in ("PA", "CA") and r.random() < 0.5:
                v = vendors.loc[r.choice(list(vendors[vendors.vendor_type == "Body shop"].index))]
                inv = f"INV-{r.randint(10000, 99999)}"
                invoices.append({"invoice_no": inv, "vendor_id": v.vendor_id, "claim_id": c["claim_id"],
                                 "amount": gross, "date": c["report_date"] + dt.timedelta(days=r.randint(5, 20))})
                pay(c, net, "Vendor", v.vendor_id, v.bank_acct, invoice=inv)
            else:
                pay(c, net)
            c["status"] = "Closed" if r.random() < 0.6 else "Open"
            c["reserve"] = 0.0 if c["status"] == "Closed" else c["reserve"]

    party_df = lambda: pd.DataFrame(parties)  # noqa: E731

    def pick(lob=None, country="US", state=None, used=set()):
        cand = [p for p in policies if p["country"] == country and (lob is None or p["lob"] in lob)
                and (state is None or p["state"] == state) and p["policy_id"] not in used
                and not any(c["policy_id"] == p["policy_id"] for c in claims)]
        p = r.choice(cand)
        used.add(p["policy_id"])
        return p

    # ------------------------------------------------------------------ seeded fraud: policy & underwriting
    for _ in range(3):   # FR-P01 rate evasion: rural garaging, urban life
        p = pick(("PA",))
        p["risk_zip"] = r.choice(["32052", "79843", "13820", "31512"])
        p["mailing_zip"] = r.choice(["33125", "77002", "10001", "30303"])
        c = add_claim(p, g.date(p["eff_date"] + dt.timedelta(days=40), min(p["exp_date"], VAL)), "Collision")
        c["description"] = f"Collision near {p['mailing_zip']}"
        c["loss_zip"] = p["mailing_zip"]
        label("policy", p["policy_id"], "FR-P01", "Garaged in a rural ZIP, mailing and loss location urban")
    for _ in range(3):   # FR-P02 STR misrepresentation
        p = pick(("HO",))
        ext.loc[p["policy_id"], "str_listing_found"] = True
        label("policy", p["policy_id"], "FR-P02", "Declared owner occupied; short-term rental listing found")
    for _ in range(2):   # FR-P03 sprinkler misrepresentation
        p = pick(("CP",))
        p["sprinkler_declared"] = True
        ext.loc[p["policy_id"], "inspection_sprinkler"] = False
        label("policy", p["policy_id"], "FR-P03", "Sprinkler declared; inspection found none")
    for _ in range(3):   # FR-P04 concealed prior losses
        p = pick(("HO", "PA"))
        ext.loc[p["policy_id"], "prior_claims_found"] = r.randint(2, 4)
        label("policy", p["policy_id"], "FR-P04", "Declared no prior claims; loss history shows several")
    for _ in range(2):   # FR-P05 undisclosed driver (fronting)
        p = pick(("PA", "CA"))
        driver = new_party(p["risk_zip"])
        for k in range(2):
            c = add_claim(p, g.date(p["eff_date"] + dt.timedelta(days=30), min(p["exp_date"], VAL)), "Collision")
            c["driver_party"] = driver["party_id"]
        label("policy", p["policy_id"], "FR-P05", "Claims keep naming a driver who is not on the policy")
    # FR-I01 ghost policy issued by underwriter + ghost claim
    for _ in range(2):
        u = emp[emp.emp_id == r.choice(uw)].iloc[0]
        p = pick(("HO",), state="FL")
        insured = next(x for x in parties if x["party_id"] == p["insured_party"])
        insured["phone"], insured["bank_acct"] = u.phone, u.bank_acct
        p["issued_by"], p["underwriter_id"] = "Manual", u.emp_id
        payments[:] = [x for x in payments if x["policy_id"] != p["policy_id"]]
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=r.randint(15, 40)), "Water", reserve=0)
        pay(c, r.uniform(18000, 24000))
        c["status"] = "Closed"
        label("policy", p["policy_id"], "FR-I01", f"Manual issue by {u.emp_id}; insured shares the underwriter's phone and bank; no premium; quick claim")
        label("claim", c["claim_id"], "FR-I01", "Claim on a ghost policy")
    for _ in range(3):   # FR-P06 backdated coverage: bound after the loss
        p = pick(("HO", "PA"))
        loss = p["eff_date"] + dt.timedelta(days=r.randint(1, 5))
        p["issue_date"] = loss + dt.timedelta(days=r.randint(2, 6))
        c = add_claim(p, loss, r.choice(CAUSES[p["lob"]]), report_lag=r.randint(8, 12))
        label("claim", c["claim_id"], "FR-P06", "Policy issued after the loss date, with the effective date backdated")
    for _ in range(4):   # FR-I02 underwriter rate overrides for one agent
        p = pick(("HO", "CP"))
        p["agent_id"], p["underwriter_id"], p["rate_override_pct"] = "AG03", uw[1], -round(r.uniform(25, 40), 1)
        label("policy", p["policy_id"], "FR-I02", f"Large rate override by {uw[1]} concentrated on agent AG03")

    # ------------------------------------------------------------------ seeded fraud: billing
    for _ in range(3):   # FR-B01 premium diversion
        p = pick(("HO", "PA", "CP"))
        x = next(x for x in payments if x["policy_id"] == p["policy_id"])
        x["collected_by_agent"], x["remitted_date"] = p["agent_id"] or "AG05", None
        x["date"] = VAL - dt.timedelta(days=r.randint(45, 120))
        label("policy", p["policy_id"], "FR-B01", "Agent collected premium and never remitted it")
    for _ in range(2):   # FR-B02 refund to a different account, after bank change by clerk
        p = pick(("HO", "PA"))
        clerk = r.choice(clerks)
        new_acct = g.acct()
        bank_changes.append({"entity": "party", "entity_id": p["insured_party"], "date": VAL - dt.timedelta(days=12),
                             "old_acct": next(x for x in parties if x["party_id"] == p["insured_party"])["bank_acct"],
                             "new_acct": new_acct, "changed_by": clerk})
        p["status"], p["cancel_date"] = "Cancelled", VAL - dt.timedelta(days=10)
        refunds.append({"refund_id": g.id("RF", 4), "policy_id": p["policy_id"], "date": VAL - dt.timedelta(days=9),
                        "amount": round(p["premium"] * 0.6, 2), "to_acct": new_acct, "approved_by": clerk})
        label("policy", p["policy_id"], "FR-B02", f"Bank account changed and refund approved by the same clerk {clerk}")
    for _ in range(2):   # FR-B03 premium charged back after the claim is paid
        p = pick(("PA", "HO"))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=r.randint(25, 60)), r.choice(CAUSES[p["lob"]]))
        cp = pay(c, r.uniform(6000, 12000))
        x = next(x for x in payments if x["policy_id"] == p["policy_id"])
        x["status"], x["method"] = "Chargeback", "Card"
        x["chargeback_date"] = cp["date"] + dt.timedelta(days=r.randint(3, 15))
        label("policy", p["policy_id"], "FR-B03", "Card premium charged back after the claim was paid")

    # ------------------------------------------------------------------ seeded fraud: claims
    for _ in range(3):   # FR-C01 loss outside the policy period
        p = pick(("HO", "PA", "CP"))
        c = add_claim(p, p["eff_date"] - dt.timedelta(days=r.randint(5, 40)), r.choice(CAUSES[p["lob"]]))
        label("claim", c["claim_id"], "FR-C01", "Loss date before the policy started")
    for _ in range(2):   # FR-C02 loss after cancellation
        p = pick(("HO", "PA"))
        p["status"], p["cancel_date"] = "Cancelled", p["eff_date"] + dt.timedelta(days=90)
        c = add_claim(p, min(p["cancel_date"] + dt.timedelta(days=r.randint(5, 30)), VAL - dt.timedelta(days=3)),
                      r.choice(CAUSES[p["lob"]]))
        label("claim", c["claim_id"], "FR-C02", "Loss after the policy was cancelled")
    for _ in range(3):   # FR-C03 paid beyond limit
        p = pick(("PA",))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=60), "Collision")
        pay(c, p["limit"] * 0.7)
        pay(c, p["limit"] * 0.6)
        label("claim", c["claim_id"], "FR-C03", "Payments exceed the coverage limit")
    for _ in range(3):   # FR-C04 deductible not applied
        p = pick(("HO", "CP"))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=80), "Water")
        c["adjuster_estimate"] = 15000.0
        pay(c, 15000.0, ded_applied=False)
        label("claim", c["claim_id"], "FR-C04", "Full estimate paid; deductible never applied")
    for _ in range(2):   # FR-C05 duplicate claim on two policies
        p1, p2 = pick(("HO",)), pick(("HO",))
        o1 = obj_by_pol[p1["policy_id"]]
        o2 = obj_by_pol[p2["policy_id"]]
        o2["description"], o2["zip"] = o1["description"], o1["zip"]
        same_party = next(x for x in parties if x["party_id"] == p1["insured_party"])
        p2["insured_party"] = same_party["party_id"]
        loss = max(p1["eff_date"], p2["eff_date"]) + dt.timedelta(days=30)
        c1 = add_claim(p1, loss, "Theft", contents=12000)
        c2 = add_claim(p2, loss, "Theft", contents=12000)
        label("claim", c2["claim_id"], "FR-C05", f"Same loss also claimed on {c1['claim_id']}")
    for _ in range(2):   # FR-C06 duplicate vendor invoice
        p = pick(("HO", "CP"))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=50), "Water")
        v = vendors[vendors.vendor_type == "Water mitigation"].iloc[0]
        inv = f"INV-{r.randint(10000, 99999)}"
        invoices.append({"invoice_no": inv, "vendor_id": v.vendor_id, "claim_id": c["claim_id"], "amount": 8400.0,
                         "date": c["report_date"] + dt.timedelta(days=7)})
        pay(c, 8400 - p["deductible"], "Vendor", v.vendor_id, v.bank_acct, invoice=inv)
        pay(c, 8400 - p["deductible"], "Vendor", v.vendor_id, v.bank_acct, invoice=inv,
            date=c["report_date"] + dt.timedelta(days=40))
        label("claim", c["claim_id"], "FR-C06", "Same vendor invoice paid twice")
    storm = D(2026, 8, 30)
    for _ in range(3):   # FR-C07 deductible absorbed by contractor (estimate inflated by the deductible)
        cand = [x for x in policies if x["lob"] == "HO" and x["risk_zip"] in ("33602", "34102", "32801")
                and x["eff_date"] <= storm <= x["exp_date"] and not any(c["policy_id"] == x["policy_id"] for c in claims)]
        p = r.choice(cand)
        c = add_claim(p, storm, "Wind", cat_event="CAT-26-HU2")
        est = round(r.uniform(9000, 16000), 2)
        c["adjuster_estimate"] = est
        v = vendors[vendors.vendor_type == "Roofer"].iloc[1]
        inv = f"INV-{r.randint(10000, 99999)}"
        invoices.append({"invoice_no": inv, "vendor_id": v.vendor_id, "claim_id": c["claim_id"],
                         "amount": est + p["deductible"], "date": c["report_date"] + dt.timedelta(days=9)})
        label("claim", c["claim_id"], "FR-C07", "Roofer invoice = adjuster estimate + deductible (deductible waived)")
    # FR-C08 staged-accident ring: shared phone/address, same attorney and body shop
    ring_phone, ring_addr = g.phone(), g.addr("33125")
    shop = vendors[vendors.vendor_type == "Body shop"].iloc[0]
    for k in range(5):
        p = pick(("PA",), state="FL")
        claimant = new_party("33125")
        claimant["phone"] = ring_phone if k % 2 == 0 else claimant["phone"]
        claimant["address"] = ring_addr if k % 2 == 1 else claimant["address"]
        loss = D(2026, 3, 1) + dt.timedelta(days=k * 9)
        c = add_claim(p, max(loss, p["eff_date"] + dt.timedelta(days=10)), "Bodily Injury", claimant=claimant["party_id"],
                      attorney="AT01", reserve=round(r.uniform(18000, 45000), 2))
        c["attorney_date"] = c["loss_date"] + dt.timedelta(days=1)
        c["description"] = "Rear-end at intersection; sudden stop by lead vehicle"
        inv = f"INV-{r.randint(10000, 99999)}"
        invoices.append({"invoice_no": inv, "vendor_id": shop.vendor_id, "claim_id": c["claim_id"],
                         "amount": round(r.uniform(6000, 9000), 2), "date": c["report_date"] + dt.timedelta(days=5)})
        clinic = vendors[vendors.vendor_type == "Medical clinic"].iloc[0]
        invoices.append({"invoice_no": f"MED-{r.randint(10000, 99999)}", "vendor_id": clinic.vendor_id,
                         "claim_id": c["claim_id"], "amount": round(r.uniform(9000, 15000), 2),
                         "date": c["report_date"] + dt.timedelta(days=12)})
        label("claim", c["claim_id"], "FR-C08", "Staged-accident ring: shared phone or address, same attorney, body shop and clinic")
    for _ in range(3):   # FR-C10 wind claim with no storm on record; old roof already damaged
        p = pick(("HO",), state="FL")
        o = obj_by_pol[p["policy_id"]]
        o["roof_year"] = r.randint(1998, 2003)
        ext.loc[p["policy_id"], "roof_condition_at_inspection"] = "Damaged"
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=r.randint(30, 120)), "Wind", reserve=round(r.uniform(25000, 60000), 2))
        c["description"] = "Roof damaged by hurricane winds"
        label("claim", c["claim_id"], "FR-C10", "Wind claim on a date and ZIP with no storm; roof was already damaged at inspection")
    for _ in range(2):   # FR-C11 arson for profit pattern
        p = pick(("CP", "HO"))
        p["prior_limit"] = p["limit"]
        p["limit"] = int(p["limit"] * 1.6)
        p["coverage_change_date"] = p["eff_date"] + dt.timedelta(days=60)
        x = next(x for x in payments if x["policy_id"] == p["policy_id"])
        x["status"] = "NSF"
        c = add_claim(p, p["coverage_change_date"] + dt.timedelta(days=r.randint(20, 50)), "Fire",
                      reserve=round(p["limit"] * 0.8, 2))
        c["description"] = "Total fire loss; building vacant at the time"
        label("claim", c["claim_id"], "FR-C11", "Limit raised 60% weeks before a total fire; premium payment bounced; vacant")
    for _ in range(3):   # FR-C12 inflated contents
        p = pick(("HO",))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=100), "Theft", contents=round(p["limit"] * r.uniform(0.32, 0.45), 2))
        label("claim", c["claim_id"], "FR-C12", "Contents claimed far above typical share of the dwelling limit")
    for _ in range(2):   # FR-C14 ghost claim: payee account belongs to the adjuster
        p = pick(("HO", "PA"))
        a = emp[emp.emp_id == r.choice(adj)].iloc[0]
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=70), r.choice(CAUSES[p["lob"]]), adjuster=a.emp_id)
        pay(c, r.uniform(7000, 14000), "Insured", p["insured_party"], a.bank_acct)
        label("claim", c["claim_id"], "FR-I03", f"Claim payment sent to adjuster {a.emp_id}'s bank account")
    for _ in range(2):   # FR-I04 split payments under authority
        p = pick(("HO", "CP"))
        a = emp[emp.emp_id == r.choice(adj)].iloc[0]
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=90), "Water", adjuster=a.emp_id, reserve=60000)
        d0 = c["report_date"] + dt.timedelta(days=20)
        for _k in range(3):
            pay(c, round(r.uniform(23500, 24900), 2), date=d0)
        label("claim", c["claim_id"], "FR-I04", f"Three same-day payments just under {a.emp_id}'s $25,000 authority")
    # FR-I05 adjuster steering to one vendor
    steer_adj = adj[4]
    rest = vendors[vendors.vendor_type == "Restoration"].iloc[0]
    for _ in range(9):
        p = pick(("HO", "CP"))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=r.randint(30, 150)), "Water", adjuster=steer_adj)
        inv = f"INV-{r.randint(10000, 99999)}"
        amt = round(r.uniform(12000, 19000), 2)
        invoices.append({"invoice_no": inv, "vendor_id": rest.vendor_id, "claim_id": c["claim_id"], "amount": amt,
                         "date": c["report_date"] + dt.timedelta(days=6)})
        pay(c, amt - p["deductible"], "Vendor", rest.vendor_id, rest.bank_acct, invoice=inv)
        label("claim", c["claim_id"], "FR-I05", f"Adjuster {steer_adj} sends nearly every job to {rest.vendor_id}")
    for _ in range(2):   # FR-C15 payee bank account changed just before payment
        p = pick(("HO",))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=60), "Water")
        new_acct = g.acct()
        d = c["report_date"] + dt.timedelta(days=25)
        bank_changes.append({"entity": "party", "entity_id": p["insured_party"], "date": d - dt.timedelta(days=1),
                             "old_acct": next(x for x in parties if x["party_id"] == p["insured_party"])["bank_acct"],
                             "new_acct": new_acct, "changed_by": "Web portal"})
        pay(c, r.uniform(9000, 15000), "Insured", p["insured_party"], new_acct, date=d)
        label("claim", c["claim_id"], "FR-C15", "Payee bank details changed one day before a large payment")
    for _ in range(2):   # FR-C16 workers comp claim after termination
        p = pick(("WC",))
        worker = new_party(p["risk_zip"])
        term = p["eff_date"] + dt.timedelta(days=100)
        c = add_claim(p, term - dt.timedelta(days=2), "Strain", claimant=worker["party_id"], report_lag=9)
        c["employer_termination_date"] = term
        label("claim", c["claim_id"], "FR-C16", "Injury reported after the worker was terminated, dated just before")
    # FR-C09 early attorney on a minor claim
    for _ in range(3):
        p = pick(("PA",))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=80), "Collision", attorney=r.choice(["AT02", "AT03"]),
                      reserve=3200.0)
        c["attorney_date"] = c["loss_date"] + dt.timedelta(days=1)
        label("claim", c["claim_id"], "FR-C09", "Attorney retained the day after a minor collision")
    # FR-C17 repeat claimant
    rep = new_party("77002")
    for k in range(3):
        p = pick(("PA", "GL"))
        add_claim(p, p["eff_date"] + dt.timedelta(days=30 + k), r.choice(["Bodily Injury", "Slip and Fall"])
                  if p["lob"] == "GL" else "Bodily Injury", claimant=rep["party_id"])
    label("party", rep["party_id"], "FR-C17", "Same claimant on three injury claims against different insureds")
    # international examples
    p = pick(("PA",), country="UK")
    c = add_claim(p, p["eff_date"] + dt.timedelta(days=40), "Collision", attorney="AT04", reserve=9000)
    c["attorney_date"] = c["loss_date"] + dt.timedelta(days=2)
    c["description"] = "Crash-for-cash pattern: induced rear-end, multiple passengers"
    label("claim", c["claim_id"], "FR-C09", "UK motor: claims-management firm engaged two days after an induced collision")
    p = pick(("HO",), country="IN")
    c = add_claim(p, p["eff_date"] - dt.timedelta(days=12), "Theft")
    label("claim", c["claim_id"], "FR-C01", "India home: theft dated before cover began")

    # look-alikes that are NOT fraud, so the SME has false positives to clear
    for _ in range(2):   # collector with scheduled jewellery and art: high contents, genuine
        p = pick(("HO",))
        add_claim(p, p["eff_date"] + dt.timedelta(days=150), "Theft", contents=round(p["limit"] * 0.34, 2),
                  desc="Burglary; scheduled jewellery and art with appraisals on file")
    for _ in range(2):   # serious injury where the family called a lawyer at once: genuine
        p = pick(("PA",))
        c = add_claim(p, p["eff_date"] + dt.timedelta(days=120), "Collision", attorney="AT05", reserve=8500.0,
                      desc="Police report confirms other driver ran a red light")
        c["attorney_date"] = c["loss_date"] + dt.timedelta(days=2)

    clm = pd.DataFrame(claims)
    for col in ("loss_zip", "employer_termination_date"):
        if col not in clm:
            clm[col] = None
    clm["loss_zip"] = clm.loss_zip.fillna(clm.policy_id.map(lambda x: pol_idx[x]["risk_zip"]))

    # ------------------------------------------------------------------ reinsurance
    reinsurers = pd.DataFrame([
        {"reinsurer_id": "RE01", "name": "Atlas Re", "domicile": "US", "rating": "A+", "capital_usd": 4.5e9, "collateral_posted": True},
        {"reinsurer_id": "RE02", "name": "Meridian Re", "domicile": "Bermuda", "rating": "A", "capital_usd": 2.1e9, "collateral_posted": True},
        {"reinsurer_id": "RE03", "name": "Harborline Re", "domicile": "UK", "rating": "A-", "capital_usd": 9.0e8, "collateral_posted": True},
        {"reinsurer_id": "RE04", "name": "Bluewater Assurance Ltd", "domicile": "Offshore (unrated jurisdiction)", "rating": "NR",
         "capital_usd": 6.0e6, "collateral_posted": False},
    ])
    treaties = pd.DataFrame([
        {"treaty_id": "TR-QS-HO", "reinsurer_id": "RE01", "type": "Quota share 40%", "lob": "HO", "start": D(2025, 1, 1),
         "end": D(2026, 12, 31), "share": 0.40, "retention": 0, "limit": 5e6, "aad": 0},
        {"treaty_id": "TR-XL-PR", "reinsurer_id": "RE02", "type": "Per-risk XoL 250k xs 250k", "lob": "CP", "start": D(2025, 6, 1),
         "end": D(2026, 5, 31), "share": 1.0, "retention": 250000, "limit": 250000, "aad": 0},
        {"treaty_id": "TR-AGG", "reinsurer_id": "RE03", "type": "Aggregate stop loss", "lob": "HO", "start": D(2025, 1, 1),
         "end": D(2025, 12, 31), "share": 1.0, "retention": 0, "limit": 2e6, "aad": 1.5e6},
        {"treaty_id": "TR-CAT-FR", "reinsurer_id": "RE04", "type": "Fronted cat XoL (100% ceded)", "lob": "HO", "start": D(2025, 6, 1),
         "end": D(2026, 5, 31), "share": 1.0, "retention": 0, "limit": 2.5e7, "aad": 0},
    ])
    cp_df = pd.DataFrame(cpays)
    paid = cp_df.groupby("claim_id").amount.sum() if len(cp_df) else pd.Series(dtype=float)
    cessions = []
    ho = clm[(clm.lob == "HO") & (clm.country == "US") & clm.claim_id.isin(paid.index)]
    for c in ho.itertuples():
        if D(2025, 1, 1) <= c.loss_date <= D(2026, 12, 31):
            loss = float(paid[c.claim_id])
            cessions.append({"cession_id": g.id("CS", 4), "claim_id": c.claim_id, "treaty_id": "TR-QS-HO",
                             "ceded_loss": round(loss * 0.4, 2), "recovery_billed": round(loss * 0.4, 2),
                             "recovery_collected": round(loss * 0.4, 2) if r.random() < 0.85 else 0.0})
    # FR-R01 double ceding: same claim billed 40% to QS and 100% again under the fronted cat treaty
    for cid in list(ho.claim_id)[:2]:
        loss = float(paid[cid])
        cessions.append({"cession_id": g.id("CS", 4), "claim_id": cid, "treaty_id": "TR-CAT-FR",
                         "ceded_loss": loss, "recovery_billed": loss, "recovery_collected": 0.0})
        label("claim", cid, "FR-R01", "Same loss recovered under two treaties: billed 140% of paid")
    # FR-R02 recovery outside the treaty period
    out = clm[(clm.lob == "HO") & (clm.loss_date < D(2025, 6, 1)) & clm.claim_id.isin(paid.index)]
    for cid in list(out.claim_id)[:2]:
        loss = float(paid[cid])
        cessions.append({"cession_id": g.id("CS", 4), "claim_id": cid, "treaty_id": "TR-CAT-FR",
                         "ceded_loss": loss, "recovery_billed": loss, "recovery_collected": 0.0})
        label("claim", cid, "FR-R02", "Recovery billed for a loss before the treaty incepted")
    # FR-R03 aggregate stop billed before the annual aggregate deductible is used up
    cessions.append({"cession_id": g.id("CS", 4), "claim_id": "AGG-2025", "treaty_id": "TR-AGG",
                     "ceded_loss": 400000.0, "recovery_billed": 400000.0, "recovery_collected": 0.0})
    label("treaty", "TR-AGG", "FR-R03", "Aggregate stop recovery billed although 2025 retained losses are under the $1.5M AAD")
    label("treaty", "TR-CAT-FR", "FR-R04", "100% fronted to an unrated offshore reinsurer with $6M capital and no collateral")
    label("treaty", "TR-CAT-FR", "FR-R05", "Bordereau under-reports coastal Florida exposure")
    bordereau = []
    pdf_ = pd.DataFrame(policies)
    for z, g_ in pdf_[(pdf_.lob == "HO") & (pdf_.country == "US")].groupby("risk_zip"):
        actual = float(g_.limit.sum())
        coastal = ZIP_INFO[z]["coastal"] and ZIP_INFO[z]["state"] == "FL"
        bordereau.append({"treaty_id": "TR-CAT-FR", "zip": z, "policies_reported": len(g_) if not coastal else max(1, len(g_) // 3),
                          "tiv_reported": actual if not coastal else round(actual * 0.35, 0), "tiv_actual": actual})

    pol = pd.DataFrame(policies)
    obj = pd.DataFrame(objects)
    ext = ext.reset_index(drop=True)
    pay_df = pd.DataFrame(payments)
    if "chargeback_date" not in pay_df:
        pay_df["chargeback_date"] = None
    return {
        "policies": pol, "objects": obj, "parties": pd.DataFrame(parties), "employees": emp, "agents": agents,
        "vendors": vendors, "attorneys": attorneys, "external": ext, "premium_payments": pay_df,
        "refunds": pd.DataFrame(refunds, columns=["refund_id", "policy_id", "date", "amount", "to_acct", "approved_by"]),
        "bank_changes": pd.DataFrame(bank_changes, columns=["entity", "entity_id", "date", "old_acct", "new_acct", "changed_by"]),
        "claims": clm, "claim_payments": pd.DataFrame(cpays), "invoices": pd.DataFrame(invoices), "cat_events": cat,
        "reinsurers": reinsurers, "treaties": treaties, "cessions": pd.DataFrame(cessions),
        "bordereau": pd.DataFrame(bordereau), "truth": pd.DataFrame(truth), "valuation_date": VAL,
    }
