      *================================================================*
      * INSURE/400  CLAIM MASTER RECORD             COPYBOOK CLMMAST   *
      *================================================================*
       01  CLM-MASTER-REC.
           05  CL-CLAIM-NO             PIC X(10).
           05  CL-POLICY-NO            PIC X(10).
           05  CL-LOSS-DATE            PIC 9(8).
           05  CL-CAUSE-CD             PIC X(3).
           05  CL-STATUS               PIC X(1).
               88  CL-STAT-OPEN            VALUE 'O'.
               88  CL-STAT-CLOSED          VALUE 'C'.
               88  CL-STAT-REOPENED        VALUE 'R'.
           05  CL-OS-RSV               PIC 9(7)V99.
           05  CL-PAY-CNT              PIC 9(1).
           05  CL-PAYMENT OCCURS 3 TIMES.
               10  CL-PAY-DATE         PIC 9(8).
               10  CL-PAY-AMT          PIC 9(7)V99.
           05  FILLER                  PIC X(2).
