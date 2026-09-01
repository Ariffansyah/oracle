# The suggestion contract (v3): say where, suggest the test, never invent the value

Written 2026-08-30. This is the active plan. `docs/RESULTS.md` holds the
measurements it rests on; `next-session.md` holds run state.

---

## The one-sentence goal

**Stop the model asserting facts it cannot know. Have it name where to look and
what test would settle it, and say so as a suggestion rather than a finding.**

Not: *"The bug is caused by the loop bound."*
But: *"This probably breaks at the loop bound — run it and check index 5."*

## Why, in numbers

Split every stored answer by what kind of claim it makes. All 101 cases, all
four v2/v3 checkpoints:

| what the model is asked for | how often it is right |
|---|---|
| **Where** — point at the code at fault | **87 – 98%** |
| **Which way** — does the change break or fix | **79 – 93%** |
| **What exactly happens** — the concrete before/after value | **15 – 31%** |

The model knows *where* and *which way*. It does not know the *value*. The v2
contract demands one anyway (`"before": what the program did at that trigger
BEFORE this commit`), so it invents one, and is wrong about four times in five.
**The fabrication is not a training defect. The output contract requires it.**

### The dry run that justifies the whole change (no GPU, 30 Aug)

Scoring the proposed contract against answers already on disk:

| run | answers with a FALSE concrete claim | of those, location still right | headline cost of deleting them |
|---|---|---|---|
| `v2_pilot2` | 68 / 99 = 69% | 90% | **0** |
| `v2_seed7` | 79 / 100 = 79% | 94% | **0** |
| `v3` | 78 / 100 = 78% | 95% | **0** |
| `v3_seed7` | 85 / 100 = 85% | 99% | **0** |

Two facts carry the plan:

1. When the model states a wrong value, **90–99% of the time it was still
   pointing at the right code**. Deleting the value leaves a correct hint.
2. The headline metric `basic_bench.py:413` is `verdict_ok and (identified or
   not buggy)`. **It never reads `before`/`after`.** Removing them costs zero
   points. Verified: the gate still prints the documented 76 and 86.

So ~78% of the model's false statements can be deleted for free.

### And it defuses the parroting found the same day

`bench/template_audit.py` measured seed 42 copying **30%** of its answer prose
verbatim from the corpus, against a **0.0%** floor from an untuned model — and
v2 does it as hard as v3, so it is a property of the whole corpus family.

Under v2 the recited sentence *"the helper compares with `> 60` where the inline
test used `>= 60`"* is a false assertion about a case that has no such
comparison. Under v3 the same recited text becomes *"check whether the extracted
helper's comparison matches the original inline test"* — true, and useful even
where it is not the defect. **The same memorisation stops being harmful.**

---

## The contract change

Keep the JSON shape CLOSE to v2 — same nesting depth, similar key count — so the
model is not learning a new format and a new behaviour at once. Swap the two
fields that force invention; keep everything that works.

Now (v2):

    {"effect": {"trigger": "running c-array-bound.c", "before": "15",
                "after": "panic: index out of range", "direction": "post-breaks"},
     "summary": "The change replaces `<` with `<=`, causing out-of-bounds access.",
     "findings": [{"category": "off-by-one", "explanation": "...", "file": "..."}]}

Proposed (v3):

    {"effect": {"trigger": "running c-array-bound.c",
                "check": "run it and watch index 5 - if the loop reaches a[5] it is past the end",
                "direction": "post-breaks", "confidence": "likely"},
     "summary": "This looks like it breaks at the loop bound in c-array-bound.c.
                 The comparison moved from `<` to `<=`, so the last index may now
                 be out of range. Worth running to confirm.",
     "findings": [{"category": "off-by-one", "explanation": "...", "file": "..."}]}

- `before` / `after` -> **`check`**: a test the reader can run, phrased as an
  instruction, not a fact.
- **`confidence`**: `likely` | `possible`. Enables a calibration check.
- `trigger`, `direction`, `findings`, `summary` unchanged in shape. `summary`
  and `explanation` are reworded as suggestions.

## Files to change

| file | change |
|---|---|
| `config.py:172` | `OUTPUT_CONTRACT` accepts `v3`; `DIFF_RENDERING` auto -> word for v3 too |
| `dataset_builder/schema.py` | `Effect`: swap `before`/`after` for `check`, add `confidence`. Add `_SYSTEM_PROMPT_V3` + `_SHORT_HINT_V3`, wire the selectors at :292-293 |
| `dataset_builder/build_mechanism_corpus.py` | hedged answer templates, **varied wording**, in `clean_direction()` (:200) and `mechanism()` (:168) |
| `bench/basic_bench.py` | `identified()` also reads `check`; new `check_useful`; `observable_ok` retired under v3; `fabricated` keeps the abs-path and identical-output rules |
| `bench/template_audit.py` | done 30 Aug; now also the corpus pre-flight |

## How success is measured

Decide the thresholds BEFORE training, as with the v3 prediction.

