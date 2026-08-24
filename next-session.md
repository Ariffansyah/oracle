Continue ORACLE at ~/Documents/oracle. Read `docs/RESULTS.md` first (every
measurement plus the command that reproduces it; the rendering-variance
sections qualify every other number in the file — the n=200 one supersedes the
n=40 one), then `docs/ROADMAP.md`.

**First action this session:** commit the working tree — see "Next steps",
step 3. Seven files have been uncommitted across three sessions, including two
finished measurements.

# The project

Two-stage JIT defect prediction. Title settled: "Predict, Then Explain:
Just-In-Time Defect Prediction with Natural-Language Findings". Stage 1 is a
gate classifier that detects buggy commits; Stage 2 is a fine-tuned 3B LLM that
verifies and explains. Base model Qwen2.5-Coder-3B-Instruct, QLoRA SFT on
teacher-labelled data (gpt-oss-120b on Groq is the teacher, the 3B is the
student). Do NOT use "Explainable JIT" — taken by PyExplainer / JITLine.

# Current state (24 Aug 2026, 12:00)

**DPO is DONE.** Third attempt succeeded: 23/23 steps in 1h25m, no OOM,
merged 23 Aug 11:46 to `artifacts/oracle-merged` on the box. The stale 13 Aug
merge it replaced is gone.

What made it fit — and note the old handoff's proposed fix would *not* have
worked on its own:

- `LORA_TARGET_MODULES` was hardcoded at `config.py:57`, so the handoff said
  to edit it. But `train_dpo.py:154` passes `peft_config=None` when continuing
  from an SFT adapter, so the loaded adapter's own r=64/7-target config is what
  applies and the edit does nothing. The target list is now env-overridable
  (`ORACLE_LORA_TARGET_MODULES`), default unchanged.
- The fix that worked: merge the SFT adapter to fp16 weights, then align a
  fresh small LoRA on top with `--from-base`.

      # artifacts/sft-merged, 6.2 GB, ~3 min
      .venv/bin/python -c "
      from fine_tuning.qlora import merge_adapter
      from config import BASE_MODEL, SFT_ADAPTER_DIR, ARTIFACTS
      merge_adapter(SFT_ADAPTER_DIR, ARTIFACTS/'sft-merged', BASE_MODEL)"

      cd ~/oracle && PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
        ORACLE_LORA_R=16 ORACLE_LORA_ALPHA=32 \
        ORACLE_LORA_TARGET_MODULES=q_proj,k_proj,v_proj,o_proj \
        nohup .venv/bin/python -m fine_tuning.train_dpo --from-base \
        --base-model artifacts/sft-merged --epochs 1 --merge > dpo.log 2>&1 &

`artifacts/sft-adapter` and `artifacts/sft-adapter/checkpoint-204` are the same
weights (md5 `35de53ff…` on both `adapter_model.safetensors`), so this trained
on checkpoint-204 as decided. Resulting DPO adapter: r=16, alpha=32,
`[k_proj, o_proj, q_proj, v_proj]`, base `artifacts/sft-merged`.

Side effect worth knowing: the reference model is now the SFT policy, not the
raw base. The old path (`ref_model=None` + attached adapter) referenced the
*unfinetuned* base, which `train_dpo.py:12` describes as intended but is not
standard DPO. Merging fixed that incidentally.

DPO loss at the four logging points (steps 5/10/15/20):

| epoch | loss | rewards/chosen | rewards/rejected | margins | accuracies | grad_norm |
|---|---|---|---|---|---|---|
| 0.22 | 1.863 | 0.0029 | -0.0039 | 0.007 | 0.425 | 18.3 |
| 0.44 | 1.754 | 0.028 | -0.077 | 0.105 | 0.95 | 20.1 |
| 0.67 | 1.743 | 0.065 | -0.200 | 0.264 | 1.00 | 13.1 |
| 0.89 | 1.575 | 0.147 | -0.442 | 0.589 | 1.00 | 11.8 |

`rewards/chosen` stays positive and climbs while rejected falls — the
`sigmoid,sft` anchor did its job (the classic DPO failure is both dropping
together). Entropy and `mean_token_accuracy` are flat, so JSON format
adherence did not degrade. The thing not to gloss over: `rewards/accuracies`
hits 1.00 by step 15, which says the mock preference pairs are close to
trivially separable.

