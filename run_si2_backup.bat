@echo off
REM Daily backup of SI2 decisions and approvals (all client workspaces).
REM Schedule once:  schtasks /Create /SC DAILY /ST 23:00 /TN "SI2 backup" /TR "%~dp0run_si2_backup.bat"
cd /d "%~dp0"
set SI2_STATE_BACKEND=mssql
set SI2_MSSQL_SERVER=SABAHOME\SQLEXPRESS02
set SI2_MSSQL_DATABASE=ISOBureauReporting
python -m tools.backup_state --out backups --keep 30
