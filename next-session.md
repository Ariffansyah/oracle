Continue ORACLE at ~/Documents/oracle. Read `docs/RESULTS.md` first (every
measurement plus the command that reproduces it), then `docs/ROADMAP.md` and
`docs/DATASETS.md`, and run `./dashboard.sh` (live) or `./status.sh --once`.

# The project

Two-stage JIT defect prediction. Title settled: "Predict, Then Explain:
Just-In-Time Defect Prediction with Natural-Language Findings". Stage 1 is a
gate classifier that detects buggy commits; Stage 2 is a fine-tuned 3B LLM that
verifies and explains. Base model Qwen2.5-Coder-3B-Instruct, QLoRA SFT on
teacher-labelled data (gpt-oss-120b on Groq is the teacher, the 3B is the
student). Do NOT use "Explainable JIT" — taken by PyExplainer / JITLine.

# Current state (18 Aug 2026, morning)

**Labelling pass 1 is running and is now 16x faster** (3.0 commits/min,
measured over a 300s window, against 0.19/min before). It had been
averaging five minutes per commit; the cause was a retry bug, not the token
budget, and it is fixed. Full write-up in RESULTS, "Labelling throughput was a
retry bug". The short version:

- Groq's free tier caps **tokens per day** (200,000 per organisation), and the
  three keys are in three separate organisations — so the real budget is
  600,000 tokens/day ÷ ~1,863 tokens per commit ≈ **320 commits/day**.
- An exhausted key answers a 429 with `retry-after` in the hundreds of seconds.
  `ask()` used to rotate keys by `attempt % len(keys)`, so every commit began on
  the same spent key and slept out its full daily penalty before trying a live
  one.
- Now a 429 longer than 60s parks that key in `_BLOCKED` and the call retries
  immediately on the next live key. `_pace()` additionally reads
  `x-ratelimit-remaining-tokens` off each response and sleeps exactly the
  shortfall, so the per-minute bucket is spent smoothly.

**The daily cap is the real ceiling and it does not go away.** Pass 1 has ~460
commits left and pass 2 adds 775, so the two passes need roughly **four days**
of free-tier budget. If that is too slow the levers are, in order: more Groq
organisations, a paid tier, or `reasoning_effort: "low"` on the teacher call
(502 of the 637 completion tokens are reasoning tokens).

Other state:

- `label_watch.sh` (the watchdog) keeps labelling alive: every 15 minutes, no
  record growth means kill and relaunch, which is safe because `label.py`
  resumes by `commit_id`. Its relaunch command no longer passes `--sleep 18` —
  that flag was declared and never applied, and now that it *is* applied it
  would cap throughput below what the pacing achieves.
- `dashboard.sh` is the live TUI (jobs, bars, stuck flags, watchdog liveness);
  `./dashboard.sh --once` for one shot, `status.sh` is the plain one-shot.
- **GPU box is OFF** (the user powered it down). `oracle-gpu` / 192.168.1.170,
  user `arpthef`, fish login shell, so every remote command goes through
  `ssh oracle-gpu "bash -lc '...'"`. SFT (~10h), whole-diff embeddings and
  serving all wait on it.
- Gate: frozen GraphCodeBERT embeddings + 14 Kamei metrics + LightGBM, AUC
  **0.8293** (`artifacts/gate.joblib`), counting baseline 0.638. No regressions.
- `sft-adapter/checkpoint-220` is the served explainer. `INFERENCE_SAMPLES=3`
  consensus is the default in `config.py`.

# Measured on the mined corpus so far (~495 of 1,734 labelled)

The SFT build already passes its gate — worth knowing before spending GPU time:

    .venv/bin/python -m dataset_builder.build_sft_data \
      --jsonl data/labelled_multilang.jsonl \
      --langs go typescript javascript java php rust python ruby --out /tmp/dry.jsonl

gives 486 examples, **0% repeated assistant turns**, 128 with findings and 358
clean. Language mix so far: go 149, javascript 102, python 46, php 41, java 40,
rust 38, ruby 35, typescript 35. Buggy/clean is 220/268.

**One risk to watch.** The whole point of the multilang corpus is to put
missing-guard findings into the SFT target distribution (RESULTS, "Prompt rules
cannot move the SFT'd 3B"). Across 141 findings so far only 14 are
`input-validation` and 10 are `null-dereference`, and only 7 explanations use
guard/validation language at all — about 5%. Extrapolated to the full 1,734
that is ~85 examples. That may be too thin to teach the behaviour. Check this
again when pass 1 completes, and if it stays thin the fix is targeted mining:
commits whose fix diff *adds* a guard, rather than a general sample.

# Decisions made (do not relitigate)

- **Small goal**: perfect the 8-language BASIC-code slice (the mined corpus)
  first. Framework idiom (next.js / react) is a LATER phase — the rules already
  exist in `llm_explainer/context.py` (`detect_framework`, `FRAMEWORK_RULES`).
- Do NOT switch the teacher to deepseek — the user vetoed it.
- `--samples` is already 1 (it is the argparse default and the launch command
  never overrode it). The old handoff note offering "`--samples 1` for a 3x
  speedup on pass 2" was wrong; there is no such speedup available.
- The user's professor rejects "previous ML methods" (no XGBoost family). The
  narrative: the LightGBM head is infrastructure, the method is the gate→LLM
  cascade plus the eval framework. Contingency if pushed: the contrastive
  encoder (`ml_model/contrastive.py`, 27,798 pairs in
  `data/contrastive_pairs.jsonl`, tokenizer at `artifacts/code_bpe.json`) —
  started, then killed per the user's pivot. Offer it, do not assume it.
- Keep the ApacheJIT gate numbers (0.8293) as-is.
- Labelling runs locally and talks only to Groq; the GPU box is irrelevant to it.

# Next steps, in order

1. Let pass 1 reach 959, then relaunch for the remaining 775 with `--limit 2000`
   (same command, resume-safe). Budget four days total for both passes.
2. Build the SFT for real once the corpus is complete, and re-check the
   missing-guard finding count before any GPU spend.
3. Power the box back on, `scp` the SFT data, `./serve.sh stop` (it is not
   running, but check), launch QLoRA SFT (~10h).
4. Eval the small goal: grounding, category accuracy, `cve_quality` against
   human CVE text, per-language separation (TS was −16.7pp on the old corpus),
   and re-test the divide-by-zero Go case.
5. Serve + TUI on a mined repo, then gate/LLM disagreement rate on
   `detect_eval` (the cascade measurement).

# Operational notes

- Local venv `.venv/bin/python`, always. Keys: `~/.zshrc` exports
  `GROQ_API_KEY{,2,3}` and `DEEPSEEK_API_KEY`; `/tmp/opencode/keys.env` holds
  the same exports for background launches.
- `pkill` self-match trap: patterns must use the `[.]` trick AND must not share
  a shell with the launching command — `pgrep` matches the tool wrapper's own
  cmdline, and `llm_explainer[.]serve` once killed its own launcher.
- Editing `label_watch.sh` while it runs: write a temp file and `mv` it into
  place, never `sed -i`, then restart the watchdog — a running bash re-reads its
  script by byte offset.
- `label_watch.log` is event-based: silence means no kills, which means healthy.
  Stuck flags in the dashboard use 15-minute windows.
- The `N/959` line in `label_multilang.log` resets on every process restart and
  is meaningless — count the output file.
- Run `count_control.py` beside every detection number.
