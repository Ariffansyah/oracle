"""Generate runnable pre/post pairs and label them by EXECUTION, not by an LLM.

    python -m dataset_builder.gen_exec_corpus --n 40 --out data/exec_corpus.jsonl
    python -m dataset_builder.gen_exec_corpus --n 12 --audit    # print, write nothing

Why this exists
---------------
Every corpus in this project so far labelled behaviour with prose someone or
something WROTE. The repair corpus collapsed into 6 sentence frames, and the
2 Sep grade found the model asserting behaviour that contradicted the code. A
target that is a sentence cannot distinguish a true explanation from a plausible
one; a target that is a MEASURED VALUE can.

So each pair is compiled and run, and `before`/`after` are whatever the program
actually printed. Nothing here invents behaviour.

Templating is the known enemy
-----------------------------
`oracle-audit-blind-spot`: raw distinctness read 99% on a corpus that was 41
frames. Every identifier, literal and driver input below is drawn per-sample, so
two samples from one family share structure but not surface. Distinctness is
reported with those slots STRIPPED, which is the only measurement that means
anything here.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import sys
import tempfile
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bench.exec_diff import run_one  # noqa: E402

NAMES = ["total", "accum", "tally", "running", "acc", "sum_so_far", "count"]
FUNCS = ["compute", "summarise", "tally_up", "reduce_all", "collect", "fold",
         "aggregate", "measure", "combine", "walk"]
ITEMS = ["values", "items", "rows", "entries", "records", "points", "samples"]

# Each family: (category, builder). The builder returns (pre, post, changed),
# where `changed` names the construct that differs -- the one thing the model
# must localise. Behaviour is NEVER asserted here; execution supplies it.
def _drv(fn, *args):
    return f"\nprint({fn}({', '.join(map(repr, args))}))\n"

def _noise(r, n=None):
    """Unrelated code, identical in pre and post, placed around the hunk.

    Without this every diff IS the whole file, so the model never sees a hunk
    surrounded by code it must ignore -- the only shape real commits come in.
    It is also the cheapest diversity axis available: a unified diff carries 3
    lines of context, so varying what sits beside the change varies the FRAME
    without writing another family. Frame ratio fell to 0.40 at 900 samples on
    36 families; widening this is what buys corpus size back.
    """
    n = r.randint(0, 4) if n is None else n
    outs = []
    for _ in range(n):
        f = r.choice(FUNCS) + "_" + r.choice(
            ["helper", "util", "aux", "misc", "inner", "extra", "shared"])
        k, j = r.randint(2, 40), r.randint(2, 15)
        outs.append(r.choice([
            f"def {f}(x):\n    return x * {k}\n",
            f"def {f}(x):\n    if x < 0:\n        return 0\n    return x + {k}\n",
            f"def {f}(x, y={j}):\n    return (x + y) % {k}\n",
            f"def {f}(xs):\n    return [v for v in xs if v != {j}]\n",
            f"def {f}(xs):\n    return {{v: v * {j} for v in xs}}\n",
            f"def {f}(s):\n    return str(s).rjust({j}, '0')\n",
            f"{f.upper()} = {k}\n",
            f"{f.upper()} = [{k}, {j}]\n",
            f"# {r.choice(['tuning', 'legacy', 'perf', 'compat'])} constant\n"
            f"{f.upper()} = {k}\n",
            f"class {f.title().replace('_', '')}:\n    LIMIT = {k}\n\n"
            f"    def scale(self, x):\n        return x * self.LIMIT\n",
        ]))
    return "\n".join(outs) + ("\n" if outs else "")


def _around(r, body):
    """Put noise on BOTH sides of the change, not only above it.

    Context above and below a hunk are different frames, and a family that only
    ever has code above it teaches the model that a diff starts a file.
    """
    top, bottom = _noise(r), _noise(r, r.randint(0, 2))
    return top + body + ("\n" + bottom if bottom.strip() else "")


def _lit(r, lo=1, hi=40, k=None):
    return [r.randint(lo, hi) for _ in range(k or r.randint(3, 7))]

# ---- off-by-one -----------------------------------------------------------
def f_range_end(r):
    fn, v, n = r.choice(FUNCS), r.choice(NAMES), r.randint(4, 40)
    pre_ = _noise(r) + f"def {fn}(n):\n    {v} = 0\n    for i in range(1, n + 1):\n        {v} += i\n    return {v}\n" + _drv(fn, n)
    return pre_, pre_.replace("range(1, n + 1)", "range(1, n)"), "range(1, n + 1) -> range(1, n)"

def f_index_bound(r):
    fn, xs = r.choice(FUNCS), r.choice(ITEMS)
    lit = _lit(r)
    pre_ = _noise(r) + f"def {fn}({xs}):\n    s = 0\n    for i in range(len({xs})):\n        s += {xs}[i]\n    return s\n" + _drv(fn, lit)
    return pre_, pre_.replace(f"range(len({xs}))", f"range(len({xs}) + 1)"), "loop bound + 1"

def f_slice_end(r):
    fn, xs, k = r.choice(FUNCS), r.choice(ITEMS), r.randint(2, 4)
    lit = _lit(r, k=r.randint(5, 8))
    pre_ = _noise(r) + f"def {fn}({xs}, n):\n    return {xs}[:n]\n" + f"\nprint({fn}({lit}, {k}))\n"
    return pre_, pre_.replace("[:n]", "[:n - 1]"), "[:n] -> [:n - 1]"

def f_while_bound(r):
    fn, xs = r.choice(FUNCS), r.choice(ITEMS)
    lit = _lit(r)
    pre_ = _noise(r) + f"def {fn}({xs}):\n    i, s = 0, 0\n    while i < len({xs}):\n        s += {xs}[i]\n        i += 1\n    return s\n" + _drv(fn, lit)
    return pre_, pre_.replace("while i < len", "while i <= len"), "while < -> <="

def f_reverse_index(r):
    fn, xs = r.choice(FUNCS), r.choice(ITEMS)
    lit = _lit(r)
    pre_ = _noise(r) + f"def {fn}({xs}):\n    s = 0\n    for i in range(len({xs}) - 1, -1, -1):\n        s += {xs}[i]\n    return s\n" + _drv(fn, lit)
    return pre_, pre_.replace(f"len({xs}) - 1, -1", f"len({xs}), -1"), "reverse start off by one"

# ---- error handling -------------------------------------------------------
def f_empty_guard(r):
    fn, xs = r.choice(FUNCS), r.choice(ITEMS)
    pre_ = _noise(r) + f"def {fn}({xs}):\n    if not {xs}:\n        return 0\n    return sum({xs}) / len({xs})\n" + _drv(fn, [])
    return pre_, pre_.replace(f"    if not {xs}:\n        return 0\n", ""), "empty guard removed"

def f_none_guard(r):
    fn = r.choice(FUNCS)
    pre_ = _noise(r) + f"def {fn}(s):\n    if s is None:\n        return 0\n    return len(s)\n" + _drv(fn, None)
    return pre_, pre_.replace("    if s is None:\n        return 0\n", ""), "None guard removed"

def f_key_guard(r):
    fn, k = r.choice(FUNCS), r.choice(["missing", "absent", "nope"])
    d = {chr(97 + i): r.randint(1, 9) for i in range(3)}
    pre_ = _noise(r) + f"def {fn}(d, k):\n    return d.get(k, 0)\n" + f"\nprint({fn}({d}, {k!r}))\n"
    return pre_, pre_.replace("d.get(k, 0)", "d[k]"), "dict.get -> subscript"

def f_zero_div_guard(r):
    fn = r.choice(FUNCS)
    pre_ = _noise(r) + f"def {fn}(a, b):\n    if b == 0:\n        return 0\n    return a / b\n" + _drv(fn, r.randint(1, 20), 0)
    return pre_, pre_.replace("    if b == 0:\n        return 0\n", ""), "zero-divisor guard removed"

def f_except_removed(r):
    fn = r.choice(FUNCS)
    pre_ = _noise(r) + f"def {fn}(s):\n    try:\n        return int(s)\n    except ValueError:\n        return 0\n" + _drv(fn, "abc")
    return pre_, _noise(r, 0) + f"def {fn}(s):\n    return int(s)\n" + _drv(fn, "abc"), "try/except removed"

def f_pop_guard(r):
    fn = r.choice(FUNCS)
    pre_ = _noise(r) + f"def {fn}({r.choice(ITEMS)}):\n    pass\n" if False else None
    xs = r.choice(ITEMS)
    pre_ = _noise(r) + f"def {fn}({xs}):\n    if not {xs}:\n        raise IndexError('empty')\n    return {xs}.pop()\n" + _drv(fn, [])
    return pre_, pre_.replace(f"    if not {xs}:\n        raise IndexError('empty')\n", ""), "explicit IndexError removed"

# ---- logic errors ---------------------------------------------------------
def f_int_division(r):
    fn, xs = r.choice(FUNCS), r.choice(ITEMS)
    lit = _lit(r, 1, 9, r.randint(2, 4))
    pre_ = _noise(r) + f"def {fn}({xs}):\n    return sum({xs}) / len({xs})\n" + _drv(fn, lit)
    return pre_, pre_.replace(") / len(", ") // len("), "/ -> //"

def f_mutable_default(r):
    fn = r.choice(FUNCS)
    a, b, c = (r.randint(1, 30) for _ in range(3))
    drv = f"\nprint({fn}({a}), {fn}({b}), {fn}({c}))\n"
    return (_noise(r) + f"def {fn}(x, acc=None):\n    if acc is None:\n        acc = []\n    acc.append(x)\n    return acc\n" + drv,
            _noise(r, 0) + f"def {fn}(x, acc=[]):\n    acc.append(x)\n    return acc\n" + drv,
            "acc=None -> acc=[]")

def f_dict_mutate(r):
    fn = r.choice(FUNCS)
    d = {chr(97 + i): r.randint(1, 30) for i in range(r.randint(3, 6))}
    pre_ = _noise(r) + f"def {fn}(d):\n    for k in list(d):\n        if d[k] % 2:\n            del d[k]\n    return d\n" + f"\nprint(sorted({fn}({d}).items()))\n"
    return pre_, pre_.replace("for k in list(d)", "for k in d"), "list(d) -> d"

def f_accum_reset(r):
    fn, v = r.choice(FUNCS), r.choice(NAMES)
    rows = [[r.randint(1, 20) for _ in range(2)] for _ in range(3)]
    body = f"        for x in row:\n            {v} += x\n        out.append({v})\n    return out\n" + _drv(fn, rows)
    return (_noise(r) + f"def {fn}(rows):\n    out = []\n    for row in rows:\n        {v} = 0\n" + body,
            _noise(r, 0) + f"def {fn}(rows):\n    out = []\n    {v} = 0\n    for row in rows:\n" + body,
            f"{v} = 0 hoisted out of the loop")

def f_comparison_flip(r):
    fn, t = r.choice(FUNCS), r.randint(5, 30)
    lit = _lit(r, 1, 40)
    pre_ = _noise(r) + f"def {fn}(xs):\n    return [x for x in xs if x > {t}]\n" + _drv(fn, lit)
    return pre_, pre_.replace(f"x > {t}", f"x >= {t}"), "> -> >="

def f_early_return(r):
    fn, xs = r.choice(FUNCS), r.choice(ITEMS)
    lit = _lit(r, 1, 20)
    pre_ = _noise(r) + f"def {fn}({xs}):\n    s = 0\n    for x in {xs}:\n        if x % 2:\n            continue\n        s += x\n    return s\n" + _drv(fn, lit)
    return pre_, pre_.replace("continue", "break"), "continue -> break"

def f_bool_logic(r):
    fn, a, b = r.choice(FUNCS), r.randint(1, 20), r.randint(1, 20)
    pre_ = _noise(r) + f"def {fn}(x, y):\n    return x > 0 and y > 0\n" + _drv(fn, a, -b)
    return pre_, pre_.replace(" and ", " or "), "and -> or"

def f_string_join(r):
    fn = r.choice(FUNCS)
    words = r.sample(["alpha", "beta", "gamma", "delta", "epsilon"], 3)
    pre_ = _noise(r) + f"def {fn}(ws):\n    return ', '.join(ws)\n" + _drv(fn, words)
    return pre_, pre_.replace("', '.join(ws)", "','.join(ws)"), "separator changed"

def f_sort_key(r):
    fn = r.choice(FUNCS)
    lit = _lit(r, 1, 200, r.randint(4, 7))
    pre_ = _noise(r) + f"def {fn}(xs):\n    return sorted(xs)\n" + _drv(fn, lit)
    return pre_, pre_.replace("sorted(xs)", "sorted(map(str, xs))"), "numeric -> lexicographic sort"

def f_copy_reference(r):
    fn, xs = r.choice(FUNCS), r.choice(ITEMS)
    lit = _lit(r, 1, 20)
    pre_ = _noise(r) + f"def {fn}({xs}):\n    out = list({xs})\n    out.sort()\n    return out\n" + f"\nd = {lit}\nprint({fn}(d), d)\n"
    return pre_, pre_.replace(f"out = list({xs})", f"out = {xs}"), "copy dropped before sort"

def f_off_by_one_len(r):
    fn, xs = r.choice(FUNCS), r.choice(ITEMS)
    lit = _lit(r, 1, 20, r.randint(4, 7))
    pre_ = _noise(r) + f"def {fn}({xs}):\n    return {xs}[len({xs}) - 1]\n" + _drv(fn, lit)
    return pre_, pre_.replace(f"len({xs}) - 1", f"len({xs}) - 2"), "last index shifted"

def f_accumulate_wrong_var(r):
    fn, a, b = r.choice(FUNCS), r.choice(NAMES), r.choice(NAMES)
    b = b if b != a else b + "_2"
    lit = _lit(r, 1, 15)
    pre_ = _noise(r) + f"def {fn}(xs):\n    {a} = 0\n    {b} = 0\n    for x in xs:\n        {a} += x\n        {b} += 1\n    return {a}\n" + _drv(fn, lit)
    return pre_, pre_.replace(f"    return {a}\n", f"    return {b}\n"), f"returns {b} instead of {a}"

def f_round_truncate(r):
    fn = r.choice(FUNCS)
    lit = _lit(r, 1, 9, 3)
    pre_ = _noise(r) + f"def {fn}(xs):\n    return round(sum(xs) / len(xs), 2)\n" + _drv(fn, lit)
    return pre_, pre_.replace("round(sum(xs) / len(xs), 2)", "int(sum(xs) / len(xs))"), "round -> int"

def f_negative_index(r):
    fn, xs = r.choice(FUNCS), r.choice(ITEMS)
    lit = _lit(r, 1, 20, r.randint(4, 6))
    pre_ = _noise(r) + f"def {fn}({xs}):\n    return {xs}[0]\n" + _drv(fn, lit)
    return pre_, pre_.replace(f"{xs}[0]", f"{xs}[-1]"), "first -> last element"

def f_strip_default(r):
    fn = r.choice(FUNCS)
    pre_ = _noise(r) + f"def {fn}(s):\n    return s.strip().lower()\n" + _drv(fn, "  Hello World  ")
    return pre_, pre_.replace(".strip().lower()", ".lower()"), "strip() dropped"

def f_range_step(r):
    fn, n = r.choice(FUNCS), r.randint(6, 30)
    pre_ = _noise(r) + f"def {fn}(n):\n    return list(range(0, n, 2))\n" + _drv(fn, n)
    return pre_, pre_.replace("range(0, n, 2)", "range(0, n, 3)"), "step 2 -> 3"

def f_max_min_swap(r):
    fn = r.choice(FUNCS)
    lit = _lit(r, 1, 50)
    pre_ = _noise(r) + f"def {fn}(xs):\n    return max(xs) - min(xs)\n" + _drv(fn, lit)
    return pre_, pre_.replace("max(xs) - min(xs)", "min(xs) - max(xs)"), "max/min swapped"

# ---- clean: behaviour must be IDENTICAL -----------------------------------
def f_rename(r):
    fn, old = r.choice(FUNCS), r.choice(NAMES)
    new = r.choice([n for n in NAMES if n != old])
    lit = _lit(r, 1, 20)
    mk = lambda v: f"def {fn}(xs):\n    {v} = 0\n    for x in xs:\n        {v} += x\n    return {v}\n" + _drv(fn, lit)
    pad = _noise(r)
    return pad + mk(old), pad + mk(new), f"{old} renamed to {new}"

def f_extract(r):
    fn, hp = r.choice(FUNCS), "_" + r.choice(["step", "add", "apply", "combine"])
    lit = _lit(r, 1, 20)
    pad = _noise(r)
    return (pad + f"def {fn}(xs):\n    s = 0\n    for x in xs:\n        s = s + x\n    return s\n" + _drv(fn, lit),
            pad + f"def {hp}(a, b):\n    return a + b\n\ndef {fn}(xs):\n    s = 0\n    for x in xs:\n        s = {hp}(s, x)\n    return s\n" + _drv(fn, lit),
            f"addition extracted into {hp}")

def f_annotate(r):
    fn = r.choice(FUNCS)
    lit = _lit(r, 1, 20)
    pad = _noise(r)
    return (pad + f"def {fn}(xs):\n    return sum(xs)\n" + _drv(fn, lit),
            pad + f"def {fn}(xs: list[int]) -> int:\n    return sum(xs)\n" + _drv(fn, lit),
            "type hints added")

def f_comprehension(r):
    fn = r.choice(FUNCS)
    lit = _lit(r, 1, 30)
    pad = _noise(r)
    return (pad + f"def {fn}(xs):\n    out = []\n    for x in xs:\n        out.append(x * 2)\n    return out\n" + _drv(fn, lit),
            pad + f"def {fn}(xs):\n    return [x * 2 for x in xs]\n" + _drv(fn, lit),
            "loop -> comprehension")

def f_docstring(r):
    fn = r.choice(FUNCS)
    lit = _lit(r, 1, 20)
    pad = _noise(r)
    return (pad + f"def {fn}(xs):\n    return sum(xs)\n" + _drv(fn, lit),
            pad + f"def {fn}(xs):\n    \"\"\"Total of xs.\"\"\"\n    return sum(xs)\n" + _drv(fn, lit),
            "docstring added")

def f_reorder_defs(r):
    a, b = r.sample(FUNCS, 2)
    k = r.randint(2, 9)
    A = f"def {a}(x):\n    return x + {k}\n"
    B = f"def {b}(x):\n    return x * {k}\n"
    drv = f"\nprint({a}({k}), {b}({k}))\n"
    return A + "\n" + B + drv, B + "\n" + A + drv, "definition order swapped"

def f_constant_named(r):
    fn, k = r.choice(FUNCS), r.randint(2, 20)
    lit = _lit(r, 1, 20)
    pad = _noise(r)
    return (pad + f"def {fn}(xs):\n    return [x * {k} for x in xs]\n" + _drv(fn, lit),
            pad + f"FACTOR = {k}\n\ndef {fn}(xs):\n    return [x * FACTOR for x in xs]\n" + _drv(fn, lit),
            "literal extracted to a named constant")

def f_equivalent_guard(r):
    fn = r.choice(FUNCS)
    lit = _lit(r, 1, 20)
    pad = _noise(r)
    return (pad + f"def {fn}(xs):\n    if len(xs) == 0:\n        return 0\n    return sum(xs)\n" + _drv(fn, lit),
            pad + f"def {fn}(xs):\n    if not xs:\n        return 0\n    return sum(xs)\n" + _drv(fn, lit),
            "len(xs) == 0 -> not xs")

def f_enumerate(r):
    fn, xs = r.choice(FUNCS), r.choice(ITEMS)
    lit = _lit(r, 1, 30)
    pad = _noise(r)
    return (pad + f"def {fn}({xs}):\n    s = 0\n    for i in range(len({xs})):\n        s += {xs}[i]\n    return s\n" + _drv(fn, lit),
            pad + f"def {fn}({xs}):\n    s = 0\n    for _, v in enumerate({xs}):\n        s += v\n    return s\n" + _drv(fn, lit),
            "range(len(x)) -> enumerate")

def f_sum_builtin(r):
    fn, xs = r.choice(FUNCS), r.choice(ITEMS)
    lit = _lit(r, 1, 30)
    pad = _noise(r)
    return (pad + f"def {fn}({xs}):\n    s = 0\n    for x in {xs}:\n        s += x\n    return s\n" + _drv(fn, lit),
            pad + f"def {fn}({xs}):\n    return sum({xs})\n" + _drv(fn, lit),
            "manual loop -> sum()")

def f_negated_branch(r):
    fn, t = r.choice(FUNCS), r.randint(5, 30)
    pad = _noise(r)
    a = r.randint(1, 40)
    return (pad + f"def {fn}(x):\n    if x > {t}:\n        return 'high'\n    return 'low'\n" + _drv(fn, a),
            pad + f"def {fn}(x):\n    if x <= {t}:\n        return 'low'\n    return 'high'\n" + _drv(fn, a),
            "branch order inverted, condition negated")

def f_fstring(r):
    fn, k = r.choice(FUNCS), r.randint(1, 50)
    pad = _noise(r)
    return (pad + f"def {fn}(n):\n    return 'n=' + str(n)\n" + _drv(fn, k),
            pad + f"def {fn}(n):\n    return f'n={{n}}'\n" + _drv(fn, k),
            "concatenation -> f-string")

def f_inline_var(r):
    fn, v = r.choice(FUNCS), r.choice(NAMES)
    lit = _lit(r, 1, 20)
    pad = _noise(r)
    return (pad + f"def {fn}(xs):\n    {v} = sum(xs)\n    return {v} * 2\n" + _drv(fn, lit),
            pad + f"def {fn}(xs):\n    return sum(xs) * 2\n" + _drv(fn, lit),
            f"{v} inlined")

def f_get_default(r):
    fn = r.choice(FUNCS)
    d = {chr(97 + i): r.randint(1, 40) for i in range(3)}
    key = r.choice(list(d))
    pad = _noise(r)
    return (pad + f"def {fn}(d, k):\n    if k in d:\n        return d[k]\n    return 0\n" + f"\nprint({fn}({d}, {key!r}))\n",
            pad + f"def {fn}(d, k):\n    return d.get(k, 0)\n" + f"\nprint({fn}({d}, {key!r}))\n",
            "if-in -> dict.get with default")

def f_else_removed(r):
    fn, t = r.choice(FUNCS), r.randint(5, 25)
    pad = _noise(r)
    a = r.randint(1, 40)
    return (pad + f"def {fn}(x):\n    if x > {t}:\n        return x\n    else:\n        return 0\n" + _drv(fn, a),
            pad + f"def {fn}(x):\n    if x > {t}:\n        return x\n    return 0\n" + _drv(fn, a),
            "redundant else removed")

def f_tuple_unpack(r):
    fn = r.choice(FUNCS)
    a, b = r.randint(1, 30), r.randint(1, 30)
    pad = _noise(r)
    return (pad + f"def {fn}(p):\n    return p[0] + p[1]\n" + f"\nprint({fn}(({a}, {b})))\n",
            pad + f"def {fn}(p):\n    a, b = p\n    return a + b\n" + f"\nprint({fn}(({a}, {b})))\n",
            "index access -> tuple unpacking")



# ---- label decoupling -----------------------------------------------------
# 34 of 38 training families were single-label (1008/1095 rows), so `differs`
# was a property of the FAMILY: a tf-idf model scored 1.000 on the within
# holdout by recognising the family and never computing anything. These two
# make every family able to emit either label. Execution still decides which --
# these only propose an edit, they never assert its effect.

def _preserve(r, pre):
    """A behaviour-preserving edit, so a BUGGY family can yield differs=False."""
    ops = []
    for n in NAMES:
        if re.search(rf"\b{n}\b", pre):
            new = r.choice([x for x in NAMES if x != n])
            if not re.search(rf"\b{new}\b", pre):
                ops.append((re.sub(rf"\b{n}\b", new, pre),
                            f"{n} renamed to {new}"))
            break
    m = re.search(r"^(def [a-z_]\w*\([^)]*\):\n)", pre, re.M)
    if m:
        doc = r.choice(["Return the computed value.", "Compute the result.",
                        "Helper used by the driver.", "Fold the input to one value.",
                        "Walk the input and accumulate."])
        ops.append((pre[:m.end()] + f'    """{doc}"""\n' + pre[m.end():],
                    "docstring added"))
        tag = r.choice(["helper", "entry point", "core loop", "main path",
                        "kept for compatibility"])
        ops.append((pre[:m.start()] + f"# {tag}\n" + pre[m.start():],
                    "comment added"))
    d = re.search(r"print\((\w+)\(", pre)
    if d:
        old = d.group(1)
        new = old + "_" + r.choice(["v2", "impl", "step", "inner"])
        if not re.search(rf"\b{new}\b", pre):
            ops.append((re.sub(rf"\b{old}\b", new, pre),
                        f"{old} renamed to {new}"))
    return r.choice(ops) if ops else None


def _break(r, pre):
    """Perturb one integer literal, so a CLEAN family can yield differs=True.

    The literal may sit in noise code that never runs, in which case execution
    records differs=False -- which is the point: whether an edit reaches the
    output is exactly what the model has to work out rather than pattern-match.
    """
    hits = [m for m in re.finditer(r"(?<![\w.])(\d+)(?![\w.])", pre)]
    if not hits:
        return None
    m = r.choice(hits)
    old = int(m.group(1))
    new = old + r.choice([-2, -1, 1, 2, 3])
    if new == old or new < 0:
        new = old + 1
    return (pre[:m.start()] + str(new) + pre[m.end():],
            f"literal {old} -> {new}")


# Commit subjects are sampled INDEPENDENTLY of the label, on purpose. A message
# that matched the edit would predict `differs` and hand the model a second
# shortcut next to the family one. Real commit messages are unreliable in
# exactly this way -- "fix" commits that refactor, "cleanup" commits that break
# something -- so an uninformative message is the realistic case, not a
# concession. `--audit` fails the build if a message ever predicts the label.
COMMIT_MSGS = [
    "refactor: tidy up {fn}", "fix: correct off-by-one in {fn}",
    "perf: avoid redundant work in {fn}", "style: rename locals in {fn}",
    "chore: minor cleanup in {fn}", "fix: handle the empty case in {fn}",
    "refactor: simplify {fn}", "update {fn} after review",
    "wip: adjust {fn}", "revert accidental change in {fn}",
    "fix: guard against bad input in {fn}", "refactor: extract constant in {fn}",
    "chore: address review comment on {fn}", "fix: tighten bounds in {fn}",
    "style: clarify intent in {fn}", "refactor: rework {fn} loop",
    "fix: off-by-one when {fn} is empty", "perf: tighten the {fn} hot path",
    "chore: rename for consistency in {fn}", "fix: correct accumulator in {fn}",
]


def _commit_msg(r, pre):
    m = re.search(r"print\((\w+)\(", pre) or re.search(r"^def (\w+)", pre, re.M)
    fn = m.group(1) + "()" if m else "the helper"
    return r.choice(COMMIT_MSGS).format(fn=fn)


FAMILIES = [
    ("off-by-one", f_range_end, True), ("off-by-one", f_index_bound, True),
    ("off-by-one", f_slice_end, True), ("off-by-one", f_while_bound, True),
    ("off-by-one", f_reverse_index, True), ("off-by-one", f_off_by_one_len, True),
    ("error-handling", f_empty_guard, True), ("error-handling", f_none_guard, True),
    ("error-handling", f_key_guard, True), ("error-handling", f_zero_div_guard, True),
    ("error-handling", f_except_removed, True), ("error-handling", f_pop_guard, True),
    ("logic-error", f_int_division, True), ("logic-error", f_mutable_default, True),
    ("logic-error", f_dict_mutate, True), ("logic-error", f_accum_reset, True),
    ("logic-error", f_comparison_flip, True), ("logic-error", f_early_return, True),
    ("logic-error", f_bool_logic, True), ("logic-error", f_accumulate_wrong_var, True),
    ("logic-error", f_round_truncate, True), ("logic-error", f_negative_index, True),
    ("logic-error", f_max_min_swap, True), ("logic-error", f_range_step, True),
    ("api-misuse", f_string_join, True), ("api-misuse", f_sort_key, True),
    ("api-misuse", f_copy_reference, True), ("api-misuse", f_strip_default, True),
    ("clean", f_rename, False), ("clean", f_extract, False),
    ("clean", f_annotate, False), ("clean", f_comprehension, False),
    ("clean", f_docstring, False), ("clean", f_reorder_defs, False),
    ("clean", f_constant_named, False), ("clean", f_equivalent_guard, False),
    ("clean", f_enumerate, False), ("clean", f_sum_builtin, False),
    ("clean", f_negated_branch, False), ("clean", f_fstring, False),
    ("clean", f_inline_var, False), ("clean", f_get_default, False),
    ("clean", f_else_removed, False), ("clean", f_tuple_unpack, False),
]



SFT_SYSTEM = """You are ORACLE. You are given one commit diff of a program that \
prints a result.

