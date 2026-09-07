"""A blind packet for grading BugsInPy explanations by hand, and the agreement
number it produces against the automatic rubric.

Every "grounded" figure in the BugsInPy section is decided by a regex rubric
written in an afternoon, and one bug has already been found in it -- it counted
a correct explanation as a fabrication whenever the measured failure named a
second exception class. A number produced that way is only as good as the
agreement between it and a person, and that agreement has never been measured.

What this validates is the RUBRIC, not the measurement. The measured failure is
shown to the rater on purpose: it is ground truth, obtained by running the
project's own test, and the rater is being asked the same question the rubric
answers -- does this explanation state what the program actually did? What is
withheld is the rubric's verdict and its working, so the rater cannot agree with
it for the wrong reason.

Three judgements per case, all plain:

    grounded   y/n  does the explanation state the real failure
    invented   y/n  does it assert a failure that did not happen
    direction  y/n  does it get the direction of the change right

`direction` has no counterpart in the rubric, and that is why it is here.
tqdm-1's fix moves `start` from `tqdm_class` to `enumerate`; the model wrote
"moved from the `enumerate` call to the `tqdm_class` constructor", which is
backwards, and it scored grounded anyway because it quoted the real TypeError.
RESULTS.md says inversions have dominated every hand-grade of this project, and
no automatic check in this pipeline can see them: `direction_reversed` compares
against the measured before/after, which on this corpus are "a failure" and
"passed". So this column is measured by a person or not at all.

Leave either blank when unsure. A blank is data; a guess is noise.

    python bench/bugsinpy_rater.py --emit
    python bench/bugsinpy_rater.py --score data/bip_rater.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bench.bugsinpy_compare import arm_path, rescore  # noqa: E402


def grounded(r: dict) -> bool:
    return bool((r["names_exception"] or r["quotes_signature"]) and
                not r["invented"])


def load(arm: str, rows_path: pathlib.Path) -> list[dict]:
    p = arm_path(arm, ROOT / "data", "bip_arm_")
    if not p.exists():
        raise SystemExit(f"no arm file at {p}")
    data = {arm: json.loads(p.read_text())}
    rescore(data, rows_path)
    return data[arm]["rows"]


def emit(arm: str, n: int, seed: int, rows_path: pathlib.Path,
         out: pathlib.Path, csv_out: pathlib.Path) -> None:
    src = {json.loads(l)["id"]: json.loads(l) for l in open(rows_path)}
    rows = [r for r in load(arm, rows_path) if r["id"] in src]
    rng = random.Random(seed)
    rng.shuffle(rows)
    picked = rows[:n]

    lines = [
        "# BugsInPy rater packet",
        "",
        f"{len(picked)} cases drawn from the `{arm}` arm with seed {seed}.",
        "",
        "Each case shows a real commit from a real project, what the project's",
        "own failing test reported before and after the change, and what the",
        "model said about it. **The before/after is ground truth** -- it was",
        "obtained by running the test at the parent commit and again with the",
        "fix applied. You are not checking the measurement. You are checking",
        "the sentence against it.",
        "",
        "For each case, two judgements:",
        "",
        "- **grounded** — `y` if the explanation states what the program",
        "  actually did: it names the real failure, or quotes a distinctive",
        "  part of the real message. `n` if it is vague, generic, or talks",
        "  only about the code without saying what the run reported.",
        "- **invented** — `y` if it asserts a failure that did not happen",
        "  (names an exception nothing raised, claims an outcome the run",
        "  contradicts). `n` otherwise.",
        "- **direction** — `y` if it gets the direction of the change right.",
        "  `n` if it states the edit backwards: says a value moved from A to B",
        "  when the diff moves it from B to A, says something was added that",
        "  was removed, or names the pre-change behaviour as the post-change",
        "  one. Read the diff for this one; an explanation can quote the real",
        "  failure and still describe the edit in reverse.",
        "",
        "An explanation can be a perfectly sensible code review and still be",
        "`grounded=n`. That is the intended reading: the question is whether it",
        "committed to the measured behaviour, not whether it is a good comment.",
        "",
        "Leave a cell blank if unsure. A blank is data; a guess is noise.",
        "",
        f"Record answers in `{csv_out.name}` as "
        f"`id,grounded,invented,direction`, then:",
        "",
        f"    python bench/bugsinpy_rater.py --score {csv_out}",
        "",
        "The rubric's own verdict is not in this file.",
        "",
        "---",
        "",
    ]
    for i, r in enumerate(picked, 1):
        base = src[r["id"]]
        diff = base["messages"][1]["content"]
        diff = diff.split("```diff", 1)[-1].rsplit("```", 1)[0].strip()
        if len(diff) > 2500:
            diff = diff[:2500] + "\n... (truncated)"
        lines.append(f"## {i}. `{r['id']}`  ({r['project']})\n")
        lines.append(f"**Commit message:** {base.get('subject') or '(none)'}\n")
        lines.append(f"**Test run:** `{(base.get('run_test') or ['?'])[0]}`\n")
        lines.append("```diff")
        lines.append(diff)
        lines.append("```\n")
        lines.append(f"**Measured before:** `{r['before']}`\n")
        lines.append(f"**Measured after:**  `{base['after']}`\n")
        lines.append(f"**The model said:** {r['explanation'] or '(nothing)'}\n")
        lines.append(f"`{r['id']}` — grounded: ____   invented: ____   "
                     f"direction: ____\n")
        lines.append("---\n")
    out.write_text("\n".join(lines))

    with open(csv_out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "grounded", "invented", "direction"])
        for r in picked:
            w.writerow([r["id"], "", "", ""])
    print(f"{len(picked)} cases -> {out}")
    print(f"blank answer sheet -> {csv_out}")
    print("Blinded: the rubric's verdict and its per-check flags are not in the "
          "packet.")


def emit_inventions(rows_path: pathlib.Path, out: pathlib.Path,
                    csv_out: pathlib.Path, arms: tuple = ("exec", "score", "diff"),
                    cap: int = 0, seed: int = 7) -> None:
    """Every flagged invention, across all three arms, for direct checking.

    A 50-case random sample contains one invention, because inventions are rare
    in the arm that matters -- which is the finding, and which also means the
    random packet cannot validate it. The claim "2% against 11%" rests on ~60
    specific rows, so those rows are checkable in full rather than sampled.
    Whether each is really an invention is a yes/no about one sentence, so this
    is a shorter job than it looks.
    """
    # `arms` is a parameter because the default three name the FIRST corpus:
    # `bip_arm_exec.json` is n=264 and a superseded checkpoint, so grading it
    # validates the rubric against output nobody reports. Pass the arms the
    # paper actually cites.
    #
    # `cap` samples the arms that invent a lot. The whole population is the
    # right packet when it is ~60 rows; on the v2 corpus the diff and score arms
    # flag ~50 each and the total runs past 100, which is a different size of
    # favour to ask. The arm under test is never capped -- its inventions are
    # the ones the headline depends on -- so what gets sampled is only the
    # comparison side, and the comparison becomes an estimate with a stated n
    # rather than a census.
    src = {json.loads(l)["id"]: json.loads(l) for l in open(rows_path)}
    rng = random.Random(seed)
    picked = []
    for i, arm in enumerate(arms):
        try:
            rows = load(arm, rows_path)
        except SystemExit:
            continue
        flagged = [(arm, r) for r in rows if r["invented"] and r["id"] in src]
        if cap and i and len(flagged) > cap:
            rng.shuffle(flagged)
            flagged = flagged[:cap]
        picked += flagged

    lines = [
        "# BugsInPy invention packet",
        "",
        f"All {len(picked)} explanations the rubric flagged as asserting a",
        f"failure that did not happen, across arms {', '.join(arms)}.",
        "",
        "Every flagged row from the FIRST arm is here -- that is the arm the",
        "headline depends on, and its inventions are the ones that would sink",
        "it. The comparison arms are sampled where they flag more than the cap,",
        "so the contrast they support is an estimate with a stated n.",
        "",
        "For each: does the explanation assert a failure the measurement",
        "contradicts or never showed?",
        "",
        "- `y` — yes, it names an exception or outcome that did not happen",
        "- `n` — no, the rubric is wrong here; the named failure IS in the",
        "  measurement, or the sentence is hedged enough not to assert it",
        "",
        "The arm each row came from is shown, because it is not blindable --",
        "the prompt differs visibly. What is withheld is which class the rubric",
        "thought was invented.",
        "",
        f"Record as `invented` against the matching `case` row in "
        f"`{csv_out.name}` -- the case number, id and arm are already filled",
        "in, so you only type y or n. Then:",
        "",
        f"    python bench/bugsinpy_rater.py --score {csv_out} --arm exec",
        "",
        "---",
        "",
    ]
    for i, (arm, r) in enumerate(picked, 1):
        base = src[r["id"]]
        lines.append(f"## {i}. `{r['id']}`  ({r['project']}, arm `{arm}`)\n")
        lines.append(f"**Commit message:** {base.get('subject') or '(none)'}\n")
        lines.append(f"**Measured before:** `{r['before']}`\n")
        lines.append(f"**Measured after:**  `{base['after']}`\n")
        lines.append(f"**The model said:** {r['explanation'] or '(nothing)'}\n")
        lines.append(f"`{r['id']}` — invented: ____\n")
        lines.append("---\n")
    out.write_text("\n".join(lines))
    # `arm` is a column because the same row is often flagged by more than one
    # arm -- 11 of 59 on the v3/diff/score packet -- and an answer sheet keyed by
    # id alone silently merges them, so one judgement lands on two different
    # sentences. `case` is the packet's own numbering, so a grader never has to
    # work out which duplicate they are looking at.
    with open(csv_out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case", "id", "arm", "invented"])
        for i, (arm, r) in enumerate(picked, 1):
            w.writerow([i, r["id"], arm, ""])
    print(f"{len(picked)} flagged inventions -> {out}")
    print(f"blank answer sheet -> {csv_out}")


def kappa(a: list[bool], b: list[bool]) -> float:
    """Cohen's kappa -- agreement above what chance alone would give."""
    n = len(a)
    if not n:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe) if pe != 1 else float("nan")


