# Positioning

> **Predict, Then Point: From Just-In-Time Risk Scores to Natural-Language
> Defect Hints**

The title states the gap the work closes: JIT defect prediction emits a
probability and stops, and a probability is not something a developer can act
on. What this document adds is *how* the second half is produced — by running
the code, not by asking a model to guess — because that is what separates the
contribution from prompting an LLM at a diff.

Two consequences of the title the paper has to honour:

- **"Point" is a claim, and it must be reported.** Localisation is measured:
  89% (exec), 92% (score), 91% (diff) of explanations name an identifier the
  patch actually touched. It is also *flat across all three arms* — pointing
  needs no execution. Report both halves; the flatness is a real finding about
  where the difficulty is not.
- **"Hints" sets the register, the guard layer sets the guarantee.** What the
  reviewer prints is not an unverified suggestion: sentences that fail
  `verify` are withheld, and the measured before/after is printed underneath
  regardless. The paper should say plainly that a "hint" here is one that
  survived a check against a run.


Where this sits in the literature, what it claims, and — more usefully — what it
deliberately does not. `RESULTS.md` carries every measurement with its
reproduction command; `ROADMAP.md` carries the plan. This file exists to stop
one specific misreading, because that misreading makes the work sound weaker
than it is and invites an objection the design already answers.

---

## The misreading to avoid

> "An SFT model takes a defect probability — say 85% — and translates it into a
> natural-language explanation."

That is a reasonable guess at the architecture and it is **not** what this is.
Nothing in the system conditions the explanation on the probability. The two
stages never exchange a value:

    Stage 1   JIT gate      commit -> probability          nothing is run
    Stage 2   this reviewer file   -> measured outcome     the code is run
              3B model      measured outcome -> prose      the score is never seen

Why it matters is not stylistic. A system that renders a risk score into fluent
English inherits every error in that score, and adds fluency to it. Measured on
the three commits of the `pyalgo` fixture, where the ground truth is not in
dispute because one commit introduces an off-by-one and the next repairs it:

| commit | Stage 1 | Stage 2 |
|---|---|---|
| introduces `range(1, n+1)` -> `range(1, n)` | 10.5% MEDIUM | **Behavior Change**, `15` -> `10` |
| repairs it, `range(1, n)` -> `range(1, n+1)` | 18.1% MEDIUM | **Behavior Change**, `10` -> `15` |
| a behaviour-preserving refactor | 18.6% MEDIUM | **No Observable Change** |

Stage 1 puts all three in the same band and scores the commit that *introduces*
the defect as the **least** risky of the three. This is not a defect peculiar to
this gate; it is what a churn-dominated score looks like from the inside, and
`RESULTS.md` measures the same phenomenon on the published benchmarks — a single
feature, `la`, reaches 0.741 AUC on QT and 0.797 on OPENSTACK against the
22-metric process gate's 0.805 and 0.837.

### What produces that number

Two different artifacts get called "the gate" in this repository and they must
not be conflated.

| | benchmark gate | the gate this reviewer calls |
|---|---|---|
| where | `corpus/deepjit.py --eval` | `artifacts/gate_noleak.joblib` |
| input | 22 process metrics from the QT / OPENSTACK CSVs | GraphCodeBERT (768-d, 512 tokens, mean-pooled over the diff) ‖ 14 Kamei metrics = 782 features |
| head | as published | LightGBM, 400 trees |
| trained on | the authors' splits | ApacheJIT commits, held-out set excluded |
| number | AUC 0.805 / 0.837 | AUC 0.753 on the 200-commit held-out set |

The AUC figures quoted above belong to the **first** column. They characterise
the reformulation against published work; they are not a property of the model
producing the percentage on screen.

The 14 metrics are Kamei et al.'s change measures, computed from git by
`corpus/kamei_metrics.py`: `ns nd nf entropy la ld lt fix ndev age nuc exp rexp
sexp`.

**Two cautions travel with the deployed gate, from `RESULTS.md` (24 Aug).**
First, `config.GATE_MODEL_PATH` still defaults to `artifacts/gate.joblib`, which
was trained on its own evaluation set — the leak was worth 0.495 F1 and 0.21
AUC. `oracle_reviewer` explicitly loads `gate_noleak.joblib` instead and labels
the number unreportable if it ever falls back. Second, the clean gate's shipped
threshold does not transfer: tuned for 95% recall on 27.5%-buggy chronological
ApacheJIT, it gives 17.4% recall on the 46%-buggy held-out set, forwarding 20 of
200 commits and dropping 76 of 92 defects. As a cascade front-end at that
setting it is worse than no gate at all. It is shown here as *context beside* a
measurement, which is the only role the evidence supports.

