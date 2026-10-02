"""Target-owned oracles and control verdicts for the AR fixtures (pure; evaluator side).

Nothing here reads Driver output to decide success. The GTK verdicts read the
app's own journal (written only by its task handler, outside the Driver sandbox);
the browser verdict reads the fixture server's ``/state`` and its journal of page
events and POST receipts. Driver results are inputs only where a control is about
the Driver's *answer* (a stale token must be refused; an impossible action must
not be claimed).

All timestamps are host ``CLOCK_MONOTONIC`` nanoseconds.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

GTK_SCHEMA = "cua.ar.gtk3_journal_v1"
TRUSTED_SEQUENCE = ("pointerdown", "mousedown", "pointerup", "mouseup", "click")

# Control kinds, by fixture.
GTK_CHECKBOX_KINDS = (
    "reference",             # positive: toggle the target once (variant normal)
    "negative_stale_token",  # a token from a replaced snapshot must be refused, no mutation
    "negative_no_action",    # observe only: the app state must stay unchanged
    "canary_absent",         # target label absent: refused/unknown, no mutation
    "canary_disabled",       # target disabled after observation (fresh token): refused/unknown, no mutation
    "delayed_effect",        # effect lands 200-500 ms after the handler: no early success, no redispatch
    "focus_steal",           # app steals focus after the toggle: effect once, focus back with the user
)
VARIANT_FOR_KIND = {
    "reference": "normal",
    "negative_stale_token": "normal",
    "negative_no_action": "normal",
    "canary_absent": "absent",
    "canary_disabled": "disabled",
    "delayed_effect": "delayed",
    "focus_steal": "focus_steal",
    "text_save": "normal",
}


def read_journal(path: str | Path) -> list[dict[str, Any]]:
    """Every complete JSON line of the app journal (a torn last line is ignored)."""
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return []
    records = []
    for line in raw.split(b"\n"):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records


def _own(records: Iterable[Mapping[str, Any]], nonce: str, app_pid: int) -> tuple[list, list]:
    own, foreign = [], []
    for record in records:
        if record.get("schema") == GTK_SCHEMA and record.get("nonce") == nonce and record.get("pid") == app_pid:
            own.append(record)
        else:
            foreign.append(record)
    return own, foreign


def gtk_effect_matches(record: Mapping[str, Any], task: str, initial: Mapping[str, Any],
                       expected_note: str | None) -> bool:
    if task == "checkbox":
        return record.get("event") == "toggle" and record.get("checked") is (not bool(initial.get("checked")))
    if task == "text":
        return record.get("event") == "save" and expected_note is not None and record.get("note_saved") == expected_note
    return False


def gtk_confirms(records: list[dict[str, Any]], *, task: str, nonce: str, app_pid: int,
                 initial: Mapping[str, Any], expected_note: str | None = None) -> dict[str, Any] | None:
    """The caller's done condition: the first own record that shows the expected effect."""
    own, _ = _own(records, nonce, app_pid)
    for record in own:
        if gtk_effect_matches(record, task, initial, expected_note):
            return record
    return None


def evaluate_gtk(records: list[dict[str, Any]], *, task: str, nonce: str, app_pid: int,
                 initial: Mapping[str, Any], t_spawn_ns: int, t_done_ns: int | None,
                 expected_note: str | None = None) -> dict[str, Any]:
    """Independent verdict over the final journal (read after the trial's linger)."""
    own, foreign = _own(records, nonce, app_pid)
    first = own[0] if own else None
    effect_ok = bool(first) and gtk_effect_matches(first, task, initial, expected_note)
    calls = [r.get("handler_calls") for r in own]
    ts_ok = None
    if first is not None:
        applied = int(first.get("t_applied_ns", -1))
        handler = int(first.get("t_handler_ns", -1))
        ts_ok = t_spawn_ns <= handler <= applied and (t_done_ns is None or applied <= t_done_ns)
    return {
        "records": len(records),
        "foreign_records": len(foreign),
        "mutation_count": len(own),
        "handler_calls_max": max((c for c in calls if isinstance(c, int)), default=0),
        "duplicate_mutation": len(own) > 1,
        "effect_ok": effect_ok,
        "ts_ok": ts_ok,
        "t_handler_ns": first.get("t_handler_ns") if first else None,
        "t_applied_ns": first.get("t_applied_ns") if first else None,
        "delay_ms_observed": ((first["t_applied_ns"] - first["t_handler_ns"]) / 1e6) if first else None,
        "verified": bool(effect_ok and len(own) == 1 and not foreign and ts_ok),
        "unchanged": not own and not foreign,
    }


