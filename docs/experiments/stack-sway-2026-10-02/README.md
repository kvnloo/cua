# Headless multi-seat sway session for CUA experiments (2026-10-02)

Fork-only lab packet (kvnloo/hermes-agent#319 sample-collection track, kvnloo/cua#36 / #94 context).
It adds an **environment** for experiments, not a new integration, protocol or Driver service. Nothing
here changes Hermes or cua-driver behaviour.

What it shows:

- A user-local headless sway 1.12 kit, installed without root.
- A session script that runs a payload inside a private compositor.
- Proof that the session cannot reach the host Hyprland desktop.
- Proof that two seats get independent cursors and keyboard focus.
- What cua-driver at upstream main can and cannot do inside the session.

No latency numbers are reported, so nothing here was timed in the quiet lane and there is no PREREG.
The `ms` fields inside receipts are incidental and are not measurements.

## Evidence

| Row | Class | Result | Receipts |
|---|---|---|---|
| Kit: 5 packages, sha256 matches the sync db | REAL | PASS | `provenance.json` |
| Isolation canary | REAL | PASS 3/3 (1 earlier run failed, see attempts) | `raw/canary/run{1,2,3}` |
| Canary sabotage with decoys | REAL | PASS 3/3 | `raw/canary/run*/control.json`, `decoy/accepts.jsonl` |
| Multi-seat: independent cursors, focus and keys | REAL | PASS 5/5, 16/16 checks each | `raw/multiseat/rep{1..5}` |
| Driver, native Wayland (opt-in) | REAL | PARTIAL | `raw/driver/native-run1`, `gtk-native-*`, `gtkinput-native-*`, `gtk-seat-attribution`, `gtk-geometry` |
| Driver, X11 apps via Xwayland | REAL | PARTIAL | `raw/driver/smoke/atspi-xwayland`, `gtkinput-xwayland-*` |
| Driver seat binding | SOURCE + REAL | NO | `raw/driver/native-run1/probe-T.jsonl` |
| Driver multicursor | SOURCE + REAL | PARTIAL: overlay yes, input no | `raw/driver/native-run1/screen-*.png` |
| jev-use browser smoke | BLOCKED | BLOCKED by `hostless` | `raw/driver/smoke-browser-*.log` |

`summary.json` states each claim precisely. `provenance.json` has every identity: source, binary,
packages, tools and script hashes.

## Session (`session/cua-sway-session.sh`)

```
hostless cua-sway-session.sh <cmd> [args...]
  CUA_SWAY_SEATS=n            seat0..seat<n-1>, 1..8 (seat0 = fallback seat)
  CUA_SWAY_OUTPUTS=WxH[,WxH]  headless outputs, laid out left to right
  CUA_SESSION_ATSPI=1         private AT-SPI bus + registry
  CUA_SWAY_TIMEOUT=secs       hard stop (default 1800)
  CUA_SESSION_EXTRA_ENV="K=V ..."
```

The payload runs as a child of the private sway. It gets `WAYLAND_DISPLAY`, `SWAYSOCK` and `DISPLAY`
from sway itself, and its stdout, stderr and exit code reach the caller. The session waits until sway
is ready: the requested number of outputs is active, the requested number of seats exists and
Xwayland answers.

The script refuses to start in these cases:

- outside `hostless` (`CUA_HOSTLESS` is not 1);
- when `WAYLAND_DISPLAY`, `WAYLAND_SOCKET`, `SWAYSOCK`, `I3SOCK` or any `HYPRLAND_*` variable is set;
- when the private Xwayland display number collides with a display the host uses.

Isolation layers, from the outside in:

1. **`hostless`.** tmpfs over the host X11/ICE directories and `/run/user/<uid>`, and the desktop
   environment variables are dropped.
2. **`env -i`.** The environment is scrubbed and private `HOME`, `TMPDIR` and `XDG_*` directories
   are set under the lane temp directory.
3. **Nested bwrap.** A private `/tmp` and a private PID namespace. Teardown kills exactly the session
   tree, and the measured count of leftover processes is 0.
4. **`landlock-scope`** (Landlock ABI >= 6). Processes in the session cannot `connect()` to abstract
   unix sockets bound outside it, and cannot signal processes outside it.
5. **Lock seeding.** Before starting, the script writes `/tmp/.X<n>-lock` into the private `/tmp`
   for every X display number the host uses, whether through a lock file, a path socket or an
   abstract socket. The lock is owned by the namespace's PID 1, so wlroots never picks a host
   display number.

Layers 4 and 5 exist because of real findings in this run:

- **`hostless` shares the network namespace.** Host abstract sockets stay connectable from plain
  `hostless`, for example the host's `@/tmp/.X11-unix/X0` and `X2`. This was demonstrated with a
  decoy socket in the control phase, never with the real host.
- **The first session design collided with the host display.** The host Hyprland's Xwayland serves
  `:1` through path sockets only (`X1` and `X1_`, no abstract socket). The first design let the
  private Xwayland claim `:1` and bind `@/tmp/.X11-unix/X1`. libxcb tries the abstract name first,
  so a host X11 client could have been routed into the private session. The canary flagged the
  session (`raw/attempts/canary-run1-fail-x11-display-shadowing`). The fix gives `:3`, and the
  canary now asserts that the abstract listeners the session adds are exactly its own display.

## Multi-seat method

`tools/seatctl.c` (about 150 lines) creates a `zwlr_virtual_pointer_v1` and a
`zwp_virtual_keyboard_v1` against one named `wl_seat`. Sway attaches each device to the seat passed
at creation (`suggested_seat` / `keyboard->seat` in sway 1.12 `input-manager.c`), with no `attach`
rule involved.

`tools/seatprobe.c` is the oracle. It is an `xdg_toplevel` that binds every `wl_seat` and logs per
seat: pointer enter, motion and button with surface-local coordinates, and keyboard enter and keys,
decoded with that seat's own keymap.

`scripts/multiseat-proof.sh` runs five phases:

- **A.** Concurrent move and click: seat0 to the left window, seat1 to the right.
- **B.** Concurrent typing of `left` and `right`.
- **C.** seat0 moves alone.
- **D.** The seats swap windows, concurrently.
- **E.** Concurrent typing of `zero` and `one`.

`scripts/verify_multiseat.py` grades the run from raw receipts only: the probe logs, `get_seats`
and `get_tree`.

Kit gotchas:

- `seatctl` waits about 250 ms after creating a device. Clients bind `wl_pointer` / `wl_keyboard`
  only after the capability event, and they miss events sent before that bind.
- Running `swaymsg seat ...` after virtual devices exist moves them to the fallback seat, because
  sway re-applies its attachment rules.

## Driver findings

All Driver runs used cua-driver 0.32.0 (sha256 `8b037961…`, git 229b65b28). Its `libs/cua-driver`
tree is identical to upstream main 352507b6c. Default safety settings were used throughout.

**Native Wayland** (requires `CUA_DRIVER_RS_ENABLE_WAYLAND=1`).

What works:

- `health_report` sees every wlroots global.
- `list_windows` and `get_window_state` work: screencopy capture plus the AT-SPI tree, 15/15 named
  controls.
- `click` and `type_text` with `delivery_mode:"foreground"` are delivered. seatprobe saw enter,
  press, release and the keys `c`, `u`, `a`.

What doesn't:

- Default background delivery is refused with a structured error. Sway has no libei or
  RemoteDesktop portal.
- The GTK3 task fixture passed 0/3. The Driver's native element `frame` equals the true window-local
  position × original_width/screenshot_width (1.326), so clicks overshoot their target. Two elements
  confirm the ratio.
- Cross-check: GTK3 does accept held virtual-pointer clicks at the true position, on both seat0 and
  seat1 (counter 0 → 1 → 2).
- The jev-use native AT-SPI smoke fails because native window titles carry a `" [app_id]"` suffix
  (wayland/mod.rs:682), and the smoke matches titles exactly.
- Windows are found with or without `SWAYSOCK`, so the missing `SWAYSOCK` is not the cause.

**X11 apps via Xwayland.**

- The GTK3 AT-SPI smoke passes: 18 elements, 6/6 expected controls.
- Foreground XTEST input on the GTK3 task fixture fully passed 1/3. The first click was lost in 2 of
  3 runs. The later click, typing and save landed 3/3.
- In background mode, buttons go through an AT-SPI action, so that is not real input. Pointer and
  keyboard input to the text entry fail, because the XI2 master-pointer route needs a uinput slave
  device.

**Seat binding: NO.** `wayland/primary_seat.rs` picks the last-advertised ordinary seat, and callers
cannot choose a seat. On 2-seat sway every Driver event arrived on seat1. The Xwayland path injects
inside the X server and never touches sway seats.

**Multicursor: PARTIAL.**

- One Driver process drew three per-session agent cursors at once through the layer-shell overlay,
  with session badges (`raw/driver/native-run1/screen-after-move-cursor-2s.png`).
- Input is not per cursor: all sessions share the one implicit seat. On Wayland,
  `parallel_mouse_drag` needs the cua-compositor inject socket, which stock sway doesn't provide.
- From source: with `WAYLAND_DISPLAY` set but no opt-in, the Driver runs no overlay at all.
- Session B was refused until it took its own snapshot, so per-session capture ownership holds.

**Browser smoke: BLOCKED.** `browser_prepare` refused with "no root-owned, non-writable system
Chromium executable". It did so in both sway arms and in an Xvfb control under `hostless`. The cause
is `hostless`'s user namespace: it maps only the invoking uid, so root-owned files appear owned by
`nobody`. The Driver is right to refuse, and nothing was bypassed.

## Attempts and failures (all retained under `raw/attempts/`)

- **`multiseat-run1-fail-click-race`.** A press was lost to the race with a freshly created device.
  Fixed by the `seatctl` settle delay.
- **`multiseat-run{2,3,4}-design-overlap`.** In phase D, seat0's target was the point where seat1
  was resting, so the cross-seat check could not tell them apart. The target was moved to
  (1100,200).
- **One exploratory run before the verifier existed.** Its raw output was not retained. Its typing
  phase lost leading keys to the same race.
- **`multiseat-reps-pre-display-fix`.** Five reps, all passing, run with the session script before
  the display fix. They are superseded by `raw/multiseat`.
- **`canary-run1-fail-x11-display-shadowing`.** The display collision described above.
- **`driver-native-run1-background-default`** and **`driver-native-run1b-no-sessionB-snapshot`.**
  Background refusal, and session B's refusal without its own snapshot. Both are kept as evidence.
- **`gtkinput-native-foreground-client-missing-frame-fallback`.** My client lacked a fallback to
  `frame`. **`gtk-seat-attribution-at-driver-point-90-107`.** A non-independent click at the
  Driver's point, which missed.

Verifier changes during the work:

- The expected virtual-keyboard identifier was corrected to `0:0:wlr_virtual_keyboard_v1`.
- The cross-seat rule became: a wrong-seat event is allowed only as that seat's own resting cursor,
  never as a click, and never at the other seat's target.

## Reproduce

```
hostless <KIT-builder> tools/build-tools.sh <KIT> <wlroots-0.20.2-src>
CUA_SWAY_SEATS=2 CUA_SWAY_OUTPUTS=1280x720 hostless session/cua-sway-session.sh scripts/multiseat-proof.sh <out>
python3 scripts/verify_multiseat.py <out>
hostless scripts/canary-run.sh <out> <host-hypr-sig> <host-hyprland-pid>
python3 verify_artifacts.py    # this packet
```

Paths in the copied scripts are placeholders (`<KIT>`, `<TMP>`, `<NODE22>`, `<HOME>`). The local
originals are identified by sha256 in `provenance.json`.
