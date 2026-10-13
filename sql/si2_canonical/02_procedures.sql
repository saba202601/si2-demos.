/* =====================================================================================================
   SI² Canonical Master · functions, procedures and views
   Safe to re-run (CREATE OR ALTER).

   Everyday use (examples in 05_how_to.sql)
     Propose:   canon.usp_ProposeElement / usp_ProposePickList / usp_ProposeSynonym / rules.usp_ProposeRule
                or gov.usp_RequestChange with a JSON payload for anything else
     Decide:    gov.usp_Decide @RequestId, @DecidedBy, @Approve          (the second person)
                gov.usp_DecideAll @DecidedBy, @Approve, filters ...       (many at once)
     Discover:  intake.usp_ScanDatabase @SourceDatabase = 'OtherDb'       (find what exists and what is missing)
                intake.usp_ProposeMissing @ScanRunId                      (turn what is missing into proposals)
     Test:      rules.usp_TestRule @RuleCode, @InputJson ; rules.usp_RunTests
   ===================================================================================================== */
USE SI2Canonical;
GO

/* ------------------------------------------------------------------------------------ lookups */
CREATE OR ALTER FUNCTION canon.fn_ScopeLabel (@ScopeId int)
RETURNS nvarchar(80)
AS
BEGIN
    RETURN (SELECT CASE WHEN ScopeType = 'GLOBAL' THEN N'GLOBAL' ELSE ScopeType + N':' + ScopeCode END
            FROM canon.Scope WHERE ScopeId = @ScopeId);
END;
GO

-- Scope text: 'GLOBAL' (default), 'COMPANY:ACME', 'PERSON:saba'. Returns NULL if the scope does not exist.
CREATE OR ALTER FUNCTION canon.fn_ScopeId (@Scope nvarchar(80))
RETURNS int
AS
BEGIN
    DECLARE @s nvarchar(80) = LTRIM(RTRIM(ISNULL(@Scope, N'GLOBAL')));
    IF @s = N'' OR UPPER(@s) = N'GLOBAL' RETURN 1;
    DECLARE @p int = CHARINDEX(N':', @s);
    IF @p = 0 RETURN NULL;
    RETURN (SELECT ScopeId FROM canon.Scope
            WHERE ScopeType = UPPER(LEFT(@s, @p - 1)) AND ScopeCode = SUBSTRING(@s, @p + 1, 80));
END;
GO

-- An element / pick list visible in a scope: the scope's own version first, then the global one.
CREATE OR ALTER FUNCTION canon.fn_ElementId (@Code nvarchar(80), @ScopeId int)
RETURNS int
AS
BEGIN
    RETURN (SELECT TOP (1) ElementId FROM canon.DataElement
            WHERE ElementCode = @Code AND ScopeId IN (ISNULL(@ScopeId, 1), 1) AND Status <> 'EXPIRED'
            ORDER BY CASE WHEN ScopeId = ISNULL(@ScopeId, 1) THEN 0 ELSE 1 END);
END;
GO

CREATE OR ALTER FUNCTION canon.fn_PickListId (@Code nvarchar(60), @ScopeId int)
RETURNS int
AS
BEGIN
    RETURN (SELECT TOP (1) PickListId FROM canon.PickList
            WHERE PickListCode = @Code AND ScopeId IN (ISNULL(@ScopeId, 1), 1) AND Status <> 'EXPIRED'
            ORDER BY CASE WHEN ScopeId = ISNULL(@ScopeId, 1) THEN 0 ELSE 1 END);
END;
GO

CREATE OR ALTER FUNCTION canon.fn_OptionId (@PickListId int, @OptionCode nvarchar(60), @ScopeId int)
RETURNS int
AS
BEGIN
    RETURN (SELECT TOP (1) OptionId FROM canon.PickListOption
            WHERE PickListId = @PickListId AND OptionCode = @OptionCode AND ScopeId IN (ISNULL(@ScopeId, 1), 1) AND Status <> 'EXPIRED'
            ORDER BY CASE WHEN ScopeId = ISNULL(@ScopeId, 1) THEN 0 ELSE 1 END, EffectiveFrom DESC);
END;
GO

CREATE OR ALTER FUNCTION rules.fn_RuleId (@Code nvarchar(40), @ScopeId int)
RETURNS int
AS
BEGIN
    RETURN (SELECT TOP (1) RuleId FROM rules.BusinessRule
            WHERE RuleCode = @Code AND ScopeId IN (ISNULL(@ScopeId, 1), 1) AND Status <> 'EXPIRED'
            ORDER BY CASE WHEN ScopeId = ISNULL(@ScopeId, 1) THEN 0 ELSE 1 END, EffectiveFrom DESC);
END;
GO

-- Add a company or a person in seconds: EXEC canon.usp_EnsureScope 'COMPANY:ACME', 'Acme Mutual';
CREATE OR ALTER PROCEDURE canon.usp_EnsureScope
    @Scope nvarchar(80),
    @Name nvarchar(200) = NULL,
    @ParentScope nvarchar(80) = NULL,
    @ScopeId int = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET @ScopeId = canon.fn_ScopeId(@Scope);
    IF @ScopeId IS NOT NULL RETURN;
    DECLARE @p int = CHARINDEX(N':', @Scope);
    IF @p = 0 THROW 50001, N'Scope must be GLOBAL, COMPANY:<code> or PERSON:<id>.', 1;
    DECLARE @type varchar(10) = UPPER(LEFT(@Scope, @p - 1)), @code nvarchar(60) = SUBSTRING(@Scope, @p + 1, 60);
    IF @type NOT IN ('COMPANY', 'PERSON') THROW 50001, N'Scope type must be COMPANY or PERSON.', 1;
    INSERT canon.Scope (ScopeType, ScopeCode, Name, ParentScopeId)
    VALUES (@type, @code, ISNULL(@Name, @code), canon.fn_ScopeId(@ParentScope));
    SET @ScopeId = SCOPE_IDENTITY();
END;
GO

/* --------------------------------------------------------------------------------- governance */
CREATE OR ALTER PROCEDURE gov.usp_RequestChange
    @ObjectType varchar(12),
    @ChangeType varchar(10),
    @ObjectCode nvarchar(300),
    @PayloadJson nvarchar(max),
    @RequestedBy nvarchar(100) = NULL,
    @Summary nvarchar(1000) = NULL,
    @Source varchar(10) = 'MANUAL',
    @ScanRunId int = NULL,
    @RequestId int = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    IF ISJSON(@PayloadJson) <> 1 THROW 50002, N'The payload is not valid JSON.', 1;
    INSERT gov.ChangeRequest (ObjectType, ChangeType, ObjectCode, Summary, PayloadJson, Source, ScanRunId, RequestedBy)
    VALUES (@ObjectType, @ChangeType, @ObjectCode, @Summary, @PayloadJson, @Source, @ScanRunId, ISNULL(@RequestedBy, SUSER_SNAME()));
    SET @RequestId = SCOPE_IDENTITY();
END;
GO

