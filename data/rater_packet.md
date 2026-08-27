# Second-rater packet

20 cases drawn from `basic_bench_oracle46.jsonl` with seed 20260826.

For each case, decide what the model's explanation got right:

- **locus** — names the right construct AND the causal claim is true
- **mechanism** — names the right construct, but the stated cause is
  wrong, inverted, or names the wrong error
- **wrong** — neither

**Run both sides before grading a mechanism claim.** Each case gives the
command. If you did not execute it, leave the grade blank rather than
guess — a blank is data, a guess is noise.

Record answers as `case_id,grade` in a CSV, then:

    python bench/rater_packet.py --score rater2.csv

---

## `rs-index-bound`  (rust)

Run it:  `cd bench/basic/rs-index-bound && <run> pre.rs` then the same for `post.rs`

```diff
diff --git ars-index-bound.rs brs-index-bound.rs
index ccc00db..2f8b82c 100644
--- ars-index-bound.rs
+++ brs-index-bound.rs
@@ -1,6 +1,6 @@
 fn sum(xs: &[i32]) -> i32 {
     let mut s = 0;
-    for i in 0..xs.len() {
+    for i in 0..=xs.len() {
         s += xs[i];
     }
     s
```

**Model summary:** The commit expands the loop range from 0..xs.len() to 0..=xs.len(), causing the loop to access one past the last element of the slice. This can lead to a buffer overflow and undefined behavior.

**Finding 1** (off-by-one): The new loop runs from 0 to xs.len() inclusive, stepping by 1. On the final iteration, i equals xs.len() and accessing xs[i] accesses one-past-the-end of the slice, potentially causing a segfault or corrupt data.

`rs-index-bound` grade: ______

---

## `js-reverse-index`  (javascript)

Run it:  `cd bench/basic/js-reverse-index && <run> pre.js` then the same for `post.js`

```diff
diff --git ajs-reverse-index.js bjs-reverse-index.js
index 5b103d9..2fd73e5 100644
--- ajs-reverse-index.js
+++ bjs-reverse-index.js
@@ -1,6 +1,6 @@
 function total(arr) {
   let s = 0;
-  for (let i = arr.length - 1; i >= 0; i--) s += arr[i];
+  for (let i = arr.length; i >= 0; i--) s += arr[i];
   return s;
 }
 console.log(total([1, 2, 3, 4]));
```

**Model summary:** The commit modifies the total function to iterate from arr.length to 0 instead of arr.length - 1 to 0. This shifts the starting index but does not alter the loop body, so the computed sum remains unchanged. No functional behavior is altered, and no new defects are introduced.

**Findings:** none reported

`js-reverse-index` grade: ______

---

## `py-dict-mutate`  (python)

Run it:  `cd bench/basic/py-dict-mutate && <run> pre.py` then the same for `post.py`

```diff
diff --git apy-dict-mutate.py bpy-dict-mutate.py
index 800cbdf..be8c733 100644
--- apy-dict-mutate.py
+++ bpy-dict-mutate.py
@@ -1,5 +1,5 @@
 def drop_odd(d):
-    for k in list(d):
+    for k in d:
         if d[k] % 2:
             del d[k]
     return d
```

**Model summary:** The commit replaces iterating over a copy of the dictionary with iterating directly over the original, causing the loop to miss elements that are deleted during iteration, potentially leaving odd entries in the dictionary.

**Finding 1** (logic-error): Iterating over the dictionary keys directly skips entries that are removed during iteration, so odd-numbered items may remain after deletion, altering the function's intended behavior.

`py-dict-mutate` grade: ______

---

## `py-annotate-only`  (python)

Run it:  `cd bench/basic/py-annotate-only && <run> pre.py` then the same for `post.py`

