"""Frontend security boilerplate the base model reliably misreads.

A code LLM shown three lines of diff sees an early `return` in a React handler
and calls it a logic error - "the function exits before doing its work", "the
user gets no feedback". It cannot see that forty lines below, outside the hunk,
the submit button is already `disabled={!token}`, so the guard is belt-and-braces
against a race, not dead code.

That is contextual myopia, and it is a *context* failure before it is a model
failure. Each case here carries a `context` block - the post-commit file body,
what `llm_inference/context.py` fetches at inference time - so the training pairs
are built on the same input the model will actually receive.

These are also the hardest pairs in the set: `chosen` and `rejected` describe the
same handful of lines, so the edit distance between them is tiny, which is
precisely the regime where plain DPO drives the chosen log-probability down along
with the rejected one. Hence DPO-Positive (`DPO_LOSS_TYPE = "dpop"`).
"""

from __future__ import annotations

from dataset_builder.schema import Analysis, Finding

# The surrounding code that makes each guard obviously correct. Keyed by file.
FILE_CONTEXT: dict[str, str] = {
    "app/contact/ContactForm.tsx": """--- app/contact/ContactForm.tsx (after this commit) ---
export function ContactForm() {
  const [pending, setPending] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!token) {
      setError("Please complete the captcha.");
      return;
    }

    setPending(true);
    await submitContact(new FormData(event.currentTarget), token);
    setPending(false);
  }

  return (
    <form onSubmit={onSubmit}>
      <input name="email" required />
      <Turnstile siteKey={SITE_KEY} onSuccess={setToken} onExpire={() => setToken(null)} />
      {error && <p role="alert">{error}</p>}
      {/* the guard above is belt-and-braces: this button is already disabled */}
      <button type="submit" disabled={!token || pending}>
        {pending ? "Sending..." : "Send"}
      </button>
    </form>
  );
}""",
    "components/NewsletterForm.tsx": """--- components/NewsletterForm.tsx (after this commit) ---
export default function NewsletterForm() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sent" | "captcha">("idle");
  const turnstileRef = useRef<TurnstileInstance>(null);

  const handleSubscribe = useCallback(async () => {
    const token = turnstileRef.current?.getResponse();
    if (!token) {
      turnstileRef.current?.reset();
      setStatus("captcha");
      return;
    }

    await subscribe(email, token);
    setStatus("sent");
  }, [email]);

  return (
    <div>
      <input value={email} onChange={(e) => setEmail(e.target.value)} />
      <Turnstile ref={turnstileRef} siteKey={SITE_KEY} />
      {status === "captcha" && <p role="alert">Please complete the captcha.</p>}
      <button onClick={handleSubscribe}>Subscribe</button>
    </div>
  );
}""",
    "app/dashboard/layout.tsx": """--- app/dashboard/layout.tsx (after this commit) ---
import { redirect } from "next/navigation";

// `redirect()` throws a NEXT_REDIRECT control-flow signal that Next.js catches;
// code after it is unreachable by design and the component never renders.
export default async function DashboardLayout({ children }) {
  const session = await getSession();

  if (!session?.user) {
    redirect("/login");
  }

  return <Shell user={session.user}>{children}</Shell>;
}""",
}

