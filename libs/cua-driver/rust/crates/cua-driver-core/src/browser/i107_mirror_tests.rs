//! Unit tests for the kvnloo/cua#107 CSHADOW shadow mirror (experiment only).

use super::*;
use crate::browser::cdp_ws::CdpConnection;
use crate::browser::mock_cdp::{MockCall, MockCdpServer, MockEvent, MockReply};
use crate::browser::semantic::{SemanticDocument, SemanticNode};
use crate::browser::store::{
    BrowserActionKind, BrowserStore, BrowserVisibility, FrameRef, TabRecord, TargetRecord,
};
use crate::browser::types::{
    BindingQuality, EndpointAccessClass, EndpointTransport, ProcessFingerprint, Rect,
};
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap};
use std::sync::{Arc, Mutex as StdMutex};

const S: &str = "mirror-s1";

fn element(id: i64, backend: i64, name: &str, attrs: &[&str], children: Vec<Value>) -> Value {
    json!({ "nodeId": id, "backendNodeId": backend, "nodeType": 1, "nodeName": name,
        "nodeValue": "", "childNodeCount": children.len(), "attributes": attrs,
        "children": children })
}

fn text(id: i64, backend: i64, value: &str) -> Value {
    json!({ "nodeId": id, "backendNodeId": backend, "nodeType": 3, "nodeName": "#text",
        "nodeValue": value })
}

/// A small fill-task page: document > html > body > [form > [input, button > "Submit"], p > text].
/// `id_offset` simulates another CDP session's nodeIds; backendNodeIds are shared.
fn page(id_offset: i64) -> Value {
    let n = |id: i64| id + id_offset;
    let input = json!({ "nodeId": n(5), "backendNodeId": 105, "nodeType": 1, "nodeName": "INPUT",
        "nodeValue": "", "childNodeCount": 0, "attributes": ["name", "verification", "value", ""] });
    let button = element(
        n(6),
        106,
        "BUTTON",
        &["type", "submit"],
        vec![text(n(7), 107, "Submit")],
    );
    let form = element(
        n(4),
        104,
        "FORM",
        &["action", "/submit"],
        vec![input, button],
    );
    let para = element(
        n(8),
        108,
        "P",
        &[],
        vec![text(n(9), 109, "private page text")],
    );
    let body = element(n(3), 103, "BODY", &["class", "page"], vec![form, para]);
    let html = element(n(2), 102, "HTML", &[], vec![body]);
    json!({ "root": { "nodeId": n(1), "backendNodeId": 101, "nodeType": 9,
        "nodeName": "#document", "nodeValue": "", "childNodeCount": 1, "children": [html] } })
}

fn frame() -> Option<(String, String)> {
    Some(("F_MAIN".into(), "L1".into()))
}

fn ev(method: &str, session: Option<&str>, params: Value) -> CdpEvent {
    CdpEvent {
        method: method.into(),
        session_id: session.map(str::to_owned),
        params,
    }
}

fn dom(method: &str, params: Value) -> CdpEvent {
    ev(method, Some(S), params)
}

fn sem_node(backend: i64, role: &str, name: &str, visibility: BrowserVisibility) -> SemanticNode {
    SemanticNode {
        ax_id: format!("ax{backend}"),
        parent_ax_id: None,
        child_ax_ids: Vec::new(),
        backend_node_id: Some(backend),
        role: role.into(),
        name: Some(name.into()),
        value: None,
        states: BTreeMap::new(),
        frame: FrameRef::main_unproven(),
        visibility,
        actions: vec![BrowserActionKind::Click],
        document_order: backend as usize,
    }
}

fn semantic() -> SemanticDocument {
    SemanticDocument {
        nodes: vec![
            sem_node(
                105,
                "textbox",
                "Verification value",
                BrowserVisibility::InViewport,
            ),
            sem_node(106, "button", "Submit", BrowserVisibility::InViewport),
        ],
        css_hidden_dom_count: 0,
        unprovable_frame_count: 0,
        complete: true,
    }
}

fn live(mode: MirrorMode) -> MirrorState {
    let mut state = MirrorState::new(mode, "CDP1".into(), 0);
    state.begin_bootstrap(S.into());
    state.complete_bootstrap(frame(), &page(0)).unwrap();
    assert_eq!(state.coverage, Coverage::Current);
    state
}

/// Apply the attributeModified to the fresh page JSON (simulates the browser state).
fn set_attr(doc: &mut Value, backend: i64, name: &str, value: &str) {
    fn walk(node: &mut Value, backend: i64, name: &str, value: &str) -> bool {
        if node["backendNodeId"].as_i64() == Some(backend) {
            let attrs = node["attributes"].as_array_mut().unwrap();
            if let Some(pos) = attrs.chunks(2).position(|c| c[0] == name) {
                attrs[pos * 2 + 1] = json!(value);
            } else {
                attrs.push(json!(name));
                attrs.push(json!(value));
            }
            return true;
        }
        if let Some(children) = node.get_mut("children").and_then(Value::as_array_mut) {
            for child in children {
                if walk(child, backend, name, value) {
                    return true;
                }
            }
        }
        false
    }
    assert!(walk(&mut doc["root"], backend, name, value));
}

