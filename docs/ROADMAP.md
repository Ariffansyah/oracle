# ORACLE — Roadmap to a Draft Paper

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

## Where we actually are (measured 2026-08-15, n=997 paired)

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
- [ ] Build on-policy DPO pairs via `--from-eval`, train, re-evaluate.

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
- [ ] **In flight:** checkpoint-220 then stock on 1000 CVEfixes records
      (`run_cve.sh`, ~28s/commit, ≈8h each). Score with
      `evaluate.py --paired data/cve_sft220.jsonl data/cve_stock.jsonl` — it
      resamples on `pair`, which the paired construction requires.
- [ ] Evaluate explanation quality against human text, not model text. This is
      the strongest evidence available for the "reviewable findings" claim.
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

## Contingency

If, after the leak is fixed, detection still fails to beat the trivial baseline
or the base model, **do not force the "our method works" framing.** Pivot to:

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
