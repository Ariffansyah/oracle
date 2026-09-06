"""JS/TS, Go, Python and C++: detection, what a command proves, and hazards.

Every one of these was measured as broken before it was written: CMake, meson,
Deno, bun, tox, nox, Django and plain requirements.txt layouts all detected
NOTHING, so the tool asked the user for a command on projects that name their
own perfectly well.
"""
import pathlib, tempfile
from oracle_reviewer.core import suggest_run, command_class
from oracle_reviewer.static_claims import risky_edits

def project(**files):
    d = pathlib.Path(tempfile.mkdtemp())
    for name, body in files.items():
        f = d / name.replace("|", "/")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
    return str(d)

# ------------------------------------------------------------------ detection
assert suggest_run(project(**{"go.mod": ""}))[0] == "go test ./..."
assert suggest_run(project(**{"tox.ini": ""}))[0] == "tox"
assert suggest_run(project(**{"noxfile.py": ""}))[0] == "nox"
assert suggest_run(project(**{"manage.py": ""}))[0] == "python manage.py test"
assert suggest_run(project(**{"requirements.txt": "", "tests|t.py": ""}))[0] == "pytest -q"

# Django wins over a bare tests/ dir: pytest against a Django project without
# pytest-django collects nothing, which looks exactly like a clean pass.
both = project(**{"manage.py": "", "tests|t.py": "", "pyproject.toml": ""})
assert suggest_run(both)[0] == "python manage.py test", suggest_run(both)

# C++ needs a CONFIGURED tree. Source alone must yield nothing rather than a
# command that fails for reasons unrelated to the commit.
assert suggest_run(project(**{"CMakeLists.txt": ""}))[0] == ""
cm = project(**{"CMakeLists.txt": "", "build|CTestTestfile.cmake": ""})
assert suggest_run(cm)[0].startswith("ctest --test-dir build")
cb = project(**{"CMakeLists.txt": "", "build|CMakeCache.txt": ""})
assert suggest_run(cb)[0] == "cmake --build build"
assert suggest_run(project(**{"meson.build": ""}))[0] == ""
ms = project(**{"meson.build": "", "build|build.ninja": ""})
assert suggest_run(ms)[0] == "meson test -C build"

# Deno and bun name their own runners.
assert suggest_run(project(**{"deno.json": '{"tasks":{"test":"deno test"}}'}))[0] \
    == "deno task test"
assert suggest_run(project(**{"deno.json": "{}"}))[0] == "deno test -A"
bun = project(**{"package.json": '{"scripts":{}}', "bun.lockb": ""})
assert suggest_run(bun)[0] == "bun test", suggest_run(bun)
# The lockfile picks the runner for a project that DOES have scripts.
bun2 = project(**{"package.json": '{"scripts":{"test":"x"}}', "bun.lockb": ""})
assert suggest_run(bun2)[0] == "bun test"

# ------------------------------------------------------- what a command proves
assert command_class("go test ./...") == "tests"
assert command_class("go build ./...") == "build"
assert command_class("go vet ./...") == "analysis"
assert command_class("staticcheck ./...") == "analysis"
assert command_class("gofmt -l .") == "style"
assert command_class("ctest --test-dir build") == "tests"
assert command_class("meson test -C build") == "tests"
assert command_class("clang-tidy a.cpp") == "analysis"
assert command_class("cppcheck src") == "analysis"
assert command_class("g++ -c main.cpp") == "build"
assert command_class("./build/tests") == "tests"      # plural, not a build
assert command_class("tox") == "tests"
assert command_class("deno lint") == "style"
assert command_class("bun test") == "tests"
assert command_class("black --check .") == "style"

# --------------------------------------------------------------- hazards
D = lambda path, body: f"--- a/{path}\n+++ b/{path}\n@@ -1,6 +1,6 @@\n{body}"
one = lambda d: (risky_edits(d) or ["NOTHING"])[0]

assert "Go error check" in one(D("a.go", "-\tif err != nil {\n-\t\treturn err\n-\t}\n+\tuse(v)\n"))
assert "defer" in one(D("a.go", "-\tdefer f.Close()\n+\tread(f)\n"))
assert "null-pointer" in one(D("a.cpp", "-  if (p == nullptr) return;\n+  use(p);\n"))
assert "free" in one(D("a.cpp", "-  free(buf);\n+  log(buf);\n"))

# Adding an error check is not removing one.
assert risky_edits(D("a.go", "+\tif err != nil {\n+\t\treturn err\n+\t}\n")) == []
# A check that moved is not a check that was deleted.
moved = D("a.go", "-\tif err != nil {\n-\t\treturn err\n-\t}\n"
                  "+\tlog(v)\n+\tif err != nil {\n+\t\treturn err\n+\t}\n")
assert risky_edits(moved) == [], risky_edits(moved)

print("ok")
