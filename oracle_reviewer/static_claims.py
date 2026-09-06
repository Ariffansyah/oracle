"""Facts derivable from the diff alone, with no run involved.

The tool's rule is that risk is measured, not guessed. That rule bars claims
about what a program DID; it does not bar a fact the diff itself settles. When
every changed line is one element whose attributes are byte-identical and whose
visible text differs, "the label changed and the submitted value did not" is
not an opinion about behaviour -- it is what the diff says.

Kept deliberately narrow. Anything the pattern does not match exactly returns
None, and the caller falls back to saying nothing was established. A static
claim that is only usually right is worse than no claim, because it reads with
the same authority as a measured one.
"""
from __future__ import annotations

import re

from .splitdiff import split

__all__ = ["TextChange", "ui_text_change"]

# One element, opening and closing tag on the same line, with plain text
# between them. Anything nested, multi-line or interpolated is out of scope.
_TAG = re.compile(
    r"^\s*<(?P<tag>[A-Za-z][\w.\-]*)(?P<attrs>[^<>]*?)>(?P<text>[^<>{}]*)</(?P=tag)>\s*$")
_ATTR = re.compile(r"""([\w:.\-]+)\s*=\s*("[^"]*"|'[^']*'|\{[^{}]*\})""")


class TextChange(tuple):
    """(tag, attrs, before_text, after_text)."""
    __slots__ = ()

    @property
    def value(self) -> str | None:
        """The submitted value, when this element carries one."""
        raw = self[1].get("value")
        return raw[1:-1] if raw and raw[0] in "\"'" else raw


def ui_text_change(diff: str) -> list[TextChange] | None:
    """Every changed line is a same-attributes, different-text element, or None.

    None means "this diff is something else" -- including a diff that also adds
    or removes lines, since an added element is new behaviour rather than
    relabelled behaviour.
    """
    found: list[TextChange] = []
    for left, right in split(diff):
        if left and left[2] == "hunk":
            continue
        if left and right and left[2] == "ctx":
            continue
        if not (left and right):
            return None               # a pure addition or deletion, not a relabel
        a, b = _TAG.match(left[1]), _TAG.match(right[1])
        if not a or not b or a["tag"] != b["tag"]:
            return None
        attrs_a = dict(_ATTR.findall(a["attrs"]))
        attrs_b = dict(_ATTR.findall(b["attrs"]))
        if attrs_a != attrs_b:
            return None               # an attribute moved: not text-only
        if a["text"].strip() == b["text"].strip():
            return None               # whitespace only; nothing to report
        found.append(TextChange((a["tag"], attrs_a,
                                 a["text"].strip(), b["text"].strip())))
    return found or None


# ---------------------------------------------------------------- what changed
# `ui_text_change` answers one shape of diff completely. Most diffs are not that
# shape, and for those the review used to say only that nothing was established
# -- true, but it left the reader to read the diff themselves. What is ALWAYS
# available without a run is what the edit did, token for token. Saying "`10`
# became `20`" is not a claim about behaviour; it is the diff restated.
# Multi-character operators are ONE token: `<=` split into `<` and `=` makes
# the reported edit "removed `=`", which tells the reader nothing.
_TOKEN = re.compile(r"\w+|\s+|[<>=!+\-*/%&|^~]+|.")


def _tokens(line: str) -> list[str]:
    return _TOKEN.findall(line)


def one_change(before: str, after: str) -> tuple[str, str] | None:
    """The single edited span between two lines, or None if there are several.

    One span is reportable as "X became Y". Several are not: naming only the
    first would describe the line inaccurately, and listing all of them is the
    diff again.
    """
    import difflib
    # Reordering a list moves the trailing comma with it, so the last entry
    # gains or loses one. That is syntax, not a change, and counting it as a
    # second edited span turns every reorder into an unhelpful "rewritten".
    if before.rstrip().endswith(",") != after.rstrip().endswith(","):
        before, after = before.rstrip().rstrip(","), after.rstrip().rstrip(",")
    a, b = _tokens(before), _tokens(after)
    ops = [op for op in difflib.SequenceMatcher(None, a, b).get_opcodes()
           if op[0] != "equal"]
    if len(ops) != 1:
        return None
    _, i1, i2, j1, j2 = ops[0]
    # An operator on its own is the edit but not the meaning: `<=` -> `<` says
    # nothing until you can see what it compares. Widen to the right until both
    # sides carry an operand, which turns it into "`<= n` became `< n`".
    word = lambda toks: any(t[:1].isalnum() for t in toks)
    for _ in range(6):
        if word(a[i1:i2]) and word(b[j1:j2]):
            break
        if i2 < len(a) and j2 < len(b):
            i2, j2 = i2 + 1, j2 + 1
        elif i1 > 0 and j1 > 0:
            i1, j1 = i1 - 1, j1 - 1
        else:
            break
    old, new = "".join(a[i1:i2]).strip(), "".join(b[j1:j2]).strip()
    return (old, new) if (old or new) and old != new else None