// ── mode / default off ───────────────────────────────────────────────────

#[test]
fn mode_is_off_unless_explicitly_shadow_or_shadow_audit() {
    assert_eq!(MirrorMode::parse(None), MirrorMode::Off);
    for raw in ["", "off", "on", "1", "SHADOW", "shadow-audit", "audit"] {
        assert_eq!(MirrorMode::parse(Some(raw)), MirrorMode::Off, "{raw:?}");
    }
    assert_eq!(MirrorMode::parse(Some("shadow")), MirrorMode::Shadow);
    assert_eq!(
        MirrorMode::parse(Some("shadow_audit")),
        MirrorMode::ShadowAudit
    );
}

#[test]
fn default_test_process_has_the_mirror_off() {
    if std::env::var_os(MIRROR_ENV).is_none() {
        assert_eq!(mode(), MirrorMode::Off);
    }
}

#[test]
fn fault_plan_parses_only_known_shapes() {
    assert_eq!(FaultPlan::parse(None), FaultPlan::None);
    assert_eq!(FaultPlan::parse(Some("")), FaultPlan::None);
    assert_eq!(FaultPlan::parse(Some("bogus:3")), FaultPlan::None);
    assert_eq!(FaultPlan::parse(Some("drop:0")), FaultPlan::None);
    assert_eq!(FaultPlan::parse(Some("drop:5")), FaultPlan::Drop(5));
    assert_eq!(FaultPlan::parse(Some("dup:2")), FaultPlan::Duplicate(2));
    assert_eq!(
        FaultPlan::parse(Some("delay:3:40")),
        FaultPlan::Delay(3, 40)
    );
    assert_eq!(FaultPlan::parse(Some("swap:4")), FaultPlan::Swap(4));
    assert_eq!(FaultPlan::parse(Some("early")), FaultPlan::Early);
    assert_eq!(FaultPlan::parse(Some("foreign:2")), FaultPlan::Foreign(2));
    assert_eq!(FaultPlan::parse(Some("stale:2")), FaultPlan::Stale(2));
    assert_eq!(FaultPlan::parse(Some("overflow:7")), FaultPlan::Overflow(7));
    assert_eq!(
        FaultPlan::parse(Some("reconnect:9")),
        FaultPlan::Reconnect(9)
    );
}

// ── bootstrap ────────────────────────────────────────────────────────────

#[test]
fn coverage_is_unknown_until_bootstrap_completes() {
    let mut state = MirrorState::new(MirrorMode::Shadow, "CDP1".into(), 0);
    assert!(matches!(state.coverage, Coverage::Unknown(_)));
    state.begin_bootstrap(S.into());
    assert!(matches!(state.coverage, Coverage::Unknown(_)));
    state.complete_bootstrap(frame(), &page(0)).unwrap();
    assert_eq!(state.coverage, Coverage::Current);
    assert_eq!(state.node_count(), 9);
}

#[test]
fn early_dom_event_keeps_coverage_unknown_after_bootstrap() {
    let mut state = MirrorState::new(MirrorMode::Shadow, "CDP1".into(), 0);
    state.begin_bootstrap(S.into());
    let outcome = state.intake(&dom(
        "DOM.attributeModified",
        json!({ "nodeId": 3, "name": "class", "value": "x" }),
    ));
    assert_eq!(outcome, Intake::Buffered);
    assert!(state.complete_bootstrap(frame(), &page(0)).is_err());
    assert!(
        matches!(&state.coverage, Coverage::Unknown(r) if r == "pre_bootstrap_event"),
        "{:?}",
        state.coverage
    );
}

#[test]
fn early_unrelated_event_does_not_poison_bootstrap() {
    let mut state = MirrorState::new(MirrorMode::Shadow, "CDP1".into(), 0);
    state.begin_bootstrap(S.into());
    let outcome = state.intake(&ev(
        "DOM.attributeModified",
        Some("other"),
        json!({ "nodeId": 3, "name": "class", "value": "x" }),
    ));
    assert_eq!(outcome, Intake::Unrelated);
    state.complete_bootstrap(frame(), &page(0)).unwrap();
    assert_eq!(state.coverage, Coverage::Current);
}

#[test]
fn node_cap_invalidates_and_frees_the_projection() {
    let mut children = Vec::new();
    for i in 0..(MAX_NODES as i64 + 5) {
        children.push(
            json!({ "nodeId": 10 + i, "backendNodeId": 1000 + i, "nodeType": 1,
            "nodeName": "DIV", "nodeValue": "", "childNodeCount": 0, "attributes": [] }),
        );
    }
    let doc = json!({ "root": { "nodeId": 1, "backendNodeId": 1, "nodeType": 9,
        "nodeName": "#document", "nodeValue": "", "childNodeCount": children.len(), "children": children } });
    let mut state = MirrorState::new(MirrorMode::Shadow, "CDP1".into(), 0);
    state.begin_bootstrap(S.into());
    assert!(state.complete_bootstrap(frame(), &doc).is_err());
    assert!(matches!(&state.coverage, Coverage::Unknown(r) if r == "node_cap"));
    assert_eq!(state.node_count(), 0);
    assert_eq!(state.stats.node_cap_trips, 1);
}

