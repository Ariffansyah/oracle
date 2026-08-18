# Datasets

Every corpus ORACLE uses, where it came from, and — importantly — which ones are
sound to report in the paper and which are not.

Status as of 2026-08-14.

---

## 1. Source dataset

### ApacheJIT

**Keshavarz & Nagappan, "ApacheJIT: A Large Dataset for Just-In-Time Defect
Prediction", MSR 2022.**

- ~106k commits from **15 Apache projects**, labelled with SZZ.
- Downloaded by `corpus/apachejit.py` from the authors' repository
  (`hosseinkshvrz/apachejit`).
- Projects present in our sample: activemq, camel, cassandra, flink, groovy,
  hadoop, hadoop-hdfs, hadoop-mapreduce, hbase, hive, ignite, kafka, spark,
  zeppelin, zookeeper.

`corpus/apachejit.py` documents the feature reconciliation required to use the
published metrics alongside metrics mined from git — entropy normalisation,
the absent `lt` column, per-file averaging of `ndev`/`nuc`. Training on one
definition while scoring on another produces confident nonsense, so this is not
optional.

**Language composition — the central limitation.** Across our labelled sample:

| extension | files |
|---|---|
| `.java` | 2768 |
| `.groovy` | 92 |
| `.xml` | 70 |
| **`.ts` / `.tsx` / `.js` / `.jsx`** | **2** |

ApacheJIT is Java by construction. Any claim about other languages requires a
different dataset.

### Derived: `data/apachejit_commits.jsonl` — 7989 commits, 24 MB

ApacheJIT rows joined with the actual commit **diffs**, fetched by
`corpus/fetch.py` from `github.com/{project}/commit/{sha}.diff`. The published
ApacheJIT export is metrics-only; ORACLE trains on code, so the diffs must be
fetched separately.

---

## 2. Labelled corpora (teacher-annotated)

SZZ gives a binary `buggy` flag. It does not give an *explanation*, and ORACLE's
whole premise is that the explanation is the output that matters. Explanations
therefore come from a teacher model.

### `data/labelled.jsonl` — 1959 commits — ⚠️ **CONTAMINATED, DO NOT REPORT**

- Teacher: `deepseek/deepseek-v4-flash`
- Split: `labelled_train.jsonl` (1759) / `labelled_heldout.jsonl` (200)
- Derived SFT set: `oracle_sft.jsonl` (1759)

**Why it is unusable.** The labelling prompt told the teacher the answer on every
SZZ-buggy commit:

> "Ground truth: a later commit in this repository fixed a defect in the lines
> this change introduced. Identify what is wrong here and report it."

The teacher complied on 98.2% of buggy commits. A second filter in `verify()`
then discarded any commit where the teacher disagreed with SZZ, so a false
negative could not survive to be counted.

Result: teacher recall **1.00**, **zero false negatives across 844 training and
92 held-out commits**. The frequently-quoted "ceiling of F1 0.87" is an artifact
of the instruction, not a measurement.

Both causes are fixed in `corpus/label.py` (`--hint` is now opt-in,
`verify(hinted=False)` keeps disagreements, every record carries a `hinted`
stamp), but **this corpus was generated before the fix**. Checkpoints trained on
it — `sft-adapter/checkpoint-110` and `checkpoint-220` — inherit the problem.

### `data/heldout_unhinted.jsonl` — 200 commits — ✅ sound

- Teacher: `groq/openai/gpt-oss-120b` (free tier)
- `hinted: false` on every record
- Same 200 commits as `labelled_heldout.jsonl`, so hinted and unhinted are
  directly comparable.

**The result that reframes the project:**

| teacher | P | R | F1 | acc | fn |
|---|---|---|---|---|---|
| hinted, deepseek-v4-flash | 0.77 | **1.00** | 0.87 | 0.86 | **0** |
| unhinted, gpt-oss-120b | 0.56 | 0.43 | **0.49** | 0.58 | 52 |
| always-buggy baseline | 0.46 | 1.00 | **0.63** | 0.46 | 0 |

A 120B model reading diffs unaided scores **F1 0.49 — below the majority-class
baseline of 0.63**. The honest reading is that **SZZ-buggy is largely not
inferable from the diff alone**: a commit is labelled buggy because a later
commit touched those lines, and that fact is frequently invisible in the change
itself.

This bounds every distillation approach on this dataset, and is why the roadmap
pivots toward label sources where the defect is genuinely present.

### `data/labelled_raw.jsonl` — 1982 raw teacher responses

