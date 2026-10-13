@echo off
rem SI2 claim coverage check: self-test, add the claim tables to SI2Canonical, read any forms in the "forms" folder, check every claim.
rem Put the company's policy forms (PDF or TXT, file name = form number) in the "forms" folder next to this file. Log: claim_check_log.txt
cd /d "%~dp0"
set LOG=claim_check_log.txt
echo SI2 claim check %DATE% %TIME% > %LOG%
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
%PY% -c "import pypdf" >nul 2>&1 || %PY% -m pip install --quiet pypdf >> %LOG% 2>&1
echo ===== 1. SELF-TEST on temporary databases ===== >> %LOG%
%PY% install_si2_canonical.py --selftest >> %LOG% 2>&1
if errorlevel 1 goto :end
echo. >> %LOG%
echo ===== 2. ADD the claim coverage tables to SI2Canonical ===== >> %LOG%
%PY% install_si2_canonical.py >> %LOG% 2>&1
if errorlevel 1 goto :end
echo. >> %LOG%
echo ===== 3. CHECK every claim ===== >> %LOG%
if exist forms\*.* (
  %PY% check_claims.py --load-forms forms >> %LOG% 2>&1
) else (
  %PY% check_claims.py >> %LOG% 2>&1
)
:end
echo. >> %LOG%
echo FINISHED %DATE% %TIME% >> %LOG%
type %LOG%
timeout /t 15
