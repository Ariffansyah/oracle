"""The `oracle` command: `main.py` with the serving setup already handled.

    oracle --repo /path/to/repo        review a repo in the TUI
    oracle analyze --diff-file x.patch any other main.py subcommand still works

Three things this does that `python main.py tui` does not:

* **Defaults the subcommand to `tui`**, so `oracle --repo X` works. Anything
  that starts with a known subcommand is passed through untouched.
* **Pins the serving defaults** before `config` is imported, which is the only
  moment they can be set - `config._env` reads the environment at import time.
  Every default here is overridable; if the variable is already set, it wins.
* **Opens the tunnel** if nothing is answering on the port, because a laptop
  reboot drops it and the failure otherwise looks like a broken model.
"""

from __future__ import annotations

import os
import subprocess
import sys
from urllib.error import URLError
from urllib.request import urlopen

# ORACLE_INFERENCE_SAMPLES defaults to 3 in config.py, and through the served
# backend those three samples come back byte-identical: serve.py ignores the
# request's temperature, so consensus costs 3x the wait for one answer. 1 is
# the honest default for interactive use.
DEFAULTS = {
    "ORACLE_BACKEND": "ollama",
    "ORACLE_OLLAMA_HOST": "http://localhost:8111",
    "ORACLE_INFERENCE_SAMPLES": "1",
}
BOX = os.environ.get("ORACLE_BOX", "oracle-gpu")


def _answering(host: str, timeout: float = 3.0) -> bool:
    try:
        with urlopen(f"{host.rstrip('/')}/api/tags", timeout=timeout) as r:
            return r.status == 200
    except (URLError, OSError, ValueError):
        return False


def _port_of(host: str) -> str:
    return host.rsplit(":", 1)[-1].strip("/") or "8111"


def ensure_server(host: str) -> bool:
    """Make sure something answers at `host`. Returns False if it cannot."""
    if _answering(host):
        return True
    if "localhost" not in host and "127.0.0.1" not in host:
        return False  # a remote host is the caller's business, not ours
    port = _port_of(host)
    print(f"oracle: nothing on {host}, opening a tunnel to {BOX} …",
          file=sys.stderr)
    # -f -N: background, no remote command. ExitOnForwardFailure makes a busy
    # port an error instead of a tunnel that silently forwards nowhere.
    subprocess.run(
        ["setsid", "ssh", "-f", "-N", "-L", f"{port}:localhost:{port}",
         "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30",
         "-o", "ServerAliveCountMax=1000", BOX],
        capture_output=True)
    return _answering(host)


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    for k, v in DEFAULTS.items():
        os.environ.setdefault(k, v)

    import main  # after the environment is set: config reads it on import

    subcommands = {c for a in main.build_parser()._actions
                   if a.dest == "cmd" for c in (a.choices or ())}
    if not argv or (argv[0] not in subcommands
                    and argv[0] not in ("-h", "--help")):
        argv = ["tui", *argv]

    host = os.environ["ORACLE_OLLAMA_HOST"]
    if argv[0] in ("tui", "analyze") and os.environ["ORACLE_BACKEND"] == "ollama":
        if not ensure_server(host):
            port = _port_of(host)
            print(
                f"oracle: no model answering on {host}.\n"
                f"  Start one on the box, then retry:\n"
                f"    ssh {BOX} bash -s <<'EOF'\n"
                f"    cd ~/oracle && setsid nohup .venv/bin/python -m llm_explainer.serve \\\n"
                f"        --model artifacts/oracle-merged --port {port} \\\n"
                f"        > ~/oracle/serve.log 2>&1 < /dev/null &\n"
                f"    EOF\n"
                f"  If the port is held by something stale: ss -tlnp | grep {port}",
                file=sys.stderr)
            return 1
    return main.main(argv)


if __name__ == "__main__":
    sys.exit(run())
