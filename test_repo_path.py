"""Paths as people actually type them.

    python test_repo_path.py

No shell sits between the text box and `git -C`, so none of the expansions a
terminal would do have happened. Each case below is a normal way to write a
path that failed against a bare subprocess call.
"""

import os

from oracle_reviewer.core import repo_path

HOME = os.path.expanduser("~")

assert repo_path("~/code/thing") == f"{HOME}/code/thing"
assert repo_path("~") == HOME
assert repo_path("$HOME/code/thing") == f"{HOME}/code/thing"
assert repo_path("'/code/thing'") == "/code/thing"       # copied from a shell
assert repo_path('"/code/thing"') == "/code/thing"
assert repo_path("  /code/thing  ") == "/code/thing"     # pasted
assert repo_path("/code/thing/") == "/code/thing"        # trailing slash
assert repo_path("' /code/thing '") == "/code/thing"     # quotes AND spaces

# Empty means "here", which is the field's default.
assert repo_path("") == "."
assert repo_path("   ") == "."
assert repo_path(None) == "."
assert repo_path(".") == "."

# A lone quote is part of the name, not a wrapper -- only a MATCHED pair is
# stripped, so a directory that really is called "it's" survives.
assert repo_path("/code/it's") == "/code/it's"
assert repo_path("'/code/thing") == "'/code/thing"

# An undefined variable is left alone rather than silently becoming a path
# under the wrong root.
assert repo_path("$NOT_SET_ANYWHERE/x") == "$NOT_SET_ANYWHERE/x"

print("ok")