Every raw response is written before verification, so a schema change means
re-parsing rather than re-paying. 23 records were dropped by `verify()`; 17 of
those were SZZ-buggy commits where even the *hinted* teacher found nothing.

---

## 3. Evaluation sets

### `data/detect_eval.jsonl` — 1000 commits, balanced 500/500 — ✅ sound, free

Sampled from the 6030 ApacheJIT commits the teacher never touched. Carries
`buggy` from SZZ and **no teacher annotation**.

This is the key economy: detection metrics need only `diff` + `buggy`, and SZZ
labels are free. A teacher is required solely for `category_match`. Balanced
50/50 because separation (TPR − FPR) is base-rate independent and balance
maximises statistical power.

Built after the 200-commit held-out set proved underpowered — the paired
bootstrap CI on tuned-vs-stock was `[-9.7, +27.4]`, spanning zero. Power analysis
put the requirement at n ≈ 860 to move the CI off zero, n ≈ 1685 for 80% power.

### `data/cvefixes_eval.jsonl` — 1000 records / 500 commit pairs — ✅ sound, free, human-written

Built by `corpus/cvefixes.py` from CVEfixes v1.0.8 (`data/cvefixes/CVEfixes.db`,
52 GB, CC BY 4.0). No teacher is involved: the **CVE description is the
explanation target**, written by a person.

CVEfixes stores the commit that *fixed* a CVE, not the one that introduced it,
and recovering the introducing commit needs SZZ over a full clone of every
repository. Instead each fix commit is emitted twice:

| record | diff | `buggy` | `analysis` |
|---|---|---|---|
| `{hash}:intro` | the fix, reversed | `true` | CVE description, category `security` |
| `{hash}:fix` | the fix, as committed | `false` | empty `findings` |

The positive and the negative differ **only in direction** — same repository,
same files, same lines, same total length (mean 1887 chars on both sides).

### ⚠️ The construction leaks through line composition

Equal *length* is not equal *composition*, and the difference is a trivial
classifier. A fix typically adds a guard, so it carries more `+` lines than `-`
lines; its reverse carries exactly the mirror image:

```
mean(plus-minus lines):  reversed -9.71    fix +9.72
```

Ten hand-written counting features — added lines, removed lines, their
difference and ratio, the same in characters — score **AUC 0.934, PR-AUC 0.935**
on the held-out 500 pairs, with no model and no embedding. `wc` solves this
benchmark.

Consequences, all of which must be stated wherever a number from this corpus is
reported:

- **Detection results on this corpus are meaningless without the counting
  baseline beside them.** It is the always-buggy of this dataset. Reproduce with
  `python count_control.py` (reads `data/cve_gate.jsonl`).
- The GraphCodeBERT + LightGBM gate scores AUC 0.792 here — *below* the counting
  baseline, so it is recovering a noisy version of the same cue rather than
  reading code.
- Both LLMs scored at chance (separation −4.2pp and −1.8pp). They did not
  exploit the cue at all, which sharpens the negative result about them and
  weakens any claim that the task measures defect understanding.

The proper repair is real vulnerability-introducing commits — SZZ over the fix,
against a full clone of each repository — rather than reversed fixes. Matching
pairs on `+`/`-` balance is the cheap alternative and costs most of the corpus.
Until one of those is done, treat this corpus as an **explanation** benchmark
with human ground truth, not as a detection benchmark.

Two construction details that are easy to get wrong, both asserted in
`python -m corpus.cvefixes --selftest`:

- **Line order.** Flipping `+`/`-` signs is semantically correct but inverts
  git's convention of printing a run of `-` before its `+`. That alone is a
  perfect classifier for "this one is reversed". Both directions are re-sorted
  into git's order; measured 0 order tells across all 1000 records. Note this
  closed one leak and missed a larger one — see the composition warning above.
- **The commit message is never used.** `subject` is the placeholder
  `(N files changed)`, as in `detect_eval.jsonl` — a fix message usually names
  the CVE.

Composition of the current 500 pairs: PHP 254, C 218, C++ 124, JavaScript 86,
Python 62, Ruby 58, Java 38, TypeScript 36, across 349 repositories (capped at
20 pairs per repository, or tensorflow and linux take over). This is the first
corpus here that is **not** Java, and the first with TypeScript in it at all.

Caveats for the paper:

- The introducing commit is **synthetic**. It never existed; a real
  vulnerability is rarely introduced by exactly reversing its fix.
- Records come in pairs, so bootstrap resampling and train/test splits must key
  on `pair`, never on the record. `evaluate.py --paired` does this.
- Every positive is category `security`, so `category_match` is degenerate here;
  score the taxonomy on ApacheJIT and the explanation text on CVEfixes.
