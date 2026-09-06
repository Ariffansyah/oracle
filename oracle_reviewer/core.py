"""Per-file, execution-grounded review. No network, no GitHub, no cloud.

The rule the whole tool is built on: RISK IS MEASURED, NOT GUESSED.

For each file a commit touches, this checks out the base tree, applies ONLY that
one file from the commit, and runs the project's own command. That attributes an
outcome to a single file instead of to the commit as a whole, so "which file
broke it" is an observation rather than an opinion.

  base run errors -> that file's run is clean   ->  FIXES
  base run clean  -> that file's run errors     ->  HIGH RISK
  both clean, output differs                    ->  BEHAVIOUR CHANGE
  byte-identical                                ->  nothing is said

Only the prose is model-written, and it is discarded unless it quotes the values
that were actually measured. A finding can be wrong about WHY; it cannot be
wrong about WHETHER.
"""
from __future__ import annotations

import contextlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exec_contract import (contradiction, direction_reversed,  # noqa: E402
                           swapped, unmeasured_claim,
                           phantom_removal)
from .static_claims import (cosmetic_only, describe, risky_edits,
                            ui_text_change)

# `next lint` or `tsc` over a real codebase does not finish in two minutes, and
# the cost is paid once per file in the commit. Raised, and made configurable,
# because "the tool timed out" was being reported as "your project is broken".
TIMEOUT = 300

_ERR = re.compile(r"\b(Traceback|Error|Exception|panic:|FAILED|AssertionError|"
                  r"SyntaxError|TypeError|ValueError|IndexError|KeyError|"
                  r"ReferenceError|NullPointerException)\b")

SYSTEM = """You are ORACLE, a local code reviewer. You are given one file's change from a commit, and the MEASURED result of running the project before and after that change.

The measurements are correct. Do not question them and do not invent others.

NEVER FORCE A VERDICT. You may call something a bug ONLY when the measurement shows the code failed. If the measurement does not establish that, you must not imply it. "This was not exercised, so I cannot tell" is a correct and useful answer; a confident guess is not. Do not hedge into a bug either -- no "this might cause", no "could lead to", no "may break". Either it was measured or it was not.

Answer with one JSON object:

  "explanation"  what to tell the developer, in one or two sentences

Four cases. Stay inside the one you were given:

1. THE RUN FAILED after the change. Explain precisely why it now fails -- name the construct responsible and the error it produces -- then say what would restore it. The measurement often contains the compiler's or runtime's own diagnostic; when it does, that diagnostic IS the reason, so quote it and name the diff line that produced it. Describe the change as the diff shows it: a line prefixed `+` was ADDED, a line prefixed `-` was removed. Never say something was removed unless a `-` line shows it being removed.

2. THE RUN WAS FAILING BEFORE and STARTS PASSING after the change. The change repaired something, and `before` holds the diagnostic it repaired. Quote that diagnostic exactly and name the diff line that removes its cause. NEVER say the change has no effect, does not affect behaviour, or is cosmetic -- the measurement shows it turned a failing run into a passing one, so any such sentence contradicts it. Do not look for a new bug in the fixed code; you were not given a measurement that shows one.

3. THE RUN STILL SUCCEEDS and only the output changed. Do not speculate about bugs; the new behaviour may be exactly what was intended. State the change plainly, e.g. "the kill reward changed from 10 to 20". One sentence.

4. THE COMMAND DID NOT EXERCISE THIS CHANGE -- output identical, nothing observed either way. Do not say it is safe and do not say it is broken; neither was measured. Say plainly that this command does not cover the change, name the construct that was edited, and suggest what a human should check -- callers of the function, other code reading the value, a test that would reach it.

Quote the measured values exactly. Never mention a number that is not in the measurements or the diff."""

USER = """## File
{path}

## Commit message
{message}

## Change
```diff
{diff}
```

## Measured by running `{cmd}`
before this file's change: {before}
after this file's change:  {after}
outcome: {outcome}"""


@dataclass
class FileReview:
    path: str
    risk: str                      # high | change | fixes | none | unverified
    before: str = ""
    after: str = ""
    explanation: str = ""
    withheld: str = ""
    diff: str = ""
    suggestion: list[str] = field(default_factory=list)
    verified: bool = True
    why_unclear: str = ""          # "" | baseline | not-exercised | timeout
    static: list = field(default_factory=list)   # facts read from the diff

    @property
    def badge(self) -> str:
        if self.risk == "unreachable":
            return "Not Checked By This Command"
        if self.risk == "ui-text":
            return "UI Text Change"
        if self.risk == "provably-safe":
            # The ONLY badge in this list that promises anything. It is earned
            # by the diff, not by the run: comments or indentation only, so
            # there is nothing here the interpreter can reach. Every other
            # identical-output result stays "Worth Checking", because for those
            # the run genuinely settled nothing.
            return "No Code Changed"
        if self.risk == "unclear" and self.why_unclear == "timeout":
            return "Command Timed Out"
        if self.risk == "unclear":
            # "Not covered" was wrong for BOTH unclear cases. A dead baseline is
            # not a coverage fact at all, and identical output does not prove
            # the change went unrun -- see review_body.
            #
            # The subject of this badge is the COMMAND'S OUTPUT, never the code.
            # It read "No Observable Change — Worth Checking" until two separate
            # readers, given the same review of a commit that rewrote a payment
            # cron's logic, both took it as a verdict that the code was
            # unchanged in effect -- one of them while quoting the body text
            # that says the opposite three lines down. A badge is what gets read
            # in a list; if it can be mistaken for a clean bill of health it
            # will be, however careful the paragraph beneath it is.
            return {"baseline": "Baseline Already Failing"}.get(
                self.why_unclear, "Command Output Unchanged — Worth Checking")
        return {"high": "High Risk", "change": "Behavior Change",
                "fixes": "Fixes A Failure", "none": "Cosmetic Only",
                "unverified": "Unverified"}[self.risk]

    def to_dict(self) -> dict:
        return asdict(self)


