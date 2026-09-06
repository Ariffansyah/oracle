"""Every figure the BugsInPy section of RESULTS.md quotes, checked against the
artifacts it was measured from.

RESULTS.md has been wrong twice by mixing denominators -- once reporting 48%
where the paired recount gave 43%, once quoting an eval's all-rows denominator
beside an analysis script's parsed-rows one. Prose cannot be diffed against a
JSON file by eye, so this does it: if a number in the section drifts from the
file it came from, this fails.

    .venv/bin/python test_bugsinpy_figures.py

Skips, rather than fails, when the artifacts are absent -- they are run outputs,
not source.
"""
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
NEEDED = ["data/bugsinpy_rows_v1.jsonl", "data/bugsinpy_gate_scores_v1.json",
          "data/bugsinpy_gate_auc.json", "data/bip_arm_exec_v1.json",
          "data/bip_arm_score_v1.json", "data/bip_arm_diff_v1.json"]
missing = [f for f in NEEDED if not (ROOT / f).exists()]
if missing:
    print(f"skip: no artifacts ({missing[0]} and {len(missing) - 1} more)")
    raise SystemExit(0)

rows = [json.loads(l) for l in open(ROOT / "data/bugsinpy_rows_v1.jsonl")]
assert len(rows) == 264, len(rows)
assert sum(r["differs"] for r in rows) == 259
assert sum(not r["differs"] for r in rows) == 5
assert len({r["project"] for r in rows}) == 17
assert sum(1 for r in rows if r["exception"]) == 221
assert sum(1 for r in rows if not r["exception"]) == 43

