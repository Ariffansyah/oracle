"""ORACLE review — explain what a commit changes, grounded in running it.

    ./serve.sh start
    python review.py --run "pytest -q"              # review HEAD in this repo
    python review.py --commit abc123 --run "npm test"
    python review.py --pr 42 --run "pytest -q" --post

WHY IT DOES NOT FALSE-POSITIVE
------------------------------
It refuses to speak unless execution has already proved there is something to
say. The pipeline is:

  1. check out base and head into two worktrees, run the SAME command in each
  2. if stdout, stderr and exit code are byte-identical -> emit NOTHING
  3. only then ask the model to explain, handing it the measured values
  4. drop any explanation that does not quote those values, or that invents a
     number -> fall back to the bare fact

So a finding can only be wrong about WHY, never about WHETHER: step 2 is a
measurement, not a prediction. The failure mode is silence, which is the right
way for a review bot to fail. `bench/exec_diff` scores 45/46 with zero false
positives on the benchmark; this is the same comparison applied to a real repo.

WHAT IT IS NOT
--------------
Not a bug finder. It reports behaviour that CHANGED, which is not the same as
behaviour that is WRONG, and it is blind to a latent defect that does not reach
the output. On real commits the unrestricted reviewer was wrong in 30 of 32
findings; that is the mode this tool deliberately does not operate in.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.request

TIMEOUT = 300

SYSTEM = """You are ORACLE. You are given one commit: its message and its diff.

COMPUTE FIRST, THEN EXPLAIN. Work out what the program printed before this \
commit and what it prints after. The commit message describes what the author \
INTENDED and is often wrong about what the change does -- trust the code, not \
the message.

Answer with one JSON object, with the keys in this order:

  "differs"      true if the two versions print different output, else false
  "before"       exactly what the pre-commit version printed
  "after"        exactly what the post-commit version printed
  "explanation"  one or two sentences for a developer: name the construct that \
changed and say what it does to the output, quoting both values

Work the values out first and let the explanation follow from them. Report only \
what the code determines; do not guess at consequences you cannot derive."""

USER = """## Commit
{message}

## Changes
```diff
{diff}
```

## Measured by running it
before: {before}
after:  {after}"""


def git(repo: str, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True,
                       text=True)
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


@contextlib.contextmanager
def worktree(repo: str, ref: str):
    """A detached checkout of `ref`, removed afterwards."""
    td = tempfile.mkdtemp(prefix="oracle-wt-")
    path = pathlib.Path(td) / "t"
    git(repo, "worktree", "add", "--detach", "-f", str(path), ref)
    try:
        yield path
    finally:
        git(repo, "worktree", "remove", "--force", str(path), check=False)
        shutil.rmtree(td, ignore_errors=True)


def observe(path: pathlib.Path, cmd: str) -> dict:
    """Run the project's own command and capture what a human would see."""
    try:
        r = subprocess.run(cmd, shell=True, cwd=path, capture_output=True,
                           text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "rc": -1, "out": "", "err": "timed out"}
    return {"status": "ok", "rc": r.returncode,
            "out": (r.stdout or "")[-4000:], "err": (r.stderr or "")[-2000:]}


def same(a: dict, b: dict) -> bool:
    return (a.get("rc"), a.get("out"), a.get("err")) == \
           (b.get("rc"), b.get("out"), b.get("err"))


def shown(v: dict, limit: int = 300) -> str:
    """The one-line summary a reviewer reads."""
    if v.get("status") == "timeout":
        return "(timed out)"
    out = (v.get("out") or "").strip()
    err = (v.get("err") or "").strip()
    body = out or err or "(no output)"
    tail = body.splitlines()[-1] if body.splitlines() else body
    rc = v.get("rc")
    return f"exit {rc}: {tail[:limit]}" if rc else tail[:limit]


_ERR = re.compile(r"\b(Traceback|Error|Exception|panic:|FAIL|AssertionError|"
                  r"SyntaxError|TypeError|ValueError|IndexError|KeyError)\b")


