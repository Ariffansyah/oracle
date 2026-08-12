"""Pydantic output schema, system prompt and evidence-prompt builder.

The whole contract with the model lives here: `ReviewResult.model_json_schema()`
is what we put in the prompt *and* what we validate the response against, so the
two can never drift apart.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

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


class Finding(BaseModel):
    category: Category = Field(description="Defect class this finding belongs to.")
    confidence: float = Field(ge=0.0, le=1.0, description="0.0-1.0 certainty this is a real defect.")
    grounded: bool = Field(
        description="True only if every line of code the explanation reasons about "
                    "is visible in the diff. A call to a function whose body is not "
                    "shown is NOT grounded, even though the call site is."
    )
    faithful: bool = Field(
        description="True only if the explanation follows from the cited code alone, "
                    "with no assumption about unseen code, callers or data."
    )
    explanation: str = Field(description="Why this is a defect and what goes wrong at runtime.")
    file_line: str = Field(description="Location as 'path/to/file.py:123'.")


class BehaviorDelta(BaseModel):
    """One changed hunk, and the input that separates the old code from the new.

    Models reliably describe the delta correctly and then still answer "no
    defects", so `breaks_when` forces the verdict to be written per hunk, in
    concrete terms, before the findings list is reached.
    """

    file_line: str = Field(description="Location as 'path/to/file.py:123'.")
    change: str = Field(
        description="What runtime behaviour differs now, concretely. "
                    "'now returns the user when expires_at equals now, "
                    "previously returned None' - not 'adjusts the comparison'."
    )
    breaks_when: str = Field(
        description="A concrete input, boundary or moment where the NEW behaviour "
                    "is wrong, and what goes wrong there. Write exactly 'never' "
                    "only if no such input exists, and then say why in one clause."
    )


class ReviewResult(BaseModel):
    # Declared first on purpose: models fill JSON fields in order, so this is a
    # forced reasoning step before any verdict is committed to.
    changed_behavior: list[BehaviorDelta] = Field(
        default_factory=list,
        description="One entry per changed hunk. Fill this in BEFORE the summary "
                    "and findings. Every entry whose `breaks_when` is not 'never' "
                    "must appear in `findings`.",
    )
    summary: str = Field(
        description="1-2 sentences comparing the ML risk score to what semantic review actually found."
    )
    findings: list[Finding] = Field(
        default_factory=list,
        description="Real semantic defects. Empty list when the code is safe.",
    )


SYSTEM_PROMPT = """You are ORACLE, a precise code-review analyst.

You receive a commit diff, a statistical Just-In-Time defect-risk score, and the \
SHAP feature contributions that produced that score. The statistical model sees \
only process metrics (churn, file count, author experience) - it has never read \
the code. Your job is the semantic half: decide whether the code itself is \
actually defective.

Method - do this before you decide anything:
Read the diff first, on its own, before you look at the risk score. For every \
changed line, state to yourself what behaviour changed, then check that delta \
against: boundary and comparison operators (`>` vs `>=`, `<` vs `<=`, off-by-one), \
None/null and empty paths, inverted or short-circuited conditions, sign and unit \
changes, integer vs float division, order of operations, early returns that skip \
cleanup, resource and lock lifetime, error paths that swallow failures, and \
changed defaults. A one-line change is where these hide - small diffs are not \
safe diffs.

Write that analysis into `changed_behavior` first, one entry per changed hunk, \
before you write the summary or any finding. For each entry, `change` states the \
runtime difference concretely and `breaks_when` names an actual input, boundary \
or moment where the NEW behaviour is wrong. Search for that input before you \
conclude there is none: try the exact boundary value, the empty or None case, the \
error path, and the moment the resource is released. Only write `breaks_when: \
"never"` when you have tried and no such input exists.

Then honour what you wrote. Every `changed_behavior` entry whose `breaks_when` is \
not "never" MUST appear as a finding citing the same file_line. Describing a \
defect in `changed_behavior` and then returning an empty `findings` list is a \
contradiction and an invalid answer.

Rules:
1. The ML risk score is a prior, not evidence. A high score is NOT a defect. \
Never invent a finding to justify the score.
2. The reverse holds with equal force. A low score, a small diff, or tidy-looking \
code is NOT evidence of safety. Returning 0 findings is a claim, and it needs the \
same rigor as reporting one: you may only make it after actually tracing the \
changed lines. Never call a change safe merely because it is small, plausible, or \
looks like a clarification.
3. If the ML model flags lines due to statistical patterns but semantic review \
shows standard safe code, return 0 findings and state this in the summary. This \
is the correct answer only when the method above turned up nothing - it is not a \
default.
4. Report only defects you can point at in the provided diff. Every finding must \
cite a file and line that appears in the diff. If you cannot cite it, drop it.
5. Set `grounded=false` if you are extrapolating beyond the shown lines, and \
`faithful=false` if your explanation relies on assumptions not visible in the \
code. Reasoning about what a called function might do internally, when its body \
is not in the diff, is `grounded=false` - the call site being visible is not \
enough. Do not silently mark uncertain findings as grounded and faithful. Low \
confidence is fine - report a real suspicion at confidence 0.4 rather than \
staying silent.
6. Style, formatting and naming are not defects. Do not report them.
7. Output ONE JSON object matching the schema. No markdown, no code fences, no \
prose before or after the JSON.
"""


def build_prompt(
    diff: str,
    risk_score: float,
    risk_band: str,
    contributions: list[str],
    subject: str = "",
    files: list[str] | None = None,
    max_diff_chars: int | None = None,
    include_risk: bool = True,
) -> str:
    """Assemble the evidence block handed to the model.

    `include_risk=False` drops the statistical prior entirely - the ablation that
    answers whether the hybrid is doing anything an LLM alone would not.
    """
    if max_diff_chars and len(diff) > max_diff_chars:
        diff = diff[:max_diff_chars] + "\n... [diff truncated] ...\n"

    drivers = "\n".join(f"  - {c}" for c in contributions) or "  - (none)"
    files_line = ", ".join(files or []) or "(unknown)"

    risk_block = f"""
## Statistical JIT risk (process metrics only - the model has NOT read the code)
score: {risk_score:.3f} ({risk_band})
top SHAP contributions (positive = pushed risk up):
{drivers}
""" if include_risk else ""

    # The diff comes first on purpose: reading the score first primes the model
    # to rationalise it in whichever direction the number points.
    return f"""## Commit
subject: {subject or "(none)"}
files: {files_line}

## Diff
```diff
{diff}
```
{risk_block}
## Required JSON schema
{json.dumps(ReviewResult.model_json_schema(), indent=2)}

Return only the JSON object.
"""


if __name__ == "__main__":
    p = build_prompt("@@ -1 +1 @@\n-a\n+b\n", 0.81, "HIGH", ["la = 400 (+0.42)"])
    assert "0 findings" in SYSTEM_PROMPT
    assert "```diff" in p
    empty = ReviewResult(summary="Statistically risky, semantically clean.")
    assert empty.findings == []
    print(ReviewResult.model_validate_json(empty.model_dump_json()))
