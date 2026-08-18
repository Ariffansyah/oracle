"""Extract contrastive training pairs from CVEfixes.

Positive pair = (code_before, code_after) of one file_change: the same change
in its buggy and fixed versions. This is the training signal for the diff
encoder — no prior JIT work pretrains on fix pairs like this.

Output: one JSON line per file_change that survives the filters:
    {"before": "...", "after": "...", "language": "Java", "file": "...", "hash": "..."}
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ROOT

DB = ROOT / "data" / "cvefixes" / "CVEfixes.db"
OUT = ROOT / "data" / "contrastive_pairs.jsonl"

# Real code only. The CVEfixes snapshot holds ChangeLogs, license files and
# build scripts that would teach the encoder line noise.
CODE_LANGS = {
    "Java", "JavaScript", "TypeScript", "Python", "C", "C++", "Go", "Rust",
    "PHP", "Ruby", "C#", "Kotlin", "Swift", "Scala", "Shell", "Perl",
}
MIN_CHARS = 40      # below this it is a stub, not code
MAX_CHARS = 60_000  # above this it is generated or vendored


def main() -> int:
    db = sqlite3.connect(DB)
    cur = db.cursor()
    cur.execute(
        "SELECT hash, filename, code_before, code_after, programming_language "
        "FROM file_change "
        "WHERE code_before IS NOT NULL AND code_after IS NOT NULL "
        "AND code_before != '' AND code_after != ''"
    )
    seen: set[tuple[str, str]] = set()  # (before, after) dedupe
    kept = skipped = 0
    with open(OUT, "w") as fh:
        for hash_, file, before, after, lang in cur:
            if lang not in CODE_LANGS:
                skipped += 1
                continue
            if not (MIN_CHARS <= len(before) <= MAX_CHARS
                    and MIN_CHARS <= len(after) <= MAX_CHARS):
                skipped += 1
                continue
            key = (before, after)
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            fh.write(json.dumps({
                "before": before, "after": after,
                "language": lang, "file": file, "hash": hash_,
            }, ensure_ascii=False) + "\n")
            kept += 1
    db.close()
    langs = {}
    with open(OUT) as fh:
        for line in fh:
            lang = json.loads(line)["language"]
            langs[lang] = langs.get(lang, 0) + 1
    print(f"{kept} pairs -> {OUT} ({skipped} skipped)")
    print("languages:", ", ".join(f"{k} {v}" for k, v in
                                  sorted(langs.items(), key=lambda kv: -kv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
