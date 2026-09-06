"""The output contract, shared by data building, training and inference.

One definition, imported everywhere: the SFT targets, the DPO pairs and the
inference parser all validate against the same model, so training data and
runtime expectations cannot drift apart.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import OUTPUT_CONTRACT  # noqa: E402

Category = Literal[
    "null-dereference",
    "off-by-one",
    "resource-leak",
    "concurrency",
    "input-validation",
    "error-handling",
    "security",
    "api-misuse",
    "logic-error",
    "other",
]


_CATEGORY_ALIASES = {
    "runtime error": "logic-error", "runtime-error": "logic-error",
    "null pointer": "null-dereference", "npe": "null-dereference",
    "nullpointerexception": "null-dereference", "null-pointer": "null-dereference",
    "off by one": "off-by-one", "boundary": "off-by-one",
    "memory leak": "resource-leak", "leak": "resource-leak",
    "race condition": "concurrency", "race": "concurrency", "deadlock": "concurrency",
    "validation": "input-validation", "input validation": "input-validation",
    "error handling": "error-handling", "exception": "error-handling",
    "vulnerability": "security", "injection": "security",
    "api misuse": "api-misuse", "misuse": "api-misuse",
    "logic": "logic-error", "logic error": "logic-error",
}


DIRECTIONS = ("post-breaks", "post-fixes", "unchanged")

# v3 only. Two buckets, because calibration is read as "is `likely` right more
# often than `possible`" and three buckets on 101 cases leaves too few in each.
CONFIDENCE = ("likely", "possible")

_CONFIDENCE_ALIASES = {
    "high": "likely", "certain": "likely", "confident": "likely",
    "sure": "likely", "strong": "likely", "probable": "likely",
    "medium": "possible", "moderate": "possible", "low": "possible",
    "uncertain": "possible", "unsure": "possible", "maybe": "possible",
    "weak": "possible", "unclear": "possible",
}

_DIRECTION_ALIASES = {
    "breaks": "post-breaks", "break": "post-breaks", "post_breaks": "post-breaks",
    "introduces": "post-breaks", "introduces-defect": "post-breaks",
    "regression": "post-breaks", "worse": "post-breaks", "buggy": "post-breaks",
    "fixes": "post-fixes", "fix": "post-fixes", "post_fixes": "post-fixes",
    "repairs": "post-fixes", "repair": "post-fixes", "better": "post-fixes",
    "no-change": "unchanged", "no change": "unchanged", "none": "unchanged",
    "same": "unchanged", "identical": "unchanged", "clean": "unchanged",
    "refactor": "unchanged", "no-op": "unchanged",
}


class Effect(BaseModel):
    """The observable behaviour change, stated BEFORE any verdict.

    This field exists because of a measured failure, not a style preference. The
    v1 contract emits `summary` first, and a model that has already written
    "this commit repairs the off-by-one" cannot then produce a finding: the only
    continuation consistent with its own first sentence is an empty list. On
    27 Aug, five of six missed defects were exactly that, and three of them drew
    a training template verbatim.

    `before` and `after` are what the program *does* - a value, an exception, a
    panic, a hang - not what the diff looks like. That is what makes the claim
    checkable: `bench/basic_bench.py` already runs both sides, so a wrong
    behavioural claim becomes a scoreable error instead of unfalsifiable prose.

    An unrecognised `direction` becomes "unclear" rather than being coerced to
    "unchanged". Mapping garbage onto a clean verdict would hide a failure the
    grader is supposed to count.
    """

    trigger: str = Field(
        description="One input or condition that exposes the difference, e.g. 'xs = [1,2,3]'."
    )
    # v1/v2 only. Optional so one model can carry all three contracts:
    # `to_json` uses exclude_none, so a v2 answer still serialises to exactly
    # the same bytes it did before `check` and `confidence` existed, and a v3
    # answer never emits an empty before/after. Deliberately NOT enforced per
    # contract - this file coerces near-misses rather than rejecting answers
    # (see `_coerce_category`), and a hard validator here would throw away a
    # usable analysis over a missing key.
    before: str | None = Field(
        default=None,
        description="v1/v2 only. Observable behaviour BEFORE this commit, at that trigger."
    )
    after: str | None = Field(
        default=None,
        description="v1/v2 only. Observable behaviour AFTER this commit, at that trigger."
    )
    # v3 only. Declared after before/after so v2 key order is unchanged, and
    # before `direction` so the v3 answer still puts its evidence first.
    check: str | None = Field(
        default=None,
        description="v3 only. A test the reader can run to settle it, as an instruction."
    )
    direction: str = Field(
        description="One of: post-breaks | post-fixes | unchanged."
    )
    confidence: str | None = Field(
        default=None,
        description="v3 only. One of: likely | possible."
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        """Two buckets only, so calibration has enough cases per bucket to read.

        Anything unrecognised becomes "possible" rather than None: a hedge the
        grader cannot classify should count as the WEAKER claim, never be
        dropped, or an unparseable confidence would silently inflate the
        `likely` bucket it is supposed to be measured against.
        """
        if v is None:
            return None
        if not isinstance(v, str):
            return "possible"
        key = v.strip().lower()
        return key if key in CONFIDENCE else _CONFIDENCE_ALIASES.get(key, "possible")

    @field_validator("direction", mode="before")
    @classmethod
    def _coerce_direction(cls, v):
        if not isinstance(v, str):
            return "unclear"
        key = v.strip().lower()
        if key in _DIRECTION_ALIASES:
            return _DIRECTION_ALIASES[key]
        return key if key in DIRECTIONS else "unclear"


class Finding(BaseModel):
    category: Category = Field(description="Defect class this finding belongs to.")

    @field_validator("category", mode="before")
    @classmethod
    def _coerce_category(cls, v):
        """Map a near-miss onto the taxonomy rather than rejecting the finding.

        A fine-tuned model occasionally emits `runtime error` for `logic-error`.
        The taxonomy is ours, the defect it found may be real, and throwing the
        whole analysis away over a label is the wrong trade.
        """
        if not isinstance(v, str):
            return v
        key = v.strip().lower()
        if key in _CATEGORY_ALIASES:
            return _CATEGORY_ALIASES[key]
        return key if key in set(Category.__args__) else "other"
    explanation: str = Field(
        description="What breaks at runtime, and at which input or boundary."
    )
    # Filled by the client when a commit is reviewed file by file. Left empty in
    # training data, so the model is never asked to produce it.
    file: str = Field(default="", description="File this finding belongs to.")


class Analysis(BaseModel):
    # First on purpose: pydantic preserves declaration order, so this is the
    # first key the model generates. Evidence before verdict.
    effect: Effect | None = Field(
        default=None,
        description="Observable behaviour change, stated before the verdict.",
    )
    summary: str = Field(
        description="1-2 sentences: what this commit changes and whether it is risky."
    )
    findings: list[Finding] = Field(
        default_factory=list,
        description="Real defects introduced by this diff. Empty when the code is safe.",
    )
    # repair contract only, and optional for the same reason `Effect.before` is:
    # `to_json` excludes None, so a v1/v2/v3 target serialises to exactly the
    # bytes it did before these existed. Declared last so key order is unchanged.
    confidence: float | None = Field(
        default=None,
        description="repair only. 0.0-1.0 support for the verdict.")
    affected_identifiers: list[str] | None = Field(
        default=None,
        description="repair only. Symbols the change touches, as they appear in the diff.")
    repair_direction: str | None = Field(
        default=None,
        description="repair only. The shape of the repair the code needs.")

    def to_json(self) -> str:
        # exclude_none keeps v1 targets byte-identical: no `"effect": null` in
        # a corpus that predates the field.
        return json.dumps(self.model_dump(exclude_none=True), ensure_ascii=False)


_SYSTEM_PROMPT_V1 = """You are ORACLE, a Just-In-Time defect reviewer.

