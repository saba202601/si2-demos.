/* =====================================================================================================
   SI² Canonical Master · schema
   -----------------------------------------------------------------------------------------------------
   canon   the company model: subject areas, data elements, pick lists, pick-list options, synonyms for
           everything, bureau code maps, where-used, and extension attributes (add any column in minutes)
   rules   the rule engine: rule sets, rules, rule conditions, rule test cases
   gov     governance: change requests with the two-person rule (maker <> checker)
   intake  discovery: scan another database, match what exists, propose what is missing

   Principles
   * Never delete. Rows are expired (Status = 'EXPIRED', EffectiveTo) and every change is kept in the
     system-versioned history tables (FOR SYSTEM_TIME ALL shows who had what, when).
   * One model, many scopes. Every master row has a Scope: GLOBAL (the standard), COMPANY:<code> (one
     carrier's additions) or PERSON:<id> (one person's working terms). Add a company or a person in seconds.
   * Synonyms for everything: data elements, pick lists, pick-list options and rules all take synonyms
     (source-system names, bureau names, abbreviations, business words). Matching uses them.
   * Business-effective dating (EffectiveFrom / EffectiveTo) is separate from the technical history.
   Run once on an empty SI2Canonical database. Re-running the installer skips this file when it exists.
   ===================================================================================================== */
USE SI2Canonical;
GO
CREATE SCHEMA canon;
GO
CREATE SCHEMA rules;
GO
CREATE SCHEMA gov;
GO
CREATE SCHEMA intake;
GO

/* ---------------------------------------------------------------------------------------- helpers */
-- Normalized text used for matching: upper case, no spaces, underscores, hyphens, dots or slashes.
CREATE FUNCTION canon.fn_Normalize (@s nvarchar(400))
RETURNS nvarchar(400)
WITH SCHEMABINDING
AS
BEGIN
    RETURN UPPER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(@s, N' ', N''), N'_', N''), N'-', N''), N'.', N''), N'/', N''));
END;
GO

/* ------------------------------------------------------------------------------------------ canon */
CREATE TABLE canon.Scope (
    ScopeId     int IDENTITY(1,1) NOT NULL CONSTRAINT PK_Scope PRIMARY KEY,
    ScopeType   varchar(10)   NOT NULL CONSTRAINT CK_Scope_Type CHECK (ScopeType IN ('GLOBAL', 'COMPANY', 'PERSON')),
    ScopeCode   nvarchar(60)  NOT NULL,
    Name        nvarchar(200) NOT NULL,
    ParentScopeId int NULL CONSTRAINT FK_Scope_Parent REFERENCES canon.Scope (ScopeId),  -- a person inside a company
    CreatedBy   nvarchar(100) NOT NULL CONSTRAINT DF_Scope_By DEFAULT (SUSER_SNAME()),
    CreatedAt   datetime2(0)  NOT NULL CONSTRAINT DF_Scope_At DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT UQ_Scope UNIQUE (ScopeType, ScopeCode)
);
GO
SET IDENTITY_INSERT canon.Scope ON;
INSERT canon.Scope (ScopeId, ScopeType, ScopeCode, Name, CreatedBy)
VALUES (1, 'GLOBAL', N'GLOBAL', N'SI² standard model (all companies)', N'SI2 seed');
SET IDENTITY_INSERT canon.Scope OFF;
GO

CREATE TABLE canon.SubjectArea (
    SubjectAreaCode varchar(40)   NOT NULL CONSTRAINT PK_SubjectArea PRIMARY KEY,
    Name            nvarchar(120) NOT NULL,
    Description     nvarchar(1000) NULL,
    SortOrder       int NOT NULL CONSTRAINT DF_SubjectArea_Sort DEFAULT (100),
    CreatedBy       nvarchar(100) NOT NULL CONSTRAINT DF_SubjectArea_By DEFAULT (SUSER_SNAME()),
    CreatedAt       datetime2(0)  NOT NULL CONSTRAINT DF_SubjectArea_At DEFAULT (SYSUTCDATETIME())
);
GO

