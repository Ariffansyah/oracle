"""The output contract, shared by data building, training and inference.

One definition, imported everywhere: the SFT targets, the DPO pairs and the
inference parser all validate against the same model, so training data and
runtime expectations cannot drift apart.
"""

from __future__ import annotations

import json
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
    before: str = Field(
        description="Observable behaviour BEFORE this commit, at that trigger."
    )
    after: str = Field(
        description="Observable behaviour AFTER this commit, at that trigger."
    )
    direction: str = Field(
        description="One of: post-breaks | post-fixes | unchanged."
    )

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

USER_TEMPLATE = """Review this commit for defects.

subject: {subject}
files: {files}
{context}
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

# One switch moves prompt, hint and expected keys together. A checkpoint scored
# under a contract it was not trained on lost six cases in forty-six to that
# alone (RESULTS.md, 27 Aug), so these must never be selected independently.
SYSTEM_PROMPT = _SYSTEM_PROMPT_V2 if OUTPUT_CONTRACT == "v2" else _SYSTEM_PROMPT_V1
SHORT_FORMAT_HINT = _SHORT_HINT_V2 if OUTPUT_CONTRACT == "v2" else _SHORT_HINT_V1


def build_user_message(diff: str, subject: str = "", files: str = "",
                       max_diff_chars: int | None = None,
                       context: str = "", include_schema: bool = True) -> str:
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
    schema_part = (
        SCHEMA_BLOCK.format(schema=json.dumps(Analysis.model_json_schema(), indent=2))
        if include_schema else SHORT_FORMAT_HINT
    )
    return USER_TEMPLATE.format(
        subject=subject or "(none)",
        files=files or "(unknown)",
        context=CONTEXT_TEMPLATE.format(context=context) if context else "",
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
