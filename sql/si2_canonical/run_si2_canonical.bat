@echo off
rem SI2 Canonical Master: self-test, install, then collect from RuleEngine, BureauReporting and ISOBureauReporting.
rem Proposals are left waiting for a person to approve (two-person rule). Output: run_log.txt in this folder.
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
  echo pyodbc not found; installing it for the current user... >> %LOG%
  python -m pip install --user pyodbc >> %LOG% 2>&1
  python -c "import pyodbc" >nul 2>&1 && set PY=python
)
if not defined PY (
  echo FAILED: no Python with pyodbc. >> %LOG%
  goto :end
)
echo Python: %PY% >> %LOG%

echo. >> %LOG%
echo ===== 1. SELF-TEST ===== >> %LOG%
%PY% install_si2_canonical.py --selftest >> %LOG% 2>&1
if errorlevel 1 (
  echo SELF-TEST DID NOT PASS - stopping before the real install. >> %LOG%
  goto :end
)
echo. >> %LOG%
echo ===== 2. INSTALL ===== >> %LOG%
%PY% install_si2_canonical.py --demo >> %LOG% 2>&1
if errorlevel 1 goto :end
echo. >> %LOG%
echo ===== 3. COLLECT (dry run) ===== >> %LOG%
%PY% collect_si2_databases.py --dry-run >> %LOG% 2>&1
echo. >> %LOG%
echo ===== 4. COLLECT (propose) ===== >> %LOG%
%PY% collect_si2_databases.py >> %LOG% 2>&1

:end
echo. >> %LOG%
echo FINISHED %DATE% %TIME% >> %LOG%
type %LOG%
timeout /t 15
