"""Assistant targets for the JIT dataset, supervised by the actual repair.

    python -m dataset_builder.build_repair_targets --audit
    python -m dataset_builder.build_repair_targets --out data/sft_repair.jsonl

Why this is different from every previous corpus in this project
----------------------------------------------------------------
v6 and v7 are 100 hand-written 5-8 line functions. Writing targets for REAL
commits stalled twice, because describing an arbitrary commit is the same task
the model fails at - only 18 of 79 mined commits could be described mechanically
at all.

A defect-inducing commit does not have that problem, because a later commit
REPAIRED it. The repair says which file, which identifiers and which direction,
objectively. Nothing here is authored; every field is read out of a diff.

  target_file           the file the fix changed that the BIC last touched
  affected_identifiers  symbols the fix added or removed
  repair_direction      the shape of the repair, classified from its own diff
  explanation           composed from those, per case

Confidence is not invented
--------------------------
`effect.confidence` in the v3 contract was a self-assessment, and it did not
transfer: seed 42 emitted 0 `possible` in 101 answers, seed 7 emitted 78% on one
set, from the SAME corpus. A constant float here would repeat that.

So confidence is derived from how strong the SZZ evidence actually is:

  lines the BIC explains in the fix   more blamed lines = a firmer link
  how many BICs the fix blames        a fix blaming 1 commit is a cleaner
                                      attribution than one blaming 31
  issue key on the fix                "ZOOKEEPER-4925: Fix data loss" is a
                                      stronger signal than "fix stuff"

That is label confidence, and it is honest: SZZ precision is 50-70%, so a
uniform 0.9 across every defective row would be a lie the model would learn.

What this still cannot do
-------------------------
The explanation says what the REPAIR did, not what the defect IS. Those are
close but not identical - a fix can be a workaround. And the labels carry SZZ's
error rate. Both belong in threats to validity.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REPOS = ROOT / "data" / "repos"

_DEF = re.compile(
    r"(?:^|\s)(?:def\s+([A-Za-z_]\w*)"
    r"|class\s+([A-Za-z_]\w*)"
    r"|function\s+([A-Za-z_$][\w$]*)"
    r"|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*="
    r"|(?:public|private|protected|static|final)\s+[\w<>\[\], ]+?\s+([A-Za-z_]\w*)\s*\()")
_CALL = re.compile(r"\b([A-Za-z_]\w{2,})\s*\(")
_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "new", "super",
             "this", "self", "print", "throw", "assert", "import", "require",
             "function", "class", "def", "public", "private", "static", "void",
             "int", "String", "boolean", "let", "const", "var", "try", "with"}

# Repair shapes, tried in order. Each is (name, test on the fix's own diff).
def _shapes(removed: str, added: str) -> str:
    r, a = removed, added
    if re.search(r"[!=<>]=|[<>]", r) and re.search(r"[!=<>]=|[<>]", a) and \
       re.sub(r"[<>=!]", "", r).strip() == re.sub(r"[<>=!]", "", a).strip():
        return "comparison operator changed"
    if re.search(r"\b(null|None|nil|undefined)\b", a) and \
       not re.search(r"\b(null|None|nil|undefined)\b", r):
        return "null or empty check added"
    if re.search(r"\bif\b", a) and not re.search(r"\bif\b", r):
        return "guard condition added"
    if re.search(r"\btry\b|\bcatch\b|\bexcept\b", a) and \
       not re.search(r"\btry\b|\bcatch\b|\bexcept\b", r):
        return "error handling added"
    if re.search(r"[-+]\s*1\b", r) != re.search(r"[-+]\s*1\b", a):
        return "boundary adjusted by one"
    if re.search(r"\b(synchronized|lock|volatile|atomic|mutex)\b", a, re.I):
        return "synchronisation added"
    if len(a.splitlines()) > len(r.splitlines()) * 2:
        return "logic added where there was none"
    if r and not a:
        return "code removed"
    return "logic replaced"



# The defect stated in the PRESENT TENSE, about the code under review.
#
# The three frames these replace all spoke from hindsight - "A later commit
# repaired {f}", "{f} was repaired afterwards", "The repair to {f} shows". The
# repair is how the target was DERIVED; it is not something the model can see.
# Training it to say "was repaired afterwards" teaches it to assert a fact it
# can never ground at inference, which manufactures a fabrication class instead
# of removing one. The repair still decides WHAT and WHERE - it just no longer
# supplies the tense.
#
# Keyed by repair shape, 4 frames each, so the skeleton count is 36 rather than
# the 3 it was. `{ids}` is filled with a varying number of identifiers, which
# widens it further without inventing anything.
DEFECT_FRAMES = {
 "comparison operator changed": [
   "The comparison controlling {ids} in {f} uses the wrong operator.",
   "{f} compares {ids} the wrong way round, so the boundary case falls to the wrong branch.",
   "The test on {ids} in {f} admits the case it should exclude.",
   "{ids} in {f} is compared with an operator that mis-handles the equal case."],
 "null or empty check added": [
   "{ids} in {f} is used without checking for null or empty first.",
   "{f} dereferences {ids} on a path where it can be absent.",
   "No null or empty check guards {ids} in {f}.",
   "{f} assumes {ids} is populated; nothing on this path establishes that."],
 "guard condition added": [
   "{ids} in {f} runs unguarded on a path that needs a condition.",
   "{f} reaches {ids} without the condition that should protect it.",
   "The call to {ids} in {f} is missing its guard.",
   "Nothing in {f} gates {ids} before it executes."],
 "error handling added": [
   "{ids} in {f} can fail and the failure is not handled.",
   "{f} calls {ids} without catching the error it can raise.",
   "An error raised by {ids} in {f} propagates uncaught.",
   "{f} leaves the failure path around {ids} unhandled."],
 "boundary adjusted by one": [
   "The boundary around {ids} in {f} is off by one.",
   "{f} is one element out when it bounds {ids}.",
   "The index or limit applied to {ids} in {f} is off by one.",
   "{ids} in {f} stops one short of, or one past, the intended element."],
 "synchronisation added": [
   "{ids} in {f} is accessed from more than one thread without synchronisation.",
   "{f} mutates {ids} without holding a lock.",
   "Concurrent access to {ids} in {f} is unsynchronised.",
   "{ids} in {f} is shared state with no mutual exclusion around it."],
 "logic added where there was none": [
   "{f} omits handling for {ids} entirely on this path.",
   "The case around {ids} in {f} is not handled at all.",
   "{f} has no branch covering {ids}.",
   "Nothing in {f} accounts for {ids} when this path is taken."],
 "code removed": [
   "{f} still carries {ids}, which this path should not execute.",
   "{ids} in {f} runs where it should not.",
   "The work {ids} does in {f} is not wanted on this path.",
   "{f} executes {ids} redundantly."],
 "logic replaced": [
   "The logic around {ids} in {f} is wrong as written.",
   "{f} computes {ids} incorrectly on this path.",
   "What {f} does with {ids} does not produce the intended result.",
   "The handling of {ids} in {f} is incorrect."],
}

# --- clean-side shape detection -------------------------------------------
# The clean explanation used to say "no later commit repairs this file", which
# is an ARGUMENT FROM ABSENCE: the label means only that no fix has blamed it
# yet, not that it is safe. Training on that teaches the model to assert
# something the data cannot establish. These frames describe what the diff
# structurally DOES instead, which is checkable against the diff itself.
_TS_CACHE: dict = {}


def ast_kinds(code: str, ext: str) -> set:
    """Node types in the changed lines, via tree-sitter where the fragment parses."""
    lang = {".py": "python", ".js": "javascript", ".mjs": "javascript",
            ".ts": "typescript", ".tsx": "typescript", ".java": "java"}.get(ext)
    if not lang or not code.strip():
        return set()
    try:
        if lang not in _TS_CACHE:
            import tree_sitter as ts
            if lang == "python":
                import tree_sitter_python as m; L = ts.Language(m.language())
            elif lang == "javascript":
                import tree_sitter_javascript as m; L = ts.Language(m.language())
            elif lang == "typescript":
                import tree_sitter_typescript as m; L = ts.Language(m.language_typescript())
            else:
                import tree_sitter_java as m; L = ts.Language(m.language())
            _TS_CACHE[lang] = ts.Parser(L)
        tree = _TS_CACHE[lang].parse(code.encode("utf8", "replace"))
    except Exception:
        return set()
    # Iterative, not recursive: a diff fragment with unbalanced braces parses
    # into a pathologically deep tree and blew Python's recursion limit at ~1000.
    # The node cap bounds the cost on very large hunks; the shapes we look for
    # appear near the top of the tree anyway.
    kinds, stack, seen = set(), [tree.root_node], 0
    while stack and seen < 20000:
        n = stack.pop()
        kinds.add(n.type)
        seen += 1
        stack.extend(n.children)
    return kinds


def clean_shape(added: str, removed: str, ext: str) -> str:
    """What the change structurally is. AST first, regex where it will not parse."""
    k = ast_kinds(added, ext) | ast_kinds(removed, ext)
    if {"function_definition", "function_declaration", "method_declaration",
        "class_definition", "class_declaration"} & k:
        return "definition"
    if {"if_statement", "else_clause", "switch_statement", "ternary_expression",
        "conditional_expression"} & k:
        return "branch"
    if {"for_statement", "while_statement", "for_in_statement",
        "enhanced_for_statement", "do_statement"} & k:
        return "loop"
    if {"return_statement"} & k:
        return "return"
    if {"assignment", "assignment_expression", "variable_declarator",
        "local_variable_declaration"} & k:
        return "assignment"
    if {"call", "call_expression", "method_invocation"} & k:
        return "call"
    # regex fallback for fragments tree-sitter will not parse
    body = added + "\n" + removed
    if re.search(r"\b(def|function|class)\b|\b(public|private|protected)\s+\w+\s+\w+\s*\(", body):
        return "definition"
    if re.search(r"\bif\b|\belse\b|\bswitch\b|\?.*:", body):
        return "branch"
    if re.search(r"\bfor\b|\bwhile\b", body):
        return "loop"
    if re.search(r"\breturn\b", body):
        return "return"
    if re.search(r"=[^=]", body):
        return "assignment"
    return "other"


# 20 frames, 3-4 per shape. Every one describes the operation and its scope; none
# claims the commit is defect-free.
# 56 frames, 8 per shape. It was 24, which produced 41 distinct skeletons across
# 1178 clean targets - 3% - while raw distinctness read 99% because the filename
# slot made every string unique. That is precisely how the v4 `check` field
# passed its audit at "100 distinct in 366" with one frame in 357 of them, so
# the count here is measured with the {f} and {ids} slots stripped, not raw.
#
# None of them claims the commit is defect-free: the label means only that no
# fix has blamed it yet. Each describes what the diff structurally DOES, which
# is checkable against the diff itself.
CLEAN_FRAMES = {
 "definition": [
   "Introduces {ids} in {f} to encapsulate logic without altering external state.",
   "Adds {ids} as a new definition in {f}; existing callers keep their previous entry points.",
   "{f} gains {ids}; the surrounding definitions are unchanged.",
   "Defines {ids} in {f} alongside the existing structure rather than in place of it.",
   "Declares {ids} in {f}; nothing that existed before is redirected through it.",
   "{ids} is new in {f}, so it has no prior behaviour to contradict.",
   "Adds {ids} to {f} as additional surface rather than a change to existing surface.",
   "{f} grows {ids}; the file's existing entry points are untouched."],
 "branch": [
   "Updates conditional branching in {f} ({ids}) while maintaining existing control flow.",
   "Adjusts the branch condition around {ids} in {f}; both arms remain reachable.",
   "Refines the guard on {ids} in {f} without changing what the branches do.",
   "Reworks conditional handling for {ids} in {f} within the existing structure.",
   "Restates the condition on {ids} in {f}; the same cases reach the same arms.",
   "{f} reorganises the branch around {ids} without adding a path.",
   "Tightens how {ids} is tested in {f}, leaving the outcomes as they were.",
   "The conditional covering {ids} in {f} is rewritten in place."],
 "loop": [
   "Modifies iteration over {ids} in {f} with the bounds it already had.",
   "Adjusts the loop around {ids} in {f}; the traversal shape is preserved.",
   "Reworks the iteration body for {ids} in {f} without changing its bounds.",
   "{f} iterates {ids} the same number of times by a different route.",
   "Restructures the loop over {ids} in {f}; entry and exit conditions are unchanged.",
   "The body of the loop on {ids} in {f} is rearranged in place.",
   "{f} keeps its traversal of {ids} and changes only what happens inside it.",
   "Iteration over {ids} in {f} is rewritten without widening its range."],
 "return": [
   "Modifies the local execution path in {ids} ({f}) with valid bounds and return paths.",
   "Adjusts what {ids} returns in {f}; every path still terminates.",
   "Reshapes the return handling for {ids} in {f} within the existing signature.",
   "{ids} in {f} returns by a different route to the same contract.",
   "The exit paths of {ids} in {f} are reorganised; each one still returns.",
   "{f} changes how {ids} arrives at its result, not what the result is.",
   "Rewrites the tail of {ids} in {f} without leaving a path unreturned.",
   "{ids} in {f} keeps its return type and its terminating paths."],
 "assignment": [
   "Adjusts assignment and references for {ids} in {f} within local scope.",
   "Rebinds {ids} in {f}; the surrounding reads are updated with it.",
   "Changes how {ids} is initialised in {f} without widening its scope.",
   "Updates the value flow through {ids} in {f}, local to the enclosing block.",
   "{ids} in {f} is assigned differently; its visibility is unchanged.",
   "Reorders the assignments around {ids} in {f} inside the same block.",
   "{f} sets {ids} by another route without exporting it further.",
   "The initialisation of {ids} in {f} moves within its existing scope."],
 "call": [
   "Updates the call to {ids} in {f}; the surrounding sequence is unchanged.",
   "Adjusts arguments passed to {ids} in {f} within the existing call site.",
   "Routes {ids} in {f} through the same path with revised inputs.",
   "{f} calls {ids} with different arguments in the same position.",
   "The invocation of {ids} in {f} is rewritten where it already stood.",
   "{f} keeps its call order and changes what {ids} receives.",
   "Revises the call site for {ids} in {f} without relocating it.",
   "{ids} is invoked from the same place in {f} with adjusted inputs."],
 "other": [
   "Edits {ids} in {f} without introducing a new execution path.",
   "Adjusts {ids} in {f} inside the existing structure.",
   "Revises {ids} in {f}; the file's shape is otherwise intact.",
   "{f} rewrites {ids} in place.",
   "Changes to {ids} in {f} stay within the block that already held them.",
   "{ids} in {f} is reworked without extending its reach.",
   "{f} modifies {ids} and nothing that depends on it.",
   "The edit to {ids} in {f} is confined to where it already was."],
}



# --- strip non-source hunks -------------------------------------------------
SRC_EXT_REVIEW = {".py", ".js", ".mjs", ".ts", ".tsx", ".java"}


def strip_non_source(diff: str, files: list[str]) -> tuple[str, list[str]]:
    """Remove hunks for files the reviewer has no business reading.

    `CHANGES.txt` predicted the CLEAN label with 98% precision over 15% of the
    corpus: 159 clean records touched it and 2 defective ones did. Those are
    hbase and hadoop release-note commits, and `build_jit_dataset.META_NAMES`
    filters `changelog.md` but not `changes.txt`. A model can score 1 record in
    7 by reading the file list instead of the code, which is the shortcut this
    whole corpus exists to remove.

    Stripping rather than dropping: the corpus is 1034 records and losing 161 of
    them costs more than the leak does. `target_file` is already required to be
    source, so removing the other hunks changes nothing the target refers to -
    it only stops the prompt carrying a label in its filenames.
    """
    keep_files = [f for f in files if Path(f).suffix in SRC_EXT_REVIEW]
    if len(keep_files) == len(files):
        return diff, files
    out, emit = [], False
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.+?) b/(.+)$", line.rstrip("\n"))
            path = m.group(2) if m else ""
            emit = Path(path).suffix in SRC_EXT_REVIEW
        if emit:
            out.append(line)
    return "".join(out), keep_files


def git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True).stdout.decode("utf8", "replace")


def sides(diff: str) -> tuple[str, str]:
    rem = "\n".join(l[1:] for l in diff.splitlines()
                    if l.startswith("-") and not l.startswith("---"))
    add = "\n".join(l[1:] for l in diff.splitlines()
                    if l.startswith("+") and not l.startswith("+++"))
    return rem, add


def symbols(text: str, limit: int = 5) -> list[str]:
    out = []
    for m in _DEF.finditer(text):
        n = next((g for g in m.groups() if g), None)
        if n and n not in out and n not in _KEYWORDS:
            out.append(n)
    for n in _CALL.findall(text):
        if n not in out and n not in _KEYWORDS:
            out.append(n)
    return out[:limit]


def pick(key: str, salt: str, opts: list[str]) -> str:
    h = int(hashlib.sha1(f"{key}{salt}".encode()).hexdigest(), 16)
    return opts[h % len(opts)]


def clean_confidence(repo: Path, rev: str) -> float:
    """How much history has passed WITHOUT this commit being blamed.

    A constant would repeat the dead-field problem the defective side avoids.
    The label is "no fix has blamed it yet", and that claim is weaker for a
    commit made last week than for one that has survived a thousand commits of
    subsequent development. Counting the descendants is a real, cheap proxy for
    how much opportunity there has been to find a defect in it.
    """
    n = git(repo, "rev-list", "--count", f"{rev}..HEAD").strip()
    n = int(n) if n.isdigit() else 0
    # 0 -> 0.50, ~1k descendants -> ~0.75, saturating below the defective ceiling
    return round(min(0.50 + (min(n, 2000) / 2000) ** 0.5 * 0.28, 0.78), 2)


def confidence(lines: int, fan_out: int, has_issue: bool) -> float:
    """Label confidence from SZZ evidence strength, not self-assessment."""
    c = 0.45
    c += min(lines, 20) / 20 * 0.20          # more blamed lines = firmer link
    c += 0.15 / max(1, fan_out) ** 0.5       # a fix blaming 1 commit beats 31
    c += 0.10 if has_issue else 0.0          # a tracked issue is real evidence
    return round(min(c, 0.92), 2)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, default=ROOT / "data/jit_dataset.jsonl")
    ap.add_argument("--szz", default=str(ROOT / ".szz_work/out/bic_ma_*.json"))
    ap.add_argument("--out", type=Path, default=ROOT / "data/sft_repair.jsonl")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--show", type=int, default=0)
    args = ap.parse_args()

    import glob
    szz = json.load(open(sorted(glob.glob(args.szz))[-1]))
    # BIC -> the fix that repaired it, with the evidence behind the link
    fix_of: dict[str, dict] = {}
    for r in szz:
        for h in r.get("inducing_commit_hash") or []:
            prev = fix_of.get(h)
            if prev is None or len(r.get("inducing_commit_hash") or []) < prev["fan"]:
                fix_of[h] = {"fix": r["fix_commit_hash"],
                             "repo": r["repo_name"].replace("/", "__"),
                             "subject": "",
                             "fan": len(r.get("inducing_commit_hash") or [])}

    rows = [json.loads(l) for l in open(args.dataset)]
    out, skipped = [], Counter()
    for row in rows:
        # Do this FIRST: the clean-side symbols, the shape classifier and the
        # grounding check must all see the same diff the model will be shown.
        row["diff"], row["files"] = strip_non_source(row["diff"], row["files"])
        if not row["diff"].strip() or not row["files"]:
            skipped["nothing but non-source"] += 1; continue
        repo = REPOS / row["project"]
        if row["label"] == 1:
            link = fix_of.get(row["rev"])
            if not link:
                skipped["no fix link"] += 1; continue
            fdiff = git(repo, "show", "--format=", "--unified=3", link["fix"])
            fsubj = git(repo, "show", "-s", "--format=%s", link["fix"]).strip()
            files = [m.group(1) for m in
                     re.finditer(r"^\+\+\+ b/(.+)$", fdiff, re.M)]
            # The file must be one THIS commit touches. The old fallback took
            # files[0] from the repair, so a target could point at a file the
            # reviewed diff never mentions.
            tgt = next((f for f in files if f in row["files"]), "")
            rem, add = sides(fdiff)
            # GROUNDING. The repair says which symbols mattered; the reviewed
            # diff decides which of them the model can actually see. Only the
            # intersection may be named.
            #
            # Taking the repair's symbols alone put a symbol absent from the
            # reviewed diff into 94% of defective targets - typically the fix's
            # TEST names, attributed to a source file, e.g. "src/attr/_make.py
            # dereferences `TestCloudpickleCompat`". That is the `no-such-entity`
            # class, 25% of the wrong findings in the 1 Sep grade, and it also
            # contradicts this corpus's own system prompt ("Name no identifier
            # that is absent from the diff"). Training on it would teach the
            # failure rather than remove it.
            seen = set(symbols(row["diff"], limit=200))
            ids = [i for i in symbols(add + "\n" + rem, limit=200)
                   if i in seen and i in row["diff"]][:5]
            if not tgt or not ids:
                skipped["fix yields nothing"] += 1; continue
            shape = _shapes(rem, add)
            issue = bool(re.search(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b", fsubj))
            conf = confidence(row["n_lines"], link["fan"], issue)
            # Vary how many identifiers the sentence names, so the frame is not
            # the only thing separating one target from the next.
            n_ids = 1 + (int(row["rev"][:8], 16) % 3)
            idtxt = ", ".join(f"`{i}`" for i in ids[:n_ids])
            expl = pick(row["rev"], "d",
                        DEFECT_FRAMES[shape]).format(f=tgt, ids=idtxt)
            if not ids:
                skipped["no identifiers"] += 1; continue
            target = {"defect_found": True, "confidence": conf,
                      "target_file": tgt, "affected_identifiers": ids,
                      "explanation": expl, "repair_direction": shape}
        else:
            rem, add = sides(row["diff"])
            ids = symbols(add + "\n" + rem)
            tgt = next((f for f in row["files"]
                        if Path(f).suffix in {".py", ".js", ".ts", ".tsx",
                                              ".java", ".mjs"}), row["files"][0])
            if not ids:
                # No extractable symbol means the explanation would name nothing
                # and the schema's affected_identifiers would be empty. Drop it
                # rather than emit a target with no grounded content.
                skipped["no identifiers"] += 1; continue
            shape = clean_shape(add, rem, Path(tgt).suffix)
            n_ids = 1 + (int(row["rev"][:8], 16) % 3)
            idtxt = ", ".join(f"`{i}`" for i in ids[:n_ids]) or "the edited code"
            expl = pick(row["rev"], "c", CLEAN_FRAMES[shape]).format(f=tgt, ids=idtxt)
            target = {"defect_found": False,
                      "confidence": clean_confidence(repo, row["rev"]),
                      "target_file": tgt, "affected_identifiers": ids,
                      "explanation": expl, "repair_direction": None}
        out.append({**row, "target": target})

    print(f"{len(out)} targets  (skipped: {dict(skipped)})")
    d = [o for o in out if o["target"]["defect_found"]]
    c = [o for o in out if not o["target"]["defect_found"]]
    print(f"  {len(d)} defective / {len(c)} clean "
          f"({100*len(d)//max(1,len(out))}% defective)")
    if d:
        cs = sorted(o["target"]["confidence"] for o in d)
        print(f"  confidence on defective: min {cs[0]}, median {cs[len(cs)//2]}, max {cs[-1]}")
        print(f"  repair shapes: {dict(Counter(o['target']['repair_direction'] for o in d).most_common(6))}")

    # the audit that caught v4's template collapse
    ex = [o["target"]["explanation"] for o in out]
    opens = [" ".join(e.split()[:4]) for e in ex]
    print(f"\n  distinct explanations {len(set(ex))}/{len(ex)}")
    print(f"  distinct 4-word openers {len(set(opens))}")
    top = Counter(" ".join(e.lower().split()[i:i+4]) for e in ex
                  for i in range(max(0, len(e.split())-3))).most_common(1)
    if top:
        print(f"  most repeated 4-gram: {top[0][1]}/{len(ex)} \"{top[0][0]}\"")

    if args.show:
        for o in out[:args.show]:
            print(f"\n  [{o['project']}] {o['subject'][:56]}")
            print("   ", json.dumps(o["target"], ensure_ascii=False)[:300])
    if args.audit:
        return
    with open(args.out, "w") as fh:
        for o in out:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
