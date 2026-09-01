# Results

Every measurement taken, with the command that reproduces it. Numbers only —
interpretation lives in `ROADMAP.md`, corpus provenance in `DATASETS.md`.

Status as of 2026-09-01.

---

## The first measurement on real code: 88-91% of findings are wrong, and most of them describe code that is not in the diff (2026-09-01, latest)

The 40 real commits have been sitting sampled-but-never-graded since 26 Aug.
They are now generated (both v6 seeds) and hand-graded. This is the first
evidence in the project from code nobody wrote for it, and it does not agree
with the bench.

### The apparatus

    ./score_v6.sh          # generates data/real_commits_v6{,_seed7}.jsonl + .md

`bench/real_commits.py` samples 40 commits from five projects that are in
**neither** the SFT corpus nor the gate's training set (`real_commits.py:41`) —
axios, clap-rs, fastapi, gin-gonic, spring-boot. There is **no stage-1 gate in
this path**: all 40 go straight to stage 2, which is not how the pipeline is
meant to run. Sampling is uniform over project history, so the base rate of
defect-introducing commits is low — these are overwhelmingly fixes, features,
refactors, docs and annotation passes.

### The grade

Graded by reading all 40 diffs, per the rule the sheet already carried: a
mechanism claim that was not executed is not graded.

| | seed 42 | seed 7 |
|---|---|---|
| commits carrying >=1 finding | **29 / 40** | **22 / 40** |
| findings | 35 | 24 |
| `locus` — right place, right mechanism | **1** | **1** |
| `mechanism` — right place, inverted claim | 1 | 1 |
| `wrong` | **32 (91%)** | **21 (88%)** |
| not graded (needs execution) | 1 | 1 |

The one correct finding, on both seeds, is `axios e8cf487`: the commit removes
the es6-promise polyfill, and both name `lib/axios.js` and the consequence for
environments without a native `Promise`.

### `wrong` here mostly means fabricated, not mistaken

The explanations describe code that is absent from the diff:

| commit | the diff | the claim |
|---|---|---|
| `fastapi 9b35d355` | adds `if size: results.update(...)` to three tutorial files | a `float()`/`int()` cast and a "moved numeric check" — neither exists |
| `axios 22ce6db` | adds trailing args to `createError`/`enhanceError` | `TypeError: Failed to construct 'Error': 2 arguments required` — not a JS error message |
| `axios 4c4e648` | `Object.hasOwnProperty` -> `Object.prototype.hasOwnProperty` | that the guard now admits inherited keys. The two are the same function; verified `node -e` |
| `spring 2d4baa33`, `118bf101`, `fab69e44` | JSpecify `@Nullable` / `@NullMarked` | runtime `NullPointerException`s from compile-time annotations |
| `gin ce2201c`, `a48f83c`, `dbd8a25` | pure feature additions | a defect in the feature each commit adds |

Two are worth escalating out of the pile.

**An inverted security fix.** `fastapi d11f820a` is a docs commit teaching the
dummy-hash idiom to *prevent* a timing attack. Seed 42 reports that it "means
`authenticate_user` will always return True, allowing unauthenticated access."
That is the opposite of what the idiom does, asserted as a vulnerability.

**The one real defect in the set was missed by both seeds.** `gin 34b1d026`
drops the `flusher, ok := w.ResponseWriter.(http.Flusher)` guard, leaving an
unchecked type assertion that can panic. Seed 42 invented an unrelated
status-code bug on the same file; seed 7 returned clean.

Two mechanical defects: `fastapi 3611c3fc` (seed 42) emitted two byte-identical
findings and `d11f820a` two near-identical ones, so 35 overstates the number of
distinct claims.

### Why no bench number predicted this

`clean_heldout` reports `false_alarm` 0/34 on every v6 checkpoint. Both numbers
are correct and they measure different things. Its clean cases are renames and
fix-reversions of 5-8 line synthetic functions. A real clean commit is a feature
addition, a CI matrix edit, an annotation pass or a docs change — shapes with no
representation in a 366-record corpus at all. **The bench false-alarm result
does not transfer to real commits, and nothing in this repo previously showed
that.**

Direction is also worth recording: 29/40 (seed 42) and 23/40 (seed 7) answers
came back `post-breaks` on a sample that is mostly fixes and features.

### Both cheap remedies were measured on this data, and neither works

The two interventions the repo already contains — filter the output on
`evaluate.py`'s grounding rule, or filter the input on the stage-1 gate — were
run against the graded sheets. Neither is usable, and the reasons are different.

**Output filter: `grounded()` removes every true positive.**

    from evaluate import grounded          # evaluate.py:82, already unit-tested

| hand grade | grounded | ungrounded (would be filtered) |
|---|---|---|
| `locus` — the only correct finding | 0 | **1** |
| `mechanism` | 1 | 0 |
| `wrong` | 24 | **8** |
| not graded | 0 | 1 |
| **seed 42 total** | 25 | **10 / 35 (29%)** |
| **seed 7 total** | 21 | **3 / 24 (12%)** |

It discards **100% of the true positives to remove 25% of the false ones**
(10% on seed 7). The eight it does catch are genuine fabrications, so it has
value as a diagnostic — but not as a gate on output.

The failure is structural, not a threshold. The one correct finding
(`axios e8cf487`) says the code "attempts to use `window.Promise`"; the diff's
changed lines hold `P.polyfill` and `require('es6-promise')`. The model
paraphrased rather than cited. `grounded()` measures vocabulary overlap, and
correct-but-paraphrased is indistinguishable from invented under that measure.

**Input filter: the gate rejects all 40 commits.**

    Gatekeeper.load().score(diff)          # ml_model/gate.py:131

| | |
|---|---|
| score range over the 40 real commits | **0.001 – 0.116** |
| `GATE_THRESHOLD` as configured | **0.15** |
| commits reaching stage 2 | **0 / 40** |

At its configured threshold the pipeline never invokes stage 2 on any of these
commits. The false-positive rate is zero because the system declines to answer.
The two-stage pipeline as configured is **inert on real commits**, and no test
in the repo would have shown that, because `real_commits.py` has no gate in its
path and every other bench set skips stage 1 too.

Re-calibrating does not rescue it:

| threshold | commits passed | seed 42 findings kept | correct finding kept |
|---|---|---|---|
| 0.010 | 29/40 | 26/35 | yes |
| 0.020 | 16/40 | 19/35 | yes |
| **0.034** | **12/40** | **14/35** | **yes** |
| 0.050 | 4/40 | 5/35 | **no** |
| 0.150 (configured) | 0/40 | 0/35 | no |

The best operating point still passes 14 false alarms to keep the one correct
finding, which sits at 0.034 — mid-pack, with false alarms scoring both above
and below it. There is no threshold that separates them.

One genuine positive: the gate's *ranking* carries signal even though its
calibration does not. The four lowest-scoring commits (0.001–0.005) are all the
spring-boot nullability-annotation commits, which is exactly right — it knows an
annotation pass is not worth reviewing. It simply scores everything else nearly
as low.

**What the pair of results means.** The gate was trained on ApacheJIT and these
five projects were chosen to sit outside both it and the SFT corpus. So *both
stages are out of distribution on the same data and fail independently* — the
gate by rejecting everything, the explainer by fabricating. Neither end can
filter the other's errors, which is why the two obvious remedies both fail.

### What is NOT claimed here

The grading is one reader, on unlabelled data, from diffs, without executing.
The core fabrications are unambiguous — a cast that is not in the file, an error
message that does not exist in the language — but the softer `wrong` calls
(a finding that describes an addition accurately and then files it as a defect)
are a judgement, and another grader could reasonably split them differently.
`clap a126149` is left ungraded on both seeds for exactly this reason: settling
it needs `cargo test -p clap_complete`, which was not run.

No claim is made about precision. A uniform sample of mature-project history
contains almost no defect-introducing commits, so there are essentially no
positives to be precise about; what is measured here is the false-alarm rate,
and it is high.

This does not touch the v6 copying result below, which is a bench measurement
and stands. What it changes is what that result means: v6 fixed recitation, and
recitation was not what stood between this model and real code.

---

## Apparatus: the TUI sent every fine-tuned checkpoint the one prompt shape it never trained on (2026-09-01, later)

Found by driving `sft-v6-suggest` through the TUI against `TestJIT/pyalgo`
rather than through `basic_bench.py`. **No number in the section below is
affected** — every bench run sets the flag correctly. What is affected is every
impression ever formed of a fine-tuned model *in the TUI*.

### The observation

`pyalgo 9227c63` "restore the inclusive bound" — `range(1, n)` becomes
`range(1, n + 1)` in `sum_to`. Ground truth: `buggy: false`, `kind: fix`.

    semantic review
    No change in stats.py.

    no defects found in the diff

The verdict is right and `no defects found in the diff` is a UI string
(`ui/tui_app.py:487`). The model-authored half, `summary`, is false: the diff
changes `stats.py`, which is the only thing it does. No `where:`/`change:`/
`check:` lines were rendered, meaning `effect` came back `None` —
a **v1-shaped answer out of a v3 checkpoint**.

Three things ruled it out as recitation or as a model defect:

| ruled out | evidence |
|---|---|
| recited from the corpus | "no change in" appears in **0 of 366** v6 targets, and nowhere in the tree |
| a UI-generated string | `grep` finds no such format string; only the header and the empty-findings line are UI |
| the expanded context | `with_context=True` and `False` both return the identical bad answer |

