"""Localization and edit-polarity checks on the saved BugsInPy arm outputs.

`grounded` asks whether an explanation reports the measured failure. These two
checks ask about the other half of the sentence, the edit:

  localized   names an identifier on a line the fix changed, or the function
              or class that encloses a changed line
  reversed    says it added X where the fix only removed X, or says it removed
              X where the fix only added X

CPU only: reads the saved explanations and BugsInPy's own fix patches, and
validates both checks against the blind human grade of 50 rows.

    python bench/bugsinpy_localization.py
"""
from __future__ import annotations

import builtins
import csv
import json
import keyword
import pathlib
import re
from collections import Counter
from math import comb

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATCHES = ROOT / "data/bugsinpy/BugsInPy/projects"
ARMS = {
    "3B tuned + execution": "bip_arm_v3plain_fix_v2.json",
    "3B tuned + execution, seed 7": "bip_arm_v3seed7_fix_v2.json",
    "3B tuned + execution, guarded": "bip_guarded_v3_fix_v2.json",
    "3B untuned + execution": "bip_arm_base_fix_v2.json",
    "3B tuned + risk score": "bip_arm_score_fix_v2.json",
    "3B tuned + diff only": "bip_arm_diff_fix_v2.json",
    "120B + execution": "bip120b_arm_exec_v2.json",
    "120B + risk score": "bip120b_arm_score_v2.json",
    "120B + diff only": "bip120b_arm_diff_v2.json",
}
REFERENCE = "3B tuned + execution"

IDENT = re.compile(r"[A-Za-z_]\w*")
STRING = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'")
DEF = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)")
# Builtins and keywords say little about WHERE a fix is; a short name matches
# too much prose. Both are dropped, which makes `localized` conservative.
COMMON = set(keyword.kwlist) | set(dir(builtins)) | {"self", "cls", "args", "kwargs"}
ADD = r"(?:add(?:s|ed|ing)?|introduc(?:e|es|ed|ing)|insert(?:s|ed|ing)?)"
REM = r"(?:remov(?:e|es|ed|ing)|delet(?:e|es|ed|ing)|drop(?:s|ped|ping)?)"
# active: "removes the `X` check";  passive: "the `X` argument was added"
ACTIVE = re.compile(rf"\b({ADD}|{REM})\b[^.;:`]{{0,40}}?`([^`]+)`", re.I)
PASSIVE = re.compile(rf"`([^`]+)`(?:\s+\w+){{0,3}}\s+(?:was|were|is|are|has been|have been|being)\s+({ADD}|{REM})\b", re.I)


def idents(code: str) -> list[str]:
    code = STRING.sub(" ", code.split("#", 1)[0])
    return [t for t in IDENT.findall(code) if len(t) >= 3 and t not in COMMON]


def parse_patch(text: str) -> tuple[Counter, Counter, set]:
    """Identifiers on added and removed lines, and the def/class around each."""
    added, removed, around, current = Counter(), Counter(), set(), None
    for line in text.splitlines():
        if line.startswith(("diff ", "index ", "--- ", "+++ ")):
            current = None
            continue
        if line.startswith("@@"):
            m = DEF.match(line.split("@@")[-1])
            current = m.group(1) if m else None
            continue
        m = DEF.match(line[1:])
        if m:
            current = m.group(1)
        if line.startswith("+"):
            added.update(idents(line[1:]))
        elif line.startswith("-"):
            removed.update(idents(line[1:]))
        else:
            continue
        if current:
            around.add(current)
    return added, removed, around


def code_names(expl: str) -> set[str]:
    """Names the sentence writes as code: inside backticks, or shaped like an
    identifier (snake_case, camelCase). Plain words such as 'start' or 'value'
    are also identifiers in half these patches and must not count."""
    inside = {t for span in re.findall(r"`([^`]+)`", expl) for t in IDENT.findall(span)}
    bare = {t for t in IDENT.findall(re.sub(r"`[^`]*`", " ", expl))
            if "_" in t.strip("_") or re.search(r"[a-z][A-Z]", t)}
    return inside | bare


def localized(expl: str, added: Counter, removed: Counter, around: set) -> bool:
    return bool(code_names(expl) & (set(added) | set(removed) | around))


def reversed_edit(expl: str, added: Counter, removed: Counter) -> bool:
    claims = [(v, s) for v, s in ACTIVE.findall(expl)] + \
             [(v, s) for s, v in PASSIVE.findall(expl)]
    for verb, span in claims:
        says_added = re.fullmatch(ADD, verb, re.I) is not None
        for name in idents(span):
            if says_added and removed[name] and not added[name]:
                return True
            if not says_added and added[name] and not removed[name]:
                return True
    return False


