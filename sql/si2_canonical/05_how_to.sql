/* =====================================================================================================
   SI² Canonical Master · how to use it (run a block at a time in SSMS)
   Two names are used: 'Saba' proposes, 'Reviewer' approves. Use real names; the same person cannot do both.
   ===================================================================================================== */
USE SI2Canonical;
GO

/* 1. What is in the model --------------------------------------------------------------------------- */
SELECT * FROM canon.vw_Summary;
SELECT * FROM canon.vw_DataElement WHERE Status = 'ACTIVE' ORDER BY SubjectArea, ElementCode;
SELECT * FROM canon.vw_PickList ORDER BY LibrarySource, PickListCode;
SELECT * FROM canon.vw_PickListOption WHERE PickList = 'CAUSE_OF_LOSS' ORDER BY SortOrder;
SELECT * FROM canon.vw_Synonym WHERE ObjectCode = 'POLICY_NUMBER';
SELECT * FROM rules.vw_Rule ORDER BY RuleSet, Priority, RuleCode;

-- Which element does a name mean? (any synonym, any source system)
SELECT ObjectType, ObjectCode, SynonymText, SourceSystem FROM canon.vw_Synonym
WHERE canon.fn_Normalize(SynonymText) = canon.fn_Normalize(N'pol_no');

/* 2. Add a data element (minutes) ------------------------------------------------------------------- */
EXEC canon.usp_ProposeElement
     @Code = 'ROOF_AGE_BAND', @Name = N'Roof Age Band', @Description = N'Roof age grouped for rating: 0-5, 6-10, 11-15, 16+ years.',
     @DataType = 'TEXT', @SubjectArea = 'PROPERTY', @Synonyms = N'RoofAgeBand,roof_age_grp', @RequestedBy = N'Saba';
SELECT * FROM gov.vw_PendingChange;
EXEC gov.usp_Decide @RequestId = 3, @DecidedBy = N'Reviewer', @Approve = 1, @Note = N'Matches the 2027 rating plan';   -- use the RequestId shown

/* 3. Add a pick list with its options ---------------------------------------------------------------- */
EXEC canon.usp_ProposePickList @Code = 'ROOF_SHAPE', @Name = N'Roof Shape', @Description = N'Shape of the roof (wind mitigation).',
     @Options = N'GABLE=Gable;HIP=Hip;FLAT=Flat;GAMBREL=Gambrel;MANSARD=Mansard', @RequestedBy = N'Saba';
EXEC gov.usp_DecideAll @DecidedBy = N'Reviewer', @ObjectCodeLike = N'ROOF_SHAPE%';

/* 4. Add a synonym (a source name or a business word) ------------------------------------------------ */
EXEC canon.usp_ProposeSynonym @ObjectType = 'ELEMENT', @ObjectCode = 'POLICY_NUMBER', @Synonym = N'POLICY_REF', @Source = N'Majesco', @RequestedBy = N'Saba';
EXEC canon.usp_ProposeSynonym @ObjectType = 'OPTION', @PickList = 'CLAIM_STATUS', @ObjectCode = 'OP', @Synonym = N'Pending', @Source = N'Majesco', @RequestedBy = N'Saba';
EXEC gov.usp_DecideAll @DecidedBy = N'Reviewer', @ObjectType = 'SYNONYM';

/* 5. Add a rule, approve it, test it ------------------------------------------------------------------ */
EXEC rules.usp_ProposeRule @RuleSet = 'UW_PERSONAL_AUTO', @Code = 'R12', @Name = N'Young driver on a high-symbol vehicle',
     @RuleType = 'REFERRAL', @ActionType = 'REFER',
     @ConditionsJson = N'[["DRIVER_AGE","<","25"],["VEHICLE_SYMBOL",">=","20"]]', @RequestedBy = N'Saba';
