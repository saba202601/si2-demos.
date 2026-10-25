-- SI² Coverage CDM: classes, catalog, terms, endorsements and synthetic policies (schema cov).
-- Version 2026.10. Generated from the same catalog as SI2_Coverage_Ontology.ttl. Illustrative.
SET NOCOUNT ON;
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'cov') EXEC('CREATE SCHEMA cov');
GO
IF OBJECT_ID('cov.Levels') IS NOT NULL DROP TABLE cov.[Levels];
CREATE TABLE cov.[Levels] (
  [attach_level] NVARCHAR(40) NOT NULL,
  [meaning] NVARCHAR(120) NULL,
  CONSTRAINT PK_cov_Levels PRIMARY KEY ([attach_level])
);
INSERT INTO cov.[Levels] ([attach_level], [meaning]) VALUES
(N'Policy', N'Applies to the whole policy term'),
(N'Line', N'Applies to one line or coverage part in the policy'),
(N'Coverage', N'Attaches to another coverage and follows it'),
(N'Object', N'Attaches to one insured object'),
(N'Endorsement', N'Changes coverage at any of the other levels');
GO
IF OBJECT_ID('cov.Classes') IS NOT NULL DROP TABLE cov.[Classes];
CREATE TABLE cov.[Classes] (
  [class] NVARCHAR(120) NOT NULL,
  [parent_class] NVARCHAR(120) NULL,
  [kind] NVARCHAR(40) NULL,
  [depth] BIGINT NULL,
  [definition] NVARCHAR(120) NULL,
  [path] NVARCHAR(400) NULL,
  CONSTRAINT PK_cov_Classes PRIMARY KEY ([class])
);
INSERT INTO cov.[Classes] ([class], [parent_class], [kind], [depth], [definition], [path]) VALUES
(N'Coverage', N'', N'Coverage', 0, N'A promise to pay or defend for a defined loss, under stated terms.', N'Coverage'),
(N'FirstPartyCoverage', N'Coverage', N'Coverage', 1, N'Pays the insured for its own loss.', N'Coverage > FirstPartyCoverage'),
(N'PropertyCoverage', N'FirstPartyCoverage', N'Coverage', 2, N'Direct physical loss to property.', N'Coverage > FirstPartyCoverage > PropertyCoverage'),
(N'DwellingCoverage', N'PropertyCoverage', N'Coverage', 3, N'The home and structures on a residence premises.', N'Coverage > FirstPartyCoverage > PropertyCoverage > DwellingCoverage'),
(N'PersonalPropertyCoverage', N'PropertyCoverage', N'Coverage', 3, N'Contents and belongings of a household.', N'Coverage > FirstPartyCoverage > PropertyCoverage > PersonalPropertyCoverage'),
(N'CommercialBuildingCoverage', N'PropertyCoverage', N'Coverage', 3, N'A commercial building.', N'Coverage > FirstPartyCoverage > PropertyCoverage > CommercialBuildingCoverage'),
(N'BusinessPersonalPropertyCoverage', N'PropertyCoverage', N'Coverage', 3, N'Contents, stock and equipment of a business.', N'Coverage > FirstPartyCoverage > PropertyCoverage > BusinessPersonalPropertyCoverage'),
(N'AutoPhysicalDamageCoverage', N'PropertyCoverage', N'Coverage', 3, N'Damage to a covered vehicle.', N'Coverage > FirstPartyCoverage > PropertyCoverage > AutoPhysicalDamageCoverage'),
(N'CollisionCoverage', N'AutoPhysicalDamageCoverage', N'Coverage', 4, N'Collision with another object or upset.', N'Coverage > FirstPartyCoverage > PropertyCoverage > AutoPhysicalDamageCoverage > CollisionCoverage'),
(N'ComprehensiveCoverage', N'AutoPhysicalDamageCoverage', N'Coverage', 4, N'Other than collision: theft, fire, hail, glass.', N'Coverage > FirstPartyCoverage > PropertyCoverage > AutoPhysicalDamageCoverage > ComprehensiveCoverage'),
(N'TimeElementCoverage', N'FirstPartyCoverage', N'Coverage', 2, N'Loss that grows with time after property damage.', N'Coverage > FirstPartyCoverage > TimeElementCoverage'),
(N'LossOfUseCoverage', N'TimeElementCoverage', N'Coverage', 3, N'Additional living expense and fair rental value.', N'Coverage > FirstPartyCoverage > TimeElementCoverage > LossOfUseCoverage'),
(N'BusinessIncomeCoverage', N'TimeElementCoverage', N'Coverage', 3, N'Lost income and extra expense of a business.', N'Coverage > FirstPartyCoverage > TimeElementCoverage > BusinessIncomeCoverage'),
(N'FirstPartyInjuryCoverage', N'FirstPartyCoverage', N'Coverage', 2, N'Medical and income benefits regardless of fault.', N'Coverage > FirstPartyCoverage > FirstPartyInjuryCoverage'),
(N'PersonalInjuryProtection', N'FirstPartyInjuryCoverage', N'Coverage', 3, N'No-fault benefits required in some states.', N'Coverage > FirstPartyCoverage > FirstPartyInjuryCoverage > PersonalInjuryProtection'),
(N'MedicalPaymentsCoverage', N'FirstPartyInjuryCoverage', N'Coverage', 3, N'Medical expenses of others or occupants, regardless of fault.', N'Coverage > FirstPartyCoverage > FirstPartyInjuryCoverage > MedicalPaymentsCoverage'),
(N'LiabilityCoverage', N'Coverage', N'Coverage', 1, N'Pays others for injury or damage the insured is legally liable for, and defends.', N'Coverage > LiabilityCoverage'),
(N'BodilyInjuryPropertyDamageLiability', N'LiabilityCoverage', N'Coverage', 2, N'Bodily injury and property damage to others.', N'Coverage > LiabilityCoverage > BodilyInjuryPropertyDamageLiability'),
(N'AutoLiability', N'BodilyInjuryPropertyDamageLiability', N'Coverage', 3, N'Liability from owning or using autos.', N'Coverage > LiabilityCoverage > BodilyInjuryPropertyDamageLiability > AutoLiability'),
(N'PremisesOperationsLiability', N'BodilyInjuryPropertyDamageLiability', N'Coverage', 3, N'Liability from premises and operations.', N'Coverage > LiabilityCoverage > BodilyInjuryPropertyDamageLiability > PremisesOperationsLiability'),
(N'PersonalLiability', N'BodilyInjuryPropertyDamageLiability', N'Coverage', 3, N'Liability of a household.', N'Coverage > LiabilityCoverage > BodilyInjuryPropertyDamageLiability > PersonalLiability'),
(N'ProductsCompletedOperationsLiability', N'LiabilityCoverage', N'Coverage', 2, N'Liability from products and completed work.', N'Coverage > LiabilityCoverage > ProductsCompletedOperationsLiability'),
(N'PersonalAdvertisingInjuryLiability', N'LiabilityCoverage', N'Coverage', 2, N'Libel, slander, false arrest, advertising injury.', N'Coverage > LiabilityCoverage > PersonalAdvertisingInjuryLiability'),
(N'EmployersLiability', N'LiabilityCoverage', N'Coverage', 2, N'Employee injury claims outside workers'' compensation.', N'Coverage > LiabilityCoverage > EmployersLiability'),
(N'UninsuredMotoristsCoverage', N'Coverage', N'Coverage', 1, N'Injury caused by an uninsured or underinsured driver.', N'Coverage > UninsuredMotoristsCoverage'),
(N'StatutoryBenefitsCoverage', N'Coverage', N'Coverage', 1, N'Benefits set by statute.', N'Coverage > StatutoryBenefitsCoverage'),
(N'WorkersCompensationBenefits', N'StatutoryBenefitsCoverage', N'Coverage', 2, N'Benefits under the workers'' compensation law of a state.', N'Coverage > StatutoryBenefitsCoverage > WorkersCompensationBenefits'),
(N'CoverageTerm', N'', N'Term', 0, N'A value that defines how much or how a coverage pays.', N'CoverageTerm'),
(N'Limit', N'CoverageTerm', N'Term', 1, N'Most the coverage pays.', N'CoverageTerm > Limit'),
(N'PerOccurrenceLimit', N'Limit', N'Term', 2, N'Most paid for one occurrence.', N'CoverageTerm > Limit > PerOccurrenceLimit'),
(N'AggregateLimit', N'Limit', N'Term', 2, N'Most paid in the policy term.', N'CoverageTerm > Limit > AggregateLimit'),
(N'PerPersonLimit', N'Limit', N'Term', 2, N'Most paid for one person.', N'CoverageTerm > Limit > PerPersonLimit'),
(N'CombinedSingleLimit', N'Limit', N'Term', 2, N'One limit for bodily injury and property damage.', N'CoverageTerm > Limit > CombinedSingleLimit'),
(N'Sublimit', N'Limit', N'Term', 2, N'A smaller limit inside a parent limit.', N'CoverageTerm > Limit > Sublimit'),
(N'Deductible', N'CoverageTerm', N'Term', 1, N'Amount the insured bears before the coverage pays.', N'CoverageTerm > Deductible'),
(N'FlatDeductible', N'Deductible', N'Term', 2, N'A fixed amount.', N'CoverageTerm > Deductible > FlatDeductible'),
(N'PercentDeductible', N'Deductible', N'Term', 2, N'A percentage of a stated value.', N'CoverageTerm > Deductible > PercentDeductible'),
(N'HurricaneDeductible', N'PercentDeductible', N'Term', 3, N'Percentage deductible for a hurricane or named storm.', N'CoverageTerm > Deductible > PercentDeductible > HurricaneDeductible'),
(N'WindHailDeductible', N'PercentDeductible', N'Term', 3, N'Percentage deductible for windstorm or hail.', N'CoverageTerm > Deductible > PercentDeductible > WindHailDeductible'),
(N'EarthquakeDeductible', N'PercentDeductible', N'Term', 3, N'Percentage deductible for earthquake.', N'CoverageTerm > Deductible > PercentDeductible > EarthquakeDeductible'),
(N'Coinsurance', N'CoverageTerm', N'Term', 1, N'Share of value the insured must carry.', N'CoverageTerm > Coinsurance'),
(N'Valuation', N'CoverageTerm', N'Term', 1, N'How a loss is valued.', N'CoverageTerm > Valuation'),
(N'WaitingPeriod', N'CoverageTerm', N'Term', 1, N'Time before a time-element coverage starts.', N'CoverageTerm > WaitingPeriod'),
(N'Endorsement', N'', N'Endorsement', 0, N'A form that changes the policy.', N'Endorsement'),
(N'AddCoverageEndorsement', N'Endorsement', N'Endorsement', 1, N'Adds a coverage.', N'Endorsement > AddCoverageEndorsement'),
(N'ModifyTermEndorsement', N'Endorsement', N'Endorsement', 1, N'Changes a limit, deductible or other term.', N'Endorsement > ModifyTermEndorsement'),
(N'BroadenEndorsement', N'Endorsement', N'Endorsement', 1, N'Widens what a coverage covers or who is insured.', N'Endorsement > BroadenEndorsement'),
(N'RestrictEndorsement', N'Endorsement', N'Endorsement', 1, N'Narrows a coverage or its valuation.', N'Endorsement > RestrictEndorsement'),
(N'ExclusionEndorsement', N'Endorsement', N'Endorsement', 1, N'Removes a cause of loss, object or activity.', N'Endorsement > ExclusionEndorsement'),
(N'StateAmendatoryEndorsement', N'Endorsement', N'Endorsement', 1, N'Changes conditions to meet a state''s law.', N'Endorsement > StateAmendatoryEndorsement');
GO
IF OBJECT_ID('cov.CoverageDef') IS NOT NULL DROP TABLE cov.[CoverageDef];
CREATE TABLE cov.[CoverageDef] (
  [coverage_code] NVARCHAR(40) NOT NULL,
  [name] NVARCHAR(120) NULL,
  [line] NVARCHAR(40) NULL,
  [lob] NVARCHAR(40) NULL,
  [class] NVARCHAR(120) NULL,
  [class_path] NVARCHAR(400) NULL,
  [attach_level] NVARCHAR(40) NULL,
  [attaches_to_object] NVARCHAR(40) NULL,
  [parent_coverage_code] NVARCHAR(40) NULL,
  CONSTRAINT PK_cov_CoverageDef PRIMARY KEY ([coverage_code])
);
INSERT INTO cov.[CoverageDef] ([coverage_code], [name], [line], [lob], [class], [class_path], [attach_level], [attaches_to_object], [parent_coverage_code]) VALUES
(N'HO_A', N'Coverage A - Dwelling', N'Personal', N'HO', N'DwellingCoverage', N'Coverage > FirstPartyCoverage > PropertyCoverage > DwellingCoverage', N'Object', N'Dwelling', N''),
(N'HO_B', N'Coverage B - Other Structures', N'Personal', N'HO', N'DwellingCoverage', N'Coverage > FirstPartyCoverage > PropertyCoverage > DwellingCoverage', N'Coverage', N'', N'HO_A'),
(N'HO_C', N'Coverage C - Personal Property', N'Personal', N'HO', N'PersonalPropertyCoverage', N'Coverage > FirstPartyCoverage > PropertyCoverage > PersonalPropertyCoverage', N'Coverage', N'', N'HO_A'),
(N'HO_D', N'Coverage D - Loss of Use', N'Personal', N'HO', N'LossOfUseCoverage', N'Coverage > FirstPartyCoverage > TimeElementCoverage > LossOfUseCoverage', N'Coverage', N'', N'HO_A'),
(N'HO_E', N'Coverage E - Personal Liability', N'Personal', N'HO', N'PersonalLiability', N'Coverage > LiabilityCoverage > BodilyInjuryPropertyDamageLiability > PersonalLiability', N'Line', N'', N''),
(N'HO_F', N'Coverage F - Medical Payments to Others', N'Personal', N'HO', N'MedicalPaymentsCoverage', N'Coverage > FirstPartyCoverage > FirstPartyInjuryCoverage > MedicalPaymentsCoverage', N'Line', N'', N''),
(N'HO_SPP', N'Scheduled Personal Property', N'Personal', N'HO', N'PersonalPropertyCoverage', N'Coverage > FirstPartyCoverage > PropertyCoverage > PersonalPropertyCoverage', N'Policy', N'', N''),
(N'HO_EQ', N'Earthquake', N'Personal', N'HO', N'DwellingCoverage', N'Coverage > FirstPartyCoverage > PropertyCoverage > DwellingCoverage', N'Coverage', N'', N'HO_A'),
(N'PA_BI', N'Bodily Injury Liability', N'Personal', N'PA', N'AutoLiability', N'Coverage > LiabilityCoverage > BodilyInjuryPropertyDamageLiability > AutoLiability', N'Line', N'', N''),
(N'PA_PD', N'Property Damage Liability', N'Personal', N'PA', N'AutoLiability', N'Coverage > LiabilityCoverage > BodilyInjuryPropertyDamageLiability > AutoLiability', N'Line', N'', N''),
(N'PA_UM', N'Uninsured Motorists', N'Personal', N'PA', N'UninsuredMotoristsCoverage', N'Coverage > UninsuredMotoristsCoverage', N'Line', N'', N''),
(N'PA_PIP', N'Personal Injury Protection', N'Personal', N'PA', N'PersonalInjuryProtection', N'Coverage > FirstPartyCoverage > FirstPartyInjuryCoverage > PersonalInjuryProtection', N'Line', N'', N''),
(N'PA_MED', N'Medical Payments', N'Personal', N'PA', N'MedicalPaymentsCoverage', N'Coverage > FirstPartyCoverage > FirstPartyInjuryCoverage > MedicalPaymentsCoverage', N'Line', N'', N''),
(N'PA_COLL', N'Collision', N'Personal', N'PA', N'CollisionCoverage', N'Coverage > FirstPartyCoverage > PropertyCoverage > AutoPhysicalDamageCoverage > CollisionCoverage', N'Object', N'Vehicle', N''),
(N'PA_COMP', N'Comprehensive', N'Personal', N'PA', N'ComprehensiveCoverage', N'Coverage > FirstPartyCoverage > PropertyCoverage > AutoPhysicalDamageCoverage > ComprehensiveCoverage', N'Object', N'Vehicle', N''),
(N'CP_BLDG', N'Building', N'Commercial', N'CP', N'CommercialBuildingCoverage', N'Coverage > FirstPartyCoverage > PropertyCoverage > CommercialBuildingCoverage', N'Object', N'Building', N''),
(N'CP_BPP', N'Business Personal Property', N'Commercial', N'CP', N'BusinessPersonalPropertyCoverage', N'Coverage > FirstPartyCoverage > PropertyCoverage > BusinessPersonalPropertyCoverage', N'Object', N'Building', N''),
(N'CP_BI', N'Business Income and Extra Expense', N'Commercial', N'CP', N'BusinessIncomeCoverage', N'Coverage > FirstPartyCoverage > TimeElementCoverage > BusinessIncomeCoverage', N'Coverage', N'', N'CP_BLDG'),
(N'GL_OCC', N'Coverage A - Bodily Injury and Property Damage', N'Commercial', N'GL', N'PremisesOperationsLiability', N'Coverage > LiabilityCoverage > BodilyInjuryPropertyDamageLiability > PremisesOperationsLiability', N'Line', N'', N''),
(N'GL_PAI', N'Coverage B - Personal and Advertising Injury', N'Commercial', N'GL', N'PersonalAdvertisingInjuryLiability', N'Coverage > LiabilityCoverage > PersonalAdvertisingInjuryLiability', N'Line', N'', N''),
(N'GL_MED', N'Coverage C - Medical Payments', N'Commercial', N'GL', N'MedicalPaymentsCoverage', N'Coverage > FirstPartyCoverage > FirstPartyInjuryCoverage > MedicalPaymentsCoverage', N'Line', N'', N''),
(N'GL_PCO', N'Products-Completed Operations', N'Commercial', N'GL', N'ProductsCompletedOperationsLiability', N'Coverage > LiabilityCoverage > ProductsCompletedOperationsLiability', N'Line', N'', N''),
(N'CA_LIAB', N'Auto Liability', N'Commercial', N'CA', N'AutoLiability', N'Coverage > LiabilityCoverage > BodilyInjuryPropertyDamageLiability > AutoLiability', N'Line', N'', N''),
(N'CA_UM', N'Uninsured Motorists', N'Commercial', N'CA', N'UninsuredMotoristsCoverage', N'Coverage > UninsuredMotoristsCoverage', N'Line', N'', N''),
(N'CA_PIP', N'Personal Injury Protection', N'Commercial', N'CA', N'PersonalInjuryProtection', N'Coverage > FirstPartyCoverage > FirstPartyInjuryCoverage > PersonalInjuryProtection', N'Line', N'', N''),
(N'CA_COLL', N'Collision', N'Commercial', N'CA', N'CollisionCoverage', N'Coverage > FirstPartyCoverage > PropertyCoverage > AutoPhysicalDamageCoverage > CollisionCoverage', N'Object', N'Vehicle', N''),
(N'CA_COMP', N'Comprehensive', N'Commercial', N'CA', N'ComprehensiveCoverage', N'Coverage > FirstPartyCoverage > PropertyCoverage > AutoPhysicalDamageCoverage > ComprehensiveCoverage', N'Object', N'Vehicle', N''),
(N'WC_PART1', N'Part One - Workers'' Compensation', N'Commercial', N'WC', N'WorkersCompensationBenefits', N'Coverage > StatutoryBenefitsCoverage > WorkersCompensationBenefits', N'Line', N'', N''),
(N'WC_EL', N'Part Two - Employers Liability', N'Commercial', N'WC', N'EmployersLiability', N'Coverage > LiabilityCoverage > EmployersLiability', N'Line', N'', N'');
GO
IF OBJECT_ID('cov.CoverageTermDef') IS NOT NULL DROP TABLE cov.[CoverageTermDef];
CREATE TABLE cov.[CoverageTermDef] (
  [coverage_code] NVARCHAR(40) NULL,
  [term_code] NVARCHAR(40) NULL,
  [term_class] NVARCHAR(40) NULL,
  [data_type] NVARCHAR(40) NULL,
  [unit] NVARCHAR(40) NULL,
  [options] NVARCHAR(40) NULL,
  [rule] NVARCHAR(40) NULL
);
INSERT INTO cov.[CoverageTermDef] ([coverage_code], [term_code], [term_class], [data_type], [unit], [options], [rule]) VALUES
(N'HO_A', N'LIMIT', N'Limit', N'AMOUNT', N'USD', N'', N'Insured to replacement cost'),
(N'HO_A', N'VALUATION', N'Valuation', N'CODE', N'', N'RC|ACV', N'Default RC'),
(N'HO_A', N'AOP_DED', N'FlatDeductible', N'AMOUNT', N'USD', N'500|1000|2500|5000', N'Default 1000'),
(N'HO_A', N'HURR_DED', N'HurricaneDeductible', N'PERCENT', N'% of HO_A', N'2|5|10', N'Policy level where mandatory'),
(N'HO_B', N'LIMIT', N'Sublimit', N'AMOUNT', N'USD', N'', N'10% of HO_A'),
(N'HO_C', N'LIMIT', N'Sublimit', N'AMOUNT', N'USD', N'', N'50% of HO_A'),
(N'HO_D', N'LIMIT', N'Sublimit', N'AMOUNT', N'USD', N'', N'20% of HO_A'),
(N'HO_E', N'LIMIT', N'PerOccurrenceLimit', N'AMOUNT', N'USD', N'100000|300000|500000', N'Default 300000'),
(N'HO_F', N'LIMIT', N'PerPersonLimit', N'AMOUNT', N'USD', N'1000|5000', N'Default 5000'),
(N'HO_SPP', N'LIMIT', N'Limit', N'AMOUNT', N'USD', N'', N'Sum of scheduled items'),
(N'HO_EQ', N'EQ_DED', N'EarthquakeDeductible', N'PERCENT', N'% of HO_A', N'10|15|20', N'Default 15'),
(N'PA_BI', N'PER_PERSON', N'PerPersonLimit', N'AMOUNT', N'USD', N'25000|50000|100000|250000', N''),
(N'PA_BI', N'PER_ACCIDENT', N'PerOccurrenceLimit', N'AMOUNT', N'USD', N'50000|100000|300000|500000', N''),
(N'PA_PD', N'LIMIT', N'PerOccurrenceLimit', N'AMOUNT', N'USD', N'25000|50000|100000', N''),
(N'PA_UM', N'PER_PERSON', N'PerPersonLimit', N'AMOUNT', N'USD', N'', N'Up to BI limits'),
(N'PA_PIP', N'LIMIT', N'PerPersonLimit', N'AMOUNT', N'USD', N'', N'State minimum'),
(N'PA_MED', N'LIMIT', N'PerPersonLimit', N'AMOUNT', N'USD', N'1000|5000|10000', N''),
(N'PA_COLL', N'DED', N'FlatDeductible', N'AMOUNT', N'USD', N'250|500|1000', N'Default 500'),
(N'PA_COMP', N'DED', N'FlatDeductible', N'AMOUNT', N'USD', N'100|250|500|1000', N'Default 250'),
(N'CP_BLDG', N'LIMIT', N'Limit', N'AMOUNT', N'USD', N'', N'Insured value'),
(N'CP_BLDG', N'COINS', N'Coinsurance', N'CODE', N'', N'80|90|100', N'Default 90'),
(N'CP_BLDG', N'VALUATION', N'Valuation', N'CODE', N'', N'RC|ACV|AGREED', N'Default RC'),
(N'CP_BLDG', N'AOP_DED', N'FlatDeductible', N'AMOUNT', N'USD', N'1000|5000|10000|25000', N'Default 5000'),
(N'CP_BLDG', N'WIND_DED', N'WindHailDeductible', N'PERCENT', N'% of building value', N'1|2|5', N'Where mandatory'),
(N'CP_BPP', N'LIMIT', N'Limit', N'AMOUNT', N'USD', N'', N'Insured value'),
(N'CP_BI', N'LIMIT', N'Limit', N'AMOUNT', N'USD', N'', N'12 months of income'),
(N'CP_BI', N'WAITING', N'WaitingPeriod', N'CODE', N'hours', N'24|72', N'Default 72'),
(N'GL_OCC', N'EACH_OCC', N'PerOccurrenceLimit', N'AMOUNT', N'USD', N'500000|1000000|2000000', N'Default 1000000'),
(N'GL_OCC', N'GEN_AGG', N'AggregateLimit', N'AMOUNT', N'USD', N'', N'2 x each occurrence'),
(N'GL_PAI', N'LIMIT', N'PerPersonLimit', N'AMOUNT', N'USD', N'', N'Equal to each occurrence'),
(N'GL_MED', N'LIMIT', N'PerPersonLimit', N'AMOUNT', N'USD', N'5000|10000', N'Default 5000'),
(N'GL_PCO', N'AGG', N'AggregateLimit', N'AMOUNT', N'USD', N'', N'Equal to general aggregate'),
(N'CA_LIAB', N'CSL', N'CombinedSingleLimit', N'AMOUNT', N'USD', N'500000|1000000|2000000', N'Default 1000000'),
(N'CA_UM', N'LIMIT', N'CombinedSingleLimit', N'AMOUNT', N'USD', N'', N'Up to CSL'),
(N'CA_PIP', N'LIMIT', N'PerPersonLimit', N'AMOUNT', N'USD', N'', N'State minimum'),
(N'CA_COLL', N'DED', N'FlatDeductible', N'AMOUNT', N'USD', N'500|1000|2500', N'Default 1000'),
(N'CA_COMP', N'DED', N'FlatDeductible', N'AMOUNT', N'USD', N'500|1000|2500', N'Default 1000'),
(N'WC_PART1', N'LIMIT', N'Limit', N'CODE', N'', N'STATUTORY', N'Statutory'),
(N'WC_EL', N'EACH_ACC', N'PerOccurrenceLimit', N'AMOUNT', N'USD', N'100000|500000|1000000', N'Default 1000000'),
(N'WC_EL', N'DIS_POL', N'AggregateLimit', N'AMOUNT', N'USD', N'', N'Equal to each accident'),
(N'WC_EL', N'DIS_EE', N'PerPersonLimit', N'AMOUNT', N'USD', N'', N'Equal to each accident');
GO
IF OBJECT_ID('cov.CoverageApplicability') IS NOT NULL DROP TABLE cov.[CoverageApplicability];
CREATE TABLE cov.[CoverageApplicability] (
  [applicability_id] NVARCHAR(40) NOT NULL,
  [coverage_code] NVARCHAR(40) NULL,
  [term_code] NVARCHAR(40) NULL,
  [country] NVARCHAR(40) NULL,
  [state] NVARCHAR(40) NULL,
  [company] NVARCHAR(40) NULL,
  [line] NVARCHAR(40) NULL,
  [lob] NVARCHAR(40) NULL,
  [product] NVARCHAR(40) NULL,
  [object] NVARCHAR(40) NULL,
  [module] NVARCHAR(40) NULL,
  [effective_from] NVARCHAR(40) NULL,
  [effective_to] NVARCHAR(40) NULL,
  [offer_status] NVARCHAR(40) NULL,
  [default_value] NVARCHAR(40) NULL,
  [specificity] BIGINT NULL,
  [reason] NVARCHAR(120) NULL,
  CONSTRAINT PK_cov_CoverageApplicability PRIMARY KEY ([applicability_id])
);
INSERT INTO cov.[CoverageApplicability] ([applicability_id], [coverage_code], [term_code], [country], [state], [company], [line], [lob], [product], [object], [module], [effective_from], [effective_to], [offer_status], [default_value], [specificity], [reason]) VALUES
(N'CA001', N'HO_A', N'', N'*', N'*', N'*', N'Personal', N'HO', N'HO-3 2024', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'', 2, N'Base coverage of the HO-3 form.'),
(N'CA002', N'HO_B', N'', N'*', N'*', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'10% of HO_A', 1, N'Follows Coverage A.'),
(N'CA003', N'HO_C', N'', N'*', N'*', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'50% of HO_A', 1, N'Follows Coverage A.'),
(N'CA004', N'HO_D', N'', N'*', N'*', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'20% of HO_A', 1, N'Follows Coverage A.'),
(N'CA005', N'HO_E', N'', N'*', N'*', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'300000', 1, N'Section II liability.'),
(N'CA006', N'HO_F', N'', N'*', N'*', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'5000', 1, N'Section II medical payments.'),
(N'CA007', N'HO_SPP', N'', N'*', N'*', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Offered', N'', 1, N'By endorsement.'),
(N'CA008', N'HO_EQ', N'', N'*', N'*', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Not available', N'', 1, N'Not offered countrywide in this illustration.'),
(N'CA009', N'HO_EQ', N'', N'*', N'CA', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Offered', N'', 2, N'Earthquake must be offered in California.'),
(N'CA010', N'HO_A', N'HURR_DED', N'*', N'*', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Not available', N'', 1, N'No hurricane deductible outside listed states.'),
(N'CA011', N'HO_A', N'HURR_DED', N'*', N'FL', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'2', 2, N'Florida hurricane deductible, policy level.'),
(N'CA012', N'HO_A', N'HURR_DED', N'*', N'TX', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'2', 2, N'Coastal windstorm deductible.'),
(N'CA013', N'PA_BI', N'', N'*', N'*', N'*', N'Personal', N'PA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'25000/50000', 1, N'Financial responsibility law.'),
(N'CA014', N'PA_PD', N'', N'*', N'*', N'*', N'Personal', N'PA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'25000', 1, N'Financial responsibility law.'),
(N'CA015', N'PA_UM', N'', N'*', N'*', N'*', N'Personal', N'PA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Offered', N'', 1, N'Rejection must be signed where allowed.'),
(N'CA016', N'PA_PIP', N'', N'*', N'*', N'*', N'Personal', N'PA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Not available', N'', 1, N'Not a no-fault state.'),
(N'CA017', N'PA_PIP', N'', N'*', N'FL', N'*', N'Personal', N'PA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'10000', 2, N'Florida no-fault.'),
(N'CA018', N'PA_PIP', N'', N'*', N'NY', N'*', N'Personal', N'PA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'50000', 2, N'New York no-fault.'),
(N'CA019', N'PA_PIP', N'', N'*', N'MI', N'*', N'Personal', N'PA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'', 2, N'Michigan no-fault; levels chosen by the insured.'),
(N'CA020', N'PA_PIP', N'', N'*', N'NJ', N'*', N'Personal', N'PA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'', 2, N'New Jersey no-fault.'),
(N'CA021', N'PA_COLL', N'', N'*', N'*', N'*', N'Personal', N'PA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Offered', N'500', 1, N'Optional physical damage.'),
(N'CA022', N'PA_COMP', N'', N'*', N'*', N'*', N'Personal', N'PA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Offered', N'250', 1, N'Optional physical damage.'),
(N'CA023', N'CP_BLDG', N'', N'*', N'*', N'*', N'Commercial', N'CP', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Offered', N'', 1, N'Building or contents, at least one.'),
(N'CA024', N'CP_BPP', N'', N'*', N'*', N'*', N'Commercial', N'CP', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Offered', N'', 1, N'Building or contents, at least one.'),
(N'CA025', N'CP_BI', N'', N'*', N'*', N'*', N'Commercial', N'CP', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Offered', N'', 1, N'Time element.'),
(N'CA026', N'CP_BLDG', N'WIND_DED', N'*', N'*', N'*', N'Commercial', N'CP', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Offered', N'', 1, N'Optional elsewhere.'),
(N'CA027', N'CP_BLDG', N'WIND_DED', N'*', N'TX', N'*', N'Commercial', N'CP', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'2', 2, N'Texas coastal wind and hail.'),
(N'CA028', N'CP_BLDG', N'WIND_DED', N'*', N'FL', N'*', N'Commercial', N'CP', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'2', 2, N'Florida named storm.'),
(N'CA029', N'GL_OCC', N'', N'*', N'*', N'*', N'Commercial', N'GL', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'1000000', 1, N'Coverage A.'),
(N'CA030', N'GL_PAI', N'', N'*', N'*', N'*', N'Commercial', N'GL', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'', 1, N'Coverage B.'),
(N'CA031', N'GL_MED', N'', N'*', N'*', N'*', N'Commercial', N'GL', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Offered', N'5000', 1, N'Coverage C.'),
(N'CA032', N'GL_PCO', N'', N'*', N'*', N'*', N'Commercial', N'GL', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'', 1, N'Products-completed operations aggregate.'),
(N'CA033', N'CA_LIAB', N'', N'*', N'*', N'*', N'Commercial', N'CA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'1000000', 1, N'Auto liability.'),
(N'CA034', N'CA_UM', N'', N'*', N'*', N'*', N'Commercial', N'CA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Offered', N'', 1, N'Rejection must be signed where allowed.'),
(N'CA035', N'CA_PIP', N'', N'*', N'*', N'*', N'Commercial', N'CA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Not available', N'', 1, N'Not a no-fault state.'),
(N'CA036', N'CA_PIP', N'', N'*', N'FL', N'*', N'Commercial', N'CA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'10000', 2, N'Florida no-fault.'),
(N'CA037', N'CA_PIP', N'', N'*', N'NY', N'*', N'Commercial', N'CA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'50000', 2, N'New York no-fault.'),
(N'CA038', N'CA_COLL', N'', N'*', N'*', N'*', N'Commercial', N'CA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Offered', N'1000', 1, N'Optional physical damage.'),
(N'CA039', N'CA_COMP', N'', N'*', N'*', N'*', N'Commercial', N'CA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Offered', N'1000', 1, N'Optional physical damage.'),
(N'CA040', N'WC_PART1', N'', N'*', N'*', N'*', N'Commercial', N'WC', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'STATUTORY', 1, N'Statutory benefits.'),
(N'CA041', N'WC_PART1', N'', N'*', N'OH', N'*', N'Commercial', N'WC', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Not available', N'', 2, N'Monopolistic state fund.'),
(N'CA042', N'WC_PART1', N'', N'*', N'WA', N'*', N'Commercial', N'WC', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Not available', N'', 2, N'Monopolistic state fund.'),
(N'CA043', N'WC_PART1', N'', N'*', N'ND', N'*', N'Commercial', N'WC', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Not available', N'', 2, N'Monopolistic state fund.'),
(N'CA044', N'WC_PART1', N'', N'*', N'WY', N'*', N'Commercial', N'WC', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Not available', N'', 2, N'Monopolistic state fund.'),
(N'CA045', N'WC_EL', N'', N'*', N'*', N'*', N'Commercial', N'WC', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Mandatory', N'1000000', 1, N'Part Two.'),
(N'CA046', N'WC_EL', N'', N'*', N'OH', N'*', N'Commercial', N'WC', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31', N'Offered', N'1000000', 2, N'Stop-gap employers liability only.');
GO
IF OBJECT_ID('cov.EndorsementDef') IS NOT NULL DROP TABLE cov.[EndorsementDef];
CREATE TABLE cov.[EndorsementDef] (
  [endorsement_code] NVARCHAR(40) NOT NULL,
  [title] NVARCHAR(120) NULL,
  [class] NVARCHAR(40) NULL,
  [attach_level] NVARCHAR(40) NULL,
  [country] NVARCHAR(40) NULL,
  [state] NVARCHAR(40) NULL,
  [company] NVARCHAR(40) NULL,
  [line] NVARCHAR(40) NULL,
  [lob] NVARCHAR(40) NULL,
  [product] NVARCHAR(40) NULL,
  [object] NVARCHAR(40) NULL,
  [module] NVARCHAR(40) NULL,
  [effective_from] NVARCHAR(40) NULL,
  [effective_to] NVARCHAR(40) NULL,
  CONSTRAINT PK_cov_EndorsementDef PRIMARY KEY ([endorsement_code])
);
INSERT INTO cov.[EndorsementDef] ([endorsement_code], [title], [class], [attach_level], [country], [state], [company], [line], [lob], [product], [object], [module], [effective_from], [effective_to]) VALUES
(N'END_HO_SPP', N'Scheduled personal property', N'AddCoverageEndorsement', N'Policy', N'*', N'*', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31'),
(N'END_HO_CINC', N'Increased Coverage C', N'ModifyTermEndorsement', N'Coverage', N'*', N'*', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31'),
(N'END_HO_ROOF_ACV', N'Roof surfacing at actual cash value', N'RestrictEndorsement', N'Coverage', N'*', N'*', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31'),
(N'END_HO_EQ', N'Earthquake', N'AddCoverageEndorsement', N'Coverage', N'*', N'CA', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31'),
(N'END_HO_FL_AMEND', N'Special provisions - Florida', N'StateAmendatoryEndorsement', N'Policy', N'*', N'FL', N'*', N'Personal', N'HO', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31'),
(N'END_CP_WIND_EXCL', N'Windstorm or hail exclusion', N'ExclusionEndorsement', N'Object', N'*', N'*', N'*', N'Commercial', N'CP', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31'),
(N'END_GL_AI_OWNER', N'Additional insured - owner (scheduled)', N'BroadenEndorsement', N'Coverage', N'*', N'*', N'*', N'Commercial', N'GL', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31'),
(N'END_GL_DESIG_OPS', N'Designated operations exclusion', N'ExclusionEndorsement', N'Line', N'*', N'*', N'*', N'Commercial', N'GL', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31'),
(N'END_CA_HNOA', N'Hired and non-owned auto', N'AddCoverageEndorsement', N'Line', N'*', N'*', N'*', N'Commercial', N'CA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31'),
(N'END_CA_TX_AMEND', N'Texas changes', N'StateAmendatoryEndorsement', N'Line', N'*', N'TX', N'*', N'Commercial', N'CA', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31'),
(N'END_WC_OTHER_STATES', N'Other states insurance (3.C)', N'BroadenEndorsement', N'Line', N'*', N'*', N'*', N'Commercial', N'WC', N'*', N'*', N'*', N'2025-01-01', N'9999-12-31');
GO
IF OBJECT_ID('cov.EndorsementEffect') IS NOT NULL DROP TABLE cov.[EndorsementEffect];
CREATE TABLE cov.[EndorsementEffect] (
  [endorsement_code] NVARCHAR(40) NULL,
  [seq] BIGINT NULL,
  [effect_type] NVARCHAR(40) NULL,
  [target_coverage_code] NVARCHAR(40) NULL,
  [target_term_code] NVARCHAR(40) NULL,
  [value] NVARCHAR(120) NULL
);
INSERT INTO cov.[EndorsementEffect] ([endorsement_code], [seq], [effect_type], [target_coverage_code], [target_term_code], [value]) VALUES
(N'END_HO_SPP', 1, N'Add', N'HO_SPP', N'', N'schedule'),
(N'END_HO_CINC', 1, N'Modify term', N'HO_C', N'LIMIT', N'70% of HO_A'),
(N'END_HO_ROOF_ACV', 1, N'Restrict', N'HO_A', N'VALUATION', N'ACV for roof surfacing'),
(N'END_HO_EQ', 1, N'Add', N'HO_EQ', N'', N''),
(N'END_HO_EQ', 2, N'Modify term', N'HO_EQ', N'EQ_DED', N'15'),
(N'END_HO_FL_AMEND', 1, N'Modify condition', N'', N'', N'Cancellation and notice per state law'),
(N'END_CP_WIND_EXCL', 1, N'Exclude', N'CP_BLDG', N'', N'Windstorm or hail'),
(N'END_GL_AI_OWNER', 1, N'Broaden', N'GL_OCC', N'', N'Scheduled owner as additional insured'),
(N'END_GL_DESIG_OPS', 1, N'Exclude', N'GL_OCC', N'', N'Scheduled operations'),
(N'END_CA_HNOA', 1, N'Add', N'CA_LIAB', N'', N'Symbols 8 and 9'),
(N'END_CA_TX_AMEND', 1, N'Modify condition', N'', N'', N'Texas conditions'),
(N'END_WC_OTHER_STATES', 1, N'Broaden', N'WC_PART1', N'', N'States listed in 3.C');
GO
IF OBJECT_ID('cov.PackageDef') IS NOT NULL DROP TABLE cov.[PackageDef];
CREATE TABLE cov.[PackageDef] (
  [product_code] NVARCHAR(40) NULL,
  [lob] NVARCHAR(40) NULL,
  [required] NVARCHAR(40) NULL
);
INSERT INTO cov.[PackageDef] ([product_code], [lob], [required]) VALUES
(N'HO-3 2024', N'HO', N'Required'),
(N'PA-Std 2024', N'PA', N'Required'),
(N'CPP 2025', N'CP', N'Optional'),
(N'CPP 2025', N'GL', N'Optional'),
(N'CPP 2025', N'CA', N'Optional'),
(N'CPP 2025', N'IM', N'Optional'),
(N'CP-Std 2025', N'CP', N'Required'),
(N'GL-Std 2025', N'GL', N'Required'),
(N'WC-Std 2025', N'WC', N'Required');
GO
IF OBJECT_ID('cov.Policy') IS NOT NULL DROP TABLE cov.[Policy];
CREATE TABLE cov.[Policy] (
  [policy_number] NVARCHAR(40) NOT NULL,
  [product_code] NVARCHAR(40) NULL,
  [country] NVARCHAR(40) NULL,
  [state] NVARCHAR(40) NULL,
  [company] NVARCHAR(40) NULL,
  [named_insured] NVARCHAR(40) NULL,
  [effective_date] NVARCHAR(40) NULL,
  [expiration_date] NVARCHAR(40) NULL,
  CONSTRAINT PK_cov_Policy PRIMARY KEY ([policy_number])
);
INSERT INTO cov.[Policy] ([policy_number], [product_code], [country], [state], [company], [named_insured], [effective_date], [expiration_date]) VALUES
(N'HO2026001', N'HO-3 2024', N'US', N'FL', N'SI2-ADM', N'Rivera Household', N'2026-03-01', N'2027-03-01'),
(N'HO2026002', N'HO-3 2024', N'US', N'CA', N'SI2-ADM', N'Nguyen Household', N'2026-03-01', N'2027-03-01'),
(N'HO2026003', N'HO-3 2024', N'US', N'OH', N'SI2-ADM', N'Baker Household', N'2026-03-01', N'2027-03-01'),
(N'PA2026001', N'PA-Std 2024', N'US', N'NY', N'SI2-ADM', N'Shah Household', N'2026-05-10', N'2027-05-10'),
(N'CPP2026001', N'CPP 2025', N'US', N'TX', N'SI2-ADM', N'Lone Star Fabrication', N'2026-04-01', N'2027-04-01'),
(N'CP2026001', N'CP-Std 2025', N'US', N'FL', N'SI2-ES', N'Harbor Point Holdings', N'2026-06-15', N'2027-06-15'),
(N'GL2026001', N'GL-Std 2025', N'US', N'NY', N'SI2-ADM', N'Empire Ridge Builders', N'2026-02-01', N'2027-02-01'),
(N'WC2026001', N'WC-Std 2025', N'US', N'PA', N'SI2-ADM', N'Keystone Plumbing', N'2026-01-01', N'2027-01-01');
GO
IF OBJECT_ID('cov.PolicyLine') IS NOT NULL DROP TABLE cov.[PolicyLine];
CREATE TABLE cov.[PolicyLine] (
  [line_id] NVARCHAR(40) NOT NULL,
  [policy_number] NVARCHAR(40) NULL,
  [lob] NVARCHAR(40) NULL,
  [line] NVARCHAR(40) NULL,
  CONSTRAINT PK_cov_PolicyLine PRIMARY KEY ([line_id])
);
INSERT INTO cov.[PolicyLine] ([line_id], [policy_number], [lob], [line]) VALUES
(N'LN001', N'HO2026001', N'HO', N'Personal'),
(N'LN002', N'HO2026002', N'HO', N'Personal'),
(N'LN003', N'HO2026003', N'HO', N'Personal'),
(N'LN004', N'PA2026001', N'PA', N'Personal'),
(N'LN005', N'CPP2026001', N'CP', N'Commercial'),
(N'LN006', N'CPP2026001', N'GL', N'Commercial'),
(N'LN007', N'CPP2026001', N'CA', N'Commercial'),
(N'LN008', N'CP2026001', N'CP', N'Commercial'),
(N'LN009', N'GL2026001', N'GL', N'Commercial'),
(N'LN010', N'WC2026001', N'WC', N'Commercial');
GO
IF OBJECT_ID('cov.PolicyObject') IS NOT NULL DROP TABLE cov.[PolicyObject];
CREATE TABLE cov.[PolicyObject] (
  [object_id] NVARCHAR(40) NOT NULL,
  [policy_number] NVARCHAR(40) NULL,
  [line_id] NVARCHAR(40) NULL,
  [object_type] NVARCHAR(40) NULL,
  [description] NVARCHAR(120) NULL,
  [value] DECIMAL(18,2) NULL,
  CONSTRAINT PK_cov_PolicyObject PRIMARY KEY ([object_id])
);
INSERT INTO cov.[PolicyObject] ([object_id], [policy_number], [line_id], [object_type], [description], [value]) VALUES
(N'OB001', N'HO2026001', N'LN001', N'Dwelling', N'Single-family dwelling, FL', 450000.0),
(N'OB002', N'HO2026002', N'LN002', N'Dwelling', N'Single-family dwelling, CA', 820000.0),
(N'OB003', N'HO2026003', N'LN003', N'Dwelling', N'Single-family dwelling, OH', 310000.0),
(N'OB004', N'PA2026001', N'LN004', N'Vehicle', N'2023 sedan', NULL),
(N'OB005', N'PA2026001', N'LN004', N'Vehicle', N'2021 SUV', NULL),
(N'OB006', N'CPP2026001', N'LN005', N'Building', N'Plant, Houston', 6600000.0),
(N'OB007', N'CPP2026001', N'LN007', N'Vehicle', N'Heavy truck VEH0005', 140000.0),
(N'OB008', N'CPP2026001', N'LN007', N'Vehicle', N'Light truck VEH0006', 52000.0),
(N'OB009', N'CP2026001', N'LN008', N'Building', N'Office, Miami', 8100000.0),
(N'OB010', N'GL2026001', N'LN009', N'Classification', N'Carpentry contractor, payroll 5,300,000', 5300000.0),
(N'OB011', N'WC2026001', N'LN010', N'Classification', N'Plumbing 5183, payroll 1,250,000', 1250000.0);
GO
IF OBJECT_ID('cov.PolicyCoverage') IS NOT NULL DROP TABLE cov.[PolicyCoverage];
CREATE TABLE cov.[PolicyCoverage] (
  [coverage_id] NVARCHAR(40) NOT NULL,
  [policy_number] NVARCHAR(40) NULL,
  [coverage_code] NVARCHAR(40) NULL,
  [name] NVARCHAR(120) NULL,
  [class] NVARCHAR(120) NULL,
  [attach_level] NVARCHAR(40) NULL,
  [attach_to_id] NVARCHAR(40) NULL,
  [parent_coverage_id] NVARCHAR(40) NULL,
  [source] NVARCHAR(40) NULL,
  CONSTRAINT PK_cov_PolicyCoverage PRIMARY KEY ([coverage_id])
);
INSERT INTO cov.[PolicyCoverage] ([coverage_id], [policy_number], [coverage_code], [name], [class], [attach_level], [attach_to_id], [parent_coverage_id], [source]) VALUES
(N'CV001', N'HO2026001', N'HO_A', N'Coverage A - Dwelling', N'DwellingCoverage', N'Object', N'OB001', N'', N'Base form'),
(N'CV002', N'HO2026001', N'HO_B', N'Coverage B - Other Structures', N'DwellingCoverage', N'Coverage', N'CV001', N'CV001', N'Base form'),
(N'CV003', N'HO2026001', N'HO_C', N'Coverage C - Personal Property', N'PersonalPropertyCoverage', N'Coverage', N'CV001', N'CV001', N'Base form'),
(N'CV004', N'HO2026001', N'HO_D', N'Coverage D - Loss of Use', N'LossOfUseCoverage', N'Coverage', N'CV001', N'CV001', N'Base form'),
(N'CV005', N'HO2026001', N'HO_E', N'Coverage E - Personal Liability', N'PersonalLiability', N'Line', N'LN001', N'', N'Base form'),
(N'CV006', N'HO2026001', N'HO_F', N'Coverage F - Medical Payments to Others', N'MedicalPaymentsCoverage', N'Line', N'LN001', N'', N'Base form'),
(N'CV007', N'HO2026001', N'HO_SPP', N'Scheduled Personal Property', N'PersonalPropertyCoverage', N'Policy', N'HO2026001', N'', N'END_HO_SPP'),
(N'CV008', N'HO2026002', N'HO_A', N'Coverage A - Dwelling', N'DwellingCoverage', N'Object', N'OB002', N'', N'Base form'),
(N'CV009', N'HO2026002', N'HO_B', N'Coverage B - Other Structures', N'DwellingCoverage', N'Coverage', N'CV008', N'CV008', N'Base form'),
(N'CV010', N'HO2026002', N'HO_C', N'Coverage C - Personal Property', N'PersonalPropertyCoverage', N'Coverage', N'CV008', N'CV008', N'Base form'),
(N'CV011', N'HO2026002', N'HO_D', N'Coverage D - Loss of Use', N'LossOfUseCoverage', N'Coverage', N'CV008', N'CV008', N'Base form'),
(N'CV012', N'HO2026002', N'HO_E', N'Coverage E - Personal Liability', N'PersonalLiability', N'Line', N'LN002', N'', N'Base form'),
(N'CV013', N'HO2026002', N'HO_F', N'Coverage F - Medical Payments to Others', N'MedicalPaymentsCoverage', N'Line', N'LN002', N'', N'Base form'),
(N'CV014', N'HO2026002', N'HO_EQ', N'Earthquake', N'DwellingCoverage', N'Coverage', N'CV008', N'CV008', N'END_HO_EQ'),
(N'CV015', N'HO2026003', N'HO_A', N'Coverage A - Dwelling', N'DwellingCoverage', N'Object', N'OB003', N'', N'Base form'),
(N'CV016', N'HO2026003', N'HO_B', N'Coverage B - Other Structures', N'DwellingCoverage', N'Coverage', N'CV015', N'CV015', N'Base form'),
(N'CV017', N'HO2026003', N'HO_C', N'Coverage C - Personal Property', N'PersonalPropertyCoverage', N'Coverage', N'CV015', N'CV015', N'Base form'),
(N'CV018', N'HO2026003', N'HO_D', N'Coverage D - Loss of Use', N'LossOfUseCoverage', N'Coverage', N'CV015', N'CV015', N'Base form'),
(N'CV019', N'HO2026003', N'HO_E', N'Coverage E - Personal Liability', N'PersonalLiability', N'Line', N'LN003', N'', N'Base form'),
(N'CV020', N'HO2026003', N'HO_F', N'Coverage F - Medical Payments to Others', N'MedicalPaymentsCoverage', N'Line', N'LN003', N'', N'Base form'),
(N'CV021', N'PA2026001', N'PA_BI', N'Bodily Injury Liability', N'AutoLiability', N'Line', N'LN004', N'', N'Base form'),
(N'CV022', N'PA2026001', N'PA_PD', N'Property Damage Liability', N'AutoLiability', N'Line', N'LN004', N'', N'Base form'),
(N'CV023', N'PA2026001', N'PA_PIP', N'Personal Injury Protection', N'PersonalInjuryProtection', N'Line', N'LN004', N'', N'Base form'),
(N'CV024', N'PA2026001', N'PA_UM', N'Uninsured Motorists', N'UninsuredMotoristsCoverage', N'Line', N'LN004', N'', N'Base form'),
(N'CV025', N'PA2026001', N'PA_COLL', N'Collision', N'CollisionCoverage', N'Object', N'OB004', N'', N'Base form'),
(N'CV026', N'PA2026001', N'PA_COMP', N'Comprehensive', N'ComprehensiveCoverage', N'Object', N'OB004', N'', N'Base form'),
(N'CV027', N'PA2026001', N'PA_COLL', N'Collision', N'CollisionCoverage', N'Object', N'OB005', N'', N'Base form'),
(N'CV028', N'PA2026001', N'PA_COMP', N'Comprehensive', N'ComprehensiveCoverage', N'Object', N'OB005', N'', N'Base form'),
(N'CV029', N'CPP2026001', N'CP_BLDG', N'Building', N'CommercialBuildingCoverage', N'Object', N'OB006', N'', N'Base form'),
(N'CV030', N'CPP2026001', N'CP_BPP', N'Business Personal Property', N'BusinessPersonalPropertyCoverage', N'Object', N'OB006', N'', N'Base form'),
(N'CV031', N'CPP2026001', N'CP_BI', N'Business Income and Extra Expense', N'BusinessIncomeCoverage', N'Coverage', N'CV029', N'CV029', N'Base form'),
(N'CV032', N'CPP2026001', N'GL_OCC', N'Coverage A - Bodily Injury and Property Damage', N'PremisesOperationsLiability', N'Line', N'LN006', N'', N'Base form'),
(N'CV033', N'CPP2026001', N'GL_PAI', N'Coverage B - Personal and Advertising Injury', N'PersonalAdvertisingInjuryLiability', N'Line', N'LN006', N'', N'Base form'),
(N'CV034', N'CPP2026001', N'GL_MED', N'Coverage C - Medical Payments', N'MedicalPaymentsCoverage', N'Line', N'LN006', N'', N'Base form'),
(N'CV035', N'CPP2026001', N'GL_PCO', N'Products-Completed Operations', N'ProductsCompletedOperationsLiability', N'Line', N'LN006', N'', N'Base form'),
(N'CV036', N'CPP2026001', N'CA_LIAB', N'Auto Liability', N'AutoLiability', N'Line', N'LN007', N'', N'Base form'),
(N'CV037', N'CPP2026001', N'CA_UM', N'Uninsured Motorists', N'UninsuredMotoristsCoverage', N'Line', N'LN007', N'', N'Base form'),
(N'CV038', N'CPP2026001', N'CA_COLL', N'Collision', N'CollisionCoverage', N'Object', N'OB007', N'', N'Base form'),
(N'CV039', N'CPP2026001', N'CA_COMP', N'Comprehensive', N'ComprehensiveCoverage', N'Object', N'OB007', N'', N'Base form'),
(N'CV040', N'CPP2026001', N'CA_COLL', N'Collision', N'CollisionCoverage', N'Object', N'OB008', N'', N'Base form'),
(N'CV041', N'CPP2026001', N'CA_COMP', N'Comprehensive', N'ComprehensiveCoverage', N'Object', N'OB008', N'', N'Base form'),
(N'CV042', N'CP2026001', N'CP_BLDG', N'Building', N'CommercialBuildingCoverage', N'Object', N'OB009', N'', N'Base form'),
(N'CV043', N'GL2026001', N'GL_OCC', N'Coverage A - Bodily Injury and Property Damage', N'PremisesOperationsLiability', N'Line', N'LN009', N'', N'Base form'),
(N'CV044', N'GL2026001', N'GL_PAI', N'Coverage B - Personal and Advertising Injury', N'PersonalAdvertisingInjuryLiability', N'Line', N'LN009', N'', N'Base form'),
(N'CV045', N'GL2026001', N'GL_PCO', N'Products-Completed Operations', N'ProductsCompletedOperationsLiability', N'Line', N'LN009', N'', N'Base form'),
(N'CV046', N'WC2026001', N'WC_PART1', N'Part One - Workers'' Compensation', N'WorkersCompensationBenefits', N'Line', N'LN010', N'', N'Base form'),
(N'CV047', N'WC2026001', N'WC_EL', N'Part Two - Employers Liability', N'EmployersLiability', N'Line', N'LN010', N'', N'Base form');
GO
IF OBJECT_ID('cov.PolicyCoverageTerm') IS NOT NULL DROP TABLE cov.[PolicyCoverageTerm];
CREATE TABLE cov.[PolicyCoverageTerm] (
  [coverage_id] NVARCHAR(40) NULL,
  [term_code] NVARCHAR(40) NULL,
  [value] NVARCHAR(40) NULL,
  [source] NVARCHAR(120) NULL
);
INSERT INTO cov.[PolicyCoverageTerm] ([coverage_id], [term_code], [value], [source]) VALUES
(N'CV001', N'LIMIT', N'450000', N'Selected'),
(N'CV001', N'VALUATION', N'RC', N'Default'),
(N'CV001', N'AOP_DED', N'1000', N'Default'),
(N'CV002', N'LIMIT', N'45000', N'Rule 10% of HO_A'),
(N'CV003', N'LIMIT', N'225000', N'Rule 50% of HO_A'),
(N'CV004', N'LIMIT', N'90000', N'Rule 20% of HO_A'),
(N'CV005', N'LIMIT', N'300000', N'Default'),
(N'CV006', N'LIMIT', N'5000', N'Default'),
(N'CV001', N'HURR_DED', N'2%', N'Mandatory in FL; applies at Policy level'),
(N'CV007', N'LIMIT', N'42000', N'Schedule: ring, watch, painting'),
(N'CV008', N'LIMIT', N'820000', N'Selected'),
(N'CV008', N'VALUATION', N'RC', N'Default'),
(N'CV008', N'AOP_DED', N'1000', N'Default'),
(N'CV009', N'LIMIT', N'82000', N'Rule 10% of HO_A'),
(N'CV010', N'LIMIT', N'574000', N'Endorsement 70% of HO_A'),
(N'CV011', N'LIMIT', N'164000', N'Rule 20% of HO_A'),
(N'CV012', N'LIMIT', N'300000', N'Default'),
(N'CV013', N'LIMIT', N'5000', N'Default'),
(N'CV014', N'EQ_DED', N'15', N'Endorsement'),
(N'CV015', N'LIMIT', N'310000', N'Selected'),
(N'CV015', N'VALUATION', N'RC', N'Default'),
(N'CV015', N'AOP_DED', N'1000', N'Default'),
(N'CV016', N'LIMIT', N'31000', N'Rule 10% of HO_A'),
(N'CV017', N'LIMIT', N'155000', N'Rule 50% of HO_A'),
(N'CV018', N'LIMIT', N'62000', N'Rule 20% of HO_A'),
(N'CV019', N'LIMIT', N'300000', N'Default'),
(N'CV020', N'LIMIT', N'5000', N'Default'),
(N'CV021', N'PER_PERSON', N'100000', N'Selected'),
(N'CV021', N'PER_ACCIDENT', N'300000', N'Selected'),
(N'CV022', N'LIMIT', N'100000', N'Selected'),
(N'CV023', N'LIMIT', N'50000', N'Mandatory in NY'),
(N'CV024', N'PER_PERSON', N'100000', N'Selected'),
(N'CV025', N'DED', N'500', N'Default'),
(N'CV026', N'DED', N'250', N'Default'),
(N'CV027', N'DED', N'500', N'Default'),
(N'CV028', N'DED', N'250', N'Default'),
(N'CV029', N'LIMIT', N'6600000', N'Selected'),
(N'CV029', N'COINS', N'90', N'Default'),
(N'CV029', N'VALUATION', N'RC', N'Default'),
(N'CV029', N'AOP_DED', N'5000', N'Default'),
(N'CV029', N'WIND_DED', N'2%', N'Mandatory in TX'),
(N'CV030', N'LIMIT', N'1500000', N'Selected'),
(N'CV031', N'LIMIT', N'1200000', N'Selected'),
(N'CV031', N'WAITING', N'72', N'Default'),
(N'CV032', N'EACH_OCC', N'1000000', N'Default'),
(N'CV032', N'GEN_AGG', N'2000000', N'Rule 2 x each occurrence'),
(N'CV033', N'LIMIT', N'1000000', N'Rule'),
(N'CV034', N'LIMIT', N'5000', N'Default'),
(N'CV035', N'AGG', N'2000000', N'Rule'),
(N'CV036', N'CSL', N'1000000', N'Default'),
(N'CV037', N'LIMIT', N'30000', N'Selected'),
(N'CV038', N'DED', N'1000', N'Default'),
(N'CV039', N'DED', N'1000', N'Default'),
(N'CV040', N'DED', N'1000', N'Default'),
(N'CV041', N'DED', N'1000', N'Default'),
(N'CV042', N'LIMIT', N'8100000', N'Selected'),
(N'CV042', N'COINS', N'90', N'Default'),
(N'CV042', N'VALUATION', N'RC', N'Default'),
(N'CV042', N'AOP_DED', N'10000', N'Selected'),
(N'CV043', N'EACH_OCC', N'1000000', N'Default'),
(N'CV043', N'GEN_AGG', N'2000000', N'Rule'),
(N'CV044', N'LIMIT', N'1000000', N'Rule'),
(N'CV045', N'AGG', N'2000000', N'Rule'),
(N'CV046', N'LIMIT', N'STATUTORY', N'Statutory'),
(N'CV047', N'EACH_ACC', N'1000000', N'Default'),
(N'CV047', N'DIS_POL', N'1000000', N'Rule'),
(N'CV047', N'DIS_EE', N'1000000', N'Rule');
GO
IF OBJECT_ID('cov.PolicyEndorsement') IS NOT NULL DROP TABLE cov.[PolicyEndorsement];
CREATE TABLE cov.[PolicyEndorsement] (
  [endorsement_id] NVARCHAR(40) NOT NULL,
  [policy_number] NVARCHAR(40) NULL,
  [endorsement_code] NVARCHAR(40) NULL,
  [title] NVARCHAR(120) NULL,
  [class] NVARCHAR(40) NULL,
  [attach_level] NVARCHAR(40) NULL,
  [attach_to_id] NVARCHAR(40) NULL,
  [note] NVARCHAR(120) NULL,
  CONSTRAINT PK_cov_PolicyEndorsement PRIMARY KEY ([endorsement_id])
);
INSERT INTO cov.[PolicyEndorsement] ([endorsement_id], [policy_number], [endorsement_code], [title], [class], [attach_level], [attach_to_id], [note]) VALUES
(N'EN001', N'HO2026001', N'END_HO_SPP', N'Scheduled personal property', N'AddCoverageEndorsement', N'Policy', N'HO2026001', N'3 scheduled items'),
(N'EN002', N'HO2026001', N'END_HO_ROOF_ACV', N'Roof surfacing at actual cash value', N'RestrictEndorsement', N'Coverage', N'CV001', N''),
(N'EN003', N'HO2026001', N'END_HO_FL_AMEND', N'Special provisions - Florida', N'StateAmendatoryEndorsement', N'Policy', N'HO2026001', N''),
(N'EN004', N'HO2026002', N'END_HO_EQ', N'Earthquake', N'AddCoverageEndorsement', N'Coverage', N'CV008', N''),
(N'EN005', N'HO2026002', N'END_HO_CINC', N'Increased Coverage C', N'ModifyTermEndorsement', N'Coverage', N'CV008', N''),
(N'EN006', N'CPP2026001', N'END_GL_AI_OWNER', N'Additional insured - owner (scheduled)', N'BroadenEndorsement', N'Coverage', N'CV032', N'Owner: Port Holdings LLC (synthetic)'),
(N'EN007', N'CPP2026001', N'END_CA_HNOA', N'Hired and non-owned auto', N'AddCoverageEndorsement', N'Line', N'LN007', N''),
(N'EN008', N'CPP2026001', N'END_CA_TX_AMEND', N'Texas changes', N'StateAmendatoryEndorsement', N'Line', N'LN007', N''),
(N'EN009', N'CP2026001', N'END_CP_WIND_EXCL', N'Windstorm or hail exclusion', N'ExclusionEndorsement', N'Object', N'OB009', N'Wind placed with a wind pool (synthetic)'),
(N'EN010', N'GL2026001', N'END_GL_DESIG_OPS', N'Designated operations exclusion', N'ExclusionEndorsement', N'Line', N'LN009', N'Excludes roofing work (synthetic)'),
(N'EN011', N'WC2026001', N'END_WC_OTHER_STATES', N'Other states insurance (3.C)', N'BroadenEndorsement', N'Line', N'LN010', N'3.C states listed; Ohio excluded (monopolistic) - stop-gap EL only');
GO
IF OBJECT_ID('cov.PolicyCoveragePremium') IS NOT NULL DROP TABLE cov.[PolicyCoveragePremium];
CREATE TABLE cov.[PolicyCoveragePremium] (
  [coverage_id] NVARCHAR(40) NULL,
  [policy_number] NVARCHAR(40) NULL,
  [state] NVARCHAR(40) NULL,
  [transaction] NVARCHAR(40) NULL,
  [written_premium] BIGINT NULL
);
INSERT INTO cov.[PolicyCoveragePremium] ([coverage_id], [policy_number], [state], [transaction], [written_premium]) VALUES
(N'CV001', N'HO2026001', N'FL', N'NB', 6120),
(N'CV005', N'HO2026001', N'FL', N'NB', 367),
(N'CV007', N'HO2026001', N'FL', N'NB', 380),
(N'CV008', N'HO2026002', N'CA', N'NB', 2950),
(N'CV012', N'HO2026002', N'CA', N'NB', 177),
(N'CV014', N'HO2026002', N'CA', N'NB', 1180),
(N'CV015', N'HO2026003', N'OH', N'NB', 1410),
(N'CV019', N'HO2026003', N'OH', N'NB', 85),
(N'CV021', N'PA2026001', N'NY', N'NB', 820),
(N'CV022', N'PA2026001', N'NY', N'NB', 410),
(N'CV023', N'PA2026001', N'NY', N'NB', 290),
(N'CV024', N'PA2026001', N'NY', N'NB', 140),
(N'CV025', N'PA2026001', N'NY', N'NB', 520),
(N'CV026', N'PA2026001', N'NY', N'NB', 190),
(N'CV027', N'PA2026001', N'NY', N'NB', 520),
(N'CV028', N'PA2026001', N'NY', N'NB', 190),
(N'CV029', N'CPP2026001', N'TX', N'NB', 38400),
(N'CV030', N'CPP2026001', N'TX', N'NB', 7900),
(N'CV031', N'CPP2026001', N'TX', N'NB', 5100),
(N'CV032', N'CPP2026001', N'TX', N'NB', 21800),
(N'CV035', N'CPP2026001', N'TX', N'NB', 6400),
(N'CV036', N'CPP2026001', N'TX', N'NB', 9800),
(N'CV037', N'CPP2026001', N'TX', N'NB', 600),
(N'CV038', N'CPP2026001', N'TX', N'NB', 2100),
(N'CV039', N'CPP2026001', N'TX', N'NB', 700),
(N'CV040', N'CPP2026001', N'TX', N'NB', 900),
(N'CV041', N'CPP2026001', N'TX', N'NB', 310),
(N'CV042', N'CP2026001', N'FL', N'NB', 31200),
(N'CV043', N'GL2026001', N'NY', N'NB', 186000),
(N'CV045', N'GL2026001', N'NY', N'NB', 31300),
(N'CV046', N'WC2026001', N'PA', N'NB', 61200);
GO
IF OBJECT_ID('cov.CoverageInForce') IS NOT NULL DROP TABLE cov.[CoverageInForce];
CREATE TABLE cov.[CoverageInForce] (
  [policy_number] NVARCHAR(40) NULL,
  [coverage_id] NVARCHAR(40) NULL,
  [coverage_code] NVARCHAR(40) NULL,
  [name] NVARCHAR(40) NULL,
  [class] NVARCHAR(120) NULL,
  [attach_level] NVARCHAR(40) NULL,
  [attaches_to] NVARCHAR(120) NULL,
  [terms] NVARCHAR(120) NULL,
  [endorsements_acting] NVARCHAR(40) NULL
);
INSERT INTO cov.[CoverageInForce] ([policy_number], [coverage_id], [coverage_code], [name], [class], [attach_level], [attaches_to], [terms], [endorsements_acting]) VALUES
(N'HO2026001', N'CV001', N'HO_A', NULL, N'DwellingCoverage', N'Object', N'Object OB001: Single-family dwelling, FL', N'LIMIT=450000; VALUATION=RC; AOP_DED=1000; HURR_DED=2%', N'END_HO_ROOF_ACV, END_HO_FL_AMEND'),
(N'HO2026001', N'CV002', N'HO_B', NULL, N'DwellingCoverage', N'Coverage', N'Coverage CV001: HO_A', N'LIMIT=45000', N'END_HO_FL_AMEND'),
(N'HO2026001', N'CV003', N'HO_C', NULL, N'PersonalPropertyCoverage', N'Coverage', N'Coverage CV001: HO_A', N'LIMIT=225000', N'END_HO_FL_AMEND'),
(N'HO2026001', N'CV004', N'HO_D', NULL, N'LossOfUseCoverage', N'Coverage', N'Coverage CV001: HO_A', N'LIMIT=90000', N'END_HO_FL_AMEND'),
(N'HO2026001', N'CV005', N'HO_E', NULL, N'PersonalLiability', N'Line', N'Line LN001: HO', N'LIMIT=300000', N'END_HO_FL_AMEND'),
(N'HO2026001', N'CV006', N'HO_F', NULL, N'MedicalPaymentsCoverage', N'Line', N'Line LN001: HO', N'LIMIT=5000', N'END_HO_FL_AMEND'),
(N'HO2026001', N'CV007', N'HO_SPP', NULL, N'PersonalPropertyCoverage', N'Policy', N'Policy HO2026001', N'LIMIT=42000', N'END_HO_SPP, END_HO_FL_AMEND'),
(N'HO2026002', N'CV008', N'HO_A', NULL, N'DwellingCoverage', N'Object', N'Object OB002: Single-family dwelling, CA', N'LIMIT=820000; VALUATION=RC; AOP_DED=1000', N''),
(N'HO2026002', N'CV009', N'HO_B', NULL, N'DwellingCoverage', N'Coverage', N'Coverage CV008: HO_A', N'LIMIT=82000', N''),
(N'HO2026002', N'CV010', N'HO_C', NULL, N'PersonalPropertyCoverage', N'Coverage', N'Coverage CV008: HO_A', N'LIMIT=574000', N'END_HO_CINC'),
(N'HO2026002', N'CV011', N'HO_D', NULL, N'LossOfUseCoverage', N'Coverage', N'Coverage CV008: HO_A', N'LIMIT=164000', N''),
(N'HO2026002', N'CV012', N'HO_E', NULL, N'PersonalLiability', N'Line', N'Line LN002: HO', N'LIMIT=300000', N''),
(N'HO2026002', N'CV013', N'HO_F', NULL, N'MedicalPaymentsCoverage', N'Line', N'Line LN002: HO', N'LIMIT=5000', N''),
(N'HO2026002', N'CV014', N'HO_EQ', NULL, N'DwellingCoverage', N'Coverage', N'Coverage CV008: HO_A', N'EQ_DED=15', N'END_HO_EQ'),
(N'HO2026003', N'CV015', N'HO_A', NULL, N'DwellingCoverage', N'Object', N'Object OB003: Single-family dwelling, OH', N'LIMIT=310000; VALUATION=RC; AOP_DED=1000', N''),
(N'HO2026003', N'CV016', N'HO_B', NULL, N'DwellingCoverage', N'Coverage', N'Coverage CV015: HO_A', N'LIMIT=31000', N''),
(N'HO2026003', N'CV017', N'HO_C', NULL, N'PersonalPropertyCoverage', N'Coverage', N'Coverage CV015: HO_A', N'LIMIT=155000', N''),
(N'HO2026003', N'CV018', N'HO_D', NULL, N'LossOfUseCoverage', N'Coverage', N'Coverage CV015: HO_A', N'LIMIT=62000', N''),
(N'HO2026003', N'CV019', N'HO_E', NULL, N'PersonalLiability', N'Line', N'Line LN003: HO', N'LIMIT=300000', N''),
(N'HO2026003', N'CV020', N'HO_F', NULL, N'MedicalPaymentsCoverage', N'Line', N'Line LN003: HO', N'LIMIT=5000', N''),
(N'PA2026001', N'CV021', N'PA_BI', NULL, N'AutoLiability', N'Line', N'Line LN004: PA', N'PER_PERSON=100000; PER_ACCIDENT=300000', N''),
(N'PA2026001', N'CV022', N'PA_PD', NULL, N'AutoLiability', N'Line', N'Line LN004: PA', N'LIMIT=100000', N''),
(N'PA2026001', N'CV023', N'PA_PIP', NULL, N'PersonalInjuryProtection', N'Line', N'Line LN004: PA', N'LIMIT=50000', N''),
(N'PA2026001', N'CV024', N'PA_UM', NULL, N'UninsuredMotoristsCoverage', N'Line', N'Line LN004: PA', N'PER_PERSON=100000', N''),
(N'PA2026001', N'CV025', N'PA_COLL', NULL, N'CollisionCoverage', N'Object', N'Object OB004: 2023 sedan', N'DED=500', N''),
(N'PA2026001', N'CV026', N'PA_COMP', NULL, N'ComprehensiveCoverage', N'Object', N'Object OB004: 2023 sedan', N'DED=250', N''),
(N'PA2026001', N'CV027', N'PA_COLL', NULL, N'CollisionCoverage', N'Object', N'Object OB005: 2021 SUV', N'DED=500', N''),
(N'PA2026001', N'CV028', N'PA_COMP', NULL, N'ComprehensiveCoverage', N'Object', N'Object OB005: 2021 SUV', N'DED=250', N''),
(N'CPP2026001', N'CV029', N'CP_BLDG', NULL, N'CommercialBuildingCoverage', N'Object', N'Object OB006: Plant, Houston', N'LIMIT=6600000; COINS=90; VALUATION=RC; AOP_DED=5000; WIND_DED=2%', N''),
(N'CPP2026001', N'CV030', N'CP_BPP', NULL, N'BusinessPersonalPropertyCoverage', N'Object', N'Object OB006: Plant, Houston', N'LIMIT=1500000', N''),
(N'CPP2026001', N'CV031', N'CP_BI', NULL, N'BusinessIncomeCoverage', N'Coverage', N'Coverage CV029: CP_BLDG', N'LIMIT=1200000; WAITING=72', N''),
(N'CPP2026001', N'CV032', N'GL_OCC', NULL, N'PremisesOperationsLiability', N'Line', N'Line LN006: GL', N'EACH_OCC=1000000; GEN_AGG=2000000', N'END_GL_AI_OWNER'),
(N'CPP2026001', N'CV033', N'GL_PAI', NULL, N'PersonalAdvertisingInjuryLiability', N'Line', N'Line LN006: GL', N'LIMIT=1000000', N''),
(N'CPP2026001', N'CV034', N'GL_MED', NULL, N'MedicalPaymentsCoverage', N'Line', N'Line LN006: GL', N'LIMIT=5000', N''),
(N'CPP2026001', N'CV035', N'GL_PCO', NULL, N'ProductsCompletedOperationsLiability', N'Line', N'Line LN006: GL', N'AGG=2000000', N''),
(N'CPP2026001', N'CV036', N'CA_LIAB', NULL, N'AutoLiability', N'Line', N'Line LN007: CA', N'CSL=1000000', N'END_CA_HNOA, END_CA_TX_AMEND'),
(N'CPP2026001', N'CV037', N'CA_UM', NULL, N'UninsuredMotoristsCoverage', N'Line', N'Line LN007: CA', N'LIMIT=30000', N'END_CA_TX_AMEND'),
(N'CPP2026001', N'CV038', N'CA_COLL', NULL, N'CollisionCoverage', N'Object', N'Object OB007: Heavy truck VEH0005', N'DED=1000', N'END_CA_TX_AMEND'),
(N'CPP2026001', N'CV039', N'CA_COMP', NULL, N'ComprehensiveCoverage', N'Object', N'Object OB007: Heavy truck VEH0005', N'DED=1000', N'END_CA_TX_AMEND'),
(N'CPP2026001', N'CV040', N'CA_COLL', NULL, N'CollisionCoverage', N'Object', N'Object OB008: Light truck VEH0006', N'DED=1000', N'END_CA_TX_AMEND'),
(N'CPP2026001', N'CV041', N'CA_COMP', NULL, N'ComprehensiveCoverage', N'Object', N'Object OB008: Light truck VEH0006', N'DED=1000', N'END_CA_TX_AMEND'),
(N'CP2026001', N'CV042', N'CP_BLDG', NULL, N'CommercialBuildingCoverage', N'Object', N'Object OB009: Office, Miami', N'LIMIT=8100000; COINS=90; VALUATION=RC; AOP_DED=10000', N'END_CP_WIND_EXCL'),
(N'GL2026001', N'CV043', N'GL_OCC', NULL, N'PremisesOperationsLiability', N'Line', N'Line LN009: GL', N'EACH_OCC=1000000; GEN_AGG=2000000', N'END_GL_DESIG_OPS'),
(N'GL2026001', N'CV044', N'GL_PAI', NULL, N'PersonalAdvertisingInjuryLiability', N'Line', N'Line LN009: GL', N'LIMIT=1000000', N''),
(N'GL2026001', N'CV045', N'GL_PCO', NULL, N'ProductsCompletedOperationsLiability', N'Line', N'Line LN009: GL', N'AGG=2000000', N''),
(N'WC2026001', N'CV046', N'WC_PART1', NULL, N'WorkersCompensationBenefits', N'Line', N'Line LN010: WC', N'LIMIT=STATUTORY', N'END_WC_OTHER_STATES'),
(N'WC2026001', N'CV047', N'WC_EL', NULL, N'EmployersLiability', N'Line', N'Line LN010: WC', N'EACH_ACC=1000000; DIS_POL=1000000; DIS_EE=1000000', N'');
GO
-- Which coverages a context may sell: most specific scope wins
CREATE OR ALTER FUNCTION cov.fn_CoverageOffer (@coverage NVARCHAR(40), @term NVARCHAR(40), @state NVARCHAR(10), @lob NVARCHAR(10),
       @product NVARCHAR(60), @company NVARCHAR(20), @asof DATE)
RETURNS TABLE AS RETURN
SELECT TOP 1 a.coverage_code, a.term_code, a.offer_status, a.default_value, a.reason
FROM cov.CoverageApplicability a
WHERE a.coverage_code = @coverage AND a.term_code = ISNULL(@term, N'')
  AND a.state IN ('*', @state) AND a.lob IN ('*', @lob) AND a.product IN ('*', @product) AND a.company IN ('*', @company)
  AND @asof BETWEEN a.effective_from AND a.effective_to
ORDER BY a.specificity DESC;
GO
-- Class hierarchy: every catalog coverage with all its ancestor classes
CREATE OR ALTER VIEW cov.vw_CoverageClassPath AS
WITH p AS (SELECT d.coverage_code, c.class, c.parent_class, 0 AS lvl FROM cov.CoverageDef d JOIN cov.Classes c ON c.class = d.class
           UNION ALL SELECT p.coverage_code, c.class, c.parent_class, p.lvl + 1 FROM p JOIN cov.Classes c ON c.class = p.parent_class)
SELECT coverage_code, class, lvl FROM p;
GO
