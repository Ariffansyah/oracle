# ORACLE

An **end-to-end instruction-tuned code LLM** for Just-In-Time (JIT) defect
prediction. No classifier, no feature engineering: a single model reads a commit
diff and answers with a structured verdict.

```json
{
  "summary": "Removes the lock around the emptiness check and pop.",
  "findings": [
    {
      "category": "concurrency",
      "explanation": "Two workers can both pass the empty check and pop, raising IndexError."
    }
  ]
}
```

Traditional JIT models (Kamei, Commit Guru, DeepJIT, JITLine) rank commits by
process metrics — churn, author experience, file history — and output a
probability. A probability cannot be acted on: nobody fixes `la = 412`. ORACLE
reformulates the task as **defect explanation with a structured output**, and
trains a model specifically for it.

## Two-stage training

```
  Qwen2.5-Coder-7B-Instruct  (base)
             │
             │  stage 1 — SFT (QLoRA, 4-bit)
             │  teaches the task and the output format
             ▼
       artifacts/sft-adapter
             │
             │  stage 2 — DPO (QLoRA, same adapter)
             │  teaches restraint: silence on safe code,
             │  findings on real defects
             ▼
       artifacts/dpo-adapter ──merge──► artifacts/oracle-merged
                                              │
                                              ▼
                                   llm_inference/client.py
                                              │
                                              ▼
                                        ui/tui_app.py
```

**Why two stages.** SFT alone produces a model that answers in the right shape
but over-reports — given churn, a rename or an added guard it manufactures a
plausible-sounding defect, because every SFT target it saw was a confident
answer. Over-reporting is a *behavioural* failure, not a formatting one, and
preference optimisation is what fixes behaviour. The DPO set is therefore
two-sided: pairs that prefer an empty `findings` list over an invented defect,
and pairs that prefer a real finding over false reassurance. Train on the first
kind alone and you get a model that has learnt to say nothing.

### DPO-Positive, and why `beta = 0.5`

`DPO_LOSS_TYPE = "dpop"`, `DPO_BETA = 0.5`.

The hardest pairs in the set are frontend security guards — a Cloudflare
Turnstile check, a CSRF header, an auth redirect — where `chosen` and `rejected`
describe *the same five lines* and disagree only about whether an early `return`
is a bug. Standard DPO maximises the *margin* between the two, and it is free to
achieve that by pushing the chosen log-probability down as long as the rejected
one falls faster. On small edit distances that is exactly what happens, and the
model degrades on the answers you wanted it to prefer.

DPO-Positive (Pal et al., 2024) adds a penalty term that keeps the chosen
log-probability from collapsing below the reference. `beta = 0.5` (rather than
the usual 0.1) holds the tuned model closer to that reference, which matters
when the corpus is small and the distinctions are narrow.

`train_dpo.py` checks the installed TRL actually supports the requested loss
before loading anything, and prints the supported list if it does not — an older
TRL has no `dpop` and would otherwise fail deep inside the trainer.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

The inference and UI layers need only `rich textual pydantic requests`. Torch,
transformers, trl, peft, datasets and bitsandbytes are needed to train — every
other command runs without them, and the training scripts exit with an install
hint rather than an ImportError.

## Pipeline

```bash
# 1. datasets (mock data is real, annotated, and trainable out of the box)
python main.py build-sft --mock --n 200
python main.py build-dpo --mock --n 120        # + Turnstile false-positive pairs

# 2. train
python main.py train-sft                     # QLoRA SFT
python main.py train-dpo --merge             # DPO, then merge weights

# 3. run
python main.py analyze --diff-file bug.patch
python main.py tui --repo /path/to/repo
```

Real data instead of mocks:

```bash
python main.py build-sft --csv data/commits.csv      # hash, diff, label
python main.py build-sft --jsonl data/commits.jsonl  # {diff, buggy, analysis?}
python main.py build-dpo --reviews data/reviews.jsonl
```

