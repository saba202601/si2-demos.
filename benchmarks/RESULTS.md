# Initial-load benchmark

`python -m benchmarks.initial_load_benchmark --policies 100000` (synthetic Personal Auto book, SQLite target,
one cloud container, 2026-10-12):

| Stage | Time |
|---|---|
| Read 3 CSV files (980,000 rows) | 1.8 s |
| Profile every column | 4.1 s |
| Propose keys (incl. claim → policy term in force) | 3.9 s |
| Data edits (Q01-Q10) | 3.8 s |
| Create tables + load parent-first | 28.1 s |
| **Total** | **41.7 s (≈ 23,500 rows/s)** |

200,000 policy terms, 300,000 claims and 480,000 payments loaded; rows and money totals reconcile; 0 foreign-key
violations. Keys found: policy (pol_no, eff_dt), claim → policy term in force on the loss date, payment → claim.
For tens of millions of rows the same plan runs table by table into SQL Server or PostgreSQL with bulk insert.
