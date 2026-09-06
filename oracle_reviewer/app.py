"""Oracle Reviewer 3B — a local, private code reviewer.

    python -m oracle_reviewer.app

Nothing leaves this machine: the model is served locally and there is no GitHub
integration, no telemetry and no network call other than to the local model host.

Layout is deliberately the one a reviewer expects: the changed files down the
left with their measured risk, the diff and the review on the right, and Apply /
Discard on the suggestion.
"""
from __future__ import annotations

import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import core

BG = "#1e1e2e"; FG = "#cdd6f4"; SUB = "#9399b2"; PANEL = "#181825"
ADD = "#a6e3a1"; DEL = "#f38ba8"; ACC = "#89b4fa"
RISK = {"high": "#f38ba8", "change": "#f9e2af", "fixes": "#a6e3a1", "ui-text": "#89b4fa", "unreachable": "#6c7086",
        "unclear": "#cba6f7", "none": "#6c7086", "unverified": "#9399b2"}
DOT = {"high": "●", "change": "●", "fixes": "●", "ui-text": "◇", "unreachable": "○",
       "unclear": "◆", "none": "○", "unverified": "○"}


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Oracle Reviewer 3B")
        self.geometry("1280x820")
        self.minsize(1100, 700)
        self.configure(bg=BG)
        self.reviews: list[core.FileReview] = []
        self.q: queue.Queue = queue.Queue()
        self._style()
        self._build()
        self.after(120, self._drain)
        self._load_commits()

    def _style(self) -> None:
        """ttk ignores bg/fg, so the combobox needs the theme spelled out."""
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure("Oracle.TCombobox", fieldbackground=BG, background=PANEL,
                     foreground=FG, arrowcolor=SUB, bordercolor=PANEL,
                     lightcolor=PANEL, darkcolor=PANEL, insertcolor=FG)
        st.map("Oracle.TCombobox", fieldbackground=[("readonly", BG)],
               selectbackground=[("!focus", BG)], selectforeground=[("!focus", FG)])
        # The dropdown is a Tk listbox that the style does not reach.
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACC)
        self.option_add("*TCombobox*Listbox.selectForeground", PANEL)
        self.option_add("*TCombobox*Listbox.font", "TkFixedFont")

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        bar = tk.Frame(self, bg=PANEL, padx=10, pady=8)
        bar.pack(fill="x")
        tk.Label(bar, text="Oracle Reviewer 3B", bg=PANEL, fg=ACC,
                 font=("TkDefaultFont", 13, "bold")).pack(side="left")
        tk.Label(bar, text="  local · private · execution-grounded", bg=PANEL,
                 fg=SUB).pack(side="left")

        form = tk.Frame(self, bg=PANEL, padx=10, pady=6)
        form.pack(fill="x")
        self.repo = tk.StringVar(value=".")
        self.commit = tk.StringVar(value="HEAD")
        self.cmd = tk.StringVar(value="pytest -q")
        self.model = tk.StringVar(value="oracle-reviewer-3b")
        self.host = tk.StringVar(value="http://localhost:8111")

        def field(label, var, width, browse=False):
            tk.Label(form, text=label, bg=PANEL, fg=SUB).pack(side="left",
                                                              padx=(8, 3))
            e = tk.Entry(form, textvariable=var, width=width, bg=BG, fg=FG,
                         insertbackground=FG, relief="flat")
            e.pack(side="left")
            if browse:
                tk.Button(form, text="…", command=self._pick, bg=BG, fg=FG,
                          relief="flat", padx=6).pack(side="left", padx=2)
            return e

        repo_entry = field("repo", self.repo, 22, browse=True)
        # Retyping the path by hand should reload the list too, not only the
        # browse button. Debounced, because a trace fires on every keystroke
        # and half a typed path is not a repository.
        self.repo.trace_add("write", self._repo_changed)
        repo_entry.bind("<Return>", lambda _e: self._load_commits())

        tk.Label(form, text="commit", bg=PANEL, fg=SUB).pack(side="left",
                                                             padx=(8, 3))
        self.commits = ttk.Combobox(form, textvariable=self.commit, width=34,
                                    style="Oracle.TCombobox")
        self.commits.pack(side="left")
        field("run", self.cmd, 16)
        field("model", self.model, 18)
        self.go = tk.Button(form, text="Review", command=self._start, bg=ACC,
                            fg=PANEL, relief="flat", padx=18,
                            font=("TkDefaultFont", 10, "bold"))
        self.go.pack(side="right", padx=(12, 4))

        body = tk.PanedWindow(self, orient="horizontal", bg=BG, sashwidth=4,
                              bd=0)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        left = tk.Frame(body, bg=PANEL)
        tk.Label(left, text="CHANGED FILES", bg=PANEL, fg=SUB,
                 anchor="w", padx=10, pady=6).pack(fill="x")
        self.files = tk.Listbox(left, bg=PANEL, fg=FG, selectbackground=ACC,
                                selectforeground=PANEL, relief="flat",
                                activestyle="none", font=("TkFixedFont", 10),
                                highlightthickness=0)
        self.files.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.files.bind("<<ListboxSelect>>", self._select)
        body.add(left, width=330, minsize=240)

        right = tk.Frame(body, bg=BG)
        self.badge = tk.Label(right, text="", bg=BG, fg=SUB, anchor="w",
                              padx=10, pady=6,
                              font=("TkDefaultFont", 11, "bold"))
        self.badge.pack(fill="x")

        self.review = tk.Text(right, height=7, bg=PANEL, fg=FG, relief="flat",
                              wrap="word", padx=12, pady=10,
                              font=("TkDefaultFont", 11))
        self.review.pack(fill="x", padx=6)
        self.review.configure(state="disabled")

        tk.Label(right, text="DIFF", bg=BG, fg=SUB, anchor="w",
                 padx=10, pady=4).pack(fill="x")
        self.diff = tk.Text(right, bg=PANEL, fg=FG, relief="flat", wrap="none",
                            padx=12, pady=8, font=("TkFixedFont", 10))
        self.diff.pack(fill="both", expand=True, padx=6)
        self.diff.tag_configure("add", foreground=ADD)
        self.diff.tag_configure("del", foreground=DEL)
        self.diff.tag_configure("hd", foreground=SUB)
        self.diff.configure(state="disabled")

        acts = tk.Frame(right, bg=BG, pady=8)
        acts.pack(fill="x")
        self.apply_b = tk.Button(acts, text="Apply suggestion",
                                 command=self._apply, bg=ADD, fg=PANEL,
                                 relief="flat", padx=14, state="disabled",
                                 font=("TkDefaultFont", 10, "bold"))
        self.apply_b.pack(side="left", padx=(10, 6))
        self.discard_b = tk.Button(acts, text="Discard", command=self._discard,
                                   bg=PANEL, fg=FG, relief="flat", padx=14,
                                   state="disabled")
        self.discard_b.pack(side="left")
        body.add(right, minsize=520)

        self.status = tk.Label(self, text="ready", bg=PANEL, fg=SUB, anchor="w",
                               padx=10, pady=4)
        self.status.pack(fill="x")

    # ---------------------------------------------------------------- commits
    def commit_ref(self) -> str:
        """The revision git should be given.

        The dropdown shows "<sha>  <subject>" because a bare sha is unreadable,
        but only the first token may reach git -- "abc1234  fix parser^" is not
        a revision. Typing "HEAD" or a sha by hand still works: the first token
        of that is itself.
        """
        return (self.commit.get().split() or ["HEAD"])[0]

    def _repo_changed(self, *_a) -> None:
        # A sha only means something in the repo it came from. Once the repo
        # changes, the selection is stale -- drop it back to HEAD so _listed
        # renames it to the new repo's tip rather than leaving a revision that
        # does not exist here.
        self.commit.set("HEAD")
        if getattr(self, "_repo_job", None):
            self.after_cancel(self._repo_job)
        self._repo_job = self.after(400, self._load_commits)

    def _load_commits(self) -> None:
        """Fill the dropdown from the repo. Off the UI thread: `git log` on a
        large history is fast but not instant, and this also runs on typing."""
        self._repo_job = None
        repo = self.repo.get()
        threading.Thread(target=self._read_log, args=(repo,),
                         daemon=True).start()

    def _read_log(self, repo: str) -> None:
        try:
            got = subprocess.run(
                ["git", "-C", core.repo_path(repo), "log", "-n", "200",
                 "--pretty=%h\x1f%s\x1f%cr"],
                capture_output=True, text=True, timeout=15)
        except Exception as e:
            self.q.put(("commits", (repo, [], f"{type(e).__name__}: {e}")))
            return
        if got.returncode:
            # git puts the reason on the FIRST line ("fatal: not a git
            # repository ..."); the lines after it are advice about the search
            # path, which is not what went wrong.
            lines = [l for l in got.stderr.splitlines() if l.strip()]
            why = next((l for l in lines if l.startswith("fatal:")),
                       lines[0] if lines else "not a git repository")
            self.q.put(("commits", (repo, [], why.removeprefix("fatal: "))))
            return
        out = []
        for line in got.stdout.splitlines():
            parts = line.split("\x1f")
            if len(parts) != 3:
                continue
            sha, subject, when = parts
            if len(subject) > 44:
                subject = subject[:43] + "…"
            out.append(f"{sha}  {subject}  ({when})")
        self.q.put(("commits", (repo, out, None)))

    # ---------------------------------------------------------------- actions
    def _pick(self) -> None:
        d = filedialog.askdirectory()
        if d:
            self.repo.set(d)          # the trace reloads the commit list

    def _start(self) -> None:
        self.go.configure(state="disabled")
        self.files.delete(0, "end")
        self.reviews = []
        self._show(None)
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self) -> None:
        try:
            rs = core.review_commit(
                self.repo.get(), self.commit_ref(), self.cmd.get(),
                self.host.get(), self.model.get(),
                progress=lambda m: self.q.put(("status", m)))
            self.q.put(("done", rs))
        except Exception as e:
            self.q.put(("error", f"{type(e).__name__}: {e}"))

    def _drain(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "status":
                    self.status.configure(text=payload)
                elif kind == "commits":
                    self._listed(*payload)
                elif kind == "error":
                    self.status.configure(text=payload)
                    self.go.configure(state="normal")
                    messagebox.showerror("Oracle Reviewer", payload)
                elif kind == "done":
                    self._filled(payload)
        except queue.Empty:
            pass
        self.after(120, self._drain)

    def _listed(self, repo: str, rows: list[str], err: str | None) -> None:
        if repo != self.repo.get():
            return                     # a later keystroke already superseded it
        self.commits.configure(values=["HEAD"] + rows)
        if err:
            self.status.configure(text=f"{repo}: {err}")
        elif rows and self.commit.get() in ("", "HEAD"):
            # HEAD stays the default, but name it, so the field says which
            # commit that actually is rather than making the user guess.
            self.commit.set(rows[0])

    def _filled(self, rs: list[core.FileReview]) -> None:
        self.reviews = rs
        for i, r in enumerate(rs):
            self.files.insert("end", f" {DOT[r.risk]}  {r.path}")
            self.files.itemconfig(i, foreground=RISK[r.risk])
        c = lambda k: sum(1 for r in rs if r.risk == k)
        if rs and all(r.why_unclear == "baseline" for r in rs):
            # Every file came back unmeasurable for the same reason. That is one
            # fact about the command, not N findings about the files.
            self.status.configure(
                text=f"`{self.cmd.get()}` already fails at the parent commit — "
                     f"nothing was measured for any of the {len(rs)} file(s). "
                     f"Point `run` at a command that succeeds here.")
        else:
            self.status.configure(
                text=f"{len(rs)} file(s) reviewed individually · {c('high')} high risk"
                     f" · {c('change')} behaviour change · {c('unclear')} not covered"
                     f" · {c('none')} cosmetic")
        self.go.configure(state="normal")
        if rs:
            self.files.selection_set(0)
            self._show(rs[0])

    def _select(self, _evt) -> None:
        sel = self.files.curselection()
        if sel:
            self._show(self.reviews[sel[0]])

    def _show(self, r: core.FileReview | None) -> None:
        for w in (self.review, self.diff):
            w.configure(state="normal")
            w.delete("1.0", "end")
        if r is None:
            self.badge.configure(text="")
            for w in (self.review, self.diff):
                w.configure(state="disabled")
            self.apply_b.configure(state="disabled")
            self.discard_b.configure(state="disabled")
            return

        self.badge.configure(text=f"Oracle AI   [{r.badge}]",
                             fg=RISK[r.risk])
        body = core.review_body(r, self.cmd.get())
        self.review.insert("1.0", body)

        for line in r.diff.splitlines():
            tag = ("hd" if line.startswith(("diff", "index", "---", "+++", "@@"))
                   else "add" if line.startswith("+")
                   else "del" if line.startswith("-") else None)
            self.diff.insert("end", line + "\n", tag or ())
        for w in (self.review, self.diff):
            w.configure(state="disabled")
        has = r.risk == "high"     # see tui.action_apply on why not `suggestion`
        self.apply_b.configure(state="normal" if has else "disabled")
        self.discard_b.configure(state="normal" if has else "disabled")

    def _apply(self) -> None:
        sel = self.files.curselection()
        if not sel:
            return
        r = self.reviews[sel[0]]
        base = f"{self.commit_ref()}^"
        if not messagebox.askyesno(
                "Apply suggestion",
                f"Restore {r.path} to its state before this commit?\n\n"
                f"Those exact lines are the ones that produced a clean run.\n"
                f"This edits your working tree."):
            return
        got = subprocess.run(
            ["git", "-C", self.repo.get(), "checkout", base, "--", r.path],
            capture_output=True, text=True)
        if got.returncode:
            messagebox.showerror("Apply failed", got.stderr.strip())
        else:
            self.status.configure(text=f"restored {r.path} from {base}")
            self.apply_b.configure(state="disabled")

    def _discard(self) -> None:
        self.apply_b.configure(state="disabled")
        self.discard_b.configure(state="disabled")
        self.status.configure(text="suggestion discarded")


def main() -> int:
    App().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