```diff
diff --git apy-annotate-only.py bpy-annotate-only.py
index 482cf6a..3989306 100644
--- apy-annotate-only.py
+++ bpy-annotate-only.py
@@ -1,7 +1,14 @@
-"""Comparison sorts."""
+"""Comparison sorts.
 
+Both sorts are stable and return a new list; the input is never mutated.
+"""
 
-def insertion_sort(items):
+from typing import Iterable, List, Sequence, TypeVar
+
+T = TypeVar("T")
+
+
+def insertion_sort(items: Iterable[T]) -> List[T]:
     out = list(items)
     for i in range(1, len(out)):
         key = out[i]
@@ -13,7 +20,7 @@ def insertion_sort(items):
     return out
 
 
-def merge(left, right):
+def merge(left: Sequence[T], right: Sequence[T]) -> List[T]:
     out = []
     i = j = 0
     while i < len(left) and j < len(right):
@@ -28,7 +35,7 @@ def merge(left, right):
     return out
 
 
-def merge_sort(items):
+def merge_sort(items: Sequence[T]) -> List[T]:
     if len(items) <= 1:
         return list(items)
     mid = len(items) // 2
```

**Model summary:** The commit adds type hints and documentation to insertion_sort, merge, and merge_sort, changing their signatures from accepting any iterable to requiring sequences and returning lists. This alters expected input types and return types, potentially breaking callers that assume iterable inputs or expect mutable outputs.

**Finding 1** (api-misuse): insertion_sort, merge, and merge_sort now accept only sequence types (e.g., list) and return lists instead of the original iterable type. Callers that pass other iterables (e.g., generators) will receive a TypeError or incorrect result type.

`py-annotate-only` grade: ______

---

## `php-extract-helper`  (php)

Run it:  `cd bench/basic/php-extract-helper && <run> pre.php` then the same for `post.php`

```diff
diff --git aphp-extract-helper.php bphp-extract-helper.php
index bf740d9..f379a83 100644
--- aphp-extract-helper.php
+++ bphp-extract-helper.php
@@ -1,7 +1,10 @@
 <?php
-$xs = [1, 2, 3];
-$s = 0;
-foreach ($xs as $x) {
-    $s += $x;
+function total(array $xs): int {
+    $s = 0;
+    foreach ($xs as $x) {
+        $s += $x;
+    }
+    return $s;
 }
-echo $s, "\n";
+
+echo total([1, 2, 3]), "\n";
```

**Model summary:** The commit refactors the helper function into a standalone total() method and calls it from the main script. No new runtime defects are introduced; the behavior remains equivalent.

**Findings:** none reported

`php-extract-helper` grade: ______

---

## `php-divzero-guard`  (php)

Run it:  `cd bench/basic/php-divzero-guard && <run> pre.php` then the same for `post.php`

```diff
diff --git aphp-divzero-guard.php bphp-divzero-guard.php
index db30b84..b8bd7c3 100644
--- aphp-divzero-guard.php
+++ bphp-divzero-guard.php
@@ -1,8 +1,5 @@
 <?php
 function avg(array $xs): float {
-    if (count($xs) === 0) {
-        return 0.0;
-    }
     return array_sum($xs) / count($xs);
 }
```

**Model summary:** The commit removes the explicit zero-count check in avg(), causing division by zero for empty arrays.

**Finding 1** (error-handling): avg() now returns array_sum($xs) / count($xs) without verifying that count($xs) > 0, leading to a DivisionByZeroError when called with an empty array.

`php-divzero-guard` grade: ______

---

## `go-extract-helper`  (go)

Run it:  `cd bench/basic/go-extract-helper && <run> pre.go` then the same for `post.go`

```diff
diff --git ago-extract-helper.go bgo-extract-helper.go
index a04c0b1..30cd4d7 100644
--- ago-extract-helper.go
+++ bgo-extract-helper.go
@@ -2,11 +2,14 @@ package main
 
 import "fmt"
 
-func main() {
-	xs := []int{1, 2, 3}
+func sum(xs []int) int {
 	s := 0
 	for _, x := range xs {
 		s += x
 	}
-	fmt.Println(s)
+	return s
+}
+
+func main() {
+	fmt.Println(sum([]int{1, 2, 3}))
 }
```

**Model summary:** The commit refactors main() into a helper function sum() and updates main() to call sum(). This change does not alter runtime behavior and introduces no new defects.

**Findings:** none reported

`go-extract-helper` grade: ______

---

## `rb-int-division`  (ruby)

Run it:  `cd bench/basic/rb-int-division && <run> pre.rb` then the same for `post.rb`

