@echo off
rem SI2 Rule Studio on your SI2Canonical database (Windows sign-in). Opens in your browser; close this window to stop it.
cd /d "%~dp0"
set SI2_SQL_SERVER=SABAHOME\SQLEXPRESS02
set SI2_SQL_DATABASE=SI2Canonical
set PY=
for %%P in ("%USERPROFILE%\venv\Scripts\python.exe" "python" "py") do (
  if not defined PY (
    %%~P -c "import pyodbc" >nul 2>&1 && set PY=%%~P
  )
)
if not defined PY (
  echo No Python with pyodbc was found.
  pause
  exit /b 1
)
%PY% -c "import streamlit, pandas" >nul 2>&1 || %PY% -m pip install --quiet streamlit pandas > studio_install_log.txt 2>&1
%PY% -c "import streamlit" >nul 2>&1 || (echo Could not install Streamlit. See studio_install_log.txt & pause & exit /b 1)
echo Starting SI2 Rule Studio at http://localhost:8501 ...
%PY% -m streamlit run app_rule_studio.py --server.headless false --browser.gatherUsageStats false > studio_log.txt 2>&1
