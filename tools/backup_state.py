"""Back up everything SI² has saved: one JSON file per client workspace (works for SQLite, SQL Server and
PostgreSQL), plus a byte-for-byte copy of the SQLite file when that is the backend. Keeps the newest N sets.

    python -m tools.backup_state --out backups --keep 30

Schedule it: Windows Task Scheduler (run_si2_backup.bat, daily) or cron. Hosted PostgreSQL (Azure, RDS) also keeps
its own automatic backups; this export is the portable, per-client copy.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from si2_common import store  # noqa: E402


def run(out: str = "backups", keep: int = 30) -> list[Path]:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = Path(out) / stamp
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for ws in store.workspaces():
        p = folder / f"SI2_backup_{ws}.json"
        p.write_text(store.export_workspace(ws))
        written.append(p)
    if store.backend() == "sqlite":
        src = sqlite3.connect(Path(store._setting("SI2_STATE_DB", str(store.ROOT / "data" / "si2_state.db"))))
        dst = sqlite3.connect(folder / "si2_state.db")
        src.backup(dst)
        dst.close()
        src.close()
        written.append(folder / "si2_state.db")
    sets = sorted(d for d in Path(out).iterdir() if d.is_dir())
    for old in sets[:-keep] if keep > 0 else []:
        for f in old.iterdir():
            f.unlink()
        old.rmdir()
    return written


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="backups")
    ap.add_argument("--keep", type=int, default=30)
    a = ap.parse_args()
    for p in run(a.out, a.keep):
        print("backed up", p)
