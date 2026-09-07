"""SQL predicate narrowing, and the many shapes that must claim nothing.

From a real Go commit, reported as "line N: rewritten":

    - WHERE id = $1 AND status != 'CANCELLED'   -- anything but CANCELLED
    + WHERE id = $1 AND status  = 'CONFIRMED'   -- only CONFIRMED

PENDING and ATTENDED tickets stopped matching. A predicate is modelled as a set
that may be a COMPLEMENT, which is what makes that direction computable across
the `!=` -> `=` switch; comparing value lists cannot see it.
"""
from oracle_reviewer.static_claims import describe, sql_filter_changed

Q = lambda t: t.replace("~", "'")
def D(old, new):
    return ("--- a/x.go\n+++ b/x.go\n@@ -1,2 +1,2 @@\n"
            f"-{Q(old)}\n+{Q(new)}\n")
say = lambda d: (sql_filter_changed(d) or (0, None))[1]

# ------------------------------------------------------------------ direction
real = D("  `UPDATE t SET status = ~CANCELLED~ WHERE id = $1 AND status != ~CANCELLED~",
         "  `UPDATE t SET status = ~CANCELLED~ WHERE id = $1 AND status = ~CONFIRMED~")
got = say(real)
assert "narrower" in got and "anything except `CANCELLED`" in got, got
# The SET assignment must not be mistaken for the filter: it names `status`
# too, and claiming that column first hid the real condition behind it.
assert "now `CONFIRMED`" in got, got

assert "wider" in say(D("  WHERE s IN (~a~, ~b~)", "  WHERE s IN (~a~, ~b~, ~c~)"))
assert "narrower" in say(D("  WHERE s IN (~a~, ~b~, ~c~)", "  WHERE s IN (~a~, ~b~)"))
assert "wider" in say(D("  WHERE s = ~a~", "  WHERE s IN (~a~, ~b~)"))
assert "narrower" in say(D("  WHERE s IN (~a~, ~b~)", "  WHERE s = ~a~"))
assert "wider" in say(D("  WHERE s = ~a~", "  WHERE s != ~b~"))
assert "narrower" in say(D("  WHERE s NOT IN (~a~)", "  WHERE s NOT IN (~a~, ~b~)"))
assert "<>" not in str(say(D("  WHERE s <> ~a~", "  WHERE s = ~b~")))
assert "narrower" in say(D("  WHERE s <> ~a~", "  WHERE s = ~b~"))

# A whole condition arriving or leaving is a direction too.
assert "added" in say(D("  WHERE id = $1", "  WHERE id = $1 AND s = ~C~"))
assert "removed" in say(D("  WHERE id = $1 AND s = ~C~", "  WHERE id = $1"))

# ----------------------------------------------------------- claims nothing
# Crossing sets: values both added and removed, direction unreadable.
assert say(D("  WHERE s IN (~a~, ~b~)", "  WHERE s IN (~b~, ~c~)")) is None
# A replacement is not an addition. This said "a `kind` condition was added --
# fewer rows match", which is a guess wearing the clothes of a fact.
assert say(D("  WHERE s = ~a~", "  WHERE kind = ~b~")) is None
# Parameters carry no value in the diff, so no direction can be read.
assert say(D("  WHERE s = $1", "  WHERE s = $2")) is None
# Identical predicate, other text changed.
assert say(D("  WHERE s = ~a~ LIMIT 10", "  WHERE s = ~a~ LIMIT 20")) is None
# Not SQL at all.
assert say(D("  const s = ~a~", "  const s = ~b~")) is None
# `!=` -> `=` on the SAME value is disjoint, not a narrowing.
assert say(D("  WHERE s != ~a~", "  WHERE s = ~a~")) is None
assert sql_filter_changed("") is None

# ------------------------------------------------------------- in describe()
facts = describe(real)
assert facts and "narrower" in facts[0], facts[:2]
assert not any("rewritten" in f for f in facts), facts

print("ok")