The SFT builder rejects a CSV with no `diff` column — ORACLE trains on code, so
a metrics-only corpus (ApacheJIT's default export) is not usable without
fetching the diffs first.

## The TUI

```bash
python main.py tui --repo /path/to/repo     # or --mock for demo commits
```

Left: commits from `git log`, marked `✓` clean / `N✗` findings once analyzed.
Middle: the syntax-highlighted diff. Right: the model's analysis, one entry per
finding with severity colouring.

| key | action |
| --- | --- |
| `a` | analyze the selected commit |
| `j` / `k` | next / previous commit |
| `s` | hide or show the commit list |
| `c` / `e` / `y` | copy diff / analysis / full report |
| `w` | write the report to `oracle-<sha>.txt` |
| `:` | command mode |
| `r`, `q` | reload, quit |

### `:` commands

Vim-style. `:` opens the line, enter runs, escape cancels, `:help` lists
everything. Settings change for the running session — no restart to try another
model or repository.

| command | does |
| --- | --- |
| `:model <name>` | switch the reviewer model (`:m` for short) |
| `:backend <transformers\|ollama>` | switch inference backend |
| `:repo <path>` | load another repository |
| `:limit <n>` | how many commits to list |
| `:context <on\|off>` | send full-file context, or review the bare diff |
| `:numctx <tokens>` | model context window |
| `:goto <n\|sha>` | jump to a commit by number or sha prefix |
| `:analyze` | analyze the current commit (`:a`) |
| `:copy [diff\|analysis\|all]` | copy to clipboard |
| `:write [path]` | write the report to a file |
| `:info` | show current settings |
| `:help` | list commands |
| `:quit` | exit (`:q`) |

`:context off` is the ablation switch: it reviews the diff with no surrounding
code, which is how you measure whether context is actually earning its tokens.

Inference runs on a worker thread, so a slow model never freezes the UI. Copy
goes out over OSC 52 *and* a native helper (`wl-copy`, `xclip`, `xsel`) when one
exists, because terminals disagree about which they honour. Textual owns the
mouse, so hold **Shift** while dragging for your terminal's own selection.

## Backends

```bash
python main.py analyze --backend transformers --model artifacts/oracle-merged
python main.py analyze --backend ollama       # served GGUF build
```

`transformers` loads local weights — a merged directory, a PEFT adapter, or the
base model. `ollama` talks to a served build over HTTP, which is how you run the
same model on another machine, and how the UI stays testable before any training
has happened.

Both paths validate against the same `Analysis` schema and both recover JSON
from fenced or prose-wrapped output.

## Configuration

Every value in `config.py` is overridable with an `ORACLE_` prefix:

```bash
ORACLE_BASE_MODEL=Qwen/Qwen2.5-Coder-1.5B-Instruct python main.py train-sft
ORACLE_BACKEND=ollama ORACLE_OLLAMA_HOST=http://192.168.1.170:11434 python main.py tui --mock
```

| key | default |
| --- | --- |
| `ORACLE_BASE_MODEL` | `Qwen/Qwen2.5-Coder-7B-Instruct` |
| `ORACLE_LORA_R` / `ORACLE_LORA_ALPHA` | `16` / `32` |
| `ORACLE_LOAD_IN_4BIT` | `true` |
| `ORACLE_SFT_LR` / `ORACLE_DPO_LR` | `2e-4` / `5e-6` |
| `ORACLE_DPO_BETA` | `0.5` |
| `ORACLE_DPO_LOSS_TYPE` | `dpop` |
| `ORACLE_BACKEND` | `ollama` |

LoRA targets `q_proj, k_proj, v_proj, o_proj` at r=16, alpha=32, 4-bit NF4 with
double quantisation. The learning rates differ by two orders of magnitude on
purpose: LoRA SFT tolerates 2e-4, while preference tuning at that rate destroys
the reference behaviour.

## Layout

```
config.py                          all configuration, ORACLE_ overridable
main.py                            CLI: build-sft, build-dpo, train-sft, train-dpo, analyze, tui
dataset_builder/schema.py          the Analysis contract + system prompt
dataset_builder/mock_data.py       annotated synthetic commits (6 defect classes, 4 safe traps)
dataset_builder/frontend_cases.py  Turnstile / auth-guard false positives for DPO
dataset_builder/build_sft_data.py  → conversational JSONL
dataset_builder/build_dpo_data.py  → {prompt, chosen, rejected}
fine_tuning/qlora.py               shared 4-bit + LoRA setup, adapter merge
fine_tuning/train_sft.py           TRL SFTTrainer
fine_tuning/train_dpo.py           TRL DPOTrainer, continues from the SFT adapter
llm_inference/client.py            transformers | ollama, strict JSON parsing
ui/tui_app.py                      three-pane Textual UI
ui/commands.py                     `:` command mode, parsed and tested standalone
llm_inference/context.py           git context retrieval (-U50, file snapshots)
docs/METHODS.md                    plain-language explanation of every method
legacy/                            the previous XGBoost + SHAP implementation
```

Every module has a `__main__` self-check:

```bash
python -m dataset_builder.schema        # schema round-trip
python -m dataset_builder.mock_data     # corpus balance
python -m dataset_builder.frontend_cases # captcha cases well-formed
python -m dataset_builder.build_sft_data --mock
python -m dataset_builder.build_dpo_data --mock
python -m fine_tuning.qlora             # LoRA config sanity, no torch needed
python -m ui.commands                   # `:` command parsing and error handling
python -m llm_inference.context         # git context retrieval, on a temp repo
python -m llm_inference.client --backend ollama
```

## Understanding the method

[`docs/METHODS.md`](docs/METHODS.md) explains every part of the pipeline in plain
language — what it does, why it exists, and which gap in the earlier JIT research
it covers. Start there if the design decisions look arbitrary.

## Known limits

* **The mock corpus is templated.** Six defect classes and four safe patterns
  with varying line numbers. It is enough to verify the pipeline trains and the
  format holds; it is not enough to produce a good reviewer. Real training needs
  real diffs with real annotations.
* **SFT targets need annotations, not labels.** A corpus with only `buggy`/`clean`
  flags trains the model to assert a verdict without a reason — `build_sft_data`
  falls back to that and says so. Distil explanations from a stronger teacher
  model for anything beyond a smoke test.
* **bitsandbytes 4-bit is CUDA-only.** On CPU, pass `--no-4bit` and expect to
  need a small base model (1.5B) and patience.
* **`legacy/`** holds the previous two-stage design (XGBoost risk model + SHAP +
  a general LLM reviewer), including an ApacheJIT loader with effort-aware
  metrics (Popt, PofB20, IFA) if you want the statistical baseline back for
  comparison.