You are given a single commit diff. Decide whether the change introduces a \
defect, and answer with one JSON object and nothing else.

Method:
1. For each changed hunk, state to yourself what runtime behaviour differs now.
2. Look for an input, boundary or moment where the NEW behaviour is wrong: \
comparison operators (`>` vs `>=`), None/empty paths, inverted conditions, sign \
and unit changes, integer division, early returns that skip cleanup, resource \
and lock lifetime, swallowed errors, changed defaults.
3. Missing validation in newly added code IS a defect and must be a finding. \
Example: a new `divide(a, b)` returning `a / b` without checking `b == 0` is a \
null-input finding, not just a risky summary. A new handler, index or auth \
path that is unsafe without a guard introduces that risk in this commit.
4. When surrounding code is provided, use it. A guard or early return is not a \
defect because its justification is outside the hunk - check the surrounding \
code for the control it protects before calling it dead or incomplete.
5. Report only defects you can point at in the diff. If the change is safe, \
return an empty `findings` list and say so in the summary.

Rules:
- A large or messy diff is not a defect. Never invent a finding to justify one.
- A small or tidy diff is not evidence of safety. Zero findings is a claim that \
requires the same rigor as reporting one.
- Style, formatting and naming are not defects.
- Output ONE JSON object. No markdown, no code fences, no prose around it.
"""

CONTEXT_TEMPLATE = """
## Surrounding code (state after this commit)
Read this before judging the diff. A guard, early return or check is not dead \
code merely because the diff does not show what depends on it - look here for \
the caller, the disabled control, or the second check.

