# The hand-grading job

**109 judgements, two files, no GPU and no server needed.** This is the only
human validation the paper has. Every "grounded" and "invents" number in
`RESULTS.md` is produced by a regex rubric written in an afternoon, and the
agreement between that rubric and a person has never been measured. Until it is,
a reviewer asking "how do you know your rubric measures what you say it does"
has no answer.

Both packets are drawn from `v3plain_fix_v2` -- the arm the paper actually cites.
The earlier packets came from `bip_arm_exec.json`, which is n=264 and a
superseded checkpoint, so grading those would have measured agreement on output
nobody reports.

---

## Job 1 -- 50 random cases (~1 hour)

Read:   `data/bip_rater_packet_v3.md`
Fill:   `data/bip_rater_v3.csv`     (columns: id, grounded, invented, direction)

Each case shows a real commit, what the project's own failing test reported
before and after it, and what the model said. **The before/after is ground
truth** -- it came from running the test. You are not checking the measurement.
You are checking the sentence against it.

| column | question | `y` when |
|---|---|---|
| `grounded` | does it state what the program actually did? | it names the real failure, or quotes a distinctive part of the real message |
| `invented` | does it assert a failure that never happened? | it names an exception nothing raised, or an outcome the run contradicts |
| `direction` | does it get the change the right way round? | the before/after are not swapped, and a move is described in the direction it actually went |

**`direction` is the most valuable column and the reason this cannot be
automated.** Nothing in the pipeline can see an inversion: `direction_reversed`
compares against the measured before/after, which on this corpus are "a failure"
and "the test passed", so a backwards explanation still scores grounded.
Worked example, `tqdm-1`: the fix moves `start` from `tqdm_class` to
`enumerate`; the model wrote "moved from the `enumerate` call to the
`tqdm_class` constructor", which is backwards, and it scored grounded anyway
because it quoted the real TypeError. That is `direction: n`, `grounded: y`.

Accepted values: `y` / `n` (also yes/no, 1/0). **Leave blank when unsure. A
blank is data; a guess is noise.**

Then:

    .venv/bin/python bench/bugsinpy_rater.py --score data/bip_rater_v3.csv \
        --arm v3plain_fix_v2 --rows data/bugsinpy_rows_v2.jsonl

## Job 2 -- 59 flagged inventions (~30 min)

Read:   `data/bip_invention_packet_v3.md`
Fill:   `data/bip_inventions_v3.csv`   (case, id, arm are pre-filled; type only `invented`)

One yes/no per row: does this explanation assert a failure the measurement
contradicts or never showed? `n` means the rubric is wrong here -- the named
failure IS in the measurement, or the sentence is hedged enough not to assert
it.

All 9 of `v3plain_fix_v2`'s flagged inventions are here, uncapped, because those are
the ones the headline depends on. `diff_fix_v2` and `score_fix_v2` are sampled at 25
each, so the contrast they support is an estimate with a stated n rather than a
census. The arm is shown because it is not blindable -- the prompts differ
visibly. What is withheld is which class the rubric thought was invented.

**Grade by `case` number, not by id.** 11 rows appear in two arms, and an answer
sheet keyed by id alone merges them, so one judgement would land on two
different sentences. The `arm` column keeps them apart.

Then:

    .venv/bin/python bench/bugsinpy_rater.py --score data/bip_inventions_v3.csv \
        --arm v3plain_fix_v2 --rows data/bugsinpy_rows_v2.jsonl

---

## What comes out

Cohen's kappa and raw agreement between the rubric and you, per field, plus the
`direction` rate which has no rubric counterpart at all. Any of these is
reportable:

* **high agreement** -- the rubric stands, and the paper says so with a number
  instead of hoping
* **low agreement** -- better to find that now than in a viva, and the
  disagreements name exactly which rubric rule is wrong
* **a bad `direction` rate** -- the strongest limit the paper can state about
  its own headline, and the only way to state it honestly

## Notes

* `data/*.csv` is gitignored, so your answers stay local until deliberately added.
* Both packets are blinded: the rubric's verdict and its per-check flags are not
  in them, so you cannot agree with it for the wrong reason.
* Regenerate either packet with `--emit` / `--emit-inventions`; the `--seed 7`
  sample is stable, so a regeneration gives the same cases.
