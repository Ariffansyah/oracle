"""Build the combined SFT corpus: word-diffs, mechanism cases, clean direction.

`data/sft_mechanism_v1.jsonl` was assembled by hand and had no builder, so the
26 Aug result rested on a file nothing in the repo could regenerate. This script
is that builder, and it fixes three things measured after that run:

1. **Word-diff rendering.** Six of `mechanism-v1`'s seven false alarms make one
   identical false claim - that a call was *removed* - when the diff shows it
   edited in place. A unified diff genuinely does render an in-place edit as
   remove+add, so the model was describing its input. Switching the rendering at
   inference was measured and lost (41/46 -> 36/46) because the model had never
   seen the notation; the fix is to train on it.

2. **The clean direction.** Every one of the 27 mechanism cases is `buggy: true`.
   Recall went to 33/33 and precision to 6/13, which is what a one-directional
   corpus predicts. `bench/clean_direction` supplies the same constructs as
   fixes and as behaviour-preserving refactors.

3. **The sequence budget, which is the big one.** `MAX_SEQ_LENGTH` is 1024 and
   TRL truncates `keep_start`, so a record whose *prompt* alone exceeds 1024
   loses its whole assistant turn and TRL drops it as fully masked. Measured on
   `sft_mechanism_v1`: 858 of 1748 records (49%) never contributed a gradient,
   which the run's own step count confirms - 224 steps x 8 accum / 2 epochs =
   896 records, not 1748. This builder measures every record against the real
   tokenizer and shrinks the diff until the answer fits, so the corpus that is
   written is the corpus that trains.

    python -m dataset_builder.build_mechanism_corpus \\
        --tokenizer artifacts/base-3b --out data/sft_mechanism_v2.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zlib
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import OUTPUT_CONTRACT
from dataset_builder.schema import (SYSTEM_PROMPT, Analysis, Effect, Finding,
                                    build_user_message)
from dataset_builder.worddiff import to_word_diff

ROOT = Path(__file__).resolve().parent.parent
LANGS8 = ["go", "javascript", "php", "java", "rust", "python", "typescript", "ruby"]


# --------------------------------------------------------------------------
# rendering


def case_diff(d: Path, cid: str, ext: str) -> str:
    """A case directory rendered the way the benchmark renders it."""
    p = subprocess.run(
        ["git", "diff", "--no-index", "--no-color", "--src-prefix=a/",
         "--dst-prefix=b/", str(d / f"pre.{ext}"), str(d / f"post.{ext}")],
        capture_output=True, text=True)
    name = f"{cid}.{ext}"
    return (p.stdout.replace(str(d / f"pre.{ext}"), name)
                    .replace(str(d / f"post.{ext}"), name))


# Matches the per-execution temp directory `bench.basic_bench._run` creates.
# Kept identical to `basic_bench._TMPDIR` on purpose: the corpus and the scorer
# must strip the same token, or a target and its grading disagree.
_TMPDIR = re.compile(r"/tmp/tmp[A-Za-z0-9_]+/")


def executed_effect(root: Path, m: dict) -> Effect | None:
    """Build the `effect` field by RUNNING the case, never by describing it.

    This is the whole point of the v2 contract. The v1 fix template said "the
    program's output changes from {was} to {now}" and filled it from the note,
    which taught the model the *form* of citing executed output without teaching
    that the citation must be real - and it went on to invent panic traces and
    absolute paths for files that do not exist (RESULTS.md, 27 Aug).

    Here `before` and `after` are the actual bytes the two versions printed, so
    every target's behavioural claim is true by construction.

    Returns None under the v1 contract, which keeps the old corpus byte-for-byte
    reproducible.
    """
    if OUTPUT_CONTRACT != "v2":
        return None
    import bench.basic_bench as bb  # imported late: only v2 needs a runner
    prev, bb.ROOT = bb.ROOT, root
    try:
        rc_pre, out_pre = bb._run(m, "pre")
        rc_post, out_post = bb._run(m, "post")
    finally:
        bb.ROOT = prev
    label = m.get("label") or ("buggy" if m.get("buggy") else "clean")
    direction = {"buggy": "post-breaks", "fix": "post-fixes"}.get(label, "unchanged")

    def obs(rc: int, out: str) -> str:
        # Strip the per-execution temp directory before it becomes a target.
        # `_run` makes a fresh one each call, so the name is not a function of
        # anything the model can see - it is a token that CANNOT be predicted,
        # only memorised. Left in, it put a random path into 66 of 318 records
        # (21%), drawn from 16 distinct values, and sft-v2-pilot re-emitted one
        # of them - `/tmp/tmpd6rhx_a0/`, present in 6 records - as execution
        # evidence on five different cases in four languages, plus a
        # one-character truncation of a second on two more. 7 of its 9
        # fabricated paths trace back here.
        #
        # The rest of the trace is kept: `main.c:5:14: runtime error: signed
        # integer overflow ...` stays true and stays informative. Only the
        # unpredictable prefix goes.
        # Strip BEFORE truncating: truncating first can cut a path mid-token and
        # leave `/tmp/tmp8bzrai1` from `/tmp/tmp8bzrai1x`, which is precisely the
        # one-character-truncated form the pilot emitted on two cases.
        out = _TMPDIR.sub("", " ".join(out.split()))[:200]
        return out or f"exit status {rc}, no output"

    return Effect(
        # Thin on purpose, and the weakest part of this corpus: every case is a
        # single file with one entry point, so the honest trigger is "run it".
        # Real commits are what make this field carry information; do not invent
        # variety here that the cases do not have.
        trigger=f"running {m['id']}.{m['ext']} as written",
        before=obs(rc_pre, out_pre),
        after=obs(rc_post, out_post),
        direction=direction,
    )


# --------------------------------------------------------------------------
# v3: the suggestion contract
#
# v2 fills `before`/`after` by RUNNING the case, so every target's behavioural
# claim is true by construction. That is right for a corpus and wrong for a
# model: at inference there is no runner, the model cannot know what the code
# prints, and the contract still demands a value. Measured 30 Aug, it gets that
# value right 15-31% of the time while getting the LOCATION right 87-98%.
#
# So v3 keeps `trigger` and `direction` and swaps the value for `check`: the
# test that would settle it, which IS derivable from the diff. Nothing here
# executes anything - if a v3 target ever needs a runner to be written, the
# field has drifted back into asserting output.

# What a reader should actually DO. Keyed on the case, not on its category.
#
# The first version of this was a per-category sentence with a filename slot,
# and the corpus has exactly two categories (82 logic-error, 18 off-by-one), so
# ten dictionary entries collapsed to two sentences and 366 targets carried 100
# distinct `check` strings - each case's six upsampled copies byte-identical.
# 357 of the 366 contained the words "the edit touches". The v4 checkpoints
# pushed that to saturation: "the edit touches" in 100% of outputs, and two
# INDEPENDENTLY TRAINED checkpoints emitting the same `check` byte for byte on
# 30-59% of cases while their summaries matched on none. That contrast is the
# proof it was recited rather than derived.
#
# Worse, the sentence carried almost no information and the metric did not
# notice, because a token dump - "the edit touches `nums`, `min(nums)`" - was
# appended to it, and `_check_useful` grades the field by substring. Removing
# that tail from the stored v4 answers drops `check_useful` on
# bench/mechanism_heldout from 20/21 to 11/21 and on bench/basic from 29/31 to
# 19/31. Half the score was the token list, not the sentence.
#
# So the tail is gone and the sentence is per-case, authored beside the case in
# `meta.json["check"]`:
#
#   probe     the input or call that reaches the defect
#   watch     what moved in the diff, and what to look for - phrased as a
#             question, never as an assertion about what the program prints
#   restored  what the fix puts back; only the 28 cases with a `-fix` child
#
# Nothing here is executed. Every field is derivable from the diff, which is the
# v3 rule: a target the model cannot reproduce from its input teaches it to
# invent. `bench/annotate_checks.py` writes them and is the file to edit.

# Six ways to join a probe to a watch, so a case's six upsampled copies are not
# six byte-identical strings. The CONTENT is the case's own; only the joint
# moves. This is the same reason `_V3_OPENERS` exists.
_V3_CHECK_FORMS = [
    "{probe} — {watch}",
    "{Watch} To see it, {probe}",
    "{probe}: {watch}",
    "{Watch} The way in is to {probe}",
    "{probe}. {Watch}",
    "{Watch} Reproduce it: {probe}",
]


def _cap(s: str) -> str:
    """Capitalise and terminate, so a `watch` can open a sentence."""
    s = s.strip()
    if not s:
        return s
    s = s[0].upper() + s[1:]
    return s if s[-1] in ".?!" else s + "."


def _join(probe: str, watch: str, case_id: str, copy: int) -> str:
    f = _V3_CHECK_FORMS[_variant(case_id, copy, len(_V3_CHECK_FORMS), "check")]
    return f.format(probe=probe.rstrip(" ."), watch=watch.rstrip(" ."),
                    Watch=_cap(watch))


# A refactor extracts a helper; the check that distinguishes it from the buggy
# sibling with the same diff shape is "compare the helper against the code it
# replaced", so the helper has to be named. Reading it off the diff rather than
# hardcoding `passing` means a new extraction case does not need a code change.
def _added_function(diff: str) -> str | None:
    """The name of the first function DEFINED on an added line, or None."""
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        m = re.search(r"\b(?:function|func|def|fn)\s+([A-Za-z_]\w*)\s*\(", line)
        if not m:
            # C / Java / TS declare a return type instead of a keyword.
            m = re.match(r"\+\s*(?:static\s+|public\s+|private\s+|const\s+)*"
                         r"(?:[A-Za-z_][\w<>\[\]*]*\s+\*?)([A-Za-z_]\w*)\s*\([^)]*\)\s*\{",
                         line)
        if m and m.group(1) not in ("if", "for", "while", "switch", "return"):
            return m.group(1)
    return None


# `likely` vs `possible`. The rule is whether the DIFF ALONE settles it. A moved
# comparison operator, a deleted zero-check, a declaration hoisted out of a loop:
# all visible in the hunk. What is NOT visible is anything that depends on how
# the CALLER uses the result - whether it kept a reference to the array you just
# aliased, whether another thread is in the map, whether the object it got back
# is expected to be fresh. Those are leads, not verdicts.
#
# Both labels must appear in useful numbers or the field is dead. A first pass
# keyed on category alone produced 9 `likely` in 366 records: a model trained on
# that never emits `likely`, always hedges, and the calibration check the field
# exists for cannot be read. Worse, maximal hedging is this contract's own
# failure mode - the thing `false_alarm` is there to catch.
_CONTEXT_DEPENDENT = {"api-misuse", "concurrency", "resource-leak", "error-handling"}

# Defect families whose category looks diff-settled but whose effect depends on
# the caller: mutating a collection the caller still holds, or mutating one while
# iterating it. The diff shows the mutation; it cannot show whether it matters.
_CONTEXT_DEPENDENT_IDS = ("-alias-mutate", "-mutate-iterate", "-array-ref-alias",
                          "-list-alias-mutate", "-array-alias-mutate",
                          # Whether an overflow or a truncation happens at all
                          # depends on the VALUES the caller passes: safe_add(1, 1)
                          # never overflows and score_percentage(1, 2) never
                          # truncates. The diff shows the guard gone; it cannot
                          # show that any real call reaches it. That is the same
                          # rule the aliasing families are on, and applying it
                          # consistently is also what moves `confidence` off a
                          # near-constant `likely` - v4 emitted 3 `possible` in
                          # 168 responses, so the field carried no information.
                          "-overflow", "-int-wrap", "-ratio-trunc")


def _confidence(m: dict, direction: str) -> str:
    cat = m.get("category", "other")
    cid = m.get("id", "")
    if direction == "unchanged":
        # An extraction is `possible` on purpose: to believe it you must compare
        # the new helper's body against the code it replaced, and that is exactly
        # the comparison the model skips when it false-alarms on added functions.
        # A rename is `likely` - the diff shows every use moving together.
        return "possible" if not m.get("renamed") else "likely"
    if cat in _CONTEXT_DEPENDENT:
        return "possible"
    if any(k in cid for k in _CONTEXT_DEPENDENT_IDS):
        return "possible"
    return "likely"

# Varied on purpose, indexed by a hash of the case id and the copy number. The
# v3 corpus repeated ONE whole summary 54 times and one sentence 105 times in
# 399 records, and `bench/template_audit.py` then measured the checkpoint
# reciting 30% of its answer prose verbatim against a 0.0% floor. Upsampling a
# byte-identical record is what teaches that. These make the N copies of a case
# differ in wording while making the same claim.
_V3_OPENERS = [
    "This looks like {a} {cat} in {file}.",
    "Possible {cat} in {file}.",
    "Worth a look: {cat} in {file}.",
    "{file} may have picked up {a} {cat} here.",
    "Flagging {a} possible {cat} in {file}.",
    "This reads like {a} {cat} in {file}.",
]

_V3_CLOSERS = [
    "Worth confirming before this lands.",
    "Please check that before merging.",
    "Run that case to be sure.",
    "I would verify that path first.",
    "Confirm it with the test above.",
    "Worth a second pair of eyes on that.",
    "That is the first thing I would run.",
    "Check it against the old behaviour before merging.",
    "I would not land this without trying that case.",
    "Settle it with that test rather than by reading.",
    "One run of that case should tell you.",
    "Worth ruling out before this goes in.",
]

# The clean half, reworded per copy. Under v2 these were ONE sentence each:
# "Every use is updated in place - ..." landed in 78 of 318 records in
# `sft_v2_pilot2` and 105 of 399 in `sft_v3_extract`, the single biggest driver
# of the verbatim recitation `bench/template_audit.py` measured. The claim is
# the same in every variant; only the wording moves.
_V3_RENAME = [
    "This commit renames `{old}` to `{new}` in {file}. Every use is updated in "
    "place, so the program should behave exactly as before.",
    "`{old}` becomes `{new}` in {file}. The declaration and all its readers move "
    "together, which is what makes this behaviour-preserving.",
    "A rename in {file}: `{old}` -> `{new}`, applied at the declaration and at "
    "every use. No call site is left pointing at the old name.",
    "{file} renames `{old}` to `{new}`. Nothing else about the function changes, "
    "so I would expect identical output.",
    "This is a pure rename in {file} — `{old}` to `{new}` — with every reference "
    "updated alongside the declaration.",
    "In {file}, `{old}` is renamed `{new}`. The edit reaches every use, so the "
    "behaviour should be untouched.",
]

_V3_EXTRACT = [
    "This commit pulls the test in {file} out into `{helper}()` and points the "
    "call site at it. The body of `{helper}()` matches what it replaced.",
    "{file} extracts `{helper}()` and rewires the caller to it. Line for line "
    "the helper does what the inline code did.",
    "`{helper}()` is added in {file} and the call site now goes through it. Its "
    "body is the same code that used to be inline.",
    "This is an extraction in {file}: `{helper}()` is new, the call site is "
    "rewired, and the logic inside the helper is unchanged from the original.",
    "{file} moves an inline test into `{helper}()`. Adding a function is not "
    "itself a change in behaviour, and this one preserves the original.",
    "The change in {file} lifts existing code into `{helper}()` without "
    "altering it, and calls the helper where the code used to sit.",
]

# `{restored}` is the parent case's own `check.restored`, cut at its first
# clause: "the `not nums` guard is back before `min(nums)`". Naming the
# construct is the whole point - the earlier version said "repairs the
# {category}", and the corpus has two categories, so 28 fix targets said one of
# two things and none of them said what had been repaired.
_V3_FIX = [
    "This commit repairs {file}: {restored}.",
    "{file} is repaired here — {restored} — and nothing else in the function "
    "moves.",
    "A repair in {file}: {restored}, so the original behaviour comes back.",
    "This undoes the defect in {file}. {Restored}, which is what it should "
    "have been all along.",
    "{Restored} in {file}, putting the function back to its correct form.",
    "{file} restores the correct form of the function: {restored}.",
]

# A `fix` case has `direction: post-fixes` — the program's behaviour DOES
# change, that is what a repair is. Until now fixes and refactors drew from one
# closer list, so 40-odd fix targets in v4 asserted "I do not see a behaviour
# change to chase" directly beneath an effect that says post-fixes. A target
# that contradicts itself teaches the model to do both.
_V3_FIX_CLOSERS = [
    "No new defect that I can see.",
    "This is the repair direction, not a regression.",
    "Nothing else rides along with the fix.",
    "I would let this land.",
    "The repair looks self-contained.",
    "No second change hiding in this hunk.",
    "Nothing further to raise on it.",
    "That is the whole of the change as far as I can see.",
    "I see no new problem introduced alongside it.",
]

_V3_CLEAN_CLOSERS = [
    "Nothing here needs changing as far as I can tell.",
    "I do not see a behaviour change to chase.",
    "Looks safe on the strength of the diff.",
    "No defect that I can see in this one.",
    "This reads as behaviour-preserving.",
    "Nothing to flag on this change.",
    "I would let this one through.",
    "No trigger here that I can point at.",
    "The two versions should agree on every input.",
    "I have nothing to raise on this commit.",
    "As far as the diff goes, this is a no-op.",
    "Clean, on the strength of what is shown here.",
    "I would not hold this up.",
    "No behaviour I can see moving either way.",
    "Nothing in this hunk changes what the program does.",
]

# Assertive -> suggestive. The technical body is left alone on purpose: claims
# about what the DIFF says ("the helper compares with `> 60`") are checkable
# from the text the model was given, and are exactly what it should keep saying.
# What gets softened is the leap from that to a settled verdict.
_V3_SOFTEN = [
    [("This introduces an ", "This looks like an "),
     ("This introduces a ", "This looks like a "),
     ("introducing a ", "which would introduce a "),
     ("introducing an ", "which would introduce an "),
     ("causing ", "which would cause "),
     ("is the whole defect", "looks like the whole defect")],
    [("This introduces an ", "That would be an "),
     ("This introduces a ", "That would be a "),
     # Not "so expect a" as well: the source sentences often carry both
     # "causing ..." and "introducing a ...", and one replacement word for
     # both produced "so expect removal ... to throw, so expect a concurrency
     # defect" in the corpus.
     ("introducing a ", "which would be a "),
     ("introducing an ", "which would be an "),
     ("causing ", "so expect "),
     ("is the whole defect", "is where I would look first")],
    [("This introduces an ", "I read that as an "),
     ("This introduces a ", "I read that as a "),
     ("introducing a ", "which points to a "),
     ("introducing an ", "which points to an "),
     ("causing ", "which should cause "),
     ("is the whole defect", "is the part to check")],
]


def _variant(case_id: str, copy: int, n: int, salt: str = "") -> int:
    """Deterministic per-(case, copy) choice, so the corpus is reproducible.

    A random choice would make two builds of the same corpus differ, and this
    repo grades corpora against each other.

    The copy index ROTATES rather than being hashed in. Hashing `case_id:copy`
    draws each copy independently, so six copies drawing from six templates
    land on about four distinct ones - the birthday problem, and the reason the
    first build of this corpus was 71% distinct on `check` rather than the ~97%
    the template count allows. Rotating guarantees the six copies of a case take
    six different templates, which is what upsampling is supposed to buy.
    `salt` decorrelates one field's choice from another's.
    """
    return (zlib.crc32(f"{case_id}:{salt}".encode()) // 7 + copy) % n


# The opener reads "This looks like {a} {cat} in {file}". `cat` is a schema
# enum, and `cat.replace("-", " ")` turns those into things that are not noun
# phrases: "an input validation", "an api misuse", "off by one". The corpus is
# the only place the model learns how to say this, so it learns to say it
# wrongly. Map each enum to the phrase a reviewer would actually write.
_CAT_PHRASE = {
    "off-by-one":        "off-by-one",
    "logic-error":       "logic error",
    "input-validation":  "missing input check",
    "null-dereference":  "null dereference",
    "concurrency":       "concurrency problem",
    "resource-leak":     "resource leak",
    "api-misuse":        "misuse of the API",
    "error-handling":    "error-handling problem",
    "security":          "security problem",
    "other":             "defect",
}


def _phrase(cat: str) -> str:
    return _CAT_PHRASE.get(cat, cat.replace("-", " "))


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


# The parent mechanism case, loaded once, so a `-fix` or `-rename` case can
# reuse the annotation of the defect it undoes. Every clean case carries
# `parent`, verified: 63 of 63 point at a bench/mechanism_pilot directory.
_PARENTS: dict[str, dict] = {}


def _parent(m: dict) -> dict:
    if not _PARENTS:
        for meta in sorted((ROOT / "bench/mechanism_pilot").glob("*/meta.json")):
            pm = json.loads(meta.read_text())
            _PARENTS[pm["id"]] = pm
    par = _PARENTS.get(m.get("parent", ""))
    if par is None:
        raise SystemExit(
            f"{m['id']}: parent {m.get('parent')!r} is not a mechanism_pilot "
            f"case, so its `check` cannot be derived. Fix `parent` in meta.json "
            f"- do NOT fall back to a generic sentence.")
    return par


def _case_check(m: dict, diff: str, direction: str, copy: int) -> str:
    """The `check` field: a probe and a watch, joined, both case-specific.

    Four kinds of case, and every one of them names its own construct:

      buggy     the case's own `check.probe` / `check.watch`
      fix       the parent's `probe` with the parent's `restored` - the fix
                puts the guard back, so the test is the same and the
                expectation is inverted
      rename    grep for the old name; the rename is complete or it is not
      extract   the same probe as the buggy sibling with the same diff shape,
                and the opposite watch. That pair is the whole reason
                bench/clean_direction exists, so their checks must be the two
                halves of one comparison, not one shared sentence.
    """
    if direction != "unchanged":
        if m.get("buggy"):
            c = m.get("check") or {}
            if not c.get("probe") or not c.get("watch"):
                raise SystemExit(
                    f"{m['id']}: no `check.probe`/`check.watch` in meta.json. "
                    f"Add one in bench/annotate_checks.py - a per-category "
                    f"fallback is what this rewrite exists to delete.")
            return _join(c["probe"], c["watch"], m["id"], copy)
        # label == "fix"
        pc = _parent(m).get("check") or {}
        if not pc.get("probe") or not pc.get("restored"):
            raise SystemExit(
                f"{m['id']}: parent {m['parent']} has no `check.restored`. "
                f"Add one in bench/annotate_checks.py.")
        return _join(pc["probe"], pc["restored"], m["id"], copy)

    if m.get("renamed"):
        old, new = m["renamed"]
        return _join(f"search {m['id']}.{m['ext']} for the old name `{old}`",
                     f"a rename has to move the declaration and every use "
                     f"together, so check that nothing still reads `{old}` and "
                     f"that `{new}` appears everywhere the old name did",
                     m["id"], copy)

    # An extraction. Same probe as the buggy sibling; opposite watch.
    pc = _parent(m).get("check") or {}
    helper = _added_function(diff)
    named = f"the extracted `{helper}()`" if helper else "the extracted helper"
    probe = pc.get("probe") or (f"run {m['id']}.{m['ext']} before and after "
                                f"with the same input")
    return _join(probe,
                 f"compare {named} against the code it replaced — if the body "
                 f"came across unchanged, every input should still take the "
                 f"same branch it did before",
                 m["id"], copy)


def suggested_effect(m: dict, diff: str, copy: int) -> Effect:
    """The v3 `effect`: a trigger, a test to run, a direction and a confidence.

    Nothing is executed. Every field is derivable from the diff and the case
    metadata, which is the whole point - at inference the model has only the
    diff, so a target it cannot reproduce from the diff teaches it to invent.
    """
    label = m.get("label") or ("buggy" if m.get("buggy") else "clean")
    direction = {"buggy": "post-breaks", "fix": "post-fixes"}.get(label, "unchanged")

    return Effect(
        trigger=f"running {m['id']}.{m['ext']} as written",
        check=_case_check(m, diff, direction, copy),
        direction=direction,
        confidence=_confidence(m, direction),
    )


def hedge(text: str, case_id: str, copy: int) -> str:
    """Reword an assertive target as a suggestion, varying with the copy index."""
    for old, rep in _V3_SOFTEN[_variant(case_id, copy, len(_V3_SOFTEN), "soften")]:
        text = text.replace(old, rep)
    return text


def _restored_clause(m: dict) -> str:
    """The first clause of the parent's `check.restored`, for a fix summary.

    "the `not nums` guard is back before `min(nums)`, so check that ..." ->
    "the `not nums` guard is back before `min(nums)`". The rest is the test,
    which belongs in `check` and would only be said twice here.
    """
    r = (_parent(m).get("check") or {}).get("restored")
    if not r:
        raise SystemExit(
            f"{m['id']}: parent {m['parent']} has no `check.restored`, so the "
            f"fix summary cannot name what came back. Add one in "
            f"bench/annotate_checks.py.")
    return r.split(", so check")[0].rstrip(". ")


def v3_analysis(a: Analysis, m: dict, diff: str, copy: int) -> Analysis:
    """Rewrite a v1/v2 target into the suggestion contract."""
    file = f"{m['id']}.{m['ext']}"
    buggy = bool(a.findings)
    label = m.get("label")

    # The opener's category comes from the FINDING, not from `meta.json`. The
    # case files carry only `logic-error` and `off-by-one` (82 and 18 of 100),
    # while the hand-authored findings distinguish input-validation,
    # error-handling, concurrency and api-misuse. v4 was trained on the coarse
    # pair and called an array overrun a "logic error" while its own finding
    # said input-validation - the summary and the finding disagreeing inside one
    # answer. Take the finer word where there is one.
    cat = (a.findings[0].category if buggy and a.findings[0].category
           else m.get("category", "other"))

    # For the clean half the v2 target is a single canned sentence per label, so
    # hedging it would preserve the duplication that is the whole problem.
    # Regenerate it from the variant templates instead.
    if not buggy and label:
        if label == "fix":
            tpl = _V3_FIX[_variant(m["id"], copy, len(_V3_FIX), "body")]
            restored = _restored_clause(m)
            body = tpl.format(file=file, restored=restored,
                              Restored=restored[0].upper() + restored[1:])
        elif m.get("renamed"):
            tpl = _V3_RENAME[_variant(m["id"], copy, len(_V3_RENAME), "body")]
            body = tpl.format(file=file, old=m["renamed"][0], new=m["renamed"][1])
        else:
            tpl = _V3_EXTRACT[_variant(m["id"], copy, len(_V3_EXTRACT), "body")]
            helper = _added_function(diff)
            if not helper:
                raise SystemExit(
                    f"{m['id']}: label=refactor, not a rename, and no function "
                    f"is defined on an added line - so there is no helper to "
                    f"name. Check the diff, do NOT fall back to prose that "
                    f"names nothing.")
            body = tpl.format(file=file, helper=helper)
    else:
        body = hedge(a.summary, m["id"], copy)

    if buggy:
        phrase = _phrase(cat)
        opener = _V3_OPENERS[_variant(m["id"], copy, len(_V3_OPENERS), "open")].format(
            a=_article(phrase), cat=phrase, file=file)
        closer = _V3_CLOSERS[_variant(m["id"], copy, len(_V3_CLOSERS), "close")]
        summary = f"{opener} {body} {closer}"
    else:
        pool = _V3_FIX_CLOSERS if label == "fix" else _V3_CLEAN_CLOSERS
        closer = pool[_variant(m["id"], copy, len(pool), "close")]
        summary = f"{body} {closer}"

    findings = [Finding(category=f.category,
                        explanation=hedge(f.explanation, m["id"], copy),
                        file=f.file)
                for f in a.findings]
    return Analysis(effect=suggested_effect(m, diff, copy),
                    summary=summary, findings=findings)


def copies(diff: str, a: Analysis, m: dict, times: int, word: bool) -> list[dict]:
    """The `times` upsampled copies of one case.

    Under v1/v2 they are byte-identical, which is what upsampling has always
    meant here. Under v3 each copy is reworded by `v3_analysis`, because
    identical copies are the mechanism behind the memorisation measured on
    30 Aug: `data/sft_v3_extract.jsonl` carried one summary 54 times and one
    sentence 105 times in 399 records, and the checkpoints trained on it recite
    30% of their answer prose verbatim against a 0.0% floor.
    """
    subject, files = f"({m['id']})", f"{m['id']}.{m['ext']}"
    if OUTPUT_CONTRACT == "v3":
        return [record(diff, v3_analysis(a, m, diff, i), subject, files, word)
                for i in range(times)]
    return [record(diff, a, subject, files, word)] * times


def record(diff: str, analysis: Analysis, subject: str, files: str,
           word: bool) -> dict:
    return {"messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(
            to_word_diff(diff) if word else diff, subject, files,
            include_schema=False)},
        {"role": "assistant", "content": analysis.to_json()},
    ]}


# --------------------------------------------------------------------------
# sources


def bulk(path: Path, word: bool) -> list[dict]:
    """The 8-language teacher-labelled corpus, re-rendered.

    Reproduces `data/sft_multilang8.jsonl` when `word` is off: same source, same
    language filter, same 1667 records.
    """
    out = []
    for line in open(path):
        if not line.strip():
            continue
        r = json.loads(line)
        if not r.get("diff") or r.get("language") not in LANGS8:
            continue
        analysis = (Analysis.model_validate(r["analysis"]) if r.get("analysis")
                    else Analysis(summary="This change is behaviour-preserving; "
                                          "no defect found."))
        out.append(record(r["diff"], analysis, r.get("subject", ""),
                          ", ".join(r.get("files", [])), word))
    return out


def mechanism(word: bool, times: int) -> list[dict]:
    """The hand-authored mechanism cases, from files this repo can regenerate.

    The assistant turns live beside each case as `analysis.json`; before this
    they existed only inside an unreproducible JSONL.
    """
    cases = []
    for meta in sorted((ROOT / "bench/mechanism_pilot").glob("*/meta.json")):
        m = json.loads(meta.read_text())
        ap = meta.parent / "analysis.json"
        if not ap.exists():
            print(f"  !! {m['id']} has no analysis.json — skipped")
            continue
        a = Analysis.model_validate(json.loads(ap.read_text()))
        # `dataset_builder.worddiff` renders the header as `ac-foo.c bc-foo.c`
        # (it drops the slash from `a/` and `b/`), and five hand-authored targets
        # had copied the `b`-prefixed form out of it - `bpy-min-empty-guard.py`
        # for a case whose file is `py-min-empty-guard.py`. The name IS in the
        # prompt, so the ghost-file check cannot see it; only the case knows its
        # own filename. Correct it here so a future edit cannot reintroduce it.
        want = f"{m['id']}.{m['ext']}"
        for fi in a.findings:
            if fi.file and fi.file != want:
                print(f"  !! {m['id']}: finding names {fi.file!r}, not {want!r} "
                      f"— corrected")
                fi.file = want
        cases.append((m, meta, a))

    # Nine `*-extract-boundary` cases share ONE hand-authored summary: they are
    # the same program in nine languages, with the same `passing()`/`grade()`
    # identifiers and the same `> 60`, so the prose is correct for all of them -
    # it is just the same prose nine times. At x6 that is 54 byte-identical
    # targets, 14% of `sft_v3_extract`, and it is the text `sft-v3-extract-seed7`
    # recited on a held-out case that has no such comparison.
    #
    # Upsampling exists to weight a case. A family of k cases sharing one target
    # is ALREADY weighted k times, so multiply by times/k rather than by times.
    # Nine cases that would have contributed 54 identical records contribute 9.
    shared = Counter(a.summary for _, _, a in cases)
    out = []
    for m, meta, a in cases:
        k = shared[a.summary]
        n = max(1, times // k)
        if k > 1 and n < times:
            print(f"  .. {m['id']}: summary shared with {k - 1} other case(s), "
                  f"x{times} -> x{n}")
        a.effect = executed_effect(ROOT / "bench/mechanism_pilot", m)
        d = case_diff(meta.parent, m["id"], m["ext"])
        out += copies(d, a, m, n, word)
    return out


# --------------------------------------------------------------------------
# corpus pre-flight for the v3 `check` field


_PARTNER = {")": "(", "}": "{", "]": "["}


def unbalanced_spans(text: str) -> list[str]:
    """Backticked spans in a target whose brackets do not balance.

    The v4 corpus built its `check` field by splitting the word-diff on
    whitespace and calling `tok.strip("(){}[];,:")`. `str.strip` works on both
    ends, so `len(xs)` lost its closing bracket and became `len(xs`, and
    `.split()` cut `Math.addExact(a, b)` into `Math.addExact(a,`. 207 of 366
    targets (56%) named an identifier that does not exist, and both v4
    checkpoints reproduced it verbatim - `` `len(xs` ``, `` `total(xs` ``,
    `` `print(s` ``.

    The token list that caused it is gone; this replaces the fix with a check
    over the WHOLE target, which is strictly wider than the old one - it would
    also catch a hand-authored `check.watch` with a typo'd bracket.
    """
    bad = []
    for span in re.findall(r"`([^`\n]+)`", text):
        stack = []
        for ch in span:
            if ch in "({[":
                stack.append(ch)
            elif ch in ")}]":
                if not stack or stack[-1] != _PARTNER[ch]:
                    bad.append(span)
                    break
                stack.pop()
        else:
            if stack:
                bad.append(span)
    return bad


def clean_direction(word: bool, times: int) -> list[dict]:
    """Fixes and refactors of the same constructs the mechanism cases teach.

    Every summary names `{id}.{ext}`, which is the filename `case_diff` puts in
    the diff header. It used to name `{parent}.{ext}` - `c-extract-boundary.c`
    for a diff whose header says `c-extract-boundary-refactor.c` - so all 54
    clean targets cited a file the model was never shown. That is the same
    fabrication-teaching pattern as the per-execution temp dir stripped on
    29 Aug: a token that cannot be derived from the input, only memorised.

    The summaries are composed from each case's own executed before/after output
    so no two targets are byte-identical: half the `sft-cve` corpus shared one assistant
    turn, the model memorised it, and ten GPU hours produced one output for
    every input. `distinct_targets()` exists because of that run.
    """
    out = []
    for meta in sorted((ROOT / "bench/clean_direction").glob("*/meta.json")):
        m = json.loads(meta.read_text())
        d = case_diff(meta.parent, m["id"], m["ext"])
        eff = executed_effect(ROOT / "bench/clean_direction", m)
        # The 9 `*-extract-boundary-refactor` cases EXTRACT a function; they
        # rename nothing, and carry no `renamed` key. Until 30 Aug they fell
        # through to the rename branch below and took its placeholder default,
        # putting "This commit renames `a local` to `a new name`" into 27
        # records as the target for a diff that adds a helper. That is the
        # sentence `sft-v3-extract` then emitted on all five held-out extract
        # cases, none of which is a rename. It was read as the model reciting a
        # template; it was the model correctly reproducing a target that was
        # wrong. Route extractions to their own branch.
        if m["label"] == "refactor" and not m.get("renamed"):
            summary = (
                f"This commit extracts part of {m['id']}.{m['ext']} into a "
                f"new helper and rewires the call site to it. The extracted "
                f"code is identical to what it replaced, so the program's "
                f"behaviour is unchanged.")
        elif m["label"] == "fix":
            if OUTPUT_CONTRACT != "v1":
                # v2: the observable output lives in `effect`, where it is real
                # and gradable. Keeping it in the prose as well is what taught
                # the model to quote output it never ran.
                summary = (
                    f"This commit repairs the {m['category']} in "
                    f"{m['id']}.{m['ext']}: the function goes back to its "
                    f"correct form, and introduces no new defect.")
            else:
                # The note carries the executed before/after output, so the
                # summary states a behaviour change that was actually observed
                # rather than one inferred from reading the diff.
                was, _, now = m["note"].partition(": ")[2].partition(" -> ")
                summary = (
                    f"This commit repairs the {m['category']} in "
                    f"{m['id']}.{m['ext']}: the function goes back to its "
                    f"correct form, and the program's output changes from {was} "
                    f"to {now}. The change removes a defect and introduces none.")
        else:
            # No placeholder default: a missing `renamed` is a corpus bug, not
            # something to paper over with prose that is false. See above.
            if not m.get("renamed"):
                raise SystemExit(
                    f"{m['id']}: label=refactor with no `renamed` and not an "
                    f"extraction. Add `renamed`, or give it its own branch - "
                    f"do NOT let it fall through to invented names.")
            old_name, new_name = m["renamed"]
            tail = ("the program's behaviour is unchanged."
                    if OUTPUT_CONTRACT != "v1"
                    else "the program's output is unchanged at "
                         f"{m['note'].rsplit('stays ', 1)[-1]}.")
            summary = (
                f"This commit renames `{old_name}` to `{new_name}` in "
                f"{m['id']}.{m['ext']}. Every use is updated in place — the "
                f"declaration and its readers are edited, not deleted — and "
                f"{tail}")
        out += copies(d, Analysis(effect=eff, summary=summary, findings=[]),
                      m, times, word)
    return out


# --------------------------------------------------------------------------
# fitting the sequence budget


class Fitter:
    """Shrink a record's diff until prompt+answer fit `max_len` tokens."""

    MARK = "\n... [diff truncated] ...\n"

    def __init__(self, tokenizer, max_len: int):
        self.tok, self.max_len = tokenizer, max_len
        self.shrunk = self.dropped = 0

    def _len(self, messages: list[dict]) -> int:
        text = self.tok.apply_chat_template(messages, tokenize=False)
        return len(self.tok(text, add_special_tokens=False)["input_ids"])

    def _split(self, user: str) -> tuple[str, str, str]:
        head, _, rest = user.partition("```diff\n")
        body, sep, tail = rest.rpartition("\n```")
        return head + "```diff\n", body, sep + tail

    def fit(self, rec: dict) -> dict | None:
        if self._len(rec["messages"]) <= self.max_len:
            return rec
        head, body, tail = self._split(rec["messages"][1]["content"])
        if not body:
            self.dropped += 1
            return None
        lo, hi, best = 0, len(body), None
        while lo <= hi:                       # largest diff that still fits
            mid = (lo + hi) // 2
            trial = dict(rec)
            trial["messages"] = list(rec["messages"])
            trial["messages"][1] = dict(rec["messages"][1])
            trial["messages"][1]["content"] = head + body[:mid] + self.MARK + tail
            if self._len(trial["messages"]) <= self.max_len:
                best, lo = trial, mid + 1
            else:
                hi = mid - 1
        if best is None:
            self.dropped += 1
            return None
        self.shrunk += 1
        return best


