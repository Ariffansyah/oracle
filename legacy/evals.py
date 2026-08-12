"""Regression check for the reviewer prompt: does it find real defects without
inventing fake ones?

    python evals.py                          # default model
    python evals.py --llm-model qwen3-coder:latest --repeat 3

Half the cases are planted defects the reviewer MUST report; half are safe diffs
it MUST leave at zero findings. Both directions matter - a prompt tweak that
fixes false negatives usually buys them back as false positives, and this is the
only thing that catches that trade.
"""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

import config
from llm_explainer.client import LLMError, OllamaClient
from llm_explainer.prompts import ReviewResult
from ml_model.kamei_metrics import MOCK_DIFF

console = Console()


@dataclass
class Case:
    name: str
    diff: str
    should_find: bool
    risk_score: float          # the prior the reviewer is shown
    note: str = ""             # what a correct finding looks like


CASES = [
    Case(
        "expiry-off-by-one", should_find=True, risk_score=0.31,
        note="`>=` admits a token at exactly expires_at",
        diff="""diff --git a/auth/session.py b/auth/session.py
--- a/auth/session.py
+++ b/auth/session.py
@@ -8,7 +8,7 @@ class SessionStore:
     def resolve(self, token):
-        if token.expires_at > now():
+        if token.expires_at >= now():
             return token.user
         return None
""",
    ),
    Case(
        "retry-loop-leak", should_find=True, risk_score=0.28,
        note="early return skips conn.close(); connection leaks on the success path",
        diff="""diff --git a/db/pool.py b/db/pool.py
--- a/db/pool.py
+++ b/db/pool.py
@@ -20,10 +20,10 @@ class Pool:
     def query(self, sql):
         conn = self.acquire()
-        try:
-            return conn.execute(sql)
-        finally:
-            conn.close()
+        result = conn.execute(sql)
+        if result.ok:
+            return result
+        conn.close()
+        raise QueryError(result.error)
""",
    ),
    Case(
        "percent-int-division", should_find=True, risk_score=0.66,
        note="integer division truncates the discount to 0 for any percent < 100",
        diff="""diff --git a/billing/discount.py b/billing/discount.py
--- a/billing/discount.py
+++ b/billing/discount.py
@@ -5,4 +5,4 @@ def apply(total, percent):
-    return total * (1 - percent / 100)
+    return total * (1 - percent // 100)
""",
    ),
    Case(
        # Was labelled "clean" until both models flagged it and both were right:
        # rejecting amount <= 0 fails zero-total orders that previously charged,
        # and swallowing an unknown promo code silently drops the discount.
        # Adding a guard is a behaviour change like any other.
        "zero-amount-guard", should_find=True, risk_score=0.94,
        note="`raise ValueError` on amount <= 0 breaks fully-discounted orders "
             "that previously posted a zero charge",
        diff="""diff --git a/payments/gateway.py b/payments/gateway.py
--- a/payments/gateway.py
+++ b/payments/gateway.py
@@ -12,6 +12,9 @@ class Gateway:
     def charge(self, amount, currency):
+        if amount <= 0:
+            raise ValueError("amount must be positive")
         return self._post("/charge", {"amount": amount, "currency": currency})
""",
    ),
    Case(
        "inert-churn", should_find=False, risk_score=0.94,
        note="renames, docstrings and a constant holding the value it replaced",
        diff=MOCK_DIFF,
    ),
    Case(
        "rename-only", should_find=False, risk_score=0.88,
        note="pure rename, behaviour identical",
        diff="""diff --git a/report/render.py b/report/render.py
--- a/report/render.py
+++ b/report/render.py
@@ -12,8 +12,8 @@ class Report:
     def build(self, rows):
-        out = []
-        for r in rows:
-            out.append(self.line(r))
-        return "\\n".join(out)
+        lines = []
+        for row in rows:
+            lines.append(self.line(row))
+        return "\\n".join(lines)
""",
    ),
    Case(
        "logging-added", should_find=False, risk_score=0.79,
        note="adds a log line and a type hint; no behavioural change",
        diff="""diff --git a/worker/task.py b/worker/task.py
--- a/worker/task.py
+++ b/worker/task.py
@@ -30,5 +30,7 @@ class Task:
-    def run(self, payload):
+    def run(self, payload: dict) -> Result:
+        log.info("running task %s", self.id)
         return self.handler(payload)
""",
    ),
]


def run_case(client: OllamaClient, case: Case) -> tuple[bool, str, ReviewResult | None]:
    try:
        review = client.review(
            diff=case.diff,
            risk_score=case.risk_score,
            risk_band=config.risk_band(case.risk_score),
            contributions=["la = 120 (+0.31)", "entropy = 0.7 (+0.18)"],
            subject="(eval case)",
            files=[case.name],
        )
    except LLMError as e:
        return False, f"error: {e}", None

    found = bool(review.findings)
    if found == case.should_find:
        detail = (review.findings[0].category if found else "clean")
        return True, detail, review
    if case.should_find:
        return False, "MISSED (returned 0 findings)", review
    return False, f"FALSE POSITIVE ({review.findings[0].category})", review


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--llm-model", default=config.OLLAMA_MODEL)
    ap.add_argument("--host", default=config.OLLAMA_HOST)
    ap.add_argument("--repeat", type=int, default=1, help="runs per case (LLMs vary)")
    ap.add_argument("--only", help="substring filter on case name")
    ap.add_argument("--verbose", action="store_true", help="print each summary")
    args = ap.parse_args(argv)

    client = OllamaClient(host=args.host, model=args.llm_model)
    cases = [c for c in CASES if not args.only or args.only in c.name]

    table = Table(title=f"prompt eval — {args.llm_model}", title_justify="left")
    table.add_column("case")
    table.add_column("expect")
    table.add_column("pass", justify="center")
    table.add_column("result")

    passed = total = 0
    started = time.time()
    for n, case in enumerate(cases, 1):
        console.print(f"[dim]({n}/{len(cases)}) {case.name} …[/]", end="\r")
        results = [run_case(client, case) for _ in range(args.repeat)]
        ok = sum(1 for r in results if r[0])
        mark = "[green]✓[/]" if ok == args.repeat else "[red]✗[/]"
        console.print(
            f"{mark} ({n}/{len(cases)}) {case.name}: {results[0][1]}"
            f"  [dim]{time.time() - started:.0f}s elapsed[/]"
        )
        passed += ok
        total += args.repeat
        mark = "[green]✓[/]" if ok == args.repeat else (
            "[yellow]~[/]" if ok else "[red]✗[/]")
        table.add_row(
            case.name,
            "finding" if case.should_find else "clean",
            f"{mark} {ok}/{args.repeat}",
            "; ".join(dict.fromkeys(r[1] for r in results)),
        )
        if args.verbose:
            for _, _, review in results:
                if review:
                    console.print(f"  [dim]{case.name}: {review.summary}[/]")

    console.print(table)
    rate = passed / total if total else 0
    style = "green" if rate == 1 else "yellow" if rate >= 0.7 else "red"
    console.print(f"[{style}]{passed}/{total} passed ({rate:.0%})[/]")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
