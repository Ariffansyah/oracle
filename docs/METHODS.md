# ORACLE methods, in plain words

One page. What each piece does, why it exists, and which hole in the earlier
research it plugs. No jargon without a translation.

---

## The problem, stated simply

A developer writes a commit. Some commits carry bugs. We want to catch them
right then, before the code is merged. That is "Just-In-Time" defect prediction:
judge the change, not the whole codebase.

Twelve years of research answered this with a **number**.

> Your commit is 94% risky.

Now what? You cannot fix a number. You do not know which line, or why, or
whether the tool is even right. Most developers look at the number once, get no
help from it, and stop looking.

**That is the hole.** Not accuracy — usefulness. The old tools were reasonably
accurate and still nobody used them, because the output could not be acted on.

ORACLE outputs this instead:

```json
{
  "summary": "Removes the lock around the emptiness check and pop.",
  "findings": [{
    "category": "concurrency",
    "explanation": "Two workers can both pass the empty check and pop, raising IndexError."
  }]
}
```

Same job. Answer you can act on.

---

## What came before, and what each one missed

| research | how it works | what it gives you | what it misses |
| --- | --- | --- | --- |
| **Kamei et al. (2013)** | 14 numbers per commit (lines added, how many files, how experienced the author) → logistic regression | a probability | never reads the code |
| **Commit Guru (2015)** | same numbers, mined automatically from any repo | a probability, on a website | never reads the code |
| **DeepJIT (2019)** | small neural net trained from scratch on commit text | a probability | learns word statistics, not meaning; needs 20k+ commits per project |
| **CC2Vec (2020)** | bigger neural net over diffs | a probability | same; and heavy to train |
| **LApredict (2021)** | plain regression on *one* number: lines added | a probability | showed the deep models were barely better than one feature — the line stalled here |
| **JITLine (2021)** | token frequencies + random forest + LIME | ranked suspicious *lines* | points at lines by statistics, cannot say what is wrong with them |

Look down the "what it gives you" column. Every row: a probability. One row
manages line numbers. **No row explains anything.**

---

## What ORACLE does differently

### 1. It reads the code

Old models see numbers *about* a commit: 412 lines added, 8 files, author has 4
prior commits. They never see a single line of the actual code.

ORACLE sees the code. That is the whole change of approach.

**Gap covered:** a model that cannot read code can never tell you what is wrong
with it. It can only tell you that commits *shaped* like this one tended to be
buggy.

### 2. It starts from a model that already knows programming

DeepJIT and CC2Vec started from nothing — random numbers — and learned from
maybe 20,000 commits. Twenty thousand commits is not enough to learn what a race
condition is.

ORACLE starts from Qwen2.5-Coder, already trained on an enormous amount of code.
It arrives knowing that `//` is floor division, that Cloudflare Turnstile is a
captcha, that `redirect()` in Next.js throws on purpose. We never teach it any of
that.

We only teach it **how to behave**: answer in this exact JSON shape, and do not
invent problems.

**Gap covered:** old models could only recognise bug patterns that appeared in
their training commits. A new kind of bug meant retraining. ORACLE recognises an
off-by-one in a language it never saw a labelled example of.

### 3. It is trained in two stages, because there are two different problems

**Stage 1 — SFT (Supervised Fine-Tuning).** Show the model thousands of examples
of "here is a diff, here is the correct answer". It learns the job and the exact
output format.

Result: a model that always answers correctly *shaped*. And that always finds
something, because every example it was shown was a confident answer. Show a
student a thousand exam papers that all have an answer written in, and they will
never leave a question blank.

**Stage 2 — DPO (Direct Preference Optimization).** Now show it *pairs*: two
possible answers to the same commit, and which one is better.

```
same diff (a safe one)
  good answer:  "no defects found"
  bad answer:   "possible logic error: the early return skips the update"
                                       ↑ this is what stage 1 taught it to say
```

There is no single correct answer being copied here. The model learns a
*preference* — which of two answers is better. That is the right tool, because
over-reporting is not a formatting mistake, it is a disposition.

**Gap covered:** old models have one failure mode — a miscalibrated number. A
model that writes sentences has a new one: **it can be confidently wrong in
fluent English**. Nobody in the JIT literature measures that, because a
probability cannot lie. Stage 2 exists to reduce it.

### 4. It reads the code *around* the change, not just the change

