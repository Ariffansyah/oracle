"""Stage 1's number, and the caveat that must travel with it.

    python test_gate_line.py

The JIT gate predicts how likely a commit is to be bug-inducing from its shape,
with nothing run. On the pyalgo fixture it scores 0.136 for the commit that
INTRODUCES an off-by-one, 0.091 for the one that FIXES that same off-by-one, and
0.137 for a pure refactor — all MEDIUM. It cannot separate introducing a defect
from repairing one, which is what an `la`-dominated AUC looks like from the
inside, and it is the gap Stage 2 exists to close. So the number is never shown
bare.
"""

from oracle_reviewer.core import gate_line

g = {"score": 0.136, "threshold": 0.047, "band": "MEDIUM", "clean": True,
     "should_review": True, "top": ["lt", "sexp", "exp"]}
line = gate_line(g)
assert "13.6%" in line and "MEDIUM" in line
assert "flags at 4.7%" in line
# The three things that stop it being read as a per-file measurement:
assert "WHOLE commit" in line
assert "commit size" in line
assert "does not distinguish introducing a defect from fixing one" in line

# No prediction must say so, and say WHY when there is a reason. "Unavailable"
# with no reason is the silent failure this tool exists to avoid.
assert gate_line(None) == "Stage 1 (JIT): no prediction — gate unavailable"
assert gate_line({"error": "gate was not preloaded"}) == \
    "Stage 1 (JIT): no prediction — gate was not preloaded"
assert "ImportError" in gate_line({"error": "ImportError: no torch"})

# A score is never invented from a partial result.
assert "no prediction" in gate_line({})

# A number from the LEAKED gate must never be presented as a prediction.
# config.GATE_MODEL_PATH still defaults to artifacts/gate.joblib, which
# RESULTS.md (24 Aug) shows was trained on its own evaluation set -- the leak
# was worth 0.495 F1 and 0.21 AUC.
leaked = dict(g, clean=False)
line = gate_line(leaked)
assert "LEAKED" in line and "not reportable" in line
assert "MEDIUM" not in line          # no band, so it cannot be read as a verdict

# The clean one is shown normally.
assert "MEDIUM" in gate_line(dict(g, clean=True))

print("ok")