An explanation generated *from* that number would be confidently wrong on the
commit that fixes the bug. An explanation generated from **execution** is not,
and the separation is structural rather than a matter of prompt quality. When a
reviewer asks "does your explanation inherit the predictor's mistakes?", the
answer has to be *no, by construction*.

### The ablation

Argued until 4 Sep, measured since. Same 519 held-out rows, same checkpoint,
same decode; the arms differ only in what the prompt appends. Scored on whether
the explanation a developer reads contains the true before and after values.

| | exec | score | diff |
|---|---|---|---|
| given | measured before/after | a defect probability | nothing |
| **quotes both true values** | **93%** | **39%** | **39%** |
| on `differs=true` rows | 87% | 26% | 19% |

Paired McNemar over the same rows: `exec` beats both at p ≈ 3e-79, and **`score`
versus `diff` is p = 0.699 — indistinguishable.** Handing the model a defect
probability leaves it exactly where the diff alone did. Execution is worth 54
points; the score is worth nothing.

`exec` is *given* the values, so quoting them is the architectural advantage
rather than a skill. And the scorer available on synthetic rows is near-chance
(AUC 0.557, metrics zero-filled for want of git history), so on its own this is
not evidence that a *good* predictor's score would be equally worthless. That
version of the experiment needs real commits.

### The same ablation on real bugs

Run since, on **BugsInPy** — 501 bugs from 17 maintained Python projects, **452
of them (90%) reproduced** by running the project's own failing test at the
parent commit and again with the fix applied. 458 frozen rows; the gate now
computes 14 of its 14 metrics for the median commit and separates
bug-introducing commits from ordinary ones at **AUC 0.628** rather than 0.557,
so the score arm is narrating a real number.

A fourth arm was added: the same base model with the LoRA adapter *off*, under
the same execution conditioning. Without it, nothing here separates "execution
grounding works" from "our fine-tune works".

| | base (no adapter) | exec | score | diff |
|---|---|---|---|---|
| **grounded in the observed failure** | 40% | **56%** | **10%** | **10%** |
| invents a failure that never happened | 2% | 3% | 10% | 11% |
| names a changed identifier | 87% | 92% | 93% | 93% |

> The `exec` column is the `sft-exec-v2` checkpoint. It was retrained on
> 6 September and now scores **87%** on these same 458 rows, with the deployed
> path at **86%** — see *"The fine-tune is not prompt engineering"* below. The
> ablation structure and every `score`/`diff` conclusion are unaffected; only
> the `exec` column moved.

`score` versus `diff` is 16 discordant pairs against 16 — an exactly balanced
split, **p = 1.00**. The finding replicates on 458 real bugs, against an
informative predictor, and the caveat above is closed.

Three things change on real bugs, and all of them matter more than the
replication:

- **The fine-tune transfers, and it transfers as value-copying.** 40% → 56%
  grounded, 93 discordant rows against 21, p = 5.3e-12. Almost all of the gain
  is in quoting the measured message — 9% → 43% — not in naming the right
  exception class (36% → 48%). The adapter taught the model to copy a value
  already sitting in its prompt. *(With the v3 corpus this becomes 40% → 87%,
  and the exception-naming half moves too: 36% → 72%.)*
- **Grounding and fabrication have different causes.** Removing execution
  triples fabrication (3% → 10%, p = 1.1e-08). Removing the adapter changes it
  not at all (7 discordant against 8, **p = 1.00**). Fine-tuning bought
  correctness; only running the code bought honesty.
- **The 93% does not transfer.** `exec` is grounded 56% of the time here, with
  the measured failure in its prompt. Being handed the answer is necessary and
  nowhere near sufficient.

Localisation needs no execution at all: every arm names a changed identifier
87–93% of the time, and the arm with the least information is not the worst at
it. Reading the diff is enough to say *where*. Saying *what happened* is what
requires running the code.

One gap is left open on purpose: there is no `base + score` arm, so the claim
"conditioning matters more than the fine-tune" is stated within the adapted
model and not independently of it.

