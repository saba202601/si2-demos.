@echo off
rem SI2 commercial application model (Party first): self-test, add the entity layer, collect the elements and pick lists (approved as Saba).
rem Output: commercial_app_log.txt and party_model_*.csv in this folder.
cd /d "%~dp0"
set LOG=commercial_app_log.txt
echo SI2 commercial application model %DATE% %TIME% > %LOG%
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
echo ===== 2. ADD the entity layer to SI2Canonical ===== >> %LOG%
%PY% install_si2_canonical.py >> %LOG% 2>&1
if errorlevel 1 goto :end
echo. >> %LOG%
echo ===== 3. COLLECT the commercial application vocabulary (approved as Saba) ===== >> %LOG%
%PY% collect_si2_databases.py --commercial-app --approve-as "Saba" >> %LOG% 2>&1
echo. >> %LOG%
echo ===== 4. THE PARTY MODEL AS IT IS NOW ===== >> %LOG%
%PY% show_entity_model.py >> %LOG% 2>&1
:end
echo. >> %LOG%
echo FINISHED %DATE% %TIME% >> %LOG%
type %LOG%
timeout /t 15