// ── event application: only established fields ──────────────────────────

#[test]
fn attribute_text_and_structure_events_apply_and_agree_with_a_fresh_read() {
    let mut state = live(MirrorMode::ShadowAudit);
    let mut fresh = page(1000);
    assert_eq!(
        state.intake(&dom(
            "DOM.attributeModified",
            json!({ "nodeId": 3, "name": "class", "value": "busy" })
        )),
        Intake::Applied
    );
    set_attr(&mut fresh, 103, "class", "busy");
    assert_eq!(
        state.intake(&dom(
            "DOM.characterDataModified",
            json!({ "nodeId": 9, "characterData": "changed" })
        )),
        Intake::Applied
    );
    fresh["root"]["children"][0]["children"][0]["children"][1]["children"][0]["nodeValue"] =
        json!("changed");
    // Window starts after the events were applied: nothing is in flight.
    let report = state.audit(state.rev, &fresh, true, &semantic());
    assert_eq!(report.coverage, "current");
    assert_eq!(report.false_current, 0, "{report:?}");
    assert_eq!(report.ambiguous_in_flight, 0);
    assert!(report.agree > 0);
}

#[test]
fn missing_event_is_invisible_to_the_mirror_and_caught_only_by_the_fresh_audit() {
    let state = live(MirrorMode::ShadowAudit);
    let mut fresh = page(1000);
    // The browser changed the Submit button's attribute, but the event never arrived.
    set_attr(&mut fresh, 106, "disabled", "");
    let report = state.audit(state.rev, &fresh, true, &semantic());
    assert_eq!(state.coverage, Coverage::Current, "the mirror cannot know");
    assert_eq!(report.false_current, 1, "{report:?}");
    assert_eq!(report.false_current_action_relevant, 1);
    assert_eq!(report.false_current_fields.get("attributes"), Some(&1));
}

#[test]
fn changes_inside_the_bracketing_window_are_ambiguous_not_false_current() {
    let mut state = live(MirrorMode::ShadowAudit);
    let window_start = state.rev;
    // Applied after the fresh read was requested: the fresh read may predate it.
    state.intake(&dom(
        "DOM.attributeModified",
        json!({ "nodeId": 6, "name": "data-x", "value": "1" }),
    ));
    let report = state.audit(window_start, &page(1000), true, &semantic());
    assert_eq!(report.false_current, 0, "{report:?}");
    assert_eq!(report.ambiguous_in_flight, 1);
    assert_eq!(report.raw_differences_including_window, 1);
}

#[test]
fn child_insert_and_remove_track_order_and_existence() {
    let mut state = live(MirrorMode::ShadowAudit);
    assert_eq!(
        state.intake(&dom(
            "DOM.childNodeInserted",
            json!({ "parentNodeId": 3, "previousNodeId": 4, "node": {
                "nodeId": 50, "backendNodeId": 150, "nodeType": 1, "nodeName": "SPAN",
                "nodeValue": "", "childNodeCount": 0, "attributes": [] } })
        )),
        Intake::Applied
    );
    assert_eq!(state.node_count(), 10);
    assert_eq!(
        state.intake(&dom(
            "DOM.childNodeRemoved",
            json!({ "parentNodeId": 3, "nodeId": 50 })
        )),
        Intake::Applied
    );
    assert_eq!(state.node_count(), 9);
    let report = state.audit(state.rev, &page(1000), true, &semantic());
    assert_eq!(report.false_current, 0, "{report:?}");
}

#[test]
fn inserted_container_without_children_is_unknown_until_set_child_nodes() {
    let mut state = live(MirrorMode::Shadow);
    let outcome = state.intake(&dom(
        "DOM.childNodeInserted",
        json!({ "parentNodeId": 3, "previousNodeId": 8, "node": {
            "nodeId": 60, "backendNodeId": 160, "nodeType": 1, "nodeName": "DIV",
            "nodeValue": "", "childNodeCount": 2, "attributes": [] } }),
    ));
    assert_eq!(outcome, Intake::Applied);
    assert_eq!(state.take_need_children(), vec![60]);
    assert_eq!(
        state.intake(&dom(
            "DOM.setChildNodes",
            json!({ "parentId": 60, "nodes": [
                { "nodeId": 61, "backendNodeId": 161, "nodeType": 3, "nodeName": "#text", "nodeValue": "a" },
                { "nodeId": 62, "backendNodeId": 162, "nodeType": 3, "nodeName": "#text", "nodeValue": "b" } ] })
        )),
        Intake::Applied
    );
    assert_eq!(state.node_count(), 12);
    assert!(state.take_need_children().is_empty());
}

#[test]
fn inline_style_invalidation_makes_style_uncertain_not_current() {
    let mut state = live(MirrorMode::ShadowAudit);
    state.intake(&dom(
        "DOM.inlineStyleInvalidated",
        json!({ "nodeIds": [6] }),
    ));
    let mut fresh = page(1000);
    set_attr(&mut fresh, 106, "style", "display: none");
    let report = state.audit(state.rev, &fresh, true, &semantic());
    // The mirror does not know the style value: unknown, never false-current.
    assert_eq!(report.false_current, 0, "{report:?}");
    assert!(report.unknown_checks >= 1);
}

