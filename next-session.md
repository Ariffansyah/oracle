Continue ORACLE at ~/Documents/oracle. Read `docs/RESULTS.md` first (every
measurement plus the command that reproduces it), then `docs/ROADMAP.md`.

**First action this session:** check whether the SFT retrain finished — see
"A training run is in flight". If it has, the queue in "Next steps" is four
GPU jobs deep and every one of them is cheap.

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

# A training run is in flight

`run_sft_ml8.sh` was relaunched 25 Aug 00:44 WIB and is training normally.

    train      data/sft_ml8_grounded.jsonl   1286 examples
    heldout    data/ml8_heldout.jsonl         341 records
    control    data/sft_ml8_base.jsonl       1332 examples   (unused, see step 5)
    output     artifacts/sft-ml8-grounded    (on the box)
    cost       154 steps at ~227 s/step = ~9h35m, so ~10:20 WIB

Check it:

    ssh oracle-gpu bash -s <<'EOF'
    nvidia-smi --query-gpu=memory.used --format=csv,noheader
    tr '\r' '\n' < ~/oracle/sft_ml8.log | grep -oE '[0-9]+/154 \[[^]]*\]' | tail -1
    EOF

It holds 4584 MiB of a 6144 MiB card, so **nothing else fits on the GPU while
it runs** — 1560 MiB free is not enough for a second 3B even in 4-bit, and an
OOM would take the run with it. Do not try. Relaunch, if it dies:

    ssh oracle-gpu 'setsid nohup bash ~/oracle/run_sft_ml8.sh \
        > ~/oracle/sft_ml8.log 2>&1 < /dev/null &'

**The user has ruled out CPU inference as a way to fill the wait.** It was
tried this session (the box has 12 cores and the base weights cached) and
stopped before any case was scored. Wait for the card instead.

# What this session established

**1. Fine-tuning helps the basic-algorithm slice — it does not damage it.**
This was the open question that gated the retrain, and it is now closed. Base
`Qwen2.5-Coder-3B-Instruct` was served straight from the box's HF cache and run
on the same 12-case benchmark, greedy, `INFERENCE_SAMPLES=1`:

| | base 3B | `oracle-merged` |
|---|---|---|
| locus correct | 9/12 | **11/12** |
| hallucinated | 2/12 | **0/12** |
| false alarms on the 4 clean cases | 1 | **0** |

Hand-graded for mechanism rather than locus: base 7/12 against the tuned
model's 8/12. The locus gap is the larger and the more reliable of the two.
Full write-up and the base model's five failures are in `docs/RESULTS.md`.

**2. `identified()` was hyphen-brittle, and it cost a whole case.**
`must_mention` was a plain lowercase substring test, so a case asking for
`"out of bounds"` scored the base model's `"out-of-bounds"` — a fully correct C
array-bound explanation — as a **hallucination**. It now flattens `-` and `_`
to spaces on both sides. This moved the base model from 8/12 to 9/12 and from 3
hallucinations to 2. Both runs in the table above were re-scored under the fix.
Every future number on this benchmark depends on it.

**3. The benchmark is 44 cases across 9 languages, all verified.**
Was 12 cases over 4 languages, covering none of ruby, php, rust, typescript or
java — between them 708 of the 1332 `ml8` training records.

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

The 12 clean cases are the false-alarm half of the target: a finding on any of
them is a hallucination by definition.

**No model has been scored on the full 44 yet.** Every basic-bench number in
the repo is still from the old 12-case set.

# Next steps, in order

Steps 1–3 all need the GPU and all are cheap. Do them in one sitting once the
card is free, with the server up the whole time.

**1. Score the three models on the full 44.** `sft-ml8-grounded` first, then
re-score `oracle-merged` and the base 3B — their existing numbers are from the
12-case set and are not comparable to anything measured from now on.

    ./serve.sh start          # or serve --model <dir> by hand, see below
    INFERENCE_SAMPLES=1 python bench/basic_bench.py --backend ollama \
        --model-name <name> --host http://localhost:8111 \
        --out data/basic_bench_<name>.jsonl

