"""Score BugsInPy commits with the real gate, on real history.

This exists to remove the caveat that made the three-arm ablation unquotable.
That result -- `score` 39% against `diff` 39%, p=0.699 -- was measured on
synthetic rows, where the gate has no repository behind it and all 14 Kamei
metrics are zero-filled. It reached AUC 0.557 there, barely above chance, so
the honest reading was "a near-chance number tells the explainer nothing",
which is a much weaker claim than "a defect probability tells it nothing".

These are real commits in real repositories. `exp`, `rexp`, `sexp`, `ndev`,
`age` and `nuc` all compute, so the arm can finally be run as it was meant to be.

Two things are produced:

  --scores   a gate probability per reproduced bug, for the `score` arm
  --auc      how well that gate separates bug-INTRODUCING commits from ordinary
             ones in these same repositories

The second is the part that makes the first quotable. Bug-introducing commits
are found by B-SZZ (Sliwerski, Zimmermann & Zeller 2005): blame the lines the
fix DELETED, as they stood at the parent of the fix, and the commits that last
touched them are the candidates. No issue-report dates are available here, so
this is B-SZZ without the date filter -- it over-collects, and that is stated
rather than hidden. Negatives are commits sampled from the same repositories at
a fixed seed, excluding anything SZZ named.

    python bench/bugsinpy_gate.py --scores --auc
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
HOME = ROOT / "data" / "bugsinpy"
REPOS = HOME / "repos"

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def git(args: list[str], repo: pathlib.Path, timeout: int = 120) -> str:
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                       timeout=timeout, stdin=subprocess.DEVNULL)
    return r.stdout or ""


def deleted_lines(repo: pathlib.Path, buggy: str, fixed: str,
                  files: list[str]) -> dict[str, list[int]]:
    """Line numbers, in the buggy revision, that the fix removed."""
    out: dict[str, list[int]] = {}
    for f in files:
        diff = git(["diff", "-U0", buggy, fixed, "--", f], repo)
        cur = 0
        for line in diff.split("\n"):
            m = HUNK.match(line)
            if m:
                cur = int(m.group(1))
                continue
            if line.startswith("---") or line.startswith("+++"):
                continue
            if line.startswith("-"):
                out.setdefault(f, []).append(cur)
                cur += 1
            elif line.startswith(" "):
                cur += 1
    return out


def szz(repo: pathlib.Path, buggy: str, fixed: str,
        files: list[str]) -> list[str]:
    """B-SZZ candidates: what last touched the lines the fix deleted."""
    found: dict[str, int] = {}
    for f, lines in deleted_lines(repo, buggy, fixed, files).items():
        for n in lines[:40]:            # a 2000-line patch is not worth blaming
            try:
                blame = git(["blame", "-l", "--porcelain", f"-L{n},{n}",
                             buggy, "--", f], repo, timeout=60)
            except Exception:
                continue
            head = blame.split("\n", 1)[0].split(" ")[0]
            if re.fullmatch(r"[0-9a-f]{40}", head):
                found[head] = found.get(head, 0) + 1
    return [c for c, _ in sorted(found.items(), key=lambda kv: -kv[1])]


def sample_commits(repo: pathlib.Path, n: int, exclude: set[str],
                   seed: int) -> list[str]:
    log = git(["log", "--no-merges", "--format=%H", "-n", "4000"], repo)
    all_c = [c for c in log.split("\n") if len(c) == 40 and c not in exclude]
    rng = random.Random(seed)
    rng.shuffle(all_c)
    return all_c[:n]


def load_gate():
    from ml_model.gate import Gatekeeper
    path = ROOT / "artifacts" / "gate_noleak.joblib"
    if not path.exists():
        raise SystemExit(f"no leak-free gate at {path}")
    return Gatekeeper.load(path)


def features_for(repo: pathlib.Path, rev: str):
    import numpy as np
    from corpus.kamei_metrics import from_git
    f = from_git(rev, str(repo))
    return f.diff, np.array(f.vector(), dtype=np.float32)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=pathlib.Path,
                    default=ROOT / "data" / "bugsinpy_rows.jsonl")
    ap.add_argument("--scores", action="store_true")
    ap.add_argument("--auc", action="store_true")
    ap.add_argument("--neg-per-pos", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "data" / "bugsinpy_gate_scores.json")
    ap.add_argument("--auc-out", type=pathlib.Path,
                    default=ROOT / "data" / "bugsinpy_gate_auc.json")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.rows)]
    gate = load_gate()
    print(f"gate loaded: threshold {gate.threshold:.3f}, "
          f"{gate.n_metrics} metric slots, embeddings={gate.use_embeddings}")

    if args.scores:
        scores = {}
        for i, r in enumerate(rows, 1):
            repo = REPOS / r["project"]
            try:
                diff, met = features_for(repo, r["fixed_commit"])
                scores[r["id"]] = {
                    "score": gate.score(diff, met),
                    "metrics_nonzero": int((met != 0).sum()),
                }
            except Exception as e:  # noqa: BLE001
                scores[r["id"]] = {"score": None, "error": f"{type(e).__name__}: {e}"[:200]}
            if i % 25 == 0:
                print(f"  scored {i}/{len(rows)}")
        args.out.write_text(json.dumps(scores, indent=1))
        vals = [v["score"] for v in scores.values() if v.get("score") is not None]
        nz = [v["metrics_nonzero"] for v in scores.values() if "metrics_nonzero" in v]
        print(f"wrote {args.out}  n={len(vals)}  "
              f"mean {sum(vals)/max(len(vals),1):.3f}  "
              f"above threshold {sum(v >= gate.threshold for v in vals)}/{len(vals)}")
        print(f"  non-zero Kamei metrics per commit: "
              f"min {min(nz) if nz else 0}, median "
              f"{sorted(nz)[len(nz)//2] if nz else 0} of 14")

    if args.auc:
        import numpy as np
        from sklearn.metrics import roc_auc_score

        pos: list[tuple[str, str]] = []
        seen: set[str] = set()
        for r in rows:
            repo = REPOS / r["project"]
            if not repo.exists():
                continue
            try:
                cands = szz(repo, r["buggy_commit"], r["fixed_commit"],
                            r["patch_files"])
            except Exception:
                cands = []
            for c in cands[:1]:                       # the top candidate only
                if c not in seen:
                    seen.add(c)
                    pos.append((r["project"], c))
        print(f"SZZ named {len(pos)} distinct bug-introducing commits "
              f"from {len(rows)} bugs")

        by_proj: dict[str, int] = {}
        for p, _ in pos:
            by_proj[p] = by_proj.get(p, 0) + 1
        neg: list[tuple[str, str]] = []
        for p, k in by_proj.items():
            for c in sample_commits(REPOS / p, k * args.neg_per_pos, seen,
                                    args.seed):
                neg.append((p, c))
        print(f"sampled {len(neg)} negatives from the same repositories")

        y, s, kept = [], [], 0
        for label, group in ((1, pos), (0, neg)):
            for p, c in group:
                try:
                    diff, met = features_for(REPOS / p, c)
                    if not diff.strip():
                        continue
                    s.append(gate.score(diff, met))
                    y.append(label)
                    kept += 1
                except Exception:
                    continue
        y_a, s_a = np.array(y), np.array(s)
        auc = float(roc_auc_score(y_a, s_a)) if len(set(y)) > 1 else float("nan")
        above = float((s_a >= gate.threshold).mean())
        rec = float((s_a[y_a == 1] >= gate.threshold).mean()) if (y_a == 1).any() else float("nan")
        res = {"n_pos": int((y_a == 1).sum()), "n_neg": int((y_a == 0).sum()),
               "auc": auc, "threshold": gate.threshold,
               "frac_above_threshold": above, "recall_at_threshold": rec,
               "mean_pos": float(s_a[y_a == 1].mean()),
               "mean_neg": float(s_a[y_a == 0].mean())}
        args.auc_out.write_text(json.dumps(res, indent=1))
        print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
