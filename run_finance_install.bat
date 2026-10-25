@echo off
rem SI2 Financial Reporting: create schema fin in SI2Canonical and load the Yellow Book, the ontology and the synthetic feeds.
cd /d "%~dp0"
set SI2_SQL_SERVER=SABAHOME\SQLEXPRESS02
set SI2_SQL_DATABASE=SI2Canonical
set PY=
for %%P in ("%USERPROFILE%\venv\Scripts\python.exe" "python" "py") do (
  if not defined PY (
    %%~P -c "import pyodbc, pandas" >nul 2>&1 && set PY=%%~P
  )
)
if not defined PY (
  echo No Python with pyodbc and pandas was found.
  pause
  exit /b 1
)
%PY% -m finance.install > finance_install_log.txt 2>&1
type finance_install_log.txt
echo.
echo Done. Open SI2 Studio, then Financial Reporting (Yellow Book). Details: finance_install_log.txt
pause
