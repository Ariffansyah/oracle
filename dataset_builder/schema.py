"""The output contract, shared by data building, training and inference.

One definition, imported everywhere: the SFT targets, the DPO pairs and the
inference parser all validate against the same model, so training data and
runtime expectations cannot drift apart.
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
    explanation: str = Field(
        description="What breaks at runtime, and at which input or boundary."
    )
    # Filled by the client when a commit is reviewed file by file. Left empty in
    # training data, so the model is never asked to produce it.
    file: str = Field(default="", description="File this finding belongs to.")


class Analysis(BaseModel):
    summary: str = Field(
        description="1-2 sentences: what this commit changes and whether it is risky."
    )
    findings: list[Finding] = Field(
        default_factory=list,
        description="Real defects introduced by this diff. Empty when the code is safe.",
    )

    def to_json(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=False)


SYSTEM_PROMPT = """You are ORACLE, a Just-In-Time defect reviewer.

You are given a single commit diff. Decide whether the change introduces a \
defect, and answer with one JSON object and nothing else.

Method:
1. For each changed hunk, state to yourself what runtime behaviour differs now.
2. Look for an input, boundary or moment where the NEW behaviour is wrong: \
comparison operators (`>` vs `>=`), None/empty paths, inverted conditions, sign \
and unit changes, integer division, early returns that skip cleanup, resource \
and lock lifetime, swallowed errors, changed defaults.
3. Report only defects you can point at in the diff. If the change is safe, \
return an empty `findings` list and say so in the summary.
4. When surrounding code is provided, use it. A guard or early return is not a \
defect because its justification is outside the hunk - check the surrounding \
code for the control it protects before calling it dead or incomplete.

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

Answer with JSON matching this schema:
{schema}
"""


def build_user_message(diff: str, subject: str = "", files: str = "",
                       max_diff_chars: int | None = None,
                       context: str = "") -> str:
    """Assemble the user turn.

    `context` is the surrounding-code block - expanded hunks or whole post-commit
    files. It goes *before* the diff on purpose: the model should build a picture
    of the file and then look at what changed in it, not judge a fragment and
    then rationalise.
    """
    if max_diff_chars and len(diff) > max_diff_chars:
        diff = diff[:max_diff_chars] + "\n... [diff truncated] ...\n"
    return USER_TEMPLATE.format(
        subject=subject or "(none)",
        files=files or "(unknown)",
        context=CONTEXT_TEMPLATE.format(context=context) if context else "",
        diff=diff,
        schema=json.dumps(Analysis.model_json_schema(), indent=2),
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
    print("schema ok (context section renders before the diff)")