def _clip(line: str, width: int = 72) -> str:
    """Cut on a boundary with an ellipsis, never mid-token."""
    t = line.strip()
    if len(t) <= width:
        return t
    cut = t[:width]
    space = cut.rfind(" ")
    return (cut[:space] if space > width // 2 else cut).rstrip(",([{") + " …"


def _alike(a: str, b: str, floor: float = 0.5) -> bool:
    """Are these two lines plausibly the same line, edited?"""
    import difflib
    return difflib.SequenceMatcher(None, a.strip(), b.strip()).ratio() >= floor


def _pair_run(dels: list, adds: list) -> list[tuple]:
    """Match removed lines to added lines by similarity, not by position.

    `split` pairs a run of changes positionally, which is right for rendering
    two columns and wrong for describing them: two `servers` entries that swap
    order get paired against each other and reported as two rewrites, when the
    truth is that each moved and was edited slightly. Greedy best-match fixes
    that; whatever is left over really was added or removed.
    """
    import difflib

    def contained(x: str, y: str) -> float:
        """How much of the SHORTER line survives in the longer one.

        Not `SequenceMatcher.ratio()`: that is symmetric, so a 90-character
        description replaced by an 890-character one scores 0.18 even though the
        original is kept whole inside the new text, and the pair is missed.
        Measured on the cases that matter, containment separates them where the
        ratio does not -- real pairs at 0.56 / 0.83 / 0.98 / 1.00 against 0.33
        for a line with no partner at all.
        """
        sm = difflib.SequenceMatcher(None, x, y)
        m = sum(block.size for block in sm.get_matching_blocks())
        return m / max(min(len(x), len(y)), 1)

    pairs, left = [], list(adds)
    for d in dels:
        best, score = None, 0.0
        for a in left:
            r = contained(d[1].strip(), a[1].strip())
            if r > score:
                best, score = a, r
        # The floor only has to reject "no plausible partner at all" -- greedy
        # best-match already handles "a better partner exists elsewhere in this
        # run" (the wrong `servers` entry scores 0.75 and still loses to 0.98).
        # Failing to pair costs a compact sentence; wrongly pairing invents an
        # "X became Y" that never happened, so the floor errs high.
        if best is not None and score >= 0.45:
            left.remove(best)
            pairs.append((d, best))
        else:
            pairs.append((d, None))
    return pairs + [(None, a) for a in left]


def describe(diff: str, limit: int = 6) -> list[str]:
    """Plain statements of what the diff did. Never about what it caused.

    Every line here is checkable by looking at the diff, which is what makes it
    safe to print next to a measurement that established nothing.
    """
    out: list[str] = []
    dels: list = []
    adds: list = []

    def flush() -> None:
        """Emit one run, in the order the lines appear in the NEW file.

        Matching by similarity can reorder the pairs relative to the diff -- two
        entries that swapped places come out back to front -- so the run is
        sorted before it is emitted.
        """
        nonlocal dels, adds
        run = sorted(_pair_run(dels, adds),
                     key=lambda pr: ((pr[1] or pr[0])[0] or 0))
        for left, right in run:
            if left and right:
                got = one_change(left[1], right[1])
                if got:
                    old, new = got
                    o, n = _clip(old, 56), _clip(new, 56)
                    # Cite the NEW file's line: that is the file the reader
                    # has open. Using the old number for edits and the new one
                    # for additions made two different changes both say "line 6".
                    at = right[0] or left[0]
                    if not old:
                        out.append(f"line {at}: added `{n}`")
                    elif not new:
                        out.append(f"line {at}: removed `{o}`")
                    elif len(new) > 200 and len(new) > 4 * max(len(old), 1):
                        out.append(f"line {at}: `{o}` became a much longer "
                                   f"value ({len(new)} characters)")
                    else:
                        out.append(f"line {at}: `{o}` became `{n}`")
                else:
                    out.append(f"line {right[0] or left[0]}: rewritten")
            elif right:
                out.append(f"line {right[0]}: added `{_clip(right[1])}`")
            elif left:
                out.append(f"line {left[0]}: removed `{_clip(left[1])}`")
        dels, adds = [], []

    for left, right in split(diff):
        if left and left[2] == "hunk":
            flush()
            continue
        if left and right and left[2] == "ctx":
            flush()
            continue
        if left and left[1].strip():
            dels.append(left)
        if right and right[1].strip():
            adds.append(right)
    flush()

    out = _group(out)
    wider = broadened(diff)
    if wider:
        name, sentence = wider
        out = [l for l in out
               if f"const {name} " not in l and f"became `{name}`" not in l]
        out.insert(0, sentence)
    if len(out) > limit:
        out = out[:limit] + ["…"]
    return out


# --------------------------------------------------------------- summarising
# Six added <option> lines are one fact, not six, and spending the budget on
# them pushed the line that mattered past the cut. Anything that repeats a shape
# is collapsed; the value is that what is left is the part that does not repeat.
_ADDED_EL = re.compile(r"^line (\d+): added `<(?P<tag>[A-Za-z][\w.\-]*)"
                       r"(?P<attrs>[^<>]*?)>(?P<text>[^<>{}]*)</(?P=tag)>`$")
# `x === "LIT"` replaced by a name that an added line defines as membership of a
# list. The branch then runs for every entry in that list, which is the point of
# the edit and the thing a reviewer needs told.
_INCLUDES = re.compile(r"const\s+(?P<name>\w+)\s*=\s*\[(?P<items>[^\]]*)\]"
                       r"\s*\.includes\(\s*(?P<subject>[\w.]+)\s*\)")
_EQ = re.compile(r"^(?P<subject>[\w.]+)\s*===?\s*(?P<lit>[\"'][^\"']*[\"'])$")


def _group(lines: list[str]) -> list[str]:
    """Collapse consecutive added elements of the same tag into one line."""
    out: list[str] = []
    run: list[tuple[str, str]] = []
    tag = None

    def flush() -> None:
        nonlocal run, tag
        if not run:
            return
        if len(run) == 1:
            out.append(f"added `<{tag}>` {run[0][1]}")
        else:
            shown = ", ".join(t for _v, t in run[:8])
            out.append(f"added {len(run)} `<{tag}>` entries: {shown}")
        run, tag = [], None

    for line in lines:
        m = _ADDED_EL.match(line)
        if m and (tag is None or m["tag"] == tag):
            tag = m["tag"]
            run.append((m["attrs"], m["text"].strip()))
            continue
        flush()
        if m:
            tag = m["tag"]
            run = [(m["attrs"], m["text"].strip())]
            continue
        out.append(line)
    flush()
    return out


def broadened(diff: str) -> tuple[str, str] | None:
    """A one-value test replaced by membership of a list the diff also adds.

    Both halves have to be present in this diff, or nothing is claimed: the
    definition, and the exact substitution that uses it.
    """
    defined: dict[str, tuple[str, str]] = {}
    for left, right in split(diff):
        if right and not left:
            m = _INCLUDES.search(right[1])
            if m:
                items = [i.strip().strip("\"'") for i in m["items"].split(",")
                         if i.strip()]
                defined[m["name"]] = (m["subject"], items)
    for left, right in split(diff):
        if not (left and right) or left[2] != "del":
            continue
        got = one_change(left[1], right[1])
        if not got:
            continue
        old, new = got
        if new not in defined:
            continue
        eq = _EQ.match(old.strip())
        subject, items = defined[new]
        if not eq or eq["subject"] != subject:
            continue
        was = eq["lit"].strip("\"'")
        added = [i for i in items if i != was]
        if not added:
            continue
        return (new, f"the `{old}` test became `{new}`, which is true for "
                     f"{', '.join(f'`{i}`' for i in items)} — so that branch "
                     f"now also runs for {', '.join(f'`{i}`' for i in added)}")
    return None
