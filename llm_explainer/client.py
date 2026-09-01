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
                    DIFF_RENDERING, INCLUDE_SCHEMA, INFERENCE_4BIT,
                    INFERENCE_SAMPLES, OUTPUT_CONTRACT,
                    INFERENCE_SAMPLE_TEMPERATURE, CHUNK_SKIP_OVER_CHARS, MAX_DIFF_CHARS, MAX_NEW_TOKENS,
                    MERGED_MODEL_DIR, OLLAMA_HOST, OLLAMA_MODEL,
                    CONTEXT_MAX_CHARS, OLLAMA_NUM_CTX, REQUEST_TIMEOUT_S,
                    TEMPERATURE)
from dataset_builder.schema import SYSTEM_PROMPT, Analysis, build_user_message
from dataset_builder.worddiff import to_word_diff

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


# Names a diff introduces at the top level: `export async function foo`,
# `const bar =`, `def baz`. No indentation is allowed after the `+`, which keeps
# this to a module's public surface - the part a sibling file can call. Matching
# indented locals too would catch names like `amount` and pull in every file
# that happens to mention one.
_DEFINES = re.compile(
    r"^\+(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:function|const|class|let|var|def|type|interface)\s+"
    r"([A-Za-z_$][A-Za-z0-9_$]*)", re.MULTILINE)


def defined_names(diff: str) -> set[str]:
    return set(_DEFINES.findall(diff))


def sibling_context(path: str, part: str, parts: list[tuple[str, str]],
                    budget: int) -> str:
    """Other files in this commit that define something this file calls.

    Per-file review is what makes a large commit reviewable, but it also hides
    the definition of every function the file calls. A form posting to a server
    action added by the same commit looks unvalidated, because the validation is
    in a sibling chunk - measured: reviewed alone the model invents an
    input-validation defect, given the sibling it correctly finds nothing.

    Only the added lines go in, and only for files whose new names actually
    appear here, so the budget is spent on the code that resolves the question.
    """
    used, spent = [], 0
    for other_path, other in parts:
        if other_path == path or spent >= budget:
            continue
        names = defined_names(other)
        if not names or not any(re.search(rf"\b{re.escape(n)}\b", part)
                                for n in names):
            continue
        added = "\n".join(l[1:] for l in other.splitlines()
                          if l.startswith("+") and not l.startswith("+++"))
        if not added.strip():
            continue
        block = f"--- {other_path} (added by this same commit) ---\n{added}\n"
        used.append(block[: budget - spent])
        spent += len(block)
    return "\n".join(used)


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



def _already_word_diff(diff: str) -> bool:
    """Has this diff already been through `to_word_diff`.

    Two signals together, because either alone is wrong: word-diff output
    carries `{+...+}` / `[-...-]` markers AND has no `+`/`-` line prefixes left
    (the renderer strips them). Source code can legitimately contain `{+`, and a
    unified diff always keeps its prefixes, so requiring both makes a false
    positive need a diff that has markers and no changed-line prefixes at once.
    """
    if "{+" not in diff and "[-" not in diff:
        return False
    for line in diff.splitlines():
        if line[:3] in ("+++", "---"):
            continue
        if line[:1] in ("+", "-"):
            return False
    return True


