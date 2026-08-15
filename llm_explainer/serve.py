"""Serve the fine-tuned model over HTTP, so the TUI can run anywhere.

The point is to keep the heavy half on the machine with the GPU and the light
half - the TUI, git, the gatekeeper - on the laptop:

    # on the GPU box
    python -m llm_explainer.serve --host 0.0.0.0 --port 8111

    # on the laptop
    ORACLE_BACKEND=ollama ORACLE_OLLAMA_HOST=http://192.168.1.170:8111 \
        python main.py tui --repo /path/to/repo

It speaks the same `/api/chat` shape the Ollama client already sends, so nothing
in `client.py` needs to know the difference.

Why not Ollama itself: converting the merged model to GGUF produced a model that
answers in tokens that decode to `?`. The weights are fine under transformers -
the conversion is what breaks, and this avoids it entirely.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BASE_MODEL, MAX_NEW_TOKENS, MERGED_MODEL_DIR, TEMPERATURE

_STATE: dict = {}


def load_model(model_path: Path, four_bit: bool = True):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    # SDPA, not eager: eager attention materialises the full n x n matrix, so a
    # 6k-token prompt tried to allocate 17GB on a 6GB card and 500'd. SDPA uses
    # the fused kernel and stays flat in memory.
    kwargs = {"dtype": torch.float16, "device_map": "auto",
              "attn_implementation": "sdpa"}
    if four_bit and torch.cuda.is_available():
        from transformers import BitsAndBytesConfig

        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16)

    print(f"loading {model_path} …", flush=True)
    started = time.time()
    # A training checkpoint is a LoRA adapter, not a merged model. Serving one
    # directly is how you test the run you just finished without first writing
    # 5.8GB of merged weights you may not keep.
    if (model_path / "adapter_config.json").exists():
        from peft import AutoPeftModelForCausalLM

        model = AutoPeftModelForCausalLM.from_pretrained(str(model_path), **kwargs)
        tok_src = (model_path if (model_path / "tokenizer_config.json").exists()
                   else BASE_MODEL)
    else:
        model = AutoModelForCausalLM.from_pretrained(str(model_path), **kwargs)
        tok_src = model_path
    model.config.use_cache = True
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(str(tok_src))
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    where = next(model.parameters()).device
    print(f"loaded in {time.time() - started:.1f}s on {where}", flush=True)
    return model, tokenizer


def generate(messages: list[dict], max_new_tokens: int) -> str:
    import torch

    model, tokenizer = _STATE["model"], _STATE["tokenizer"]
    text = tokenizer.apply_chat_template(messages, tokenize=False,
                                         add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        out = model.generate(
            **inputs, max_new_tokens=max_new_tokens,
            do_sample=TEMPERATURE > 0,
            **({"temperature": TEMPERATURE} if TEMPERATURE > 0 else {}),
            use_cache=True,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id)
    return tokenizer.decode(out[0][inputs["input_ids"].shape[1]:],
                            skip_special_tokens=True)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's naming
        if self.path.rstrip("/") in ("/api/tags", "/api/version"):
            self._send(200, {"models": [{"name": _STATE["name"]}],
                             "version": "oracle-serve"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") != "/api/chat":
            self._send(404, {"error": "only /api/chat is served"})
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as e:
            self._send(400, {"error": f"bad JSON: {e}"})
            return

        messages = req.get("messages") or []
        if not messages:
            self._send(400, {"error": "no messages"})
            return
        budget = int((req.get("options") or {}).get("num_predict", MAX_NEW_TOKENS))

        started = time.time()
        try:
            content = generate(messages, budget)
        except Exception as e:  # a bad request must not kill the server
            import torch

            if "out of memory" in str(e).lower():
                # Free the fragments before the next request inherits them.
                torch.cuda.empty_cache()
                chars = sum(len(m.get("content", "")) for m in messages)
                self._send(500, {"error": (
                    f"prompt too large for this GPU ({chars} chars). Lower "
                    f"ORACLE_CONTEXT_MAX_CHARS / ORACLE_FULL_FILE_MAX_CHARS.")})
                return
            self._send(500, {"error": f"{type(e).__name__}: {e}"})
            return
        took = time.time() - started
        print(f"  {self.client_address[0]} -> {len(content)} chars in {took:.1f}s",
              flush=True)
        self._send(200, {"model": _STATE["name"], "done": True,
                         "message": {"role": "assistant", "content": content},
                         "total_duration": int(took * 1e9)})

    def log_message(self, *_args):
        pass  # the handler prints what matters


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", type=Path, default=Path(MERGED_MODEL_DIR))
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8111)
    ap.add_argument("--no-4bit", dest="four_bit", action="store_false")
    args = ap.parse_args(argv)

    if not args.model.exists():
        raise SystemExit(f"{args.model} not found — train and merge first")

    _STATE["model"], _STATE["tokenizer"] = load_model(args.model, args.four_bit)
    _STATE["name"] = args.model.name

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"serving {args.model.name} on http://{args.host}:{args.port}/api/chat\n"
          f"point a client at it with:\n"
          f"  ORACLE_BACKEND=ollama ORACLE_OLLAMA_HOST=http://<this-host>:{args.port} "
          f"ORACLE_OLLAMA_MODEL={args.model.name}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
