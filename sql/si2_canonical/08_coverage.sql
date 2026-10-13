/* =====================================================================================================
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


-- New causes of loss and the words claims use for them (canonical CAUSE_OF_LOSS options and synonyms)

INSERT canon.PickListOption (PickListId, OptionCode, OptionName, Description, LobScope, StateScope, SortOrder, EffectiveFrom, CreatedBy)
SELECT p.PickListId, v.c, v.n, v.d, '*', '*', 900, '2020-01-01', N'SI2 coverage'
FROM (VALUES
    (N'FLOOD', N'Flood / surface water / storm surge', N'Cause of loss used by the SI² coverage check.'),
    (N'EARTHMV', N'Earth movement / earthquake', N'Cause of loss used by the SI² coverage check.'),
    (N'SINKHOLE', N'Sinkhole collapse', N'Cause of loss used by the SI² coverage check.'),
    (N'MOLD', N'Mold / fungi / rot', N'Cause of loss used by the SI² coverage check.'),
    (N'WEAR', N'Wear and tear / deterioration', N'Cause of loss used by the SI² coverage check.'),
    (N'SEWER', N'Water backup through sewer or drain', N'Cause of loss used by the SI² coverage check.'),
    (N'FREEZE', N'Freezing', N'Cause of loss used by the SI² coverage check.'),
    (N'COLLAPSE', N'Collapse', N'Cause of loss used by the SI² coverage check.'),
    (N'SMOKE', N'Smoke', N'Cause of loss used by the SI² coverage check.'),
    (N'EXPLOS', N'Explosion', N'Cause of loss used by the SI² coverage check.'),
    (N'NEGLECT', N'Neglect', N'Cause of loss used by the SI² coverage check.'),
    (N'INTENT', N'Intentional loss', N'Cause of loss used by the SI² coverage check.'),
    (N'POWER', N'Power failure off premises', N'Cause of loss used by the SI² coverage check.'),
    (N'VERMIN', N'Insects / rodents / vermin', N'Cause of loss used by the SI² coverage check.'),
    (N'ICESNOW', N'Weight of ice, snow or sleet', N'Cause of loss used by the SI² coverage check.'),
    (N'FALLOBJ', N'Falling objects', N'Cause of loss used by the SI² coverage check.'),
    (N'RACING', N'Racing / speed contest', N'Cause of loss used by the SI² coverage check.'),
    (N'RIDESHARE', N'Used for hire / ride-sharing', N'Cause of loss used by the SI² coverage check.'),
    (N'ANIMAL', N'Contact with an animal', N'Cause of loss used by the SI² coverage check.'),
    (N'GLASS', N'Glass breakage', N'Cause of loss used by the SI² coverage check.')
) v (c, n, d) JOIN canon.PickList p ON p.PickListCode = 'CAUSE_OF_LOSS' AND p.ScopeId = 1
WHERE NOT EXISTS (SELECT 1 FROM canon.PickListOption x WHERE x.PickListId = p.PickListId AND x.OptionCode = v.c AND x.ScopeId = 1);
GO

INSERT canon.Synonym (ObjectType, ObjectId, SynonymText, SynonymType, SourceSystem, CreatedBy)
SELECT 'OPTION', o.OptionId, v.w, 'BUSINESS', N'*', N'SI2 coverage'
FROM (VALUES
    (N'ANIMAL', N'animal'),
    (N'ANIMAL', N'deer'),
    (N'ANIMAL', N'hit a cow'),
    (N'ANIMAL', N'hit a deer'),
    (N'ANIMAL', N'hit an elk'),
    (N'ANIMAL', N'moose'),
    (N'ANIMAL', N'struck a deer'),
    (N'BRKDN', N'boiler broke down'),
    (N'BRKDN', N'compressor failed'),
    (N'BRKDN', N'electrical breakdown'),
    (N'BRKDN', N'engine failure'),
    (N'BRKDN', N'mechanical breakdown'),
    (N'BRKDN', N'transmission failed'),
    (N'COLL', N'accident with'),
    (N'COLL', N'collision'),
    (N'COLL', N'crashed'),
    (N'COLL', N'hit a pole'),
    (N'COLL', N'hit another car'),
    (N'COLL', N'ran into'),
    (N'COLL', N'rear ended'),
    (N'COLL', N'rear-ended'),
    (N'COLL', N'rolled over'),
    (N'COLL', N'sideswiped'),
    (N'COLL', N'single car accident'),
    (N'COLL', N't-boned'),
    (N'COLLAPSE', N'caved in'),
    (N'COLLAPSE', N'collapse'),
    (N'COLLAPSE', N'collapsed'),
    (N'COLLAPSE', N'roof caved'),
    (N'EARTHMV', N'earth movement'),
    (N'EARTHMV', N'earth sinking'),
    (N'EARTHMV', N'earthquake'),
    (N'EARTHMV', N'foundation shifted'),
    (N'EARTHMV', N'ground shifted'),
    (N'EARTHMV', N'landslide'),
    (N'EARTHMV', N'mudslide'),
    (N'EARTHMV', N'tremor'),
    (N'EMPDIS', N'cashier took money'),
    (N'EMPDIS', N'embezzled'),
    (N'EMPDIS', N'embezzlement'),
    (N'EMPDIS', N'employee stole'),
    (N'EMPDIS', N'employee theft'),
    (N'EXPLOS', N'blast'),
    (N'EXPLOS', N'exploded'),
    (N'EXPLOS', N'explosion'),
    (N'FALLOBJ', N'branch fell'),
    (N'FALLOBJ', N'fallen tree'),
    (N'FALLOBJ', N'falling object'),
    (N'FALLOBJ', N'fell on'),
    (N'FALLOBJ', N'limb fell'),
    (N'FALLOBJ', N'tree fell'),
    (N'FIRE', N'burned'),
    (N'FIRE', N'burnt'),
    (N'FIRE', N'caught fire'),
    (N'FIRE', N'fire'),
    (N'FIRE', N'flames'),
    (N'FIRE', N'grease fire'),
    (N'FIRE', N'kitchen fire'),
    (N'FIRE', N'wildfire'),
    (N'FLOOD', N'creek overflowed'),
    (N'FLOOD', N'flood'),
    (N'FLOOD', N'flooded'),
    (N'FLOOD', N'flooding'),
    (N'FLOOD', N'high water'),
    (N'FLOOD', N'inundation'),
    (N'FLOOD', N'mudflow'),
    (N'FLOOD', N'overflow of the river'),
    (N'FLOOD', N'rising water'),
    (N'FLOOD', N'river overflowed'),
    (N'FLOOD', N'standing water in the yard'),
    (N'FLOOD', N'storm surge'),
    (N'FLOOD', N'surface water'),
    (N'FLOOD', N'surge'),
    (N'FLOOD', N'tidal water'),
    (N'FLOOD', N'water came in from outside'),
    (N'FLOOD', N'water came in under the door'),
    (N'FLOOD', N'water came under the door'),
    (N'FLOOD', N'waves'),
    (N'FREEZE', N'freezing'),
    (N'FREEZE', N'frozen pipe'),
    (N'FREEZE', N'frozen pipes'),
    (N'FREEZE', N'ice in the pipes'),
    (N'FREEZE', N'pipe froze'),
    (N'FREEZE', N'pipes burst in the cold'),
    (N'FREEZE', N'pipes froze'),
    (N'GLASS', N'broken glass'),
    (N'GLASS', N'cracked windshield'),
    (N'GLASS', N'glass breakage'),
    (N'GLASS', N'window shattered'),
    (N'GLASS', N'windshield'),
    (N'HAIL', N'hail'),
    (N'HAIL', N'hail stones'),
    (N'HAIL', N'hailstorm'),
    (N'ICESNOW', N'heavy snow on the roof'),
    (N'ICESNOW', N'ice dam'),
    (N'ICESNOW', N'sleet'),
    (N'ICESNOW', N'snow load'),
    (N'ICESNOW', N'weight of ice'),
    (N'ICESNOW', N'weight of snow'),
    (N'INTENT', N'deliberately'),
    (N'INTENT', N'intentional'),
    (N'INTENT', N'on purpose'),
    (N'INTENT', N'set the fire herself'),
    (N'INTENT', N'set the fire himself'),
    (N'INTENT', N'staged'),
    (N'LTNG', N'lightning'),
    (N'LTNG', N'lightning strike'),
    (N'LTNG', N'struck by lightning'),
    (N'MOLD', N'dry rot'),
    (N'MOLD', N'fungi'),
    (N'MOLD', N'fungus'),
    (N'MOLD', N'mildew'),
    (N'MOLD', N'mold'),
    (N'MOLD', N'mould'),
    (N'MOLD', N'rot'),
    (N'MOLD', N'wet rot'),
    (N'NEGLECT', N'did not repair'),
    (N'NEGLECT', N'failed to protect the property'),
    (N'NEGLECT', N'left the window open for weeks'),
    (N'NEGLECT', N'neglect'),
    (N'NEGLECT', N'neglected'),
    (N'POWER', N'blackout'),
    (N'POWER', N'power failure'),
    (N'POWER', N'power outage'),
    (N'POWER', N'power went out'),
    (N'POWER', N'utility outage'),
    (N'RACING', N'drag race'),
    (N'RACING', N'racing'),
    (N'RACING', N'speed contest'),
    (N'RACING', N'street race'),
    (N'RACING', N'track day'),
    (N'RIDESHARE', N'carry persons or property for a fee'),
    (N'RIDESHARE', N'carrying passengers for a fee'),
    (N'RIDESHARE', N'delivering food'),
    (N'RIDESHARE', N'delivery driver'),
    (N'RIDESHARE', N'driving for doordash'),
    (N'RIDESHARE', N'for a fee'),
    (N'RIDESHARE', N'for hire'),
    (N'RIDESHARE', N'lyft'),
    (N'RIDESHARE', N'ride sharing'),
    (N'RIDESHARE', N'ride-share'),
    (N'RIDESHARE', N'ride-sharing'),
    (N'RIDESHARE', N'rideshare'),
    (N'RIDESHARE', N'uber'),
    (N'SEWER', N'back up through sewers'),
    (N'SEWER', N'backed up sewer'),
    (N'SEWER', N'backing up through sewers'),
    (N'SEWER', N'backs up through sewers'),
    (N'SEWER', N'backs up through sewers or drains'),
    (N'SEWER', N'backup through the drain'),
    (N'SEWER', N'drain backed up'),
    (N'SEWER', N'drain backup'),
    (N'SEWER', N'overflow from a sump pump'),
    (N'SEWER', N'overflows from a sump pump'),
    (N'SEWER', N'septic backed up'),
    (N'SEWER', N'sewer'),
    (N'SEWER', N'sewer backed up'),
    (N'SEWER', N'sewer backup'),
    (N'SEWER', N'sewer or drain backup'),
    (N'SEWER', N'sewers or drains'),
    (N'SEWER', N'sump overflow'),
    (N'SEWER', N'sump pump'),
    (N'SEWER', N'sump pump failed'),
    (N'SEWER', N'sump pump overflow'),
    (N'SEWER', N'toilet backed up'),
    (N'SEWER', N'water backing up'),
    (N'SINKHOLE', N'cavity under the foundation'),
    (N'SINKHOLE', N'ground collapsed under'),
    (N'SINKHOLE', N'sink hole'),
    (N'SINKHOLE', N'sinkhole'),
    (N'SLIP', N'fell on the floor'),
    (N'SLIP', N'fell on the stairs'),
    (N'SLIP', N'slip and fall'),
    (N'SLIP', N'slipped'),
    (N'SLIP', N'tripped'),
    (N'SMOKE', N'smoke'),
    (N'SMOKE', N'smoke damage'),
    (N'SMOKE', N'soot'),
    (N'SPRK', N'fire sprinkler discharged'),
    (N'SPRK', N'sprinkler head'),
    (N'SPRK', N'sprinkler leakage'),
    (N'THEFT', N'break-in'),
    (N'THEFT', N'broke in'),
    (N'THEFT', N'burglary'),
    (N'THEFT', N'missing jewelry'),
    (N'THEFT', N'robbed'),
    (N'THEFT', N'stole'),
    (N'THEFT', N'stolen'),
    (N'THEFT', N'taken from'),
    (N'THEFT', N'theft'),
    (N'VERMIN', N'bats'),
    (N'VERMIN', N'insects'),
    (N'VERMIN', N'mice'),
    (N'VERMIN', N'raccoons'),
    (N'VERMIN', N'rats'),
    (N'VERMIN', N'rodents'),
    (N'VERMIN', N'squirrels'),
    (N'VERMIN', N'termite'),
    (N'VERMIN', N'termites'),
    (N'VERMIN', N'vermin'),
    (N'VMM', N'graffiti'),
    (N'VMM', N'keyed the car'),
    (N'VMM', N'malicious mischief'),
    (N'VMM', N'smashed'),
    (N'VMM', N'vandalism'),
    (N'VMM', N'vandalized'),
    (N'WATER', N'ac line leaked'),
    (N'WATER', N'accidental discharge'),
    (N'WATER', N'burst pipe'),
    (N'WATER', N'dishwasher leaked'),
    (N'WATER', N'overflowed tub'),
    (N'WATER', N'pipe burst'),
    (N'WATER', N'plumbing leak'),
    (N'WATER', N'sudden leak'),
    (N'WATER', N'supply line'),
    (N'WATER', N'washing machine hose'),
    (N'WATER', N'water heater burst'),
    (N'WATER', N'water heater leaked'),
    (N'WEAR', N'corrosion'),
    (N'WEAR', N'cracking over time'),
    (N'WEAR', N'deteriorated'),
    (N'WEAR', N'deterioration'),
    (N'WEAR', N'gradual leak'),
    (N'WEAR', N'latent defect'),
    (N'WEAR', N'leaking for months'),
    (N'WEAR', N'long-term leak'),
    (N'WEAR', N'marring'),
    (N'WEAR', N'old age'),
    (N'WEAR', N'rust'),
    (N'WEAR', N'seepage'),
    (N'WEAR', N'settling'),
    (N'WEAR', N'slow leak'),
    (N'WEAR', N'wear and tear'),
    (N'WEAR', N'worn out'),
    (N'WIND', N'blew off'),
    (N'WIND', N'high winds'),
    (N'WIND', N'hurricane'),
    (N'WIND', N'shingles blown'),
    (N'WIND', N'tornado'),
    (N'WIND', N'tropical storm'),
    (N'WIND', N'wind'),
    (N'WIND', N'wind-driven'),
    (N'WIND', N'windstorm')
) v (c, w)
CROSS APPLY (SELECT TOP (1) o.OptionId FROM canon.PickListOption o JOIN canon.PickList p ON p.PickListId = o.PickListId WHERE p.PickListCode = 'CAUSE_OF_LOSS' AND o.OptionCode = v.c AND o.Status = 'ACTIVE' ORDER BY o.ScopeId) o
WHERE NOT EXISTS (SELECT 1 FROM canon.Synonym s WHERE s.ObjectType = 'OPTION' AND s.ObjectId = o.OptionId AND s.SynonymText = v.w);
GO

-- Synthetic forms (SI²'s own wording) and how SI² read them

INSERT cov.Form (FormNumber, Edition, Title, LobCode, Products, States, FormKind, Source, FormText, IsSynthetic, LoadedBy)
SELECT v.n, v.e, v.t, v.l, v.p, v.s, v.k, 'SYNTHETIC', v.x, 1, N'SI2 coverage'
FROM (VALUES
    (N'SIM HO 3', N'01 26', N'Homeowners Special Form (synthetic)', N'HO', N'HO3,HO5', CAST(NULL AS nvarchar(4000)), N'BASE', N'SECTION I - PROPERTY COVERAGES
Coverage A - Dwelling: the dwelling on the residence premises, including attached structures.
Coverage B - Other Structures: structures set apart from the dwelling by clear space.
Coverage C - Personal Property: property owned or used by an insured anywhere in the world.
Coverage D - Loss Of Use: additional living expense while the residence premises is not fit to live in.
PERILS INSURED AGAINST - COVERAGE A AND COVERAGE B
We insure against risk of direct physical loss to property described in Coverages A and B unless the loss is excluded in this policy.
PERILS INSURED AGAINST - COVERAGE C
We insure for direct physical loss to property described in Coverage C caused by the following perils only, unless the loss is excluded.
Fire or lightning.
Windstorm or hail; interior damage only if the wind or hail first makes an opening in the roof or a wall.
Explosion. Smoke, meaning sudden and accidental damage from smoke.
Vandalism or malicious mischief. Theft, including attempted theft.
Falling objects. Weight of ice, snow or sleet.
Accidental discharge or overflow of water from a plumbing, heating or air conditioning system or household appliance, such as a burst pipe or a washing machine hose.
Freezing of a plumbing system, if you maintained heat in the building.
SECTION I - EXCLUSIONS
We do not insure for loss caused directly or indirectly by any of the following, regardless of any other cause contributing to the loss.
Flood, surface water, waves, tidal water, storm surge, overflow of a body of water, or spray from any of these, whether or not driven by wind.
Water which backs up through sewers or drains or overflows from a sump pump.
Earth movement, including earthquake, landslide, mudflow, earth sinking, rising or shifting, and sinkhole.
Wear and tear, marring, deterioration, mechanical breakdown, latent defect, rust, corrosion, settling, cracking or seepage of water over a period of weeks or months.
Mold, fungus or wet or dry rot, unless hidden within the walls or ceilings and resulting from an accidental discharge of water covered by this policy.
Birds, rodents, insects, termites or other vermin.
Neglect, meaning failure to use all reasonable means to protect covered property at and after the time of loss.
Intentional loss, meaning any loss arising out of an act committed by or at the direction of an insured with the intent to cause a loss.
Power failure, meaning the failure of power or other utility service if the failure takes place off the residence premises.
War, nuclear hazard, and ordinance or law.
SECTION I - DEDUCTIBLE
Unless otherwise noted in this policy, we pay only the part of the loss over the deductible stated in the Declarations.
SECTION I - LIMITS OF LIABILITY
We will not pay more than the limit of liability shown in the Declarations for each coverage.
SECTION I - CONDITIONS
Duties after loss: give prompt notice to us, protect the property from further damage, and show the damaged property.'),
    (N'SIM HO 4', N'01 26', N'Renters Broad Form (synthetic)', N'HO', N'HO4', CAST(NULL AS nvarchar(4000)), N'BASE', N'SECTION I - PROPERTY COVERAGES
Coverage C - Personal Property: property owned or used by an insured anywhere in the world.
Coverage D - Loss Of Use: additional living expense while the rented premises is not fit to live in.
PERILS INSURED AGAINST - COVERAGE C
We insure for direct physical loss to property described in Coverage C caused by the following perils only.
Fire or lightning. Windstorm or hail. Explosion. Smoke. Vandalism or malicious mischief. Theft. Falling objects.
Weight of ice, snow or sleet. Accidental discharge or overflow of water from a plumbing system or household appliance, such as a burst pipe.
SECTION I - EXCLUSIONS
We do not insure for loss caused by flood, surface water, storm surge or waves; water backing up through sewers or drains; earth movement including earthquake and sinkhole; wear and tear or deterioration; mold, fungus or rot; vermin; neglect; intentional loss; or power failure off the premises.
SECTION I - DEDUCTIBLE
We pay only the part of the loss over the deductible stated in the Declarations.'),
    (N'SIM HO 6', N'01 26', N'Unit-Owners Form (synthetic)', N'HO', N'HO6', CAST(NULL AS nvarchar(4000)), N'BASE', N'SECTION I - PROPERTY COVERAGES
Coverage A - Dwelling: the alterations, fixtures and improvements that are part of the unit.
Coverage C - Personal Property: property owned or used by an insured.
PERILS INSURED AGAINST - COVERAGE A
We insure against risk of direct physical loss to property described in Coverage A unless the loss is excluded.
PERILS INSURED AGAINST - COVERAGE C
We insure for direct physical loss to Coverage C property caused by fire or lightning, windstorm or hail, explosion, smoke, vandalism, theft, falling objects, weight of ice or snow, and accidental discharge of water such as a burst pipe or appliance leak.
SECTION I - EXCLUSIONS
We do not insure for loss caused by flood, storm surge or surface water; sewer or drain backup; earthquake or other earth movement; sinkhole; wear and tear, deterioration or seepage over weeks or months; mold or rot; vermin; neglect; intentional loss; or power failure.
SECTION I - DEDUCTIBLE
We pay only the part of the loss over the deductible stated in the Declarations.'),
    (N'SIM DP 3', N'01 26', N'Dwelling Property Special Form (synthetic)', N'HO', N'DP3', CAST(NULL AS nvarchar(4000)), N'BASE', N'COVERAGES
Coverage A - Dwelling: the dwelling at the described location, rented to others.
Coverage C - Personal Property: landlord''s household property at the dwelling.
PERILS INSURED AGAINST - COVERAGE A
We insure against risk of direct physical loss to Coverage A property unless the loss is excluded.
PERILS INSURED AGAINST - COVERAGE C
We insure Coverage C property for fire or lightning, windstorm or hail, explosion, smoke, vandalism, theft and burst pipe or accidental discharge of water.
GENERAL EXCLUSIONS
We do not insure for loss caused by flood or storm surge; sewer backup; earth movement or earthquake; sinkhole; wear and tear, deterioration or settling; mold or rot; vermin; neglect; intentional loss; or vandalism and theft if the dwelling was vacant for more than 60 days.
DEDUCTIBLE
We pay only the part of the loss over the deductible stated in the Declarations.'),
    (N'SIM HO 04 95', N'01 26', N'Water Back-Up and Sump Discharge (synthetic)', N'HO', N'HO3,HO5,HO6,HO4', CAST(NULL AS nvarchar(4000)), N'ENDORSEMENT', N'ADDITIONAL COVERAGE - WATER BACK-UP
We will pay for direct physical loss caused by water which backs up through sewers or drains or overflows from a sump pump, up to $10,000 per loss.
The Water Back-Up exclusion in Section I Exclusions does not apply to the coverage given by this endorsement.'),
    (N'SIM HO 23 FL', N'01 26', N'Sinkhole Loss Coverage - Florida (synthetic)', N'HO', N'HO3,HO5,DP3', N'FL', N'ENDORSEMENT', N'ADDITIONAL COVERAGE - SINKHOLE LOSS
We will pay for direct physical loss to Coverage A property caused by sinkhole activity, when a sinkhole is verified by a professional engineer.'),
    (N'SIM HO 32 FL', N'01 26', N'Hurricane Percentage Deductible (synthetic)', N'HO', N'HO3,HO5,HO6,DP3', CAST(NULL AS nvarchar(4000)), N'ENDORSEMENT', N'HURRICANE DEDUCTIBLE
For loss caused by windstorm during a hurricane, the deductible is 2% of the Coverage A limit shown in the Declarations.'),
    (N'SIM HO 04 26', N'01 26', N'Limited Fungi, Wet or Dry Rot Coverage (synthetic)', N'HO', N'HO3,HO5,HO6', CAST(NULL AS nvarchar(4000)), N'ENDORSEMENT', N'ADDITIONAL COVERAGE - FUNGI, WET OR DRY ROT
We will pay for loss caused by mold, fungi, wet rot or dry rot that results from a covered peril, up to $10,000 per policy term.'),
    (N'SIM HO 04 54', N'01 26', N'Earthquake (synthetic)', N'HO', N'HO3,HO5,HO6', CAST(NULL AS nvarchar(4000)), N'ENDORSEMENT', N'ADDITIONAL COVERAGE - EARTHQUAKE
We will pay for direct physical loss caused by earthquake, including land shock waves or tremors.'),
    (N'SIM HO 04 94', N'01 26', N'Windstorm or Hail Exclusion (synthetic)', N'HO', N'HO3,HO5,HO6,DP3', CAST(NULL AS nvarchar(4000)), N'ENDORSEMENT', N'WINDSTORM OR HAIL EXCLUSION
We do not insure for loss caused by windstorm or hail, including hurricane and tornado; this risk is insured by the state wind pool.'),
    (N'SIM PP 00 01', N'01 26', N'Personal Auto Policy (synthetic)', N'PA', N'PA_STD', CAST(NULL AS nvarchar(4000)), N'BASE', N'PART D - COVERAGE FOR DAMAGE TO YOUR AUTO
INSURING AGREEMENT - COLLISION COVERAGE
We will pay for direct and accidental loss to your covered auto caused by collision with another object or by overturn, if Collision Coverage is shown in the Declarations.
INSURING AGREEMENT - OTHER THAN COLLISION COVERAGE
We will pay for direct and accidental loss to your covered auto not caused by collision, if Other Than Collision Coverage is shown in the Declarations.
Loss caused by the following is Other Than Collision: missiles or falling objects; fire; theft; explosion or earthquake; windstorm; hail, water or flood; malicious mischief or vandalism; riot; contact with a bird or animal; glass breakage.
PART D - EXCLUSIONS
We will not pay for loss to your covered auto while it is being used to carry persons or property for a fee, including ride-sharing and delivery, unless the ride-share endorsement is attached.
We will not pay for loss due to and confined to wear and tear, freezing, mechanical or electrical breakdown or failure, or road damage to tires.
We will not pay for loss to your covered auto while it is used in any race or speed contest.
We will not pay for loss caused intentionally by or at the direction of an insured.
PART D - LIMIT OF LIABILITY
Our limit is the lesser of the actual cash value of the stolen or damaged property or the amount necessary to repair or replace it, minus the deductible shown in the Declarations.
PART E - DUTIES AFTER AN ACCIDENT OR LOSS
We must be notified promptly of how, when and where the accident or loss happened.'),
    (N'SIM PP 03 RS', N'01 26', N'Ride-Share Coverage (synthetic)', N'PA', N'PA_STD', CAST(NULL AS nvarchar(4000)), N'ENDORSEMENT', N'ADDITIONAL COVERAGE - RIDE-SHARE
The exclusion for carrying persons for a fee does not apply while you are logged in to a ride-sharing or delivery platform and waiting for or carrying a passenger or delivery.'),
    (N'SIM BP 00 03', N'01 26', N'Businessowners Coverage Form (synthetic)', N'BP', N'BOP', CAST(NULL AS nvarchar(4000)), N'BASE', N'SECTION I - PROPERTY - COVERAGE
We will pay for direct physical loss of or damage to Building and Business Personal Property at the premises caused by or resulting from any Covered Cause of Loss.
COVERED CAUSES OF LOSS
Risks of direct physical loss unless the loss is excluded or limited in this policy.
SECTION I - EXCLUSIONS
We will not pay for loss caused by flood, surface water, storm surge or waves; earth movement or earthquake; sinkhole; wear and tear, rust, corrosion or deterioration; mold or fungi; insects, rodents or vermin; power failure off the premises; mechanical breakdown; dishonest acts by you or your employees, including employee theft and embezzlement; or neglect.
SECTION I - LIMITS OF INSURANCE
The most we will pay for loss in any one occurrence is the applicable Limit of Insurance shown in the Declarations.
SECTION I - DEDUCTIBLES
We will not pay for loss in any one occurrence until the amount of loss exceeds the Deductible shown in the Declarations.'),
    (N'SIM BP 04 ED', N'01 26', N'Employee Dishonesty (synthetic)', N'BP', N'BOP', CAST(NULL AS nvarchar(4000)), N'ENDORSEMENT', N'ADDITIONAL COVERAGE - EMPLOYEE DISHONESTY
We will pay for loss of Business Personal Property and money resulting from employee theft or embezzlement by an employee, up to $25,000 per occurrence.'),
    (N'SIS CP 10 30', N'01 26', N'Commercial Property Special Causes of Loss (synthetic)', N'CP', N'CP', CAST(NULL AS nvarchar(4000)), N'BASE', N'COVERED CAUSES OF LOSS - BUILDING AND BUSINESS PERSONAL PROPERTY
Covered Causes of Loss means risks of direct physical loss unless the loss is excluded or limited in this form.
EXCLUSIONS
We will not pay for loss caused by flood, surface water, storm surge or waves; earth movement or earthquake; water that backs up through sewers or drains; wear and tear, rust, corrosion, deterioration or settling; mold or fungi; vermin; mechanical breakdown; power failure off the premises; neglect; intentional loss; or collapse, except as provided in the Additional Coverage for Collapse.
ADDITIONAL COVERAGE - COLLAPSE
We will pay for direct physical loss caused by abrupt collapse of a building caused by decay hidden from view or the weight of ice, snow or rain.
DEDUCTIBLE
We will not pay for loss in any one occurrence until the amount of loss exceeds the Deductible shown in the Declarations.'),
    (N'SIS CP 10 65', N'01 26', N'Flood Coverage Endorsement (synthetic)', N'CP', N'CP', CAST(NULL AS nvarchar(4000)), N'ENDORSEMENT', N'ADDITIONAL COVERAGE - FLOOD
We will pay for direct physical loss caused by flood, surface water or storm surge, up to $1,000,000 per occurrence.')
) v (n, e, t, l, p, s, k, x)
WHERE NOT EXISTS (SELECT 1 FROM cov.Form f WHERE f.FormNumber = v.n AND f.Edition = v.e);
GO

INSERT cov.FormSection (FormId, Seq, Heading, SectionType, Coverages, OpenPerils, CauseCodes, SectionText)
SELECT f.FormId, v.s, v.h, v.t, v.c, v.o, v.cc, v.x
FROM (VALUES
    (N'SIM HO 3', N'01 26', 1, N'SECTION I - PROPERTY COVERAGES', N'COVERED', N'DWELL,OTHSTR,PERSPROP,LOU', 0, CAST(NULL AS nvarchar(4000)), N'Coverage A - Dwelling: the dwelling on the residence premises, including attached structures. Coverage B - Other Structures: structures set apart from the dwelling by clear space. Coverage C - Personal Property: property owned or used by an insured anywhere in the world. Coverage D - Loss Of Use: additional living expense while the residence premises is not fit to live in.'),
    (N'SIM HO 3', N'01 26', 2, N'PERILS INSURED AGAINST - COVERAGE A AND COVERAGE B', N'COVERED', N'DWELL,OTHSTR', 1, CAST(NULL AS nvarchar(4000)), N'We insure against risk of direct physical loss to property described in Coverages A and B unless the loss is excluded in this policy.'),
    (N'SIM HO 3', N'01 26', 3, N'PERILS INSURED AGAINST - COVERAGE C', N'COVERED', N'PERSPROP', 0, N'EXPLOS,FIRE,FREEZE,HAIL,ICESNOW,LTNG,SMOKE,THEFT,VMM,WATER,WIND', N'We insure for direct physical loss to property described in Coverage C caused by the following perils only, unless the loss is excluded. Fire or lightning. Windstorm or hail interior damage only if the wind or hail first makes an opening in the roof or a wall. Explosion. Smoke, meaning sudden and accidental damage from smoke. Vandalism or malicious mischief. Theft, including attempted theft. Falling objects. Weight of ice, snow or sleet. Accidental discharge or overflow of water from a plumbing, heating or air conditioning system or household appliance, such as a burst pipe or a washing machine hose. Freezing of a plumbing system, if you maintained heat in the building.'),
    (N'SIM HO 3', N'01 26', 4, N'SECTION I - EXCLUSIONS', N'EXCLUSION', CAST(NULL AS nvarchar(4000)), 0, N'BRKDN,EARTHMV,FLOOD,INTENT,MOLD,NEGLECT,POWER,SEWER,SINKHOLE,VERMIN,WEAR', N'We do not insure for loss caused directly or indirectly by any of the following, regardless of any other cause contributing to the loss. Flood, surface water, waves, tidal water, storm surge, overflow of a body of water, or spray from any of these, whether or not driven by wind. Water which backs up through sewers or drains or overflows from a sump pump. Earth movement, including earthquake, landslide, mudflow, earth sinking, rising or shifting, and sinkhole. Wear and tear, marring, deterioration, mechanical breakdown, latent defect, rust, corrosion, settling, cracking or seepage of water over a period of weeks or months. Mold, fungus or wet or dry rot, unless hidden within the walls or ceilings and resulting from an accidental discharge of water covered by this policy. Birds, rodents, insects, termites or other vermin. Neglect, meaning failure to use all reasonable means to protect covered property at and after the time of loss. Intentional loss, meaning any loss arising out of an act committed by or at the direction of an insured with the intent to cause a loss. Power failure, meaning the failure of power or other utility service if the failure takes place off the residence premises. War, nuclear hazard, and ordinance or law.'),
    (N'SIM HO 3', N'01 26', 5, N'SECTION I - DEDUCTIBLE', N'DEDUCTIBLE', CAST(NULL AS nvarchar(4000)), 0, CAST(NULL AS nvarchar(4000)), N'Unless otherwise noted in this policy, we pay only the part of the loss over the deductible stated in the Declarations.'),
    (N'SIM HO 3', N'01 26', 6, N'SECTION I - LIMITS OF LIABILITY', N'LIMIT', CAST(NULL AS nvarchar(4000)), 0, CAST(NULL AS nvarchar(4000)), N'We will not pay more than the limit of liability shown in the Declarations for each coverage.'),
    (N'SIM HO 3', N'01 26', 7, N'SECTION I - CONDITIONS', N'CONDITION', CAST(NULL AS nvarchar(4000)), 0, CAST(NULL AS nvarchar(4000)), N'Duties after loss: give prompt notice to us, protect the property from further damage, and show the damaged property.'),
    (N'SIM HO 4', N'01 26', 1, N'SECTION I - PROPERTY COVERAGES', N'COVERED', N'PERSPROP,LOU', 0, CAST(NULL AS nvarchar(4000)), N'Coverage C - Personal Property: property owned or used by an insured anywhere in the world. Coverage D - Loss Of Use: additional living expense while the rented premises is not fit to live in.'),
    (N'SIM HO 4', N'01 26', 2, N'PERILS INSURED AGAINST - COVERAGE C', N'COVERED', N'PERSPROP', 0, N'EXPLOS,FIRE,HAIL,ICESNOW,LTNG,SMOKE,THEFT,VMM,WATER,WIND', N'We insure for direct physical loss to property described in Coverage C caused by the following perils only. Fire or lightning. Windstorm or hail. Explosion. Smoke. Vandalism or malicious mischief. Theft. Falling objects. Weight of ice, snow or sleet. Accidental discharge or overflow of water from a plumbing system or household appliance, such as a burst pipe.'),
    (N'SIM HO 4', N'01 26', 3, N'SECTION I - EXCLUSIONS', N'EXCLUSION', CAST(NULL AS nvarchar(4000)), 0, N'EARTHMV,FLOOD,INTENT,MOLD,NEGLECT,POWER,SEWER,SINKHOLE,VERMIN,WEAR', N'We do not insure for loss caused by flood, surface water, storm surge or waves water backing up through sewers or drains earth movement including earthquake and sinkhole wear and tear or deterioration mold, fungus or rot vermin neglect intentional loss or power failure off the premises.'),
    (N'SIM HO 4', N'01 26', 4, N'SECTION I - DEDUCTIBLE', N'DEDUCTIBLE', CAST(NULL AS nvarchar(4000)), 0, CAST(NULL AS nvarchar(4000)), N'We pay only the part of the loss over the deductible stated in the Declarations.'),
    (N'SIM HO 6', N'01 26', 1, N'SECTION I - PROPERTY COVERAGES', N'COVERED', N'DWELL,PERSPROP', 0, CAST(NULL AS nvarchar(4000)), N'Coverage A - Dwelling: the alterations, fixtures and improvements that are part of the unit. Coverage C - Personal Property: property owned or used by an insured.'),
    (N'SIM HO 6', N'01 26', 2, N'PERILS INSURED AGAINST - COVERAGE A', N'COVERED', N'DWELL', 1, CAST(NULL AS nvarchar(4000)), N'We insure against risk of direct physical loss to property described in Coverage A unless the loss is excluded.'),
    (N'SIM HO 6', N'01 26', 3, N'PERILS INSURED AGAINST - COVERAGE C', N'COVERED', N'PERSPROP', 0, N'EXPLOS,FIRE,HAIL,ICESNOW,LTNG,SMOKE,THEFT,VMM,WATER,WIND', N'We insure for direct physical loss to Coverage C property caused by fire or lightning, windstorm or hail, explosion, smoke, vandalism, theft, falling objects, weight of ice or snow, and accidental discharge of water such as a burst pipe or appliance leak.'),
    (N'SIM HO 6', N'01 26', 4, N'SECTION I - EXCLUSIONS', N'EXCLUSION', CAST(NULL AS nvarchar(4000)), 0, N'EARTHMV,FLOOD,INTENT,MOLD,NEGLECT,POWER,SEWER,SINKHOLE,VERMIN,WEAR', N'We do not insure for loss caused by flood, storm surge or surface water sewer or drain backup earthquake or other earth movement sinkhole wear and tear, deterioration or seepage over weeks or months mold or rot vermin neglect intentional loss or power failure.'),
    (N'SIM HO 6', N'01 26', 5, N'SECTION I - DEDUCTIBLE', N'DEDUCTIBLE', CAST(NULL AS nvarchar(4000)), 0, CAST(NULL AS nvarchar(4000)), N'We pay only the part of the loss over the deductible stated in the Declarations.'),
    (N'SIM DP 3', N'01 26', 1, N'COVERAGES', N'COVERED', N'DWELL,PERSPROP', 0, CAST(NULL AS nvarchar(4000)), N'Coverage A - Dwelling: the dwelling at the described location, rented to others. Coverage C - Personal Property: landlord''s household property at the dwelling.'),
    (N'SIM DP 3', N'01 26', 2, N'PERILS INSURED AGAINST - COVERAGE A', N'COVERED', N'DWELL', 1, CAST(NULL AS nvarchar(4000)), N'We insure against risk of direct physical loss to Coverage A property unless the loss is excluded.'),
    (N'SIM DP 3', N'01 26', 3, N'PERILS INSURED AGAINST - COVERAGE C', N'COVERED', N'PERSPROP', 0, N'EXPLOS,FIRE,HAIL,LTNG,SMOKE,THEFT,VMM,WATER,WIND', N'We insure Coverage C property for fire or lightning, windstorm or hail, explosion, smoke, vandalism, theft and burst pipe or accidental discharge of water.'),
    (N'SIM DP 3', N'01 26', 4, N'GENERAL EXCLUSIONS', N'EXCLUSION', CAST(NULL AS nvarchar(4000)), 0, N'EARTHMV,FLOOD,INTENT,MOLD,NEGLECT,SEWER,SINKHOLE,THEFT,VERMIN,VMM,WEAR', N'We do not insure for loss caused by flood or storm surge sewer backup earth movement or earthquake sinkhole wear and tear, deterioration or settling mold or rot vermin neglect intentional loss or vandalism and theft if the dwelling was vacant for more than 60 days.'),
    (N'SIM DP 3', N'01 26', 5, N'DEDUCTIBLE', N'DEDUCTIBLE', CAST(NULL AS nvarchar(4000)), 0, CAST(NULL AS nvarchar(4000)), N'We pay only the part of the loss over the deductible stated in the Declarations.'),
    (N'SIM HO 04 95', N'01 26', 1, N'ADDITIONAL COVERAGE - WATER BACK-UP', N'ADDS', CAST(NULL AS nvarchar(4000)), 0, N'SEWER', N'We will pay for direct physical loss caused by water which backs up through sewers or drains or overflows from a sump pump, up to $10,000 per loss. The Water Back-Up exclusion in Section I Exclusions does not apply to the coverage given by this endorsement.'),
    (N'SIM HO 23 FL', N'01 26', 1, N'ADDITIONAL COVERAGE - SINKHOLE LOSS', N'ADDS', CAST(NULL AS nvarchar(4000)), 0, N'SINKHOLE', N'We will pay for direct physical loss to Coverage A property caused by sinkhole activity, when a sinkhole is verified by a professional engineer.'),
    (N'SIM HO 32 FL', N'01 26', 1, N'HURRICANE DEDUCTIBLE', N'DEDUCTIBLE', CAST(NULL AS nvarchar(4000)), 0, N'WIND', N'For loss caused by windstorm during a hurricane, the deductible is 2% of the Coverage A limit shown in the Declarations.'),
    (N'SIM HO 04 26', N'01 26', 1, N'ADDITIONAL COVERAGE - FUNGI, WET OR DRY ROT', N'ADDS', CAST(NULL AS nvarchar(4000)), 0, N'MOLD', N'We will pay for loss caused by mold, fungi, wet rot or dry rot that results from a covered peril, up to $10,000 per policy term.'),
    (N'SIM HO 04 54', N'01 26', 1, N'ADDITIONAL COVERAGE - EARTHQUAKE', N'ADDS', CAST(NULL AS nvarchar(4000)), 0, N'EARTHMV,FLOOD', N'We will pay for direct physical loss caused by earthquake, including land shock waves or tremors.'),
    (N'SIM HO 04 94', N'01 26', 1, N'WINDSTORM OR HAIL EXCLUSION', N'EXCLUSION', CAST(NULL AS nvarchar(4000)), 0, N'HAIL,WIND', N'We do not insure for loss caused by windstorm or hail, including hurricane and tornado this risk is insured by the state wind pool.'),
    (N'SIM PP 00 01', N'01 26', 1, N'PART D - COVERAGE FOR DAMAGE TO YOUR AUTO', N'COVERED', CAST(NULL AS nvarchar(4000)), 0, CAST(NULL AS nvarchar(4000)), N'PART D - COVERAGE FOR DAMAGE TO YOUR AUTO'),
    (N'SIM PP 00 01', N'01 26', 2, N'INSURING AGREEMENT - COLLISION COVERAGE', N'COVERED', N'COLL', 0, N'COLL', N'We will pay for direct and accidental loss to your covered auto caused by collision with another object or by overturn, if Collision Coverage is shown in the Declarations.'),
    (N'SIM PP 00 01', N'01 26', 3, N'INSURING AGREEMENT - OTHER THAN COLLISION COVERAGE', N'COVERED', N'COMP', 0, N'ANIMAL,COLL,EARTHMV,EXPLOS,FIRE,FLOOD,GLASS,HAIL,THEFT,VMM,WIND', N'We will pay for direct and accidental loss to your covered auto not caused by collision, if Other Than Collision Coverage is shown in the Declarations. Loss caused by the following is Other Than Collision: missiles or falling objects fire theft explosion or earthquake windstorm hail, water or flood malicious mischief or vandalism riot contact with a bird or animal glass breakage.'),
    (N'SIM PP 00 01', N'01 26', 4, N'PART D - EXCLUSIONS', N'EXCLUSION', CAST(NULL AS nvarchar(4000)), 0, N'BRKDN,FREEZE,RACING,RIDESHARE,WEAR', N'We will not pay for loss to your covered auto while it is being used to carry persons or property for a fee, including ride-sharing and delivery, unless the ride-share endorsement is attached. We will not pay for loss due to and confined to wear and tear, freezing, mechanical or electrical breakdown or failure, or road damage to tires. We will not pay for loss to your covered auto while it is used in any race or speed contest. We will not pay for loss caused intentionally by or at the direction of an insured.'),
    (N'SIM PP 00 01', N'01 26', 5, N'PART D - LIMIT OF LIABILITY', N'LIMIT', CAST(NULL AS nvarchar(4000)), 0, N'THEFT', N'Our limit is the lesser of the actual cash value of the stolen or damaged property or the amount necessary to repair or replace it, minus the deductible shown in the Declarations.'),
    (N'SIM PP 00 01', N'01 26', 6, N'PART E - DUTIES AFTER AN ACCIDENT OR LOSS', N'CONDITION', CAST(NULL AS nvarchar(4000)), 0, CAST(NULL AS nvarchar(4000)), N'We must be notified promptly of how, when and where the accident or loss happened.'),
    (N'SIM PP 03 RS', N'01 26', 1, N'ADDITIONAL COVERAGE - RIDE-SHARE', N'ADDS', CAST(NULL AS nvarchar(4000)), 0, N'RIDESHARE', N'The exclusion for carrying persons for a fee does not apply while you are logged in to a ride-sharing or delivery platform and waiting for or carrying a passenger or delivery.'),
    (N'SIM BP 00 03', N'01 26', 1, N'SECTION I - PROPERTY - COVERAGE', N'COVERED', N'PERSPROP,BPP,BLDG', 0, CAST(NULL AS nvarchar(4000)), N'We will pay for direct physical loss of or damage to Building and Business Personal Property at the premises caused by or resulting from any Covered Cause of Loss.'),
    (N'SIM BP 00 03', N'01 26', 2, N'COVERED CAUSES OF LOSS', N'COVERED', CAST(NULL AS nvarchar(4000)), 1, CAST(NULL AS nvarchar(4000)), N'Risks of direct physical loss unless the loss is excluded or limited in this policy.'),
    (N'SIM BP 00 03', N'01 26', 3, N'SECTION I - EXCLUSIONS', N'EXCLUSION', CAST(NULL AS nvarchar(4000)), 0, N'BRKDN,EARTHMV,EMPDIS,FLOOD,MOLD,NEGLECT,POWER,SINKHOLE,VERMIN,WEAR', N'We will not pay for loss caused by flood, surface water, storm surge or waves earth movement or earthquake sinkhole wear and tear, rust, corrosion or deterioration mold or fungi insects, rodents or vermin power failure off the premises mechanical breakdown dishonest acts by you or your employees, including employee theft and embezzlement or neglect.'),
    (N'SIM BP 00 03', N'01 26', 4, N'SECTION I - LIMITS OF INSURANCE', N'LIMIT', CAST(NULL AS nvarchar(4000)), 0, CAST(NULL AS nvarchar(4000)), N'The most we will pay for loss in any one occurrence is the applicable Limit of Insurance shown in the Declarations.'),
    (N'SIM BP 00 03', N'01 26', 5, N'SECTION I - DEDUCTIBLES', N'DEDUCTIBLE', CAST(NULL AS nvarchar(4000)), 0, CAST(NULL AS nvarchar(4000)), N'We will not pay for loss in any one occurrence until the amount of loss exceeds the Deductible shown in the Declarations.'),
    (N'SIM BP 04 ED', N'01 26', 1, N'ADDITIONAL COVERAGE - EMPLOYEE DISHONESTY', N'ADDS', CAST(NULL AS nvarchar(4000)), 0, N'EMPDIS', N'We will pay for loss of Business Personal Property and money resulting from employee theft or embezzlement by an employee, up to $25,000 per occurrence.'),
    (N'SIS CP 10 30', N'01 26', 1, N'COVERED CAUSES OF LOSS - BUILDING AND BUSINESS PERSONAL PROPERTY', N'COVERED', N'PERSPROP,BPP,BLDG', 1, CAST(NULL AS nvarchar(4000)), N'Covered Causes of Loss means risks of direct physical loss unless the loss is excluded or limited in this form.'),
    (N'SIS CP 10 30', N'01 26', 2, N'EXCLUSIONS', N'EXCLUSION', CAST(NULL AS nvarchar(4000)), 0, N'BRKDN,COLLAPSE,EARTHMV,FLOOD,INTENT,MOLD,NEGLECT,POWER,SEWER,VERMIN,WEAR', N'We will not pay for loss caused by flood, surface water, storm surge or waves earth movement or earthquake water that backs up through sewers or drains wear and tear, rust, corrosion, deterioration or settling mold or fungi vermin mechanical breakdown power failure off the premises neglect intentional loss or collapse, except as provided in the Additional Coverage for Collapse.'),
    (N'SIS CP 10 30', N'01 26', 3, N'ADDITIONAL COVERAGE - COLLAPSE', N'ADDS', CAST(NULL AS nvarchar(4000)), 0, N'COLLAPSE,ICESNOW', N'We will pay for direct physical loss caused by abrupt collapse of a building caused by decay hidden from view or the weight of ice, snow or rain.'),
    (N'SIS CP 10 30', N'01 26', 4, N'DEDUCTIBLE', N'DEDUCTIBLE', CAST(NULL AS nvarchar(4000)), 0, CAST(NULL AS nvarchar(4000)), N'We will not pay for loss in any one occurrence until the amount of loss exceeds the Deductible shown in the Declarations.'),
    (N'SIS CP 10 65', N'01 26', 1, N'ADDITIONAL COVERAGE - FLOOD', N'ADDS', CAST(NULL AS nvarchar(4000)), 0, N'FLOOD', N'We will pay for direct physical loss caused by flood, surface water or storm surge, up to $1,000,000 per occurrence.')
) v (n, e, s, h, t, c, o, cc, x) JOIN cov.Form f ON f.FormNumber = v.n AND f.Edition = v.e
WHERE NOT EXISTS (SELECT 1 FROM cov.FormSection z WHERE z.FormId = f.FormId AND z.Seq = v.s);
GO

-- Synthetic policies, coverages and attached forms

INSERT cov.Policy (PolicyNumber, ProductCode, LobCode, StateCode, InsuredName, EffectiveDate, ExpirationDate, IsSynthetic)
SELECT v.n, v.p, v.l, v.s, v.i, v.e, v.x, 1
FROM (VALUES
    (N'SIM-HO3-24001', N'HO3', N'HO', N'FL', N'Aisha Johnson', N'2026-04-26', N'2027-04-26'),
    (N'SIM-HO3-24002', N'HO3', N'HO', N'TX', N'Carlos Nguyen', N'2025-02-03', N'2026-02-03'),
    (N'SIM-HO5-24003', N'HO5', N'HO', N'FL', N'Carlos Garcia', N'2025-01-21', N'2026-01-21'),
    (N'SIM-HO4-24004', N'HO4', N'HO', N'NC', N'Carlos Johnson', N'2025-03-03', N'2026-03-03'),
    (N'SIM-HO6-24005', N'HO6', N'HO', N'NC', N'Carlos Garcia', N'2025-02-01', N'2026-02-01'),
    (N'SIM-DP3-24006', N'DP3', N'HO', N'NC', N'Priya Silva', N'2026-01-12', N'2027-01-12'),
    (N'SIM-PA-24007', N'PA_STD', N'PA', N'FL', N'Omar Garcia', N'2025-09-27', N'2026-09-27'),
    (N'SIM-PA-24008', N'PA_STD', N'PA', N'TX', N'Grace Nguyen', N'2025-04-08', N'2026-04-08'),
    (N'SIM-BOP-24009', N'BOP', N'BP', N'GA', N'Elena Patel', N'2025-07-17', N'2026-07-17'),
    (N'SIS-CP-24010', N'CP', N'CP', N'TX', N'Carlos Patel', N'2026-02-13', N'2027-02-13'),
    (N'SIM-HO3-24011', N'HO3', N'HO', N'NC', N'David Patel', N'2025-07-27', N'2026-07-27'),
    (N'SIM-HO3-24012', N'HO3', N'HO', N'TX', N'Sofia Smith', N'2025-05-03', N'2026-05-03'),
    (N'SIM-HO5-24013', N'HO5', N'HO', N'NC', N'Robert Silva', N'2026-06-09', N'2027-06-09'),
    (N'SIM-HO4-24014', N'HO4', N'HO', N'GA', N'Sofia Rossi', N'2026-05-25', N'2027-05-25'),
    (N'SIM-HO6-24015', N'HO6', N'HO', N'GA', N'James Johnson', N'2025-01-12', N'2026-01-12'),
    (N'SIM-DP3-24016', N'DP3', N'HO', N'FL', N'Wei Wilson', N'2025-02-21', N'2026-02-21'),
    (N'SIM-PA-24017', N'PA_STD', N'PA', N'AL', N'Carlos Wilson', N'2026-06-10', N'2027-06-10'),
    (N'SIM-PA-24018', N'PA_STD', N'PA', N'SC', N'Grace Chen', N'2026-04-24', N'2027-04-24'),
    (N'SIM-BOP-24019', N'BOP', N'BP', N'AL', N'Robert Haddad', N'2025-06-20', N'2026-06-20'),
    (N'SIS-CP-24020', N'CP', N'CP', N'GA', N'Grace Garcia', N'2025-05-25', N'2026-05-25'),
    (N'SIM-HO3-24021', N'HO3', N'HO', N'NC', N'James Smith', N'2025-11-11', N'2026-11-11'),
    (N'SIM-HO3-24022', N'HO3', N'HO', N'NC', N'Kevin Smith', N'2025-10-08', N'2026-10-08'),
    (N'SIM-HO5-24023', N'HO5', N'HO', N'NC', N'Elena Patel', N'2026-01-29', N'2027-01-29'),
    (N'SIM-HO4-24024', N'HO4', N'HO', N'GA', N'Sofia Wilson', N'2025-03-09', N'2026-03-09'),
    (N'SIM-HO6-24025', N'HO6', N'HO', N'TX', N'Grace Silva', N'2025-10-12', N'2026-10-12'),
    (N'SIM-DP3-24026', N'DP3', N'HO', N'FL', N'Priya Okafor', N'2025-01-01', N'2026-01-01'),
    (N'SIM-PA-24027', N'PA_STD', N'PA', N'NC', N'Carlos Lopez', N'2025-08-27', N'2026-08-27'),
    (N'SIM-PA-24028', N'PA_STD', N'PA', N'SC', N'Kevin Chen', N'2026-05-20', N'2027-05-20'),
    (N'SIM-BOP-24029', N'BOP', N'BP', N'TX', N'James Brown', N'2025-08-07', N'2026-08-07'),
    (N'SIS-CP-24030', N'CP', N'CP', N'TX', N'Fatima Martin', N'2025-09-03', N'2026-09-03'),
    (N'SIM-HO3-24031', N'HO3', N'HO', N'SC', N'Aisha Smith', N'2025-04-21', N'2026-04-21'),
    (N'SIM-HO3-24032', N'HO3', N'HO', N'SC', N'Linda Lopez', N'2025-11-17', N'2026-11-17'),
    (N'SIM-HO5-24033', N'HO5', N'HO', N'NC', N'Omar Brown', N'2026-04-30', N'2027-04-30'),
    (N'SIM-HO4-24034', N'HO4', N'HO', N'GA', N'Kevin Martin', N'2025-04-02', N'2026-04-02'),
    (N'SIM-HO6-24035', N'HO6', N'HO', N'AL', N'Brian Smith', N'2026-02-03', N'2027-02-03'),
    (N'SIM-DP3-24036', N'DP3', N'HO', N'TX', N'Omar Haddad', N'2026-02-27', N'2027-02-27'),
    (N'SIM-PA-24037', N'PA_STD', N'PA', N'GA', N'Grace Garcia', N'2025-09-21', N'2026-09-21'),
    (N'SIM-PA-24038', N'PA_STD', N'PA', N'GA', N'Fatima Martin', N'2026-01-26', N'2027-01-26'),
    (N'SIM-BOP-24039', N'BOP', N'BP', N'SC', N'Wei Brown', N'2026-03-27', N'2027-03-27'),
    (N'SIS-CP-24040', N'CP', N'CP', N'SC', N'Robert Okafor', N'2025-06-23', N'2026-06-23'),
    (N'SIM-HO3-24041', N'HO3', N'HO', N'SC', N'Sofia Silva', N'2026-04-07', N'2027-04-07'),
    (N'SIM-HO3-24042', N'HO3', N'HO', N'SC', N'Grace Smith', N'2025-05-27', N'2026-05-27'),
    (N'SIM-HO5-24043', N'HO5', N'HO', N'SC', N'Aisha Okafor', N'2025-05-04', N'2026-05-04'),
    (N'SIM-HO4-24044', N'HO4', N'HO', N'NC', N'David Nguyen', N'2026-03-28', N'2027-03-28'),
    (N'SIM-HO6-24045', N'HO6', N'HO', N'TX', N'Aisha Haddad', N'2025-06-22', N'2026-06-22'),
    (N'SIM-DP3-24046', N'DP3', N'HO', N'NC', N'Elena Chen', N'2025-07-04', N'2026-07-04'),
    (N'SIM-PA-24047', N'PA_STD', N'PA', N'NC', N'Carlos Johnson', N'2025-07-24', N'2026-07-24'),
    (N'SIM-PA-24048', N'PA_STD', N'PA', N'NC', N'Elena Johnson', N'2025-11-12', N'2026-11-12')
) v (n, p, l, s, i, e, x)
WHERE NOT EXISTS (SELECT 1 FROM cov.Policy z WHERE z.PolicyNumber = v.n);
GO

INSERT cov.PolicyCoverage (PolicyNumber, CoverageCode, LimitAmount, DeductibleAmount)
SELECT v.n, v.c, v.l, v.d
FROM (VALUES
    (N'SIM-HO3-24001', N'DWELL', 340000, 1000),
    (N'SIM-HO3-24001', N'OTHSTR', 34000, 1000),
    (N'SIM-HO3-24001', N'PERSPROP', 170000, 1000),
    (N'SIM-HO3-24001', N'LOU', 68000, 0),
    (N'SIM-HO3-24002', N'DWELL', 270000, 500),
    (N'SIM-HO3-24002', N'OTHSTR', 27000, 500),
    (N'SIM-HO3-24002', N'PERSPROP', 135000, 500),
    (N'SIM-HO3-24002', N'LOU', 54000, 0),
    (N'SIM-HO5-24003', N'DWELL', 710000, 1000),
    (N'SIM-HO5-24003', N'OTHSTR', 71000, 1000),
    (N'SIM-HO5-24003', N'PERSPROP', 355000, 1000),
    (N'SIM-HO5-24003', N'LOU', 142000, 0),
    (N'SIM-HO4-24004', N'PERSPROP', 25000, 500),
    (N'SIM-HO4-24004', N'LOU', 10000, 0),
    (N'SIM-HO6-24005', N'DWELL', 50000, 2500),
    (N'SIM-HO6-24005', N'PERSPROP', 60000, 2500),
    (N'SIM-HO6-24005', N'LOU', 20000, 0),
    (N'SIM-DP3-24006', N'DWELL', 440000, 1000),
    (N'SIM-DP3-24006', N'OTHSTR', 44000, 1000),
    (N'SIM-DP3-24006', N'PERSPROP', 44000, 1000),
    (N'SIM-DP3-24006', N'LOU', 88000, 0),
    (N'SIM-PA-24007', N'BI', 100000, 0),
    (N'SIM-PA-24007', N'PD', 50000, 0),
    (N'SIM-PA-24007', N'COMP', 29000, 250),
    (N'SIM-PA-24007', N'COLL', 29000, 1000),
    (N'SIM-PA-24008', N'BI', 100000, 0),
    (N'SIM-PA-24008', N'PD', 50000, 0),
    (N'SIM-PA-24008', N'COMP', 58000, 250),
    (N'SIM-BOP-24009', N'BLDG', 350000, 1000),
    (N'SIM-BOP-24009', N'BPP', 140000, 1000),
    (N'SIM-BOP-24009', N'LIAB', 1000000, 0),
    (N'SIS-CP-24010', N'BLDG', 8200000, 5000),
    (N'SIS-CP-24010', N'BPP', 4100000, 5000),
    (N'SIM-HO3-24011', N'DWELL', 620000, 1000),
    (N'SIM-HO3-24011', N'OTHSTR', 62000, 1000),
    (N'SIM-HO3-24011', N'PERSPROP', 310000, 1000),
    (N'SIM-HO3-24011', N'LOU', 124000, 0),
    (N'SIM-HO3-24012', N'DWELL', 440000, 500),
    (N'SIM-HO3-24012', N'OTHSTR', 44000, 500),
    (N'SIM-HO3-24012', N'PERSPROP', 220000, 500),
    (N'SIM-HO3-24012', N'LOU', 88000, 0),
    (N'SIM-HO5-24013', N'DWELL', 550000, 1000),
    (N'SIM-HO5-24013', N'OTHSTR', 55000, 1000),
    (N'SIM-HO5-24013', N'PERSPROP', 275000, 1000),
    (N'SIM-HO5-24013', N'LOU', 110000, 0),
    (N'SIM-HO4-24014', N'PERSPROP', 40000, 500),
    (N'SIM-HO4-24014', N'LOU', 10000, 0),
    (N'SIM-HO6-24015', N'DWELL', 50000, 1000),
    (N'SIM-HO6-24015', N'PERSPROP', 60000, 1000),
    (N'SIM-HO6-24015', N'LOU', 20000, 0),
    (N'SIM-DP3-24016', N'DWELL', 460000, 500),
    (N'SIM-DP3-24016', N'OTHSTR', 46000, 500),
    (N'SIM-DP3-24016', N'PERSPROP', 46000, 500),
    (N'SIM-DP3-24016', N'LOU', 92000, 0),
    (N'SIM-PA-24017', N'BI', 100000, 0),
    (N'SIM-PA-24017', N'PD', 50000, 0),
    (N'SIM-PA-24017', N'COMP', 41000, 500),
    (N'SIM-PA-24018', N'BI', 100000, 0),
    (N'SIM-PA-24018', N'PD', 50000, 0),
    (N'SIM-PA-24018', N'COMP', 28000, 100),
    (N'SIM-PA-24018', N'COLL', 28000, 1000),
    (N'SIM-BOP-24019', N'BLDG', 400000, 1000),
    (N'SIM-BOP-24019', N'BPP', 160000, 1000),
    (N'SIM-BOP-24019', N'LIAB', 1000000, 0),
    (N'SIS-CP-24020', N'BLDG', 7200000, 5000),
    (N'SIS-CP-24020', N'BPP', 3600000, 5000),
    (N'SIM-HO3-24021', N'DWELL', 890000, 2500),
    (N'SIM-HO3-24021', N'OTHSTR', 89000, 2500),
    (N'SIM-HO3-24021', N'PERSPROP', 445000, 2500),
    (N'SIM-HO3-24021', N'LOU', 178000, 0),
    (N'SIM-HO3-24022', N'DWELL', 530000, 2500),
    (N'SIM-HO3-24022', N'OTHSTR', 53000, 2500),
    (N'SIM-HO3-24022', N'PERSPROP', 265000, 2500),
    (N'SIM-HO3-24022', N'LOU', 106000, 0),
    (N'SIM-HO5-24023', N'DWELL', 450000, 500),
    (N'SIM-HO5-24023', N'OTHSTR', 45000, 500),
    (N'SIM-HO5-24023', N'PERSPROP', 225000, 500),
    (N'SIM-HO5-24023', N'LOU', 90000, 0),
    (N'SIM-HO4-24024', N'PERSPROP', 60000, 500),
    (N'SIM-HO4-24024', N'LOU', 10000, 0),
    (N'SIM-HO6-24025', N'DWELL', 50000, 1000),
    (N'SIM-HO6-24025', N'PERSPROP', 60000, 1000),
    (N'SIM-HO6-24025', N'LOU', 20000, 0),
    (N'SIM-DP3-24026', N'DWELL', 550000, 1000),
    (N'SIM-DP3-24026', N'OTHSTR', 55000, 1000),
    (N'SIM-DP3-24026', N'PERSPROP', 55000, 1000),
    (N'SIM-DP3-24026', N'LOU', 110000, 0),
    (N'SIM-PA-24027', N'BI', 100000, 0),
    (N'SIM-PA-24027', N'PD', 50000, 0),
    (N'SIM-PA-24027', N'COMP', 23000, 500),
    (N'SIM-PA-24027', N'COLL', 23000, 1000),
    (N'SIM-PA-24028', N'BI', 100000, 0),
    (N'SIM-PA-24028', N'PD', 50000, 0),
    (N'SIM-PA-24028', N'COMP', 27000, 500),
    (N'SIM-PA-24028', N'COLL', 27000, 1000),
    (N'SIM-BOP-24029', N'BLDG', 1000000, 1000),
    (N'SIM-BOP-24029', N'BPP', 400000, 1000),
    (N'SIM-BOP-24029', N'LIAB', 1000000, 0),
    (N'SIS-CP-24030', N'BLDG', 2200000, 5000),
    (N'SIS-CP-24030', N'BPP', 1100000, 5000),
    (N'SIM-HO3-24031', N'DWELL', 270000, 1000),
    (N'SIM-HO3-24031', N'OTHSTR', 27000, 1000),
    (N'SIM-HO3-24031', N'PERSPROP', 135000, 1000),
    (N'SIM-HO3-24031', N'LOU', 54000, 0),
    (N'SIM-HO3-24032', N'DWELL', 250000, 1000),
    (N'SIM-HO3-24032', N'OTHSTR', 25000, 1000),
    (N'SIM-HO3-24032', N'PERSPROP', 125000, 1000),
    (N'SIM-HO3-24032', N'LOU', 50000, 0),
    (N'SIM-HO5-24033', N'DWELL', 760000, 1000),
    (N'SIM-HO5-24033', N'OTHSTR', 76000, 1000),
    (N'SIM-HO5-24033', N'PERSPROP', 380000, 1000),
    (N'SIM-HO5-24033', N'LOU', 152000, 0),
    (N'SIM-HO4-24034', N'PERSPROP', 40000, 1000),
    (N'SIM-HO4-24034', N'LOU', 10000, 0),
    (N'SIM-HO6-24035', N'DWELL', 50000, 1000),
    (N'SIM-HO6-24035', N'PERSPROP', 60000, 1000),
    (N'SIM-HO6-24035', N'LOU', 20000, 0),
    (N'SIM-DP3-24036', N'DWELL', 770000, 1000),
    (N'SIM-DP3-24036', N'OTHSTR', 77000, 1000),
    (N'SIM-DP3-24036', N'PERSPROP', 77000, 1000),
    (N'SIM-DP3-24036', N'LOU', 154000, 0),
    (N'SIM-PA-24037', N'BI', 100000, 0),
    (N'SIM-PA-24037', N'PD', 50000, 0),
    (N'SIM-PA-24037', N'COMP', 58000, 100),
    (N'SIM-PA-24037', N'COLL', 58000, 500),
    (N'SIM-PA-24038', N'BI', 100000, 0),
    (N'SIM-PA-24038', N'PD', 50000, 0),
    (N'SIM-PA-24038', N'COMP', 37000, 100),
    (N'SIM-PA-24038', N'COLL', 37000, 1000),
    (N'SIM-BOP-24039', N'BLDG', 1600000, 1000),
    (N'SIM-BOP-24039', N'BPP', 640000, 1000),
    (N'SIM-BOP-24039', N'LIAB', 1000000, 0),
    (N'SIS-CP-24040', N'BLDG', 3900000, 5000),
    (N'SIS-CP-24040', N'BPP', 1950000, 5000),
    (N'SIM-HO3-24041', N'DWELL', 750000, 500),
    (N'SIM-HO3-24041', N'OTHSTR', 75000, 500),
    (N'SIM-HO3-24041', N'PERSPROP', 375000, 500),
    (N'SIM-HO3-24041', N'LOU', 150000, 0),
    (N'SIM-HO3-24042', N'DWELL', 750000, 1000),
    (N'SIM-HO3-24042', N'OTHSTR', 75000, 1000),
    (N'SIM-HO3-24042', N'PERSPROP', 375000, 1000),
    (N'SIM-HO3-24042', N'LOU', 150000, 0),
    (N'SIM-HO5-24043', N'DWELL', 490000, 2500),
    (N'SIM-HO5-24043', N'OTHSTR', 49000, 2500),
    (N'SIM-HO5-24043', N'PERSPROP', 245000, 2500),
    (N'SIM-HO5-24043', N'LOU', 98000, 0),
    (N'SIM-HO4-24044', N'PERSPROP', 40000, 2500),
    (N'SIM-HO4-24044', N'LOU', 10000, 0),
    (N'SIM-HO6-24045', N'DWELL', 50000, 2500),
    (N'SIM-HO6-24045', N'PERSPROP', 60000, 2500),
    (N'SIM-HO6-24045', N'LOU', 20000, 0),
    (N'SIM-DP3-24046', N'DWELL', 420000, 1000),
    (N'SIM-DP3-24046', N'OTHSTR', 42000, 1000),
    (N'SIM-DP3-24046', N'PERSPROP', 42000, 1000),
    (N'SIM-DP3-24046', N'LOU', 84000, 0),
    (N'SIM-PA-24047', N'BI', 100000, 0),
    (N'SIM-PA-24047', N'PD', 50000, 0),
    (N'SIM-PA-24047', N'COMP', 38000, 250),
    (N'SIM-PA-24047', N'COLL', 38000, 1000),
    (N'SIM-PA-24048', N'BI', 100000, 0),
    (N'SIM-PA-24048', N'PD', 50000, 0),
    (N'SIM-PA-24048', N'COMP', 18000, 100),
    (N'SIM-PA-24048', N'COLL', 18000, 1000)
) v (n, c, l, d)
WHERE NOT EXISTS (SELECT 1 FROM cov.PolicyCoverage z WHERE z.PolicyNumber = v.n AND z.CoverageCode = v.c);
GO

INSERT cov.PolicyForm (PolicyNumber, FormNumber, Seq)
SELECT v.n, v.f, v.s
FROM (VALUES
    (N'SIM-HO3-24001', N'SIM HO 3', 1),
    (N'SIM-HO3-24001', N'SIM HO 04 95', 2),
    (N'SIM-HO3-24001', N'SIM HO 23 FL', 3),
    (N'SIM-HO3-24001', N'SIM HO 32 FL', 4),
    (N'SIM-HO3-24002', N'SIM HO 3', 1),
    (N'SIM-HO3-24002', N'SIM HO 04 95', 2),
    (N'SIM-HO3-24002', N'SIM HO 32 FL', 3),
    (N'SIM-HO5-24003', N'SIM HO 3', 1),
    (N'SIM-HO5-24003', N'SIM HO 04 95', 2),
    (N'SIM-HO5-24003', N'SIM HO 23 FL', 3),
    (N'SIM-HO5-24003', N'SIM HO 32 FL', 4),
    (N'SIM-HO4-24004', N'SIM HO 4', 1),
    (N'SIM-HO4-24004', N'SIM HO 04 95', 2),
    (N'SIM-HO6-24005', N'SIM HO 6', 1),
    (N'SIM-HO6-24005', N'SIM HO 32 FL', 2),
    (N'SIM-DP3-24006', N'SIM DP 3', 1),
    (N'SIM-DP3-24006', N'SIM HO 32 FL', 2),
    (N'SIM-PA-24007', N'SIM PP 00 01', 1),
    (N'SIM-PA-24008', N'SIM PP 00 01', 1),
    (N'SIM-BOP-24009', N'SIM BP 00 03', 1),
    (N'SIS-CP-24010', N'SIS CP 10 30', 1),
    (N'SIM-HO3-24011', N'SIM HO 3', 1),
    (N'SIM-HO3-24011', N'SIM HO 04 95', 2),
    (N'SIM-HO3-24011', N'SIM HO 32 FL', 3),
    (N'SIM-HO3-24011', N'SIM HO 04 26', 4),
    (N'SIM-HO3-24012', N'SIM HO 3', 1),
    (N'SIM-HO3-24012', N'SIM HO 04 95', 2),
    (N'SIM-HO3-24012', N'SIM HO 32 FL', 3),
    (N'SIM-HO5-24013', N'SIM HO 3', 1),
    (N'SIM-HO5-24013', N'SIM HO 32 FL', 2),
    (N'SIM-HO4-24014', N'SIM HO 4', 1),
    (N'SIM-HO6-24015', N'SIM HO 6', 1),
    (N'SIM-DP3-24016', N'SIM DP 3', 1),
    (N'SIM-DP3-24016', N'SIM HO 32 FL', 2),
    (N'SIM-PA-24017', N'SIM PP 00 01', 1),
    (N'SIM-PA-24018', N'SIM PP 00 01', 1),
    (N'SIM-BOP-24019', N'SIM BP 00 03', 1),
    (N'SIS-CP-24020', N'SIS CP 10 30', 1),
    (N'SIM-HO3-24021', N'SIM HO 3', 1),
    (N'SIM-HO3-24021', N'SIM HO 04 95', 2),
    (N'SIM-HO3-24021', N'SIM HO 32 FL', 3),
    (N'SIM-HO3-24022', N'SIM HO 3', 1),
    (N'SIM-HO3-24022', N'SIM HO 04 95', 2),
    (N'SIM-HO3-24022', N'SIM HO 32 FL', 3),
    (N'SIM-HO5-24023', N'SIM HO 3', 1),
    (N'SIM-HO5-24023', N'SIM HO 04 95', 2),
    (N'SIM-HO5-24023', N'SIM HO 32 FL', 3),
    (N'SIM-HO5-24023', N'SIM HO 04 26', 4),
    (N'SIM-HO4-24024', N'SIM HO 4', 1),
    (N'SIM-HO6-24025', N'SIM HO 6', 1),
    (N'SIM-HO6-24025', N'SIM HO 04 95', 2),
    (N'SIM-HO6-24025', N'SIM HO 32 FL', 3),
    (N'SIM-DP3-24026', N'SIM DP 3', 1),
    (N'SIM-DP3-24026', N'SIM HO 04 95', 2),
    (N'SIM-DP3-24026', N'SIM HO 23 FL', 3),
    (N'SIM-DP3-24026', N'SIM HO 32 FL', 4),
    (N'SIM-PA-24027', N'SIM PP 00 01', 1),
    (N'SIM-PA-24028', N'SIM PP 00 01', 1),
    (N'SIM-BOP-24029', N'SIM BP 00 03', 1),
    (N'SIS-CP-24030', N'SIS CP 10 30', 1),
    (N'SIM-HO3-24031', N'SIM HO 3', 1),
    (N'SIM-HO3-24031', N'SIM HO 04 95', 2),
    (N'SIM-HO3-24031', N'SIM HO 32 FL', 3),
    (N'SIM-HO3-24032', N'SIM HO 3', 1),
    (N'SIM-HO3-24032', N'SIM HO 04 95', 2),
    (N'SIM-HO3-24032', N'SIM HO 32 FL', 3),
    (N'SIM-HO5-24033', N'SIM HO 3', 1),
    (N'SIM-HO5-24033', N'SIM HO 32 FL', 2),
    (N'SIM-HO4-24034', N'SIM HO 4', 1),
    (N'SIM-HO4-24034', N'SIM HO 04 95', 2),
    (N'SIM-HO6-24035', N'SIM HO 6', 1),
    (N'SIM-HO6-24035', N'SIM HO 04 95', 2),
    (N'SIM-HO6-24035', N'SIM HO 32 FL', 3),
    (N'SIM-HO6-24035', N'SIM HO 04 26', 4),
    (N'SIM-DP3-24036', N'SIM DP 3', 1),
    (N'SIM-DP3-24036', N'SIM HO 04 95', 2),
    (N'SIM-DP3-24036', N'SIM HO 32 FL', 3),
    (N'SIM-PA-24037', N'SIM PP 00 01', 1),
    (N'SIM-PA-24038', N'SIM PP 00 01', 1),
    (N'SIM-BOP-24039', N'SIM BP 00 03', 1),
    (N'SIM-BOP-24039', N'SIM BP 04 ED', 2),
    (N'SIS-CP-24040', N'SIS CP 10 30', 1),
    (N'SIM-HO3-24041', N'SIM HO 3', 1),
    (N'SIM-HO3-24041', N'SIM HO 04 95', 2),
    (N'SIM-HO3-24041', N'SIM HO 32 FL', 3),
    (N'SIM-HO3-24041', N'SIM HO 04 26', 4),
    (N'SIM-HO3-24042', N'SIM HO 3', 1),
    (N'SIM-HO3-24042', N'SIM HO 04 95', 2),
    (N'SIM-HO3-24042', N'SIM HO 32 FL', 3),
    (N'SIM-HO3-24042', N'SIM HO 04 26', 4),
    (N'SIM-HO5-24043', N'SIM HO 3', 1),
    (N'SIM-HO5-24043', N'SIM HO 32 FL', 2),
    (N'SIM-HO4-24044', N'SIM HO 4', 1),
    (N'SIM-HO6-24045', N'SIM HO 6', 1),
    (N'SIM-HO6-24045', N'SIM HO 32 FL', 2),
    (N'SIM-DP3-24046', N'SIM DP 3', 1),
    (N'SIM-DP3-24046', N'SIM HO 32 FL', 2),
    (N'SIM-PA-24047', N'SIM PP 00 01', 1),
    (N'SIM-PA-24048', N'SIM PP 00 01', 1)
) v (n, f, s)
WHERE NOT EXISTS (SELECT 1 FROM cov.PolicyForm z WHERE z.PolicyNumber = v.n AND z.FormNumber = v.f);
GO

-- Synthetic claims and payments (some carry findings on purpose)

INSERT cov.Claim (ClaimNumber, PolicyNumber, LossDate, ReportedDate, CauseCode, CoverageCode, LossDescription, Notes, AdjusterName, RecordedLimit, RecordedDeductible, GrossLoss, PaidAmount, ReserveAmount, IsSynthetic)
SELECT v.n, v.p, v.ld, v.rd, v.ca, v.co, v.de, v.nt, v.ad, v.rl, v.rdd, v.g, v.pa, v.re, 1
FROM (VALUES
    (N'CLM-69901', N'SIM-HO3-24001', N'2026-08-24', N'2026-08-26', N'WIND', N'DWELL', N'Storm surge pushed seawater into the house; water came in under the door, about two feet of water on the first floor.', N'Cause code entered by the adjuster on the first call.', N'Ben Clarke', 340000, 1000, 48000, 46000, 0),
    (N'CLM-69902', N'SIM-HO3-24001', N'2026-08-24', N'2026-08-26', N'WIND', N'DWELL', N'Hurricane winds tore off part of the roof and broke windows; wind-driven rain damaged ceilings.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 340000, 1000, 30000, 0, 0),
    (N'CLM-69903', N'SIM-HO3-24001', N'2026-08-24', N'2026-08-26', N'WATER', N'DWELL', N'The washing machine hose burst while the family was at work; water spread across the laundry room and hallway.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 340000, 1000, 12500, 11500, 0),
    (N'CLM-69904', N'SIM-HO3-24001', N'2026-08-24', N'2026-08-26', N'WIND', N'DWELL', N'Hurricane winds tore shingles off the roof, and the storm surge then pushed seawater through the front door.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 340000, 1000, 60000, 0, 0),
    (N'CLM-69905', N'SIM-HO3-24001', N'2026-08-24', N'2026-08-26', N'SEWER', N'DWELL', N'After heavy rain the sewer backed up through the basement floor drain; carpet and drywall ruined.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 340000, 1000, 19000, 18000, 0),
    (N'CLM-69906', N'SIM-PA-24007', N'2026-01-25', N'2026-01-27', N'COMP', N'COMP', N'Insured rear-ended another car at a red light; front bumper and radiator damaged.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 29000, 250, 6200, 5950, 0),
    (N'CLM-70001', N'SIM-HO6-24025', N'2026-02-27', N'2026-03-23', N'WATER', N'DWELL', N'The washing machine hose burst while the family was at work; water spread across the laundry room and hallway.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 50000, 1000, 19393, 9196, 9197),
    (N'CLM-70002', N'SIM-HO3-24001', N'2026-09-20', N'2026-09-25', N'FREEZE', N'DWELL', N'Pipes froze during the cold snap and burst in the attic; heat was on.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 340000, 1000, 6846, 5846, 0),
    (N'CLM-70003', N'SIS-CP-24040', N'2025-08-12', N'2025-08-12', N'VMM', N'BLDG', N'Vandals broke in and spray-painted graffiti on the walls; vandalism to fixtures.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 3900000, 5000, 8071, 0, 3071),
    (N'CLM-70004', N'SIM-PA-24047', N'2025-10-16', N'2025-10-20', N'COMP', N'COMP', N'Rock hit the windshield on the interstate; cracked windshield.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 38000, 250, 4737, 4487, 0),
    (N'CLM-70005', N'SIM-HO4-24004', N'2025-10-13', N'2025-10-13', N'WATER', N'PERSPROP', N'The washing machine hose burst while the family was at work; water spread across the laundry room and hallway.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 25000, 0, 7349, 7349, 0),
    (N'CLM-70006', N'SIM-PA-24047', N'2026-03-18', N'2026-03-21', N'COMP', N'COMP', N'Rock hit the windshield on the interstate; cracked windshield.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 38000, 250, 13432, 6591, 6591),
    (N'CLM-70007', N'SIM-PA-24047', N'2025-10-07', N'2025-10-28', N'COMP', N'COMP', N'Vehicle stolen from the driveway overnight; recovered stripped.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 38000, 250, 7144, 0, 6894),
    (N'CLM-70008', N'SIM-PA-24027', N'2025-11-05', N'2025-11-21', N'COLL', N'COLL', N'Insured was driving for Uber with a passenger when another car sideswiped the vehicle.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 23000, 1000, 4941, 0, 0),
    (N'CLM-70009', N'SIM-BOP-24029', N'2026-01-15', N'2026-01-18', N'EMPDIS', N'BPP', N'Bookkeeper embezzled cash over three months; police report filed.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 400000, 1000, 28177, 27177, 0),
    (N'CLM-70010', N'SIM-BOP-24019', N'2025-08-20', N'2025-08-21', N'VMM', N'BLDG', N'Vandals broke in and spray-painted graffiti on the walls; vandalism to fixtures.', N'Limit updated on the claim by the adjuster.', N'Ben Clarke', 600000, 1000, 5926, 0, 4926),
    (N'CLM-70011', N'SIM-DP3-24016', N'2025-12-28', N'2026-01-01', N'WEAR', N'DWELL', N'Roof leaking because the shingles are worn out; deterioration over many years, ceiling stained.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 460000, 500, 3497, 0, 0),
    (N'CLM-70012', N'SIM-BOP-24029', N'2025-12-03', N'2025-12-07', N'FIRE', N'BLDG', N'A grease fire started on the stove and burned the kitchen cabinets; smoke damage through the first floor.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 1000000, 1000, 9073, 4036, 4037),
    (N'CLM-70013', N'SIS-CP-24010', N'2026-11-22', N'2026-11-25', N'FLOOD', N'BLDG', N'River overflowed after the storm; flood water two feet deep in the warehouse.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 8200000, 5000, 21004, 0, 0),
    (N'CLM-70014', N'SIS-CP-24020', N'2025-08-30', N'2025-08-31', N'WIND', N'BLDG', N'High winds during the storm blew off shingles; rain came through the opening in the roof into the bedroom.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 7200000, 5000, 9792, 2396, 2396),
    (N'CLM-70015', N'SIM-DP3-24016', N'2025-11-24', N'2025-11-27', N'WIND', N'DWELL', N'High winds during the storm blew off shingles; rain came through the opening in the roof into the bedroom.', CAST(NULL AS nvarchar(4000)), N'Tom Reed', 460000, 500, 49950, 49450, 0),
    (N'CLM-70016', N'SIM-HO3-24031', N'2025-11-19', N'2025-11-19', N'THEFT', N'PERSPROP', N'Break-in while the insured was on vacation; jewelry and a laptop stolen.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 135000, 1000, 16411, 7706, 7705),
    (N'CLM-70017', N'SIM-PA-24028', N'2026-04-30', N'2026-05-20', N'COLL', N'COLL', N'Insured rear-ended another car at a red light; front bumper and radiator damaged.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 27000, 1000, 4555, 0, 3555),
    (N'CLM-70018', N'SIS-CP-24040', N'2026-04-24', N'2026-05-01', N'FIRE', N'BLDG', N'A grease fire started on the stove and burned the kitchen cabinets; smoke damage through the first floor.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 3900000, 5000, 8928, 3928, 0),
    (N'CLM-70019', N'SIM-PA-24037', N'2025-10-31', N'2025-11-01', N'COLL', N'COLL', N'Insured was driving for Uber with a passenger when another car sideswiped the vehicle.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 58000, 500, 4207, 3707, 0),
    (N'CLM-70020', N'SIM-HO6-24005', N'2025-01-19', N'2025-02-08', N'WEAR', N'DWELL', N'Roof leaking because the shingles are worn out; deterioration over many years, ceiling stained.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 50000, 2500, 11421, 0, 0),
    (N'CLM-70021', N'SIM-DP3-24006', N'2026-02-08', N'2026-02-09', N'WIND', N'DWELL', N'High winds during the storm blew off shingles; rain came through the opening in the roof into the bedroom.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 440000, 1000, 6604, 5604, 0),
    (N'CLM-70022', N'SIM-PA-24047', N'2026-05-09', N'2026-05-18', N'COMP', N'COMP', N'Insured hit a deer on the highway at night; hood and headlight damaged.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 38000, 250, 9379, 4564, 4565),
    (N'CLM-70023', N'SIS-CP-24040', N'2025-11-29', N'2025-12-03', N'VMM', N'BLDG', N'Vandals broke in and spray-painted graffiti on the walls; vandalism to fixtures.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 3900000, 5000, 6347, 674, 673),
    (N'CLM-70024', N'SIM-HO3-24021', N'2026-04-25', N'2026-04-26', N'HAIL', N'DWELL', N'Hailstorm damaged the roof shingles and gutters.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 890000, 2500, 10426, 7926, 0),
    (N'CLM-70025', N'SIM-HO4-24024', N'2025-02-08', N'2025-02-28', N'SEWER', N'PERSPROP', N'After heavy rain the sewer backed up through the basement floor drain; carpet and drywall ruined.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 60000, 500, 2418, 0, 0),
    (N'CLM-70026', N'SIM-HO6-24045', N'2026-03-30', N'2026-04-03', N'WIND', N'DWELL', N'High winds during the storm blew off shingles; rain came through the opening in the roof into the bedroom.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 50000, 2500, 28573, 13036, 13037),
    (N'CLM-70027', N'SIM-PA-24047', N'2025-07-16', N'2025-08-05', N'COMP', N'COMP', N'Vehicle stolen from the driveway overnight; recovered stripped.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 38000, 250, 3966, 1858, 1858),
    (N'CLM-70028', N'SIM-HO6-24035', N'2026-09-08', N'2026-09-10', N'SEWER', N'DWELL', N'After heavy rain the sewer backed up through the basement floor drain; carpet and drywall ruined.', CAST(NULL AS nvarchar(4000)), N'Tom Reed', 50000, 1000, 50450, 49450, 0),
    (N'CLM-70029', N'SIM-HO3-24012', N'2025-10-08', N'2025-10-16', N'SINKHOLE', N'DWELL', N'Cracks in the walls and floor; engineer confirmed a sinkhole under the foundation.', N'Limit updated on the claim by the adjuster.', N'Dev Shah', 660000, 500, 3379, 0, 0),
    (N'CLM-70030', N'SIM-HO5-24043', N'2025-07-07', N'2025-07-15', N'WIND', N'DWELL', N'High winds during the storm blew off shingles; rain came through the opening in the roof into the bedroom.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 490000, 0, 10158, 10158, 0),
    (N'CLM-70031', N'SIS-CP-24010', N'2026-01-24', N'2026-02-13', N'FLOOD', N'BLDG', N'River overflowed after the storm; flood water two feet deep in the warehouse.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 8200000, 5000, 9334, 0, 0),
    (N'CLM-70032', N'SIM-HO4-24024', N'2025-05-06', N'2025-05-06', N'THEFT', N'PERSPROP', N'Break-in while the insured was on vacation; jewelry and a laptop stolen.', CAST(NULL AS nvarchar(4000)), N'Tom Reed', 60000, 500, 49950, 49450, 0),
    (N'CLM-70033', N'SIM-HO4-24014', N'2026-07-26', N'2026-07-28', N'WATER', N'PERSPROP', N'The washing machine hose burst while the family was at work; water spread across the laundry room and hallway.', CAST(NULL AS nvarchar(4000)), N'Tom Reed', 40000, 500, 49950, 49450, 0),
    (N'CLM-70034', N'SIM-PA-24007', N'2026-06-02', N'2026-06-02', N'COLL', N'COLL', N'Insured rear-ended another car at a red light; front bumper and radiator damaged.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 29000, 1000, 6790, 0, 5790),
    (N'CLM-70035', N'SIM-BOP-24019', N'2025-11-09', N'2025-11-28', N'THEFT', N'BPP', N'Break-in while the insured was on vacation; jewelry and a laptop stolen.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 160000, 1000, 14829, 13829, 0),
    (N'CLM-70036', N'SIM-PA-24028', N'2027-04-09', N'2027-04-15', N'COLL', N'COLL', N'Insured rear-ended another car at a red light; front bumper and radiator damaged.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 27000, 1000, 4700, 1850, 1850),
    (N'CLM-70037', N'SIM-PA-24007', N'2026-05-30', N'2026-06-03', N'COLL', N'COLL', N'Insured rear-ended another car at a red light; front bumper and radiator damaged.', N'Limit updated on the claim by the adjuster.', N'Ben Clarke', 44000, 1000, 7349, 3174, 3175),
    (N'CLM-70038', N'SIM-PA-24048', N'2026-03-14', N'2026-03-25', N'COMP', N'COMP', N'Insured hit a deer on the highway at night; hood and headlight damaged.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 18000, 100, 9375, 4638, 4637),
    (N'CLM-70039', N'SIM-HO3-24031', N'2026-02-11', N'2026-02-15', N'FIRE', N'DWELL', N'A grease fire started on the stove and burned the kitchen cabinets; smoke damage through the first floor.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 270000, 1000, 4637, 0, 3637),
    (N'CLM-70040', N'SIM-PA-24008', N'2025-12-30', N'2026-01-02', N'COLL', N'COLL', N'Insured rear-ended another car at a red light; front bumper and radiator damaged.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 0, 0, 498, 0, 0),
    (N'CLM-70041', N'SIM-HO4-24034', N'2026-02-20', N'2026-02-22', N'FIRE', N'PERSPROP', N'A grease fire started on the stove and burned the kitchen cabinets; smoke damage through the first floor.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 40000, 1000, 24115, 0, 23115),
    (N'CLM-70042', N'SIM-PA-24037', N'2025-10-23', N'2025-10-23', N'COLL', N'COLL', N'Insured rear-ended another car at a red light; front bumper and radiator damaged.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 58000, 500, 3692, 3192, 0),
    (N'CLM-70043', N'SIM-HO3-24011', N'2026-07-20', N'2026-07-22', N'MOLD', N'DWELL', N'Insured found mold behind the bathroom vanity; plumber says it was a slow leak for months.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 620000, 1000, 2007, 0, 0),
    (N'CLM-70044', N'SIM-HO4-24044', N'2026-06-10', N'2026-06-16', N'THEFT', N'PERSPROP', N'Break-in while the insured was on vacation; jewelry and a laptop stolen.', CAST(NULL AS nvarchar(4000)), N'Tom Reed', 40000, 2500, 51950, 49450, 0),
    (N'CLM-70045', N'SIM-HO3-24012', N'2025-10-11', N'2025-10-19', N'WATER', N'DWELL', N'The washing machine hose burst while the family was at work; water spread across the laundry room and hallway.', N'Limit updated on the claim by the adjuster.', N'Ana Torres', 660000, 500, 29194, 14347, 14347),
    (N'CLM-70046', N'SIM-PA-24028', N'2027-05-08', N'2027-05-12', N'COMP', N'COMP', N'Rock hit the windshield on the interstate; cracked windshield.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 27000, 500, 2957, 2457, 0),
    (N'CLM-70047', N'SIS-CP-24010', N'2027-01-12', N'2027-01-13', N'WIND', N'BLDG', N'High winds during the storm blew off shingles; rain came through the opening in the roof into the bedroom.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 8200000, 5000, 23075, 0, 18075),
    (N'CLM-70048', N'SIM-HO6-24005', N'2025-03-25', N'2025-03-25', N'SINKHOLE', N'DWELL', N'Cracks in the walls and floor; engineer confirmed a sinkhole under the foundation.', CAST(NULL AS nvarchar(4000)), N'Tom Reed', 50000, 2500, 51950, 49450, 0),
    (N'CLM-70049', N'SIM-HO4-24044', N'2026-08-08', N'2026-08-16', N'WIND', N'PERSPROP', N'High winds during the storm blew off shingles; rain came through the opening in the roof into the bedroom.', CAST(NULL AS nvarchar(4000)), N'Tom Reed', 40000, 2500, 51950, 49450, 0),
    (N'CLM-70050', N'SIM-PA-24048', N'2026-07-02', N'2026-07-02', N'COLL', N'COLL', N'Insured was driving for Uber with a passenger when another car sideswiped the vehicle.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 18000, 1000, 7014, 0, 0),
    (N'CLM-70051', N'SIM-HO3-24001', N'2027-03-09', N'2027-08-08', N'THEFT', N'PERSPROP', N'Break-in while the insured was on vacation; jewelry and a laptop stolen.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 170000, 1000, 11195, 5098, 5097),
    (N'CLM-70052', N'SIM-HO5-24013', N'2026-12-17', N'2026-12-17', N'EARTHMV', N'DWELL', N'Earthquake shook the house; chimney cracked and foundation shifted.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 550000, 1000, 2353, 0, 0),
    (N'CLM-70053', N'SIM-HO5-24013', N'2026-05-09', N'2026-05-29', N'SEWER', N'DWELL', N'After heavy rain the sewer backed up through the basement floor drain; carpet and drywall ruined.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 550000, 1000, 4767, 0, 0),
    (N'CLM-70054', N'SIM-HO3-24032', N'2026-04-28', N'2026-04-28', N'WEAR', N'DWELL', N'Roof leaking because the shingles are worn out; deterioration over many years, ceiling stained.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 250000, 1000, 29023, 0, 0),
    (N'CLM-70055', N'SIM-DP3-24046', N'2026-04-21', N'2026-04-21', N'SEWER', N'DWELL', N'After heavy rain the sewer backed up through the basement floor drain; carpet and drywall ruined.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 420000, 1000, 8792, 0, 0),
    (N'CLM-70056', N'SIM-BOP-24019', N'2026-05-29', N'2026-05-29', N'EMPDIS', N'BPP', N'Bookkeeper embezzled cash over three months; police report filed.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 160000, 1000, 3937, 0, 0),
    (N'CLM-70057', N'SIM-HO4-24014', N'2026-05-07', N'2026-05-27', N'SEWER', N'PERSPROP', N'After heavy rain the sewer backed up through the basement floor drain; carpet and drywall ruined.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 40000, 500, 4870, 0, 0),
    (N'CLM-70058', N'SIM-PA-24027', N'2026-05-26', N'2026-05-27', N'COMP', N'COMP', N'Insured hit a deer on the highway at night; hood and headlight damaged.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 23000, 500, 3477, 2977, 0),
    (N'CLM-70059', N'SIM-HO4-24014', N'2026-10-20', N'2026-10-20', N'WIND', N'PERSPROP', N'High winds during the storm blew off shingles; rain came through the opening in the roof into the bedroom.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 40000, 500, 3805, 0, 3305),
    (N'CLM-70060', N'SIM-HO4-24024', N'2025-03-29', N'2025-04-03', N'FIRE', N'PERSPROP', N'A grease fire started on the stove and burned the kitchen cabinets; smoke damage through the first floor.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 60000, 500, 6031, 2766, 2765),
    (N'CLM-70061', N'SIM-DP3-24036', N'2026-11-14', N'2026-11-23', N'WIND', N'DWELL', N'Hurricane winds tore off part of the roof and broke windows; wind-driven rain damaged ceilings.', CAST(NULL AS nvarchar(4000)), N'Tom Reed', 770000, 15400, 64850, 49450, 0),
    (N'CLM-70062', N'SIM-PA-24028', N'2026-06-14', N'2026-06-15', N'COMP', N'COMP', N'Insured hit a deer on the highway at night; hood and headlight damaged.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 27000, 500, 7058, 0, 6558),
    (N'CLM-70063', N'SIM-HO6-24015', N'2025-03-02', N'2025-03-04', N'THEFT', N'PERSPROP', N'Break-in while the insured was on vacation; jewelry and a laptop stolen.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 60000, 1000, 6565, 0, 5565),
    (N'CLM-70064', N'SIM-HO6-24045', N'2025-11-10', N'2025-11-24', N'WIND', N'DWELL', N'High winds during the storm blew off shingles; rain came through the opening in the roof into the bedroom.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 50000, 0, 5343, 5343, 0),
    (N'CLM-70065', N'SIM-PA-24027', N'2026-06-17', N'2026-06-18', N'COLL', N'COLL', N'Insured was driving for Uber with a passenger when another car sideswiped the vehicle.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 23000, 1000, 6917, 0, 0),
    (N'CLM-70066', N'SIM-PA-24027', N'2025-08-14', N'2025-09-03', N'COMP', N'COMP', N'Vehicle stolen from the driveway overnight; recovered stripped.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 23000, 500, 10902, 10402, 0),
    (N'CLM-70067', N'SIM-PA-24008', N'2025-11-07', N'2025-11-10', N'COMP', N'COMP', N'Insured hit a deer on the highway at night; hood and headlight damaged.', N'Limit updated on the claim by the adjuster.', N'Dev Shah', 87000, 250, 17851, 0, 17601),
    (N'CLM-70068', N'SIM-BOP-24019', N'2025-12-22', N'2025-12-29', N'THEFT', N'BPP', N'Break-in while the insured was on vacation; jewelry and a laptop stolen.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 160000, 1000, 15826, 14826, 0),
    (N'CLM-70069', N'SIS-CP-24030', N'2025-10-22', N'2025-10-23', N'WATER', N'BPP', N'Supply line to the restroom sink burst overnight; water damage to the shop floor and stock.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 1100000, 5000, 10409, 5409, 0),
    (N'CLM-70070', N'SIM-DP3-24006', N'2026-09-13', N'2026-09-16', N'WIND', N'DWELL', N'High winds during the storm blew off shingles; rain came through the opening in the roof into the bedroom.', N'Limit updated on the claim by the adjuster.', N'Ben Clarke', 660000, 1000, 27023, 0, 26023),
    (N'CLM-70071', N'SIM-HO3-24001', N'2026-12-11', N'2026-12-24', N'THEFT', N'PERSPROP', N'Break-in while the insured was on vacation; jewelry and a laptop stolen.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 170000, 1000, 5988, 4988, 0),
    (N'CLM-70072', N'SIM-HO3-24022', N'2025-09-17', N'2025-10-07', N'SINKHOLE', N'DWELL', N'Cracks in the walls and floor; engineer confirmed a sinkhole under the foundation.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 530000, 2500, 8438, 0, 0),
    (N'CLM-70073', N'SIM-HO3-24031', N'2025-10-02', N'2025-10-04', N'MOLD', N'DWELL', N'Insured found mold behind the bathroom vanity; plumber says it was a slow leak for months.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 270000, 1000, 3661, 2661, 0),
    (N'CLM-70074', N'SIM-PA-24047', N'2026-02-10', N'2026-02-15', N'COLL', N'COLL', N'Insured was driving for Uber with a passenger when another car sideswiped the vehicle.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 38000, 1000, 7133, 0, 0),
    (N'CLM-70075', N'SIM-HO6-24045', N'2025-11-20', N'2025-11-20', N'WIND', N'DWELL', N'High winds during the storm blew off shingles; rain came through the opening in the roof into the bedroom.', CAST(NULL AS nvarchar(4000)), N'Tom Reed', 50000, 2500, 51950, 49450, 0),
    (N'CLM-70076', N'SIM-HO4-24004', N'2025-12-20', N'2025-12-21', N'WIND', N'PERSPROP', N'High winds during the storm blew off shingles; rain came through the opening in the roof into the bedroom.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 25000, 0, 12669, 12669, 0),
    (N'CLM-70077', N'SIM-PA-24008', N'2025-10-18', N'2025-10-22', N'COLL', N'COLL', N'Insured rear-ended another car at a red light; front bumper and radiator damaged.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 0, 0, 1532, 0, 0),
    (N'CLM-70078', N'SIM-HO4-24004', N'2025-09-30', N'2025-10-10', N'SEWER', N'PERSPROP', N'After heavy rain the sewer backed up through the basement floor drain; carpet and drywall ruined.', N'Limit updated on the claim by the adjuster.', N'Chloe Park', 38000, 500, 4435, 0, 3935),
    (N'CLM-70079', N'SIM-HO4-24044', N'2026-11-30', N'2026-12-02', N'FIRE', N'PERSPROP', N'A grease fire started on the stove and burned the kitchen cabinets; smoke damage through the first floor.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 40000, 0, 11656, 11656, 0),
    (N'CLM-70080', N'SIM-PA-24017', N'2026-08-24', N'2026-08-24', N'COLL', N'COLL', N'Insured rear-ended another car at a red light; front bumper and radiator damaged.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 0, 0, 2952, 0, 0),
    (N'CLM-70081', N'SIM-HO5-24033', N'2027-03-01', N'2027-03-01', N'WIND', N'DWELL', N'Hurricane winds tore off part of the roof and broke windows; wind-driven rain damaged ceilings.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 760000, 15200, 22723, 0, 7523),
    (N'CLM-70082', N'SIM-PA-24008', N'2025-07-24', N'2025-07-27', N'COMP', N'COMP', N'Rock hit the windshield on the interstate; cracked windshield.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 58000, 250, 15958, 15708, 0),
    (N'CLM-70083', N'SIM-HO4-24034', N'2025-12-12', N'2025-12-14', N'MOLD', N'PERSPROP', N'Insured found mold behind the bathroom vanity; plumber says it was a slow leak for months.', N'Limit updated on the claim by the adjuster.', N'Dev Shah', 60000, 1000, 7860, 0, 0),
    (N'CLM-70084', N'SIM-HO6-24015', N'2024-12-11', N'2024-12-31', N'THEFT', N'PERSPROP', N'Break-in while the insured was on vacation; jewelry and a laptop stolen.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 60000, 1000, 9984, 4492, 4492),
    (N'CLM-70085', N'SIM-PA-24018', N'2026-09-03', N'2026-09-14', N'COMP', N'COMP', N'Rock hit the windshield on the interstate; cracked windshield.', CAST(NULL AS nvarchar(4000)), N'Dev Shah', 28000, 100, 7355, 0, 7255),
    (N'CLM-70086', N'SIM-PA-24028', N'2026-07-25', N'2026-07-26', N'COMP', N'COMP', N'Vehicle stolen from the driveway overnight; recovered stripped.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 27000, 500, 6295, 0, 5795),
    (N'CLM-70087', N'SIM-BOP-24029', N'2025-07-17', N'2025-08-06', N'THEFT', N'BPP', N'Break-in while the insured was on vacation; jewelry and a laptop stolen.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 400000, 1000, 5471, 2236, 2235),
    (N'CLM-70088', N'SIM-HO5-24023', N'2026-06-20', N'2026-06-26', N'HAIL', N'DWELL', N'Hailstorm damaged the roof shingles and gutters.', CAST(NULL AS nvarchar(4000)), N'Ana Torres', 450000, 500, 8194, 3847, 3847),
    (N'CLM-70089', N'SIM-BOP-24039', N'2026-07-10', N'2026-07-19', N'FIRE', N'BLDG', N'A grease fire started on the stove and burned the kitchen cabinets; smoke damage through the first floor.', CAST(NULL AS nvarchar(4000)), N'Chloe Park', 1600000, 1000, 11504, 5252, 5252),
    (N'CLM-70090', N'SIM-PA-24007', N'2026-01-16', N'2026-01-25', N'COLL', N'COLL', N'Insured rear-ended another car at a red light; front bumper and radiator damaged.', CAST(NULL AS nvarchar(4000)), N'Ben Clarke', 29000, 1000, 7501, 3250, 3251)
) v (n, p, ld, rd, ca, co, de, nt, ad, rl, rdd, g, pa, re)
WHERE NOT EXISTS (SELECT 1 FROM cov.Claim z WHERE z.ClaimNumber = v.n);
GO

INSERT cov.ClaimPayment (ClaimNumber, Amount, Payee, PayeeType, PaymentDate)
SELECT v.n, v.a, v.p, v.t, v.d
FROM (VALUES
    (N'CLM-69901', 1, 46000, N'Aisha Johnson', N'INSURED', N'2026-09-05'),
    (N'CLM-69903', 1, 11500, N'Aisha Johnson', N'INSURED', N'2026-09-05'),
    (N'CLM-69905', 1, 18000, N'Aisha Johnson', N'INSURED', N'2026-09-05'),
    (N'CLM-69906', 1, 5950, N'Omar Garcia', N'INSURED', N'2026-02-06'),
    (N'CLM-70001', 1, 9196, N'Grace Silva', N'INSURED', N'2026-04-02'),
    (N'CLM-70002', 1, 5846, N'Metro Auto Body', N'VENDOR', N'2026-10-05'),
    (N'CLM-70004', 1, 4487, N'Coastal Builders', N'VENDOR', N'2025-10-30'),
    (N'CLM-70005', 1, 7349, N'Coastal Builders', N'VENDOR', N'2025-10-20'),
    (N'CLM-70006', 1, 6591, N'BlueSky Roofing', N'VENDOR', N'2026-03-31'),
    (N'CLM-70009', 1, 27177, N'James Brown', N'INSURED', N'2026-01-23'),
    (N'CLM-70012', 1, 4036, N'SafeGlass Inc', N'VENDOR', N'2025-12-17'),
    (N'CLM-70014', 1, 2396, N'Coastal Builders', N'VENDOR', N'2025-09-10'),
    (N'CLM-70015', 1, 24600, N'Rapid Restore LLC', N'VENDOR', N'2025-12-03'),
    (N'CLM-70015', 2, 24850, N'Rapid Restore LLC', N'VENDOR', N'2025-12-06'),
    (N'CLM-70016', 1, 7706, N'Metro Auto Body', N'VENDOR', N'2025-11-29'),
    (N'CLM-70018', 1, 3928, N'AquaDry Restoration', N'VENDOR', N'2026-05-11'),
    (N'CLM-70019', 1, 3707, N'Grace Garcia', N'INSURED', N'2025-11-06'),
    (N'CLM-70021', 1, 5604, N'BlueSky Roofing', N'VENDOR', N'2026-02-19'),
    (N'CLM-70022', 1, 4564, N'Metro Auto Body', N'VENDOR', N'2026-05-28'),
    (N'CLM-70023', 1, 674, N'AquaDry Restoration', N'VENDOR', N'2025-12-13'),
    (N'CLM-70024', 1, 7926, N'City Plumbing Co', N'VENDOR', N'2026-05-06'),
    (N'CLM-70026', 1, 13036, N'Aisha Haddad', N'INSURED', N'2026-04-13'),
    (N'CLM-70027', 1, 1858, N'BlueSky Roofing', N'VENDOR', N'2025-10-16'),
    (N'CLM-70028', 1, 24600, N'Rapid Restore LLC', N'VENDOR', N'2026-09-16'),
    (N'CLM-70028', 2, 24850, N'Rapid Restore LLC', N'VENDOR', N'2026-09-19'),
    (N'CLM-70030', 1, 10158, N'Metro Auto Body', N'VENDOR', N'2025-07-22'),
    (N'CLM-70032', 1, 24600, N'Rapid Restore LLC', N'VENDOR', N'2025-05-12'),
    (N'CLM-70032', 2, 24850, N'Rapid Restore LLC', N'VENDOR', N'2025-05-15'),
    (N'CLM-70033', 1, 24600, N'Rapid Restore LLC', N'VENDOR', N'2026-08-03'),
    (N'CLM-70033', 2, 24850, N'Rapid Restore LLC', N'VENDOR', N'2026-08-06'),
    (N'CLM-70035', 1, 13829, N'City Plumbing Co', N'VENDOR', N'2025-12-08'),
    (N'CLM-70036', 1, 1850, N'Kevin Chen', N'INSURED', N'2027-04-25'),
    (N'CLM-70037', 1, 3174, N'Coastal Builders', N'VENDOR', N'2026-06-13'),
    (N'CLM-70038', 1, 4638, N'Coastal Builders', N'VENDOR', N'2026-04-04'),
    (N'CLM-70042', 1, 3192, N'Grace Garcia', N'INSURED', N'2025-11-02'),
    (N'CLM-70044', 1, 24600, N'Rapid Restore LLC', N'VENDOR', N'2026-06-22'),
    (N'CLM-70044', 2, 24850, N'Rapid Restore LLC', N'VENDOR', N'2026-06-25'),
    (N'CLM-70045', 1, 14347, N'BlueSky Roofing', N'VENDOR', N'2025-10-29'),
    (N'CLM-70046', 1, 2457, N'Coastal Builders', N'VENDOR', N'2027-05-22'),
    (N'CLM-70048', 1, 24600, N'Rapid Restore LLC', N'VENDOR', N'2025-03-31'),
    (N'CLM-70048', 2, 24850, N'Rapid Restore LLC', N'VENDOR', N'2025-04-03'),
    (N'CLM-70049', 1, 24600, N'Rapid Restore LLC', N'VENDOR', N'2026-08-22'),
    (N'CLM-70049', 2, 24850, N'Rapid Restore LLC', N'VENDOR', N'2026-08-25'),
    (N'CLM-70051', 1, 5098, N'Aisha Johnson', N'INSURED', N'2027-03-19'),
    (N'CLM-70058', 1, 2977, N'Carlos Lopez', N'INSURED', N'2026-06-06'),
    (N'CLM-70060', 1, 2766, N'AquaDry Restoration', N'VENDOR', N'2025-04-13'),
    (N'CLM-70061', 1, 24600, N'Rapid Restore LLC', N'VENDOR', N'2026-11-29'),
    (N'CLM-70061', 2, 24850, N'Rapid Restore LLC', N'VENDOR', N'2026-12-02'),
    (N'CLM-70064', 1, 5343, N'BlueSky Roofing', N'VENDOR', N'2025-12-01'),
    (N'CLM-70066', 1, 10402, N'Carlos Lopez', N'INSURED', N'2026-02-23'),
    (N'CLM-70068', 1, 14826, N'Coastal Builders', N'VENDOR', N'2026-01-08'),
    (N'CLM-70069', 1, 5409, N'Coastal Builders', N'VENDOR', N'2025-11-02'),
    (N'CLM-70071', 1, 4988, N'BlueSky Roofing', N'VENDOR', N'2027-01-03'),
    (N'CLM-70073', 1, 2661, N'Aisha Smith', N'INSURED', N'2025-10-09'),
    (N'CLM-70075', 1, 24600, N'Rapid Restore LLC', N'VENDOR', N'2025-11-26'),
    (N'CLM-70075', 2, 24850, N'Rapid Restore LLC', N'VENDOR', N'2025-11-29'),
    (N'CLM-70076', 1, 12669, N'SafeGlass Inc', N'VENDOR', N'2025-12-28'),
    (N'CLM-70079', 1, 11656, N'SafeGlass Inc', N'VENDOR', N'2026-12-09'),
    (N'CLM-70082', 1, 15708, N'Grace Nguyen', N'INSURED', N'2025-08-06'),
    (N'CLM-70084', 1, 4492, N'AquaDry Restoration', N'VENDOR', N'2025-11-16'),
    (N'CLM-70087', 1, 2236, N'City Plumbing Co', N'VENDOR', N'2025-11-06'),
    (N'CLM-70088', 1, 3847, N'AquaDry Restoration', N'VENDOR', N'2026-07-06'),
    (N'CLM-70089', 1, 5252, N'Coastal Builders', N'VENDOR', N'2026-07-29'),
    (N'CLM-70090', 1, 3250, N'Coastal Builders', N'VENDOR', N'2026-02-04')
) v (n, s, a, p, t, d)
WHERE NOT EXISTS (SELECT 1 FROM cov.ClaimPayment z WHERE z.ClaimNumber = v.n AND z.Amount = v.a AND z.PaymentDate = v.d);
GO

SELECT (SELECT COUNT(*) FROM cov.Form) AS Forms, (SELECT COUNT(*) FROM cov.FormSection) AS Sections, (SELECT COUNT(*) FROM cov.Policy) AS Policies, (SELECT COUNT(*) FROM cov.Claim) AS Claims, (SELECT COUNT(*) FROM cov.ClaimPayment) AS Payments;
GO
