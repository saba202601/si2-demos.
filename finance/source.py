"""Source data for the Yellow Book: a synthetic P&C company's operational and ledger feeds.

The feeds look like what a carrier's warehouse and general ledger hand to statutory reporting:

    premium_txn      policy-level written premium by annual statement line, state and reinsurance basis
    gl_premium       premium as booked in the general ledger by line and basis (should agree with premium_txn)
    claim_txn        claim payments (loss, DCC, A&O, salvage) by claim, accident year and calendar year
    claim_reserve    case reserves (loss, DCC) at each year-end
    ibnr             actuarial bulk + IBNR and A&O unpaid by line, accident year and year-end
    expense_ledger   operating expenses by Part 3 line with LAE / underwriting / investment allocation
    gl_balance       balance sheet accounts (current and prior year) with the statement line they report on
    investment       investment income collected / earned and realized gains by asset class
    reinsurer        reinsurers and their share of ceded business (Schedule F)

All names, codes and amounts are invented. Connectors: the same tables can come from CSV uploads or from SQL Server
(schema fin in SI2Canonical, created by finance/sql/01_create_fin.sql).
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .blank import YEAR

COMPANY = {"name": "SI² Mutual Insurance Company (synthetic)", "naic_code": "00000", "domicile": "FL", "year": YEAR}
# lines written: asl code -> (direct written premium 2025, expected loss ratio, tail years, quota share ceded, affiliate ceded)
BOOK = {
    "1": (18e6, 0.45, 2, 0.20, 0.00), "2.1": (12e6, 0.50, 2, 0.20, 0.00), "4": (210e6, 0.62, 3, 0.25, 0.05),
    "5.1": (46e6, 0.55, 3, 0.20, 0.00), "5.2": (24e6, 0.60, 6, 0.20, 0.00), "9.1": (15e6, 0.48, 2, 0.15, 0.00),
    "12": (6e6, 0.20, 2, 0.40, 0.00), "16": (88e6, 0.66, 9, 0.10, 0.05), "17.1": (40e6, 0.63, 8, 0.25, 0.00),
    "19.1": (22e6, 0.72, 4, 0.10, 0.00), "19.2": (150e6, 0.68, 5, 0.10, 0.00), "19.4": (38e6, 0.70, 6, 0.15, 0.00),
    "21.1": (110e6, 0.64, 2, 0.10, 0.00), "21.2": (21e6, 0.60, 2, 0.10, 0.00),
}
ASSUMED = {"16": (6e6, 0.0), "4": (0.0, 3e6)}           # line -> (assumed from affiliates, assumed from non-affiliates)
STATE_MIX = {"FL": .24, "TX": .16, "GA": .10, "NY": .09, "NC": .08, "PA": .08, "IL": .07, "NJ": .06, "OH": .06, "CA": .06}
REINSURERS = [("AA-1001", "00010", "Atlas Reinsurance Company", "NY", "QS", 0.40),
              ("AA-1002", "00011", "Meridian Re Ltd", "BMU", "QS", 0.25),
              ("AA-1003", "00012", "Harborline Reinsurance Corp", "CT", "QS", 0.20),
              ("AA-1004", "00013", "Northgate Re SE", "DEU", "QS", 0.15),
              ("AF-0001", "00001", "SI² Mutual Holding Re (affiliate)", "FL", "AFF", 1.00)]
EXPENSES = {   # Part 3 line -> (amount, LAE share, underwriting share, investment share)
    "1.1": (21e6, 1, 0, 0), "1.3": (2.4e6, 1, 0, 0), "2.1": (118e6, 0, 1, 0), "2.2": (0.9e6, 0, 1, 0), "2.3": (19e6, 0, 1, 0),
    "2.4": (6.5e6, 0, 1, 0), "2.7": (1.1e6, 0, 1, 0), "3": (1.8e6, 0, 1, 0), "4": (7.4e6, 0.02, 0.98, 0),
    "5": (2.2e6, 0.15, 0.85, 0), "6": (3.9e6, 0.05, 0.95, 0), "7": (1.2e6, 0, 1, 0), "8.1": (96e6, 0.42, 0.53, 0.05),
    "8.2": (7.2e6, 0.42, 0.53, 0.05), "9": (18e6, 0.42, 0.53, 0.05), "10": (2.6e6, 0.3, 0.65, 0.05), "11": (0.8e6, 0, 0.9, 0.1),
    "12": (3.1e6, 0.4, 0.55, 0.05), "13": (9.5e6, 0.38, 0.55, 0.07), "14": (4.4e6, 0.35, 0.6, 0.05),
    "15": (14e6, 0.35, 0.6, 0.05), "16": (1.1e6, 0.3, 0.7, 0), "17": (2.3e6, 0.35, 0.65, 0), "18": (5.6e6, 0.3, 0.6, 0.1),
    "20.1": (24e6, 0, 1, 0), "20.2": (1.4e6, 0, 1, 0), "20.3": (2.1e6, 0, 1, 0), "20.4": (0.6e6, 0, 0.9, 0.1),
    "21": (1.9e6, 0, 0, 1), "22": (0.7e6, 0, 0, 1),
}
INVEST = {   # exhibit of net investment income line -> (collected, earned)
    "1": (6.1e6, 6.2e6), "1.1": (9.8e6, 9.9e6), "1.2": (31.5e6, 32.4e6), "1.3": (0, 0), "2.1": (0.6e6, 0.6e6),
    "2.11": (0, 0), "2.2": (7.9e6, 7.9e6), "2.21": (1.5e6, 1.5e6), "3": (1.2e6, 1.25e6), "4": (3.4e6, 3.4e6),
    "5": (0, 0), "6": (4.2e6, 4.3e6), "7": (0, 0), "8": (2.6e6, 2.7e6), "9": (0, 0),
}
INV_DEDUCT = {"12": 0.4e6, "13": 1.1e6, "14": 1.3e6, "15": 0}
GL = [  # account, name, statement page/line, current year, prior year, nonadmitted (current year)
    ("1100", "Bonds at amortized cost", "P2.1", 1_050e6, 1_000e6, 0),
    ("1210", "Preferred stocks", "P2.2.1", 18e6, 17e6, 0), ("1220", "Common stocks at fair value", "P2.2.2", 265e6, 241e6, 0),
    ("1310", "Mortgage loans - first liens", "P2.3.1", 24e6, 26e6, 0), ("1410", "Home office building", "P2.4.1", 41e6, 42.5e6, 0),
    ("1700", "Other invested assets (LP interests)", "P2.8", 58e6, 49e6, 2.5e6), ("1800", "Receivables for securities", "P2.9", 3.1e6, 1.9e6, 0),
    ("2100", "Investment income due and accrued", "P2.14", 15.4e6, 14.6e6, 0),
    ("2210", "Uncollected premiums and agents' balances", "P2.15.1", 96e6, 91e6, 4.2e6),
    ("2220", "Deferred premiums and installments not yet due", "P2.15.2", 172e6, 160e6, 0),
    ("2310", "Amounts recoverable from reinsurers (paid losses)", "P2.16.1", 21e6, 18e6, 0),
    ("2410", "Net deferred tax asset", "P2.18.2", 38e6, 35e6, 9e6), ("2510", "Guaranty funds receivable", "P2.19", 1.2e6, 1.4e6, 0),
    ("2610", "EDP equipment and software", "P2.20", 12e6, 13e6, 3e6), ("2620", "Furniture and equipment", "P2.21", 4e6, 4.5e6, 4e6),
    ("2710", "Receivables from affiliates", "P2.23", 6e6, 5e6, 0),
    ("3210", "Reinsurance payable on paid losses and LAE", "P3.2", 5.5e6, 4.9e6, 0),
    ("3410", "Commissions payable", "P3.4", 21e6, 19.5e6, 0), ("3510", "Accrued other expenses", "P3.5", 18e6, 16.4e6, 0),
    ("3610", "Taxes, licenses and fees payable", "P3.6", 9.1e6, 8.6e6, 0), ("3710", "Current federal income taxes payable", "P3.7.1", 4.4e6, 3.2e6, 0),
    ("3910", "Advance premium", "P3.10", 6.8e6, 6.1e6, 0), ("3920", "Policyholder dividends declared and unpaid", "P3.11.2", 1.5e6, 1.4e6, 0),
    ("4010", "Ceded reinsurance premiums payable", "P3.12", 33e6, 30e6, 0), ("4020", "Funds held under reinsurance treaties", "P3.13", 7.5e6, 7e6, 0),
    ("4030", "Amounts withheld for account of others", "P3.14", 3.6e6, 3.3e6, 0), ("4040", "Remittances and items not allocated", "P3.15", 2.2e6, 1.8e6, 0),
    ("4050", "Provision for reinsurance", "P3.16", 1.1e6, 1.3e6, 0), ("4080", "Drafts outstanding", "P3.18", 4.6e6, 4.1e6, 0),
    ("4090", "Payable to affiliates", "P3.19", 5.2e6, 4.4e6, 0), ("4110", "Payable for securities", "P3.21", 2.9e6, 1.2e6, 0),
    ("5100", "Common capital stock", "P3.30", 5e6, 5e6, 0), ("5300", "Surplus notes", "P3.33", 50e6, 50e6, 0),
    ("5400", "Gross paid in and contributed surplus", "P3.34", 120e6, 120e6, 0),
]
SURPLUS_CHANGES = {"24": 14.6e6, "26": 3.0e6, "28": 0.2e6, "35": -12e6}   # Page 4 capital and surplus lines, current year
TAX_RATE = 0.21


def _book_rng(seed=2025):
    return np.random.default_rng(seed)


def premium_txn(seed: int = 2025) -> pd.DataFrame:
    """Policy-level written premium for policies written in the prior and current year (annual terms)."""
    rng = _book_rng(seed)
    rows = []
    states, w = list(STATE_MIX), np.array(list(STATE_MIX.values()))
    pid = 0
    for line, (dwp, _lr, _tail, qs, aff) in BOOK.items():
        for year, scale in ((YEAR - 1, 0.94), (YEAR, 1.0)):
            n = int(dwp / 1e6 * 6)
            prem = rng.gamma(4.0, dwp * scale / n / 4.0, n)
            prem *= dwp * scale / prem.sum()
            eff = [dt.date(year, 1, 1) + dt.timedelta(days=int(d)) for d in rng.integers(0, 365, n)]
            st_ = rng.choice(states, n, p=w / w.sum())
            for p, e, s in zip(prem, eff, st_):
                pid += 1
                pol = f"P{year % 100:02d}-{pid:06d}"
                base = {"policy_id": pol, "asl_code": line, "state": s, "eff_date": e,
                        "exp_date": e.replace(year=e.year + 1) if not (e.month == 2 and e.day == 29) else dt.date(e.year + 1, 2, 28),
                        "written_year": year}
                rows.append({**base, "basis": "D", "affiliate": 0, "written": round(p, 2)})
                if qs:
                    rows.append({**base, "basis": "C", "affiliate": 0, "written": round(p * qs, 2)})
                if aff:
                    rows.append({**base, "basis": "C", "affiliate": 1, "written": round(p * aff, 2)})
        for flag, amt in enumerate(ASSUMED.get(line, (0, 0))):
            if amt:
                for year, scale in ((YEAR - 1, 0.94), (YEAR, 1.0)):
                    e = dt.date(year, 1, 1)
                    rows.append({"policy_id": f"ASM-{line}-{year}-{flag}", "asl_code": line, "state": "FL", "eff_date": e,
                                 "exp_date": dt.date(year + 1, 1, 1), "written_year": year, "basis": "A",
                                 "affiliate": 1 - flag, "written": round(amt * scale, 2)})
    return pd.DataFrame(rows)


def gl_premium(ptx: pd.DataFrame, late_entry: float = 0.0) -> pd.DataFrame:
    """Premium as booked in the GL for the current year. `late_entry` adds a manual GL entry the policy system lacks."""
    cur = ptx[ptx.written_year == YEAR]
    g = cur.groupby(["asl_code", "basis", "affiliate"]).written.sum().reset_index()
    if late_entry:
        m = (g.asl_code == "4") & (g.basis == "D")
        g.loc[m, "written"] += late_entry
    g["gl_account"] = "4" + g.basis.map({"D": "100", "A": "200", "C": "300"}) + g.affiliate.astype(str)
    return g


def unearned(ptx: pd.DataFrame, at: dt.date) -> pd.Series:
    """Pro-rata unearned premium at a year-end by policy row."""
    days = (pd.to_datetime(ptx.exp_date) - pd.to_datetime(ptx.eff_date)).dt.days.clip(lower=1)
    left = (pd.to_datetime(ptx.exp_date) - pd.Timestamp(at)).dt.days.clip(lower=0)
    started = pd.to_datetime(ptx.eff_date) <= pd.Timestamp(at)
    return (ptx.written * (left / days)).where(started, 0.0)


def claims(seed: int = 2025) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Claim payments and year-end case reserves for accident years YEAR-9 .. YEAR, plus actuarial IBNR."""
    rng = _book_rng(seed + 1)
    pays, res, ibnr = [], [], []
    states, w = list(STATE_MIX), np.array(list(STATE_MIX.values()))
    cid = 0
    for line, (dwp, lr, tail, qs, aff) in BOOK.items():
        ceded = qs + aff
        for ay in range(YEAR - 9, YEAR + 1):
            prem = dwp * (0.96 ** (YEAR - ay)) * 0.98
            ult = prem * lr * rng.normal(1.0, 0.05)
            n = max(8, int(ult / 250_000))
            sev = rng.lognormal(0, 0.9, n)
            sev = sev / sev.sum() * ult
            # cumulative paid pattern over `tail` years (S-curve), case reserve = most of what is reported but unpaid
            ages = np.arange(1, 11)
            paid_pat = 1 - np.exp(-ages / max(tail * 0.45, 0.6))
            rep_pat = np.minimum(1, paid_pat + (1 - paid_pat) * 0.75)
            for k, s in enumerate(sev):
                cid += 1
                clm = f"C{ay % 100:02d}{line.replace('.', '')}-{cid:06d}"
                st_ = rng.choice(states, p=w / w.sum())
                lag = rng.integers(0, 2 if tail <= 3 else 3)
                closed_np = rng.random() < 0.18
                prev_paid = prev_dcc = 0.0
                for age in ages:
                    cy = ay + age - 1
                    if cy > YEAR:
                        break
                    if age - 1 < lag:
                        continue
                    jit = rng.normal(1, 0.04)
                    cum_paid = 0.0 if closed_np else s * min(1, paid_pat[age - 1] * jit)
                    cum_dcc = cum_paid * (0.06 if tail > 4 else 0.02)
                    reported = 0.0 if closed_np and age > 1 else s * min(1, rep_pat[age - 1] * jit)
                    if cum_paid - prev_paid > 0.5:
                        pays.append({"claim_id": clm, "asl_code": line, "state": st_, "accident_year": ay, "calendar_year": cy,
                                     "pay_type": "LOSS", "amount": round(cum_paid - prev_paid, 2), "ceded_pct": ceded})
                    if cum_dcc - prev_dcc > 0.5:
                        pays.append({"claim_id": clm, "asl_code": line, "state": st_, "accident_year": ay, "calendar_year": cy,
                                     "pay_type": "DCC", "amount": round(cum_dcc - prev_dcc, 2), "ceded_pct": ceded})
                    prev_paid, prev_dcc = cum_paid, cum_dcc
                    case = 0.0 if paid_pat[age - 1] > 0.97 else max(reported - cum_paid, 0.0)
                    res.append({"claim_id": clm, "asl_code": line, "state": st_, "accident_year": ay, "valuation_year": cy,
                                "case_loss": round(case, 2), "case_dcc": round(case * (0.05 if tail > 4 else 0.015), 2),
                                "ceded_pct": ceded, "closed": int(case == 0 and cy >= ay + lag),
                                "closed_without_payment": int(closed_np)})
            for vy in range(ay, YEAR + 1):
                age = vy - ay + 1
                unreported = ult * (1 - rep_pat[min(age, 10) - 1])
                ibnr.append({"asl_code": line, "accident_year": ay, "valuation_year": vy,
                             "ibnr_loss": round(unreported * 0.92, 2), "ibnr_dcc": round(unreported * 0.05, 2),
                             "ao_unpaid": round((ult - ult * paid_pat[min(age, 10) - 1]) * 0.035, 2), "ceded_pct": ceded})
    pay = pd.DataFrame(pays)
    sal = pay[pay.pay_type == "LOSS"].sample(frac=0.08, random_state=seed).copy()
    sal["pay_type"], sal["amount"] = "SALVAGE", (sal.amount * -0.15).round(2)
    ao = pay[pay.pay_type == "LOSS"].groupby(["asl_code", "state", "accident_year", "calendar_year", "ceded_pct"]).amount.sum().reset_index()
    ao["amount"], ao["pay_type"], ao["claim_id"] = (ao.amount * 0.045).round(2), "AO", ""
    pay = pd.concat([pay, sal, ao[pay.columns]], ignore_index=True)
    return pay, pd.DataFrame(res), pd.DataFrame(ibnr)