### The fine-tune is not prompt engineering

The obvious objection to the row above is that a 3B model's grounding is a
prompt away, and a LoRA adapter is an expensive way to buy what a better prompt
gives free. That objection was **tested and, on the v2 checkpoint, it won**: a
hand-written system prompt with three worked examples brought the *un-adapted*
base to 279/458 (61%), and the adapter's advantage over it vanished (93/98,
p = 0.77). Prompting and fine-tuning were substitutes.

Retraining on a pytest-shaped corpus (6 September) reverses that.

| configuration | grounded | invents |
|---|---|---|
| **`sft-exec-v3`, bare 40-word prompt** | **400/458 (87%)** | **9** |
| `sft-exec-v3` + the hand-written few-shot prompt | 356/458 (78%) | 31 |
| base + the hand-written few-shot prompt | 279/458 (61%) | 11 |
| `sft-exec-v2`, bare prompt | 255/458 (56%) | 12 |
| base, bare prompt | 183/458 (40%) | 11 |

- **The adapter with no prompt engineering beats the base with the best prompt
  available**, by 121 rows: 139 discordant against 18, p = 2.4e-24, while
  fabricating less (9 against 11).
- **The prompt actively hurts the tuned model.** 400 → 356, p = 1.0e-05, and
  fabrication triples, 9 → 31, p = 6.0e-05. The few-shot examples carry failure
  signatures that are not the measured one and the model matches them instead.
  Prompting and fine-tuning are no longer substitutes; they are antagonistic.

**The honest caveat.** `grounded` is satisfied by quoting the measured failure,
and the `exec` prompt contains that string — so a one-line `print(before)` scores
458/458. 87% measures *faithfulness to a measurement*, not bug-finding. The
subset that escapes this ceiling is the 250 rows with no exception class to name:

| subset | n | v3 | base + few-shot | p |
|---|---|---|---|---|
| **no class to name** (`AssertionError`/bare) | 250 | **78%** | 47% | 7.5e-15 |
| named exception present | 208 | **98%** | 78% | 3.1e-11 |

The hard subset is the majority of the corpus and carries the larger discordant
count (95/16). The model is not emitting familiar exception names more often; it
is lifting the measured text where the measured text is all there is.

### What the product does, not just the model

The deployed path — `oracle_reviewer.core.explain` plus the seven-stage guard
chain — scored **183/458 (40%)** on 5 September, statistically indistinguishable
from the un-fine-tuned base (67 discordant against 67, p = 1.00). That null was
the strongest negative result in this project.

It now scores **392/458 (86%)**: 217 discordant rows against 8, p = 5.5e-54,
with fabrications down from 8 to 2.

- **The guard chain is now neutral on correctness and positive on safety.**
  Guarded 392 against unguarded 400 is 31/39, **p = 0.403** — a wash — while
  fabrications fall 9 → 2. The guards have stopped compensating for a weak model
  and are trimming the last inventions off a strong one.
- **89% of the gain is the corpus, and that is now measured rather than
  argued.** Guarded v2 used `sft-exec-v2` and a three-case `core.SYSTEM`;
  guarded v3 uses `sft-exec-v3` and the four-case prompt added 1h50m later. The
  missing cell — v2 adapter, four-case prompt — scores **207/458**, so the +209
  splits into **+24 from the prompt** (p = 0.022) and **+185 from the retrain**
  (p = 5.9e-45). The prompt fix also *raised* fabrication 8 → 15; the corpus
  took it to 2. Prompting trades timidity for overreach, and only the retrain
  fixes both. The unguarded arms
  never touch `core.SYSTEM` and carry no such confound.

### The same ablation across a 40x change in model size

Run on 4 September against gpt-oss-120b, to test whether any of this is an
artifact of using a small model. It is not.

**Both halves of this table are the earlier 264-row corpus**, so its 3B column
reads 50% where the 458-row table above reads 56%. The two corpora are never
mixed; the 120B has no measurement on the larger one.

| | 3B exec | 3B score | 3B diff | 120B exec | 120B score | 120B diff |
|---|---|---|---|---|---|---|
| grounded | 50% | 6% | 6% | **91%** | 37% | 41% |
| invents a failure that never happened | 2% | 11% | 9% | 4% | **28%** | **30%** |

