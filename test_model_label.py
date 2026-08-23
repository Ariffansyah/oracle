"""What the TUI header claims about the model, and when it warns.

    python test_model_label.py
"""

from pathlib import Path

from ui.tui_app import model_label, served_note

# A served model is identified by host too: two boxes can both serve a model
# called "oracle-merged" and mean different weights.
assert model_label("ollama", Path("artifacts/oracle-merged"), "oracle-merged",
                   "http://localhost:8111") == "ollama:oracle-merged @ localhost:8111"
assert model_label("transformers", Path("artifacts/oracle-merged"),
                   "ignored") == "transformers:oracle-merged"

# Ollama reports "name:tag"; the config names it without one.
assert served_note("oracle-merged", ["oracle-merged"]) == "  ✓"
assert served_note("qwen2.5-review", ["qwen2.5-review:latest"]) == "  ✓"

# The mismatch this exists to catch: header names one model, server has another.
assert served_note("oracle-merged", ["qwen2.5-review:latest"]) == "  (server has qwen2.5-review:latest)"
assert served_note("oracle-merged", []) == "  (no model served)"

print("ok")
