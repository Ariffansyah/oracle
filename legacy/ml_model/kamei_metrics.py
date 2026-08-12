"""Extraction of the 14 Kamei et al. JIT process metrics from a commit.

Two sources are supported:

* ``from_git(rev, repo)``  - real metrics mined from a git repository.
* ``mock_commit(seed)``    - a synthetic commit so the pipeline runs
  out-of-the-box with no repository at hand.
"""

from __future__ import annotations

import math
import random
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field

from config import KAMEI_FEATURES

_FIX_WORDS = ("fix", "bug", "defect", "patch", "issue", "crash", "regression", "hotfix")


@dataclass
class CommitFeatures:
    """A commit reduced to the Kamei feature vector plus the raw diff."""

    ns: float = 0.0
    nd: float = 0.0
    nf: float = 0.0
    entropy: float = 0.0
    la: float = 0.0
    ld: float = 0.0
    lt: float = 0.0
    fix: float = 0.0
    ndev: float = 0.0
    age: float = 0.0
    nuc: float = 0.0
    exp: float = 0.0
    rexp: float = 0.0
    sexp: float = 0.0

    rev: str = "WORKING"
    subject: str = ""
    author: str = ""
    files: list[str] = field(default_factory=list)
    diff: str = ""

    def vector(self) -> list[float]:
        """Feature values ordered exactly as ``config.KAMEI_FEATURES``."""
        d = asdict(self)
        return [float(d[name]) for name in KAMEI_FEATURES]

    def as_dict(self) -> dict[str, float]:
        d = asdict(self)
        return {name: float(d[name]) for name in KAMEI_FEATURES}


_MISSING = object()


def _git(args: list[str], repo: str, default=_MISSING) -> str:
    """Run git; return stdout. With ``default`` set, failures return it instead
    of raising (root commits have no ``rev^``, new files have no old blob)."""
    proc = subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        if default is _MISSING:
            raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
        return default
    return proc.stdout


def _entropy(per_file_changes: list[int]) -> float:
    """Normalised Shannon entropy of the change spread over the touched files."""
    total = sum(per_file_changes)
    if total == 0 or len(per_file_changes) < 2:
        return 0.0
    h = -sum((c / total) * math.log2(c / total) for c in per_file_changes if c)
    return h / math.log2(len(per_file_changes))


def from_git(rev: str, repo: str = ".") -> CommitFeatures:
    """Mine the Kamei metrics for ``rev`` out of the git repo at ``repo``."""
    author, ts, subject = _git(
        ["show", "-s", "--format=%an%x00%at%x00%s", rev], repo
    ).strip().split("\x00")
    commit_ts = int(ts)

    files, la, ld, per_file = [], 0, 0, []
    for line in _git(["show", "--numstat", "--format=", rev], repo).splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        added = int(added) if added.isdigit() else 0     # "-" for binary files
        deleted = int(deleted) if deleted.isdigit() else 0
        files.append(path)
        la += added
        ld += deleted
        per_file.append(added + deleted)

    dirs = {p.rsplit("/", 1)[0] if "/" in p else "." for p in files}
    subsystems = {p.split("/", 1)[0] if "/" in p else "." for p in files}

    # History of the touched files *before* this commit.
    # ndev and nuc are per-file averages, not totals across the commit - that is
    # how ApacheJIT defines them (its ndev median is fractional), and the model
    # trained on it would misread totals.
    per_file_devs, per_file_nuc, last_touch = [], [], []
    lt = 0
    for path in files:
        log = _git(
            ["log", f"{rev}^", "--format=%an%x00%at", "--", path], repo, default=""
        ).splitlines()
        devs = {entry.split("\x00")[0] for entry in log}
        per_file_devs.append(len(devs))
        per_file_nuc.append(len(log))
        if log:
            last_touch.append(int(log[0].split("\x00")[1]))
        lt += len(_git(["show", f"{rev}^:{path}"], repo, default="").splitlines())

    age_days = (
        sum((commit_ts - t) for t in last_touch) / len(last_touch) / 86400
        if last_touch else 0.0
    )

    prior = _git(
        ["rev-list", "--count", f"--author={author}", f"{rev}^"], repo, default="0"
    ).strip()

    # REXP is Kamei's time-weighted experience, sum(1 / (age_in_years + 1)),
    # not a commit count inside a fixed window. ApacheJIT's `arexp` uses the
    # weighted form, so a count here would sit on a different scale entirely.
    rexp = 0.0
    for ts_line in _git(
        ["log", f"{rev}^", f"--author={author}", "--format=%at"], repo, default=""
    ).splitlines():
        years = (commit_ts - int(ts_line)) / (365.25 * 86400)
        rexp += 1.0 / (max(years, 0.0) + 1.0)
    sexp_out = _git(
        ["log", f"{rev}^", f"--author={author}", "--format=", "--name-only"],
        repo, default="",
    ).splitlines()
    sexp = sum(
        1 for p in sexp_out
        if p and (p.split("/", 1)[0] if "/" in p else ".") in subsystems
    )

    return CommitFeatures(
        ns=len(subsystems),
        nd=len(dirs),
        nf=len(files),
        entropy=_entropy(per_file),
        la=la,
        ld=ld,
        lt=lt / max(len(files), 1),
        fix=float(any(w in subject.lower() for w in _FIX_WORDS)),
        ndev=sum(per_file_devs) / max(len(per_file_devs), 1),
        age=age_days,
        nuc=sum(per_file_nuc) / max(len(per_file_nuc), 1),
        exp=float(prior or 0),
        rexp=rexp,
        sexp=float(sexp),
        rev=rev,
        subject=subject,
        author=author,
        files=files,
        diff=_git(["show", "--format=", "--unified=3", rev], repo),
    )


