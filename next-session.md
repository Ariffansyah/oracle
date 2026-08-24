Continue ORACLE at ~/Documents/oracle. Read `docs/RESULTS.md` first (every
measurement plus the command that reproduces it), then `docs/ROADMAP.md`.

**First action this session:** nothing is running and the GPU box is free —
see "Nothing is running". The SFT retrain was stopped at 2/154 steps and is
staged to relaunch, but read step 3 in "Next steps" before spending 9.5 hours
on it.

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

# Nothing is running — the box is free

The SFT retrain was launched 24 Aug ~13:00 and **stopped at 2/154 steps** at the
user's request; they wanted `oracle-gpu` for something else. No checkpoint was
written and nothing was lost but ~7 minutes. `artifacts/sft-ml8-grounded` does
not exist.

**Everything it needs is already staged**, so relaunching is one command:

    ssh oracle-gpu 'setsid nohup bash ~/oracle/run_sft_ml8.sh \
        > ~/oracle/sft_ml8.log 2>&1 < /dev/null &'

    train      data/sft_ml8_grounded.jsonl   1286 examples   (on the box)
    heldout    data/ml8_heldout.jsonl         341 records    (on the box)
    control    data/sft_ml8_base.jsonl       1332 examples   (unused, see step 5)
    cost       154 steps at ~221 s/step = ~9h30m

It needs the whole card, so stop the inference server first
(`./serve.sh stop`) and expect the TUI to be down for the duration.

Before relaunching, consider step 3 below — scoring the base model on
`bench/basic_bench.py` takes ten minutes and may show this retrain is pointed
the wrong way.

# What this session established

Nine findings, most of them negative, all reproducible. Full write-ups with
commands are in `docs/RESULTS.md`.

1. **Rendering variance at n=200.** 800 calls, zero dropped. Verdict agreement
   89.2%, commits unanimous 77.5%, per-rendering **F1 spread 0.088**. The n=40
   figure of 0.233 was mostly small-sample noise and must not be quoted again,
   but 0.088 is still 2.2x the 0.04 guard-corpus gap, so the variance column
   stays mandatory. This is the strongest result the project has.

2. **DPO is closed as a null.** Three runs agree it moves nothing. The previous
   handoff blamed gradient clipping; a controlled retrain disproves that (Adam
   normalises by `g/sqrt(v)`, so it is scale-invariant to a uniform gradient
   rescale). Greedy output from `sft-merged`, `oracle-merged` and
   `oracle-merged-v2` is byte-identical. Real pairs do not fit the card:
   0 of 525 grounded `from_labelled` pairs are under `DPO_MAX_LENGTH=512`
   (shortest 615 tokens), 61% would need 1536, and the card OOMs at 768. All
   525 also share one hardcoded rejected string, so the objective is degenerate
   even if it fit. **Do not spend more GPU on DPO.**

3. **The gate was trained on its own evaluation set.** `apachejit_commits.jsonl`
   contains all 200 heldout commits. Worth **0.495 F1 and 0.21 AUC**
   (0.781 -> 0.286, 0.9638 -> 0.7530). Fixed by `train_gate.py --exclude`;
   clean model at `artifacts/gate_noleak.joblib`, `gate.joblib` left in place so
   old numbers stay reproducible.

4. **`GATE_THRESHOLD` does not transfer.** Tuned to 0.047 for 95.1% recall on
   27.5%-buggy ApacheJIT, it gives 17.4% recall on the 46%-buggy heldout —
   forwarding 20 of 200 commits and dropping 76 of 92 defects. Retuned it hits
   F1 0.699, but that threshold is picked on the eval set, so treat it as an
   upper bound.

5. **Stage 2 is the weakest detector in the system.** On the same 200 commits:
   always-buggy 0.630, clean gate retuned 0.699, teacher 0.491, student 0.375.
   Distillation cannot pass 0.491. Stage 1 detects; Stage 2 should be measured
   on explanation, not detection.

6. **The evaluation was out of domain.** Training is 21 non-Apache web/infra
   projects, 11.5% Java; the heldout is 100% Apache, ~85% Java, zero project
   overlap. F1 0.375 is an out-of-domain number, and part of the gate-vs-LLM
   gap in (5) is domain rather than architecture. Student-vs-teacher is still
   clean; the variance result is unaffected.