def repo_path(raw: str) -> str:
    """Make what a person types into a path `git -C` accepts.

    There is no shell between the text box and git, so none of the expansions a
    terminal would do have happened. Every one of these is a normal way to write
    a path and every one of them fails against a bare subprocess call:

        ~/code/thing        tilde is not expanded
        $HOME/code/thing    variables are not expanded
        '/code/thing'       quotes survive a copy from a shell command
         /code/thing        a stray space survives a paste

    A trailing slash is already fine; it is normalised anyway so the same repo
    typed two ways is one string.
    """
    p = (raw or "").strip()
    if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'":
        p = p[1:-1].strip()
    p = os.path.expanduser(os.path.expandvars(p))
    return os.path.normpath(p) if p else "."


def git(repo: str, *args: str, check: bool = True) -> str:
    # stdin=DEVNULL, not inherited. A TUI has taken the terminal's descriptors
    # over, and spawning with them raises "bad value(s) in fds_to_keep" from a
    # worker thread. It also stops any command from blocking on a prompt.
    r = subprocess.run(["git", "-C", str(repo), *args], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


# Installed dependencies are gitignored, so a worktree has none of them. For an
# interpreted language that is fatal before the code is even reached: pnpm exits
# on `runDepsStatusCheck` because node_modules does not match the lockfile, and
# the review measures the package manager's complaint instead of the project.
#
# Linked rather than copied -- node_modules is routinely gigabytes, and copying
# it for every file in a commit would cost more than the review. The link means
# the dependency tree is the one CURRENTLY installed, not the one this commit
# specified; for a commit that changes dependencies the run is therefore not
# faithful, which is why `deps_linked` is reported rather than done silently.
_DEPS = ("node_modules", ".venv", "venv", "vendor", ".bundle", "Pods",
         ".yarn/cache", ".pnpm-store")


def link_deps(repo: str, path: pathlib.Path) -> list[str]:
    """Point the worktree at the source repo's installed dependencies."""
    linked = []
    src_root = pathlib.Path(repo_path(repo))
    for name in _DEPS:
        src, dst = src_root / name, path / name
        if not src.exists() or dst.exists():
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(src.resolve(), target_is_directory=src.is_dir())
            linked.append(name)
        except OSError:
            pass                      # a missing link is not worth failing over
    return linked


@contextlib.contextmanager
def worktree(repo: str, ref: str):
    td = tempfile.mkdtemp(prefix="oracle-wt-")
    path = pathlib.Path(td) / "t"
    git(repo, "worktree", "add", "--detach", "-f", str(path), ref)
    link_deps(repo, path)
    try:
        yield path
    finally:
        # `git worktree remove` deletes the symlinks themselves, not what they
        # point at, so the real node_modules is untouched.
        git(repo, "worktree", "remove", "--force", str(path), check=False)
        shutil.rmtree(td, ignore_errors=True)


# What differs between two runs of the SAME code. Comparing raw output makes
# every one of these look like a behaviour change:
#
#   the worktree path   each run gets a fresh mkdtemp, so any printed path
#                       differs by construction -- stack traces, lint output,
#                       anything naming a file
#   progress redraws    a spinner rewrites its line with \r; whichever frame
#                       the run ended on is captured
#   durations           "3 passed in 0.12s" is different every single run
#   timestamps          "verified 9s ago", ISO stamps, wall-clock times
#   colour              ANSI codes appear or not depending on TTY detection
_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?"
                  r"(?:Z|[+-]\d{2}:?\d{2})?")
_CLOCK = re.compile(r"\b\d{1,2}:\d{2}:\d{2}\b")
_AGO = re.compile(r"\b\d+(?:\.\d+)?\s*\S*\s*ago\b", re.I)
# Attached units only (0.12s, 450ms), or spelled out (9 seconds). A bare "m"
# is left alone -- too many real values end in it.
_DUR = re.compile(r"\b\d+(?:[.,]\d+)?(?:ms|s|h)\b"
                  r"|\b\d+(?:[.,]\d+)?\s+(?:ms|secs?|seconds?|minutes?|hours?)\b", re.I)


def scrub(text: str, root: str | pathlib.Path | None = None) -> str:
    """Strip what varies run to run, so a diff in output means a diff in code.

    Applied to BOTH sides before they are compared or shown, so what you read
    is what was actually compared.
    """
    if not text:
        return ""
    # A progress bar rewrites one line many times; keep the state it ended on.
    # Split on \n only -- str.splitlines() also breaks on \r, which would turn
    # every redraw frame into its own line instead of collapsing them. Strip a
    # CRLF terminator first, or the last field of the split is the empty tail.
    lines = [line.rstrip("\r").split("\r")[-1].rstrip()
             for line in text.split("\n")]
    t = _ANSI.sub("", "\n".join(lines))
    if root:
        t = t.replace(str(root), "<repo>")
    t = _ISO.sub("<time>", t)
    t = _CLOCK.sub("<time>", t)
    t = _AGO.sub("<ago>", t)
    t = _DUR.sub("<dur>", t)
    return t


