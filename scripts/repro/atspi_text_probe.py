"""One GTK3 entry on this host. Records which AT-SPI events the change emits.

This is a trace for kvnloo/cua#20, not a capture-skipping policy. The probe
always observes. It does not drive Chrome, restart a process, or claim a
false-negative rate.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib, Gtk


def main() -> None:
    events: list[dict[str, str | None]] = []

    def on_event(event, *_args) -> None:
        name = role = None
        try:
            source = event.source
            if source is not None:
                name = source.get_name()
                role = source.get_role_name()
        except Exception:
            pass
        events.append({"type": event.type, "name": name, "role": role})

    Atspi.init()
    listener = Atspi.EventListener.new(on_event, None)
    kinds = (
        "object:text-changed",
        "object:text-caret-moved",
        "object:state-changed:focused",
        "object:children-changed",
    )
    registered = {kind: bool(listener.register(kind)) for kind in kinds}

    window = Gtk.Window(title="cua-atspi-probe")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    entry = Gtk.Entry()
    entry.set_text("before")
    extra = Gtk.Label(label="extra")
    box.pack_start(entry, False, False, 0)
    window.add(box)
    window.show_all()
    entry.grab_focus()

    def mutate() -> bool:
        entry.set_text("after-token")
        box.pack_start(extra, False, False, 0)
        extra.show()
        return False

    def remove_child() -> bool:
        box.remove(extra)
        return False

    def finish() -> bool:
        window.destroy()
        Gtk.main_quit()
        return False

    GLib.timeout_add(400, mutate)
    GLib.timeout_add(800, remove_child)
    GLib.timeout_add(1400, finish)
    Gtk.main()

    types = sorted({event["type"] for event in events if event["type"]})
    report = {
        "host": platform.platform(),
        "gtk": "3.0",
        "registered": registered,
        "event_count": len(events),
        "event_types": types,
        "events": events,
        "not_tested": [
            "process restart",
            "web-content navigation",
            "false-negative rate",
            "event latency distribution",
        ],
        "classification": {
            "gtk3-entry-text-change": "invalidation hint only; text-changed events were observed for this one widget, which is not permission to skip a later capture",
            "focus": "state-changed:focused observed on the probe entry",
            "structure": "children-changed observed when the probe window and label appeared",
            "always-observe": "event absence was not measured, so absence stays an always-observe scope",
        },
    }
    destination = Path(__file__).with_name("atspi-census-20260925.json")
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {destination} events={len(events)} types={len(types)}")


if __name__ == "__main__":
    main()