7. **`grounded()` never rejected anything.** A finding naming a touched file
   short-circuited the check, so on single-file commits everything passed:
   69/69 live findings, 597/597 corpus. Every "grounded: N%" before today was
   100% by construction. Now 78.3% live, 81.9% corpus.

8. **`fix_agreement()` has never executed.** It reads a `fix_diff` field no
   dataset provides, returned NaN, and the report's NaN guard printed nothing.
   It now says "unavailable". Making it real is blocked: ApacheJIT's `fix`
   column is a boolean not a hash, and all 500 CVEfixes pairs are exact
   reverses, which would make the metric tautological.

9. **Two species of hallucination.** Species one cites nothing (a Makefile
   finding claiming `CFLAGS` was deleted when it is on line 1) — grounding
   catches it, 21.7% of live findings. Species two cites real tokens and states
   a falsehood (a heap.js finding predicting a `RangeError` that JS cannot
   raise; `node` proves the change is behaviour-preserving) — **grounding is
   blind to it and nothing in the repo measures it.**

# The one bright result

`bench/basic_bench.py` on `oracle-merged`: **8/12 hand-graded correct, 11/12 by
the automated locus scorer, zero false alarms on the 4 clean cases.** Against
0.375 on Apache Java this is a different regime, and it is the regime the
user's goal lives in. The model finds the right line 11 times in 12 and
explains it correctly 8 times — the gap is mechanism, not localisation, which
is a much easier problem than the one the paper framing was chasing.

# Next steps, in order

**1. When the retrain lands, evaluate `sft-ml8-grounded` on the clean slice.**

    data/ml8_heldout.jsonl   341 records, 5 projects
                             gin, fastapi, axios, clap, spring-boot

Those projects are in neither the new training set nor the gate's, so this is
the first slice clean for **both** stages, and the first honest cascade
measurement available. Use `INFERENCE_SAMPLES=1` (see Operational notes).

**2. Run `bench/basic_bench.py` on the new checkpoint** and compare to the
8/12 baseline. Cheap, and it speaks directly to the user's goal.

**3. Score the BASE model (`Qwen2.5-Coder-3B-Instruct`) on the same benchmark.**
This is the highest-value cheap experiment outstanding. The SFT trained on
messy real-world commits; if the base model explains basic algorithms better,
the fine-tuning is damaging the slice the user cares about and the fix is to
stop training on that data, not to train more. ~10 min on the box.

**4. Expand the benchmark to ~40 cases** covering all 8 languages. 12 is too
few to claim a rate, and ruby, php, rust and typescript are uncovered (ruby and
php are not installed locally). This is CPU-only and can be done while a GPU
job runs.

**5. Only if 1–3 show the grounding filter mattered:** the isolating control
run. `data/sft_ml8_base.jsonl` is already built — same split, same 1332
records, filter OFF. Comparing `sft-ml8-grounded` to `checkpoint-204` confounds
three changes at once (grounding filter, project split, smaller corpus); this
run is the only way to attribute a difference to grounding. Another ~9.5h.

**6. Retune the gate threshold on a slice separate from the eval set**, then
report an honest Stage 1 number and the cascade disagreement rate.

**Not on the list, deliberately:** more DPO (2), more prompt rules (disproved
17 Aug), context injection (disproved 24 Aug — it *suppressed* findings on the
race case), and more class mining (guard mining moved its class 28.4% -> 33.9%
for a 0.04 F1 gap, under the noise floor).

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

# Committed this session

    1d44955  feat(dpo): make max_grad_norm configurable
    c4bd83b  feat(evaluate): add a with-context evaluation path
    1056180  ci(dashboard): track variance progress and name the served model
    4a66678  docs: record the n=200 variance result and close out DPO
    6a6fa16  fix(client): report why all samples failed, not just that they did
    e7325c3  feat(gate): add --exclude so the eval set can be kept out of training
    6cd86f4  fix(evaluate): make grounded() reject findings, stop hiding a dead metric
    d1c3878  feat(bench): executable benchmark, project-split, grounding filter

Uncommitted at handoff: `docs/RESULTS.md` and `next-session.md` (this file).

New data files, all local and on the box: `data/ml8_train.jsonl` (1332),
`data/ml8_heldout.jsonl` (341), `data/sft_ml8_grounded.jsonl` (1286),
`data/sft_ml8_base.jsonl` (1332, the unused control), `data/variance200.jsonl`
(800 rows), `data/basic_bench_oracle.jsonl` (12 rows).