**Correction to the previous handoff.** It claimed the clipped `grad_norm`
(11.8–20.1 against HF's default `max_grad_norm=1.0`) had pushed the effective
learning rate below the 5e-6 schedule. **That was wrong and is disproved.**
`max_grad_norm` is now a knob (`DPO_MAX_GRAD_NORM`, default 25.0) and the run
was repeated above the observed gradient range: the loss curve moved by less
than a rounding error. `paged_adamw_8bit` normalises by `g/sqrt(v)`, so Adam is
scale-invariant to a uniform gradient rescale. Clipping was never the lever.
Full table in RESULTS.md, "DPO retrain: the clipping hypothesis, eliminated".

**DPO changed nothing measurable — confirmed three times.** Greedy output
(`INFERENCE_SAMPLES=1`) from `sft-merged`, `oracle-merged` (23 Aug) and
`oracle-merged-v2` (24 Aug) is byte-identical on `data/go_race_case.diff`,
with `sft-merged` run twice as a determinism control. All three miss the
verified data race.

**Real preference pairs do not fit this card.** `from_labelled()` over all
1,673 records yields 525 grounded pairs, of which **0 fit under
`DPO_MAX_LENGTH=512`** — the shortest is 615 tokens, the median prompt 1235
against the mock set's 414. 61% would need `max_length=1536`; the card OOMs at
768. Independently, all 525 pairs share one hardcoded rejected string, so the
objective is degenerate even if it fit. `from_labelled()` is not wired into
`build_dpo_data.main()` at all. **Recommendation: stop spending on DPO** and
report the null. Details in RESULTS.md.

**The headline finding: the model's verdict is unstable to cosmetic
reformatting.** Full writeup in RESULTS.md; the short version:

    verdict agreement    87.7%   (100/114)
    category agreement   85.1%   (97/114)
    commits unanimous    72.5%   (29/40)

Per-rendering detection on the *same* 40 commits with the *same* model:
F1 ranged **0.080 (rehash) to 0.312 (bare_hunk), a spread of 0.233**, from
edits that touch git metadata only and change no line of code. The
guard-corpus ablation turns on a 0.04 F1 gap — roughly six times smaller than
the noise. §4's "neither run was seed-repeated" caveat is now the main event.

This was found by accident: the TUI cleared a Go commit containing a textbook
data race (`go run -race`: 4 warnings; 1 run in 20 loses a record). Chasing it
ruled out, in order, DPO (SFT misses it identically), the TUI (the CLI
reproduces it), and the with-context path (I claimed this and was wrong) —
before the perturbation test showed the real answer.

Everything else, unchanged from the last handoff: labelling done both corpora
(1,011 + 662 = 1,673 records); the ablation verdict stands (guard corpus did
not earn its budget, guard *mining* raised guard-class share 28.4% → 33.9%,
keep the two claims separate); gate AUC **0.8293**; `INFERENCE_SAMPLES=3`
(but see Operational notes — that path is *not* deterministic); DPO does not
fit this card on real pairs, from either source (0 of 115 on-policy under 460
tokens, 0 of 525 `from_labelled` under 512).

# Next steps, in order

**~~1. The 200-commit variance run.~~ DONE (24 Aug).** 800/800 rows in
`data/variance200.jsonl`, zero dropped. Verdict agreement **89.2%**, commits
unanimous **77.5%**, per-rendering **F1 spread 0.088** (0.329 `no_index` to
0.417 `bare_hunk`). The n=40 spread of 0.233 was mostly small-sample noise and
should not be quoted again — but 0.088 is still 2.2x the 0.04 guard-corpus gap,
so the variance column is still mandatory and §4's conclusion is unchanged.
Re-report anytime with `variance.py --score data/variance200.jsonl` (no GPU).

**~~2. Evaluate the DPO model.~~ DONE (24 Aug), null confirmed.** A retrain
with the clipping fix (`artifacts/oracle-merged-v2`) produces greedy output
byte-identical to both `oracle-merged` and `sft-merged`. See the corrected DPO
section above; the clipping hypothesis is disproved and real pairs do not fit
this card. **Do not spend more GPU on DPO** without a >=16GB card and a
non-degenerate rejected side.

**3. Commit the working tree** (see "Uncommitted at handoff"). This is now the
first action of the session.

**4. Smoke-test and pull the merged model** if you want it locally:

       ssh oracle-gpu "cd ~/oracle && .venv/bin/python main.py analyze --backend transformers --no-gate --json | tail -12"
       rsync -az oracle-gpu:~/oracle/artifacts/oracle-merged/ artifacts/oracle-merged/

   6.2 GB. Note the local venv has **no** `peft`/`torch`-GPU stack (see
   Operational notes), so local serving means the merged model or Ollama.

**5. Eval the small goal** end to end: grounding, category accuracy,
`cve_quality` against human CVE text, per-language separation (TS was -16.7pp
on the old corpus), and re-test the divide-by-zero Go case that motivated the
guard mining. Run `count_control.py` beside every detection number.

**6. Serve + TUI on a mined repo**, then the cascade measurement: gate/LLM
disagreement rate on `detect_eval`.

# Uncommitted at handoff

Only these six, all modified, nothing untracked. The previous handoff also
listed `variance.py`, `test_model_label.py`, `ui/tui_app.py` and
`ui/commands.py` here — those were committed in `d8d20aa` and the list was
stale.

- `config.py` — `LORA_TARGET_MODULES` now reads `ORACLE_LORA_TARGET_MODULES`
  (was a hardcoded list, default unchanged), plus `DPO_MAX_GRAD_NORM`
  (default 25.0) at line 93.
- `fine_tuning/train_dpo.py` — `--max-grad-norm` flag, passed to `DPOConfig`.
  Previously unset, so HF's default of 1.0 applied silently.
- `dashboard.sh` — new `variance` row (progress + live agreement rate, own
  stall check for a dropped tunnel); `serve` row now names the served model,
  not just the port; `sft-merged` added to the artifact timestamps; watchdog
  row no longer shows red once the corpus is complete (it cried wolf for days,
  which is how a real red gets ignored). Plus the three earlier fixes from the
  last handoff, still uncommitted. Note its stall check still cannot tell a
  finished run from a dead one — see Operational notes.
- `evaluate.py` — carried over from the previous handoff, still uncommitted.
- `docs/RESULTS.md` — the variance section, plus three new ones (24 Aug):
  n=200 variance, the eliminated clipping hypothesis, and the real-pair
  token audit.
- `next-session.md` — this file.

New artifacts on the box, not synced locally: `artifacts/dpo-adapter-v2` and
`artifacts/oracle-merged-v2` (6.2 GB). `oracle-merged` was deliberately *not*
overwritten — the 200-commit variance numbers were measured on it and must stay
reproducible. Also on the box: `run_dpo2.sh`, `cmp3.sh`, `cmp_greedy.sh`,
throwaway launchers, delete when convenient.

# Known-stale comments worth fixing

In `fine_tuning/train_dpo.py`:

- The `padding_free=True` comment (~line 167) claims it saves about a quarter
  of the activation memory. **Confirmed dead** — TRL 1.9.2 prints
  `[RANK 0] padding_free=True is temporarily unavailable after a refactor and
  is currently disabled` on every run. The flag is a no-op and the saving is
  gone.
- The comment below it says prompts run 751–1132 tokens, median 751. The
  measured DPO set is 414 median, 476 p90, 795 max. `config.py:60` is correct.
- `truncation_mode="keep_end"` now warns it is deprecated and removed in TRL
  v2.0.0.

# Operational notes

- **Training runs on `oracle-gpu`, never locally.** The local venv has no
  `trl`/`peft`/`datasets`/`accelerate`/`bitsandbytes`, and this laptop's GPU is
  an AMD Radeon 680M with no ROCm stack — `torch.cuda.is_available()` is
  False. Installing the training deps locally drags in a CPU torch that
  replaces the CUDA wheel; if that happens, restore with
  `pip install --force-reinstall torch==2.13.0 --index-url https://download.pytorch.org/whl/cu130`
  and re-pin `fsspec<=2026.6.0`.
- `./serve.sh start` did not open the tunnel — the server came up on the box
  but `status` reported `tunnel: down`. Open it by hand, with keepalive for
  long runs:

      ssh -f -N -L 8111:localhost:8111 -o ExitOnForwardFailure=yes \
          -o ServerAliveInterval=30 -o ServerAliveCountMax=1000 oracle-gpu

- The `pkill`/`pgrep` self-match trap is real and `serve.sh:29` warns about it:
  killing and launching the server **in one ssh call** makes `pkill` match the
  launch command's own cmdline and kill the new server. Two separate calls.
- To A/B two models, restart the server with `--model artifacts/<dir>`; the
  port is unchanged, which is why the dashboard now prints the served model
  name.
- `evaluate.py:116` sends the **bare diff** (`client.analyze`, no snapshots,
  no `-U50`). Every published number is therefore a no-context number, while
  the TUI and `main.py analyze --commit` default to the *with-context* path,
  which has never been evaluated. Closing that gap needs local checkouts of
  apache/cassandra-scale repos, since heldout records carry only
  `project` + `commit_id` + diff text.
- Long GPU jobs: launch with `setsid nohup ... < /dev/null &` from the GPU box
  shell so they survive the local machine disconnecting.
- The `ssh ... "cd ~/oracle && cmd &"` shape puts only the backgrounded half in
  `~/oracle`; anything after the `&` runs in the login directory.
- Editing a script while it runs on the GPU box: write a temp file and `mv` it
  into place, never `sed -i` — a running bash re-reads its script by byte
  offset.
- A failed input redirect cannot be muted by `2>/dev/null` on the same command.
  Wrap it: `{ wc -l < "$F"; } 2>/dev/null`.
- **The remote shell on `oracle-gpu` is fish.** `VAR=val cmd` prefixes and
  `$!` do not parse there, so the 23 Aug launch command recorded in this file
  fails with exit 127 if pasted through `ssh`. Either write a `bash` script and
  `rsync` it over, or pipe with `ssh oracle-gpu bash -s <<'EOF'`.
- **Three status checks in this repo report intent, not observed state**, and
  all three lied during the 24 Aug session:
  `dashboard.sh` called a *completed* variance run "STUCK" (its stall check
  reads mtime and cannot tell finished from dead); `serve.sh stop` printed
  `tunnel closed` while leaving the local forwarder listening on 8111, which
  then made the next `serve.sh start` fail with `Address already in use`; and
  `serve.sh start` printed "server started" on the launch command returning,
  not on the server answering. Worth one fix pass.
- **`INFERENCE_SAMPLES=3` is not deterministic.** `client.py:453` runs sample 0
  greedy and samples 1..n at `INFERENCE_SAMPLE_TEMPERATURE=0.6`. Any A/B of two
  checkpoints must set `INFERENCE_SAMPLES=1` or it measures the sampler, not
  the model.
- Local venv `.venv/bin/python`, always. Keys: `~/.zshrc` exports
  `GROQ_API_KEY1..6` and `DEEPSEEK_API_KEY`. Labelling is done, so these mostly
  do not matter for the small goal.
- Run `count_control.py` beside every detection number.
- The Go data-race commit that started the variance finding is saved at
  `data/go_race_case.diff`. It is the cheapest end-to-end check there is: the
  model should report `concurrency` on it, and `go run -race` proves the bug
  (4 warnings; 1 run in 20 loses a record). Rebuild a repo from it with
  `git apply` on the pre-image, or just feed it straight in:

      .venv/bin/python main.py analyze --diff-file data/go_race_case.diff --no-gate --json

# Decisions made (do not relitigate)

- **Small goal**: perfect the 8-language BASIC-code slice (the mined corpus)
  first. Framework idiom (next.js / react) is a LATER phase — the rules already
  exist in `llm_explainer/context.py` (`detect_framework`, `FRAMEWORK_RULES`).
- DPO runs on checkpoint-204, not checkpoint-136, despite the ablation. Done.
- Do NOT switch the teacher to deepseek — the user vetoed it.
- The user's professor rejects "previous ML methods" (no XGBoost family). The
  narrative: the LightGBM head is infrastructure, the method is the gate→LLM
  cascade plus the eval framework. Contingency if pushed: the contrastive
  encoder (`ml_model/contrastive.py`, 27,798 pairs in
  `data/contrastive_pairs.jsonl`, tokenizer at `artifacts/code_bpe.json`) —
  started, then killed per the user's pivot. Offer it, do not assume it.
- Keep the ApacheJIT gate numbers (0.8293) as-is.
- Labelling is DONE. No more Groq budget needed for the small goal.
