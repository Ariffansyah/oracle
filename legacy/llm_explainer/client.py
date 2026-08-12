"""Ollama chat client with strict-schema parsing and a regex fallback.

Even with `format=json` a local model occasionally wraps its answer in a
```json fence or bolts prose on either side, so `extract_json()` recovers the
first balanced JSON object before validation.
"""

from __future__ import annotations

import json
import re

import requests
from pydantic import ValidationError

from config import (
    LLM_MAX_DIFF_CHARS,
    LLM_NUM_CTX,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_S,
    OLLAMA_HOST,
    OLLAMA_MODEL,
)
from llm_explainer.prompts import SYSTEM_PROMPT, ReviewResult, build_prompt

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class LLMError(RuntimeError):
    pass


def extract_json(text: str) -> dict:
    """Pull a JSON object out of a possibly-decorated model response."""
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Scan for the first balanced {...}, ignoring braces inside strings.
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i, ch in enumerate(text[start:], start):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)

    raise LLMError(f"no JSON object in model response: {text[:200]!r}")


class OllamaClient:
    def __init__(
        self,
        host: str = OLLAMA_HOST,
        model: str = OLLAMA_MODEL,
        timeout: int = LLM_TIMEOUT_S,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        try:
            return requests.get(f"{self.host}/api/tags", timeout=3).ok
        except requests.RequestException:
            return False

    def chat(self, system: str, user: str) -> str:
        try:
            resp = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": LLM_TEMPERATURE,
                        "num_ctx": LLM_NUM_CTX,
                    },
                },
                timeout=self.timeout,
            )
        except requests.Timeout as e:
            # A big model that is still loading looks exactly like a dead host
            # unless these are separated.
            raise LLMError(
                f"{self.model} did not answer within {self.timeout}s — raise "
                f"ORACLE_LLM_TIMEOUT_S, or the model may still be loading"
            ) from e
        except requests.RequestException as e:
            # Full urllib3 trace is noise in the dashboard; keep it as __cause__.
            raise LLMError(
                f"cannot reach Ollama at {self.host} — is `ollama serve` running?"
            ) from e
        if not resp.ok:
            raise LLMError(f"Ollama {resp.status_code}: {resp.text[:200]}")
        return resp.json()["message"]["content"]

    @staticmethod
    def _contradictions(review: ReviewResult) -> list[str]:
        """Hunks the model said break, but then left out of `findings`.

        Models describe a defect accurately in `changed_behavior` and still
        return an empty findings list, so the contradiction is checked in code
        rather than trusted to the prompt.
        """
        cited = {f.file_line for f in review.findings}
        return [
            f"{d.file_line}: you wrote it breaks when {d.breaks_when!r} but "
            f"reported no finding for it"
            for d in review.changed_behavior
            if d.breaks_when.strip().lower().rstrip(".") != "never"
            and d.file_line not in cited
        ]

    def review(
        self,
        diff: str,
        risk_score: float,
        risk_band: str,
        contributions: list[str],
        subject: str = "",
        files: list[str] | None = None,
        retries: int = 1,
        include_risk: bool = True,
    ) -> ReviewResult:
        """Run the review and return a validated `ReviewResult`."""
        prompt = build_prompt(
            diff, risk_score, risk_band, contributions, subject, files,
            max_diff_chars=LLM_MAX_DIFF_CHARS, include_risk=include_risk,
        )
        last: Exception | None = None
        review: ReviewResult | None = None
        for attempt in range(retries + 1):
            raw = self.chat(SYSTEM_PROMPT, prompt)
            try:
                review = ReviewResult.model_validate(extract_json(raw))
            except (LLMError, ValidationError) as e:
                last = e
                prompt = (
                    f"{prompt}\n\nYour previous answer was rejected: {e}\n"
                    "Return ONLY a valid JSON object matching the schema."
                )
                continue

            conflicts = self._contradictions(review)
            if not conflicts or attempt == retries:
                return review  # out of retries: the raw answer beats no answer
            prompt = (
                f"{prompt}\n\nYour previous answer contradicted itself:\n"
                + "\n".join(f"- {c}" for c in conflicts)
                + "\nEither report those as findings, or set breaks_when to "
                  "'never' if you were wrong. Return the corrected JSON only."
            )
        raise LLMError(f"model produced no schema-valid JSON after {retries + 1} tries: {last}")


if __name__ == "__main__":
    assert extract_json('```json\n{"summary": "ok", "findings": []}\n```')["summary"] == "ok"
    assert extract_json('Here you go: {"a": "}"} trailing prose')["a"] == "}"
    assert extract_json('{"a": {"b": 1}}')["a"]["b"] == 1
    try:
        extract_json("no json here")
    except LLMError:
        pass
    else:
        raise AssertionError("expected LLMError")

    c = OllamaClient()
    print(f"ollama at {c.host}: {'up' if c.available() else 'unreachable'}")
