# ORACLE

**On-commit Risk And Code-Location Estimator**

### Predict, Then Point: From Just-In-Time Risk Scores to Natural-Language Defect Hints

A two-stage pipeline for Just-In-Time (JIT) defect prediction. A gate classifier
turns a commit into a *risk score*, and a small instruction-tuned code model
turns the commits worth reading into *a place to look and a test to run*.

```json
{
  "effect": {
    "trigger": "two workers popping from an empty queue at the same time",
    "check": "run two workers against a queue of length 1 and see whether either raises IndexError",
    "direction": "post-breaks",
    "confidence": "likely"
  },
  "summary": "This looks like a concurrency defect in worker.py. The lock around the emptiness check and the pop is gone, so the check no longer protects the pop. Worth confirming before this lands.",
  "findings": [
    {
      "category": "concurrency",
      "explanation": "Check whether two workers can both pass the empty test before either pops. If they can, the second pop is on an empty queue."
    }
  ]
}
```

Traditional JIT models (Kamei, Commit Guru, DeepJIT, JITLine) rank commits by
process metrics — churn, author experience, file history — and output a
probability. A probability cannot be acted on: nobody fixes `la = 412`. ORACLE
reformulates the task as **defect localisation with a structured, checkable
output**, and trains a model specifically for it.

## Why "point" and not "explain"

The second stage used to be asked for an explanation: what the program did
before the commit and what it does after, as concrete values. That is the wrong
question to ask a model that cannot run the code, and the cost is measurable.
Splitting every stored answer by the kind of claim it makes, across four
checkpoints and 101 executable cases:

| what the model is asked for | how often it is right |
|---|---|
| **where** — cite the code at fault | **87 – 98%** |
| **which way** — does the change break it or fix it | **79 – 93%** |
| **what exactly happens** — the concrete before/after value | **15 – 31%** |

The model knows where and which way. It does not know the value, and the
contract demanded one anyway, so it invented one: **69–85% of answers carried a
concrete claim that running the code contradicts.** In 90–99% of those the
answer was still pointing at the right code — a correct hint with a false
sentence bolted on.

Deleting the value costs nothing. The headline metric
(`bench/basic_bench.py:413`, `verdict_ok and (identified or not buggy)`) never
read it. So the `v3` output contract keeps `trigger` and `direction`, drops
`before`/`after`, and replaces them with **`check`** — the test that would
settle it, which *is* derivable from the diff — plus a **`confidence`** of
`likely` or `possible`.

An answer that says "this looks like an off-by-one at the boundary test; call it
with exactly 60" is useful when it is right and harmless when it is wrong. The
same content asserted as fact is a lie 4 times in 5.