```
{context}
```
"""

# Measured, not predicted. The 2 Sep hand-grade found the model's two worst
# failures were an INVERTED before/after and a FABRICATED exception — both of
# which are guesses about behaviour it was never shown. bench/exec_diff.py runs
# both versions, so the guess can be replaced by the fact.
OBSERVED_TEMPLATE = """
## Observed behaviour (both versions were executed)
These two outputs were MEASURED by running the code, not predicted. They are
ground truth. Your explanation must account for this exact difference, and must
not assert any behaviour that contradicts it.

before (pre-commit):  {before}
after  (post-commit): {after}
"""

USER_TEMPLATE = """Review this commit for defects.

subject: {subject}
files: {files}
{context}{observed}
## Changes
```diff
{diff}
```
{schema}"""

SCHEMA_BLOCK = """
Answer with JSON matching this schema:
{schema}
"""

# Without the schema. A fine-tuned model has learnt the format; repeating 357
# tokens of JSON Schema in every prompt is pure cost - it was ~45% of the
# training sequence, and the vocab-sized logits that dominate DPO memory scale
# directly with it.
_SHORT_HINT_V1 = """
Answer with one JSON object: {"summary": "...", "findings": [{"category": "...", "explanation": "..."}]}
"""

# ---------------------------------------------------------------------------
# v2: evidence before verdict.
#
# The v1 contract asks the model (step 1) to "state to yourself what runtime
# behaviour differs now" and then gives it nowhere to write that down - the
# first key it emits is `summary`, which is the verdict. So the reasoning step
# has no slot and collapses into the conclusion, and the conclusion is then
# unrevisable because generation only runs forwards.
#
# v2 gives that step a slot, puts it first, and makes what goes in it checkable
# by execution.

_SYSTEM_PROMPT_V2 = """You are ORACLE, a Just-In-Time defect reviewer.

You are given a single commit diff. Work out what the change does to the \
program's behaviour, then decide whether it introduces a defect. Answer with \
one JSON object and nothing else.

Fill the keys IN ORDER. Do not decide the verdict first.

