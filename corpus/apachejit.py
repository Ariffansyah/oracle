"""Train the risk model on ApacheJIT instead of the synthetic stand-in.

ApacheJIT (Keshavarz & Nagappan, MSR 2022) is ~106k commits from 15 Apache
projects, labelled with SZZ. Download and train in one step:

    python -m ml_model.apachejit --download
    python -m ml_model.apachejit --csv data/apachejit_total.csv

Feature reconciliation is the whole job here. ApacheJIT's columns are not
identical to what `kamei_metrics.from_git` mines, and training on one definition
while scoring on another produces confident nonsense:

  ent    unnormalised Shannon entropy (0..6.6); we mine it normalised by
         log2(nf), so ApacheJIT's column is divided by log2(nf) on load.
  lt     absent from ApacheJIT entirely. Filled with 0.0, which makes it
         constant, so no tree ever splits on it and the real `lt` we mine at
         inference is simply ignored rather than misread.
  ndev   ApacheJIT averages developers per touched file (median 2.33, i.e.
         fractional); `from_git` matches this.
  nuc    likewise averaged per file.
  arexp  time-weighted prior commits, sum(1/(age_years+1)); `from_git` matches.

`asexp` is a straight count in both, but ApacheJIT's exact subsystem definition
is not recoverable from the CSV, so treat that one column as approximate.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np

from config import ROOT
from corpus.kamei_metrics import KAMEI_FEATURES

CSV_URL = ("https://raw.githubusercontent.com/hosseinkshvrz/apachejit/"
           "master/dataset/apachejit_total.csv")
DEFAULT_CSV = ROOT / "data" / "apachejit_total.csv"

# ApacheJIT column -> our feature name. `lt` has no source column.
COLUMN_MAP = {
    "ns": "ns", "nd": "nd", "nf": "nf", "ent": "entropy", "la": "la", "ld": "ld",
    "fix": "fix", "ndev": "ndev", "age": "age", "nuc": "nuc",
    "aexp": "exp", "arexp": "rexp", "asexp": "sexp",
}


def download(dest: Path = DEFAULT_CSV) -> Path:
    import requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {CSV_URL}")
    resp = requests.get(CSV_URL, timeout=600)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    print(f"{dest} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


def load_rows(path: Path) -> list[dict]:
    rows = list(csv.DictReader(open(path)))
    if not rows:
        raise SystemExit(f"{path} is empty")
    return rows


def row_values(row: dict) -> dict[str, float]:
    """One ApacheJIT row -> {feature: value}, reconciled to our definitions."""
    nf = float(row["nf"]) or 1.0
    out = {name: 0.0 for name in KAMEI_FEATURES}  # `lt` stays 0.0: no source column
    for src, dst in COLUMN_MAP.items():
        v = row[src]
        v = 1.0 if v == "True" else 0.0 if v == "False" else float(v)
        if dst == "entropy" and nf > 1:
            v /= math.log2(nf)  # match the normalised entropy we mine
        out[dst] = v
    return out


def features_from_row(row: dict):
    """One ApacheJIT row -> CommitFeatures, so a mined commit and a corpus row
    take the identical path through the scorer."""
    from ml_model.kamei_metrics import CommitFeatures

    return CommitFeatures(
        **row_values(row),
        rev=row.get("commit_id", "")[:12],
        subject=f"{row.get('project', '')} {row.get('commit_id', '')[:8]}",
    )


def load(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (X in KAMEI_FEATURES order, y, author_date) sorted by time."""
    rows = load_rows(path)
    X = np.array([[row_values(r)[name] for name in KAMEI_FEATURES] for r in rows],
                 dtype=np.float64)
    y = np.array([r["buggy"] == "True" for r in rows], dtype=int)
    when = np.array([int(float(r["author_date"])) for r in rows], dtype=np.int64)

    order = np.argsort(when)
    return X[order], y[order], when[order]


def time_split(X, y, when, train_frac: float = 0.8):
    """Chronological split. A random split leaks the future into training and
    inflates every metric - defect prediction is a forecasting problem."""
    cut = int(len(y) * train_frac)
    return (X[:cut], y[:cut]), (X[cut:], y[cut:]), when[cut]



