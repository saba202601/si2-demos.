@echo off
rem SI2 Canonical Master: refresh, approve the seeded ISO changes, then collect from SQLEXPRESS02 and the prior SQLEXPRESS.
rem Proposals are made by 'SI2 collector' and approved as Saba (the second person). Output: run_log.txt in this folder.
cd /d "%~dp0"
set LOG=run_log.txt
echo SI2 Canonical run %DATE% %TIME% > %LOG%

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

echo ===== 1. REFRESH SI2Canonical ===== >> %LOG%
%PY% install_si2_canonical.py >> %LOG% 2>&1
if errorlevel 1 goto :end
echo. >> %LOG%
echo ===== 2. COLLECT from SQLEXPRESS02 (approved as Saba) ===== >> %LOG%
%PY% collect_si2_databases.py --approve-seed --discover --approve-as "Saba" >> %LOG% 2>&1
echo. >> %LOG%
echo ===== 3. COLLECT from the prior version SQLEXPRESS (approved as Saba) ===== >> %LOG%
%PY% collect_si2_databases.py --source-server "SABAHOME\SQLEXPRESS" --approve-as "Saba" >> %LOG% 2>&1

:end
echo. >> %LOG%
echo FINISHED %DATE% %TIME% >> %LOG%
type %LOG%
timeout /t 15
