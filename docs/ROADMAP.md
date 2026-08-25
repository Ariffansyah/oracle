# ORACLE — Roadmap to a Draft Paper

**Every measurement, with its reproduction command, lives in `RESULTS.md`.**
This file carries the plan and the interpretation.

**Window:** 2026-08-14 → 2026-10-14 (8 working weeks + buffer)
**Deliverable:** a submittable draft with defensible results on established
benchmarks.

---

## The gap we are filling

Just-In-Time defect prediction has produced increasingly accurate *rankers* and
almost no *reviewers*. The progression in the literature runs:

| generation | output | what a developer can do with it |
|---|---|---|
| Kamei et al. (2013) | a probability per commit | nothing actionable — nobody fixes `la = 412` |
| DeepJIT (2019), CC2Vec (2020) | a better probability | same |
| JITLine (2021) | ranked suspicious *lines* | look at a line, with no statement of what is wrong |
| **ORACLE** | **a structured finding: category + explanation** | **read the claim, agree or disagree** |

The thesis is that the last step is the one that makes JIT prediction usable,
and that it is reachable by a small instruction-tuned model rather than a large
one. Everything in this roadmap serves that claim.

**Explicitly deferred:** arbitrary languages and frameworks (the Next.js /
TypeScript case). That is the follow-on goal. This window establishes the
reformulation on benchmarks where prior work has published numbers.

---

## Where we actually are (2026-08-25)

The goal moved on 24 Aug and this section has not caught up with it. The
detection numbers below are still reproducible and still the honest ApacheJIT
picture, but they no longer describe what the project is trying to do.

**The current target** is basic algorithmic code in the 8 corpus languages at
8/10 correct with no hallucination, measured by `bench/basic_bench.py`, whose
labels are proved by executing the code rather than inferred from SZZ.

**Where that stands:** `oracle-merged` scores **41/46 (89%) correct locus, 2
false alarms (4%)**, best of three checkpoints and better than the 25 Aug
retrain. The locus half of the goal is met; the "correct explanation" half is
unmeasured, and the "no hallucination" half is 2 cases short. Full write-up and
the five approaches that were measured and lost are in `RESULTS.md`.

**What this changes for the paper.** Criterion 3 (beats the base model) now has
a second, cleaner piece of evidence that does not depend on SZZ labels, a
teacher, or a threshold: 33/46 base -> 41/46 tuned on executable ground truth.
Criteria 2 and 4 still fail on detection. The *Contingency* pivot below is no
longer a fallback — it is the better paper, and 25 Aug added three more findings
of exactly its type (a scorer that reported correct answers as hallucinations, a
sampling safeguard that never executed, and a grounding rule whose obvious
repair grounded a third of findings against random commits).

---

## The ApacheJIT detection picture (measured 2026-08-15, n=997 paired)

Both models evaluated on `detect_eval.jsonl` — 1000 ApacheJIT commits, balanced
500/500, SZZ labels only. Reproduce with
`python evaluate.py --paired data/detect_sft220.jsonl data/detect_stock.jsonl`.

| metric | checkpoint-220 | stock 3B | trivial baseline |
|---|---|---|---|
| valid JSON | 99.8% | 99.9% | — |
| grounded | 99.8% | 98.4% | — |
| detection F1 | 0.64 | 0.59 | **0.67** (always-buggy) |
| accuracy | 0.61 | 0.56 | 0.50 (always-clean) |
| separation (TPR−FPR) | **+21.0pp** | +11.6pp | 0.0pp |
| category match vs teacher | 27.1% | 26.9% | — |

Tuned − stock separation: **+9.5pp, 95% CI [+2.0, +17.0], p=0.007.** McNemar on
per-commit correctness agrees (209 vs 162, p=0.017).

Read honestly:

- **Criterion 3 passes.** At n=997 the paired CI excludes zero — tuning beats the
  base model, which the n=200 run could not establish (`[-9.7, +27.4]`).
- **Criterion 2 still fails on F1.** 0.64 against always-buggy's 0.67. Accuracy
  does clear always-clean (0.61 vs 0.50), and separation is the honest measure
  at a 50/50 base rate — F1 there rewards a model merely for saying yes.
- Both numbers are on **checkpoints trained on the leaked corpus**, so this is
  the pre-fix baseline, not a result. Its value is as the comparison point that
  will show whether the leak fix mattered.
- Format quality is **not** a contribution: stock matched it once given the
  schema. The only format-side gain is needing no schema block (~24% shorter
  prompt).
- Category match at 27% is the weakest number and is currently unexplained.

### The blocker that gates everything

