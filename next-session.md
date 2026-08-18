Continue ORACLE at ~/Documents/oracle. Read `docs/RESULTS.md` first (every
measurement plus the command that reproduces it), then `docs/ROADMAP.md` and
`docs/DATASETS.md`, and run `./dashboard.sh` (live) or `./status.sh --once`.

**First action this session:** restart the labelling watchdog — the guard phase
was stopped at 6 of 480 on 18 Aug evening with all six Groq keys rate-limited,
and nothing is running now. See "Next steps", step 0. Everything else in this
file is context for what to do while it runs and once it lands.

**Uncommitted working tree** from 18 Aug: `corpus/label.py` (6th key),
`dashboard.sh` (denominator fix), `label_watch.sh` (stderr fix),
`next-session.md`, `docs/RESULTS.md`. Review and commit them early, or the next
watchdog edit lands on top of unreviewed changes.

# The project

Two-stage JIT defect prediction. Title settled: "Predict, Then Explain:
Just-In-Time Defect Prediction with Natural-Language Findings". Stage 1 is a
gate classifier that detects buggy commits; Stage 2 is a fine-tuned 3B LLM that
verifies and explains. Base model Qwen2.5-Coder-3B-Instruct, QLoRA SFT on
teacher-labelled data (gpt-oss-120b on Groq is the teacher, the 3B is the
student). Do NOT use "Explainable JIT" — taken by PyExplainer / JITLine.

# Current state (18 Aug 2026, evening)

**Labelling pass 1 is DONE.** 1,013 commits attempted, **1,011 kept** in
`data/labelled_multilang.jsonl`. It overshot the 959 target because `--limit`
counts the commits not yet done at each relaunch, not the cumulative total — a
resumed run attempts up to `limit` more. No harm, just more corpus.

**Pass 2 — the guard corpus — is STOPPED, mid-phase.** It reached 6 kept /
6 attempted of 480 before the user stopped it on 18 Aug evening: all six
keys were rate-limited, so the run was burning clock, not budget. Both the
labeller and `label_watch.sh` were killed (the watchdog first — it relaunches
the labeller within 15 minutes otherwise).

**To resume, next day, when the daily budget resets** — one command, the
watchdog picks the phase itself from the raw line counts and relaunches:

    setsid nohup ./label_watch.sh >> label_watch.log 2>&1 < /dev/null &

Run it from a shell that contains no `pkill` pattern (self-match trap below).
Resume is free: `label.py` skips by `commit_id`, so the 6 already-kept
records stand.

**Six Groq keys now** (`GROQ_API_KEY1..6`, six separate organisations), so the
daily ceiling is 6 x 200,000 = 1.2M tokens/day / ~1,863 tokens per commit
~= **640 commits/day**, and all six were spent by 18 Aug evening. The 480-commit
guard phase is under a day of budget once they reset, so one resumed day should
finish it.
Adding a key is three edits: `~/.zshrc`, `/tmp/opencode/keys.env`, and the
comma-separated env list in `corpus/label.py` (`PROVIDERS["groq"]`); then
restart the labeller so it inherits the new environment.

Other state:

- `label_watch.sh` (the watchdog) keeps labelling alive and moves it between
  phases: every 15 minutes, no record growth means kill and relaunch, which is
  safe because `label.py` resumes by `commit_id`.
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

# Measured on the completed pass-1 corpus (1,011 labelled)

    .venv/bin/python -m dataset_builder.build_sft_data \
      --jsonl data/labelled_multilang.jsonl \
      --langs go typescript javascript java php rust python ruby --out /tmp/dry.jsonl

gives **1,005 examples, 0% repeated assistant turns**, 251 with findings and
754 clean. Buggy/clean is 415/596. Language mix: go 302, javascript 222, php
107, java 88, rust 79, python 78, typescript 70, ruby 59. Findings by category:
logic-error 103, error-handling 47, api-misuse 34, input-validation 33,
null-dereference 24, resource-leak 10, other 9, security 8, concurrency 7.

# Targeted guard corpus — mined 18 Aug, labelling STOPPED at 6 of 480

The general sample was too thin for the defect class the paper turns on: 7
guard-flavoured findings out of 141. So `corpus/mine.py --guards` now mines that
class directly — commits whose later fix *adds* a missing check.

`data/guard_commits.jsonl`: **1,458 commits, all 8 languages** (go 324, java 280,
javascript 230, php 228, rust 175, python 79, typescript 77, ruby 65), from
151,476 commits of history over 21 repositories. By class: nil-check 727,
falsy-check 536, empty-check 285, error-check 186, **zero-check 146**,
bounds-check 47, validation-raise 38. Those 146 zero-checks are the
divide-by-zero case `calculator.go` exposed — 20x the signal the general corpus
carried.

The SZZ step needed changing and this is the part to remember: a fix that only
*inserts* a guard deletes nothing, so `blame_origins()` (which blames deleted
lines) returns the empty set for exactly these commits.
`blame_insertion_context()` blames a ±3-line window around each insertion point
instead. Full reasoning in RESULTS, "Targeted mining for guard-adding fixes".

**To label it** (do NOT drop the two flags):

    .venv/bin/python -m corpus.label --in data/guard_commits.jsonl \
      --out data/labelled_guards.jsonl --raw data/labelled_guards_raw.jsonl \
      --provider groq --workers 1 --limit 2000 --per-language 60 --no-balance

