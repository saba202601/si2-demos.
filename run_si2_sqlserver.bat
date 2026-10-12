@echo off
REM SI2 demos on SQL Server Express (Windows Authentication): decisions and approvals are saved permanently.
REM Usage: run_si2_sqlserver.bat app_migration.py   (or app_rules.py, app_rating.py, app_bureau.py ...)
cd /d "%~dp0"
python -m pip install -q streamlit pandas numpy openpyxl pypdf pyodbc
set SI2_STATE_BACKEND=mssql
set SI2_BUREAU_BACKEND=mssql
set SI2_MSSQL_SERVER=SABAHOME\SQLEXPRESS02
set SI2_MSSQL_DATABASE=ISOBureauReporting
set APP=%1
if "%APP%"=="" set APP=app_migration.py
python -m streamlit run %APP%
