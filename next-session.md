Continue ORACLE at ~/Documents/oracle. Read docs/RESULTS.md first (every
measurement + the command that reproduces it), then docs/ROADMAP.md and
docs/DATASETS.md, and run ./status.sh.

# Something is running right now

GraphCodeBERT is being fine-tuned end to end on the GPU box. It was launched
detached, so it is unaffected by any editor or agent session closing:

    ssh oracle-gpu "bash -lc 'cd ~/oracle && PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True nohup .venv/bin/python -m ml_model.train_encoder --jsonl data/apachejit_commits.jsonl > ~/oracle/encoder_full.log 2>&1 &'"

Monitor it:

    ssh oracle-gpu "bash -lc 'pgrep -af \"ml_model[.]train_encoder\"'"
    ssh oracle-gpu "bash -lc 'tr \"\r\" \"\n\" < ~/oracle/encoder_full.log | grep -E \"commits,|epoch |best |model ->|Error|Traceback\"'"

There is no per-step progress bar — the script prints one line per epoch and
runs 4 epochs over 6391 training commits at 512 tokens, so expect long silences.
`nvidia-smi` through `./status.sh` is the liveness check in between: ~3.5 GB
used and 100% utilisation means it is working.

What the run is for: the deployed gate freezes GraphCodeBERT and fits LightGBM
on its embeddings. This trains the encoder on the defect label instead. Compare
its AUC / PR-AUC against the numbers already in RESULTS §3, on the identical
chronological 80/20 split (test n=1598):

| variant | AUC | PR-AUC |
|---|---|---|
| counting baseline | 0.638 | 0.363 |
| metrics only | 0.777 | 0.660 |
| frozen embeddings + metrics (deployed) | 0.822 | 0.699 |
| fine-tuned encoder + metrics | *this run* | |

If it beats 0.822, it is the paper's Stage 1 and `artifacts/gate-encoder` becomes
the gate. If it does not, say so — the frozen gate stays and the negative result
is worth a sentence. An earlier attempt at this run died silently after loading
1164 commits (a stale corpus copy) and was never measured; `~/oracle/encoder.log`
still holds that dead run, the live one is `encoder_full.log`.

# Where the project stands

The two-stage framing is the paper: a classifier detects, an LLM explains.
Title is settled — "Predict, Then Explain: Just-In-Time Defect Prediction with
Natural-Language Findings". Do NOT use "Explainable JIT"; it is taken by
PyExplainer / JITLine and it means feature attribution, which is not what this
does.

Stage 1 works. The gate scores AUC 0.822 on ApacheJIT (n=1598) against a
counting baseline of 0.638 and metrics-only 0.777, so reading the code adds
+0.045. That is the first real positive result in the project.

Stage 2 is weaker. checkpoint-220 beats stock on ApacheJIT detection —
separation +21.0pp vs +11.6pp, difference +9.5pp CI [+2.0, +17.0] p=0.007,
McNemar p=0.017 — but neither beats the always-buggy F1 of 0.665, and the LLM
cannot detect out of distribution. Its measured strength is grounding (99.8%).

# The two known weaknesses, and their one cause

The model cannot recognise Java RCE-class vulnerabilities, and it reads
JavaScript/TypeScript framework code badly. Both come from the training corpus,
not the recipe: `data/labelled.jsonl` is 1959 Apache commits, 3083 `.java` files,
ordinary defects, teacher-labelled. It contains no security material and no
`.ts`/`.tsx` at all. RESULTS §2.2 already shows the consequence — TypeScript
separation −16.7pp, JavaScript −7.1pp, both worse than chance.

CVEfixes is the obvious security source, and it holds 583 Java, 1302 JavaScript
and 767 TypeScript fix commits. It cannot supply framework knowledge, though:
the whole Next.js ecosystem (`vercel/next.js`, `next-auth`, `nextjs-auth0`)
amounts to 10 fix commits in the entire database.

# Settled this session: the paired construction cannot be repaired

Roadmap item 4 proposed matching pairs on `+`/`-` balance to remove the leak
that lets `wc` score AUC 0.934 on `cvefixes_eval.jsonl`. It was implemented as
`corpus/cvefixes.py --balance N` and measured. It does not work:

| filter | pairs kept | counting-control AUC |
|---|---|---|
| none | 500 | 0.934 |
| \|Δlines\| ≤ 10 | 738 | 0.920 |
| \|Δlines\| ≤ 3 | 364 | 0.895 |

Line counts balance to a mean of exactly 0.00 and the AUC barely moves, because
`plus-minus chars` alone still scores 0.880 — a fix adds *longer* lines even when
it adds the same number of them. Any asymmetry survives the mirror, so no filter
on one feature can close it.