```diff
diff --git arb-int-division.rb brb-int-division.rb
index 6149204..c754a36 100644
--- arb-int-division.rb
+++ brb-int-division.rb
@@ -1,5 +1,5 @@
 def mean(xs)
-  xs.sum.to_f / xs.size
+  xs.sum / xs.size
 end
 
 puts mean([1, 2])
```

**Model summary:** The commit replaces floating-point division with integer division in the mean calculation, causing truncation of decimal results and altering the function's return type from float to int.

**Finding 1** (logic-error): Integer division discards the fractional part of the sum, producing a non-numeric result that may mislead callers expecting a float. This changes the function's behavior and return type, which can lead to incorrect calculations or type mismatches.

`rb-int-division` grade: ______

---

## `js-sort-numeric`  (javascript)

Run it:  `cd bench/basic/js-sort-numeric && <run> pre.js` then the same for `post.js`

```diff
diff --git ajs-sort-numeric.js bjs-sort-numeric.js
index 429e86f..4546f1c 100644
--- ajs-sort-numeric.js
+++ bjs-sort-numeric.js
@@ -1,4 +1,4 @@
 function sorted(xs) {
-  return [...xs].sort((a, b) => a - b);
+  return [...xs].sort();
 }
 console.log(sorted([10, 9, 1, 20]).join(","));
```

**Model summary:** The commit replaces a numeric sort with a default sort, which can produce incorrect ordering for non-numeric strings.

**Finding 1** (logic-error): Using sort() without a comparator leaves the array unsorted, so the output may be out of order or even reversed for strings that compare numerically but are not numeric literals.

`js-sort-numeric` grade: ______

---

## `c-array-bound`  (c)

Run it:  `cd bench/basic/c-array-bound && <run> pre.c` then the same for `post.c`

```diff
diff --git ac-array-bound.c bc-array-bound.c
index 1b5f34c..98b78fc 100644
--- ac-array-bound.c
+++ bc-array-bound.c
@@ -4,7 +4,7 @@ int main(void)
 {
     int a[5] = {1, 2, 3, 4, 5};
     int s = 0;
-    for (int i = 0; i < 5; i++) s += a[i];
+    for (int i = 0; i <= 5; i++) s += a[i];
     printf("%d\n", s);
     return 0;
 }
```

**Model summary:** The commit expands the loop condition from i < 5 to i <= 5, causing the program to access out-of-bounds array elements and potentially segfault.

**Finding 1** (off-by-one): By changing the loop to run from 0 to 5 (inclusive), the program accesses array indices 5 and beyond, which are out of bounds and may cause a segmentation fault.

`c-array-bound` grade: ______

---

## `rb-string-mutate`  (ruby)

Run it:  `cd bench/basic/rb-string-mutate && <run> pre.rb` then the same for `post.rb`

```diff
diff --git arb-string-mutate.rb brb-string-mutate.rb
index 132e49e..b5538ed 100644
--- arb-string-mutate.rb
+++ brb-string-mutate.rb
@@ -1,5 +1,5 @@
 def shout(s)
-  t = s.dup
+  t = s
   t << "!"
   t
 end
```

**Model summary:** The commit replaces a duplicate of the input string with the original string in the shout method, causing the appended "!" to be lost, which is a logic error.

**Finding 1** (logic-error): By assigning the original input string to t instead of its duplicate, the method no longer appends the trailing "!" to the string, altering its behavior from the intended shout effect.

`rb-string-mutate` grade: ______

---

## `php-slice-end`  (php)

Run it:  `cd bench/basic/php-slice-end && <run> pre.php` then the same for `post.php`

```diff
diff --git aphp-slice-end.php bphp-slice-end.php
index d1f3836..8b2a90c 100644
--- aphp-slice-end.php
+++ bphp-slice-end.php
@@ -1,6 +1,6 @@
 <?php
 function firstN(array $xs, int $n): array {
-    return array_slice($xs, 0, $n);
+    return array_slice($xs, 0, $n - 1);
 }
 
 echo implode(",", firstN([1, 2, 3, 4], 2)), "\n";
```

