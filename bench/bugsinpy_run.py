"""Reproduce a BugsInPy bug by running it, and record what the fix changed.

This is ORACLE's own per-file execution mechanism pointed at somebody else's
corpus. The loop is the one `oracle_reviewer/core.py` already runs -- check out
the parent, run, check out ONE file from the child, run again, and attribute the
difference to that file -- except that here the command is not guessed. BugsInPy
names the triggering test, so `suggest_run` has nothing to do and the "baseline
already failing" case, which is a defeat on a real repository, is the entire
point: the test is SUPPOSED to fail before the fix.

Per bug, in one container, one environment, two runs:

  1. worktree at `buggy_commit`
  2. `git checkout <fixed> -- <test_file>`   the triggering test is usually ADDED
     by the fix commit, so at the buggy commit it does not exist yet. BugsInPy's
     own checkout script does the same thing; without it every bug reports
     "no such file" and nothing is measured.
  3. install, run the test               -> BEFORE   (expected: fails)
  4. `git checkout <fixed> -- <src>`     the fix, and only the fix
  5. run the test again                  -> AFTER    (expected: passes)

A bug counts as REPRODUCED only if the test fails at (3) and passes at (5). That
is a real differential oracle: not our label, not our mutation, and checkable by
anyone with the same two commits.

Environments are containers, one image per Python minor version, because the
pinned requirements are from 2020 and the host runs 3.14. Nothing is installed
on the host.

    python bench/bugsinpy_run.py --ids tqdm-1,tqdm-2
    python bench/bugsinpy_run.py --projects tqdm,PySnooper,cookiecutter
    python bench/bugsinpy_run.py --projects thefuck --jobs 4 --keep-going

Results append to data/bugsinpy_exec.jsonl, one row per bug, and a bug already
present is skipped unless --redo, so a long sweep can be interrupted.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import pathlib
import shlex
import shutil
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOME = ROOT / "data" / "bugsinpy"
REPOS = HOME / "repos"
WORK = HOME / "work"
MANIFEST = ROOT / "data" / "bugsinpy_manifest.jsonl"
OUT = ROOT / "data" / "bugsinpy_exec.jsonl"

CLONE_TIMEOUT = 1800
BUILD_TIMEOUT = 1800
CAP = 20000          # bytes of captured output kept per run


def sh(cmd: list[str], cwd: pathlib.Path | None = None, timeout: int = 300):
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True,
                          capture_output=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)


_CLONE_LOCKS: dict[str, "threading.Lock"] = {}
_LOCKS_GUARD = threading.Lock()


def ensure_clone(project: str, url: str) -> pathlib.Path:
    """A full clone -- the gate needs the history to compute its metrics.

    One lock per project: with --jobs 6 the first six bugs of a project all
    start at once, and six concurrent clones of the same repository is both
    slow and a race over the same destination.
    """
    with _LOCKS_GUARD:
        lock = _CLONE_LOCKS.setdefault(project, threading.Lock())
    with lock:
        return _clone(project, url)


def _clone(project: str, url: str) -> pathlib.Path:
    dst = REPOS / project
    if (dst / ".git").exists() or (dst / "HEAD").exists():
        return dst
    REPOS.mkdir(parents=True, exist_ok=True)
    tmp = REPOS / f".{project}.partial"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    r = sh(["git", "clone", "--quiet", url, str(tmp)], timeout=CLONE_TIMEOUT)
    if r.returncode != 0:
        raise RuntimeError(f"clone failed: {(r.stderr or '').strip()[:300]}")
    tmp.rename(dst)
    return dst


# What the fix commit changed that is part of the test harness rather than the
# program: test modules, conftest, and the data files that sit beside them. The
# source side is deliberately excluded -- checking any of it out early would
# apply part of the fix before the "before" measurement, and the bug would
# quietly report as already passing.
def test_side(repo: pathlib.Path, fixed: str, patch_files: list[str]) -> list[str]:
    r = sh(["git", "show", "--name-only", "--format=", fixed], cwd=repo, timeout=120)
    out = []
    for line in (r.stdout or "").split("\n"):
        f = line.strip()
        if not f or f in patch_files:
            continue
        low = f.lower()
        parts = low.split("/")
        if any(p in ("test", "tests", "testing") for p in parts[:-1]) \
                or parts[-1].startswith(("test_", "conftest")) \
                or parts[-1].endswith(("_test.py", "_tests.py")):
            out.append(f)
    return out


def image_for(pyver: str) -> str:
    minor = ".".join(pyver.split(".")[:2]) if pyver else "3.8"
    if minor not in {"3.6", "3.7", "3.8"}:
        minor = "3.8"
    return f"python:{minor}"


# These freeze files were taken on the authors' own machines and carry three
# kinds of line that cannot install here:
#   * `pkg-resources==0.0.0`, a Debian packaging artifact with no PyPI release,
#     which fails the whole resolve on its own
#   * `pywin32==227` and friends, which have no Linux distribution at all
#   * `-e git+https://.../pandas@<sha>#egg=pandas`, an editable VCS pin of the
#     project itself -- it would clone the project a second time, over the
#     network, at a commit that is not the one under test
# The project is installed from the checkout, so its own pin goes too.
_PLATFORM_ONLY = {"pywin32", "pypiwin32", "pywinpty", "wmi", "win32-setctime",
                  "appscript", "pyobjc", "pyobjc-core"}


def clean_requirements(text: str, project: str) -> str:
    drop = {"pkg-resources", "pkg_resources", project.lower()} | _PLATFORM_ONLY
    keep = []
    for line in text.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("-r ") or s.startswith("-e "):
            continue
        if "git+" in s or s.startswith("--"):
            continue
        name = s.split("==")[0].split(">")[0].split("<")[0].split("[")[0].strip().lower()
        if name.replace("_", "-") in drop:
            continue
        keep.append(s)
    return "\n".join(keep) + "\n"


# run_test.sh is whatever the bug's author typed. Two forms cannot work in a
# single-interpreter container: `tox`, which wants every interpreter in the
# project's envlist and reports InterpreterNotFound for the four it lacks, and
# the `py.test` console script, which the pinned pytest does not always install.
# Both mean the same thing as `python -m pytest`, so say that instead.
def rewrite_run(cmd: str) -> str:
    c = cmd.strip()
    for head in ("tox ", "py.test ", "pytest "):
        if c.startswith(head):
            return "python -m pytest " + c[len(head):]
    if c in ("tox", "py.test", "pytest"):
        return "python -m pytest"
    return c


def script(row: dict, files: list[str]) -> str:
    """The whole reproduction, as one shell script run inside the container."""
    fixed = row["fixed_commit"]
    tests = [t for t in row["test_file"].split(";") if t.strip()]
    # bug.info names the test MODULE, but a fix commit often adds the fixtures
    # that module reads as well -- cookiecutter-1 needs a non-ASCII JSON file
    # that lives beside the test. Checking out only the module leaves the
    # fixture at the buggy revision, and the test then fails on both sides for
    # a reason that has nothing to do with the bug. Take everything the fix
    # touched on the test side; leave everything on the source side alone.
    tests = sorted(set(tests) | set(row.get("test_side") or []))
    runs = [rewrite_run(c) for c in (row["run_test"] or
                                     ["python -m pytest " + " ".join(tests)])]
    pypath = row.get("pythonpath") or ""

    # A `pythonpath` of e.g. "tqdm/build/lib/" means the tests import the BUILT
    # package, not the source tree -- so the fix does not take effect until the
    # build is re-run. Skipping this rebuild makes before and after identical and
    # the bug silently unreproducible.
    # A compiled project must be rebuilt after the fix lands, for the same
    # reason the `pythonpath` case must: otherwise the .so on disk is still the
    # buggy one and before and after are identical by construction.
    build = ""
    if row.get("needs_ext"):
        build = "python setup.py -q build_ext --inplace >>/out/build.log 2>&1 || true"
    if pypath:
        build = "python setup.py -q build >/dev/null 2>&1 || true"
        pp = ":".join(f"$PWD/{p.strip()}" for p in pypath.split(";") if p.strip())
        export_pp = f'export PYTHONPATH="{pp}:$PWD:${{PYTHONPATH:-}}"'
    else:
        export_pp = 'export PYTHONPATH="$PWD:${PYTHONPATH:-}"'

    # A freeze only pins what the authors had INSTALLED. Anything that arrives
    # later as a transitive dependency is resolved fresh, at today's version,
    # and a few of those broke compatibility after these environments were
    # captured in 2020. `markupsafe` 2.1 deleted `soft_unicode`, which Jinja2 <3
    # imports on the way up -- and that alone was 14 of keras's 21 failures,
    # surfacing as `ImportError: cannot import name 'soft_unicode'`. Cap only
    # what the corpus does not pin: if the authors named a version, theirs wins.
    caps = []
    pinned = {l.split("==")[0].strip().lower().replace("_", "-")
              for l in clean_requirements(row["requirements"],
                                          row["project"]).split("\n") if l.strip()}
    for name, cap in (("markupsafe", "markupsafe<2.1"),
                      ("itsdangerous", "itsdangerous<2"),
                      ("werkzeug", "werkzeug<2"),
                      ("jinja2", "jinja2<3")):
        if name not in pinned:
            caps.append(cap)
    caps_line = ("pip install -q --disable-pip-version-check "
                 + " ".join(f'"{c}"' for c in caps)
                 + " >>/out/pip.log 2>&1 || true") if caps else ""

    runlines = "\n".join(runs)
    project = row["project"]
    project_lc = project.lower()
    co_tests = " ".join(shlex.quote(t) for t in tests)
    co_src = " ".join(shlex.quote(f) for f in files)

    return f"""set -u
