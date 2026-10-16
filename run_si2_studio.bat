@echo off
rem SI2 Studio: every SI2 engine in one desktop app on this PC.
rem The Rule Studio and the Canonical Master work on SI2Canonical (Windows sign-in); the other engines use their synthetic demo data.
rem First run: creates an "SI2 Studio" shortcut on your desktop. Keep this window open while you use the Studio; close it to stop.
cd /d "%~dp0"
title SI2 Studio
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
echo Checking the Studio's Python packages ...
%PY% -c "import streamlit, pandas, numpy, pypdf, openpyxl" >nul 2>&1 || %PY% -m pip install --quiet streamlit pandas numpy pypdf openpyxl > si2_studio_install_log.txt 2>&1
%PY% -c "import streamlit" >nul 2>&1 || (echo Could not install Streamlit. See si2_studio_install_log.txt & pause & exit /b 1)

rem desktop shortcut (once)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $l=Join-Path $d 'SI2 Studio.lnk'; if(-not (Test-Path $l)){ $s=(New-Object -ComObject WScript.Shell).CreateShortcut($l); $s.TargetPath='%~f0'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%SystemRoot%\System32\imageres.dll,109'; $s.Description='SI2 Studio - every SI2 engine on SI2Canonical'; $s.Save(); Write-Host 'Desktop shortcut created: SI2 Studio' }"

echo Checking SI2Canonical ...
%PY% -m si2_common.master_source > si2_studio_check.txt 2>&1
if errorlevel 1 (
  echo   SI2Canonical could not be read - the Studio opens with demo data. Details: si2_studio_check.txt
) else (
  echo   SI2Canonical OK
)

rem a free port: 8501, or the next one if an earlier Studio is still running
for /f %%p in ('%PY% -c "import socket;s=[p for p in range(8501,8521) if socket.socket().connect_ex(('127.0.0.1',p))];print(s[0] if s else 8501)"') do set PORT=%%p

rem open the browser as soon as the Studio answers
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 90;$i++){ try{ (New-Object Net.Sockets.TcpClient('127.0.0.1',%PORT%)).Close(); Start-Process 'http://localhost:%PORT%'; break } catch { Start-Sleep -Seconds 1 } }"

echo.
echo SI2 Studio is starting at http://localhost:%PORT%  - your browser opens by itself in a few seconds.
echo Keep this window open while you use the Studio. Close it to stop.
%PY% -m streamlit run si2_studio.py --server.port %PORT% --server.headless true --browser.gatherUsageStats false > si2_studio_log.txt 2>&1
echo.
echo SI2 Studio stopped. If it did not open, see si2_studio_log.txt in %~dp0
pause
