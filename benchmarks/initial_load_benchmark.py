"""Initial-load benchmark: about one million synthetic rows (policy terms, claims, payments).

    python -m benchmarks.initial_load_benchmark --policies 100000

Times every stage (read, profile, propose, edits, create + load) and checks that the reconciliation balances.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from migrate import initial_load as IL  # noqa: E402


def synth(n_pol: int, seed: int = 3):
    rng = np.random.default_rng(seed)
    states = np.array(["FL", "GA", "NC", "NY", "OH", "TX", "NJ", "PA"])
    pol_no = np.char.add("PA", np.char.zfill(np.arange(1, n_pol + 1).astype(str), 7))
    terms = 2
    p_no = np.repeat(pol_no, terms)
    start = pd.to_datetime("2023-01-01") + pd.to_timedelta(rng.integers(0, 365, n_pol), "D")
    eff = np.concatenate([start.values[:, None] + np.array([0, 365], "timedelta64[D]")], axis=1).reshape(-1)
    eff = pd.to_datetime(eff)
    exp = eff + pd.Timedelta(days=365)
    n_t = len(p_no)
    pol = pd.DataFrame({"POL_NO": p_no, "EFF_DT": eff.strftime("%Y-%m-%d"), "EXP_DT": exp.strftime("%Y-%m-%d"),
                        "STATE_CD": rng.choice(states, n_t), "ZIP_CD": np.char.zfill(rng.integers(1000, 99999, n_t).astype(str), 5),
                        "LOB_CD": "AUTOP", "WRITTEN_PREM": np.round(rng.uniform(500, 4000, n_t), 2),
                        "POL_STATUS": np.where(np.arange(n_t) % 2, "A", "E")})
    n_c = int(n_t * 1.5)
    ti = rng.integers(0, n_t, n_c)
    loss = eff[ti] + pd.to_timedelta(rng.integers(1, 360, n_c), "D")
    clm = pd.DataFrame({"CLAIM_NO": np.char.add("CL", np.char.zfill(np.arange(1, n_c + 1).astype(str), 8)),
                        "POL_NO": p_no[ti], "LOSS_DT": loss.strftime("%Y-%m-%d"),
                        "REPORT_DT": (loss + pd.to_timedelta(rng.integers(0, 20, n_c), "D")).strftime("%Y-%m-%d"),
                        "CLAIM_STATUS": rng.choice(["O", "C", "R"], n_c), "RESERVE_AMT": np.round(rng.uniform(0, 9000, n_c), 2)})
    n_p = int(n_c * 1.6)
    ci = rng.integers(0, n_c, n_p)
    pay = pd.DataFrame({"PMT_ID": np.char.zfill(np.arange(1, n_p + 1).astype(str), 9), "CLAIM_NO": clm.CLAIM_NO.values[ci],
                        "PMT_DT": (pd.to_datetime(clm.REPORT_DT.values[ci]) + pd.to_timedelta(rng.integers(1, 200, n_p), "D"))
                        .strftime("%m/%d/%Y"),
                        "PMT_AMT": np.round(rng.uniform(50, 5000, n_p), 2).astype(str), "PMT_TYPE": rng.choice(["IND", "MED", "EXP"], n_p)})
    return pol, clm, pay


def run(n_pol: int):
    t0 = time.time()
    pol, clm, pay = synth(n_pol)
    files = [(f"{n}.csv", d.to_csv(index=False).encode()) for n, d in (("policy", pol), ("claim", clm), ("claim_payment", pay))]
    total = len(pol) + len(clm) + len(pay)
    print(f"synthetic rows: {total:,} (policy terms {len(pol):,}, claims {len(clm):,}, payments {len(pay):,}) "
          f"in {time.time() - t0:.1f}s")
    times = {}

    def tick(name, t):
        times[name] = time.time() - t
        print(f"  {name:<16}{times[name]:7.1f}s")
    t = time.time(); st = IL.stage(files); tick("read", t)
    t = time.time(); prof = IL.profile(st); tick("profile", t)
    t = time.time(); props = IL.propose(st, prof); tick("propose keys", t)
    props.loc[(props.confidence >= 90) & ~props.conflict, "status"] = "Approved"
    t = time.time(); ed = IL.quality_edits(st, prof, props); tick("data edits", t)
    db = str(Path(tempfile.gettempdir()) / "si2_benchmark.db")
    t = time.time(); r = IL.build_and_load(st, prof, props, db, "benchmark", blocked=IL.blocked_rows(ed, set())); tick("create + load", t)
    rec = r["recon"]
    print(rec[["table", "source rows", "loaded", "quarantined", "rows balance", "totals balance"]].to_string(index=False))
    print(f"total {sum(times.values()):.1f}s for {total:,} rows · {total / sum(times.values()):,.0f} rows/s · "
          f"FK violations {r['fk_violations']} · keys: "
          + "; ".join(f"{x.table}({', '.join(x.columns)})" for x in props[(props.kind != 'PICKLIST') & (props.status == 'Approved')].itertuples()))
    return times, r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--policies", type=int, default=100_000)
    run(ap.parse_args().policies)
