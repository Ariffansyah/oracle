"""Render a unified diff the way `git diff --word-diff=plain` would.

Why this exists: a unified diff shows an edited line as a removal followed by an
addition, and the model reads that literally — six of `mechanism-v1`'s seven
false alarms are one claim, that a call was *removed*, when the diff shows it
edited in place. `--word-diff=plain` marks the change inside the line,
`[-gone-]{+added+}`, which makes an in-place edit unmistakable.

Swapping the rendering at *inference* was measured and lost (41/46 -> 36/46):
the model was fine-tuned on unified diffs and reads boundaries badly in a
notation it has never seen. So the rendering has to change in *training*, and
the corpus records carry only diff text — the original blobs are long gone.
This module converts the text, so no re-fetch is needed.

Correctness is not assumed: `_selftest` regenerates real word-diffs with git and
compares, over every case in `bench/mechanism_pilot`.
"""

from __future__ import annotations

import re

_HUNK = re.compile(r"^@@ .* @@")


_TOKEN = re.compile(r"\s+|\S+")


def _tokens(lines: list[str]) -> list[str]:
    """Words and whitespace runs, both as tokens.

    Diffing whitespace alongside words is what keeps `i [-<-]{+<=+} 5` from
    collapsing to `i[-<-]{+<=+}5`: the spaces around a changed word are equal on
    both sides, so they fall outside the marked span exactly as git puts them.
    """
    return _TOKEN.findall("\n".join(lines))


def _segments(removed: list[str], added: list[str]) -> list[tuple[str, str]]:
    """(kind, text) runs, kind in {equal, del, add}."""
    import difflib

    a, b = _tokens(removed), _tokens(added)
    out: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            out.append(("equal", "".join(a[i1:i2])))
        else:
            if i2 > i1:
                out.append(("del", "".join(a[i1:i2])))
            if j2 > j1:
                out.append(("add", "".join(b[j1:j2])))
    return out


def _hug(segs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Move whitespace at the edges of a marked run into its equal neighbour.

    `difflib` will happily put the indentation of the *next* line inside an
    insertion, giving `{+\\t+}for (...)`; git hugs the marker to the changed
    words instead. Purely cosmetic - it never changes which words are marked -
    but it is the difference between a diff that reads like git's and one that
    does not. Segments that are whitespace only are left alone, since moving
    their content would delete the segment, and so is whitespace that spans a
    line break: git marks a wholly deleted line *including* its indentation.
    """
    segs = [list(s) for s in segs]
    for i, (kind, text) in enumerate(segs):
        if kind == "equal" or not text.strip():
            continue
        at_line_start = i == 0 or segs[i - 1][1].endswith("\n")
        lead = text[:len(text) - len(text.lstrip())]
        if lead and i and not at_line_start and "\n" not in lead:
            segs[i - 1][1] += lead
            segs[i][1] = text = text[len(lead):]
        tail = text[len(text.rstrip()):]
        if tail and i + 1 < len(segs) and "\n" not in tail:
            segs[i + 1][1] = tail + segs[i + 1][1]
            segs[i][1] = text[:len(text) - len(tail)]
    return [(k, t) for k, t in segs if t]


_OPEN = {"del": "[-", "add": "{+"}
_CLOSE = {"del": "-]", "add": "+}"}


def _mark(removed: list[str], added: list[str]) -> str:
    """Word-diff text for one hunk, markers closed at every line break.

    git never lets `[-...-]` straddle a newline: it closes the marker at the end
    of the line and opens a fresh one on the next. Without that a multi-line
    deletion renders as one run-on blob and the line structure of the code -
    the thing the reader is matching against the file - is lost.
    """
    lines: list[str] = [""]
    for kind, text in _hug(_segments(removed, added)):
        for i, part in enumerate(text.split("\n")):
            if i:
                lines.append("")
            if not part:
                continue
            # Marking pure whitespace says nothing a reader can act on, and
            # git leaves it unmarked; only the words carry the change.
            marked = kind != "equal" and part.strip()
            lines[-1] += (_OPEN[kind] + part + _CLOSE[kind]) if marked else part
    return "\n".join(lines)


def to_word_diff(diff: str) -> str:
    """Convert unified-diff text to word-diff text, headers preserved.

    git word-diffs a whole hunk at once, not each removal/addition run: the
    pre-image (context + removed lines) is diffed against the post-image
    (context + added lines) as two continuous token streams. That is why a line
    moved out of a loop shows up as an insertion in one place and a deletion in
    another, and why indentation shared with the surrounding context stays
    outside the markers.
    """
    out: list[str] = []
    pre: list[str] = []
    post: list[str] = []
    in_hunk = False

    def flush() -> None:
        nonlocal pre, post
        if pre or post:
            out.extend(_mark(pre, post).split("\n"))
        pre, post = [], []

    for line in diff.splitlines():
        if _HUNK.match(line) or line.startswith(
                ("diff --git", "index ", "--- ", "+++ ", "old mode", "new mode",
                 "similarity ", "rename ", "new file", "deleted file",
                 "Binary files")):
            flush()
            in_hunk = bool(_HUNK.match(line))
            out.append(line)
            continue
        if not in_hunk:
            flush()
            out.append(line)
            continue
        if line.startswith("\\"):          # "\ No newline at end of file"
            continue
        if line.startswith("-"):
            pre.append(line[1:])
        elif line.startswith("+"):
            post.append(line[1:])
        else:
            body = line[1:] if line.startswith(" ") else line
            pre.append(body)
            post.append(body)
    flush()
    return "\n".join(out) + ("\n" if diff.endswith("\n") else "")


def _selftest() -> None:
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "bench"
    cases = sorted(root.glob("*/*/meta.json"))
    assert cases, f"no bench cases under {root}"

    def git(args: list[str], a: Path, b: Path) -> str:
        p = subprocess.run(["git", "diff", "--no-index", "--no-color", *args,
                            "--src-prefix=a/", "--dst-prefix=b/", str(a), str(b)],
                           capture_output=True, text=True)
        return p.stdout

    checked = mismatched = 0
    for meta in cases:
        import json
        m = json.loads(meta.read_text())
        d = meta.parent
        pre, post = d / f"pre.{m['ext']}", d / f"post.{m['ext']}"
        if not (pre.exists() and post.exists()):
            continue
        unified = git([], pre, post)
        want = git(["--word-diff=plain"], pre, post)
        got = to_word_diff(unified)

        def body(text: str) -> list[str]:
            keep, seen = [], False
            for ln in text.splitlines():
                if _HUNK.match(ln):
                    seen = True
                    continue
                if seen and ln.strip():
                    keep.append(ln.rstrip())
            return keep

        checked += 1
        if body(got) != body(want):
            mismatched += 1
            if mismatched <= 2:
                print(f"  mismatch {d.name}\n    want {body(want)}\n    got  {body(got)}")
    print(f"word-diff: {checked - mismatched}/{checked} cases match git exactly")
    assert checked, "no comparable cases"
    return checked, mismatched


if __name__ == "__main__":
    _selftest()