git config --global --add safe.directory '*'
cd {shlex.quote(str(WORK / row['id']))}

python -m venv /venv 2>/dev/null || python -m venv --without-pip /venv
export PATH=/venv/bin:$PATH

# NOT `--upgrade setuptools`. Current setuptools vendors a typeguard that
# registers a pytest plugin using an ini type the pinned pytest rejects, and
# every test run in the environment dies on `assert type in (None, "pathlist",
# ...)` before collection. That one line was two whole projects, pandas and
# luigi, reported as unreproducible. These requirements are from 2020; give them
# a 2020 toolchain.
pip install -q --disable-pip-version-check "pip<22" "setuptools<60" "wheel<0.38" \
  >/out/pip.log 2>&1 || true

# Resolve the pins together first; fall back to one-at-a-time so that a single
# dead pin costs one package instead of the whole environment. Whatever still
# fails is written down -- a missing dependency surfaces later as a bare
# ModuleNotFoundError with no hint of where it came from.
: > /out/pip_failed.txt
if [ -s /bugsinpy_reqs.txt ]; then
  if ! pip install -q --disable-pip-version-check --pre -r /bugsinpy_reqs.txt >>/out/pip.log 2>&1; then
    echo "BATCH-RESOLVE-FAILED, falling back to one at a time" >>/out/pip.log
    while read -r p; do
      [ -z "$p" ] && continue
      pip install -q --disable-pip-version-check --pre "$p" >>/out/pip.log 2>&1 \
        || echo "$p" >> /out/pip_failed.txt
    done < /bugsinpy_reqs.txt
  fi