def observe(path: pathlib.Path, cmd: str, timeout: int = TIMEOUT) -> dict:
    try:
        r = subprocess.run(cmd, shell=True, cwd=path, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"rc": -1, "out": "", "err": "timed out", "timeout": True}
    except Exception as e:
        return {"rc": -1, "out": "", "err": str(e)[:200], "timeout": False}
    return {"rc": r.returncode,
            "out": scrub(r.stdout, path)[-4000:],
            "err": scrub(r.stderr, path)[-2000:], "timeout": False}


def errored(v: dict) -> bool:
    return bool(v.get("timeout")) or bool(v.get("rc")) or \
        bool(_ERR.search(v.get("err") or ""))


def same(a: dict, b: dict) -> bool:
    return (a.get("rc"), a.get("out"), a.get("err")) == \
           (b.get("rc"), b.get("out"), b.get("err"))


def _body(v: dict) -> str:
    """The output that matters, with the failure reason not thrown away.

    This used to be `out or err`, so stderr was discarded whenever stdout had
    anything at all. `go test` puts the package summary on stdout and the
    COMPILER DIAGNOSTICS on stderr, so a build failure was shown as

        FAIL  example.com/api [build failed]

    while the two lines naming the actual errors -- an undefined method and a
    call with too many arguments -- were dropped before anyone, model or human,
    could read them. The reason was measured and then withheld by accident.
    """
    out = (v.get("out") or "").strip()
    err = (v.get("err") or "").strip()
    if v.get("rc") and err:
        return f"{err}\n{out}" if out else err
    return out or err


# A compiler or interpreter diagnostic: `path:line[:col]: message`. This is the
# line that says WHY, as against a runner's summary line that says only THAT.
_DIAG = re.compile(r"^\s*\.?/?[\w./\\-]+\.\w+:\d+(?::\d+)?:\s+\S")


def error_detail(v: dict) -> str | None:
    """The most informative line of a failing run, or None."""
    lines = [l for l in _body(v).splitlines() if l.strip()]
    for line in lines:
        if _DIAG.match(line):
            return line.strip()
    for line in lines:
        if _ERR.search(line):
            return line.strip()
    return None


def shown(v: dict, limit: int = 240) -> str:
    if v.get("timeout"):
        return "(timed out)"
    body = _body(v)
    if not body:
        return "(no output)"
    lines = body.splitlines()
    tail = lines[-1][:limit]
    # Say when this is only the LAST line. Showing "2" for a program that prints
    # 10, 9, 2 invited "the output remains 2" -- true of what was displayed,
    # false of what the program does.
    if len(lines) > 1:
        tail = f"{tail}   (last of {len(lines)} lines)"
    return f"exit {v['rc']}: {tail}" if v.get("rc") else tail


def shown_pair(a: dict, b: dict, limit: int = 240) -> tuple[str, str]:
    """Two display strings that actually contain the difference.

    `shown` takes the LAST line, which is right for a test runner ("3 passed
    in 0.1s") and wrong for a program that prints several values. Observed:
    `main.py` printing 10/9/2 before and 15/9/2 after was displayed as "2" on
    both sides -- the run differed, the badge said Behavior Change, and the two
    values handed to the model were identical, so it duly reported that nothing
    had changed. The evidence was truncated away before anyone could see it.

    When the runs differ, show the first line that differs. When they agree,
    the last line is still the useful summary.
    """
    if a.get("timeout") or b.get("timeout"):
        return shown(a, limit), shown(b, limit)
    # When one side failed and said why, that reason IS the difference. Showing
    # the first line that merely differs buries it under a summary line.
    da, db = error_detail(a), error_detail(b)
    if (da is None) != (db is None):
        one = lambda v, d: (f"exit {v['rc']}: {d[:limit]}" if v.get("rc")
                            else d[:limit]) if d else shown(v, limit)
        return one(a, da), one(b, db)
    la, lb = _body(a).splitlines(), _body(b).splitlines()
    if la == lb:
        return shown(a, limit), shown(b, limit)

    n = next((i for i in range(max(len(la), len(lb)))
              if (la[i] if i < len(la) else None)
              != (lb[i] if i < len(lb) else None)), 0)
    multi = max(len(la), len(lb)) > 1

    def one(lines: list[str], v: dict) -> str:
        text = lines[n] if n < len(lines) else "(output ends here)"
        text = text[:limit]
        if multi:
            text = f"line {n + 1}: {text}"
        return f"exit {v['rc']}: {text}" if v.get("rc") else text

    return one(la, a), one(lb, b)


_COMMENT = ("#", "//", "*", "/*", '"""', "'''", "--")


def substantive(diff: str) -> bool:
    """Does this diff change anything but comments and blank lines?

    The distinction matters because an identical run means two different
    things. If the edit was a comment, identical output really is the whole
    story. If the edit was LOGIC and the output still did not move, the
    command simply never exercised it -- and reporting that as "no behaviour
    change" would assert a safety result that was never measured.
    """
    for line in diff.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line[:1] in ("+", "-"):
            body = line[1:].strip()
            if body and not body.startswith(_COMMENT):
                return True
    return False


def changed_files(repo: str, base: str, head: str) -> list[str]:
    out = git(repo, "diff", "--name-only", f"{base}..{head}").split("\n")
    return [p for p in (x.strip() for x in out) if p]