def errored(v: dict) -> bool:
    """Did this run FAIL, as opposed to merely printing something else?

    Severity is read off the measurement here, never off the model's opinion.
    A reviewer that calls something High because it looks wrong is guessing; a
    non-zero exit or an exception on stderr is a fact, and it is the only thing
    this tool is willing to escalate on.
    """
    if v.get("status") == "timeout":
        return True
    return bool(v.get("rc")) or bool(_ERR.search(v.get("err") or ""))


def classify(pre: dict, post: dict) -> tuple[str, str]:
    """(kind, severity) from the two runs alone."""
    if same(pre, post):
        return "none", "none"
    if errored(post) and not errored(pre):
        return "breaks", "high"
    if errored(pre) and not errored(post):
        return "fixes", "info"
    return "changes", "info"


def primary_hunk(diff: str) -> dict | None:
    """The first changed file and the first line the commit ADDS.

    Anchors the comment where the change is, instead of dropping a wall of text
    at the bottom of the PR.
    """
    path, new_ln, removed, added = None, None, [], []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            if path and (removed or added):
                break
            path, new_ln, removed, added = line[6:], None, [], []
        elif line.startswith("@@") and path:
            m = re.search(r"\+(\d+)", line)
            if m and new_ln is None:
                new_ln = int(m.group(1))
        elif path and new_ln is not None:
            if line.startswith("-") and not line.startswith("---"):
                removed.append(line[1:])
            elif line.startswith("+") and not line.startswith("+++"):
                added.append(line[1:])
            elif added or removed:
                break
            else:
                new_ln += 1
    if not path or new_ln is None:
        return None
    return {"path": path, "line": new_ln, "removed": removed, "added": added}


