"""Package the ORACLE reviewer as an Ollama model (default name: qwen2.5-oracle).

Two modes:

  --prompt-only   Bake the ORACLE system prompt and decoding params onto an
                  existing Ollama model. No training, no torch, seconds to run.
                  The weights are stock; only the prompt is baked in.

  (default)       Merge the DPO LoRA adapter into the base weights and import
                  the result. Needs torch + peft and a finished training run.

    python dpo_pipeline/publish_ollama.py --prompt-only --from qwen2.5-coder:7b
    python dpo_pipeline/publish_ollama.py --adapter artifacts/dpo-adapter
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run as a script

from config import (
    DPO_BASE_MODEL,
    OLLAMA_HOST,
    DPO_OUTPUT_DIR,
    LLM_NUM_CTX,
    LLM_TEMPERATURE,
    OLLAMA_MODEL,
    ROOT,
)
from llm_explainer.prompts import SYSTEM_PROMPT

MERGED_DIR = ROOT / "artifacts" / "oracle-merged"


def write_modelfile(source: str, path: Path) -> Path:
    """Modelfile pinning the ORACLE prompt and low-variance decoding."""
    path.write_text(
        f'FROM {source}\n\n'
        f'PARAMETER temperature {LLM_TEMPERATURE}\n'
        f'PARAMETER num_ctx {LLM_NUM_CTX}\n'
        f'PARAMETER top_p 0.9\n'
        f'PARAMETER repeat_penalty 1.0\n\n'
        f'SYSTEM """{SYSTEM_PROMPT.strip()}"""\n'
    )
    return path


def merge_adapter(adapter: Path, base_model: str, out: Path) -> Path:
    """Fold the LoRA delta into the base weights and save as safetensors."""
    import torch
    from peft import AutoPeftModelForCausalLM
    from transformers import AutoTokenizer

    if not adapter.exists():
        raise SystemExit(
            f"{adapter} not found - train first:\n"
            f"  python dpo_pipeline/dataset_builder.py --input data/reviews.jsonl\n"
            f"  python dpo_pipeline/train_dpo.py"
        )

    print(f"merging {adapter} into {base_model} (this loads the full base model)")
    model = AutoPeftModelForCausalLM.from_pretrained(
        str(adapter), dtype=torch.float16, device_map="cpu"
    )
    merged = model.merge_and_unload()
    out.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(out), safe_serialization=True)
    AutoTokenizer.from_pretrained(base_model).save_pretrained(str(out))
    print(f"merged weights -> {out}")
    return out


def ollama_create(name: str, modelfile: Path, quantize: str | None) -> None:
    if not shutil.which("ollama"):
        raise SystemExit("ollama not on PATH")
    cmd = ["ollama", "create", name, "-f", str(modelfile)]
    if quantize:
        cmd += ["-q", quantize]
    # The CLI talks to whichever server OLLAMA_HOST points at, which is where
    # the model gets registered - not necessarily this machine.
    env = {**os.environ, "OLLAMA_HOST": OLLAMA_HOST}
    print(f"OLLAMA_HOST={OLLAMA_HOST} " + " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default="qwen2.5-oracle", help="Ollama model name to create")
    ap.add_argument("--prompt-only", action="store_true",
                    help="bake the prompt onto an existing Ollama model, no training")
    ap.add_argument("--from", dest="source", default=OLLAMA_MODEL,
                    help="base Ollama model for --prompt-only")
    ap.add_argument("--adapter", type=Path, default=Path(DPO_OUTPUT_DIR))
    ap.add_argument("--base-model", default=DPO_BASE_MODEL)
    ap.add_argument("--merged-dir", type=Path, default=MERGED_DIR)
    ap.add_argument("--quantize", default=None,
                    help="quantise on import, e.g. q4_K_M (merged mode only)")
    ap.add_argument("--dry-run", action="store_true", help="write the Modelfile, do not create")
    args = ap.parse_args(argv)

    if args.prompt_only:
        source, quantize = args.source, None
    else:
        source = str(merge_adapter(args.adapter, args.base_model, args.merged_dir))
        quantize = args.quantize

    modelfile = write_modelfile(source, ROOT / "artifacts" / f"Modelfile.{args.name}")
    print(f"Modelfile -> {modelfile}")
    if args.dry_run:
        return
    ollama_create(args.name, modelfile, quantize)
    print(f"\ndone. use it:\n  python main.py analyze --mock --llm-model {args.name}")


if __name__ == "__main__":
    main()