CREATE TABLE canon.PickList (
    PickListId    int IDENTITY(1,1) NOT NULL CONSTRAINT PK_PickList PRIMARY KEY,
    PickListCode  varchar(60)    NOT NULL,
    Name          nvarchar(200)  NOT NULL,
    Description   nvarchar(2000) NULL,
    LibrarySource varchar(30)    NOT NULL CONSTRAINT DF_PickList_Lib DEFAULT ('COMPANY'),  -- ISO, NCCI, USPS, IAIABC, COMPANY ...
    LibraryRelease nvarchar(60)  NULL,                                                    -- circular / manual edition
    OwnerSME      nvarchar(100)  NULL,
    ScopeId       int NOT NULL CONSTRAINT DF_PickList_Scope DEFAULT (1) CONSTRAINT FK_PickList_Scope REFERENCES canon.Scope (ScopeId),
    Status        varchar(10)    NOT NULL CONSTRAINT DF_PickList_Status DEFAULT ('ACTIVE')
                  CONSTRAINT CK_PickList_Status CHECK (Status IN ('PROPOSED', 'ACTIVE', 'EXPIRED')),
    EffectiveFrom date NOT NULL CONSTRAINT DF_PickList_From DEFAULT ('2020-01-01'),
    EffectiveTo   date NULL,
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_PickList_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_PickList_At DEFAULT (SYSUTCDATETIME()),
    ValidFrom datetime2(0) GENERATED ALWAYS AS ROW START HIDDEN NOT NULL CONSTRAINT DF_PickList_VF DEFAULT (SYSUTCDATETIME()),
    ValidTo   datetime2(0) GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL CONSTRAINT DF_PickList_VT DEFAULT (CONVERT(datetime2(0), '9999-12-31 23:59:59')),
    PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo),
    CONSTRAINT UQ_PickList UNIQUE (PickListCode, ScopeId)
) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = canon.PickList_History));
GO

CREATE TABLE canon.PickListOption (
    OptionId      int IDENTITY(1,1) NOT NULL CONSTRAINT PK_PickListOption PRIMARY KEY,
    PickListId    int NOT NULL CONSTRAINT FK_Option_PickList REFERENCES canon.PickList (PickListId),
    OptionCode    nvarchar(60)   NOT NULL,
    OptionName    nvarchar(300)  NOT NULL,
    Description   nvarchar(2000) NULL,
    LobScope      varchar(60)    NOT NULL CONSTRAINT DF_Option_Lob DEFAULT ('*'),   -- '*' or a list such as 'PA,CA'
    StateScope    varchar(200)   NOT NULL CONSTRAINT DF_Option_State DEFAULT ('*'),
    SortOrder     int NOT NULL CONSTRAINT DF_Option_Sort DEFAULT (100),
    ScopeId       int NOT NULL CONSTRAINT DF_Option_Scope DEFAULT (1) CONSTRAINT FK_Option_Scope REFERENCES canon.Scope (ScopeId),
    Status        varchar(10)    NOT NULL CONSTRAINT DF_Option_Status DEFAULT ('ACTIVE')
                  CONSTRAINT CK_Option_Status CHECK (Status IN ('PROPOSED', 'ACTIVE', 'EXPIRED')),
    EffectiveFrom date NOT NULL CONSTRAINT DF_Option_From DEFAULT ('2020-01-01'),
    EffectiveTo   date NULL,
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_Option_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_Option_At DEFAULT (SYSUTCDATETIME()),
    ValidFrom datetime2(0) GENERATED ALWAYS AS ROW START HIDDEN NOT NULL CONSTRAINT DF_Option_VF DEFAULT (SYSUTCDATETIME()),
    ValidTo   datetime2(0) GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL CONSTRAINT DF_Option_VT DEFAULT (CONVERT(datetime2(0), '9999-12-31 23:59:59')),
    PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo),
    CONSTRAINT UQ_PickListOption UNIQUE (PickListId, OptionCode, LobScope, ScopeId, EffectiveFrom)
) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = canon.PickListOption_History));
GO
GO

