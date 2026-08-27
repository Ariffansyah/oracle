"""Generate the clean-direction cases the SFT corpus has never had.

`sft_mechanism_v1` taught the model 27 bug families in one direction only - every
mechanism case is `buggy: true`. The measured result was recall 33/33 and
precision 6/13: the model learned the constructs and now reports them wherever it
sees them. The counterweight is the same constructs where they are *not* a
defect, and there are two kinds worth distinguishing:

  fix       the pilot case run backwards - a commit that REMOVES the defect.
            Teaches direction: seeing `intdiv` disappear is not seeing it appear.
  refactor  a behaviour-preserving rename on the correct program. Teaches the
            in-place edit, which is the single fabrication behind six of
            `mechanism-v1`'s seven false alarms ("the call was removed").

Both are verified by execution before they are written, and a case that does not
behave as its label claims is dropped rather than shipped. `basic_bench.py`
cannot host these: its `verify()` calls a case clean only when pre and post
produce identical output, which is false for a fix by construction. That is why
these carry a three-value `label` instead of a `buggy` flag.

    python bench/make_clean_direction.py            # write and verify
    python bench/make_clean_direction.py --verify   # re-prove, write nothing
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
PILOT = BENCH / "mechanism_pilot"
OUT = BENCH / "clean_direction"

# Same runners basic_bench.py uses, kept in step with it deliberately.
RUN = {
    "c":          lambda p, t: (["gcc", "-O0", "-w", "-o", str(t / "a.out"), str(p)], [str(t / "a.out")]),
    "go":         lambda p, t: (None, ["go", "run", str(p)]),
    "java":       lambda p, t: (None, ["java", str(p)]),
    "javascript": lambda p, t: (None, ["node", str(p)]),
    "php":        lambda p, t: (None, ["php", str(p)]),
    "python":     lambda p, t: (None, ["python3", str(p)]),
    "ruby":       lambda p, t: (None, ["ruby", str(p)]),
    "rust":       lambda p, t: (["rustc", "-A", "warnings", "-o", str(t / "a.out"), str(p)], [str(t / "a.out")]),
    "typescript": lambda p, t: (None, ["deno", "run", "-q", "--no-check", str(p)]),
}

# Identifiers that are not the program's own locals. Renaming one of these
# changes what the program calls, not what it names.
RESERVED = set("""
int char double float long short void const static return if else for while do
switch case break continue struct typedef sizeof printf main func package import
var range make len cap append print println fmt public class private String
System out new this null true false let const function console log Math Number
Array Object def end puts require module do elsif unless nil self lambda
fn let mut pub use std impl struct enum match Some None Ok Err vec String i32
u32 usize f64 println echo array count strlen foreach as elseif function
from typing List Dict Optional def class pass raise try except with yield
number string boolean interface type export default async await
float64 float32 int64 int32 uint8 byte rune bool include stdio stdlib string_h
""".split())

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def run(path: Path, lang: str, tmp: Path) -> tuple[int, str]:
    build, cmd = RUN[lang](path, tmp)
    if build:
        b = subprocess.run(build, capture_output=True, text=True, cwd=tmp)
        if b.returncode:
            return b.returncode, f"[build failed] {b.stderr[:200]}"
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=tmp, timeout=60)
    return p.returncode, (p.stdout + p.stderr).strip()


def rename_candidate(src: str) -> str | None:
    """The program's own most-used local name, or None if there isn't a safe one.

    Type and class names are excluded, not because renaming them is unsafe in
    principle but because it stops being a *local* rename: java coupling a public
    class to its filename, `float64` being a go builtin, `include` being a C
    preprocessor directive. Execution catches all three anyway - this just stops
    wasting a case on them.
    """
    declared = set(re.findall(r"\b(?:class|struct|enum|interface|type)\s+(\w+)", src))
    declared |= set(re.findall(r"^\s*#\s*(\w+)", src, re.M))
    counts: dict[str, int] = {}
    for m in IDENT.finditer(src):
        name = m.group(0)
        if name in RESERVED or name in declared or len(name) < 3:
            continue
        counts[name] = counts.get(name, 0) + 1
    # >=2 uses, so the rename is an in-place edit on several lines rather than a
    # one-token change that word-diff renders as a single marker.
    ranked = [n for n, c in sorted(counts.items(), key=lambda kv: -kv[1]) if c >= 2]
    return ranked[0] if ranked else None


def rename(src: str, old: str, new: str) -> str:
    return re.sub(rf"\b{re.escape(old)}\b", new, src)


def cases() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(PILOT.glob("*/meta.json"))]


def build(write: bool) -> tuple[int, int]:
    tmp = OUT / ".tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    made, skipped = 0, 0
    for c in cases():
        cid, lang, ext = c["id"], c["language"], c["ext"]
        d = PILOT / cid
        pre_src = (d / f"pre.{ext}").read_text()      # correct program
        post_src = (d / f"post.{ext}").read_text()    # defective program

        rc_pre, out_pre = run(d / f"pre.{ext}", lang, tmp)
        rc_post, out_post = run(d / f"post.{ext}", lang, tmp)

        # --- fix direction: the defect is removed by this commit --------------
        fid = f"{cid}-fix"
        if (rc_pre, out_pre) != (rc_post, out_post):
            emit(fid, lang, ext, post_src, pre_src, "fix", c,
                 f"reverses {cid}: {out_post!r} -> {out_pre!r}", write)
            made += 1
        else:
            skipped += 1
            print(f"  skip {fid}: pre and post behave identically, so there is "
                  f"no defect to remove")

        # --- refactor direction: behaviour-preserving in-place edit -----------
        old = rename_candidate(pre_src)
        if not old:
            skipped += 1
            print(f"  skip {cid}-rename: no safe local identifier")
            continue
        new = f"{old}_x" if not old.endswith("_x") else f"{old}2"
        ren_src = rename(pre_src, old, new)
        if ren_src == pre_src:
            skipped += 1
            continue
        cls = re.search(r"\b(?:public\s+)?class\s+(\w+)", pre_src)
        probe = tmp / (f"{cls.group(1)}.{ext}" if lang == "java" and cls
                       else f"probe.{ext}")
        probe.write_text(ren_src)
        try:
            rc_ren, out_ren = run(probe, lang, tmp)
        except Exception as e:
            rc_ren, out_ren = -1, str(e)
        if (rc_ren, out_ren) == (rc_pre, out_pre):
            emit(f"{cid}-rename", lang, ext, pre_src, ren_src, "refactor", c,
                 f"renames the local `{old}` to `{new}`; output stays {out_pre!r}",
                 write, renamed=(old, new))
            made += 1
        else:
            skipped += 1
            print(f"  skip {cid}-rename: rename changed behaviour "
                  f"({out_pre!r} -> {out_ren!r})")
    shutil.rmtree(tmp, ignore_errors=True)
    return made, skipped


def emit(cid: str, lang: str, ext: str, pre: str, post: str, label: str,
         parent: dict, note: str, write: bool, renamed=None) -> None:
    if not write:
        return
    d = OUT / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / f"pre.{ext}").write_text(pre)
    (d / f"post.{ext}").write_text(post)
    meta = {"id": cid, "language": lang, "ext": ext, "label": label,
            "parent": parent["id"], "category": parent["category"], "note": note}
    if renamed:
        meta["renamed"] = list(renamed)
    (d / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")


def verify() -> int:
    """Re-prove every generated case behaves as its label claims."""
    tmp = OUT / ".tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    bad = 0
    metas = sorted(OUT.glob("*/meta.json"))
    for mp in metas:
        m = json.loads(mp.read_text())
        d, ext = mp.parent, m["ext"]
        rc_pre, out_pre = run(d / f"pre.{ext}", m["language"], tmp)
        rc_post, out_post = run(d / f"post.{ext}", m["language"], tmp)
        same = (rc_pre, out_pre) == (rc_post, out_post)
        ok = same if m["label"] == "refactor" else not same
        if not ok:
            bad += 1
            print(f"  BAD LABEL {m['id']} ({m['label']}): "
                  f"pre={out_pre!r} post={out_post!r}")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{len(metas) - bad}/{len(metas)} clean-direction cases verified")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", action="store_true",
                    help="only re-prove existing cases, generate nothing")
    ap.add_argument("--from", dest="src", type=Path, default=PILOT,
                    help="directory of buggy cases to derive from")
    ap.add_argument("--out", dest="dst", type=Path, default=OUT,
                    help="where to write the derived cases")
    args = ap.parse_args(argv)
    globals()["PILOT"] = args.src.resolve()
    globals()["OUT"] = args.dst.resolve()
    if args.verify:
        return 1 if verify() else 0
    made, skipped = build(write=True)
    print(f"\n{made} clean-direction cases written to {OUT}, {skipped} skipped")
    return 1 if verify() else 0


if __name__ == "__main__":
    sys.exit(main())
