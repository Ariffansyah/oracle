# ORACLE

**Predict, then explain.** A two-stage pipeline for Just-In-Time (JIT) defect
prediction: a gate classifier turns a commit into a *risk score*, and an
instruction-tuned code LLM turns the commits worth reading into
*natural-language findings*.

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

## The pipeline

```
  commit ──► stage 1: gate ──► risk score ──► stage 2: explainer ──► findings
             LightGBM on            0..1        Qwen2.5-Coder-3B     category +
             embeddings +                       QLoRA, tuned for     explanation
             process metrics                    this task
```

**Stage 1 detects.** `ml_model/gate.py`, 7989 ApacheJIT commits, chronological
80/20 split, test n=1598 at 95% target recall:

| variant | AUC | PR-AUC | LLM calls saved |
|---|---|---|---|
| counting baseline | 0.638 | 0.363 | — |
| process metrics only (the 2013 baseline) | 0.777 | 0.660 | 20.4% |
| **embeddings + metrics** | **0.822** | **0.699** | 28.2% |

Reading the code adds +0.045 AUC over process metrics alone, and the stack
clears the counting baseline by +0.184. This is where the *prediction* in
"JIT defect prediction" actually lives.

**Stage 2 explains.** The tuned 3B emits a structured finding per defect and
grounds it in the diff (99.1% grounded, against 80.7% for the stock base
model). What it does *not* do is detect out of distribution: on CVEfixes its
separation is −4.2pp, statistically indistinguishable from chance. Each
component is used where it measures well, and neither claim leans on the other.

**The gate's verdict is never put into the explainer's prompt.** Telling a model
the answer and then scoring its agreement is how `corpus/label.py` produced a
teacher with recall 1.00 and zero false negatives — a number that was true by
construction. The gate selects *who* gets an LLM call; the explainer reaches its
own verdict, and the disagreement rate between the two is itself a measurement.

## The name

Not an acronym. A **test oracle** is the part of a testing system that decides
whether a program's observed behaviour is correct — the component that supplies
the verdict everything else is measured against. That is the job here: read a
commit, decide whether it carries a defect, and say what the defect is.

The name is also a standing reminder of the failure mode this project keeps
catching in itself. An oracle is only worth having if its verdict is checkable.
Every label in `bench/` is proved by executing the code rather than inferred
from SZZ, and every number in `docs/RESULTS.md` ships with the command that
reproduces it, for that reason.

## Training the explainer, in two stages

```
  Qwen2.5-Coder-3B-Instruct  (base)
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
                                   llm_explainer/client.py
                                              │
                                              ▼
                                        ui/tui_app.py
```

**Why two training stages.** SFT alone produces a model that answers in the right shape
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

## Evaluation

```bash
python evaluate.py --model artifacts/sft-adapter/checkpoint-220   # a checkpoint
python evaluate.py --model Qwen/Qwen2.5-Coder-3B-Instruct         # the baseline
python evaluate.py --compare data/eval_sft220.jsonl data/eval_stock.jsonl
```

Five measures against `data/labelled_heldout.jsonl` — valid JSON, detection
P/R/F1 against the SZZ label, grounding, category match against the teacher, and
fix agreement where a repair diff is available. `--model` takes a local adapter,
a merged directory, or a hub id: an untrained base model is the baseline the
tuned one has to beat, so it is a supported target rather than a missing path.

The baseline gets the full JSON Schema in its prompt and the tuned model does
not, because that is what each was built for — the tuned model learnt the format
from a schema-free prompt, and handing a stock model a prompt that never names
the fields measures the prompt instead of the model.

Reviews run unchunked here. The teacher labelled each commit in one prompt and
the SFT targets were built the same way; scoring a per-file review against those
labels would measure the chunker.

### On-policy DPO

```bash
python -m dpo_pipeline.build_dpo_data --from-eval data/eval_sft220.jsonl
```

Preference pairs built from the tuned model's own errors on held-out commits:
the teacher's analysis is the chosen side, the sentence the model actually
produced is the rejected one. That is the point of going on-policy — the
rejection is real output rather than a hallucination written by hand.

