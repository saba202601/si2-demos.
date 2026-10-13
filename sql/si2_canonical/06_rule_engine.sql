/* =====================================================================================================
   SI² Canonical Master · rule engine for every role, line, product, state and company
   -----------------------------------------------------------------------------------------------------
   rules.Role / RoleAuthority   who owns rules and how much each role may approve (bind TIV, reserve, payment)
   rules.Company / Product      the companies and products rules can be scoped to
   rules.RuleTemplate           rule patterns with blanks and the questions SI² asks to fill them
   rules.RuleScope              where a rule applies: COMPANY, LOB, PRODUCT, STATE, CHANNEL, PROGRAM (none = everywhere);
                                the most specific rule with the same OverrideKey wins (a Florida rule overrides countrywide)
   rules.DecisionTable / Row    many-row rules kept as one table (notice days by state, minimum premium, commission)
   rules.BusinessRule           + TemplateCode, Phase, OwnerRole, OverrideKey, ParametersJson
   Phases run in order: DATA, ELIGIBILITY, REFERRAL, RATING, FORMS, COMPLIANCE, BILLING, ROUTING, AUTHORITY, ALERT.
   Safe to re-run: every object is created only when missing.
   ===================================================================================================== */
USE SI2Canonical;
GO

IF OBJECT_ID(N'rules.Role') IS NULL
CREATE TABLE rules.Role (
    RoleCode     varchar(40)    NOT NULL CONSTRAINT PK_Role PRIMARY KEY,
    Name         nvarchar(120)  NOT NULL,
    Department   nvarchar(120)  NULL,
    Description  nvarchar(1000) NULL,
    SortOrder    int NOT NULL CONSTRAINT DF_Role_Sort DEFAULT (100),
    CreatedBy    nvarchar(100)  NOT NULL CONSTRAINT DF_Role_By DEFAULT (SUSER_SNAME()),
    CreatedAt    datetime2(0)   NOT NULL CONSTRAINT DF_Role_At DEFAULT (SYSUTCDATETIME())
);
GO

IF OBJECT_ID(N'rules.RoleAuthority') IS NULL
CREATE TABLE rules.RoleAuthority (
    AuthorityId   int IDENTITY(1,1) NOT NULL CONSTRAINT PK_RoleAuthority PRIMARY KEY,
    RoleCode      varchar(40)    NOT NULL CONSTRAINT FK_Authority_Role REFERENCES rules.Role (RoleCode),
    AuthorityType varchar(30)    NOT NULL,      -- BIND_TIV, PREMIUM, RESERVE_CHANGE, CLAIM_PAYMENT, RATE_DEVIATION_PCT, REFUND
    LobScope      varchar(60)    NOT NULL CONSTRAINT DF_Authority_Lob DEFAULT ('*'),
    LimitAmount   decimal(19, 2) NOT NULL,
    Notes         nvarchar(500)  NULL,
    Status        varchar(10)    NOT NULL CONSTRAINT DF_Authority_Status DEFAULT ('ACTIVE')
                  CONSTRAINT CK_Authority_Status CHECK (Status IN ('PROPOSED', 'ACTIVE', 'EXPIRED')),
    EffectiveFrom date NOT NULL CONSTRAINT DF_Authority_From DEFAULT ('2020-01-01'),
    EffectiveTo   date NULL,
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_Authority_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_Authority_At DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT UQ_RoleAuthority UNIQUE (RoleCode, AuthorityType, LobScope, EffectiveFrom)
);
GO

IF OBJECT_ID(N'rules.Company') IS NULL
CREATE TABLE rules.Company (
    CompanyCode  varchar(20)    NOT NULL CONSTRAINT PK_Company PRIMARY KEY,
    Name         nvarchar(200)  NOT NULL,
    Description  nvarchar(1000) NULL,
    NaicCode     varchar(10)    NULL,
    IsSynthetic  bit NOT NULL CONSTRAINT DF_Company_Synthetic DEFAULT (0),
    CreatedBy    nvarchar(100)  NOT NULL CONSTRAINT DF_Company_By DEFAULT (SUSER_SNAME()),
    CreatedAt    datetime2(0)   NOT NULL CONSTRAINT DF_Company_At DEFAULT (SYSUTCDATETIME())
);
GO