def diff_line_index(diff: str) -> dict[tuple[str, int], int]:
    """Map ``(file_path, line_in_new_file)`` to its 1-based line in the diff text.

    Lets a finding cited as ``payments/checkout.py:43`` be pointed at inside the
    rendered diff, which is the only thing the reviewer actually saw.
    """
    index: dict[tuple[str, int], int] = {}
    path, new_no = None, None
    for offset, line in enumerate(diff.splitlines(), 1):
        if line.startswith("+++ "):
            path = line[4:].strip()
            path = path[2:] if path.startswith(("a/", "b/")) else path
            new_no = None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            new_no = int(m.group(1)) if m else None
        elif new_no is None or path is None:
            continue
        elif line.startswith("-"):
            continue  # removed lines do not exist in the new file
        elif line.startswith(("+", " ")) or not line:
            index.setdefault((path, new_no), offset)
            new_no += 1
        else:
            new_no = None  # left the hunk (next `diff --git`, trailing text)
    return index


# Deliberately behaviour-preserving: renamed locals, docstrings, type hints and a
# module constant holding the value it replaced. High churn, zero semantic change
# - which is the whole point of the demo. Anything that alters an error path, a
# boundary or a default belongs in `evals.py` as a finding-expected case instead.
MOCK_DIFF = '''diff --git a/payments/checkout.py b/payments/checkout.py
index 8a1f2c3..b4d9e07 100644
--- a/payments/checkout.py
+++ b/payments/checkout.py
@@ -1,5 +1,9 @@
+"""Order checkout totals."""
+
 from decimal import Decimal

+PERCENT_SCALE = 100
+

 class Checkout:
@@ -41,10 +45,13 @@ class Checkout:
-    def apply_discount(self, order, rule):
-        pct = rule.percent
-        return order.total * (1 - pct / 100)
+    def apply_discount(self, order, rule):
+        """Return `order.total` with `rule` applied."""
+        percent = rule.percent
+        return order.total * (1 - percent / PERCENT_SCALE)

-    def line_items(self, order):
-        out = []
-        for i in order.items:
-            out.append(self.render(i))
-        return out
+    def line_items(self, order):
+        """Render each item on the order."""
+        rendered = []
+        for item in order.items:
+            rendered.append(self.render(item))
+        return rendered
diff --git a/payments/receipt.py b/payments/receipt.py
index 1c0aa21..77bd310 100644
--- a/payments/receipt.py
+++ b/payments/receipt.py
@@ -12,8 +12,11 @@ class Receipt:
-    def format(self, order):
-        ln = []
-        for x in order.items:
-            ln.append("%s x%s" % (x.name, x.qty))
-        return "\\n".join(ln)
+    def format(self, order):
+        """One line per item: name and quantity."""
+        lines = []
+        for item in order.items:
+            lines.append(f"{item.name} x{item.qty}")
+        return "\\n".join(lines)
'''


def mock_commit(seed: int | None = None, risky: bool = True) -> CommitFeatures:
    """A synthetic commit for demos and smoke tests."""
    # Ranges are picked so the ApacheJIT-trained model actually scores these
    # HIGH/LOW on every seed. Retune them if the training corpus changes -
    # `mock_commit(risky=True)` scoring below the threshold silently skips the
    # LLM half of the demo.
    rng = random.Random(seed)
    la = rng.randint(400, 1800) if risky else rng.randint(3, 25)
    return CommitFeatures(
        ns=rng.randint(2, 4) if risky else 1,
        nd=rng.randint(4, 12) if risky else 1,
        nf=rng.randint(10, 40) if risky else rng.randint(1, 2),
        entropy=round(rng.uniform(0.7, 1.0) if risky else rng.uniform(0.0, 0.2), 3),
        la=la,
        ld=int(la * rng.uniform(0.3, 0.8)),
        lt=rng.randint(200, 4000),
        fix=1.0 if risky else 0.0,
        ndev=round(rng.uniform(4, 12) if risky else rng.uniform(1, 2), 2),
        age=round(rng.uniform(1, 60) if risky else rng.uniform(100, 600), 1),
        nuc=round(rng.uniform(40, 300) if risky else rng.uniform(1, 8), 2),
        exp=rng.randint(2, 40) if risky else rng.randint(400, 2000),
        rexp=round(rng.uniform(1, 20), 2) if risky else round(rng.uniform(150, 600), 2),
        sexp=rng.randint(0, 12) if risky else rng.randint(200, 1500),
        rev=f"mock{int(time.time()) % 100000:05d}",
        subject="refactor: name locals consistently and document payment helpers",
        author="demo@oracle.local",
        files=["payments/checkout.py", "payments/receipt.py"],
        diff=MOCK_DIFF,
    )


if __name__ == "__main__":
    c = mock_commit(seed=7)
    assert len(c.vector()) == len(KAMEI_FEATURES), "feature vector length drifted"
    assert abs(_entropy([5, 5]) - 1.0) < 1e-9, "even spread must be entropy 1.0"
    assert _entropy([10, 0]) == 0.0, "single-file change must be entropy 0.0"
    assert _entropy([]) == 0.0

    idx = diff_line_index(MOCK_DIFF)
    lines = MOCK_DIFF.splitlines()
    # checkout.py hunk starts at new line 41; walk to the guard we added at 44.
    assert lines[idx[("payments/checkout.py", 5)] - 1] == "+PERCENT_SCALE = 100"
    assert lines[idx[("payments/checkout.py", 46)] - 1].endswith('"""Return `order.total` with `rule` applied."""')
    assert lines[idx[("payments/receipt.py", 16)] - 1] == '+            lines.append(f"{item.name} x{item.qty}")'
    assert ("payments/receipt.py", 13) in idx
    print(c.as_dict())
