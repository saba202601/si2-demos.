@echo off
rem SI2 Data Bridge: self-test, then teach SI2Canonical the demo systems' fields and values (approved as Saba)
rem and move a legacy extract to a modern policy system and an ISO-style statistical record through the canonical model.
rem Output: bridge_log.txt and the files in bridge_out\ in this folder.
cd /d "%~dp0"
set LOG=bridge_log.txt
echo SI2 Data Bridge %DATE% %TIME% > %LOG%
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
echo ===== 2. REGISTER the systems in SI2Canonical and RUN the bridge (approved as Saba) ===== >> %LOG%
%PY% run_bridge.py --register --approve-as "Saba" --rows 200 >> %LOG% 2>&1
echo. >> %LOG%
echo ===== 3. RUN AGAIN: nothing new to register ===== >> %LOG%
%PY% run_bridge.py --register --approve-as "Saba" --rows 200 >> %LOG% 2>&1
:end
echo. >> %LOG%
echo FINISHED %DATE% %TIME% >> %LOG%
type %LOG%
timeout /t 15
