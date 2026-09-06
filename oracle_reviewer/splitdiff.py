"""Turn a unified diff into two aligned columns, the way a reviewer reads it.

A unified diff interleaves the two versions, so following one of them means
skipping every line belonging to the other. Side by side, a changed line sits
opposite the line it replaced and the eye compares them directly.

The alignment rule is the one that matters: within a run of changes, the Nth
removed line is placed opposite the Nth added line, and whichever side runs out
first is padded. That is what puts `range(1, n)` directly across from
`range(1, n + 1)` instead of five lines below it.
"""
from __future__ import annotations

import re

__all__ = ["Row", "split"]

_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
# Header lines carry no content. "--- a/x" and "+++ b/x" must be dropped BEFORE
# the +/- tests below, or the file paths are rendered as a deleted and an added
# line of code.
_HEADER = ("diff ", "index ", "--- ", "+++ ", "old mode", "new mode",
           "new file", "deleted file", "similarity ", "rename ", "Binary ")


class Row(tuple):
    """(left, right), each None or (lineno | None, text, kind).

    kind is one of: ctx, del, add, hunk. A `hunk` row spans both columns.
    """
    __slots__ = ()


def split(diff: str) -> list[Row]:
    rows: list[Row] = []
    lno = rno = 0
    dels: list[tuple] = []
    adds: list[tuple] = []
    # Everything before the first @@ is preamble, whatever it looks like. Without
    # this a `git show` (commit message indented by four spaces) renders as
    # context lines of source, and a message line starting with "-" renders as
    # deleted code.
    seen_hunk = False

    def flush() -> None:
        """Pair the pending removals against the pending additions."""
        nonlocal dels, adds
        for i in range(max(len(dels), len(adds))):
            rows.append(Row((dels[i] if i < len(dels) else None,
                             adds[i] if i < len(adds) else None)))
        dels, adds = [], []

    for line in diff.splitlines():
        m = _HUNK.match(line)
        if m:
            flush()
            seen_hunk = True
            lno, rno = int(m.group(1)), int(m.group(2))
            rows.append(Row(((None, line, "hunk"), (None, line, "hunk"))))
            continue
        if not seen_hunk or line.startswith(_HEADER):
            continue
        if line.startswith("-"):
            dels.append((lno, line[1:], "del"))
            lno += 1
        elif line.startswith("+"):
            adds.append((rno, line[1:], "add"))
            rno += 1
        else:
            # A context line ends the run: what follows is a separate change.
            flush()
            body = line[1:] if line.startswith(" ") else line
            rows.append(Row(((lno, body, "ctx"), (rno, body, "ctx"))))
            lno += 1
            rno += 1
    flush()
    return rows