EXEC gov.usp_DecideAll @DecidedBy = N'Reviewer', @ObjectType = 'RULE';
EXEC rules.usp_TestRule @RuleCode = 'R12', @InputJson = N'{"DRIVER_AGE": 22, "VEHICLE_SYMBOL": 24}';
INSERT rules.RuleTestCase (RuleId, Name, InputJson, ExpectedFires)
SELECT RuleId, N'22-year-old, symbol 24: refer', N'{"DRIVER_AGE":22,"VEHICLE_SYMBOL":24}', 1 FROM rules.BusinessRule WHERE RuleCode = 'R12';
EXEC rules.usp_RunTests;

/* 6. One company, one person: their own additions on top of the standard -------------------------- */
EXEC canon.usp_EnsureScope @Scope = N'COMPANY:ACME', @Name = N'Acme Mutual';
EXEC canon.usp_EnsureScope @Scope = N'PERSON:saba', @Name = N'Saba (working terms)', @ParentScope = N'COMPANY:ACME';
EXEC canon.usp_ProposeElement @Code = 'LOYALTY_TIER', @Name = N'Loyalty Tier', @Description = N'Acme loyalty program tier.',
     @Scope = N'COMPANY:ACME', @RequestedBy = N'Saba';
EXEC gov.usp_DecideAll @DecidedBy = N'Reviewer', @ObjectCodeLike = N'LOYALTY_TIER';
SELECT * FROM canon.vw_DataElement WHERE Scope = N'COMPANY:ACME';

-- Any extra attribute on anything, without changing a table
EXEC gov.usp_RequestChange @ObjectType = 'EXTENSION', @ChangeType = 'ADD', @ObjectCode = N'POLICY_NUMBER',
     @PayloadJson = N'{"object_type":"ELEMENT","object_code":"POLICY_NUMBER","name":"Data steward","value":"Underwriting operations"}',
     @RequestedBy = N'Saba';
EXEC gov.usp_DecideAll @DecidedBy = N'Reviewer', @ObjectType = 'EXTENSION';

/* 7. Collect from another database and add what is missing ------------------------------------------ */
EXEC intake.usp_ScanDatabase @SourceDatabase = 'SI2_SourceDemo', @SourceSystem = N'Guidewire', @StartedBy = N'Saba';
SELECT * FROM intake.vw_Candidate WHERE ScanRunId = 1 ORDER BY CandidateType, Status, SourceTable, SourceColumn;
EXEC intake.usp_ProposeMissing @ScanRunId = 1, @RequestedBy = N'Saba';
SELECT * FROM gov.vw_PendingChange WHERE ScanRunId = 1;
-- Reject the ones you do not want, e.g. technical columns:   EXEC gov.usp_DecideAll N'Reviewer', 0, N'Technical', 1, NULL, N'%ROWVERSION%';
EXEC gov.usp_DecideAll @DecidedBy = N'Reviewer', @ScanRunId = 1;
-- The next scan of the same source recognizes everything you approved (approved aliases, 0.99).

/* 8. Change and expire (never delete), and see the history -------------------------------------------- */
EXEC gov.usp_RequestChange 'ELEMENT', 'UPDATE', N'ROOF_AGE_BAND', N'{"code":"ROOF_AGE_BAND","owner":"Property product team"}', N'Saba';
EXEC gov.usp_RequestChange 'OPTION', 'EXPIRE', N'ROOF_SHAPE.MANSARD', N'{"picklist":"ROOF_SHAPE","code":"MANSARD","effective_to":"2027-12-31"}', N'Saba';
EXEC gov.usp_DecideAll @DecidedBy = N'Reviewer';
SELECT ElementCode, OwnerSME, Status, ValidFrom, ValidTo FROM canon.DataElement FOR SYSTEM_TIME ALL WHERE ElementCode = 'ROOF_AGE_BAND' ORDER BY ValidFrom;
SELECT RequestId, ObjectType, ChangeType, ObjectCode, RequestedBy, DecidedBy, Status, ResultMessage FROM gov.ChangeRequest ORDER BY RequestId DESC;