**The claim this document rests on replicates at both scales.** `score` and
`diff` are indistinguishable for the 3B (p=1.00) and for the 120B (p=0.126) —
a defect probability leaves either model exactly where the diff alone did.

Two further readings, and the second is the one that matters:

- **The large model is much better at the task.** 91% against 50%. The size
  claim this document used to make does not survive it.
- **The large model needs the measurement more, not less.** Removing execution
  costs it 54 points against the 3B's 44, and its ungrounded fabrication rate is
  28% — more than double the small model's 11%. Grounding is not a crutch for
  weak models; it is what stops a strong one from being confidently wrong.


---

## What the name means

In software engineering a **test oracle** is the mechanism that decides whether
an execution is correct. The name here is literal, not a metaphor for
authority. `oracle_reviewer/core.py` checks out the parent commit, applies
**one file** from the commit, runs the project's own command, and compares the
result to the same command at the parent. Risk is then read off exit status:

    base run errors -> this file's run is clean   ->  FIXES
    base run clean  -> this file's run errors     ->  HIGH RISK
    both clean, output differs                    ->  BEHAVIOUR CHANGE
    byte-identical                                ->  nothing is claimed

That is a differential oracle. It is why the risk tier has no false-positive
rate to report: a claim of "this file broke the run" is an observation, and the
per-file isolation is what makes it attributable to a file rather than to a
commit.

The same harness underwrites the corpus. `bench/exec_diff.py` runs pre and post
for all 46 `bench/basic` cases across nine languages (C, Go, Java, JavaScript,
PHP, Python, Ruby, Rust, TypeScript); 45 execute cleanly on both sides and one
fails to build, and the executed `differs` verdict agrees with the corpus
`buggy` label on 45 of 46. The labels this project trains and evaluates on are
therefore established by running the code, not inferred by SZZ.

---

## The four neighbourhoods

**1. Explainable JIT defect prediction.** The closest framing, and the one the
roadmap already argues: JIT-DP produces rankers, not reviewers. Prior
explainability work is feature attribution — which metric moved the score. This
replaces attribution with a statement about program behaviour, and the honest
distinction from that line of work is that it does not explain the model at all.
It explains the *change*. Stage 1's score is reported beside it, with its caveat
attached, and is never the subject of the explanation.

**2. Automated code review.** The output shape overlaps: a natural-language
comment on a diff. The training signal does not. ACR models are trained on human
review comments, which are opinions with unknown correctness. Here the target is
generated from measured execution, so the supervision has a defined notion of
right — and the evaluation is likewise execution-checkable rather than a
similarity score against what some reviewer happened to write.

**3. Generative AI for software quality.** The umbrella. This project used to
make a size claim inside it — that a 3B model given measured values is *enough*,
and a large model doing the same job is a chat wrapper that demonstrates nothing.
**That claim was tested on 4 September and it is false.** On the same 264
BugsInPy rows (the v1 corpus), with the same prompt and the same measured
values, gpt-oss-120b is grounded in 91% of its explanations against the trained
3B's 50% (McNemar, only-3B=6, only-120B=113, p=1.1e-26). Explanation length is
not the cause: median 39 words against 40.

The `base` arm run on 5 September narrows what is left of the claim from the
other side. On 458 rows, `Qwen2.5-Coder-3B-Instruct` **as shipped** — no
adapter, no ORACLE training data, just the measured failure in its prompt — is
grounded 40% of the time, against the fine-tuned 56%. The fine-tune is worth a
real and significant 16 points (p = 5.3e-12), but "a *task-specific* small model
is what makes this work" cannot be argued against 0; it has to be argued against
40, and most of what remains is the model learning to copy a value it was
already given.

The claim that replaces it is not about size at all, and it is stronger:

> **Measurement is what makes explanation possible, and scale does not
> substitute for it.**

Take execution away from the large model and it falls further than the small one
— 91% to 37%, a 54-point drop against the 3B's 44 — and its fabrication rate
more than doubles the 3B's: 28% against 11% (p=2.3e-08). A 40x larger model,
given a risk score instead of a measurement, writes more confident, more
specific, more fluent wrong answers. That is an argument for grounding that no
amount of prompting or parameter count answers, and it exists only because the
large model was actually run.