1. `effect` - FIRST, before you have an opinion.
   - `trigger`: one concrete input or condition where the two versions differ.
   - `before`: what the program did at that trigger BEFORE this commit.
   - `after`: what it does AFTER.
   Write observable behaviour: a value, an exception, a panic, a hang, a race. \
   Not "it is correct", not "it is risky" - those are verdicts, not behaviour. \
   If you cannot name a trigger where the two versions differ, the behaviour is \
   unchanged and you must say so rather than inventing one.
   - `direction`: `post-breaks` if the new code is wrong at that trigger, \
   `post-fixes` if the old code was wrong and the new code is right, \
   `unchanged` if both behave identically.
   State only behaviour you can derive from the code in front of you. Never \
   quote a file path, a line number or program output you have not been given: \
   an invented trace is a worse failure than saying the behaviour is unchanged.

2. `summary` - SECOND. One or two sentences, and it must agree with the \
   `effect` you just wrote. If `direction` is `post-breaks`, the summary says \
   the commit introduces a defect.

3. `findings` - LAST. One entry per defect the change introduces, each naming \
   the construct it lives in. `direction: post-breaks` requires at least one \
   finding; `post-fixes` and `unchanged` require an empty list.

What to look at when deciding `after`: comparison operators (`>` vs `>=`), \
None/empty paths, inverted conditions, sign and unit changes, integer division, \
early returns that skip cleanup, resource and lock lifetime, swallowed errors, \
changed defaults. Watch for a construct that changed meaning because code was \
added *around* it - a lock or guard absorbed by a new function still shows as \
unchanged context in the diff, and the function it used to protect is now \
unprotected.

Missing validation in newly added code IS a defect. A new `divide(a, b)` \
returning `a / b` with no `b == 0` check breaks at `b = 0`, and that is an \
`effect` with a trigger, not just a risky-sounding summary.

When surrounding code is provided, use it. A guard or early return is not a \
defect because its justification is outside the hunk.

Rules:
- A large or messy diff is not a defect. Never invent a finding to justify one.
- A small or tidy diff is not evidence of safety. `unchanged` is a claim that \
requires the same rigor as reporting a defect.
- Style, formatting and naming are not defects.
- Output ONE JSON object. No markdown, no code fences, no prose around it.
"""

_SHORT_HINT_V2 = """
Answer with one JSON object, keys in this order:
{"effect": {"trigger": "...", "before": "...", "after": "...", "direction": "post-breaks|post-fixes|unchanged"}, "summary": "...", "findings": [{"category": "...", "explanation": "..."}]}
"""

# ---------------------------------------------------------------------------
# v3: the suggestion contract. Say where and which way; suggest the test.
#
# v2 asks for `before` and `after` - what the program actually printed. The
# model cannot run the code, so it cannot know. Measured on 30 Aug across all
# four v2/v3 checkpoints and all 101 cases, split by claim type:
#
#     where  (does it cite the code at fault)   87-98% right
#     which way (post-breaks vs post-fixes)     79-93% right
#     the concrete before/after value           15-31% right
#
# So the contract demands the one thing the model is bad at, and it fills the
# slot by inventing. 69-85% of stored answers carry a value that running the
# code contradicts - and in 90-99% of those the answer was still pointing at
# the RIGHT code. The false value is bolted onto a correct hint.
#
# v3 removes the slot. `check` asks for the test that would settle it, which is
# derivable from the diff, instead of the result of that test, which is not.
# The headline metric never read before/after (basic_bench.py:413), so this
# costs nothing measurable and deletes the whole class of false claim.
#
# `confidence` exists so the hedge is calibrated rather than blanket. A model
# that says "maybe" about everything is never wrong and never useful; the
# false-alarm rate on clean cases is what catches that, and the `likely` vs
# `possible` split is what makes the hedge informative.

_SYSTEM_PROMPT_V3 = """You are ORACLE, a Just-In-Time defect reviewer.

You are given a single commit diff. Work out what the change does, then point \
the reader at what to check. Answer with one JSON object and nothing else.

You CANNOT run the code and have never seen this program's output. Report what \
to look at and what test would settle it — never what the program printed, \
returned or computed.

Fill the keys IN ORDER. Do not decide the verdict first.

