@echo off
rem SI2 Canonical Master. Duplicate review: refresh the procedures, then write duplicate_review_<time>.xlsx (nothing in the master changes)
cd /d "%~dp0"
set LOG=duplicate_review_log.txt
echo SI2 run %DATE% %TIME% > %LOG%
set PY=
for %%P in ("%USERPROFILE%\venv\Scripts\python.exe" "python" "py") do (
  if not defined PY (
    %%~P -c "import pyodbc, openpyxl" >nul 2>&1 && set PY=%%~P
  )
)
if not defined PY (
  for %%P in ("%USERPROFILE%\venv\Scripts\python.exe" "python" "py") do (
    if not defined PY (
      %%~P -c "import pyodbc" >nul 2>&1 && set PY=%%~P
    )
  )
)
if not defined PY (
  echo FAILED: no Python with pyodbc. >> %LOG%
  goto :end
)
%PY% install_si2_canonical.py >> %LOG% 2>&1
%PY% review_duplicates.py >> %LOG% 2>&1
:end
echo FINISHED %DATE% %TIME% >> %LOG%
type %LOG%
timeout /t 20