CREATE TABLE canon.DataElement (
    ElementId       int IDENTITY(1,1) NOT NULL CONSTRAINT PK_DataElement PRIMARY KEY,
    ElementCode     varchar(80)    NOT NULL,                 -- POLICY_NUMBER
    Name            nvarchar(200)  NOT NULL,                 -- Policy Number
    BusinessDescription nvarchar(2000) NULL,
    SubjectAreaCode varchar(40)    NULL CONSTRAINT FK_Element_Subject REFERENCES canon.SubjectArea (SubjectAreaCode),
    DataType        varchar(20)    NOT NULL CONSTRAINT DF_Element_Type DEFAULT ('TEXT')
                    CONSTRAINT CK_Element_Type CHECK (DataType IN ('TEXT', 'CODE', 'INTEGER', 'DECIMAL', 'AMOUNT', 'DATE', 'DATETIME', 'BOOLEAN', 'PERCENT')),
    MaxLength       int NULL,
    DecimalPlaces   int NULL,
    PickListId      int NULL CONSTRAINT FK_Element_PickList REFERENCES canon.PickList (PickListId),
    IsPII           bit NOT NULL CONSTRAINT DF_Element_PII DEFAULT (0),
    IsBureauReported bit NOT NULL CONSTRAINT DF_Element_Bureau DEFAULT (0),
    RiskClass       varchar(10)    NOT NULL CONSTRAINT DF_Element_Risk DEFAULT ('MEDIUM')
                    CONSTRAINT CK_Element_Risk CHECK (RiskClass IN ('LOW', 'MEDIUM', 'HIGH')),
    OwnerSME        nvarchar(100)  NULL,
    ExampleValue    nvarchar(200)  NULL,
    ScopeId         int NOT NULL CONSTRAINT DF_Element_Scope DEFAULT (1) CONSTRAINT FK_Element_Scope REFERENCES canon.Scope (ScopeId),
    Status          varchar(10)    NOT NULL CONSTRAINT DF_Element_Status DEFAULT ('ACTIVE')
                    CONSTRAINT CK_Element_Status CHECK (Status IN ('PROPOSED', 'ACTIVE', 'EXPIRED')),
    EffectiveFrom   date NOT NULL CONSTRAINT DF_Element_From DEFAULT ('2020-01-01'),
    EffectiveTo     date NULL,
    CreatedBy       nvarchar(100)  NOT NULL CONSTRAINT DF_Element_By DEFAULT (SUSER_SNAME()),
    CreatedAt       datetime2(0)   NOT NULL CONSTRAINT DF_Element_At DEFAULT (SYSUTCDATETIME()),
    ValidFrom datetime2(0) GENERATED ALWAYS AS ROW START HIDDEN NOT NULL CONSTRAINT DF_Element_VF DEFAULT (SYSUTCDATETIME()),
    ValidTo   datetime2(0) GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL CONSTRAINT DF_Element_VT DEFAULT (CONVERT(datetime2(0), '9999-12-31 23:59:59')),
    PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo),
    CONSTRAINT UQ_DataElement UNIQUE (ElementCode, ScopeId)
) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = canon.DataElement_History));
GO
GO