1. `effect` — FIRST, before you have an opinion.
   - `trigger`: one input or condition where the two versions may differ, \
   derived from the diff, e.g. 'a score of exactly 60', 'an empty list'.
   - `check`: the test that would settle it, as an instruction to the reader — \
   "call it with an empty list and see whether it still returns 0". NOT a \
   result. Never write a number, return value or trace as though you observed \
   it. If you find yourself writing what the program does, rewrite it as what \
   to run.
   - `direction`: `post-breaks` if the new code looks wrong at that trigger, \
   `post-fixes` if the old code was wrong and the new is right, `unchanged` if \
   both look the same.
   - `confidence`: `likely` when the diff alone is enough to be fairly sure, \
   `possible` when it is a lead worth checking. A wrong `likely` costs more \
   than an honest `possible`.

2. `summary` — SECOND, agreeing with the `effect` you just wrote. One or two \
   sentences, phrased as a suggestion ("looks like", "probably", "worth \
   checking"), ending with what the reader should do.

3. `findings` — LAST. One entry per defect the change may introduce, each \
   naming the construct it lives in, written as what to verify rather than as \
   proven fact. `post-breaks` requires at least one finding; `post-fixes` and \
   `unchanged` require an empty list.

Look at: comparison operators (`>` vs `>=`), None/empty paths, inverted \
conditions, sign and unit changes, integer division, early returns that skip \
cleanup, resource and lock lifetime, swallowed errors, changed defaults. Watch \
for a construct that changed meaning because code was added *around* it — a \
guard absorbed by a new function still shows as unchanged context. Missing \
validation in new code is worth flagging: a new `divide(a, b)` with no `b == 0` \
check has a trigger at `b = 0`.

Rules:
- Hedged wording is not a licence to flag everything. Naming a suspect on a \
change that does nothing is still a false alarm, and it is this contract's \
main risk. If nothing looks wrong, say `unchanged` and leave `findings` empty.
- A large or messy diff is not a defect; a tidy one is not evidence of safety.
- Style, formatting and naming are not defects.
- Never quote a file path or line number you were not given.
- Output ONE JSON object. No markdown, no code fences, no prose around it.
"""

_SHORT_HINT_V3 = """
Answer with one JSON object, keys in this order:
{"effect": {"trigger": "...", "check": "...", "direction": "post-breaks|post-fixes|unchanged", "confidence": "likely|possible"}, "summary": "...", "findings": [{"category": "...", "explanation": "..."}]}
"""

# One switch moves prompt, hint and expected keys together. A checkpoint scored
# under a contract it was not trained on lost six cases in forty-six to that
# alone (RESULTS.md, 27 Aug), so these must never be selected independently.

# --- repair contract -------------------------------------------------------
# The repair-supervised contract (1 Sep). NOT a variant of v1/v2/v3: different
# keys, different user template, and its targets are derived from the diff that
# REPAIRED each defect rather than written from the buggy code alone.
#
# This literal is byte-identical to the system turn in data/sft_repair_msgs.jsonl
# and `dataset_builder/build_repair_sft.py` imports it from here rather than
# keeping its own copy. That is deliberate. `_PROMPTS.get(OUTPUT_CONTRACT, ...)`
# falls back to the V1 prompt for any unknown name, so setting
# ORACLE_OUTPUT_CONTRACT=repair without this entry would have served the new
# checkpoint the one prompt shape it never trained on - the same failure that
# cost the project two days through the TUI, arriving by a different door.
_SYSTEM_PROMPT_REPAIR = 'You are ORACLE, a Just-In-Time defect reviewer.\n\nYou are given one commit diff. Decide whether it introduces a defect, and answer with one JSON object and nothing else.\n\nYou CANNOT run the code. Report only what the diff shows.\n\n  "defect_found"          true if this change introduces a defect, else false\n  "confidence"            0.0-1.0, how strongly the evidence supports that call\n  "target_file"           the file the defect is in, or the file the change centres on\n  "affected_identifiers"  the symbols the change touches, as they appear in the diff\n  "explanation"           one sentence, naming only identifiers present in the diff\n  "repair_direction"      if defect_found, the shape of the repair the code needs; otherwise null\n\nName no identifier that is absent from the diff. If the change adds a definition that did not exist before, it has no prior behaviour to contradict.'

# Also byte-identical to training. No schema block and no context block: the
# repair corpus carries neither, so `build_user_message` must not add them.
_USER_TEMPLATE_REPAIR = """Review this commit.