CLAIMED_EFFECTS = ("verified", "applied", "confirmed", "changed")
ACTION_TOOLS = ("click", "set_value", "browser_click", "browser_type")


def unverified_success_claims(caller: Mapping[str, Any], oracle: Mapping[str, Any]) -> list[str]:
    """Driver results that claim an effect the target never showed, or showed only
    after the tool had already returned (G2 'no unverified success').

    Only the trial's last action is checked: it is the one whose effect the journal
    records (the toggle, or the Save click). An earlier ``set_value`` reports on the
    field contents, which the journal does not observe."""
    out = []
    applied = oracle.get("t_applied_ns")
    actions = [c for c in caller.get("calls") or [] if c.get("tool") in ACTION_TOOLS]
    for call in actions[-1:]:
        if not call.get("ok"):
            continue
        st = call.get("structured") or {}
        claimed = st.get("verified") is True or str(st.get("effect") or "").lower() in CLAIMED_EFFECTS
        if not claimed:
            continue
        if oracle.get("unchanged") or applied is None:
            out.append(f"{call['tool']} claimed effect={st.get('effect')!r} but the target never changed")
        elif call.get("t1_ns") is not None and applied > call["t1_ns"]:
            out.append(f"{call['tool']} claimed effect={st.get('effect')!r} before the target changed")
    return out