-- One synonym table for every kind of object.
CREATE TABLE canon.Synonym (
    SynonymId     int IDENTITY(1,1) NOT NULL CONSTRAINT PK_Synonym PRIMARY KEY,
    ObjectType    varchar(12)    NOT NULL CONSTRAINT CK_Synonym_Object CHECK (ObjectType IN ('ELEMENT', 'PICKLIST', 'OPTION', 'RULE', 'RULESET')),
    ObjectId      int            NOT NULL,      -- ElementId / PickListId / OptionId / RuleId / RuleSetId
    SynonymText   nvarchar(300)  NOT NULL,
    SynonymType   varchar(20)    NOT NULL CONSTRAINT DF_Synonym_Type DEFAULT ('BUSINESS')
                  CONSTRAINT CK_Synonym_Type CHECK (SynonymType IN ('BUSINESS', 'ABBREVIATION', 'SOURCE', 'BUREAU', 'APP', 'VALUE', 'LEGACY')),
    SourceSystem  nvarchar(60)   NOT NULL CONSTRAINT DF_Synonym_Source DEFAULT (N'*'),   -- Guidewire, DuckCreek, ISO, NCCI, '*' = any
    MatchMethod   varchar(30)    NULL,          -- how it was found when it came from intake
    Confidence    decimal(4,2)   NULL,
    ScopeId       int NOT NULL CONSTRAINT DF_Synonym_Scope DEFAULT (1) CONSTRAINT FK_Synonym_Scope REFERENCES canon.Scope (ScopeId),
    Status        varchar(10)    NOT NULL CONSTRAINT DF_Synonym_Status DEFAULT ('ACTIVE')
                  CONSTRAINT CK_Synonym_Status CHECK (Status IN ('PROPOSED', 'ACTIVE', 'EXPIRED')),
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_Synonym_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_Synonym_At DEFAULT (SYSUTCDATETIME()),
    ValidFrom datetime2(0) GENERATED ALWAYS AS ROW START HIDDEN NOT NULL CONSTRAINT DF_Synonym_VF DEFAULT (SYSUTCDATETIME()),
    ValidTo   datetime2(0) GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL CONSTRAINT DF_Synonym_VT DEFAULT (CONVERT(datetime2(0), '9999-12-31 23:59:59')),
    PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo),
    CONSTRAINT UQ_Synonym UNIQUE (ObjectType, ObjectId, SynonymText, SourceSystem, ScopeId)
) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = canon.Synonym_History));
GO
GO

-- Pick-list option -> the code a bureau (ISO, NCCI, state) expects.
CREATE TABLE canon.BureauCodeMap (
    BureauCodeMapId int IDENTITY(1,1) NOT NULL CONSTRAINT PK_BureauCodeMap PRIMARY KEY,
    OptionId      int NOT NULL CONSTRAINT FK_BureauMap_Option REFERENCES canon.PickListOption (OptionId),
    Bureau        varchar(20)    NOT NULL,          -- ISO, NCCI, CA-WCIRB, NY-NYCIRB ...
    BureauField   nvarchar(120)  NULL,              -- e.g. 'TRANSACTION CODE'
    BureauCode    nvarchar(30)   NOT NULL,
    LobScope      varchar(60)    NOT NULL CONSTRAINT DF_BureauMap_Lob DEFAULT ('*'),
    LibraryRelease nvarchar(60)  NULL,
    Status        varchar(10)    NOT NULL CONSTRAINT DF_BureauMap_Status DEFAULT ('ACTIVE')
                  CONSTRAINT CK_BureauMap_Status CHECK (Status IN ('PROPOSED', 'ACTIVE', 'EXPIRED')),
    EffectiveFrom date NOT NULL CONSTRAINT DF_BureauMap_From DEFAULT ('2020-01-01'),
    EffectiveTo   date NULL,
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_BureauMap_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_BureauMap_At DEFAULT (SYSUTCDATETIME()),
    ValidFrom datetime2(0) GENERATED ALWAYS AS ROW START HIDDEN NOT NULL CONSTRAINT DF_BureauMap_VF DEFAULT (SYSUTCDATETIME()),
    ValidTo   datetime2(0) GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL CONSTRAINT DF_BureauMap_VT DEFAULT (CONVERT(datetime2(0), '9999-12-31 23:59:59')),
    PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo),
    CONSTRAINT UQ_BureauCodeMap UNIQUE (OptionId, Bureau, LobScope, EffectiveFrom)
) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = canon.BureauCodeMap_History));
GO

-- Where-used: which app, system, table or bureau layout uses an element (impact analysis before a change).
CREATE TABLE canon.ElementUsage (
    UsageId       int IDENTITY(1,1) NOT NULL CONSTRAINT PK_ElementUsage PRIMARY KEY,
    ElementId     int NOT NULL CONSTRAINT FK_Usage_Element REFERENCES canon.DataElement (ElementId),
    UsedIn        nvarchar(60)   NOT NULL,          -- 'ISO bureau', 'NCCI bureau', 'Rule engine', 'Guidewire' ...
    ObjectName    nvarchar(200)  NULL,              -- table / record / layout
    FieldName     nvarchar(200)  NOT NULL,
    Notes         nvarchar(1000) NULL,
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_Usage_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_Usage_At DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT UQ_ElementUsage UNIQUE (ElementId, UsedIn, ObjectName, FieldName)
);
GO