subject: {subject}
files: {files}

```diff
{diff}
```"""


def repair_to_analysis(obj: dict) -> "Analysis":
    """Map a repair-contract answer onto `Analysis`.

    Everything downstream - the benches, the grading sheet, the TUI - reads
    `summary` and `findings`. Rather than teach each of them a second shape,
    the repair answer is adapted here.

    `category` is "other" because the repair contract does not ask for one, and
    inventing a taxonomy label the model never emitted would put a value into a
    field no metric could then trust.
    """
    expl = (obj.get("explanation") or "").strip()
    found = bool(obj.get("defect_found"))
    ids = obj.get("affected_identifiers") or None
    if isinstance(ids, str):
        ids = [ids]
    return Analysis(
        summary=expl,
        findings=([Finding(category="other", explanation=expl,
                           file=obj.get("target_file") or "")] if found else []),
        confidence=obj.get("confidence"),
        affected_identifiers=ids,
        repair_direction=obj.get("repair_direction") or None,
    )


_PROMPTS = {"v1": _SYSTEM_PROMPT_V1, "v2": _SYSTEM_PROMPT_V2, "v3": _SYSTEM_PROMPT_V3,
            "repair": _SYSTEM_PROMPT_REPAIR}
_HINTS = {"v1": _SHORT_HINT_V1, "v2": _SHORT_HINT_V2, "v3": _SHORT_HINT_V3}

# Opt-in, off by default: suppress speculative consequence clauses.
#
# Measured by hand-grade on 2 Sep (data/mechanism_grade_oracle46.json): 8 of 33
# findings had a CORRECT mechanism with one false consequence bolted on — an
# `ArrayIndexOutOfBounds` case that also offers NullPointerException, a Rust
# bounds check predicted as "segfault or corrupt data", an integer result called
# "non-numeric". Those 8 are the entire difference between 39% and 64%
# mechanism-correct, and none of them is a reasoning failure: the model is
# answering a question it was not asked and cannot check.
#
# Off unless ORACLE_NO_SPECULATION is set, because it changes the prompt the
# checkpoints were trained under and every stored number was measured without it.
_NO_SPECULATION = """
- State the mechanism the diff shows and its immediate result, then stop. Do \
not add alternative outcomes, downstream consequences, or hedged predictions. \
If an index goes out of bounds, say that; do not also guess whether the runtime \
panics, segfaults, throws, or corrupts memory. One consequence, the one the \
code forces."""

SYSTEM_PROMPT = _PROMPTS.get(OUTPUT_CONTRACT, _SYSTEM_PROMPT_V1)
if os.getenv("ORACLE_NO_SPECULATION", "") not in ("", "0", "false", "False"):
    SYSTEM_PROMPT = SYSTEM_PROMPT.rstrip() + "\n" + _NO_SPECULATION + "\n"
SHORT_FORMAT_HINT = _HINTS.get(OUTPUT_CONTRACT, _SHORT_HINT_V1)


def build_user_message(diff: str, subject: str = "", files: str = "",
                       max_diff_chars: int | None = None,
                       context: str = "", include_schema: bool = True,
                       observed: tuple[str, str] | None = None) -> str:
    """Assemble the user turn.

    `context` is the surrounding-code block - expanded hunks or whole post-commit
    files. It goes *before* the diff on purpose: the model should build a picture
    of the file and then look at what changed in it, not judge a fragment and
    then rationalise.

    `include_schema=False` swaps the full JSON Schema for a one-line hint. Use it
    for training data and for the fine-tuned model, which already knows the
    format; keep it True for a base model that does not. Training and inference
    must agree, or the model meets a prompt shape it never saw.
    """
    if max_diff_chars and len(diff) > max_diff_chars:
        diff = diff[:max_diff_chars] + "\n... [diff truncated] ...\n"
    if OUTPUT_CONTRACT == "repair":
        # Byte-identical to training: no schema, no context, no "## Changes".
        # `include_schema` and `context` are accepted and ignored rather than
        # rejected, so a caller that passes them gets the trained shape instead
        # of a prompt the checkpoint has never seen.
        return _USER_TEMPLATE_REPAIR.format(
            subject=subject or "(none)", files=files or "(unknown)", diff=diff)
    schema_part = (
        SCHEMA_BLOCK.format(schema=json.dumps(Analysis.model_json_schema(), indent=2))
        if include_schema else SHORT_FORMAT_HINT
    )
    return USER_TEMPLATE.format(
        subject=subject or "(none)",
        files=files or "(unknown)",
        context=CONTEXT_TEMPLATE.format(context=context) if context else "",
        observed=(OBSERVED_TEMPLATE.format(before=observed[0], after=observed[1])
                  if observed else ""),
        diff=diff,
        schema=schema_part,
    )


if __name__ == "__main__":
    a = Analysis(summary="Adds a null guard; behaviour unchanged for valid input.")
    assert a.findings == []
    assert json.loads(a.to_json())["findings"] == []
    b = Analysis.model_validate_json(
        '{"summary": "off-by-one", "findings": '
        '[{"category": "off-by-one", "explanation": "admits expired tokens"}]}'
    )
    assert b.findings[0].category == "off-by-one"
    msg = build_user_message("@@ -1 +1 @@\n-a\n+b\n", "fix: x", "a.py")
    assert "```diff" in msg and "properties" in msg
    assert "Surrounding code" not in msg, "no context section when none given"

    with_ctx = build_user_message("@@ -1 +1 @@\n-a\n+b\n", "fix: x", "a.py",
                                  context="<button disabled={!token} />")
    assert "Surrounding code" in with_ctx and "disabled={!token}" in with_ctx
    # Context must precede the diff so the file is read before the fragment.
    assert with_ctx.index("Surrounding code") < with_ctx.index("## Changes")
    assert Finding(category="other", explanation="x").file == ""
    # A near-miss is mapped, not rejected; anything unknown lands on "other".
    assert Finding(category="runtime error", explanation="x").category == "logic-error"
    assert Finding(category="NPE", explanation="x").category == "null-dereference"
    assert Finding(category="banana", explanation="x").category == "other"

    # --- v2 contract -----------------------------------------------------
    e = Effect(trigger="xs=[1,2,3]", before="6", after="panic", direction="breaks")
    assert e.direction == "post-breaks", "alias must map onto the taxonomy"
    assert Effect(trigger="t", before="a", after="b",
                  direction="banana").direction == "unclear", \
        "unknown direction must not be coerced onto a clean verdict"
    # `effect` is the FIRST key generated - that is the whole point of the field.
    with_eff = Analysis(effect=e, summary="breaks at the end", findings=[])
    assert list(json.loads(with_eff.to_json()))[0] == "effect"
    # ... and a v1 answer still serialises without it.
    assert "effect" not in json.loads(Analysis(summary="x").to_json())
    assert Finding(category="off-by-one", explanation="x").category == "off-by-one"

    long = build_user_message("@@ -1 +1 @@\n-a\n+b\n", include_schema=True)
    short = build_user_message("@@ -1 +1 @@\n-a\n+b\n", include_schema=False)
    assert "properties" in long and "properties" not in short
    assert '"summary"' in short, "short form still names the fields"
    assert len(short) < len(long) / 2, (len(short), len(long))
    print(f"schema ok — full {len(long)} chars, short {len(short)} chars "
          f"({100 - 100 * len(short) // len(long)}% smaller)")
