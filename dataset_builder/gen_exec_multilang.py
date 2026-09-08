"""Generate an execution-verified behaviour-change corpus in many languages.

    python -m dataset_builder.gen_exec_multilang --out data/exec_ml.jsonl

The label is not a heuristic. Each program is emitted twice -- `pre` and `post`
-- both are RUN, and `differs` is set by comparing stdout, stderr and exit code.
That is the whole point: every JIT corpus in the literature labels commits by
SZZ, and `bench/direction_probe.py` measures what that costs (a defect and its
own repair are indistinguishable on size-matched pairs, 14/35, p = 0.31).

FAMILY DISJOINTNESS IS LOAD-BEARING. The evaluation set is the fixture triplets
in `bench/mechanism_pilot` and `bench/clean_direction`. Every family name here
is checked against those at build time (`--check-disjoint`, on by default) and
the build fails if one collides. Generating training data from the fixtures the
model is scored on is the leak this project has already been bitten by once --
see RESULTS.md, "The gate was trained on its own evaluation set".

Each family emits BOTH classes from the same program:
  * a semantic edit   -> behaviour is expected to change
  * a cosmetic edit   -> behaviour is expected to be preserved
The expectation is only a sanity check; the LABEL is what running produced. A
family whose semantic edit turns out not to change output is kept, with the
measured label, and counted in the summary.
"""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------- templates
# One shape per family, written per language. `{a}`/`{b}`/`{n}` are randomised
# per sample so a family yields many distinct programs rather than one repeated.
# Families are deliberately NOT the fixture families (see module docstring).

SHAPES: dict[str, dict[str, str]] = {
    "g_accumulate_upto": {
        "py": "def total(n):\n    s = 0\n    for i in range(1, n + 1):\n        s += i\n    return s\n\nprint(total({n}))\n",
        "js": "function total(n) {{\n  let s = 0;\n  for (let i = 1; i <= n; i++) {{\n    s += i;\n  }}\n  return s;\n}}\nconsole.log(total({n}));\n",
        "rb": "def total(n)\n  s = 0\n  (1..n).each {{ |i| s += i }}\n  s\nend\nputs total({n})\n",
        "php": "<?php\nfunction total($n) {{\n  $s = 0;\n  for ($i = 1; $i <= $n; $i++) {{\n    $s += $i;\n  }}\n  return $s;\n}}\necho total({n}), \"\\n\";\n",
    },
    "g_scaled_ratio": {
        "py": "def pct(a, b):\n    return a * 100 / b\n\nprint('{{:.2f}}'.format(pct({a}, {b})))\n",
        "js": "function pct(a, b) {{\n  return (a * 100) / b;\n}}\nconsole.log(pct({a}, {b}).toFixed(2));\n",
        "rb": "def pct(a, b)\n  a * 100.0 / b\nend\nputs format('%.2f', pct({a}, {b}))\n",
        "php": "<?php\nfunction pct($a, $b) {{\n  return $a * 100 / $b;\n}}\nprintf(\"%.2f\\n\", pct({a}, {b}));\n",
    },
    "g_threshold_count": {
        "py": "def above(xs, t):\n    c = 0\n    for x in xs:\n        if x > t:\n            c += 1\n    return c\n\nprint(above([{a}, {b}, {n}], {b}))\n",
        "js": "function above(xs, t) {{\n  let c = 0;\n  for (const x of xs) {{\n    if (x > t) c += 1;\n  }}\n  return c;\n}}\nconsole.log(above([{a}, {b}, {n}], {b}));\n",
        "rb": "def above(xs, t)\n  c = 0\n  xs.each {{ |x| c += 1 if x > t }}\n  c\nend\nputs above([{a}, {b}, {n}], {b})\n",
        "php": "<?php\nfunction above($xs, $t) {{\n  $c = 0;\n  foreach ($xs as $x) {{ if ($x > $t) $c += 1; }}\n  return $c;\n}}\necho above([{a}, {b}, {n}], {b}), \"\\n\";\n",
    },
    "g_running_peak": {
        "py": "def peak(xs):\n    best = xs[0]\n    for x in xs:\n        if x > best:\n            best = x\n    return best\n\nprint(peak([{a}, {n}, {b}]))\n",
        "js": "function peak(xs) {{\n  let best = xs[0];\n  for (const x of xs) {{\n    if (x > best) best = x;\n  }}\n  return best;\n}}\nconsole.log(peak([{a}, {n}, {b}]));\n",
        "rb": "def peak(xs)\n  best = xs[0]\n  xs.each {{ |x| best = x if x > best }}\n  best\nend\nputs peak([{a}, {n}, {b}])\n",
        "php": "<?php\nfunction peak($xs) {{\n  $best = $xs[0];\n  foreach ($xs as $x) {{ if ($x > $best) $best = $x; }}\n  return $best;\n}}\necho peak([{a}, {n}, {b}]), \"\\n\";\n",
    },
    "g_join_labels": {
        "py": "def label(k, v):\n    return str(k) + ':' + str(v)\n\nprint(label({a}, {b}))\n",
        "js": "function label(k, v) {{\n  return String(k) + ':' + String(v);\n}}\nconsole.log(label({a}, {b}));\n",
        "rb": "def label(k, v)\n  k.to_s + ':' + v.to_s\nend\nputs label({a}, {b})\n",
        "php": "<?php\nfunction label($k, $v) {{\n  return strval($k) . ':' . strval($v);\n}}\necho label({a}, {b}), \"\\n\";\n",
    },
    "g_tail_slice": {
        "py": "def tail(xs, k):\n    return xs[k:]\n\nprint(tail([{a}, {b}, {n}], 1))\n",
        "js": "function tail(xs, k) {{\n  return xs.slice(k);\n}}\nconsole.log(JSON.stringify(tail([{a}, {b}, {n}], 1)));\n",
        "rb": "def tail(xs, k)\n  xs[k..]\nend\np tail([{a}, {b}, {n}], 1)\n",
        "php": "<?php\nfunction tail($xs, $k) {{\n  return array_slice($xs, $k);\n}}\necho json_encode(tail([{a}, {b}, {n}], 1)), \"\\n\";\n",
    },
}