def preflight_v3(rows: list[dict]) -> None:
    """Report the three things the v4 corpus got wrong, before it is written.

    The v4 run was launched, and only afterwards did the audit show the `check`
    field was a per-category sentence in 357 of 366 targets and named a
    non-existent identifier in 207. Both were visible in the corpus. Print them
    at build time so a run is never launched on a corpus nobody read.
    """
    checks, targets = [], []
    for r in rows:
        a = json.loads(r["messages"][-1]["content"])
        targets.append(r["messages"][-1]["content"])
        if isinstance(a.get("effect"), dict) and a["effect"].get("check"):
            checks.append(a["effect"]["check"])

    print("\n  v3 pre-flight")
    n = len(checks)
    if n:
        d = len(set(checks))
        print(f"    check: {d} distinct of {n} ({100 * d / n:.0f}%)")
        # The share of a case's own copies that are byte-identical is the number
        # that matters: upsampling a byte-identical record is what teaches
        # recitation. Under v4 it was 100%.
        worst = Counter(checks).most_common(1)[0]
        print(f"    check: most repeated x{worst[1]} — {worst[0][:70]}...")
        if d < n * 0.8:
            print(f"    !!! under 80% distinct. Each case's copies should differ.")

    bad = Counter()
    for t in targets:
        for span in unbalanced_spans(t):
            bad[span] += 1
    if bad:
        print(f"    !!! {sum(bad.values())} unbalanced backticked spans, "
              f"{len(bad)} distinct: {list(bad)[:5]}")
        print(f"        These name identifiers that do not exist. This is the "
              f"v4 defect; do not train on it.")
    else:
        print(f"    identifiers: 0 unbalanced backticked spans in "
              f"{len(targets)} targets")

    # `check_useful` grades the check against the case's own `must_mention`.
    # If the corpus's own targets do not satisfy it, the field is not teaching
    # what the metric reads, and the metric will measure nothing.
    try:
        sys.path.insert(0, str(ROOT))
        from bench.basic_bench import _check_useful
    except Exception:
        return
    cases = {}
    for d in ("bench/mechanism_pilot", "bench/clean_direction"):
        for meta in (ROOT / d).glob("*/meta.json"):
            m = json.loads(meta.read_text())
            cases[f"{m['id']}.{m['ext']}"] = m
    hit = tot = 0
    misses = []
    for r, chk in zip([r for r in rows
                       if json.loads(r["messages"][-1]["content"])
                            .get("effect", {}).get("check")], checks):
        a = json.loads(r["messages"][-1]["content"])
        f = (a["findings"][0].get("file") if a.get("findings") else None)
        c = cases.get(f or "")
        if not c or not c.get("buggy"):
            continue
        tot += 1
        if _check_useful(c, chk):
            hit += 1
        elif c["id"] not in misses:
            misses.append(c["id"])
    if tot:
        print(f"    check_useful on the corpus's OWN targets: {hit}/{tot} "
              f"({100 * hit / tot:.0f}%)")
        if misses:
            print(f"        misses: {sorted(misses)}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labelled", type=Path, default=ROOT / "data/labelled_all.jsonl")
    ap.add_argument("--out", type=Path, default=ROOT / "data/sft_mechanism_v2.jsonl")
    ap.add_argument("--tokenizer", help="model dir whose tokenizer sets the budget")
    ap.add_argument("--max-seq-length", type=int, default=1024)
    ap.add_argument("--mechanism-times", type=int, default=6,
                    help="upsample factor for the 28 mechanism cases")
    ap.add_argument("--clean-times", type=int, default=3,
                    help="upsample factor for the 54 clean-direction cases")
    ap.add_argument("--no-bulk", action="store_true",
                    help="executable cases only. Under the v2 contract the 1673 "
                         "teacher-labelled commits carry no pre/post to run, so "
                         "they cannot get a true `effect`; this builds the "
                         "pilot corpus in which every effect is executed.")
    ap.add_argument("--unified", action="store_true",
                    help="keep unified diffs (the v1 rendering) instead of word-diffs")
    args = ap.parse_args(argv)

    word = not args.unified
    parts = {
        f"mechanism x{args.mechanism_times}": mechanism(word, args.mechanism_times),
        f"clean-direction x{args.clean_times}": clean_direction(word, args.clean_times),
    }
    if not args.no_bulk:
        parts["bulk (8 langs, teacher-labelled)"] = bulk(args.labelled, word)
    elif OUTPUT_CONTRACT == "v1":
        print("  !! --no-bulk under the v1 contract drops 1673 records and buys "
              "nothing; it exists for v2/v3, where they cannot carry an effect.")

    # Under v2 every record must carry the field or the model learns it is
    # optional and stops emitting it. Say so loudly rather than shipping a
    # corpus that quietly teaches the opposite of what the contract intends.
    if OUTPUT_CONTRACT in ("v2", "v3"):
        missing = {name: sum(1 for r in group
                             if "effect" not in json.loads(r["messages"][-1]["content"]))
                   for name, group in parts.items()}
        bad = {k: v for k, v in missing.items() if v}
        if bad:
            print(f"\n  !! {OUTPUT_CONTRACT} contract, but these records "
                  f"carry NO `effect`:")
            for k, v in bad.items():
                print(f"       {k}: {v}")
            print("     A mixed corpus teaches the field is optional. Use "
                  "--no-bulk for the executable-only pilot, or give the bulk "
                  "records an effect first.")
    rows = [r for group in parts.values() for r in group]
    for name, group in parts.items():
        print(f"  {name}: {len(group)}")

    if args.tokenizer:
        from transformers import AutoTokenizer
        fitter = Fitter(AutoTokenizer.from_pretrained(args.tokenizer),
                        args.max_seq_length)
        fitted = [f for f in (fitter.fit(r) for r in rows) if f]
        print(f"\nsequence budget ({args.max_seq_length} tokens): "
              f"{len(rows) - fitter.shrunk - fitter.dropped} fit as written, "
              f"{fitter.shrunk} had the diff shrunk, {fitter.dropped} dropped")
        rows = fitted
    else:
        print("\n!! no --tokenizer: sequence budget NOT enforced. TRL truncates "
              "keep_start and drops fully-masked records, so an unfitted corpus "
              "trains on an unknown subset of itself.")

    if OUTPUT_CONTRACT == "v3":
        preflight_v3(rows)

    from dataset_builder.build_sft_data import write_jsonl
    write_jsonl(rows, args.out)
    clean = sum(1 for r in rows
                if not json.loads(r["messages"][-1]["content"])["findings"])
    print(f"{len(rows)} SFT examples -> {args.out}  "
          f"({len(rows) - clean} with findings, {clean} clean, "
          f"{100 * clean / max(len(rows), 1):.0f}% clean)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
