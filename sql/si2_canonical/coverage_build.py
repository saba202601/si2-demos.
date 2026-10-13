"""Writes 08_coverage.sql: the claim coverage tables (schema cov), the synthetic forms, policies and claims, and the new
causes of loss with their loss words as canonical pick-list options and synonyms.

    python sql/si2_canonical/coverage_build.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import coverage as C  # noqa: E402

BY = "SI2 coverage"

SCHEMA = r"""/* =====================================================================================================
   SI² Canonical Master · claim coverage check
   -----------------------------------------------------------------------------------------------------
   cov.Form / FormSection     every policy form and its sections (covered, exclusion, additional coverage, limit,
                              deductible, condition) with the causes of loss each section names
   cov.Policy / PolicyCoverage / PolicyForm   limits and deductibles by coverage, and the forms attached to the policy
   cov.Claim / ClaimPayment   the claim as the adjuster recorded it, and what was paid to whom
   cov.CoverageAlert          what SI² found and who must look: the adjuster for coverage, the underwriter with a copy to the
                              claims manager for limits, deductibles and coverage changes; closed by someone other than the adjuster
   Forms, policies and claims loaded here are synthetic (IsSynthetic = 1). Safe to re-run.
   ===================================================================================================== */
USE SI2Canonical;
GO
IF SCHEMA_ID(N'cov') IS NULL EXEC (N'CREATE SCHEMA cov');
GO
IF OBJECT_ID(N'cov.Form') IS NULL
CREATE TABLE cov.Form (
    FormId       int IDENTITY(1,1) NOT NULL CONSTRAINT PK_CovForm PRIMARY KEY,
    FormNumber   nvarchar(40)   NOT NULL,
    Edition      varchar(10)    NOT NULL CONSTRAINT DF_CovForm_Ed DEFAULT (''),
    Title        nvarchar(300)  NOT NULL,
    LobCode      varchar(20)    NULL,
    Products     varchar(200)   NULL,
    States       varchar(200)   NULL,
    FormKind     varchar(12)    NOT NULL CONSTRAINT CK_CovForm_Kind CHECK (FormKind IN ('BASE', 'ENDORSEMENT')),
    Source       varchar(20)    NOT NULL CONSTRAINT DF_CovForm_Src DEFAULT ('SYNTHETIC'),   -- SYNTHETIC, PDF, TEXT
    FormText     nvarchar(max)  NOT NULL,
    IsSynthetic  bit            NOT NULL CONSTRAINT DF_CovForm_Syn DEFAULT (0),
    Status       varchar(10)    NOT NULL CONSTRAINT DF_CovForm_Status DEFAULT ('ACTIVE'),
    LoadedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_CovForm_By DEFAULT (SUSER_SNAME()),
    LoadedAt     datetime2(0)   NOT NULL CONSTRAINT DF_CovForm_At DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT UQ_CovForm UNIQUE (FormNumber, Edition)
);
GO
IF OBJECT_ID(N'cov.FormSection') IS NULL
CREATE TABLE cov.FormSection (
    SectionId    int IDENTITY(1,1) NOT NULL CONSTRAINT PK_CovSection PRIMARY KEY,
    FormId       int NOT NULL CONSTRAINT FK_CovSection_Form REFERENCES cov.Form (FormId),
    Seq          int NOT NULL,
    Heading      nvarchar(300)  NOT NULL,
    SectionType  varchar(12)    NOT NULL CONSTRAINT CK_CovSection_Type CHECK (SectionType IN
                 ('COVERED', 'EXCLUSION', 'ADDS', 'LIMIT', 'DEDUCTIBLE', 'CONDITION', 'DEFINITION', 'OTHER')),
    Coverages    varchar(200)   NULL,
    OpenPerils   bit            NOT NULL CONSTRAINT DF_CovSection_Open DEFAULT (0),
    CauseCodes   varchar(400)   NULL,
    SectionText  nvarchar(max)  NOT NULL,
    ReviewedBy   nvarchar(100)  NULL,         -- a person confirms how SI² read the section
    CONSTRAINT UQ_CovSection UNIQUE (FormId, Seq)
);
GO
IF OBJECT_ID(N'cov.Policy') IS NULL
CREATE TABLE cov.Policy (
    PolicyNumber   nvarchar(40)  NOT NULL CONSTRAINT PK_CovPolicy PRIMARY KEY,
    ProductCode    varchar(20)   NOT NULL,
    LobCode        varchar(20)   NOT NULL,
    StateCode      char(2)       NOT NULL,
    InsuredName    nvarchar(200) NOT NULL,
    EffectiveDate  date          NOT NULL,
    ExpirationDate date          NOT NULL,
    IsSynthetic    bit           NOT NULL CONSTRAINT DF_CovPolicy_Syn DEFAULT (0)
);
GO
IF OBJECT_ID(N'cov.PolicyCoverage') IS NULL
CREATE TABLE cov.PolicyCoverage (
    PolicyNumber     nvarchar(40)   NOT NULL CONSTRAINT FK_CovPC_Policy REFERENCES cov.Policy (PolicyNumber),
    CoverageCode     varchar(20)    NOT NULL,     -- canonical COVERAGE pick list
    LimitAmount      decimal(19, 2) NOT NULL,
    DeductibleAmount decimal(19, 2) NOT NULL CONSTRAINT DF_CovPC_Ded DEFAULT (0),
    CONSTRAINT PK_CovPolicyCoverage PRIMARY KEY (PolicyNumber, CoverageCode)
);
GO
IF OBJECT_ID(N'cov.PolicyForm') IS NULL
CREATE TABLE cov.PolicyForm (
    PolicyNumber nvarchar(40) NOT NULL CONSTRAINT FK_CovPF_Policy REFERENCES cov.Policy (PolicyNumber),
    FormNumber   nvarchar(40) NOT NULL,
    Seq          int          NOT NULL,
    CONSTRAINT PK_CovPolicyForm PRIMARY KEY (PolicyNumber, FormNumber)
);
GO
IF OBJECT_ID(N'cov.Claim') IS NULL
CREATE TABLE cov.Claim (
    ClaimNumber        nvarchar(40)   NOT NULL CONSTRAINT PK_CovClaim PRIMARY KEY,
    PolicyNumber       nvarchar(40)   NOT NULL,
    LossDate           date           NULL,
    ReportedDate       date           NULL,
    CauseCode          varchar(20)    NULL,
    CoverageCode       varchar(20)    NULL,
    LossDescription    nvarchar(max)  NULL,
    Notes              nvarchar(max)  NULL,
    AdjusterName       nvarchar(100)  NULL,
    RecordedLimit      decimal(19, 2) NULL,
    RecordedDeductible decimal(19, 2) NULL,
    GrossLoss          decimal(19, 2) NULL,
    PaidAmount         decimal(19, 2) NOT NULL CONSTRAINT DF_CovClaim_Paid DEFAULT (0),
    ReserveAmount      decimal(19, 2) NOT NULL CONSTRAINT DF_CovClaim_Res DEFAULT (0),
    IsSynthetic        bit            NOT NULL CONSTRAINT DF_CovClaim_Syn DEFAULT (0)
);
GO
IF OBJECT_ID(N'cov.ClaimPayment') IS NULL
CREATE TABLE cov.ClaimPayment (
    PaymentId    int IDENTITY(1,1) NOT NULL CONSTRAINT PK_CovPayment PRIMARY KEY,
    ClaimNumber  nvarchar(40)   NOT NULL CONSTRAINT FK_CovPayment_Claim REFERENCES cov.Claim (ClaimNumber),
    Amount       decimal(19, 2) NOT NULL,
    Payee        nvarchar(200)  NOT NULL,
    PayeeType    varchar(12)    NOT NULL CONSTRAINT DF_CovPayment_Type DEFAULT ('VENDOR'),
    PaymentDate  date           NOT NULL
);
GO
IF OBJECT_ID(N'cov.CoverageAlert') IS NULL
CREATE TABLE cov.CoverageAlert (
    AlertId      int IDENTITY(1,1) NOT NULL CONSTRAINT PK_CovAlert PRIMARY KEY,
    ClaimNumber  nvarchar(40)   NOT NULL,
    PolicyNumber nvarchar(40)   NULL,
    AlertType    varchar(30)    NOT NULL,
    Title        nvarchar(200)  NOT NULL,
    Severity     varchar(10)    NOT NULL,
    SendTo       varchar(40)    NOT NULL,      -- rules.Role code
    CopyTo       varchar(40)    NULL,
    Message      nvarchar(1000) NOT NULL,
    Evidence     nvarchar(2000) NULL,
    AdjusterName nvarchar(100)  NULL,
    Status       varchar(10)    NOT NULL CONSTRAINT DF_CovAlert_Status DEFAULT ('OPEN')
                 CONSTRAINT CK_CovAlert_Status CHECK (Status IN ('OPEN', 'CLOSED')),
    RaisedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_CovAlert_By DEFAULT (N'SI2 claim check'),
    RaisedAt     datetime2(0)   NOT NULL CONSTRAINT DF_CovAlert_At DEFAULT (SYSUTCDATETIME()),
    ClosedBy     nvarchar(100)  NULL,
    ClosedAt     datetime2(0)   NULL,
    CloseNote    nvarchar(1000) NULL,
    CONSTRAINT CK_CovAlert_NotOwnClaim CHECK (ClosedBy IS NULL OR AdjusterName IS NULL OR ClosedBy <> AdjusterName)
);
GO
CREATE OR ALTER VIEW cov.vw_AlertInbox
AS
SELECT a.AlertId, a.Status, a.Severity, a.SendTo, ISNULL(r.Name, a.SendTo) AS SendToRole, a.CopyTo, ISNULL(c.Name, a.CopyTo) AS CopyToRole,
       a.ClaimNumber, a.PolicyNumber, a.Title, a.Message, a.Evidence, a.AdjusterName, a.RaisedAt, a.ClosedBy, a.ClosedAt, a.CloseNote