-- Add any attribute to any object without changing the tables (company- or person-specific if needed).
CREATE TABLE canon.ExtensionAttribute (
    ExtensionId   int IDENTITY(1,1) NOT NULL CONSTRAINT PK_ExtensionAttribute PRIMARY KEY,
    ObjectType    varchar(12)    NOT NULL CONSTRAINT CK_Ext_Object CHECK (ObjectType IN ('ELEMENT', 'PICKLIST', 'OPTION', 'RULE', 'RULESET')),
    ObjectId      int            NOT NULL,
    AttributeName nvarchar(100)  NOT NULL,          -- e.g. 'Guidewire entity', 'Retention period', 'Steward email'
    AttributeValue nvarchar(2000) NULL,
    ScopeId       int NOT NULL CONSTRAINT DF_Ext_Scope DEFAULT (1) CONSTRAINT FK_Ext_Scope REFERENCES canon.Scope (ScopeId),
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_Ext_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_Ext_At DEFAULT (SYSUTCDATETIME()),
    ValidFrom datetime2(0) GENERATED ALWAYS AS ROW START HIDDEN NOT NULL CONSTRAINT DF_Ext_VF DEFAULT (SYSUTCDATETIME()),
    ValidTo   datetime2(0) GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL CONSTRAINT DF_Ext_VT DEFAULT (CONVERT(datetime2(0), '9999-12-31 23:59:59')),
    PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo),
    CONSTRAINT UQ_ExtensionAttribute UNIQUE (ObjectType, ObjectId, AttributeName, ScopeId)
) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = canon.ExtensionAttribute_History));
GO

/* ------------------------------------------------------------------------------------------ rules */
CREATE TABLE rules.RuleSet (
    RuleSetId     int IDENTITY(1,1) NOT NULL CONSTRAINT PK_RuleSet PRIMARY KEY,
    RuleSetCode   varchar(60)    NOT NULL,
    Name          nvarchar(200)  NOT NULL,
    Purpose       varchar(30)    NOT NULL CONSTRAINT CK_RuleSet_Purpose CHECK (Purpose IN
                  ('UNDERWRITING', 'RATING', 'CLAIMS', 'FRAUD', 'BUREAU', 'DATA_QUALITY', 'BILLING', 'COMPLIANCE', 'DISTRIBUTION', 'OTHER')),
    Description   nvarchar(2000) NULL,
    OwnerSME      nvarchar(100)  NULL,
    ScopeId       int NOT NULL CONSTRAINT DF_RuleSet_Scope DEFAULT (1) CONSTRAINT FK_RuleSet_Scope REFERENCES canon.Scope (ScopeId),
    Status        varchar(10)    NOT NULL CONSTRAINT DF_RuleSet_Status DEFAULT ('ACTIVE')
                  CONSTRAINT CK_RuleSet_Status CHECK (Status IN ('PROPOSED', 'ACTIVE', 'EXPIRED')),
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_RuleSet_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_RuleSet_At DEFAULT (SYSUTCDATETIME()),
    ValidFrom datetime2(0) GENERATED ALWAYS AS ROW START HIDDEN NOT NULL CONSTRAINT DF_RuleSet_VF DEFAULT (SYSUTCDATETIME()),
    ValidTo   datetime2(0) GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL CONSTRAINT DF_RuleSet_VT DEFAULT (CONVERT(datetime2(0), '9999-12-31 23:59:59')),
    PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo),
    CONSTRAINT UQ_RuleSet UNIQUE (RuleSetCode, ScopeId)
) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = rules.RuleSet_History));
GO

