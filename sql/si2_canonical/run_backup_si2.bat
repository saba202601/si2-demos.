@echo off
rem SI2Canonical backup: full backup with checksums, verified, zipped, copied to Desktop\SI2 Backups (synced to Google Drive)
rem and to OneDrive\SI2 Backups when OneDrive is on this PC. Keeps the 10 newest. Output: backup_log.txt in this folder.
cd /d "%~dp0"
set LOG=backup_log.txt
echo SI2Canonical backup %DATE% %TIME% > %LOG%
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
%PY% backup_si2.py --database SI2Canonical >> %LOG% 2>&1
:end
echo FINISHED %DATE% %TIME% >> %LOG%
type %LOG%
timeout /t 20
