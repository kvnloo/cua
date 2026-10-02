"""Per-trial bwrap sandbox for the Driver under test (owner default D8).

The Driver sees the whole filesystem read-only, except:
  * its own fresh per-trial home (HOME and TMPDIR; XDG dirs default under HOME),
  * the private session's runtime dir (D-Bus / AT-SPI sockets live there),
  * /dev (shared memory for X and Chromium).
The evaluator's private root (fixture state journals, nonces, trial ledgers) is
replaced by an empty read-only tmpfs, so the Driver can neither read the oracle
nor forge it. The per-trial nonce reaches the fixture app on an inherited pipe;
the Driver is spawned without it (close_fds). No pid/net/time namespace is
unshared: CLOCK_MONOTONIC and the session's sockets stay shared, so the harness,
the app and the Driver stamp the same clock.

Pure argv construction; unit-tested without bwrap.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

BWRAP = "/usr/bin/bwrap"


def driver_argv(driver: str | Path, *, trial_home: str | Path, runtime_dir: str | Path | None,
                private_roots: Sequence[str | Path], driver_args: Sequence[str] = ("mcp",)) -> list[str]:
    home = str(trial_home)
    argv = [BWRAP, "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev", "--bind", home, home]
    if runtime_dir:
        argv += ["--bind", str(runtime_dir), str(runtime_dir)]
    for root in private_roots:
        argv += ["--tmpfs", str(root), "--remount-ro", str(root)]
    argv += ["--die-with-parent", "--", str(driver), *driver_args]
    return argv


def driver_env(base: Mapping[str, str], trial_home: str | Path) -> dict[str, str]:
    """The jev-use Driver environment with HOME/TMPDIR moved into the trial home."""
    env = dict(base)
    env["HOME"] = str(trial_home)
    env["TMPDIR"] = str(Path(trial_home) / "tmp")
    for key in ("XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
        env.pop(key, None)
    return env


def prepare_home(trial_home: str | Path) -> Path:
    home = Path(trial_home)
    (home / "tmp").mkdir(parents=True, exist_ok=False)
    home.chmod(0o700)
    return home