CREATE TABLE rules.BusinessRule (
    RuleId        int IDENTITY(1,1) NOT NULL CONSTRAINT PK_BusinessRule PRIMARY KEY,
    RuleSetId     int NOT NULL CONSTRAINT FK_Rule_RuleSet REFERENCES rules.RuleSet (RuleSetId),
    RuleCode      varchar(40)    NOT NULL,
    Name          nvarchar(200)  NOT NULL,
    Description   nvarchar(2000) NULL,              -- plain English, what an SME would say
    RuleType      varchar(20)    NOT NULL CONSTRAINT CK_Rule_Type CHECK (RuleType IN
                  ('VALIDATION', 'DERIVATION', 'ELIGIBILITY', 'REFERRAL', 'PRICING', 'ROUTING', 'CALCULATION', 'ALERT', 'TRANSFORMATION')),
    LobScope      varchar(60)    NOT NULL CONSTRAINT DF_Rule_Lob DEFAULT ('*'),
    StateScope    varchar(200)   NOT NULL CONSTRAINT DF_Rule_State DEFAULT ('*'),
    TargetElementId int NULL CONSTRAINT FK_Rule_Target REFERENCES canon.DataElement (ElementId),
    ConditionLogic varchar(3)    NOT NULL CONSTRAINT DF_Rule_Logic DEFAULT ('ALL') CONSTRAINT CK_Rule_Logic CHECK (ConditionLogic IN ('ALL', 'ANY')),
    ConditionText nvarchar(2000) NULL,              -- the readable condition, e.g. driver_age < 21 and vehicle_value > 40000
    ActionType    varchar(20)    NOT NULL CONSTRAINT CK_Rule_Action CHECK (ActionType IN
                  ('ACCEPT', 'DECLINE', 'REFER', 'SURCHARGE_PCT', 'CREDIT_PCT', 'SET_VALUE', 'LOOKUP', 'REJECT', 'WARN', 'ROUTE', 'FLAG', 'CALCULATE')),
    ActionValue   nvarchar(400)  NULL,
    Severity      varchar(10)    NOT NULL CONSTRAINT DF_Rule_Severity DEFAULT ('INFO') CONSTRAINT CK_Rule_Severity CHECK (Severity IN ('INFO', 'WARNING', 'ERROR')),
    Message       nvarchar(500)  NULL,
    Priority      int NOT NULL CONSTRAINT DF_Rule_Priority DEFAULT (100),
    ExpressionJson nvarchar(max) NULL CONSTRAINT CK_Rule_Json CHECK (ExpressionJson IS NULL OR ISJSON(ExpressionJson) = 1),
    OwnerSME      nvarchar(100)  NULL,
    ScopeId       int NOT NULL CONSTRAINT DF_Rule_Scope DEFAULT (1) CONSTRAINT FK_Rule_Scope REFERENCES canon.Scope (ScopeId),
    Status        varchar(10)    NOT NULL CONSTRAINT DF_Rule_Status DEFAULT ('ACTIVE')
                  CONSTRAINT CK_Rule_Status CHECK (Status IN ('PROPOSED', 'ACTIVE', 'EXPIRED')),
    EffectiveFrom date NOT NULL CONSTRAINT DF_Rule_From DEFAULT ('2020-01-01'),
    EffectiveTo   date NULL,
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_Rule_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_Rule_At DEFAULT (SYSUTCDATETIME()),
    ValidFrom datetime2(0) GENERATED ALWAYS AS ROW START HIDDEN NOT NULL CONSTRAINT DF_Rule_VF DEFAULT (SYSUTCDATETIME()),
    ValidTo   datetime2(0) GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL CONSTRAINT DF_Rule_VT DEFAULT (CONVERT(datetime2(0), '9999-12-31 23:59:59')),
    PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo),
    CONSTRAINT UQ_BusinessRule UNIQUE (RuleCode, ScopeId, EffectiveFrom)
) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = rules.BusinessRule_History));
GO