# (name, per-language (find, replace)) -- SEMANTIC: output is expected to move.
SEMANTIC: dict[str, dict[str, tuple[str, str]]] = {
    "g_accumulate_upto": {
        "py": ("range(1, n + 1)", "range(1, n)"),
        "js": ("i <= n", "i < n"),
        "rb": ("(1..n)", "(1...n)"),
        "php": ("$i <= $n", "$i < $n"),
    },
    "g_scaled_ratio": {
        "py": ("a * 100 / b", "a * 100 // b"),
        "js": ("(a * 100) / b", "Math.trunc((a * 100) / b)"),
        "rb": ("a * 100.0 / b", "a * 100 / b"),
        "php": ("$a * 100 / $b", "intdiv($a * 100, $b)"),
    },
    "g_threshold_count": {
        "py": ("if x > t:", "if x >= t:"),
        "js": ("if (x > t) c += 1;", "if (x >= t) c += 1;"),
        "rb": ("c += 1 if x > t", "c += 1 if x >= t"),
        "php": ("if ($x > $t) $c += 1;", "if ($x >= $t) $c += 1;"),
    },
    "g_running_peak": {
        "py": ("best = xs[0]", "best = 0"),
        "js": ("let best = xs[0];", "let best = 0;"),
        "rb": ("best = xs[0]", "best = 0"),
        "php": ("$best = $xs[0];", "$best = 0;"),
    },
    "g_join_labels": {
        "py": ("str(k) + ':' + str(v)", "str(v) + ':' + str(k)"),
        "js": ("String(k) + ':' + String(v)", "String(v) + ':' + String(k)"),
        "rb": ("k.to_s + ':' + v.to_s", "v.to_s + ':' + k.to_s"),
        "php": ("strval($k) . ':' . strval($v)", "strval($v) . ':' . strval($k)"),
    },
    "g_tail_slice": {
        "py": ("xs[k:]", "xs[k + 1:]"),
        "js": ("xs.slice(k)", "xs.slice(k + 1)"),
        "rb": ("xs[k..]", "xs[(k + 1)..]"),
        "php": ("array_slice($xs, $k)", "array_slice($xs, $k + 1)"),
    },
}

# COSMETIC: a rename or a comment. Output must be preserved -- these are the
# negatives, and they are deliberately LARGER edits than the semantic ones so
# the corpus cannot be solved by diff size.
COSMETIC_RENAME = {
    "g_accumulate_upto": {"py": ("s", "acc"), "js": ("s", "acc"),
                          "rb": ("s", "acc"), "php": ("$s", "$acc")},
    "g_scaled_ratio": {"py": ("a", "num"), "js": ("a", "num"),
                       "rb": ("a", "num"), "php": ("$a", "$num")},
    "g_threshold_count": {"py": ("c", "hits"), "js": ("c", "hits"),
                          "rb": ("c", "hits"), "php": ("$c", "$hits")},
    "g_running_peak": {"py": ("best", "top"), "js": ("best", "top"),
                       "rb": ("best", "top"), "php": ("$best", "$top")},
    "g_join_labels": {"py": ("k", "key"), "js": ("k", "key"),
                      "rb": ("k", "key"), "php": ("$k", "$key")},
    "g_tail_slice": {"py": ("xs", "items"), "js": ("xs", "items"),
                     "rb": ("xs", "items"), "php": ("$xs", "$items")},
}