sc = json.load(open(ROOT / "data/bugsinpy_gate_scores_v1.json"))
nz = sorted(v["metrics_nonzero"] for v in sc.values() if "metrics_nonzero" in v)
assert nz[len(nz) // 2] == 13, nz[len(nz) // 2]
vals = sorted(x["score"] for x in sc.values() if x.get("score") is not None)
assert round(vals[0], 3) == 0.034 and round(vals[-1], 3) == 0.995
assert round(vals[len(vals) // 2], 2) == 0.92

auc = json.load(open(ROOT / "data/bugsinpy_gate_auc.json"))
assert round(auc["auc"], 3) == 0.628, auc["auc"]
assert (auc["n_pos"], auc["n_neg"]) == (213, 644)

arms = {a: json.load(open(ROOT / f"data/bip_arm_{a}_v1.json"))
        for a in ("exec", "score", "diff")}

# Score from the stored explanations with the rubric that is in the tree right
# now, exactly as `bugsinpy_compare.py` does. Reading the `counts` block baked
# into each arm file would pin the numbers to whichever rubric happened to be
# checked out on the night the arms ran -- and that rubric had a bug, counting a
# correct explanation as a fabrication whenever the measured signature named a
# second exception class.
sys.path.insert(0, str(ROOT))
from bench.bugsinpy_compare import rescore  # noqa: E402

rescore(arms, ROOT / "data/bugsinpy_rows_v1.jsonl")
for _arm in arms:
    c = {"parsed": 0, "exception": 0, "signature": 0, "symbol": 0,
         "invented": 0, "grounded": 0}
    for r in arms[_arm]["rows"]:
        c["parsed"] += bool(r["explanation"])
        c["exception"] += bool(r["names_exception"])
        c["signature"] += bool(r["quotes_signature"])
        c["symbol"] += bool(r["names_symbol"])
        c["invented"] += bool(r["invented"])
        c["grounded"] += bool((r["names_exception"] or r["quotes_signature"])
                              and not r["invented"])
    arms[_arm]["counts"] = c
TABLE = {
    "exec":  dict(parsed=258, exception=104, signature=107, symbol=236,
                  invented=6, grounded=132),
    "score": dict(parsed=260, exception=13, signature=8, symbol=244,
                  invented=29, grounded=17),
    "diff":  dict(parsed=257, exception=8, signature=11, symbol=241,
                  invented=25, grounded=16),
}
for arm, want in TABLE.items():
    assert arms[arm]["n"] == 264, (arm, arms[arm]["n"])
    for key, val in want.items():
        assert arms[arm]["counts"][key] == val, (arm, key,
                                                 arms[arm]["counts"][key], val)

# the arms must be row-aligned, or every McNemar below is meaningless
ids = [r["id"] for r in arms["exec"]["rows"]]
for arm in arms:
    assert [r["id"] for r in arms[arm]["rows"]] == ids, arm


def grounded(r):
    return bool((r["names_exception"] or r["quotes_signature"])
                and not r["invented"])


ex = arms["exec"]["rows"]
hi = [r for r in ex if r["exception"]]
lo = [r for r in ex if not r["exception"]]
assert (sum(map(grounded, hi)), len(hi)) == (122, 221)
assert (sum(map(grounded, lo)), len(lo)) == (10, 43)

per = collections.defaultdict(lambda: [0, 0])
for r in ex:
    per[r["project"]][0] += grounded(r)
    per[r["project"]][1] += 1
assert per["black"] == [4, 23], per["black"]
assert per["scrapy"] == [25, 38], per["scrapy"]
assert per["fastapi"] == [10, 16], per["fastapi"]

from scipy.stats import binomtest  # noqa: E402


def mcnemar(a, b, metric):
    pick = grounded if metric == "grounded" else (lambda r: bool(r["invented"]))
    fa = [pick(r) for r in arms[a]["rows"]]
    fb = [pick(r) for r in arms[b]["rows"]]
    n01 = sum(1 for x, y in zip(fa, fb) if x and not y)
    n10 = sum(1 for x, y in zip(fa, fb) if y and not x)
    p = binomtest(n01, n01 + n10, 0.5).pvalue if n01 + n10 else 1.0
    return n01, n10, float(p)


for a, b, metric, w01, w10, lo_p, hi_p in [
        ("exec", "score", "grounded", 116, 1, 0, 1e-30),
        ("exec", "diff", "grounded", 119, 3, 0, 1e-30),
        ("score", "diff", "grounded", 8, 7, 0.99, 1.01),
        ("exec", "score", "invented", 1, 24, 0, 1e-5),
        ("exec", "diff", "invented", 1, 20, 0, 1e-4),
        ("score", "diff", "invented", 13, 9, 0.52, 0.53)]:
    n01, n10, p = mcnemar(a, b, metric)
    assert (n01, n10) == (w01, w10), (a, b, metric, n01, n10)
    assert lo_p <= p <= hi_p, (a, b, metric, p)

# The headline claim: score and diff are indistinguishable, exec is not.
_, _, p_sd = mcnemar("score", "diff", "grounded")
_, _, p_es = mcnemar("exec", "score", "grounded")
assert p_sd > 0.05 and p_es < 0.001

# --- the scale comparison, POSITIONING.md "40x change in model size" --------
# Skipped rather than failed when the 120B arms are absent: they are API runs
# and somebody re-running this offline should still get a green suite.
scale = {k: ROOT / f"data/bip120b_arm_{k}_v1.json"
         for k in ("exec", "score", "diff")}
if all(v.exists() for v in scale.values()):
    big = {k: json.load(open(v)) for k, v in scale.items()}
    rescore(big, ROOT / "data/bugsinpy_rows_v1.jsonl")
    small = {"exec": arms["exec"], "score": arms["score"],
             "diff": arms["diff"]}
    ids = [r["id"] for r in small["exec"]["rows"]]
    for k in big:
        assert [r["id"] for r in big[k]["rows"]] == ids, k

    def rate(pack, fn):
        return sum(fn(r) for r in pack["rows"])

    assert rate(big["exec"], grounded) == 239, rate(big["exec"], grounded)
    assert rate(big["score"], grounded) == 97, rate(big["score"], grounded)
    assert rate(big["diff"], grounded) == 109, rate(big["diff"], grounded)
    assert rate(big["diff"], lambda r: bool(r["invented"])) == 79
    assert rate(small["exec"], grounded) == 132
    assert rate(small["score"], grounded) == 17
    inv = lambda r: bool(r["invented"])
    assert rate(small["exec"], inv) == 6
    assert rate(small["score"], inv) == 29
    assert rate(big["exec"], inv) == 10, rate(big["exec"], inv)
    assert rate(big["score"], inv) == 75, rate(big["score"], inv)

    # the rest of the RESULTS.md scale table, so no cell in it can drift
    for pack, want in ((big["exec"], dict(parsed=261, exception=197,
                                          signature=213, symbol=250)),
                       (big["score"], dict(parsed=263, exception=91,
                                           signature=45, symbol=250)),
                       (big["diff"], dict(parsed=263, exception=100,
                                          signature=51, symbol=249))):
        got = {
            "parsed": rate(pack, lambda r: bool(r["explanation"])),
            "exception": rate(pack, lambda r: bool(r["names_exception"])),
            "signature": rate(pack, lambda r: bool(r["quotes_signature"])),
            "symbol": rate(pack, lambda r: bool(r["names_symbol"])),
        }
        assert got == want, (got, want)

    # "only 5 of the 3B's 264 outputs came near its 128-token ceiling"
    near = rate(small["exec"], lambda r: len(r["explanation"]) > 430)
    assert near <= 10, near

    # the two claims the section actually rests on
    drop_small = rate(small["exec"], grounded) - rate(small["score"], grounded)
    drop_big = rate(big["exec"], grounded) - rate(big["score"], grounded)
    assert drop_big > drop_small, (drop_big, drop_small)   # 142 > 115 rows
    assert rate(big["score"], inv) > 2 * rate(small["score"], inv)

    n01 = sum(1 for a, b in zip(small["exec"]["rows"], big["exec"]["rows"])
              if grounded(a) and not grounded(b))
    n10 = sum(1 for a, b in zip(small["exec"]["rows"], big["exec"]["rows"])
              if grounded(b) and not grounded(a))
    assert (n01, n10) == (6, 113), (n01, n10)
    p_scale = float(binomtest(n01, n01 + n10, 0.5).pvalue)
    assert p_scale < 1e-20, p_scale

    # verbosity is not the explanation: the medians must stay within a word
    import statistics as _st
    w = {k: _st.median([len((r["explanation"] or "").split())
                        for r in pack["rows"]])
         for k, pack in (("3b", small["exec"]), ("120b", big["exec"]))}
    assert abs(w["3b"] - w["120b"]) <= 2, w

    # THE claim: a risk score is indistinguishable from no score, at BOTH
    # scales. If this ever starts failing, the thesis has changed.
    for pack_a, pack_b, lo in ((small["score"], small["diff"], 0.05),
                               (big["score"], big["diff"], 0.05)):
        n01 = sum(1 for a, b in zip(pack_a["rows"], pack_b["rows"])
                  if grounded(a) and not grounded(b))
        n10 = sum(1 for a, b in zip(pack_a["rows"], pack_b["rows"])
                  if grounded(b) and not grounded(a))
        pv = float(binomtest(n01, n01 + n10, 0.5).pvalue)
        assert pv > lo, (n01, n10, pv)

V2 = ROOT / "data/bugsinpy_rows_v2.jsonl"
V2_ARMS = {a: ROOT / f"data/bip_arm_{a}_v2.json"
           for a in ("base", "exec", "score", "diff")}
if V2.exists() and all(v.exists() for v in V2_ARMS.values()):
    v2rows = [json.loads(l) for l in open(V2)]
    assert len(v2rows) == 458, len(v2rows)
    assert sum(r["differs"] for r in v2rows) == 452
    assert sum(not r["differs"] for r in v2rows) == 6
    assert len({r["project"] for r in v2rows}) == 17
    assert sum(1 for r in v2rows if r["exception"]) == 398

    sc2 = json.load(open(ROOT / "data/bugsinpy_gate_scores_v2.json"))
    nz2 = sorted(v["metrics_nonzero"] for v in sc2.values())
    assert nz2[len(nz2) // 2] == 14, nz2[len(nz2) // 2]
    v2v = sorted(x["score"] for x in sc2.values())
    assert round(v2v[0], 3) == 0.034 and round(v2v[-1], 3) == 0.995
    assert sum(x > 0.0469 for x in v2v) == 456

    a2 = {a: json.load(open(f)) for a, f in V2_ARMS.items()}
    rescore(a2, V2)
    ids2 = [r["id"] for r in a2["exec"]["rows"]]
    for a in a2:
        assert [r["id"] for r in a2[a]["rows"]] == ids2, a

    T2 = {
        "base":  dict(parsed=456, exception=163, signature=43, symbol=399,
                      invented=11, grounded=183),
        "exec":  dict(parsed=448, exception=218, signature=198, symbol=421,
                      invented=12, grounded=255),
        "score": dict(parsed=448, exception=40, signature=14, symbol=428,
                      invented=47, grounded=48),
        "diff":  dict(parsed=447, exception=38, signature=18, symbol=427,
                      invented=52, grounded=48),
    }
    for arm, want in T2.items():
        got = {
            "parsed": sum(bool(r["explanation"]) for r in a2[arm]["rows"]),
            "exception": sum(bool(r["names_exception"]) for r in a2[arm]["rows"]),
            "signature": sum(bool(r["quotes_signature"]) for r in a2[arm]["rows"]),
            "symbol": sum(bool(r["names_symbol"]) for r in a2[arm]["rows"]),
            "invented": sum(bool(r["invented"]) for r in a2[arm]["rows"]),
            "grounded": sum(grounded(r) for r in a2[arm]["rows"]),
        }
        assert got == want, (arm, got, want)

    def mc2(a, b, metric):
        pick = grounded if metric == "grounded" else (lambda r: bool(r["invented"]))
        fa = [pick(r) for r in a2[a]["rows"]]
        fb = [pick(r) for r in a2[b]["rows"]]
        n01 = sum(1 for x, y in zip(fa, fb) if x and not y)
        n10 = sum(1 for x, y in zip(fa, fb) if y and not x)
        pv = binomtest(n01, n01 + n10, 0.5).pvalue if n01 + n10 else 1.0
        return n01, n10, float(pv)

    for a, b, metric, w01, w10, lo_p, hi_p in [
            ("exec", "base", "grounded", 93, 21, 0, 1e-10),
            ("exec", "score", "grounded", 213, 6, 0, 1e-50),
            ("exec", "diff", "grounded", 212, 5, 0, 1e-50),
            ("score", "diff", "grounded", 16, 16, 0.99, 1.01),
            ("base", "score", "grounded", 144, 9, 0, 1e-30),
            ("base", "diff", "grounded", 142, 7, 0, 1e-30),
            ("score", "exec", "invented", 38, 3, 0, 1e-7),
            ("diff", "exec", "invented", 43, 3, 0, 1e-9),
            ("score", "diff", "invented", 17, 22, 0.52, 0.53),
            ("base", "exec", "invented", 7, 8, 0.99, 1.01)]:
        n01, n10, pv = mc2(a, b, metric)
        assert (n01, n10) == (w01, w10), (a, b, metric, n01, n10)
        assert lo_p <= pv <= hi_p, (a, b, metric, pv)

    # "with an exception class 60%, on a bare assertion 25%"
    e2 = a2["exec"]["rows"]
    hi2 = [r for r in e2 if r["exception"]]
    lo2 = [r for r in e2 if not r["exception"]]
    assert (sum(map(grounded, hi2)), len(hi2)) == (240, 398)
    assert (sum(map(grounded, lo2)), len(lo2)) == (15, 60)

    per2 = collections.defaultdict(lambda: [0, 0])
    for r in e2:
        per2[r["project"]][0] += grounded(r)
        per2[r["project"]][1] += 1
    assert per2["black"] == [4, 23], per2["black"]
    assert per2["scrapy"] == [27, 38], per2["scrapy"]
    assert per2["pandas"] == [104, 161], per2["pandas"]
    assert per2["matplotlib"] == [9, 29], per2["matplotlib"]

    # The two v2 claims that carry the section: the fine-tune transfers under
    # execution, and it does nothing to fabrication.
    assert mc2("exec", "base", "grounded")[2] < 1e-10
    assert mc2("base", "exec", "invented")[2] > 0.05
    # and the thesis claim, again, on 458 real bugs
    assert mc2("score", "diff", "grounded")[2] > 0.05

GUARD = ROOT / "data/bip_guarded_v2.json"
if V2.exists() and GUARD.exists() and V2_ARMS["exec"].exists():
    gp = {"guarded": json.load(open(GUARD)),
          "exec": json.load(open(V2_ARMS["exec"])),
          "base": json.load(open(V2_ARMS["base"]))}
    rescore(gp, V2)
    gids = [r["id"] for r in gp["exec"]["rows"]]
    for k in gp:
        assert [r["id"] for r in gp[k]["rows"]] == gids, k
    gr_rows = gp["guarded"]["rows"]
    assert len(gr_rows) == 458
    assert sum(bool(r["explanation"]) for r in gr_rows) == 439
    assert sum(bool(r["withheld"]) for r in gr_rows) == 36
    assert sum(bool(r["names_exception"]) for r in gr_rows) == 140
    assert sum(bool(r["quotes_signature"]) for r in gr_rows) == 162
    assert sum(bool(r["names_symbol"]) for r in gr_rows) == 398
    assert sum(bool(r["invented"]) for r in gr_rows) == 8
    assert sum(grounded(r) for r in gr_rows) == 183

    def mcg(a, b, metric="grounded"):
        pick = grounded if metric == "grounded" else (lambda r: bool(r["invented"]))
        fa = [pick(r) for r in gp[a]["rows"]]
        fb = [pick(r) for r in gp[b]["rows"]]
        n01 = sum(1 for x, y in zip(fa, fb) if x and not y)
        n10 = sum(1 for x, y in zip(fa, fb) if y and not x)
        return n01, n10, float(binomtest(n01, n01 + n10, 0.5).pvalue
                               if n01 + n10 else 1.0)

    n01, n10, pv = mcg("exec", "guarded")
    assert (n01, n10) == (101, 29) and pv < 1e-9, (n01, n10, pv)
    # THE deployment finding: the shipped path is indistinguishable from the
    # un-fine-tuned base model. If this ever starts failing, say so loudly --
    # it means the prompt around the guards stopped throwing away the adapter.
    n01, n10, pv = mcg("guarded", "base")
    assert (n01, n10) == (67, 67) and pv > 0.99, (n01, n10, pv)
    n01, n10, pv = mcg("exec", "guarded", "invented")
    assert (n01, n10) == (8, 4), (n01, n10)

    # "roughly 30% guard, 70% prompt"
    G = {r["id"]: r for r in gr_rows}
    E = {r["id"]: r for r in gp["exec"]["rows"]}
    lost = [i for i in gids if grounded(E[i]) and not grounded(G[i])]
    wh = {i for i in lost if G[i]["withheld"]}
    silent = {i for i in lost if not G[i]["explanation"]}
    assert (len(lost), len(wh), len(silent)) == (101, 29, 13)
    assert len(lost) - len(wh | silent) == 70

    # "71 of 458 deployed answers against 11 in the bench arm"
    import re as _re
    nochange = _re.compile(
        r"does not (affect|change|alter)|no (observable|visible|functional) change"
        r"|behaviou?r (is )?unchanged|remains the same", _re.I)
    hit_g = sum(bool(nochange.search(r["explanation"] or "")) for r in gr_rows)
    hit_e = sum(bool(nochange.search(r["explanation"] or ""))
                for r in gp["exec"]["rows"])
    assert (hit_g, hit_e) == (71, 11), (hit_g, hit_e)
    assert sum(grounded(G[i]) for i in gids
               if nochange.search(G[i]["explanation"] or "")) == 9

# --- v3: the retrained checkpoint, RESULTS.md "40% -> 86% deployed" ----------
# The v2 blocks above are deliberately left asserting their original values:
# they pin a historical measurement of a real configuration, and the files they
# read are frozen. This block pins what superseded them.
V3 = {a: ROOT / f"data/bip_arm_{a}_v2.json" for a in ("v3plain", "v3strong")}
GUARD3 = ROOT / "data/bip_guarded_v3_v2.json"
if (V2.exists() and GUARD3.exists() and V3["v3plain"].exists()
        and V3["v3strong"].exists() and V2_ARMS["base"].exists()
        and (ROOT / "data/bip_arm_basestrong_v2.json").exists()):
    a3 = {k: json.load(open(f)) for k, f in V3.items()}
    a3["guarded"] = json.load(open(GUARD3))
    a3["base"] = json.load(open(V2_ARMS["base"]))
    a3["exec"] = json.load(open(V2_ARMS["exec"]))
    a3["basestrong"] = json.load(open(ROOT / "data/bip_arm_basestrong_v2.json"))
    a3["guardedv2"] = json.load(open(GUARD))
    rescore(a3, V2)
    ids3 = [r["id"] for r in a3["v3plain"]["rows"]]
    for k in a3:
        assert [r["id"] for r in a3[k]["rows"]] == ids3, k

    T3 = {
        "v3plain":  dict(parsed=440, exception=331, signature=390, symbol=414,
                         invented=9, grounded=400),
        "v3strong": dict(parsed=422, exception=313, signature=373, symbol=384,
                         invented=31, grounded=356),
        "guarded":  dict(parsed=436, exception=329, signature=381, symbol=379,
                         invented=2, grounded=392),
    }
    for arm, want in T3.items():
        R = a3[arm]["rows"]
        assert len(R) == 458, (arm, len(R))
        got = {
            "parsed": sum(bool(r["explanation"]) for r in R),
            "exception": sum(bool(r["names_exception"]) for r in R),
            "signature": sum(bool(r["quotes_signature"]) for r in R),
            "symbol": sum(bool(r["names_symbol"]) for r in R),
            "invented": sum(bool(r["invented"]) for r in R),
            "grounded": sum(grounded(r) for r in R),
        }
        assert got == want, (arm, got, want)
    assert sum(bool(r["withheld"]) for r in a3["guarded"]["rows"]) == 18
    assert sum(1 for r in a3["guarded"]["rows"]
               if r["withheld"] and not r["explanation"]) == 14

    def mc3(a, b, metric="grounded"):
        pick = grounded if metric == "grounded" else (lambda r: bool(r["invented"]))
        fa = [pick(r) for r in a3[a]["rows"]]
        fb = [pick(r) for r in a3[b]["rows"]]
        n01 = sum(1 for x, y in zip(fa, fb) if x and not y)
        n10 = sum(1 for x, y in zip(fa, fb) if y and not x)
        return n01, n10, float(binomtest(n01, n01 + n10, 0.5).pvalue
                               if n01 + n10 else 1.0)

    # THE claim: the adapter on a bare prompt beats the base on the best prompt.
    # If this stops holding, the "not just prompt engineering" argument is gone.
    n01, n10, pv = mc3("v3plain", "basestrong")
    assert (n01, n10) == (139, 18) and pv < 1e-20, (n01, n10, pv)
    assert mc3("v3plain", "exec")[:2] == (158, 13)
    assert mc3("v3plain", "base")[:2] == (224, 7)
    # the strong prompt HURTS the tuned model, on both correctness and honesty
    n01, n10, pv = mc3("v3plain", "v3strong")
    assert (n01, n10) == (71, 27) and pv < 1e-4, (n01, n10, pv)
    n01, n10, pv = mc3("v3strong", "v3plain", "invented")
    assert (n01, n10) == (26, 4) and pv < 1e-4, (n01, n10, pv)
    # the deployed path, and the guard chain now costing nothing measurable
    n01, n10, pv = mc3("guarded", "guardedv2")
    assert (n01, n10) == (217, 8) and pv < 1e-50, (n01, n10, pv)
    n01, n10, pv = mc3("guarded", "v3plain")
    assert (n01, n10) == (31, 39) and pv > 0.05, (n01, n10, pv)

    # The copy-ceiling defence: the gain is larger where no exception class
    # exists to name, which is the majority of the corpus.
    v2rows = {r["id"]: r for r in (json.loads(l) for l in open(V2))}
    hard = [i for i in ids3
            if str(v2rows[i].get("exception") or "").strip()
            in ("", "none", "None", "AssertionError")]
    assert len(hard) == 250, len(hard)
    H = set(hard)
    P3 = {r["id"]: r for r in a3["v3plain"]["rows"]}
    BS = {r["id"]: r for r in a3["basestrong"]["rows"]}
    for tag, sel, want in (("hard", hard, (196, 117, 95, 16)),
                           ("easy", [i for i in ids3 if i not in H],
                            (204, 162, 44, 2))):
        gv3 = sum(grounded(P3[i]) for i in sel)
        gbs = sum(grounded(BS[i]) for i in sel)
        n01 = sum(1 for i in sel if grounded(P3[i]) and not grounded(BS[i]))
        n10 = sum(1 for i in sel if grounded(BS[i]) and not grounded(P3[i]))
        assert (gv3, gbs, n01, n10) == want, (tag, gv3, gbs, n01, n10)

    # The decomposition: the missing cell of the 2x2 is the v2 adapter under the
    # CURRENT four-case core.SYSTEM. Without it the deployed 40% -> 86% claim
    # confounds the retrain with a prompt edit made 1h50m after the v2 run.
    ISO = ROOT / "data/bip_guarded_v2adapter_4case_v2.json"
    if ISO.exists():
        a3["iso"] = json.load(open(ISO))
        rescore({"iso": a3["iso"]}, V2)
        assert [r["id"] for r in a3["iso"]["rows"]] == ids3
        R = a3["iso"]["rows"]
        assert sum(grounded(r) for r in R) == 207, sum(grounded(r) for r in R)
        assert sum(bool(r["invented"]) for r in R) == 15
        assert sum(bool(r["withheld"]) for r in R) == 19
        # prompt alone: real but small, and it RAISES fabrication (8 -> 15)
        n01, n10, pv = mc3("iso", "guardedv2")
        assert (n01, n10) == (63, 39) and 0.01 < pv < 0.05, (n01, n10, pv)
        # corpus alone, prompt held fixed: the claim this decomposition exists for
        n01, n10, pv = mc3("guarded", "iso")
        assert (n01, n10) == (196, 11) and pv < 1e-40, (n01, n10, pv)
        # and the two effects sum to the headline
        g = lambda k: sum(grounded(r) for r in a3[k]["rows"])
        assert g("iso") - g("guardedv2") == 24
        assert g("guarded") - g("iso") == 185
        assert g("guarded") - g("guardedv2") == 209

    # Not a degenerate paste: no recitation, and the signature is a minority of
    # the prose. `print(before)` would score 458/458 on this rubric.
    G3 = [r for r in a3["v3plain"]["rows"] if grounded(r)]
    assert len(G3) == 400
    frames = {" ".join(sorted(set((r["explanation"] or "").lower().split())))
              for r in G3}
    assert len(frames) == 400, len(frames)
    ratio = sorted(len(str(v2rows[r["id"]].get("before") or ""))
                   / max(1, len(r["explanation"] or "")) for r in G3)
    assert sum(1 for x in ratio if x >= 0.9) == 2, sum(1 for x in ratio if x >= 0.9)


print("ok")
