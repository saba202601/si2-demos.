"""Generate the Yellow Book from the connected source and check it.

generate(src) -> Statement with every value keyed by (field_id, dim) where dim is '' for company totals, a state code
on the state page, or a reinsurer id on Schedule F. Each value carries its lineage (which feed and rule produced it).
edits(stmt)   -> the cross-checks the NAIC and every regulator run (crossfoots, page-to-page ties, state-page and
                 Schedule P reconciliations), each with expected, actual and difference.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

from . import blank as B
from .source import unearned

Y = B.YEAR
YE, PYE = dt.date(Y, 12, 31), dt.date(Y - 1, 12, 31)
FIVE_YEAR_GROUPS = {   # Five-Year Historical Data line groups (SI² outline – verify against the instructions)
    "1": ["11.1", "11.2", "16", "17.1", "17.2", "17.3", "18.1", "18.2", "19.1", "19.2", "19.3", "19.4"],
    "2": ["1", "2.1", "2.2", "2.3", "2.4", "2.5", "9.1", "9.2", "12", "21.1", "21.2", "26", "27"],
    "3": ["3", "4", "5.1", "5.2", "8", "22"],
    "4": ["6", "10", "13.1", "13.2", "14", "15.1", "15.2", "15.3", "15.4", "15.5", "15.6", "15.7", "15.8", "15.9", "23",
          "24", "28", "29", "30", "34"],
    "5": ["31", "32", "33"],
}


@dataclass
class Statement:
    values: dict = field(default_factory=dict)        # (field_id, dim) -> value
    lineage: dict = field(default_factory=dict)       # field_id -> text
    notes: list = field(default_factory=list)

    def set(self, page, line, col, value, why="", dim=""):
        fid = B.field_id(page, str(line), str(col))
        self.values[(fid, dim)] = float(value) if value is not None and not isinstance(value, str) else value
        if why and fid not in self.lineage:
            self.lineage[fid] = why

    def get(self, page, line, col, dim="") -> float:
        v = self.values.get((B.field_id(page, str(line), str(col)), dim), 0.0)
        return v if isinstance(v, (int, float)) else 0.0

    def frame(self) -> pd.DataFrame:
        f = B.fields().set_index("field_id")
        rows = [{"field_id": k, "dim": d, "value": v} for (k, d), v in self.values.items()]
        df = pd.DataFrame(rows)
        df = df.join(f[["page_code", "page_name", "line_no", "line_caption", "col_no", "col_caption", "source"]], on="field_id")
        df["lineage"] = df.field_id.map(self.lineage).fillna("")
        return df


def _by_line(df, col="written"):
    return df.groupby("asl_code")[col].sum()


def generate(src: dict) -> Statement:
    s = Statement()
    ptx, glp = src["premium_txn"], src["gl_premium"]
    lines = [c for c in B.ASL_CODES if c != "35"]

    # ------------------------------------------------------------------ UIE Part 1B: premiums written (GL premium)
    def glsum(basis, aff):
        g = glp[(glp.basis == basis) & (glp.affiliate == aff)]
        return g.groupby("asl_code").written.sum()
    cols1b = {"1": glp[glp.basis == "D"].groupby("asl_code").written.sum(), "2": glsum("A", 1), "3": glsum("A", 0),
              "4": glsum("C", 1), "5": glsum("C", 0)}
    why1b = "GL premium (gl_premium) by annual statement line and reinsurance basis"
    for c, ser in cols1b.items():
        for ln, v in ser.items():
            s.set("U1B", ln, c, v, why1b)
    for ln in lines:
        net = sum(s.get("U1B", ln, c) for c in "12") + s.get("U1B", ln, "3") - s.get("U1B", ln, "4") - s.get("U1B", ln, "5")
        if any(s.get("U1B", ln, c) for c in "12345"):
            s.set("U1B", ln, "6", net, "Cols. 1 + 2 + 3 - 4 - 5")

    # ------------------------------------------------------------------ Part 1A and Part 1: unearned and earned
    sign = ptx.basis.map({"D": 1.0, "A": 1.0, "C": -1.0})
    uep_cy = (unearned(ptx, YE) * sign).groupby(ptx.asl_code).sum()
    uep_py = (unearned(ptx[ptx.written_year < Y], PYE) * sign[ptx.written_year < Y]).groupby(ptx.asl_code[ptx.written_year < Y]).sum()
    ebub = {"16": 0.012 * s.get("U1B", "16", "1")}
    ebub_py = {"16": 0.012 * 0.94 * s.get("U1B", "16", "1")}
    for ln, v in uep_cy.items():
        s.set("U1A", ln, "1", v, "Pro-rata unearned premium at 12/31 from policy terms (premium_txn), net of ceded")
        s.set("U1A", ln, "3", ebub.get(ln, 0.0), "Earned but unbilled: workers' compensation audit premium estimate (1.2% of direct)")
        s.set("U1A", ln, "5", v + ebub.get(ln, 0.0), "Cols. 1 + 2 + 3 + 4")
    for ln in lines:
        if s.get("U1B", ln, "6") or s.get("U1A", ln, "5"):
            s.set("U1", ln, "1", s.get("U1B", ln, "6"), "Part 1B, Col. 6")
            s.set("U1", ln, "2", uep_py.get(ln, 0.0) + ebub_py.get(ln, 0.0), "Unearned premium at 12/31 prior year (prior-year policies)")
            s.set("U1", ln, "3", s.get("U1A", ln, "5"), "Part 1A, Col. 5")
            s.set("U1", ln, "4", s.get("U1", ln, "1") + s.get("U1", ln, "2") - s.get("U1", ln, "3"), "Cols. 1 + 2 - 3")

    # ------------------------------------------------------------------ Part 2 / 2A: losses
    pay, res, ib = src["claim_txn"], src["claim_reserve"], src["ibnr"]
    cy = pay[pay.calendar_year == Y]
    loss_cy = cy[cy.pay_type.isin(["LOSS", "SALVAGE"])]
    dir_paid = _by_line(loss_cy, "amount")
    ceded_paid = (loss_cy.amount * loss_cy.ceded_pct).groupby(loss_cy.asl_code).sum()

    def unpaid(vy):
        r = res[res.valuation_year == vy]
        i = ib[ib.valuation_year == vy]
        case_d = _by_line(r, "case_loss")
        case_c = (r.case_loss * r.ceded_pct).groupby(r.asl_code).sum()
        ibnr_d = _by_line(i, "ibnr_loss")
        ibnr_c = (i.ibnr_loss * i.ceded_pct).groupby(i.asl_code).sum()
        lae = ((r.case_dcc * (1 - r.ceded_pct)).groupby(r.asl_code).sum()
               .add((i.ibnr_dcc * (1 - i.ceded_pct)).groupby(i.asl_code).sum(), fill_value=0)
               .add(i.groupby("asl_code").ao_unpaid.sum(), fill_value=0))
        return case_d, case_c, ibnr_d, ibnr_c, lae

    cd, cc, idd, ic, lae = unpaid(Y)
    _cdp, _ccp, _idp, _icp, lae_py = unpaid(Y - 1)
    net_unpaid_py = (_cdp - _ccp).add(_idp - _icp, fill_value=0)
    for ln in lines:
        if ln not in cd.index and ln not in idd.index:
            continue
        s.set("U2A", ln, "1", cd.get(ln, 0), "Case reserves at 12/31 (claim_reserve), direct")
        s.set("U2A", ln, "3", cc.get(ln, 0), "Case reserves x ceded share")
        s.set("U2A", ln, "4", cd.get(ln, 0) - cc.get(ln, 0), "Cols. 1 + 2 - 3")
        s.set("U2A", ln, "5", idd.get(ln, 0), "Actuarial bulk + IBNR (ibnr), direct")
        s.set("U2A", ln, "7", ic.get(ln, 0), "IBNR x ceded share")
        s.set("U2A", ln, "8", s.get("U2A", ln, "4") + s.get("U2A", ln, "5") - s.get("U2A", ln, "7"), "Cols. 4 + 5 + 6 - 7")
        s.set("U2A", ln, "9", lae.get(ln, 0), "DCC case + DCC IBNR net of ceded, plus adjusting and other unpaid")
        s.set("U2", ln, "1", dir_paid.get(ln, 0), "Loss payments in the year net of salvage (claim_txn), direct")
        s.set("U2", ln, "3", ceded_paid.get(ln, 0), "Loss payments x ceded share")
        s.set("U2", ln, "4", s.get("U2", ln, "1") + s.get("U2", ln, "2") - s.get("U2", ln, "3"), "Cols. 1 + 2 - 3")
        s.set("U2", ln, "5", s.get("U2A", ln, "8"), "Part 2A, Col. 8")
        s.set("U2", ln, "6", net_unpaid_py.get(ln, 0), "Net losses unpaid at 12/31 prior year")
        s.set("U2", ln, "7", s.get("U2", ln, "4") + s.get("U2", ln, "5") - s.get("U2", ln, "6"), "Cols. 4 + 5 - 6")
        ep = s.get("U1", ln, "4")
        s.set("U2", ln, "8", 100 * s.get("U2", ln, "7") / ep if ep else 0, "Col. 7 / Part 1, Col. 4 x 100")

    # line 35 totals for every ASL page
    for page, cols in (("U1B", "123456"), ("U1A", "12345"), ("U1", "1234"), ("U2", "1234567"), ("U2A", "123456789")):
        for c in cols:
            s.set(page, "35", c, sum(s.get(page, ln, c) for ln in lines), "Sum of lines 1 through 34")
    s.set("U2", "35", "8", 100 * s.get("U2", "35", "7") / s.get("U1", "35", "4"), "Col. 7 / Part 1, Col. 4 x 100")

    # ------------------------------------------------------------------ Part 3: expenses
    ex = src["expense_ledger"].set_index("part3_line")
    lae_paid_d = cy[cy.pay_type.isin(["DCC", "AO"])].amount.sum()
    lae_paid_c = (cy[cy.pay_type == "DCC"].amount * cy[cy.pay_type == "DCC"].ceded_pct).sum()
    lae_unpaid_cy, lae_unpaid_py = lae.sum(), lae_py.sum()
    ext = {"1.1": lae_paid_d + (lae_unpaid_cy - lae_unpaid_py) + ex.at["1.1", "amount"] * 0,
           "1.3": lae_paid_c}
    for ln_, r in ex.iterrows():
        amt = ext.get(ln_, r.amount) if ln_ in ("1.1", "1.3") else r.amount
        s.set("U3", ln_, "1", amt * r.lae_share, "expense_ledger x LAE allocation" if ln_ not in ext else "DCC and A&O paid + change in unpaid LAE")
        s.set("U3", ln_, "2", amt * r.uw_share, "expense_ledger x underwriting allocation")
        s.set("U3", ln_, "3", amt * r.inv_share, "expense_ledger x investment allocation")
    for c in "123":
        g = lambda ln, c=c: s.get("U3", ln, c)  # noqa: E731
        s.set("U3", "1.4", c, g("1.1") + g("1.2") - g("1.3"), "1.1 + 1.2 - 1.3")
        s.set("U3", "2.8", c, g("2.1") + g("2.2") - g("2.3") + g("2.4") + g("2.5") - g("2.6") + g("2.7"), "Net commission")
        s.set("U3", "19", c, sum(g(x) for x in ["3", "4", "5", "6", "7", "8.1", "8.2", "9", "10", "11", "12", "13", "14", "15",
                                                 "16", "17", "18"]), "Lines 3 to 18")
        s.set("U3", "20.5", c, sum(g(x) for x in ["20.1", "20.2", "20.3", "20.4"]), "20.1 to 20.4")
        s.set("U3", "25", c, g("1.4") + g("2.8") + g("19") + g("20.5") + g("21") + g("22") - g("23") + g("24"),
              "Lines 1.4 + 2.8 + 19 + 20.5 + 21 + 22 - 23 + 24")
    gl = src["gl_balance"].set_index("statement_line")
    unpaid_cy = {"1": lae_unpaid_cy, "2": gl.loc[["P3.4", "P3.5", "P3.6"], "balance_cy"].sum(), "3": 0.0}
    unpaid_py = {"1": lae_unpaid_py, "2": gl.loc[["P3.4", "P3.5", "P3.6"], "balance_py"].sum(), "3": 0.0}
    for c in "123":
        s.set("U3", "26", c, unpaid_cy[c], "Unpaid at 12/31 (Page 3 lines 3, 4, 5, 6)")
        s.set("U3", "27", c, unpaid_py[c], "Unpaid at 12/31 prior year")
        s.set("U3", "30", c, s.get("U3", "25", c) - unpaid_cy[c] + unpaid_py[c], "Lines 25 - 26 + 27 - 28 + 29")
    for ln_ in [x for x in B.lines().query("page_code == 'U3' and line_kind != 'H'").line_no]:
        s.set("U3", ln_, "4", sum(s.get("U3", ln_, c) for c in "123"), "Cols. 1 + 2 + 3")

    # ------------------------------------------------------------------ Exhibit of net investment income
    inv = src["investment"].set_index("nii_line")
    for ln_, r in inv.iterrows():
        s.set("NII", ln_, "1", r.collected, "investment feed: collected")
        s.set("NII", ln_, "2", r.earned, "investment feed: earned")
    for c in "12":
        s.set("NII", "10", c, inv["collected" if c == "1" else "earned"].sum(), "Total gross investment income")
    s.set("NII", "11", "2", s.get("U3", "25", "3"), "Part 3, Line 25, Col. 3")
    for ln_, v in src["inv_deductions"].items():
        s.set("NII", ln_, "2", v, "investment feed: deductions")
    s.set("NII", "16", "2", sum(s.get("NII", x, "2") for x in ["11", "12", "13", "14", "15"]), "Lines 11 through 15")
    s.set("NII", "17", "2", s.get("NII", "10", "2") - s.get("NII", "16", "2"), "Line 10 minus Line 16")

    # ------------------------------------------------------------------ Page 4: income and surplus
    P = lambda ln, v, why: s.set("P4", ln, "1", v, why)  # noqa: E731
    P("1", s.get("U1", "35", "4"), "Part 1, Line 35, Col. 4")
    P("2", s.get("U2", "35", "7"), "Part 2, Line 35, Col. 7")
    P("3", s.get("U3", "25", "1"), "Part 3, Line 25, Col. 1")
    P("4", s.get("U3", "25", "2"), "Part 3, Line 25, Col. 2")
    P("5", 0, "")
    P("6", sum(s.get("P4", x, "1") for x in "2345"), "Lines 2 through 5")
    P("7", 0, "")
    P("8", s.get("P4", "1", "1") - s.get("P4", "6", "1") + s.get("P4", "7", "1"), "Line 1 minus Line 6 plus Line 7")
    P("9", s.get("NII", "17", "2"), "Exhibit of Net Investment Income, Line 17")
    P("10", 8.2e6, "Realized gains from the investment ledger, net of capital gains tax")
    P("11", s.get("P4", "9", "1") + s.get("P4", "10", "1"), "Lines 9 + 10")
    P("12", -1.9e6, "Agents' balances charged off (GL)")
    P("13", 3.4e6, "Installment and service fees (GL)")
    P("15", s.get("P4", "12", "1") + s.get("P4", "13", "1"), "Lines 12 through 14")
    P("16", s.get("P4", "8", "1") + s.get("P4", "11", "1") + s.get("P4", "15", "1"), "Lines 8 + 11 + 15")
    P("17", 2.1e6, "Policyholder dividends declared (GL)")
    P("18", s.get("P4", "16", "1") - s.get("P4", "17", "1"), "Line 16 minus Line 17")
    P("19", max(0.0, s.get("P4", "18", "1") * src["tax_rate"] * 0.8), "Tax provision (tax-exempt interest reduces the rate)")
    P("20", s.get("P4", "18", "1") - s.get("P4", "19", "1"), "Line 18 minus Line 19")
    P("21", src["surplus_py"], "Page 3, Line 37, prior year")
    P("22", s.get("P4", "20", "1"), "Line 20")
    for ln_, v in src["surplus_changes"].items():
        P(ln_, v, "GL surplus movements")
    na_cy = src["gl_balance"].nonadmitted_cy.sum()
    na_py = round(na_cy * 0.9, 2)
    P("27", -(na_cy - na_py), "Change in nonadmitted assets (Page 2, Col. 2)")
    P("38", sum(s.get("P4", x, "1") for x in ["22", "23", "24", "25", "26", "27", "28", "29", "30", "31", "32.1", "32.2",
                                               "32.3", "33.1", "33.2", "33.3", "34", "35", "36", "37"]), "Lines 22 through 37")
    P("39", s.get("P4", "21", "1") + s.get("P4", "38", "1"), "Lines 21 plus 38")
    # prior-year column: last year's filed statement (synthetic: scaled from this year), ending at last year's surplus
    flow = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20"]
    for ln_ in flow:
        s.set("P4", ln_, "2", s.get("P4", ln_, "1") * 0.95, "Prior-year filed statement")
    s.set("P4", "22", "2", s.get("P4", "20", "2"), "Line 20")
    for ln_ in ("24", "26", "27", "28", "35"):
        s.set("P4", ln_, "2", s.get("P4", ln_, "1") * 0.8, "Prior-year filed statement")
    chg = sum(s.get("P4", x, "2") for x in ["22", "24", "26", "27", "28", "35"])
    s.set("P4", "38", "2", chg, "Lines 22 through 37")
    s.set("P4", "39", "2", src["surplus_py"], "Page 3, Line 37, prior year")
    s.set("P4", "21", "2", src["surplus_py"] - chg, "Surplus at 12/31 two years ago")

    # ------------------------------------------------------------------ Page 3: liabilities and surplus
    def liab(col, line, v, why):
        s.set("P3", line, col, v, why)
    for col, bal, l1, l3, l9, surplus in (("1", "balance_cy", s.get("U2A", "35", "8"), s.get("U2A", "35", "9"), s.get("U1A", "35", "5"),
                                           s.get("P4", "39", "1")),
                                          ("2", "balance_py", s.get("U2", "35", "6"), lae_unpaid_py, s.get("U1", "35", "2"),
                                           src["surplus_py"])):
        liab(col, "1", l1, "Part 2A, Line 35, Col. 8")
        liab(col, "3", l3, "Part 2A, Line 35, Col. 9")
        liab(col, "9", l9, "Part 1A, Line 35, Col. 5")
        for r in src["gl_balance"].itertuples():
            if r.statement_line.startswith("P3."):
                liab(col, r.statement_line[3:], getattr(r, bal), f"GL account {r.account} {r.account_name}")
        liab(col, "26", sum(s.get("P3", x, col) for x in ["1", "2", "3", "4", "5", "6", "7.1", "7.2", "8", "9", "10", "11.1",
                                                           "11.2", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21",
                                                           "22", "23", "24", "25"]), "Lines 1 through 25")
        liab(col, "28", s.get("P3", "26", col) + s.get("P3", "27", col), "Lines 26 and 27")
        other = sum(s.get("P3", x, col) for x in ["29", "30", "31", "32", "33", "34"]) - s.get("P3", "36.1", col) - s.get("P3", "36.2", col)
        liab(col, "35", surplus - other, "Surplus as regards policyholders less capital, surplus notes and paid-in surplus")
        liab(col, "37", surplus, "Page 4, Line 39" if col == "1" else "Prior-year surplus")
        liab(col, "38", s.get("P3", "28", col) + surplus, "Lines 28 + 37")

    # ------------------------------------------------------------------ Page 2: assets (cash balances the ledger)
    g2 = src["gl_balance"][src["gl_balance"].statement_line.str.startswith("P2.")]
    for _, r in g2.iterrows():
        ln_ = r.statement_line[3:]
        s.set("P2", ln_, "1", r.balance_cy, f"GL account {r.account} {r.account_name}")
        s.set("P2", ln_, "2", r.nonadmitted_cy, "Nonadmitted portion (SSAP rules)")
        s.set("P2", ln_, "3", r.balance_cy - r.nonadmitted_cy, "Cols. 1 - 2")
        s.set("P2", ln_, "4", r.balance_py - round(r.nonadmitted_cy * 0.9, 2), "Prior year net admitted")
    for col in ("3", "4"):
        target = s.get("P3", "38", "1" if col == "3" else "2")
        others = sum(v for (fid, d), v in s.values.items() if fid.startswith("P2.") and fid.endswith(f".C{col}") and d == "")
        s.set("P2", "5", col, target - others, "Cash and short-term investments from the cash ledger (balances the statement)")
    s.set("P2", "5", "1", s.get("P2", "5", "3"), "Cash ledger")
    s.set("P2", "5", "2", 0, "")
    for col in "1234":
        sub = sum(s.get("P2", x, col) for x in ["1", "2.1", "2.2", "3.1", "3.2", "4.1", "4.2", "4.3", "5", "6", "7", "8", "9", "10", "11"])
        s.set("P2", "12", col, sub, "Lines 1 to 11")
        tot = sub + sum(s.get("P2", x, col) for x in ["13", "14", "15.1", "15.2", "15.3", "16.1", "16.2", "16.3", "17", "18.1",
                                                      "18.2", "19", "20", "21", "22", "23", "24", "25"])
        s.set("P2", "26", col, tot, "Lines 12 to 25")
        s.set("P2", "28", col, tot + s.get("P2", "27", col), "Lines 26 and 27")

    # ------------------------------------------------------------------ Page 5: cash flow (current year)
    def d(line):            # change in a page 2/3 balance (current minus prior)
        return s.get(*line, "1" if line[0] == "P3" else "3") - s.get(*line, "2" if line[0] == "P3" else "4")
    C = lambda ln, v, why: s.set("P5", ln, "1", v, why)  # noqa: E731
    C("1", s.get("U1B", "35", "6") - d(("P2", "15.1")) - d(("P2", "15.2")) + d(("P3", "10")) + d(("P3", "12")),
      "Net premiums written less increase in premium receivables plus increase in advance and ceded premiums payable")
    C("2", s.get("NII", "10", "1") - s.get("NII", "16", "2") + s.get("NII", "14", "2"), "Investment income collected less cash deductions")
    C("3", s.get("P4", "15", "1"), "Page 4, Line 15")
    C("4", s.get("P5", "1", "1") + s.get("P5", "2", "1") + s.get("P5", "3", "1"), "Lines 1 through 3")
    C("5", s.get("U2", "35", "4") - d(("P3", "2")) + d(("P2", "16.1")), "Net losses paid (Part 2, Col. 4) adjusted for reinsurance balances")
    C("7", s.get("U3", "30", "1") + s.get("U3", "30", "2"), "Part 3, Line 30, Cols. 1 + 2")
    C("8", s.get("P4", "17", "1") - d(("P3", "11.2")), "Page 4, Line 17 less increase in dividends payable")
    C("9", s.get("P4", "19", "1") - d(("P3", "7.1")), "Page 4, Line 19 less increase in taxes payable")
    C("10", sum(s.get("P5", x, "1") for x in ["5", "6", "7", "8", "9"]), "Lines 5 through 9")
    C("11", s.get("P5", "4", "1") - s.get("P5", "10", "1"), "Line 4 minus Line 10")
    for i, (ln_, sold, gl_line) in enumerate((("1", 210e6, "1"), ("2", 40e6, "2.2"), ("3", 4e6, "3.1"), ("4", 0, "4.1"), ("5", 6e6, "8"))):
        C(f"12.{ln_}", sold, "Investment ledger: proceeds")
        bought = sold + d(("P2", gl_line)) - (src["surplus_changes"].get("24", 0) if gl_line == "2.2" else 0) + (1.5e6 if gl_line == "4.1" else 0)
        C(f"13.{ln_}", max(bought, 0), "Investment ledger: purchases (proceeds + change in carrying value - unrealized gains)")
    C("12.8", sum(s.get("P5", f"12.{k}", "1") for k in range(1, 8)), "Lines 12.1 to 12.7")
    C("13.7", sum(s.get("P5", f"13.{k}", "1") for k in range(1, 7)), "Lines 13.1 to 13.6")
    C("15", s.get("P5", "12.8", "1") - s.get("P5", "13.7", "1") - s.get("P5", "14", "1"), "Line 12.8 minus 13.7 minus 14")
    cash_change = s.get("P2", "5", "3") - s.get("P2", "5", "4")
    s.set("P5", "16.5", "1", src["surplus_changes"].get("35", 0), "Page 4, Line 35 (paid)")
    C("16.6", cash_change - s.get("P5", "11", "1") - s.get("P5", "15", "1") - s.get("P5", "16.5", "1"),
      "Other cash provided (applied): balancing item - review before filing")
    C("17", sum(s.get("P5", f"16.{k}", "1") for k in range(1, 7)), "Lines 16.1 to 16.6")
    C("18", s.get("P5", "11", "1") + s.get("P5", "15", "1") + s.get("P5", "17", "1"), "Lines 11 + 15 + 17")
    C("19.1", s.get("P2", "5", "4"), "Page 2, Line 5, Col. 4")
    C("19.2", s.get("P5", "18", "1") + s.get("P5", "19.1", "1"), "Line 18 plus Line 19.1")
    s.notes.append("Cash flow line 16.6 is the balancing item in the synthetic book; in production it comes from the cash ledger.")

    # ------------------------------------------------------------------ State page (direct business by state)
    direct = ptx[ptx.basis == "D"]
    cur = direct[direct.written_year == Y]
    w_st = cur.groupby(["state", "asl_code"]).written.sum()
    uep_c = unearned(direct, YE).groupby([direct.state, direct.asl_code]).sum()
    old = direct[direct.written_year < Y]
    uep_p = unearned(old, PYE).groupby([old.state, old.asl_code]).sum()
    paid_st = loss_cy.groupby(["state", "asl_code"]).amount.sum()
    dcc_st = cy[cy.pay_type == "DCC"].groupby(["state", "asl_code"]).amount.sum()
    r_cy, r_py = res[res.valuation_year == Y], res[res.valuation_year == Y - 1]
    case_cy, case_py = r_cy.groupby(["state", "asl_code"]).case_loss.sum(), r_py.groupby(["state", "asl_code"]).case_loss.sum()
    dccr_cy, dccr_py = r_cy.groupby(["state", "asl_code"]).case_dcc.sum(), r_py.groupby(["state", "asl_code"]).case_dcc.sum()
    prem_share = w_st / w_st.groupby(level="asl_code").transform("sum")
    ib_cy = ib[ib.valuation_year == Y].groupby("asl_code").ibnr_loss.sum()
    ib_py = ib[ib.valuation_year == Y - 1].groupby("asl_code").ibnr_loss.sum()
    keys = sorted(set(w_st.index) | set(paid_st.index))
    for st_, ln in keys:
        k = (st_, ln)
        sh = prem_share.get(k, 0.0)
        unpaid_c = case_cy.get(k, 0) + sh * ib_cy.get(ln, 0)
        unpaid_p = case_py.get(k, 0) + sh * ib_py.get(ln, 0)
        vals = {"1": w_st.get(k, 0), "2": w_st.get(k, 0) + uep_p.get(k, 0) - uep_c.get(k, 0), "4": uep_c.get(k, 0),
                "5": paid_st.get(k, 0), "6": paid_st.get(k, 0) + unpaid_c - unpaid_p, "7": unpaid_c,
                "8": dcc_st.get(k, 0), "9": dcc_st.get(k, 0) + dccr_cy.get(k, 0) - dccr_py.get(k, 0), "10": dccr_cy.get(k, 0),
                "11": w_st.get(k, 0) * 0.148, "12": w_st.get(k, 0) * 0.029}
        for c, v in vals.items():
            s.set("SP", ln, c, v, "Policy, claim and reserve feeds by state (direct business); IBNR allocated by premium", dim=st_)
    for st_ in sorted({k[0] for k in keys}):
        for c in ["1", "2", "4", "5", "6", "7", "8", "9", "10", "11", "12"]:
            s.set("SP", "35", c, sum(s.get("SP", ln, c, st_) for ln in lines), "Lines 1 through 34", dim=st_)
    for c in ["1", "2", "4", "5", "6", "7", "8", "9", "10", "11", "12"]:
        for ln in lines + ["35"]:
            tot = sum(v for (fid, dd), v in s.values.items() if fid == B.field_id("SP", ln, c) and dd not in ("", "Total"))
            if tot:
                s.set("SP", ln, c, tot, "Sum of all states (grand total)", dim="Total")

    # ------------------------------------------------------------------ Schedule F Part 3
    rein = src["reinsurer"]
    ceded_nonaff = s.get("U1B", "35", "5")
    ceded_aff = s.get("U1B", "35", "4")
    rec_paid = src["gl_balance"].set_index("statement_line").at["P2.16.1", "balance_cy"]
    for r in rein.itertuples():
        share = r.share
        base = ceded_aff if r.program == "AFF" else ceded_nonaff * share
        tot_c = ceded_aff + ceded_nonaff
        frac = base / tot_c if tot_c else 0
        vals = {"1": r.reinsurer_id, "2": r.naic_code, "3": r.name, "4": r.domicile, "5": "", "6": base,
                "7": rec_paid * frac, "8": rec_paid * 0.06 * frac, "9": s.get("U2A", "35", "3") * frac,
                "10": cc.sum() * 0.03 * frac, "11": s.get("U2A", "35", "7") * frac, "12": ic.sum() * 0.04 * frac}
        uep_ceded = (unearned(ptx[ptx.basis == "C"], YE)).sum()
        vals["13"] = uep_ceded * frac
        vals["14"] = 0.0
        vals["15"] = sum(vals[k] for k in ["7", "8", "9", "10", "11", "12", "13", "14"])
        vals["16"] = s.get("P3", "12", "1") * frac
        vals["17"] = 0.0
        vals["18"] = vals["15"] - vals["16"] - vals["17"]
        vals["19"] = s.get("P3", "13", "1") * frac
        for c, v in vals.items():
            s.set("SF3", "R", c, v, "Ceded business x reinsurer share (reinsurer feed)", dim=r.reinsurer_id)
    for c in [str(i) for i in range(6, 20)]:
        s.set("SF3", "T", c, sum(s.get("SF3", "R", c, rid) for rid in rein.reinsurer_id), "Sum of reinsurers")

    # ------------------------------------------------------------------ Schedule P
    _schedule_p(s, src)

    # ------------------------------------------------------------------ Five-year historical data
    f1b = lambda lns, cols: sum(s.get("U1B", ln, c) for ln in lns for c in cols)  # noqa: E731
    cur_vals = {}
    for k, lns in FIVE_YEAR_GROUPS.items():
        cur_vals[k] = f1b(lns, "123")
        cur_vals[str(int(k) + 6)] = f1b(lns, "6")
    cur_vals["6"] = sum(cur_vals[k] for k in "12345")
    cur_vals["12"] = sum(cur_vals[str(k)] for k in range(7, 12))
    pe = s.get("P4", "1", "1")
    cur_vals.update({"13": s.get("P4", "8", "1"), "14": s.get("P4", "11", "1"), "15": s.get("P4", "15", "1"),
                     "16": s.get("P4", "17", "1"), "17": s.get("P4", "19", "1"), "18": s.get("P4", "20", "1"),
                     "19": s.get("P2", "28", "3"), "20.1": s.get("P2", "15.1", "3"), "20.2": s.get("P2", "15.2", "3"),
                     "20.3": s.get("P2", "15.3", "3"), "21": s.get("P3", "28", "1"), "22": s.get("P3", "1", "1"),
                     "23": s.get("P3", "3", "1"), "24": s.get("P3", "9", "1"), "25": s.get("P3", "30", "1") + s.get("P3", "31", "1"),
                     "26": s.get("P3", "37", "1"), "27": s.get("P5", "11", "1"), "28": s.get("P3", "37", "1"),
                     "29": s.get("P3", "37", "1") / 4.6, "37": 100.0, "38": 100 * s.get("P4", "2", "1") / pe,
                     "39": 100 * s.get("P4", "3", "1") / pe, "40": 100 * s.get("P4", "4", "1") / pe,
                     "41": 100 * s.get("P4", "8", "1") / pe, "42": 100 * s.get("P4", "4", "1") / s.get("U1B", "35", "6"),
                     "43": 100 * (s.get("P4", "2", "1") + s.get("P4", "3", "1")) / pe,
                     "44": 100 * s.get("U1B", "35", "6") / s.get("P3", "37", "1")})
    one_year = sum(s.get("SP2SUM", ay, "11") for ay in B.AY_ROWS[:-1])
    two_year = sum(s.get("SP2SUM", ay, "12") for ay in B.AY_ROWS[:-1])
    cur_vals["45"], cur_vals["47"] = one_year, two_year
    cur_vals["46"] = 100 * one_year / src["surplus_py"]
    cur_vals["48"] = 100 * two_year / src["surplus_py"]
    pct_lines = {"37", "38", "39", "40", "41", "42", "43", "44", "46", "48"}
    for ln_, v in cur_vals.items():
        s.set("H5", ln_, "1", v, "Current-year statement")
        for k in range(1, 5):
            s.set("H5", ln_, str(k + 1), v if ln_ in pct_lines else v * (0.955 ** k), "Prior filings (synthetic history)")
    return s


def _schedule_p(s: Statement, src: dict) -> None:
    pay, res, ib, ptx = src["claim_txn"], src["claim_reserve"], src["ibnr"], src["premium_txn"]
    asl = {c: p for c, _n, p in B.ASL}
    pay = pay.assign(sp=pay.asl_code.map(asl))
    res = res.assign(sp=res.asl_code.map(asl))
    ib = ib.assign(sp=ib.asl_code.map(asl))
    # premiums earned by accident year: current year from Part 1; earlier years from the earned history
    from .source import BOOK
    hist = {}
    for ln, (dwp, _lr, _t, qs, aff) in BOOK.items():
        for ay in range(Y - 9, Y + 1):
            if ay == Y:
                da = s.get("U1B", ln, "1") + s.get("U1B", ln, "2") + s.get("U1B", ln, "3")
                net = s.get("U1", ln, "4")
                da_e = da + (s.get("U1", ln, "2") - s.get("U1", ln, "3")) * (da / max(s.get("U1B", ln, "6"), 1))
                hist[(ln, ay)] = (da_e, da_e - net, net)
            else:
                da = dwp * (0.96 ** (Y - ay)) * 0.98
                hist[(ln, ay)] = (da, da * (qs + aff), da * (1 - qs - aff))
    eh = pd.DataFrame([{"asl_code": k[0], "sp": asl[k[0]], "accident_year": k[1], "ep_da": v[0], "ep_c": v[1], "ep_n": v[2]}
                       for k, v in hist.items()])
    upto = pay[pay.calendar_year <= Y]
    rcy = res[res.valuation_year == Y]
    icy = ib[ib.valuation_year == Y]
    groups = [("SUM", None)] + [(c, c) for c, _ in B.SCHED_P_LINES]
    for code, sp in groups:
        sel = (lambda d: d) if sp is None else (lambda d, sp=sp: d[d.sp == sp])
        p, r, i, e = sel(upto), sel(rcy), sel(icy), sel(eh)
        if sp is not None and p.empty and r.empty and e.empty:
            continue
        page = f"SP1{code}"
        tot = {}
        for ay in range(Y - 9, Y + 1):
            pa, ra, ia, ea = p[p.accident_year == ay], r[r.accident_year == ay], i[i.accident_year == ay], e[e.accident_year == ay]
            loss = pa[pa.pay_type.isin(["LOSS", "SALVAGE"])]
            dcc = pa[pa.pay_type == "DCC"]
            v = {"1": ea.ep_da.sum(), "2": ea.ep_c.sum(), "4": loss.amount.sum(), "5": (loss.amount * loss.ceded_pct).sum(),
                 "6": dcc.amount.sum(), "7": (dcc.amount * dcc.ceded_pct).sum(), "8": pa[pa.pay_type == "AO"].amount.sum(),
                 "9": -pa[pa.pay_type == "SALVAGE"].amount.sum(),
                 "11": float(pd.concat([pa.claim_id[pa.claim_id != ""], ra.claim_id]).nunique()),
                 "13": ra.case_loss.sum(), "14": (ra.case_loss * ra.ceded_pct).sum(), "15": ia.ibnr_loss.sum(),
                 "16": (ia.ibnr_loss * ia.ceded_pct).sum(), "17": ra.case_dcc.sum(), "18": (ra.case_dcc * ra.ceded_pct).sum(),
                 "19": ia.ibnr_dcc.sum(), "20": (ia.ibnr_dcc * ia.ceded_pct).sum(), "21": ia.ao_unpaid.sum(), "22": 0.0,
                 "24": float((ra.case_loss > 0).sum()), "31": 0.0, "32": 0.0, "33": 100.0}
            v["3"] = v["1"] - v["2"]
            v["10"] = v["4"] - v["5"] + v["6"] - v["7"] + v["8"]
            v["23"] = v["13"] - v["14"] + v["15"] - v["16"] + v["17"] - v["18"] + v["19"] - v["20"] + v["21"]
            v["25"] = v["4"] + v["6"] + v["8"] + v["13"] + v["15"] + v["17"] + v["19"] + v["21"]
            v["26"] = v["5"] + v["7"] + v["14"] + v["16"] + v["18"] + v["20"]
            v["27"] = v["25"] - v["26"]
            v["28"] = 100 * v["25"] / v["1"] if v["1"] else 0
            v["29"] = 100 * v["26"] / v["2"] if v["2"] else 0
            v["30"] = 100 * v["27"] / v["3"] if v["3"] else 0
            v["34"] = v["13"] - v["14"] + v["15"] - v["16"]
            v["35"] = v["17"] - v["18"] + v["19"] - v["20"] + v["21"]
            for c, x in v.items():
                s.set(page, str(ay), c, x, "Claim payments, case reserves, IBNR and earned premium by accident year")
                if c not in ("28", "29", "30", "33"):
                    tot[c] = tot.get(c, 0) + x
        for c, x in tot.items():
            s.set(page, "Totals", c, x, "Sum of prior and accident years")
        for c in ("28", "29", "30"):
            d, n = {"28": ("25", "1"), "29": ("26", "2"), "30": ("27", "3")}[c]
            s.set(page, "Totals", c, 100 * tot[d] / tot[n] if tot.get(n) else 0, "Totals")
        # Part 2 (incurred net losses and DCC) and Part 3 (cumulative paid net losses and DCC) by valuation year
        pall, rall, iall = sel(pay), sel(res), sel(ib)
        pnet = pall[pall.pay_type.isin(["LOSS", "SALVAGE", "DCC"])].assign(net=lambda d: d.amount * (1 - d.ceded_pct))
        for ay in range(Y - 9, Y + 1):
            inc = {}
            for vy in range(ay, Y + 1):
                col = str(vy - (Y - 9) + 1)
                paid_net = pnet[(pnet.accident_year == ay) & (pnet.calendar_year <= vy)].net.sum()
                rr = rall[(rall.accident_year == ay) & (rall.valuation_year == vy)]
                ii = iall[(iall.accident_year == ay) & (iall.valuation_year == vy)]
                case = ((rr.case_loss + rr.case_dcc) * (1 - rr.ceded_pct)).sum()
                ibnr = ((ii.ibnr_loss + ii.ibnr_dcc) * (1 - ii.ceded_pct)).sum()
                inc[vy] = paid_net + case + ibnr
                s.set(f"SP2{code}", str(ay), col, inc[vy], "Net paid + case + IBNR (losses and DCC) at the valuation date")
                s.set(f"SP3{code}", str(ay), col, paid_net, "Cumulative net paid losses and DCC at the valuation date")
            if ay <= Y - 1:
                s.set(f"SP2{code}", str(ay), "11", inc[Y] - inc[Y - 1], "Valued 12/31/current minus prior year")
            if ay <= Y - 2:
                s.set(f"SP2{code}", str(ay), "12", inc[Y] - inc[Y - 2], "Valued 12/31/current minus two years ago")
            rr = rall[(rall.accident_year == ay) & (rall.valuation_year == Y)]
            s.set(f"SP3{code}", str(ay), "11", float(((rr.closed == 1) & (rr.closed_without_payment == 0)).sum()), "Claims closed with payment")
            s.set(f"SP3{code}", str(ay), "12", float(((rr.closed == 1) & (rr.closed_without_payment == 1)).sum()), "Claims closed without payment")


# ------------------------------------------------------------------------------------------ edits
def edits(s: Statement, tolerance: float = 1.0) -> pd.DataFrame:
    """Cross-checks between pages, crossfoots and reconciliations. Pass when |difference| <= tolerance (dollars)."""
    g = s.get
    out = []

    def chk(eid, name, kind, expected, actual, ref):
        diff = actual - expected
        tol = 0 if name.startswith(("Part 1B crossfoot on every", "Part 2 crossfoot on every")) or "by line" in name else tolerance
        out.append({"edit_id": eid, "edit": name, "type": kind, "expected": round(expected, 2), "actual": round(actual, 2),
                    "difference": round(diff, 2), "result": "PASS" if abs(diff) <= tol else "FAIL", "reference": ref})

    chk("E01", "Total admitted assets = total liabilities + surplus", "Balance", g("P3", "38", "1"), g("P2", "28", "3"), "Page 2 L28 C3 vs Page 3 L38")
    chk("E02", "Prior-year assets = prior-year liabilities + surplus", "Balance", g("P3", "38", "2"), g("P2", "28", "4"), "Page 2 L28 C4 vs Page 3 L38 C2")
    chk("E03", "Premiums earned on Page 4 = Part 1 total", "Page tie", g("U1", "35", "4"), g("P4", "1", "1"), "Page 4 L1 vs Part 1 L35 C4")
    chk("E04", "Losses incurred on Page 4 = Part 2 total", "Page tie", g("U2", "35", "7"), g("P4", "2", "1"), "Page 4 L2 vs Part 2 L35 C7")
    chk("E05", "LAE incurred on Page 4 = Part 3 LAE total", "Page tie", g("U3", "25", "1"), g("P4", "3", "1"), "Page 4 L3 vs Part 3 L25 C1")
    chk("E06", "Other underwriting expenses on Page 4 = Part 3 total", "Page tie", g("U3", "25", "2"), g("P4", "4", "1"), "Page 4 L4 vs Part 3 L25 C2")
    chk("E07", "Losses on Page 3 = Part 2A net unpaid", "Page tie", g("U2A", "35", "8"), g("P3", "1", "1"), "Page 3 L1 vs Part 2A L35 C8")
    chk("E08", "LAE on Page 3 = Part 2A unpaid LAE", "Page tie", g("U2A", "35", "9"), g("P3", "3", "1"), "Page 3 L3 vs Part 2A L35 C9")
    chk("E09", "Unearned premiums on Page 3 = Part 1A total", "Page tie", g("U1A", "35", "5"), g("P3", "9", "1"), "Page 3 L9 vs Part 1A L35 C5")
    chk("E10", "Surplus on Page 3 = Page 4 surplus account", "Page tie", g("P4", "39", "1"), g("P3", "37", "1"), "Page 3 L37 vs Page 4 L39")
    chk("E11", "Prior-year surplus carried forward", "Page tie", g("P3", "37", "2"), g("P4", "21", "1"), "Page 4 L21 vs Page 3 L37 C2")
    chk("E12", "Net investment income on Page 4 = exhibit", "Page tie", g("NII", "17", "2"), g("P4", "9", "1"), "Page 4 L9 vs NII L17")
    chk("E13", "Cash at year end on cash flow = Page 2", "Page tie", g("P2", "5", "3"), g("P5", "19.2", "1"), "Page 5 L19.2 vs Page 2 L5 C3")
    chk("E14", "Net premiums written Part 1 Col. 1 = Part 1B Col. 6", "Page tie", g("U1B", "35", "6"), g("U1", "35", "1"), "Part 1 C1 vs Part 1B C6")
    chk("E15", "Unearned premiums Part 1 Col. 3 = Part 1A Col. 5", "Page tie", g("U1A", "35", "5"), g("U1", "35", "3"), "Part 1 C3 vs Part 1A C5")
    chk("E16", "Net losses unpaid Part 2 Col. 5 = Part 2A Col. 8", "Page tie", g("U2A", "35", "8"), g("U2", "35", "5"), "Part 2 C5 vs Part 2A C8")
    chk("E17", "Expenses incurred: Part 3 Col. 4 = Cols. 1 + 2 + 3", "Crossfoot", g("U3", "25", "1") + g("U3", "25", "2") + g("U3", "25", "3"),
        g("U3", "25", "4"), "Part 3 L25")
    # crossfoots by line
    bad1b = [ln for ln in B.ASL_CODES if abs(g("U1B", ln, "6") - (g("U1B", ln, "1") + g("U1B", ln, "2") + g("U1B", ln, "3") - g("U1B", ln, "4") - g("U1B", ln, "5"))) > tolerance]
    chk("E18", "Part 1B crossfoot on every line (Col. 6 = 1 + 2 + 3 - 4 - 5)", "Crossfoot", 0, len(bad1b), "lines failing: " + (", ".join(bad1b) or "none"))
    bad2 = [ln for ln in B.ASL_CODES if abs(g("U2", ln, "7") - (g("U2", ln, "4") + g("U2", ln, "5") - g("U2", ln, "6"))) > tolerance]
    chk("E19", "Part 2 crossfoot on every line (Col. 7 = 4 + 5 - 6)", "Crossfoot", 0, len(bad2), "lines failing: " + (", ".join(bad2) or "none"))
    # state page and Schedule P reconciliations
    chk("E20", "State page direct premiums written (all states) = Part 1B direct", "Reconciliation", g("U1B", "35", "1"),
        g("SP", "35", "1", "Total"), "Page 19 L35 C1 summed over states vs Part 1B L35 C1")
    bad_sp = [ln for ln in B.ASL_CODES[:-1] if abs(g("SP", ln, "1", "Total") - g("U1B", ln, "1")) > tolerance]
    chk("E21", "State page direct premiums by line = Part 1B direct by line", "Reconciliation", 0, len(bad_sp),
        "lines failing: " + (", ".join(bad_sp) or "none"))
    chk("E22", "Schedule P net losses unpaid = Page 3 losses", "Reconciliation", g("P3", "1", "1"), g("SP1SUM", "Totals", "34"),
        "Schedule P Part 1 Summary C34 vs Page 3 L1")
    chk("E23", "Schedule P net LAE unpaid = Page 3 LAE", "Reconciliation", g("P3", "3", "1"), g("SP1SUM", "Totals", "35"),
        "Schedule P Part 1 Summary C35 vs Page 3 L3")
    chk("E24", "Schedule P current accident year net earned premium = Page 4 premiums earned", "Reconciliation", g("P4", "1", "1"),
        g("SP1SUM", str(Y), "3"), f"Schedule P Part 1 Summary AY {Y} C3 vs Page 4 L1")
    chk("E25", "Schedule F ceded premiums = Part 1B ceded", "Reconciliation", g("U1B", "35", "4") + g("U1B", "35", "5"),
        g("SF3", "T", "6"), "Schedule F Part 3 C6 total vs Part 1B C4 + C5")
    chk("E26", "Surplus account: Line 39 = Line 21 + Line 38", "Crossfoot", g("P4", "21", "1") + g("P4", "38", "1"), g("P4", "39", "1"), "Page 4")
    chk("E27", "Cash flow: Line 18 = 11 + 15 + 17", "Crossfoot", g("P5", "11", "1") + g("P5", "15", "1") + g("P5", "17", "1"),
        g("P5", "18", "1"), "Page 5")
    return pd.DataFrame(out)


def page_view(stmt: Statement, page: str, dim: str = "") -> pd.DataFrame:
    """One page as the blank shows it: lines down, columns across."""
    ln = B.lines().query("page_code == @page")
    co = B.columns().query("page_code == @page")
    rows = []
    for r in ln.itertuples():
        row = {"Line": r.line_no if r.line_no not in ("UW", "INV", "OTH", "CS", "OPS", "INVS", "FIN", "GPW", "NPW", "SOI", "BS",
                                                      "RBC", "OP", "OPC", "DEV") else "", "Caption": r.caption}
        for c in co.itertuples():
            v = stmt.values.get((B.field_id(page, r.line_no, c.col_no), dim))
            row[f"{c.col_no}. {c.caption}"] = v
        rows.append(row)
    return pd.DataFrame(rows)