IF OBJECT_ID(N'rules.Product') IS NULL
CREATE TABLE rules.Product (
    ProductCode  varchar(20)    NOT NULL CONSTRAINT PK_Product PRIMARY KEY,
    LobCode      varchar(20)    NOT NULL,
    Name         nvarchar(200)  NOT NULL,
    CompanyCode  varchar(20)    NULL CONSTRAINT FK_Product_Company REFERENCES rules.Company (CompanyCode),
    States       varchar(400)   NULL,           -- where it is sold, comma separated
    CreatedBy    nvarchar(100)  NOT NULL CONSTRAINT DF_Product_By DEFAULT (SUSER_SNAME()),
    CreatedAt    datetime2(0)   NOT NULL CONSTRAINT DF_Product_At DEFAULT (SYSUTCDATETIME())
);
GO

IF OBJECT_ID(N'rules.RuleTemplate') IS NULL
CREATE TABLE rules.RuleTemplate (
    TemplateCode  varchar(60)    NOT NULL CONSTRAINT PK_RuleTemplate PRIMARY KEY,
    Name          nvarchar(200)  NOT NULL,
    OwnerRole     varchar(40)    NULL CONSTRAINT FK_Template_Role REFERENCES rules.Role (RoleCode),
    Phase         varchar(20)    NOT NULL,
    RuleType      varchar(20)    NOT NULL,
    ActionType    varchar(20)    NOT NULL,
    Sentence      nvarchar(500)  NOT NULL,      -- e.g. 'Refer to {route} when {conditions}'
    Description   nvarchar(2000) NULL,
    QuestionsJson nvarchar(max)  NOT NULL CONSTRAINT CK_Template_Json CHECK (ISJSON(QuestionsJson) = 1),
    ExampleText   nvarchar(500)  NULL,
    Status        varchar(10)    NOT NULL CONSTRAINT DF_Template_Status DEFAULT ('ACTIVE')
                  CONSTRAINT CK_Template_Status CHECK (Status IN ('PROPOSED', 'ACTIVE', 'EXPIRED')),
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_Template_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_Template_At DEFAULT (SYSUTCDATETIME())
);
GO

IF OBJECT_ID(N'rules.RuleScope') IS NULL
CREATE TABLE rules.RuleScope (
    RuleScopeId  int IDENTITY(1,1) NOT NULL CONSTRAINT PK_RuleScope PRIMARY KEY,
    RuleId       int NOT NULL CONSTRAINT FK_RuleScope_Rule REFERENCES rules.BusinessRule (RuleId),
    Dimension    varchar(12)  NOT NULL CONSTRAINT CK_RuleScope_Dim CHECK (Dimension IN ('COMPANY', 'LOB', 'PRODUCT', 'STATE', 'CHANNEL', 'PROGRAM')),
    ScopeValue   nvarchar(60) NOT NULL,
    CreatedBy    nvarchar(100) NOT NULL CONSTRAINT DF_RuleScope_By DEFAULT (SUSER_SNAME()),
    CreatedAt    datetime2(0)  NOT NULL CONSTRAINT DF_RuleScope_At DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT UQ_RuleScope UNIQUE (RuleId, Dimension, ScopeValue)
);
GO