-- Applies an approved request to the master tables. Called by gov.usp_Decide inside its transaction.
CREATE OR ALTER PROCEDURE gov.usp_Apply
    @RequestId int,
    @Result nvarchar(2000) = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ot varchar(12), @ct varchar(10), @j nvarchar(max), @by nvarchar(100);
    SELECT @ot = ObjectType, @ct = ChangeType, @j = PayloadJson, @by = RequestedBy FROM gov.ChangeRequest WHERE RequestId = @RequestId;
    IF @ot IS NULL THROW 50003, N'Change request not found.', 1;

    DECLARE @scopeText nvarchar(80) = ISNULL(JSON_VALUE(@j, '$.scope'), N'GLOBAL'), @scopeId int;
    IF @ot <> 'SUBJECT_AREA'
        EXEC canon.usp_EnsureScope @Scope = @scopeText, @ScopeId = @scopeId OUTPUT;

    DECLARE @code nvarchar(300) = JSON_VALUE(@j, '$.code'),
            @from date = ISNULL(TRY_CONVERT(date, JSON_VALUE(@j, '$.effective_from')), CONVERT(date, SYSUTCDATETIME())),
            @to date = ISNULL(TRY_CONVERT(date, JSON_VALUE(@j, '$.effective_to')), CONVERT(date, SYSUTCDATETIME())),
            @id int, @pl int, @msg nvarchar(2000);

    /* ---- SCOPE */
    IF @ot = 'SCOPE' AND @ct = 'ADD'
    BEGIN
        EXEC canon.usp_EnsureScope @Scope = @scopeText, @Name = N'', @ScopeId = @id OUTPUT;
        UPDATE canon.Scope SET Name = ISNULL(JSON_VALUE(@j, '$.name'), Name) WHERE ScopeId = @id;
        SET @Result = N'Scope ' + @scopeText + N' ready.'; RETURN;
    END;

    /* ---- SUBJECT AREA */
    IF @ot = 'SUBJECT_AREA' AND @ct = 'ADD'
    BEGIN
        IF EXISTS (SELECT 1 FROM canon.SubjectArea WHERE SubjectAreaCode = @code) THROW 50004, N'Subject area already exists.', 1;
        INSERT canon.SubjectArea (SubjectAreaCode, Name, Description, SortOrder, CreatedBy)
        VALUES (@code, ISNULL(JSON_VALUE(@j, '$.name'), @code), JSON_VALUE(@j, '$.description'),
                ISNULL(TRY_CONVERT(int, JSON_VALUE(@j, '$.sort')), 100), @by);
        SET @Result = N'Subject area ' + @code + N' added.'; RETURN;
    END;

    /* ---- PICK LIST */
    IF @ot = 'PICKLIST' AND @ct = 'ADD'
    BEGIN
        IF EXISTS (SELECT 1 FROM canon.PickList WHERE PickListCode = @code AND ScopeId = @scopeId)
            THROW 50004, N'Pick list already exists in this scope.', 1;
        INSERT canon.PickList (PickListCode, Name, Description, LibrarySource, LibraryRelease, OwnerSME, ScopeId, EffectiveFrom, CreatedBy)
        VALUES (@code, ISNULL(JSON_VALUE(@j, '$.name'), @code), JSON_VALUE(@j, '$.description'),
                ISNULL(JSON_VALUE(@j, '$.library'), 'COMPANY'), JSON_VALUE(@j, '$.release'), JSON_VALUE(@j, '$.owner'), @scopeId, @from, @by);
        SET @Result = N'Pick list ' + @code + N' added.'; RETURN;
    END;
    IF @ot = 'PICKLIST' AND @ct = 'EXPIRE'
    BEGIN
        SET @pl = canon.fn_PickListId(@code, @scopeId);
        IF @pl IS NULL THROW 50005, N'Pick list not found.', 1;
        UPDATE canon.PickList SET Status = 'EXPIRED', EffectiveTo = @to WHERE PickListId = @pl;
        SET @Result = N'Pick list ' + @code + N' expired.'; RETURN;
    END;

    /* ---- PICK-LIST OPTION */
    IF @ot = 'OPTION'
    BEGIN
        SET @pl = canon.fn_PickListId(JSON_VALUE(@j, '$.picklist'), @scopeId);
        IF @pl IS NULL THROW 50005, N'Pick list not found for the option.', 1;
        IF @ct = 'ADD'
        BEGIN
            INSERT canon.PickListOption (PickListId, OptionCode, OptionName, Description, LobScope, StateScope, SortOrder, ScopeId, EffectiveFrom, CreatedBy)
            VALUES (@pl, @code, ISNULL(JSON_VALUE(@j, '$.name'), @code), JSON_VALUE(@j, '$.description'),
                    ISNULL(JSON_VALUE(@j, '$.lob'), '*'), ISNULL(JSON_VALUE(@j, '$.state'), '*'),
                    ISNULL(TRY_CONVERT(int, JSON_VALUE(@j, '$.sort')), 100), @scopeId, @from, @by);
            SET @id = SCOPE_IDENTITY();
            IF JSON_VALUE(@j, '$.bureau') IS NOT NULL
                INSERT canon.BureauCodeMap (OptionId, Bureau, BureauField, BureauCode, LobScope, EffectiveFrom, CreatedBy)
                VALUES (@id, JSON_VALUE(@j, '$.bureau'), JSON_VALUE(@j, '$.bureau_field'), JSON_VALUE(@j, '$.bureau_code'),
                        ISNULL(JSON_VALUE(@j, '$.lob'), '*'), @from, @by);
            SET @Result = N'Option ' + JSON_VALUE(@j, '$.picklist') + N'.' + @code + N' added.'; RETURN;
        END;
        SET @id = canon.fn_OptionId(@pl, @code, @scopeId);
        IF @id IS NULL THROW 50005, N'Option not found.', 1;
        IF @ct = 'UPDATE'
        BEGIN
            UPDATE canon.PickListOption
            SET OptionName = ISNULL(JSON_VALUE(@j, '$.name'), OptionName), Description = ISNULL(JSON_VALUE(@j, '$.description'), Description),
                SortOrder = ISNULL(TRY_CONVERT(int, JSON_VALUE(@j, '$.sort')), SortOrder)
            WHERE OptionId = @id;
            SET @Result = N'Option ' + @code + N' updated.'; RETURN;
        END;
        IF @ct = 'EXPIRE'
        BEGIN
            UPDATE canon.PickListOption SET Status = 'EXPIRED', EffectiveTo = @to WHERE OptionId = @id;
            SET @Result = N'Option ' + @code + N' expired.'; RETURN;
        END;
    END;

    /* ---- BUREAU CODE */
    IF @ot = 'BUREAU_CODE' AND @ct = 'ADD'
    BEGIN
        SET @pl = canon.fn_PickListId(JSON_VALUE(@j, '$.picklist'), @scopeId);
        SET @id = canon.fn_OptionId(@pl, JSON_VALUE(@j, '$.option'), @scopeId);
        IF @id IS NULL THROW 50005, N'Option not found for the bureau code.', 1;
        INSERT canon.BureauCodeMap (OptionId, Bureau, BureauField, BureauCode, LobScope, LibraryRelease, EffectiveFrom, CreatedBy)
        VALUES (@id, JSON_VALUE(@j, '$.bureau'), JSON_VALUE(@j, '$.bureau_field'), JSON_VALUE(@j, '$.bureau_code'),
                ISNULL(JSON_VALUE(@j, '$.lob'), '*'), JSON_VALUE(@j, '$.release'), @from, @by);
        SET @Result = N'Bureau code added.'; RETURN;
    END;
    IF @ot = 'BUREAU_CODE' AND @ct = 'EXPIRE'
    BEGIN
        SET @id = TRY_CONVERT(int, JSON_VALUE(@j, '$.id'));
        IF NOT EXISTS (SELECT 1 FROM canon.BureauCodeMap WHERE BureauCodeMapId = @id) THROW 50005, N'Bureau code not found.', 1;
        UPDATE canon.BureauCodeMap SET Status = 'EXPIRED', EffectiveTo = @to WHERE BureauCodeMapId = @id;
        SET @Result = N'Bureau code expired.'; RETURN;
    END;

    /* ---- DATA ELEMENT */
    IF @ot = 'ELEMENT'
    BEGIN
        IF @ct = 'ADD'
        BEGIN
            IF EXISTS (SELECT 1 FROM canon.DataElement WHERE ElementCode = @code AND ScopeId = @scopeId)
                THROW 50004, N'Data element already exists in this scope.', 1;
            SET @pl = canon.fn_PickListId(JSON_VALUE(@j, '$.picklist'), @scopeId);
            IF JSON_VALUE(@j, '$.picklist') IS NOT NULL AND @pl IS NULL THROW 50005, N'Pick list for the element not found.', 1;
            INSERT canon.DataElement (ElementCode, Name, BusinessDescription, SubjectAreaCode, DataType, MaxLength, DecimalPlaces, PickListId,
                                      IsPII, IsBureauReported, RiskClass, OwnerSME, ExampleValue, ScopeId, EffectiveFrom, CreatedBy)
            VALUES (@code, ISNULL(JSON_VALUE(@j, '$.name'), @code), JSON_VALUE(@j, '$.description'), JSON_VALUE(@j, '$.subject_area'),
                    ISNULL(JSON_VALUE(@j, '$.data_type'), CASE WHEN @pl IS NULL THEN 'TEXT' ELSE 'CODE' END),
                    TRY_CONVERT(int, JSON_VALUE(@j, '$.max_length')), TRY_CONVERT(int, JSON_VALUE(@j, '$.decimals')), @pl,
                    ISNULL(TRY_CONVERT(bit, JSON_VALUE(@j, '$.is_pii')), 0), ISNULL(TRY_CONVERT(bit, JSON_VALUE(@j, '$.is_bureau')), 0),
                    ISNULL(JSON_VALUE(@j, '$.risk'), 'MEDIUM'), JSON_VALUE(@j, '$.owner'), JSON_VALUE(@j, '$.example'), @scopeId, @from, @by);
            SET @id = SCOPE_IDENTITY();
            INSERT canon.Synonym (ObjectType, ObjectId, SynonymText, SynonymType, SourceSystem, MatchMethod, Confidence, ScopeId, CreatedBy)
            SELECT DISTINCT 'ELEMENT', @id, s.[text], ISNULL(s.[type], 'BUSINESS'), ISNULL(s.[source], N'*'), s.method, s.confidence, @scopeId, @by
            FROM OPENJSON(@j, '$.synonyms') WITH ([text] nvarchar(300) '$.text', [type] varchar(20) '$.type', [source] nvarchar(60) '$.source',
                                                  method varchar(30) '$.method', confidence decimal(4,2) '$.confidence') s
            WHERE s.[text] IS NOT NULL;
            SET @Result = N'Data element ' + @code + N' added.'; RETURN;
        END;
        SET @id = canon.fn_ElementId(@code, @scopeId);
        IF @id IS NULL THROW 50005, N'Data element not found.', 1;
        IF @ct = 'UPDATE'
        BEGIN
            SET @pl = canon.fn_PickListId(JSON_VALUE(@j, '$.picklist'), @scopeId);
            UPDATE canon.DataElement
            SET Name = ISNULL(JSON_VALUE(@j, '$.name'), Name),
                BusinessDescription = ISNULL(JSON_VALUE(@j, '$.description'), BusinessDescription),
                SubjectAreaCode = ISNULL(JSON_VALUE(@j, '$.subject_area'), SubjectAreaCode),
                DataType = ISNULL(JSON_VALUE(@j, '$.data_type'), DataType),
                MaxLength = ISNULL(TRY_CONVERT(int, JSON_VALUE(@j, '$.max_length')), MaxLength),
                PickListId = ISNULL(@pl, PickListId),
                IsPII = ISNULL(TRY_CONVERT(bit, JSON_VALUE(@j, '$.is_pii')), IsPII),
                IsBureauReported = ISNULL(TRY_CONVERT(bit, JSON_VALUE(@j, '$.is_bureau')), IsBureauReported),
                RiskClass = ISNULL(JSON_VALUE(@j, '$.risk'), RiskClass),
                OwnerSME = ISNULL(JSON_VALUE(@j, '$.owner'), OwnerSME),
                ExampleValue = ISNULL(JSON_VALUE(@j, '$.example'), ExampleValue)
            WHERE ElementId = @id;
            SET @Result = N'Data element ' + @code + N' updated.'; RETURN;
        END;
        IF @ct = 'EXPIRE'
        BEGIN
            UPDATE canon.DataElement SET Status = 'EXPIRED', EffectiveTo = @to WHERE ElementId = @id;
            SET @Result = N'Data element ' + @code + N' expired.'; RETURN;
        END;
    END;

    /* ---- SYNONYM (for an element, pick list, option, rule or rule set) */
    IF @ot IN ('SYNONYM', 'EXTENSION')
    BEGIN
        DECLARE @sot varchar(12) = UPPER(JSON_VALUE(@j, '$.object_type')), @soc nvarchar(300) = JSON_VALUE(@j, '$.object_code');
        SET @id = CASE @sot
                    WHEN 'ELEMENT'  THEN canon.fn_ElementId(@soc, @scopeId)
                    WHEN 'PICKLIST' THEN canon.fn_PickListId(@soc, @scopeId)
                    WHEN 'OPTION'   THEN canon.fn_OptionId(canon.fn_PickListId(JSON_VALUE(@j, '$.picklist'), @scopeId), @soc, @scopeId)
                    WHEN 'RULE'     THEN rules.fn_RuleId(@soc, @scopeId)
                    WHEN 'RULESET'  THEN (SELECT TOP (1) RuleSetId FROM rules.RuleSet WHERE RuleSetCode = @soc AND ScopeId IN (@scopeId, 1)
                                          ORDER BY CASE WHEN ScopeId = @scopeId THEN 0 ELSE 1 END)
                  END;
        IF @id IS NULL THROW 50005, N'The object for the synonym / attribute was not found.', 1;
        IF @ot = 'SYNONYM' AND @ct = 'ADD'
        BEGIN
            INSERT canon.Synonym (ObjectType, ObjectId, SynonymText, SynonymType, SourceSystem, MatchMethod, Confidence, ScopeId, CreatedBy)
            VALUES (@sot, @id, JSON_VALUE(@j, '$.text'), ISNULL(JSON_VALUE(@j, '$.type'), 'BUSINESS'), ISNULL(JSON_VALUE(@j, '$.source'), N'*'),
                    JSON_VALUE(@j, '$.method'), TRY_CONVERT(decimal(4,2), JSON_VALUE(@j, '$.confidence')), @scopeId, @by);
            SET @Result = N'Synonym ''' + JSON_VALUE(@j, '$.text') + N''' added to ' + @sot + N' ' + @soc + N'.'; RETURN;
        END;
        IF @ot = 'SYNONYM' AND @ct = 'EXPIRE'
        BEGIN
            UPDATE canon.Synonym SET Status = 'EXPIRED'
            WHERE ObjectType = @sot AND ObjectId = @id AND SynonymText = JSON_VALUE(@j, '$.text')
              AND SourceSystem = ISNULL(JSON_VALUE(@j, '$.source'), N'*') AND ScopeId = @scopeId;
            SET @Result = N'Synonym expired.'; RETURN;
        END;
        IF @ot = 'EXTENSION'
        BEGIN
            IF EXISTS (SELECT 1 FROM canon.ExtensionAttribute WHERE ObjectType = @sot AND ObjectId = @id AND AttributeName = JSON_VALUE(@j, '$.name') AND ScopeId = @scopeId)
                UPDATE canon.ExtensionAttribute SET AttributeValue = JSON_VALUE(@j, '$.value')
                WHERE ObjectType = @sot AND ObjectId = @id AND AttributeName = JSON_VALUE(@j, '$.name') AND ScopeId = @scopeId;
            ELSE
                INSERT canon.ExtensionAttribute (ObjectType, ObjectId, AttributeName, AttributeValue, ScopeId, CreatedBy)
                VALUES (@sot, @id, JSON_VALUE(@j, '$.name'), JSON_VALUE(@j, '$.value'), @scopeId, @by);
            SET @Result = N'Attribute ' + JSON_VALUE(@j, '$.name') + N' set on ' + @sot + N' ' + @soc + N'.'; RETURN;
        END;
    END;

    /* ---- RULE SET */
    IF @ot = 'RULESET' AND @ct = 'ADD'
    BEGIN
        INSERT rules.RuleSet (RuleSetCode, Name, Purpose, Description, OwnerSME, ScopeId, CreatedBy)
        VALUES (@code, ISNULL(JSON_VALUE(@j, '$.name'), @code), ISNULL(JSON_VALUE(@j, '$.purpose'), 'OTHER'),
                JSON_VALUE(@j, '$.description'), JSON_VALUE(@j, '$.owner'), @scopeId, @by);
        SET @Result = N'Rule set ' + @code + N' added.'; RETURN;
    END;

    /* ---- RULE */
    IF @ot = 'RULE'
    BEGIN
        IF @ct = 'ADD'
        BEGIN
            DECLARE @rs int = (SELECT TOP (1) RuleSetId FROM rules.RuleSet WHERE RuleSetCode = JSON_VALUE(@j, '$.ruleset') AND ScopeId IN (@scopeId, 1)
                               ORDER BY CASE WHEN ScopeId = @scopeId THEN 0 ELSE 1 END);
            IF @rs IS NULL THROW 50005, N'Rule set not found.', 1;
            DECLARE @target int = canon.fn_ElementId(JSON_VALUE(@j, '$.target_element'), @scopeId);
            INSERT rules.BusinessRule (RuleSetId, RuleCode, Name, Description, RuleType, LobScope, StateScope, TargetElementId, ConditionLogic,
                                       ConditionText, ActionType, ActionValue, Severity, Message, Priority, ExpressionJson, OwnerSME, ScopeId, EffectiveFrom, CreatedBy)
            VALUES (@rs, @code, ISNULL(JSON_VALUE(@j, '$.name'), @code), JSON_VALUE(@j, '$.description'), ISNULL(JSON_VALUE(@j, '$.rule_type'), 'VALIDATION'),
                    ISNULL(JSON_VALUE(@j, '$.lob'), '*'), ISNULL(JSON_VALUE(@j, '$.state'), '*'), @target, ISNULL(JSON_VALUE(@j, '$.logic'), 'ALL'),
                    JSON_VALUE(@j, '$.condition_text'), ISNULL(JSON_VALUE(@j, '$.action_type'), 'WARN'), JSON_VALUE(@j, '$.action_value'),
                    ISNULL(JSON_VALUE(@j, '$.severity'), 'INFO'), JSON_VALUE(@j, '$.message'), ISNULL(TRY_CONVERT(int, JSON_VALUE(@j, '$.priority')), 100),
                    JSON_QUERY(@j, '$.expression'), JSON_VALUE(@j, '$.owner'), @scopeId, @from, @by);
            SET @id = SCOPE_IDENTITY();
            IF EXISTS (SELECT 1 FROM OPENJSON(@j, '$.conditions') c
                       WHERE canon.fn_ElementId(JSON_VALUE(c.value, '$.element'), @scopeId) IS NULL)
            BEGIN
                SET @msg = N'Unknown data element in the conditions: ' +
                    (SELECT STRING_AGG(JSON_VALUE(c.value, '$.element'), N', ') FROM OPENJSON(@j, '$.conditions') c
                     WHERE canon.fn_ElementId(JSON_VALUE(c.value, '$.element'), @scopeId) IS NULL) + N'. Add the element first.';
                THROW 50005, @msg, 1;
            END;
            INSERT rules.RuleCondition (RuleId, Seq, ElementId, Operator, Value1, Value2, CreatedBy)
            SELECT @id, CONVERT(int, c.[key]) + 1, canon.fn_ElementId(JSON_VALUE(c.value, '$.element'), @scopeId),
                   UPPER(JSON_VALUE(c.value, '$.operator')), JSON_VALUE(c.value, '$.value1'), JSON_VALUE(c.value, '$.value2'), @by
            FROM OPENJSON(@j, '$.conditions') c;
            -- rule engine: template, phase, owner role, override key, where it applies, and its test cases
            IF COL_LENGTH(N'rules.BusinessRule', N'Phase') IS NOT NULL
                EXEC sp_executesql N'UPDATE rules.BusinessRule SET TemplateCode = JSON_VALUE(@j, ''$.template''), Phase = JSON_VALUE(@j, ''$.phase''),
                        OwnerRole = JSON_VALUE(@j, ''$.owner_role''), OverrideKey = JSON_VALUE(@j, ''$.override_key''),
                        ParametersJson = JSON_QUERY(@j, ''$.parameters'') WHERE RuleId = @id', N'@j nvarchar(max), @id int', @j = @j, @id = @id;
            IF OBJECT_ID(N'rules.RuleScope') IS NOT NULL
                EXEC sp_executesql N'INSERT rules.RuleScope (RuleId, Dimension, ScopeValue, CreatedBy)
                        SELECT DISTINCT @id, UPPER(d.[key]), LEFT(v.value, 60), @by
                        FROM OPENJSON(@j, ''$.applies_to'') d CROSS APPLY OPENJSON(d.value) v
                        WHERE UPPER(d.[key]) IN (''COMPANY'', ''LOB'', ''PRODUCT'', ''STATE'', ''CHANNEL'', ''PROGRAM'') AND LEN(v.value) > 0',
                     N'@j nvarchar(max), @id int, @by nvarchar(100)', @j = @j, @id = @id, @by = @by;
            INSERT rules.RuleTestCase (RuleId, Name, InputJson, ExpectedFires, CreatedBy)
            SELECT @id, LEFT(JSON_VALUE(t.value, '$.name'), 200), JSON_QUERY(t.value, '$.input'), TRY_CONVERT(bit, JSON_VALUE(t.value, '$.fires')), @by
            FROM OPENJSON(@j, '$.tests') t WHERE JSON_QUERY(t.value, '$.input') IS NOT NULL;
            SET @Result = N'Rule ' + @code + N' added.'; RETURN;
        END;
        SET @id = rules.fn_RuleId(@code, @scopeId);
        IF @id IS NULL THROW 50005, N'Rule not found.', 1;
        IF @ct = 'UPDATE'
        BEGIN
            UPDATE rules.BusinessRule
            SET Name = ISNULL(JSON_VALUE(@j, '$.name'), Name), Description = ISNULL(JSON_VALUE(@j, '$.description'), Description),
                Message = ISNULL(JSON_VALUE(@j, '$.message'), Message), Severity = ISNULL(JSON_VALUE(@j, '$.severity'), Severity),
                Priority = ISNULL(TRY_CONVERT(int, JSON_VALUE(@j, '$.priority')), Priority),
                ActionType = ISNULL(JSON_VALUE(@j, '$.action_type'), ActionType), ActionValue = ISNULL(JSON_VALUE(@j, '$.action_value'), ActionValue),
                ConditionText = ISNULL(JSON_VALUE(@j, '$.condition_text'), ConditionText), OwnerSME = ISNULL(JSON_VALUE(@j, '$.owner'), OwnerSME)
            WHERE RuleId = @id;
            SET @Result = N'Rule ' + @code + N' updated.'; RETURN;
        END;
        IF @ct = 'EXPIRE'
        BEGIN
            UPDATE rules.BusinessRule SET Status = 'EXPIRED', EffectiveTo = @to WHERE RuleId = @id;
            SET @Result = N'Rule ' + @code + N' expired.'; RETURN;
        END;
    END;

    /* ---- RULE TEMPLATE */
    IF @ot = 'TEMPLATE' AND @ct = 'ADD'
    BEGIN
        EXEC sp_executesql N'INSERT rules.RuleTemplate (TemplateCode, Name, OwnerRole, Phase, RuleType, ActionType, Sentence, Description, QuestionsJson, ExampleText, CreatedBy)
                VALUES (@code, ISNULL(JSON_VALUE(@j, ''$.name''), @code), JSON_VALUE(@j, ''$.owner_role''), ISNULL(JSON_VALUE(@j, ''$.phase''), ''REFERRAL''),
                        ISNULL(JSON_VALUE(@j, ''$.rule_type''), ''REFERRAL''), ISNULL(JSON_VALUE(@j, ''$.action_type''), ''REFER''),
                        ISNULL(JSON_VALUE(@j, ''$.sentence''), @code), JSON_VALUE(@j, ''$.description''), ISNULL(JSON_QUERY(@j, ''$.questions''), N''[]''),
                        JSON_VALUE(@j, ''$.example''), @by)',
            N'@j nvarchar(max), @code nvarchar(300), @by nvarchar(100)', @j = @j, @code = @code, @by = @by;
        SET @Result = N'Template ' + @code + N' added.'; RETURN;
    END;

    /* ---- DECISION TABLE ROW */
    IF @ot = 'DTABLE_ROW' AND @ct = 'ADD'
    BEGIN
        EXEC sp_executesql N'INSERT rules.DecisionTableRow (TableCode, InputsJson, OutputsJson, Note, EffectiveFrom, CreatedBy)
                VALUES (JSON_VALUE(@j, ''$.table''), JSON_QUERY(@j, ''$.inputs''), JSON_QUERY(@j, ''$.outputs''), JSON_VALUE(@j, ''$.note''), @from, @by)',
            N'@j nvarchar(max), @from date, @by nvarchar(100)', @j = @j, @from = @from, @by = @by;
        SET @Result = N'Row added to ' + ISNULL(JSON_VALUE(@j, '$.table'), N'?') + N'.'; RETURN;
    END;
    IF @ot = 'DTABLE_ROW' AND @ct = 'EXPIRE'
    BEGIN
        EXEC sp_executesql N'UPDATE rules.DecisionTableRow SET Status = ''EXPIRED'', EffectiveTo = @to WHERE RowId = TRY_CONVERT(int, JSON_VALUE(@j, ''$.row_id''))',
            N'@j nvarchar(max), @to date', @j = @j, @to = @to;
        SET @Result = N'Row expired.'; RETURN;
    END;

    /* ---- ROLE AUTHORITY (a new limit ends the open one the day before) */
    IF @ot = 'AUTHORITY' AND @ct = 'ADD'
    BEGIN
        EXEC sp_executesql N'UPDATE rules.RoleAuthority SET EffectiveTo = DATEADD(day, -1, @from), Status = ''EXPIRED''
                WHERE RoleCode = JSON_VALUE(@j, ''$.role'') AND AuthorityType = JSON_VALUE(@j, ''$.authority'')
                  AND LobScope = ISNULL(JSON_VALUE(@j, ''$.lob''), ''*'') AND EffectiveTo IS NULL AND Status = ''ACTIVE'';
                INSERT rules.RoleAuthority (RoleCode, AuthorityType, LobScope, LimitAmount, Notes, EffectiveFrom, CreatedBy)
                VALUES (JSON_VALUE(@j, ''$.role''), JSON_VALUE(@j, ''$.authority''), ISNULL(JSON_VALUE(@j, ''$.lob''), ''*''),
                        TRY_CONVERT(decimal(19,2), JSON_VALUE(@j, ''$.limit'')), JSON_VALUE(@j, ''$.note''), @from, @by)',
            N'@j nvarchar(max), @from date, @by nvarchar(100)', @j = @j, @from = @from, @by = @by;
        SET @Result = N'Authority for ' + ISNULL(JSON_VALUE(@j, '$.role'), N'?') + N' set.'; RETURN;
    END;

    SET @msg = N'Unsupported change: ' + @ot + N' ' + @ct + N'.';
    THROW 50006, @msg, 1;
END;
GO

-- The second person approves or rejects. Maker <> checker is enforced.
CREATE OR ALTER PROCEDURE gov.usp_Decide
    @RequestId int,
    @DecidedBy nvarchar(100),
    @Approve bit = 1,
    @Note nvarchar(1000) = NULL,
    @Quiet bit = 0,
    @OutStatus varchar(10) = NULL OUTPUT,
    @OutResult nvarchar(2000) = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @status varchar(10), @maker nvarchar(100), @result nvarchar(2000);
    SELECT @status = Status, @maker = RequestedBy FROM gov.ChangeRequest WHERE RequestId = @RequestId;
    IF @status IS NULL THROW 50003, N'Change request not found.', 1;
    IF @status <> 'PENDING' THROW 50007, N'This change request has already been decided.', 1;
    IF @maker = @DecidedBy THROW 50008, N'Two-person rule: the person who requested a change cannot approve it.', 1;

    IF @Approve = 0
    BEGIN
        UPDATE gov.ChangeRequest SET Status = 'REJECTED', DecidedBy = @DecidedBy, DecidedAt = SYSUTCDATETIME(), DecisionNote = @Note,
                                     ResultMessage = N'Rejected.' WHERE RequestId = @RequestId;
        UPDATE intake.Candidate SET Status = 'REJECTED' WHERE ChangeRequestId = @RequestId;
        SELECT @OutStatus = 'REJECTED', @OutResult = N'Rejected.';
        IF @Quiet = 0 SELECT @RequestId AS RequestId, @OutStatus AS Status, @OutResult AS Result;
        RETURN;
    END;

    BEGIN TRY
        BEGIN TRANSACTION;
        EXEC gov.usp_Apply @RequestId = @RequestId, @Result = @result OUTPUT;
        UPDATE gov.ChangeRequest SET Status = 'APPROVED', DecidedBy = @DecidedBy, DecidedAt = SYSUTCDATETIME(), DecisionNote = @Note,
                                     ResultMessage = @result WHERE RequestId = @RequestId;
        UPDATE intake.Candidate SET Status = 'APPROVED' WHERE ChangeRequestId = @RequestId;
        COMMIT;
        SELECT @OutStatus = 'APPROVED', @OutResult = @result;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK;
        SET @result = ERROR_MESSAGE();
        UPDATE gov.ChangeRequest SET Status = 'FAILED', DecidedBy = @DecidedBy, DecidedAt = SYSUTCDATETIME(), DecisionNote = @Note,
                                     ResultMessage = @result WHERE RequestId = @RequestId;
        SELECT @OutStatus = 'FAILED', @OutResult = @result;
    END CATCH;
    IF @Quiet = 0 SELECT @RequestId AS RequestId, @OutStatus AS Status, @OutResult AS Result;
END;
GO

-- Decide many pending requests at once (in request order), e.g. everything from one scan.
CREATE OR ALTER PROCEDURE gov.usp_DecideAll
    @DecidedBy nvarchar(100),
    @Approve bit = 1,
    @Note nvarchar(1000) = NULL,
    @ScanRunId int = NULL,
    @ObjectType varchar(12) = NULL,
    @ObjectCodeLike nvarchar(300) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @ids TABLE (RequestId int PRIMARY KEY);
    INSERT @ids SELECT RequestId FROM gov.ChangeRequest
    WHERE Status = 'PENDING' AND RequestedBy <> @DecidedBy
      AND (@ScanRunId IS NULL OR ScanRunId = @ScanRunId)
      AND (@ObjectType IS NULL OR ObjectType = @ObjectType)
      AND (@ObjectCodeLike IS NULL OR ObjectCode LIKE @ObjectCodeLike);
    DECLARE @out TABLE (RequestId int, Status varchar(10), Result nvarchar(2000));
    DECLARE @id int = (SELECT MIN(RequestId) FROM @ids), @st varchar(10), @rs nvarchar(2000);
    WHILE @id IS NOT NULL
    BEGIN
        EXEC gov.usp_Decide @RequestId = @id, @DecidedBy = @DecidedBy, @Approve = @Approve, @Note = @Note, @Quiet = 1,
                            @OutStatus = @st OUTPUT, @OutResult = @rs OUTPUT;
        INSERT @out VALUES (@id, @st, @rs);
        SET @id = (SELECT MIN(RequestId) FROM @ids WHERE RequestId > @id);
    END;
    SELECT Status, COUNT(*) AS Requests FROM @out GROUP BY Status;
    SELECT o.RequestId, r.ObjectType, r.ChangeType, r.ObjectCode, o.Status, o.Result
    FROM @out o JOIN gov.ChangeRequest r ON r.RequestId = o.RequestId
    WHERE o.Status = 'FAILED' ORDER BY o.RequestId;
END;
GO

/* ------------------------------------------------------------ quick proposals (minutes, not days) */
-- EXEC canon.usp_ProposeElement 'TELEMATICS_IND', 'Telematics Indicator', 'Vehicle is rated with a usage-based program.',
--      @DataType = 'CODE', @PickList = 'YES_NO', @SubjectArea = 'VEHICLE', @Synonyms = 'TelematicsInd,UBI_FLAG', @RequestedBy = 'Saba';
CREATE OR ALTER PROCEDURE canon.usp_ProposeElement
    @Code varchar(80), @Name nvarchar(200), @Description nvarchar(2000) = NULL,
    @DataType varchar(20) = NULL, @MaxLength int = NULL, @PickList varchar(60) = NULL, @SubjectArea varchar(40) = NULL,
    @IsPII bit = 0, @IsBureauReported bit = 0, @RiskClass varchar(10) = 'MEDIUM', @Owner nvarchar(100) = NULL,
    @Synonyms nvarchar(2000) = NULL,            -- comma-separated
    @SynonymSource nvarchar(60) = N'*',
    @Scope nvarchar(80) = N'GLOBAL', @RequestedBy nvarchar(100) = NULL, @RequestId int = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @j nvarchar(max) = (
        SELECT @Code AS code, @Name AS name, @Description AS description, @DataType AS data_type, @MaxLength AS max_length,
               @PickList AS picklist, @SubjectArea AS subject_area, @IsPII AS is_pii, @IsBureauReported AS is_bureau,
               @RiskClass AS risk, @Owner AS owner, @Scope AS scope,
               JSON_QUERY(ISNULL((SELECT LTRIM(RTRIM(s.value)) AS [text], CASE WHEN @SynonymSource = N'*' THEN 'BUSINESS' ELSE 'SOURCE' END AS [type],
                                         @SynonymSource AS [source]
                                  FROM STRING_SPLIT(@Synonyms, ',') s WHERE LTRIM(RTRIM(s.value)) <> N'' FOR JSON PATH), N'[]')) AS synonyms
        FOR JSON PATH, WITHOUT_ARRAY_WRAPPER);
    DECLARE @summary nvarchar(1000) = N'New data element ' + @Code + N' (' + @Name + N')';
    EXEC gov.usp_RequestChange 'ELEMENT', 'ADD', @Code, @j, @RequestedBy, @summary, 'MANUAL', NULL, @RequestId OUTPUT;
    SELECT @RequestId AS RequestId, N'Waiting for a second person: EXEC gov.usp_Decide ' + CONVERT(nvarchar(20), @RequestId) + N', ''<name>'', 1;' AS NextStep;
END;
GO

-- EXEC canon.usp_ProposePickList 'ROOF_TYPE', 'Roof Type', 'Roof covering material',
--      @Options = 'ASPH=Asphalt shingle;METAL=Metal;TILE=Clay or concrete tile;WOOD=Wood shake', @RequestedBy = 'Saba';
CREATE OR ALTER PROCEDURE canon.usp_ProposePickList
    @Code varchar(60), @Name nvarchar(200), @Description nvarchar(2000) = NULL,
    @Options nvarchar(max) = NULL,              -- 'CODE=Name;CODE=Name' (add options to an existing list by passing its code)
    @Library varchar(30) = 'COMPANY', @Scope nvarchar(80) = N'GLOBAL', @RequestedBy nvarchar(100) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @j nvarchar(max), @rid int, @summary nvarchar(1000);
    DECLARE @made TABLE (RequestId int, ObjectCode nvarchar(300));
    IF canon.fn_PickListId(@Code, canon.fn_ScopeId(@Scope)) IS NULL
    BEGIN
        SET @j = (SELECT @Code AS code, @Name AS name, @Description AS description, @Library AS library, @Scope AS scope FOR JSON PATH, WITHOUT_ARRAY_WRAPPER);
        SET @summary = N'New pick list ' + @Code;
        EXEC gov.usp_RequestChange 'PICKLIST', 'ADD', @Code, @j, @RequestedBy, @summary, 'MANUAL', NULL, @rid OUTPUT;
        INSERT @made VALUES (@rid, @Code);
    END;
    DECLARE @opt TABLE (n int IDENTITY(1,1), code nvarchar(60), name nvarchar(300));
    INSERT @opt (code, name)
    SELECT LTRIM(RTRIM(CASE WHEN CHARINDEX(N'=', s.value) > 0 THEN LEFT(s.value, CHARINDEX(N'=', s.value) - 1) ELSE s.value END)),
           LTRIM(RTRIM(CASE WHEN CHARINDEX(N'=', s.value) > 0 THEN SUBSTRING(s.value, CHARINDEX(N'=', s.value) + 1, 300) ELSE s.value END))
    FROM STRING_SPLIT(ISNULL(@Options, N''), ';') s WHERE LTRIM(RTRIM(s.value)) <> N'';
    DECLARE @n int = 1, @max int = (SELECT COUNT(*) FROM @opt), @oc nvarchar(60), @on nvarchar(300);
    WHILE @n <= @max
    BEGIN
        SELECT @oc = code, @on = name FROM @opt WHERE n = @n;
        SET @j = (SELECT @Code AS picklist, @oc AS code, @on AS name, @n * 10 AS sort, @Scope AS scope FOR JSON PATH, WITHOUT_ARRAY_WRAPPER);
        SET @summary = N'New option ' + @Code + N'.' + @oc + N' (' + @on + N')';
        DECLARE @ocode nvarchar(300) = @Code + N'.' + @oc;
        EXEC gov.usp_RequestChange 'OPTION', 'ADD', @ocode, @j, @RequestedBy, @summary, 'MANUAL', NULL, @rid OUTPUT;
        INSERT @made VALUES (@rid, @ocode);
        SET @n += 1;
    END;
    SELECT RequestId, ObjectCode, N'Waiting for a second person (gov.usp_DecideAll)' AS NextStep FROM @made;
END;
GO

-- EXEC canon.usp_ProposeSynonym 'ELEMENT', 'POLICY_NUMBER', 'POL_NBR', @Source = 'DuckCreek', @RequestedBy = 'Saba';
-- EXEC canon.usp_ProposeSynonym 'OPTION', 'O', 'Open', @PickList = 'CLAIM_STATUS', ...   (option code first, then the synonym)
CREATE OR ALTER PROCEDURE canon.usp_ProposeSynonym
    @ObjectType varchar(12), @ObjectCode nvarchar(300), @Synonym nvarchar(300),
    @Source nvarchar(60) = N'*', @PickList varchar(60) = NULL, @SynonymType varchar(20) = NULL,
    @Scope nvarchar(80) = N'GLOBAL', @RequestedBy nvarchar(100) = NULL, @RequestId int = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @j nvarchar(max) = (
        SELECT UPPER(@ObjectType) AS object_type, @ObjectCode AS object_code, @PickList AS picklist, @Synonym AS [text],
               ISNULL(@SynonymType, CASE WHEN @Source = N'*' THEN 'BUSINESS' ELSE 'SOURCE' END) AS [type], @Source AS [source], @Scope AS scope
        FOR JSON PATH, WITHOUT_ARRAY_WRAPPER);
    DECLARE @summary nvarchar(1000) = N'Synonym ''' + @Synonym + N''' for ' + @ObjectType + N' ' + ISNULL(@PickList + N'.', N'') + @ObjectCode;
    EXEC gov.usp_RequestChange 'SYNONYM', 'ADD', @ObjectCode, @j, @RequestedBy, @summary, 'MANUAL', NULL, @RequestId OUTPUT;
    SELECT @RequestId AS RequestId;
END;
GO

-- EXEC rules.usp_ProposeRule 'UW_PA', 'R12', 'Young driver on a sports car', 'REFERRAL', 'REFER', NULL,
--      @ConditionsJson = '[["DRIVER_AGE","<","25"],["VEHICLE_SYMBOL",">=","20"]]', @RequestedBy = 'Saba';
CREATE OR ALTER PROCEDURE rules.usp_ProposeRule
    @RuleSet varchar(60), @Code varchar(40), @Name nvarchar(200), @RuleType varchar(20), @ActionType varchar(20), @ActionValue nvarchar(400) = NULL,
    @ConditionsJson nvarchar(max) = N'[]',      -- [["ELEMENT","operator","value1","value2"], ...]
    @Logic varchar(3) = 'ALL', @Description nvarchar(2000) = NULL, @Message nvarchar(500) = NULL, @Severity varchar(10) = 'INFO',
    @Lob varchar(60) = '*', @State varchar(200) = '*', @Priority int = 100, @EffectiveFrom date = NULL,
    @Scope nvarchar(80) = N'GLOBAL', @RequestedBy nvarchar(100) = NULL, @RequestId int = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    IF ISJSON(@ConditionsJson) <> 1 THROW 50002, N'@ConditionsJson must be a JSON array such as [["DRIVER_AGE","<","21"]].', 1;
    DECLARE @conds nvarchar(max) = (
        SELECT JSON_VALUE(c.value, '$[0]') AS element, JSON_VALUE(c.value, '$[1]') AS operator,
               JSON_VALUE(c.value, '$[2]') AS value1, JSON_VALUE(c.value, '$[3]') AS value2
        FROM OPENJSON(@ConditionsJson) c ORDER BY CONVERT(int, c.[key]) FOR JSON PATH);
    DECLARE @sep nvarchar(10) = CASE WHEN @Logic = 'ANY' THEN N' or ' ELSE N' and ' END;
    DECLARE @text nvarchar(2000) = (
        SELECT STRING_AGG(JSON_VALUE(c.value, '$[0]') + N' ' + JSON_VALUE(c.value, '$[1]') + ISNULL(N' ' + JSON_VALUE(c.value, '$[2]'), N'')
                          + ISNULL(N' AND ' + JSON_VALUE(c.value, '$[3]'), N''), @sep)
        FROM OPENJSON(@ConditionsJson) c);
    DECLARE @j nvarchar(max) = (
        SELECT @RuleSet AS ruleset, @Code AS code, @Name AS name, @Description AS description, @RuleType AS rule_type,
               @ActionType AS action_type, @ActionValue AS action_value, @Logic AS logic, @text AS condition_text, @Message AS message,
               @Severity AS severity, @Lob AS lob, @State AS state, @Priority AS priority, @EffectiveFrom AS effective_from, @Scope AS scope,
               JSON_QUERY(ISNULL(@conds, N'[]')) AS conditions
        FOR JSON PATH, WITHOUT_ARRAY_WRAPPER);
    DECLARE @summary nvarchar(1000) = N'New rule ' + @Code + N': ' + @Name;
    EXEC gov.usp_RequestChange 'RULE', 'ADD', @Code, @j, @RequestedBy, @summary, 'MANUAL', NULL, @RequestId OUTPUT;
    SELECT @RequestId AS RequestId, @text AS ConditionText;
END;
GO

/* ------------------------------------------------------------------------------------ rule engine */
-- Evaluate one rule against input values. Keys are element codes (any case): {"DRIVER_AGE":19,"STATE":"TX"}
CREATE OR ALTER PROCEDURE rules.usp_TestRule
    @RuleCode varchar(40),
    @InputJson nvarchar(max),
    @Scope nvarchar(80) = N'GLOBAL',
    @Fires bit = NULL OUTPUT,
    @Quiet bit = 0
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @rule int = rules.fn_RuleId(@RuleCode, canon.fn_ScopeId(@Scope));
    IF @rule IS NULL THROW 50005, N'Rule not found.', 1;
    IF ISJSON(@InputJson) <> 1 THROW 50002, N'@InputJson is not valid JSON.', 1;

    DECLARE @eval TABLE (Seq int, ElementCode varchar(80), Operator varchar(12), Value1 nvarchar(1000), Value2 nvarchar(400), InputValue nvarchar(4000), IsTrue bit);
    INSERT @eval (Seq, ElementCode, Operator, Value1, Value2, InputValue)
    SELECT c.Seq, e.ElementCode, c.Operator, c.Value1, c.Value2, i.value
    FROM rules.RuleCondition c
    JOIN canon.DataElement e ON e.ElementId = c.ElementId
    OUTER APPLY (SELECT TOP (1) j.value FROM OPENJSON(@InputJson) j WHERE UPPER(j.[key]) COLLATE DATABASE_DEFAULT = UPPER(e.ElementCode)) i
    WHERE c.RuleId = @rule;

    UPDATE v SET IsTrue =
        CASE
          WHEN Operator = 'IS NULL' THEN CASE WHEN InputValue IS NULL OR InputValue = N'' THEN 1 ELSE 0 END
          WHEN Operator = 'IS NOT NULL' THEN CASE WHEN InputValue IS NULL OR InputValue = N'' THEN 0 ELSE 1 END
          WHEN InputValue IS NULL THEN 0
          WHEN Operator = 'IN' THEN CASE WHEN EXISTS (SELECT 1 FROM STRING_SPLIT(Value1, ',') s WHERE LTRIM(RTRIM(s.value)) = InputValue) THEN 1 ELSE 0 END
          WHEN Operator = 'NOT IN' THEN CASE WHEN EXISTS (SELECT 1 FROM STRING_SPLIT(Value1, ',') s WHERE LTRIM(RTRIM(s.value)) = InputValue) THEN 0 ELSE 1 END
          WHEN Operator = 'LIKE' THEN CASE WHEN InputValue LIKE Value1 THEN 1 ELSE 0 END
          WHEN Operator = 'NOT LIKE' THEN CASE WHEN InputValue LIKE Value1 THEN 0 ELSE 1 END
          WHEN TRY_CONVERT(decimal(38, 6), InputValue) IS NOT NULL AND TRY_CONVERT(decimal(38, 6), Value1) IS NOT NULL THEN
            CASE Operator
              WHEN '='  THEN CASE WHEN TRY_CONVERT(decimal(38, 6), InputValue) =  TRY_CONVERT(decimal(38, 6), Value1) THEN 1 ELSE 0 END
              WHEN '<>' THEN CASE WHEN TRY_CONVERT(decimal(38, 6), InputValue) <> TRY_CONVERT(decimal(38, 6), Value1) THEN 1 ELSE 0 END
              WHEN '>'  THEN CASE WHEN TRY_CONVERT(decimal(38, 6), InputValue) >  TRY_CONVERT(decimal(38, 6), Value1) THEN 1 ELSE 0 END
              WHEN '>=' THEN CASE WHEN TRY_CONVERT(decimal(38, 6), InputValue) >= TRY_CONVERT(decimal(38, 6), Value1) THEN 1 ELSE 0 END
              WHEN '<'  THEN CASE WHEN TRY_CONVERT(decimal(38, 6), InputValue) <  TRY_CONVERT(decimal(38, 6), Value1) THEN 1 ELSE 0 END
              WHEN '<=' THEN CASE WHEN TRY_CONVERT(decimal(38, 6), InputValue) <= TRY_CONVERT(decimal(38, 6), Value1) THEN 1 ELSE 0 END
              WHEN 'BETWEEN' THEN CASE WHEN TRY_CONVERT(decimal(38, 6), InputValue) BETWEEN TRY_CONVERT(decimal(38, 6), Value1)
                                                                                    AND TRY_CONVERT(decimal(38, 6), Value2) THEN 1 ELSE 0 END
            END
          ELSE
            CASE Operator
              WHEN '='  THEN CASE WHEN InputValue =  Value1 THEN 1 ELSE 0 END
              WHEN '<>' THEN CASE WHEN InputValue <> Value1 THEN 1 ELSE 0 END
              WHEN '>'  THEN CASE WHEN InputValue >  Value1 THEN 1 ELSE 0 END
              WHEN '>=' THEN CASE WHEN InputValue >= Value1 THEN 1 ELSE 0 END
              WHEN '<'  THEN CASE WHEN InputValue <  Value1 THEN 1 ELSE 0 END
              WHEN '<=' THEN CASE WHEN InputValue <= Value1 THEN 1 ELSE 0 END
              WHEN 'BETWEEN' THEN CASE WHEN InputValue BETWEEN Value1 AND Value2 THEN 1 ELSE 0 END
            END
        END
    FROM @eval v;

    DECLARE @logic varchar(3) = (SELECT ConditionLogic FROM rules.BusinessRule WHERE RuleId = @rule);
    SET @Fires = CASE
        WHEN NOT EXISTS (SELECT 1 FROM @eval) THEN 0
        WHEN @logic = 'ANY' THEN CASE WHEN EXISTS (SELECT 1 FROM @eval WHERE IsTrue = 1) THEN 1 ELSE 0 END
        ELSE CASE WHEN EXISTS (SELECT 1 FROM @eval WHERE ISNULL(IsTrue, 0) = 0) THEN 0 ELSE 1 END END;

    IF @Quiet = 0
    BEGIN
        SELECT r.RuleCode, r.Name, @Fires AS Fires, CASE WHEN @Fires = 1 THEN r.ActionType ELSE NULL END AS Action,
               CASE WHEN @Fires = 1 THEN r.ActionValue ELSE NULL END AS ActionValue, CASE WHEN @Fires = 1 THEN r.Message ELSE NULL END AS Message
        FROM rules.BusinessRule r WHERE r.RuleId = @rule;
        SELECT Seq, ElementCode, Operator, Value1, Value2, InputValue, IsTrue FROM @eval ORDER BY Seq;
    END;
END;
GO

-- Run every saved test case (or one rule's) and show pass / fail.
CREATE OR ALTER PROCEDURE rules.usp_RunTests
    @RuleCode varchar(40) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @res TABLE (TestCaseId int, RuleCode varchar(40), Name nvarchar(200), Expected bit, Actual bit);
    DECLARE @t int = (SELECT MIN(t.TestCaseId) FROM rules.RuleTestCase t JOIN rules.BusinessRule r ON r.RuleId = t.RuleId
                      WHERE @RuleCode IS NULL OR r.RuleCode = @RuleCode);
    DECLARE @code varchar(40), @in nvarchar(max), @exp bit, @name nvarchar(200), @fires bit, @scope nvarchar(80);
    WHILE @t IS NOT NULL
    BEGIN
        SELECT @code = r.RuleCode, @in = t.InputJson, @exp = t.ExpectedFires, @name = t.Name, @scope = canon.fn_ScopeLabel(r.ScopeId)
        FROM rules.RuleTestCase t JOIN rules.BusinessRule r ON r.RuleId = t.RuleId WHERE t.TestCaseId = @t;
        EXEC rules.usp_TestRule @RuleCode = @code, @InputJson = @in, @Scope = @scope, @Fires = @fires OUTPUT, @Quiet = 1;
        INSERT @res VALUES (@t, @code, @name, @exp, @fires);
        SET @t = (SELECT MIN(t.TestCaseId) FROM rules.RuleTestCase t JOIN rules.BusinessRule r ON r.RuleId = t.RuleId
                  WHERE t.TestCaseId > @t AND (@RuleCode IS NULL OR r.RuleCode = @RuleCode));
    END;
    SELECT SUM(CASE WHEN Expected = Actual THEN 1 ELSE 0 END) AS Passed, SUM(CASE WHEN Expected = Actual THEN 0 ELSE 1 END) AS Failed FROM @res;
    SELECT *, CASE WHEN Expected = Actual THEN 'PASS' ELSE 'FAIL' END AS Outcome FROM @res ORDER BY RuleCode, TestCaseId;
END;
GO

/* ----------------------------------------------------------------------------------------- intake */
-- Scan another database on this server: every column is matched to the master model (approved source
-- alias, element code, synonym, element name, common abbreviations, table + column); for code-like text
-- columns the distinct values are matched to pick-list options. Nothing is changed in the master tables.
CREATE OR ALTER PROCEDURE intake.usp_ScanDatabase
    @SourceDatabase sysname,
    @SourceSystem nvarchar(60) = NULL,          -- name used for source-specific synonyms; default = database name
    @StartedBy nvarchar(100) = NULL,
    @SchemaFilter sysname = NULL,
    @TableLike nvarchar(128) = NULL,            -- e.g. 'POL%'
    @ScanValues bit = 1,
    @MaxDistinct int = 50,                      -- a text column with at most this many distinct values is treated as a code list
    @Scope nvarchar(80) = N'GLOBAL',
    @ScanRunId int = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    IF DB_ID(@SourceDatabase) IS NULL THROW 50010, N'Database not found on this server.', 1;
    SET @SourceSystem = ISNULL(@SourceSystem, @SourceDatabase);
    SET @StartedBy = ISNULL(@StartedBy, SUSER_SNAME());
    DECLARE @scopeId int = ISNULL(canon.fn_ScopeId(@Scope), 1);

    IF NOT EXISTS (SELECT 1 FROM intake.SourceSystem WHERE SourceSystemCode = @SourceSystem)
        INSERT intake.SourceSystem (SourceSystemCode, Name, Kind, DatabaseName) VALUES (@SourceSystem, @SourceSystem, 'DATABASE', @SourceDatabase);
    INSERT intake.ScanRun (SourceSystemCode, DatabaseName, SchemaFilter, StartedBy) VALUES (@SourceSystem, @SourceDatabase, @SchemaFilter, @StartedBy);
    SET @ScanRunId = SCOPE_IDENTITY();

    /* 1. columns of the source database */
    CREATE TABLE #cols (
        ColId int IDENTITY(1,1) PRIMARY KEY,
        SchemaName sysname COLLATE DATABASE_DEFAULT, TableName sysname COLLATE DATABASE_DEFAULT, ColumnName sysname COLLATE DATABASE_DEFAULT,
        DataType varchar(60) COLLATE DATABASE_DEFAULT, MaxLen int,
        NormCol nvarchar(400) COLLATE DATABASE_DEFAULT NULL, NormAlt nvarchar(400) COLLATE DATABASE_DEFAULT NULL,
        NormTabCol nvarchar(400) COLLATE DATABASE_DEFAULT NULL);
    DECLARE @sql nvarchar(max) = N'
        SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH
        FROM ' + QUOTENAME(@SourceDatabase) + N'.INFORMATION_SCHEMA.COLUMNS c
        JOIN ' + QUOTENAME(@SourceDatabase) + N'.INFORMATION_SCHEMA.TABLES t ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME
        WHERE t.TABLE_TYPE = ''BASE TABLE'' AND (@f IS NULL OR c.TABLE_SCHEMA = @f) AND (@tl IS NULL OR c.TABLE_NAME LIKE @tl)
          AND c.TABLE_NAME NOT LIKE ''%[_]History'' AND c.TABLE_NAME NOT IN (''sysdiagrams'')';
    INSERT #cols (SchemaName, TableName, ColumnName, DataType, MaxLen)
    EXEC sp_executesql @sql, N'@f sysname, @tl nvarchar(128)', @f = @SchemaFilter, @tl = @TableLike;

    UPDATE #cols SET NormCol = canon.fn_Normalize(ColumnName), NormTabCol = canon.fn_Normalize(TableName + ColumnName);
    -- common abbreviations at the end of a column name: _CD, _DT, _NO / _NBR / _NUM, _AMT, _IND, _PCT, _QTY
    UPDATE #cols SET NormAlt =
        CASE WHEN NormCol LIKE N'%CD'  THEN LEFT(NormCol, LEN(NormCol) - 2) + N'CODE'
             WHEN NormCol LIKE N'%DT'  THEN LEFT(NormCol, LEN(NormCol) - 2) + N'DATE'
             WHEN NormCol LIKE N'%NBR' OR NormCol LIKE N'%NUM' THEN LEFT(NormCol, LEN(NormCol) - 3) + N'NUMBER'
             WHEN NormCol LIKE N'%NO'  THEN LEFT(NormCol, LEN(NormCol) - 2) + N'NUMBER'
             WHEN NormCol LIKE N'%AMT' THEN LEFT(NormCol, LEN(NormCol) - 3) + N'AMOUNT'
             WHEN NormCol LIKE N'%IND' THEN LEFT(NormCol, LEN(NormCol) - 3) + N'INDICATOR'
             WHEN NormCol LIKE N'%PCT' THEN LEFT(NormCol, LEN(NormCol) - 3) + N'PERCENT'
             WHEN NormCol LIKE N'%QTY' THEN LEFT(NormCol, LEN(NormCol) - 3) + N'QUANTITY'
             WHEN NormCol LIKE N'%CODE' THEN LEFT(NormCol, LEN(NormCol) - 4)
        END;

    /* 2. every way the master model can be recognized */
    CREATE TABLE #ekeys (ElementId int, ElementCode varchar(80) COLLATE DATABASE_DEFAULT, KeyText nvarchar(400) COLLATE DATABASE_DEFAULT,
                         Method varchar(30), Conf decimal(4,2));
    INSERT #ekeys
    SELECT ElementId, ElementCode, canon.fn_Normalize(ElementCode), 'Exact code', 0.95
    FROM canon.DataElement WHERE Status = 'ACTIVE' AND ScopeId IN (@scopeId, 1)
    UNION ALL
    SELECT ElementId, ElementCode, canon.fn_Normalize(Name), 'Element name', 0.90
    FROM canon.DataElement WHERE Status = 'ACTIVE' AND ScopeId IN (@scopeId, 1)
    UNION ALL
    SELECT e.ElementId, e.ElementCode, canon.fn_Normalize(s.SynonymText),
           CASE WHEN s.SourceSystem = @SourceSystem THEN 'Approved alias' ELSE 'Synonym' END,
           CASE WHEN s.SourceSystem = @SourceSystem THEN 0.99 ELSE 0.90 END
    FROM canon.Synonym s JOIN canon.DataElement e ON e.ElementId = s.ObjectId
    WHERE s.ObjectType = 'ELEMENT' AND s.Status = 'ACTIVE' AND e.Status = 'ACTIVE' AND s.ScopeId IN (@scopeId, 1) AND e.ScopeId IN (@scopeId, 1);
    CREATE INDEX IX_ekeys ON #ekeys (KeyText);

    INSERT intake.Candidate (ScanRunId, CandidateType, SourceSchema, SourceTable, SourceColumn, SourceDataType, SourceLength,
                             MatchedObjectType, MatchedObjectId, MatchedCode, MatchMethod, Confidence, Status)
    SELECT @ScanRunId, 'ELEMENT', c.SchemaName, c.TableName, c.ColumnName, c.DataType, c.MaxLen,
           CASE WHEN m.ElementId IS NOT NULL THEN 'ELEMENT' END, m.ElementId, m.ElementCode, m.Method, m.Conf,
           CASE WHEN m.ElementId IS NULL THEN 'NEW' ELSE 'MATCHED' END
    FROM #cols c
    OUTER APPLY (
        SELECT TOP (1) k.ElementId, k.ElementCode,
               CASE WHEN k.KeyText = c.NormCol THEN k.Method WHEN k.KeyText = c.NormAlt THEN 'Abbreviation' ELSE 'Table + column' END AS Method,
               CONVERT(decimal(4,2), CASE WHEN k.KeyText = c.NormCol THEN k.Conf WHEN k.KeyText = c.NormAlt THEN k.Conf - 0.05 ELSE k.Conf - 0.10 END) AS Conf
        FROM #ekeys k
        WHERE k.KeyText IN (c.NormCol, c.NormAlt, c.NormTabCol)
        ORDER BY CASE WHEN k.KeyText = c.NormCol THEN k.Conf WHEN k.KeyText = c.NormAlt THEN k.Conf - 0.05 ELSE k.Conf - 0.10 END DESC
    ) m;

    /* 3. values of code-like text columns */
    IF @ScanValues = 1
    BEGIN
        CREATE TABLE #okeys (PickListId int, OptionId int, OptionCode nvarchar(60) COLLATE DATABASE_DEFAULT, KeyText nvarchar(400) COLLATE DATABASE_DEFAULT,
                             Method varchar(30), Conf decimal(4,2));
        INSERT #okeys
        SELECT PickListId, OptionId, OptionCode, canon.fn_Normalize(OptionCode), 'Exact code', 0.95
        FROM canon.PickListOption WHERE Status = 'ACTIVE' AND ScopeId IN (@scopeId, 1)
        UNION ALL
        SELECT PickListId, OptionId, OptionCode, canon.fn_Normalize(OptionName), 'Option name', 0.90
        FROM canon.PickListOption WHERE Status = 'ACTIVE' AND ScopeId IN (@scopeId, 1)
        UNION ALL
        SELECT o.PickListId, o.OptionId, o.OptionCode, canon.fn_Normalize(s.SynonymText),
               CASE WHEN s.SourceSystem = @SourceSystem THEN 'Approved alias' ELSE 'Synonym' END,
               CASE WHEN s.SourceSystem = @SourceSystem THEN 0.99 ELSE 0.88 END
        FROM canon.Synonym s JOIN canon.PickListOption o ON o.OptionId = s.ObjectId
        WHERE s.ObjectType = 'OPTION' AND s.Status = 'ACTIVE' AND o.Status = 'ACTIVE' AND s.ScopeId IN (@scopeId, 1);
        CREATE INDEX IX_okeys ON #okeys (PickListId, KeyText);

        CREATE TABLE #vals (v nvarchar(300) COLLATE DATABASE_DEFAULT, n bigint);
        DECLARE @cid int, @s sysname, @t sysname, @c sysname, @pl int, @nd int, @top int = @MaxDistinct + 1;
        DECLARE cur CURSOR LOCAL FAST_FORWARD FOR
            SELECT k.CandidateId, k.SourceSchema, k.SourceTable, k.SourceColumn, e.PickListId
            FROM intake.Candidate k
            LEFT JOIN canon.DataElement e ON e.ElementId = k.MatchedObjectId
            WHERE k.ScanRunId = @ScanRunId AND k.CandidateType = 'ELEMENT'
              AND k.SourceDataType IN ('char', 'varchar', 'nchar', 'nvarchar') AND k.SourceLength BETWEEN 1 AND 100
              AND (k.Status = 'NEW' OR e.PickListId IS NOT NULL);
        OPEN cur;
        FETCH NEXT FROM cur INTO @cid, @s, @t, @c, @pl;
        WHILE @@FETCH_STATUS = 0
        BEGIN
            TRUNCATE TABLE #vals;
            BEGIN TRY
                SET @sql = N'SELECT TOP (@top) LTRIM(RTRIM(CONVERT(nvarchar(300), ' + QUOTENAME(@c) + N'))), COUNT_BIG(*) FROM '
                         + QUOTENAME(@SourceDatabase) + N'.' + QUOTENAME(@s) + N'.' + QUOTENAME(@t)
                         + N' WHERE ' + QUOTENAME(@c) + N' IS NOT NULL AND LTRIM(RTRIM(' + QUOTENAME(@c) + N')) <> N'''''
                         + N' GROUP BY LTRIM(RTRIM(CONVERT(nvarchar(300), ' + QUOTENAME(@c) + N'))) ORDER BY COUNT_BIG(*) DESC';
                INSERT #vals EXEC sp_executesql @sql, N'@top int', @top = @top;
            END TRY
            BEGIN CATCH
                UPDATE intake.Candidate SET SampleValues = LEFT(N'Could not read values: ' + ERROR_MESSAGE(), 1000) WHERE CandidateId = @cid;
            END CATCH;
            SET @nd = (SELECT COUNT(*) FROM #vals);
            UPDATE intake.Candidate
            SET DistinctValues = CASE WHEN @nd > @MaxDistinct THEN NULL ELSE @nd END,
                SampleValues = CASE WHEN @nd > @MaxDistinct THEN N'More than ' + CONVERT(nvarchar(10), @MaxDistinct) + N' distinct values (not a code list)'
                                    ELSE (SELECT STRING_AGG(CONVERT(nvarchar(max), v), N', ') FROM (SELECT TOP (12) v FROM #vals ORDER BY n DESC) x) END
            WHERE CandidateId = @cid AND @nd > 0;
            IF @nd BETWEEN 1 AND @MaxDistinct
                INSERT intake.Candidate (ScanRunId, CandidateType, SourceSchema, SourceTable, SourceColumn, SourceValue, ValueRows,
                                         MatchedObjectType, MatchedObjectId, MatchedCode, MatchMethod, Confidence, Status)
                SELECT @ScanRunId, 'OPTION', @s, @t, @c, x.v, x.n,
                       CASE WHEN m.OptionId IS NOT NULL THEN 'OPTION' END, m.OptionId, m.OptionCode, m.Method, m.Conf,
                       CASE WHEN m.OptionId IS NULL THEN 'NEW' ELSE 'MATCHED' END
                FROM #vals x
                OUTER APPLY (SELECT TOP (1) o.OptionId, o.OptionCode, o.Method, o.Conf FROM #okeys o
                             WHERE @pl IS NOT NULL AND o.PickListId = @pl AND o.KeyText = canon.fn_Normalize(x.v)
                             ORDER BY o.Conf DESC) m;
            FETCH NEXT FROM cur INTO @cid, @s, @t, @c, @pl;
        END;
        CLOSE cur; DEALLOCATE cur;
    END;

    UPDATE intake.ScanRun SET FinishedAt = SYSUTCDATETIME(),
        ColumnsScanned  = (SELECT COUNT(*) FROM intake.Candidate WHERE ScanRunId = @ScanRunId AND CandidateType = 'ELEMENT'),
        ElementsMatched = (SELECT COUNT(*) FROM intake.Candidate WHERE ScanRunId = @ScanRunId AND CandidateType = 'ELEMENT' AND Status = 'MATCHED'),
        ElementsNew     = (SELECT COUNT(*) FROM intake.Candidate WHERE ScanRunId = @ScanRunId AND CandidateType = 'ELEMENT' AND Status = 'NEW'),
        ValuesMatched   = (SELECT COUNT(*) FROM intake.Candidate WHERE ScanRunId = @ScanRunId AND CandidateType = 'OPTION' AND Status = 'MATCHED'),
        ValuesNew       = (SELECT COUNT(*) FROM intake.Candidate WHERE ScanRunId = @ScanRunId AND CandidateType = 'OPTION' AND Status = 'NEW')
    WHERE ScanRunId = @ScanRunId;

    SELECT ScanRunId, DatabaseName, ColumnsScanned, ElementsMatched, ElementsNew, ValuesMatched, ValuesNew,
           N'Next: EXEC intake.usp_ProposeMissing ' + CONVERT(nvarchar(20), ScanRunId) + N';' AS NextStep
    FROM intake.ScanRun WHERE ScanRunId = @ScanRunId;
    SELECT CandidateType, Status, MatchMethod, COUNT(*) AS Items, AVG(Confidence) AS AvgConfidence
    FROM intake.Candidate WHERE ScanRunId = @ScanRunId GROUP BY CandidateType, Status, MatchMethod ORDER BY CandidateType, Status, Items DESC;
END;
GO

-- Turn one scan into change requests: new elements (with a new pick list when the column is a code list),
-- new pick-list options, and newly learned synonyms (so the next scan matches them as approved aliases).
CREATE OR ALTER PROCEDURE intake.usp_ProposeMissing
    @ScanRunId int,
    @RequestedBy nvarchar(100) = NULL,
    @LearnSynonyms bit = 1,
    @Scope nvarchar(80) = N'GLOBAL'
AS
BEGIN
    SET NOCOUNT ON;
    SET @RequestedBy = ISNULL(@RequestedBy, N'SI2 intake');
    DECLARE @src nvarchar(60) = (SELECT SourceSystemCode FROM intake.ScanRun WHERE ScanRunId = @ScanRunId);
    DECLARE @db sysname = (SELECT DatabaseName FROM intake.ScanRun WHERE ScanRunId = @ScanRunId);
    IF @src IS NULL THROW 50011, N'Scan run not found.', 1;
    DECLARE @rid int, @j nvarchar(max), @summary nvarchar(1000), @code nvarchar(300);

    /* new elements: one proposal per distinct column name */
    DECLARE @new TABLE (n int IDENTITY(1,1), NormCol nvarchar(400), ColumnName sysname, DataType varchar(60), MaxLen int, Tables int,
                        Distinct_ int NULL, Samples nvarchar(1000) NULL, FirstWhere nvarchar(400));
    INSERT @new (NormCol, ColumnName, DataType, MaxLen, Tables, Distinct_, Samples, FirstWhere)
    SELECT canon.fn_Normalize(SourceColumn), MIN(SourceColumn), MIN(SourceDataType), MAX(SourceLength), COUNT(*), MAX(DistinctValues),
           MAX(SampleValues), MIN(SourceSchema + N'.' + SourceTable + N'.' + SourceColumn)
    FROM intake.Candidate
    WHERE ScanRunId = @ScanRunId AND CandidateType = 'ELEMENT' AND Status = 'NEW'
    GROUP BY canon.fn_Normalize(SourceColumn);

    DECLARE @n int = 1, @max int = (SELECT COUNT(*) FROM @new), @col sysname, @dt varchar(60), @len int, @nd int, @samples nvarchar(1000),
            @where nvarchar(400), @type varchar(20), @isCode bit, @norm nvarchar(400), @tables int, @fp varchar(60), @nvals int;
    WHILE @n <= @max
    BEGIN
        SELECT @col = ColumnName, @dt = DataType, @len = MaxLen, @nd = Distinct_, @samples = Samples, @where = FirstWhere, @norm = NormCol, @tables = Tables
        FROM @new WHERE n = @n;
        SET @code = UPPER(REPLACE(REPLACE(@col, N' ', N'_'), N'-', N'_'));
        SET @isCode = CASE WHEN @nd BETWEEN 1 AND 50 AND @dt IN ('char', 'varchar', 'nchar', 'nvarchar') THEN 1 ELSE 0 END;
        SET @type = CASE WHEN @isCode = 1 THEN 'CODE'
                         WHEN @dt IN ('int', 'bigint', 'smallint', 'tinyint') THEN 'INTEGER'
                         WHEN @dt IN ('money', 'smallmoney') OR (@dt IN ('decimal', 'numeric') AND (@norm LIKE N'%AMT%' OR @norm LIKE N'%AMOUNT%' OR @norm LIKE N'%PREM%' OR @norm LIKE N'%PAID%' OR @norm LIKE N'%RESERVE%')) THEN 'AMOUNT'
                         WHEN @dt IN ('decimal', 'numeric', 'float', 'real') THEN 'DECIMAL'
                         WHEN @dt = 'date' THEN 'DATE'
                         WHEN @dt IN ('datetime', 'datetime2', 'smalldatetime', 'datetimeoffset') THEN 'DATETIME'
                         WHEN @dt = 'bit' THEN 'BOOLEAN'
                         ELSE 'TEXT' END;
        -- value fingerprint: do the values all belong to an existing pick list (e.g. Y / N -> YES_NO)?
        SET @fp = NULL;
        IF @isCode = 1
        BEGIN
            SET @nvals = (SELECT COUNT(DISTINCT SourceValue) FROM intake.Candidate
                          WHERE ScanRunId = @ScanRunId AND CandidateType = 'OPTION' AND canon.fn_Normalize(SourceColumn) = @norm);
            WITH k AS (
                SELECT o.PickListId, canon.fn_Normalize(o.OptionCode) AS KeyText FROM canon.PickListOption o WHERE o.Status = 'ACTIVE'
                UNION SELECT o.PickListId, canon.fn_Normalize(o.OptionName) FROM canon.PickListOption o WHERE o.Status = 'ACTIVE'
                UNION SELECT o.PickListId, canon.fn_Normalize(s.SynonymText) FROM canon.Synonym s
                      JOIN canon.PickListOption o ON s.ObjectType = 'OPTION' AND o.OptionId = s.ObjectId WHERE s.Status = 'ACTIVE' AND o.Status = 'ACTIVE'),
            v AS (SELECT DISTINCT SourceValue FROM intake.Candidate
                  WHERE ScanRunId = @ScanRunId AND CandidateType = 'OPTION' AND canon.fn_Normalize(SourceColumn) = @norm)
            SELECT TOP (1) @fp = p.PickListCode
            FROM v JOIN k ON k.KeyText = canon.fn_Normalize(v.SourceValue)
            JOIN canon.PickList p ON p.PickListId = k.PickListId AND p.Status = 'ACTIVE'
            GROUP BY p.PickListCode, p.PickListId, p.LibrarySource
            HAVING COUNT(DISTINCT v.SourceValue) = @nvals
            ORDER BY (SELECT COUNT(*) FROM canon.PickListOption x WHERE x.PickListId = p.PickListId AND x.Status = 'ACTIVE'),
                     CASE WHEN p.LibrarySource IN ('STANDARD', 'SI2', 'COMPANY') THEN 0 ELSE 1 END, p.PickListCode;
        END;
        IF canon.fn_ElementId(@code, canon.fn_ScopeId(@Scope)) IS NULL
           AND NOT EXISTS (SELECT 1 FROM gov.ChangeRequest WHERE ObjectType = 'ELEMENT' AND ChangeType = 'ADD' AND ObjectCode = @code AND Status = 'PENDING')
        BEGIN
            IF @isCode = 1 AND @fp IS NULL AND canon.fn_PickListId(@code, canon.fn_ScopeId(@Scope)) IS NULL
            BEGIN
                SET @j = (SELECT @code AS code, @col AS name, N'Values found in ' + @db + N'.' + @where + N'. SME to confirm the meaning of each code.' AS description,
                                 'COMPANY' AS library, @Scope AS scope FOR JSON PATH, WITHOUT_ARRAY_WRAPPER);
                SET @summary = N'New pick list ' + @code + N' (' + CONVERT(nvarchar(10), @nd) + N' values: ' + LEFT(ISNULL(@samples, N''), 200) + N')';
                EXEC gov.usp_RequestChange 'PICKLIST', 'ADD', @code, @j, @RequestedBy, @summary, 'INTAKE', @ScanRunId, @rid OUTPUT;
            END;
            SET @j = (SELECT @code AS code, @col AS name,
                             N'Found in ' + @db + N'.' + @where + CASE WHEN @tables > 1 THEN N' and ' + CONVERT(nvarchar(10), @tables - 1) + N' other table(s)' ELSE N'' END
                             + N' (' + @dt + ISNULL(N'(' + CONVERT(nvarchar(10), NULLIF(@len, -1)) + N')', N'') + N'). SME to write the business description.' AS description,
                             @type AS data_type, CASE WHEN @len > 0 THEN @len END AS max_length,
                             CASE WHEN @isCode = 1 THEN ISNULL(@fp, @code) END AS picklist, 'MEDIUM' AS risk, @Scope AS scope,
                             JSON_QUERY((SELECT @col AS [text], 'SOURCE' AS [type], @src AS [source], 'New from intake' AS method FOR JSON PATH)) AS synonyms
                      FOR JSON PATH, WITHOUT_ARRAY_WRAPPER);
            SET @summary = N'New data element ' + @code + N' (' + @type + N', ' + CONVERT(nvarchar(10), @tables) + N' table(s))'
                         + ISNULL(N'; values match pick list ' + @fp + N' (value fingerprint)', N'')
                         + ISNULL(N'; sample: ' + LEFT(@samples, 200), N'');
            EXEC gov.usp_RequestChange 'ELEMENT', 'ADD', @code, @j, @RequestedBy, @summary, 'INTAKE', @ScanRunId, @rid OUTPUT;
            UPDATE intake.Candidate SET Status = 'PROPOSED', ChangeRequestId = @rid
            WHERE ScanRunId = @ScanRunId AND CandidateType = 'ELEMENT' AND Status = 'NEW' AND canon.fn_Normalize(SourceColumn) = @norm;
            -- values of a fingerprinted column already exist; otherwise they become the options of the new pick list
            IF @fp IS NOT NULL
                UPDATE intake.Candidate SET Status = 'MATCHED', MatchMethod = 'Value fingerprint', MatchedCode = @fp
                WHERE ScanRunId = @ScanRunId AND CandidateType = 'OPTION' AND Status = 'NEW' AND canon.fn_Normalize(SourceColumn) = @norm;
            IF @isCode = 1 AND @fp IS NULL
            BEGIN
                DECLARE @v nvarchar(300), @vn int = 0;
                DECLARE vcur CURSOR LOCAL FAST_FORWARD FOR
                    SELECT SourceValue FROM intake.Candidate
                    WHERE ScanRunId = @ScanRunId AND CandidateType = 'OPTION' AND Status = 'NEW' AND canon.fn_Normalize(SourceColumn) = @norm
                    GROUP BY SourceValue ORDER BY SUM(ValueRows) DESC;
                OPEN vcur; FETCH NEXT FROM vcur INTO @v;
                WHILE @@FETCH_STATUS = 0
                BEGIN
                    SET @vn += 1;
                    SET @j = (SELECT @code AS picklist, LEFT(@v, 60) AS code, @v AS name, @vn * 10 AS sort, @Scope AS scope FOR JSON PATH, WITHOUT_ARRAY_WRAPPER);
                    SET @summary = N'Option ' + @code + N'.' + LEFT(@v, 60) + N' (SME: give the business name)';
                    DECLARE @oc nvarchar(300) = @code + N'.' + LEFT(@v, 60);
                    EXEC gov.usp_RequestChange 'OPTION', 'ADD', @oc, @j, @RequestedBy, @summary, 'INTAKE', @ScanRunId, @rid OUTPUT;
                    UPDATE intake.Candidate SET Status = 'PROPOSED', ChangeRequestId = @rid
                    WHERE ScanRunId = @ScanRunId AND CandidateType = 'OPTION' AND Status = 'NEW' AND canon.fn_Normalize(SourceColumn) = @norm AND SourceValue = @v;
                    FETCH NEXT FROM vcur INTO @v;
                END;
                CLOSE vcur; DEALLOCATE vcur;
            END;
        END;
        SET @n += 1;
    END;

    /* new values for existing pick lists */
    DECLARE @pc varchar(60), @val nvarchar(300), @rows bigint, @cols nvarchar(1000);
    DECLARE ocur CURSOR LOCAL FAST_FORWARD FOR
        SELECT p.PickListCode, o.SourceValue, SUM(o.ValueRows),
               STRING_AGG(CONVERT(nvarchar(max), o.SourceTable + N'.' + o.SourceColumn), N', ')
        FROM intake.Candidate o
        JOIN intake.Candidate e ON e.ScanRunId = o.ScanRunId AND e.CandidateType = 'ELEMENT' AND e.SourceSchema = o.SourceSchema
                               AND e.SourceTable = o.SourceTable AND e.SourceColumn = o.SourceColumn AND e.Status IN ('MATCHED', 'APPROVED')
        JOIN canon.DataElement d ON d.ElementId = e.MatchedObjectId
        JOIN canon.PickList p ON p.PickListId = d.PickListId
        WHERE o.ScanRunId = @ScanRunId AND o.CandidateType = 'OPTION' AND o.Status = 'NEW'
        GROUP BY p.PickListCode, o.SourceValue;
    OPEN ocur; FETCH NEXT FROM ocur INTO @pc, @val, @rows, @cols;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @code = @pc + N'.' + LEFT(@val, 60);
        IF NOT EXISTS (SELECT 1 FROM gov.ChangeRequest WHERE ObjectType = 'OPTION' AND ObjectCode = @code AND Status = 'PENDING')
        BEGIN
            SET @j = (SELECT @pc AS picklist, LEFT(@val, 60) AS code, @val AS name, 900 AS sort, @Scope AS scope FOR JSON PATH, WITHOUT_ARRAY_WRAPPER);
            SET @summary = N'Value ''' + @val + N''' (' + CONVERT(nvarchar(20), @rows) + N' rows in ' + LEFT(@cols, 300) + N') is not in pick list '
                         + @pc + N'. Approve to add it, or reject and add it as a synonym of an existing option.';
            EXEC gov.usp_RequestChange 'OPTION', 'ADD', @code, @j, @RequestedBy, @summary, 'INTAKE', @ScanRunId, @rid OUTPUT;
            UPDATE o SET Status = 'PROPOSED', ChangeRequestId = @rid
            FROM intake.Candidate o
            JOIN intake.Candidate e ON e.ScanRunId = o.ScanRunId AND e.CandidateType = 'ELEMENT' AND e.SourceSchema = o.SourceSchema
                                   AND e.SourceTable = o.SourceTable AND e.SourceColumn = o.SourceColumn
            JOIN canon.DataElement d ON d.ElementId = e.MatchedObjectId
            JOIN canon.PickList p ON p.PickListId = d.PickListId
            WHERE o.ScanRunId = @ScanRunId AND o.CandidateType = 'OPTION' AND o.Status = 'NEW' AND p.PickListCode = @pc AND o.SourceValue = @val;
        END;
        FETCH NEXT FROM ocur INTO @pc, @val, @rows, @cols;
    END;
    CLOSE ocur; DEALLOCATE ocur;

    /* learned synonyms: matched by name, abbreviation or table + column (not yet an approved alias for this source) */
    IF @LearnSynonyms = 1
    BEGIN
        DECLARE @ec varchar(80), @sc sysname, @mm varchar(30), @cf decimal(4,2);
        DECLARE scur CURSOR LOCAL FAST_FORWARD FOR
            SELECT MatchedCode, SourceColumn, MIN(MatchMethod), MIN(Confidence)
            FROM intake.Candidate
            WHERE ScanRunId = @ScanRunId AND CandidateType = 'ELEMENT' AND Status = 'MATCHED' AND MatchMethod NOT IN ('Approved alias', 'Exact code')
            GROUP BY MatchedCode, SourceColumn;
        OPEN scur; FETCH NEXT FROM scur INTO @ec, @sc, @mm, @cf;
        WHILE @@FETCH_STATUS = 0
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM canon.Synonym s WHERE s.ObjectType = 'ELEMENT' AND s.ObjectId = canon.fn_ElementId(@ec, canon.fn_ScopeId(@Scope))
                                                         AND s.SynonymText = @sc AND s.SourceSystem = @src)
               AND NOT EXISTS (SELECT 1 FROM gov.ChangeRequest WHERE ObjectType = 'SYNONYM' AND Status = 'PENDING'
                                                         AND ObjectCode = @ec AND JSON_VALUE(PayloadJson, '$.text') = @sc AND JSON_VALUE(PayloadJson, '$.source') = @src)
            BEGIN
                SET @j = (SELECT 'ELEMENT' AS object_type, @ec AS object_code, @sc AS [text], 'SOURCE' AS [type], @src AS [source],
                                 @mm AS method, @cf AS confidence, @Scope AS scope FOR JSON PATH, WITHOUT_ARRAY_WRAPPER);
                SET @summary = @src + N' column ' + @sc + N' = ' + @ec + N' (' + @mm + N', ' + CONVERT(nvarchar(10), @cf) + N')';
                EXEC gov.usp_RequestChange 'SYNONYM', 'ADD', @ec, @j, @RequestedBy, @summary, 'INTAKE', @ScanRunId, @rid OUTPUT;
                UPDATE intake.Candidate SET ChangeRequestId = @rid
                WHERE ScanRunId = @ScanRunId AND CandidateType = 'ELEMENT' AND Status = 'MATCHED' AND MatchedCode = @ec AND SourceColumn = @sc;
            END;
            FETCH NEXT FROM scur INTO @ec, @sc, @mm, @cf;
        END;
        CLOSE scur; DEALLOCATE scur;
    END;

    SELECT ObjectType, ChangeType, COUNT(*) AS Requests FROM gov.ChangeRequest
    WHERE ScanRunId = @ScanRunId AND Status = 'PENDING' GROUP BY ObjectType, ChangeType ORDER BY ObjectType;
    SELECT N'Review: SELECT * FROM gov.vw_PendingChange WHERE ScanRunId = ' + CONVERT(nvarchar(20), @ScanRunId)
         + N';  Approve (second person): EXEC gov.usp_DecideAll @DecidedBy = N''<name>'', @ScanRunId = ' + CONVERT(nvarchar(20), @ScanRunId) + N';' AS NextStep;
END;
GO

/* -------------------------------------------------------------------------------------------- views */
CREATE OR ALTER VIEW canon.vw_DataElement
AS
SELECT e.ElementCode, e.Name, e.BusinessDescription, e.SubjectAreaCode AS SubjectArea, e.DataType, e.MaxLength,
       p.PickListCode AS PickList, e.IsPII, e.IsBureauReported, e.RiskClass, e.OwnerSME,
       canon.fn_ScopeLabel(e.ScopeId) AS Scope, e.Status, e.EffectiveFrom, e.EffectiveTo,
       (SELECT STRING_AGG(CONVERT(nvarchar(max), s.SynonymText + CASE WHEN s.SourceSystem = N'*' THEN N'' ELSE N' (' + s.SourceSystem + N')' END), N'; ')
        FROM canon.Synonym s WHERE s.ObjectType = 'ELEMENT' AND s.ObjectId = e.ElementId AND s.Status = 'ACTIVE') AS Synonyms,
       (SELECT STRING_AGG(CONVERT(nvarchar(max), u.UsedIn + N': ' + ISNULL(u.ObjectName + N'.', N'') + u.FieldName), N'; ')
        FROM canon.ElementUsage u WHERE u.ElementId = e.ElementId) AS UsedIn,
       e.ElementId, e.CreatedBy, e.CreatedAt
FROM canon.DataElement e
LEFT JOIN canon.PickList p ON p.PickListId = e.PickListId;
GO

CREATE OR ALTER VIEW canon.vw_PickListOption
AS
SELECT p.PickListCode AS PickList, p.Name AS PickListName, p.LibrarySource, o.OptionCode, o.OptionName, o.Description,
       o.LobScope, o.StateScope, o.SortOrder, canon.fn_ScopeLabel(o.ScopeId) AS Scope, o.Status, o.EffectiveFrom, o.EffectiveTo,
       (SELECT STRING_AGG(CONVERT(nvarchar(max), b.Bureau + N' ' + b.BureauCode + CASE WHEN b.LobScope = '*' THEN N'' ELSE N' [' + b.LobScope + N']' END), N'; ')
        FROM canon.BureauCodeMap b WHERE b.OptionId = o.OptionId AND b.Status = 'ACTIVE') AS BureauCodes,
       (SELECT STRING_AGG(CONVERT(nvarchar(max), s.SynonymText + CASE WHEN s.SourceSystem = N'*' THEN N'' ELSE N' (' + s.SourceSystem + N')' END), N'; ')
        FROM canon.Synonym s WHERE s.ObjectType = 'OPTION' AND s.ObjectId = o.OptionId AND s.Status = 'ACTIVE') AS Synonyms,
       o.OptionId, p.PickListId
FROM canon.PickListOption o
JOIN canon.PickList p ON p.PickListId = o.PickListId;
GO

CREATE OR ALTER VIEW canon.vw_PickList
AS
SELECT p.PickListCode, p.Name, p.Description, p.LibrarySource, p.LibraryRelease, canon.fn_ScopeLabel(p.ScopeId) AS Scope, p.Status,
       (SELECT COUNT(*) FROM canon.PickListOption o WHERE o.PickListId = p.PickListId AND o.Status = 'ACTIVE') AS ActiveOptions,
       (SELECT STRING_AGG(CONVERT(nvarchar(max), e.ElementCode), N', ') FROM canon.DataElement e WHERE e.PickListId = p.PickListId) AS UsedByElements,
       (SELECT STRING_AGG(CONVERT(nvarchar(max), s.SynonymText), N'; ') FROM canon.Synonym s
        WHERE s.ObjectType = 'PICKLIST' AND s.ObjectId = p.PickListId AND s.Status = 'ACTIVE') AS Synonyms,
       p.PickListId
FROM canon.PickList p;
GO

CREATE OR ALTER VIEW canon.vw_Synonym
AS
SELECT s.ObjectType,
       CASE s.ObjectType WHEN 'ELEMENT' THEN e.ElementCode WHEN 'PICKLIST' THEN p.PickListCode
                         WHEN 'OPTION' THEN op.PickListCode + N'.' + o.OptionCode WHEN 'RULE' THEN r.RuleCode WHEN 'RULESET' THEN rs.RuleSetCode END AS ObjectCode,
       s.SynonymText, s.SynonymType, s.SourceSystem, s.MatchMethod, s.Confidence, canon.fn_ScopeLabel(s.ScopeId) AS Scope, s.Status, s.CreatedBy, s.CreatedAt, s.SynonymId
FROM canon.Synonym s
LEFT JOIN canon.DataElement e ON s.ObjectType = 'ELEMENT' AND e.ElementId = s.ObjectId
LEFT JOIN canon.PickList p ON s.ObjectType = 'PICKLIST' AND p.PickListId = s.ObjectId
LEFT JOIN canon.PickListOption o ON s.ObjectType = 'OPTION' AND o.OptionId = s.ObjectId
LEFT JOIN canon.PickList op ON op.PickListId = o.PickListId
LEFT JOIN rules.BusinessRule r ON s.ObjectType = 'RULE' AND r.RuleId = s.ObjectId
LEFT JOIN rules.RuleSet rs ON s.ObjectType = 'RULESET' AND rs.RuleSetId = s.ObjectId;
GO

CREATE OR ALTER VIEW rules.vw_Rule
AS
SELECT rs.RuleSetCode AS RuleSet, rs.Purpose, r.RuleCode, r.Name, r.Description, r.RuleType, r.LobScope, r.StateScope,
       te.ElementCode AS TargetElement, r.ConditionLogic,
       ISNULL(CASE WHEN r.ConditionLogic = 'ANY'
              THEN (SELECT STRING_AGG(CONVERT(nvarchar(max), e.ElementCode + N' ' + c.Operator + ISNULL(N' ' + c.Value1, N'') + ISNULL(N' AND ' + c.Value2, N'')), N' OR ')
                           WITHIN GROUP (ORDER BY c.Seq)
                    FROM rules.RuleCondition c JOIN canon.DataElement e ON e.ElementId = c.ElementId WHERE c.RuleId = r.RuleId)
              ELSE (SELECT STRING_AGG(CONVERT(nvarchar(max), e.ElementCode + N' ' + c.Operator + ISNULL(N' ' + c.Value1, N'') + ISNULL(N' AND ' + c.Value2, N'')), N' AND ')
                           WITHIN GROUP (ORDER BY c.Seq)
                    FROM rules.RuleCondition c JOIN canon.DataElement e ON e.ElementId = c.ElementId WHERE c.RuleId = r.RuleId) END, r.ConditionText) AS Conditions,
       r.ActionType, r.ActionValue, r.Severity, r.Message, r.Priority, canon.fn_ScopeLabel(r.ScopeId) AS Scope, r.Status, r.EffectiveFrom, r.EffectiveTo,
       (SELECT COUNT(*) FROM rules.RuleTestCase t WHERE t.RuleId = r.RuleId) AS TestCases, r.ExpressionJson, r.RuleId
FROM rules.BusinessRule r
JOIN rules.RuleSet rs ON rs.RuleSetId = r.RuleSetId
LEFT JOIN canon.DataElement te ON te.ElementId = r.TargetElementId;
GO

CREATE OR ALTER VIEW gov.vw_PendingChange
AS
SELECT RequestId, ObjectType, ChangeType, ObjectCode, Summary, Source, ScanRunId, RequestedBy, RequestedAt, PayloadJson
FROM gov.ChangeRequest WHERE Status = 'PENDING';
GO

CREATE OR ALTER VIEW intake.vw_Candidate
AS
SELECT k.ScanRunId, r.DatabaseName, k.CandidateType, k.SourceSchema, k.SourceTable, k.SourceColumn, k.SourceDataType, k.SourceLength,
       k.SourceValue, k.ValueRows, k.DistinctValues, k.SampleValues, k.MatchedCode, k.MatchMethod, k.Confidence, k.Status, k.ChangeRequestId, k.CandidateId
FROM intake.Candidate k JOIN intake.ScanRun r ON r.ScanRunId = k.ScanRunId;
GO

-- One-row health summary of the master model.
CREATE OR ALTER VIEW canon.vw_Summary
AS
SELECT
    (SELECT COUNT(*) FROM canon.SubjectArea) AS SubjectAreas,
    (SELECT COUNT(*) FROM canon.DataElement WHERE Status = 'ACTIVE') AS DataElements,
    (SELECT COUNT(*) FROM canon.PickList WHERE Status = 'ACTIVE') AS PickLists,
    (SELECT COUNT(*) FROM canon.PickListOption WHERE Status = 'ACTIVE') AS PickListOptions,
    (SELECT COUNT(*) FROM canon.Synonym WHERE Status = 'ACTIVE') AS Synonyms,
    (SELECT COUNT(*) FROM canon.BureauCodeMap WHERE Status = 'ACTIVE') AS BureauCodes,
    (SELECT COUNT(*) FROM canon.ElementUsage) AS WhereUsed,
    (SELECT COUNT(*) FROM rules.RuleSet WHERE Status = 'ACTIVE') AS RuleSets,
    (SELECT COUNT(*) FROM rules.BusinessRule WHERE Status = 'ACTIVE') AS Rules,
    (SELECT COUNT(*) FROM rules.RuleTestCase) AS RuleTests,
    (SELECT COUNT(*) FROM gov.ChangeRequest WHERE Status = 'PENDING') AS PendingChanges,
    (SELECT COUNT(*) FROM canon.Scope) AS Scopes;
GO
