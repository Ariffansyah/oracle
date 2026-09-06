# Mechanism hand-grade — `oracle-merged` on bench/basic (33 buggy cases)

Graded 2 Sep 2026. The scorer's `fully correct` metric checks **locus** only —
`basic_bench.py:225` says so outright: *"This checks locus, not correctness.
It cannot detect an inverted claim."* This sheet grades the MECHANISM: whether
the causal claim in the finding is true, checked against each case's `note`
ground truth and the actual pre/post diff.

**DRAFT — needs your sign-off.** Judgements are mine; the borderline ones are
marked `imprecise` and are exactly where a second reader should look first.

## Result

| grade | count | |
|---|---|---|
| `correct` | 13/33 (39%) | mechanism claim is true |
| `imprecise` | 8/33 (24%) | right mechanism, one false detail attached |
| `wrong` | 9/33 (27%) | mechanism claim is false |
| `miss` | 3/33 (9%) | said no defect at all |

- **mechanism correct, strict: 13/33 (39%)**
- **mechanism correct, lenient: 21/33 (64%)** (counting `imprecise`)
- locus, for contrast: **30/33 (91%)** buggy; **41/46 (89%)** overall

The gap between 91% locus and 39-64% mechanism IS the locus/mechanism split
this project has been describing. It is now measured on all 33, not 10.

## Wrong mechanism (9) — locus right, causal claim false

### `c-strcpy-bound` (c, buffer-overflow)
- **ground truth:** strcpy of a 11-byte string into an 8-byte buffer overflows
- **model:** strcpy writes up to sizeof(dst) bytes but does not add a null terminator, so the resulting string may be truncated and lack a terminating '\0', potentially causing undefined behavior or truncation of output.
- **grade:** `wrong` — claims strcpy 'does not add a null terminator' and 'writes up to sizeof(dst)'. Both false: strcpy DOES terminate, and it writes as many bytes as the source needs. The real defect (11 bytes into an 8-byte buffer) is stated only in the summary, not the finding

### `go-accum-reset` (go, logic-error)
- **ground truth:** accumulator hoisted out of the loop; sums become cumulative
- **model:** The new `total := 0` inside the outer loop shadows the existing `total` variable declared before the inner loop, resetting it to zero on each iteration. This cancels the sum computed in the original code and produces incorrect results.
- **grade:** `wrong` — INVERTED. Says a new 'total := 0' inside the loop resets each iteration. The diff does the opposite: the reset was REMOVED from the loop, so sums become cumulative

### `js-sort-numeric` (javascript, api-misuse)
- **ground truth:** default sort is lexicographic: 1,10,20,9
- **model:** Using sort() without a comparator leaves the array unsorted, so the output may be out of order or even reversed for strings that compare numerically but are not numeric literals.
- **grade:** `wrong` — claims sort() 'leaves the array unsorted'. It sorts lexicographically (1,10,20,9) — that IS the defect and the model missed it

### `py-dict-mutate` (python, logic-error)
- **ground truth:** deleting from a dict while iterating it raises RuntimeError
- **model:** Iterating over the dictionary keys directly skips entries that are removed during iteration, so odd-numbered items may remain after deletion, altering the function's intended behavior.
- **grade:** `wrong` — claims entries are silently skipped. Python raises RuntimeError: dictionary changed size during iteration

### `py-pop-guard` (python, error-handling)
- **ground truth:** the removed check was not redundant: pop() on an empty list raised IndexError, now it raises AttributeError on None.next
- **model:** By removing the check for self.head being None, pop() no longer raises IndexError when called on an empty list, potentially returning None or corrupting internal state instead of raising a clear error, which can hide bugs or cause runtime failures downstream.
- **grade:** `wrong` — claims pop() now 'silently succeeds' / returns None. It raises AttributeError on None.next — an error either way, just a worse one

### `rb-string-mutate` (ruby, logic-error)
- **ground truth:** without dup, << mutates the caller's string
- **model:** By assigning the original input string to t instead of its duplicate, the method no longer appends the trailing "!" to the string, altering its behavior from the intended shout effect.
- **grade:** `wrong` — claims the '!' is no longer appended. It is appended — to the CALLER's string, which is the defect

### `rs-int-division` (rust, logic-error)
- **ground truth:** the cast moved after the division, so the mean truncates
- **model:** Using float division (as_f64 / len as f64) discards the fractional part of the sum, leading to an inaccurate mean for integer slices. This alters the intended numerical behavior of the function.
- **grade:** `wrong` — INVERTED. Says integer division was replaced with float division; the diff moved the cast AFTER the division, i.e. the opposite

### `rs-overflow` (rust, logic-error)
- **ground truth:** u8 200 + 100 overflows; checked_add handled it, plain + panics
- **model:** Using `a + b` discards the overflow flag, so adding two values that exceed `u8::MAX` will produce a result that wraps around rather than triggering a panic or overflow handling, potentially yielding incorrect results in subsequent calculations.
- **grade:** `wrong` — claims a+b wraps around 'rather than triggering a panic'. Debug Rust panics on overflow, which is the note's mechanism

