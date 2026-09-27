# Pinned commit build

Commit `c5ee191c02b11448ffefcc38b78b064a87d8ef23` is in this repository. It is an ancestor of `test/rfc-fast-path-one-candidate-20260925`. Its message is `chore(cua-driver): advance published installer version to 0.29.1 [skip ci]`.

Command, from a detached worktree of that commit:

```
cargo build -p cua-driver --bin cua-driver
```

Result: `Finished dev profile [unoptimized + debuginfo] target(s) in 2m 20s`.

The debug binary printed `cua-driver 0.29.1`. `cua-driver status` exited 1 and printed `Cua Driver daemon is not running`. `cua-driver doctor` printed `binary: cua-driver 0.29.1 (x86_64-linux)`, `display server: Wayland+XWayland`, `X11 connection: no top-level windows returned`, and `AT-SPI: org.a11y.Bus reachable via session bus`.

This binary was not installed over the release at `~/.cua-driver`. The installed release remains `cua-driver 0.28.2`. No model session was started. No desktop trial was run.