New artifacts on the box, not synced locally: `artifacts/dpo-adapter-v2`,
`artifacts/oracle-merged-v2` (6.2 GB, the DPO null), `artifacts/gate_noleak.joblib`,
and `artifacts/sft-ml8-grounded` when the run finishes. Throwaway launchers on
the box worth deleting: `run_dpo2.sh`, `cmp3.sh`, `cmp_greedy.sh`, `ctx2.py`,
`ctx_test.sh`.

# Operational notes

- **Training runs on `oracle-gpu`, never locally.** The local venv has no
  `trl`/`peft`/`datasets`/`accelerate`/`bitsandbytes`, and this laptop's GPU is
  an AMD Radeon 680M with no ROCm stack. Installing training deps locally drags
  in a CPU torch that replaces the CUDA wheel; restore with
  `pip install --force-reinstall torch==2.13.0 --index-url https://download.pytorch.org/whl/cu130`
  and re-pin `fsspec<=2026.6.0`.
- **The remote shell on `oracle-gpu` is fish.** `VAR=val cmd` prefixes and `$!`
  do not parse there, so any bash-shaped command pasted through `ssh` fails
  with exit 127. Write a bash script and `rsync` it over, or pipe with
  `ssh oracle-gpu bash -s <<'EOF'`.
- **`INFERENCE_SAMPLES=3` is not deterministic.** `client.py:453` runs sample 0
  greedy and samples 1..n at `INFERENCE_SAMPLE_TEMPERATURE=0.6`. Any A/B of two
  checkpoints must set `INFERENCE_SAMPLES=1` or it measures the sampler. This
  cost an hour: a first checkpoint comparison showed all three models
  "differing" and the entire difference was the minority-findings clause.
- **Four status checks in this repo report intent, not observed state**, and
  all four lied today: `dashboard.sh` called a *completed* variance run
  "STUCK" (its stall check reads mtime); `serve.sh stop` printed
  `tunnel closed` while leaving the forwarder listening on 8111, which then
  made the next `serve.sh start` fail with `Address already in use`;
  `serve.sh start` printed "server started" on the launch command returning,
  not on the server answering; and `serve.sh`'s `ssh -f -N -L` tunnel does not
  survive being launched from a detached context. Open the tunnel by hand:

      setsid ssh -f -N -L 8111:localhost:8111 -o ExitOnForwardFailure=yes \
          -o ServerAliveInterval=30 -o ServerAliveCountMax=1000 oracle-gpu

  If it will not bind, something stale is holding 8111 — `ss -tlnp | grep 8111`
  and kill it.
- **`main.py analyze --commit` is broken on the box.** `main.py:99` imports
  `git_diff` from `ui.tui_app`, which imports `textual`, which is not installed
  there. The CLI's commit path depends on the TUI package, which is very likely
  why the with-context path was never evaluated — it cannot run where the GPU
  is. Work around it by calling `llm_explainer.context.gather` directly, the
  way `evaluate.py:119` does.
- The `pkill`/`pgrep` self-match trap is real and `serve.sh:29` warns about it:
  killing and launching the server in one ssh call makes `pkill` match the
  launch command's own cmdline. Two separate calls.
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

# Known-stale comments worth fixing

In `fine_tuning/train_dpo.py`:

- The `padding_free=True` comment (~line 167) claims it saves about a quarter
  of the activation memory. **Confirmed dead** — TRL 1.9.2 prints
  `padding_free=True is temporarily unavailable after a refactor and is
  currently disabled` on every run, including the 24 Aug one.
- The comment below it says prompts run 751–1132 tokens, median 751. The
  measured DPO set is 414 median, 476 p90, 795 max. `config.py` is correct.
- `truncation_mode="keep_end"` warns it is deprecated and removed in TRL v2.0.0.

In `evaluate.py`: `identifiers()` only keeps tokens containing `_`, `.` or
camelCase, so plain names (`main`, `buf`, `len`) and all-caps macros (`CFLAGS`)
are invisible to grounding. For C and Makefile diffs this under-counts in both
directions — it rejects legitimate findings too. Worth measuring grounding
per-language before the 78.3% goes in a table.

# Decisions made (do not relitigate)

- **The immediate goal is the basic-algorithm slice at 8/10 with no
  hallucination**, measured by `bench/basic_bench.py`, not detection F1 on
  Apache Java.
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
