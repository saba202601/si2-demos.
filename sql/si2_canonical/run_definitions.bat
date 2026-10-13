@echo off
rem SI2 Canonical Master: add the held-back items with the business definitions Saba supplied (definitions_20261013.csv).
cd /d "%~dp0"
set LOG=run_definitions_log.txt
echo SI2 definitions run %DATE% %TIME% > %LOG%
set PY=
for %%P in ("%USERPROFILE%\venv\Scripts\python.exe" "python" "py") do (
  if not defined PY (
    %%~P -c "import pyodbc" >nul 2>&1 && set PY=%%~P
  )
)
if not defined PY (
  echo FAILED: no Python with pyodbc. >> %LOG%
  goto :end
)
%PY% collect_si2_databases.py --definitions definitions_20261013.csv --approve-as "Saba" >> %LOG% 2>&1
:end
echo FINISHED %DATE% %TIME% >> %LOG%
type %LOG%
timeout /t 15