`corpus/label.py` previously told the teacher the answer on SZZ-buggy commits:

> "Ground truth: a later commit in this repository fixed a defect in the lines
> this change introduced. Identify what is wrong here and report it."

Consequence: teacher recall 1.00 with **zero false negatives across 844
training and 92 held-out commits**. The teacher complied on 98.2% of buggy
commits. A second filter in `verify()` discarded any disagreement, so `fn = 0`
was guaranteed by construction independently of the hint.

Both are fixed in code (`--hint` now opt-in; `verify(hinted=False)` keeps
disagreements; every record stamped `hinted`). **The corpus itself is still
contaminated and must be regenerated.** No result trained on the current
`labelled.jsonl` is publishable.

---

## Acceptance criteria

The draft is submittable when all of these hold on held-out data at n ≥ 1000:

1. **No label leakage.** Corpus regenerated unhinted; teacher-vs-SZZ recall
   materially below 1.00 with a non-zero false-negative count.
2. **Beats the trivial baseline.** Detection F1 above always-buggy, and accuracy
   above always-clean, on the same split.
3. **Beats the base model, significantly.** Paired bootstrap CI on the
   separation difference excludes zero.
4. **Explanation quality is measured, not asserted.** Grounding, category
   agreement, and fix-agreement-against-the-repair-diff reported on every
   benchmark.
5. **At least two datasets**, one of which carries human-written explanations
   rather than model-generated ones.

If (2) or (3) fail after the leak is fixed, the paper pivots — see
*Contingency*.

---

## Phase 1 — Repair the foundation (Weeks 1–2, Aug 14–27)

Nothing else is worth doing until the corpus is clean.

- [ ] Obtain a free teacher. Groq free tier (`openai/gpt-oss-120b`, already a
      provider in `corpus/label.py`) or wake the Ollama box at
      `192.168.1.170`. DeepSeek if funded.
- [ ] Relabel all ~2000 ApacheJIT commits **unhinted**. The run now prints its
      own teacher-vs-SZZ ceiling; record it. This number replaces the fictitious
      0.87 and is the real ceiling for everything downstream.
- [ ] Rebuild SFT data, retrain (~14h GPU).
- [ ] Re-evaluate at n=1000 against stock (~12h GPU).
- [x] ~~Build on-policy DPO pairs via `--from-eval`, train, re-evaluate.~~
      **Blocked on hardware, 24 Aug.** Three DPO runs move nothing measurable
      and the token audit says why: 0 of 115 on-policy pairs fit under 460
      tokens, 0 of 525 `from_labelled` pairs under 512 (shortest is 615, median
      prompt 1235). 61% would need `max_length=1536`; the 6GB card OOMs at 768.
      Independently, every `from_labelled` pair shares one hardcoded rejected
      string, so the objective is degenerate even if it fit. Needs a >=16GB card
      and a per-example rejected side. See RESULTS.md.

**Exit:** acceptance criteria 1–3 answered with real numbers, pass or fail.

**Done Aug 15:** the 1000-commit pre-fix baseline, above. Tuning beats stock
significantly; neither beats always-buggy on F1.

**Reordered:** Phase 3 was pulled forward. The unhinted-teacher pilot (F1 0.49,
below the 0.63 baseline) says SZZ-buggy is largely not inferable from the diff,
so relabelling ApacheJIT with a clean teacher would spend ~34 GPU hours to
distil a signal that is not there. CVEfixes needs no teacher at all, so it goes
first and the relabel waits on what it shows.

---

## Phase 2 — Comparability (Weeks 3–4, Aug 28 – Sep 10)

Adds the benchmark prior work reports on, and two languages, in one step.

- [ ] `corpus/deepjit.py` — loader for **QT (C++)** and **OPENSTACK (Python)**
      (Hoang et al., MSR 2019). Emit the existing record shape; follow the
      feature-reconciliation discipline of `corpus/apachejit.py`.
- [ ] Use the authors' published splits. Do not re-split — comparability is the
      entire point.
- [ ] Label unhinted, train, evaluate.
- [ ] Report ORACLE's detection numbers beside published DeepJIT / CC2Vec /
      JITLine figures, with the explicit caveat that we optimise for
      explanation and they optimise for ranking.

**Exit:** a comparison table against prior work on a dataset we did not choose.

---

## Phase 3 — Teacher-free explanations (Weeks 5–6, Sep 11–24)

The methodological centrepiece, and the answer to "your explanations come from
another model."

- [x] `corpus/cvefixes.py` — loader for **CVEfixes** v1.0.8, restored at
      `data/cvefixes/CVEfixes.db`. Emits `data/cvefixes_eval.jsonl`.
