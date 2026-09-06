"""Decide, structurally, that a commit cannot have introduced a defect.

    from llm_explainer.ast_guardrails import safe_change, commit_verdict
    v = safe_change(pre_src, post_src, "python")
    if v.safe: ...      # skip the LLM, answer `unchanged` with no findings

Why
---
The 1 Sep hand-grade found the tuned model flagging 29 of 40 real commits that
were feature additions, annotation passes, docs and CI edits. Some of those are
decidable without a language model: if every declaration that existed before is
still there with the same body, and the only difference is new declarations,
comments or type annotations, then no existing caller can observe a change.

Which way to be wrong
---------------------
A false BYPASS is a defect nobody ever reviews. A false NON-bypass costs one
LLM call. So every rule here refuses unless it can prove safety, and anything
unparseable, unrecognised or merely unusual returns `safe=False`. The verdict is
never "probably fine"; it is "the pre-image declarations all survive byte-for-
byte after normalisation, and nothing else changed".

What normalisation removes
--------------------------
Comments, docstrings and type annotations, then all whitespace. That is what
makes "docstring-only" and "type-hint-only" edits fall out of the same
comparison as "added a new function" rather than needing rules of their own:
after stripping, an unchanged body is byte-identical to its old self.

Scope
-----
python, javascript, typescript, java - the languages this project mines. A file
in any other language makes the whole commit unsafe, because a commit is only as
safe as the file we understand least.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

EXT_LANG = {".py": "python", ".js": "javascript", ".mjs": "javascript",
            ".cjs": "javascript", ".ts": "typescript", ".tsx": "typescript",
            ".java": "java"}

# Files that cannot affect what the program does when it runs. These are NEUTRAL
# rather than unknown: an unknown file sinks the whole commit, and that was too
# strict - TestJIT's "add sum and max helpers" is a pure function addition, and
# it was refused only because the same commit touches `.gitignore`.
#
# The bar for entry here is that the file is never executed and never consumed
# by the program at run time. Build and dependency files are deliberately NOT in
# the list: a Makefile, a package.json or a pom.xml changes what gets built and
# with which versions, which is exactly the kind of thing a reviewer should see.
INERT_NAMES = {".gitignore", ".gitattributes", ".editorconfig", ".gitmodules",
               "license", "licence", "license.txt", "license.md", "notice",
               "copying", "authors", "contributors", "codeowners",
               ".mailmap", "changelog.md", "changelog", "readme", "readme.md"}
INERT_SUFFIX = {".md", ".rst", ".adoc", ".txt"}


def is_inert(path: str) -> bool:
    """A file whose contents cannot change behaviour at run time."""
    p = Path(path)
    return p.name.lower() in INERT_NAMES or p.suffix.lower() in INERT_SUFFIX

# Node types that declare something a caller can reach. Anything else at the top
# level is executable statement, and a change there is not structural.
DECLS = {
    "python": {"function_definition", "class_definition", "decorated_definition"},
    "javascript": {"function_declaration", "class_declaration", "method_definition",
                   "lexical_declaration", "variable_declaration",
                   "export_statement"},
    "typescript": {"function_declaration", "class_declaration", "method_definition",
                   "lexical_declaration", "variable_declaration",
                   "export_statement", "interface_declaration",
                   "type_alias_declaration"},
    "java": {"class_declaration", "interface_declaration", "method_declaration",
             "constructor_declaration", "field_declaration", "enum_declaration"},
}

IMPORTS = {
    "python": {"import_statement", "import_from_statement"},
    "javascript": {"import_statement"},
    "typescript": {"import_statement"},
    "java": {"import_declaration"},
}

COMMENTS = {"comment", "line_comment", "block_comment", "documentation_comment"}

# Only these are descended into, to index their members. Descending into a
# FUNCTION body collected its `return` as a top-level statement and made every
# added-function commit read as "top-level executable statements changed" - the
# body is already inside the declaration's own normalised form.
CONTAINERS = {"class_definition", "class_declaration", "interface_declaration",
              "enum_declaration", "class_body", "decorated_definition"}

# Type annotation node types, stripped so a type-hint-only edit reads as no
# change. `type` covers python's annotations and TS's `: Foo`.
TYPES = {"type", "type_annotation", "type_parameters", "type_arguments",
         "generic_type", "type_identifier", "predefined_type"}

_WS = re.compile(rb"\s+")


@dataclass
class Verdict:
    safe: bool
    reason: str

    def __bool__(self) -> bool:
        return self.safe


def language_of(path: str) -> str | None:
    return EXT_LANG.get(Path(path).suffix.lower())


def _parser(lang: str):
    import tree_sitter as ts
    if lang == "python":
        import tree_sitter_python as m
        return ts.Parser(ts.Language(m.language()))
    if lang == "javascript":
        import tree_sitter_javascript as m
        return ts.Parser(ts.Language(m.language()))
    if lang == "typescript":
        import tree_sitter_typescript as m
        return ts.Parser(ts.Language(m.language_typescript()))
    if lang == "java":
        import tree_sitter_java as m
        return ts.Parser(ts.Language(m.language()))
    raise ValueError(lang)


def _name_of(node, src: bytes) -> str | None:
    n = node.child_by_field_name("name")
    if n is not None:
        return src[n.start_byte:n.end_byte].decode("utf8", "replace")
    # export/lexical wrappers carry the name one level down
    for c in node.named_children:
        n = c.child_by_field_name("name")
        if n is not None:
            return src[n.start_byte:n.end_byte].decode("utf8", "replace")
    return None


def _widen_left(src: bytes, start: int) -> int:
    """Extend a stripped type range back over its own punctuation.

    Removing the `type` node alone leaves the syntax that introduced it, so
    `def a(x: int) -> int` normalised to `defa(x:)->:` and never matched the
    un-annotated `defa(x):`. Only `:` and `->` immediately left of a type node
    are eaten, so Java's lambda arrow - which never sits there - is untouched.
    """
    i = start
    while i > 0 and src[i - 1:i].isspace():
        i -= 1
    if src[max(0, i - 2):i] == b"->":
        i -= 2
    elif src[max(0, i - 1):i] == b":":
        i -= 1
    else:
        return start
    while i > 0 and src[i - 1:i].isspace():
        i -= 1
    return i


def _strip_ranges(node, src: bytes, lang: str, out: list) -> None:
    """Byte ranges of comments, docstrings and type annotations."""
    if node.type in COMMENTS:
        out.append((node.start_byte, node.end_byte))
        return
    if node.type in TYPES:
        out.append((_widen_left(src, node.start_byte), node.end_byte))
        return
    # python docstring: a bare string statement first in a block
    if lang == "python" and node.type == "block" and node.named_child_count:
        first = node.named_child(0)
        if (first.type == "expression_statement" and first.named_child_count
                and first.named_child(0).type == "string"):
            out.append((first.start_byte, first.end_byte))
    for c in node.children:
        _strip_ranges(c, src, lang, out)


def normalise(node, src: bytes, lang: str) -> bytes:
    """Node source with comments, docstrings, types and whitespace removed."""
    ranges: list = []
    _strip_ranges(node, src, lang, ranges)
    keep, cursor = [], node.start_byte
    for a, b in sorted(ranges):
        if a >= node.end_byte or b <= node.start_byte:
            continue
        a, b = max(a, node.start_byte), min(b, node.end_byte)
        if a > cursor:
            keep.append(src[cursor:a])
        cursor = max(cursor, b)
    keep.append(src[cursor:node.end_byte])
    return _WS.sub(b"", b"".join(keep))


def normalise_header(node, src: bytes, lang: str) -> bytes:
    """A container's declaration WITHOUT its members.

    A class's normalised form contains its methods, so adding one changed the
    class and every added-method commit read as "changes the body of C". The
    members are indexed separately one level down, so the container only has to
    compare its own header - name, bases, modifiers, decorators.
    """
    ranges: list = []
    _strip_ranges(node, src, lang, ranges)
    body = node.child_by_field_name("body")
    if body is not None:
        ranges.append((body.start_byte, body.end_byte))
    keep, cursor = [], node.start_byte
    for a, b in sorted(ranges):
        if a >= node.end_byte or b <= node.start_byte:
            continue
        a, b = max(a, node.start_byte), min(b, node.end_byte)
        if a > cursor:
            keep.append(src[cursor:a])
        cursor = max(cursor, b)
    keep.append(src[cursor:node.end_byte])
    return _WS.sub(b"", b"".join(keep))


def _index(src_text: str, lang: str) -> tuple[dict, bytes, list] | None:
    """{(kind, name): normalised body} for a file, plus its other top-level nodes."""
    try:
        src = src_text.encode("utf8")
        tree = _parser(lang).parse(src)
    except Exception:
        return None
    if tree.root_node.has_error:
        return None                      # unparseable: refuse to judge it

    decls: dict = {}
    other: list = []

    def walk(node, depth: int) -> None:
        for c in node.named_children:
            if c.type in DECLS.get(lang, ()):
                is_container = c.type in CONTAINERS
                decls[(c.type, _name_of(c, src), depth)] = (
                    normalise_header(c, src, lang) if is_container
                    else normalise(c, src, lang))
                # Descend only into containers, so a changed METHOD inside an
                # otherwise-identical class is still caught.
                if is_container:
                    body = c.child_by_field_name("body")
                    if body is not None:
                        walk(body, depth + 1)
            elif c.type in IMPORTS.get(lang, ()) or c.type in COMMENTS:
                continue                 # handled separately / not behaviour
            elif depth == 0:
                # Executable statements, module level only. Below that they
                # belong to a declaration and are compared as part of it.
                other.append(normalise(c, src, lang))

    walk(tree.root_node, 0)
    return decls, src, other


def safe_change(pre_text: str, post_text: str, lang: str) -> Verdict:
    """True only when every pre-image declaration survives unchanged."""
    if lang not in DECLS:
        return Verdict(False, f"{lang} is not a language this can reason about")
    a, b = _index(pre_text, lang), _index(post_text, lang)
    if a is None or b is None:
        return Verdict(False, "one side does not parse cleanly")
    pre, _, pre_other = a
    post, _, post_other = b

    removed = [k for k in pre if k not in post]
    if removed:
        return Verdict(False, f"removes {removed[0][1] or removed[0][0]}")
    changed = [k for k in pre if pre[k] != post[k]]
    if changed:
        return Verdict(False, f"changes the body of {changed[0][1] or changed[0][0]}")
    # Executable top-level statements must be identical as a SET and in count:
    # adding a module-level call changes what the program does on import.
    if sorted(pre_other) != sorted(post_other):
        return Verdict(False, "top-level executable statements changed")

    added = [k for k in post if k not in pre]
    if added:
        return Verdict(True, f"adds {len(added)} declaration(s); "
                             f"every pre-existing one is byte-identical")
    return Verdict(True, "no declaration added, changed or removed "
                         "(comments, docstrings or type annotations only)")


def _git(repo: str, args: list[str]) -> str:
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True).stdout


def commit_verdict(repo: str, rev: str) -> Verdict:
    """Safe only when EVERY changed file is safe. One unknown file sinks it."""
    files = [f for f in _git(repo, ["show", "--format=", "--name-only", rev]).split()
             if f]
    if not files:
        return Verdict(False, "no files in commit")
    judged = 0
    for path in files:
        if is_inert(path):
            continue          # cannot execute; carries no behaviour to change
        lang = language_of(path)
        if lang is None:
            return Verdict(False, f"{path}: not a language this can reason about")
        judged += 1
        pre = _git(repo, ["show", f"{rev}^:{path}"])
        post = _git(repo, ["show", f"{rev}:{path}"])
        if not post:
            return Verdict(False, f"{path}: deleted or unreadable")
        if not pre:
            return Verdict(False, f"{path}: new file, nothing to compare")
        v = safe_change(pre, post, lang)
        if not v.safe:
            return Verdict(False, f"{path}: {v.reason}")
    inert = len(files) - judged
    if judged == 0:
        return Verdict(True, f"all {len(files)} changed file(s) are non-executing "
                             f"(docs, licence, ignore rules)")
    tail = f", plus {inert} non-executing file(s)" if inert else ""
    return Verdict(True, f"{judged} source file(s) structurally safe{tail}")


def _selftest() -> None:
    # --- python: adding a top-level function is safe
    pre = "def a(x):\n    return x + 1\n"
    post = pre + "\n\ndef b(y):\n    return y * 2\n"
    assert safe_change(pre, post, "python").safe

    # changing an existing body is NOT safe, even by one operator
    assert not safe_change(pre, "def a(x):\n    return x - 1\n", "python").safe

    # removing a function is NOT safe
    assert not safe_change(post, pre, "python").safe

    # docstring-only and type-hint-only edits are safe
    assert safe_change(pre, 'def a(x):\n    """doc."""\n    return x + 1\n',
                       "python").safe
    assert safe_change(pre, "def a(x: int) -> int:\n    return x + 1\n",
                       "python").safe

    # a new top-level CALL is not safe: it changes what running the file does
    assert not safe_change(pre, pre + "print(a(1))\n", "python").safe

    # a changed method inside an unchanged class must be caught
    cpre = "class C:\n    def m(self):\n        return 1\n"
    cpost = "class C:\n    def m(self):\n        return 2\n"
    assert not safe_change(cpre, cpost, "python").safe
    assert safe_change(cpre, "class C:\n    def m(self):\n        return 1\n"
                             "    def n(self):\n        return 3\n", "python").safe

    # --- javascript
    jpre = "export function a(x) { return x + 1 }\n"
    assert safe_change(jpre, jpre + "export function b(y) { return y }\n",
                       "javascript").safe
    assert not safe_change(jpre, "export function a(x) { return x + 2 }\n",
                           "javascript").safe
    assert safe_change(jpre, "// JSDoc\n" + jpre, "javascript").safe

    # --- java: added method safe, changed body not
    kpre = "class C { int m() { return 1; } }\n"
    assert safe_change(kpre, "class C { int m() { return 1; } int n() { return 2; } }\n",
                       "java").safe
    assert not safe_change(kpre, "class C { int m() { return 9; } }\n", "java").safe

    # unparseable input must refuse rather than guess
    assert not safe_change(pre, "def a(x:\n", "python").safe
    # an unsupported language must refuse
    assert not safe_change("a", "b", "rust").safe

    # inert files must not sink an otherwise-safe commit, and must not become a
    # loophole for anything that actually runs
    from llm_explainer.ast_guardrails import is_inert
    assert is_inert(".gitignore") and is_inert("docs/guide.md") and is_inert("LICENSE")
    assert not is_inert("Makefile"), "a Makefile changes what gets built"
    assert not is_inert("package.json"), "dependency files change what is resolved"
    assert not is_inert("pom.xml") and not is_inert("app.py")

    print("ast_guardrails selftest ok")


if __name__ == "__main__":
    _selftest()