#[test]
fn property_only_changes_are_never_claimed() {
    // Typed input.value has no DOM event; the attribute stays "" in both reads,
    // and the value property is reported as an unestablished field.
    let state = live(MirrorMode::ShadowAudit);
    let report = state.audit(state.rev, &page(1000), true, &semantic());
    assert_eq!(report.false_current, 0);
    assert!(UNESTABLISHED_FIELDS.contains(&"value_property"));
    assert!(UNESTABLISHED_FIELDS.contains(&"visibility"));
    assert!(UNESTABLISHED_FIELDS.contains(&"occlusion"));
    assert!(UNESTABLISHED_FIELDS.contains(&"focus"));
    assert!(UNESTABLISHED_FIELDS.contains(&"geometry"));
    assert!(
        report.unknown_action_relevant >= (UNESTABLISHED_FIELDS.len() as u64) * 2,
        "{report:?}"
    );
}

#[test]
fn action_relevant_match_set_is_reported_unknown_with_a_dom_estimate() {
    let state = live(MirrorMode::ShadowAudit);
    let report = state.audit(state.rev, &page(1000), true, &semantic());
    assert_eq!(report.match_set.fresh_count, 1);
    assert_eq!(report.match_set.fresh_actionable_visible, 1);
    assert_eq!(report.match_set.mirror_status, "unknown");
    assert_eq!(report.match_set.mirror_dom_estimate, Some(1));
}

#[test]
fn competing_submit_insert_changes_the_dom_estimate() {
    let mut state = live(MirrorMode::ShadowAudit);
    state.intake(&dom(
        "DOM.childNodeInserted",
        json!({ "parentNodeId": 4, "previousNodeId": 6, "node": {
            "nodeId": 70, "backendNodeId": 170, "nodeType": 1, "nodeName": "BUTTON",
            "nodeValue": "", "childNodeCount": 1, "attributes": ["type", "submit"],
            "children": [ { "nodeId": 71, "backendNodeId": 171, "nodeType": 3,
                "nodeName": "#text", "nodeValue": "Submit" } ] } }),
    ));
    let report = state.audit(0, &page(1000), true, &semantic());
    assert_eq!(report.match_set.mirror_dom_estimate, Some(2));
    assert_eq!(report.match_set.mirror_status, "unknown");
}

#[test]
fn audit_with_unknown_coverage_counts_everything_unknown() {
    let mut state = live(MirrorMode::ShadowAudit);
    state.intake(&dom("DOM.documentUpdated", json!({})));
    let report = state.audit(state.rev, &page(1000), true, &semantic());
    assert!(
        report.coverage.starts_with("unknown:"),
        "{}",
        report.coverage
    );
    assert_eq!(report.false_current, 0);
    assert_eq!(report.compared_nodes, 0);
    assert!(report.unknown_action_relevant > 0);
    assert_eq!(report.match_set.mirror_dom_estimate, None);
}

#[test]
fn audit_report_carries_no_page_text_or_attribute_values() {
    let state = live(MirrorMode::ShadowAudit);
    let mut fresh = page(1000);
    set_attr(&mut fresh, 108, "title", "secret-attribute-value");
    let report = state.audit(state.rev, &fresh, true, &semantic());
    let text = serde_json::to_string(&report).unwrap();
    assert!(!text.contains("private page text"), "{text}");
    assert!(!text.contains("secret-attribute-value"), "{text}");
    assert!(!text.contains("Submit"), "{text}");
}

// ── invalidation, gaps and faults (DC18 at the intake seam) ─────────────

#[test]
fn document_updated_navigation_and_frame_changes_invalidate() {
    for (method, reason) in [
        ("DOM.documentUpdated", "document_updated"),
        ("Page.frameNavigated", "frame_navigated"),
        ("Page.documentOpened", "document_opened"),
        ("Page.frameAttached", "frame_tree_changed"),
        ("Page.frameDetached", "frame_tree_changed"),
        ("Inspector.targetReloadedAfterCrash", "reloaded_after_crash"),
    ] {
        let mut state = live(MirrorMode::Shadow);
        assert_eq!(
            state.intake(&dom(method, json!({ "frame": { "id": "F_MAIN" } }))),
            Intake::Invalidated(reason.into()),
            "{method}"
        );
        assert_eq!(
            state.node_count(),
            0,
            "{method}: projection must be dropped"
        );
    }
}

#[test]
fn session_loss_events_are_reported_as_lost() {
    let mut state = live(MirrorMode::Shadow);
    assert!(matches!(
        state.intake(&dom("Inspector.detached", json!({ "reason": "x" }))),
        Intake::SessionLost(_)
    ));
    let mut state = live(MirrorMode::Shadow);
    assert!(matches!(
        state.intake(&dom("Inspector.targetCrashed", json!({}))),
        Intake::SessionLost(_)
    ));
    let mut state = live(MirrorMode::Shadow);
    assert!(matches!(
        state.intake(&ev(
            "Target.detachedFromTarget",
            None,
            json!({ "sessionId": S })
        )),
        Intake::SessionLost(_)
    ));
    let mut state = live(MirrorMode::Shadow);
    assert!(matches!(
        state.intake(&ev(
            "Target.targetDestroyed",
            None,
            json!({ "targetId": "CDP1" })
        )),
        Intake::SessionLost(_)
    ));
    let mut state = live(MirrorMode::Shadow);
    assert_eq!(
        state.intake(&ev(
            "Target.detachedFromTarget",
            None,
            json!({ "sessionId": "someone-else" })
        )),
        Intake::Unrelated
    );
}