- [x] Map CVE description → `Analysis.summary` + a `security` finding. These are
      **human-written** explanations: no teacher, no leak, no cost.
- [x] Evaluated checkpoint-220 and stock on 1000 records / 500 pairs
      (`run_cve.sh`). **Both models are at chance.**

### Result (2026-08-15, n=982 paired, 497 blocks)

| metric | checkpoint-220 | stock 3B |
|---|---|---|
| separation (TPR−FPR) | **−4.2pp** | **−1.8pp** |
| positive rate | 0.72 | 0.77 |
| F1 / accuracy | 0.57 / 0.48 | 0.60 / 0.49 |
| grounded | **99.1%** | 80.7% |
| category match vs CVE | 12.9% | **32.1%** |

Difference −2.6pp, 95% CI `[-9.1, +4.0]`, p=0.78. Neither model beats the other,
and neither beats zero.

Within the complete pairs — the same commit forward and reversed:

| | ckpt-220 | stock |
|---|---|---|
| flags both directions | 269 (55%) | 328 (66%) |
| flags neither | 57 | 61 |
| correct (flags intro, clears fix) | 70 | 50 |
| backwards | 92 | 58 |
| forced-choice accuracy | 0.432 (p=0.10) | 0.463 (p=0.50) |

Three things this says, and only the first is about our model:

1. **Neither model reads direction.** Given the same lines forward and reversed,
   both fire on "this diff looks risky" and cannot say which way the code moved.
   Removing every confound left nothing behind.
2. **Fine-tuning bought format, not judgment.** Grounding 99.1% vs 80.7% is a
   real and reproducible gain. Separation is not.
3. **Fine-tuning on ApacheJIT destroyed the `security` category.** Stock emits
   `security` 397 times in 851 findings; checkpoint-220 emits it 103 times in 754
   and says `logic-error` 440 times instead — on commits that are, by
   construction, CVEs. The Java bug-fix teacher corpus overwrote a class the base
   model already had. This is a distillation cost worth reporting on its own.

**Exit:** criteria 4 and 5 satisfied on human ground truth. The answer is
negative.

### Correction (2026-08-16): the paired corpus leaks through line composition

Equal total length is not equal composition. A fix adds a guard, so it carries
~9.7 more `+` lines than `-` lines and its reverse carries the mirror. Ten
counting features score **AUC 0.934** on the held-out pairs with no model at all
(`python count_control.py data/cve_gate.jsonl 0.6667`).

So this corpus **cannot carry a detection claim**. It remains valid as an
explanation benchmark with human ground truth. Two facts survive the correction,
and one gets stronger:

- Both LLMs sat at chance on a task a line-counter solves at 0.934. They did not
  even find the cue.
- The gate scores 0.792 here — *below* the counting baseline, so it is
  recovering a noisy version of `wc`, not reading code.

Every detection number from a paired corpus now ships with its counting baseline,
the same way F1 ships with always-buggy.

---

## Stage 1 — the gate, measured (2026-08-16)

The first positive result in this project, and it is not the LLM.

`python -m ml_model.train_gate --jsonl data/apachejit_commits.jsonl --ablate`,
7989 commits, chronological 80/20 split, test n=1598, target recall 95%:

| variant | AUC | PR-AUC | LLM calls saved |
|---|---|---|---|
| counting baseline | 0.638 | 0.363 | — |
| metrics only (the 2013 baseline) | 0.777 | 0.660 | 20.4% |
| embeddings only | 0.761 | 0.498 | 27.1% |
| **embeddings + metrics** | **0.822** | **0.699** | 28.2% |

Reading the code adds **+0.045 AUC and +0.039 PR-AUC** over process metrics
alone, and the whole stack clears the counting baseline by +0.184. AUC 0.822 is
inside the range DeepJIT and CC2Vec report on QT/OPENSTACK.

This is what makes the two-stage framing evidential rather than face-saving:
the classifier detects (0.822), the LLM explains (99.1% grounded) and cannot
detect out of distribution (separation −4.2pp). Each component is used where it
measures well.

**Do not pipe the gate's verdict into the explainer's prompt.** That is the
`corpus/label.py` hint in a new costume — the teacher complied on 98.2% of buggy
commits when told the answer. The gate selects *who* gets an LLM call; the LLM
reaches its own verdict, and the disagreement rate between the two is itself a
number nobody in JIT has been able to report.
- [x] Evaluate explanation quality against human text, not model text. This is
      the strongest evidence available for the "reviewable findings" claim.
      Measured: word-overlap F1 0.033 (220) vs 0.028 (stock), p=0.017 — both
      near zero; fine-tuning gains significance, not magnitude. See RESULTS §2.4.