FROM cov.CoverageAlert a
LEFT JOIN rules.Role r ON r.RoleCode = a.SendTo
LEFT JOIN rules.Role c ON c.RoleCode = a.CopyTo;
GO
-- Closing an alert: never by the adjuster who handles the claim (checked by CK_CovAlert_NotOwnClaim too).
CREATE OR ALTER PROCEDURE cov.usp_CloseAlert
    @AlertId int,
    @ClosedBy nvarchar(100),
    @Note nvarchar(1000)
AS
BEGIN
    SET NOCOUNT ON;
    IF NULLIF(LTRIM(RTRIM(@Note)), N'') IS NULL THROW 50021, N'Say why the alert is closed.', 1;
    IF EXISTS (SELECT 1 FROM cov.CoverageAlert WHERE AlertId = @AlertId AND AdjusterName = @ClosedBy)
        THROW 50022, N'The adjuster on the claim cannot close an alert about that claim.', 1;
    UPDATE cov.CoverageAlert SET Status = 'CLOSED', ClosedBy = @ClosedBy, ClosedAt = SYSUTCDATETIME(), CloseNote = @Note
    WHERE AlertId = @AlertId AND Status = 'OPEN';
    IF @@ROWCOUNT = 0 THROW 50023, N'Alert not found or already closed.', 1;