def mcnemar(b: int, c: int) -> float:
    n, k = b + c, min(b, c)
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def kappa(a: list[bool], b: list[bool]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def selfcheck() -> None:
    patch = ("@@ -1,3 +1,3 @@ def tenumerate(iterable, start=0):\n"
             "-    return enumerate(tqdm_class(iterable, start))\n"
             "+    return enumerate(tqdm_class(iterable), start)\n"
             "@@ -9,2 +9,3 @@ class Status:\n"
             "     states = (DONE,\n"
             "+              UNKNOWN,\n")
    a, r, f = parse_patch(patch)
    assert f == {"tenumerate", "Status"} and a["UNKNOWN"] == 1 and not r["UNKNOWN"]
    assert localized("fixes `tenumerate`", a, r, f)
    assert not localized("the start value", a, r, set())
    assert localized("passes `start` to enumerate", a, r, set())
    assert localized("the tqdm_class call", a, r, set())
    assert reversed_edit("It removes the `UNKNOWN` status check.", a, r)
    assert reversed_edit("The `UNKNOWN` state was removed from the tuple.", a, r)
    assert not reversed_edit("It adds `UNKNOWN` to the states.", a, r)
    assert not reversed_edit("It moves `start` out of the call.", a, r)


def main() -> None:
    selfcheck()
    rows = {json.loads(l)["id"]: json.loads(l) for l in open(ROOT / "data/bugsinpy_rows_v2.jsonl")}
    patch = {}
    for bid in rows:
        project, n = bid.rsplit("-", 1)
        patch[bid] = parse_patch((PATCHES / project / "bugs" / n / "bug_patch.txt").read_text(errors="replace"))

    res = {}
    for label, f in ARMS.items():
        d = json.loads((ROOT / "data" / f).read_text())
        res[label] = {r["id"]: (localized(r["explanation"] or "", *patch[r["id"]]),
                                reversed_edit(r["explanation"] or "", *patch[r["id"]][:2]))
                      for r in d["rows"]}
        assert len(res[label]) == 458, (label, len(res[label]))

    ref = res[REFERENCE]
    print(f"{'arm':32s} {'localized':>14s} {'p vs ref':>9s} {'reversed':>12s} {'p vs ref':>9s}")
    out = {}
    for label, r in res.items():
        loc = sum(v[0] for v in r.values())
        rev = sum(v[1] for v in r.values())
        pl = mcnemar(sum(ref[i][0] and not r[i][0] for i in r), sum(r[i][0] and not ref[i][0] for i in r))
        pr = mcnemar(sum(ref[i][1] and not r[i][1] for i in r), sum(r[i][1] and not ref[i][1] for i in r))
        out[label] = {"localized": loc, "reversed": rev, "p_localized": pl, "p_reversed": pr}
        print(f"{label:32s} {loc:4d} ({loc / 4.58:3.0f}%) {pl:9.2g} {rev:4d} ({rev / 4.58:3.0f}%) {pr:9.2g}")

    # validation against the 50 blind human grades of the reference arm
    human = {r["id"]: r for r in csv.DictReader(open(ROOT / "data/bip_rater_v3_author.csv"))}
    ids = [i for i in human if human[i]["edit_ok"] in ("y", "n")]
    auto = [ref[i][0] for i in ids]
    hum = [human[i]["edit_ok"] == "y" for i in ids]
    print(f"\nvalidation, {len(ids)} rows: localized {sum(auto)}, human edit_ok {sum(hum)}, "
          f"agree {sum(a == h for a, h in zip(auto, hum))}, kappa {kappa(auto, hum):+.2f}")
    print("  localized but human edit_ok=n:", sum(a and not h for a, h in zip(auto, hum)))
    ids = [i for i in human if human[i]["direction"] in ("y", "n")]
    auto = [ref[i][1] for i in ids]
    hum = [human[i]["direction"] == "n" for i in ids]
    tp = [i for i in ids if ref[i][1] and human[i]["direction"] == "n"]
    fp = [i for i in ids if ref[i][1] and human[i]["direction"] == "y"]
    print(f"  reversed: auto {sum(auto)}, human {sum(hum)}, both {len(tp)} {tp}, auto only {fp}, "
          f"kappa {kappa(auto, hum):+.2f}")
    (ROOT / "data/bip_localization_v2.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