| metric | now | target |
|---|---|---|
| location rate (when it speaks) | 87–98% | **must not drop** below the v2 pair |
| false alarms on clean cases | 4–15% | **must not rise** above the v2 pair |
| fabricated concrete values | 69–85% of answers | **0 by construction** |
| verbatim copying (`template_audit`) | 18–30% | lower, and measured either way |
| `check_useful` (new) | n/a | reported, no threshold on the first run |
| confidence calibration (new) | n/a | `likely` should beat `possible` |

**Amended for v6 (31 Aug), stated before the run is scored.** The first three
rows are unchanged and still gate. Two are added, and one is reinterpreted:

| metric | v4 pair | v6 target |
|---|---|---|
| `check` `distinct*` on mech_heldout | **1 / 1** | a large majority of 21 |
| cross-seed identical `check` | 13/21, 16/46, 21/34 | near the `summary` control (0–1) |
| `check_useful` | 29/31, 20/21 | **a DROP toward the 19/31, 11/21 "no tail" figures is the honest number arriving, not a regression** |
| confidence `possible` | 3 in 168 | present in useful numbers; `likely` still beats it |

The `check_useful` row is the one to be careful with. v4's 95% was substantially
a list of changed tokens pasted after the sentence, and v6 deletes that list. A
v6 score near 95% would mean the sentence alone reaches the defect as often as
sentence-plus-dump did; a score near 60% would mean the metric is now reading
what it claims to read. **Either is a result. Reading a drop as a regression is
the mistake to avoid.**

**The metric that can kill the idea is the false-alarm rate.** A model that
hedges on everything is never wrong and never useful. If false alarms rise, the
hedging bought nothing and the result is negative — say so.

**Metric gate before reading anything:** the patched scorer must still print
**76** and **86** on the stored v2 rows. A scorer that does not reproduce those
is measuring something else and its deltas mean nothing.

## Schedule — 2 days

| when | what | GPU |
|---|---|---|
| Day 1 AM | contract v3 in `config.py` + `schema.py`; rewrite corpus answers; run `template_audit.py` on the new corpus as pre-flight | no |
| Day 1 PM | patch the scorer; **pass the 76/86 gate** | no |
| Day 1 eve | launch seed 42 and seed 7 **chained in one script** (~7h each) | 14h |

### The training command — note the sequence length

    ORACLE_OUTPUT_CONTRACT=v3 .venv/bin/python fine_tuning/train_sft.py \
        --dataset data/sft_v4_suggest.jsonl --max-seq-length 1152 --seed 42
    # then the same with --seed 7, chained

**`--max-seq-length 1152`, not the 1024 default.** The v3 prompt is 662 tokens
against v2's 651 and the answers run ~22 tokens longer, so at 1024 the fitter
drops 43 records — and every one of them is a BUGGY case, which would leave the
corpus 59% clean instead of 52% and train a model biased toward saying nothing.
At 1152 nothing is dropped and 29 diffs are shrunk, a better fitting profile
than the v2 corpus's own 210 shrunk / 12 dropped. **Training at 1024 on a corpus
fitted to 1152 re-truncates it**, which is the "trains on an unknown subset of
itself" failure the builder warns about.
| Day 2 AM | score both, audit both | no |
| Day 2 PM | write up | no |

Chain the seeds so a crash on the first loses one run, not the night.

## Guard rails, learned the hard way

- **Two seeds, always.** Seed alone flips 24 of 101 cases; a single-seed delta
  is not a result. If only one seed fits, say "single seed, not readable".
- **Run `template_audit.py` on every checkpoint** before believing any
  comparison between two of them.
- **A corpus-vs-corpus control is not a control.** `sft_v3_extract` shares 78 of
  `sft_v2_pilot2`'s 80 records. Only an out-of-family checkpoint is a floor.
- **Vary the answer wording in the corpus.** v3 repeated one whole summary 54
  times. Check it before training, not after.
- **Keep the held-out cases out of the corpus.**

## Known risk

The model may not reliably emit the new JSON shape, burning the night on
malformed output. Mitigation is the design rule above: keep the shape close to
v2, swap two fields, do not redesign the schema.

---

## Progress