EXT = {"py": "py", "js": "js", "rb": "rb", "php": "php"}


def rename(src: str, old: str, new: str) -> str:
    """Whole-token rename, so `s` does not eat the `s` inside `else`."""
    import re
    if old.startswith("$"):
        return re.sub(re.escape(old) + r"\b", new, src)
    return re.sub(rf"\b{re.escape(old)}\b", new, src)


def unified(pre: str, post: str, name: str) -> str:
    import difflib
    return "".join(difflib.unified_diff(
        pre.splitlines(keepends=True), post.splitlines(keepends=True),
        fromfile=f"a/{name}", tofile=f"b/{name}"))


def fixture_families() -> set[str]:
    out = set()
    for p in itertools.chain(
            (ROOT / "bench/mechanism_pilot").glob("*/meta.json"),
            (ROOT / "bench/clean_direction").glob("*/meta.json")):
        m = json.loads(p.read_text())
        out.add(m.get("parent") or m.get("id"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "data/exec_ml.jsonl")
    ap.add_argument("--per-family", type=int, default=24,
                    help="samples per (family, language, edit-kind)")
    ap.add_argument("--langs", default="py,js,rb,php")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    fx = fixture_families()
    clash = fx & set(SHAPES)
    if clash:
        raise SystemExit(f"LEAK: family names collide with the eval fixtures: {clash}")
    print(f"{len(SHAPES)} families, disjoint from {len(fx)} fixture families\n")

    from bench.exec_diff import run_one
    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    rng = random.Random(args.seed)
    out, skipped, surprises = [], 0, 0
    import tempfile

    for fam, per_lang in SHAPES.items():
        for lang in langs:
            tpl = per_lang.get(lang)
            if not tpl:
                continue
            for kind in ("semantic", "cosmetic"):
                made = 0
                for _ in range(args.per_family * 3):
                    if made >= args.per_family:
                        break
                    a, b, n = rng.randint(2, 40), rng.randint(2, 40), rng.randint(3, 30)
                    pre = tpl.format(a=a, b=b, n=n)
                    if kind == "semantic":
                        find, repl = SEMANTIC[fam][lang]
                        if find not in pre:
                            continue
                        post = pre.replace(find, repl, 1)
                    else:
                        old, new = COSMETIC_RENAME[fam][lang]
                        post = rename(pre, old, new)
                    if post == pre:
                        continue
                    with tempfile.TemporaryDirectory() as td:
                        wd = pathlib.Path(td)
                        pa, pb = wd / f"pre.{EXT[lang]}", wd / f"post.{EXT[lang]}"
                        pa.write_text(pre); pb.write_text(post)
                        ra = run_one(pa, EXT[lang])
                        rb_ = run_one(pb, EXT[lang])
                    if ra.get("status") != "ok" or rb_.get("status") != "ok":
                        skipped += 1
                        continue
                    differs = (ra["out"] != rb_["out"] or ra["err"] != rb_["err"]
                               or ra["rc"] != rb_["rc"])
                    if differs != (kind == "semantic"):
                        surprises += 1
                    out.append({
                        "family": fam, "lang": lang, "kind": kind,
                        "differs": bool(differs),
                        "diff": unified(pre, post, f"prog.{EXT[lang]}"),
                        "before": ra["out"].strip()[:200],
                        "after": rb_["out"].strip()[:200],
                    })
                    made += 1
                print(f"  {fam:<22}{lang:<5}{kind:<10}{made:>4}", flush=True)

    with open(args.out, "w") as fh:
        for o in out:
            fh.write(json.dumps(o) + "\n")
    pos = sum(o["differs"] for o in out)
    print(f"\n{len(out)} rows -> {args.out}")
    print(f"  behaviour-changing {pos} ({pos / max(len(out),1):.0%})")
    print(f"  runs that failed to execute, dropped: {skipped}")
    print(f"  edits whose measured label defied the expectation: {surprises} "
          f"(kept, with the MEASURED label)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