- CVE text is written post-hoc by someone who knew the bug, and describes the
  vulnerability rather than always pointing at diff lines.
- The negative side's `summary` is the one templated string in the file. The CVE
  describes the defect, not its repair, so there is no human text for it. Treat
  `:fix` records as detection targets only.

### `data/eval_*.jsonl` — 200 rows each

Model outputs on `labelled_heldout.jsonl`: `eval_sft110`, `eval_sft220`,
`eval_stock`. Inputs to `evaluate.py --compare` and to
`build_dpo_data.py --from-eval`.

---

## 4. Training sets

| file | rows | contents |
|---|---|---|
| `oracle_sft.jsonl` | 1759 | conversational SFT — ⚠️ built from the contaminated corpus |
| `oracle_dpo.jsonl` | — | mock/templated preference pairs |
| `oracle_dpo_onpolicy.jsonl` | 49 | 33 on-policy false positives + 16 hard negatives |

`oracle_dpo_onpolicy.jsonl` is built from checkpoint-220's own errors, so the
rejected side is text the model really produces rather than a hallucination
written by hand. Hard negatives are capped at half the false-positive count so
that possibly-invented explanations cannot dominate.

---

## 5. Planned additions

Ordered by what each unblocks. None yet integrated.

### QT + OPENSTACK — comparability and two more languages

**Hoang et al., "DeepJIT: An End-to-End Deep Learning Framework for
Just-In-Time Defect Prediction", MSR 2019.**

C++ and Python. Used by DeepJIT, CC2Vec and JITLine, so it enables a comparison
table against published numbers. Use the authors' splits unchanged —
comparability is the entire point.

### CrossVul / BigVul — more vulnerability data if CVEfixes is not enough

- **Nikitopoulos et al., "CrossVul", FSE 2021** — 40+ languages
- **Fan et al., "BigVul", MSR 2020** — C/C++

CVEfixes is integrated (section 3); these are the fallbacks if 12k fix commits
prove too few, or if the reversed-fix construction needs a second dataset to
show it generalises.

### JIT-Defects4J / LApredict — the standard modern JIT benchmark

**Zeng et al., ISSTA 2021.** 21 Java projects; the dataset against which DeepJIT,
CC2Vec and JITLine are compared.

### ManySStuBs4J — external taxonomy validation

**Karampatsis & Sutton, MSR 2020.** 153k single-statement Java bugs with pattern
categories. Our 10-category taxonomy in `dataset_builder/schema.py` currently
rests on nothing but our own choice; this provides an external check.

---

## 6. Multi-language mining (infrastructure only)

`corpus/mine.py` derives SZZ labels from any git repository in any of 14
languages — find fix commits by message, take the lines they repaired,
`git blame` those lines in the fix's parent, mark the commits that last touched
them as buggy. Partial clones (`--filter=blob:none`) keep it to megabytes, and
no API is involved, so it is free.

Partial clones were the original bottleneck — `blob:none` forced lazy blob
fetches over the network and no run ever finished. Clones are now full,
`--single-branch`, `--no-checkout`, and mining is CPU-bound and free.

### `data/multilang_commits.jsonl` — 1,734 commits, 8 languages

The general sample: go 541, javascript 337, php 207, java 154, rust 135,
python 124, typescript 122, ruby 108. Teacher labelling into
`data/labelled_multilang.jsonl` is in progress.

### `data/guard_commits.jsonl` — 1,458 commits, 8 languages

Mined by `corpus/mine.py --guards` for one specific defect class: commits whose
later fix *adds* a missing check. 151,476 commits of history over 21
repositories yielded 21,239 fix commits, of which 1,839 (8.7%) add a guard.

By language: go 324, java 280, javascript 230, php 228, rust 175, python 79,
typescript 77, ruby 65. By guard class: nil-check 727, falsy-check 536,
empty-check 285, error-check 186, **zero-check 146**, bounds-check 47,
validation-raise 38.

Why it exists: the general sample produced only 7 guard-flavoured findings in
141: the student cannot learn to report an *absent* guard from targets that only
ever describe a changed line. See RESULTS, "Targeted mining for guard-adding
fixes", which also covers the SZZ change this required — a pure insertion
deletes nothing, so the standard deletion-blame returns the empty set for
exactly these commits.

Every record is `buggy: true` by construction, and carries `guard_kinds`,
`fix_commit` and `fix_subject` as provenance. None of those reach the teacher
prompt (`build_user_message` sends diff, subject and files only), so they are
eval material, not a label leak. Label it with `--no-balance` and
`--per-language 60`, which samples 480 commits evenly across the eight.