`--no-balance` because the corpus is buggy by construction — the balancer would
fill half the sample with a clean class that does not exist and label only half
the limit. `--per-language 60` samples 480 evenly across the eight languages;
uncapped it is 969 net-new commits, which is ~3 days of free-tier budget against
~1.5. Composition is capped at labelling time, not mining time, because mining
is free and labelling is what costs days.

Then build the SFT from both corpora together:

    cat data/labelled_multilang.jsonl data/labelled_guards.jsonl > data/labelled_all.jsonl
    .venv/bin/python -m dataset_builder.build_sft_data --jsonl data/labelled_all.jsonl \
      --langs go typescript javascript java php rust python ruby --out data/sft_multilang8.jsonl

**Decided with the user, 18 Aug:** finish pass 1, then the guard corpus at
`--per-language 60` (480 commits), and **drop pass 2** — the 775 remaining
general commits are more of the same data, while the guard corpus fixes a known
blocker. Roughly 2.75 days of free-tier budget to an SFT-ready corpus.

`label_watch.sh` runs that sequence by itself once started: it decides the phase
from `labelled_multilang_raw.jsonl`'s line count (attempts, not kept records —
`verify()` drops labels, so the output file can never be relied on to reach the
limit), and launches the guard command with `--per-language 60 --no-balance`
once pass 1 has attempted its 959. Pass 1 is past that, so a restart goes
straight to the guard phase — but the watchdog itself is NOT running and must be
started by hand. `dashboard.sh` reads the same signal and shows which phase is
live.

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

# Next steps, in order — what to do after the 480 finish

**Step 0, first thing: restart the watchdog** — the guard phase was stopped at 6
of 480 with every key rate-limited, so nothing is running:

    setsid nohup ./label_watch.sh >> label_watch.log 2>&1 < /dev/null &

Then check it is advancing before walking away, and again once it should be done:

    ./dashboard.sh --once                       # phase row + bar
    wc -l data/labelled_guards.jsonl            # kept records, target ~480
    wc -l data/labelled_guards_raw.jsonl        # attempts; the phase is done at 480
    tail -3 label_watch.log                     # kills and relaunches, if any

Short of 480 with the watchdog alive means it is still working — leave it. Short
of 480 with nothing running means the watchdog died: restart it with
`setsid nohup ./label_watch.sh >> label_watch.log 2>&1 < /dev/null &`, from a
shell that does not also contain a `pkill` pattern (see the self-match trap
below).

1. **Build the SFT from both corpora.** This is the merge the whole labelling
   effort was for:

       cat data/labelled_multilang.jsonl data/labelled_guards.jsonl \
         > data/labelled_all.jsonl
       .venv/bin/python -m dataset_builder.build_sft_data \
         --jsonl data/labelled_all.jsonl \
         --langs go typescript javascript java php rust python ruby \
         --out data/sft_multilang8.jsonl

   Expect roughly 1,005 + ~450 = **~1,450 examples**. Two gates before any GPU
   spend, both printed by the build:
   - **repeated assistant turns must stay ~0%** — the build refuses to train on
     a corpus that memorised one answer.
   - **findings count must jump.** Pass 1 gave 251 of 1,005 with findings. The
     guard corpus is buggy by construction, so nearly all ~450 should carry a
     finding; if they do not, the teacher is not seeing the guard class and that
     is a prompt problem to fix *before* 10 hours of GPU time.

2. **Re-check the guard-class share** on the merged corpus — the reason the
   guard corpus exists. Count findings whose category or explanation is
   guard/validation-flavoured and compare against pass 1's 275 findings. Use one
   script for both corpora so the numbers are comparable; the 20.7% recorded in
   RESULTS is a broad regex and does NOT compare to the earlier hand-counted 5%.

3. **Power the GPU box on**, `scp data/sft_multilang8.jsonl` over, `./serve.sh
   stop` (it is not running, but check), then launch QLoRA SFT (~10h). Nothing
   else can proceed in parallel on that box.

4. **Eval the small goal** against `checkpoint-220` as the incumbent: grounding,
   category accuracy, `cve_quality` against human CVE text, per-language
   separation (TS was -16.7pp on the old corpus), and re-test the divide-by-zero
   Go case that motivated the guard mining. Run `count_control.py` beside every
   detection number.

5. **Serve + TUI on a mined repo**, then the cascade measurement: gate/LLM
   disagreement rate on `detect_eval`.

If the guard phase came up short and the budget is spent, the fallback is to let
it run another day rather than to train on a partial guard corpus — step 1's
findings gate is the point of the exercise. Dropped general-corpus pass 2 (the
775 remaining commits) stays dropped; that decision is in the section above.

# Operational notes

- Local venv `.venv/bin/python`, always. Keys: `~/.zshrc` exports
  `GROQ_API_KEY1..6` and `DEEPSEEK_API_KEY`; `/tmp/opencode/keys.env` holds
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
  is meaningless — count the output file. Same for the guard phase's `N/480`.
- `--limit` applies to the commits not yet labelled at launch, not to the
  cumulative total, so a resumed run overshoots the limit. Pass 1 ended at 1,013
  attempts against a 959 limit for this reason.
- `dashboard.sh` must NOT take its denominator from the log's "N commits to
  label": that N is what was left at the last relaunch, while the bar's
  numerator counts the whole output file. Mixing them once read 924/829 = 111%.
- A failed input redirect cannot be muted by `2>/dev/null` on the same command
  (`wc -l < "$MISSING" 2>/dev/null`) — the shell reports it before that redirect
  takes effect. Wrap it: `{ wc -l < "$F"; } 2>/dev/null`.
- Run `count_control.py` beside every detection number.