CREATE TABLE rules.RuleCondition (
    ConditionId   int IDENTITY(1,1) NOT NULL CONSTRAINT PK_RuleCondition PRIMARY KEY,
    RuleId        int NOT NULL CONSTRAINT FK_Condition_Rule REFERENCES rules.BusinessRule (RuleId),
    Seq           int NOT NULL CONSTRAINT DF_Condition_Seq DEFAULT (1),
    ElementId     int NOT NULL CONSTRAINT FK_Condition_Element REFERENCES canon.DataElement (ElementId),
    Operator      varchar(12)    NOT NULL CONSTRAINT CK_Condition_Op CHECK (Operator IN
                  ('=', '<>', '>', '>=', '<', '<=', 'IN', 'NOT IN', 'BETWEEN', 'IS NULL', 'IS NOT NULL', 'LIKE', 'NOT LIKE')),
    Value1        nvarchar(1000) NULL,              -- for IN / NOT IN: comma-separated pick-list codes
    Value2        nvarchar(400)  NULL,              -- upper bound for BETWEEN
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_Condition_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_Condition_At DEFAULT (SYSUTCDATETIME()),
    ValidFrom datetime2(0) GENERATED ALWAYS AS ROW START HIDDEN NOT NULL CONSTRAINT DF_Condition_VF DEFAULT (SYSUTCDATETIME()),
    ValidTo   datetime2(0) GENERATED ALWAYS AS ROW END   HIDDEN NOT NULL CONSTRAINT DF_Condition_VT DEFAULT (CONVERT(datetime2(0), '9999-12-31 23:59:59')),
    PERIOD FOR SYSTEM_TIME (ValidFrom, ValidTo),
    CONSTRAINT UQ_RuleCondition UNIQUE (RuleId, Seq)
) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = rules.RuleCondition_History));
GO

CREATE TABLE rules.RuleTestCase (
    TestCaseId    int IDENTITY(1,1) NOT NULL CONSTRAINT PK_RuleTestCase PRIMARY KEY,
    RuleId        int NOT NULL CONSTRAINT FK_Test_Rule REFERENCES rules.BusinessRule (RuleId),
    Name          nvarchar(200)  NOT NULL,
    InputJson     nvarchar(max)  NOT NULL CONSTRAINT CK_Test_Json CHECK (ISJSON(InputJson) = 1),   -- {"driver_age":19,"vehicle_value":45000}
    ExpectedFires bit NOT NULL,
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_Test_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_Test_At DEFAULT (SYSUTCDATETIME())
);
GO

/* -------------------------------------------------------------------------------------------- gov */
CREATE TABLE gov.ChangeRequest (
    RequestId     int IDENTITY(1,1) NOT NULL CONSTRAINT PK_ChangeRequest PRIMARY KEY,
    ObjectType    varchar(12)    NOT NULL CONSTRAINT CK_Request_Object CHECK (ObjectType IN
                  ('SUBJECT_AREA', 'ELEMENT', 'PICKLIST', 'OPTION', 'SYNONYM', 'BUREAU_CODE', 'RULESET', 'RULE', 'EXTENSION', 'SCOPE')),
    ChangeType    varchar(10)    NOT NULL CONSTRAINT CK_Request_Change CHECK (ChangeType IN ('ADD', 'UPDATE', 'EXPIRE')),
    ObjectCode    nvarchar(300)  NOT NULL,          -- readable: STATE, STATE.TX, R04 ...
    Summary       nvarchar(1000) NULL,
    PayloadJson   nvarchar(max)  NOT NULL CONSTRAINT CK_Request_Json CHECK (ISJSON(PayloadJson) = 1),
    Source        varchar(10)    NOT NULL CONSTRAINT DF_Request_Source DEFAULT ('MANUAL') CONSTRAINT CK_Request_Source CHECK (Source IN ('MANUAL', 'INTAKE', 'SEED')),
    ScanRunId     int NULL,
    RequestedBy   nvarchar(100)  NOT NULL,
    RequestedAt   datetime2(0)   NOT NULL CONSTRAINT DF_Request_At DEFAULT (SYSUTCDATETIME()),
    Status        varchar(10)    NOT NULL CONSTRAINT DF_Request_Status DEFAULT ('PENDING')
                  CONSTRAINT CK_Request_Status CHECK (Status IN ('PENDING', 'APPROVED', 'REJECTED', 'FAILED')),
    DecidedBy     nvarchar(100)  NULL,
    DecidedAt     datetime2(0)   NULL,
    DecisionNote  nvarchar(1000) NULL,
    ResultMessage nvarchar(2000) NULL,
    CONSTRAINT CK_Request_TwoPerson CHECK (DecidedBy IS NULL OR DecidedBy <> RequestedBy)   -- maker <> checker
);
GO
CREATE INDEX IX_Request_Status ON gov.ChangeRequest (Status, ObjectType);
GO

