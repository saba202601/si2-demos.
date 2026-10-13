@echo off
rem SI2 Canonical Master. Apply the newest duplicate_review_<time>.xlsx: rows marked MERGE / EXPIRE, approved as Saba
cd /d "%~dp0"
set LOG=apply_review_log.txt
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
%PY% review_duplicates.py --apply latest --approve-as "Saba" >> %LOG% 2>&1
:end
echo FINISHED %DATE% %TIME% >> %LOG%
type %LOG%
timeout /t 20