#[test]
fn unrelated_and_stale_session_events_are_ignored_and_counted() {
    let mut state = live(MirrorMode::Shadow);
    let rev = state.rev;
    for session in ["other-session", "mirror-s0-stale"] {
        assert_eq!(
            state.intake(&ev(
                "DOM.attributeModified",
                Some(session),
                json!({ "nodeId": 3, "name": "class", "value": "x" })
            )),
            Intake::Unrelated
        );
    }
    assert_eq!(state.rev, rev);
    assert_eq!(state.stats.unrelated, 2);
    assert_eq!(state.coverage, Coverage::Current);
}

#[test]
fn structural_inconsistencies_invalidate_instead_of_guessing() {
    // Duplicate insert.
    let mut state = live(MirrorMode::Shadow);
    let insert = dom(
        "DOM.childNodeInserted",
        json!({ "parentNodeId": 3, "previousNodeId": 0, "node": {
            "nodeId": 50, "backendNodeId": 150, "nodeType": 1, "nodeName": "SPAN",
            "nodeValue": "", "childNodeCount": 0, "attributes": [] } }),
    );
    assert_eq!(state.intake(&insert), Intake::Applied);
    assert_eq!(
        state.intake(&insert),
        Intake::Invalidated("duplicate_node".into())
    );
    // Removal of an unknown node (e.g. reordered remove before insert, or a duplicate remove).
    let mut state = live(MirrorMode::Shadow);
    assert_eq!(
        state.intake(&dom(
            "DOM.childNodeRemoved",
            json!({ "parentNodeId": 3, "nodeId": 77 })
        )),
        Intake::Invalidated("missing_node".into())
    );
    // Insert after a sibling the mirror never saw (a missed earlier insert).
    let mut state = live(MirrorMode::Shadow);
    assert_eq!(
        state.intake(&dom(
            "DOM.childNodeInserted",
            json!({ "parentNodeId": 3, "previousNodeId": 999, "node": {
                "nodeId": 51, "backendNodeId": 151, "nodeType": 1, "nodeName": "SPAN",
                "nodeValue": "", "childNodeCount": 0, "attributes": [] } })
        )),
        Intake::Invalidated("missing_previous".into())
    );
    // Attribute on an unknown node.
    let mut state = live(MirrorMode::Shadow);
    assert_eq!(
        state.intake(&dom(
            "DOM.attributeModified",
            json!({ "nodeId": 4242, "name": "a", "value": "b" })
        )),
        Intake::Invalidated("missing_node".into())
    );
    // Child count disagreeing with a fully known child list.
    let mut state = live(MirrorMode::Shadow);
    assert_eq!(
        state.intake(&dom(
            "DOM.childNodeCountUpdated",
            json!({ "nodeId": 3, "childNodeCount": 5 })
        )),
        Intake::Invalidated("child_count_mismatch".into())
    );
    // Unmodeled DOM events are treated as possible changes.
    let mut state = live(MirrorMode::Shadow);
    assert!(matches!(
        state.intake(&dom("DOM.somethingNew", json!({}))),
        Intake::Invalidated(r) if r.starts_with("unmodeled:")
    ));
}

#[test]
fn events_while_unknown_are_discarded_and_counted() {
    let mut state = live(MirrorMode::Shadow);
    state.intake(&dom("DOM.documentUpdated", json!({})));
    assert_eq!(
        state.intake(&dom(
            "DOM.attributeModified",
            json!({ "nodeId": 3, "name": "class", "value": "x" })
        )),
        Intake::DiscardedUnknown
    );
    assert_eq!(state.stats.discarded_unknown, 1);
}

#[test]
fn overflow_invalidates_and_is_counted() {
    let mut state = live(MirrorMode::Shadow);
    state.overflow(MAX_QUEUED_EVENTS + 1);
    assert!(matches!(&state.coverage, Coverage::Unknown(r) if r == "overflow"));
    assert_eq!(state.stats.overflows, 1);
    assert_eq!(state.node_count(), 0);
}

#[test]
fn fault_drop_removes_every_nth_mutation_event() {
    let mut f = FaultInjector::new(FaultPlan::Drop(2));
    let now = std::time::Instant::now();
    let a = dom(
        "DOM.attributeModified",
        json!({ "nodeId": 3, "name": "a", "value": "1" }),
    );
    assert_eq!(f.filter(a.clone(), S, now).deliver.len(), 1);
    let out = f.filter(a.clone(), S, now);
    assert!(out.deliver.is_empty());
    assert_eq!(out.injected.as_deref(), Some("drop"));
    // Non-mutation and foreign-session events are never counted or dropped.
    assert_eq!(
        f.filter(ev("Page.loadEventFired", Some(S), json!({})), S, now)
            .deliver
            .len(),
        1
    );
}