def expense_ledger() -> pd.DataFrame:
    return pd.DataFrame([{"part3_line": k, "amount": v[0], "lae_share": v[1], "uw_share": v[2], "inv_share": v[3]}
                         for k, v in EXPENSES.items()])


def gl_balance() -> pd.DataFrame:
    return pd.DataFrame(GL, columns=["account", "account_name", "statement_line", "balance_cy", "balance_py", "nonadmitted_cy"])


def investment() -> pd.DataFrame:
    return pd.DataFrame([{"nii_line": k, "collected": v[0], "earned": v[1]} for k, v in INVEST.items()])


def reinsurers() -> pd.DataFrame:
    return pd.DataFrame(REINSURERS, columns=["reinsurer_id", "naic_code", "name", "domicile", "program", "share"])


def build(seed: int = 2025, late_gl_entry: float = 0.0) -> dict:
    """Every feed the statement needs, as one 'connected source'."""
    ptx = premium_txn(seed)
    pay, res, ib = claims(seed)
    return {"company": COMPANY, "premium_txn": ptx, "gl_premium": gl_premium(ptx, late_gl_entry), "claim_txn": pay,
            "claim_reserve": res, "ibnr": ib, "expense_ledger": expense_ledger(), "gl_balance": gl_balance(),
            "investment": investment(), "inv_deductions": INV_DEDUCT, "surplus_changes": SURPLUS_CHANGES,
            "reinsurer": reinsurers(), "surplus_py": 905e6, "tax_rate": TAX_RATE}


FEEDS = ["premium_txn", "gl_premium", "claim_txn", "claim_reserve", "ibnr", "expense_ledger", "gl_balance", "investment",
         "reinsurer"]
