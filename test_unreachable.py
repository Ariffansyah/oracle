"""Files the command cannot even open.

    python test_unreachable.py

"The output was identical, so either it never ran or it changed nothing" is true
but weak when the command provably cannot READ the file. `tsc` is the TypeScript
compiler; a workflow YAML is not something it declines to report on, it is
something it never opens. Saying so is a fact about the toolchain.

Claiming a command cannot reach a file is a strong statement, so the mapping
covers only tools with a narrow, well-understood input set. Everything else
returns None and the ordinary "nothing was established" wording stands.
"""

from oracle_reviewer.core import FileReview, review_body, unreachable

# A CI workflow is run by the forge, not by any local command at all.
why, alt = unreachable("npx tsc --noEmit", ".github/workflows/cleanup.yml")
assert "executed by GitHub" in why
assert "actionlint" in alt

# A tool with a known input set, given a file outside it.
why, alt = unreachable("npx tsc --noEmit", "config/app.yml")
assert "`tsc` does not read `.yml` files" in why and alt == "yamllint"
assert unreachable("pytest -q", "deploy/k8s.yaml")[1] == "yamllint"
assert unreachable("npx eslint .", "styles/main.css")[1] == "stylelint"
assert unreachable("go test ./...", "scripts/deploy.sh")[1] == "shellcheck"

# Files the tool DOES read must never be dismissed.
assert unreachable("npx tsc --noEmit", "components/X.tsx") is None
assert unreachable("npx tsc --noEmit", "lib/util.js") is None
assert unreachable("pytest -q", "src/x.py") is None
assert unreachable("pytest -q", "pyproject.toml") is None
assert unreachable("go test ./...", "main.go") is None
assert unreachable("cargo test", "src/lib.rs") is None

# An unrecognised command claims nothing: a bundler may well read YAML.
assert unreachable("npm run build", "anything.yml") is None
assert unreachable("make check", "anything.yml") is None
assert unreachable("./run.sh", "config.yml") is None

# A file with no extension is not guessed at.
assert unreachable("npx tsc --noEmit", "Makefile") is None
assert unreachable("npx tsc --noEmit", "LICENSE") is None

# The tool name must be a whole word, not a substring of something else.
assert unreachable("npx tsc-alias", "x.yml") is None
assert unreachable("mygo build", "x.yml") is None

# The verdict says the identical output is not evidence, and names an
# alternative rather than leaving the reader stuck.
r = FileReview(path=".github/workflows/x.yml", risk="unreachable",
               static=list(unreachable("npx tsc --noEmit",
                                       ".github/workflows/x.yml")))
body = review_body(r, "npx tsc --noEmit")
assert "cannot check this file" in body
assert "not evidence about the change" in body
assert "What would check it: actionlint" in body
assert r.badge == "Not Checked By This Command"

print("ok")
