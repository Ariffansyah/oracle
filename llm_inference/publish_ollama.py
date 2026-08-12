"""Register the reviewer as a named Ollama model.

    python -m llm_inference.publish_ollama --prompt-only --from qwen2.5-coder:14b
    python -m llm_inference.publish_ollama --merged artifacts/oracle-merged

`--prompt-only` bakes the ORACLE system prompt and decoding params onto an
existing model: seconds, no training, stock weights. It reserves the name and
gives any client the reviewer behaviour, but it is not a fine-tune.

Without it, the merged fine-tuned weights are imported instead - that is the
real ORACLE model, and it replaces the same name so anything pointed at it
upgrades in place.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (ARTIFACTS, MERGED_MODEL_DIR, OLLAMA_HOST, OLLAMA_MODEL,
                    TEMPERATURE)
from dataset_builder.schema import SYSTEM_PROMPT

DEFAULT_NAME = "qwen2.5-review"


def write_modelfile(source: str, path: Path, num_ctx: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"FROM {source}\n\n"
        f"PARAMETER temperature {TEMPERATURE}\n"
        f"PARAMETER num_ctx {num_ctx}\n"
        f"PARAMETER top_p 0.9\n"
        f"PARAMETER repeat_penalty 1.0\n\n"
        f'SYSTEM """{SYSTEM_PROMPT.strip()}"""\n'
    )
    return path


def ollama_create(name: str, modelfile: Path, host: str,
                  quantize: str | None = None) -> None:
    if not shutil.which("ollama"):
        raise SystemExit("ollama not on PATH")
    cmd = ["ollama", "create", name, "-f", str(modelfile)]
    if quantize:
        cmd += ["-q", quantize]
    # The model registers on whichever server OLLAMA_HOST points at, which is
    # not necessarily this machine.
    print(f"OLLAMA_HOST={host} " + " ".join(cmd))
    subprocess.run(cmd, check=True, env={**os.environ, "OLLAMA_HOST": host})


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default=DEFAULT_NAME)
    ap.add_argument("--prompt-only", action="store_true",
                    help="bake the prompt onto a served model, no training")
    ap.add_argument("--from", dest="source", default=OLLAMA_MODEL,
                    help="base model for --prompt-only")
    ap.add_argument("--merged", type=Path, default=Path(MERGED_MODEL_DIR),
                    help="merged fine-tuned weights to import")
    ap.add_argument("--host", default=OLLAMA_HOST)
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--quantize", default=None, help="e.g. q4_K_M (merged only)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.prompt_only:
        source, quantize = args.source, None
        print(f"prompt-only: stock {source} weights + the ORACLE system prompt")
    else:
        if not args.merged.exists():
            raise SystemExit(
                f"{args.merged} not found — train and merge first:\n"
                f"  python main.py train-sft\n"
                f"  python main.py train-dpo --merge\n"
                f"or pass --prompt-only to bake the prompt onto a served model."
            )
        source, quantize = str(args.merged), args.quantize

    modelfile = write_modelfile(source, ARTIFACTS / f"Modelfile.{args.name}",
                                args.num_ctx)
    print(f"Modelfile -> {modelfile}")
    if args.dry_run:
        return
    ollama_create(args.name, modelfile, args.host, quantize)
    print(f"\ndone:\n"
          f"  ORACLE_OLLAMA_MODEL={args.name} python main.py analyze\n"
          f"  ORACLE_OLLAMA_MODEL={args.name} python main.py tui --repo .")


if __name__ == "__main__":
    main()