def base_lines(diff: str) -> list[str]:
    """The lines this change REMOVED — i.e. what the file said before.

    Offered as the suggestion for a high-risk file, because those exact lines
    are known to have produced a clean run.
    """
    out, seen_hunk = [], False
    for line in diff.splitlines():
        if line.startswith("@@"):
            seen_hunk = True
        elif seen_hunk and line.startswith("-") and not line.startswith("---"):
            out.append(line[1:])
    return out


# ---------------------------------------------------------------- the model
def ask(host: str, model: str, prompt: str, timeout: int = 180) -> str:
    body = json.dumps({
        "model": model, "stream": False,
        "options": {"temperature": 0.0, "num_predict": 320},
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(f"{host}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


def first_json(text: str) -> dict | None:
    for m in re.finditer(r"\{", text):
        depth = 0
        for j in range(m.start(), len(text)):
            depth += (text[j] == "{") - (text[j] == "}")
            if depth == 0:
                try:
                    v = json.loads(text[m.start():j + 1])
                except Exception:
                    break
                return v if isinstance(v, dict) else None
    return None


def verify(expl: str, before: str, after: str, diff: str,
           measured: bool = True, case: str = "") -> str | None:
    """Why this prose must not be shown, or None if it may be.

    `measured` is False for the two cases where the run established nothing --
    identical output, or a baseline that was already failing. A verdict either
    way is unsupported there, so the bar is higher, not lower.
    """
    if not expl or len(expl.strip()) < 15:
        return "empty"
    nums = lambda s: set(re.findall(r"-?\d+", s))
    invented = nums(expl) - (nums(before) | nums(after) | nums(diff) |
                             {"0", "1", "2"})
    if invented:
        return f"invented {sorted(invented)[:2]}"
    if not measured:
        # A dead baseline is stricter than an unexercised one: there, both runs
        # failed for a reason that has nothing to do with this file, so a
        # sentence reporting what was observed is unsupported as well.
        why = unmeasured_claim(expl, baseline_broken=(case == "baseline"))
        if why:
            return why
    # A deletion the diff does not contain. Checkable whether or not anything
    # was measured, so it is not inside the `not measured` branch above.
    gone = phantom_removal(expl, diff)
    if gone:
        return gone
    # Quoting the right numbers is not the same as quoting them on the right
    # side. The checkpoint's measured failure is that it reports the post-state
    # where the pre-state belongs, and every number in such a sentence IS in the
    # measurements -- so the check above passes it. Direction has to be its own
    # test. See exec_contract.direction_reversed.
    return direction_reversed(expl, before, after)


# A period followed by space and a capital or a backtick. Not `h.Cache.Set` and
# not `0.12s`: those have no space after the dot, which is what separates a
# sentence boundary from code and decimals.
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\"\'])")


def sentences(text: str) -> list[str]:
    return [t.strip() for t in _SENT.split((text or "").strip()) if t.strip()]


def filter_prose(expl: str, before: str, after: str, diff: str,
                 measured: bool = True, case: str = "") -> tuple[str, list[str]]:
    """Keep the sentences that survive the checks; report what was dropped.

    The checks used to run on the whole explanation, so one false clause
    suppressed everything around it. Observed: a two-sentence answer whose first
    sentence invented a removal and whose second correctly named the compiler
    error was withheld entire, and the true half went with it. Per sentence, the
    invented half goes and the measured half stays.

    A kept sentence may open with "This", whose antecedent was dropped. That
    reads a little bare and is still true, which is the right trade against
    printing a false claim.
    """
    kept, dropped = [], []
    for one in sentences(expl):
        why = verify(one, before, after, diff, measured, case)
        (dropped if why else kept).append(why or one)
    return " ".join(kept), dropped


def explain(host: str, model: str, r: FileReview, message: str, cmd: str,
            outcome: str, measured: bool = True) -> None:
    """Fill in `explanation`, or record why it was withheld. Never raises."""
    prompt = USER.format(path=r.path, message=message, diff=r.diff[:9000],
                         cmd=cmd, before=r.before, after=r.after,
                         outcome=outcome)
    try:
        got = first_json(ask(host, model, prompt)) or {}
        expl = str(got.get("explanation") or "")
        expl = unicodedata.normalize("NFKC", expl).replace(" ", " ").strip()
    except Exception as e:
        r.withheld = f"model unavailable ({type(e).__name__})"
        return
    # The model was trained on the four-field exec contract, so it still emits
    # `differs`/`before`/`after` even though only `explanation` is asked for.
    # Those fields are free evidence about the sentence: if it assigned the
    # measured after-state to the before slot, the prose was written off the
    # same mistake and states the change backwards.
    if swapped(got, r.before, r.after) or contradiction(got):
        r.withheld = "the model reported the two runs the wrong way round"
        return
    kept, dropped = filter_prose(expl, r.before, r.after, r.diff, measured,
                                 r.why_unclear)
    r.explanation = kept
    if dropped:
        # Deduplicated: several sentences failing the same check is one fact
        # about the answer, not several.
        r.withheld = "; ".join(dict.fromkeys(dropped))


# Ordered most specific first. Each entry is (marker file, builder), where the
# builder returns a command or None when the marker turns out not to say enough.
def _npm(root: pathlib.Path) -> tuple[str, str] | None:
    """A JS/TS project names its own commands, so read them rather than guess."""
    try:
        pkg = json.loads((root / "package.json").read_text())
    except Exception:
        return None
    scripts = pkg.get("scripts") or {}
    runner = ("pnpm" if (root / "pnpm-lock.yaml").exists() else
              "yarn" if (root / "yarn.lock").exists() else "npm")
    # Prefer a command whose OUTPUT changes with behaviour. `dev` and `start`
    # are servers -- they never exit, so they can measure nothing.
    # typecheck before lint: it is usually much faster and it is about
    # behaviour, where a linter is about style.
    for name in ("test", "test:unit", "typecheck", "lint", "build"):
        if name in scripts:
            # npm, yarn and pnpm all take `<runner> test` for the test script;
            # anything else needs an explicit `run`.
            verb = "" if name == "test" else "run "
            return (f"{runner} {verb}{name}", f"package.json scripts.{name}")
    if (root / "tsconfig.json").exists():
        return ("npx tsc --noEmit", "tsconfig.json, no test script")
    return None


def _make(root: pathlib.Path) -> tuple[str, str] | None:
    try:
        body = (root / "Makefile").read_text()
    except Exception:
        return None
    for target in ("test", "check"):
        if re.search(rf"^{target}:", body, re.M):
            return (f"make {target}", f"Makefile target `{target}`")
    return None


def _python(root: pathlib.Path) -> tuple[str, str] | None:
    if (root / "tests").is_dir() or list(root.glob("test_*.py")):
        return ("pytest -q", "a tests directory")
    for entry in ("main.py", "app.py", "run.py", "manage.py"):
        if (root / entry).exists():
            return (f"python {entry}", entry)
    return None


_DETECT = [
    ("package.json", _npm),
    ("Makefile", _make),
    ("go.mod", lambda r: ("go test ./...", "go.mod")),
    ("Cargo.toml", lambda r: ("cargo test", "Cargo.toml")),
    ("pom.xml", lambda r: ("mvn -q test", "pom.xml")),
    ("build.gradle", lambda r: ("gradle test", "build.gradle")),
    ("Gemfile", lambda r: ("bundle exec rspec", "Gemfile")),
    ("composer.json", lambda r: ("composer test", "composer.json")),
    ("pyproject.toml", _python),
    ("setup.py", _python),
    ("main.py", _python),
]


def suggest_run(repo: str) -> tuple[str, str]:
    """A run command this project might actually have, and why it was picked.

    Nothing here is language-specific to the REVIEW -- the tool runs a command
    and compares output, so any language works. What is language-specific is
    knowing which command that is, and defaulting to `python main.py` made the
    tool look broken on every project that is not Python.

    Returns ("", "") when the repository says nothing useful; the caller should
    then ask rather than run something that cannot succeed.
    """
    root = pathlib.Path(repo_path(repo))
    for marker, build in _DETECT:
        if not (root / marker).exists():
            continue
        got = build(root)
        if got:
            return got
    for entry in ("main.py", "index.js", "main.go"):
        if (root / entry).exists():
            runner = {"main.py": "python", "index.js": "node", "main.go": "go run"}
            return (f"{runner[entry]} {entry}", entry)
    return ("", "")


# What each tool can even read. Only tools whose input set is narrow and well
# understood are listed: claiming a command cannot reach a file is a strong
# statement, and a wrong one would dismiss a real finding.
_READS = {
    "tsc": {".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"},
    "eslint": {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte"},
    "jest": {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".snap"},
    "vitest": {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"},
    "pytest": {".py", ".pyi", ".cfg", ".ini", ".toml"},
    "python": {".py", ".pyi"},
    "python3": {".py", ".pyi"},
    "mypy": {".py", ".pyi"},
    "ruff": {".py", ".pyi"},
    "go": {".go", ".mod", ".sum"},
    "cargo": {".rs", ".toml"},
    "stylelint": {".css", ".scss", ".less"},
}
# What WOULD check a file this command cannot read.
_CHECKS = {
    ".yml": "yamllint", ".yaml": "yamllint",
    ".json": "jq . <file>", ".css": "stylelint", ".scss": "stylelint",
    ".sh": "shellcheck", ".bash": "shellcheck",
    ".tf": "terraform validate", ".sql": "sqlfluff lint",
    "Dockerfile": "hadolint",
}


def unreachable(cmd: str, path: str) -> tuple[str, str] | None:
    """Why this command cannot exercise this file, and what would. Or None.

    "The output was identical, so either it never ran or it changed nothing" is
    true but weak when the command provably cannot READ the file. `tsc` is the
    TypeScript compiler; a workflow YAML is not something it declines to
    report on, it is something it never opens. Saying so is a fact about the
    toolchain, not a guess about behaviour.
    """
    ext = pathlib.PurePath(path).suffix.lower()
    name = pathlib.PurePath(path).name
    # A CI workflow is not run by ANY local command -- it runs on the forge.
    if path.startswith(".github/workflows/") and ext in (".yml", ".yaml"):
        return ("this is a GitHub Actions workflow: it is executed by GitHub "
                "when the workflow triggers, so no command run here exercises "
                "it at all",
                "actionlint, which checks workflow syntax and expressions")
    if not ext and name not in _CHECKS:
        return None
    # The name must be the WHOLE command word: `\b` after "tsc" also matches
    # inside "tsc-alias", which is a different tool with different inputs.
    tool = next((t for t in _READS
                 if re.search(rf"(?:^|[\s/]){re.escape(t)}(?=\s|$)", cmd)), None)
    if tool is None or ext in _READS[tool]:
        return None
    return (f"`{tool}` does not read `{ext}` files, so this command could not "
            f"have exercised this change whatever it does",
            _CHECKS.get(ext) or _CHECKS.get(name) or "")


# ------------------------------------------------------------------ stage 1
# The JIT gate answers a question this tool does not: how likely is this commit
# to be bug-inducing, from its shape alone, with nothing run. It is shown next
# to the measured verdicts rather than merged with them, because the two are not
# the same kind of statement -- one is a prediction over a population, the other
# is an observation about this run.
#
# Measured on the three commits in the pyalgo fixture:
#
#   introduces an off-by-one   0.136  MEDIUM
#   fixes that same off-by-one 0.091  MEDIUM
#   a pure refactor            0.137  MEDIUM
#
# It cannot separate introducing a defect from repairing one, which is what
# `la`-dominated AUC looks like from the inside. That is the gap Stage 2 exists
# to close, so the number travels with the caveat, never alone.
_GATE = None
_GATE_ERROR: str | None = None
_GATE_CLEAN = False


def preload_gate() -> str | None:
    """Load Stage 1 NOW, before a TUI takes the terminal over.

    torch's first model load starts `multiprocessing.resource_tracker`, which
    spawns a helper process and passes it the process's file descriptors. Once
    a full-screen app owns the terminal those descriptors are no longer valid
    and the spawn dies with "bad value(s) in fds_to_keep" -- so the gate could
    never load from inside the running UI, only from a plain script. Loading it
    up front makes the spawn happen while stdio is still ordinary, and every
    later call reuses the loaded model.

    Returns None on success, or why it could not be loaded.
    """
    global _GATE, _GATE_ERROR, _GATE_CLEAN
    if _GATE is not None:
        return None
    try:
        import numpy as np

        from corpus.kamei_metrics import KAMEI_FEATURES
        from ml_model.gate import Gatekeeper

        # NOT the default artifact. config's GATE_MODEL_PATH points at
        # artifacts/gate.joblib, which RESULTS.md (24 Aug) shows was trained on
        # its own evaluation set -- the leak was worth 0.495 F1 and 0.21 AUC.
        # A number from it is train-on-test and must not be shown to anyone.
        clean = pathlib.Path("artifacts/gate_noleak.joblib")
        _GATE = (Gatekeeper.load(clean) if clean.exists()
                 else Gatekeeper.load())
        _GATE_CLEAN = clean.exists()
        # `load` does NOT touch the encoder -- it is lazy, and loads on the
        # first encode. Scoring a throwaway diff here is what actually forces
        # torch to start, which is the whole point of preloading.
        _GATE.score("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
                    np.zeros(len(KAMEI_FEATURES), dtype=float))
    except Exception as e:
        _GATE_ERROR = f"{type(e).__name__}: {e}"[:160]
        return _GATE_ERROR
    return None


def gate_risk(repo: str, commit: str) -> dict | None:
    """Stage 1's probability for this commit, or None when it cannot be had.

    Loading the encoder costs seconds, so the gate is kept between calls. Every
    failure path returns None: a missing gate must degrade to "no prediction",
    never to a fabricated one.
    """
    global _GATE
    try:
        import numpy as np

        from corpus.kamei_metrics import KAMEI_FEATURES, from_git
        if _GATE is None:
            # Loading here would be inside the UI, which is exactly what fails.
            return {"error": _GATE_ERROR or "gate was not preloaded"}
        root = repo_path(repo)
        diff = git(root, "diff", f"{commit}^..{commit}")
        feats = from_git(commit, root).as_dict()
        m = np.array([feats[k] for k in KAMEI_FEATURES], dtype=float)
        d = _GATE.decide(diff, m)
    except Exception as e:
        # Never a bare None: "unavailable" with no reason is the silent failure
        # this tool exists to avoid.
        return {"error": f"{type(e).__name__}: {e}"[:160]}
    if d.score != d.score:                     # NaN: unscored
        return {"error": "the gate returned no score for this diff"}
    return {"score": d.score, "threshold": d.threshold, "band": d.band,
            "clean": _GATE_CLEAN,
            "should_review": d.should_review,
            "top": [k for k, _v in (d.top_metrics or [])[:3]]}


def gate_line(g: dict | None) -> str:
    """One line for a UI, with the caveat attached to the number."""
    if not g:
        return "Stage 1 (JIT): no prediction — gate unavailable"
    if g.get("error"):
        return f"Stage 1 (JIT): no prediction — {g['error']}"
    if not g.get("clean"):
        return (f"Stage 1 (JIT): {g['score']:.1%} — FROM A LEAKED GATE, trained "
                f"on its own evaluation set; not reportable")
    return (f"Stage 1 (JIT): {g['score']:.1%} {g['band']} "
            f"(flags at {g['threshold']:.1%}) — predicted for the WHOLE commit "
            f"from its shape; mostly commit size, and it does not distinguish "
            f"introducing a defect from fixing one")


def norm_out(v: str) -> str:
    return " ".join((v or "").split())


def review_body(r: FileReview, cmd: str) -> str:
    """The prose to show for one file — the SAME words in every front end.

    This lives here rather than in a UI because the wording is the safety
    result. The caveat on an unmeasured file is not decoration: it is the
    difference between "nothing was established" and a clean bill of health,
    and it must not depend on which client rendered it. It is also always
    present, never a fallback — as a fallback, a model sentence that got
    through would silently replace it.
    """
    if r.risk == "none":
        return (f"Only comments or formatting changed here, and running "
                f"`{cmd}` confirms the output is identical. Nothing to report."
                    + _from_diff(r))
    if r.risk == "unreachable":
        why, alt = r.static
        body = (f"`{cmd}` cannot check this file — {why}. That is why the "
                f"output was identical; it is not evidence about the change.")
        if alt:
            body += f" What would check it: {alt}."
        return body + _from_diff(r)
    if r.risk == "ui-text":
        # Every sentence here is settled by the diff. Nothing is claimed about
        # what ran -- the last paragraph says so explicitly, because the reader
        # must not take a static fact for a measured one.
        lines = []
        for tag, _attrs, before, after in r.static:
            lines.append(f"The displayed text was changed from `{before}` to "
                         f"`{after}`.")
        vals = [c.value for c in r.static if c.value]
        body = " ".join(lines)
        if vals and len(vals) == len(r.static):
            body += (f" The underlying value{'s' if len(vals) > 1 else ''} "
                     f"({', '.join(f'`{v}`' for v in vals)}) "
                     f"{'are' if len(vals) > 1 else 'is'} unchanged, so this "
                     f"affects only what the user sees, not what is submitted.")
        body += (f"\n\nThat is what the diff says. `{cmd}` produced identical "
                 f"output, but it does not exercise the UI, so no behaviour was "
                 f"observed either way — this is read from the change, not from "
                 f"a run.")
        return body
    if r.risk == "unclear":
        if r.why_unclear == "timeout":
            return (f"`{cmd}` did not finish within the time limit, at the "
                    f"parent commit as well as this one. Nothing failed and "
                    f"nothing was established — the run simply never got to an "
                    f"answer. Raise the limit with `--timeout`, or use a faster "
                    f"command: a type check usually beats a full lint or build."
                    + _from_diff(r))
        if r.why_unclear == "baseline":
            body = (f"`{cmd}` was ALREADY failing before this commit, so this "
                    f"file was never measured against a working baseline. "
                    f"Nothing was established about it either way — not that "
                    f"it is safe, not that it is broken. Fix the baseline, or "
                    f"point the run command at something that works, then "
                    f"review again.")
        else:
            # "logic" overstates it: substantive() only separates code from
            # comments, and a changed string literal is neither logic nor a
            # comment.
            body = (f"This file's code changed and `{cmd}` produced byte-for-"
                    f"byte identical output. Two things produce that, and this "
                    f"cannot tell them apart: the changed code never ran, or it "
                    f"ran and made no difference to what this command prints. "
                    f"Either way nothing is established beyond the inputs this "
                    f"command happens to use. It is NOT a clean bill of health. "
                    f"Worth checking what else calls into what changed.")
        # Show the measurement here too. It used to appear only for the
        # attributable verdicts, so an unclear file printed prose about the
        # output with no output beside it to check the prose against.
        if norm_out(r.before) == norm_out(r.after):
            body += f"\n\noutput, identical on both sides:  {r.before}"
        else:
            body += f"\n\nbefore:  {r.before}\nafter:   {r.after}"
        if r.explanation:
            note = (f"\n\n(Part of the explanation was withheld: {r.withheld}.)"
                    if r.withheld else "")
            return body + "\n\n" + r.explanation + note + _from_diff(r)
        if r.withheld:
            return (body + f"\n\n(A model explanation was withheld: "
                    f"{r.withheld}.)" + _from_diff(r))
        return body + _from_diff(r)
    if r.explanation:
        body = r.explanation
        if r.withheld:
            body += f"\n\n(Part of the explanation was withheld: {r.withheld}.)"
    else:
        body = (f"Explanation withheld ({r.withheld}). The measurement stands "
                f"on its own:")
    if r.risk in ("high", "change", "fixes"):
        body += f"\n\nbefore:  {r.before}\nafter:   {r.after}"
    return body + _from_diff(r)


def _from_diff(r: FileReview) -> str:
    """What the edit did, restated from the diff.

    Every verdict gets this, because it is available without a run and it is
    the part a reader would otherwise have to reconstruct themselves. It is
    labelled as coming from the diff so it is never mistaken for a measurement
    -- restating an edit is not a claim about what the edit caused.
    """
    facts = describe(r.diff)
    body = ("\n\nFrom the diff:\n" + "\n".join(f"  · {f}" for f in facts)
            if facts else "")
    # Hazards are worth printing whatever the run found, but they matter most
    # where it found nothing: on a real repo 11 of 12 commits produced
    # byte-identical output, and this is the only thing left that can speak.
    # Measured on 457 real BugsInPy defects, these patterns fire on 16% of the
    # bug-INTRODUCING direction against 4% of the fix direction -- so they are
    # a signal, not a coin flip, and they are labelled as read-from-the-diff so
    # they are never mistaken for something that was observed.
    hazards = risky_edits(r.diff)
    if hazards:
        body += ("\n\nWorth checking, from the diff alone:\n"
                 + "\n".join(f"  ! {h}" for h in hazards))
    return body


# ---------------------------------------------------------------- the review
def review_commit(repo: str, commit: str, cmd: str, host: str, model: str,
                  progress=None, timeout: int = TIMEOUT) -> list[FileReview]:
    """One FileReview per changed file, each grounded in its own run."""
    repo = repo_path(repo)
    say = progress or (lambda *_: None)
    base = git(repo, "rev-parse", f"{commit}^").strip()
    head = git(repo, "rev-parse", commit).strip()
    message = git(repo, "log", "-1", "--pretty=%s", commit).strip()
    files = changed_files(repo, base, head)
    if not files:
        return []

    say(f"running `{cmd}` at base ({base[:8]}) …")
    with worktree(repo, base) as w:
        baseline = observe(w, cmd, timeout)

    out: list[FileReview] = []
    for i, path in enumerate(files, 1):
        say(f"[{i}/{len(files)}] isolating {path} …")
        diff = git(repo, "diff", f"{base}..{head}", "--", path)
        r = FileReview(path=path, risk="none", diff=diff)
        if not diff.strip():
            continue
        # base tree + ONLY this file from head: the outcome is attributable
        with worktree(repo, base) as w:
            got = subprocess.run(["git", "-C", str(w), "checkout", head, "--",
                                  path], capture_output=True, text=True)
            if got.returncode != 0:          # deleted file, or unmergeable
                subprocess.run(["git", "-C", str(w), "rm", "-q", "-f", "--",
                                path], capture_output=True, text=True)
            res = observe(w, cmd, timeout)

        r.before, r.after = shown_pair(baseline, res)

        # ORDER MATTERS. Each guard below removes a case the later ones cannot
        # judge honestly; running them the other way round reports findings that
        # were never measured.

        # 1. Comments and whitespace only. This must come FIRST: appending a
        #    comment shifts line numbers in a traceback, so stderr changes and a
        #    naive output comparison calls a comment a behaviour change.
        if not substantive(diff):
            r.risk = "none"
            out.append(r)
            continue

        # 2. The command cannot READ this file. True whether or not the run
        #    worked, so it comes before every measured case: a difference in
        #    output could not have come from this file, and an identical output
        #    is not evidence about it either.
        miss = unreachable(cmd, path)
        if miss:
            r.risk, r.static = "unreachable", list(miss)
            say(f"[{i}/{len(files)}] {path}: `{cmd}` cannot read it ...")
            out.append(r)
            continue

        # 3a. Neither run finished. A timeout is not a failure of the project
        #     and must not be worded as one -- nothing ran to an answer.
        if baseline.get("timeout"):
            r.risk, r.why_unclear = "unclear", "timeout"
            say(f"[{i}/{len(files)}] {path}: `{cmd}` timed out ...")
            out.append(r)
            continue

        # 3b. Only the run AFTER the change failed to finish, against a baseline
        #     that did. That is attributable, and it is the shape a hang has.
        if res.get("timeout"):
            r.risk = "high"
            r.suggestion = base_lines(diff)
            say(f"[{i}/{len(files)}] {path}: did not finish after this change ...")
            explain(host, model, r, message, cmd,
                    f"the run finished at the parent commit but did NOT finish "
                    f"within {timeout}s after this file's change")
            out.append(r)
            continue

        # 4. The project ALREADY fails at the parent commit. Nothing this file
        #    does can be attributed against a broken baseline -- unless it fixes
        #    it, which is case 3.
        if errored(baseline) and errored(res):
            r.risk, r.why_unclear = "unclear", "baseline"
            say(f"[{i}/{len(files)}] {path}: baseline already failing ...")
            explain(host, model, r, message, cmd,
                    "the project ALREADY FAILED before this change, so this "
                    "file could not be evaluated against a working baseline; "
                    "nothing about it was established either way",
                    measured=False)
            out.append(r)
            continue

        # 5. Same output. This is absence of evidence, not evidence of safety
        #    -- and note it does NOT establish that the change went unrun. A
        #    behaviour-preserving refactor that executes on every call produces
        #    exactly this too. Telling the two apart needs coverage, which is
        #    per-language; until there is some, neither may be claimed.
        if same(baseline, res):
            # Nothing was observed -- but the diff may still settle something on
            # its own. A relabelled element with an untouched `value` is the
            # clearest case: what the user reads changed, what the form submits
            # did not, and neither claim needs a run.
            text = ui_text_change(diff)
            if text:
                r.risk, r.static = "ui-text", text
                say(f"[{i}/{len(files)}] {path}: display text only ...")
                out.append(r)
                continue
            # Identical output plus a diff that cannot reach the interpreter
            # is the one case where "nothing changed" is provable rather than
            # merely unrefuted. Saying so is not the false all-clear the guard
            # strips; withholding it is just an unhelpful shrug.
            proof = cosmetic_only(diff)
            if proof:
                r.risk, r.static = "provably-safe", [proof]
                say(f"[{i}/{len(files)}] {path}: comments/indentation only ...")
                out.append(r)
                continue
            r.risk, r.why_unclear = "unclear", "not-exercised"
            say(f"[{i}/{len(files)}] {path}: not covered by `{cmd}` ...")
            explain(host, model, r, message, cmd,
                    "the output is byte-for-byte IDENTICAL. That means either "
                    "the changed code never ran, or it ran and changed nothing "
                    "this command prints -- which of the two is NOT known. "
                    "Nothing was established either way",
                    measured=False)
            out.append(r)
            continue

        # 6. Now the outcome is attributable.
        if errored(res) and not errored(baseline):
            r.risk, outcome = "high", "the run FAILED after this file's change"
            r.suggestion = base_lines(diff)
        elif errored(baseline) and not errored(res):
            r.risk, outcome = "fixes", "the run started PASSING after this change"
        else:
            r.risk, outcome = "change", "the run still succeeds, output differs"
        say(f"[{i}/{len(files)}] {path}: {r.badge} — explaining …")
        explain(host, model, r, message, cmd, outcome)
        out.append(r)
    return out
