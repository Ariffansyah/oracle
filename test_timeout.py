"""A command that does not finish is not a project that fails.

    python test_timeout.py

`pnpm run lint` on a real Next.js codebase exceeded the old 120s budget, and the
result was reported as "Baseline Already Failing" — wording that blames the
project for the tool running out of time. A timeout is now its own case, and the
one-sided timeout (fine before, hangs after) is a finding rather than a shrug.
"""

import subprocess
import tempfile
from pathlib import Path

from oracle_reviewer.core import FileReview, review_body, review_commit

def repo(first: str, second: str) -> str:
    R = Path(tempfile.mkdtemp()) / "r"
    R.mkdir()
    g = lambda *a: subprocess.run(["git", "-C", str(R), *a], capture_output=True)
    subprocess.run(["git", "init", "-q", str(R)], capture_output=True)
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (R / "m.py").write_text(first)
    g("add", "-A"); g("commit", "-qm", "init")
    (R / "m.py").write_text(second)
    g("add", "-A"); g("commit", "-qm", "change it")
    return str(R)

HANG = "import time\ntime.sleep(30)\nprint('done')\n"
FAST = "print('done')\n"

# Both sides hang: nothing failed, nothing finished.
r = review_commit(repo(HANG, HANG.replace("done", "DONE")), "HEAD",
                  "python m.py", "http://localhost:8111", "oracle-reviewer-3b",
                  timeout=2)[0]
assert r.risk == "unclear" and r.why_unclear == "timeout", (r.risk, r.why_unclear)
assert r.badge == "Command Timed Out"
body = review_body(r, "python m.py")
assert "did not finish within the time limit" in body
assert "ALREADY failing" not in body      # the wording this case exists to fix
assert "--timeout" in body                # and it says how to fix it

# Fine before, hangs after: that IS attributable, and it is what a hang looks
# like. It must not be filed under "nothing was established".
r = review_commit(repo(FAST, HANG), "HEAD", "python m.py",
                  "http://localhost:8111", "oracle-reviewer-3b", timeout=3)[0]
assert r.risk == "high", r.risk
assert r.why_unclear == ""
# This diff is a pure addition, so there are no removed lines to show -- and
# that is exactly why Apply is gated on the risk rather than on `suggestion`:
# `git checkout` restores the whole file either way.
assert r.suggestion == [], r.suggestion

# The badge for a timeout is distinct from the other two unclear cases.
b = lambda w: FileReview(path="x", risk="unclear", why_unclear=w).badge
assert b("timeout") == "Command Timed Out"
assert b("baseline") == "Baseline Already Failing"
assert b("not-exercised") == "No Observable Change — Worth Checking"

print("ok")
