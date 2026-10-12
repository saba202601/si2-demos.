-- SI² ISO Bureau Reporting - SQL Server Express DDL (generated from engine/db.py)
IF DB_ID('ISOBureauReporting') IS NULL CREATE DATABASE ISOBureauReporting;
GO
USE ISOBureauReporting;
GO
IF OBJECT_ID('dbo.bureau') IS NULL
CREATE TABLE dbo.bureau (
    bureau_code NVARCHAR(20) PRIMARY KEY,
    bureau_name NVARCHAR(1000) NOT NULL,
    code_basis NVARCHAR(100) NOT NULL DEFAULT 'POLICY_EFF'
);
GO
IF OBJECT_ID('dbo.line_of_business') IS NULL
CREATE TABLE dbo.line_of_business (
    lob_code NVARCHAR(20) PRIMARY KEY,
    lob_name NVARCHAR(1000) NOT NULL,
    lob_family NVARCHAR(100) NOT NULL
);
GO
IF OBJECT_ID('dbo.canonical_element') IS NULL
CREATE TABLE dbo.canonical_element (
    element_id INT IDENTITY(1,1) PRIMARY KEY,
    element_code NVARCHAR(100) NOT NULL,
    element_name NVARCHAR(1000) NOT NULL,
    business_description NVARCHAR(MAX) NOT NULL,
    data_type NVARCHAR(100) NOT NULL,
    picklist_code NVARCHAR(100),
    eff_date DATE NOT NULL,
    exp_date DATE NOT NULL DEFAULT '9999-12-31',
    status NVARCHAR(100) NOT NULL DEFAULT 'PENDING',
    created_by NVARCHAR(100) NOT NULL DEFAULT 'system',
    created_at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    approved_by NVARCHAR(100),
    approved_at DATETIME2(0),
    supersedes_id INT,
    notes NVARCHAR(MAX)
);
GO
IF OBJECT_ID('dbo.element_alias') IS NULL
CREATE TABLE dbo.element_alias (
    alias_id INT IDENTITY(1,1) PRIMARY KEY,
    element_code NVARCHAR(100) NOT NULL,
    alias_name NVARCHAR(1000) NOT NULL,
    alias_context NVARCHAR(100) NOT NULL,
    eff_date DATE NOT NULL,
    exp_date DATE NOT NULL DEFAULT '9999-12-31',
    status NVARCHAR(100) NOT NULL DEFAULT 'PENDING',
    created_by NVARCHAR(100) NOT NULL DEFAULT 'system',
    created_at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    approved_by NVARCHAR(100),
    approved_at DATETIME2(0),
    supersedes_id INT,
    notes NVARCHAR(MAX)
);
GO
IF OBJECT_ID('dbo.source_mapping') IS NULL
CREATE TABLE dbo.source_mapping (
    source_map_id INT IDENTITY(1,1) PRIMARY KEY,
    source_system NVARCHAR(100) NOT NULL,
    source_entity NVARCHAR(100) NOT NULL,
    source_attribute NVARCHAR(100) NOT NULL,
    source_data_type NVARCHAR(100),
    element_code NVARCHAR(100) NOT NULL,
    eff_date DATE NOT NULL,
    exp_date DATE NOT NULL DEFAULT '9999-12-31',
    status NVARCHAR(100) NOT NULL DEFAULT 'PENDING',
    created_by NVARCHAR(100) NOT NULL DEFAULT 'system',
    created_at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    approved_by NVARCHAR(100),
    approved_at DATETIME2(0),
    supersedes_id INT,
    notes NVARCHAR(MAX)
);
GO
IF OBJECT_ID('dbo.picklist') IS NULL
CREATE TABLE dbo.picklist (
    picklist_id INT IDENTITY(1,1) PRIMARY KEY,
    picklist_code NVARCHAR(100) NOT NULL,
    picklist_name NVARCHAR(1000) NOT NULL,
    business_description NVARCHAR(MAX),
    eff_date DATE NOT NULL,
    exp_date DATE NOT NULL DEFAULT '9999-12-31',
    status NVARCHAR(100) NOT NULL DEFAULT 'PENDING',
    created_by NVARCHAR(100) NOT NULL DEFAULT 'system',
    created_at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    approved_by NVARCHAR(100),
    approved_at DATETIME2(0),
    supersedes_id INT,
    notes NVARCHAR(MAX)
);
GO
IF OBJECT_ID('dbo.picklist_alias') IS NULL
CREATE TABLE dbo.picklist_alias (
    alias_id INT IDENTITY(1,1) PRIMARY KEY,
    picklist_code NVARCHAR(100) NOT NULL,
    alias_name NVARCHAR(1000) NOT NULL,
    alias_context NVARCHAR(100) NOT NULL,
    eff_date DATE NOT NULL,
    exp_date DATE NOT NULL DEFAULT '9999-12-31',
    status NVARCHAR(100) NOT NULL DEFAULT 'PENDING',
    created_by NVARCHAR(100) NOT NULL DEFAULT 'system',
    created_at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    approved_by NVARCHAR(100),
    approved_at DATETIME2(0),
    supersedes_id INT,
    notes NVARCHAR(MAX)
);
GO
IF OBJECT_ID('dbo.picklist_option') IS NULL
CREATE TABLE dbo.picklist_option (
    option_id INT IDENTITY(1,1) PRIMARY KEY,
    picklist_code NVARCHAR(100) NOT NULL,
    lob_scope NVARCHAR(100) NOT NULL DEFAULT '*',
    option_code NVARCHAR(100) NOT NULL,
    option_name NVARCHAR(1000) NOT NULL,
    business_description NVARCHAR(MAX),
    eff_date DATE NOT NULL,
    exp_date DATE NOT NULL DEFAULT '9999-12-31',
    status NVARCHAR(100) NOT NULL DEFAULT 'PENDING',
    created_by NVARCHAR(100) NOT NULL DEFAULT 'system',
    created_at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    approved_by NVARCHAR(100),
    approved_at DATETIME2(0),
    supersedes_id INT,
    notes NVARCHAR(MAX)
);
GO
IF OBJECT_ID('dbo.picklist_option_alias') IS NULL
CREATE TABLE dbo.picklist_option_alias (
    alias_id INT IDENTITY(1,1) PRIMARY KEY,
    picklist_code NVARCHAR(100) NOT NULL,
    option_code NVARCHAR(100) NOT NULL,
    source_system NVARCHAR(100) NOT NULL,
    source_value NVARCHAR(100) NOT NULL,
    eff_date DATE NOT NULL,
    exp_date DATE NOT NULL DEFAULT '9999-12-31',
    status NVARCHAR(100) NOT NULL DEFAULT 'PENDING',
    created_by NVARCHAR(100) NOT NULL DEFAULT 'system',
    created_at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    approved_by NVARCHAR(100),
    approved_at DATETIME2(0),
    supersedes_id INT,
    notes NVARCHAR(MAX)
);
GO
IF OBJECT_ID('dbo.bureau_code_map') IS NULL
CREATE TABLE dbo.bureau_code_map (
    code_map_id INT IDENTITY(1,1) PRIMARY KEY,
    bureau_code NVARCHAR(100) NOT NULL,
    lob_scope NVARCHAR(100) NOT NULL DEFAULT '*',
    picklist_code NVARCHAR(100) NOT NULL,
    option_code NVARCHAR(100) NOT NULL,
    bureau_value NVARCHAR(100) NOT NULL,
    eff_date DATE NOT NULL,
    exp_date DATE NOT NULL DEFAULT '9999-12-31',
    status NVARCHAR(100) NOT NULL DEFAULT 'PENDING',
    created_by NVARCHAR(100) NOT NULL DEFAULT 'system',
    created_at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    approved_by NVARCHAR(100),
    approved_at DATETIME2(0),
    supersedes_id INT,
    notes NVARCHAR(MAX)
);
GO
IF OBJECT_ID('dbo.layout_version') IS NULL
CREATE TABLE dbo.layout_version (
    layout_id INT IDENTITY(1,1) PRIMARY KEY,
    bureau_code NVARCHAR(100) NOT NULL,
    lob_code NVARCHAR(100) NOT NULL,
    record_type NVARCHAR(100) NOT NULL,
    version_no INT NOT NULL,
    record_length INT NOT NULL DEFAULT 150,
    source_file NVARCHAR(MAX),
    eff_date DATE NOT NULL,
    exp_date DATE NOT NULL DEFAULT '9999-12-31',
    status NVARCHAR(100) NOT NULL DEFAULT 'PENDING',
    created_by NVARCHAR(100) NOT NULL DEFAULT 'system',
    created_at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    approved_by NVARCHAR(100),
    approved_at DATETIME2(0),
    supersedes_id INT,
    notes NVARCHAR(MAX)
);
GO
IF OBJECT_ID('dbo.layout_field') IS NULL
CREATE TABLE dbo.layout_field (
    field_id INT IDENTITY(1,1) PRIMARY KEY,
    layout_id INT NOT NULL REFERENCES dbo.layout_version(layout_id),
    seq INT NOT NULL,
    bureau_field_name NVARCHAR(1000) NOT NULL,
    start_pos INT NOT NULL,
    length INT NOT NULL,
    field_format NVARCHAR(100) NOT NULL,
    required NVARCHAR(100) NOT NULL DEFAULT 'Y',
    element_code NVARCHAR(100) NOT NULL,
    transform_rule_code NVARCHAR(100) NOT NULL,
    bureau_description NVARCHAR(MAX),
    business_description NVARCHAR(MAX),
    eff_date DATE NOT NULL,
    exp_date DATE NOT NULL DEFAULT '9999-12-31',
    status NVARCHAR(100) NOT NULL DEFAULT 'PENDING',
    created_by NVARCHAR(100) NOT NULL DEFAULT 'system',
    created_at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    approved_by NVARCHAR(100),
    approved_at DATETIME2(0),
    supersedes_id INT,
    notes NVARCHAR(MAX)
);
GO
IF OBJECT_ID('dbo.business_rule') IS NULL
CREATE TABLE dbo.business_rule (
    rule_id INT IDENTITY(1,1) PRIMARY KEY,
    rule_code NVARCHAR(100) NOT NULL,
    rule_name NVARCHAR(1000) NOT NULL,
    rule_category NVARCHAR(100) NOT NULL,
    bureau_code NVARCHAR(100) NOT NULL DEFAULT 'ISO',
    lob_scope NVARCHAR(100) NOT NULL DEFAULT '*',
    record_type_scope NVARCHAR(100) NOT NULL DEFAULT '*',
    state_scope NVARCHAR(100) NOT NULL DEFAULT '*',
    element_code NVARCHAR(100),
    expression_json NVARCHAR(MAX) NOT NULL,
    severity NVARCHAR(100) NOT NULL DEFAULT 'ERROR',
    message NVARCHAR(MAX),
    business_description NVARCHAR(MAX),
    eff_date DATE NOT NULL,
    exp_date DATE NOT NULL DEFAULT '9999-12-31',
    status NVARCHAR(100) NOT NULL DEFAULT 'PENDING',
    created_by NVARCHAR(100) NOT NULL DEFAULT 'system',
    created_at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    approved_by NVARCHAR(100),
    approved_at DATETIME2(0),
    supersedes_id INT,
    notes NVARCHAR(MAX)
);
GO
IF OBJECT_ID('dbo.approval_log') IS NULL
CREATE TABLE dbo.approval_log (
    log_id INT IDENTITY(1,1) PRIMARY KEY,
    object_table NVARCHAR(100) NOT NULL,
    object_id INT NOT NULL,
    action NVARCHAR(100) NOT NULL,
    actor NVARCHAR(100) NOT NULL,
    comment NVARCHAR(MAX),
    at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME()
);
GO
IF OBJECT_ID('dbo.source_transaction') IS NULL
CREATE TABLE dbo.source_transaction (
    txn_id INT IDENTITY(1,1) PRIMARY KEY,
    source_system NVARCHAR(100) NOT NULL,
    source_txn_key NVARCHAR(100) NOT NULL,
    record_type NVARCHAR(100) NOT NULL,
    lob_code NVARCHAR(100) NOT NULL,
    accounting_date DATE NOT NULL,
    payload_json NVARCHAR(MAX) NOT NULL,
    corrects_txn_id INT,
    corrected_by NVARCHAR(100),
    correction_note NVARCHAR(100),
    loaded_at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME()
);
GO
IF OBJECT_ID('dbo.submission_batch') IS NULL
CREATE TABLE dbo.submission_batch (
    batch_id INT IDENTITY(1,1) PRIMARY KEY,
    bureau_code NVARCHAR(100) NOT NULL,
    lob_code NVARCHAR(100) NOT NULL,
    record_type NVARCHAR(100) NOT NULL,
    period_type NVARCHAR(100) NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    layout_id INT,
    status NVARCHAR(100) NOT NULL,
    record_count INT DEFAULT 0,
    valid_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    warning_count INT DEFAULT 0,
    total_premium DECIMAL(18,2) DEFAULT 0,
    total_paid DECIMAL(18,2) DEFAULT 0,
    total_outstanding DECIMAL(18,2) DEFAULT 0,
    total_alae DECIMAL(18,2) DEFAULT 0,
    file_name NVARCHAR(1000),
    file_text NVARCHAR(MAX),
    parent_batch_id INT,
    created_by NVARCHAR(100),
    created_at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    sme_approved_by NVARCHAR(100),
    sme_approved_at DATETIME2(0),
    submitted_at DATETIME2(0),
    response_at DATETIME2(0),
    closed_at DATETIME2(0)
);
GO
IF OBJECT_ID('dbo.submission_record') IS NULL
CREATE TABLE dbo.submission_record (
    rec_id INT IDENTITY(1,1) PRIMARY KEY,
    batch_id INT NOT NULL REFERENCES dbo.submission_batch(batch_id),
    txn_id INT NOT NULL,
    line_no INT,
    record_text NVARCHAR(MAX),
    canonical_json NVARCHAR(MAX),
    status NVARCHAR(100) NOT NULL,
    messages_json NVARCHAR(MAX)
);
GO
IF OBJECT_ID('dbo.batch_event') IS NULL
CREATE TABLE dbo.batch_event (
    event_id INT IDENTITY(1,1) PRIMARY KEY,
    batch_id INT NOT NULL,
    status_from NVARCHAR(100),
    status_to NVARCHAR(100) NOT NULL,
    actor NVARCHAR(100),
    comment NVARCHAR(MAX),
    at DATETIME2(0) NOT NULL DEFAULT SYSDATETIME()
);
GO
CREATE INDEX IX_canonical_element_status_eff ON dbo.canonical_element(status, eff_date, exp_date);
CREATE INDEX IX_element_alias_status_eff ON dbo.element_alias(status, eff_date, exp_date);
CREATE INDEX IX_source_mapping_status_eff ON dbo.source_mapping(status, eff_date, exp_date);
CREATE INDEX IX_picklist_status_eff ON dbo.picklist(status, eff_date, exp_date);
CREATE INDEX IX_picklist_alias_status_eff ON dbo.picklist_alias(status, eff_date, exp_date);
CREATE INDEX IX_picklist_option_status_eff ON dbo.picklist_option(status, eff_date, exp_date);
CREATE INDEX IX_picklist_option_alias_status_eff ON dbo.picklist_option_alias(status, eff_date, exp_date);
CREATE INDEX IX_bureau_code_map_status_eff ON dbo.bureau_code_map(status, eff_date, exp_date);
CREATE INDEX IX_layout_version_status_eff ON dbo.layout_version(status, eff_date, exp_date);
CREATE INDEX IX_layout_field_status_eff ON dbo.layout_field(status, eff_date, exp_date);
CREATE INDEX IX_business_rule_status_eff ON dbo.business_rule(status, eff_date, exp_date);
CREATE INDEX IX_layout_field_layout ON dbo.layout_field(layout_id, seq);
CREATE INDEX IX_source_txn_period ON dbo.source_transaction(lob_code, record_type, accounting_date);
CREATE INDEX IX_submission_record_batch ON dbo.submission_record(batch_id, status);
GO
