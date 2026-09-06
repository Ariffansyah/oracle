"""Suppress findings that execution proves impossible.

If running pre and post yields byte-identical stdout, exit code and stderr, then
"this commit breaks something" is not merely unlikely — it is refuted. Unlike
the vocabulary-overlap grounding filter, this is a measurement, so the finding
can be dropped rather than down-weighted.

The cost is stated, not hidden: a defect whose effect does not reach the output
is invisible here, and c-array-bound is exactly that case (reading a[5] returned
0, so the sum is still 15). The filter will suppress its correct finding.
"""
import json, sys

# The facts file must match the bench root being filtered. It was hardcoded to
# bench/basic's, so every id lookup missed on any other root: `v` was None, the
# filter passed all rows through and still printed an empty suppression list --
# a silent no-op that looked like "nothing needed suppressing".
src, dst = sys.argv[1], sys.argv[2]
facts_path = sys.argv[3] if len(sys.argv) > 3 else "data/exec_diff_basic.json"
facts = json.load(open(facts_path))
if not (set(facts) & {json.loads(l)["id"] for l in open(src)}):
    sys.exit(f"!! {facts_path} shares no case id with {src} -- wrong facts file")
rows, dropped, lost = [], [], []
for line in open(src):
    r = json.loads(line)
    v = facts.get(r["id"])
    p = r.get("predicted") or {}
    if v and not v["differs"] and (p.get("findings") or []):
        (lost if v["buggy"] else dropped).append(r["id"])
        p["findings"] = []
        if isinstance(p.get("effect"), dict):
            p["effect"]["direction"] = "unchanged"
        r["predicted"] = p
    rows.append(r)
with open(dst, "w") as fh:
    for r in rows:
        fh.write(json.dumps(r) + "\n")
print(f"  suppressed on CLEAN cases (true false-alarms killed): {dropped}")
print(f"  suppressed on BUGGY cases (real findings lost)      : {lost}")