fi
# pytest, but ONLY if the pinned requirements did not already bring one. This
# line used to install unconditionally, which quietly upgraded thefuck's pinned
# pytest past 4.0, where `request.node.get_marker` was removed -- so its own
# conftest raised AttributeError and 18 of its 32 bugs looked unreproducible.
# The pin is the environment the bug was recorded in; do not overrule it.
python -c "import pytest" >/dev/null 2>&1 || \
  pip install -q --disable-pip-version-check pytest >>/out/pip.log 2>&1 || \
  pip install -q --disable-pip-version-check "pytest<6" >>/out/pip.log 2>&1 || true
# pytest-cov because several projects put `--cov` in the addopts of their
# setup.cfg and pytest aborts on the unrecognised argument before collecting.
# --no-deps so it cannot drag pytest forward either.
python -c "import pytest_cov" >/dev/null 2>&1 || \
  pip install -q --disable-pip-version-check --no-deps pytest-cov >>/out/pip.log 2>&1 || true

# Cython 3 rejects the `from numpy cimport int64_t` syntax that pandas 1.0 and
# spacy 2.x still use, so every C extension fails to compile and the package
# imports as a stub. Pinning it in the venv is not enough: pip's PEP 517 build
# isolation builds in a FRESH environment from the project's own
# pyproject.toml, which asks for Cython with no upper bound and gets 3.x. The
# isolation has to be turned off for the pin to be the compiler that runs.
NEEDS_EXT=no
if grep -qs -e cython -e Cython -e ext_modules setup.py 2>/dev/null; then
  NEEDS_EXT=yes
  pip install -q --disable-pip-version-check "Cython<3" >>/out/pip.log 2>&1 || true