A commit counts as an error only when SZZ and the teacher agree about it. They
agree on roughly seven in eight; on the eighth "wrong" is not established, and a
pair built on a disputed label teaches the disagreement. Missed defects are
included alongside false positives by default, for the reason above: a set that
only ever prefers the empty answer teaches silence. `--no-misses` drops them.

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
| `ORACLE_BASE_MODEL` | `Qwen/Qwen2.5-Coder-3B-Instruct` |
| `ORACLE_LORA_R` / `ORACLE_LORA_ALPHA` | `32` / `64` |
| `ORACLE_LOAD_IN_4BIT` | `true` |
| `ORACLE_SFT_LR` / `ORACLE_DPO_LR` | `2e-4` / `5e-6` |
| `ORACLE_DPO_BETA` | `0.5` |
| `ORACLE_DPO_LOSS_TYPE` | `dpop` |
| `ORACLE_BACKEND` | `ollama` |

LoRA targets all seven linear projections (`q/k/v/o_proj` plus
`gate/up/down_proj`) at r=32, alpha=64, 4-bit NF4 with double quantisation. The
MLP projections are included because format adherence lives there as much as in
attention. The learning rates differ by two orders of magnitude on purpose: LoRA
SFT tolerates 2e-4, while preference tuning at that rate destroys the reference
behaviour.

### Why 3B

The task is narrow — read a diff, emit one JSON verdict — and a small model
masters it once trained. That buys three things at once: it trains inside 6GB of
VRAM (7B was measured OOMing on a GTX 1660 SUPER *before the first step*), it
answers in well under a second, and it runs on the machine that wrote the code
rather than a server. Hyperparameters are sized for it: sequence 1024 (real
prompts measure 414 tokens median, 476 at p90), generation capped at 256 tokens
(answers measure 24 median, 60 max), greedy decoding so a verdict is
reproducible.

`ORACLE_BASE_MODEL=Qwen/Qwen2.5-Coder-1.5B-Instruct` halves memory and latency
again if you want it smaller still.

## Layout

```
config.py                          all configuration, ORACLE_ overridable
main.py                            CLI: build-sft, build-dpo, train-sft, train-dpo, analyze, tui
dataset_builder/schema.py          the Analysis contract + system prompt
dataset_builder/mock_data.py       annotated synthetic commits (6 defect classes, 4 safe traps)
dpo_pipeline/frontend_cases.py     Turnstile / auth-guard false positives for DPO
dataset_builder/build_sft_data.py  → conversational JSONL
dpo_pipeline/build_dpo_data.py     → {prompt, chosen, rejected}, incl. on-policy
evaluate.py                        score a reviewer on held-out commits
fine_tuning/qlora.py               shared 4-bit + LoRA setup, adapter merge
fine_tuning/train_sft.py           TRL SFTTrainer
fine_tuning/train_dpo.py           TRL DPOTrainer, continues from the SFT adapter
llm_explainer/client.py            transformers | ollama, strict JSON parsing
ui/tui_app.py                      three-pane Textual UI
corpus/fetch.py                    fetch real ApacheJIT diffs for training
ml_model/gate.py                   stage 1: LightGBM head, embeddings + metrics
ml_model/train_gate.py             train and ablate the gate (--ablate)
bench/basic_bench.py               executable benchmark, labels proved by running
ui/commands.py                     `:` command mode, parsed and tested standalone
llm_explainer/context.py           git context retrieval (-U50, file snapshots)
docs/METHODS.md                    plain-language explanation of every method
```

Every module has a `__main__` self-check:

```bash
python -m dataset_builder.schema        # schema round-trip
python -m dataset_builder.mock_data     # corpus balance
python -m dpo_pipeline.frontend_cases # captcha cases well-formed
python -m dataset_builder.build_sft_data --mock
python -m dpo_pipeline.build_dpo_data --mock
python -m fine_tuning.qlora             # LoRA config sanity, no torch needed
python -m ui.commands                   # `:` command parsing and error handling
python -m llm_explainer.context         # git context retrieval, on a temp repo
python -m llm_explainer.client --backend ollama
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
* **The gate scores; it does not explain.** An earlier revision ranked commits
  with XGBoost/CatBoost over the 14 process metrics alone, and that was removed:
  three boosters landed within 0.005 AUC of each other on ApacheJIT
  (0.862–0.867), which says the metrics were the ceiling rather than the
  algorithm. What replaced it reads the code — LightGBM over embeddings *plus*
  metrics, +0.045 AUC over metrics alone. A risk score still cannot be acted on
  by itself; that is the whole reason stage 2 exists.
* **The explainer cannot detect out of distribution.** Separation −4.2pp on
  CVEfixes, indistinguishable from chance, against 99.1% grounding. Do not read
  its verdict as a detector — that is stage 1's job.