- [x] `bench/template_audit.py` written and run over 14 checkpoints (30 Aug)
- [x] Parroting measured: real (30% vs 0.0% floor), and NOT v3-specific
- [x] Corpus repetition control: v2 25%, v3 26% — repetition hypothesis dead
- [x] Three-tier accuracy split measured (where 87-98 / direction 79-93 / value 15-31)
- [x] Dry run: 69-85% of answers carry a false value, ~0 headline cost to drop it
- [x] This plan
- [x] `config.py` — contract v3 (+ `client.py` word-diff rendering)
- [x] `dataset_builder/schema.py` — `check`/`confidence`, v3 prompt + hint, selectors
- [x] `dataset_builder/build_mechanism_corpus.py` — hedged varied answers, 3 corpus bugs fixed
- [x] Corpus pre-flight: repeated-sentence + ghost-filename checks in `write_jsonl`
- [x] `bench/basic_bench.py` — `check_useful`, calibration, observable retired under v3. **Gate PASSES: 76 and 86 exactly**
- [x] `data/sft_v4_suggest.jsonl` built and pre-flighted
- [x] `score_v4.sh` — serve, tunnel, all three sets, both seeds, then report
- [x] Train v4 seed 42 + seed 7, chained, 2 epochs — **`--max-seq-length 1152`**
- [x] Score all four v4 checkpoints on all three sets, 12/12 suites (31 Aug)
- [x] **v4 verdict: thresholds cleared, evidence recited.** False alarms 9-11%
      (band 4-15%), `locus unconfirmed` 0 everywhere, `observable` claims on
      clean code 12/11 -> 0/0. But verbatim copying tripled (basic 28.7/24.3%
      against v2's 11.6/6.2%), `check` saturated at 100% "the edit touches",
      and `confidence` ran 3 `possible` in 168 responses. Mixed, leaning
      negative on the novelty claim. Not written up as a win.
- [x] **Epoch 1 vs epoch 2 separates the causes.** The epoch-1 checkpoints are
      measurably less converged and copy IDENTICALLY. Convergence is not the
      cause; the corpus template is. Epoch 2 also moved nothing past seed noise
      on any metric — so v6 trains one epoch, at half the GPU cost.
- [x] The `check` field measured directly (`bench/check_field_audit.py`):
      `distinct*` = 1 on all 21 mech_heldout cases on both seeds; cross-seed
      byte identity 13/21 on `check` against 0/21 on `summary`; and
      `check_useful` halves when the appended token list is stripped.
- [x] `data/sft_v6_suggest.jsonl` — per-case probe/watch, 341 distinct checks
      of 366, "the edit touches" gone, self-similarity median 54.6% -> 37.4%
- [ ] Train v6 seed 42 + seed 7, chained, **one epoch**, 1152 — launched 31 Aug
- [ ] Score with `./score_v6.sh`, audit, write up

### Scoring, when training lands

    ./score_v4.sh              # both seeds, then compare + audit
    ./score_v4.sh seed42       # one seed
    ./score_v4.sh --report     # re-read rows already scored, no GPU

**No merge step.** `llm_explainer/serve.py:62` detects `adapter_config.json` and
loads a LoRA adapter directly, which is exactly what `train_sft.py` writes.
Merging first would cost ~20 minutes per seed and change nothing.

**The contract is set on the CLIENT side.** `serve.py` only generates from the
`messages` it is handed, so the system prompt comes from the local config.
`score_v4.sh` sets `ORACLE_OUTPUT_CONTRACT=v3 ORACLE_INCLUDE_SCHEMA=false
ORACLE_INFERENCE_SAMPLES=1` on every bench call. Verified before the run:
the v3 prompt is selected (names `check` and `confidence`, never `before`), the
diff renders through `dataset_builder.worddiff` as v3 requires, and the client
parses a fenced v3 answer with `before`/`after` absent.

**The script refuses to start while training is running** — serving needs
~2.5GB and training holds ~4.5GB of the 6GB card, so both at once is an OOM
mid-run and a half-written rows file.

Note for reading the audit afterwards: the new corpus has 6502 distinct 8-grams
against `sft_v3_extract`'s 2337, so it is a harder thing to copy and the metric
is correspondingly more sensitive. `v2_pilot2` scores 11.6% against it, versus
30.5% against the corpus it was trained on.

### The corpus that is ready to train

`data/sft_v5_suggest.jsonl`, built with:

    ORACLE_OUTPUT_CONTRACT=v3 .venv/bin/python \
        dataset_builder/build_mechanism_corpus.py --no-bulk \
        --tokenizer Qwen/Qwen2.5-Coder-3B-Instruct --max-seq-length 1152 \
        --out data/sft_v5_suggest.jsonl

**The 30 Aug run trained on `data/sft_v4_suggest.jsonl`, not this file.** Same
366 records and the same builder, but v4 carried a token-trimming defect: 207 of
366 targets (56%) named an identifier that does not exist — `len(xs` for
`len(xs)`, `double)correct` for `(double)correct` — because `tok.strip()` took
off a closing bracket whose opener was interior. Both v4 checkpoints reproduce
it. v5 is that defect fixed (0 of 366) and nothing else; v4 is retained so
`template_audit.py` can still measure those checkpoints against what they saw.
Any copying number for `v4`/`v4_seed7`/`v4_ep1`/`v4_ep1_seed7` reads against v4.

| | v3 corpus (`sft_v3_extract`) | new (`sft_v4_suggest`) |
|---|---|---|
| records | 399 | 366 |
| distinct targets | 98 | **356** |
| worst whole-target repeat | 54 (14%) | **2 (1%)** |
| worst repeated sentence | 105 (26%) | **32 (9%)** |
| targets naming a file not in their prompt | 282 | **0** |
| clean share | 47% | 52% |
| dropped by the sequence budget | — | **0** |
| confidence split | n/a | 75% likely / 25% possible |
