@echo off
rem SI2 insurance forms: every field, alias, pick list and option on the fillable PDFs in acord_forms\ goes into SI2Canonical
rem (proposed by the collector, approved as Saba), with where-used rows per form. Output: forms_log.txt and forms_report_*.csv here.
cd /d "%~dp0"
set LOG=forms_log.txt
echo SI2 insurance forms %DATE% %TIME% > %LOG%
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
%PY% -c "import pypdf" >nul 2>&1 || %PY% -m pip install -q "pypdf>=4.0" >> %LOG% 2>&1
if not exist acord_forms\*.pdf (
  echo FAILED: put the fillable PDF forms in %~dp0acord_forms\ first. >> %LOG%
  goto :end
)
echo ===== 1. SELF-TEST on temporary databases ===== >> %LOG%
%PY% install_si2_canonical.py --selftest >> %LOG% 2>&1
if errorlevel 1 goto :end
echo. >> %LOG%
echo ===== 2. UPDATE SI2Canonical (crime entities added to the model) ===== >> %LOG%
%PY% install_si2_canonical.py >> %LOG% 2>&1
if errorlevel 1 goto :end
echo. >> %LOG%
echo ===== 3. COMMERCIAL APPLICATION MODEL incl. crime (approved as Saba) ===== >> %LOG%
%PY% collect_si2_databases.py --commercial-app --approve-as "Saba" >> %LOG% 2>&1
echo. >> %LOG%
echo ===== 4. EVERY FIELD ON THE FORMS (approved as Saba) ===== >> %LOG%
%PY% collect_si2_databases.py --forms acord_forms --approve-as "Saba" >> %LOG% 2>&1
echo. >> %LOG%
echo ===== 5. RUN AGAIN: nothing new should be proposed ===== >> %LOG%
%PY% collect_si2_databases.py --forms acord_forms --dry-run >> %LOG% 2>&1
:end
echo. >> %LOG%
echo FINISHED %DATE% %TIME% >> %LOG%
type %LOG%
timeout /t 15