class OracleClient:
    """Reviews a diff and returns a validated `Analysis`."""

    def __init__(self, model_path: str | Path | None = None,
                 backend: str = BACKEND, base_model: str = BASE_MODEL,
                 ollama_host: str = OLLAMA_HOST, ollama_model: str = OLLAMA_MODEL,
                 include_schema: bool | None = None):
        self.model_path = Path(model_path) if model_path else Path(MERGED_MODEL_DIR)
        trained = (self.model_path / "config.json").exists() or \
                  (self.model_path / "adapter_config.json").exists()
        # A hub id ("Qwen/Qwen2.5-Coder-3B-Instruct") is org/name where neither
        # the path nor its parent is a local directory. A mistyped local path
        # keeps the "not found" error instead of a confusing download attempt.
        self.is_hub_id = (not self.model_path.exists()
                          and not self.model_path.is_absolute()
                          and str(self.model_path).count("/") == 1
                          and not self.model_path.parent.exists())
        # "auto": the trained model when it exists, a served model until then.
        # Resolved here rather than at import so a training run that finishes
        # mid-session is picked up without editing config.
        if backend == "auto":
            backend = "transformers" if trained else "ollama"
        self.backend = backend
        # The fine-tuned model learnt the format from a schema-free prompt; a
        # stock base model has not, and judging it on a prompt that never names
        # the fields measures the prompt rather than the model. Over HTTP the
        # client cannot tell which it is talking to, so config can say.
        if include_schema is None:
            include_schema = {"true": True, "false": False}.get(
                str(INCLUDE_SCHEMA).lower(),
                not (backend == "transformers" and trained))
        self.include_schema = include_schema
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
        # 4-bit keeps a 3B entirely in VRAM on a 6GB card; fp16 does not fit and
        # transformers falls back to CPU offload without saying so loudly.
        load_kwargs = {"dtype": torch.float16, "device_map": "auto"}
        if INFERENCE_4BIT and torch.cuda.is_available():
            from transformers import BitsAndBytesConfig

            load_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.float16)

        # use_cache is disabled during training; inference wants it on.
        if (path / "adapter_config.json").exists():
            from peft import AutoPeftModelForCausalLM

            print(f"loading adapter {path}")
            self._model = AutoPeftModelForCausalLM.from_pretrained(
                str(path), **load_kwargs)
            tok_src = path if (path / "tokenizer_config.json").exists() else self.base_model
        elif path.exists():
            print(f"loading merged model {path}")
            self._model = AutoModelForCausalLM.from_pretrained(
                str(path), **load_kwargs)
            tok_src = path
        elif self.is_hub_id:
            # An untrained baseline: `--model Qwen/Qwen2.5-Coder-3B-Instruct` is
            # a hub id, not a directory. Comparing against it is the whole point
            # of an evaluation, so it is not an error.
            print(f"loading base model {path} from the hub")
            self._model = AutoModelForCausalLM.from_pretrained(
                str(path), **load_kwargs)
            tok_src = path
        else:
            raise InferenceError(
                f"{path} not found — train and merge first, or use "
                f"--backend ollama to review against a served model"
            )
        self._tokenizer = AutoTokenizer.from_pretrained(str(tok_src))
        self._model.config.use_cache = True
        self._model.eval()

    def _generate_local(self, messages: list[dict],
                        temperature: float | None = None) -> str:
        self._load()
        import torch

        text = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
        inputs = self._tokenizer(text, return_tensors="pt").to(self._model.device)
        with torch.inference_mode():
            out = self._model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                # Greedy. A defect verdict should be reproducible, and sampling
                # only adds ways to produce invalid JSON.
                do_sample=(temperature if temperature is not None
                           else TEMPERATURE) > 0,
                **({"temperature": temperature if temperature is not None
                    else TEMPERATURE}
                   if (temperature if temperature is not None else TEMPERATURE) > 0
                   else {}),
                use_cache=True,
                pad_token_id=self._tokenizer.pad_token_id
                or self._tokenizer.eos_token_id,
            )
        return self._tokenizer.decode(
            out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    # --- ollama ------------------------------------------------------------
    def _generate_ollama(self, messages: list[dict],
                         temperature: float | None = None) -> str:
        import requests

        try:
            resp = requests.post(
                f"{self.ollama_host}/api/chat",
                json={"model": self.ollama_model, "messages": messages,
                      "stream": False, "format": "json",
                      # num_ctx must be explicit: Ollama silently truncates to
                      # its default otherwise, and a context-carrying prompt is
                      # exactly what overflows it.
                      "options": {"temperature": (temperature
                                                  if temperature is not None
                                                  else TEMPERATURE),
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
        from llm_explainer.context import gather

        ctx = gather(repo, rev, with_snapshots=with_context)
        if not ctx.diff.strip():
            raise InferenceError(f"{rev} has no diff to review")

        # Measure what is actually sent, not the plain diff. `-U60` expansion
        # routinely triples a diff, so deciding on `ctx.diff` let exactly the
        # commits that balloon skip chunking and arrive as one oversized prompt
        # - a 2.9kB diff reaching the GPU as 21kB and OOMing it.
        payload = ctx.expanded_diff or ctx.diff
        parts = split_diff(payload)
        if len(payload) > CHUNK_OVER_CHARS and len(parts) > 1:
            return self._analyze_chunked(
                parts, ctx.subject, retries, progress,
                snapshots=ctx.snapshots if with_context else {})

        # Same context-shedding fallback the per-file path gets. A single-file
        # commit can carry a 6kB snapshot and OOM just as easily, and shedding
        # context beats handing the user a 500.
        self._degraded = []
        context = ctx.context_block() if with_context else ""
        fw = ctx.framework_block() if with_context else ""
        return self._analyze_with_fallback(
            payload, ctx.subject, ", ".join(ctx.files), retries,
            "\n".join(b for b in (context, fw) if b))

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
                # Bound it here too: the whole-commit path applies a budget, the
                # per-file path used to hand over the entire snapshot.
                if len(file_context) > CONTEXT_MAX_CHARS:
                    file_context = (file_context[:CONTEXT_MAX_CHARS]
                                    + "\n... [context truncated] ...\n")
                file_context = f"--- {path} (after this commit) ---\n{file_context}"
            # The definitions this file calls into may live in a sibling chunk.
            # Without them a call site is judged on faith, and the model guesses.
            siblings = sibling_context(path, part, parts, CONTEXT_MAX_CHARS // 2)
            if siblings:
                file_context = (file_context + "\n" + siblings if file_context
                                else siblings)
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
        """One review. With INFERENCE_SAMPLES > 1, several, kept by agreement."""
        if INFERENCE_SAMPLES > 1:
            return self._analyze_consensus(diff, subject, files, retries, context)
        return self._analyze_single(diff, subject, files, retries, context)

    def _analyze_consensus(self, diff: str, subject: str, files: str,
                           retries: int, context: str) -> Analysis:
        """Answer N times, keep findings a majority agrees on.

        A model that writes prose can invent a defect fluently and only once.
        Sampling several times and requiring agreement removes exactly that -
        the failure mode a probability-only model cannot have, and the one that
        makes a reviewer untrustworthy.
        """
        from collections import Counter

        analyses = []
        last: InferenceError | None = None
        for i in range(INFERENCE_SAMPLES):
            try:
                analyses.append(self._analyze_single(
                    diff, subject, files, retries, context,
                    temperature=0.0 if i == 0 else INFERENCE_SAMPLE_TEMPERATURE))
            except InferenceError as e:
                last = e
                continue
        if not analyses:
            # Without the cause this reads as a model problem when it is
            # usually a transport one - a stopped server and unparseable JSON
            # produced the same message.
            raise InferenceError(
                f"no valid answer in {INFERENCE_SAMPLES} samples; last error: "
                f"{last}")
        if len(analyses) == 1:
            return analyses[0]

        votes = max(1, len(analyses) // 2 + 1)
        counts = Counter(f.category for a in analyses for f in a.findings)
        keep = {c for c, n in counts.items() if n >= votes}
        merged, seen = [], set()
        for a in analyses:
            for f in a.findings:
                if f.category in keep and f.category not in seen:
                    seen.add(f.category)
                    merged.append(f)
        summary = next((a.summary for a in analyses
                        if bool(a.findings) == bool(merged)), analyses[0].summary)
        dropped = len(counts) - len(keep)
        if dropped > 0:
            summary += (f" ({dropped} finding(s) appeared in a minority of "
                        f"{len(analyses)} samples and were dropped.)")
        return Analysis(summary=summary, findings=merged)

    def _render(self, diff: str) -> str:
        """Render the diff the way the served checkpoint was TRAINED to see it.

        Every path into the model goes through here - TUI, `main.py analyze`,
        `analyze_commit`, TestJIT's score.py - so the rendering cannot drift
        between them. It drifted for two days: the TUI sent unified diffs to a
        word-diff-trained checkpoint, which is the mismatch that cost the one
        real defect in the TestJIT pyalgo history.

        `dataset_builder.worddiff` is deliberately the only renderer used. git's
        own `--word-diff` disagrees with it on 24% of cases and is NOT what the
        corpora were built with, so reaching for git here would swap one
        mismatch for a subtler one.
        """
        mode = str(DIFF_RENDERING).lower()
        if mode == "auto":
            mode = "word" if OUTPUT_CONTRACT in ("v2", "v3") else "unified"
        if mode != "word":
            return diff
        if _already_word_diff(diff):
            # `basic_bench.py --word-diff-module` renders before it calls us, so
            # without this the benchmark would render TWICE. That is not a
            # harmless no-op: to_word_diff is NOT idempotent - a second pass eats
            # a space of indentation - so it would have silently changed every
            # benchmark number rather than failing loudly.
            return diff
        try:
            return to_word_diff(diff)
        except Exception:
            # A renderer that throws must not take the review with it; an
            # un-rendered answer is worth more than no answer.
            return diff

    def _analyze_single(self, diff: str, subject: str = "", files: str = "",
                        retries: int = 1, context: str = "",
                        temperature: float | None = None) -> Analysis:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(
                self._render(diff), subject, files, max_diff_chars=MAX_DIFF_CHARS,
                context=context, include_schema=self.include_schema)},
        ]
        last: Exception | None = None
        for attempt in range(retries + 1):
            raw = (self._generate_ollama(messages, temperature)
                   if self.backend == "ollama"
                   else self._generate_local(messages, temperature))
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

    # A hub id is a baseline to load, not a missing directory; and it gets the
    # full schema, because it never saw the short form in training.
    stock = OracleClient(model_path="Qwen/Qwen2.5-Coder-3B-Instruct",
                         backend="transformers")
    assert stock.is_hub_id and stock.include_schema
    missing = OracleClient(model_path="artifacts/nope", backend="transformers")
    assert not missing.is_hub_id and missing.include_schema
    assert OracleClient(backend="ollama").include_schema
    print(f"json recovery + diff splitting ok ({len(parts)} chunks)")


if __name__ == "__main__":
    _selftest()
    main()
