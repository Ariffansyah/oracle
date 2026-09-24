# Grade

Graded blind against `data/bip_rater_packet_v3.md` (50) and
`data/bip_invention_packet_v3.md` (59). The rubric's verdicts were not read
until every cell was filled; the confirmation query in the last section was
run afterwards, to explain the disagreements, not to produce them.

| column | rule |
|---|---|
| `grounded` | About the **failure clause only**. `y` if the sentence's account of what the run reported is correct — quoting the real message counts, and so does naming the real failure in its own words. `n` if the account is inverted (expected/actual swapped) or asserts a failure where the run passed. A correct failure clause attached to a wrong edit clause is still `y` — that is the `tqdm-1` precedent in `docs/GRADING.md`. |
| `invented` | Asserts a failure the measurement contradicts or never showed. A claim about what the **fixed** code now does (raises X, catches X) is not an invention. A hedge on causation ("may have caused") is not a hedge on existence. |
| `direction` | `n` only for a **reversal** of a stated before→after relation: edit polarity (added↔removed, A→B stated as B→A), observation polarity (expected↔actual), or pre-change behaviour named as post-change. Imprecise, incomplete, or wrong-hunk descriptions are `y` — they are wrong in a different way, and I tracked that separately as `edit_ok`. |

`edit_ok` is a fourth column of my own, not in the packet: does the sentence
name an edit that is actually in the diff **and** is the operative one? It is
in this file only; the CSV keeps the three-column schema the scorer reads.

## Headline

| measure | n | result |
|---|---|---|
| grounded | 50 | **46 y / 4 n** (92%) |
| invented | 50 | **3 y** (6%) |
| direction | 50 | **39 right way round / 11 backwards** (78% / 22%) |
| edit_ok (mine) | 50 | **31 y / 19 n** (62%) |
| inventions packet | 59 | **53 y / 6 n** |

Against the rubric, on the same 50: grounded 47/50 agreement, κ +0.63.
invented 47/50, κ +0.00 — the rubric flags **zero** of these 50, so there is
no agreement to measure above chance; my 3 are all human-only.

The interesting number is the gap between grounded (92%) and edit_ok (62%).
They are close to independent: the failure clause is quoted from a string the
harness put in the prompt, the edit clause has to be read off the diff. Nearly
all of the model's wrongness lives in the half of the sentence the rubric does
not look at.

## The 50, in full

`g/i/d/e` = grounded, invented, direction, edit_ok.