#[test]
fn fault_duplicate_delivers_twice() {
    let mut f = FaultInjector::new(FaultPlan::Duplicate(1));
    let a = dom(
        "DOM.attributeModified",
        json!({ "nodeId": 3, "name": "a", "value": "1" }),
    );
    assert_eq!(f.filter(a, S, std::time::Instant::now()).deliver.len(), 2);
}

#[test]
fn fault_swap_reorders_adjacent_mutations() {
    let mut f = FaultInjector::new(FaultPlan::Swap(1));
    let now = std::time::Instant::now();
    let a = dom(
        "DOM.attributeModified",
        json!({ "nodeId": 3, "name": "a", "value": "1" }),
    );
    let b = dom(
        "DOM.attributeModified",
        json!({ "nodeId": 3, "name": "a", "value": "2" }),
    );
    assert!(f.filter(a, S, now).deliver.is_empty());
    let out = f.filter(b, S, now).deliver;
    assert_eq!(out.len(), 2);
    assert_eq!(out[0].params["value"], "2");
    assert_eq!(out[1].params["value"], "1");
}

#[test]
fn fault_delay_holds_then_releases_after_the_deadline() {
    let mut f = FaultInjector::new(FaultPlan::Delay(1, 30));
    let now = std::time::Instant::now();
    let a = dom(
        "DOM.attributeModified",
        json!({ "nodeId": 3, "name": "a", "value": "1" }),
    );
    assert!(f.filter(a, S, now).deliver.is_empty());
    assert!(f.next_due().is_some());
    assert!(f.release_due(now).is_empty());
    let later = now + std::time::Duration::from_millis(31);
    assert_eq!(f.release_due(later).len(), 1);
}

#[test]
fn fault_foreign_and_stale_add_retagged_copies() {
    for plan in [FaultPlan::Foreign(1), FaultPlan::Stale(1)] {
        let mut f = FaultInjector::new(plan.clone());
        let a = dom(
            "DOM.attributeModified",
            json!({ "nodeId": 3, "name": "a", "value": "1" }),
        );
        let out = f.filter(a, S, std::time::Instant::now()).deliver;
        assert_eq!(out.len(), 2, "{plan:?}");
        assert_eq!(out[0].session_id.as_deref(), Some(S));
        assert_ne!(out[1].session_id.as_deref(), Some(S), "{plan:?}");
    }
}

#[test]
fn fault_overflow_and_reconnect_signal_once() {
    let mut f = FaultInjector::new(FaultPlan::Overflow(2));
    let now = std::time::Instant::now();
    let a = dom(
        "DOM.attributeModified",
        json!({ "nodeId": 3, "name": "a", "value": "1" }),
    );
    assert!(!f.filter(a.clone(), S, now).overflow);
    assert!(f.filter(a.clone(), S, now).overflow);
    assert!(!f.filter(a.clone(), S, now).overflow, "fires once");
    let mut f = FaultInjector::new(FaultPlan::Reconnect(1));
    assert!(f.filter(a.clone(), S, now).reconnect);
    assert!(!f.filter(a, S, now).reconnect);
}

#[test]
fn faulted_streams_never_produce_false_current_without_detection_paths() {
    // Detectable faults (structure): duplicate insert / reordered remove -> unknown.
    let mut state = live(MirrorMode::ShadowAudit);
    let mut f = FaultInjector::new(FaultPlan::Duplicate(1));
    let insert = dom(
        "DOM.childNodeInserted",
        json!({ "parentNodeId": 3, "previousNodeId": 0, "node": {
            "nodeId": 50, "backendNodeId": 150, "nodeType": 1, "nodeName": "SPAN",
            "nodeValue": "", "childNodeCount": 0, "attributes": [] } }),
    );
    let mut last = Intake::NoOp;
    for e in f.filter(insert, S, std::time::Instant::now()).deliver {
        last = state.intake(&e);
    }
    assert_eq!(last, Intake::Invalidated("duplicate_node".into()));
    // Undetectable faults (a dropped attribute event) remain invisible until a fresh read.
    let mut state = live(MirrorMode::ShadowAudit);
    let mut f = FaultInjector::new(FaultPlan::Drop(1));
    let change = dom(
        "DOM.attributeModified",
        json!({ "nodeId": 6, "name": "disabled", "value": "" }),
    );
    for e in f.filter(change, S, std::time::Instant::now()).deliver {
        state.intake(&e);
    }
    let mut fresh = page(1000);
    set_attr(&mut fresh, 106, "disabled", "");
    let report = state.audit(state.rev, &fresh, true, &semantic());
    assert_eq!(report.false_current_action_relevant, 1);
}

// ── owner integration: TabRecord lifetime ────────────────────────────────

fn record() -> TargetRecord {
    TargetRecord {
        target_id: String::new(),
        pid: 42,
        window_id: 7,
        ws_url: "ws://127.0.0.1:9222/devtools/browser/x".into(),
        endpoint_owner_pid: 42,
        endpoint_transport: EndpointTransport::LegacyJsonVersion,
        endpoint_access_class: EndpointAccessClass::EmbeddedApplication,
        generation: 0,
        transport_session: None,
        fingerprint: ProcessFingerprint {
            pid: 42,
            start_time: Some(1),
            executable: None,
        },
        native_title: "t".into(),
        native_bounds: Rect::new(0.0, 0.0, 800.0, 600.0),
        cdp_target_id: "CDP1".into(),
        cdp_window_id: Some(11),
        quality: BindingQuality::Exact,
        tabs: HashMap::new(),
    }
}

