Continue ORACLE at ~/Documents/oracle. Read `docs/RESULTS.md` first (every
measurement plus the command that reproduces it), then `docs/ROADMAP.md`.

**First action this session:** nothing is running and the GPU box is free.
Read "Where this landed" — the retrain finished and is a regression, so the
obvious next move (ship it) is the wrong one.

# The project

Two-stage JIT defect prediction. Title settled: "Predict, Then Explain:
Just-In-Time Defect Prediction with Natural-Language Findings". Stage 1 is a
gate classifier that detects buggy commits; Stage 2 is a fine-tuned 3B LLM that
verifies and explains. Base model Qwen2.5-Coder-3B-Instruct, QLoRA SFT on
teacher-labelled data (gpt-oss-120b on Groq is the teacher, the 3B is the
student). Do NOT use "Explainable JIT" — taken by PyExplainer / JITLine.

**The user's stated goal (24 Aug), which supersedes the old framing:** get
basic algorithmic code (loops, functions, boundaries) in the 8 corpus
languages to **8/10 correct with no hallucination**. That is a narrower and
much more achievable target than beating a baseline on Apache Java, and
`bench/basic_bench.py` is the instrument for it.

# Where this landed

`sft-ml8-grounded` trained cleanly and is **worse than the checkpoint it was
meant to replace.** 154/154 steps in 9h27m, finished 25 Aug 10:10 WIB, loss
1.714 -> 0.418, token accuracy 0.597 -> 0.883, no divergence. The adapter is at
`artifacts/sft-ml8-grounded` on the box (239 MB, plus checkpoint-77 and -154).

All three models on the 44-case benchmark, greedy, one sample, fixed scorer:

| | base 3B | `oracle-merged` | `sft-ml8-grounded` |
|---|---|---|---|
| fully correct (locus) | 33/44 (75%) | **40/44 (91%)** | 38/44 (86%) |
| false alarms (proved) | 2 | **1** | 3 |

**`oracle-merged`, the older checkpoint, is the best model this project has.**
The retrain loses 2 cases and triples the false alarms. Do not ship it.

The one signal worth acting on: **all three of the retrain's false alarms are
refactor-only clean cases** — `js-extract-helper`, `js-rename-param`,
`php-extract-helper` — against one for `oracle-merged`. The new checkpoint
invents defects in code that provably does not change behaviour, which is the
same failure the 0.088 rendering-variance result points at, moved the wrong
way. The 12 clean cases are where the "no hallucination" half of the goal is
decided, and the retrain went backwards on them while going forwards on
detection.

Do **not** read this as "the grounding filter hurts". `sft-ml8-grounded`
differs from `oracle-merged` in three ways at once — grounding filter, project
split, smaller corpus — which is exactly what the control run in step 3 below
exists to separate.

Serving a checkpoint (one at a time; a second 3B does not fit the 6GB card,
and an OOM would take a training run with it):

    ssh oracle-gpu bash -s <<'EOF'
    cd ~/oracle && setsid nohup .venv/bin/python -m llm_explainer.serve \
        --model artifacts/oracle-merged --port 8111 > ~/oracle/serve.log 2>&1 < /dev/null &
    EOF

`serve.py` loads a LoRA adapter directly, so a training checkpoint can be
scored without merging first.

# What this session established

**1. Fine-tuning beats the base model on this slice.** 33/44 -> 40/44, +7
cases. The base model's failures are not subtle: on six buggy cases it
describes the change correctly and then concludes "This change does not
introduce any defects", and on `ts-nullish-default` it emitted unescaped quotes
inside a JSON string and failed schema validation twice.

**2. The retrain is a small regression, not a collapse** — see "Where this
landed". A first reading said php fell 5/5 -> 1/5; it is 3/5. The difference
was the scorer, not the model (finding 4).

**3. The benchmark is 44 cases across 9 languages, all proved by execution.**

    python bench/basic_bench.py --verify     # 44/44 verified, ~3 min, no GPU

| language | buggy | clean | total |
|---|---|---|---|
| c | 3 | 1 | 4 |
| go | 3 | 2 | 5 |
| java | 4 | 1 | 5 |
| javascript | 3 | 2 | 5 |
| php | 4 | 1 | 5 |
| python | 3 | 2 | 5 |
| ruby | 4 | 1 | 5 |
| rust | 4 | 1 | 5 |
| typescript | 4 | 1 | 5 |
| **all** | **32** | **12** | **44** |

