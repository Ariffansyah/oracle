"""Context retrieval - what the model needs beyond the hunk.

A three-line diff is a keyhole. `if (!token) return;` looks like dead code, or a
handler that silently does nothing, until you can see the submit button forty
lines below that is already `disabled={!token}`. The guard is belt-and-braces;
the diff alone cannot show that, and the model hallucinates a logic error.

Two mechanisms, cheapest first:

  expanded_diff   `git diff -U50` - the same change with fifty lines of
                  surrounding code per hunk. Usually enough.
  file_snapshot   `git show <rev>:<path>` - the whole post-commit file, attached
                  when it is small enough to be worth the tokens.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (CONTEXT_MAX_CHARS, EXPANDED_CONTEXT_LINES,
                    FULL_FILE_MAX_CHARS)


def _git(args: list[str], repo: str, default: str | None = None) -> str:
    proc = subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        if default is None:
            raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
        return default
    return proc.stdout


@dataclass
class CommitContext:
    """Everything handed to the model for one commit."""

    rev: str
    subject: str = ""
    author: str = ""
    diff: str = ""                       # standard unified=3
    expanded_diff: str = ""              # unified=EXPANDED_CONTEXT_LINES
    files: list[str] = field(default_factory=list)
    snapshots: dict[str, str] = field(default_factory=dict)  # path -> file body
    truncated: list[str] = field(default_factory=list)

    def context_block(self, max_chars: int = CONTEXT_MAX_CHARS) -> str:
        """Full-file bodies, budgeted. Empty string when nothing fits."""
        if not self.snapshots:
            return ""
        parts, used = [], 0
        for path, body in self.snapshots.items():
            block = f"--- {path} (after this commit) ---\n{body}\n"
            if used + len(block) > max_chars:
                self.truncated.append(path)
                continue
            parts.append(block)
            used += len(block)
        return "\n".join(parts)


def changed_files(repo: str, rev: str) -> list[str]:
    out = _git(["show", "--name-only", "--format=", rev], repo, default="")
    return [line.strip() for line in out.splitlines() if line.strip()]


def expanded_diff(repo: str, rev: str,
                  lines: int = EXPANDED_CONTEXT_LINES) -> str:
    """`git show -U<lines>` - the change with room around it."""
    return _git(["show", "--format=", f"--unified={lines}", rev], repo, default="")


def file_snapshot(repo: str, rev: str, path: str,
                  max_chars: int = FULL_FILE_MAX_CHARS) -> str | None:
    """The file as it exists *after* the commit, or None if too big/deleted."""
    body = _git(["show", f"{rev}:{path}"], repo, default="")
    if not body or len(body) > max_chars:
        return None
    return body


def gather(repo: str, rev: str, lines: int = EXPANDED_CONTEXT_LINES,
           with_snapshots: bool = True) -> CommitContext:
    """Diff, expanded diff, and post-commit file bodies for one revision."""
    meta = _git(["show", "-s", "--format=%s%x00%an", rev], repo, default="\x00")
    subject, _, author = meta.strip().partition("\x00")

    ctx = CommitContext(
        rev=rev,
        subject=subject,
        author=author,
        diff=_git(["show", "--format=", "--unified=3", rev], repo, default=""),
        expanded_diff=expanded_diff(repo, rev, lines),
        files=changed_files(repo, rev),
    )
    if with_snapshots:
        for path in ctx.files:
            if (body := file_snapshot(repo, rev, path)) is not None:
                ctx.snapshots[path] = body
    return ctx


def gather_worktree(repo: str, lines: int = EXPANDED_CONTEXT_LINES) -> CommitContext:
    """Same, for uncommitted changes - review before you commit."""
    diff = _git(["diff", "HEAD", "--unified=3"], repo, default="")
    files = [f.strip() for f in
             _git(["diff", "HEAD", "--name-only"], repo, default="").splitlines()
             if f.strip()]
    ctx = CommitContext(
        rev="WORKTREE", subject="(uncommitted changes)",
        diff=diff,
        expanded_diff=_git(["diff", "HEAD", f"--unified={lines}"], repo, default=""),
        files=files,
    )
    for path in files:
        target = Path(repo) / path
        if target.is_file() and target.stat().st_size <= FULL_FILE_MAX_CHARS:
            ctx.snapshots[path] = target.read_text(errors="replace")
    return ctx


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        run = lambda *a: subprocess.run(["git", "-C", tmp, *a], check=True,
                                        capture_output=True)
        run("init", "-q")
        src = Path(tmp) / "form.tsx"
        # A guard whose justification lives far outside a 3-line hunk.
        src.write_text("const a = 1;\n" * 40 + "if (!token) return;\n"
                       + "const b = 2;\n" * 40 + "<button disabled={!token} />\n")
        run("add", "-A")
        run("-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "init")

        ctx = gather(tmp, "HEAD")
        assert ctx.files == ["form.tsx"], ctx.files
        assert "form.tsx" in ctx.snapshots
        assert "disabled={!token}" in ctx.snapshots["form.tsx"], \
            "snapshot must carry the code the hunk cannot show"
        assert len(ctx.expanded_diff) >= len(ctx.diff)
        assert ctx.context_block(), "context block should not be empty"
        # Budget must drop what does not fit rather than overflow.
        assert ctx.context_block(max_chars=10) == ""
        print(f"context ok: {len(ctx.files)} file(s), diff {len(ctx.diff)}B, "
              f"expanded {len(ctx.expanded_diff)}B, "
              f"snapshot {len(ctx.snapshots['form.tsx'])}B")
