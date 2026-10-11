"""Demo source system: a legacy policy admin, claims and bill review system.

Column names and code values are deliberately the source system's own (POL_NO, DATE_OF_LOSS,
CLM_STAT = 'OPEN' ...), so the workbench has real mapping work to do. A handful of data quality
problems are seeded on purpose so the bureau returns errors the SME can revise.
All data is synthetic.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

CARRIER_CODE = "12345"
SEED = 2026

STATES = ["FL", "GA", "NC", "SC", "TN", "AL", "VA", "IL", "MO", "KY"]
CLASSES = {  # class: (description, illustrative rate per $100 payroll)
    "8810": ("CLERICAL OFFICE EMPLOYEES NOC", 0.18), "8742": ("SALESPERSONS OR COLLECTORS-OUTSIDE", 0.32),
    "5403": ("CARPENTRY NOC", 7.80), "5183": ("PLUMBING NOC", 4.10), "5190": ("ELECTRICAL WIRING-WITHIN BUILDINGS", 3.20),
    "7380": ("DRIVERS, CHAUFFEURS AND THEIR HELPERS NOC", 5.60), "9082": ("RESTAURANT NOC", 1.60),
    "8017": ("STORE: RETAIL NOC", 1.40), "8832": ("PHYSICIAN AND CLERICAL", 0.35),
    "9014": ("BUILDINGS-OPERATION BY CONTRACTORS", 3.10), "8380": ("AUTOMOBILE SERVICE OR REPAIR CENTER", 2.90),
    "7219": ("TRUCKING: NOC-ALL EMPLOYEES & DRIVERS", 6.80), "8868": ("COLLEGE: PROFESSIONAL EMPLOYEES", 0.40),
}
FIRST = ["Atlas", "Blue Ridge", "Coastal", "Delta", "Evergreen", "Frontier", "Granite", "Harbor", "Iron Gate",
         "Juniper", "Keystone", "Lakeside", "Magnolia", "Northstar", "Oakwood", "Pinecrest", "Quarry", "Riverbend",
         "Summit", "Tidewater", "Union", "Valley", "Westfield", "Yellow Pine"]
LAST = ["Builders", "Logistics", "Plumbing", "Electric", "Medical Group", "Diner", "Outfitters", "Trucking",
        "Auto Care", "Facility Services", "Academy", "Contractors", "Supply", "Partners"]
LEGAL = ["CORP", "LLC", "PARTNERSHIP", "INDIVIDUAL", "S-CORP"]
CITIES = {"FL": ("TAMPA", "336"), "GA": ("SAVANNAH", "314"), "NC": ("RALEIGH", "276"), "SC": ("COLUMBIA", "292"),
          "TN": ("NASHVILLE", "372"), "AL": ("MOBILE", "366"), "VA": ("RICHMOND", "232"), "IL": ("PEORIA", "616"),
          "MO": ("SPRINGFIELD", "658"), "KY": ("LEXINGTON", "405")}
BODY = ["42", "53", "34", "31", "38", "25", "66"]
NATURE = ["52", "49", "40", "10", "28", "43"]
CAUSE = ["56", "29", "31", "81", "97", "45"]
CPT = [("99213", "OFFICE VISIT EST PT"), ("97110", "THERAPEUTIC EXERCISE"), ("97140", "MANUAL THERAPY"),
       ("72148", "MRI LUMBAR SPINE"), ("73721", "MRI KNEE"), ("99283", "ED VISIT MOD"), ("20610", "JOINT INJECTION")]
ICD = ["S39.012A", "M54.50", "S83.511A", "S61.411A", "S63.501A", "M75.101"]
TAXONOMY = ["207X00000X", "225100000X", "261QU0200X", "207P00000X", "2085R0202X"]


def _d(x: dt.date) -> str:
    return x.strftime("%m/%d/%Y")  # legacy systems love MM/DD/YYYY strings


def build() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    pols, pstates, expos, claims, pays, bills = [], [], [], [], [], []
    for i in range(190):
        eff = dt.date(2022, 1, 1) + dt.timedelta(days=int(rng.integers(0, 1730)))
        eff = eff.replace(day=1) if rng.random() < 0.6 else eff
        exp = eff.replace(year=eff.year + 1)
        cancel = None
        if rng.random() < 0.06:
            cancel = eff + dt.timedelta(days=int(rng.integers(60, 300)))
        home = str(rng.choice(STATES))
        city, zip3 = CITIES[home]
        pol_no = f"WC{1000 + i:05d}{eff.year % 100:02d}"
        fein = f"{rng.integers(10, 99)}{rng.integers(1000000, 9999999)}"
        pols.append({
            "POL_NO": pol_no, "INSD_NM": f"{rng.choice(FIRST)} {rng.choice(LAST)} {rng.choice(['INC', 'LLC', 'CO'])}",
            "FED_TAX_ID": fein, "EFF_DT": _d(eff), "EXP_DT": _d(exp), "CANC_DT": _d(cancel) if cancel else "",
            "ISSUE_DT": _d(eff - dt.timedelta(days=int(rng.integers(-5, 25)))),
            "TRANS_TYPE": "NEW" if rng.random() < 0.45 else "RENEWAL",
            "PLAN_CD": "AR" if rng.random() < 0.08 else "VOLUNTARY",
            "ENTITY_TYPE": str(rng.choice(LEGAL, p=[.4, .35, .1, .1, .05])),
            "AGENCY_NM": f"{rng.choice(['First Coast', 'Peachtree', 'Piedmont', 'Heartland'])} Insurance Agency",
            "MAIL_ADDR1": f"{rng.integers(100, 9999)} {rng.choice(['MAIN', 'OAK', 'COMMERCE', 'INDUSTRIAL', 'PARK'])} "
                          f"{rng.choice(['ST', 'AVE', 'BLVD', 'PKWY'])}",
            "MAIL_CITY": city, "MAIL_ST": home, "MAIL_ZIP": f"{zip3}{rng.integers(10, 99)}",
            "EMP_CNT": int(rng.integers(3, 180)), "DED_TYPE": "MED" if rng.random() < 0.12 else "NONE",
            "DED_AMT": 2500 if rng.random() < 0.12 else 0, "EL_EACH_ACC": 100000, "EL_POLICY": 500000,
            "EL_EACH_EMP": 100000, "BILL_PLAN": str(rng.choice(["ANNUAL", "QUARTERLY", "MONTHLY"])),
            "AUDIT_FREQ": "ANNUAL", "RETRO_IND": "N", "INTERSTATE_RISK_ID": f"{rng.integers(100000000, 999999999)}",
        })
        states = [home] + ([str(rng.choice([s for s in STATES if s != home]))] if rng.random() < 0.15 else [])
        for st in states:
            xmod = round(float(rng.choice([1.0, 1.0, 1.0, rng.uniform(0.78, 1.32)])), 2)
            classes = list(rng.choice(list(CLASSES), size=int(rng.integers(1, 4)), replace=False))
            if "8810" not in classes and rng.random() < 0.6:
                classes.append("8810")
            std_prem = 0.0
            for cl in classes:
                rate = CLASSES[cl][1]
                payroll = int(rng.integers(40, 1800)) * 1000 if cl != "8810" else int(rng.integers(30, 400)) * 1000
                aud = int(payroll * float(rng.uniform(0.85, 1.15)) // 100 * 100)
                prem = round(aud * rate / 100, 0)
                std_prem += prem * xmod
                expos.append({"POL_NO": pol_no, "RISK_ST": st, "CLS_CD": cl, "CLS_DESC": CLASSES[cl][0],
                              "RATE": rate, "EST_PAYROLL": payroll, "AUD_PAYROLL": aud, "MANUAL_PREM": prem})
            pstates.append({"POL_NO": pol_no, "RISK_ST": st, "XMOD_FCTR": xmod, "STD_PREM": round(std_prem, 0),
                            "EXP_CONST": 160, "PREM_DISC": round(std_prem * 0.04, 0)})
            # claims for this policy-state
            n = int(rng.poisson(0.9 if std_prem > 8000 else 0.4))
            st_classes = classes
            for _ in range(n):
                acc = eff + dt.timedelta(days=int(rng.integers(3, 360)))
                if acc > dt.date(2026, 9, 25):
                    continue
                sev = str(rng.choice(["MED ONLY", "TTD", "PPD-MINOR", "PPD-MAJOR", "PTD", "FATAL"],
                                     p=[.68, .2, .07, .03, .01, .01]))
                closed = rng.random() < (0.85 if sev == "MED ONLY" else 0.5)
                status = "CLOSED" if closed else ("REOPENED" if rng.random() < 0.08 else "OPEN")
                med_paid = round(float(rng.gamma(1.6, 900 if sev == "MED ONLY" else 6000)), 2)
                ind_paid = 0.0 if sev == "MED ONLY" else round(float(rng.gamma(2.0, {"TTD": 3500, "PPD-MINOR": 9000,
                                                                                      "PPD-MAJOR": 30000, "PTD": 90000,
                                                                                      "FATAL": 120000}[sev])), 2)
                med_rsv = 0.0 if closed else round(float(rng.gamma(1.5, 4000)), 2)
                ind_rsv = 0.0 if closed or sev == "MED ONLY" else round(float(rng.gamma(1.5, 8000)), 2)
                clm_no = f"{st}{acc.year % 100:02d}{len(claims) + 1:06d}"
                aww = int(rng.integers(450, 1800))
                claims.append({
                    "CLAIM_NO": clm_no, "POL_NO": pol_no, "JURIS_ST": st, "CLS_CD": str(rng.choice(st_classes)),
                    "DATE_OF_LOSS": _d(acc), "RPT_DT": _d(acc + dt.timedelta(days=int(rng.integers(0, 20)))),
                    "CLOSE_DT": _d(acc + dt.timedelta(days=int(rng.integers(20, 300)))) if closed else "",
                    "CLM_STAT": status, "INJ_SVRTY": sev, "LOSS_TYP": str(rng.choice(["TRAUMA", "OCC DISEASE", "CUMULATIVE"], p=[.85, .07, .08])),
                    "RECOV_TYP": "NONE" if rng.random() < .93 else "SUBRO", "CLM_TYP": "WC ONLY",
                    "SETTLE_TYP": "NONE" if rng.random() < .9 else "COMPROMISE",
                    "BODY_PART": str(rng.choice(BODY)), "NATURE_INJ": str(rng.choice(NATURE)), "CAUSE_INJ": str(rng.choice(CAUSE)),
                    "WKLY_WG": aww, "CLMT_SEX": str(rng.choice(["M", "F"])), "CLMT_DOB": _d(dt.date(int(rng.integers(1960, 2004)), int(rng.integers(1, 13)), int(rng.integers(1, 28)))),
                    "HIRE_DT": _d(acc - dt.timedelta(days=int(rng.integers(30, 4000)))),
                    "OCCUPATION": str(rng.choice(["LABORER", "DRIVER", "COOK", "CLERK", "ELECTRICIAN", "NURSE", "CARPENTER"])),
                    "LUMP_SUM_IND": "Y" if (closed and sev in ("PPD-MINOR", "PPD-MAJOR") and rng.random() < .4) else "N",
                    "ATTY_IND": "Y" if (sev != "MED ONLY" and rng.random() < .3) else "N",
                    "IND_PAID": ind_paid, "IND_RSV": ind_rsv, "MED_PAID": med_paid, "MED_RSV": med_rsv,
                    "EXP_PAID": round(med_paid * float(rng.uniform(0, .08)), 2), "EXP_RSV": 0.0 if closed else 500.0,
                })
                # indemnity payments (WCIND)
                if ind_paid > 0:
                    left, start = ind_paid, acc + dt.timedelta(days=8)
                    k = 0
                    while left > 1 and k < 12 and start < dt.date(2026, 9, 28):
                        amt = round(min(left, aww * 0.6667 * 2), 2)
                        ben = {"TTD": "TTD", "PPD-MINOR": "PPD-S", "PPD-MAJOR": "PPD-U", "PTD": "PTD", "FATAL": "DEATH"}[sev]
                        if k == 0 and sev != "TTD":
                            ben = "TTD"
                        pays.append({"CLAIM_NO": clm_no, "PMT_ID": f"P{len(pays) + 1:08d}", "CHECK_DT": _d(start + dt.timedelta(days=14)),
                                     "SVC_FROM": _d(start), "SVC_THRU": _d(start + dt.timedelta(days=13)), "PMT_AMT": amt,
                                     "BEN_CD": ben, "WK_BEN_AMT": round(aww * 0.6667, 2)})
                        left -= amt
                        start += dt.timedelta(days=14)
                        k += 1
                # medical bill lines (WCMED)
                nb = int(rng.integers(1, 4 if sev == "MED ONLY" else 7))
                for b in range(nb):
                    svc = acc + dt.timedelta(days=int(rng.integers(0, 200)))
                    if svc > dt.date(2026, 9, 20):
                        continue
                    bill_id = f"B{len(bills) + 1:09d}"
                    for ln in range(1, int(rng.integers(1, 4)) + 1):
                        cpt = CPT[int(rng.integers(0, len(CPT)))]
                        chg = round(float(rng.uniform(90, 2400)), 2)
                        bills.append({"BILL_ID": bill_id, "LINE_NO": ln, "CLAIM_NO": clm_no, "DOS": _d(svc),
                                      "PAID_DT": _d(svc + dt.timedelta(days=int(rng.integers(10, 45)))),
                                      "CPT_CD": cpt[0], "CPT_MOD": str(rng.choice(["", "", "GP", "59"])), "BILLED_AMT": chg,
                                      "ALLOWED_PAID": round(chg * float(rng.uniform(0.45, 0.9)), 2),
                                      "DX1": str(rng.choice(ICD)), "DX2": str(rng.choice(["", "", "Z04.3"])),
                                      "PROV_TAXONOMY": str(rng.choice(TAXONOMY)), "PROV_NPI": f"1{rng.integers(100000000, 999999999)}",
                                      "PROV_ZIP": f"{CITIES[st][1]}{rng.integers(10, 99)}",
                                      "NETWORK_IND": str(rng.choice(["PPO", "NONE", "PPO", "HMO"])),
                                      "POS_CD": str(rng.choice(["11", "11", "22", "23"])), "UNITS": int(rng.integers(1, 4))})

    src = {"PC_POLICY": pd.DataFrame(pols), "PC_POLICY_STATE": pd.DataFrame(pstates),
           "PC_CLASS_EXPOSURE": pd.DataFrame(expos), "CC_CLAIM": pd.DataFrame(claims),
           "CC_INDEMNITY_PAYMENT": pd.DataFrame(pays), "BR_MEDICAL_BILL_LINE": pd.DataFrame(bills)}
    _seed_issues(src)
    return src


def _seed_issues(src: dict[str, pd.DataFrame]) -> None:
    """Realistic data problems a bureau would reject; spread across months so each run shows some."""
    p, e, c, pay, b = (src[k] for k in ("PC_POLICY", "PC_CLASS_EXPOSURE", "CC_CLAIM", "CC_INDEMNITY_PAYMENT",
                                         "BR_MEDICAL_BILL_LINE"))
    p.loc[p.index[7::23], "FED_TAX_ID"] = ""                      # missing FEIN
    e.loc[e.index[11::37], "CLS_CD"] = "9999"                      # class code not in the plan
    c.loc[c.index[5::29], "CLM_STAT"] = "PENDING"                  # status with no bureau equivalent
    c.loc[c.index[9::31], "INJ_SVRTY"] = "TTD/TPD"                  # ambiguous injury type
    idx = c.index[13::41]                                          # paid more than incurred (negative reserve)
    c.loc[idx, "IND_RSV"] = -c.loc[idx, "IND_PAID"].clip(lower=500) * 0.3
    med_only = c.index[(c.INJ_SVRTY == "MED ONLY")][3::25]          # medical-only claim carrying indemnity
    c.loc[med_only, "IND_PAID"] = 850.0
    pol = p.set_index("POL_NO")
    for i in c.index[17::43]:                                      # accident date before policy effective
        eff = dt.datetime.strptime(pol.loc[c.at[i, "POL_NO"], "EFF_DT"], "%m/%d/%Y").date()
        c.at[i, "DATE_OF_LOSS"] = _d(eff - dt.timedelta(days=12))
    b.loc[b.index[19::53], "ALLOWED_PAID"] = b.loc[b.index[19::53], "BILLED_AMT"] * 1.25   # paid above charge
    b.loc[b.index[27::61], "CPT_CD"] = ""                          # missing procedure code
    pay.loc[pay.index[15::47], "BEN_CD"] = "MISC"                  # unmapped benefit code


def describe(src: dict[str, pd.DataFrame]) -> pd.DataFrame:
    meta = {"PC_POLICY": "Policy admin: policy header, insured, address",
            "PC_POLICY_STATE": "Policy admin: state premium and experience mod",
            "PC_CLASS_EXPOSURE": "Policy admin: class code exposure and premium",
            "CC_CLAIM": "Claims: claim header, injury details, paid and reserves",
            "CC_INDEMNITY_PAYMENT": "Claims: indemnity payment checks",
            "BR_MEDICAL_BILL_LINE": "Bill review: medical bill lines"}
    return pd.DataFrame([{"source table": k, "description": meta[k], "rows": len(v), "columns": v.shape[1]}
                         for k, v in src.items()])