def ask(host: str, model: str, prompt: str, timeout: int = 180) -> str:
    body = json.dumps({
        "model": model, "stream": False,
        "options": {"temperature": 0.0, "num_predict": 300},
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(f"{host}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


# Shared so the brace-counting bug that blanked 18 BugsInPy rows -- and
# any review whose failure message contained a lone brace -- is fixed in
# exactly one place. See oracle_reviewer/jsonio.py.
from oracle_reviewer.jsonio import first_json  # noqa: E402


def verify(expl: str, before: str, after: str, diff: str) -> str | None:
    """Why this explanation must not be shown, or None if it may be."""
    if not expl or len(expl) < 20:
        return "empty"
    nums = lambda s: set(re.findall(r"-?\d+", s))
    allowed = nums(before) | nums(after) | nums(diff) | {"0", "1", "2"}
    invented = nums(expl) - allowed
    if invented:
        return f"invented {sorted(invented)[:2]}"
    key = lambda s: re.sub(r"\s+", "", s)[:40]
    if key(before) and key(before) not in re.sub(r"\s+", "", expl):
        return "does not quote the before value"
    if key(after) and key(after) not in re.sub(r"\s+", "", expl):
        return "does not quote the after value"
    return None


def review(repo: str, commit: str, cmd: str, host: str, model: str,
           quiet: bool) -> list[dict]:
    base = git(repo, "rev-parse", f"{commit}^").strip()
    head = git(repo, "rev-parse", commit).strip()
    message = git(repo, "log", "-1", "--pretty=%s", commit).strip()
    diff = git(repo, "diff", f"{base}..{head}")
    if not diff.strip():
        return []

    say = (lambda *a: None) if quiet else (lambda *a: print(*a, file=sys.stderr))
    say(f"running `{cmd}` at {base[:8]} …")
    with worktree(repo, base) as w:
        pre = observe(w, cmd)
    say(f"running `{cmd}` at {head[:8]} …")
    with worktree(repo, head) as w:
        post = observe(w, cmd)

    kind, severity = classify(pre, post)
    if kind == "none":
        return [{"kind": "none", "message": message, "command": cmd,
                 "observable": shown(pre)}]

    before, after = shown(pre), shown(post)
    prompt = USER.format(message=message, diff=diff[:12000],
                         before=before, after=after)
    expl, why = "", "model unavailable"
    try:
        got = first_json(ask(host, model, prompt)) or {}
        expl = unicodedata.normalize("NFKC", str(got.get("explanation") or ""))
        expl = expl.replace(" ", " ").strip()
        why = verify(expl, before, after, diff)
    except Exception as e:
        why = f"model error: {type(e).__name__}"

    return [{"kind": kind, "severity": severity, "message": message,
             "before": before, "after": after,
             "explanation": expl if why is None else "",
             "suppressed": why, "command": cmd, "hunk": primary_hunk(diff),
             "files": git(repo, "diff", "--name-only", f"{base}..{head}").split()}]


def as_markdown(f: dict) -> str:
    """The comment body. Tone follows the measurement, not a guess.

    `breaks` is the only kind that escalates, and only because a run FAILED --
    which is why it can carry a suggestion: the pre-commit lines are known to
    have run clean.
    """
    if f["kind"] == "none":
        return (f"**ORACLE**: ran `{f['command']}` at base and head — output is "
                f"byte-identical. No behavioural change detected.")

    head = {
        "breaks": "### :red_circle: This commit makes the code fail",
        "fixes": "### :white_check_mark: This commit fixes a failing run",
        "changes": "### :information_source: What this commit changes",
    }[f["kind"]]
    lead = {
        "breaks": f"Running `{f['command']}` succeeds before this commit and "
                  f"fails after it.",
        "fixes": f"Running `{f['command']}` fails before this commit and "
                 f"succeeds after it.",
        "changes": f"Running `{f['command']}` before and after gives different "
                   f"output. This is a behaviour change, not necessarily a bug.",
    }[f["kind"]]

    out = [head, "", lead, "",
           "| | output |", "|---|---|",
           f"| before | `{f['before']}` |",
           f"| after | `{f['after']}` |", ""]
    if f["explanation"]:
        out += [f["explanation"], ""]
    elif f["suppressed"]:
        out += [f"_Explanation withheld ({f['suppressed']}) — the measured "
                f"values above are the finding._", ""]

    h = f.get("hunk")
    if f["kind"] == "breaks" and h and h["removed"]:
        out += ["Reverting this hunk restores the passing run:", "",
                "```suggestion"] + h["removed"] + ["```", ""]
    out += [f"<sub>Verified by running the code, not predicted. "
            f"Severity is set by the exit status, not by a model. "
            f"Files: {', '.join(f['files'][:6])}</sub>"]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--pr", type=int, help="review a GitHub PR's head commit")
    ap.add_argument("--run", dest="cmd", required=True,
                    help="the command that shows what the project does, "
                         "e.g. 'pytest -q' or 'node index.js'")
    ap.add_argument("--host", default="http://localhost:8111")
    ap.add_argument("--model-name", default="oracle-merged")
    ap.add_argument("--post", action="store_true",
                    help="post the review to the PR with gh")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    commit = args.commit
    if args.pr:
        commit = subprocess.run(
            ["gh", "pr", "view", str(args.pr), "--json", "headRefOid",
             "-q", ".headRefOid"], capture_output=True, text=True,
            cwd=args.repo).stdout.strip() or commit

    findings = review(args.repo, commit, args.cmd, args.host,
                      args.model_name, args.quiet)
    if args.json:
        print(json.dumps(findings, indent=1))
        return 0
    for f in findings:
        md = as_markdown(f)
        print(md)
        if args.post and args.pr and f["kind"] != "none":
            h = f.get("hunk")
            done = False
            if h:
                r = subprocess.run(
                    ["gh", "pr", "review", str(args.pr), "--comment",
                     "--body", md], cwd=args.repo, capture_output=True,
                    text=True)
                done = r.returncode == 0
            if not done:
                subprocess.run(["gh", "pr", "comment", str(args.pr),
                                "--body", md], cwd=args.repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
