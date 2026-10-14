# Portability and provenance

This packet contains public repository source and synthetic fixture data only.

Captured `*.raw.log` files are path-sanitized copies of the internally retained raw stdout/stderr. Private checkout/environment prefixes were replaced by `<origin-worktree>`, `<grok-worktree>`, `<python-environment>`, or relative packet paths. No timestamps, assertions, result counts, warnings, or source values were changed. The source files themselves are byte-identical Git blobs and have independent SHA-256 manifests.

`commands.sh` is a portable equivalent of the originally executed commands. Supply clean worktrees at the two pinned commits and a prepared Python environment. It writes `*.rerun.log`, leaving the captured logs unchanged. `observe.py` now emits the repository-relative source path using `QUALIFICATION_SOURCE_ROOT`; observation logic is unchanged.

The explicitly loaded guard blocks native cua imports, subprocess.Popen/os.system, and socket connects. The pytest guard also checks that cua/cua._native were never imported. This is fixture evidence, not a sandbox security audit. The pytest assertion-rewrite warning arises because guards.py is imported before pytest registers it as a plugin; it appears in both captured runs.

No dependency installs are part of replay. `environment.json` records the existing environment used. The native cua SDK is intentionally refused, and normal repository conftest/native fixtures are not loaded. Full suite, hosted CI, Swift, Rust, macOS, live Lume, and real guest testing were not performed.
