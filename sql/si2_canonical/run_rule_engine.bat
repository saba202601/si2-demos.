@echo off
rem SI2 Rule Engine: add the rule engine and the rule library to SI2Canonical, then self-test everything on a throw-away copy.
rem Output: rule_engine_log.txt in this folder.
cd /d "%~dp0"
set LOG=rule_engine_log.txt
echo SI2 Rule Engine run %DATE% %TIME% > %LOG%

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

echo ===== 1. SELF-TEST on temporary databases ===== >> %LOG%
%PY% install_si2_canonical.py --selftest >> %LOG% 2>&1
if errorlevel 1 goto :end
echo. >> %LOG%
echo ===== 2. ADD the rule engine and library to SI2Canonical ===== >> %LOG%
%PY% install_si2_canonical.py >> %LOG% 2>&1

:end
echo. >> %LOG%
echo FINISHED %DATE% %TIME% >> %LOG%
type %LOG%
timeout /t 15