IF OBJECT_ID(N'rules.DecisionTable') IS NULL
CREATE TABLE rules.DecisionTable (
    TableCode     varchar(60)    NOT NULL CONSTRAINT PK_DecisionTable PRIMARY KEY,
    Name          nvarchar(200)  NOT NULL,
    OwnerRole     varchar(40)    NULL CONSTRAINT FK_DTable_Role REFERENCES rules.Role (RoleCode),
    Description   nvarchar(2000) NULL,
    InputsJson    nvarchar(max)  NOT NULL CONSTRAINT CK_DTable_In CHECK (ISJSON(InputsJson) = 1),    -- ["STATE","CANCEL_REASON"]
    OutputsJson   nvarchar(max)  NOT NULL CONSTRAINT CK_DTable_Out CHECK (ISJSON(OutputsJson) = 1),  -- ["NOTICE_DAYS"]
    IsIllustrative bit NOT NULL CONSTRAINT DF_DTable_Illus DEFAULT (0),   -- values to be confirmed by compliance / the company
    Status        varchar(10)    NOT NULL CONSTRAINT DF_DTable_Status DEFAULT ('ACTIVE'),
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_DTable_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_DTable_At DEFAULT (SYSUTCDATETIME())
);
GO

IF OBJECT_ID(N'rules.DecisionTableRow') IS NULL
CREATE TABLE rules.DecisionTableRow (
    RowId         int IDENTITY(1,1) NOT NULL CONSTRAINT PK_DecisionTableRow PRIMARY KEY,
    TableCode     varchar(60)    NOT NULL CONSTRAINT FK_DRow_Table REFERENCES rules.DecisionTable (TableCode),
    InputsJson    nvarchar(1000) NOT NULL CONSTRAINT CK_DRow_In CHECK (ISJSON(InputsJson) = 1),     -- {"STATE":"FL","CANCEL_REASON":"NONPAY"}; "*" = any
    OutputsJson   nvarchar(1000) NOT NULL CONSTRAINT CK_DRow_Out CHECK (ISJSON(OutputsJson) = 1),   -- {"NOTICE_DAYS":10}
    Note          nvarchar(500)  NULL,
    Status        varchar(10)    NOT NULL CONSTRAINT DF_DRow_Status DEFAULT ('ACTIVE')
                  CONSTRAINT CK_DRow_Status CHECK (Status IN ('PROPOSED', 'ACTIVE', 'EXPIRED')),
    EffectiveFrom date NOT NULL CONSTRAINT DF_DRow_From DEFAULT ('2020-01-01'),
    EffectiveTo   date NULL,
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_DRow_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_DRow_At DEFAULT (SYSUTCDATETIME())
);
GO

/* ---- new columns on the rules (nullable, so existing rules keep working) */
IF COL_LENGTH(N'rules.BusinessRule', N'TemplateCode') IS NULL
    ALTER TABLE rules.BusinessRule ADD TemplateCode varchar(60) NULL;
GO
IF COL_LENGTH(N'rules.BusinessRule', N'Phase') IS NULL
    ALTER TABLE rules.BusinessRule ADD Phase varchar(20) NULL;
GO
IF COL_LENGTH(N'rules.BusinessRule', N'OwnerRole') IS NULL
    ALTER TABLE rules.BusinessRule ADD OwnerRole varchar(40) NULL;
GO
IF COL_LENGTH(N'rules.BusinessRule', N'OverrideKey') IS NULL
    ALTER TABLE rules.BusinessRule ADD OverrideKey varchar(120) NULL;
GO
IF COL_LENGTH(N'rules.BusinessRule', N'ParametersJson') IS NULL
    ALTER TABLE rules.BusinessRule ADD ParametersJson nvarchar(max) NULL;
GO

/* ---- wider lists of allowed values */
IF OBJECT_ID(N'rules.CK_Rule_Action', N'C') IS NOT NULL ALTER TABLE rules.BusinessRule DROP CONSTRAINT CK_Rule_Action;
ALTER TABLE rules.BusinessRule ADD CONSTRAINT CK_Rule_Action CHECK (ActionType IN
    ('ACCEPT', 'DECLINE', 'REFER', 'SURCHARGE_PCT', 'CREDIT_PCT', 'SET_VALUE', 'LOOKUP', 'REJECT', 'WARN', 'ROUTE', 'FLAG', 'CALCULATE',
     'ATTACH_FORM', 'REQUIRE', 'NOTIFY', 'APPROVE_BY', 'ALERT'));