To serve a checkpoint other than `oracle-merged`, pass `--model`:

    # on the box; base-3b is a symlink into the HF cache, made this session
    .venv/bin/python -m llm_explainer.serve --model artifacts/base-3b --port 8111
    .venv/bin/python -m llm_explainer.serve --model artifacts/sft-ml8-grounded --port 8111

A training checkpoint is a LoRA adapter and `serve.py` loads one directly
(`serve.py:60`), so `sft-ml8-grounded` can be scored without merging first.

**2. Evaluate `sft-ml8-grounded` on the clean slice.**

    data/ml8_heldout.jsonl   341 records, 5 projects
                             gin, fastapi, axios, clap, spring-boot

Those projects are in neither the new training set nor the gate's, so this is
the first slice clean for **both** stages, and the first honest cascade
measurement available. Use `INFERENCE_SAMPLES=1` (see Operational notes).

**3. Hand-grade the 44 for mechanism.** The automated scorer checks locus only
and is a floor, not a verdict — it cannot see an inverted claim. The 8/10 goal
is a mechanism claim, so it needs the hand pass. ~44 short reads.

**4. Only if 1–3 show the grounding filter mattered:** the isolating control
run. `data/sft_ml8_base.jsonl` is already built — same split, same 1332
records, filter OFF. Comparing `sft-ml8-grounded` to `checkpoint-204` confounds
three changes at once (grounding filter, project split, smaller corpus); this
run is the only way to attribute a difference to grounding. Another ~9.5h.

**5. Retune the gate threshold on a slice separate from the eval set**, then
report an honest Stage 1 number and the cascade disagreement rate.

**6. Measure grounding per-language** before the 78.3% figure goes in a table —
see the `identifiers()` note under "Known-stale comments".

**Not on the list, deliberately:** more DPO (closed as a null, see below), more
prompt rules (disproved 17 Aug), context injection (disproved 24 Aug — it
*suppressed* findings on the race case), and more class mining (guard mining
moved its class 28.4% -> 33.9% for a 0.04 F1 gap, under the noise floor).

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
today. Worth putting to the professor as an option before spending more GPU on
the original framing.

# Committed this session (25 Aug)

    6e16524  fix(bench): make identified() hyphen-insensitive, score the base model
    d22cf97  feat(bench): expand basic-algorithm benchmark to 44 cases, 9 languages
    d8b12d8  docs: record the 44-case benchmark, verified in all 9 languages

**Uncommitted:** `llm_explainer/serve.py` — picks `bfloat16` instead of
`float16` when there is no CUDA device, because `float16` has no real CPU
matmul kernel and a 3B model crawls under it. Written for the CPU experiment
the user then stopped. It is a correct fix and changes nothing on the GPU path
(`torch.cuda.is_available()` is true there), but it is untested at any scale
and the user has ruled out the use case it was written for. Commit it or revert
it; do not leave it dangling a third time. The copy on the box is already
synced.

New this session: `bench/basic/` grew from 12 to 44 case directories;
`data/basic_bench_base.jsonl` (12 rows, the base 3B on the old set);
`artifacts/base-3b` on the box, a symlink into the HF cache pointing at
`models--Qwen--Qwen2.5-Coder-3B-Instruct/snapshots/488639f1ff…`.

Still on the box, not synced locally: `artifacts/dpo-adapter-v2`,
`artifacts/oracle-merged-v2` (6.2 GB, the DPO null), `artifacts/gate_noleak.joblib`.
Throwaway launchers worth deleting: `run_dpo2.sh`, `cmp3.sh`, `cmp_greedy.sh`,
`ctx2.py`, `ctx_test.sh`.

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
- **`INFERENCE_SAMPLES=3` is not deterministic.** `client.py:453` runs sample 0
  greedy and samples 1..n at `INFERENCE_SAMPLE_TEMPERATURE=0.6`. Any A/B of two
  checkpoints must set `INFERENCE_SAMPLES=1` or it measures the sampler. Every
  basic-bench number so far was taken at `INFERENCE_SAMPLES=1`, greedy.
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
per-language before the 78.3% goes in a table. Note that `basic_bench.py`'s
`identified()` hit the mirror-image bug this session and was fixed by
flattening `-`/`_`; `identifiers()` has not had the same pass.

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
