"""Inference against the fine-tuned reviewer.

Two backends behind one interface:

  transformers  local weights - a merged model directory, a PEFT adapter, or the
                base model. This is the fine-tuned ORACLE.
  ollama        a served GGUF build of the same model, over HTTP.

Both return a validated `Analysis`. The model is asked for strict JSON, but even
a fine-tuned model occasionally wraps it in a fence or trails prose, so
`extract_json` recovers the first balanced object before validation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError

from config import (BACKEND, BASE_MODEL, CHUNK_MAX_FILES, CHUNK_OVER_CHARS,
                    CHUNK_SKIP_OVER_CHARS, MAX_DIFF_CHARS, MAX_NEW_TOKENS,
                    MERGED_MODEL_DIR, OLLAMA_HOST, OLLAMA_MODEL,
                    CONTEXT_MAX_CHARS, OLLAMA_NUM_CTX, REQUEST_TIMEOUT_S,
                    TEMPERATURE)
from dataset_builder.schema import SYSTEM_PROMPT, Analysis, build_user_message

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_FILE_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+)$", re.MULTILINE)


def split_diff(diff: str) -> list[tuple[str, str]]:
    """Split a commit diff into (path, per-file diff) pairs.

    Returns a single ("", diff) pair when there are no `diff --git` headers, so
    a hand-written patch still goes through one code path.
    """
    matches = list(_FILE_HEADER.finditer(diff))
    if not matches:
        return [("", diff)] if diff.strip() else []

    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(diff)
        path = m.group(2)  # the "b/" side: the file after the change
        out.append((path, diff[m.start():end]))
    return out


class InferenceError(RuntimeError):
    pass


def extract_json(text: str) -> dict:
    """Pull a JSON object out of a possibly-decorated response."""
    if fenced := _FENCE.search(text):
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

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
    raise InferenceError(f"no JSON object in response: {text[:200]!r}")


class OracleClient:
    """Reviews a diff and returns a validated `Analysis`."""

    def __init__(self, model_path: str | Path | None = None,
                 backend: str = BACKEND, base_model: str = BASE_MODEL,
                 ollama_host: str = OLLAMA_HOST, ollama_model: str = OLLAMA_MODEL):
        self.backend = backend
        self.model_path = Path(model_path) if model_path else Path(MERGED_MODEL_DIR)
        self.base_model = base_model
        self.ollama_host = ollama_host.rstrip("/")
        self.ollama_model = ollama_model
        self._model = None
        self._tokenizer = None
        self._degraded: list[str] = []  # context shed to get an answer

    # --- transformers ------------------------------------------------------
    def _load(self):
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        path = self.model_path
        if (path / "adapter_config.json").exists():
            from peft import AutoPeftModelForCausalLM

            print(f"loading adapter {path}")
            self._model = AutoPeftModelForCausalLM.from_pretrained(
                str(path), dtype=torch.bfloat16, device_map="auto")
            tok_src = path if (path / "tokenizer_config.json").exists() else self.base_model
        elif path.exists():
            print(f"loading merged model {path}")
            self._model = AutoModelForCausalLM.from_pretrained(
                str(path), dtype=torch.bfloat16, device_map="auto")
            tok_src = path
        else:
            raise InferenceError(
                f"{path} not found — train and merge first, or use "
                f"--backend ollama to review against a served model"
            )
        self._tokenizer = AutoTokenizer.from_pretrained(str(tok_src))
        self._model.eval()

    def _generate_local(self, messages: list[dict]) -> str:
        self._load()
        import torch

        text = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
        inputs = self._tokenizer(text, return_tensors="pt").to(self._model.device)
        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                temperature=TEMPERATURE,
                do_sample=TEMPERATURE > 0,
                pad_token_id=self._tokenizer.pad_token_id
                or self._tokenizer.eos_token_id,
            )
        return self._tokenizer.decode(
            out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    # --- ollama ------------------------------------------------------------
    def _generate_ollama(self, messages: list[dict]) -> str:
        import requests

        try:
            resp = requests.post(
                f"{self.ollama_host}/api/chat",
                json={"model": self.ollama_model, "messages": messages,
                      "stream": False, "format": "json",
                      # num_ctx must be explicit: Ollama silently truncates to
                      # its default otherwise, and a context-carrying prompt is
                      # exactly what overflows it.
                      "options": {"temperature": TEMPERATURE,
                                  "num_ctx": OLLAMA_NUM_CTX}},
                timeout=REQUEST_TIMEOUT_S,
            )
        except requests.Timeout as e:
            raise InferenceError(
                f"{self.ollama_model} did not answer within {REQUEST_TIMEOUT_S}s "
                f"— it may still be loading") from e
        except requests.RequestException as e:
            raise InferenceError(
                f"cannot reach Ollama at {self.ollama_host}") from e
        if not resp.ok:
            raise InferenceError(f"Ollama {resp.status_code}: {resp.text[:200]}")
        return resp.json()["message"]["content"]

    # --- public ------------------------------------------------------------
    def analyze_commit(self, repo: str, rev: str, retries: int = 1,
                       progress=None, with_context: bool = True) -> Analysis:
        """Review a revision with its surrounding code, not just the hunks.

        Fetches `git show -U50` and the post-commit body of each changed file,
        so a guard is judged against the control it protects rather than in
        isolation. Falls back to the plain diff when context cannot be read.
        """
        from llm_inference.context import gather

        ctx = gather(repo, rev, with_snapshots=with_context)
        if not ctx.diff.strip():
            raise InferenceError(f"{rev} has no diff to review")

        parts = split_diff(ctx.expanded_diff or ctx.diff)
        if len(ctx.diff) > CHUNK_OVER_CHARS and len(parts) > 1:
            return self._analyze_chunked(
                parts, ctx.subject, retries, progress,
                snapshots=ctx.snapshots if with_context else {})

        return self._analyze_one(
            ctx.expanded_diff or ctx.diff, ctx.subject, ", ".join(ctx.files),
            retries, context=ctx.context_block() if with_context else "")

    def analyze(self, diff: str, subject: str = "", files: str = "",
                retries: int = 1, chunked: bool | None = None,
                progress=None, context: str = "") -> Analysis:
        """Review a diff. Large commits are reviewed file by file and merged.

        `chunked=None` decides by size; pass True/False to force. `progress` is
        called as (index, total, path) before each file.
        """
        parts = split_diff(diff)
        if chunked is None:
            chunked = len(diff) > CHUNK_OVER_CHARS and len(parts) > 1
        if chunked and len(parts) > 1:
            return self._analyze_chunked(parts, subject, retries, progress)
        return self._analyze_one(diff, subject, files, retries, context=context)

    def _analyze_chunked(self, parts: list[tuple[str, str]], subject: str,
                         retries: int, progress=None,
                         snapshots: dict[str, str] | None = None) -> Analysis:
        """One prompt per file, findings merged and attributed.

        Reviewing a whole large commit in a single prompt spreads attention over
        every file at once; per file the model gets the same budget for a
        fraction of the code.
        """
        parts = parts[:CHUNK_MAX_FILES]
        findings, reviewed, skipped, failed = [], [], [], []
        self._degraded = []

        for i, (path, part) in enumerate(parts, 1):
            if progress:
                progress(i, len(parts), path)
            if len(part) > CHUNK_SKIP_OVER_CHARS:
                skipped.append(path)  # generated, vendored or a lockfile
                continue
            # Each file is reviewed against its own body, so per-file review
            # narrows the code without narrowing the context.
            file_context = (snapshots or {}).get(path, "")
            if file_context:
                file_context = f"--- {path} (after this commit) ---\n{file_context}"
            try:
                result = self._analyze_with_fallback(part, subject, path,
                                                     retries, file_context)
            except InferenceError as e:
                # A dropped file is a silent blind spot - the one file that
                # fails is disproportionately likely to be the interesting one.
                failed.append((path, str(e)))
                continue
            reviewed.append(path)
            for f in result.findings:
                findings.append(f.model_copy(update={"file": f.file or path}))

        with_ctx = sum(1 for p in reviewed if (snapshots or {}).get(p))
        bits = [f"Reviewed {len(reviewed)} file(s) individually"
                + (f", {with_ctx} with full file context" if with_ctx else "")]
        if skipped:
            bits.append(f"skipped {len(skipped)} oversized "
                        f"({', '.join(skipped[:3])})")
        if failed:
            detail = "; ".join(f"{p} ({e[:60]})" for p, e in failed[:3])
            bits.append(f"{len(failed)} FAILED TO REVIEW — not covered by this "
                        f"verdict: {detail}")
        if self._degraded:
            bits.append(f"{len(self._degraded)} file(s) reviewed with reduced "
                        f"context")
        bits.append(f"{len(findings)} finding(s)" if findings
                    else ("no defects found in the files that were reviewed"
                          if failed else "no defects found"))
        return Analysis(summary="; ".join(bits) + ".", findings=findings)

    def _analyze_with_fallback(self, diff: str, subject: str, path: str,
                               retries: int, context: str) -> Analysis:
        """Shed context rather than skip the file.

        Attempts, in order: full file context, then a trimmed context, then the
        bare diff. Only a failure at every rung counts as a real failure, so an
        oversized or slow file still gets reviewed with whatever fits.
        """
        attempts = []
        if context:
            attempts.append(("full file context", context))
            if len(context) > CONTEXT_MAX_CHARS // 2:
                head = context[: CONTEXT_MAX_CHARS // 2]
                attempts.append(("trimmed context",
                                 head + "\n... [context truncated] ...\n"))
        attempts.append(("diff only", ""))

        last: Exception | None = None
        for label, ctx in attempts:
            try:
                return self._analyze_one(diff, subject, path, retries, context=ctx)
            except InferenceError as e:
                last = e
                self._degraded.append(f"{path}: retried with {label} after {e}")
        raise InferenceError(str(last))

    def _analyze_one(self, diff: str, subject: str = "", files: str = "",
                     retries: int = 1, context: str = "") -> Analysis:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(
                diff, subject, files, max_diff_chars=MAX_DIFF_CHARS,
                context=context)},
        ]
        last: Exception | None = None
        for attempt in range(retries + 1):
            raw = (self._generate_ollama(messages) if self.backend == "ollama"
                   else self._generate_local(messages))
            try:
                return Analysis.model_validate(extract_json(raw))
            except (InferenceError, ValidationError) as e:
                last = e
                if attempt == retries:
                    break
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content":
                        f"That was rejected: {e}. Reply with ONLY a JSON object "
                        f"matching the schema."},
                ]
        raise InferenceError(f"no schema-valid JSON after {retries + 1} tries: {last}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Review one diff.")
    ap.add_argument("--diff-file", type=Path)
    ap.add_argument("--model", type=Path, default=None)
    ap.add_argument("--backend", choices=("transformers", "ollama"), default=BACKEND)
    args = ap.parse_args(argv)

    if args.diff_file:
        diff = args.diff_file.read_text()
    else:
        from dataset_builder.mock_data import DEFECT_TEMPLATES

        diff = DEFECT_TEMPLATES[0][0].format(n=8)
        print("no --diff-file, using a mock defective commit\n")

    client = OracleClient(model_path=args.model, backend=args.backend)
    print(client.analyze(diff, subject="(cli)").model_dump_json(indent=2))


def _selftest() -> None:
    assert extract_json('```json\n{"summary":"s","findings":[]}\n```')["summary"] == "s"
    assert extract_json('here: {"a": "}"} trailing')["a"] == "}"
    assert extract_json('{"a": {"b": 1}}')["a"]["b"] == 1
    try:
        extract_json("nothing here")
    except InferenceError:
        pass
    else:
        raise AssertionError("expected InferenceError")

    two = """diff --git a/app/page.tsx b/app/page.tsx
--- a/app/page.tsx
+++ b/app/page.tsx
@@ -1,2 +1,3 @@
+const x = 1;
diff --git a/lib/db.ts b/lib/db.ts
--- a/lib/db.ts
+++ b/lib/db.ts
@@ -4,3 +4,4 @@
+export const db = createClient();
"""
    parts = split_diff(two)
    assert [p for p, _ in parts] == ["app/page.tsx", "lib/db.ts"], parts
    assert parts[0][1].startswith("diff --git a/app/page.tsx")
    assert "lib/db.ts" not in parts[0][1], "chunk leaked into its neighbour"
    assert parts[1][1].count("diff --git") == 1
    # Renames: the b/ side is the file that exists after the change.
    ren = split_diff("diff --git a/old.py b/new.py\n--- a/old.py\n+++ b/new.py\n+x\n")
    assert ren[0][0] == "new.py", ren
    # A bare patch with no headers stays one chunk.
    assert len(split_diff("@@ -1 +1 @@\n-a\n+b\n")) == 1
    assert split_diff("") == []
    print(f"json recovery + diff splitting ok ({len(parts)} chunks)")


if __name__ == "__main__":
    _selftest()
    main()