This is the failure that cost us the most, so it gets the most space.

A diff shows only the lines that changed. Here is a real one:

```diff
+    if (!token) {
+      setError("Please complete the captcha.");
+      return;
+    }
```

The model looks at this and says: *logic error — the function returns early, the
form silently does nothing, the user gets no feedback.*

It is wrong. Forty lines further down the same file, outside the diff:

```jsx
<button type="submit" disabled={!token || pending}>
```

The button is already disabled. The guard is a second line of defence against a
race. It is *correct code*, and the model called it a bug because **it could not
see the rest of the file**.

That is contextual myopia, and it is a *context* problem before it is a model
problem. So ORACLE fetches:

- `git show -U50` — fifty lines around every change instead of three
- `git show <commit>:<file>` — the whole file after the change, when it is small
  enough to fit

and puts that **before** the diff in the prompt, so the model builds a picture of
the file first and then looks at what changed inside it.

**Gap covered:** entirely absent from the earlier work, because a metrics model
has no concept of "context" at all — it sees `la=412` whether the surrounding
code is a captcha guard or a rocket launch.

### 5. It reviews one file at a time

Measured on a real 34 KB commit touching 15 files:

| approach | result |
| --- | --- |
| whole commit in one prompt | **0 findings** — it summarised the commit correctly and noticed nothing |
| one prompt per file | **7 findings**, 4 of them real |

Attention spread across fifteen files at once produces a description. Attention
on one file produces a review.

**Gap covered:** nobody hit this before because nobody was feeding whole commits
to a language model — a metrics model does not care how many files there are.

### 6. When something fails, it says so

If a file cannot be reviewed — too slow, too large, a bad response — ORACLE names
it and refuses to claim coverage:

```
2 FAILED TO REVIEW — not covered by this verdict: components/Auth/signup-form.tsx (…)
; no defects found in the files that were reviewed
```

An earlier version said `1 failed to review; no defects found`, which reads as a
clean bill of health for a commit whose most interesting file was skipped.

Before giving up it sheds context and retries: **full file → trimmed → diff
only**. A file is never dropped merely for being big.

---

## The training recipe, in one place

**QLoRA.** Fine-tuning a 7-billion-parameter model normally needs enormous
memory. QLoRA squashes the frozen base model to 4 bits and trains a small set of
extra weights bolted onto the attention layers — about 0.1% of the total. Fits on
one GPU. The frozen base is also what *protects* the pretrained knowledge: train
everything on 200 examples and you wash out the programming knowledge you came
for.

**DPO-Positive instead of plain DPO.** In the captcha pairs, the good answer and
the bad answer are nearly identical text — same file, same lines, disagreeing
only about whether the guard is a bug. Plain DPO pushes the two apart, and it is
allowed to do that by making the *good* answer less likely as long as the bad one
drops faster. On near-identical pairs that is exactly what happens. DPO-Positive
adds a penalty that stops the good answer sinking.

That is why `DPO_LOSS_TYPE = "dpop"` and `DPO_BETA = 0.5` — a higher beta keeps
the tuned model closer to where it started, which matters when the corpus is
small and the distinctions are fine.

**A two-sided preference set.** Sixty pairs teach "say nothing about safe code".
Twenty teach "speak up about real defects". Train on the first kind alone and the
model finds the obvious optimum: never say anything. Silence scores perfectly on
a corpus that only rewards silence.

---

## Honest limits

- **Nothing is trained yet.** Every script works; 7B QLoRA needs a GPU this
  machine does not have. Today ORACLE runs on a stock model with a strict prompt.
- **The mock corpus is templated.** Six defect patterns, four safe patterns, five
  captcha cases. Enough to prove the pipeline trains and the format holds. Not
  enough to produce a good reviewer. Real training needs real diffs with real
  written explanations, which means distilling them from a stronger model.
- **The statistical baseline lives in `legacy/`.** CatBoost on ApacheJIT: AUC
  0.8666, Popt 0.8113, PofB20 0.5621. Kept as a comparison row, not as the
  method. Also worth knowing: CatBoost, LightGBM and XGBoost landed within 0.005
  AUC of each other on identical data — the 14 metrics are the ceiling, not the
  algorithm.
- **The context claim is untested.** `--no-context` exists precisely so the
  before/after can be measured rather than asserted. Until that experiment runs,
  "context reduces hallucination" is a hypothesis with one anecdote behind it.