def score(csv_path: pathlib.Path, arm: str, rows_path: pathlib.Path) -> int:
    rubric = {r["id"]: r for r in load(arm, rows_path)}
    # Keyed by id, but an invention sheet carries an `arm` column and may hold
    # the same id twice. Only the rows for the arm being scored are read, so a
    # duplicate no longer overwrites its twin from another arm.
    human: dict[str, dict] = {}
    with open(csv_path) as fh:
        for row in csv.DictReader(fh):
            if (row.get("arm") or "").strip() not in ("", arm):
                continue
            human[row["id"].strip()] = row

    # `direction` is a standalone human measurement -- there is nothing
    # automatic to agree with, which is the point of collecting it.
    dvals = [(row.get("direction") or "").strip().lower() for row in human.values()]
    dgraded = [v in ("y", "yes", "1") for v in dvals
               if v in ("y", "n", "yes", "no", "1", "0")]
    if dgraded:
        ok = sum(dgraded)
        print(f"\n=== direction  n={len(dgraded)} graded (human only, no rubric "
              f"counterpart)")
        print(f"  states the change the right way round  {ok}/{len(dgraded)} "
              f"({ok / len(dgraded):.0%})")
        print(f"  BACKWARDS                              "
              f"{len(dgraded) - ok}/{len(dgraded)} "
              f"({1 - ok / len(dgraded):.0%})")

    for field, auto in (("grounded", grounded),
                        ("invented", lambda r: bool(r["invented"]))):
        h, m, skipped = [], [], 0
        for rid, row in human.items():
            v = (row.get(field) or "").strip().lower()
            if v not in ("y", "n", "yes", "no", "1", "0"):
                skipped += 1
                continue
            if rid not in rubric:
                continue
            h.append(v in ("y", "yes", "1"))
            m.append(auto(rubric[rid]))
        if not h:
            print(f"\n{field}: nothing graded yet "
                  f"({skipped} blank of {len(human)})")
            continue
        n = len(h)
        agree = sum(x == y for x, y in zip(h, m))
        both = sum(x and y for x, y in zip(h, m))
        h_only = sum(x and not y for x, y in zip(h, m))
        m_only = sum(y and not x for x, y in zip(h, m))
        print(f"\n=== {field}  n={n} graded, {skipped} left blank")
        print(f"  agreement      {agree}/{n} ({agree / n:.0%})")
        print(f"  Cohen's kappa  {kappa(h, m):+.2f}")
        print(f"  human yes      {sum(h)}/{n} ({sum(h) / n:.0%})")
        print(f"  rubric yes     {sum(m)}/{n} ({sum(m) / n:.0%})")
        print(f"  both yes {both}   human only {h_only}   rubric only {m_only}")
        graded_ids = [k for k in human if k in rubric and
                      (human[k].get(field) or "").strip().lower()
                      in ("y", "n", "yes", "no", "1", "0")]
        dis = [rid for rid, x, y in zip(graded_ids, h, m) if x != y]
        if dis:
            print(f"  where they differ ({len(dis)}):")
        for rid in dis[:8]:
            print(f"    {rid}: human={human[rid][field]} "
                  f"rubric={'y' if auto(rubric[rid]) else 'n'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--emit-inventions", action="store_true",
                    help="every flagged invention, all arms, for direct checking")
    ap.add_argument("--score", type=pathlib.Path)
    ap.add_argument("--arm", default="exec")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--rows", type=pathlib.Path,
                    default=ROOT / "data" / "bugsinpy_rows_v1.jsonl")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "data" / "bip_rater_packet.md")
    ap.add_argument("--csv", type=pathlib.Path,
                    default=ROOT / "data" / "bip_rater.csv")
    ap.add_argument("--arms", default="exec,score,diff",
                    help="--emit-inventions: arms to pull flagged rows from; "
                         "the FIRST is never sampled")
    ap.add_argument("--cap", type=int, default=0,
                    help="--emit-inventions: max rows from each arm after the "
                         "first (0 = take all)")
    args = ap.parse_args()
    if args.emit:
        emit(args.arm, args.n, args.seed, args.rows, args.out, args.csv)
        return 0
    if args.emit_inventions:
        emit_inventions(args.rows, args.out, args.csv,
                        arms=tuple(a.strip() for a in args.arms.split(",")),
                        cap=args.cap, seed=args.seed)
        return 0
    if args.score:
        return score(args.score, args.arm, args.rows)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