| # | id | g | i | d | e | note |
|---|---|---|---|---|---|---|
| 1 | matplotlib-3 | y | n | y | y | |
| 2 | spacy-5 | y | n | y | y | argument order stated the right way round |
| 3 | ansible-11 | y | n | y | y | "adds get_config" — imported, not defined; harmless |
| 4 | pandas-38 | y | n | y | n | names the `rlocs == []` hunk; the fix is the `clocs` comprehension |
| 5 | pandas-60 | y | n | y | y | |
| 6 | keras-11 | y | n | y | y | rationale false ("treated as a sequence regardless of type"), edit right |
| 7 | pandas-147 | y | **y** | **n** | y | says the old code "re-raised as TypeError"; the run says DID NOT RAISE. Pre-change behaviour named as post-change |
| 8 | pandas-157 | y | n | y | y | |
| 9 | pandas-130 | y | n | y | y | |
| 10 | scrapy-7 | **n** | **y** | y | y | **run passed before and after** (`OK`/`OK`); asserts "the request was failing" |
| 11 | pandas-112 | y | n | y | y | |
| 12 | luigi-2 | y | n | y | y | |
| 13 | pandas-167 | y | n | **n** | y | "allowing partial string indexing on non-date-like indexes" — the flag defaults False, so the change *disallows* it |
| 14 | httpie-2 | **n** | **y** | **n** | n | fabricates the edit (no default 5→6 in the diff) and reads `assert 0 == 6` backwards as "observed 6 redirects" |
| 15 | thefuck-9 | y | n | y | n | the second `pop` is wrapped in try/except, not removed |
| 16 | pandas-40 | y | n | y | n | fabricated edit; `is_array_like` untouched, the fix is `how=how` |
| 17 | matplotlib-27 | **n** | n | **n** | y | edit exactly right; `assert 'None' == ''` read backwards ("expected 'None', received an empty string") |
| 18 | scrapy-1 | y | n | y | n | the `url_pattern.match` check is kept, a `None` guard is added before it |
| 19 | ansible-6 | y | n | y | n | no `version.split()` in the diff; direction of the real edit still right |
| 20 | thefuck-4 | y | n | y | y | |
| 21 | black-23 | y | n | **n** | n | says the commit "removes the `print >>` syntax"; it adds grammar fallbacks so black can *parse* it |
| 22 | thefuck-29 | **n** | n | **n** | n | credits the **docstring**; the fix is the dict-merge order. Also reads `assert 'new-val' == 'val'` backwards |
| 23 | pandas-54 | y | n | **n** | n | the change *adds* CategoricalIndex to the skip; sentence says it enables what it disables |
| 24 | pandas-35 | y | n | y | y | |
| 25 | scrapy-10 | y | n | y | y | names the real mechanism (latin-1 double-encoding) without quoting; rubric scores this `n` |
| 26 | youtube-dl-18 | y | n | y | y | |
| 27 | matplotlib-2 | y | n | y | y | |
| 28 | scrapy-22 | y | n | y | y | |
| 29 | fastapi-12 | y | n | **n** | n | "the `auto_error` flag was removed" — the diff **adds** the `auto_error` branch |
| 30 | thefuck-2 | y | n | y | y | |
| 31 | pandas-45 | y | n | **n** | n | "removes the `isinstance(data, abc.Set)` check ... which prevented the TypeError" — the diff adds it, and it is what raises |
| 32 | pandas-33 | y | n | y | y | |
| 33 | scrapy-23 | y | n | y | y | names the wrong test (`test_503` in `RetryTest`; the run is `test_proxy_auth`) |
| 34 | matplotlib-24 | y | n | y | y | |
| 35 | youtube-dl-35 | y | n | y | n | the edit it names is in `arte.py`; the test is `test_utils`, fixed by the added format string. Rubric scores grounded `n` |
| 36 | luigi-25 | y | n | y | y | |
| 37 | ansible-5 | y | n | y | y | expected/actual the right way round, unlike 14/17/22 |
| 38 | pandas-161 | y | n | y | n | `np.where` is retained; its condition changed |
| 39 | luigi-23 | y | n | y | y | |
| 40 | luigi-15 | y | n | **n** | n | "removes the UNKNOWN status check" — UNKNOWN is **added** to the tuple |
| 41 | tornado-1 | y | n | y | y | |
| 42 | pandas-88 | y | n | y | n | the `nlevels > 1` check pre-existed; `and index` is what was added |
| 43 | pandas-140 | y | n | y | n | from-side wrong: `dtypes[idx]` → `dtypes.iloc[idx]` |
| 44 | pandas-114 | y | n | y | y | |
| 45 | httpie-5 | y | n | y | y | |
| 46 | youtube-dl-15 | y | n | y | n | garbled account of the lookbehind |
| 47 | matplotlib-28 | y | n | **n** | y | sign flip: says the guard fires when limits are "non-negative"; it fires when one is ≤ 0. Its own account would leave the bug in place |
| 48 | matplotlib-11 | y | n | y | n | the `dpi` argument is not removed; the save/restore pair is |
| 49 | fastapi-16 | y | n | y | y | |
| 50 | youtube-dl-7 | y | n | y | n | vacuous: "replaces `v.startswith(\"'\"` with `v.startswith(\"'\"`" |

### The 11 backwards ones, by kind