`ruby` 3.4.10 and `php` 8.5.9 were installed on the laptop for this; java 21,
deno 2.9, rustc, go, node and gcc were already present.

**4. The scorer was counting correct paraphrases as hallucinations.**
`identified()` demanded every `must_mention` token as a literal substring, and
`grade()` turned a failed match on a buggy case into a hallucination — the one
metric the goal says must be zero. Four of the retrain's seven reported
hallucinations were correct answers that paraphrased (said "removes a
null-check for an empty array" without ever writing `count`). Fixed three ways:
alternatives in `must_mention`, proved false alarms reported apart from
unconfirmed locus, and every dash-like character folded (the 3B wrote U+2011).
Three entries were also too *loose* and would have passed wrong answers:
`"int"` matched "print", `"var"` matched "variable", `"acc"` matched "across".

**5. Two bugs made every earlier basic-bench number un-reproducible.**
`INFERENCE_SAMPLES=1` set nothing — `config.py:18` reads
`ORACLE_INFERENCE_SAMPLES` — so every earlier run was 3-sample consensus while
its write-up said greedy. And the three samples were byte-identical anyway,
because `serve.py` ignores the request's temperature. **`_analyze_consensus`
has therefore never done anything through `serve.py`**: the "sample several
times, keep what a majority agrees on" defence is a no-op on the backend where
every measurement is taken. `_env()` now warns when a bare name is set and the
prefixed one is not. Full write-up in `docs/RESULTS.md`.

# Next steps, in order

**1. Hand-grade the 44 for mechanism.** The automated scorer checks locus only
and is a floor, not a verdict — it cannot see an inverted claim. The 8/10 goal
is a mechanism claim, so it needs the hand pass. ~44 short reads, no GPU. The
cheapest outstanding item, and it gates any claim about the goal.

**2. Decide whether `_analyze_consensus` should be made real.** It is a no-op
through `serve.py` (finding 5), so a designed safeguard does not exist where it
is measured. Two options, and this is a judgement call rather than a bug fix:
make `serve.py` honour the request's temperature — which makes every run
non-deterministic and breaks comparability with everything measured so far — or
delete the consensus path and say so in the paper. **Do not change it silently
between benchmark runs.**

**3. The isolating control run**, now clearly worth the GPU time.
`data/sft_ml8_base.jsonl` is built — same split, same 1332 records, grounding
filter OFF. `sft-ml8-grounded` differs from `oracle-merged` in three ways at
once, so this is the only way to attribute the regression to the filter rather
than to the project split or the smaller corpus. ~9.5h.

**4. Evaluate `oracle-merged` — not the retrain — on the clean slice.**

    data/ml8_heldout.jsonl   341 records, 5 projects
                             gin, fastapi, axios, clap, spring-boot

Those projects are in neither training set nor the gate's, so this is the first
slice clean for **both** stages, and the first honest cascade measurement
available. Use `ORACLE_INFERENCE_SAMPLES=1`.

**5. Chase the refactor false alarms.** All three of the retrain's are
behaviour-preserving refactors, and only 5 of the 44 cases are
extract-helper/rename shaped. Add more clean refactor cases before drawing a
rate from them.

**6. Retune the gate threshold on a slice separate from the eval set**, then
report an honest Stage 1 number and the cascade disagreement rate.

**7. Measure grounding per-language** before the 78.3% figure goes in a table —
see the `identifiers()` note under "Known-stale comments".

**Not on the list, deliberately:** more DPO (closed as a null), more prompt
rules (disproved 17 Aug), context injection (disproved 24 Aug — it *suppressed*
findings on the race case), and more class mining (guard mining moved its class
28.4% -> 33.9% for a 0.04 F1 gap, under the noise floor).

# Findings from 24 Aug that still stand

All reproducible, full write-ups in `docs/RESULTS.md`.

1. **Rendering variance at n=200.** 800 calls, zero dropped. Verdict agreement
   89.2%, commits unanimous 77.5%, per-rendering **F1 spread 0.088**. The n=40
   figure of 0.233 was mostly small-sample noise and must not be quoted again,
   but 0.088 is still 2.2x the 0.04 guard-corpus gap, so the variance column
   stays mandatory. This is the strongest result the project has.

2. **DPO is closed as a null.** Three runs agree it moves nothing. Greedy output
   from `sft-merged`, `oracle-merged` and `oracle-merged-v2` is byte-identical.
   Real pairs do not fit the card: 0 of 525 grounded `from_labelled` pairs are
   under `DPO_MAX_LENGTH=512` (shortest 615 tokens), 61% would need 1536, and
   the card OOMs at 768. All 525 also share one hardcoded rejected string, so
   the objective is degenerate even if it fit. **Do not spend more GPU on DPO.**

3. **The gate was trained on its own evaluation set.** `apachejit_commits.jsonl`
   contains all 200 heldout commits. Worth **0.495 F1 and 0.21 AUC**
   (0.781 -> 0.286, 0.9638 -> 0.7530). Fixed by `train_gate.py --exclude`;
   clean model at `artifacts/gate_noleak.joblib`, `gate.joblib` left in place so
   old numbers stay reproducible.

4. **`GATE_THRESHOLD` does not transfer.** Tuned to 0.047 for 95.1% recall on
   27.5%-buggy ApacheJIT, it gives 17.4% recall on the 46%-buggy heldout.
   Retuned it hits F1 0.699, but that threshold is picked on the eval set, so
   treat it as an upper bound.

5. **Stage 2 is the weakest detector in the system.** On the same 200 commits:
   always-buggy 0.630, clean gate retuned 0.699, teacher 0.491, student 0.375.
   Distillation cannot pass 0.491. Stage 1 detects; Stage 2 should be measured
   on explanation, not detection.

6. **The evaluation was out of domain.** Training is 21 non-Apache web/infra
   projects, 11.5% Java; the heldout is 100% Apache, ~85% Java, zero project
   overlap. F1 0.375 is an out-of-domain number. Student-vs-teacher is still
   clean; the variance result is unaffected.

7. **`grounded()` never rejected anything.** A finding naming a touched file
   short-circuited the check, so on single-file commits everything passed:
   69/69 live findings, 597/597 corpus. Every "grounded: N%" before 24 Aug was
   100% by construction. Now 78.3% live, 81.9% corpus.

8. **`fix_agreement()` has never executed.** It reads a `fix_diff` field no
   dataset provides, returned NaN, and the report's NaN guard printed nothing.
   It now says "unavailable". Making it real is blocked: ApacheJIT's `fix`
   column is a boolean not a hash, and all 500 CVEfixes pairs are exact
   reverses, which would make the metric tautological.

9. **Two species of hallucination.** Species one cites nothing — grounding
   catches it, 21.7% of live findings. Species two cites real tokens and states
   a falsehood (a heap.js finding predicting a `RangeError` that JS cannot
   raise) — **grounding is blind to it.** `bench/basic_bench.py` is the only
   instrument in the repo that can see species two, because it executes the
   code.

# Paper status

Measured against the acceptance criteria in `ROADMAP.md:86`: criteria 2 and 4
fail outright, 3 is unverified, 5 is compromised by the line-composition leak,
1 passes as written though a new leak class appeared. **Not submittable as a
detect-and-explain system.**

There is a strong paper in the negatives: rendering variance (0.088 from edits
that change no code), the gate trained on its own eval set (0.495 F1), and the
line-composition leak in paired corpora (AUC 0.934 with no model). That is a
coherent methods contribution — *how LLM-based JIT defect prediction gets
measured wrong, and by how much* — and every number in it is reproducible
today. This session added two more of the same species, both from the
measurement apparatus rather than the model: a scorer that reported correct
paraphrases as hallucinations (4 of 7 on one checkpoint), and a sampling
safeguard that has never executed on the backend where every number is taken. Worth putting to the professor as an option before spending more GPU on
the original framing.

# Committed this session (25 Aug)

    6d74114  fix(bench): stop scoring correct paraphrases as hallucinations
    5b5ed81  fix(serve): use bfloat16 when there is no CUDA device
    05b91ee  fix(dashboard): stop the variance probe matching its own command line
    c685ee5  docs: hand off with the retrain in flight and the benchmark at 44 cases
    d8b12d8  docs: record the 44-case benchmark, verified in all 9 languages
    d22cf97  feat(bench): expand basic-algorithm benchmark to 44 cases, 9 languages
    6e16524  fix(bench): make identified() hyphen-insensitive, and score the base model

Working tree is clean apart from `docs/RESULTS.md` and this file.

New this session: `bench/basic/` grew from 12 to 44 case directories;
`data/basic_bench_base44.jsonl`, `data/basic_bench_oracle44.jsonl` and
`data/basic_bench_ml8.jsonl` (44 rows each, the three-way run);
`data/basic_bench_base.jsonl` and `data/basic_bench_oracle.jsonl` (12 rows
each, the superseded set — keep them, `--score` still re-grades them).
`artifacts/base-3b` on the box is a symlink into the HF cache pointing at
`models--Qwen--Qwen2.5-Coder-3B-Instruct/snapshots/488639f1ff…`.

Still on the box, not synced locally: `artifacts/sft-ml8-grounded` (the
regression — keep it, step 3 compares against it), `artifacts/dpo-adapter-v2`,
`artifacts/oracle-merged-v2` (6.2 GB, the DPO null),
`artifacts/gate_noleak.joblib`. Throwaway launchers worth deleting:
`run_dpo2.sh`, `cmp3.sh`, `cmp_greedy.sh`, `ctx2.py`, `ctx_test.sh`.

# Operational notes

- **Training runs on `oracle-gpu`, never locally.** The local venv has no
  `trl`/`peft`/`datasets`/`accelerate`/`bitsandbytes`, and this laptop's GPU is
  an AMD Radeon 680M with no ROCm stack. Installing training deps locally drags
  in a CPU torch that replaces the CUDA wheel; restore with
  `pip install --force-reinstall torch==2.13.0 --index-url https://download.pytorch.org/whl/cu130`
  and re-pin `fsspec<=2026.6.0`.
- **The remote shell on `oracle-gpu` is fish**, and it bit twice this session.
  `VAR=val cmd` prefixes, `$!`, and any `\"...$...\"` nesting fail there with
  exit 127 or `fish: $" is not a valid variable in fish`. The shape that always
  works is a heredoc:

      ssh oracle-gpu bash -s <<'EOF'
      ...bash here...
      EOF

  `ssh oracle-gpu 'bash -lc "..."'` works only while the inner string contains
  no `$`.
- **Every setting is read as `ORACLE_<NAME>`.** `config.py:18` is
  `os.getenv(f"ORACLE_{name}")`, so a bare `INFERENCE_SAMPLES=1` sets nothing
  and the run silently uses the default of 3. `_env()` now prints a warning to
  stderr when the bare name is set and the prefixed one is not — **if you see
  that line, the run you just started is not configured the way you think.**
  Pin comparisons with `ORACLE_INFERENCE_SAMPLES=1`.
- **`serve.py` ignores the request's temperature**, so through the served
  backend every sample is greedy and the samples are byte-identical. That makes
  `INFERENCE_SAMPLES=3` deterministic but 3x the cost, and it makes
  `_analyze_consensus` a no-op — see step 2 in "Next steps". Results are still
  not identical to a 1-sample run: `client.py:473` keeps only the first finding
  per category, so consensus can drop a second finding of the same category.
- **Four status checks in this repo report intent, not observed state**:
  `dashboard.sh` called a *completed* variance run "STUCK" (its stall check
  reads mtime); `serve.sh stop` printed `tunnel closed` while leaving the
  forwarder listening; `serve.sh start` printed "server started" on the launch
  command returning, not on the server answering; and `serve.sh`'s `ssh -f -N -L`
  tunnel does not survive being launched from a detached context. Open the
  tunnel by hand:

      setsid ssh -f -N -L 8111:localhost:8111 -o ExitOnForwardFailure=yes \
          -o ServerAliveInterval=30 -o ServerAliveCountMax=1000 oracle-gpu

  `ssh -O exit oracle-gpu` does **not** close it — that only drops the control
  master. Find the forwarder with `ss -tlnp | grep 8111` and kill the pid.
- **The `pkill`/`pgrep` self-match trap is real** and `serve.sh:29` warns about
  it. It fired twice this session: `pkill -f "8111:localhost:8111"` killed its
  own shell (exit 144), and `pgrep -f llm_explainer.serve` reported two live
  pids for a server that was already dead — both were the pgrep pipeline
  itself. **Confirm a server is down with `nvidia-smi`, not with `pgrep`.**
- **`main.py analyze --commit` is broken on the box.** `main.py:99` imports
  `git_diff` from `ui.tui_app`, which imports `textual`, which is not installed
  there. Work around it by calling `llm_explainer.context.gather` directly, the
  way `evaluate.py:119` does.
- Long GPU jobs: launch with `setsid nohup ... < /dev/null &` so they survive
  the local machine disconnecting.
- The `ssh ... "cd ~/oracle && cmd &"` shape puts only the backgrounded half in
  `~/oracle`; anything after the `&` runs in the login directory.
- Editing a script while it runs on the GPU box: write a temp file and `mv` it
  into place, never `sed -i` — a running bash re-reads its script by byte
  offset.
- Local venv `.venv/bin/python`, always. Keys: `~/.zshrc` exports
  `GROQ_API_KEY1..6` and `DEEPSEEK_API_KEY`. Labelling is done.
- Run `count_control.py` beside every detection number.
- `data/go_race_case.diff` is the cheapest end-to-end check: the model should
  report `concurrency`, and `go run -race` proves the bug (4 warnings; ~4% of
  runs lose a record). Every checkpoint so far reports it clean.
- Benchmark runtimes now installed on the laptop: `ruby` 3.4.10 and `php` 8.5.9
  (`sudo pacman -S ruby php`). `java` 21, `deno` 2.9, `rustc`, `go`, `node` and
  `gcc` were already there. `--verify` names the missing binary if one goes
  away.

# Known-stale comments worth fixing

In `fine_tuning/train_dpo.py`:

- The `padding_free=True` comment (~line 167) claims it saves about a quarter
  of the activation memory. **Confirmed dead** — TRL 1.9.2 prints
  `padding_free=True is temporarily unavailable after a refactor and is
  currently disabled` on every run.
- The comment below it says prompts run 751–1132 tokens, median 751. The
  measured DPO set is 414 median, 476 p90, 795 max. `config.py` is correct.
- `truncation_mode="keep_end"` warns it is deprecated and removed in TRL v2.0.0.

In `evaluate.py`: `identifiers()` only keeps tokens containing `_`, `.` or
camelCase, so plain names (`main`, `buf`, `len`) and all-caps macros (`CFLAGS`)
are invisible to grounding. For C and Makefile diffs this under-counts in both
directions — it rejects legitimate findings too. Worth measuring grounding
per-language before the 78.3% goes in a table. `basic_bench.py`'s
`identified()` had the same class of bug twice this session and is now fixed
three ways — any-of alternatives, all dash-like characters folded, and proved
false alarms reported apart from unconfirmed locus. **`identifiers()` has had
none of that pass**, and it feeds the grounding number the paper would quote.

# Decisions made (do not relitigate)

- **The immediate goal is the basic-algorithm slice at 8/10 with no
  hallucination**, measured by `bench/basic_bench.py`, not detection F1 on
  Apache Java.
- **No CPU inference.** Ruled out by the user 25 Aug; wait for the GPU.
- **Small goal before frameworks.** Framework idiom (next.js / react) is a
  LATER phase; the rules already exist in `llm_explainer/context.py`
  (`detect_framework`, `FRAMEWORK_RULES`).
- DPO ran on checkpoint-204, not checkpoint-136. Done, and now closed as a null.
- Do NOT switch the teacher to deepseek — the user vetoed it.
- The user's professor rejects "previous ML methods" (no XGBoost family). The
  narrative: the LightGBM head is infrastructure, the method is the gate→LLM
  cascade plus the eval framework. Contingency if pushed: the contrastive
  encoder (`ml_model/contrastive.py`, 27,798 pairs in
  `data/contrastive_pairs.jsonl`, tokenizer at `artifacts/code_bpe.json`) —
  started, then killed per the user's pivot. Offer it, do not assume it.
- Keep the ApacheJIT gate AUC 0.8293 as the gate's own-split number, but never
  quote a gate number measured on `labelled_heldout.jsonl` — those are leaked.
- Labelling is DONE. No more Groq budget needed.