GO
IF OBJECT_ID(N'rules.CK_Rule_Type', N'C') IS NOT NULL ALTER TABLE rules.BusinessRule DROP CONSTRAINT CK_Rule_Type;
ALTER TABLE rules.BusinessRule ADD CONSTRAINT CK_Rule_Type CHECK (RuleType IN
    ('VALIDATION', 'DERIVATION', 'ELIGIBILITY', 'REFERRAL', 'PRICING', 'ROUTING', 'CALCULATION', 'ALERT', 'TRANSFORMATION',
     'FORMS', 'AUTHORITY', 'COMPLIANCE', 'BILLING'));
GO
IF OBJECT_ID(N'rules.CK_RuleSet_Purpose', N'C') IS NOT NULL ALTER TABLE rules.RuleSet DROP CONSTRAINT CK_RuleSet_Purpose;
ALTER TABLE rules.RuleSet ADD CONSTRAINT CK_RuleSet_Purpose CHECK (Purpose IN
    ('UNDERWRITING', 'RATING', 'CLAIMS', 'FRAUD', 'BUREAU', 'DATA_QUALITY', 'BILLING', 'COMPLIANCE', 'DISTRIBUTION', 'OTHER',
     'EXECUTIVE', 'PRODUCT', 'REINSURANCE', 'CAPITAL'));
GO
IF OBJECT_ID(N'gov.CK_Request_Object', N'C') IS NOT NULL ALTER TABLE gov.ChangeRequest DROP CONSTRAINT CK_Request_Object;
ALTER TABLE gov.ChangeRequest ADD CONSTRAINT CK_Request_Object CHECK (ObjectType IN
    ('SUBJECT_AREA', 'ELEMENT', 'PICKLIST', 'OPTION', 'SYNONYM', 'BUREAU_CODE', 'RULESET', 'RULE', 'EXTENSION', 'SCOPE',
     'TEMPLATE', 'DTABLE_ROW', 'AUTHORITY'));
GO

/* ---- the rule catalog as people read it */
CREATE OR ALTER VIEW rules.vw_RuleCatalog
AS
SELECT r.RuleId, r.RuleCode, r.Name, rs.RuleSetCode AS RuleSet, ISNULL(r.OwnerRole, '') AS OwnerRole, ISNULL(r.Phase, '') AS Phase,
       ISNULL(r.TemplateCode, '') AS TemplateCode, r.ActionType, r.ActionValue, r.Severity, r.Message, r.ConditionText,
       ISNULL((SELECT STRING_AGG(CONVERT(nvarchar(max), s.ScopeValue), N', ') FROM rules.RuleScope s WHERE s.RuleId = r.RuleId AND s.Dimension = 'COMPANY'), N'') AS Companies,
       ISNULL((SELECT STRING_AGG(CONVERT(nvarchar(max), s.ScopeValue), N', ') FROM rules.RuleScope s WHERE s.RuleId = r.RuleId AND s.Dimension = 'LOB'),
              CASE WHEN r.LobScope = '*' THEN N'' ELSE r.LobScope END) AS Lines,
       ISNULL((SELECT STRING_AGG(CONVERT(nvarchar(max), s.ScopeValue), N', ') FROM rules.RuleScope s WHERE s.RuleId = r.RuleId AND s.Dimension = 'PRODUCT'), N'') AS Products,
       ISNULL((SELECT STRING_AGG(CONVERT(nvarchar(max), s.ScopeValue), N', ') FROM rules.RuleScope s WHERE s.RuleId = r.RuleId AND s.Dimension = 'STATE'),
              CASE WHEN r.StateScope = '*' THEN N'' ELSE r.StateScope END) AS States,
       r.OverrideKey, r.Status, r.EffectiveFrom, r.EffectiveTo,
       (SELECT COUNT(*) FROM rules.RuleTestCase t WHERE t.RuleId = r.RuleId) AS TestCases, r.CreatedBy, r.CreatedAt
FROM rules.BusinessRule r
JOIN rules.RuleSet rs ON rs.RuleSetId = r.RuleSetId;
GO