On the bench the same shape is answered correctly — all 21 `-fix` cases in
`clean_heldout`, both seeds, return `direction: post-fixes` with a populated
effect and a summary naming the changed token ("This undoes the defect in
`py-loop-bound-loosen-fix.py`. The `len(xs)` bound is now `<`…"). `effect
claimed` is 34/34 on that set.

### The mechanism

`llm_explainer/client.py:191`, under `INCLUDE_SCHEMA="auto"`:

    include_schema = not (backend == "transformers" and trained)

For `backend == "ollama"` that is unconditionally `True`, and the selftest pins
it (`client.py:628`: `assert OracleClient(backend="ollama").include_schema`).
The comment beside it says why — over HTTP the client cannot see whether it is
talking to a fine-tuned model, so it sends the full JSON Schema.

Every corpus is built schema-free and every bench run sets
`ORACLE_INCLUDE_SCHEMA=false` (`score_v6.sh`). The TUI set nothing. It was the
only caller handing a fine-tuned checkpoint a prompt shape absent from its
training data.

### The measurement

Same commit, same live `sft-v6-suggest` server, the flag as the only variable:

| | `include_schema=True` (TUI default) | `include_schema=False` (as scored) |
|---|---|---|
| `effect` | **`null`** | `trigger` + `check` + `direction` + `confidence` |
| `summary` | "No change in stats.py." | "…restores the inclusive bound in `sum_to`, which is the repair direction." |
| `findings` | 0 | 0 |

### The fix, and what it does not fix

`ui/tui_app.py` now carries `os.environ.setdefault("ORACLE_INCLUDE_SCHEMA",
"false")` beside the existing `ORACLE_OUTPUT_CONTRACT` guard — the same defect
one prompt field over, and the contract got a guard in August while the schema
flag never did. `setdefault`, so an explicit `true` still wins for a base-model
baseline, which does need the schema. `client._selftest()` still passes: the
`auto` rule is untouched, only the TUI's default.

**The answer is still wrong on this commit after the fix.** It returns
`direction: post-breaks` for a commit that is a fix, while its own summary calls
it "the repair direction" — the field contradicts the prose beside it. The
verdict (0 findings) and the `check` are right. `clean_heldout` does not catch
this: v6 scored `post-fixes` on all 21 of its fix cases, and this real commit is
the same shape and fails. It is the first direction error observed on real code
and it is not in any bench number.

---

## The v6 result: the template is gone, the scores did not move, and `confidence` is seed-bimodal (2026-09-01)

The 31 Aug section below rebuilt the corpus and closed with "whether a model
trained on the rebuilt corpus copies less, or scores the same, is not measured
until the two-seed v6 run is scored". It is scored. It copies about half as
much, it scores the same, and one contract field is worse than v4 in a way v4
could not have shown.

### The run

    ~/oracle/run_v6.sh          # setsid nohup, log ~/oracle/run_v6.log
    ./score_v6.sh               # both seeds, three sets, then compare + audit

| | seed 42 | seed 7 |
|---|---|---|
| adapter | `artifacts/sft-v6-suggest` | `artifacts/sft-v6-suggest-seed7` |
| tag | `v6` | `v6_seed7` |
| started → exit 0 | 20:42:30 → 00:26:48 | 00:26:48 → 04:10:54 |
| wall clock | 3 h 44 m | 3 h 44 m |

ONE epoch each (46 steps), `--max-seq-length 1152`, corpus
`data/sft_v6_suggest.jsonl`, md5 `053b5c02c8a4e4bcec7378accbdff248` verified on
both boxes, 366 records, 0 dropped. The second epoch was dropped because the
31 Aug `v4_ep1` comparison returned "no" on every metric across all three sets.

### Measured noise floor, three corpora

Two seeds, identical corpus, seed the only variable. An effect smaller than this
on a set is not readable there.

| pair | basic | mech_heldout | clean_heldout |
|---|---|---|---|
| v2_pilot2 / v2_seed7 | 14 of 46 | 10 of 21 | **0 of 34** |
| v4 / v4_seed7 | 5 of 46 | 2 of 21 | **0 of 34** |
| **v6 / v6_seed7** | **4 of 46** | **3 of 21** | **1 of 34** |

### 1. False alarms — the gate holds

    python bench/compare_seeds.py --base v4 v4_seed7 --new v6 v6_seed7

| set | v2 pair | v4 pair | **v6 pair** | readable? |
|---|---|---|---|---|
| basic | 5 / 5 | 4 / 5 | **7 / 3** | no — seeds disagree |
| mech_heldout | 0 / 0 | 0 / 0 | **0 / 0** | no — unchanged |
| clean_heldout | 0 / 0 | 0 / 0 | **0 / 1** | no — seeds disagree |

Seed 42 alone reads 7/46 (15%), above v4's 9–11%; seed 7 reads 3/46 (7%), below
it. The band is 3–7 against v4's 4–5. **No readable rise.** A single-seed read of
this metric would have reported a regression that the pair does not support.

The one new fact: `clean_heldout` produced the first non-zero false alarm in the
project's history (1/34, seed 7). The v2 pair and all four v4 checkpoints scored
0/34. It sits exactly at v6's own noise floor for that set — but that floor was
**0** for both earlier corpora, so v6 is marginally less seed-stable there.

### 2. Location — held

Locus confirmed, buggy cases only. On `basic` v6 is **33/33 on both seeds**,
against v4's 31/33 and 33/33 — the two v4 misses are its two errored rows. On
`mech_heldout` v6 is **20/21 on both seeds** where v4 was 21/21 on both.
`compare_seeds` reads that as inside the ±2 band, and it is; it is recorded
because it is consistent across two independently trained seeds rather than a
single flip.

### 3. Copying — halved on every set, both seeds

    python bench/template_audit.py --corpus data/sft_v6_suggest.jsonl --tags v6 v6_seed7
    python bench/template_audit.py --corpus data/sft_v4_suggest.jsonl --tags v4 v4_seed7

Each family read against the corpus it actually trained on. A checkpoint read
against a corpus it never saw is a floor, not a copying rate, and the two must
not share a column.

| run | set | mean | median | p90 | ≥50% | longest |
|---|---|---|---|---|---|---|
| v4 | basic | 28.7% | 19.9% | 66.7% | 12/44 | 30 |
| v4_seed7 | basic | 24.3% | 14.0% | 60.0% | 10/46 | 25 |
| **v6** | basic | **11.8%** | 9.7% | 30.6% | **0/46** | 13 |
| **v6_seed7** | basic | **14.8%** | 9.8% | 30.8% | **1/46** | 15 |
| v4 | mech_heldout | 16.2% | 17.8% | 23.6% | 0/21 | 17 |
| v4_seed7 | mech_heldout | 16.0% | 10.4% | 26.7% | 2/21 | 12 |
| **v6** | mech_heldout | **9.0%** | 9.3% | 17.9% | **0/21** | 11 |
| **v6_seed7** | mech_heldout | **13.2%** | 10.0% | 29.8% | **0/21** | 14 |
| v4 | clean_heldout | 71.1% | 74.1% | 77.4% | **34/34** | 26 |
| v4_seed7 | clean_heldout | 74.6% | 75.0% | 79.4% | **33/34** | 28 |
| **v6** | clean_heldout | **35.2%** | 39.4% | 61.8% | **5/34** | 23 |
| **v6_seed7** | clean_heldout | **34.2%** | 35.4% | 45.5% | **4/34** | 20 |

The worst number in the v4 run — essentially every `clean_heldout` answer at
least half verbatim corpus text — goes from 34/34 and 33/34 to 5/34 and 4/34.

### The `check` field is composed, not recited

    python bench/check_field_audit.py --tags v4 v4_seed7 v6 v6_seed7 \
        --pairs v4:v4_seed7 v6:v6_seed7

`distinct*` blanks the filename and the trailing token dump, leaving the
sentence.

| tag | set | n | distinct\* | useful | no tail | top 4-gram |
|---|---|---|---|---|---|---|
| v4 | mech_heldout | 21 | **1** | 20/21 | 11/21 | **21/21** |
| v4_seed7 | mech_heldout | 21 | **1** | 20/21 | 11/21 | **21/21** |
| **v6** | mech_heldout | 21 | **21** | 19/21 | 19/21 | 15/21 |
| **v6_seed7** | mech_heldout | 21 | **21** | 20/21 | 20/21 | 11/21 |
| v4 | basic | 44 | 9 | 29/31 | 19/31 | 36/44 |
| v4_seed7 | basic | 46 | 9 | 29/33 | 21/33 | 36/46 |
| **v6** | basic | 46 | **45** | 30/33 | 30/33 | 21/46 |
| **v6_seed7** | basic | 46 | **44** | 30/33 | 30/33 | 20/46 |
| v4 / v4_seed7 | clean_heldout | 34 | 13 / 14 | — | — | 22/34, 21/34 |
| **v6 / v6_seed7** | clean_heldout | 34 | **32 / 33** | — | — | 13/34, 13/34 |

Cross-seed byte identity — two independently trained seeds, same case. `summary`
is the control: models that reason can agree on content and still differ in
wording.

| pair | set | identical `check` | identical `summary` |
|---|---|---|---|
| v4 / v4_seed7 | basic | 16/46 | 0/46 |
| v4 / v4_seed7 | mech_heldout | **13/21** | 0/21 |
| v4 / v4_seed7 | clean_heldout | 21/34 | 1/34 |
| **v6 / v6_seed7** | basic | **1/46** | 0/46 |
| **v6 / v6_seed7** | mech_heldout | **0/21** | 0/21 |
| **v6 / v6_seed7** | clean_heldout | **4/34** | 0/34 |

The v4 seeds agreed byte for byte on 62% of held-out mechanism checks and never
on a summary. The v6 seeds now agree on `check` at the same rate they agree on
`summary` — which is to say, not at all. Saturation is reduced but not gone:
v4's top 4-gram covered 21/21 mech answers, v6's covers 15/21 and 11/21.

Counting `check` as prose *lowers* v6's copying rate on `clean_heldout`
(35.2% → 30.6%, seed 42), because the field is now less recited than the
surrounding summary. In v4 it was the most templated field in the answer.

### 4. `check_useful` rose, and `compare_seeds` understates it

`useful` **equals** `no tail` on both v6 seeds and all sets: the strip is a no-op
because there is no token dump left to remove. v6's number is therefore earned by
the sentence, which v4's never was.

| set | v4 raw (dump included) | v4 sentence only | **v6** |
|---|---|---|---|
| basic | 29/31, 29/33 | 19/31 (61%), 21/33 (64%) | **30/33 (91%), 30/33 (91%)** |
| mech_heldout | 20/21, 20/21 | 11/21 (52%), 11/21 (52%) | **19/21 (90%), 20/21 (95%)** |

**`compare_seeds` reads the raw `check_useful` off the rows** — 29,29 → 30,30 on
basic — and reports "inside seed band". That comparison is against v4's inflated
figure and understates the change by roughly 30 points. Against the sentence-only
column the move is **+30pp on basic and +38pp on mech**. The pre-registered
expectation was a *drop* toward 52–64%.

### 5. `confidence` — the one thing that did not transfer

The corpus was rebalanced 75% → 58% `likely` (213/153) and the `possible` rule
widened to cover overflow and truncation. The output distribution:

| set | v6 seed 42 | v6 seed 7 |
|---|---|---|
| basic | 46 likely, **0 possible** | 10 likely, **36 possible** |
| mech_heldout | 21 likely, **0 possible** | 5 likely, **16 possible** |
| clean_heldout | 34 likely, **0 possible** | 33 likely, 1 possible |

Same corpus, same recipe, one epoch each. Seed 42 emitted `likely` on all 101
answers. Seed 7 applied the corpus rule — `likely` on unchanged code where the
diff settles it, `possible` where the outcome depends on caller values — on 78%
of `basic`. The field is not constant, as v4 suggested; it is **bimodal on
seed**, which is worse, because a single-seed run reports either "dead" or
"working".

Precision inverts on `mech_heldout` (seed 7): `likely` 2/5 (40%), `possible`
15/16 (94%). The model is more accurate when it hedges.

A content change to the corpus (what `check` says) transferred completely. A
distribution change (how often `confidence` says `possible`) did not transfer at
all.

### The extract prediction is falsified a second time

| case | v4 | v4_seed7 | v6 | v6_seed7 |
|---|---|---|---|---|
| php-extract-helper ← stable target | quiet | ALARM | **ALARM** | **quiet** |
| py-extract-helper ← stable target | quiet | quiet | **ALARM** | **quiet** |
| go-extract-helper | quiet | quiet | ALARM | quiet |
| java-extract-method | ALARM | ALARM | ALARM | quiet |
| js-extract-helper | quiet | ALARM | quiet | quiet |
| c-const — CONTROL | ALARM | ALARM | ALARM | ALARM |
| py-comprehension — CONTROL | ALARM | ALARM | ALARM | ALARM |

Predicted to go quiet; they are seed-split, exactly as under v4. Both non-extract
controls still alarm in all four checkpoints, so the model did not go globally
timid — the predicted effect is simply absent.

### Headline accuracy — flat

`fully correct`, v6 vs v4, both as seed pairs:

| set | v4 pair | **v6 pair** | readable? |
|---|---|---|---|
| basic | 40 / 41 | **39 / 43** | no — seeds disagree |
| mech_heldout | 21 / 19 | **20 / 17** | no — inside seed band |
| clean_heldout | 34 / 34 | **34 / 33** | no — seeds disagree |

No metric moved past noise in either direction. v6 also parsed all 46 `basic`
cases where v4 seed 42 errored on 2.

### What is NOT claimed here

The copying reduction is a property of two seeds on three synthetic sets, and
`clean_heldout` — where the drop is largest — is the set whose answers are
shortest. Nothing here shows the model is *reasoning*; it shows the stored
answers are no longer reproducible from the corpus, which is the objection the
31 Aug reading raised and not more than that.

The 40 real commits (`data/real_commits_v6.jsonl`,
`data/real_commits_v6_seed7.jsonl`) are generated but **unlabelled and
un-hand-graded**; they contribute no number above.

`check_useful` grades by substring against each case's `must_mention`. It
rewards naming the right identifier; it does not verify the suggested test would
run, and no check in any v6 answer has been executed.

---

## The `check` field was a template, and the metric that graded it was scoring a token dump (2026-08-31)

The v4 result cleared both gating thresholds while verbatim copying tripled, and
the epoch-1 checkpoints proved convergence was not the cause — the corpus was.
This is the corpus defect, measured, and the rebuild that answers it.

### What the field actually was

`suggested_effect()` built `check` from a ten-key dictionary keyed on the case's
`category`. The corpus has **two** categories — 82 `logic-error`, 18
`off-by-one` — so eight of the ten entries were dead and the field was two
sentences with a filename slot, plus a token list scraped off the word-diff.

| `data/sft_v4_suggest.jsonl` (= v5, same field) | |
|---|---|
| distinct `check` strings in 366 targets | **100** |
| targets containing "the edit touches" | **357 (97%)** |
| a case's six upsampled copies, byte-identical `check` | **all of them** |

### What the model did with it

    python bench/check_field_audit.py --tags v4 v4_seed7 --pairs v4:v4_seed7

`distinct*` blanks the filename and the trailing token dump, leaving the
sentence — the part that is supposed to vary with the case.

| tag | set | n | distinct | distinct\* | most repeated 4-gram |
|---|---|---|---|---|---|
| v4 | basic | 44 | 44 | **9** | 36/44 "once and compare against" |
| v4 | mech_heldout | 21 | 21 | **1** | 21/21 "the changed branch more" |
| v4 | clean_heldout | 34 | 34 | 13 | 22/34 "the changed branch more" |
| v4_seed7 | mech_heldout | 21 | 21 | **1** | 21/21 "the changed branch more" |

**One sentence, on all 21 held-out mechanism cases, on both seeds.** The raw
`distinct` column reads 21/21 and means nothing: every check names its own file.

The cross-seed control settles that this is recitation and not convergence on a
good answer. Two independently trained seeds, same case:

| pair | set | identical `check` | identical `summary` |
|---|---|---|---|
| v4 / v4_seed7 | basic | 16/46 | **0/46** |
| v4 / v4_seed7 | mech_heldout | 13/21 | **0/21** |
| v4 / v4_seed7 | clean_heldout | 21/34 | 1/34 |
| v2_pilot2 / v2_seed7 | basic | 0/46 (no field) | 5/46 |

Two models that reason from a diff can agree on content and still differ in
wording. These agree byte for byte on `check` and never on `summary`.

### The metric was reading the token dump, not the sentence

`_check_useful` grades `check` by substring against the case's `must_mention`,
and the v4 corpus appended `— the edit touches \`a\`, \`b\`, \`c\`` to every one.
Strip that tail from the stored answers and re-grade:

| tag | set | `check_useful` | with the tail removed |
|---|---|---|---|
| v4 | basic | 29/31 (94%) | **19/31 (61%)** |
| v4 | mech_heldout | 20/21 (95%) | **11/21 (52%)** |
| v4_ep1 | basic | 32/33 (97%) | **21/33 (64%)** |
| v4_seed7 | mech_heldout | 20/21 (95%) | **11/21 (52%)** |

Roughly half the headline score was a list of changed tokens pasted after the
sentence. A reader who ran only what the sentence told them would reach the
defect about half the time, not 95% of the time.

### Why no existing check caught it

`bench/template_audit.py` scores copying over `summary` + `findings[].explanation`
and **has never read `effect.check`**. The field that was 97% template was
invisible to the tool whose whole purpose is measuring templating, so it did not
appear in any number the pre-registered plan was checked against. `--with-check`
now exists, off by default so published figures stay comparable.

### A second defect found in the same pass

`_V3_CLEAN_CLOSERS` was drawn for both `refactor` and `fix` cases. A `fix` case
carries `direction: post-fixes` — the behaviour *does* change, that is what a
repair is — and roughly 40 v4 fix targets signed off with "I do not see a
behaviour change to chase" directly beneath it. A target that contradicts itself
teaches the model to do both. Fixes now have their own closers.

### The rebuild — `data/sft_v6_suggest.jsonl`

The category dictionary is gone. Each of the 37 mechanism cases carries its own
`check` in `meta.json`, authored beside the case in `bench/annotate_checks.py`:

* `probe` — the input or call that reaches the defect
* `watch` — what moved in the diff and what to look for, phrased as a question
* `restored` — what the fix puts back (the 28 cases with a `-fix` child)

The 63 clean cases derive theirs: a `fix` reuses its parent's probe with the
parent's `restored`; a rename greps for the old name; an extraction takes the
same probe as the buggy sibling with the same diff shape and the opposite watch,
so the counter-aligned pair becomes the two halves of one comparison. Six
connective forms, rotated so a case's six copies take six different ones.
Nothing is executed; every field is derivable from the diff.

    ORACLE_OUTPUT_CONTRACT=v3 .venv/bin/python \
        dataset_builder/build_mechanism_corpus.py --no-bulk \
        --tokenizer Qwen/Qwen2.5-Coder-3B-Instruct --max-seq-length 1152 \
        --out data/sft_v6_suggest.jsonl

| corpus | v4 / v5 | **v6** |
|---|---|---|
| records | 366 | 366 |
| distinct `check` strings | 100 (27%) | **341 (93%)** |
| "the edit touches" | 357 (97%) | **0** |
| distinct assistant turns | 359 | **366 (all)** |
| worst repeated sentence | 9% | **5%** |
| unbalanced backticked identifiers | 0 (v5) | 0 |
| `check_useful` on its own targets | — | 177/177 |
| confidence split | 75% likely | **58% likely** |

### Corpus self-similarity, leave-one-CASE-out

    python bench/template_audit.py --corpus data/sft_v6_suggest.jsonl --self

How much of a target is reachable verbatim from **other cases** — the whole
upsampled family is left out, or the metric measures upsampling and reports
~91% for every corpus ever built.

| corpus | mean | median | ≥50% | longest run |
|---|---|---|---|---|
| `sft_v4_suggest` | 46.3% | 54.6% | 193/366 | 117 words |
| **`sft_v6_suggest`** | **40.8%** | **37.4%** | **153/366** | **62 words** |
| `sft_v4_suggest` +check | 56.3% | 63.7% | 203/366 | 118 words |
| **`sft_v6_suggest`** +check | **49.0%** | **46.8%** | **171/366** | **96 words** |

The median target went from more than half recitable out of its neighbours to
about a third, and the longest shared span halved. This is a corpus property,
knowable before a GPU is booked — which is the point, because the v4 run was
launched on a corpus whose defect was already in the file.

### What is NOT claimed here

Every number above is a corpus or a re-score of stored v4 answers. Whether a
model trained on the rebuilt corpus copies less, or scores the same, is not
measured until the two-seed v6 run is scored. The thresholds in
`docs/PLAN_SUGGEST_CONTRACT.md` are unchanged and false alarms remain the metric
that can kill it.

---

## Three corpus bugs behind "the model recites templates" (2026-08-30, later still)

Found while building the v3 suggestion contract. All three are in the
extract-boundary family — the exact family the v3 experiment was built to
teach — and together they explain the hand-read symptom that the template audit
had just shown was NOT caused by repetition.

### Bug 1 — 27 targets said "renames `a local` to `a new name`"

`clean_direction()` read `m["renamed"]` with a placeholder default. The nine
`*-extract-boundary-refactor` cases EXTRACT a helper; they rename nothing and
carry no `renamed` key, so all nine fell through to the rename branch and took
the default. At x3 that is 27 records whose target, for a diff that adds a
function, reads:

    This commit renames `a local` to `a new name` in c-extract-boundary.c.
    Every use is updated in place ... and the program's behaviour is unchanged.

`sft-v3-extract` then emitted that sentence on all five held-out extract cases,
none of which is a rename. **It was read on 30 Aug as the model reciting a
template. It was the model correctly reproducing a target that was false.**
Extractions now have their own branch, and a missing `renamed` is a hard error
instead of a default.

### Bug 2 — every clean target named a file that was not in its own diff

Summaries were composed with `{parent}.{ext}` while `case_diff` writes the diff
header as `{id}.{ext}`: the target said `c-extract-boundary.c` for a diff that
says `c-extract-boundary-refactor.c`. All 54 clean targets did this. A filename
absent from the prompt cannot be derived, only memorised — the same shape as the
per-execution temp dir stripped on 29 Aug.

Related, and separately fixed: five hand-authored `analysis.json` files had
copied the `b`-prefixed form out of the word-diff header
(`bpy-min-empty-guard.py` for `py-min-empty-guard.py`), because
`dataset_builder.worddiff` renders `a/foo.c b/foo.c` as `afoo.c bfoo.c`.

### Bug 3 — nine cases, one summary, upsampled to 54

The nine `*-extract-boundary` mechanism cases are the same program in nine
languages — same `passing()`/`grade()`, same `> 60` — and share one
hand-authored summary. Correct prose, nine times, x6 upsampling = **54
byte-identical targets, 14% of the corpus.** That is the text
`sft-v3-extract-seed7` recited on a held-out case with no such comparison.

Upsampling exists to weight a case; k cases sharing a target are already
weighted k times. `mechanism()` now uses `times // k`, so those nine contribute
9 records instead of 54.

### Why every 29 Aug check passed

`write_jsonl` already had a duplication check with a 20% bar. The v3 corpus's
worst WHOLE-TARGET repeat was 54/399 = 13.5%, so it passed. The 105-of-399
figure was a *sentence* inside otherwise-differing summaries, which that check
cannot see. Pre-flight now also measures:

- **the most repeated sentence** (>= 8 words) across all targets, bar 10%
- **targets naming a source file absent from their own prompt**
- whole-target duplication, bar lowered 20% -> 10%

Run against the corpora that already exist, the new checks fire on both:

| corpus | distinct targets | worst sentence | ghost filenames |
|---|---|---|---|
| `sft_v2_pilot2` (318) | 80 | 78 = **25%** | **255** |
| `sft_v3_extract` (399) | 98 | 105 = **26%** | **282** |
| new v3-contract corpus (366) | 355 | 34 = 9% | **0** |

The ghost filenames are `main.py` (27x), `main.c`, `main.go`, `Math.java` — they
come from the executed runtime traces v2 puts in `effect.before/after`, which
name the runner's own file rather than the case's. That is why
`basic_bench_v3.jsonl`'s first row answers a **C** case with a **Go** panic
trace citing `main.go:6`. Under v3 there is no executed output in the target and
the count is zero.

---

## The template audit: parroting is real, and it is NOT a v3 defect (2026-08-30, later)

**Both pre-registered gates failed. The 30 Aug diagnosis below ("the v3 corpus
taught two templates") is WRONG as stated — not because the parroting is not
real, but because v2 does it just as hard. Do not rebuild the v3 corpus on the
strength of it.**

Reproduce:

    python bench/template_audit.py --corpus data/sft_v3_extract.jsonl \
        --tags gptoss120b base44 oracle46 mechanism_v1 mechanism_v2 \
               v2_pilot2 v2_seed7 v3 v3_seed7

### Gate 1 — do the v3 runs copy more than the v2 runs? NO

Verbatim 8-word coverage: the share of an answer's prose words (`summary` +
`findings[].explanation`, JSON schema excluded) sitting inside an 8-word window
that appears word-for-word in the corpus. `bench/basic`, mean over 46 cases:

| checkpoint | saw this corpus | coverage |
|---|---|---|
| `base44` (untuned) | no | **0.0%** |
| `oracle46` | no | 0.3% |
| `gptoss120b` | no | 0.8% |
| `mechanism_v1` | no | 3.4% |
| `mechanism_v2` | no | 13.0% |
| `v2_pilot2` (seed 42) | 78 of its 80 records | **30.5%** |
| `v2_seed7` (seed 7) | 78 of its 80 records | 18.6% |
| `v3` (seed 42) | yes | **30.2%** |
| `v3_seed7` (seed 7) | yes | 17.9% |

**The metric is sound and the parroting is enormous** — a third of seed 42's
answer text is lifted verbatim, against a 0.0% floor from an untuned model on
the same 46 cases. Longest single verbatim run: 86 words.

**And v3 is indistinguishable from v2**: 30.2 vs 30.5, 17.9 vs 18.6. The
pre-registered condition was "the v3 pair shows markedly higher overlap than
the v2 pair". It does not. It shows the same.

What actually separates the four runs is the **seed**, not the corpus: seed 42
lands at ~30% on either corpus, seed 7 at ~18% on either corpus.

### Why the earlier cross-corpus control was worthless

`sft_v3_extract` is `sft_v2_pilot2` plus 20 records: 78 of 80 v2 records are
byte-identical rows in v3, 98 distinct records against 80. Scoring a v2
checkpoint against "the v3 corpus" was scoring it against its own training
data. The only usable floor is a checkpoint from outside the family, which is
why the table above starts with four of them.

### Gate 2 — is v3 more repetitive than v2? NO

| | records | distinct summaries | most-repeated sentence |
|---|---|---|---|
| `sft_v2_pilot2` | 318 | 80 | 78x = **25%** of records |
| `sft_v3_extract` | 399 | 98 | 105x = **26%** of records |

Same sentence in both ("Every use is updated in place — ... behaviour is
unchanged"), same share. **The "105 of 399" figure that triggered the rebuild
plan is not a v3 anomaly; v2 was 78 of 318.**

One real v3-only difference: v3 repeats a single *whole summary* 54 times (14%
of records — the 9 clean `extract-boundary-refactor` pairs all share one canned
answer), where v2's most-repeated whole summary appears 6 times (2%). That
concentration is genuine. It also **did not move the copying metric at all**,
which is the point.

### The hand-read "8 rename claims" is a seed effect, not a corpus effect

Summaries applying a template to a case it does not fit, all three sets pooled:

| run | "renames X to Y" on a non-rename case | "repairs the ..." on a non-fix case | total |
|---|---|---|---|
| `v2_pilot2` | 1 | 10 | **11** |
| `v2_seed7` | 1 | 0 | 1 |
| `v3` | 8 | 2 | **10** |
| `v3_seed7` | 1 | 0 | 1 |

Seed 42 misapplies a template ~10 times on either corpus; seed 7 once. The five
cases hand-read on 30 Aug were the v3 seed-42 rename misfires — real, but the
v2 seed-42 checkpoint misfires the *repair* template exactly as often. By this
project's own readability rule (both seeds must move the same way, further than
the seed pair's own spread) template misapplication is **not readable** as a v3
effect.

### What this costs, and the one thing it makes newly suspect

Every v2-vs-v3 comparison published so far is a comparison of two checkpoints
that recite at the same rate. The corpus change did not alter the failure mode
it was blamed for.

`clean_heldout` is the set most affected. All four runs sit at **82% verbatim
coverage** there, with 34/34 verdicts and zero seed flips. No case id leaks
(checked: 0 of 34 appear in the corpus) — but the *answer sentences* do. That
set rewards emitting a memorised sentence on a recognised diff shape. Its prized
"zero noise floor" is zero because it is a template-recall test, so a perfect
score there is much weaker evidence than it has been read as.

### Consequences for the plan

- **Test 3 (rebuild the v3 corpus, retrain) is cancelled by its own gate.** It
  would have been measured against a v2 baseline that parrots identically.
- **The proposed pre-flight repetition check would not have caught this.** v2
  and v3 score the same on it; it would have passed or failed both. The check
  worth adding is `bench/template_audit.py` against an out-of-family floor
  checkpoint, which measures the symptom instead of a proxy for it.
- The extract-shape question ("does coverage fix the false alarms?") remains
  untested, and is now known to be untestable on this corpus family without
  fixing the parroting first.

---

## SUPERSEDED IN PART — v3 extract-boundary: the prediction is falsified, and the corpus taught two templates (2026-08-30)

Two checkpoints on the v3 extract-boundary corpus, `--seed 42` and `--seed 7`,
identical in every other respect (verified from `training_args.bin`, not from
the live cmdline: `seed=42`/`seed=7`, `lr=2e-4 bs=1 ga=8 epochs=2.0`).

| | launched | finished | runtime | steps |
|---|---|---|---|---|
| `sft-v3-extract` | not recorded | 29 Aug 06:07 | not recorded | 100 / epoch 2.0 |
| `sft-v3-extract-seed7` | 29 Aug 06:08:13 | 29 Aug 13:21 | 7h12m (25,950 s) | 100 / epoch 2.0 |

`train_loss` 0.2177 on seed 7 is the average over training; the final step is
0.0108, token accuracy 0.9975. No divergence.

Scored with the contract pinned on BOTH sides, GPU-served through the same
remote-serve + tunnel harness as the v2 baselines (no CPU fallback, which would
not have been comparable):

    ORACLE_OUTPUT_CONTRACT=v2 ORACLE_INCLUDE_SCHEMA=false ORACLE_INFERENCE_SAMPLES=1 \
      .venv/bin/python bench/basic_bench.py --backend ollama \
      --model-name sft-v3-extract --host http://localhost:8111 --word-diff-module \
      --out data/basic_bench_v3.jsonl
    # --root bench/mechanism_heldout --out data/heldout_mech_v3.jsonl
    # --root bench/clean_heldout     --out data/heldout_clean_v3.jsonl
    # and the same three with sft-v3-extract-seed7 -> *_v3_seed7.jsonl

    python bench/compare_seeds.py

Metric gate checked before reading anything: `compare_seeds.py` reproduces the
documented v2 headlines exactly — seed 42 `31+11+34 = 76`, seed 7 `35+17+34 =
86`. The metric has not drifted.

### The pre-registered prediction, and what happened

Stated before the run: **`php-extract-helper` and `py-extract-helper` go quiet
on BOTH v3 seeds.** Those are the only two of the five held-out extract cases
where the v2 pair agrees, so they are the only two where movement can be
attributed to the corpus rather than the seed.

| case | v2/42 | v2/7 | v3/42 | v3/7 | |
|---|---|---|---|---|---|
| `php-extract-helper` | ALARM | ALARM | quiet | **ALARM** | stable target — **not met** |
| `py-extract-helper` | ALARM | ALARM | quiet | quiet | stable target — met |
| `go-extract-helper` | ALARM | quiet | quiet | ALARM | seed-unstable |
| `java-extract-method` | quiet | ALARM | quiet | ALARM | seed-unstable |
| `js-extract-helper` | quiet | quiet | quiet | **ALARM** | no headroom — **new false alarm** |

One of two targets moved. **The prediction as stated is falsified.**

`false_alarm` on `bench/basic` went **5,5 -> 2,7**. The seeds disagree in
opposite directions on the metric the corpus was built to move. Seed 42 read
alone is a triumph; seed 7 read alone is a regression. This is exactly the
failure mode the two-seed protocol exists to catch.

### Nothing improved readably; one thing regressed readably

`_readable()` requires both seeds to move the same way by more than the spread
the v2 pair shows on its own (floored at 2).

| set | metric | v2/42 | v2/7 | v3/42 | v3/7 | readable? |
|---|---|---|---|---|---|---|
| basic | fully | 31 | 35 | 40 | 38 | no — inside band (±4) |
| basic | false_alarm | 5 | 5 | 2 | 7 | no — seeds disagree |
| mech_heldout | fully | 11 | 17 | 17 | 19 | no — inside band (±6) |
| clean_heldout | **observable** | 12 | 11 | **6** | **6** | **YES (−6/−5)** |
| clean_heldout | fully | 34 | 34 | 34 | 34 | unchanged |

`basic` `fully` rises on both seeds (+9/+3) but the smaller move is +3 against a
±4 band. Suggestive, not reportable. `mech_heldout` cannot resolve anything —
10 of its 21 cases flip on seed alone.

**The only readable effect of the entire v3 run is a regression**, and it is on
`clean_heldout`, the one set with a zero noise floor. Four cases lose
`observable_ok` on both v3 seeds: `java-unit-scale-rename`,
`py-boundary-flip-rename`, `py-loop-bound-loosen-fix`, `py-precedence-avg-rename`.

It is not a claiming failure — `effect_claimed` is unchanged at 33/34 — and
`direction` actually improved (31,33 -> 33,34). The model still says which way
the change goes; it states the concrete observable value correctly half as
often:

| case | v2 before/after | v3 before/after |
|---|---|---|
| `java-unit-scale-rename` | 5000 / 5000 | **3000 / 3000** |
| `py-precedence-avg-rename` | 30.0 / 30.0 | **33.33 / 33.33** |
| `py-boundary-flip-rename` | `[False, True, True]` | **`[False, True]`** |

Self-consistent, correctly labelled `unchanged`, and numerically wrong. The
model stopped computing the value and started producing a plausible one.

### THE FINDING: the corpus taught two templates, and the seed picks one

The headline numbers understate the problem. Reading the stored `predicted`
answers on the five held-out extract cases shows neither seed is reasoning about
extraction at all — both are reciting verbatim strings from the v3 corpus.

**Seed 42 recites the clean-direction rename template.** On `py-`, `go-`,
`java-`, `js-` and `php-extract-helper` alike it answers:

> "This commit renames `xs` to `ys` in *<file>*. Every use is updated in place —
> the declaration and its readers are edited, not deleted — and the program's
> behaviour is unchanged."

None of those cases is a rename. That sentence occurs **105 times in
`data/sft_v3_extract.jsonl`** (399 records). Counting summaries that claim a
rename on a case whose id is not a rename, pooled over all three sets:

| run | rename-claims | on a non-rename case |
|---|---|---|
| `v2_pilot2` | 18 | 1 |
| `v2_seed7` | 19 | 1 |
| **`v3`** | 26 | **8** |
| `v3_seed7` | 18 | 1 |

**Seed 42's false alarms did not drop because it learned that extraction is
safe. They dropped because it stopped reading the diff and recited the clean
template.** Its `5 -> 2` is template collapse, not transfer.

**Seed 7 recites the buggy half of the same pair.** On `java-extract-method` it
answers that the helper "compares with `> 60` where the inline test used
`>= 60`" — a verbatim string from `data/sft_v3_extract.jsonl`, describing the
`*-extract-boundary` training case. The held-out case contains no such
comparison. That is fabrication sourced directly from the corpus.

So the counter-aligned pair did what it was designed to prevent at the level of
a surface rule, and then failed one level down: instead of learning "added
function = safe" or "added function = suspicious", the model memorised **both
answer texts** and emits whichever one the seed favours. The apparent
improvement and the apparent regression are the same defect.

This also explains the `observable` regression above: a model reciting a
template is not computing a value, so its literals drift.

### What survives

**The control held.** `c-const` and `py-comprehension` false-alarm on all four
runs, v2 and v3, both seeds. The model did not become globally timid, so the
weaker "it just flags less" explanation is ruled out — which is what makes the
template diagnosis the remaining one.

### What this run answers

- Extract-shape coverage was **not** the cause of the extract false alarms.
  The corpus bought no readable improvement and cost observable-correctness.
- A 399-record corpus in which one summary sentence appears 105 times teaches
  that sentence, not the reasoning behind it. **Template frequency is now a
  corpus-validation property that nothing in `build_mechanism_corpus` checks.**
- Two seeds remain mandatory. Every single-seed reading of this run — in either
  direction — would have been wrong.

---

## The v2 pilot: the contract is learned, and the evidence it emits is mostly wrong (2026-08-28)

`sft-v2-pilot`, the first checkpoint trained on the v2 output contract. 318
records, 2 epochs, 80/80 steps in 5h44m, finished 01:49 WIB. `train_loss` 0.279,
final step 0.0091, token accuracy 0.9977, no divergence. Step arithmetic holds —
318 x 2 / 8 = 79.5 -> 80 — so no record was silently dropped.

Scored with the contract pinned on BOTH sides, which is what the configuration
finding of 27 Aug exists to enforce:

    ORACLE_OUTPUT_CONTRACT=v2 ORACLE_INCLUDE_SCHEMA=false ORACLE_INFERENCE_SAMPLES=1 \
      .venv/bin/python bench/basic_bench.py --backend ollama \
      --model-name sft-v2-pilot --host http://localhost:8111 --word-diff-module \
      --out data/basic_bench_v2_pilot.jsonl
    # --root bench/mechanism_heldout --out data/heldout_mech_v2_pilot.jsonl
    # --root bench/clean_heldout     --out data/heldout_clean_v2_pilot.jsonl

### Read this first: the live run reported the opposite of the truth

The run printed `effect claimed 0/46 <- v1 contract`, which reads as "the model
did not learn the contract". **It had learned it perfectly.** Two apparatus
defects, both fixed:

- `basic_bench.py` built each row by hand-picking keys out of `grade()` and
  **dropped every `effect_*` key on the way in**, so `summarise()` saw no claim
  on any row. A live run could not report a nonzero effect tier no matter what
  the model emitted. Rows now spread `grade()` whole.
- The zero-claims line **hardcoded** the string `v1 contract`, asserting a cause
  it never checked. It now reads `OUTPUT_CONTRACT` and, under v2, says the zero
  is a finding to investigate rather than an expected result.

The full answer was already stored under `predicted` and `--score` re-grades
stored rows, so nothing had to be re-run. **Every number below comes from
`--score` over the stored rows, so all three sets are graded by one scorer.**

`--score` needs `--root` for a non-default set; without it the ids do not
resolve and it prints `no gradable rows`. It fails safe, but silently.

### The format half of the contract: answered without qualification

| | `bench/basic` | `mechanism_heldout` | `clean_heldout` |
|---|---|---|---|
| n | 46 | 21 | 34 |
| well-formed `effect`, all four keys | **46/46** | **21/21** | **34/34** |
| `direction` a legal value | 46/46 | 21/21 | 34/34 |
| errored calls | 0 | 0 | 0 |

`unclear` never fired. **The baseline was 0 claims on all seven stored runs** —
re-verified here: `heldout_mech_v2_n21` and `heldout_clean_v2_n34` carry 0/21 and
0/34 effect objects. This is the first checkable behavioural claim any checkpoint
in this project has made, on 101/101 answers.

### The claims themselves

| | `bench/basic` | `mechanism_heldout` | `clean_heldout` |
|---|---|---|---|
| fully correct (locus) | 36/46 (78%) | 14/21 (67%) | 34/34 (100%) |
| false alarms | 1/46 (2%) | 0/21 | 0/34 |
| direction right | 35/46 (76%) | 19/21 (90%) | 30/34 (88%) |
| observable right | 17/46 (37%) | 4/21 (19%) | 14/34 (41%) |
| **FABRICATED** | **6/46 (13%)** | **1/21 (5%)** | **3/34 (9%)** |

The acceptance criterion was written in advance with two halves: `direction_ok`
materially above the rate implied by v1's six template misses, **and**
`fabricated` at zero. **The first half is met — 84/101 overall, against a
baseline where the question could not be asked. The second is not.**

Against the previous checkpoint under identical rendering and schema settings,
`bench/basic` locus is flat (36/46 against 37/46) while **false alarms fall 5 ->
1**; `clean_heldout` is unchanged at 34/34; `mechanism_heldout` falls 19/21 ->
14/21. That drop decomposes as **one verdict flip and four `unconfirmed`** —
the model still detects 18/21 but stops citing the token `must_mention` asks
for. At least some read as correct paraphrase (`go-boundary-flip`: "flips the
inequality in inRange ... return true for inputs less than 100 instead of
greater or equal", which never writes `<=` or `boundary`), so 14/21 is a floor
and the true gap is smaller than five cases. **The matching rule was not
touched** — this repo requires measuring any such change against random pairings
first, and that control has not been run.

### `direction_ok` earns its place; `observable_ok` and `trigger` do not

Splitting the observable failures into their two kinds, over all 101 answers:
**9 inverted** (the claim matches the opposite side exactly — `java-string-equals`
claims `false -> true` where the truth is `true -> false`) and **57 invented**
(`c-const` claims `3 -> 3` where the program prints `9 -> 9`: direction right,
value fabricated).

The tier that justifies the contract: on `bench/basic`, **4 of the 5 inverted
and 3 of the 5 fabricated answers were graded CORRECT by the locus scorer.**
`identified()` structurally cannot see an inverted claim; `direction_ok` can, and
it catches 2 answers on `bench/basic` that locus passes.

**`effect.trigger` is degenerate: it echoes the case filename in 101/101
answers.** The builder fills it with `f"running {m['id']}.{m['ext']} as written"`
(`build_mechanism_corpus.py:102`) while the schema specifies "One input or
condition that exposes the difference, e.g. `xs = [1,2,3]`". The corpus
contradicts its own field description, and the model learned the corpus. The
field currently carries no information and **must not be searched by any scorer**
— it contains the case name, so matching `must_mention` against it grounds the
answer on its own filename. That was tested: searching `trigger` would flip three
`mechanism_heldout` cases to "identified" purely on the case name (`boundary`
from `go-boundary-flip`, `precedence` from `py-precedence-avg`). Searching only
`before`/`after` flips 0 and 1. **The locus drop above is real, not a scoring
artifact.**

### The fabricated evidence has a mechanism, and it is in the corpus

10 fabrications across 101 answers: 9 absolute paths, 1 behaviour-change claim on
byte-identical output. The path rule is proof, not suspicion, and is now stronger
than "the model was never handed a path": `outputs()` executes each case in a
**fresh temp dir on every call**, so the real path differs between two runs of the
scorer on the same file (`go-nil-map`: `tmpaswlmjkc`, then `tmppg2vk9c9`). The
path is not a function of the input and cannot be known by anything.

Where the fabricated paths come from:

| cited | appears in `sft_v2_pilot.jsonl` | emitted on |
|---|---|---|
| `/tmp/tmpd6rhx_a0/` | **6 records** | `php-divzero-guard`, `rs-index-bound`, `rs-unwrap-none`, `js-swallowed-error-fix`, `rb-swallowed-error-fix` |
| `/tmp/tmp8bzrai1/` | 0 — but `/tmp/tmp8bzrai1x` is in **6 records** | `go-loop-bound-loosen`, `go-loop-bound-loosen-fix` |
| `/tmp/tmp7v1q1q1x/`, `/tmp/tmp_qlzz_hx/` | 0 | `go-nil-map`, `py-pop-guard` |

**One memorized temp directory is re-emitted as execution evidence on five
different cases in four languages**, and a second is emitted as a one-character
truncation of a corpus token. Seven of nine are traceable to the training set;
two are novel invention in the learned register.

**The cause is `executed_effect`.** `obs()`
(`build_mechanism_corpus.py:94`) takes the raw bytes of the executed output and
truncates to 200 chars with no normalisation, so **66 of 318 records (21%) carry
a per-execution random temp dir**, drawn from only 16 distinct values. The
function's own docstring says it exists to stop the model inventing absolute
paths; it put real, unlearnable ones into a fifth of the targets instead.

The correction is one line and was verified read-only: collapsing
`/tmp/tmp\w+/` takes 66 records to 0 while leaving the claim true —
`-2147483648 main.c:5:14: runtime error: signed integer overflow ...` keeps
everything informative and loses only the token nothing could have predicted.

**This is not simply copying.** The v1 corpora contain **zero** absolute paths,
yet the earlier checkpoint still fabricated `bench/mechanism_pilot/` paths
(27 Aug). The register tracks whatever the corpus supplies; what v2 added was
tokens that are impossible to get right.

### `observable_ok` is not reproducible, and is slightly inflated

Three identical `--score` runs over the same stored `clean_heldout` file gave
**14, 15, 14**. Locus and `fabricated` are stable; `observable_ok` is not.

The cause is the same temp dir. `rb-loop-bound-loosen-fix` claims `before = "3"`;
the real pre-output is a Ruby `TypeError`, so the claim is **wrong**. But
`_obs_match`'s numeric rule — "the claim's integers all appear in the real
output" — matches `3` against the random directory name: `tmpoc3wg92t` contains a
`3` and scores the wrong claim correct, `tmp5p5o2xzg` does not. **The tier is
decided by a coin flip on a random string.**

Stripping the temp dir before matching: 36/101 -> **35/101**. The inflation is
one case today, but the mechanism is unbounded for any single-digit claim, and it
makes the tier non-reproducible.

**Both fixed the same day.** `outputs()` and `obs()` now strip the token, and the
scorer change was measured against random pairings before it shipped, as this
repo requires: own-case 35/101 against random-case 3/101, **unchanged** by the
strip. Discrimination is identical; what it buys is determinism — over six
independent executions of all 101 cases, raw gave 35 four times and 36 twice,
normalised gave 35 six times. Every observable number in the tables above is the
stable one.

That `_obs_match` grounds only 3/101 against a randomly paired case is worth
recording on its own: this rule discriminates, unlike the `identifiers()` bug
that grounded 18-36% against unrelated diffs.

### What this run does and does not answer

It answers, exactly as scoped in advance: the model emits a well-formed `effect`
(101/101) and `direction_ok` beats zero decisively (84/101). Both yes.

It does **not** answer whether the contract fixes explanation correctness. 80
unique targets heavily upsampled, and `observable_ok` at 35% is **ambiguous
between "the contract is wrong" and "318 records is too little"** — and now a
third reading is on the table and better supported than either: **the corpus
teaches an unlearnable token, and the scorer rewards accidental matches on it.**
Fix those two before spending a larger training run on the question.

---

## The v2 output contract: evidence before verdict, and a claim that can be checked (2026-08-27)

The diagnosis first, because it is the reason for every change below.

**Every missed defect is the model agreeing with its own first sentence.** Of
54 buggy cases across `bench/basic` and `mechanism_heldout`, v2 missed six, and
this is what its summary said on each:

    c-array-bound      "This commit repairs the logic-error ... goes back to its correct behavior"
    go-offbyone        "The commit repairs the logic-error ... goes back to its correct form"
    java-array-bound   "This commit repairs the logic-error ... goes back to its correct form"
    php-shadow-update  "The commit renames `total` to `sum`. Every use is updated in place ..."
    py-shadow-update   "The commit renames `total` to `subtotal`. Every use is updated in place ..."
    js-reverse-index   (its own wording)

**Five of six are training templates, reproduced verbatim** — three the `fix`
template, two the `rename` template — and every one of those templates ends in
"no defect". `php-shadow-update` shows the mechanism plainly: the real defect is
a shadowed variable, which on the surface looks like a rename, so the model
matched the shape, printed the sentence, and the sentence carried it to a clean
verdict.

Two structural causes, both fixable, neither reachable by prompting:

1. **The contract emits the verdict before the evidence.** `Analysis` declared
   `summary` first, so `summary` is the first key generated. A model that has
   written "this commit repairs the off-by-one" has no continuation available
   except `findings: []` — generation runs forwards only. Meanwhile the v1
   system prompt's step 1 asks it to "state to yourself what runtime behaviour
   differs now" and gives it **nowhere to write that down**, so the reasoning
   step has no slot and collapses into the conclusion.
2. **The templates are cheaper than reading the code.** 162 clean-direction
   records taught two fixed sentences that any superficially-matching diff can
   trigger.

This is why five prompt-rule attempts lost. The format forces the order; the
corpus rewards the shortcut.

### What changed

**`config.OUTPUT_CONTRACT`** (`v1` | `v2`, default `v1`). One switch moves the
system prompt, the short format hint and the expected keys together. They are
deliberately not selectable apart: this session measured a checkpoint scored
under a contract it was not trained on losing six cases in forty-six to that
alone.

**`Effect`** (`dataset_builder/schema.py`), the first field of `Analysis`:

    {"effect": {"trigger": "...", "before": "...", "after": "...",
                "direction": "post-breaks|post-fixes|unchanged"}, ...}

`before` and `after` are what the program *does* — a value, an exception, a
panic — not what the diff looks like. An unrecognised `direction` becomes
`unclear` rather than being coerced onto `unchanged`; mapping garbage onto a
clean verdict would hide the failure the grader exists to count. `to_json()`
uses `exclude_none`, so v1 targets stay byte-identical.

**Two grading tiers** (`bench/basic_bench.py::grade_effect`), scored on every
run and every `--score`:

| tier | question | catches |
|---|---|---|
| `direction_ok` | which way did the code move | inversions — the failure that has dominated every hand-grade, and which `identified()` structurally cannot see |
| `observable_ok` | does the claimed before/after match what ran | invented values |
| `fabricated` | proof, not suspicion | an absolute path the model was never given, or a claimed behaviour change on a case whose two sides are byte-identical |

The absolute-path rule is sound by construction: `build_user_message` passes a
bare `name.ext` and the diff headers carry `a/name.ext`, so the model is never
handed a filesystem path. Any absolute path in an answer is fabricated.

`observable_ok` is deliberately lenient — containment either way, or the
claim's integers all appearing in the real output, or claim and reality naming
the same runtime failure. Strict equality would fail correct paraphrases, which
is the mistake the grounding checker already made once.

**The corpus builder fills `effect` by executing the case**
(`build_mechanism_corpus.py::executed_effect`), so every target's behavioural
claim is true by construction, and the `fix` template no longer quotes program
output in its prose — that string is what taught the model the *form* of citing
executed output without teaching that the citation must be real.

Target diversity survives the change: the `effect` object carries per-case real
output, so `clean_direction` still yields **54/54 distinct assistant turns**.

### The baseline, and what it is not

    .venv/bin/python bench/basic_bench.py --score data/basic_bench_mechanism_v2.jsonl

| run | locus | effect claimed |
|---|---|---|
| `oracle-merged` unified | 41/46 | **0/46** |
| `mechanism-v1` unified | 39/46 | **0/46** |
| `mechanism-v2` module word-diff | 37/46 | **0/46** |
| `mechanism-v2` `mechanism_heldout` n=21 | 19/21 | **0/21** |
| `mechanism-v2` `clean_heldout` n=34 | 34/34 | **0/34** |

**No checkpoint in this project has ever made a checkable behavioural claim.**
That is the honest starting point, and it is reported over the answers that
made a claim rather than over `n`, so "did not answer this question" is never
counted as "answered it wrongly".

Every locus number above is unchanged by this work — verified by re-scoring all
seven stored runs — so the new tiers add a measurement without moving an
existing one.

**Nothing here is evidence that the v2 contract works.** It is untrained. The
next run is the test, and its acceptance criterion is stated in advance:
`direction_ok` materially above the rate implied by v1's six template misses,
with `fabricated` at zero.

---

## Counter-aligned boundary cases: the surface rule is falsified, and a worse failure surfaces (2026-08-27)

`next-session.md` item 3. Both held-out sets were aligned with the direction
rule the 27 Aug section proposed — tightening-is-buggy, loosening-is-fix — so
neither could test it. Fourteen counter-aligned cases now exist, every label
proved by execution:

| direction | label | where | n |
|---|---|---|---|
| loosening (`<` -> `<=`) on a loop bound **IS a bug** | `buggy` | `bench/mechanism_heldout` | 7 |
| tightening (`<=` -> `<`) on a loop bound **IS a fix** | `fix` | `bench/clean_heldout` | 7 |

Languages: c, go, java, javascript, php, python, ruby. Each is a `total`/`joinAll`
helper whose bound is a separate parameter or the container's length; the `-fix`
member of each pair is the same two files reversed.

    .venv/bin/python bench/basic_bench.py --root bench/mechanism_heldout --verify
    .venv/bin/python bench/basic_bench.py --root bench/clean_heldout    --verify
    # 21/21 and 34/34 verified by execution

**Denominators changed: `mechanism_heldout` 14 -> 21, `clean_heldout` 27 -> 34.**
The 12/14 and 27/27 in the section below are on the old sets and are not
comparable to anything measured on the new ones.

### v2 on the expanded sets

    ORACLE_INFERENCE_SAMPLES=1 ORACLE_INCLUDE_SCHEMA=false .venv/bin/python \
      bench/basic_bench.py --backend ollama --model-name sft-mechanism-v2 \
      --host http://localhost:8111 --word-diff-module \
      --root bench/mechanism_heldout --out data/heldout_mech_v2_n21.jsonl
    # --root bench/clean_heldout --out data/heldout_clean_v2_n34.jsonl

| set | n | fully correct | false alarms |
|---|---|---|---|
| `mechanism_heldout` | 21 | 19 (90%) | 0 |
| `clean_heldout` | 34 | 34 (100%) | 0 |

The two misses are `php-shadow-update` and `py-shadow-update`, the same unseen
family as before. **Every one of the 14 counter-aligned cases is answered
correctly.**

### The direction rule is falsified

A model applying "loosening is a repair, tightening is a defect" would fail all
seven `-loosen` cases. v2 gets 7/7, in all seven languages, including the three
where it fails `bench/basic`:

    go-loop-bound-loosen   for i := 0; i [-<-]{+<=+} n; i++
    -> "The change loosens the loop condition from 'i < n' to 'i <= n', causing
        the loop to run one extra iteration when n > 0 ... leading to a slice
        out-of-range panic at runtime."          findings: 1, correct

Together with the configuration rerun in the section above — where
`oracle-merged`, which has no clean-direction training at all, fails the same
`bench/basic` off-by-one cases under the same rendering — the surface-rule
attribution is refuted from two independent directions. **It should not be
carried into the paper.**

What still needs explaining is narrower: why v2 fails `c-array-bound`,
`go-offbyone` and `java-array-bound` while passing seven counter-aligned cases
of the same family. The one structural difference visible is that the failing
cases bound the loop with the container's own length expression (`len(xs)`,
`xs.length`, a literal `5`) while the passing ones bound it with a separate
parameter `n`. That is an observation, not a result — it is one hypothesis and
it has not been tested.

### The finding that outranks all of the above: fabricated execution evidence

`go-offbyone`, which v2 calls a repair, justifies the call like this:

    "the program's output changes from 'panic: runtime error: index out of
     range [4] with length 3\n\ngoroutine 1 [running]:\nmain.sum(...)\n\t
     /home/arp/Documents/oracle/bench/mechanism_pilot/go-offbyone.go:6 ...'
     to '9'."

`bench/mechanism_pilot/go-offbyone.go` **does not exist.** The model fabricated
a runtime panic trace, complete with an absolute path into the training corpus's
own directory and plausible line numbers, and presented it as observed program
behaviour.

The mechanism is the `fix` template. `dataset_builder/build_mechanism_corpus.py:150`
composes every `fix` target as *"the program's output changes from {was} to
{now}"*, filling `was`/`now` from the case note's executed before/after output.
That teaches the form — quote the program's output when you judge something a
fix — without teaching that the quote must be something you actually ran.

Across v2's 101 answers on the three evaluation sets:

| | count |
|---|---|
| answers examined | 101 |
| quote executed program output | 42 |
| of those, cite an absolute filesystem path | 6 |
| paths that point into `bench/mechanism_pilot/` | 6 |
| of those paths that exist | **0** |

Two of the fabricated paths name `go-loop-bound-loosen` and
`py-loop-bound-loosen` — cases created on 27 Aug, in `mechanism_heldout`, that
have never been in `mechanism_pilot` and did not exist when v2 was trained. The
model is not recalling a path; it is generating one under the directory its
training corpus was built from.

**Five of the six sit inside answers the scorer graded correct**, and they are
part of `clean_heldout`'s 34/34. The verdict is right and the justification is
invented.

**This decides `next-session.md` item 5** in the direction of the strict
reading, and sharpens it: the fabrication at issue is not a decorative worked
example, it is *evidence* — an appeal to program behaviour the model never
observed, in the exact register the corpus taught it to sound authoritative in.
A reader checking the claim finds a path that does not exist.

**What this costs, and what it buys.**

- Every "fully correct" figure in this project is a locus-and-verdict number.
  None of them inspect whether the justification is fabricated. `34/34` and
  `19/21` are floors on verdict, not statements about explanation quality.
- The grounding check does not catch this: a fabricated path and a fabricated
  panic trace are made of tokens that appear in the diff and the case name.
- It is a clean, reportable result of exactly the type `ROADMAP.md`'s
  contingency names. Templated distillation targets transfer their *rhetorical
  form* along with their content, and a form that cites executed output teaches
  the model to cite executed output it does not have. That is a general claim
  about distillation for explanation, demonstrable in six lines.

**Next, in order:** count fabricated evidence across `oracle-merged` and
`mechanism-v1` on the same sets (does the untemplated checkpoint do it too, and
at what rate); then decide whether the `fix` template should quote output at all.

---

## The configuration confound, settled: the "regression" is the renderer (2026-08-27)

`next-session.md` item 2. The three-way table in the section below compares
checkpoints that were never measured under the same conditions. One rerun —
`oracle-merged` in v2's *exact* configuration, no training — settles it, and
reverses the result.

    ORACLE_INFERENCE_SAMPLES=1 ORACLE_INCLUDE_SCHEMA=false .venv/bin/python \
      bench/basic_bench.py --backend ollama --model-name oracle-merged \
      --host http://localhost:8111 --word-diff-module \
      --out data/basic_bench_oracle46_wordmodule.jsonl

All five runs on `bench/basic` (n=46), scored with the current scorer via
`--score`:

| run file | checkpoint | schema | rendering | locus | false alarms |
|---|---|---|---|---|---|
| `basic_bench_oracle46` | `oracle-merged` | on | unified | **41/46 (89%)** | 2 |
| `basic_bench_oracle46_word` | `oracle-merged` | on | git `--word-diff` | 36/46 (78%) | 4 |
| `basic_bench_oracle46_wordmodule` | `oracle-merged` | off | module word-diff | **35/46 (76%)** | 1 |
| `basic_bench_mechanism_v1` | `mechanism-v1` | on | unified | 39/46 (85%) | 7 |
| `basic_bench_mechanism_v2` | `mechanism-v2` | off | module word-diff | **37/46 (80%)** | 5 |

**Same weights, configuration only: 41 -> 35.** Six cases, 13 points, no
retraining. The v2 "regression" that section was written to explain is 41 -> 37,
four cases. **The configuration effect is larger than the entire gap it was
invoked to account for.**

**Under identical measurement v2 is the better checkpoint**, 37/46 against
35/46. One of `oracle-merged`'s 46 calls (`rb-string-mutate`) returned no
schema-valid JSON after two tries and is scored as no-finding; granting it
charitably gives 36/46, still below v2. The `schema on` runs are the ones with
the 41 and 39; nothing about the checkpoints changed between them.

Decomposition, schema held on so the renderer moves alone:

| change | locus | off-by-one |
|---|---|---|
| baseline (unified, schema on) | 41/46 | 8/9 |
| renderer only -> git word-diff | 36/46 | 5/9 |
| renderer + schema off -> module word-diff | 35/46 | 4/9 |

The renderer carries most of it; dropping the schema adds roughly one more case.

### This overturns the surface-rule attribution

| off-by-one (n=9) | unified | git word-diff | module word-diff |
|---|---|---|---|
| `oracle-merged` | 8/9 | 5/9 | **4/9** |
| `mechanism-v1` | 9/9 | — | — |
| `mechanism-v2` | — | — | **5/9** |

Every unified run scores 8–9 of 9. Every word-diff run scores 4–5 of 9,
**whichever checkpoint it is.** `oracle-merged` never saw a single
clean-direction record and still collapses to 4/9 in the configuration v2 was
measured in — one case *worse* than v2.

The section below attributes v2's off-by-one collapse to the 162
clean-direction records installing a surface rule keyed to the direction of the
operator swap. **That attribution does not survive this run.** The collapse
reproduces on a checkpoint with no such training. On `c-array-bound`, under the
same module word-diff:

    oracle-merged: "The change expands the loop condition from i < 5 to i <= 5,
                    causing the loop to include the last element of the array.
                    This corrects a buffer overflow and does not introduce any
                    new runtime defects."                         findings: []

    mechanism-v2:  "This commit repairs the logic-error in c-array-bound.c: the
                    program goes back to its correct behavior, and no new
                    defects are introduced."                      findings: []

`oracle-merged` reads the swap correctly — it names `i < 5` and `i <= 5` — and
then calls the loosening a repair anyway. Same verdict, same error, different
vocabulary.

**What each factor actually supplied.** The rendering supplies the mistake: the
direction rule is present in a checkpoint trained only on unified diffs, and
appears as soon as that checkpoint is shown a word-diff. The clean-direction
corpus supplies the *wording* — v2 draws the `fix` template
(`dataset_builder/build_mechanism_corpus.py:150`) verbatim where `oracle-merged`
phrases the same wrong answer in its own words. Training data made the error
fluent and templated; it did not create it.

**Consequences.**

- The three-way checkpoint table below must not be quoted. Its three columns
  differ in two factors each, and correcting for them reverses the ranking.
- Every future benchmark comparison fixes schema and renderer across all arms,
  and the run file records both.
- "Word-diff closed the in-place-edit fabrication class" still stands — that was
  a within-configuration comparison. "v2 is the weakest checkpoint on locus"
  does not.

---

## `sft-mechanism-v2`: 37/46, and the boundary rule it learned (2026-08-27)

> **Partly superseded — read the section above first.** The three-way checkpoint
> table here compares runs that differ in prompt shape and diff rendering as well
> as in weights. Correcting for that reverses the ranking: under v2's own
> configuration `oracle-merged` scores 35/46, below v2's 37/46. The surface-rule
> attribution below is also not supported — the same off-by-one collapse
> reproduces on `oracle-merged`, which has no clean-direction training. What
> survives: the word-diff fix to the in-place-edit fabrication class, the block-
> rewrite artifact, and the step arithmetic.

The combined retrain — word-diffs, mechanism cases, clean-direction examples,
a corpus budgeted to fit — trained cleanly and is **the weakest of the three
checkpoints on locus.** The interesting part is not the number.

    250/250 steps, 15h31m, exit 0, train_loss 0.9165, 1.684M tokens
    artifacts/sft-mechanism-v2   (adapter, 240 MB, + checkpoint-250)

**First run in this project whose corpus was fully trained.** 1995 records x 1
epoch / 8 grad-accum = 249.4 -> 250 steps, which is what the log shows. Run the
arithmetic on every future run: v1 (1748 records) took 224 steps and therefore
trained on 890.

### The three evaluation sets

    ORACLE_INFERENCE_SAMPLES=1 ORACLE_INCLUDE_SCHEMA=false .venv/bin/python \
      bench/basic_bench.py --backend ollama --model-name sft-mechanism-v2 \
      --host http://localhost:8111 --word-diff-module \
      --out data/basic_bench_mechanism_v2.jsonl
    # --root bench/mechanism_heldout --out data/heldout_mech_v2.jsonl
    # --root bench/clean_heldout     --out data/heldout_clean_v2.jsonl

| set | n | fully correct | false alarms |
|---|---|---|---|
| `bench/basic` | 46 | 37 (80%) | 5 |
| `mechanism_heldout` | 14 | 12 (86%) | 0 |
| `clean_heldout` | 27 | 27 (100%) | 0 |

Against the earlier checkpoints on the 46 — **but see the confound below, this
table is not clean**:

| | `oracle-merged` | `mechanism-v1` | `mechanism-v2` |
|---|---|---|---|
| locus correct | **41/46 (89%)** | 39/46 (85%) | 37/46 (80%) |
| buggy located | 30/33 | **33/33** | 29/33 |
| clean passed | **11/13** | 6/13 | 8/13 |
| false alarms | **2** | 7 | 5 |

### Word-diff fixed what it was aimed at

v1's precision collapse was one claim: six of its seven false alarms said a
call or print was *removed* when the diff shows it edited in place. **Zero of
v2's five make that claim.** The rendering change removed that fabrication
class outright. This is the second intervention in the project to move
anything, and the first to fully close a named failure mode.

### Word-diff bought a new artifact: block rewrites

`--word-diff` marks an in-place edit unmistakably and renders a *whole-block
rewrite* as interleaved noise. One line of Python:

    def evens(xs):
        [-out-]{+return+} [-=-]{+[x+} [-[]-]
        for x in [-xs:-]
            {+xs+} if x % 2 == [-0:-]
    [-            out.append(x)-]
    [-    return out-]{+0]+}

git's own `--word-diff=plain` mangles it the same way, so this is word-diff
itself and not `dataset_builder/worddiff.py`. **Four of v2's five remaining
false alarms are on extract/refactor cases, which are exactly block rewrites.**
The rendering artifact was moved, not eliminated.

### The finding that matters: a surface rule on comparison direction

Every one of v2's four lost buggy cases is off-by-one. That category alone
falls **9/9 -> 5/9 while every other category holds at 100%**:

| category (buggy cases) | n | v1 | v2 |
|---|---|---|---|
| logic-error | 15 | 15 | 15 |
| off-by-one | 9 | 9 | **5** |
| error-handling | 7 | 7 | 7 |
| buffer-overflow | 1 | 1 | 1 |
| api-misuse | 1 | 1 | 1 |

Three of the four render as a bare operator swap and draw the same answer,
in the `fix` template's own words (`build_mechanism_corpus.py:150`), with
`findings: []`:

    c-array-bound     for (int i = 0; i [-<-]{+<=+} 5; i++)
    go-offbyone       for i := 0; i [-<-]{+<=+} len(xs); i++
    java-array-bound  for (int i = 0; i [-<-]{+<=+} xs.length; i++)
    -> "This commit repairs the logic-error in ...: the program goes back to
        its correct behavior, and no new defects are introduced."

Now the held-out boundary cases, which it gets **right**:

    go-boundary-flip       n [-<=-]{+<+} 100   buggy -> flagged   correct
    py-boundary-flip     age [->=-]{+>+}  18   buggy -> flagged   correct
    go-boundary-flip-fix   n [-<-]{+<=+} 100   fix   -> clean     correct

**The rule the model learned is keyed to the direction of the operator swap,
not to what the loop indexes:** loosening a comparison (`<` -> `<=`) reads as a
repair, tightening it (`<=` -> `<`) reads as a defect. That is true of a range
predicate like `n <= 100` and false of a loop bound like `i <= len(xs)`, where
loosening is the classic overrun.

162 clean-direction records, every one of them `findings: []` and "removes a
defect and introduces none", made that prior strong enough to override reading
the code. Note it generalised the fix template to **loop bounds, a family that
appears nowhere in the fix corpus** — all 28 `fix` cases are ratio-trunc,
guards and aliasing.

### Therefore the held-out numbers are inflated

**Every boundary case in both held-out sets is aligned with that surface rule**
— tightening-is-buggy, loosening-is-fix. None of them tests it adversarially.
`bench/basic`'s loop bounds do, and v2 fails all three. So 12/14 and 27/27 are
not evidence that the rule is understood; on the boundary component they are
evidence that it happened to point the right way.

Separately, `clean_heldout` at 27/27 with zero findings everywhere cannot
distinguish v2 from a model that answers "clean, no findings" to everything of
that shape. It is only informative read beside `mechanism_heldout` (12/14),
which rules the degenerate model out. The two misses there are
`php-shadow-update` and `py-shadow-update` — one unseen family the mechanism
training did not reach.

**What the sets need:** boundary cases in the counter-aligned direction — a
loosening that IS a bug, a tightening that IS a fix. **Built 27 Aug**, four of
each, execution-proved: `mechanism_heldout` 14 -> 18, `clean_heldout` 27 -> 31.
The 12/14 and 27/27 above are on the OLD sets and are not comparable to any
number taken on the new ones.

### The confound: v2 was not measured under the same conditions — now settled

v2 ran short-hint (`ORACLE_INCLUDE_SCHEMA=false`) with module-rendered
word-diffs, both matching its training. `oracle-merged` and `mechanism-v1` were
measured with the JSON Schema in the prompt and unified diffs. **Some unknown
share of 89% -> 80% belongs to the configuration rather than the checkpoint**,
and the three-way table above must carry that caveat wherever it is quoted.
Separating them needed one no-training rerun. **It has been done** — see the
section above. The answer is that configuration accounts for more than the whole
gap: `oracle-merged` scores 35/46 under v2's configuration, and v2 is the better
checkpoint when both are measured the same way.

Locus is also still a floor: 37/46 is not comparable to the 31/46 that
`oracle-merged` and `mechanism-v1` both scored on locus+mechanism. That
hand-grade has not been done for v2.

---

## Two apparatus findings, 2026-08-27

**9. The benchmark scored a total outage as a result.** Run under a python
without `requests`, every one of the 46 calls raised, and each was scored as
"said nothing" — which on a clean case reads as a pass. The harness printed
**"13/46 fully correct, 0 false alarms"**: the 13 clean cases passing by
default, formatted exactly like a real score. `summarise()` now refuses to
print any score when more than 20% of calls errored
(`bench/basic_bench.py`, `MAX_ERROR_RATE`), and prints a count when any did.

**10. `--word-diff` and the training renderer are not the same renderer.**
`basic_bench.diff_of` shells out to git; `sft_mechanism_v2` was built with
`dataset_builder/worddiff.to_word_diff`, which matches git on 76% of cases.
Scoring a word-diff-trained checkpoint through git measures a train/inference
mismatch. Added `--word-diff-module`, which is what every word-diff-trained
checkpoint must be scored with; `--word-diff` still reproduces the 25 Aug
inference-swap result.

The dashboard carried three more of the same species, all fixed 27 Aug: the
benchmark panel's hallucination column had been **empty since `summarise()`
was renamed to "false alarms"**; the progress bar reported held-out runs
against `bench/basic`'s 46 cases and printed "160%, ~74/46"; and 12-case and
44-case runs were listed flush against 46-case runs with nothing marking the
denominator. The artifacts panel was hand-named and had never listed
`sft-mechanism-v1` or `-v2`; the error panel showed a 67-hour-old traceback
with no filename or age.

---

## Where the model actually stands (2026-08-26)

**26 Aug, latest:** `mechanism-v1-merged` — the first retrain aimed at
explanation correctness rather than detection — finds **all 33 buggy cases
(100% recall, a project first)** and fixes **three of the four inverted-
direction mechanism failures**, but false alarms went 2 -> 7 and locus
39/46 vs `oracle-merged`'s 41/46. Six of the seven false alarms are one
fabrication (a call "removed" that was edited in place), which is the
already-diagnosed unified-diff rendering artifact firing more often, not a new
failure. Full write-up at the end of this file: "Mechanism training: the
direction failures move, precision pays for it".

**Superseded by the full hand-grade, next section.** With all 46 cases graded
for mechanism rather than only the 10 known failures, **both checkpoints score
31/46 (67%)**. `mechanism-v1` explains five more buggy cases correctly and
loses exactly five clean ones. "The better explainer and the worse reporter" is
right as a description of its behaviour and wrong as a claim about its overall
correctness — the two are tied, and neither is near the 8/10 goal.

The 25 Aug picture, which the rest of this section describes, still stands as
the baseline everything above is measured against:

> **`oracle-merged` gets 31/46 (67%) correct on locus AND mechanism.** 41/46
> (89%) was locus only; the hand-grade found 10 more cases where the model
> named the right construct but the stated causal claim is wrong or inverted,
> on top of the 5 it already missed outright.

Read that with these qualifications:

1. **89% was never an explanation-correctness number, and now we know the gap.**
   The scorer checks whether the answer names the faulty construct, not whether
   the mechanism it describes is true. The hand-grade (below) is the instrument
   that settles it, and it moves the real figure from "below 89%, unknown by how
   much" to **67%, below the project's 8/10 goal.**
2. **The mechanism failures are disproportionately *inverted direction*, not
   noise.** `c-int-division`, `go-accum-reset`, `rb-string-mutate`,
   `rs-int-division` all get the right line and describe the wrong direction of
   the effect (truncation happens at a different step than claimed, a reset
   moved the opposite way, a mutation is gained not lost, division direction is
   backwards). This looks like the model pattern-matching to a familiar bug
   trope near the right line rather than tracing the actual runtime semantics.
3. **False alarms are 2, and the target is 0.** Both are behaviour-preserving
   refactors, and the cause is now known: a unified diff renders an edited line
   as remove+add, so the model describing a "removed" docstring is reading its
   input correctly. A rendering artifact, not a reasoning failure.
4. **`oracle-merged` is the older checkpoint and the best one.** The 25 Aug
   retrain (`sft-ml8-grounded`) scored worse. Training is not the lever here.

Five approaches were measured and lost on 25 Aug: retraining on the same corpus,
prompt rules for summary factuality, context injection, word-diff rendering at
inference, and (earlier) DPO. The one live idea with a mechanism behind it is
retraining on word-diffs — see the last section.

---

## The full 46-case hand-grade of `mechanism-v1`: 31/46, a dead heat (2026-08-26)

Outstanding since the retrain landed — only the 10 known failures had been
re-read, so 39/46 was a locus floor and the comparable "67%" could not be
restated. Now graded in full, every mechanism verdict settled by executing pre
and post. Grades are data, not prose: `data/handgrade_mechanism_v1.csv`.

| | `oracle-merged` | `mechanism-v1` |
|---|---|---|
| buggy cases located | 30/33 | **33/33** |
| of those, mechanism correct | 20 | **25** |
| clean cases passed | **11/13** | 6/13 |
| **locus + mechanism correct** | **31/46 (67%)** | **31/46 (67%)** |

**The two checkpoints are exactly tied, by different routes.** The mechanism
retrain bought +5 correct explanations on buggy cases and paid exactly −5 on
clean ones. Not approximately — 20→25 and 11→6.

That is a sharper statement than the 26 Aug write-up's "the first real
movement", and it does not retract it: the movement is real and it is on
precisely what the training targeted. It is the *net* that is a wash, and the
26 Aug session could not see that because it re-read only the 10 known
failures.

**Case-level, which is where the interesting part is:**

    fixed by the retrain      go-accum-reset, py-dict-mutate, py-pop-guard,
                              rb-string-mutate, rs-int-division          (5)
    locus misses recovered    go-nil-map, java-concurrent-modify         (2)
    still wrong on both       c-int-division, c-strcpy-bound,
                              php-concat-operator, rs-overflow,
                              ts-reduce-empty                            (5)
    NEW mechanism failures    go-offbyone, java-string-equals            (2 regressions)
                              js-reverse-index (was a locus miss)        (1)

**`java-string-equals` is a new inverted-direction failure, and it is exactly
the species the retrain was built to remove.** The model claims `==` makes
`same()` return **true** for two equal-content strings; the program prints
**false**. So the retrain did not eliminate inverted direction as a class — it
fixed the four instances it was trained on and produced a fresh one elsewhere.
That is what the family-selection limitation predicts, and it is the strongest
in-house evidence for it.

**Two failure sub-species worth separating, both new here:**

1. **The summary contradicts its own finding.** `java-array-bound` says
   NullPointerException in the summary and ArrayIndexOutOfBoundsException in the
   finding; `php-divzero-guard` says non-empty arrays throw in the summary and
   names the empty array correctly in the finding; `ts-reduce-empty` gets
   TypeError right in the summary and wrong (RangeError) in the finding. A
   grader reading only one field would score these differently — which is a
   scorer-design problem, not just a model problem.
2. **The mechanism is right and the illustration is fabricated.**
   `rb-int-division` claims `mean([1,2])` returns 0 (verified: 1);
   `rb-range-bound` claims zero for n>1 (verified: 10); `py-range-bound` claims
   "one less than the intended sum" (verified: 15 → 10, short by 5);
   `rs-int-division` claims 2.5 becomes 2 (verified: 1.50 → 1.00). These are
   graded **locus** here, because the causal claim is true and only the worked
   example is invented — but four of 25 "correct" explanations carry a false
   number, and a stricter rater would grade them down. **This is the single
   most likely source of inter-rater disagreement** and the packet in
   `bench/rater_packet.py` exists partly to measure it.

**Reproduce:**

    python bench/basic_bench.py --score data/basic_bench_mechanism_v1.jsonl

## The mechanism training families were chosen by looking at test failures

**This is the limitation most likely to sink the explanation result, and it is
the same species of error this document spends its length documenting in other
people's work and in this project's own gate.** It is recorded here in full
rather than left for a reviewer to find.

`bench/mechanism_pilot` was, per the 25 Aug handoff, "built directly from the
hand-grade's 10 mechanism failures ... one case per failure family". Checked
mechanically, the correspondence is total:

| hand-grade failure | training family present |
|---|---|
| `c-int-division`, `rs-int-division` | `*-ratio-trunc` (c, go, java, php) |
| `go-accum-reset` | `*-reset` (java, js, py, rb) |
| `rb-string-mutate`, `py-dict-mutate` | `*-alias-mutate` (js, php, py, rb) |
| `py-pop-guard`, `ts-reduce-empty` | `*-empty-guard` (go, js, py, rb) |
| `c-strcpy-bound`, `rs-overflow` | `*-overflow` (c, rs) |
| `php-concat-operator` | `*-coerce` (js, php, py, rb) |

**10 of 10. There is no held-out family.** The programs differ — different
languages, different code — so this is not literal test-set training. But the
*selection* of what to teach was driven by which test cases failed, which is
tuning on the test set by another name.

**What this does and does not license.** `mechanism-v1` fixing 5 of the 10 is a
sound **existence proof**: a 3B can be taught mechanism, where four prompt-rule
attempts moved nothing. That claim survives. The **rate does not** — "5 of 10"
cannot be quoted as generalisation, and any table putting it next to a baseline
is misleading.

**Two repairs, both now in place.**

1. **Held-out families.** `bench/mechanism_heldout` (14 cases) and
   `bench/clean_heldout` (27 cases, 14 fix + 13 refactor) cover six mechanisms
   the mechanism training never saw — operator precedence, boundary-comparison
   direction, fallback/default order, unit scale, shadowed-variable update,
   rounding direction, and swallowed errors. All 41 are proved by execution and
   appear in no training corpus.

       python bench/basic_bench.py --root bench/mechanism_heldout --verify
       python bench/basic_bench.py --root bench/clean_heldout --verify

2. **The real commits.** `data/real_commits.jsonl` is 40 commits sampled at
   random from the five held-out projects. No family selection, no relationship
   to the training data at all. **This is the cleanest evidence available for
   the central claim** and is why it outranks "more n" as a reason to run it.

**A guard, because the directories sit next to each other.**
`bench/mechanism_pilot` and `bench/clean_direction` are training data, and
`--root` puts them one flag away from a headline number. `basic_bench.py` now
refuses to score them quietly — it prints a block warning that a score there
measures memorisation. The apparatus findings in this document are mostly cases
where nothing warned; this one warns.

## Half of every SFT corpus never trained anything (2026-08-26)

`MAX_SEQ_LENGTH` is 1024 and TRL truncates `keep_start`, so a record whose
*prompt* alone reaches 1024 tokens loses its entire assistant turn. TRL then
drops it — the training log says so in as many words, "Dropping fully masked
examples from train dataset" — and the run continues without it.

Measured on `data/sft_mechanism_v1.jsonl` with the run's own tokenizer:

| | records | prompt >= 1024 | effective |
|---|---|---|---|
| `sft_mechanism_v1` | 1748 | **858 (49.1%)** | 890 |
| `sft_ml8_grounded` | 1286 | — | 616 |

The step counts confirm it independently, and they were in the logs all along:
224 steps x 8 grad-accum / 2 epochs = **896 records, not 1748**; for
`sft-ml8-grounded`, 154 steps => **616 of 1286**. Reproduce with:

    ssh oracle-gpu 'cd ~/oracle && .venv/bin/python -c "..."'   # tokenizer probe
    grep -oE "[0-9]+/[0-9]+" sft_mechanism_v1.log | tail -1     # step count

Three consequences:

1. **The mechanism dose was never 4.6%.** All 81 pilot records fit (max 1055
   tokens) while half the bulk corpus did not, so the real share of what
   trained was **9%** — double the figure recorded on 26 Aug.
2. **It is not a label-balance artifact.** Truncation drops slightly more buggy
   records than clean ones, 34.6% buggy nominal against 30.1% effective. That
   is far too small to explain recall 33/33 with precision 6/13, so the
   one-directional mechanism corpus remains the explanation for that.
3. **`config.py`'s own comment is stale and says so twice.** "prompts run 414
   tokens median, 476 at p90, 795 max" was measured on the DPO set; the line
   below it already corrects this to "~800 tokens median". The real corpus is
   1121 tokens median, 1916 at p90, 3996 max.

`dataset_builder/build_mechanism_corpus.py` measures every record against the
real tokenizer and shrinks the diff until the answer survives. On the rebuilt
corpus, **0 of 1995 records are dropped** — 250 steps at 1 epoch, which is the
arithmetic working out.

## Prompt shape has never matched between training and inference (2026-08-26)

`basic_bench.py` never sets `include_schema`, and `client.py:170` resolves it to
**True** for the `ollama` backend — so every benchmark number was taken with the
full JSON Schema in the prompt. `sft_base`, `sft_multilang8` and
`sft_ml8_grounded` are **100% short-hint**. `config.py:160` already says "Set
`ORACLE_INCLUDE_SCHEMA=false` when serving a checkpoint from serve.py", and no
run has.

The 81 mechanism-pilot records are the *only* training data ever built with the
schema (82 of 1748 in `sft_mechanism_v1`), which is a confound in the 26 Aug
mechanism result: those records matched the inference shape and the other 95%
did not. Re-baselining both checkpoints under `ORACLE_INCLUDE_SCHEMA=false` is
cheap and has not been done.

## Stage 1 against DeepJIT / CC2Vec / JITLine (2026-08-26)

The comparison the project has claimed since the README and never run. QT and
OPENSTACK on the **authors' splits, unchanged** — 23133/2571 and 11973/1331,
matched 100% on commit hash against the JITLine metrics tables.

    python -m corpus.deepjit --eval

| project | n test | buggy | AUC | PR-AUC | F1 @0.5 | always-buggy F1 |
|---|---|---|---|---|---|---|
| qt | 2571 | 7.1% | **0.8049** | 0.2797 | 0.333 | 0.133 |
| openstack | 1331 | 12.2% | **0.8373** | 0.3814 | 0.442 | 0.218 |

Against JITLine's own published numbers, read out of the stored cell outputs of
`JITLine_RQ1-RQ3.ipynb` in its replication package (Zenodo 4596503, cells 11
and 12) rather than transcribed from the paper:

| project | ORACLE gate AUC | JITLine AUC | ORACLE F1 | JITLine F1 |
|---|---|---|---|---|
| qt | 0.805 | 0.82 | 0.333 | 0.24 |
| openstack | 0.837 | 0.83 | 0.442 | 0.33 |

**The gate lands inside the published range**, on metrics alone — JITLine adds
code-token features and SMOTE on the same commits.

**But run the count control before believing that means much.** `la` — lines
added, one feature — scores:

| project | la only | la+ld | la+ld+nf | full gate (22 metrics) | JITLine |
|---|---|---|---|---|---|
| qt | 0.741 | 0.735 | 0.744 | 0.805 | 0.82 |
| openstack | **0.797** | 0.809 | 0.807 | 0.837 | 0.83 |

On OPENSTACK a **single-feature line counter is 0.033 AUC from JITLine's
published number**, and the full 22-metric gate beats that counter by 0.040.
This is a fact about the benchmark rather than about any model on it: QT and
OPENSTACK have little headroom above commit size, and DeepJIT, CC2Vec, JITLine
and this gate are all competing inside it.

It is the `count_control.py` discipline applied to somebody else's benchmark,
and it is an apparatus finding in its own right — the eighth. It also settles
what the head-to-head licenses: **"the gate is a credible Stage 1" is
supported; "we closed the gap with DeepJIT" is not, because the gap on this
benchmark is mostly churn.** The control now runs automatically inside
`corpus/deepjit.py --eval`, so the AUC cannot be quoted without it. Caveats that must travel with
this table: F1 is at 0.5 against JITLine's own operating point, so AUC is the
honest comparison; and the gate's *own* operating point (95% recall) gives
F1 0.177 on qt and 0.354 on openstack, because buying recall at a 7% base rate
costs precision. That is the right trade for a cascade and a bad leaderboard
number.

**DeepJIT and CC2Vec are not in the table, deliberately.** JITLine's numbers
above come from its replication package, so they are sourced. The other two
would have to be transcribed from their papers and are not quoted here. What
*is* sourced, from the JITLine abstract (arXiv 2103.07068v2), is the relation:
JITLine reports being "at least 26%-38% more accurate (F-measure)" than CC2Vec
and DeepJIT, so both sit below the JITLine column.

**And the reason CC2Vec's published number was high is a leak.** The same
abstract records that CC2Vec trained on the test set, and that excluding it
drops CC2Vec's F-measure by **38.5% on OpenStack and 45.7% on Qt**. That is the
same failure this project found in its own gate — trained on its own evaluation
set, worth 0.495 F1 and 0.21 AUC — occurring in a published, peer-reviewed JIT
defect prediction model, and caught only because someone ran a replication.
It is external corroboration for the methods framing: the apparatus findings
here are not a local accident, they are the field's normal failure mode.

**What this data cannot do.** The code channel in the released DeepJIT pickles
is the placeholder string `"added _ code removed _ code"` in every entry of all
four splits — checked exhaustively, not sampled. So Stage 2 cannot be run on
QT/OPENSTACK without re-mining both repositories by commit hash. This is a
Stage 1 comparison and must be labelled as one.

## 0. Trivial baselines

No detection number in this project means anything without the matching trivial
baseline beside it. Two are in play.

| baseline | where it applies | value |
|---|---|---|
| always-buggy | F1 at a 50/50 base rate | **F1 0.665** |
| always-clean | accuracy at a 50/50 base rate | **acc 0.500** |
| counting (10 features on `+`/`-` lines) | any diff-direction task | see §4 |

Separation (TPR − FPR) is the measure that survives all three: it is zero for
any constant answer and independent of base rate.

```
python count_control.py data/cve_gate.jsonl 0.6667      # paired corpus
python count_control.py data/apachejit_commits.jsonl 0.8 # ApacheJIT
```

---

## 1. ApacheJIT detection — `data/detect_eval.jsonl`

1000 commits, balanced 500/500, SZZ labels only, no teacher involved. Sampled
from the 6030 commits the teacher never touched.

```
python evaluate.py --paired data/detect_sft220.jsonl data/detect_stock.jsonl
```

| metric | checkpoint-220 | stock 3B | trivial |
|---|---|---|---|
| valid JSON | 99.8% | 99.9% | — |
| precision | 0.59 | 0.55 | 0.50 |
| recall | 0.71 | 0.63 | 1.00 |
| F1 | 0.64 | 0.59 | **0.665** |
| accuracy | 0.61 | 0.56 | 0.500 |
| **separation (TPR−FPR)** | **+21.0pp** | +11.6pp | 0.0pp |
| grounded | 99.8% | 98.4% | — |
| category match vs teacher | 27.1% | 26.9% | — |
| median latency | 21.7s | 19.8s | — |
| confusion | tp=355 fp=251 fn=143 tn=249 | tp=314 fp=256 fn=185 tn=244 | — |

**Paired bootstrap, n=997, 10000 resamples:**

```
separation diff   +9.5pp   95% CI [+2.0, +17.0]   p=0.007
McNemar           220-only-correct 209, stock-only-correct 162, p=0.017
```

Acceptance criterion 3 (beats the base model significantly) **passes**.
Criterion 2 fails on F1 (0.64 < 0.665), passes on accuracy (0.61 > 0.500).

Both checkpoints were trained on the leaked corpus, so this is the pre-fix
baseline, not a publishable result.

---

## 2. CVEfixes paired detection — `data/cvefixes_eval.jsonl`

500 fix commits, each emitted forward (clean) and reversed (buggy). Human-written
CVE descriptions, no teacher. **See §4 — this corpus cannot carry a detection
claim.**

```
python evaluate.py --paired data/cve_sft220.jsonl data/cve_stock.jsonl
python evaluate.py --paired data/cve_trained.jsonl data/cve_stock.jsonl
```

| metric | checkpoint-220 | stock 3B | sft-cve (CVE-trained) |
|---|---|---|---|
| valid JSON | 98.6% | 99.6% | 100% |
| precision / recall | 0.49 / 0.70 | 0.49 / 0.76 | — / 0.00 |
| F1 | 0.57 | 0.60 | 0.00 |
| accuracy | 0.48 | 0.49 | 0.500 |
| **separation** | **−4.2pp** | **−1.8pp** | **0.0pp** |
| positive rate | 0.72 | 0.77 | 0.00 |
| grounded | 99.1% | 80.7% | — |
| category match vs CVE | 12.9% | 32.1% | — |
| median latency | 19.9s | 17.5s | 9.9s |
| confusion | tp=345 fp=363 fn=150 tn=128 | tp=378 fp=387 fn=120 tn=111 | tp=0 fp=0 fn=500 tn=500 |

**Paired bootstrap (resampled on `pair`):**

```
220 vs stock        −2.6pp   95% CI [−9.1, +4.0]   p=0.78   n=982, 497 blocks
sft-cve vs stock    +1.8pp   95% CI [−2.3, +5.8]   p=0.20   n=996, 499 blocks
```

The `sft-cve` figure is an artifact: stock's separation is negative, so scoring
exactly zero beats it arithmetically.

### 2.1 Within-pair behaviour

The same commit, forward and reversed. This is the measurement the paired
construction exists for.

| | checkpoint-220 | stock 3B |
|---|---|---|
| complete pairs | 488 | 497 |
| flags both directions | 269 (55%) | 328 (66%) |
| flags neither | 57 (12%) | 61 (12%) |
| correct (flags intro, clears fix) | 70 | 50 |
| backwards | 92 | 58 |
| forced-choice accuracy | 0.432 (sign test p=0.099) | 0.463 (p=0.501) |

Neither model reads direction. Both fire on "this diff looks risky."

### 2.2 Per-language separation (checkpoint-220)

| language | n | TPR | FPR | separation |
|---|---|---|---|---|
| PHP | 124 | 0.76 | 0.76 | +0.0pp |
| C | 109 | 0.72 | 0.76 | −3.7pp |
| C++ | 62 | 0.68 | 0.66 | +1.6pp |
| JavaScript | 42 | 0.67 | 0.74 | −7.1pp |
| Python | 30 | 0.60 | 0.66 | −5.5pp |
| Ruby | 29 | 0.69 | 0.71 | −2.5pp |
| Java | 19 | 0.84 | 0.74 | +10.5pp |
| TypeScript | 18 | 0.67 | 0.83 | −16.7pp |

Java's +10.5pp is n=19. Noise.

### 2.3 The `sft-cve` collapse

Trained on 1000 CVEfixes pairs, the model emits **one distinct output** across
all 1000 records:

```
1000×  "This change removes a vulnerable code path. No defect is introduced."
```

Cause: half the SFT targets were that identical string, and `assistant_only_loss`
puts the whole loss on the target text, so memorising it drove loss near zero on
50% of examples. Training loss 0.925 and token accuracy 0.862 looked healthy for
exactly that reason.

**Check before any future training run:** count distinct assistant turns in the
SFT file. Ten hours of GPU went into a null result that was visible in the data.

### 2.4 Explanation quality against the human CVE text

Acceptance criterion 4, measured on human ground truth — the CVE description
beside each finding. Word overlap is content-word F1 between the finding's
explanation and the CVE summary; identifier Jaccard is the shared-mechanism
measure (both name the same function/symbol or not). Inference already paid.

```
python cve_quality.py data/cve_sft220.jsonl data/cve_stock.jsonl
```

| measure | checkpoint-220 | stock 3B |
|---|---|---|
| word overlap F1 | 0.033 (median 0.000) | 0.028 (median 0.000) |
| nonzero word overlap | 37.1% | 23.6% |
| identifier Jaccard | 0.009 (5.4% nonzero) | 0.004 (2.2% nonzero) |

**Paired bootstrap (567 commits, 10000 resamples):**

```
word overlap      +0.005   95% CI [+0.000, +0.009]   p=0.017
identifier Jacc   +0.004   95% CI [+0.001, +0.008]   p=0.011
```

Fine-tuning moves the model toward the human text, and the CI just excludes
zero — but the absolute levels are the result: explanations share almost no
vocabulary with the CVE. Read alongside §2's category match (12.9% vs 32.1%):
the models describe the same defect at the diff level (names the changed
symbols, e.g. `blk_mq_tag_to_rq`, `calendar displayname`) while the human text
states the mechanism (use-after-free, XSS). The gap is a level mismatch, and
the paper should say so — it is the honest ceiling of the "reviewable
findings" claim, not a fixable token problem.

---

## 3. Stage 1 — the gate

GraphCodeBERT embeddings (768) + 14 Kamei process metrics → LightGBM.
Threshold tuned to 95% recall; "saved" is the share of commits that never reach
the LLM.

```
python -m ml_model.train_gate --jsonl data/apachejit_commits.jsonl --ablate
```

**ApacheJIT, 7989 commits, 27.5% buggy, chronological 80/20, test n=1598:**

| variant | AUC | PR-AUC | threshold | recall | LLM calls | saved |
|---|---|---|---|---|---|---|
| counting baseline | 0.638 | 0.363 | — | — | — | — |
| metrics only (2013 baseline) | 0.777 | 0.660 | 0.093 | 95.1% | 79.6% | 20.4% |
| embeddings only | 0.761 | 0.498 | 0.067 | 95.1% | 72.9% | 27.1% |
| **embeddings + metrics** | **0.822** | **0.699** | 0.037 | 95.1% | 71.8% | 28.2% |
| fine-tuned encoder + metrics | 0.828 | 0.709 | 0.017 | 95.0% | 70.4% | 29.6% |
| frozen emb+metrics, head re-swept | 0.829 | 0.702 | — | 95% | 69.9% | 30.1% |

Reading the code adds **+0.045 AUC / +0.039 PR-AUC** over process metrics alone,
and the stack clears the counting baseline by **+0.184**. AUC 0.822 is inside the
range DeepJIT and CC2Vec report on QT/OPENSTACK.

**Fine-tuning the encoder (4 epochs, 6391 train commits, 512 tokens, ~14h on
the 1660 SUPER) buys +0.006 AUC — inside noise.** Epoch 3 is the best checkpoint
(0.8283 / 0.7088); a head re-sweep on frozen embeddings scores the same
(0.8293 / 0.702, `python -m ml_model.sweep_gate`). The frozen gate stays Stage
1; the encoder run settles the question the paper needed asked. Full table:

```
epoch 1  loss=0.833  AUC=0.8162  PR-AUC=0.6874  saved=26.6%
epoch 2  loss=0.742  AUC=0.8179  PR-AUC=0.6977  saved=26.8%
epoch 3  loss=0.664  AUC=0.8283  PR-AUC=0.7088  saved=29.6%
epoch 4  loss=0.547  AUC=0.8266  PR-AUC=0.7065  saved=30.4%
```

The head sweep also tested unixcoder-base (0.824) and codebert-base (0.822)
against graphcodebert (0.829) — graphcodebert stays the encoder.

**CVEfixes paired, 3000 records, 50% buggy, repo-disjoint split, test n=1000:**

| variant | AUC | PR-AUC | recall | saved |
|---|---|---|---|---|
| counting baseline | **0.934** | 0.935 | — | — |
| gate (embeddings only — corpus has no process metrics) | 0.792 | 0.792 | 95.0% | 19.2% |

The gate scores *below* the counting baseline here, so it is recovering a noisy
version of `wc`. See §4.

An earlier run reported 0.832 on a stale 1164-commit copy of the corpus; the
7989 figure above supersedes it.

---

## 4. The paired-corpus confound

Equal total length is not equal composition. A fix adds a guard, so it carries
more `+` lines than `-` lines; its reverse carries the mirror image.

```
mean(plus-minus lines):   reversed −9.71    fix +9.72
```

| features | AUC | PR-AUC |
|---|---|---|
| counting only (all 10) | **0.934** | 0.935 |
| plus-minus lines alone | 0.908 | 0.879 |
| plus-minus chars alone | 0.925 | 0.910 |

For contrast, the same control on ApacheJIT, where the labels are real SZZ and
nothing is reversed:

| features | AUC | PR-AUC |
|---|---|---|
| counting only (all 10) | 0.638 | 0.363 |
| plus-minus lines alone | 0.634 | 0.344 |
| plus-minus chars alone | 0.629 | 0.339 |

`wc` solves the paired corpus and does not solve ApacheJIT. Consequences:

- **`cvefixes_eval.jsonl` cannot carry a detection claim.** It remains valid as
  an explanation benchmark with human ground truth.
- The gate's 0.792 there is an artifact.
- Both LLMs sat at chance on a task a line-counter solves at 0.934 — they did not
  even find the cue. This sharpens the negative result about the LLMs and weakens
  any claim that the task measures defect understanding.

The construction closed a smaller leak (git prints `-` before `+`; a naive sign
flip inverts that, and both directions are re-sorted) while missing this one.

---

## 5. Teacher ceiling — why ApacheJIT distillation was abandoned

Same 200 held-out commits, hinted versus unhinted.

| teacher | P | R | F1 | acc | fn |
|---|---|---|---|---|---|
| hinted, deepseek-v4-flash | 0.77 | **1.00** | 0.87 | 0.86 | **0** |
| unhinted, gpt-oss-120b (120B) | 0.56 | 0.43 | **0.49** | 0.58 | 52 |
| always-buggy | 0.46 | 1.00 | 0.63 | 0.46 | 0 |

A 120B model reading diffs unaided scores below the majority-class baseline.
SZZ-buggy is largely not inferable from the diff alone.

---

## 6. Training runs

| run | data | examples | steps | epochs | wall | loss | token acc |
|---|---|---|---|---|---|---|---|
| `sft-adapter/checkpoint-110`, `-220` | ApacheJIT (leaked corpus) | 1759 | 220 | 2 | 13h46m | — | — |
| `sft-cve/checkpoint-172` | CVEfixes pairs | 2000 → 1376 used | 172 | 1 | 9h49m | 0.925 | 0.862 |

`sft-cve` lost ~600 examples to `MAX_SEQ_LENGTH=1024`: prompts over the limit
lose their assistant turn entirely and TRL drops them as fully masked. Pairs are
within 2 characters of each other, so the drops are symmetric and balance holds.

Hyperparameters were held identical between the two runs so that the difference
is attributable to the data.

---

## 7. Corpora

| file | rows | status |
|---|---|---|
| `apachejit_commits.jsonl` | 7989 | ✅ sound |
| `detect_eval.jsonl` | 1000 (500/500) | ✅ sound, SZZ only |
| `heldout_unhinted.jsonl` | 200 | ✅ sound |
| `cvefixes_eval.jsonl` | 1000 (500 pairs) | ⚠️ explanation only, see §4 |
| `cvefixes_train.jsonl` | 2000 (1000 pairs) | ⚠️ same, repo/CVE-disjoint from eval |
| `cvefixes_all.jsonl` | 13850 (6925 pairs) | full scan, 3074 repositories |
| `cve_gate.jsonl` | 3000 | train+eval concatenated, positional split at 0.6667 |
| `labelled.jsonl` and everything derived | 1959 | ⚠️ label leakage, not reportable |
| `mined.jsonl` | 0 | empty |

`CVEfixes.db` — 52 GB, 11873 CVEs, 12923 fixes, 12107 commits, 51342 file
changes. Full corpus language spread: PHP 3392, C 3162, JavaScript 1108,
Python 1098, C++ 1032, Ruby 662, TypeScript 616, Go 588.

---

## 8. What the numbers support

| claim | evidence | verdict |
|---|---|---|
| the gate detects | AUC 0.822 vs counting 0.638, ApacheJIT n=1598 | ✅ holds |
| reading code beats counting lines | +0.045 AUC over metrics-only, with control | ✅ holds |
| fine-tuning improves format | grounded 99.1% vs 80.7%, both corpora | ✅ holds |
| fine-tuning improves detection | +9.5pp on ApacheJIT, p=0.007 | ⚠️ in-distribution only |
| the LLM detects out of distribution | separation −4.2pp on CVEfixes | ❌ fails |
| the LLM beats the trivial baseline | F1 0.64 vs 0.665 | ❌ fails |
| distillation preserves the taxonomy | `security` 12.9% vs stock's 32.1% | ❌ fails |
| CVEfixes is a clean detection benchmark | counting scores 0.934 | ❌ fails |

---

## 9. Next

Ordered by cost. Everything in the first group is free and answers an
acceptance criterion.

### No GPU, do first

1. **Explanation quality against the human text.** Never actually measured.
   `cve_sft220.jsonl` and `cve_stock.jsonl` already hold 754 and 851 findings
   beside the CVE descriptions that are the ground truth. This is the core of
   acceptance criterion 4 and the strongest evidence available for the reviewable
   findings claim, and it costs nothing — the inference is already done.
2. **Gate/LLM disagreement rate.** Two independent verdicts on the same commits;
   no prior JIT work has had a second one to compare. Score the gate over
   `detect_eval.jsonl` and cross-tabulate with `detect_sft220.jsonl`.
3. **Commit the repository.** 33 untracked source files against a single
   `initial commit`. `corpus/cvefixes.py`, `count_control.py`,
   `evaluate.py --paired`, three docs.

### Cheap, decides the paper's shape

4. **Repair the paired construction, or retire the detection claim.** Two
   options: match pairs on `+`/`-` balance (correct, costs most of the corpus —
   6925 pairs is enough to absorb it), or recover real vulnerability-introducing
   commits by running SZZ over each fix, which needs full clones. Re-run
   `count_control.py` on whatever comes out; if it is not near 0.5, it is not
   fixed.
5. **Rebuild the CVE training set with a non-degenerate clean target.** The clean
   half needs a target that cannot be produced without reading the diff. Either
   drop it from training and sample negatives elsewhere, or derive it from the
   diff. Verify with a distinct-assistant-turn count before spending GPU.

### GPU, only after 4 and 5

6. **Retrain on the repaired corpus.** ~10h. This is the experiment that decides
   whether a small model can learn direction when trained on it directly.
7. **Phase 2 comparability** — `corpus/deepjit.py` for QT (C++) and OPENSTACK
   (Python), authors' splits unchanged. Enables a table against published
   DeepJIT / CC2Vec / JITLine numbers.

### Reconsidered

8. **The unhinted ApacheJIT relabel** (~34 GPU hours) stays deferred. A 120B
   teacher scores F1 0.49 there, below the 0.63 baseline — the signal is not in
   the diff, and distilling it would spend the budget to reproduce noise.

### Prompt rules cannot move the SFT'd 3B (17 Aug)

Divide-by-zero in new Go code (`calculator.go`): summary says "risky, no zero
check", findings stay empty. Tried, in order, on the served checkpoint-220:

- `INFERENCE_SAMPLES=3` consensus: no change (majority of structured heads
  says "no finding"; consensus amplifies the bias, does not fix it).
- `SYSTEM_PROMPT` rule "missing validation in new code IS a finding", then
  promoted to rule 3 with an inline divide example: no change, single-sample
  or consensus.

Cause: SFT targets (Java bug-fix commits) contain findings only for changed-
line wrongness (flips, null derefs); "absent guard in new code" is outside the
target distribution, and prompt text cannot override the imprint at 3B.

Fix is data, not prompt: mined Go/JS commits whose fixes ADD guards (e.g.
dovecot `return -1` on error) put missing-validation into the SFT target
distribution. Until then, measure the gap: summaries flagging risk with empty
findings = unreported-risk rate, report it as a known limitation.

### Labelling throughput was a retry bug, not a token budget (18 Aug)

Pass 1 over `data/multilang_commits.jsonl` had been averaging ~5 minutes per
commit — 14 records in 75 minutes on 18 Aug, against a per-minute budget that
allows roughly four. The worker thread spent that time in `time.sleep`, not in
the network, so the ceiling was self-inflicted.

Measured cause, in three steps:

1. One labelling call costs `1863` total tokens (1226 prompt, 637 completion,
   of which 502 are reasoning) and returns in ~1.8s. Reproduce by posting
   `SYSTEM_PROMPT` + `build_user_message(...)` for one record and reading
   `usage` off the response.
2. Groq's free tier caps **tokens per day**, not only per minute:
   `Rate limit reached ... on tokens per day (TPD): Limit 200000, Used 199955`.
   The three keys sit in three *different* organisations, so the daily budget
   is 3 × 200,000 = **600,000 tokens/day ≈ 320 commits/day**, and the 8000 TPM
   limit is never the binding constraint over a long run.
3. An exhausted key answers with `retry-after` in the hundreds of seconds (716s
   and 960s observed). `ask()` rotated keys by `attempt % len(keys)`, so every
   commit began on the same spent key, slept out its full daily penalty, and
   only then tried a live one. That sleep *is* the five minutes.

Fixed in `corpus/label.py`: a 429 whose penalty exceeds 60s parks that key in
`_BLOCKED` and the call retries immediately on the next live key; only when
every key is parked does it wait, and then only until the earliest unblocks.
Short (per-minute) 429s still sleep their `retry-after`. Alongside it,
`_pace()` reads `x-ratelimit-remaining-tokens` off each response and sleeps
exactly the shortfall before the next call, so the per-minute bucket is spent
smoothly instead of by collision.

Two smaller defects fell out of the same read: `--sleep` was declared and never
applied (the `--sleep 18` in `label_watch.sh` did nothing, and is now dropped),
and `Provider.keys` returned `""` for unset key variables, which would send an
empty bearer token as though it were a fallback.

Measured after the fix by counting records written to
`data/labelled_multilang.jsonl` over a 300-second window (492 -> 507):
**3.0 commits/min**, against **0.19/min** before (14 records in 75 minutes) —
a **16x** speedup, with no change to the teacher, the prompt, or `--samples`.
`--samples` was already 1: it is the argparse default and the launch command
never overrode it, so the "3x faster with `--samples 1`" note in the old handoff
was offering a speedup that did not exist.

That burst rate holds only while daily budget remains. The daily cap is the real
limit and it does not go away: at ~1,863 tokens a commit against 600,000
tokens/day the sustained ceiling is ~320 commits/day, so the remaining ~1,250
commits of passes 1 and 2 need roughly **four days** of free-tier budget. The
levers, in order, are more Groq organisations, a paid tier, or
`reasoning_effort: "low"` on the teacher call — 502 of the 637 completion tokens
are reasoning tokens.

### Targeted mining for guard-adding fixes (18 Aug)

The general mined corpus does not carry the defect class the paper needs. Across
the 512 labelled records available on 18 Aug, the teacher produced 141 findings,
of which 14 were `input-validation`, 10 `null-dereference`, and only 7 used
guard or validation language at all — about 5%. Extrapolated to the full 1,734
that is ~85 examples, which is not enough to move the behaviour that "Prompt
rules cannot move the SFT'd 3B" identified as a data problem.

`corpus/mine.py --guards` mines that class directly. A fix whose diff *adds* a
check is the mirror image of the gap: the defect is the line that was not there,
so the commit it blames back to is exactly the missing training example.

**The SZZ step had to change.** `blame_origins()` blames the lines a fix
*deleted*, which is the correct rule and useless here — a commit that only
inserts a guard deletes nothing, so it returns the empty set for precisely the
commits this mode looks for. `blame_insertion_context()` blames a ±3-line window
around each insertion point in the fix's parent instead, on the reasoning that
the line which should have been guarded is the one the guard was inserted next
to. Replaced lines still go through the original deletion-blame path.

**What counts as a guard.** An added line only qualifies if it opens a
conditional or bails out early (`COND_RE`, `EXIT_RE`), which stops `len(` from
matching every second line of ordinary code, and comments and test paths are
excluded outright. Qualifying lines are then classified into `zero-check`,
`nil-check`, `error-check`, `bounds-check`, `empty-check`, `falsy-check` and
`validation-raise`. Ruby and Rust needed the postfix form (`return if x.nil?`)
or the whole Ruby slice mined empty — the self-check in `mine.py` carries one
real hunk per language for exactly this reason.

Yield over 21 repositories, 151,476 commits of history scanned:

| | |
|---|---|
| fix commits found | 21,239 |
| of those, adding a guard | 1,839 (8.7%) |
| introducing commits mined | **1,458** |

By language — all eight, which the general corpus reached only for the four
largest: go 324, java 280, javascript 230, php 228, rust 175, python 79,
typescript 77, ruby 65.

By guard class: `nil-check` 727, `falsy-check` 536, `empty-check` 285,
`error-check` 186, **`zero-check` 146**, `bounds-check` 47,
`validation-raise` 38. The 146 zero-checks are the divide-by-zero class that
`calculator.go` exposed — against 7 guard-flavoured findings in the entire
general corpus, a 20x increase in the training signal for the exact behaviour
the prompt could not buy.

Two defects surfaced while running it. `git()` decoded subprocess output as
strict UTF-8, so one latin-1 source file raised `UnicodeDecodeError` out of the
helper and cost an entire repository's slice — `apache/commons-lang` and
`gohugoio/hugo` both died that way, the latter throwing away 207 already-detected
guard fixes (recovered: +162 records after the fix). And repository yield tracks
repository size, not the goal: the first pass returned 228 php and 15 rust.

**Composition is capped at labelling time, not mining time**, because mining is
free and labelling costs days: `label.py --per-language N`. At `--per-language
60` the guard corpus samples to ~480 balanced commits, roughly 1.5 days of
free-tier budget, against ~3 days for the uncapped 969.

Reproduce:

    python -m corpus.mine --guards --repos <slugs> \
      --langs "go typescript javascript java php rust python ruby"
    python -m corpus.label --in data/guard_commits.jsonl \
      --out data/labelled_guards.jsonl --raw data/labelled_guards_raw.jsonl \
      --provider groq --workers 1 --per-language 60 --no-balance --limit 2000

`--no-balance` matters: the guard corpus is buggy by construction, and the
balancer would otherwise fill half the sample with a clean class that does not
exist and label only half the requested limit.

### Labelling pass 1 complete (18 Aug, evening)

Pass 1 over the general mined corpus finished: **1,013 commits attempted, 1,011
kept**, 0 dropped by `verify()` in the final fragment. It overshot the 959
target because `--limit` applies to the commits *not yet done* at each
relaunch, not to the cumulative total — a resumed run therefore attempts up to
`limit` more. Harmless here (more corpus), but it means the limit is not a
budget cap across restarts.

Composition of the 1,011:

| | |
|---|---|
| buggy / clean | 415 / 596 |
| languages | go 302, javascript 222, php 107, java 88, rust 79, python 78, typescript 70, ruby 59 (+6 stragglers: c 4, kotlin 1, unlabelled 1) |
| findings | 275 total — logic-error 103, error-handling 47, api-misuse 34, input-validation 33, null-dereference 24, resource-leak 10, other 9, security 8, concurrency 7 |

The SFT build passes its gate on this corpus:

    .venv/bin/python -m dataset_builder.build_sft_data \
      --jsonl data/labelled_multilang.jsonl \
      --langs go typescript javascript java php rust python ruby --out /tmp/dry.jsonl

gives **1,005 examples, 0% repeated assistant turns**, 251 with findings, 754
clean.

A keyword sweep for guard/validation language over those 275 findings hits **78
(28.4%)**, against the ~5% recorded above. **The two numbers are not
comparable** — the earlier 7-of-141 was a hand count, this is a broad regex. It
is not evidence the guard problem solved itself, and the targeted corpus is
still the plan.

That sweep now lives in `guard_share.py` rather than in a shell history, so
every corpus is measured the same way:

    .venv/bin/python guard_share.py data/labelled_multilang.jsonl

An earlier ad-hoc version of the same regex reported 20.7% (57 findings). It was
wrong: it matched `null (pointer|deref)` with a literal space, so it missed the
hyphenated `null-dereference` category entirely — 24 findings, every one of them
a missing-check defect. The corrected pattern matches `(nil|null)[ -]?(pointer|
deref)` and takes the count to 78. **28.4% is the pass-1 baseline the guard
corpus has to beat**; treat any earlier 20.7% in notes or handoffs as superseded.

Guard share by category on pass 1 — the breakdown is what makes the number
readable, since two categories are guard-flavoured by definition and the rest
are not:

| category | findings | guard-flavoured |
|---|---|---|
| logic-error | 103 | 10 |
| error-handling | 47 | 8 |
| api-misuse | 34 | 1 |
| input-validation | 33 | 33 |
| null-dereference | 24 | 24 |
| resource-leak | 10 | 1 |
| other | 9 | 0 |
| security | 8 | 1 |
| concurrency | 7 | 0 |

So 57 of the 78 are the two categories that are guard-flavoured by construction,
and only 21 of the other 197 findings describe a missing check. That is the gap
the targeted corpus exists to close.

**Six Groq organisations now**, not three: `GROQ_API_KEY1..6`, so the ceiling is
6 × 200,000 = 1.2M tokens/day ÷ ~1,863 tokens per commit ≈ **640 commits/day**.
The 480-commit guard phase is therefore under a day of budget, not the ~1.5 days
estimated at three keys.

### Guard-corpus labelling resumed (18 Aug, 20:48)

The phase was stopped at 6 of 480 on the evening of 18 Aug with all six Groq
keys returning 429, and both the labeller and the watchdog were killed. It was
restarted the same evening after probing the keys directly:

    curl -s -D - -o /dev/null -X POST https://api.groq.com/openai/v1/chat/completions \
      -H "Authorization: Bearer $GROQ_API_KEY1" -H "Content-Type: application/json" \
      -d '{"model":"openai/gpt-oss-120b","messages":[{"role":"user","content":"hi"}],"max_tokens":1}'

All six answered `HTTP/2 200` with `x-ratelimit-remaining-tokens: 7927` of an
8,000 limit. **The evening's 429s were the per-minute ceiling, not the daily
one** — the retry-after values in `label_guards.log` were 2–17 minutes, which is
TPM churn; a spent daily budget returns a retry-after measured in hours. Worth
remembering, because the run was stopped on the assumption that the day's budget
was gone. Probe before waiting a day: Groq does not expose a daily-remaining
header, so a single 1-token request is the only cheap way to tell the two limits
apart.

Restarted with the documented one-liner and it went straight to the guard phase,
as designed (pass 1's raw count is past its 959 limit):

    setsid nohup ./label_watch.sh >> label_watch.log 2>&1 < /dev/null &

The evening's run was stopped again at 21:0x, at **37 kept / 37 attempted of
480, 0 dropped, 0 failed** — the per-minute ceiling makes throughput about
5 commits per minute at `--workers 1`, so the remaining 443 are a next-day job
against a fresh daily budget rather than an overnight one. Composition of the
37, too small to conclude from but worth watching:

| | |
|---|---|
| records with a finding | 22 of 37 (59%) |
| guard-flavoured findings | 8 of 22 (36.4%) |

The guard share is above pass 1's 28.4%, which is the intended direction. The
finding rate is the number to watch: the corpus is buggy by construction, so a
finding rate that settles near 59% rather than near 100% means the teacher is
not seeing the guard class, and that is a prompt problem to fix *before* ten
hours of GPU time. Re-measure with `guard_share.py` at ~100 records — early
enough to change the prompt without burning the phase — and again at 480.

### Guard corpus finished, checkpoint-204 trained and evaluated (19–21 Aug)

The guard phase ran to completion over 19–20 Aug (not captured turn-by-turn —
no session was open) and landed at **662 kept / 662 attempted, 0 dropped, 0
failed** — overshot the 480 target the same way pass 1 overshot 959, but for a
distinct reason this time: `--per-language 60` capped against *this run's*
sample, not against records already on disk from earlier relaunches, so each
restart re-capped 60-per-language on top of what was already kept. `guard_share.py`
on the finished corpus:

    .venv/bin/python guard_share.py data/labelled_multilang.jsonl data/labelled_guards.jsonl

    data/labelled_guards.jsonl
      662 records, 322 findings, 109 guard-flavoured (33.9%)
        logic-error           144  guard   23
        error-handling         51  guard    5
        null-dereference       38  guard   38
        input-validation       33  guard   33
        api-misuse             22  guard    1
        security               14  guard    6
        concurrency             9  guard    1
        off-by-one              6  guard    2
        resource-leak           4  guard    0
        other                   1  guard    0

**33.9% beats the pass-1 baseline of 28.4%** — the guard corpus did what it was
mined for, and the extra 182 commits over budget bought more of that signal
rather than diluting it. `corpus/label.py`'s per-language cap was fixed after
the fact (`cap_per_language()`, seeded with counts already in the output file)
so a future relaunch stops at the true 60/language instead of re-capping on
top of prior kept records — not yet committed, see "Uncommitted at handoff"
below.

Merged and built the SFT set:

    cat data/labelled_multilang.jsonl data/labelled_guards.jsonl > data/labelled_all.jsonl   # 1,673 records
    .venv/bin/python -m dataset_builder.build_sft_data --jsonl data/labelled_all.jsonl \
      --langs go typescript javascript java php rust python ruby --out data/sft_multilang8.jsonl
    # -> 1,667 examples

Trained on `oracle-gpu` (`sft_multilang8.log`, finished 21 Aug 07:41) ->
`artifacts/sft-adapter/checkpoint-204`. Evaluated the same day across all
three heldout sets (`evaluate.py`, log `eval_204.log`):

| eval | commits | detection P/R/F1 | acc | grounded | category match | findings |
|---|---|---|---|---|---|---|
| `sft-204` (`labelled_heldout.jsonl`, default) | 200 | 0.42/0.22/0.29 | 0.50 | 100.0% | 5.9% | 57 |
| `sft-204-1k` (`detect_eval.jsonl`, ApacheJIT) | 1000 | 0.52/0.29/0.37 | 0.51 | 99.0% | — | 309 |
| `cve-204` (`cvefixes_eval.jsonl`, human text) | 1000 | 0.59/0.51/0.55 | 0.58 | 91.5% | 20.8% | 531 |

checkpoint-204 (merged corpus, guard-augmented) beats checkpoint-220's old
numbers on the CVE set specifically — the set with human ground truth, the
strongest evidence available. Category match on the smaller two evals (5.9%,
n/a) is noisy at 200 commits and not the number to trust; cve-204's 20.8% is
the one comparable to the 27% figure ROADMAP flags as stuck.

### Ablation: general-only vs guard-augmented SFT (21–22 Aug)

To isolate whether the guard corpus actually earned its ~2.75 days of Groq
budget, rather than the merged corpus just having more data, built a
same-size control from pass 1 alone (no guard commits):

    .venv/bin/python -m dataset_builder.build_sft_data --jsonl data/labelled_multilang.jsonl \
      --langs go typescript javascript java php rust python ruby --out data/sft_general.jsonl
    # -> 1,005 examples, same corpus build as the original pass-1 measurement

Trained on `oracle-gpu` (`sft_general.log`, finished 22 Aug 04:52) ->
`artifacts/sft-adapter-general/checkpoint-136`. Evaluated 22 Aug across the
same three heldout sets as checkpoint-204 (`evaluate.py`, log
`eval_general.log`, 11:07–20:43):

| eval | commits | detection P/R/F1 | acc | grounded | category match | findings |
|---|---|---|---|---|---|---|
| `sft-general` (`labelled_heldout.jsonl`, default) | 200 | 0.53/0.25/0.34 | 0.56 | 100.0% | 5.9% | 53 |
| `sft-general-1k` (`detect_eval.jsonl`, ApacheJIT) | 1000 | 0.49/0.25/0.33 | 0.49 | 99.6% | — | 278 |
| `cve-general` (`cvefixes_eval.jsonl`, human text) | 1000 | 0.63/0.57/0.59 | 0.61 | 94.9% | 21.0% | 545 |

Head to head against checkpoint-204 (guard-augmented, 1,667 examples vs the
control's 1,005):

| eval | metric | general (136) | guard-augmented (204) | delta |
|---|---|---|---|---|
| ApacheJIT 1k | F1 | 0.33 | 0.37 | **-0.04 for general** |
| ApacheJIT 1k | recall | 0.25 | 0.29 | -0.04 |
| CVEfixes 1k | F1 | 0.59 | 0.55 | **+0.04 for general** |
| CVEfixes 1k | recall | 0.57 | 0.51 | +0.06 |
| CVEfixes 1k | grounded | 94.9% | 91.5% | +3.4pp |
| CVEfixes 1k | category match | 21.0% | 20.8% | +0.2pp (tie) |
| 200-commit heldout | F1 | 0.34 | 0.29 | +0.05 (noisy at n=200) |

**Verdict: the guard corpus did not earn its budget.** The guard-augmented
adapter wins only on ApacheJIT — the in-distribution set whose teacher labels
come from the same pipeline that mined the guard commits — and loses on
CVEfixes, the only set with human ground truth, on every metric that matters
there. Category match, the number this ablation was built to move, is a tie
(21.0% vs 20.8%, within noise at n=1000). The control reached it with 40%
fewer training examples, so the merged corpus's extra data bought nothing that
transfers off-distribution.

Two caveats on how hard to read this:

- Per §4, `cvefixes_eval.jsonl` cannot carry a *detection* claim (the counting
  baseline scores 0.934 on it), so the F1/recall deltas on that row are weak
  evidence. Grounded% and category match are the usable signals there, and
  those are +3.4pp and a tie.
- Neither run was seed-repeated. A 0.04 F1 gap on a single seed is not a
  result; both directions of the ApacheJIT/CVE split could move under a rerun.

What this changes: the paper cannot claim the guard corpus improves
detection or explanation quality. It can still claim the guard *mining* raised
the guard-class share of the corpus from 28.4% to 33.9% (see "Guard share by
category") — a corpus-composition result, not a model result. Keep the two
claims separate.

### Rendering variance: the same commit, four ways (23 Aug)

Every number above is a single greedy pass over one exact rendering of each
commit. That is only meaningful if the model reads a *commit* rather than a
rendering of one. A Go commit with an unambiguous data race (verified with
`go run -race`: 4 warnings, and 1 run in 20 silently loses a record) was
reported as `concurrency` on one rendering of its diff and `null-dereference`
on another that differed only in blob hashes and where git grouped a blank
line — same model, same greedy decode, same code shown.

So `variance.py` measures the noise floor directly: perturb the diff without
touching a single line of code, re-ask, and count how often the answer moves.
The three perturbations edit git metadata only, so any disagreement is the
model reacting to text it should ignore.

| rendering | what changes | applied to |
|---|---|---|
| `base` | nothing (reference) | — |
| `no_index` | drops the `index <sha>..<sha>` line | 40/40 |
| `rehash` | rotates the blob hashes, keeps the mode | 40/40 |
| `bare_hunk` | strips the function name after the `@@` | 34/40 |

Run against `oracle-merged` (post-DPO) on the first 40 held-out commits,
160 calls, zero failures:

    .venv/bin/python variance.py --limit 40 --backend ollama \
      --model-name oracle-merged --host http://localhost:8111
    # -> data/variance_results.jsonl; re-report with --score

    verdict agreement    87.7%   (100/114)
    category agreement   85.1%   (97/114)
    commits unanimous    72.5%   (29/40)

Detection on the *same 40 commits* with the *same model*, per rendering:

| rendering | F1 | prec | recall | tp/fp/fn/tn |
|---|---|---|---|---|
| `base` | 0.154 | 0.222 | 0.118 | 2/7/15/16 |
| `no_index` | 0.276 | 0.333 | 0.235 | 4/8/13/15 |
| `rehash` | 0.080 | 0.125 | 0.059 | 1/7/16/16 |
| `bare_hunk` | 0.312 | 0.333 | 0.294 | 5/10/12/13 |

**F1 spread 0.080–0.312 = 0.233 from cosmetic edits alone.** The
guard-corpus ablation above turns on a 0.04 F1 gap. That gap is roughly six
times smaller than what deleting a blob hash moves the same model on the same
data.

The flips have a direction — removing metadata git puts in the header makes
the model report *more*, not randomly different:

    bare_hunk   +7 / -1     (more findings / fewer)
    no_index    +3 / -0
    rehash      +1 / -2

How hard to read this, honestly:

- n=40, and it is the *first* 40 of the heldout, not a random sample. The
  absolute F1 here (base 0.154) is far below the 0.34 this checkpoint scores
  on the full 200 — which is itself a demonstration of how small-n these
  numbers are. Only the *spread within the same 40 commits* is the
  measurement; the absolute values are not comparable to the tables above.
- 17 of the 40 are buggy, so one tp swing moves F1 hard. That inflates the
  spread relative to what 200 commits would show.
- One model, three perturbation types. Says nothing yet about whether SFT is
  more or less stable than DPO.

What this changes: §4's "neither run was seed-repeated" caveat stops being a
footnote. Until the 200-commit version of this run exists, no single-seed gap
smaller than the rendering spread can be reported as a result — including the
guard-corpus verdict. The ablation's *direction* may well survive; its
magnitude is currently unqualified.

Reproduce a single flip interactively: `:perturb bare_hunk` in the TUI, then
`a`. The header shows `rendering:<name>` while it is active so a perturbed
verdict cannot be mistaken for the model's real one. A commit that does not
flip proves nothing (72.5% were unanimous) — it is a spot check, not the
measurement.

### Rendering variance at n=200 (24 Aug)

The 200-commit version of the run above, same model (`oracle-merged`), same
three perturbations, 800 calls, **zero dropped**:

    .venv/bin/python variance.py --limit 200 --backend ollama \
      --model-name oracle-merged --host http://localhost:8111 \
      --out data/variance200.jsonl --name "oracle-merged, 200 x 4"
    .venv/bin/python variance.py --score data/variance200.jsonl

| | n=40 | n=200 |
|---|---|---|
| verdict agreement | 87.7% (100/114) | 89.2% (522/585) |
| category agreement | 85.1% (97/114) | 85.3% (499/585) |
| commits unanimous | 72.5% (29/40) | 77.5% (155/200) |

585 comparisons, not 600: 15 perturbations did not apply and are skipped
rather than scored as agreement. 63 commits flipped verdict on at least one
rendering.

Detection on the same 200 commits, per rendering:

| rendering | F1 | prec | recall | tp/fp/fn |
|---|---|---|---|---|
| `base` | 0.375 | 0.441 | 0.326 | 30/38/62 |
| `no_index` | 0.329 | 0.394 | 0.283 | 26/40/66 |
| `rehash` | 0.352 | 0.418 | 0.304 | 28/39/64 |
| `bare_hunk` | 0.417 | 0.461 | 0.380 | 35/41/57 |

**F1 spread 0.088**, down from 0.233 at n=40. Both branches predicted for this
run were half-right:

- The n=40 spread *was* mostly small-sample noise. With 17 buggy commits in
  that sample a single tp swing moved F1 by ~0.06, and the 0.233 figure should
  not be quoted again.
- The effect did *not* vanish. 0.088 is still **2.2x the 0.04 F1 gap** the
  guard-corpus ablation turns on, so §4's conclusion stands unchanged: that
  ablation cannot be reported as a result without a variance column beside it.

`bare_hunk` remains the most permissive rendering and `no_index` the least, the
same ordering as n=40, so the direction is stable even though the magnitude
shrank. Absolute F1 (base 0.375) is now in line with the 0.34 this checkpoint
scores on the full heldout, which is the expected correction from the biased
first-40 sample.

### DPO retrain: the clipping hypothesis, eliminated (24 Aug)

The 23 Aug DPO run logged `grad_norm` 11.8–20.1 against HF's default
`max_grad_norm=1.0` and produced output byte-identical to SFT. The standing
explanation was that clipping every step 10–20x had driven the effective
learning rate far below the 5e-6 schedule. **That explanation is wrong.**

`max_grad_norm` is now a knob (`config.py:93`, `DPO_MAX_GRAD_NORM`, default
25.0, env `ORACLE_DPO_MAX_GRAD_NORM`) and the run was repeated with it set
above the observed gradient range — one variable changed, everything else
identical:

| step | grad_norm 23 Aug | grad_norm 24 Aug | loss 23 Aug | loss 24 Aug | margins 23 Aug | margins 24 Aug |
|---|---|---|---|---|---|---|
| 5 | 18.3 | 17.75 | 1.863 | 1.862 | 0.007 | 0.008 |
| 10 | 20.1 | 19.38 | 1.754 | 1.753 | 0.105 | 0.105 |
| 15 | 13.1 | 12.75 | 1.743 | 1.748 | 0.264 | 0.253 |
| 20 | 11.8 | 11.56 | 1.575 | 1.585 | 0.589 | 0.560 |

Removing the clip changed the loss curve by less than a rounding error,
because `paged_adamw_8bit` normalises the update by `g/sqrt(v)`. Adam is
scale-invariant to a uniform rescaling of the gradient: clipping changes the
gradient's magnitude, not the step Adam takes from it. Gradient clipping was
never the lever.

Output comparison, `data/go_race_case.diff`, greedy, `INFERENCE_SAMPLES=1`,
`sft-merged` run twice as a determinism control:

    sft_a  md5=5bb2c1a4d335c82ca94094869553129b
    sft_b  md5=5bb2c1a4d335c82ca94094869553129b   <- control: deterministic
    dpo1   md5=5bb2c1a4d335c82ca94094869553129b   (oracle-merged, 23 Aug)
    dpo2   md5=5bb2c1a4d335c82ca94094869553129b   (oracle-merged-v2, 24 Aug)

All four identical. Both DPO checkpoints and the SFT model they came from
produce the same bytes, and all three miss the verified data race.

A methods note that cost an hour to learn: **`INFERENCE_SAMPLES=3` is not a
deterministic path.** `client.py:453` runs sample 0 greedy and samples 1..n at
`INFERENCE_SAMPLE_TEMPERATURE=0.6`. A first pass at the comparison above showed
all three checkpoints "differing", and the entire difference was the
`(N finding(s) appeared in a minority of 3 samples and were dropped.)` clause
moving between 3 and 1. Any checkpoint A/B must set `INFERENCE_SAMPLES=1` or it
measures the sampler.

### Why real preference pairs do not fit this card (24 Aug)

`from_labelled()` builds pairs from the teacher-labelled corpus, keeping only
findings that `grounded()` can trace to text actually in the diff. Run over all
1,673 records:

    source records            1673
    pairs after grounded()     525  (31.4%)

                              min    med    p90    p95    max
    prompt                    509   1235   1935   2100   2552
    chosen                     78    144    191    220    426
    rejected                   24     24     24     24     24
    prompt+max(answer)        615   1386   2093   2270   2713

| max_length | pairs kept |
|---|---|
| 512 (current) | 0 (0.0%) |
| 768 | 40 (7.6%) |
| 1024 | 122 (23.2%) |
| 1536 | 322 (61.3%) |
| 2048 | 468 (89.1%) |

**Not "most do not fit" — none do.** The shortest real pair is 615 tokens
against a 512 budget. The mock pairs that trained all three DPO runs have a
414-token median prompt; the real ones have 1235. The templates were never a
scaled-down version of the real distribution, they were a different one.
Keeping a useful 61% needs `max_length=1536`, and `config.py` records a
measured OOM at 768 on this 6GB card — a factor of two past where the hardware
already failed.

A second blocker is independent of memory:

    1 unique rejected string(s) across 525 pairs
    '{"summary": "This change looks like a small, safe adjustment; no defects
      found.", "findings": []}'

Every rejected side is the same hardcoded sentence, so the objective reduces to
"do not emit this exact string" — the same degenerate signal that saturates
`rewards/accuracies` at 1.00 by step 10 on the mock set. Fixing the fit would
not fix the signal. Working DPO needs both: real pairs at `max_length>=1536` on
a >=16GB card, and a rejected side generated per-example from the model's own
wrong answers.

`from_labelled()` is also unreachable from the CLI — `build_dpo_data.main()`
wires only `--mock`, `--reviews` and `--from-eval` — which is presumably why
this wall was not hit earlier.

**What this supports.** Three DPO runs agree the stage moves nothing
measurable, and the audit gives two independent reasons this card cannot
resolve. The null is reportable as-is: preference alignment on 180 synthetic
pairs does not move a 3B reviewer. It is not evidence that DPO cannot help
here, only that it was never given a signal.

### The gate was trained on its own evaluation set (24 Aug)

`train_gate.py` defaults to `--jsonl data/apachejit_commits.jsonl`. That file
contains **all 200** commits of `data/labelled_heldout.jsonl`. Every gate number
ever measured on the held-out set is train-on-test.

Retraining with `--exclude data/labelled_heldout.jsonl` costs nothing on the
gate's own chronological split (AUC 0.823 against the published 0.8293) and
changes the held-out numbers completely:

| gate | prec | rec | F1 | AUC |
|---|---|---|---|---|
| `gate.joblib` (leaked) | 1.000 | 0.641 | 0.781 | 0.9638 |
| `gate_noleak.joblib` (clean) | 0.800 | 0.174 | 0.286 | 0.7530 |

The leak was worth **0.495 F1 and 0.21 AUC**. Labels agree 200/200 between the
two files, so this is not a labelling artifact.

The clean run also exposes that `GATE_THRESHOLD` does not transfer. Tuned to
0.047 for 95.1% recall on 27.5%-buggy chronological ApacheJIT, it yields 17.4%
recall on the 46%-buggy held-out set: it forwards 20 of 200 commits to Stage 2
and drops 76 of 92 defects. At its shipped setting the cascade front-end is
worse than no gate at all.

Operating points on the held-out set, clean gate:

| threshold | tp | fp | fn | prec | rec | F1 | sent to Stage 2 |
|---|---|---|---|---|---|---|---|
| 0.047 (trained) | 16 | 4 | 76 | 0.800 | 0.174 | 0.286 | 20/200 |
| 0.006 (best F1) | 79 | 55 | 13 | 0.590 | 0.859 | **0.699** | 134/200 |
| 0.001 (95% recall) | 92 | 103 | 0 | 0.472 | 1.000 | 0.641 | 195/200 |

0.699 is tuned on the evaluation set and is therefore an upper bound; the
95%-recall point, which is not tuned for F1, still clears the trivial baseline.

### Where Stage 2 actually sits (24 Aug)

All on the same 200 held-out commits:

| | prec | rec | F1 |
|---|---|---|---|
| always-buggy baseline | 0.460 | 1.000 | **0.630** |
| clean gate, retuned | 0.590 | 0.859 | 0.699 |
| teacher, gpt-oss-120b unhinted | 0.563 | 0.435 | 0.491 |
| student, 3B `oracle-merged` | 0.441 | 0.326 | 0.375 |

Distillation cannot lift Stage 2 past 0.491, and 0.491 is below the trivial
baseline. Optimising Stage 2 for detection is optimising the weaker component
toward a lower ceiling. Stage 1 detects; Stage 2 should be measured on
explanation.

### The evaluation was out of domain (24 Aug)

The number above is worse than it looks, because the model was never trained on
anything resembling the test set.

    heldout  (200)  ~85% Java, 100% Apache: camel 42, cassandra 23, ignite 19,
                    hbase 19, activemq 18, groovy 16, hadoop 16, hive 16, ...
    training (1673) 21 non-Apache web/infra projects: laravel 201, caddy 150,
                    hugo 149, netty 140, express 119, sinatra 119, axios 115,
                    gin 111, flask 104, fastify 102, tokio 88, ...
                    java share: 192/1673 = 11.5%

Zero project overlap, and Java is 11.5% of training against ~85% of the
evaluation. **F1 0.375 is an out-of-domain measurement.** Two consequences:

- The gate-vs-Stage-2 comparison above is not like-for-like. The gate trained
  on ApacheJIT, the same domain as the test set; the LLM did not. Some of the
  0.699 vs 0.375 gap is domain, not architecture.
- Student-vs-teacher (0.375 vs 0.491) is still clean: the teacher ran unhinted
  on the same held-out commits.

The rendering-variance result is unaffected - it holds the model and the
commits fixed and varies only the rendering.

Fixed by splitting `labelled_all.jsonl` by **project** (`split_by_project.py`),
holding out gin, fastapi, axios, clap and spring-boot: 1332 train / 341 held
out, every language present on both sides. Those 5 projects appear in neither
the new training set nor the gate's (`labelled_all` shares 0 commits with
`apachejit_commits.jsonl`), making `data/ml8_heldout.jsonl` the first slice in
this project clean for **both** stages, and the cascade measurable at last.

### grounded() never rejected anything (24 Aug)

`grounded()` returned True as soon as a finding named a file the diff touched.
On a single-file commit every finding names the only file, so the check was a
no-op: it passed **69 of 69** live findings and **597 of 597** corpus findings.
Every "grounded: N%" in this file before today was 100% by construction.

The filename is now necessary but not sufficient. Deleted lines still ground a
finding, since removing a guard is a real defect class and only 27 of 597
corpus findings (4.5%) rest on deleted lines alone.

    live model output   69/69  (100%)  -> 54/69  (78.3%)
    training corpus    597/597 (100%)  -> 489/597 (81.9%)   108 rejected
    all-grounded records  525/1673     -> 425/1673

**Both figures are superseded**: `identifiers()` was under-counting, and the
rule that replaced it is measured in the next section. Do not quote 78.3% or
81.9%.

Filtering on it at inference was measured and rejected: it costs 0.065 F1 for
no precision gain (0.441 -> 0.440), because detection F1 is blind to whether a
finding is correct. A finding inventing a defect on a commit that happens to be
buggy scores as a true positive.

`fix_agreement()` has never executed. It reads `r["fix_diff"]`, which no dataset
in `data/` provides, so it returned NaN and the report's NaN guard printed
nothing - the output looked complete while one of its five advertised measures
had never run once. It now prints "unavailable" with the reason. Making it real
is not plumbing: ApacheJIT's `fix` column is a boolean, not a hash, and all 500
CVEfixes pairs are exact reverses of each other, so the paired record as
"repair" would make the metric tautological.

### Two species of hallucination (24 Aug)

| species | example | grounding catches it |
|---|---|---|
| cites nothing | Makefile finding claims `CFLAGS` was removed; it is on line 1 of a new file | yes - 21.7% of live findings |
| cites real tokens, states a falsehood | heap.js finding predicts `RangeError: Index out of range`, which JS cannot raise for `arr[0]`; verified with node that removing the guard is behaviour-preserving | **no** |

A third failure is the plain miss: the Go data race (`data/go_race_case.diff`,
4 `-race` warnings, 4% of runs lose a record) reported as clean by every
checkpoint.

Species two is the dangerous one and nothing in this repo measures it.
Grounding passes it, detection F1 rewards it, `fix_agreement` never runs. All
three examples above were settled by *executing* the code, which is what
`bench/basic_bench.py` was built to do.

### Basic-algorithm benchmark (24 Aug)

`bench/basic/`, 12 cases (8 buggy, 4 clean) in go, javascript, python and c,
each small enough to run. Ground truth is proved rather than inferred: buggy
means post misbehaves where pre does not, clean means both produce identical
output, re-verified on every invocation.

    python bench/basic_bench.py --verify        # 12/12 verified, ~40s, no GPU

**Superseded by the 44-case three-way run below, and the sampling note here is
wrong.** `INFERENCE_SAMPLES=1` sets nothing: `config.py:18` reads
`ORACLE_INFERENCE_SAMPLES`, so this ran 3-sample consensus at the default. See
"Two bugs that made every earlier basic-bench number un-reproducible". Kept for
the hand-vs-automated gap, which still holds.

`oracle-merged`, greedy, `INFERENCE_SAMPLES=1` *(as recorded; actually 3)*:

| grading | score |
|---|---|
| automated (locus: does it name the faulty construct) | 11/12, 0 hallucinated |
| hand (mechanism: is the explanation right) | **8/12**, 1 inverted, 2 wrong-mechanism, 1 miss |

The two numbers measure different things and the gap is the point: the model
finds the right line in 11 of 12 cases and explains it correctly in 8. The
automated scorer cannot see an inverted claim - `go-accum-reset` names `total`
correctly while describing a hoisted accumulator as newly added inside the
loop - so treat it as a floor.

Against the same model's 0.375 on Apache Java, this is a different regime.
Basic algorithmic code across the 8 corpus languages is near the training
distribution and is where the useful target (8/10 with no hallucination) is
realistic. 12 cases is too few to claim a rate; ruby, php, rust and typescript
are not covered yet.

### Base vs fine-tuned, 12 cases (25 Aug) — superseded

A first pass compared base `Qwen2.5-Coder-3B-Instruct` with `oracle-merged` on
the 12-case set and concluded fine-tuning helps. **That conclusion survives the
rerun; the numbers do not.** Both runs were recorded as `INFERENCE_SAMPLES=1`
and were in fact 3-sample consensus, and the scorer has since been fixed twice.
The 44-case three-way run below replaces this table entirely.

### Benchmark expanded to 44 cases, then 46, 9 languages (25 Aug)

12 cases over 4 languages was too few to claim a rate, and it covered none of
ruby, php, rust, typescript or java — between them 708 of the 1332 `ml8`
training records. The set is now 46 cases, every label still proved by
execution rather than inferred:

    python bench/basic_bench.py --verify     # 46/46 verified, ~3 min, no GPU

The last two — `py-annotate-only` and `py-pop-guard` — were added after the
three-way run below, from a live session against `~/Documents/TestJIT/pystruct`
where the model failed two real commits. They are the only cases here taken
from the wild rather than written for the benchmark.

| language | buggy | clean | total |
|---|---|---|---|
| c | 3 | 1 | 4 |
| go | 3 | 2 | 5 |
| java | 4 | 1 | 5 |
| javascript | 3 | 2 | 5 |
| php | 4 | 1 | 5 |
| python | 4 | 3 | 7 |
| ruby | 4 | 1 | 5 |
| rust | 4 | 1 | 5 |
| typescript | 4 | 1 | 5 |
| **all** | **33** | **13** | **46** |

The 13 clean cases are the false-alarm half of the target — a finding on any of
them is a hallucination by definition, proved by execution. Every one of them is
a behaviour-preserving refactor, because that is what makes a case clean:
extract a helper, rename a local, add type annotations, swap a loop for a
comprehension. That is also where every model tested so far invents defects.

Runtimes, all local, no container: rust compiles with plain `rustc` (no `-O`,
because debug assertions are what turn a silent integer overflow into a visible
panic), typescript runs under `deno run` (no tsconfig, and Deno 2 does not
type-check on `run`, so this measures runtime behaviour like every other case),
java uses the Java 11+ single-file source launcher (no `javac` step, no
class-name/filename constraint), ruby and php run their interpreters directly.
`ruby` and `php` were installed on the laptop for this; the rest were already
present.

All three models have since been scored on the full 44 — see below.

### Three models on the full 44 (25 Aug)

The first honest run of this benchmark: 44 cases, 9 languages, greedy, one
sample, scored with the fixed scorer. **These three columns are a 44-case
measurement and stay that way** — `py-annotate-only` and `py-pop-guard` were
added afterwards, and only `oracle-merged` has been run on the full 46 (see
below). Do not mix the two denominators. `sft-ml8-grounded` is the retrain that
finished 25 Aug 10:10 WIB (154/154 steps, 9h27m, loss 1.714 -> 0.418, token
accuracy 0.597 -> 0.883).

    # on the box, one model at a time - a second 3B does not fit the 6GB card
    .venv/bin/python -m llm_explainer.serve --model artifacts/<name> --port 8111

    # on the laptop, through the tunnel. Note the ORACLE_ prefix.
    ORACLE_INFERENCE_SAMPLES=1 python bench/basic_bench.py --backend ollama \
        --model-name <name> --host http://localhost:8111 \
        --out data/basic_bench_<name>.jsonl

| | base 3B | `oracle-merged` | `sft-ml8-grounded` |
|---|---|---|---|
| verdict correct | 34/44 (77%) | 40/44 (91%) | 38/44 (86%) |
| **fully correct (locus)** | 33/44 (75%) | **40/44 (91%)** | 38/44 (86%) |
| **false alarms** (proved by execution) | 2 | **1** | 3 |
| locus unconfirmed | 1 | 0 | 0 |

| language | base | `oracle-merged` | `sft-ml8-grounded` |
|---|---|---|---|
| c | 4/4 | 4/4 | 4/4 |
| go | 4/5 | 4/5 | 5/5 |
| java | 3/5 | 4/5 | 5/5 |
| javascript | 3/5 | 4/5 | 3/5 |
| php | 4/5 | 5/5 | 3/5 |
| python | 3/5 | 5/5 | 4/5 |
| ruby | 4/5 | 5/5 | 5/5 |
| rust | 5/5 | 4/5 | 5/5 |
| typescript | 3/5 | 5/5 | 4/5 |
| **all** | **33/44** | **40/44** | **38/44** |

Three results, in order of how much they should change what happens next.

**1. Fine-tuning beats the base model, on a slice where the base model is
already decent.** 33/44 -> 40/44 is +7 cases, and the base model's failures are
not subtle: it answers "This change does not introduce any defects" on six
buggy cases it has just described correctly, and on `ts-nullish-default` it
emitted unescaped quotes inside a JSON string and failed schema validation
twice. Criterion 3 of the acceptance list is about separation on ApacheJIT, not
this, but the direction is the same.

**2. The retrain is a regression, and a small one.** `sft-ml8-grounded` loses 2
cases against `oracle-merged` and triples the false alarms, 1 -> 3. It gains
java (4/5 -> 5/5), go and rust; it loses php (5/5 -> 3/5), typescript (5/5 ->
4/5), python and javascript. **Do not ship it, and do not read it as proof that
the grounding filter hurts** - `sft-ml8-grounded` differs from `oracle-merged`
in three ways at once (grounding filter, project split, smaller corpus), which
is exactly what the control run on `data/sft_ml8_base.jsonl` exists to
separate.

**3. All three of the retrain's false alarms are refactor-only clean cases**:
`js-extract-helper`, `js-rename-param`, `php-extract-helper`. Against
`oracle-merged`'s one (`rs-rename-local`). The new checkpoint invents defects
in code that provably does not change behaviour - the same failure the 0.088
rendering-variance result points at, moved in the wrong direction. This is the
single most useful signal on the page: the 12 clean cases are where the "no
hallucination" half of the goal is decided, and the retrain went backwards on
them while going forwards on detection.

Every failure across all three runs was read by hand. All 15 are genuine
after the scorer fixes below; none is a scoring artifact.

### Two bugs that made every earlier basic-bench number un-reproducible (25 Aug)

**`INFERENCE_SAMPLES=1` never set anything.** `config.py:18` is
`os.getenv(f"ORACLE_{name}")`, so the variable is `ORACLE_INFERENCE_SAMPLES`.
Every basic-bench run before this one ran 3-sample consensus at the default
while its write-up said greedy single-sample. `_env()` now prints to stderr when
the bare name is set and the prefixed one is not:

    config: ignoring INFERENCE_SAMPLES='1' - this setting is read from
    ORACLE_INFERENCE_SAMPLES, so the bare name has no effect

The warning is in `_env` itself, so it covers every setting in `config.py`, not
just the one that bit.

**The three samples were byte-identical anyway.** `client.py:453` asks for
samples 1..n at `INFERENCE_SAMPLE_TEMPERATURE=0.6`, but `serve.py`'s `do_POST`
reads only `num_predict` from `options` and `generate()` uses the server's own
`TEMPERATURE`, which is 0.0. Verified against the live server:

    temp=0.0 -> The sea is vast and mysterious, with waves crashing against ...
    temp=1.8 -> The sea is vast and mysterious, with waves crashing against ...

Consequences, in order of severity:

- **`_analyze_consensus` has never done anything through `serve.py`.** The
  "sample several times, keep what a majority agrees on" defence - the one
  designed to catch a defect invented fluently and only once - is a no-op on
  the served backend. It is not dead code on the local-transformers backend;
  it has simply never been exercised where every measurement is taken.
- Every served run costs 3x the GPU time for three copies of one answer.
- Results are *not* simply equal to greedy: `client.py:473` merges findings by
  category and keeps the first per category, so a case emitting two findings of
  one category loses one under consensus. That is why all three models were
  rerun rather than relabelled.

The 24 Aug note "`INFERENCE_SAMPLES=3` is not a deterministic path" is
therefore right about the API and wrong about this backend, where it is
deterministic and merely wasteful. Whether that observation was taken with the
`ORACLE_` prefix is not recoverable from the logs.

### Scorer: correct paraphrases were being counted as hallucinations (25 Aug)

`identified()` required every `must_mention` token as a literal substring, and
`grade()` turned a failed match on a buggy case into a hallucination. So an
explanation that was right but paraphrased scored as a fabrication - the one
metric the goal says must be zero. Four of `sft-ml8-grounded`'s seven reported
hallucinations were correct answers:

| case | what the model said | token demanded |
|---|---|---|
| `php-divzero-guard` | "removes a null-check for an empty array in avg(), causing a DivisionByZeroError" | `count` |
| `php-slice-end` | "returns the first n-1 elements instead of the first n" | `array_slice` |
| `rb-int-division` | "replaces floating-point division with integer division" | `to_f` |
| `ts-nullish-default` | "replaces a null-coalescing operator with a logical-or" | `nullish` (and it wrote U+2011, not an ASCII hyphen) |

This is why php looked like a collapse to 1/5. It is 3/5.

Three fixes:

1. **A `must_mention` entry is a requirement; a list is a set of alternatives.**
   All requirements must hold, any one alternative meets its own. A bare string
   is a one-alternative requirement, so old cases still work. Alternatives use
   stems (`captur`, `mutat`, `exclud`) because the models inflect - `"captures"`
   failed against "capture the final loop iteration value".
2. **`grade()` separates the two failures** that were one `hallucinated` count.
   A finding on a case whose pre and post produce byte-identical output is
   *proved* fabricated by execution. An unmatched locus on a buggy case only
   means the scorer could not confirm it. Only the first is evidence of
   invention. `hallucinated` survives as their union so stored rows keep their
   schema.
3. **`_flat()` folds every dash-like character**, not just ASCII `-` and `_`.

Three entries were too *loose* rather than too strict and would have passed
wrong answers: `"int"` matched "print" and "point", `"var"` matched "variable",
`"acc"` matched "across". All three are now alternatives that name the real
locus.

Re-scoring is free and needs no GPU - `--score` re-grades stored answers
through the same `grade()` the live run uses:

    python bench/basic_bench.py --score data/basic_bench_oracle44.jsonl

**Never trust a stored row's own `verdict_ok` / `identified` / `hallucinated`
field.** Scorer fixes land after runs do - twice in one day here - and the
fields record what the scorer believed at run time. Only `predicted` is
evidence.

### Grounding: plain identifiers were invisible, and the fix needed a threshold (25 Aug)

`identifiers()` kept only tokens carrying `_`, `.` or a camelCase hump, so
`main`, `buf`, `len`, `size` and all-caps macros like `CFLAGS` never counted. In
a C, Makefile or shell diff that leaves the changed code with an **empty
vocabulary**, so no finding about it could ground however correct it was:

    -    memcpy(buf, src, len);
    +    memcpy(buf, src, size);

Not one token there survives the old filter. This is the same class of bug
`bench/basic_bench.py`'s `identified()` had — a right answer failing because it
did not phrase itself the way the matcher expected — and it under-counted in
both directions, shrinking the diff's vocabulary as well as the finding's.

**The obvious fix is worse than the bug.** Admitting plain names filtered
through `_STOP` moves grounding from 82.5% to 98.9%, which reads as a win until
it is controlled. The control: score every finding against a **randomly paired
commit**. A rule that passes those is measuring shared English, not grounding.

    python bench/../evaluate.py          # self-checks, both directions

| rule | real | mismatched | separation |
|---|---|---|---|
| decorated only (old) | 79–89% | 0.5–1.5% | +78 to +88pp |
| plain admitted freely | 96–99% | **18–36%** | +63 to +72pp |
| **shipped rule** | **93–94%** | **2.8–4.6%** | **+89 to +91pp** |

Ranges are across `labelled_multilang.jsonl` (275 findings),
`detect_sft220.jsonl` (635) and `cve_sft220.jsonl` (754). Admitting plain names
freely grounds **more than a third** of findings against a commit they have
nothing to do with.

The shipped rule, in `grounded()`:

- one **decorated** name shared is enough;
- otherwise **three** shared names, plain included;
- unless the changed code carries no decorated name at all — C, Makefile,
  shell — in which case one plain name is all a finding *can* cite.

It beats the old rule on separation on all three corpora **while finding more
real groundings**, so it is not a loosening. Separation is the measure §0 of
this file already commits to, and it is the right one here: a grounding check
that cannot tell a real pairing from a random one is not measuring grounding.

Grounding on `labelled_multilang.jsonl` moves **82.5% -> 92.7%**:

| language | findings | grounded |
|---|---|---|
| go | 98 | 94.9% |
| javascript | 72 | 93.1% |
| python | 21 | 100.0% |
| java | 21 | 90.5% |
| typescript | 12 | 91.7% |
| php | 19 | 84.2% |
| ruby | 20 | 80.0% |
| rust | 11 | 100.0% |
| c | 1 | 100.0% |
| **all** | **275** | **92.7%** |

ruby at 80.0% and php at 84.2% are the low pair, on 20 and 19 findings — too
few to act on, and worth re-reading before any per-language claim goes in a
table.

**Known limit, deliberately kept.** The token regex requires three characters,
so `i`, `n` and `xs` stay invisible. Admitting two-character tokens would let
stray prose ("is", "as", "it") ground a finding, which is the failure this
function exists to catch. A finding whose only citation is a one-letter loop
variable still cannot ground.

### `oracle-merged` on the full 46, including the two wild cases (25 Aug)

`py-annotate-only` and `py-pop-guard` were added after the three-way run, from
a live TUI session against `~/Documents/TestJIT/pystruct` in which the model
failed two real commits. Only `oracle-merged` has been scored on the full set,
so this is a **46-case number and does not belong in the 44-case table above.**

    ORACLE_INFERENCE_SAMPLES=1 python bench/basic_bench.py --backend ollama \
        --model-name oracle-merged --host http://localhost:8111 \
        --out data/basic_bench_oracle46.jsonl

| metric | score |
|---|---|
| verdict correct | 41/46 (89%) |
| **fully correct (locus)** | **41/46 (89%)** |
| **false alarms** (proved by execution) | 2/46 (4%) |
| locus unconfirmed | 0/46 (0%) |

| language | score |
|---|---|
| c | 4/4 |
| php | 5/5 |
| ruby | 5/5 |
| typescript | 5/5 |
| python | 6/7 |
| go | 4/5 |
| java | 4/5 |
| javascript | 4/5 |
| rust | 4/5 |
| **all** | **41/46** |

The five failures:

| case | failure |
|---|---|
| `go-nil-map` | miss — "initializing the map lazily... does not alter runtime behavior". A nil map panics on assignment. |
| `java-concurrent-modify` | miss — "the new logic correctly skips removed elements and does not introduce concurrency issues". It throws `ConcurrentModificationException`. |
| `js-reverse-index` | miss — "shifts the starting index but does not alter the loop body, so the computed sum remains unchanged". The sum is `NaN`. |
| `rs-rename-local` | **false alarm** — a consistent rename read as "forgets to update the return value". |
| `py-annotate-only` | **false alarm** — see below. |

**`py-pop-guard` is correct here.** It names the removed `self.head is None`
check and the lost `IndexError`, though only partly right on mechanism — it
predicts pop will "silently succeed... potentially returning None" where it
actually raises `AttributeError`, so the locus scorer passes it and a mechanism
hand-grade would not.

**This does NOT explain the miss seen in the TUI on the same commit.** An
earlier draft of this section blamed a weaker checkpoint; that was wrong.
`oracle-merged` was serving for both live sessions. The cause is context
injection — see the next section.

**`py-annotate-only` is the most instructive failure on this page.** It is not
the base model's error (inventing a removed docstring). `oracle-merged` invents
a *runtime consequence* for type annotations:

> "insertion_sort, merge, and merge_sort now accept only sequence types and
> return lists instead of the original iterable type. Callers that pass other
> iterables (e.g., generators) will receive a TypeError or incorrect result
> type."

Python does not enforce annotations at runtime, and `insertion_sort` calls
`list(items)`, which consumes any iterable. One line disproves it:

    generator -> [1, 2, 3]
    tuple     -> [1, 2, 3]
    return type: list

This is species two: every token it cites (`insertion_sort`, `merge`,
`merge_sort`, `TypeError`) is real and on a changed line, so `grounded()` passes
it while the claim is fabricated. Same shape as the 24 Aug `heap.js` `RangeError`
case — a confident prediction of an exception the language will not raise.

**Both remaining false alarms are behaviour-preserving refactors**, and both
checkpoints fail `py-annotate-only` for *different* invented reasons. Counting
the three from `sft-ml8-grounded`, that is four independent reproductions in one
day of the same failure: **this system invents defects in code that provably
does not change behaviour.** It is the clearest and most repeatable finding the
benchmark has produced, and unlike the detection numbers it does not depend on
SZZ labels, a teacher model, or a threshold.

### Context injection breaks this commit pair in BOTH directions (25 Aug)

The TUI reviews a revision through `analyze_commit(..., with_context=True)`,
which sends `git show -U50` plus the post-commit body of every changed file.
The benchmark sends the bare diff. On the two `pystruct` commits, that single
difference flips both verdicts — same model, same commit, same sample count:

    ORACLE_INFERENCE_SAMPLES=1 python - <<'PY'
    from llm_explainer.client import OracleClient
    cl = OracleClient(backend="ollama", ollama_host="http://localhost:8111")
    for ctx in (True, False):
        print(ctx, cl.analyze_commit("~/Documents/TestJIT/pystruct",
                                     "370806c", with_context=ctx).model_dump())
    PY

| commit | label | without context | with context (the TUI path) |
|---|---|---|---|
| `370806c` drop pop guard | buggy | 1 finding, right locus — **correct** | 0 findings — **miss** |
| `9745800` add annotations | clean | 0 findings — **correct** | 1 finding — **false alarm** |

Without context the model scores 2/2 on this pair. With context it scores 0/2.
It is not that context makes the model quieter or noisier: it **suppresses a
true finding on the buggy commit and invents a false one on the clean commit**,
which is the worst possible pair of errors and rules out a simple
threshold/verbosity explanation.

This is the second reproduction of the 24 Aug result that context injection
suppressed findings on `data/go_race_case.diff`, and the first where the
opposite error is visible in the same session. **The `with_context=True` default
in `analyze_commit` (`client.py:290`) is what the TUI ships**, so the
interactive tool is running the configuration that scores worst here.

Caveat, and it matters: this is **two commits in one small repo**, chosen
because they failed. It is enough to justify measuring the context path
properly — the `--context` flag added 24 Aug now has a reason to be run across
a real slice — and not enough to conclude that context always hurts. The clean
half of the benchmark is the natural place to measure it, since `bench/basic`
has no repo and therefore no context path today.

**Consequence for the benchmark.** `bench/basic_bench.py` feeds bare diffs, so
every number it reports is the *without-context* configuration. `py-pop-guard`
scoring correct there while the same commit misses in the TUI is not a
contradiction; it is the two paths disagreeing. Any claim about what a user
experiences must say which path it measured.

### A summary-factuality prompt rule is a null, and slightly negative (25 Aug)

`oracle-merged` gets the *verdict* right on `pystruct` 9745800 (clean, zero
findings) while its summary says the commit "removes the stable flag from the
docstring". The word `stable` appears 0 times before the commit and 1 time
after — it was added. The scorer cannot see this: for a clean case
`grade()` computes `false_alarm = flagged and not buggy`, and with no findings
`flagged` is False, so the case scores **correct** and the summary is never
read.

The system prompt has hard rules for findings ("Never invent a finding") and
none for the summary, so appending one looked like the cheap fix. It is not.
Appending to `SYSTEM_PROMPT`:

    - The summary is held to the same standard as a finding: every claim in it
      must be visible in the diff. Do not describe an added line as removed, or
      a removed line as added.

| case | baseline | with the rule |
|---|---|---|
| `go-accum-reset` | correct | **miss** |
| `py-annotate-only` | false alarm | false alarm |
| `rs-rename-local` | false alarm | false alarm |
| `c-array-bound` | correct | correct |
| `js-extract-helper` | correct | correct |
| `py-pop-guard` | correct | correct |

It fixed no inverted summary and cost a case: `go-accum-reset` was rewritten to
"replaces a redundant local total variable with a global zero initialization,
preserving existing logic" — wrong, and now silent. **Do not add summary rules
to the prompt.** The model was fine-tuned on the exact current prompt, so
appending to it is a train/test mismatch that is paid for and returns nothing.
Third independent loss for prompt rules in this repo, after 17 Aug (detection)
and context injection (twice).

**What this leaves.** Four "right verdict, wrong prose" cases are now on record
in one session — `go-accum-reset` (inverted), `py-pop-guard` (wrong mechanism),
real `370806c` (says the change introduces the `IndexError` it removes), real
`9745800` (says an added line was removed). 41/46 is therefore a
**verdict-and-locus number, not an explanation-correctness number**, and the
project's stated goal is about the explanation. The hand-grade is the only
instrument that measures the gap; nothing automated in this repo can see an
inverted claim, and two attempts today to build a matcher that could
(`identified()`, `identifiers()`) produced confidently wrong scores before the
control caught them.

### The hand-grade (25 Aug): 31/46, not 41/46

Ran the hand-grade next-session.md called for: read `pre`/`post` source for all
46 cases against `data/basic_bench_oracle46.jsonl`'s `predicted.summary` and
`predicted.findings[].explanation`, and where the causal claim wasn't obvious
from source alone, actually executed pre and post (gcc+ASan, go, rustc, java,
node, deno, ruby, php, python — the same runtimes `bench/basic_bench.py` uses)
to confirm what really happens. No automated scorer change; this is a manual
read against ground truth, spot-checked afterward against two of the flagged
cases (`c-int-division`, `go-accum-reset`) by re-running pre/post directly.

| | count |
|---|---|
| locus + mechanism both correct | **31/46 (67%)** |
| locus correct, mechanism wrong or inverted | 10/46 (22%) |
| locus wrong outright (already known: `go-nil-map`, `java-concurrent-modify`, `js-reverse-index`, `py-annotate-only`, `rs-rename-local`) | 5/46 (11%) |

The 10 mechanism failures, claimed vs. verified:

| case | model claimed | actually happens |
|---|---|---|
| `c-int-division` | fraction lost "during addition" of the values | inputs are exact ints (no fraction to lose yet); truncation is at the division step (`s/n` as int/int) — confirmed: prints `2.00`, correct is `2.50` |
| `c-strcpy-bound` | `strcpy` "writes up to sizeof(dst) bytes", truncating | `strcpy` has no bound awareness and writes all 12 bytes into an 8-byte buffer — ASan confirms a real stack-buffer-overflow WRITE of size 12, not a truncation |
| `go-accum-reset` | shadowed `total := 0` resets to zero every iteration | opposite: `total` moved *out* of the loop, so it stops resetting per row and accumulates across rows — confirmed pre `[3 7 5]`, post `[3 10 15]` |
| `php-concat-operator` | `+` on non-numeric strings does numeric coercion (`"hi123"`-style) | PHP 8.5 throws a fatal `TypeError: Unsupported operand types: string + string` — confirmed |
| `py-dict-mutate` | deleted keys are silently skipped, leaving stray entries | raises `RuntimeError: dictionary changed size during iteration` — a crash, not a silent miss |
| `rb-string-mutate` | the appended `"!"` is lost | opposite: removing `.dup` means the mutation leaks onto the caller's string via aliasing — confirmed pre prints `hi`, post prints `hi!` |
| `rs-int-division` | commit "replaces integer division with floating-point division" | exactly backwards: pre was float division (`1.50`, correct), post is integer division then cast (`1.00`, wrong) |
| `rs-overflow` | value "silently wraps around" instead of panicking | under this benchmark's own flags (debug, no `-O`), literal operands make `rustc` reject it at **compile time** — neither wraps nor panics at runtime |
| `ts-reduce-empty` | empty-array case "returns undefined" | throws `TypeError: Reduce of empty array with no initial value` |
| `py-pop-guard` | pop "silently succeeds" | raises `AttributeError: 'NoneType' object has no attribute 'next'` (already known, listed above) |

Borderline calls, left as passing, flagged rather than silently resolved:
`java-array-bound` hedges with an impossible `NullPointerException` alternative
for a primitive `int[]` alongside the correct `ArrayIndexOutOfBoundsException`;
`js-sort-numeric` says the array is "left unsorted" when it is sorted, just
lexicographically; `py-mutable-default` has garbled phrasing but the core claim
(same list object reused across calls) is right. Also outside the count because
no finding fired (correctly scored not-hallucinated): `js-extract-helper`'s
*summary* wrongly claims `report` was renamed to `sum` — `report` is preserved
intact and `sum` is a separately extracted helper.

**Reading it:** two of ten are repeats of cases already flagged by hand before
this pass (`go-accum-reset`, `py-pop-guard`); eight are new. Four of the ten are
a *specific* pattern — inverted direction of effect (`c-int-division`,
`go-accum-reset`, `rb-string-mutate`, `rs-int-division`) — the model gets the
right line and the right general category (division/reset/mutation) but
describes the change backwards, which reads as pattern-matching to a familiar
bug trope near the right token rather than tracing actual runtime semantics.
That is a third species of failure alongside the two in finding 9 below: not
"cites nothing" (species 1, grounding catches it) and not "cites real tokens,
states an unrelated falsehood" (species 2), but *cites the right tokens, states
the right category, gets the direction backwards*. Grounding cannot catch it
because the tokens are real; the automated locus scorer cannot catch it because
the location is right. Only execution catches it.

### The trace-through prompt addendum: tested, lost (25 Aug)

Hypothesis: the inverted-direction failures happen because the model pattern-
matches to a familiar bug trope near the right token instead of tracing actual
before/after behaviour, so an explicit instruction to trace a concrete example
through old and new code before naming a direction might fix them — untested
territory, distinct from the summary-factuality rule that already failed
(that one targeted diff-rendering wording, this one targets causal reasoning).

Appended as a monkeypatched sixth `Method` step (nothing in the repo edited;
`schema.SYSTEM_PROMPT` patched in-process for this run only), then reran all 46
cases through `oracle-merged`, greedy, same as every other basic-bench number:

    6. Before finalizing any claim about direction - a value increasing,
    decreasing, being reset, reused, truncated, skipped, or reversed - trace
    one concrete example through the changed lines in the OLD code and the NEW
    code and compare the two results. State the claim to match that trace, not
    the closest-sounding familiar bug name. If the trace shows the new code
    does more of something, earlier, or that the OLD code was the one with the
    problem, say so even if it is the less common direction for that bug
    category.

**It fixed none of the ten mechanism failures and cost two more cases.**

| locus-level (automated scorer) | baseline | +addendum |
|---|---|---|
| verdict + locus correct | 41/46 (89%) | 40/46 (87%) |
| false alarms | 2 | 3 |

Case-by-case against the 10 known mechanism failures: 6 came back **byte-
identical or unchanged in substance** (`rb-string-mutate`, `rs-int-division`,
`php-concat-operator`, `py-dict-mutate`, `rs-overflow`, `ts-reduce-empty`,
`py-pop-guard` — still describing the wrong direction or the wrong runtime
outcome). Two got **worse**: `c-int-division` replaced one wrong claim with a
fabricated one — "the sum overflows before being cast to double" and "a
division by zero when casting" — neither of which happens (no overflow, no
division by zero, verified); `go-accum-reset` stopped flagging the bug
entirely, concluding "preserving existing logic, no new runtime defects
introduced" — a hallucinated-direction finding regressed into a miss.

At the locus level, two long-standing misses got fixed
(`js-reverse-index`, `rs-rename-local`) but two **new** false alarms appeared
on refactor-only clean cases (`go-extract-helper`, `py-comprehension`) — the
addendum's extra scrutiny made the model *more* willing to invent a defect in
behaviour-preserving code, the opposite of what "no hallucination" needs.
Net: -1 locus, +1 false alarm, and zero mechanism fixes.

**Prompting is not the lever for mechanism, any more than training was for
detection.** This is the fourth prompt-rule attempt in this project to fail
(after 17 Aug detection, 25 Aug summary-factuality, and this one), each
targeting a different failure and each disproved by rerunning the actual
benchmark rather than trusting the intuition behind the rule. **Do not add
this addendum to `SYSTEM_PROMPT`.**

### The second model: `openai/gpt-oss-120b` on the same 46 cases (25 Aug)

Closes the "second model" gap in the paper-status section below. Same 46
cases, same unmodified `SYSTEM_PROMPT`, same schema, greedy (temperature 0),
via Groq — this is the project's own distillation teacher, not a checkpoint of
this project's model, so it is a genuine test of whether the failures found on
Qwen2.5-Coder-3B are properties of *this class of system* or of *this specific
3B model*.

    .venv/bin/python bench/second_model_bench.py --out data/basic_bench_gptoss120b.jsonl

| | oracle-merged (3B, fine-tuned) | gpt-oss-120b (teacher, zero-shot) |
|---|---|---|
| locus correct | 41/46 (89%) | **45/46 (98%)** |
| false alarms | 2 | **1** |
| locus **+ mechanism** correct (hand-graded) | 31/46 (67%) | **43/46 (93%)** |
| locus-mechanism gap | 22 points | **5 points** |

Hand-graded the same way as the first pass — pre/post source read, and
execution used to settle every claim not obvious from source alone. Checked
against the 10 cases where oracle-merged's mechanism was wrong or inverted:

| case | gpt-oss-120b |
|---|---|
| `c-int-division` | fixed |
| `c-strcpy-bound` | fixed |
| `go-accum-reset` | fixed |
| `php-concat-operator` | partially fixed — hedges toward the true outcome ("or a type error") but the primary claim is still wrong, and misattributes the cause to `strict_types` (the file declares none; PHP 8.5 throws the `TypeError` regardless) |
| `py-dict-mutate` | fixed |
| `rb-string-mutate` | fixed |
| `rs-int-division` | fixed |
| `rs-overflow` | **not fixed — same failure as oracle-merged.** Both models describe generic runtime overflow behaviour (panic/wrap); the verified truth is that `post.rs` fails to *compile* under the benchmark's own flags (`rustc`, no `-O`): `error: this arithmetic operation will overflow`, `#[deny(arithmetic_overflow)]`, because the operands are literals rustc const-folds before runtime. Neither a 3B fine-tune nor a 120B general model anticipates this. |
| `ts-reduce-empty` | fixed |
| `py-pop-guard` | fixed |

8 of 10 fully fixed, 1 partial, 1 identically unfixed. The one remaining false
alarm (`java-extract-method`) is also qualitatively different from
oracle-merged's refactor false alarms: it flags a *hypothetical*
`NullPointerException` for an untested null-array input rather than
misdescribing the executed path — still a false alarm by this benchmark's
strict rule (any finding on a clean case counts), but a different species of
mistake than inventing a defect in code that was actually run.

**Reading it:**

1. **The inverted-direction mechanism failure is largely scale/capability-
   dependent, not a universal property of LLM-based JIT review.** Nine of the
   ten cases that beat a fine-tuned 3B model are handled correctly by a 120B
   general model with no fine-tuning and no task-specific training at all. That
   is evidence *against* reading the hand-grade as "this is what these systems
   always do" and evidence *for* reading it as "this is what a 3B distillation
   currently does."
2. **`rs-overflow` is the interesting exception.** Both models fail it the same
   way, for the same reason: this is a rustc-specific compile-time subtlety
   (literal-operand const-folding) that neither model's training data made
   salient. Not every mechanism gap closes with scale — this one looks like it
   needs the specific fact, not more general capability.
3. **This reframes what "training is not the lever" means.** Five retraining
   attempts on this project's own data didn't move the number — but the
   teacher itself clears the mechanism bar the student misses, on the exact
   same cases. That is evidence the ceiling is in the distillation, not in a 3B
   parameter count; it does not mean a better-targeted training signal
   couldn't close the gap, only that the five approaches tried so far did not
   find it.
4. **The instrument, not just the model, is what this result validates.** The
   hand-grade methodology cleanly separated a 22-point locus/mechanism gap on
   one model from a 5-point gap on another, using the same 46 cases and the
   same procedure. A locus-only benchmark would have reported 89% vs 98% and
   missed that the *real* gap (67% vs 93%) is more than four times wider.

### The refactor false alarm is a rendering artifact, but word-diff is not the fix (25 Aug)

**The mechanism.** A unified diff renders an edited line as a removal plus an
addition. On `pystruct` 9745800 the docstring is expanded in place:

    -"""Comparison sorts."""
    +"""Comparison sorts.
    +
    +Both sorts are stable and return a new list; the input is never mutated.
    +"""

A line containing the docstring genuinely *was* removed, so when the model
reported that a docstring was removed it was describing the representation it
was handed, not inventing one. `--word-diff=plain` marks the edit inside the
line and removes the ambiguity:

    """Comparison [-sorts."""-]{+sorts.+}
    {+Both sorts are stable and return a new list; the input is never mutated.+}

Asked again with that rendering, the model returns zero findings and an
accurate summary. **The false alarm is a rendering artifact, not a reasoning
failure** — which is a far more tractable problem than "the model hallucinates
on refactors", and it is the same lever as the 0.088 rendering-variance result.
Note that the three perturbations in `variance.py` (`no_index`, `rehash`,
`bare_hunk`) are all metadata-only; this is the first one measured that changes
how the *code* is represented.

**The fix does not survive contact with the benchmark.**

    ORACLE_INFERENCE_SAMPLES=1 python bench/basic_bench.py --word-diff \
        --backend ollama --model-name oracle-merged --host http://localhost:8111 \
        --out data/basic_bench_oracle46_word.jsonl

| | unified | word-diff |
|---|---|---|
| verdict correct | 40/46 (87%) | 37/46 (80%) |
| **fully correct (locus)** | **41/46 (89%)** | 36/46 (78%) |
| **false alarms** | **2** | 4 |

**9 regressions against 4 improvements.**

| case | unified | word-diff |
|---|---|---|
| `py-annotate-only` | false alarm | **correct** |
| `rs-rename-local` | false alarm | **correct** |
| `go-nil-map` | miss | **correct** |
| `java-concurrent-modify` | miss | **correct** |
| `c-array-bound` | correct | **miss** |
| `rs-index-bound` | correct | **miss** |
| `php-concat-operator` | correct | **miss** |
| `rb-int-division` | correct | **miss** |
| `rb-range-bound` | correct | **unconfirmed** |
| `c-const` | correct | **false alarm** |
| `go-extract-helper` | correct | **false alarm** |
| `php-extract-helper` | correct | **false alarm** |
| `py-comprehension` | correct | **false alarm** |

Both in-place-edit false alarms are fixed, exactly as the mechanism predicts.
But three clean cases that were fine under unified acquire invented defects, and
boundary detection degrades badly — `c-array-bound` and `rs-index-bound`, the
plainest off-by-one cases in the set, both become misses.

The cause is train/test mismatch: the model was fine-tuned on unified diffs and
has never seen `[-gone-]{+added+}`, so it reads operators and boundaries less
reliably in it. **Do not switch the inference rendering.**

**What this points at instead.** The tractable experiment is to train on the
rendering you want the model to read: regenerate the SFT corpus with word-diffs
and retrain. Unlike the 25 Aug retrain, that has a mechanism behind it rather
than a hope — a measured artifact, a rendering that removes it, and a measured
reason the swap fails at inference only. `data/sft_ml8_base.jsonl` and the
corpus builders are in place. It is also the one remaining idea today that is
not already disproved: retraining on the same data lost, prompt rules lost
three times, context injection lost three times, and DPO is a null.

### Mechanism training: the direction failures move, precision pays for it (26 Aug)

The sixth approach, and the first one that is neither a prompt rule nor a
repeat of the same corpus. Trained on hand-written examples of the exact bug
families the 25 Aug hand-grade proved the model describes backwards.

**The corpus is a small lever, and it is worth naming the dose.**
`data/sft_mechanism_v1.jsonl` is 1748 records / 1692 unique:

| source | records |
|---|---|
| the existing `sft_base` / `sft_ml8` corpora | ~1665 |
| `bench/mechanism_pilot` cases, upsampled 3x | 81 (27 unique, 4.6%) |

So the intervention is 27 hand-written cases seen six times each (3x upsample
x 2 epochs) on top of the same base corpus that produced `sft-ml8-grounded` —
the retrain that came out *worse*. All 27 are `buggy: true`; nothing in the
addition teaches the clean direction.

    # 14h on the 6GB card, 224 steps, 2 epochs, exit 0
    .venv/bin/python -m fine_tuning.train_sft \
        --dataset data/sft_mechanism_v1.jsonl --output-dir artifacts/sft-mechanism-v1
    # merged, served, then:
    ORACLE_INFERENCE_SAMPLES=1 .venv/bin/python bench/basic_bench.py \
        --backend ollama --model-name mechanism-v1-merged \
        --host http://localhost:8111 --out data/basic_bench_mechanism_v1.jsonl

Both runs re-scored with the current scorer (`--score`) so they are comparable:

| | `oracle-merged` | `mechanism-v1-merged` |
|---|---|---|
| fully correct (locus) | **41/46 (89%)** | 39/46 (85%) |
| buggy cases located | 30/33 | **33/33 (100%)** |
| clean cases passed | **11/13** | 6/13 |
| false alarms | **2** | 7 |

**Every buggy case is now located.** The three long-standing locus misses —
`go-nil-map`, `java-concurrent-modify`, `js-reverse-index` — are all fixed, and
nothing regressed into a miss. That is the first time any checkpoint has found
all 33.

**Five clean cases regressed into false alarms:** `c-const`,
`go-extract-helper`, `java-extract-method`, `php-extract-helper`,
`py-extract-helper`.

#### Mechanism, hand-graded against the 10 known failures

Same method as 25 Aug — read the source, and execute where the claim is not
obvious. Verified this pass by running `deno`, `php`, `gcc`, `rustc` and `go`
directly on the case files.

| case | new claim | verified | verdict |
|---|---|---|---|
| `go-accum-reset` | `total` declared before the outer loop, never reset, so rowSums returns cumulative sums | pre `[3 7 5]`, post `[3 10 15]` | **fixed** |
| `rb-string-mutate` | `t = s` mutates the caller's string; callers see the modification | matches | **fixed** |
| `rs-int-division` | integer division truncates, 2.5 becomes 2 | matches | **fixed** |
| `py-dict-mutate` | `RuntimeError` because dict size changes during iteration | matches | **fixed** |
| `py-pop-guard` | `self.head.next` without checking `self.head` → `AttributeError` | matches | **fixed** |
| `c-strcpy-bound` | overwrites memory beyond the buffer → overflow | core claim right, but adds a false subclaim ("strcpy does not append a null terminator" — it does) | borderline |
| `ts-reduce-empty` | throws `RangeError`, "attempts to read xs[0]" | throws `TypeError: Reduce of empty array with no initial value` | partial — right that it throws (baseline said "returns undefined"), wrong exception |
| `c-int-division` | "truncation during accumulation", `average(1,2)` returns 0 | truncation is at `s / n`, not the accumulation; verified output is `1.00`, not 0 | **still wrong** |
| `php-concat-operator` | "invalid PHP syntax, parse error" | runtime `Fatal error: Uncaught TypeError: Unsupported operand types: string + string` | **still wrong** (new flavour) |
| `rs-overflow` | "silently wraps" | `rustc` rejects at compile time: `error: this arithmetic operation will overflow`, `#[deny(arithmetic_overflow)]` | **still wrong** (identical to baseline and to gpt-oss-120b) |

**5 fixed, 1 borderline, 1 partial, 3 unfixed.** More pointedly, of the four
cases the hand-grade singled out as *inverted direction* — `c-int-division`,
`go-accum-reset`, `rb-string-mutate`, `rs-int-division` — **three of four are
fixed.** That is the pattern the 27 cases were written to target, and it is the
first intervention in this project that moved it at all. Prompting moved none.

#### The false alarms are one fabrication, not five

Six of the seven false alarms make the same false claim: **that a call or a
statement was removed, when it was edited in place.**

| case | fabricated claim | verified |
|---|---|---|
| `go-extract-helper` | "the call to sum(...) is removed, so printing never happens" | `go run post.go` prints `6` |
| `py-extract-helper` | "Removing the print call ... no longer printed" | `python3 post.py` prints `6` |
| `java-extract-method` | "main no longer calls System.out.println(sum(...))" | it does |
| `php-extract-helper` | "removes the original array argument" | it does not |
| `py-annotate-only` | "removes the original non-generic implementations" | they are preserved |
| `rs-rename-local` | "`acc` is declared but never used" | it is returned |

The rendering is why. `bench/basic_bench.py`'s unified diff for
`go-extract-helper` reads:

    -func main() {
    -	xs := []int{1, 2, 3}
     	s := 0
     	...
    -	fmt.Println(s)
    +	return s
    +}
    +
    +func main() {
    +	fmt.Println(sum([]int{1, 2, 3}))
     }

`-\tfmt.Println(s)` appears; the `+` line that restores it is eight lines
below, and the model never reconciles the two. **This is not a new failure
mode — it is the remove+add rendering artifact already documented above,
firing five times more often.** The mechanism training did not teach the model
to fabricate; it made the model more assertive, and the assertiveness landed
on a defect the input representation was already inviting.

That also explains why the gains and the losses are the same event. All 27
training cases are `buggy: true`, so the only thing the corpus can shift is the
model's willingness to report. Recall went to 33/33 and precision fell to 6/13.
A model that simply always answered "buggy" would score 33/46 with 13 false
alarms; `mechanism-v1` is at 39/46 with 7, so it has not collapsed into that,
but it has moved measurably toward it.

**Reading it:**

1. **The mechanism lever works and the precision lever is separate.** Three of
   four inverted-direction failures fixed by 27 examples is the first real
   movement on explanation correctness this project has measured. It cost
   precision on refactors, but the precision loss has a *different, already
   diagnosed cause* — the diff rendering — rather than being the flip side of
   the same dial.
2. **The two live experiments now compose.** Word-diff rendering removes the
   remove+add ambiguity and fixes exactly these false alarms, but swapping it
   at inference loses because the model was trained on unified diffs. The
   experiment already queued — regenerate the SFT corpus as word-diffs and
   train on it — is the fix for the six fabrications above. Combining it with
   the mechanism cases is the obvious next run.
3. **The corpus needs the clean direction.** 27 buggy-only examples bought
   recall at the cost of precision, which is what training on one label
   predicts. Cases where the same construct appears and is *not* a defect —
   and cases where the commit *fixes* one of these bugs — are the missing half.
4. **A full 46-case mechanism hand-grade has not been run on this checkpoint.**
   Only the 10 known failures were re-graded. The comparable 67% figure for
   `oracle-merged` cannot be restated for `mechanism-v1` until the rest are
   read, and the locus number (39/46) is a floor, exactly as it was before.

#### The benchmark cannot express a bug-fix commit

Trying to build the missing clean-direction control surfaced a limitation
worth recording. `bench/basic_bench.py:114`:

    differs = (rc_pre, out_pre) != (rc_post, out_post)
    ok = differs if c["buggy"] else not differs

A clean case is *defined* as one where pre and post produce identical output.
A commit that fixes a bug changes behaviour, so it cannot be labelled clean —
the verifier would call it `BAD LABEL`. **The harness conflates
"behaviour-preserving" with "introduces no defect".** That is correct for
refactors, which is all 13 clean cases are today, and wrong for fixes. Any
control that asks "does the model over-report on a commit that removes a
defect" needs a third label, not a `buggy` flag.

### The locus/mechanism split shows up on real commits too (26 Aug)

`mechanism-v1-merged` served on the box, TUI run against a real repository
through the tunnel. **Unquantified — no counts, no execution checks, an
impression from reading output.** Recorded for what was observed, not how
strongly.

Reading the findings unprompted, the split was: some correct; some **name the
right thing but the explanation misses**; some wrong. That is the three-way
taxonomy the 25 Aug hand-grade named, arrived at independently, by eye, on
real code.

This is the third reproduction of that taxonomy:

| # | where | gap between locus and mechanism |
|---|---|---|
| 1 | hand-grade of the 46 (`oracle-merged`) | 89% -> 67%, 22 points |
| 2 | `gpt-oss-120b` on the same 46 | 98% -> 93%, 5 points |
| 3 | this TUI session, real commits | observed, not measured |

**Why the third one matters.** The strongest objection to the whole
explanation result is that the 46 cases are hand-written toy programs, so the
locus/mechanism gap could be an artifact of synthetic code. It is not: the same
split appears on real commits the model has never seen, and it was noticed
without anyone looking for it.

**What it is not.** A number. "Some / some / some" is consistent with anything
from 60% to 85% and cannot go in a paper. Turning it into evidence needs the
repo and revisions recorded, each finding graded locus / mechanism / wrong,
and every mechanism claim checked by running the code — the same discipline
the 46 got. That is also the cheapest available fix for the two weakest points
in this evaluation, n=46 and all-synthetic, since the repos are already cloned
in `data/repos/`. Use only the five held-out projects (`axios`, `clap`, `gin`,
`fastapi`, `spring-boot`); the `apache__*` repos are leaked into the gate's
training set.