### `ts-reduce-empty` (typescript, error-handling)
- **ground truth:** reduce with no initial value throws on an empty array
- **model:** When called with an empty array, the new version of total() uses reduce without an initial value, resulting in undefined being returned. The original version returned 0, so the change breaks the contract of the function and can lead to runtime errors for callers that assume the result is a number.
- **grade:** `wrong` — claims undefined is returned. reduce with no seed on an empty array throws TypeError

## Misses (3) — asserted no defect

### `go-nil-map` (go, error-handling)
- **ground truth:** a nil map reads fine but panics on assignment
- **model:** (no finding) The commit replaces a manual map creation with a variable declaration, initializing the map lazily. This change does not alter runtime behavior and introduces no new defects.
- **grade:** `miss` — verdict_ok=False, no findings, asserted no defect

### `java-concurrent-modify` (java, logic-error)
- **ground truth:** removing inside a for-each throws ConcurrentModificationException
- **model:** (no finding) The commit replaces an Iterator-based loop with a for-each loop that removes elements from the list while iterating. The new logic correctly skips removed elements and does not introduce concurrency i
- **grade:** `miss` — verdict_ok=False, asserted the for-each removal is safe

### `js-reverse-index` (javascript, off-by-one)
- **ground truth:** starts at arr.length; arr[length] is undefined so the sum is NaN
- **model:** (no finding) The commit modifies the total function to iterate from arr.length to 0 instead of arr.length - 1 to 0. This shifts the starting index but does not alter the loop body, so the computed sum remains unch
- **grade:** `miss` — verdict_ok=False, claimed the sum is unchanged

## Imprecise (8) — right mechanism, one false detail

### `java-array-bound` (java, off-by-one)
- **ground truth:** i <= xs.length reads one past the end; Java throws
- **model:** The new loop runs one extra time, accessing xs[xs.length] which is out of bounds and may throw a NullPointerException or ArrayIndexOutOfBoundsException, whereas the previous version only accessed valid indices.
- **grade:** `imprecise` — core OOB claim right, but offers NullPointerException as an alternative outcome, which is false

### `java-string-equals` (java, logic-error)
- **ground truth:** == compares references, so two equal Strings compare false
- **model:** Using == instead of equals causes same("foo", "foo") to return false, contradicting the intended contract of equals and leading to incorrect program logic.
- **grade:** `imprecise` — reference-vs-value mechanism right, but the concrete example is false: same("foo","foo") returns TRUE in Java because literals are interned

### `php-concat-operator` (php, logic-error)
- **ground truth:** + is arithmetic in PHP; concatenating strings with it is a TypeError
- **model:** Using the binary plus operator on non-string operands (e.g., a number and a string) results in numeric addition instead of string concatenation, producing unexpected output like 'hi123' for the example input.
- **grade:** `imprecise` — right that + is arithmetic not concatenation, but predicts output 'hi123'; PHP 8 raises TypeError

### `py-range-bound` (python, off-by-one)
- **ground truth:** range(1, n) drops the last term: 10 instead of 15
- **model:** By changing the range to go from 1 to n rather than 1 to n+1, the loop no longer adds the final integer (n), resulting in a computed sum that is always one less than the correct value for n > 1.
- **grade:** `imprecise` — right that the last term is dropped, but says the sum is 'one less than correct'; for n=5 it is 10 vs 15, i.e. n less

### `rb-int-division` (ruby, logic-error)
- **ground truth:** dropping to_f makes / integer division, so the mean truncates
- **model:** Integer division discards the fractional part of the sum, producing a non-numeric result that may mislead callers expecting a float. This changes the function's behavior and return type, which can lead to incorrect calculations or type mismatches.
- **grade:** `imprecise` — integer-division truncation right, but calls the result 'non-numeric'; it is an Integer

### `rs-index-bound` (rust, off-by-one)
- **ground truth:** 0..=xs.len() indexes one past the end; Rust panics
- **model:** The new loop runs from 0 to xs.len() inclusive, stepping by 1. On the final iteration, i equals xs.len() and accessing xs[i] accesses one-past-the-end of the slice, potentially causing a segfault or corrupt data.
- **grade:** `imprecise` — one-past-the-end right, but predicts segfault/corrupt data; Rust bounds-checks and panics

### `ts-nullish-default` (typescript, logic-error)
- **ground truth:** ?? only replaces null/undefined; || also replaces the empty string
- **model:** Replacing ?? with || makes the function treat falsy inputs (false, 0, '', null, undefined) as falsy, causing it to return "anon" even when a non‑empty string is passed. This alters the intended behavior and can produce incorrect results for valid inputs.
- **grade:** `imprecise` — falsy-vs-nullish right, but claims 'anon' is returned 'even when a non-empty string is passed', which is false