END;
GO
"""


def q(v) -> str:
    if v is None:
        return "CAST(NULL AS nvarchar(4000))"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(float(v)) if isinstance(v, float) and not float(v).is_integer() else str(int(v))
    return "N'" + str(v).replace("'", "''") + "'"


def values(rows: list[tuple], cols: str, target: str, key_where: str, alias: str = "v") -> str:
    out = []
    for i in range(0, len(rows), 400):
        chunk = rows[i:i + 400]
        out.append(f"INSERT {target}\nSELECT {cols}\nFROM (VALUES\n" + ",\n".join("    (" + ", ".join(q(x) for x in r) + ")" for r in chunk)
                   + f"\n) {alias} " + key_where + ";\nGO")
    return "\n".join(out)


def build_sql() -> str:
    lib = C.FormLibrary.synthetic()
    pols = C.synthetic_policies()
    claims = C.synthetic_claims(pols, lib=lib)
    out = [SCHEMA, "-- New causes of loss and the words claims use for them (canonical CAUSE_OF_LOSS options and synonyms)"]
    opts = [(code, name, f"Cause of loss used by the SI² coverage check.") for code, name in C.NEW_CAUSES]
    out.append(values(opts, "p.PickListId, v.c, v.n, v.d, '*', '*', 900, '2020-01-01', N'" + BY + "'",
                      "canon.PickListOption (PickListId, OptionCode, OptionName, Description, LobScope, StateScope, SortOrder, EffectiveFrom, CreatedBy)",
                      "(c, n, d) JOIN canon.PickList p ON p.PickListCode = 'CAUSE_OF_LOSS' AND p.ScopeId = 1\n"
                      "WHERE NOT EXISTS (SELECT 1 FROM canon.PickListOption x WHERE x.PickListId = p.PickListId AND x.OptionCode = v.c AND x.ScopeId = 1)"))
    syn = sorted({(code, w) for code, words in C.CAUSE_WORDS.items() for w in words})
    out.append(values(syn, "'OPTION', o.OptionId, v.w, 'BUSINESS', N'*', N'" + BY + "'",
                      "canon.Synonym (ObjectType, ObjectId, SynonymText, SynonymType, SourceSystem, CreatedBy)",
                      "(c, w)\nCROSS APPLY (SELECT TOP (1) o.OptionId FROM canon.PickListOption o JOIN canon.PickList p ON p.PickListId = o.PickListId "
                      "WHERE p.PickListCode = 'CAUSE_OF_LOSS' AND o.OptionCode = v.c AND o.Status = 'ACTIVE' ORDER BY o.ScopeId) o\n"
                      "WHERE NOT EXISTS (SELECT 1 FROM canon.Synonym s WHERE s.ObjectType = 'OPTION' AND s.ObjectId = o.OptionId AND s.SynonymText = v.w)"))
    out.append("-- Synthetic forms (SI²'s own wording) and how SI² read them")
    forms = [(f["number"], f["edition"], f["title"], f["lob"], ",".join(f["products"]), ",".join(f.get("states", [])) or None, f["kind"], f["text"].strip())
             for f in C.FORMS]
    out.append(values(forms, "v.n, v.e, v.t, v.l, v.p, v.s, v.k, 'SYNTHETIC', v.x, 1, N'" + BY + "'",
                      "cov.Form (FormNumber, Edition, Title, LobCode, Products, States, FormKind, Source, FormText, IsSynthetic, LoadedBy)",
                      "(n, e, t, l, p, s, k, x)\nWHERE NOT EXISTS (SELECT 1 FROM cov.Form f WHERE f.FormNumber = v.n AND f.Edition = v.e)"))
    secs = []
    for f in C.FORMS:
        for s in lib.sections[f["number"]]:
            secs.append((f["number"], f["edition"], s["seq"], s["heading"], s["type"], ",".join(s["coverages"]) or None, s["open_perils"],
                         ",".join(sorted({c for cl in s["clauses"] for c in cl["causes"]})) or None, " ".join(c["text"] for c in s["clauses"]) or s["heading"]))
    out.append(values(secs, "f.FormId, v.s, v.h, v.t, v.c, v.o, v.cc, v.x",
                      "cov.FormSection (FormId, Seq, Heading, SectionType, Coverages, OpenPerils, CauseCodes, SectionText)",
                      "(n, e, s, h, t, c, o, cc, x) JOIN cov.Form f ON f.FormNumber = v.n AND f.Edition = v.e\n"
                      "WHERE NOT EXISTS (SELECT 1 FROM cov.FormSection z WHERE z.FormId = f.FormId AND z.Seq = v.s)"))
    out.append("-- Synthetic policies, coverages and attached forms")
    out.append(values([(p["policy_number"], p["product"], p["lob"], p["state"], p["insured"], p["effective"], p["expiration"]) for p in pols.values()],
                      "v.n, v.p, v.l, v.s, v.i, v.e, v.x, 1", "cov.Policy (PolicyNumber, ProductCode, LobCode, StateCode, InsuredName, EffectiveDate, ExpirationDate, IsSynthetic)",
                      "(n, p, l, s, i, e, x)\nWHERE NOT EXISTS (SELECT 1 FROM cov.Policy z WHERE z.PolicyNumber = v.n)"))
    out.append(values([(p["policy_number"], c, float(r["limit"]), float(r["deductible"])) for p in pols.values() for c, r in p["coverages"].items()],
                      "v.n, v.c, v.l, v.d", "cov.PolicyCoverage (PolicyNumber, CoverageCode, LimitAmount, DeductibleAmount)",
                      "(n, c, l, d)\nWHERE NOT EXISTS (SELECT 1 FROM cov.PolicyCoverage z WHERE z.PolicyNumber = v.n AND z.CoverageCode = v.c)"))
    out.append(values([(p["policy_number"], f, i + 1) for p in pols.values() for i, f in enumerate(p["forms"])],
                      "v.n, v.f, v.s", "cov.PolicyForm (PolicyNumber, FormNumber, Seq)",
                      "(n, f, s)\nWHERE NOT EXISTS (SELECT 1 FROM cov.PolicyForm z WHERE z.PolicyNumber = v.n AND z.FormNumber = v.f)"))
    out.append("-- Synthetic claims and payments (some carry findings on purpose)")
    out.append(values([(c["claim_number"], c["policy_number"], c["loss_date"], c["reported_date"], c["cause"], c["coverage"], c["description"], c["notes"] or None,
                        c["adjuster"], c["recorded_limit"], c["recorded_deductible"], c["gross_loss"], c["paid"], c["reserve"]) for c in claims],
                      "v.n, v.p, v.ld, v.rd, v.ca, v.co, v.de, v.nt, v.ad, v.rl, v.rdd, v.g, v.pa, v.re, 1",
                      "cov.Claim (ClaimNumber, PolicyNumber, LossDate, ReportedDate, CauseCode, CoverageCode, LossDescription, Notes, AdjusterName, "
                      "RecordedLimit, RecordedDeductible, GrossLoss, PaidAmount, ReserveAmount, IsSynthetic)",
                      "(n, p, ld, rd, ca, co, de, nt, ad, rl, rdd, g, pa, re)\nWHERE NOT EXISTS (SELECT 1 FROM cov.Claim z WHERE z.ClaimNumber = v.n)"))
    pays = [(c["claim_number"], i + 1, float(p["amount"]), p["payee"], p.get("payee_type", "VENDOR"), p["date"]) for c in claims for i, p in enumerate(c["payments"])]
    out.append(values(pays, "v.n, v.a, v.p, v.t, v.d", "cov.ClaimPayment (ClaimNumber, Amount, Payee, PayeeType, PaymentDate)",
                      "(n, s, a, p, t, d)\nWHERE NOT EXISTS (SELECT 1 FROM cov.ClaimPayment z WHERE z.ClaimNumber = v.n AND z.Amount = v.a AND z.PaymentDate = v.d)"))
    out.append("SELECT (SELECT COUNT(*) FROM cov.Form) AS Forms, (SELECT COUNT(*) FROM cov.FormSection) AS Sections, (SELECT COUNT(*) FROM cov.Policy) AS Policies, "
               "(SELECT COUNT(*) FROM cov.Claim) AS Claims, (SELECT COUNT(*) FROM cov.ClaimPayment) AS Payments;\nGO\n")
    return "\n\n".join(out)


if __name__ == "__main__":
    sql = build_sql()
    (HERE / "08_coverage.sql").write_text(sql, encoding="utf-8")
    print(f"08_coverage.sql written: {len(C.FORMS)} forms, {sum(len(v) for v in C.CAUSE_WORDS.values())} loss words, {len(sql):,} bytes")
