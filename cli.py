"""The `oracle` command: `main.py` with the serving setup already handled.

    oracle                             choose a repo and its run command, review
    oracle --repo /path/to/repo        skip the picker, review that repo
    oracle serve                       start the model server and the tunnel
    oracle serve stop|status           stop it, or ask whether it is up
    oracle analyze --diff-file x.patch any other main.py subcommand still works

`oracle` with no subcommand opens the EXECUTION-GROUNDED reviewer
(`oracle_reviewer.tui`), which runs the project's command before and after a
change and only speaks about a difference it observed. The older three-pane
diff UI is still reachable as `oracle tui`.

Four things this does that `python -m oracle_reviewer.tui` does not:

* **Defaults to the reviewer**, so `oracle` and `oracle --repo X` both work.
  Anything starting with a known subcommand is passed through untouched.
* **Owns the server lifecycle** through `serve`, so starting the thing the UI
  talks to is not a separate script the user has to know about.
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
    # ConnectTimeout and a subprocess timeout, both: without them a box that is
    # merely ASLEEP (rather than refusing) leaves ssh waiting on a TCP handshake
    # that takes minutes to fail, and `oracle` looks hung at startup with one
    # line of output. BatchMode keeps it from stopping to ask for a passphrase
    # in a terminal the TUI is about to take over.
    try:
        subprocess.run(
            ["setsid", "ssh", "-f", "-N", "-L", f"{port}:localhost:{port}",
             "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
             "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30",
             "-o", "ServerAliveCountMax=1000", BOX],
            capture_output=True, timeout=20)
    except subprocess.TimeoutExpired:
        return False
    return _answering(host)


USAGE = """oracle — execution-grounded code review, locally served.

  oracle                        pick a repository and its run command, review
  oracle --repo PATH            skip the picker and review PATH
  oracle --repo PATH --run CMD  skip detection too, and use CMD

  oracle serve                  start the model server on the box + the tunnel
  oracle serve status           is the server up, is the tunnel up
  oracle serve stop             take both down

  oracle analyze --diff-file x.patch    review one diff, no UI
  oracle tui --repo PATH                the older three-pane diff UI
  oracle <subcommand> --help            build-sft, train-sft, ... (see main.py)

The reviewer runs your project's own command before and after each changed file
and speaks only about a difference it observed. That command is the setting
that matters most, which is why the picker shows it, says where it came from,
and lets you edit it before anything runs.
"""


def _no_server(host: str) -> None:
    """What to do when nothing answers. `oracle serve`, not a hand-rolled ssh.

    The instructions here used to spell out a `llm_explainer.serve` invocation
    with `--model artifacts/oracle-merged`, which is the checkpoint from a
    superseded output contract: it scores like the UNTRAINED base on BugsInPy.
    Anyone following the old message got a working server and a model that
    could not explain anything, which is the hardest kind of failure to see.
    """
    port = _port_of(host)
    print(f"oracle: no model answering on {host}.\n"
          f"  Start it:            oracle serve\n"
          f"  Check what is up:    oracle serve status\n"
          f"  If the port is held by something stale: ss -tlnp | grep {port}",
          file=sys.stderr)


def serve(args: list[str]) -> int:
    """`oracle serve [start|stop|status|tui]` -> serve.sh, which owns the box.

    Delegated rather than reimplemented: serve.sh already carries the hard-won
    details -- reusing a server that is already serving the right model, giving
    the tunnel its own connection so a control-master timeout cannot silently
    take the forward down, and not trusting a launch call to return.
    """
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.sh")
    if not os.path.exists(script):
        print(f"oracle: {script} is missing", file=sys.stderr)
        return 1
    return subprocess.run([script, *(args or ["start"])]).returncode


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    for k, v in DEFAULTS.items():
        os.environ.setdefault(k, v)

    if argv and argv[0] == "serve":
        return serve(argv[1:])
    if argv and argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0

    import main  # after the environment is set: config reads it on import

    subcommands = {c for a in main.build_parser()._actions
                   if a.dest == "cmd" for c in (a.choices or ())}
    # No subcommand means the execution-grounded reviewer, not main.py's older
    # `tui`. `oracle tui` still reaches the old three-pane UI on purpose.
    if not argv or (argv[0] not in subcommands
                    and argv[0] not in ("-h", "--help")):
        host = os.environ["ORACLE_OLLAMA_HOST"]
        if os.environ["ORACLE_BACKEND"] == "ollama" and not ensure_server(host):
            _no_server(host)
            return 1
        from oracle_reviewer.tui import main as reviewer
        sys.argv = ["oracle", *argv]
        return reviewer()

    host = os.environ["ORACLE_OLLAMA_HOST"]
    if argv[0] in ("tui", "analyze") and os.environ["ORACLE_BACKEND"] == "ollama":
        if not ensure_server(host):
            _no_server(host)
            return 1
    return main.main(argv)


if __name__ == "__main__":
    sys.exit(run())