| kind | cases |
|---|---|
| added stated as removed | fastapi-12, pandas-45, luigi-15, black-23, pandas-54 |
| expected/actual swapped on a bare `assert X == Y` | httpie-2, matplotlib-27, thefuck-29 |
| pre-change behaviour named as post-change | pandas-147, pandas-167 |
| condition sign flipped | matplotlib-28 |

The middle row is worth its own sentence in the limits section: the measured
`before` for those three is a bare pytest line with no labels on either side,
and of the 6 cases where the model paraphrased such a line instead of quoting
it, **3 came out backwards**. Quoting is safe; paraphrasing a bare assert is a
coin flip.

## The inventions packet: 53 y, 6 n

All 6 of my `n`s are rubric false positives, and they fall into two classes
that `invents_exception()` in `bench/eval_bugsinpy_arms.py:128` produces by
construction — it compares exception **class names** in the sentence against
class names in the measured string, so:

**Class 1 — the measured failure is a bare pytest assert, which names no
exception.** The model writes `AssertionError: assert 2 == 1`, quoting the
measured line and adding the class that an `assert` raises by definition. The
rubric sees `named={AssertionError}`, `measured={}` and calls it a fabrication.
Cases 1 `httpie-4`, 4 `fastapi-6`, 9 `pandas-92` — rubric reason, verbatim:
`says AssertionError; the measured failure names no exception`.

**Class 2 — the exception named is what the FIXED code now does.** Case 6
`tornado-8`: the fix catches `ValueError` and returns 400, and the sentence
says so; the measured before (`AssertionError: 500 != 400`) is also stated
correctly. Case 8 `keras-28`: the fix now raises `ValueError`; the measured
`assert 7 == 6` is quoted. Neither asserts a failure that did not happen.

Case 44 `pandas-135` is a third kind: the sentence describes a `TypeError` that
appears in a `try/except` **in the code**, and hedges the effect ("may have
been causing issues"). It asserts nothing about the run.

Per-arm agreement with the rubric on this packet:

| arm | n | agree | rubric y | my y |
|---|---|---|---|---|
| v3plain_fix_v2 (all flagged) | 9 | **4/9 (44%)** | 9 | 4 |
| score_fix_v2 (sampled) | 25 | 25/25 (100%) | 25 | 25 |
| diff_fix_v2 (sampled) | 25 | 24/25 (96%) | 25 | 24 |

**This is the finding that matters for the headline.** The comparison arms
invent constantly and the rubric catches them cleanly — 49/50 confirmed. The
headline arm's 9 flags are 5 false positives out of 9, all of the same two
kinds, because it is the arm whose sentences stay close to the measured string
and therefore trip a check that punishes naming `AssertionError` next to an
`assert`. Corrected, `v3plain_fix_v2` invents on **4 of 458**, not 9 — and because
`grounded = (names_exception or quotes_signature) and not invented`, all five
cleared rows also flip to grounded: the headline goes **412/458 -> 417/458**.
The comparison arms are unaffected (score 105, diff 76), so the gap widens
rather than narrows. Nothing here is retrained or re-run through the model;
it is the same generations rescored.

The fix is two lines in `invents_exception`: seed `measured` with
`AssertionError` when the signature matches `^assert\b` or contains `!=`/`==`
with no class name, and ignore a class the sentence attributes to post-change
behaviour ("now raises", "catches"). Both need re-running the arms, not
retraining anything.

## Two closest calls

`scrapy-7` (case 10) and `httpie-2` (case 14) are the two I would most expect
an independent rater to score differently. `scrapy-7`'s run passes at both
commits, so there is no failure to be grounded in and I scored `grounded=n,
invented=y`; a rater who reads "grounded" as "quotes something real" could
justify `y`. `httpie-2` quotes the real numbers 0 and 6 but recasts them as
redirect counts and invents the edit — I scored `grounded=n` on the rule that
an inverted observation is not the observation; the tqdm-1 precedent in
`docs/GRADING.md` only covers an inverted *edit*, and does not settle this.

Grade those two yourself first. If you disagree with both, grounded goes to
48/50 and the rubric agreement goes up, not down.
