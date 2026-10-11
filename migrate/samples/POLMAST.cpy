      *================================================================*
      * INSURE/400  POLICY MASTER RECORD            COPYBOOK POLMAST   *
      *================================================================*
       01  POL-MASTER-REC.
           05  PM-POLICY-NO            PIC X(10).
           05  PM-INSURED-NAME         PIC X(30).
           05  PM-EFF-DATE             PIC 9(8).
           05  PM-EXP-DATE             PIC 9(8).
           05  PM-STATE                PIC X(2).
           05  PM-LOB-CD               PIC X(2).
               88  PM-LOB-PERS-AUTO        VALUE 'PA'.
               88  PM-LOB-HOMEOWNERS       VALUE 'HO'.
               88  PM-LOB-WORKERS-COMP     VALUE 'WC'.
           05  PM-STATUS               PIC X(1).
               88  PM-STAT-ACTIVE          VALUE 'A'.
               88  PM-STAT-CANCELLED       VALUE 'C'.
               88  PM-STAT-EXPIRED         VALUE 'E'.
               88  PM-STAT-SUSPENDED       VALUE 'S'.
           05  PM-WRITTEN-PREM         PIC 9(7)V99.
           05  PM-AGENT-NO             PIC X(6).
           05  PM-PAY-PLAN             PIC X(1).
               88  PM-PAY-ANNUAL           VALUE '1'.
               88  PM-PAY-SEMI-ANNUAL      VALUE '2'.
               88  PM-PAY-QUARTERLY        VALUE '4'.
               88  PM-PAY-MONTHLY          VALUE 'M'.
           05  FILLER                  PIC X(3).