Do not describe the change. COMPUTE it. Work out what the program printed before \
this commit and what it prints after, then answer with one JSON object:

  "differs"  true if the two versions print different output, else false
  "before"   exactly what the pre-commit version printed
  "after"    exactly what the post-commit version printed

If the program raises, give the exception type and message. Report only what the \
code determines; do not guess at consequences you cannot derive."""

SFT_USER = """## Commit
{message}

## Changes
```diff
{diff}
```"""


def unified(pre: str, post: str, path: str, context: int = 3) -> str:
    import difflib
    d = difflib.unified_diff(pre.splitlines(), post.splitlines(),
                             fromfile=f"a/{path}", tofile=f"b/{path}",
                             lineterm="", n=context)
    return "\n".join(d)


def frame(s: str) -> str:
    """Strip the slots, so distinctness measures STRUCTURE not surface."""
    s = re.sub(r"\b\d+\b", "N", s)
    s = re.sub(r"\b[a-z_][a-z0-9_]*\b", "ID", s)
    return re.sub(r"\s+", " ", s).strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=40, help="samples per family")
    ap.add_argument("--seed", type=int, default=11)
    # n=3 lines of context hides the driver call in 244/1095 rows: the diff
    # shows `def aggregate(n)` changing but never what n was, so before/after
    # are not derivable from the input and the target teaches guessing.
    ap.add_argument("--preserve-rate", type=float, default=0.34, metavar="P",
                    help="fraction of rows using a behaviour-preserving edit "
                         "instead of the family's own mutation")
    ap.add_argument("--break-rate", type=float, default=0.22, metavar="P",
                    help="fraction using a literal perturbation, which may or "
                         "may not reach the output")
    ap.add_argument("--context", type=int, default=3, metavar="N",
                    help="diff context lines; large values keep the driver "
                         "call visible so the values are actually derivable")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "data/exec_corpus.jsonl")
    ap.add_argument("--audit", action="store_true", help="print a few, write nothing")
    # A build gate, not a report. The repair corpus shipped at 41 frames and
    # nothing stopped it, because the audit line was printed and not read.
    ap.add_argument("--min-frame-ratio", type=float, default=0.5, metavar="R",
                    help="fail the build if distinct frames / samples < R")
    # The repair corpus was 71% negative and the model answered `false` to
    # everything, scoring 0/40 recall on its own training positives. This corpus
    # is 74% POSITIVE by default -- the same trap mirrored. Clean families are
    # sampled proportionally harder so the executed labels come out near even.
    ap.add_argument("--balance", action="store_true",
                    help="sample clean families harder for a ~50/50 label split")
    # TWO holdouts, because they answer different questions and only reporting
    # the easy one would flatter the result:
    #   within-family : families the model trained on, values it never saw.
    #                   "can it COMPUTE?"
    #   cross-family  : defect shapes held out entirely. "does it GENERALISE?"
    # The repair run had neither and trained on all 1164 records.
    ap.add_argument("--holdout-frac", type=float, default=0.1, metavar="F",
                    help="fraction of each trained family held out by value")
    ap.add_argument("--holdout-families", type=int, default=6, metavar="K",
                    help="whole families reserved, never trained on")
    ap.add_argument("--sft", action="store_true",
                    help="emit ChatML records for training instead of raw pairs")
    args = ap.parse_args()
    r = random.Random(args.seed)

    out, stats = [], Counter()
    with tempfile.TemporaryDirectory() as td:
        wd = pathlib.Path(td)
        n_bug = sum(1 for _, _, b in FAMILIES if b)
        n_cln = sum(1 for _, _, b in FAMILIES if not b)
        for cat, fam, buggy in FAMILIES:
            # Per-family count, not per-corpus: with 28 buggy families and 8
            # clean ones, equal sampling can only ever produce a 78/22 corpus.
            k = args.n
            if args.balance and not buggy:
                k = max(1, round(args.n * n_bug / max(1, n_cln)))
            for i in range(k):
                pre, post, changed = fam(r)
                # Every family emits BOTH labels. Which of the three edits is
                # used is independent of the family, so `differs` stops being a
                # family property and has to be worked out from the code.
                pick = r.random()
                if pick < args.preserve_rate:
                    alt = _preserve(r, pre)
                    if alt: post, changed = alt
                elif pick < args.preserve_rate + args.break_rate:
                    alt = _break(r, pre)
                    if alt: post, changed = alt
                pf, qf = wd / "pre.py", wd / "post.py"
                pf.write_text(pre); qf.write_text(post)
                a, b = run_one(pf, "py"), run_one(qf, "py")
                if a["status"] != "ok":
                    stats["pre-failed"] += 1
                    continue
                differs = (a.get("raw"), a.get("rc"), a.get("err")) != \
                          (b.get("raw"), b.get("rc"), b.get("err"))
                # The LABEL is what happened, not what the family intended. A
                # buggy family whose mutation did not manifest is recorded as
                # clean, because that is what the machine observed.
                if differs != buggy:
                    stats[f"label-flip:{fam.__name__}"] += 1
                shown = lambda v: (v.get("out") or "").strip() or (
                    f"{v.get('err','')[:80]}" if v.get("err") else "(no output)")
                out.append({
                    "family": fam.__name__, "category": cat if differs else "clean",
                    "changed": changed, "differs": differs,
                    "diff": unified(pre, post, f"{fam.__name__}.py",
                                    args.context),
                    "before": shown(a), "after": shown(b),
                    "message": _commit_msg(r, pre),
                })
                stats["ok"] += 1

    frames = Counter(frame(o["diff"]) for o in out)
    befores = len({(o["before"], o["after"]) for o in out})
    print(f"{len(out)} pairs, {len(FAMILIES)} families")
    print(f"  distinct diff FRAMES (slots stripped) : {len(frames)}")
    print(f"  distinct (before, after) value pairs  : {befores}/{len(out)} "
          f"({100*befores/max(1,len(out)):.0f}%)")
    print(f"  buggy / clean by EXECUTION            : "
          f"{sum(o['differs'] for o in out)} / {sum(not o['differs'] for o in out)}")
    for k, v in stats.items():
        if k != "ok":
            print(f"  {k}: {v}")
    ratio = len(frames) / max(1, len(out))
    if ratio < args.min_frame_ratio:
        # stdout is block-buffered to a file while stderr is not, so without
        # this the failure prints ABOVE the stats it refers to.
        sys.stdout.flush()
        raise SystemExit(
            f"\nFAILED: frame ratio {ratio:.2f} < {args.min_frame_ratio}. "
            f"{len(out)} samples collapse to {len(frames)} structures, so the "
            f"model would learn the templates rather than the behaviour. Add "
            f"families or widen the per-sample variation before training on this.")

    if args.audit:
        for o in out[:2] + out[-1:]:
            print("\n" + "=" * 70)
            print(o["diff"])
            print(f"  -> before={o['before']!r}  after={o['after']!r}  "
                  f"differs={o['differs']}  changed={o['changed']}")
        return
    # ---- splits -----------------------------------------------------------
    fam_of = {o["family"] if not args.sft else o["family"]: None for o in out}
    fams = sorted({o["family"] for o in out})
    buggy_f = sorted({o["family"] for o in out if o["differs"]})
    clean_f = [f for f in fams if f not in buggy_f]
    rs = random.Random(args.seed + 1)
    # Hold out from BOTH pools: a cross-family set of only buggy shapes would
    # measure recall and call it generalisation.
    k_b = max(1, round(args.holdout_families * len(buggy_f) / max(1, len(fams))))
    k_c = max(1, args.holdout_families - k_b)
    held_fams = set(rs.sample(buggy_f, min(k_b, len(buggy_f))) +
                    rs.sample(clean_f, min(k_c, len(clean_f))))

    cross = [o for o in out if o["family"] in held_fams]
    rest = [o for o in out if o["family"] not in held_fams]
    within = []
    for lab in (True, False):                     # stratified, so balance holds
        pool = [o for o in rest if o["differs"] == lab]
        rs.shuffle(pool)
        within += pool[:round(len(pool) * args.holdout_frac)]
    wid = {id(o) for o in within}
    train = [o for o in rest if id(o) not in wid]

    def bal(rs_):
        n = len(rs_) or 1
        return f"{len(rs_):>5} ({100*sum(o['differs'] for o in rs_)/n:.0f}% positive)"
    print(f"\n  train            {bal(train)}   {len({o['family'] for o in train})} families")
    print(f"  holdout within   {bal(within)}   values unseen, families seen")
    print(f"  holdout cross    {bal(cross)}   {len(held_fams)} families never trained on")
    print(f"    held-out families: {', '.join(sorted(held_fams))}")
    for name, rs_ in (("train", train), ("within", within), ("cross", cross)):
        if not rs_:
            sys.stdout.flush()
            raise SystemExit(f"FAILED: {name} split is empty")
        if not any(o["differs"] for o in rs_) or all(o["differs"] for o in rs_):
            sys.stdout.flush()
            raise SystemExit(f"FAILED: {name} split has only one label — it "
                             f"cannot measure both recall and false alarms")

    def to_sft(rows_):
        # The TARGET IS THE MEASURED VALUE, and nothing else. `changed` stays in
        # the raw corpus as metadata but is deliberately NOT trained on: it is
        # one templated string per family, so training on it would teach the
        # mapping from diff-shape to phrase -- the exact recitation this corpus
        # exists to avoid. before/after are 77% distinct and cannot be memorised.
        return [{"messages": [
            {"role": "system", "content": SFT_SYSTEM},
            {"role": "user", "content": SFT_USER.format(
                message=o["message"], diff=o["diff"])},
            {"role": "assistant", "content": json.dumps(
                {"differs": o["differs"], "before": o["before"],
                 "after": o["after"]}, ensure_ascii=False)},
        ], "family": o["family"], "category": o["category"],
            "differs": o["differs"]} for o in rows_]

    for name, rows_ in (("", train), ("_holdout_within", within),
                        ("_holdout_cross", cross)):
        path = args.out.with_name(args.out.stem + name + args.out.suffix)
        payload = to_sft(rows_) if args.sft else rows_
        with open(path, "w") as fh:
            for o in payload:
                fh.write(json.dumps(o, ensure_ascii=False) + "\n")
        print(f"-> {path}  ({len(payload)})")


if __name__ == "__main__":
    main()
