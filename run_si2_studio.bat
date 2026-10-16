@echo off
rem SI2 Studio: every SI2 engine in one app on this PC. The Rule Studio works on SI2Canonical (Windows sign-in);
rem the other engines use their synthetic demo data. Opens http://localhost:8501 - keep this window open while you use it.
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
%PY% -c "import streamlit, pandas, numpy, pypdf, openpyxl" >nul 2>&1 || %PY% -m pip install --quiet streamlit pandas numpy pypdf openpyxl > si2_studio_install_log.txt 2>&1
%PY% -c "import streamlit" >nul 2>&1 || (echo Could not install Streamlit. See si2_studio_install_log.txt & pause & exit /b 1)
echo Starting SI2 Studio at http://localhost:8501 ... keep this window open.
%PY% -m streamlit run si2_studio.py --server.headless false --browser.gatherUsageStats false > si2_studio_log.txt 2>&1