### `ts-slice-end` (typescript, off-by-one)
- **ground truth:** slice(0, n - 1) returns one element too few
- **model:** firstN now returns all elements up to but not including the nth element, whereas the previous implementation returned all elements up to and including the nth element. This mismatch can lead to missing elements in the output array, breaking any caller that relies on the inclusive slice behavior.
- **grade:** `imprecise` — net effect right (one element short) but describes slice(0,n) as including the nth element

## Correct (13)

### `c-array-bound` (c, off-by-one)
- **ground truth:** reads a[5], one past the array
- **model:** By changing the loop to run from 0 to 5 (inclusive), the program accesses array indices 5 and beyond, which are out of bounds and may cause a segmentation fault.
- **grade:** `correct` — names a[5]/one-past-end and the OOB read

### `c-int-division` (c, logic-error)
- **ground truth:** s becomes int so s / n truncates: 2.00 not 2.50
- **model:** By using int for the sum, fractional values from the input array are lost during addition, leading to an integer average that is not equivalent to the true arithmetic mean, potentially resulting in nonsensical or incorrect output.
- **grade:** `correct` — int accumulator truncates; matches note

### `go-offbyone` (go, off-by-one)
- **ground truth:** i <= len(xs) indexes one past the end; Go panics
- **model:** By changing the loop to run up to len(xs) instead of len(xs)-1, the function will attempt to read xs[len(xs)] which is out of bounds and will cause a runtime panic, breaking the intended behavior of summing the slice.
- **grade:** `correct` — xs[len(xs)] out of bounds, runtime panic

### `java-null-guard` (java, error-handling)
- **ground truth:** the null check is gone, so len(null) throws NullPointerException
- **model:** Calling length() on a null String throws a NullPointerException, whereas the previous version returned 0.
- **grade:** `correct` — NPE on length() of null, previously 0

### `js-var-capture` (javascript, logic-error)
- **ground truth:** var is function-scoped, so every closure captures the final i
- **model:** Using var instead of let causes i to be hoisted to the function scope and retain its final value (3) after the loop, so all arrow functions capture and return 3, breaking the intended behavior of returning a function that captures the current loop index.
- **grade:** `correct` — var hoists to function scope, all closures capture 3

### `php-divzero-guard` (php, error-handling)
- **ground truth:** the empty-array guard is gone, so avg([]) throws DivisionByZeroError
- **model:** avg() now returns array_sum($xs) / count($xs) without verifying that count($xs) > 0, leading to a DivisionByZeroError when called with an empty array.
- **grade:** `correct` — DivisionByZeroError on empty array, guard removed

### `php-loose-compare` (php, logic-error)
- **ground truth:** === became ==, so "0" and 0 now compare equal
- **model:** Using loose equality ($a == $b) makes the function return true for inputs that are equal in value but of different types (e.g., "0" and 0). This can lead to incorrect comparisons and logic errors in callers that expect strict equality.
- **grade:** `correct` — == equates "0" and 0, exactly the note

### `php-slice-end` (php, off-by-one)
- **ground truth:** array_slice length is n - 1, one element short
- **model:** firstN now returns all elements from the start up to but not including the nth element, whereas the original returned the first n elements. This mismatch can lead to unexpected output or off-by-one errors for callers.
- **grade:** `correct` — one element short via n-1 length

### `py-mutable-default` (python, logic-error)
- **ground truth:** mutable default argument persists across calls
- **model:** Using a mutable default (an empty list) for the acc parameter means that the same list object is reused across calls, leading to incorrect results or side‑effects when the function is called multiple times.
- **grade:** `correct` — same list object reused across calls

### `rb-nil-guard` (ruby, error-handling)
- **ground truth:** the nil check is gone, so size_of(nil) raises NoMethodError
- **model:** Calling length on a nil object raises NoMethodError, whereas the previous version returned 0. This changes runtime behavior and can crash callers that expect a non‑negative integer.
- **grade:** `correct` — NoMethodError on nil.length, previously 0

### `rb-range-bound` (ruby, off-by-one)
- **ground truth:** 1...n excludes n, so the sum drops the last term
- **model:** Using `(1...n).sum` computes the sum of numbers from 1 to n-1 instead of 1 to n, so calling `total(5)` will return 10 instead of the intended 15, leading to incorrect output.
- **grade:** `correct` — 1...n excludes n; total(5)=10 not 15, numerically exact

### `rs-unwrap-none` (rust, error-handling)
- **ground truth:** unwrap() on an empty slice's first() panics
- **model:** first now calls xs.first().unwrap(), which will panic if xs is empty, whereas the original used unwrap_or and returned 0, preserving previous behavior.
- **grade:** `correct` — unwrap() panics on empty, unwrap_or returned 0

### `ts-sort-in-place` (typescript, logic-error)
- **ground truth:** sort() mutates; dropping the copy reorders the caller's array
- **model:** Using xs.sort modifies the caller's original array instead of returning a new sorted array, breaking any code that expects a fresh copy.
- **grade:** `correct` — sort() mutates the caller's array