# (subject, files, diff, correct analysis, the hallucination to train against)
TURNSTILE_CASES: list[tuple[str, str, str, Analysis, Analysis]] = [
    (
        "feat: require Turnstile token before contact submit",
        "app/contact/ContactForm.tsx",
        """diff --git a/app/contact/ContactForm.tsx b/app/contact/ContactForm.tsx
--- a/app/contact/ContactForm.tsx
+++ b/app/contact/ContactForm.tsx
@@ -28,10 +28,17 @@ export function ContactForm() {
   const [token, setToken] = useState<string | null>(null);
+  const [error, setError] = useState<string | null>(null);

   async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
     event.preventDefault();
+
+    if (!token) {
+      setError("Please complete the captcha.");
+      return;
+    }
+
     setPending(true);
-    await submitContact(new FormData(event.currentTarget));
+    await submitContact(new FormData(event.currentTarget), token);
     setPending(false);
   }
""",
        Analysis(
            summary="Adds a Turnstile token guard before submitting the contact "
                    "form. The early return is intended: without a captcha token "
                    "the request must not be sent. No defect.",
            findings=[],
        ),
        Analysis(
            summary="The handler can return before completing submission, "
                    "leaving the form in an inconsistent state.",
            findings=[Finding(
                category="logic-error",
                explanation="The early `return` when `token` is null skips "
                            "`setPending(true)` and the submit call, so the form "
                            "silently does nothing and the user is left without "
                            "feedback.",
            )],
        ),
    ),
    (
        "fix: verify Turnstile server-side in the signup action",
        "app/actions/signup.ts",
        """diff --git a/app/actions/signup.ts b/app/actions/signup.ts
--- a/app/actions/signup.ts
+++ b/app/actions/signup.ts
@@ -12,6 +12,14 @@ export async function signup(formData: FormData) {
   const email = formData.get("email") as string;
+  const captcha = formData.get("cf-turnstile-response") as string | null;
+
+  if (!captcha) {
+    return { ok: false, error: "captcha_required" };
+  }
+
+  const verified = await verifyTurnstile(captcha);
+  if (!verified.success) {
+    return { ok: false, error: "captcha_failed" };
+  }

   const user = await db.user.create({ data: { email } });
   return { ok: true, userId: user.id };
""",
        Analysis(
            summary="Adds server-side Turnstile verification before creating the "
                    "user. Both early returns are the intended failure path for a "
                    "missing or invalid captcha. No defect.",
            findings=[],
        ),
        Analysis(
            summary="The action now has multiple exit points that bypass user "
                    "creation, which may break the signup flow.",
            findings=[Finding(
                category="logic-error",
                explanation="Returning early on a missing captcha means "
                            "`db.user.create` is never reached, so legitimate "
                            "signups can fail silently without any account being "
                            "created.",
            )],
        ),
    ),
    (
        "feat: gate newsletter subscribe on captcha",
        "components/NewsletterForm.tsx",
        """diff --git a/components/NewsletterForm.tsx b/components/NewsletterForm.tsx
--- a/components/NewsletterForm.tsx
+++ b/components/NewsletterForm.tsx
@@ -18,8 +18,13 @@ export default function NewsletterForm() {
   const turnstileRef = useRef<TurnstileInstance>(null);

   const handleSubscribe = useCallback(async () => {
-    await subscribe(email);
+    const token = turnstileRef.current?.getResponse();
+    if (!token) {
+      turnstileRef.current?.reset();
+      return;
+    }
+
+    await subscribe(email, token);
   }, [email]);
""",
        Analysis(
            summary="Reads the Turnstile token before subscribing and resets the "
                    "widget when it is absent. The guard is intended security "
                    "boilerplate. No defect.",
            findings=[],
        ),
        Analysis(
            summary="The callback exits without subscribing and without informing "
                    "the user.",
            findings=[Finding(
                category="error-handling",
                explanation="When `getResponse()` returns undefined the function "
                            "returns without calling `subscribe`, so the "
                            "subscription is dropped and no error is surfaced to "
                            "the caller.",
            )],
        ),
    ),
    (
        "feat: block API route without a valid captcha header",
        "app/api/lead/route.ts",
        """diff --git a/app/api/lead/route.ts b/app/api/lead/route.ts
--- a/app/api/lead/route.ts
+++ b/app/api/lead/route.ts
@@ -5,6 +5,12 @@ export async function POST(req: NextRequest) {
   const body = await req.json();
+  const token = req.headers.get("cf-turnstile-token");
+
+  if (!token || !(await verifyTurnstile(token, req.ip))) {
+    return NextResponse.json({ error: "forbidden" }, { status: 403 });
+  }

   await saveLead(body);
   return NextResponse.json({ ok: true });
""",
        Analysis(
            summary="Rejects lead submissions without a verified Turnstile token. "
                    "The 403 short-circuit is the intended behaviour for an "
                    "unverified request. No defect.",
            findings=[],
        ),
        Analysis(
            summary="The route can return before saving the lead, losing data.",
            findings=[Finding(
                category="logic-error",
                explanation="`saveLead(body)` is skipped whenever the header is "
                            "missing, so lead data submitted by real users is "
                            "discarded without being persisted.",
            )],
        ),
    ),
    (
        "refactor: extract auth guard in dashboard layout",
        "app/dashboard/layout.tsx",
        """diff --git a/app/dashboard/layout.tsx b/app/dashboard/layout.tsx
--- a/app/dashboard/layout.tsx
+++ b/app/dashboard/layout.tsx
@@ -8,7 +8,11 @@ export default async function DashboardLayout({ children }) {
   const session = await getSession();

-  return <Shell>{children}</Shell>;
+  if (!session?.user) {
+    redirect("/login");
+  }
+
+  return <Shell user={session.user}>{children}</Shell>;
 }
""",
        Analysis(
            summary="Redirects unauthenticated visitors away from the dashboard "
                    "before rendering. `redirect()` throwing to unwind the render "
                    "is the documented Next.js pattern. No defect.",
            findings=[],
        ),
        Analysis(
            summary="The component may never return JSX, breaking the render.",
            findings=[Finding(
                category="null-dereference",
                explanation="If `session` is null the component calls `redirect` "
                            "and never returns an element, so React receives "
                            "undefined and the dashboard fails to render.",
            )],
        ),
    ),
]


def context_for(files: str) -> str:
    """Post-commit file body for a case, or "" when none is bundled."""
    return FILE_CONTEXT.get(files, "")


def turnstile_pairs() -> list[tuple[str, str, str, Analysis, Analysis, str]]:
    """Cases with their surrounding-code block attached."""
    return [(subject, files, diff, chosen, rejected, context_for(files))
            for subject, files, diff, chosen, rejected in TURNSTILE_CASES]


if __name__ == "__main__":
    assert len(TURNSTILE_CASES) >= 5
    for subject, files, diff, chosen, rejected in TURNSTILE_CASES:
        assert chosen.findings == [], f"{subject}: chosen must report no defect"
        assert rejected.findings, f"{subject}: rejected must hallucinate one"
        assert "diff --git" in diff and ("return" in diff or "redirect" in diff)
        assert files.split("/")[-1] in diff, f"{subject}: file not in its own diff"
    with_ctx = [c for c in turnstile_pairs() if c[5]]
    assert len(with_ctx) >= 3, "most cases should carry file context"
    ctx = context_for("app/contact/ContactForm.tsx")
    assert "disabled={!token || pending}" in ctx, \
        "context must contain the control the guard protects"
    assert "disabled" not in TURNSTILE_CASES[0][2], \
        "the diff itself must NOT show it - that is the whole point"
    cats = {r.findings[0].category for *_, r in TURNSTILE_CASES}
    print(f"{len(TURNSTILE_CASES)} frontend false-positive cases "
          f"({len(with_ctx)} with full file context), "
          f"hallucinated as: {sorted(cats)}")
