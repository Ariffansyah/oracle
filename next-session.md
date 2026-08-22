Continue ORACLE at ~/Documents/oracle. Read `docs/RESULTS.md` first (every
measurement plus the command that reproduces it, latest section is "Ablation:
general-only vs guard-augmented SFT"), then `docs/ROADMAP.md`.

**First action this session:** check whether the ablation eval finished —
see "Next steps", step 0. If it's done, the comparison is the point of this
whole handoff.

# The project

Two-stage JIT defect prediction. Title settled: "Predict, Then Explain:
Just-In-Time Defect Prediction with Natural-Language Findings". Stage 1 is a
gate classifier that detects buggy commits; Stage 2 is a fine-tuned 3B LLM that
verifies and explains. Base model Qwen2.5-Coder-3B-Instruct, QLoRA SFT on
teacher-labelled data (gpt-oss-120b on Groq is the teacher, the 3B is the
student). Do NOT use "Explainable JIT" — taken by PyExplainer / JITLine.

# Current state (22 Aug 2026)

**Labelling is done, both corpora.** Pass 1: 1,011 kept (`data/labelled_multilang.jsonl`).
Guard corpus: 662 kept (`data/labelled_guards.jsonl`), overshot the 480 target
(per-language cap didn't count records already on disk across relaunches — fixed
in `corpus/label.py`, not yet committed, see "Uncommitted at handoff"). Merged:
`data/labelled_all.jsonl`, 1,673 records. Guard-class share on the guard corpus
alone: **33.9%** (109/322 findings), beats pass 1's 28.4% baseline — the
targeted mining did what it was for. Full numbers in RESULTS.md, "Guard corpus
finished, checkpoint-204 trained and evaluated".

**Two SFT adapters trained and being compared:**

- `artifacts/sft-adapter/checkpoint-204` — trained on `data/sft_multilang8.jsonl`
  (1,667 examples, pass 1 + guard corpus merged). Evaluated 21 Aug: CVE eval
  (human ground truth, 1000 commits) gives P=0.59 R=0.51 F1=0.55, grounded
  91.5%, category match 20.8%.
- `artifacts/sft-adapter-general/checkpoint-136` — trained on `data/sft_general.jsonl`
  (1,005 examples, pass 1 only, no guard commits) — the ablation control, same
  build as the original pass-1 corpus. Training finished 22 Aug 04:52.
  **Evaluation launched 22 Aug, in progress at handoff** (`eval_general.log` on
  `oracle-gpu`, background `setsid nohup`, ~12.5h by checkpoint-204's timing:
  200-commit eval ~2.5h, ApacheJIT 1000 ~5h, CVEfixes 1000 ~5h).

The ablation question: does the guard corpus's extra signal actually improve
detection/category-match, or would the same GPU hour have gone just as far on
more general-corpus data? checkpoint-204 vs checkpoint-general on the CVE eval
(category match, grounded%) is the number that answers it.

Other state, unchanged from before:

- **GPU box is ON right now** (`oracle-gpu` / 192.168.1.170, user `arpthef`,
  fish login shell — every remote command goes through
  `ssh oracle-gpu "bash -lc '...'"`) running the ablation eval. Do not launch
  anything else on it until `EVAL_GENERAL_DONE` shows in `eval_general.log`.
- Gate: frozen GraphCodeBERT embeddings + 14 Kamei metrics + LightGBM, AUC
  **0.8293** (`artifacts/gate.joblib`), counting baseline 0.638. No regressions.
- `INFERENCE_SAMPLES=3` consensus is the default in `config.py`.

# Uncommitted at handoff

Local working tree has changes from the guard-phase overshoot investigation,
never committed:

- `corpus/label.py` — adds `cap_per_language()`, seeded with per-language
  counts already in the output file, so a resumed run stops at the true
  `--per-language N` instead of re-capping N more on top of what's already
  kept. This is the fix for the 480→662 overshoot.
- `dashboard.sh` — guard-phase total now computed from what's actually on
  disk per language (`awk` over `labelled_guards.jsonl`) instead of a fixed
  480, since the corpus can legitimately end up bigger than the nominal
  target; also widened the eval-progress log glob to pick up `eval*.log`
  (needed once `eval_general.log` existed, not just `detect*.log`/`cve*.log`),
  and fixed the training-progress grep pattern.
- `run_phase2.sh` (untracked) — start/stop wrapper for the labelling watchdog,
  superseded now that both phases are done; keep or delete, wasn't reused this
  session.

Worth a commit once the ablation eval's numbers are in, same session or next.

# Decisions made (do not relitigate)

- **Small goal**: perfect the 8-language BASIC-code slice (the mined corpus)
  first. Framework idiom (next.js / react) is a LATER phase — the rules already
  exist in `llm_explainer/context.py` (`detect_framework`, `FRAMEWORK_RULES`).
- Do NOT switch the teacher to deepseek — the user vetoed it.
- The user's professor rejects "previous ML methods" (no XGBoost family). The
  narrative: the LightGBM head is infrastructure, the method is the gate→LLM
  cascade plus the eval framework. Contingency if pushed: the contrastive
  encoder (`ml_model/contrastive.py`, 27,798 pairs in
  `data/contrastive_pairs.jsonl`, tokenizer at `artifacts/code_bpe.json`) —
  started, then killed per the user's pivot. Offer it, do not assume it.
- Keep the ApacheJIT gate numbers (0.8293) as-is.
- Labelling runs locally and talks only to Groq; the GPU box is irrelevant to it.
  Labelling itself is now DONE — no more Groq budget needed for the small goal.

# Next steps, in order

**Step 0, first thing: check the ablation eval.**

    ssh oracle-gpu "tail -5 ~/oracle/eval_general.log"

`EVAL_GENERAL_DONE` at the end means all three stages landed
(`data/eval_sft_general.jsonl`, `data/detect_sft_general.jsonl`,
`data/cve_sft_general.jsonl` on the GPU box). If not done and nothing is
running (`ssh oracle-gpu "pgrep -af evaluate.py"` empty, watch the self-match
trap below), the job died — relaunch:

    ssh oracle-gpu "bash -lc 'cd ~/oracle && setsid nohup bash -c \"
      .venv/bin/python evaluate.py --backend transformers --model artifacts/sft-adapter-general/checkpoint-136 --name sft-general --out data/eval_sft_general.jsonl
      .venv/bin/python evaluate.py --backend transformers --model artifacts/sft-adapter-general/checkpoint-136 --heldout data/detect_eval.jsonl --limit 1000 --name sft-general-1k --out data/detect_sft_general.jsonl
      .venv/bin/python evaluate.py --backend transformers --model artifacts/sft-adapter-general/checkpoint-136 --heldout data/cvefixes_eval.jsonl --limit 1000 --name cve-general --out data/cve_sft_general.jsonl
      echo EVAL_GENERAL_DONE
    \" > eval_general.log 2>&1 < /dev/null &'"

1. **Write up the ablation comparison** in RESULTS.md against the
   checkpoint-204 table (already there). This decides whether the guard
   corpus was worth the ~2.75 days of budget it cost, and whether the paper's
   "guard corpus" framing holds.

2. **Commit the uncommitted files** (see above) — the per-language cap fix
   is worth keeping regardless of the ablation's outcome.

3. **DPO on the winning adapter**, `./finish_training.sh` (~1-3h) — picks
   whichever of checkpoint-204 / checkpoint-general the ablation favors, or
   204 by default if the ablation is a wash (it has the guard-class signal
   the paper's defect story turns on, per RESULTS "Guard share by category").

4. **Eval the small goal** end to end: grounding, category accuracy,
   `cve_quality` against human CVE text, per-language separation (TS was
   -16.7pp on the old corpus), and re-test the divide-by-zero Go case that
   motivated the guard mining. Run `count_control.py` beside every detection
   number.

5. **Serve + TUI on a mined repo**, then the cascade measurement: gate/LLM
   disagreement rate on `detect_eval`.

# Operational notes

- Local venv `.venv/bin/python`, always. Keys: `~/.zshrc` exports
  `GROQ_API_KEY1..6` and `DEEPSEEK_API_KEY`; `/tmp/opencode/keys.env` holds
  the same exports for background launches. Labelling is done, so these
  mostly don't matter anymore for the small goal.
- `pkill`/`pgrep` self-match trap: a remote command whose own cmdline contains
  the search pattern (e.g. `ssh ... "pgrep -af evaluate.py"`) matches itself.
  Prefer `nvidia-smi --query-compute-apps=...` to check whether the GPU is
  actually busy, it doesn't have this problem.
- Editing a script while it runs on the GPU box: write a temp file and `mv` it
  into place, never `sed -i` — a running bash re-reads its script by byte
  offset.
- A failed input redirect cannot be muted by `2>/dev/null` on the same command
  (`wc -l < "$MISSING" 2>/dev/null`) — the shell reports it before that redirect
  takes effect. Wrap it: `{ wc -l < "$F"; } 2>/dev/null`.
- Run `count_control.py` beside every detection number.
- Long GPU jobs: launch with `setsid nohup ... < /dev/null &` from the GPU box
  shell so they survive the local machine disconnecting or shutting down —
  confirmed working for the ablation eval, session's local device was shut
  down mid-run without affecting it.
