"""Seeded per-trial layout for the AR GTK3 fixture (pure; no GTK import).

The same (task, seed, variant) always yields the same layout, so the two arms of
an AB/BA pair see identical labels, ids, order, spacing and geometry, while no
fixed coordinate, index or label can be replayed across seeds.
"""

from __future__ import annotations

import random

VARIANTS = ("normal", "delayed", "focus_steal", "disabled", "absent")
TASKS = ("checkbox", "text", "user")

# Benign, unambiguous labels. The target and the distractors are drawn from the
# same pool so a label never identifies the target by itself.
CHECK_LABELS = (
    "I agree", "Remember me", "Enable sync", "Show previews", "Word wrap", "Auto-save",
    "Line numbers", "Dark mode", "Compact layout", "Show status bar", "Send reports",
    "Check spelling",
)
BUTTON_LABELS = ("Refresh", "Undo", "Redo", "Zoom in", "Zoom out", "Duplicate", "Rename", "Help")
FIELD_LABELS = ("Note", "Comment", "Memo", "Remark", "Caption", "Summary")
SAVE_LABELS = ("Save note", "Save comment", "Store memo", "Keep remark", "Apply caption", "Save summary")
N_DISTRACTOR_CHECKS = 3
N_DISTRACTOR_BUTTONS = 2


def layout_for(task: str, seed: int, variant: str) -> dict:
    """The deterministic per-seed layout. Pure: unit-tested without GTK."""
    rng = random.Random(f"ar-gtk3:{task}:{seed}")
    checks = rng.sample(CHECK_LABELS, N_DISTRACTOR_CHECKS + 1)
    buttons = rng.sample(BUTTON_LABELS, N_DISTRACTOR_BUTTONS)
    field_i = rng.randrange(len(FIELD_LABELS))
    target, distractor_checks = checks[0], checks[1:]
    # Order of the controls in the box (the target's position is random).
    items = [("check", label) for label in distractor_checks] + [("button", label) for label in buttons]
    if task == "checkbox":
        items.insert(rng.randrange(len(items) + 1), ("target", target))
    elif task == "text":
        items.insert(rng.randrange(len(items) + 1), ("note", FIELD_LABELS[field_i]))
    layout = {
        "task": task,
        "seed": seed,
        "variant": variant,
        "title": f"AR Fixture {rng.randrange(16**6):06x}",
        "target_label": target if task == "checkbox" else None,
        "note_label": FIELD_LABELS[field_i] if task == "text" else None,
        "save_label": SAVE_LABELS[field_i] if task == "text" else None,
        "initial_checked": rng.random() < 0.5,
        "items": items,
        "widget_ids": {label: f"w{rng.randrange(16**8):08x}" for _, label in items},
        "spacing": rng.randrange(4, 24),
        "border": rng.randrange(8, 40),
        "window_size": [rng.randrange(380, 560), rng.randrange(300, 460)],
        "window_pos": [rng.randrange(40, 900), rng.randrange(40, 500)],
        "delay_ms": rng.randrange(200, 501),
        "steal_map_ms": rng.randrange(30, 201),
    }
    if task == "checkbox" and variant == "absent":
        # The target label is removed; a fresh distractor takes its slot so the
        # tree keeps its size. The caller is still asked for ``target_label``.
        spare = [label for label in CHECK_LABELS if label not in checks]
        replacement = rng.choice(spare)
        layout["items"] = [("check", replacement) if kind == "target" else (kind, label) for kind, label in items]
        layout["widget_ids"][replacement] = layout["widget_ids"].pop(target)
    return layout