**Model summary:** The commit modifies firstN to return array_slice($xs, 0, $n - 1) instead of the original $n, causing the function to omit the last element of the input array. This alters the intended behavior and may produce incorrect results for callers expecting the full slice up to the specified count.

**Finding 1** (logic-error): firstN now returns all elements from the start up to but not including the nth element, whereas the original returned the first n elements. This mismatch can lead to unexpected output or off-by-one errors for callers.

`php-slice-end` grade: ______

---

## `ts-rename-param`  (typescript)

Run it:  `cd bench/basic/ts-rename-param && <run> pre.ts` then the same for `post.ts`

```diff
diff --git ats-rename-param.ts bts-rename-param.ts
index 43e5f48..f0b6161 100644
--- ats-rename-param.ts
+++ bts-rename-param.ts
@@ -1,7 +1,7 @@
 interface Point { x: number; y: number; }
 
-function dist(p: Point): number {
-  return Math.abs(p.x) + Math.abs(p.y);
+function dist(pt: Point): number {
+  return Math.abs(pt.x) + Math.abs(pt.y);
 }
 
 console.log(dist({ x: -3, y: 4 }));
```

**Model summary:** The commit renames a parameter from `p` to `pt` in the `dist` function without altering its usage. This is a simple renaming change with no functional impact, so it does not introduce any defects.

**Findings:** none reported

`ts-rename-param` grade: ______

---

## `php-loose-compare`  (php)

Run it:  `cd bench/basic/php-loose-compare && <run> pre.php` then the same for `post.php`

```diff
diff --git aphp-loose-compare.php bphp-loose-compare.php
index 6db1c4c..bd43524 100644
--- aphp-loose-compare.php
+++ bphp-loose-compare.php
@@ -1,6 +1,6 @@
 <?php
 function same($a, $b): bool {
-    return $a === $b;
+    return $a == $b;
 }
 
 var_dump(same("0", 0));
```

**Model summary:** The commit replaces strict equality ($a === $b) with loose equality ($a == $b) in the same() function, causing the function to return true for non-identical values that are equal in value but not identical in type (e.g., "0" and 0). This change alters behavior and may introduce unexpected results for callers.

**Finding 1** (input-validation): Using loose equality ($a == $b) makes the function return true for inputs that are equal in value but of different types (e.g., "0" and 0). This can lead to incorrect comparisons and logic errors in callers that expect strict equality.

`php-loose-compare` grade: ______

---

## `java-concurrent-modify`  (java)

Run it:  `cd bench/basic/java-concurrent-modify && <run> pre.java` then the same for `post.java`

```diff
diff --git ajava-concurrent-modify.java bjava-concurrent-modify.java
index 86c71f9..b2bc777 100644
--- ajava-concurrent-modify.java
+++ bjava-concurrent-modify.java
@@ -1,13 +1,12 @@
 import java.util.ArrayList;
-import java.util.Iterator;
 import java.util.List;
 
 class Main {
     public static void main(String[] args) {
         List<Integer> xs = new ArrayList<>(List.of(1, 2, 3, 4));
-        for (Iterator<Integer> it = xs.iterator(); it.hasNext(); ) {
-            if (it.next() % 2 == 0) {
-                it.remove();
+        for (Integer x : xs) {
+            if (x % 2 == 0) {
+                xs.remove(x);
             }
         }
         System.out.println(xs);
```

**Model summary:** The commit replaces an Iterator-based loop with a for-each loop that removes elements from the list while iterating. The new logic correctly skips removed elements and does not introduce concurrency issues, so no defects are apparent.

**Findings:** none reported

`java-concurrent-modify` grade: ______

---

## `py-pop-guard`  (python)

Run it:  `cd bench/basic/py-pop-guard && <run> pre.py` then the same for `post.py`

```diff
diff --git apy-pop-guard.py bpy-pop-guard.py
index 33ed922..65ae104 100644
--- apy-pop-guard.py
+++ bpy-pop-guard.py
@@ -17,8 +17,6 @@ class LinkedList:
         self.size += 1
 
     def pop(self):
-        if self.head is None:
-            raise IndexError("pop from empty list")
         node = self.head
         self.head = node.next
         self.size -= 1
```

