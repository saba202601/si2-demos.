/* =====================================================================================================
   SI² Canonical Master · a small "other database" to try the scan on (optional).
   It looks like a policy / claims / billing system: most columns already exist in the master model under
   another name, some values are new, and a few columns are new altogether (RoofMaterial, PetInjuryInd ...).

   Then, in SI2Canonical:
       EXEC intake.usp_ScanDatabase @SourceDatabase = 'SI2_SourceDemo', @SourceSystem = 'Guidewire';
       EXEC intake.usp_ProposeMissing @ScanRunId = 1;
   ===================================================================================================== */
IF DB_ID(N'SI2_SourceDemo') IS NULL
    CREATE DATABASE SI2_SourceDemo;
GO
USE SI2_SourceDemo;
GO
IF OBJECT_ID('dbo.gw_Policy') IS NOT NULL DROP TABLE dbo.gw_Policy;
IF OBJECT_ID('dbo.gw_Claim') IS NOT NULL DROP TABLE dbo.gw_Claim;
IF OBJECT_ID('dbo.bill_Invoice') IS NOT NULL DROP TABLE dbo.bill_Invoice;
GO
CREATE TABLE dbo.gw_Policy (
    PolicyNumber   varchar(20) NOT NULL PRIMARY KEY,
    BaseState      char(2)     NOT NULL,
    PeriodStart    date        NOT NULL,
    PeriodEnd      date        NOT NULL,
    PolicyStatus   varchar(20) NOT NULL,
    ProducerCode   varchar(10) NULL,
    WrittenPremium decimal(12, 2) NOT NULL,
    TelematicsInd  char(1)     NULL,
    RoofMaterial   varchar(20) NULL,
    SalesChannel   varchar(20) NULL
);
INSERT dbo.gw_Policy VALUES
 ('P-1001', 'TX', '2026-01-01', '2027-01-01', 'INFORCE',   'A100', 1250.00, 'Y', 'Shingle', 'Agent'),
 ('P-1002', 'FL', '2026-02-15', '2027-02-15', 'INFORCE',   'A100', 2410.00, 'N', 'Metal',   'Agent'),
 ('P-1003', 'GA', '2026-03-01', '2027-03-01', 'CANCELLED', 'A200',  980.00, 'N', 'Tile',    'Online'),
 ('P-1004', 'NC', '2026-03-20', '2027-03-20', 'INFORCE',   'A300', 1730.00, 'Y', 'Shingle', 'Online'),
 ('P-1005', 'OH', '2026-04-01', '2027-04-01', 'LAPSED',    'A200',  860.00, 'N', 'Shingle', 'Agent'),
 ('P-1006', 'NY', '2026-05-10', '2027-05-10', 'INFORCE',   'A300', 3120.00, 'N', 'Slate',   'Broker'),
 ('P-1007', 'TX', '2026-06-01', '2027-06-01', 'INFORCE',   'A100', 1495.00, 'Y', 'Metal',   'Agent'),
 ('P-1008', 'FL', '2026-06-15', '2027-06-15', 'INFORCE',   'A400', 2875.00, 'N', 'Tile',    'Broker');
GO
CREATE TABLE dbo.gw_Claim (
    ClaimNumber    varchar(20) NOT NULL PRIMARY KEY,
    PolicyNumber   varchar(20) NOT NULL,
    LossDate       date        NOT NULL,
    LossCause      varchar(20) NOT NULL,
    ClaimStatus    varchar(10) NOT NULL,
    PAID_AMT       decimal(12, 2) NOT NULL,
    OS_RSV         decimal(12, 2) NOT NULL,
    AttorneyInd    char(1)     NOT NULL,
    FraudScore     decimal(5, 1) NULL,
    PetInjuryInd   char(1)     NULL
);
INSERT dbo.gw_Claim VALUES
 ('C-501', 'P-1001', '2026-04-03', 'waterdamage', 'open',     1200.00,  3800.00, 'N', 12.0, 'N'),
 ('C-502', 'P-1002', '2026-05-21', 'wind',        'closed',   8400.00,     0.00, 'N', 22.5, 'N'),
 ('C-503', 'P-1004', '2026-06-02', 'fire',        'open',    15200.00, 41000.00, 'Y', 35.0, 'N'),
 ('C-504', 'P-1006', '2026-06-30', 'burglary',    'reopened', 2600.00,  1500.00, 'N', 88.0, 'N'),
 ('C-505', 'P-1007', '2026-07-12', 'hail',        'open',        0.00,  9600.00, 'N', 18.0, 'N'),
 ('C-506', 'P-1008', '2026-08-09', 'dogbite',     'open',      450.00, 12000.00, 'Y', 41.0, 'Y');
GO
CREATE TABLE dbo.bill_Invoice (
    InvoiceNumber  varchar(20) NOT NULL PRIMARY KEY,
    PolicyNumber   varchar(20) NOT NULL,
    DueDate        date        NOT NULL,
    AmountDue      decimal(12, 2) NOT NULL,
    PaymentMethod  varchar(10) NULL,
    PaymentPlan    varchar(10) NOT NULL
);
INSERT dbo.bill_Invoice VALUES
 ('I-9001', 'P-1001', '2026-02-01',  104.17, 'ACH',    '12PAY'),
 ('I-9002', 'P-1002', '2026-02-15', 2410.00, 'CHECK',  'PIF'),
 ('I-9003', 'P-1004', '2026-04-20',  144.17, 'CARD',   '12PAY'),
 ('I-9004', 'P-1005', '2026-05-01',  215.00, 'CRYPTO', '4PAY'),
 ('I-9005', 'P-1007', '2026-07-01',   28.75, 'CARD',   'WEEKLY');
GO
