# Sandbox canonical held-key names — 2026-10-12

Canonical task: https://github.com/kvnloo/cua/issues/135. Owner dot/ayo, separately claimed before coding. Pinned main/base: `a329fcf435191655a8dc8271c0df9ea824c2b564`. Exact code candidate: `1ec915074dcc62a65faa109a359a6e361710d6d2`. Evidence publication adds only this packet; the tracker records its full final SHA separately.

EnvTransport promised KeySpec name resolution, but its 59-entry suffix allowlist omitted 85 of the protocol's 144 valid names. Genuine public Sandbox Keyboard.key_down/key_up rejected KEY_A and KEY_NUMPAD_ENTER before the native client's keyboard_json call. Native KeySpec parsing uses the proto enum vocabulary. Requirement evidence is that existing explicit adapter invariant and canonical enum, not a fabricated live user report. Plain Python one-character inputs intentionally retain character semantics even where native KeySpec chooses a named letter.

The correction changes only EnvTransport: complete the explicit allowlist with protocol-grouped physical, digit, punctuation, numpad, media/volume/brightness and browser/launch names; give single-character input precedence; clarify the parity comment. No runtime proto parsing, dependency, blanket KEY_* passthrough, protocol or native-driver change. KEY_UNSPECIFIED and unknown names remain refused. Existing aliases remain intact; no invented left_control alias. Original plain a/A, digit, punctuation and é controls still send character JSON.

| Execution | Result |
| --- | --- |
| First public real-package RED | 4 FAIL / 24 PASS / 24 deselected |
| Initial owning suite with public tests only | 4 FAIL / 48 PASS |
| Final owning regression overlay on untouched base | 89 FAIL / 107 PASS |
| Fixed owning suite, identical final tests | 196 PASS |
| Adjacent forwarding and agentless suites | 7 PASS |
| Ruff 0.17.0 lint and format checks | PASS |
| Independent xhigh owning / adjacent reruns | 196 PASS / 7 PASS |

A vocabulary-test preparation command initially used the wrong working directory and failed before editing files; it is not test evidence. The initial 4 FAIL / 48 PASS owning run therefore still contained only the public regression overlay. After correcting that file path, the identical final overlay produced the recorded 89 FAIL / 107 PASS baseline.

The 89 baseline failures comprise 85 canonical helper cases plus four public down/up cases. The 107 passing tests contain old cases, remaining canonical names and public controls. All 144 expected helper names come from the explicit proto enum, exclude its sentinel, and were checked against actual source; the complete allowlist has no missing/extra valid names. The 28 public cases run real Sandbox, Keyboard and EnvTransport through the existing env_factory and FakeEnv recording-client seam. There is no fake Sandbox, extracted helper, production test switch or import stub. Unknown-key controls require ValueError with exact message and zero keyboard_json dispatch.

This is Python adapter composition with a recording native-client boundary, not native RPC parsing, physical input, desktop acceptance or hosted CI. Parent independent source critic confirms X11 maps relevant enums to keysyms and emits Down/Up, subject to display/target/keymap. macOS, Windows and Linux Wayland use ToolBackend, which explicitly refuses separate Down/Up. This patch does not remove that limitation or certify physical US-layout behavior. Source review and executed Python behavior remain separate.

Existing Python3.12.14 environment and Ruff0.17.0 were reused; no install, sync, native build, OS dependency, credential operation, cleanup or desktop execution. Versions and 12 base/candidate source hashes are in environment-source-census.json. Independent xhigh exact-code critic receipt and logs accompany publication. In logs, machine roots, volatile addresses and trailing pytest-output whitespace are sanitized without changing outcomes. commands.txt intentionally retains absolute execution paths for precise reproduction.

Pinned original attribution is ddupont / Dillon DuPont (GitHub ddupont808), maintained adapter commit `9166817485ae53f3966935c13878a8196d79a399`, upstream #4397. Official GitHub GraphQL blame confirms the relevant original file. Local shallow blame produced a boundary author and was excluded from attribution. Existing source history is retained; no external patch was cherry-picked or material contribution replaced. New commits identify OpenAI Codex; no human coauthor, DCO/CLA/signoff or maintainer acceptance is manufactured.

Current AGENTS/CONTRIBUTING, selected-item skill, component pyproject/TESTING, canonical factory AGENTS/control-plane/HITL/registry and #74/#14/#77 were read. CUA remains tracked at kvnloo/cua. Bounded searches found no competing current EnvTransport key vocabulary PR. The three qualified held-key-related branches were fetched read-only and their actual paths inspected: deprecated agent forwarding and docs changes, with no env.py diff. #4536/#4858 remain separate agent/native backend work. No shared dashboard or other worktree was changed.

Publication is fork-only on dot/cua/held-key-parity-20261012. Final main/ownership and remote-absence checks precede a normal push; the remote full SHA is verified and an append-only done result releases the claim on #135. Upstream publication remains with Hermes. No unrelated permission holds or canceled uploads are touched.

Final observed upstream main still equals the pinned base `a329fcf435191655a8dc8271c0df9ea824c2b564`; no main drift was observed. The pre-push issue readback retains dot/ayo ownership and no comments; the requested remote branch is absent. Exact tested executable source is unchanged after the code commit.