- [ ] Document the caveat honestly: CVE text is written post-hoc with knowledge
      of the bug, and describes the vulnerability rather than always pointing at
      diff lines.

**Exit:** acceptance criterion 4 and 5 satisfied, on human ground truth.

---

## Phase 4 — Validation and writing (Weeks 7–8, Sep 25 – Oct 8)

- [ ] **ManySStuBs4J** (Karampatsis & Sutton, MSR 2020) — validate the
      10-category taxonomy against an external bug-pattern taxonomy. Currently
      the categories rest on nothing but our own choice.
- [ ] Ablations, all already supported by the codebase:
      context on/off (`:context off`), chunked vs whole-commit,
      `INFERENCE_SAMPLES=1` vs `3`, 1.5B vs 3B, SFT-only vs SFT+DPO.
- [ ] Write the draft.

**Buffer:** Oct 9–14.

---

## GPU budget

One 6 GB card, and it is the throughput constraint. Measured rates: SFT ≈ 14h
per run (220 steps / 1759 examples); evaluation ≈ 6h per 1000 commits per model;
DPO ≈ 1–3h.

| phase | GPU hours |
|---|---|
| 1 — repair | ~34 |
| 2 — comparability | ~26 |
| 3 — CVE | ~20 |
| 4 — ablations | ~20 |
| **total** | **~100h over 8 weeks ≈ 13h/week** |

Feasible, with no slack for a second full retrain. Sequence runs overnight and
do not start a training run without knowing which acceptance criterion it
answers.

---

## Contingency — now the recommended path (updated 2026-08-25)

Detection did not beat the trivial baseline, and ten days of work since has not
moved it. **Do not force the "our method works" framing.** Pivot to:

> *A task reformulation and evaluation methodology for JIT defect explanation,
> with an honest baseline study.*

That paper is defensible with what already exists:

- Prior JIT work outputs a probability and therefore **cannot evaluate
  explanations at all**. Grounding, category agreement, and
  fix-agreement-against-the-repair-diff are new measures for a task the field
  has not been able to measure.
- The label-leak finding is itself a contribution: teacher distillation for
  defect explanation silently leaks labels, here is the measurement and the
  correction.
- **The measurement apparatus fails in ways nobody reports.** By 25 Aug this is
  a series, not an anecdote: a gate trained on its own eval set (0.495 F1), a
  grounding check that never rejected anything, rendering variance of 0.088 from
  edits that change no code, a scorer that graded correct paraphrases as
  hallucinations, a consensus safeguard that has never executed on the backend
  where every number is taken, and a grounding repair whose obvious form grounded
  a third of findings against randomly paired commits. Each was caught by a
  control, and the controls are the contribution.
- **An executable benchmark for defect explanation.** 46 cases, 9 languages, every
  label proved by running the code. It separates locus from mechanism and proves
  false alarms rather than assuming them — neither is possible on an SZZ-labelled
  corpus, and it is what showed the refactor false alarm to be a rendering
  artifact rather than a reasoning failure.

Negative and methodological results publish at MSR. A forced positive claim on
F1 0.60 against a 0.63 baseline does not survive review.

---

## Deferred beyond this window

- Arbitrary languages and frameworks (Next.js / TypeScript / the BookNesa case).
  Mining infrastructure exists (`corpus/mine.py`, 14 languages) and a corpus is
  accumulating, but coverage is thin and labelling is unfunded.
- Stage-1 gate fusion — using `gate.joblib`'s probability as an ensemble signal
  rather than an on/off filter. Genuinely promising and free, but it is a
  second contribution and would dilute the first.
- Mixture-of-Agents. Requires model diversity we do not have on 6 GB with no API
  budget; self-consistency (`INFERENCE_SAMPLES=3`) is the cheap version and is
  already implemented.

---

## Open risks

| risk | impact | mitigation |
|---|---|---|
| Unhinted teacher finds defects on very few buggy commits | SFT targets collapse toward silence | measure on a small pilot before relabelling everything |
| SZZ-buggy defects often not visible in the diff | caps achievable recall regardless of model | report the unhinted teacher ceiling as the honest upper bound |
| No funding for teacher labelling | Phases 1–3 stall | Groq free tier; local Ollama box |
| Single 6 GB card | no room for a failed retrain | pilot every change at small n first |
| Category match stuck near 27% | weakens the explanation claim | ManySStuBs4J may show the taxonomy itself is the problem |
