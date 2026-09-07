"""The definitions a change refers to, fetched from the repo by grep.

The model gets one file's diff and a measurement. When that diff CALLS
something, it sees the call and has never seen the thing:

    cacheVersion := h.EventCache.Version()
    h.EventCache.Set(cacheKey, body, cacheVersion)

Both are defined in another file, so v3 could only report that `Set` gained a
parameter -- never what the parameter is for, which `Version`'s doc comment
states outright.

Retrieval is done in CODE, not by a second model pass. That is not an
implementation detail, it is the point. A model pass costs ~22s on this card,
can invent a definition that never existed, and would make the explanation
depend on model output that nothing measured -- while this project's claim is
that the facts come from execution and static reading, and the model only
phrases them. A grep costs milliseconds and cannot hallucinate.

The budget is the ADAPTER's: it was trained at 1024 tokens, so a few hundred
characters of definition is affordable and a whole file is not.
"""
from __future__ import annotations

import re
import subprocess

__all__ = ["called_symbols", "find_definition", "related_context"]

# Called or constructed in an ADDED line. Method calls are taken from the last
# component, so `h.EventCache.Version()` yields `Version`.
_CALL = re.compile(r"(?:\.|\b)(?P<name>[A-Za-z_]\w{2,})\s*\(")
_NEW = re.compile(r"\b(?:new|struct|interface)\s+(?P<name>[A-Z]\w{2,})\b")

# Language keywords only. An earlier version also listed "generic" names --
# get, set, add, log, join -- and that dropped `Cache.Set`, the single most
# relevant symbol in the commit this was written for. Whether a name is
# interesting is not a property of the name; it is whether THIS repo declares
# it. `len` and `printf` have no declaration here and fall out for free, while
# `Set` has one and is exactly what was missing.
_SKIP = {
    "if", "for", "while", "switch", "return", "func", "def", "class",
    "range", "type", "import", "from", "self", "this", "super", "new",
    "await", "async", "require", "module", "exports", "struct", "interface",
    "int", "str", "float", "bool", "list", "dict", "map", "make", "len",
    "true", "false", "nil", "null", "not", "and", "or", "in", "is",
}

# How a declaration of NAME looks. One pattern, several languages: the keyword
# forms cover Go/Python/TS/Java/C#/Rust, the assignment forms cover the JS
# idioms where a function is a value.
def _decl_patterns(name: str) -> list[str]:
    n = re.escape(name)
    return [
        rf"^[[:space:]]*(func|def|class|type|struct|interface|fn|impl)[[:space:]].*\b{n}\b",
        rf"^[[:space:]]*(export[[:space:]]+)?(async[[:space:]]+)?function[[:space:]]+{n}\b",
        rf"^[[:space:]]*(export[[:space:]]+)?(const|let|var)[[:space:]]+{n}[[:space:]]*=",
        rf"^[[:space:]]*({n})[[:space:]]*\([^)]*\)[[:space:]]*\{{",   # method in a class body
    ]


def called_symbols(diff: str, limit: int = 6) -> list[str]:
    """Names the added lines call, minus anything the diff itself defines."""
    added, defined = [], set()
    for line in diff.splitlines():
        if line.startswith("+++") or not line.startswith("+"):
            continue
        body = line[1:]
        added.append(body)
        m = re.match(r"\s*(?:export\s+|async\s+)*"
                     r"(?:func|def|function|class|type|struct|interface|fn)\s+"
                     r"(?:\([^)]*\)\s*)?(\w+)", body)
        if m:
            defined.add(m.group(1))

    seen: list[str] = []
    for body in added:
        for m in list(_CALL.finditer(body)) + list(_NEW.finditer(body)):
            n = m.group("name")
            if (n.lower() in _SKIP or n in defined or n in seen
                    or n.isupper()):          # SHOUTY names are constants
                continue
            seen.append(n)
    return seen[:limit]


def find_definition(repo: str, name: str, exclude: str = "",
                    lines: int = 6) -> tuple[str, str] | None:
    """(file, snippet) for the first plausible definition of `name`."""
    for pat in _decl_patterns(name):
        try:
            got = subprocess.run(
                ["git", "-C", repo, "grep", "-n", "-E", "--", pat],
                capture_output=True, text=True, timeout=10).stdout
        except Exception:
            return None
        for hit in got.splitlines():
            parts = hit.split(":", 2)
            if len(parts) < 3:
                continue
            path, lno, _ = parts[0], parts[1], parts[2]
            if path == exclude or not lno.isdigit():
                continue
            try:
                body = subprocess.run(
                    ["git", "-C", repo, "show", f"HEAD:{path}"],
                    capture_output=True, text=True, timeout=10).stdout.splitlines()
            except Exception:
                continue
            i = int(lno) - 1
            # Walk back over the doc comment: it is usually the sentence that
            # says WHY, which is exactly what the caller's diff cannot show.
            start = i
            while start > 0 and re.match(r"^\s*(//|#|\*|/\*)", body[start - 1]):
                start -= 1
            return (path, "\n".join(body[start:i + lines]))
    return None


def related_context(repo: str, path: str, diff: str,
                    budget: int = 900) -> list[tuple[str, str]]:
    """Definitions the diff calls, newest-first, inside a character budget.

    `budget` is deliberately small. The adapter was trained at 1024 tokens
    (~4000 chars) and the diff already claims most of that, so this buys the
    one or two definitions that carry the meaning -- not a file.
    """
    out: list[tuple[str, str]] = []
    spent = 0
    for name in called_symbols(diff):
        got = find_definition(repo, name, exclude=path)
        if not got:
            continue
        where, snippet = got
        if spent + len(snippet) > budget:
            break
        out.append((f"{where}: {name}", snippet))
        spent += len(snippet)
    return out