fi

# pandas compiles with -Werror, and gcc 12 warns about casts in Cython's
# generated code that gcc 8 never mentioned. Every one of those warnings then
# ends the build. The code is not being changed here, so the warnings are not
# ours to fix -- they just must not be fatal.
export CFLAGS="${{CFLAGS:-}} -Wno-error -Wno-array-bounds -Wno-deprecated-declarations -Wno-stringop-overflow"

if [ -f setup.py ] || [ -f pyproject.toml ]; then
  if [ "$NEEDS_EXT" = yes ]; then
    pip install -q --disable-pip-version-check --no-build-isolation -e . >>/out/pip.log 2>&1 \
      || pip install -q --disable-pip-version-check -e . >>/out/pip.log 2>&1 \
      || echo "EDITABLE-INSTALL-FAILED" >>/out/pip.log
  else
    pip install -q --disable-pip-version-check -e . >>/out/pip.log 2>&1 \
      || pip install -q --disable-pip-version-check --no-build-isolation -e . >>/out/pip.log 2>&1 \
      || pip install -q --disable-pip-version-check --no-deps -e . >>/out/pip.log 2>&1 \
      || echo "EDITABLE-INSTALL-FAILED" >>/out/pip.log
  fi
fi
{export_pp}

# One of black's pinned requirements ships a top-level `tests` package, and it
# lands in site-packages next to the project's own `tests/` directory. Because
# the installed one has an __init__.py and the project's does not, Python's
# import scan takes the REGULAR package and never reaches the namespace portion
# -- no matter that $PWD comes first on the path. Every black bug then reported
# `ModuleNotFoundError: No module named 'tests.test_black'`, which reads like a
# missing file and is actually a stolen name.
SP=$(python -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || echo "")
if [ -n "$SP" ]; then
  for shadow in tests test; do
    if [ -e "$PWD/$shadow" ] && [ -e "$SP/$shadow" ]; then
      rm -rf "$SP/$shadow" "$SP/$shadow.py"
      echo "removed a site-packages '$shadow' shadowing the project's own" >>/out/pip.log
    fi
  done
fi
# THE PINS WIN. Everything after the requirements install -- `pip install -e .`,
# pytest, pytest-cov, a recovery install -- resolves its own dependencies and
# happily moves a pinned package forward. That is how keras ended up with
# markupsafe 2.1 and `cannot import name 'soft_unicode'`, and spacy with an
# attrs new enough to reject `attrib(convert=...)`: 18 bugs failing for a
# version nobody chose. Re-assert the pinned set last, so the environment the
# test runs in is the environment the bug was recorded in.
if [ -s /bugsinpy_reqs.txt ]; then
  pip install -q --disable-pip-version-check --pre -r /bugsinpy_reqs.txt \
    >>/out/pip.log 2>&1 || true
fi
{caps_line}
pip freeze > /out/freeze.txt 2>/dev/null

# BugsInPy's requirements.txt is a freeze of the authors' environment, and for
# some bugs it is missing a dependency the TEST needs but the package does not
# -- PySnooper's tests import `python_toolbox`, which appears nowhere. Rather
# than write those off, install what the failure names and try once more, up to
# three times, and record every package added this way so the environment stays
# auditable.
: > /out/extra_installs.txt
run_test_now () {{
  for attempt in 1 2 3 4; do
    ( {runlines} ) > "$1" 2>&1
    rc=$?
    miss=$(grep -oE "No module named '[^']+'" "$1" | head -1 \
           | sed "s/No module named '//; s/'$//" | cut -d. -f1)
    if [ -n "$miss" ] && [ "$attempt" -lt 4 ] \
       && [ "$miss" != "{project}" ] && [ "$miss" != "{project_lc}" ]; then
      if pip install -q --disable-pip-version-check "$miss" >>/out/pip.log 2>&1; then
        echo "$miss" >> /out/extra_installs.txt
        continue
      fi
    fi
    break
  done
  echo $rc > "$2"
}}