**Model summary:** The commit removes the explicit check for an empty list in LinkedList.pop(), causing the method to silently succeed when called on an empty list, which can lead to unexpected behavior or missing IndexError.

**Finding 1** (error-handling): By removing the check for self.head being None, pop() no longer raises IndexError when called on an empty list, potentially returning None or corrupting internal state instead of raising a clear error, which can hide bugs or cause runtime failures downstream.

`py-pop-guard` grade: ______

---

## `js-extract-helper`  (javascript)

Run it:  `cd bench/basic/js-extract-helper && <run> pre.js` then the same for `post.js`

```diff
diff --git ajs-extract-helper.js bjs-extract-helper.js
index 2e15aa7..861449c 100644
--- ajs-extract-helper.js
+++ bjs-extract-helper.js
@@ -1,6 +1,9 @@
-function report(xs) {
+function sum(xs) {
   let s = 0;
   for (const x of xs) s += x;
-  return `sum=${s} n=${xs.length}`;
+  return s;
+}
+function report(xs) {
+  return `sum=${sum(xs)} n=${xs.length}`;
 }
 console.log(report([1, 2, 3]));
```

**Model summary:** The commit renames the helper function from `report` to `sum` and removes the string interpolation, returning the numeric sum instead. This alters the function's output type but does not introduce any runtime defects.

**Findings:** none reported

`js-extract-helper` grade: ______

---

## `rb-range-bound`  (ruby)

Run it:  `cd bench/basic/rb-range-bound && <run> pre.rb` then the same for `post.rb`

```diff
diff --git arb-range-bound.rb brb-range-bound.rb
index 22e16f5..716d759 100644
--- arb-range-bound.rb
+++ brb-range-bound.rb
@@ -1,5 +1,5 @@
 def total(n)
-  (1..n).sum
+  (1...n).sum
 end
 
 puts total(5)
```

**Model summary:** The commit replaces `(1..n).sum` with `(1...n).sum`, changing the range from inclusive to exclusive. This alters the summation behavior and may produce incorrect results for certain inputs.

**Finding 1** (logic-error): Using `(1...n).sum` computes the sum of numbers from 1 to n-1 instead of 1 to n, so calling `total(5)` will return 10 instead of the intended 15, leading to incorrect output.

`rb-range-bound` grade: ______

---

## `ts-slice-end`  (typescript)

Run it:  `cd bench/basic/ts-slice-end && <run> pre.ts` then the same for `post.ts`

```diff
diff --git ats-slice-end.ts bts-slice-end.ts
index e130425..1ccce4e 100644
--- ats-slice-end.ts
+++ bts-slice-end.ts
@@ -1,5 +1,5 @@
 function firstN(xs: number[], n: number): number[] {
-  return xs.slice(0, n);
+  return xs.slice(0, n - 1);
 }
 
 console.log(firstN([1, 2, 3, 4, 5], 3).join(","));
```

**Model summary:** The commit modifies firstN to return xs.slice(0, n - 1) instead of xs.slice(0, n), causing it to exclude the last element of the input array. This alters the function's behavior and may produce incorrect results for callers expecting the original slice semantics.

**Finding 1** (logic-error): firstN now returns all elements up to but not including the nth element, whereas the previous implementation returned all elements up to and including the nth element. This mismatch can lead to missing elements in the output array, breaking any caller that relies on the inclusive slice behavior.

`ts-slice-end` grade: ______

---

## `js-rename-param`  (javascript)

Run it:  `cd bench/basic/js-rename-param && <run> pre.js` then the same for `post.js`

```diff
diff --git ajs-rename-param.js bjs-rename-param.js
index d0ef213..bb34f3d 100644
--- ajs-rename-param.js
+++ bjs-rename-param.js
@@ -1,5 +1,5 @@
-function scale(xs, k) {
-  return xs.map((x) => x * k);
+function scale(values, factor) {
+  return values.map((v) => v * factor);
 }
 
 console.log(scale([1, 2, 3], 2).join(","));
```

**Model summary:** The commit renames the parameter of the scale function from 'xs' to 'values' and updates the map callback accordingly. This is a simple parameter renaming with no functional changes, so it does not introduce any new runtime defects.

**Findings:** none reported

`js-rename-param` grade: ______

---