fn store_with_tab() -> (BrowserStore, String, String) {
    let store = BrowserStore::new();
    let tid = store.mint_target("sess-a", record());
    let tab_id = store.mint_tab_id();
    store.update_target("sess-a", &tid, |rec| {
        rec.tabs.insert(
            tab_id.clone(),
            TabRecord {
                tab_id: tab_id.clone(),
                cdp_target_id: "CDP1".into(),
                title: "t".into(),
                url: "http://127.0.0.1/".into(),
                active: Some(true),
                generation: 0,
                snapshots: HashMap::new(),
                i107_mirror: None,
            },
        );
    });
    (store, tid, tab_id)
}

fn tab(store: &BrowserStore, tid: &str, tab_id: &str) -> TabRecord {
    store
        .get_target("sess-a", tid)
        .unwrap()
        .tabs
        .get(tab_id)
        .cloned()
        .unwrap()
}

type Seen = Arc<StdMutex<Vec<(String, Option<String>)>>>;

async fn mock_browser(seen: Seen) -> MockCdpServer {
    MockCdpServer::start(Arc::new(move |call: &MockCall| {
        seen.lock()
            .unwrap()
            .push((call.method.clone(), call.session_id.clone()));
        match call.method.as_str() {
            "Target.attachToTarget" => MockReply::ok(json!({ "sessionId": S })),
            "Page.getFrameTree" => MockReply::ok(json!({ "frameTree": { "frame": {
                "id": "F_MAIN", "loaderId": "L1", "url": "http://127.0.0.1/" } } })),
            "DOM.getDocument" => MockReply::ok(page(0)),
            "Test.emit" => MockReply::ok(json!({})).with_events(vec![MockEvent {
                method: "DOM.attributeModified".into(),
                session_id: Some(S.into()),
                params: json!({ "nodeId": 3, "name": "class", "value": "emitted" }),
            }]),
            _ => MockReply::ok(json!({})),
        }
    }))
    .await
}

async fn wait_until(mut f: impl FnMut() -> bool) {
    for _ in 0..200 {
        if f() {
            return;
        }
        tokio::time::sleep(std::time::Duration::from_millis(5)).await;
    }
    panic!("condition not reached");
}

#[tokio::test]
async fn off_mode_creates_no_event_session_and_no_mirror() {
    let seen: Seen = Arc::default();
    let server = mock_browser(seen.clone()).await;
    let conn = Arc::new(CdpConnection::connect(&server.ws_url()).await.unwrap());
    let (store, tid, tab_id) = store_with_tab();
    let t = tab(&store, &tid, &tab_id);
    let mirror = ensure_for_tab(
        MirrorMode::Off,
        &store,
        "sess-a",
        &tid,
        &tab_id,
        &t,
        &conn,
        0,
    );
    assert!(mirror.is_none());
    tokio::time::sleep(std::time::Duration::from_millis(30)).await;
    assert!(seen.lock().unwrap().is_empty(), "no CDP traffic when off");
    assert!(tab(&store, &tid, &tab_id).i107_mirror.is_none());
}

#[tokio::test]
async fn existing_profile_sockets_never_get_a_mirror() {
    let seen: Seen = Arc::default();
    let server = mock_browser(seen.clone()).await;
    let conn = Arc::new(CdpConnection::connect(&server.ws_url()).await.unwrap());
    conn.restrict_to_existing_profile();
    let (store, tid, tab_id) = store_with_tab();
    let t = tab(&store, &tid, &tab_id);
    let mirror = ensure_for_tab(
        MirrorMode::ShadowAudit,
        &store,
        "sess-a",
        &tid,
        &tab_id,
        &t,
        &conn,
        0,
    );
    assert!(mirror.is_none());
    tokio::time::sleep(std::time::Duration::from_millis(30)).await;
    assert!(seen.lock().unwrap().is_empty());
}

#[tokio::test]
async fn bootstrap_order_is_subscribe_attach_enable_frame_tree_document() {
    let seen: Seen = Arc::default();
    let server = mock_browser(seen.clone()).await;
    let conn = Arc::new(CdpConnection::connect(&server.ws_url()).await.unwrap());
    let (store, tid, tab_id) = store_with_tab();
    let t = tab(&store, &tid, &tab_id);
    let mirror = ensure_for_tab(
        MirrorMode::Shadow,
        &store,
        "sess-a",
        &tid,
        &tab_id,
        &t,
        &conn,
        0,
    )
    .expect("mirror");
    wait_until(|| mirror.coverage() == Coverage::Current).await;
    let methods: Vec<String> = seen
        .lock()
        .unwrap()
        .iter()
        .map(|(m, _)| m.clone())
        .collect();
    assert_eq!(
        methods,
        vec![
            "Target.attachToTarget",
            "Page.enable",
            "Inspector.enable",
            "Page.getFrameTree",
            "DOM.getDocument"
        ]
    );
    // Every call after attach runs on the one persistent event session.
    assert!(seen.lock().unwrap()[1..]
        .iter()
        .all(|(_, s)| s.as_deref() == Some(S)));
    // The mirror is held by the existing TabRecord owner and reused.
    let again = ensure_for_tab(
        MirrorMode::Shadow,
        &store,
        "sess-a",
        &tid,
        &tab_id,
        &tab(&store, &tid, &tab_id),
        &conn,
        0,
    )
    .unwrap();
    assert!(Arc::ptr_eq(&mirror, &again));
    assert_eq!(seen.lock().unwrap().len(), 5, "no second event session");
}

