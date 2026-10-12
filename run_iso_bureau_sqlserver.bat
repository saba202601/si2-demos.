@echo off
REM SI2 ISO Bureau Reporting on SQL Server Express (Windows Authentication)
cd /d "%~dp0"
python -m pip install -q streamlit pandas openpyxl pyodbc
set SI2_BUREAU_BACKEND=mssql
set SI2_MSSQL_SERVER=SABAHOME\SQLEXPRESS02
set SI2_MSSQL_DATABASE=ISOBureauReporting
python -m iso_bureau.check_sqlserver
if errorlevel 1 (pause & exit /b 1)
python -m streamlit run app_iso_bureau.py