Conclusion to carry into the paper: CVEfixes is an explanation benchmark with
human-written ground truth, and it is not a detection benchmark. Stop trying to
make it one. Reproduce with:

    python count_control.py data/cvesec_train.jsonl 0.8

# Uncommitted work from this session

Nothing here is committed. The repo still has one "initial commit" and ~35
untracked files.

- `corpus/cvefixes.py` — new `--cwe CWE-502,CWE-94` filter (joins
  `cwe_classification`), new `--balance N` filter, and the summary now prints
  the CWE histogram and mean plus-minus.
- `corpus/cvefixes.py` — the clean-side SFT target was one fixed sentence, which
  is what collapsed `sft-cve` (half the targets byte-identical, loss near zero,
  one distinct output across all 1000 eval records, ten GPU hours wasted). It now
  restates that record's CVE, so every negative target is distinct and still
  cannot be produced without reading which way the diff moves.
- `dataset_builder/build_sft_data.py` — `distinct_targets()`, called from
  `write_jsonl`, prints how many distinct assistant turns a file has and warns
  loudly when one string is ≥20% of targets. Never train on a file that trips
  this warning.
- `data/cvesec_train.jsonl` (214 pairs) and `data/cvesec_eval.jsonl` (150 pairs)
  — Java + JavaScript + TypeScript, repo-disjoint from each other, balanced
  diffs, CWE-79/22/78/89/1321 heavy. Built with the `--balance 3` filter, so per
  the table above they still carry the counting leak. Usable as explanation
  material, not as a detection benchmark.

# What to do next, in order

1. Read out the encoder run above and add it to RESULTS §3.
2. Mine real multi-language commits. `corpus/mine.py` already derives SZZ labels
   from any git repository and already lists `vercel/next.js` first in
   `DEFAULT_REPOS`; `data/mined.jsonl` is empty because the runs never finished.
   The bottleneck is that `--filter=blob:none` makes `git blame` fetch blobs over
   the network one at a time. Clone the target repos fully once and blame
   locally. This is the only path to both a non-Java gate and JS/TS training
   data, so it unblocks most of what is left.
3. Retrain the explainer for security on the `intro` direction only, with
   negatives drawn from the mined real commits rather than from reversed fixes.
   No mirrors means no counting leak and no identical-target collapse — it fixes
   both known failures of `sft-cve` at once. Check `distinct_targets()` output
   before spending the GPU. Roughly 10 GPU hours.
4. Framework idiom does not belong in the weights. A 3B Qwen2.5-Coder does not
   know Next.js server actions or route handlers, and 214 pairs will not teach
   it. Detect the framework and state its rules in the prompt through
   `llm_explainer/context.py`, which already assembles the surrounding-code
   block. Costs no GPU.
5. Still never measured, and it is acceptance criterion 4: explanation quality
   against the human CVE text. `data/cve_sft220.jsonl` and `data/cve_stock.jsonl`
   already hold 754 and 851 findings beside the CVE descriptions that are their
   ground truth. The inference is already paid for.
6. Gate/LLM disagreement rate on `detect_eval` — two independent verdicts, which
   no prior JIT work has had.
7. Commit the repo.

Deferred: the unhinted ApacheJIT relabel (~34 GPU hours). A 120B teacher scores
F1 0.49 there, below the 0.63 baseline, so the signal is not in the diff.

# Operational notes

- The GPU box is `oracle-gpu` (192.168.1.170, user `arpthef`). Its login shell is
  fish, so every remote command must go through `ssh oracle-gpu "bash -lc '...'"`.
- Remote code lives at `~/oracle`, local code at `~/Documents/oracle`. There is
  no sync script; local edits do not reach the box on their own.
- Always `.venv/bin/python`, never system python, on both machines.
- `pkill -f llm_explainer.serve` over ssh kills its own wrapper shell, because
  the pattern matches the `bash -lc` command string, and ssh then exits 255.
  Quote it as `pkill -f "llm_explainer[.]serve"`.
- The card is 6 GB. Nothing else can be resident while training runs — the
  explainer server alone holds 2.2 GB.
- To use the TUI, serve the model on the box and tunnel to it. This is off right
  now, deliberately, so the encoder run has the whole card:

      ssh oracle-gpu "bash -lc 'cd ~/oracle && nohup .venv/bin/python -m llm_explainer.serve --port 8111 > ~/oracle/serve.log 2>&1 &'"
      ssh -f -N -L 8111:localhost:8111 oracle-gpu
      ORACLE_BACKEND=ollama ORACLE_OLLAMA_HOST=http://localhost:8111 .venv/bin/python main.py tui --repo .

- `GROQ_API_KEY` is in `~/.zshrc` (free tier, 8000 TPM, needs `--workers 1
  --sleep 18`).
- Run `count_control.py` beside every detection number. A model that does not
  clear it has learnt to count lines.