### `data/labelled_guards.jsonl` — the labelled slice, in progress

The 480-commit teacher pass over the above. Running as of 18 Aug 20:48 (see
RESULTS, "Guard-corpus labelling resumed"); `data/labelled_guards_raw.jsonl` is
the attempt log and reaches 480 when the phase is done. Merge with pass 1 before
building the SFT:

    cat data/labelled_multilang.jsonl data/labelled_guards.jsonl \
      > data/labelled_all.jsonl

Whether it did its job is one number — the guard-flavoured share of findings,
measured the same way on both corpora:

    .venv/bin/python guard_share.py data/labelled_multilang.jsonl \
      data/labelled_guards.jsonl

Pass 1 sits at 78 of 275 findings (28.4%); this corpus has to beat that.

---

## 7. Licensing

Checked 2026-08-15. Anything marked *unverified* must be confirmed before
submission — do not cite a licence from this table without re-checking it.

| dataset | licence | source | status |
|---|---|---|---|
| **CVEfixes v1.0.8** | **CC BY 4.0** | Zenodo `10.5281/zenodo.13118970` | ✅ verified |
| **BigVul** (`ZeoVan/MSR_20_Code_vulnerability_CSV_Dataset`) | **MIT** | GitHub API | ✅ verified |
| **ApacheJIT** (`hosseinkshvrz/apachejit`) | **none declared** | GitHub API | ⚠️ see below |
| **JIT-Defects4J** (`soarsmu/JIT-Defects4J`) | **none declared** | GitHub API | ⚠️ see below |
| CVEfixes collection code (`secureIT-project/CVEfixes`) | NOASSERTION | GitHub API | ⚠️ inspect repo |
| DeepJIT QT / OPENSTACK | unverified | — | ⚠️ to check |
| ManySStuBs4J | unverified | — | ⚠️ to check |

### "None declared" — what it means for us

Strictly, a repository with no `LICENSE` file is *all rights reserved*. In
practice these are research artifacts published alongside peer-reviewed papers
precisely so that others can build on them, and citing them is the accepted
norm across the JIT literature.

**ApacheJIT is the one that matters**, because it is our primary dataset. The
safe position is: cite the MSR 2022 paper, do not redistribute the data, and
point readers at the authors' repository to obtain it themselves. If we ever
release a derived corpus, ask the authors first.

### Upstream code provenance

CVEfixes and BigVul aggregate code from thousands of upstream repositories under
their own licences — GPL, Apache, MIT and others. The *dataset* licence governs
the collection, not the underlying code. This is standard for vulnerability
datasets and accepted for research use, but it belongs in threats to validity if
we quote or redistribute code snippets.

### Citations to include

- Keshavarz, H., Nagappan, M. "ApacheJIT: A Large Dataset for Just-In-Time
  Defect Prediction." MSR 2022.
- Bhandari, G., Naseer, A., Moonen, L. "CVEfixes: Automated Collection of
  Vulnerabilities and Their Fixes from Open-Source Software." PROMISE 2021.
  Dataset v1.0.8, Moonen, L. & Vidziunas, L., `10.5281/zenodo.13118970`.
- Fan, J., Li, Y., Wang, S., Nguyen, T. N. "A C/C++ Code Vulnerability Dataset
  with Code Changes and CVE Summaries." MSR 2020.
- Hoang, T., Dam, H. K., Kamei, Y., Lo, D., Ubayashi, N. "DeepJIT: An End-to-End
  Deep Learning Framework for Just-In-Time Defect Prediction." MSR 2019.
- Zeng, Z., Zhang, Y., Zhang, H., Zhang, L. "Deep Just-In-Time Defect
  Prediction: How Far Are We?" ISSTA 2021.
- Karampatsis, R.-M., Sutton, C. "How Often Do Single-Statement Bugs Surface in
  the Wild?" MSR 2020.

---

## Summary: what is safe to report

| corpus | status |
|---|---|
| ApacheJIT + fetched diffs | ✅ sound, published dataset |
| `detect_eval.jsonl` (1000, SZZ only) | ✅ sound, no teacher involved |
| `cvefixes_eval.jsonl` (1000, CVE text) | ✅ sound, human-written, synthetic positives |
| `heldout_unhinted.jsonl` (200) | ✅ sound |
| `labelled.jsonl` and everything derived | ⚠️ label leakage — not reportable |
| `sft-adapter/checkpoint-110` / `-220` | ⚠️ trained on the leaked corpus |
| `mined.jsonl` | empty |