/* ----------------------------------------------------------------------------------------- intake */
CREATE TABLE intake.SourceSystem (
    SourceSystemCode nvarchar(60)  NOT NULL CONSTRAINT PK_SourceSystem PRIMARY KEY,   -- Guidewire, DuckCreek, AGI-INS ...
    Name          nvarchar(200)  NOT NULL,
    Kind          varchar(12)    NOT NULL CONSTRAINT DF_SourceSystem_Kind DEFAULT ('DATABASE') CONSTRAINT CK_SourceSystem_Kind CHECK (Kind IN ('DATABASE', 'FILE', 'API', 'BUREAU', 'APP')),
    DatabaseName  sysname        NULL,
    Notes         nvarchar(1000) NULL,
    CreatedBy     nvarchar(100)  NOT NULL CONSTRAINT DF_SourceSystem_By DEFAULT (SUSER_SNAME()),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_SourceSystem_At DEFAULT (SYSUTCDATETIME())
);
GO

CREATE TABLE intake.ScanRun (
    ScanRunId     int IDENTITY(1,1) NOT NULL CONSTRAINT PK_ScanRun PRIMARY KEY,
    SourceSystemCode nvarchar(60) NOT NULL CONSTRAINT FK_ScanRun_Source REFERENCES intake.SourceSystem (SourceSystemCode),
    DatabaseName  sysname        NOT NULL,
    SchemaFilter  sysname        NULL,
    StartedBy     nvarchar(100)  NOT NULL,
    StartedAt     datetime2(0)   NOT NULL CONSTRAINT DF_ScanRun_At DEFAULT (SYSUTCDATETIME()),
    FinishedAt    datetime2(0)   NULL,
    ColumnsScanned int NULL,
    ElementsMatched int NULL,
    ElementsNew   int NULL,
    ValuesMatched int NULL,
    ValuesNew     int NULL,
    Message       nvarchar(2000) NULL
);
GO

CREATE TABLE intake.Candidate (
    CandidateId   int IDENTITY(1,1) NOT NULL CONSTRAINT PK_Candidate PRIMARY KEY,
    ScanRunId     int NOT NULL CONSTRAINT FK_Candidate_Run REFERENCES intake.ScanRun (ScanRunId),
    CandidateType varchar(10)    NOT NULL CONSTRAINT CK_Candidate_Type CHECK (CandidateType IN ('ELEMENT', 'OPTION')),
    SourceSchema  sysname        NOT NULL,
    SourceTable   sysname        NOT NULL,
    SourceColumn  sysname        NOT NULL,
    SourceDataType varchar(60)   NULL,
    SourceLength  int NULL,
    SourceValue   nvarchar(300)  NULL,              -- for OPTION candidates
    ValueRows     bigint NULL,
    DistinctValues int NULL,
    SampleValues  nvarchar(1000) NULL,
    MatchedObjectType varchar(12) NULL,
    MatchedObjectId int NULL,
    MatchedCode   nvarchar(200)  NULL,
    MatchMethod   varchar(30)    NULL,
    Confidence    decimal(4,2)   NULL,
    Status        varchar(10)    NOT NULL CONSTRAINT CK_Candidate_Status CHECK (Status IN ('MATCHED', 'NEW', 'PROPOSED', 'IGNORED', 'APPROVED', 'REJECTED')),
    ChangeRequestId int NULL CONSTRAINT FK_Candidate_Request REFERENCES gov.ChangeRequest (RequestId),
    CreatedAt     datetime2(0)   NOT NULL CONSTRAINT DF_Candidate_At DEFAULT (SYSUTCDATETIME())
);
GO
CREATE INDEX IX_Candidate_Run ON intake.Candidate (ScanRunId, Status, CandidateType);
GO
