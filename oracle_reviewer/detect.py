"""What a repository IS, and which commands could actually establish a baseline.

`core.suggest_run` answers "what does this project call its own test command".
That is the right question for a headless run and the wrong one for a launcher:
it returns ONE command, chosen without ever trying it. On a real Next.js repo it
returned `pnpm run lint`, which cannot even start inside a worktree -- pnpm
verifies the dependency tree before running a script, a linked `node_modules`
never satisfies that check, and the review then measured the package manager's
complaint identically on both sides and correctly refused to say anything.

Three failures were measured on that one repository, and all three are addressed
here rather than left for the user to work around by hand:

  1. `pnpm run <script>` dies in `runDepsStatusCheck` before reaching the code.
     Fixed by resolving a script to the BINARY it actually invokes, so the
     package manager is never in the loop: `./node_modules/.bin/eslint`.
  2. The project-wide command exits non-zero on pre-existing errors unrelated to
     the commit, so no baseline is possible. Fixed by `accepts_files`: a command
     that takes paths can be scoped to the files a commit touched, and scoping
     eslint to one changed file turned exit 1 into a clean exit 0.
  3. A build can be impossible whatever you do -- Turbopack rejects a
     `node_modules` symlink that points out of the project root. Nothing here
     can fix that, so a build is ordered LAST and never chosen when something
     cheaper is available.

Nothing in this module runs anything. It proposes an ordered ladder and says
why; deciding which candidate actually holds is the caller's job, and needs the
base commit to try them against.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

__all__ = ["Candidate", "Project", "describe", "find_repos", "with_files"]

# Where a project keeps executables that are installed but not on PATH. Checked
# in order, so a repo with both a node and a python toolchain resolves each
# token against the right one.
_BIN_DIRS = ("node_modules/.bin", ".venv/bin", "venv/bin", ".tox/py3/bin")

# Tools that take file paths as trailing arguments. Only tools whose argument
# handling is unambiguous are listed: appending a path to a command that does
# not expect one turns a working baseline into a usage error, which is a worse
# failure than the one being avoided.
_TAKES_FILES = {
    "eslint", "biome", "prettier", "stylelint", "tsc", "oxlint",
    "pytest", "mypy", "ruff", "flake8", "pylint", "black",
    "vitest", "jest", "phpstan", "psalm", "rubocop",
}


@dataclass
class Candidate:
    """One command that might establish a baseline, and why it was proposed."""
    cmd: str
    why: str
    accepts_files: bool = False
    # True when this command builds or bundles. Kept last in the ladder: it is
    # the slowest thing a project owns, and it is the one most likely to be
    # impossible inside a worktree.
    heavy: bool = False


@dataclass
class Project:
    root: pathlib.Path
    language: str = "unknown"
    framework: str = ""
    manager: str = ""
    candidates: list[Candidate] = field(default_factory=list)

    @property
    def stack(self) -> str:
        """One line for a picker: `TypeScript · Next.js · pnpm`."""
        return " · ".join(p for p in (self.language, self.framework,
                                      self.manager) if p)

    @property
    def best(self) -> str:
        return self.candidates[0].cmd if self.candidates else ""


def with_files(cmd: str, files: list[str]) -> str:
    """Scope `cmd` to `files`, when its tool is one that takes paths.

    This is what rescues a baseline in a repository carrying lint debt: the
    project-wide run is red for reasons that have nothing to do with the commit
    under review, while the same tool over the touched files is clean.
    """
    if not files or not cmd:
        return cmd
    tool = pathlib.Path(cmd.split()[0].split("/")[-1]).name
    if tool not in _TAKES_FILES:
        return cmd
    return f"{cmd} {' '.join(files)}"


def _local_bin(root: pathlib.Path, token: str) -> str | None:
    """The repo-local executable for `token`, as a path a shell can run."""
    for d in _BIN_DIRS:
        if (root / d / token).exists():
            return f"./{d}/{token}"
    return None


def _resolve(root: pathlib.Path, script_body: str) -> tuple[str, bool]:
    """Rewrite a package script to call its binary directly.

    `"lint": "eslint ."` becomes `./node_modules/.bin/eslint .` -- same tool,
    same arguments, but the package manager never runs, so its dependency
    verification cannot reject the worktree. Returns the command and whether
    the rewrite happened.
    """
    parts = script_body.split()
    if not parts:
        return script_body, False
    # `next build`, `tsc --noEmit`, `vitest run` -- the tool is the first token.
    binp = _local_bin(root, parts[0])
    if not binp:
        return script_body, False
    return " ".join([binp, *parts[1:]]), True


def _js(root: pathlib.Path, p: Project) -> None:
    try:
        pkg = json.loads((root / "package.json").read_text())
    except Exception:
        return
    scripts = pkg.get("scripts") or {}
    deps = {**(pkg.get("dependencies") or {}),
            **(pkg.get("devDependencies") or {})}

    p.language = "TypeScript" if (root / "tsconfig.json").exists() else "JavaScript"
    p.manager = ("pnpm" if (root / "pnpm-lock.yaml").exists() else
                 "yarn" if (root / "yarn.lock").exists() else
                 "bun" if (root / "bun.lockb").exists()
                       or (root / "bun.lock").exists() else "npm")
    for dep, name in (("next", "Next.js"), ("nuxt", "Nuxt"), ("@angular/core", "Angular"),
                      ("@nestjs/core", "NestJS"), ("astro", "Astro"), ("svelte", "Svelte"),
                      ("vue", "Vue"), ("remix", "Remix"), ("express", "Express"),
                      ("react", "React")):
        if dep in deps:
            p.framework = name
            break

    # Ordered by what makes the best baseline, not by what the project lists
    # first: a test proves behaviour, a typecheck proves the code still
    # compiles, a linter proves neither but is fast and file-scopable, and a
    # build is the slowest and least likely to survive a worktree.
    for name in ("test", "test:unit", "typecheck", "type-check", "lint", "build"):
        body = scripts.get(name)
        if not body:
            continue
        cmd, rewritten = _resolve(root, body)
        tool = cmd.split()[0].split("/")[-1] if cmd.split() else ""
        why = f"package.json scripts.{name}"
        if rewritten:
            why += f" (as {tool}, bypassing {p.manager})"
        p.candidates.append(Candidate(
            cmd, why,
            accepts_files=tool in _TAKES_FILES,
            heavy=name == "build" or "build" in body))

    # A project can own a usable tool without naming it in `scripts`.
    for tool, why in (("vitest", "vitest is installed"),
                      ("jest", "jest is installed"),
                      ("eslint", "eslint is installed"),
                      ("tsc", "typescript is installed")):
        binp = _local_bin(root, tool)
        if binp and not any(tool in c.cmd for c in p.candidates):
            cmd = f"{binp} --noEmit" if tool == "tsc" else binp
            p.candidates.append(Candidate(cmd, why,
                                          accepts_files=tool in _TAKES_FILES))
    if p.manager == "bun" and not p.candidates:
        p.candidates.append(Candidate("bun test", "bun's built-in test runner"))


def _py(root: pathlib.Path, p: Project) -> None:
    p.language = "Python"
    if (root / "manage.py").exists():
        p.framework = "Django"
    else:
        blob = ""
        for f in ("pyproject.toml", "requirements.txt", "Pipfile"):
            try:
                blob += (root / f).read_text().lower()
            except Exception:
                pass
        for key, name in (("fastapi", "FastAPI"), ("flask", "Flask"),
                          ("django", "Django"), ("streamlit", "Streamlit")):
            if key in blob:
                p.framework = name
                break
    if (root / ".venv").is_dir():
        p.manager = ".venv"

    if p.framework == "Django" and (root / "manage.py").exists():
        py = _local_bin(root, "python") or "python"
        p.candidates.append(Candidate(f"{py} manage.py test", "manage.py (Django)"))
    pytest_bin = _local_bin(root, "pytest")
    has_tests = ((root / "tests").is_dir() or (root / "test").is_dir()
                 or any(root.glob("test_*.py")))
    if has_tests:
        p.candidates.append(Candidate(f"{pytest_bin or 'pytest'} -q",
                                      "a tests directory" if not pytest_bin
                                      else "a tests directory (repo-local pytest)",
                                      accepts_files=True))
    for tool in ("ruff", "mypy"):
        binp = _local_bin(root, tool)
        if binp:
            arg = " check" if tool == "ruff" else ""
            p.candidates.append(Candidate(f"{binp}{arg}", f"{tool} is installed",
                                          accepts_files=True))
    for entry in ("main.py", "app.py", "run.py"):
        if (root / entry).exists():
            py = _local_bin(root, "python") or "python"
            p.candidates.append(Candidate(f"{py} {entry}", entry))
            break


def _simple(lang: str, framework: str, cmds: list[tuple[str, str]]):
    def build(root: pathlib.Path, p: Project) -> None:
        p.language, p.framework = lang, framework
        p.candidates.extend(Candidate(c, w) for c, w in cmds)
    return build


# Marker -> the function that fills in a Project. First match wins, so the more
# specific markers come first.
_TABLE = [
    ("package.json", _js),
    ("deno.json", _simple("TypeScript", "Deno", [("deno test -A", "deno.json")])),
    ("go.mod", _simple("Go", "", [("go test ./...", "go.mod"),
                                  ("go build ./...", "go.mod")])),
    ("Cargo.toml", _simple("Rust", "", [("cargo test", "Cargo.toml"),
                                        ("cargo check", "Cargo.toml")])),
    ("pom.xml", _simple("Java", "Maven", [("mvn -q test", "pom.xml")])),
    ("build.gradle", _simple("Java", "Gradle", [("gradle test", "build.gradle")])),
    ("Gemfile", _simple("Ruby", "", [("bundle exec rspec", "Gemfile")])),
    ("composer.json", _simple("PHP", "", [("composer test", "composer.json")])),
    ("manage.py", _py),
    ("pyproject.toml", _py),
    ("setup.py", _py),
    ("requirements.txt", _py),
    ("Pipfile", _py),
    ("CMakeLists.txt", _simple("C/C++", "CMake",
                               [("ctest --test-dir build", "CMakeLists.txt")])),
    ("Makefile", _simple("", "Make", [("make test", "Makefile")])),
]


def describe(repo: str | pathlib.Path) -> Project:
    """Identify `repo` and propose baseline commands, best first."""
    root = pathlib.Path(repo).expanduser().resolve()
    p = Project(root=root)
    if not root.is_dir():
        return p
    for marker, build in _TABLE:
        if (root / marker).exists():
            build(root, p)
            if p.candidates or p.language != "unknown":
                break
    # A build is the slowest candidate and the one most likely to be impossible
    # inside a worktree; it should never be tried before something cheaper.
    p.candidates.sort(key=lambda c: c.heavy)
    return p


def find_repos(roots: list[str] | None = None, depth: int = 2) -> list[pathlib.Path]:
    """Git repositories under `roots`, most recently modified first.

    Shallow on purpose: a full-disk walk is slow and turns up vendored checkouts
    nobody wants to review.
    """
    home = pathlib.Path.home()
    roots = roots or [str(home / "Documents"), str(home / "code"),
                      str(home / "projects"), str(home / "src")]
    found: dict[pathlib.Path, float] = {}
    for r in roots:
        base = pathlib.Path(r).expanduser()
        if not base.is_dir():
            continue
        for d in ([base] if (base / ".git").exists() else []):
            found[d] = d.stat().st_mtime
        for lvl in range(1, depth + 1):
            try:
                for git in base.glob("/".join(["*"] * lvl) + "/.git"):
                    repo = git.parent
                    try:
                        found[repo] = git.stat().st_mtime
                    except OSError:
                        pass
            except OSError:
                continue
    return sorted(found, key=lambda d: found[d], reverse=True)