**`check` only earns that if it is composed rather than recited.** The first
corpus built it from a ten-key dictionary keyed on the case's `category`, and
the corpus has two categories — so the field was two sentences with a filename
slot, plus a list of changed tokens. The model emitted one of them on 21 of 21
held-out cases. `check` is now written per case, beside the case, as a probe
("call `smallest([])` with an empty list") and a watch ("the `not nums` guard
that returned the default is gone, so check whether `min(nums)` raises
ValueError instead of returning a sentinel"). See
[`docs/RESULTS.md`](docs/RESULTS.md) for the measurement and
`bench/annotate_checks.py` for the annotations.

Hedging has its own failure mode, and it is the one to watch: a model that says
"maybe check everything" is never wrong and never useful. The guard is the
false-alarm rate on cases whose two sides are proved identical by execution. It
must not rise. See [`docs/PLAN_SUGGEST_CONTRACT.md`](docs/PLAN_SUGGEST_CONTRACT.md)
for the thresholds, fixed before training.

## The pipeline

```
  commit ──► stage 1: gate ──► risk score ──► stage 2: pointer ──► where + check
             LightGBM on            0..1        Qwen2.5-Coder-3B    location,
             embeddings +                       QLoRA, tuned for    direction,
             process metrics                    this task           suggested test
```

**Stage 1 detects.** `ml_model/gate.py`, 7989 ApacheJIT commits, chronological
80/20 split, test n=1598 at 95% target recall:

| variant | AUC | PR-AUC | LLM calls saved |
|---|---|---|---|
| counting baseline | 0.638 | 0.363 | — |
| process metrics only (the 2013 baseline) | 0.777 | 0.660 | 20.4% |
| **embeddings + metrics** | **0.822** | **0.699** | 28.2% |

Reading the code adds +0.045 AUC over process metrics alone, and the stack
clears the counting baseline by +0.184. This is where the *prediction* in "JIT
defect prediction" actually lives.

**Stage 2 points.** The tuned 3B names the construct at fault and the test that
would confirm it, grounded in the diff (99.1% grounded, against 80.7% for the
stock base model). What it does *not* do is detect out of distribution: on
CVEfixes its separation is −4.2pp, statistically indistinguishable from chance.
Each component is used where it measures well, and neither claim leans on the
other.

**The gate's verdict is never put into the pointer's prompt.** Telling a model
the answer and then scoring its agreement is how `corpus/label.py` produced a
teacher with recall 1.00 and zero false negatives — a number that was true by
construction. The gate selects *who* gets an LLM call; stage 2 reaches its own
verdict, and the disagreement rate between the two is itself a measurement.

## The name

**O**n-commit **R**isk **A**nd **C**ode-**L**ocation **E**stimator. The
expansion is also the scope statement: it estimates *risk* and *location*, and
deliberately does not estimate the value the program will print.

It is also a **test oracle** — the part of a testing system that decides whether
observed behaviour is correct, the component that supplies the verdict
everything else is measured against. That reading is a standing reminder of the
failure mode this project keeps catching in itself: an oracle is only worth
having if its verdict is checkable. Every label in `bench/` is proved by
executing the code rather than inferred from SZZ, and every number in
`docs/RESULTS.md` ships with the command that reproduces it, for that reason.

## Measuring whether the model reasons or recites

`bench/template_audit.py` measures how much of an answer is copied word for word
from the training corpus — the share of its prose sitting inside an 8-word
window that appears verbatim in a target.

Copying is only meaningful against a floor, so it is scored against checkpoints
that never saw the corpus. On `bench/basic`, 46 cases:

| checkpoint | saw this corpus | copied verbatim |
|---|---|---|
| `base44` (untuned) | no | **0.0%** |
| `gptoss120b`, `oracle46` | no | 0.3 – 0.8% |
| `mechanism_v2` | no | 13.0% |
| the v2 / v3 checkpoints | yes | **17.9 – 30.5%** |

A third of some answers is lifted text, against a 0.0% floor, with an 86-word
longest verbatim run. **Run this before believing any comparison between two
checkpoints.** A corpus-versus-corpus control does not work: two corpora in the
same family shared 78 of 80 records, which made a checkpoint look original
against training data it had memorised.

**The audit had a blind spot, and it cost a training run.** `template_audit.py`
scores `summary` + `findings[].explanation` and never read `effect.check` — so a
`check` field that was a per-category template in 97% of corpus targets was
invisible to the tool whose purpose is measuring templating, and a two-seed run
was launched on it. Two things close it:

```bash
python bench/template_audit.py --corpus <corpus> --with-check   # count check as prose
python bench/template_audit.py --corpus <corpus> --self         # corpus vs itself
python bench/check_field_audit.py --tags v4 v6 --pairs v4:v4_seed7
```

`--self` is leave-one-**case**-out: how much of a target is reachable verbatim
from *other cases*, with the whole upsampled family excluded. That is a property
of the corpus, knowable before a GPU is booked. `sft_v4_suggest` scored a median
of 54.6%; the rebuilt `sft_v6_suggest` scores 37.4%, with the longest shared span
down from 117 words to 62.

`check_field_audit.py` measures the field directly. Its sharpest column is
`distinct*` — the check with the filename and the trailing token list blanked,
leaving the sentence. Both v4 seeds score **1** on all 21 held-out mechanism
cases: one sentence, every case. Its control is cross-seed byte identity — two
independently trained seeds emitted the identical `check` on 13/21 of those
cases and the identical `summary` on 0/21.

Corpus pre-flight in `dataset_builder/build_sft_data.py` checks three things
the older validation could not see:

* the most repeated **sentence** across targets, not just whole duplicates — one
  corpus had 98 distinct targets in 399 rows and still put one sentence in 26%
  of them;
* targets naming a **source file absent from their own prompt** — unlearnable,
  so memorised, then emitted on unrelated cases;
* whole-target duplication, at a 10% bar rather than 20%.

## Training the model, in two stages

```
  Qwen2.5-Coder-3B-Instruct  (base)
             │
             │  stage 1 — SFT (QLoRA, 4-bit)
             │  teaches the task and the output contract
             ▼
       artifacts/sft-adapter
             │
             │  stage 2 — DPO (QLoRA, same adapter)
             │  teaches restraint: silence on safe code,
             │  a pointer on real defects
             ▼
       artifacts/dpo-adapter ──merge──► artifacts/oracle-merged
                                              │
                                              ▼
                                   llm_explainer/client.py
                                              │
                                              ▼
                                        ui/tui_app.py
```

**Why two training stages.** SFT alone produces a model that answers in the
right shape but over-reports — given churn, a rename or an added guard it
manufactures a plausible-sounding defect, because every SFT target it saw was a
confident answer. Over-reporting is a *behavioural* failure, not a formatting
one, and preference optimisation is what fixes behaviour. The DPO set is
therefore two-sided: pairs that prefer an empty `findings` list over an invented
defect, and pairs that prefer a real pointer over false reassurance. Train on
the first kind alone and you get a model that has learnt to say nothing.

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

### Two seeds, always

Seed alone moves 24 of 101 cases and the headline metric by 10. Every
single-seed comparison this project published before 28 Aug was therefore
unsupported, and `bench/compare_seeds.py` exists to stop that happening again:
a corpus effect is readable only where **both** seeds move the same way by more
than the spread the seed pair shows on its own.

The noise floor is per set, not global — `bench/clean_heldout` had zero flips
across a seed pair while `bench/mechanism_heldout` flipped 10 of 21. Do not read
a difference on a set that cannot resolve one.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

The inference and UI layers need only `rich textual pydantic requests`. Torch,
transformers, trl, peft, datasets and bitsandbytes are needed to train — every
other command runs without them, and the training scripts exit with an install
hint rather than an ImportError.

### The `oracle` command

```bash
pip install -e .            # installs the `oracle` entry point

oracle serve                # start the model server on the box + the tunnel
oracle                      # pick a repository and review it
oracle serve stop           # take the server and tunnel down
```

`oracle serve status` says whether each is up, and distinguishes a stopped
server from a box it cannot reach at all.

Plain `oracle` opens a **picker** before the reviewer starts: it lists the git
repositories under your home directory, identifies each one
(`TypeScript · Next.js · pnpm`), and proposes the commands that could establish
a baseline, best first. `e` edits the command, enter starts, `q` quits.

The picker exists because the run command decides what the reviewer can
observe, and it used to be chosen invisibly. A detected `pnpm run lint` cannot
start inside a worktree — pnpm verifies its dependency tree first and a linked
`node_modules` never satisfies that check — so the review measured the package
manager's complaint on both sides and refused to speak. That reads as a broken
model when it is a wrong setting, so the setting is now shown before anything
runs, and package scripts are resolved to the binary they invoke
(`./node_modules/.bin/eslint`) so the package manager is never in the way.

`--repo PATH` skips the picker; `--run CMD` skips detection as well.

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

The executable corpus, under the suggestion contract:

`sft_v6_suggest` supersedes `sft_v4_suggest` (whose `check` field was a
per-category template) and `sft_v5_suggest` (that field unchanged; built to fix
a token-trimming bug and never trained). The v4 file is kept because the
checkpoints trained on 30 Aug are only auditable against the corpus they saw.

```bash
ORACLE_OUTPUT_CONTRACT=v3 python dataset_builder/build_mechanism_corpus.py \
    --no-bulk --tokenizer Qwen/Qwen2.5-Coder-3B-Instruct \
    --max-seq-length 1152 --out data/sft_v6_suggest.jsonl

ORACLE_OUTPUT_CONTRACT=v3 python -m fine_tuning.train_sft \
    --dataset data/sft_v6_suggest.jsonl --max-seq-length 1152 --epochs 1 --seed 42
```

The builder prints a v3 pre-flight before it writes: distinct `check` strings,
unbalanced backticked identifiers, and `check_useful` scored against the
corpus's own targets. **Read it.** The v4 defect was in the file before the run
started and nothing printed it.

`--epochs 1`, not the default 2: `compare_seeds.py --base v4 v4_seed7 --new
v4_ep1 v4_ep1_seed7` returned "no" on every metric across all three sets, so the
second epoch moved nothing past seed noise and doubled the run.

`--max-seq-length 1152`, not the 1024 default. The v3 prompt is 662 tokens and
its answers run longer than v2's; at 1024 the fitter drops 43 records and every
one of them is a buggy case, which would leave the corpus 59% clean and train a
model biased toward silence. **Build and train at the same length** — training
at 1024 on a corpus fitted to 1152 re-truncates it.

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
python bench/basic_bench.py --backend ollama --model-name <served> \
    --host http://localhost:8111 --out data/basic_bench_<tag>.jsonl
python bench/basic_bench.py --score data/basic_bench_<tag>.jsonl   # re-grade, no GPU
python bench/compare_seeds.py                                      # with the noise band
python bench/template_audit.py --corpus <corpus> --tags <tags>     # copying vs a floor
```

`bench/` holds executable cases: each has a `pre` and a `post` that are actually
run, so a label is proved rather than inferred, and a behavioural claim is
gradable. Stored rows keep the full answer in `predicted`, so any scorer fix can
be replayed over past runs at no GPU cost — stored verdicts are never trusted,
only `predicted` is.

Scored metrics: verdict, **locus** (does it cite the code at fault), false
alarms on cases proved identical by execution, direction, and — under v3 —
whether the suggested `check` reaches the real defect, and whether `likely` is
right more often than `possible`.

```bash
python evaluate.py --model artifacts/sft-adapter/checkpoint-220   # a checkpoint
python evaluate.py --model Qwen/Qwen2.5-Coder-3B-Instruct         # the baseline
python evaluate.py --compare data/eval_sft220.jsonl data/eval_stock.jsonl
```

The baseline gets the full JSON Schema in its prompt and the tuned model does
not, because that is what each was built for — the tuned model learnt the format
from a schema-free prompt, and handing a stock model a prompt that never names
the fields measures the prompt instead of the model.

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
| `ORACLE_OUTPUT_CONTRACT` | `v1` — `v1` \| `v2` \| `v3` |
| `ORACLE_DIFF_RENDERING` | `auto` — word-diff under v2/v3, unified under v1 |
| `ORACLE_LORA_R` / `ORACLE_LORA_ALPHA` | `64` / `128` |
| `ORACLE_LOAD_IN_4BIT` | `true` |
| `ORACLE_SFT_LR` / `ORACLE_DPO_LR` | `2e-4` / `5e-6` |
| `ORACLE_DPO_BETA` | `0.5` |
| `ORACLE_DPO_LOSS_TYPE` | `dpop` |
| `ORACLE_BACKEND` | `ollama` |

`OUTPUT_CONTRACT` is one switch on purpose: the system prompt, the format hint
and the expected keys move together. A checkpoint scored under a contract it was
not trained on lost six cases in forty-six to that alone, so leave it at the
contract the checkpoint was trained on.

LoRA targets all seven linear projections (`q/k/v/o_proj` plus
`gate/up/down_proj`) at r=64, alpha=128, 4-bit NF4 with double quantisation. The
MLP projections are included because format adherence lives there as much as in
attention. The learning rates differ by two orders of magnitude on purpose: LoRA
SFT tolerates 2e-4, while preference tuning at that rate destroys the reference
behaviour.

### Why 3B

The task is narrow — read a diff, emit one JSON pointer — and a small model
masters it once trained. That buys three things at once: it trains inside 6GB of
VRAM (7B was measured OOMing on a GTX 1660 SUPER *before the first step*), it
answers in well under a second, and it runs on the machine that wrote the code
rather than a server. Greedy decoding, so a verdict is reproducible.

Sequence length is 1024 for v1/v2 and 1152 for v3; generation is capped at 768
tokens so a third finding is never truncated mid-sentence.

`ORACLE_BASE_MODEL=Qwen/Qwen2.5-Coder-1.5B-Instruct` halves memory and latency
again if you want it smaller still.

## Layout

```
config.py                          all configuration, ORACLE_ overridable
main.py                            CLI: build-sft, build-dpo, train-sft, train-dpo, analyze, tui
dataset_builder/schema.py          the Analysis contract + the v1/v2/v3 system prompts
dataset_builder/mock_data.py       annotated synthetic commits (6 defect classes, 4 safe traps)
dataset_builder/worddiff.py        the word-diff renderer the corpora are built with
dpo_pipeline/frontend_cases.py     Turnstile / auth-guard false positives for DPO
dataset_builder/build_sft_data.py  → conversational JSONL, plus corpus pre-flight
dataset_builder/build_mechanism_corpus.py  the executable-case corpus, all three contracts
dpo_pipeline/build_dpo_data.py     → {prompt, chosen, rejected}, incl. on-policy
evaluate.py                        score a reviewer on held-out commits
fine_tuning/qlora.py               shared 4-bit + LoRA setup, adapter merge
fine_tuning/train_sft.py           TRL SFTTrainer (--seed to measure run-to-run variance)
fine_tuning/train_dpo.py           TRL DPOTrainer, continues from the SFT adapter
llm_explainer/client.py            transformers | ollama, strict JSON parsing
ui/tui_app.py                      three-pane Textual UI
corpus/fetch.py                    fetch real ApacheJIT diffs for training
ml_model/gate.py                   stage 1: LightGBM head, embeddings + metrics
ml_model/train_gate.py             train and ablate the gate (--ablate)
bench/basic_bench.py               executable benchmark, labels proved by running
bench/compare_seeds.py             two-seed comparison with the noise band
bench/template_audit.py            verbatim copying against an out-of-family floor
bench/check_field_audit.py         is `check` composed or recited: distinctness,
                                   saturation, cross-seed identity, and whether
                                   `check_useful` is scoring a token dump
bench/annotate_checks.py           the per-case probe/watch/restored annotations
ui/commands.py                     `:` command mode, parsed and tested standalone
llm_explainer/context.py           git context retrieval (-U50, file snapshots)
docs/METHODS.md                    plain-language explanation of every method
docs/RESULTS.md                    every measurement, with the command that reproduces it
docs/PLAN_SUGGEST_CONTRACT.md      the v3 contract: rationale, thresholds, schedule
```

Every module has a `__main__` self-check:

```bash
python -m dataset_builder.schema        # schema round-trip
python -m dataset_builder.mock_data     # corpus balance
python -m dpo_pipeline.frontend_cases   # captcha cases well-formed
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

* **The v3 contract cleared its thresholds and its evidence was recited.** The
  v4 pair held false alarms at 9–11% (v2 was 4–15%) and named the defect on
  every case it spoke on, while verbatim copying roughly tripled and two of the
  four `effect` fields collapsed to near constants. Scoring better while
  reciting more is not the claim this project wants; the corpus rebuild above is
  the response, and it is not measured until the v6 pair is scored.
* **Hedged output can hide failure.** "It might be here, please check" is never
  strictly wrong, so a lazy model scores well by being vague. The false-alarm
  rate on execution-proved-identical cases is the guard, and it is the number to
  read first.
* **These models recite.** Up to 30% of an answer can be text copied verbatim
  from the corpus, against a 0.0% floor from an untuned model. Never compare two
  checkpoints without running `bench/template_audit.py` against an out-of-family
  floor — and run it `--with-check` as well, because the default metric cannot
  see `effect.check`, which is where the worst templating has been found so far.
* **A field the audit cannot see is a field that will template.** The check that
  did not exist is the defect that shipped. Before trusting any per-field number,
  confirm something measures that field.
* **The mock corpus is templated.** Six defect classes and four safe patterns
  with varying line numbers. It is enough to verify the pipeline trains and the
  format holds; it is not enough to produce a good reviewer.
* **SFT targets need annotations, not labels.** A corpus with only `buggy`/`clean`
  flags trains the model to assert a verdict without a reason — `build_sft_data`
  falls back to that and says so.
* **bitsandbytes 4-bit is CUDA-only.** On CPU, pass `--no-4bit` and expect to
  need a small base model (1.5B) and patience.
* **The gate scores; it does not point.** An earlier revision ranked commits
  with XGBoost/CatBoost over the 14 process metrics alone, and that was removed:
  three boosters landed within 0.005 AUC of each other on ApacheJIT
  (0.862–0.867), which says the metrics were the ceiling rather than the
  algorithm. What replaced it reads the code — LightGBM over embeddings *plus*
  metrics, +0.045 AUC over metrics alone. A risk score still cannot be acted on
  by itself; that is the whole reason stage 2 exists.
* **Stage 2 cannot detect out of distribution.** Separation −4.2pp on CVEfixes,
  indistinguishable from chance, against 99.1% grounding. Do not read its
  verdict as a detector — that is stage 1's job.
