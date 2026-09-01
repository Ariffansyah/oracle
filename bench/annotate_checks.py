"""Add a per-case `check` annotation to every bench/mechanism_pilot meta.json.

The v3 `check` field was a per-CATEGORY sentence with a filename slot, and the
corpus has only two categories, so 366 targets carried 100 distinct check
strings and 357 of them contained the words "the edit touches". The model
pushed that to saturation (100% of v4 outputs) and two independently trained
checkpoints emitted byte-identical `check` strings 30-59% of the time.

These annotations replace the category key with the case's own mechanism:

  probe     the input or call that reaches the defect
  watch     what changed, and what a reader should look for - phrased as a
            question, never as an assertion about what the program prints
  restored  only where a `-fix` child exists: what the fix puts back

Nothing here is an executed value. Every field is derivable from the diff,
which is the v3 rule: a target the model cannot reproduce from its input
teaches it to invent.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The nine `*-extract-boundary` cases are the same program in nine languages.
# They share a summary already, so `mechanism()` downsamples them from x6 to x1;
# sharing the probe wording costs nine records, not fifty-four.
def boundary(call):
    return dict(
        probe=f"call `{call}` with a score of exactly 60, the boundary the "
              f"comparison names",
        watch="the extracted `passing()` tests `score > 60` where the inline "
              "test was `score >= 60`, so check whether exactly 60 still comes "
              "back as a pass",
    )


CHECKS = {
  # ---- boundary family (9 languages, no -fix child; counter-aligned refactor)
  "c-extract-boundary":    boundary("grade(60)"),
  "go-extract-boundary":   boundary("grade(60)"),
  "java-extract-boundary": boundary("grade(60)"),
  "js-extract-boundary":   boundary("grade(60)"),
  "php-extract-boundary":  boundary("grade(60)"),
  "py-extract-boundary":   boundary("grade(60)"),
  "rb-extract-boundary":   boundary("grade(60)"),
  "rs-extract-boundary":   boundary("grade(60)"),
  "ts-extract-boundary":   boundary("grade(60)"),

  # ---- ratio truncation: the cast moved across the division
  "c-ratio-trunc": dict(
    probe="call `score_percentage(1, 3)`, two ints that do not divide evenly",
    watch="the `(double)` cast now wraps the whole division instead of "
          "`correct` alone, so check whether `correct / total` runs as integer "
          "division and truncates before the cast reaches it",
    restored="the `(double)` cast is back on `correct` alone, before the "
             "division, so check that the ratio is computed in floating point "
             "rather than truncated by integer division",
  ),
  "go-ratio-trunc": dict(
    probe="call `scorePercentage(1, 3)`, two ints that do not divide evenly",
    watch="`float64()` now wraps the whole division instead of each operand, "
          "so check whether `correct/total` runs as integer division and "
          "truncates before the cast reaches it",
    restored="`float64()` is back on each operand, before the division, so "
             "check that the ratio is computed in floating point rather than "
             "truncated by integer division",
  ),
  "java-ratio-trunc": dict(
    probe="call `scorePercentage(1, 3)`, two ints that do not divide evenly",
    watch="the `(double)` cast now wraps `correct / total` instead of "
          "`correct` alone, so check whether the division itself is integer "
          "division and truncates before the cast applies",
    restored="the `(double)` cast is back on `correct` alone, so check that "
             "the division happens in floating point instead of truncating "
             "before the cast",
  ),
  "php-ratio-trunc": dict(
    probe="call `score_percentage(1, 3)`, two ints that do not divide evenly",
    watch="`/` is replaced by `intdiv()`, which truncates by definition where "
          "`/` returned a float for int operands, so check what a non-exact "
          "ratio does now",
    restored="`intdiv()` is replaced by `/`, which returns a float for int "
             "operands, so check that a non-exact ratio is no longer truncated "
             "by integer division",
  ),

  # ---- removed guards
  "c-signed-overflow": dict(
    probe="call `safe_add(INT_MAX, 1)`",
    watch="the `INT_MAX`/`INT_MIN` guard that clamped the result is gone, so "
          "check whether `a + b` is now signed integer overflow — undefined "
          "behavior rather than a clamped value",
    restored="the `INT_MAX`/`INT_MIN` guard is back in front of `a + b`, so "
             "check that the sum clamps instead of overflowing into undefined "
             "behavior",
  ),
  "go-first-empty-guard": dict(
    probe="call `firstOrDefault` with an empty slice",
    watch="the `len(xs) == 0` guard that returned the default is gone, so "
          "check whether `xs[0]` now panics with index out of range instead",
    restored="the `len(xs) == 0` guard is back before `xs[0]`, so check that "
             "an empty slice returns the default instead of a panic",
  ),
  "py-min-empty-guard": dict(
    probe="call `smallest([])` with an empty list",
    watch="the `not nums` guard that returned the default is gone, so check "
          "whether `min(nums)` raises ValueError on the empty case instead of "
          "returning a sentinel",
    restored="the `not nums` guard is back before `min(nums)`, so check that "
             "an empty list returns the default instead of raising ValueError",
  ),
  "py-zerodiv-guard": dict(
    probe="call `safe_divide(10, 0)` with a zero divisor",
    watch="the `b == 0` guard is gone, so check whether the division now "
          "raises ZeroDivisionError instead of returning the sentinel",
    restored="the `b == 0` guard is back before the division, so check that a "
             "zero divisor returns the sentinel instead of raising "
             "ZeroDivisionError",
  ),
  "js-math-min-empty": dict(
    probe="call `smallest([])` with an empty array",
    watch="the `nums.length === 0` guard is gone, so check what "
          "`Math.min(...nums)` returns when the spread is empty — Infinity is "
          "a value, not an error, so nothing will throw",
    restored="the `nums.length === 0` guard is back before "
             "`Math.min(...nums)`, so check that an empty array returns the "
             "sentinel rather than Infinity",
  ),
  "rb-first-empty-guard": dict(
    probe="call `first_or_default` with an empty array",
    watch="the `xs.empty?` guard is gone, so check what `xs.first` returns on "
          "an empty array — nil is returned rather than raised, so the default "
          "is lost silently",
    restored="the `xs.empty?` guard is back before `xs.first`, so check that "
             "an empty array returns the default instead of nil",
  ),

  # ---- overflow checks swapped for bare arithmetic
  "java-int-wrap": dict(
    probe="call `safeAdd(Integer.MAX_VALUE, 1)`",
    watch="`Math.addExact`, which throws ArithmeticException on overflow, is "
          "replaced by plain `+`, which wraps silently in Java — so check "
          "whether the overflow still surfaces at all",
    restored="`Math.addExact` is back in place of plain `+`, so check that an "
             "overflowing sum throws ArithmeticException instead of wrapping "
             "silently",
  ),
  "rs-runtime-overflow": dict(
    probe="call `add_scores` with u8 values that sum past 255",
    watch="`checked_add(...).unwrap_or(u8::MAX)`, which saturated, is replaced "
          "by plain `+`, and the values come from a runtime slice rather than "
          "literals — so check whether this panics at run time instead of "
          "saturating",
    restored="`checked_add` with its saturating fallback is back in place of "
             "plain `+`, so check that a sum past 255 saturates instead of "
             "panicking at run time",
  ),

  # ---- accumulator hoisted out of the loop
  "java-batch-total-reset": dict(
    probe="call `batchTotals` with two or more batches",
    watch="`int total = 0` is hoisted outside the loop, so check whether the "
          "accumulator still resets per batch or carries the previous batch's "
          "total forward",
    restored="`int total = 0` is back inside the loop, so check that the "
             "accumulator resets per batch instead of carrying the previous "
             "batch's total forward",
  ),
  "js-word-count-reset": dict(
    probe="call `lineWordCounts` with two or more lines",
    watch="`let count = 0` is hoisted outside the loop, so check whether the "
          "count still resets per line or accumulates across lines",
    restored="`let count = 0` is back inside the loop, so check that the count "
             "resets per line instead of accumulating across lines",
  ),
  "py-row-max-reset": dict(
    probe="call `row_maxes` with two or more rows, the later ones holding "
          "smaller values than the first",
    watch="`best = 0` is hoisted outside the loop, so check whether the "
          "running max still resets per row or a high value from an earlier "
          "row leaks into later ones",
    restored="`best = 0` is back inside the loop, so check that the running "
             "max resets per row instead of leaking a high value from an "
             "earlier row",
  ),
  "rb-row-min-reset": dict(
    probe="call `row_mins` with two or more rows, the later ones holding "
          "larger values than the first",
    watch="`best` is now seeded once outside the block and only reset when "
          "nil, so check whether a low value from an earlier row survives into "
          "later rows",
    restored="`best = row[0]` is seeded fresh per row again rather than only "
             "when nil, so check that a low value from an earlier row no "
             "longer survives into later rows",
  ),

  # ---- the copy that stops a mutation reaching the caller
  "js-array-alias-mutate": dict(
    probe="pass an array in, then look at the caller's own variable after the "
          "call returns",
    watch="`[...items]` is replaced by `out = items`, so `out` aliases the "
          "caller's array rather than copying it — check whether the `push()` "
          "is visible to the caller too",
    restored="the `[...items]` spread copy is back, so check that the "
             "`push()` no longer reaches the caller's array",
  ),
  "py-list-alias-mutate": dict(
    probe="pass a list in, then look at the caller's own variable after the "
          "call returns",
    watch="`list(items)` is replaced by `out = items`, so `out` is the same "
          "list the caller holds — check whether the `append()` mutates the "
          "caller's list too",
    restored="the `list(items)` copy is back, so check that the `append()` no "
             "longer mutates the caller's list",
  ),
  "rb-array-alias-mutate": dict(
    probe="pass an array in, then look at the caller's own variable after the "
          "call returns",
    watch="`items.dup` is replaced by `out = items`, so `out` is the same "
          "object the caller holds — check whether the `<<` mutates the "
          "caller's array too",
    restored="the `items.dup` copy is back, so check that the `<<` no longer "
             "mutates the caller's array",
  ),
  "php-array-ref-alias": dict(
    probe="pass an array in, then look at the caller's own variable after the "
          "call returns",
    watch="the parameter becomes `&$items` and `$out =& $items` adds an "
          "explicit reference, which bypasses PHP's by-value array copy — "
          "check whether the append is visible to the caller too",
    restored="the `&` reference is dropped from both the parameter and `$out`, "
             "restoring PHP's by-value array copy, so check that the append no "
             "longer reaches the caller's array",
  ),

  # ---- mutating a collection while iterating it
  "js-array-mutate-iterate": dict(
    probe="call `removeEvens` with two or more consecutive even numbers",
    watch="the `[...items]` copy the loop iterated is gone and the loop now "
          "walks `items` itself while `splice()` removes from it — check "
          "whether removing shifts the later elements and the loop skips "
          "an index",
    restored="the `[...items]` copy is back as the thing the loop iterates, so "
             "check that removals no longer shift elements out from under the "
             "index",
  ),
  "py-list-mutate-iterate": dict(
    probe="call `remove_evens` with two or more consecutive even numbers",
    watch="the `list(items)` copy the loop iterated is gone and the loop now "
          "walks `items` itself while `remove()` mutates it — check whether "
          "removing shifts the later elements and the loop skips one",
    restored="the `list(items)` copy is back as the thing the loop iterates, "
             "so check that removals no longer shift elements past the index",
  ),
  "rb-array-mutate-iterate": dict(
    probe="call `remove_evens` with two or more consecutive even numbers",
    watch="`items.dup` is gone and `each` now walks `items` itself while "
          "`delete` mutates it — check whether deleting shifts the later "
          "elements and the block skips one",
    restored="the `items.dup` copy is back as the thing `each` walks, so check "
             "that deletions no longer shift elements past the index",
  ),
  "java-map-concurrent-modify": dict(
    probe="call `removeEvens` with a map that has at least one even value",
    watch="the `new ArrayList<>(m.keySet())` snapshot is gone and the loop "
          "iterates `m.keySet()` directly while `m.remove` runs — check "
          "whether that raises ConcurrentModificationException",
    restored="the `new ArrayList<>(m.keySet())` snapshot copy is back as the "
             "thing the loop iterates, so check that removing during the walk "
             "no longer raises ConcurrentModificationException",
  ),

  # ---- type coercion
  "js-loose-equal-coerce": dict(
    probe="call `isMatch` with a numeric string and the number it looks like, "
          "such as `\"007\"` and `7`",
    watch="`===` is replaced by `==`, so check whether the string is coerced "
          "to a number and matches where the strict test did not",
    restored="`===` is back in place of `==`, so check that a numeric string "
             "no longer coerces into a match with the number",
  ),
  "py-str-concat-typeerror": dict(
    probe="call `build_message(3, \"items\")` with an int and a str",
    watch="the `str(count)` conversion is gone and Python does not "
          "coerce int to str for `+`, so check whether this raises TypeError "
          "rather than concatenating",
    restored="the `str(count)` conversion is back, so check that the "
             "concatenation succeeds instead of raising TypeError",
  ),
  "rb-str-concat-typeerror": dict(
    probe="call `build_message(3, \"items\")` with an Integer and a String",
    watch="`count.to_s` is gone and `Integer#+` tries to coerce its argument "
          "as a number, so check whether this raises TypeError rather than "
          "concatenating",
    restored="`count.to_s` is back, so check that the concatenation succeeds "
             "instead of raising TypeError",
  ),
  "php-compound-assign-coerce": dict(
    probe="call `build_label(\"user-\", \"bob\")` with two non-numeric strings",
    watch="`.=` (string concat-assign) is replaced by `+=` (numeric "
          "add-assign), and PHP 8 does not coerce two non-numeric strings for "
          "`+` — check which operand types `+` will accept here",
    restored="`.=` is back in place of `+=`, so check that the two strings "
             "concatenate instead of hitting `+`'s operand types",
  ),
}


def main():
    d = ROOT / "bench/mechanism_pilot"
    seen, missing, extra = 0, [], []
    for meta in sorted(d.glob("*/meta.json")):
        m = json.loads(meta.read_text())
        c = CHECKS.get(m["id"])
        if not c:
            missing.append(m["id"])
            continue
        m["check"] = c
        meta.write_text(json.dumps(m, indent=2) + "\n")
        seen += 1
    extra = sorted(set(CHECKS) - {json.loads(p.read_text())["id"]
                                 for p in d.glob("*/meta.json")})
    print(f"annotated {seen} cases")
    if missing:
        print(f"  !! NO annotation for: {missing}")
    if extra:
        print(f"  !! annotation for a case that does not exist: {extra}")
    return 1 if (missing or extra) else 0


if __name__ == "__main__":
    raise SystemExit(main())
