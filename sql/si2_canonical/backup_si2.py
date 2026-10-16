"""Back up SI2Canonical (or any database) and copy the backup to folders that sync to the cloud.

    python backup_si2.py                         # SI2Canonical -> Desktop\\SI2 Backups (Google Drive) and OneDrive\\SI2 Backups
    python backup_si2.py --database ISOBureauReporting --keep 10

Steps: SQL Server writes a full backup with checksums to C:\\Projects\\AGI-INS\\si2_backups (the folder is shared with the
SQL Server service), verifies it can be restored (RESTORE VERIFYONLY), zips it, and copies the zip to every cloud folder found.
Windows sign-in only; nothing is deleted except older backups beyond --keep.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

DRIVERS = ["ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "ODBC Driver 13 for SQL Server",
           "SQL Server Native Client 11.0", "SQL Server"]


def connect(server):
    import pyodbc
    driver = next((d for d in DRIVERS if d in pyodbc.drivers()), None)
    if not driver:
        raise SystemExit("No SQL Server ODBC driver on this PC.")
    return pyodbc.connect(f"DRIVER={{{driver}}};SERVER={server};DATABASE=master;Trusted_Connection=yes;TrustServerCertificate=yes;",
                          autocommit=True)


def run(cur, sql):
    cur.execute(sql)
    while True:                       # BACKUP / RESTORE report progress as messages: read them all so the command finishes
        try:
            if not cur.nextset():
                break
        except Exception:  # noqa: BLE001
            break


def cloud_folders() -> list[Path]:
    home = Path(os.environ.get("USERPROFILE", Path.home()))
    desktop = home / "Desktop"
    try:                              # the real Desktop (it may be redirected); Google Drive syncs it on this PC
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"], capture_output=True, text=True, timeout=30)
        if r.stdout.strip():
            desktop = Path(r.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    out = []
    for root in dict.fromkeys([desktop, Path(os.environ.get("OneDrive", "") or "/nonexistent")]):
        if root.exists():
            out.append(root / "SI2 Backups")
    return out


def keep_latest(folder: Path, pattern: str, keep: int) -> None:
    files = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default=os.environ.get("SI2_SQL_SERVER", "SABAHOME\\SQLEXPRESS02"))
    ap.add_argument("--database", default="SI2Canonical")
    ap.add_argument("--folder", default=r"C:\Projects\AGI-INS\si2_backups")
    ap.add_argument("--keep", type=int, default=10, help="backups kept in each folder")
    a = ap.parse_args()

    folder = Path(a.folder)
    folder.mkdir(parents=True, exist_ok=True)
    con = connect(a.server)
    cur = con.cursor()
    # let the SQL Server service write into the folder (it runs under its own account)
    try:
        cur.execute("SELECT TOP (1) service_account FROM sys.dm_server_services WHERE servicename LIKE 'SQL Server (%'")
        account = cur.fetchone()[0]
    except Exception:  # noqa: BLE001
        account = "NT SERVICE\\MSSQL$" + a.server.split("\\")[-1]
    subprocess.run(["icacls", str(folder), "/grant", f"{account}:(OI)(CI)M"], capture_output=True)

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    bak = folder / f"{a.database}_{stamp}.bak"
    path = str(bak).replace("'", "''")
    name = f"{a.database} full backup {stamp}".replace("'", "''")
    print(f"Backing up {a.database} on {a.server} ...")
    try:
        run(cur, f"BACKUP DATABASE [{a.database}] TO DISK = N'{path}' WITH INIT, CHECKSUM, COPY_ONLY, COMPRESSION, NAME = N'{name}'")
    except Exception as ex:  # noqa: BLE001 - SQL Server Express cannot compress: back up without it
        if "COMPRESSION" not in str(ex).upper():
            raise
        run(cur, f"BACKUP DATABASE [{a.database}] TO DISK = N'{path}' WITH INIT, CHECKSUM, COPY_ONLY, NAME = N'{name}'")
    if not bak.exists():
        print(f"FAILED: SQL Server did not write {bak}. Check that the SQL Server service ({account}) can write to {folder}.")
        return 1
    run(cur, f"RESTORE VERIFYONLY FROM DISK = N'{path}' WITH CHECKSUM")
    print(f"  backup written and verified: {bak}  ({bak.stat().st_size / 1e6:,.1f} MB)")

    zpath = bak.with_suffix(".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.write(bak, bak.name)
    print(f"  zipped: {zpath.name}  ({zpath.stat().st_size / 1e6:,.1f} MB)")
    keep_latest(folder, f"{a.database}_*.bak", 3)
    keep_latest(folder, f"{a.database}_*.zip", a.keep)

    copies = []
    for target in cloud_folders():
        try:
            target.mkdir(exist_ok=True)
            shutil.copy2(zpath, target / zpath.name)
            keep_latest(target, f"{a.database}_*.zip", a.keep)
            copies.append(target)
        except OSError as ex:
            print(f"  could not copy to {target}: {ex}")
    for t in copies:
        print(f"  copied to {t}")
    if not copies:
        print("  no cloud folder found (Desktop synced by Google Drive, or OneDrive); the backup is only on this PC.")
    print("Backup OK")
    print(f"\nTo restore (SSMS, or sqlcmd):  RESTORE DATABASE [{a.database}] FROM DISK = N'<the .bak from the zip>' WITH REPLACE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