> **BOTH HALVES OF THAT PARAGRAPH ARE STRUCK, 8 Sep 2026.** Re-run on the v2
> corpus against `sft-exec-v3`, neither claim survives:
>
> * **The large model degrades more gracefully, not less.** The 3B falls
>   90% -> 23% (67 points); the 120B falls 94% -> 40% (54). The direction is the
>   reverse of what is written above.
> * **The fabrication gap is gone.** 29% for the 120B against 26% for the 3B,
>   where v1 had 28% against 11%.
>
> What replaces them is stronger than either, and it is the claim to lead with:
> **a 3B given a measurement beats a 40x larger model given a risk score, by 230
> rows — 412/458 against 182/458, paired 240/10, p = 2.5e-58.** Execution
> grounding is worth more than a 40x increase in parameters. See `RESULTS.md`,
> *The 3B against a 40x larger model*.

What survives for the 3B is a deployment argument, and it must be stated with
its price attached: self-hosting costs 41 points of grounding and buys zero data
egress, ~3 GB of VRAM, and no code leaving the machine. That is a defensible
trade for reviewing proprietary code. It is not a claim that small is enough.

> **SUPERSEDED 8 Sep 2026.** The 41-point figure was measured on the v1 corpus
> against the checkpoint that `sft-exec-v3` replaced. Re-run on the 458-row v2
> corpus, the 3B scores **412/458 (90%)** against the 120B's **429 (94%)** --
> paired McNemar 15/32, **p = 0.0186**. The price is **4 points, not 41**, the
> 3B fabricates *less* (9 against 15), and on the 60 rows with no exception class
> to name it leads, 41 to 36. The 120B's entire remaining advantage is +19 rows
> on `AssertionError` signatures. The paragraph above understates the 3B badly
> and should be rewritten around the new figure before it is used anywhere; see
> `RESULTS.md`, *The 3B against a 40x larger model*.

**4. Differential testing and regression oracles.** The neighbourhood the
academic framing usually misses, and mechanically the closest. Per-file
execution isolation is delta-style: hold everything constant, vary one file,
observe. It is also where the honest limits live, below.

---

## What is measured

Value tier, 519 held-out rows from families the model never trained on, same
base model and decode settings in both arms (`RESULTS.md`, 3 Sep):

| | base | fine-tuned |
|---|---|---|
| emits valid JSON | 97% | 99% |
| verdict correct | 47% | 79% |
| **both before and after values right** | **8%** | **42%** |
| ...on diffs that do change behaviour | 4% | 22% |
| self-contradictory | 28% | 5% |

The shortcut control matters more than the headline. On a `differs=false` row
the two values are equal, so copying one into the other scores without computing
anything — but the base model has that shortcut available too, scores 8%, and
that is *below* its own always-copy ceiling of 14%. The fine-tuned model clears
its own ceiling by 44 rows.

---

## What this cannot do

Stated plainly because the tool now states it to its users, and a paper should
not claim more than the tool does.

**Coverage is the binding constraint.** An oracle sees only what the command
exercises. A rendered UI label, a workflow YAML, a branch no input reaches: all
produce identical output, and identical output is not evidence of safety. The
reviewer distinguishes the reasons rather than blurring them — `Baseline Already
Failing`, `Command Timed Out`, `Not Checked By This Command`, `No Observable
Change`. That last verdict is deliberately worded to say it cannot tell whether
the changed code ran at all, because without coverage instrumentation it cannot.

**The value tier is weak where it counts.** 22% on diffs that change behaviour.
The reviewer does not rest on it — the values shown to the user come from the
run, not the model — but any claim about the model *computing* a new value is a
claim about a 22% capability.

**Prose is guarded because it is not trustworthy unguarded.** `exec_contract.py`
withholds an explanation that contradicts itself, states a change in the wrong
direction, asserts safety or breakage where nothing was measured, or blames a
run's outcome on the change. Each of those guards exists because the model did
it. They are part of the system, not a deployment detail, and the fraction of
explanations withheld belongs in any evaluation of it.

**Stage 1 is out of distribution off-benchmark.** The gate is trained on
ApacheJIT-derived data. Scoring an arbitrary repository's commit is
extrapolation, which is a second reason the number carries a caveat.

---

## The claim, in one sentence

Stage 1 predicts, Stage 2 observes, and the language model explains only what
Stage 2 measured — so the explanation cannot inherit the predictor's errors,
and where nothing was measured the system says so instead of narrating a score.

Measured at two model scales forty times apart, and true at both: without the
measurement, the explanation is not merely worse, it is invented.