# --- BEFORE: the buggy commit, with the triggering test brought forward ---
git checkout -q {fixed} -- {co_tests} 2>/dev/null || echo "TEST-CHECKOUT-FAILED" >&2
{build}
run_test_now /out/before.txt /out/before.rc

# --- AFTER: the same tree, plus the fix, and nothing else ---
git checkout -q {fixed} -- {co_src} || echo "SRC-CHECKOUT-FAILED" >&2
git diff --stat HEAD -- {co_src} > /out/applied.txt 2>&1
{build}
run_test_now /out/after.txt /out/after.rc

# Some builds unpack vendored sources that carry their own uid -- matplotlib
# fetches and extracts freetype -- and those files land under a subuid the host
# user cannot delete, so the worktree cannot be removed and the checkout leaks.
# Hand everything back to the container root, which maps to the host user.
chown -R 0:0 . 2>/dev/null || true
chmod -R u+w . 2>/dev/null || true
"""


def read(p: pathlib.Path, cap: int = CAP) -> str:
    try:
        return p.read_text(errors="replace")[:cap]
    except Exception:
        return ""


def one(row: dict, timeout: int) -> dict:
    rid = row["id"]
    res = {"id": rid, "project": row["project"], "bug": row["bug"],
           "status": "error", "detail": ""}
    work = WORK / rid
    outdir = HOME / "out" / rid
    t0 = time.time()
    try:
        repo = ensure_clone(row["project"], row["github_url"])
        if work.exists():
            sh(["git", "worktree", "remove", "--force", str(work)], cwd=repo)
            shutil.rmtree(work, ignore_errors=True)
        work.parent.mkdir(parents=True, exist_ok=True)
        r = sh(["git", "worktree", "add", "--detach", "-f", str(work),
                row["buggy_commit"]], cwd=repo, timeout=600)
        if r.returncode != 0:
            res["detail"] = f"worktree: {(r.stderr or '').strip()[:200]}"
            res["status"] = "no-commit"
            return res

        if outdir.exists():
            shutil.rmtree(outdir, ignore_errors=True)
        outdir.mkdir(parents=True, exist_ok=True)
        reqs = outdir / "reqs.txt"
        reqs.write_text(clean_requirements(row["requirements"], row["project"]))

        files = row["patch_files"]
        row = dict(row, test_side=test_side(repo, row["fixed_commit"], files))
        setup_py = work / "setup.py"
        row = dict(row, needs_ext=setup_py.exists() and
                   any(k in setup_py.read_text(errors="replace")
                       for k in ("ext_modules", "cythonize", "Extension(")))
        body = script(row, files)
        (outdir / "run.sh").write_text(body)

        cmd = ["docker", "run", "--rm", "--network", "host",
               "-v", f"{HOME}:{HOME}",
               "-v", f"{outdir}:/out",
               "-v", f"{reqs}:/bugsinpy_reqs.txt:ro",
               "-w", str(work), image_for(row["python_version"]),
               "bash", "-lc", body]
        c = sh(cmd, timeout=timeout)
        res["container_rc"] = c.returncode
        res["container_err"] = (c.stderr or "")[-2000:]

        before, after = read(outdir / "before.txt"), read(outdir / "after.txt")
        brc = (read(outdir / "before.rc").strip() or "-1")
        arc = (read(outdir / "after.rc").strip() or "-1")
        res.update({
            "before": before, "after": after,
            "before_rc": int(brc) if brc.lstrip("-").isdigit() else -1,
            "after_rc": int(arc) if arc.lstrip("-").isdigit() else -1,
            "applied": read(outdir / "applied.txt", 2000),
            "pip_failed": [x for x in read(outdir / "pip_failed.txt", 4000).split("\n") if x.strip()],
            "extra_installs": [x for x in read(outdir / "extra_installs.txt", 2000).split("\n") if x.strip()],
            "pip_log_tail": read(outdir / "pip.log", 200000)[-1500:],
            "run_test": row["run_test"],
            "patch_files": files,
            "python_version": row["python_version"],
            "buggy_commit": row["buggy_commit"],
            "fixed_commit": row["fixed_commit"],
        })
        if res["before_rc"] == -1 or res["after_rc"] == -1:
            res["status"] = "no-run"
            res["detail"] = "the test command never produced an exit status"
        elif res["before_rc"] != 0 and res["after_rc"] == 0:
            res["status"] = "reproduced"
        elif res["before_rc"] == 0 and res["after_rc"] == 0:
            res["status"] = "passes-before"
            res["detail"] = "the triggering test already passes at the buggy commit"
        elif res["after_rc"] != 0:
            res["status"] = "fails-after"
            res["detail"] = "still failing with the fix applied -- environment, not the bug"
        else:
            res["status"] = "odd"
    except subprocess.TimeoutExpired:
        res["status"] = "timeout"
        res["detail"] = f"exceeded {timeout}s"
    except Exception as e:  # noqa: BLE001
        res["detail"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        res["seconds"] = round(time.time() - t0, 1)
        try:
            repo = REPOS / row["project"]
            if work.exists():
                sh(["git", "worktree", "remove", "--force", str(work)], cwd=repo)
                shutil.rmtree(work, ignore_errors=True)
            if work.exists():
                # last resort: re-enter the user namespace, where those subuid
                # files are ours again
                subprocess.run(["podman", "unshare", "rm", "-rf", str(work)],
                               capture_output=True, timeout=300,
                               stdin=subprocess.DEVNULL)
                sh(["git", "worktree", "prune"], cwd=repo)
                res["leaked_worktree"] = work.exists()
        except Exception:
            pass
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--projects", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--one-file-only", action="store_true",
                    help="only bugs whose patch touches a single file (410/501)")
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--retry-failed", action="store_true",
                    help="re-run bugs that neither reproduced nor passed before")
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    args = ap.parse_args()

    if not MANIFEST.exists():
        print("run: python bench/bugsinpy.py --manifest", file=sys.stderr)
        return 1
    rows = [json.loads(l) for l in open(MANIFEST)]
    if args.ids:
        want = {s.strip() for s in args.ids.split(",") if s.strip()}
        rows = [r for r in rows if r["id"] in want]
    if args.projects:
        want = {s.strip() for s in args.projects.split(",") if s.strip()}
        rows = [r for r in rows if r["project"] in want]
    if args.one_file_only:
        rows = [r for r in rows if r["n_files"] == 1]
    rows = [r for r in rows if r["fixed_commit"] and r["buggy_commit"]
            and r["github_url"] and r["run_test"]]

    # A bug that failed under an older version of this script is not "done".
    # Most failures so far were the harness and not the corpus -- a missing test
    # fixture, a requirements file read as the wrong encoding -- and each fix
    # makes a batch of them runnable again.
    done: set[str] = set()
    if args.out.exists() and not args.redo:
        settled = {"reproduced", "passes-before"} if args.retry_failed else None
        for line in open(args.out):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if settled is None or r.get("status") in settled:
                done.add(r["id"])
        rows = [r for r in rows if r["id"] not in done]
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        print(f"nothing to do ({len(done)} already in {args.out})")
        return 0

    print(f"{len(rows)} bugs, {args.jobs} job(s), {args.timeout}s cap each")
    fh = open(args.out, "a")
    tally: dict[str, int] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(one, r, args.timeout): r for r in rows}
        for i, f in enumerate(concurrent.futures.as_completed(futs), 1):
            res = f.result()
            tally[res["status"]] = tally.get(res["status"], 0) + 1
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"  [{i}/{len(rows)}] {res['id']:<22} {res['status']:<14}"
                  f" {res['seconds']:>6.0f}s  {res.get('detail', '')[:60]}")
    fh.close()
    print("\n" + "  ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
