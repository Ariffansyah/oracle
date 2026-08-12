"""Synthetic commits with real annotations.

Each template is a diff plus the analysis a correct reviewer would produce, so
both builders can emit trainable data before any teacher labelling exists. The
defective templates are real defect classes; the safe ones are the traps that
make reviewers hallucinate - churn, renames, added guards, logging.
"""

from __future__ import annotations

import random

from dataset_builder.schema import Analysis, Finding

# (diff template, category, explanation) - `{n}` varies the line numbers so the
# model cannot key on a literal.
DEFECT_TEMPLATES = [
    (
        """diff --git a/auth/session.py b/auth/session.py
--- a/auth/session.py
+++ b/auth/session.py
@@ -{n},7 +{n},7 @@ class SessionStore:
     def resolve(self, token):
-        if token.expires_at > now():
+        if token.expires_at >= now():
             return token.user
         return None
""",
        "off-by-one",
        "A token is now accepted at exactly `expires_at`, so every session "
        "stays valid one tick past its expiry.",
    ),
    (
        """diff --git a/db/pool.py b/db/pool.py
--- a/db/pool.py
+++ b/db/pool.py
@@ -{n},8 +{n},8 @@ class Pool:
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
""",
        "resource-leak",
        "The success path returns before `conn.close()`, so every successful "
        "query leaks a connection until the pool is exhausted.",
    ),
    (
        """diff --git a/billing/discount.py b/billing/discount.py
--- a/billing/discount.py
+++ b/billing/discount.py
@@ -{n},4 +{n},4 @@ def apply(total, percent):
-    return total * (1 - percent / 100)
+    return total * (1 - percent // 100)
""",
        "logic-error",
        "Integer division truncates to 0 for any percent below 100, so every "
        "discount silently becomes no discount.",
    ),
    (
        """diff --git a/cache/store.py b/cache/store.py
--- a/cache/store.py
+++ b/cache/store.py
@@ -{n},5 +{n},5 @@ class Store:
     def get(self, key):
-        entry = self.data.get(key)
-        if entry is None:
-            return None
-        return entry.value
+        return self.data.get(key).value
""",
        "null-dereference",
        "A missing key now raises AttributeError on None instead of returning "
        "None, turning a cache miss into a crash.",
    ),
    (
        """diff --git a/api/handler.py b/api/handler.py
--- a/api/handler.py
+++ b/api/handler.py
@@ -{n},6 +{n},8 @@ def handle(request):
     try:
         return process(request)
-    except ValidationError as e:
-        return error_response(400, str(e))
+    except Exception:
+        return error_response(200, "ok")
""",
        "error-handling",
        "Every exception is now swallowed and reported as HTTP 200, so real "
        "failures look like successes to the caller.",
    ),
    (
        """diff --git a/worker/queue.py b/worker/queue.py
--- a/worker/queue.py
+++ b/worker/queue.py
@@ -{n},6 +{n},5 @@ class Queue:
     def pop(self):
-        with self.lock:
-            if not self.items:
-                return None
-            return self.items.pop()
+        if not self.items:
+            return None
+        return self.items.pop()
""",
        "concurrency",
        "The lock is gone, so two workers can pass the emptiness check and both "
        "pop, raising IndexError under concurrent access.",
    ),
]

SAFE_TEMPLATES = [
    """diff --git a/report/render.py b/report/render.py
--- a/report/render.py
+++ b/report/render.py
@@ -{n},8 +{n},9 @@ class Report:
     def build(self, rows):
-        out = []
-        for r in rows:
-            out.append(self.line(r))
-        return "\\n".join(out)
+        \"\"\"Render one line per row.\"\"\"
+        lines = []
+        for row in rows:
+            lines.append(self.line(row))
+        return "\\n".join(lines)
""",
    """diff --git a/worker/task.py b/worker/task.py
--- a/worker/task.py
+++ b/worker/task.py
@@ -{n},5 +{n},7 @@ class Task:
-    def run(self, payload):
+    def run(self, payload: dict) -> Result:
+        log.info("running task %s", self.id)
         return self.handler(payload)
""",
    """diff --git a/core/limits.py b/core/limits.py
--- a/core/limits.py
+++ b/core/limits.py
@@ -{n},4 +{n},7 @@
+# Requests above this are rejected upstream.
+MAX_BODY_BYTES = 1048576
+
 class Limits:
     pass
""",
    """diff --git a/util/text.py b/util/text.py
--- a/util/text.py
+++ b/util/text.py
@@ -{n},6 +{n},6 @@ def slug(value):
-    v = value.strip().lower()
-    v = v.replace(" ", "-")
-    return v
+    normalised = value.strip().lower()
+    normalised = normalised.replace(" ", "-")
+    return normalised
""",
]

SAFE_SUMMARIES = [
    "Renames locals and adds a docstring; runtime behaviour is unchanged.",
    "Adds a type hint and a log line; no behavioural change.",
    "Introduces a module constant and a comment; nothing executes differently.",
    "Renames a local variable; the computed result is identical.",
]


def mock_commits(n: int, rng: random.Random) -> list[tuple[str, Analysis]]:
    """`n` (diff, analysis) pairs, roughly half defective."""
    out = []
    for i in range(n):
        line = rng.randint(5, 200)
        if i % 2 == 0:
            diff_t, category, explanation = rng.choice(DEFECT_TEMPLATES)
            out.append((
                diff_t.format(n=line),
                Analysis(
                    summary=f"This change introduces a {category} defect.",
                    findings=[Finding(category=category, explanation=explanation)],
                ),
            ))
        else:
            idx = rng.randrange(len(SAFE_TEMPLATES))
            out.append((
                SAFE_TEMPLATES[idx].format(n=line),
                Analysis(summary=SAFE_SUMMARIES[idx], findings=[]),
            ))
    return out


if __name__ == "__main__":
    rng = random.Random(0)
    pairs = mock_commits(20, rng)
    assert len(pairs) == 20
    assert sum(1 for _, a in pairs if a.findings) == 10, "should be half defective"
    assert all("diff --git" in d for d, _ in pairs)
    cats = {a.findings[0].category for _, a in pairs if a.findings}
    print(f"20 mock commits ok, defect categories: {sorted(cats)}")