#[tokio::test]
async fn audit_cut_applies_events_queued_before_the_ping_reply() {
    let seen: Seen = Arc::default();
    let server = mock_browser(seen.clone()).await;
    let conn = Arc::new(CdpConnection::connect(&server.ws_url()).await.unwrap());
    let (store, tid, tab_id) = store_with_tab();
    let t = tab(&store, &tid, &tab_id);
    let mirror = ensure_for_tab(
        MirrorMode::ShadowAudit,
        &store,
        "sess-a",
        &tid,
        &tab_id,
        &t,
        &conn,
        0,
    )
    .unwrap();
    wait_until(|| mirror.coverage() == Coverage::Current).await;
    let window = mirror
        .audit_window_start()
        .expect("audit mode has a window");
    // The page mutates; the event is on the wire before this call's reply.
    conn.call(Some(S), "Test.emit", json!({})).await.unwrap();
    let mut fresh = page(1000);
    set_attr(&mut fresh, 103, "class", "emitted");
    let report = mirror
        .audit(window, &fresh, true, &semantic(), "sess-a")
        .await;
    assert_eq!(report.coverage, "current");
    assert_eq!(report.false_current, 0, "{report:?}");
    assert!(report.window_end_rev > window);
}

#[tokio::test]
async fn shadow_mode_has_no_audit_window() {
    let seen: Seen = Arc::default();
    let server = mock_browser(seen.clone()).await;
    let conn = Arc::new(CdpConnection::connect(&server.ws_url()).await.unwrap());
    let (store, tid, tab_id) = store_with_tab();
    let t = tab(&store, &tid, &tab_id);
    let mirror = ensure_for_tab(
        MirrorMode::Shadow,
        &store,
        "sess-a",
        &tid,
        &tab_id,
        &t,
        &conn,
        0,
    )
    .unwrap();
    assert!(mirror.audit_window_start().is_none());
}

#[tokio::test]
async fn session_end_drops_the_mirror_and_detaches_its_event_session() {
    let seen: Seen = Arc::default();
    let server = mock_browser(seen.clone()).await;
    let conn = Arc::new(CdpConnection::connect(&server.ws_url()).await.unwrap());
    let (store, tid, tab_id) = store_with_tab();
    let t = tab(&store, &tid, &tab_id);
    let mirror = ensure_for_tab(
        MirrorMode::Shadow,
        &store,
        "sess-a",
        &tid,
        &tab_id,
        &t,
        &conn,
        0,
    )
    .unwrap();
    wait_until(|| mirror.coverage() == Coverage::Current).await;
    let weak = Arc::downgrade(&mirror);
    drop(mirror);
    drop(t);
    store.remove_session("sess-a");
    assert!(
        weak.upgrade().is_none(),
        "the owner drop releases the mirror"
    );
    wait_until(|| {
        seen.lock()
            .unwrap()
            .iter()
            .any(|(m, _)| m == "Target.detachFromTarget")
    })
    .await;
}

#[tokio::test]
async fn navigation_invalidation_drops_the_mirror() {
    let seen: Seen = Arc::default();
    let server = mock_browser(seen.clone()).await;
    let conn = Arc::new(CdpConnection::connect(&server.ws_url()).await.unwrap());
    let (store, tid, tab_id) = store_with_tab();
    let t = tab(&store, &tid, &tab_id);
    let mirror = ensure_for_tab(
        MirrorMode::Shadow,
        &store,
        "sess-a",
        &tid,
        &tab_id,
        &t,
        &conn,
        0,
    )
    .unwrap();
    let weak = Arc::downgrade(&mirror);
    drop(mirror);
    drop(t);
    store.invalidate_tab_snapshots("sess-a", &tid, &tab_id);
    assert!(tab(&store, &tid, &tab_id).i107_mirror.is_none());
    assert!(weak.upgrade().is_none());
}

#[tokio::test]
async fn generation_invalidation_drops_the_mirror() {
    let seen: Seen = Arc::default();
    let server = mock_browser(seen.clone()).await;
    let conn = Arc::new(CdpConnection::connect(&server.ws_url()).await.unwrap());
    let (store, tid, tab_id) = store_with_tab();
    let t = tab(&store, &tid, &tab_id);
    let mirror = ensure_for_tab(
        MirrorMode::Shadow,
        &store,
        "sess-a",
        &tid,
        &tab_id,
        &t,
        &conn,
        0,
    )
    .unwrap();
    let weak = Arc::downgrade(&mirror);
    drop(mirror);
    drop(t);
    assert_eq!(store.invalidate_endpoint_generation(42, 0), 1);
    assert!(weak.upgrade().is_none());
}