def gtk_control_verdict(kind: str, caller: Mapping[str, Any], oracle: Mapping[str, Any],
                        extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Pass/fail for one GTK trial. ``caller`` is the frozen caller's own record
    (outcome, error code, dispatch count); ``oracle`` is ``evaluate_gtk``; ``extra``
    carries external observations (bus DoAction count, focus journal)."""
    extra = extra or {}
    reasons: list[str] = []
    outcome = caller.get("outcome")
    dispatches = int(caller.get("dispatch_count", 0))
    do_action = extra.get("do_action_on_bus")  # None when the bus was not monitored

    def need(condition: bool, why: str) -> None:
        if not condition:
            reasons.append(why)

    reasons.extend(unverified_success_claims(caller, oracle))

    if kind in ("reference", "delayed_effect", "focus_steal", "text_save"):
        need(outcome == "verified", f"caller outcome {outcome!r} != verified")
        need(bool(oracle.get("verified")), "oracle did not verify exactly one own effect")
        need(oracle.get("mutation_count") == 1, f"mutation_count {oracle.get('mutation_count')} != 1")
        need(dispatches == (2 if kind == "text_save" else 1), f"caller dispatches {dispatches}")
        if do_action is not None and kind != "text_save":
            # text_save legitimately sends 2 (set_value's activate commit + Save);
            # its duplicate check is the journal's mutation_count.
            need(do_action == 1, f"DoAction on bus {do_action}")
        done = caller.get("t_done_ns")
        applied = oracle.get("t_applied_ns")
        need(done is not None and applied is not None and applied <= done, "done before the effect landed")
        if kind == "delayed_effect":
            delay = oracle.get("delay_ms_observed")
            need(delay is not None and delay >= 195, f"effect delay {delay} ms < 200 (variant not exercised)")
        if kind == "focus_steal":
            need(bool(extra.get("steal_observed")), "the app never took the focus (variant not exercised)")
            need(bool(extra.get("focus_back_with_user")), "focus did not end with the user's window")
    elif kind == "negative_stale_token":
        need(outcome == "refused", f"caller outcome {outcome!r} != refused")
        need("stale" in str(caller.get("error_code") or ""), f"error code {caller.get('error_code')!r} is not stale")
        need(bool(oracle.get("unchanged")), "app state changed")
        if do_action is not None:
            need(do_action == 0, f"DoAction on bus {do_action}")
    elif kind == "negative_no_action":
        need(outcome == "observed_only", f"caller outcome {outcome!r}")
        need(dispatches == 0, f"caller dispatches {dispatches}")
        need(bool(oracle.get("unchanged")), "app state changed without an action")
        if do_action is not None:
            need(do_action == 0, f"DoAction on bus {do_action}")
    elif kind in ("canary_absent", "canary_disabled"):
        need(outcome in ("refused", "unknown"), f"caller outcome {outcome!r} not refused/unknown")
        need(bool(oracle.get("unchanged")), "app state changed on an impossible task")
        if kind == "canary_disabled":
            need(dispatches == 1, "disabled canary did not reach the Driver")
            need(str(caller.get("canary_disable_ack") or "").startswith("disabled"),
                 "the app did not acknowledge disabling the target")
    else:
        reasons.append(f"unknown control kind {kind}")
    return {"kind": kind, "passed": not reasons, "reasons": reasons}


# --------------------------------------------------------------------- browser
def trusted_click_sequence(page_events: list[Mapping[str, Any]], target_prefix: str = "button") -> dict[str, Any]:
    """Whether the page saw a trusted pointerdown..click on the Submit button,
    in order, before its ``submit`` event."""
    seq_idx = 0
    trusted_kinds: list[str] = []
    submit_after = False
    untrusted_click = False
    for event in sorted(page_events, key=lambda e: e.get("seq", 0)):
        kind = event.get("kind")
        target = str(event.get("target") or "")
        if kind in TRUSTED_SEQUENCE and target.startswith(target_prefix):
            if event.get("is_trusted") is not True:
                untrusted_click = True
                continue
            trusted_kinds.append(kind)
            if seq_idx < len(TRUSTED_SEQUENCE) and kind == TRUSTED_SEQUENCE[seq_idx]:
                seq_idx += 1
        elif kind == "submit" and seq_idx == len(TRUSTED_SEQUENCE):
            submit_after = True
    return {"complete": seq_idx == len(TRUSTED_SEQUENCE), "submit_after_click": submit_after,
            "trusted_kinds": trusted_kinds, "untrusted_click": untrusted_click}


def evaluate_browser(journal: list[Mapping[str, Any]], state: Mapping[str, Any] | None, *, token: str,
                     t_spawn_ns: int, t_done_ns: int | None) -> dict[str, Any]:
    posts = [r for r in journal if r.get("source") == "target" and r.get("kind") == "submit_post"]
    own_posts = [r for r in posts if r.get("value") == token]
    page = [r for r in journal if r.get("source") == "page"]
    seq = trusted_click_sequence(page)
    first = own_posts[0] if own_posts else None
    ts_ok = None
    if first is not None:
        t_post = int(first["recv_mono_ns"])
        ts_ok = t_spawn_ns <= t_post and (t_done_ns is None or t_post <= t_done_ns)
    state_ok = bool(state) and state.get("submitted") == token
    return {
        "state_ok": state_ok,
        "posts": len(posts),
        "own_posts": len(own_posts),
        "duplicate_mutation": len(posts) > 1,
        "trusted_sequence": seq,
        "ts_ok": ts_ok,
        "t_post_ns": first.get("recv_mono_ns") if first else None,
        "verified": bool(state_ok and len(posts) == 1 and len(own_posts) == 1 and ts_ok
                         and seq["complete"] and seq["submit_after_click"] and not seq["untrusted_click"]),
    }


def browser_control_verdict(caller: Mapping[str, Any], oracle: Mapping[str, Any]) -> dict[str, Any]:
    reasons = []
    if caller.get("outcome") != "verified":
        reasons.append(f"caller outcome {caller.get('outcome')!r} != verified")
    if not oracle.get("verified"):
        reasons.append("oracle did not verify one trusted submit")
    done, post = caller.get("t_done_ns"), oracle.get("t_post_ns")
    if done is None or post is None or post > done:
        reasons.append("done before the POST landed")
    return {"kind": "browser_fill_submit", "passed": not reasons, "reasons": reasons}
