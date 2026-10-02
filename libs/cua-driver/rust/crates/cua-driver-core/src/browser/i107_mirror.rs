//! kvnloo/cua#107 lane CSHADOW: a shadow-mode DOM observation mirror.
//!
//! EXPERIMENT ONLY, measurement-only, not for promotion and not a public
//! contract. Default off: it exists only when `CUA_DRIVER_EXP_I107_MIRROR`
//! is exactly `shadow` or `shadow_audit`. Nothing it computes reaches a tool
//! caller; results go to the env-gated phase trace only.
//!
//! What it is: a bounded, read-only projection of one tab's DOM, held by the
//! existing [`super::store::TabRecord`] owner, so `remove_session`, the
//! session-end hook, `invalidate_endpoint_generation` and navigation
//! invalidation (`invalidate_tab_snapshots`) drop it with the tab.
//!
//! What it never does: mint, revive or validate a ref; touch the action
//! path, mutation revalidation or verification; or let event absence or an
//! unchanged revision stand in for a fresh read.
//!
//! Mechanics (kvnloo/cua#107 mirror-correctness rules 1-8):
//! - One persistent event session per tab, attached by the mirror itself
//!   (the dialog-session pattern: one session per target, enabled only after
//!   the subscription exists). The subscription is created before the
//!   session is attached, and every bootstrap/resync uses a brand-new
//!   session, so DOM events on the current session always follow its
//!   `DOM.getDocument` reply and events of older sessions are unrelated.
//! - Only DOM structure, node names, text node values and attributes are
//!   covered. Visibility, geometry, occlusion, focus, typed (property) values
//!   and every AX-derived fact have no establishing event and are always
//!   unknown. `inlineStyleInvalidated` makes `style` uncertain.
//! - Any inconsistency (missing node, missing sibling, duplicate insert,
//!   child-count mismatch, unmodeled DOM event), navigation, document
//!   replacement, session loss, crash, queue overflow, node-cap breach or a
//!   loader change turns coverage `unknown`, drops the projection and forces
//!   a rate-limited resync from a fresh `DOM.getDocument` on a new session.
//! - `shadow_audit` compares the mirror with the normal fresh `semantic_v2`
//!   read at every snapshot, bracketing that read between the mirror
//!   revision before its `DOM.getDocument` and an ordered round trip on the
//!   mirror's own session after it.

use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet, VecDeque};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex as StdMutex, OnceLock};
use std::time::{Duration, Instant};

use serde::Serialize;
use serde_json::{json, Value};
use tokio::sync::{mpsc, oneshot};

use super::cdp_ws::{CdpConnection, CdpEvent, CdpMethodPolicy};
use super::semantic::SemanticDocument;
use super::store::{BrowserActionKind, BrowserStore, BrowserVisibility, TabRecord};

/// Enables the mirror (`shadow` | `shadow_audit`); anything else is off.
pub(crate) const MIRROR_ENV: &str = "CUA_DRIVER_EXP_I107_MIRROR";
/// DC18 fault injection at the intake seam (experiment only).
pub(crate) const FAULT_ENV: &str = "CUA_DRIVER_EXP_I107_MIRROR_FAULT";
/// Hard caps frozen in the i107 pre-registration (`resource_budget_C`).
pub(crate) const MAX_NODES: usize = 20_000;
pub(crate) const MAX_QUEUED_EVENTS: usize = 10_000;
const RESYNC_MIN_INTERVAL: Duration = Duration::from_millis(250);
const MAX_RESYNCS: u32 = 50;
const DETACH_TIMEOUT: Duration = Duration::from_secs(1);
const CUT_TIMEOUT: Duration = Duration::from_secs(2);
/// Fixture mutation-id attribute, used only for event-lag correlation.
const OP_ATTR_PREFIX: &str = "data-i107-op";
const MAX_REPORTED_IDS: usize = 16;

/// Covered (event-established) fields per node.
pub(crate) const COVERED_FIELDS: &[&str] = &[
    "exists",
    "node_name",
    "node_value",
    "attributes",
    "children",
];
/// Fields no subscribed event establishes: always unknown in the mirror.
pub(crate) const UNESTABLISHED_FIELDS: &[&str] = &[
    "visibility",
    "geometry",
    "occlusion",
    "focus",
    "value_property",
    "ax_role",
    "ax_name",
    "ax_states",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum MirrorMode {
    Off,
    Shadow,
    ShadowAudit,
}

impl MirrorMode {
    pub(crate) fn parse(raw: Option<&str>) -> Self {
        match raw {
            Some("shadow") => Self::Shadow,
            Some("shadow_audit") => Self::ShadowAudit,
            _ => Self::Off,
        }
    }

    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Off => "off",
            Self::Shadow => "shadow",
            Self::ShadowAudit => "shadow_audit",
        }
    }
}

/// The process-wide mode, read once.
pub(crate) fn mode() -> MirrorMode {
    static MODE: OnceLock<MirrorMode> = OnceLock::new();
    *MODE.get_or_init(|| MirrorMode::parse(std::env::var(MIRROR_ENV).ok().as_deref()))
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum Coverage {
    Unknown(String),
    Current,
}

impl Coverage {
    fn label(&self) -> String {
        match self {
            Self::Current => "current".into(),
            Self::Unknown(reason) => format!("unknown:{reason}"),
        }
    }
}

/// What one event did to the projection.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum Intake {
    Applied,
    /// A known event that establishes no covered field.
    NoOp,
    /// Another session, or not about this target.
    Unrelated,
    /// Delivered before the bootstrap read completed.
    Buffered,
    /// Coverage is already unknown; there is no base to apply it to.
    DiscardedUnknown,
    /// Coverage became unknown; a resync is required.
    Invalidated(String),
    /// Coverage became unknown and the event session is gone.
    SessionLost(String),
}

#[derive(Debug, Clone)]
struct MNode {
    backend: i64,
    node_type: i64,
    name: String,
    value: String,
    attrs: BTreeMap<String, String>,
    /// Regular children (nodeIds, ordered). `None`: not pushed to this session.
    children: Option<Vec<i64>>,
    /// Shadow roots, content documents and template contents (nodeIds).
    attached: Vec<i64>,
    parent: Option<i64>,
    changed_rev: u64,
    uncertain_attrs: BTreeSet<String>,
}

/// Counters only; no page content.
#[derive(Debug, Default, Clone, Serialize)]
pub(crate) struct MirrorStats {
    pub(crate) events_total: u64,
    pub(crate) applied: u64,
    pub(crate) noop: u64,
    pub(crate) unrelated: u64,
    pub(crate) buffered_early: u64,
    pub(crate) discarded_unknown: u64,
    pub(crate) discarded_overflow: u64,
    pub(crate) invalidations: BTreeMap<String, u64>,
    pub(crate) bootstraps: u64,
    pub(crate) bootstrap_failures: u64,
    pub(crate) resyncs: u64,
    pub(crate) reconnects: u64,
    pub(crate) overflows: u64,
    pub(crate) node_cap_trips: u64,
    pub(crate) request_children: u64,
    pub(crate) faults_injected: u64,
    pub(crate) queue_hwm: usize,
    pub(crate) nodes_hwm: usize,
    pub(crate) by_method: BTreeMap<String, u64>,
    pub(crate) handle_ns: u64,
    pub(crate) bootstrap_ns: u64,
    pub(crate) construct_ns: u64,
    pub(crate) cut_ns: u64,
    pub(crate) audit_ns: u64,
    pub(crate) audits: u64,
}

/// The pure, synchronous mirror state machine (unit-testable, no I/O).
#[derive(Debug)]
pub(crate) struct MirrorState {
    pub(crate) mode: MirrorMode,
    pub(crate) cdp_target_id: String,
    pub(crate) generation: u64,
    pub(crate) instance: u64,
    session: Option<String>,
    bootstrapping: bool,
    early: VecDeque<CdpEvent>,
    frame: Option<(String, String)>,
    pub(crate) rev: u64,
    pub(crate) coverage: Coverage,
    nodes: HashMap<i64, MNode>,
    by_backend: HashMap<i64, i64>,
    need_children: Vec<i64>,
    op_marks: Vec<(String, u64)>,
    node_cap_tripped: bool,
    pub(crate) stats: MirrorStats,
}

fn as_i64(v: &Value, key: &str) -> Option<i64> {
    v.get(key).and_then(Value::as_i64)
}

fn attrs_of(v: &Value) -> BTreeMap<String, String> {
    let mut out = BTreeMap::new();
    if let Some(list) = v.get("attributes").and_then(Value::as_array) {
        for pair in list.chunks(2) {
            if let [name, value] = pair {
                out.insert(
                    name.as_str().unwrap_or("").to_owned(),
                    value.as_str().unwrap_or("").to_owned(),
                );
            }
        }
    }
    out
}

fn text_like(node_type: i64) -> bool {
    matches!(node_type, 3 | 4 | 8)
}

fn invalidating(method: &str) -> bool {
    matches!(
        method,
        "Page.frameNavigated"
            | "Page.documentOpened"
            | "Page.frameAttached"
            | "Page.frameDetached"
            | "Inspector.detached"
            | "Inspector.targetCrashed"
    )
}

impl MirrorState {
    pub(crate) fn new(mode: MirrorMode, cdp_target_id: String, generation: u64) -> Self {
        static INSTANCE: AtomicU64 = AtomicU64::new(1);
        Self {
            mode,
            cdp_target_id,
            generation,
            instance: INSTANCE.fetch_add(1, Ordering::Relaxed),
            session: None,
            bootstrapping: false,
            early: VecDeque::new(),
            frame: None,
            rev: 0,
            coverage: Coverage::Unknown("not_bootstrapped".into()),
            nodes: HashMap::new(),
            by_backend: HashMap::new(),
            need_children: Vec::new(),
            op_marks: Vec::new(),
            node_cap_tripped: false,
            stats: MirrorStats::default(),
        }
    }

    pub(crate) fn node_count(&self) -> usize {
        self.nodes.len()
    }

    pub(crate) fn take_need_children(&mut self) -> Vec<i64> {
        std::mem::take(&mut self.need_children)
    }

    fn take_op_marks(&mut self) -> Vec<(String, u64)> {
        std::mem::take(&mut self.op_marks)
    }

    fn clear_projection(&mut self) {
        self.nodes.clear();
        self.by_backend.clear();
        self.need_children.clear();
    }

    /// Coverage becomes unknown and the projection is dropped; the mirror
    /// never keeps advertising state after a gap.
    pub(crate) fn invalidate(&mut self, reason: &str) -> Intake {
        self.coverage = Coverage::Unknown(reason.to_owned());
        self.clear_projection();
        *self
            .stats
            .invalidations
            .entry(reason.to_owned())
            .or_default() += 1;
        Intake::Invalidated(reason.to_owned())
    }

    pub(crate) fn overflow(&mut self, queued: usize) {
        self.stats.queue_hwm = self.stats.queue_hwm.max(queued);
        self.stats.overflows += 1;
        self.invalidate("overflow");
    }

    pub(crate) fn begin_bootstrap(&mut self, session: String) {
        self.session = Some(session);
        self.bootstrapping = true;
        self.early.clear();
        self.frame = None;
        self.clear_projection();
        self.coverage = Coverage::Unknown("bootstrap".into());
    }

    /// Build the projection from this session's own fresh `DOM.getDocument`.
    pub(crate) fn complete_bootstrap(
        &mut self,
        frame: Option<(String, String)>,
        document: &Value,
    ) -> Result<(), String> {
        let started = Instant::now();
        self.bootstrapping = false;
        self.frame = frame;
        self.rev += 1;
        let rev = self.rev;
        let root = document.get("root").cloned().unwrap_or(Value::Null);
        let built = self.insert_subtree(&root, None, rev);
        self.stats.construct_ns += started.elapsed().as_nanos() as u64;
        if let Err(reason) = built {
            self.stats.bootstrap_failures += 1;
            if reason == "node_cap" {
                self.node_cap_tripped = true;
                self.stats.node_cap_trips += 1;
            }
            self.invalidate(&reason);
            return Err(reason);
        }
        self.stats.bootstraps += 1;
        self.stats.nodes_hwm = self.stats.nodes_hwm.max(self.nodes.len());
        let early = std::mem::take(&mut self.early);
        let poisoned = early
            .iter()
            .any(|event| event.method.starts_with("DOM.") || invalidating(&event.method));
        if poisoned {
            // No reliable boundary between these events and the read.
            self.invalidate("pre_bootstrap_event");
            return Err("pre_bootstrap_event".into());
        }
        self.coverage = Coverage::Current;
        Ok(())
    }

    pub(crate) fn bootstrap_failed(&mut self, reason: &str) {
        self.bootstrapping = false;
        self.stats.bootstrap_failures += 1;
        self.invalidate(reason);
    }

    fn insert_subtree(&mut self, v: &Value, parent: Option<i64>, rev: u64) -> Result<i64, String> {
        let id = as_i64(v, "nodeId").ok_or_else(|| "node_without_id".to_owned())?;
        if self.nodes.contains_key(&id) {
            return Err("duplicate_node".into());
        }
        let node_type = as_i64(v, "nodeType").unwrap_or(0);
        let listed = v.get("children").and_then(Value::as_array);
        let children = match (listed, as_i64(v, "childNodeCount")) {
            (Some(_), _) => Some(Vec::new()),
            (None, Some(count)) if count > 0 => None,
            _ => Some(Vec::new()),
        };
        if children.is_none() {
            self.need_children.push(id);
        }
        let backend = as_i64(v, "backendNodeId").unwrap_or(0);
        self.nodes.insert(
            id,
            MNode {
                backend,
                node_type,
                name: v
                    .get("nodeName")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_owned(),
                value: v
                    .get("nodeValue")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_owned(),
                attrs: attrs_of(v),
                children,
                attached: Vec::new(),
                parent,
                changed_rev: rev,
                uncertain_attrs: BTreeSet::new(),
            },
        );
        self.by_backend.insert(backend, id);
        if self.nodes.len() > MAX_NODES {
            return Err("node_cap".into());
        }
        if let Some(list) = listed {
            let mut ids = Vec::with_capacity(list.len());
            for child in list {
                ids.push(self.insert_subtree(child, Some(id), rev)?);
            }
            if let Some(node) = self.nodes.get_mut(&id) {
                node.children = Some(ids);
            }
        }
        let mut attached = Vec::new();
        if let Some(roots) = v.get("shadowRoots").and_then(Value::as_array) {
            for root in roots {
                attached.push(self.insert_subtree(root, Some(id), rev)?);
            }
        }
        for key in ["contentDocument", "templateContent"] {
            if let Some(doc) = v.get(key).filter(|d| d.is_object()) {
                attached.push(self.insert_subtree(doc, Some(id), rev)?);
            }
        }
        if let Some(node) = self.nodes.get_mut(&id) {
            node.attached = attached;
        }
        // Pseudo elements are outside the covered projection on both sides.
        Ok(id)
    }

    fn remove_subtree(&mut self, id: i64) {
        let mut stack = vec![id];
        while let Some(next) = stack.pop() {
            if let Some(node) = self.nodes.remove(&next) {
                if self.by_backend.get(&node.backend) == Some(&next) {
                    self.by_backend.remove(&node.backend);
                }
                stack.extend(node.children.into_iter().flatten());
                stack.extend(node.attached);
            }
        }
    }

    fn touch(&mut self, id: i64) {
        let rev = self.rev;
        if let Some(node) = self.nodes.get_mut(&id) {
            node.changed_rev = rev;
        }
    }

    /// The intake seam: every delivered CDP event passes here exactly once.
    pub(crate) fn intake(&mut self, event: &CdpEvent) -> Intake {
        let started = Instant::now();
        self.stats.events_total += 1;
        match self.stats.by_method.get_mut(&event.method) {
            Some(count) => *count += 1,
            None => {
                self.stats.by_method.insert(event.method.clone(), 1);
            }
        }
        let outcome = self.classify_and_apply(event);
        match &outcome {
            Intake::Applied => self.stats.applied += 1,
            Intake::NoOp => self.stats.noop += 1,
            Intake::Unrelated => self.stats.unrelated += 1,
            Intake::Buffered => self.stats.buffered_early += 1,
            Intake::DiscardedUnknown => self.stats.discarded_unknown += 1,
            Intake::Invalidated(_) | Intake::SessionLost(_) => {}
        }
        self.stats.nodes_hwm = self.stats.nodes_hwm.max(self.nodes.len());
        self.stats.handle_ns += started.elapsed().as_nanos() as u64;
        outcome
    }

    fn classify_and_apply(&mut self, event: &CdpEvent) -> Intake {
        let Some(event_session) = event.session_id.as_deref() else {
            return self.browser_level(event);
        };
        if Some(event_session) != self.session.as_deref() {
            return Intake::Unrelated;
        }
        if self.bootstrapping {
            if self.early.len() >= MAX_QUEUED_EVENTS {
                self.stats.overflows += 1;
                self.early.clear();
                return self.invalidate("overflow");
            }
            self.early.push_back(event.clone());
            return Intake::Buffered;
        }
        match event.method.as_str() {
            "Inspector.detached" => return self.lose("inspector_detached"),
            "Inspector.targetCrashed" => return self.lose("target_crashed"),
            _ => {}
        }
        if self.coverage != Coverage::Current {
            return Intake::DiscardedUnknown;
        }
        let p = &event.params;
        match event.method.as_str() {
            "DOM.documentUpdated" => self.invalidate("document_updated"),
            "Page.frameNavigated" => self.invalidate("frame_navigated"),
            "Page.documentOpened" => self.invalidate("document_opened"),
            "Page.frameAttached" | "Page.frameDetached" => self.invalidate("frame_tree_changed"),
            "Inspector.targetReloadedAfterCrash" => self.invalidate("reloaded_after_crash"),
            "DOM.setChildNodes" => self.set_child_nodes(p),
            "DOM.childNodeInserted" => self.child_inserted(p),
            "DOM.childNodeRemoved" => self.child_removed(p),
            "DOM.childNodeCountUpdated" => {
                let (Some(id), Some(count)) = (as_i64(p, "nodeId"), as_i64(p, "childNodeCount"))
                else {
                    return self.invalidate("malformed_event");
                };
                match self.nodes.get(&id).map(|node| node.children.as_ref()) {
                    None => self.invalidate("missing_node"),
                    Some(Some(children)) if children.len() as i64 != count => {
                        self.invalidate("child_count_mismatch")
                    }
                    Some(_) => Intake::NoOp,
                }
            }
            "DOM.attributeModified" => {
                let (Some(id), Some(name)) =
                    (as_i64(p, "nodeId"), p.get("name").and_then(Value::as_str))
                else {
                    return self.invalidate("malformed_event");
                };
                let value = p.get("value").and_then(Value::as_str).unwrap_or("");
                if !self.nodes.contains_key(&id) {
                    return self.invalidate("missing_node");
                }
                self.rev += 1;
                let rev = self.rev;
                if let Some(node) = self.nodes.get_mut(&id) {
                    node.attrs.insert(name.to_owned(), value.to_owned());
                    node.uncertain_attrs.remove(name);
                    node.changed_rev = rev;
                }
                if self.mode == MirrorMode::ShadowAudit && name.starts_with(OP_ATTR_PREFIX) {
                    self.op_marks.push((value.chars().take(40).collect(), rev));
                }
                Intake::Applied
            }
            "DOM.attributeRemoved" => {
                let (Some(id), Some(name)) =
                    (as_i64(p, "nodeId"), p.get("name").and_then(Value::as_str))
                else {
                    return self.invalidate("malformed_event");
                };
                if !self.nodes.contains_key(&id) {
                    return self.invalidate("missing_node");
                }
                self.rev += 1;
                let rev = self.rev;
                if let Some(node) = self.nodes.get_mut(&id) {
                    node.attrs.remove(name);
                    node.uncertain_attrs.remove(name);
                    node.changed_rev = rev;
                }
                Intake::Applied
            }
            "DOM.characterDataModified" => {
                let Some(id) = as_i64(p, "nodeId") else {
                    return self.invalidate("malformed_event");
                };
                if !self.nodes.contains_key(&id) {
                    return self.invalidate("missing_node");
                }
                self.rev += 1;
                let rev = self.rev;
                if let Some(node) = self.nodes.get_mut(&id) {
                    node.value = p
                        .get("characterData")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_owned();
                    node.changed_rev = rev;
                }
                Intake::Applied
            }
            "DOM.shadowRootPushed" => {
                let Some(host) = as_i64(p, "hostId") else {
                    return self.invalidate("malformed_event");
                };
                if !self.nodes.contains_key(&host) {
                    return self.invalidate("missing_node");
                }
                self.rev += 1;
                let rev = self.rev;
                let root = p.get("root").cloned().unwrap_or(Value::Null);
                match self.insert_subtree(&root, Some(host), rev) {
                    Ok(id) => {
                        if let Some(node) = self.nodes.get_mut(&host) {
                            node.attached.push(id);
                            node.changed_rev = rev;
                        }
                        Intake::Applied
                    }
                    Err(reason) => self.structural_failure(&reason),
                }
            }
            "DOM.shadowRootPopped" => {
                let (Some(host), Some(root)) = (as_i64(p, "hostId"), as_i64(p, "rootId")) else {
                    return self.invalidate("malformed_event");
                };
                let known = self
                    .nodes
                    .get(&host)
                    .is_some_and(|node| node.attached.contains(&root));
                if !known {
                    return self.invalidate("missing_node");
                }
                self.rev += 1;
                if let Some(node) = self.nodes.get_mut(&host) {
                    node.attached.retain(|id| *id != root);
                }
                self.touch(host);
                self.remove_subtree(root);
                Intake::Applied
            }
            "DOM.inlineStyleInvalidated" => {
                let ids: Vec<i64> = p
                    .get("nodeIds")
                    .and_then(Value::as_array)
                    .map(|ids| ids.iter().filter_map(Value::as_i64).collect())
                    .unwrap_or_default();
                if ids.iter().any(|id| !self.nodes.contains_key(id)) {
                    return self.invalidate("missing_node");
                }
                for id in ids {
                    if let Some(node) = self.nodes.get_mut(&id) {
                        node.uncertain_attrs.insert("style".into());
                    }
                }
                Intake::NoOp
            }
            // Known DOM events outside the covered fields.
            "DOM.pseudoElementAdded"
            | "DOM.pseudoElementRemoved"
            | "DOM.topLayerElementsUpdated"
            | "DOM.scrollableFlagUpdated"
            | "DOM.affectedByStartingStylesFlagUpdated"
            | "DOM.adoptedStyleSheetsModified" => Intake::NoOp,
            m if m.starts_with("DOM.") => self.invalidate(&format!("unmodeled:{m}")),
            _ => Intake::NoOp,
        }
    }

    fn lose(&mut self, reason: &str) -> Intake {
        self.invalidate(reason);
        Intake::SessionLost(reason.to_owned())
    }

    fn browser_level(&mut self, event: &CdpEvent) -> Intake {
        let p = &event.params;
        match event.method.as_str() {
            "Target.detachedFromTarget"
                if self.session.is_some()
                    && p.get("sessionId").and_then(Value::as_str) == self.session.as_deref() =>
            {
                self.lose("session_detached")
            }
            "Target.targetCrashed" | "Target.targetDestroyed"
                if p.get("targetId").and_then(Value::as_str)
                    == Some(self.cdp_target_id.as_str()) =>
            {
                self.lose("target_gone")
            }
            _ => Intake::Unrelated,
        }
    }

    fn structural_failure(&mut self, reason: &str) -> Intake {
        if reason == "node_cap" {
            self.node_cap_tripped = true;
            self.stats.node_cap_trips += 1;
        }
        self.invalidate(reason)
    }

    fn set_child_nodes(&mut self, p: &Value) -> Intake {
        let Some(parent) = as_i64(p, "parentId") else {
            return self.invalidate("malformed_event");
        };
        let nodes = p
            .get("nodes")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default();
        match self.nodes.get(&parent).map(|node| node.children.clone()) {
            None => return self.invalidate("missing_node"),
            Some(Some(existing)) if !existing.is_empty() => {
                return self.invalidate("unexpected_set_child_nodes")
            }
            Some(_) => {}
        }
        self.rev += 1;
        let rev = self.rev;
        let mut ids = Vec::with_capacity(nodes.len());
        for node in &nodes {
            match self.insert_subtree(node, Some(parent), rev) {
                Ok(id) => ids.push(id),
                Err(reason) => return self.structural_failure(&reason),
            }
        }
        if let Some(node) = self.nodes.get_mut(&parent) {
            node.children = Some(ids);
            node.changed_rev = rev;
        }
        self.need_children.retain(|id| *id != parent);
        Intake::Applied
    }

    fn child_inserted(&mut self, p: &Value) -> Intake {
        let (Some(parent), Some(previous)) =
            (as_i64(p, "parentNodeId"), as_i64(p, "previousNodeId"))
        else {
            return self.invalidate("malformed_event");
        };
        let position = match self.nodes.get(&parent).map(|node| node.children.as_ref()) {
            None => return self.invalidate("missing_node"),
            Some(None) => return self.invalidate("insert_into_unpushed"),
            Some(Some(_)) if previous == 0 => 0,
            Some(Some(children)) => match children.iter().position(|id| *id == previous) {
                Some(index) => index + 1,
                None => return self.invalidate("missing_previous"),
            },
        };
        self.rev += 1;
        let rev = self.rev;
        let node = p.get("node").cloned().unwrap_or(Value::Null);
        match self.insert_subtree(&node, Some(parent), rev) {
            Ok(id) => {
                if let Some(parent_node) = self.nodes.get_mut(&parent) {
                    if let Some(children) = parent_node.children.as_mut() {
                        children.insert(position, id);
                    }
                    parent_node.changed_rev = rev;
                }
                Intake::Applied
            }
            Err(reason) => self.structural_failure(&reason),
        }
    }

    fn child_removed(&mut self, p: &Value) -> Intake {
        let (Some(parent), Some(id)) = (as_i64(p, "parentNodeId"), as_i64(p, "nodeId")) else {
            return self.invalidate("malformed_event");
        };
        let found = self.nodes.contains_key(&id)
            && self
                .nodes
                .get(&parent)
                .and_then(|node| node.children.as_ref())
                .is_some_and(|children| children.contains(&id));
        if !found {
            return self.invalidate("missing_node");
        }
        self.rev += 1;
        if let Some(children) = self
            .nodes
            .get_mut(&parent)
            .and_then(|node| node.children.as_mut())
        {
            children.retain(|child| *child != id);
        }
        self.touch(parent);
        self.remove_subtree(id);
        Intake::Applied
    }

    fn label_of(&self, node: &MNode) -> Option<String> {
        if let Some(label) = node.attrs.get("aria-label") {
            return Some(label.trim().to_owned());
        }
        if node.name == "INPUT" {
            return node.attrs.get("value").map(|value| value.trim().to_owned());
        }
        let mut text = String::new();
        let mut stack: Vec<i64> = node.children.clone()?.into_iter().rev().collect();
        while let Some(id) = stack.pop() {
            let child = self.nodes.get(&id)?;
            if child.node_type == 3 {
                text.push_str(&child.value);
            }
            stack.extend(child.children.clone()?.into_iter().rev());
        }
        Some(text.trim().to_owned())
    }

    /// DOM-level look-alike count for (button, "Submit"). A diagnostic
    /// estimate only: the real match set depends on AX names and visibility,
    /// which no subscribed event establishes.
    fn dom_submit_estimate(&self) -> usize {
        self.nodes
            .values()
            .filter(|node| node.node_type == 1)
            .filter(|node| {
                node.name == "BUTTON"
                    || (node.name == "INPUT"
                        && matches!(
                            node.attrs.get("type").map(String::as_str),
                            Some("submit" | "button")
                        ))
                    || node.attrs.get("role").map(String::as_str) == Some("button")
            })
            .filter(|node| self.label_of(node).as_deref() == Some("Submit"))
            .count()
    }

    fn children_backends(&self, node: &MNode) -> Option<Vec<i64>> {
        node.children.as_ref().map(|children| {
            children
                .iter()
                .filter_map(|id| self.nodes.get(id).map(|child| child.backend))
                .collect()
        })
    }

    fn differs(&self, node: &MNode, fresh: &FreshNode) -> bool {
        node.name != fresh.name
            || (text_like(fresh.node_type) && node.value != fresh.value)
            || node.attrs != fresh.attrs
            || self
                .children_backends(node)
                .is_some_and(|children| children != fresh.children)
    }

    fn under_changed(&self, node: &MNode, window_start_rev: u64) -> bool {
        let mut cursor = node.parent;
        let mut hops = 0;
        while let Some(id) = cursor {
            let Some(ancestor) = self.nodes.get(&id) else {
                return false;
            };
            if ancestor.changed_rev > window_start_rev {
                return true;
            }
            cursor = ancestor.parent;
            hops += 1;
            if hops > 4096 {
                return false;
            }
        }
        false
    }

    fn nearest_mirrored_ancestor(&self, fresh: &FreshTree, backend: i64) -> Option<&MNode> {
        let mut cursor = fresh.nodes.get(&backend).and_then(|node| node.parent);
        let mut hops = 0;
        while let Some(parent) = cursor {
            if let Some(node) = self
                .by_backend
                .get(&parent)
                .and_then(|id| self.nodes.get(id))
            {
                return Some(node);
            }
            cursor = fresh.nodes.get(&parent).and_then(|node| node.parent);
            hops += 1;
            if hops > 4096 {
                return None;
            }
        }
        None
    }

    /// Compare covered fields with a fresh read (`shadow_audit`). Changes the
    /// mirror applied after `window_start_rev` may postdate the fresh read
    /// and are counted as ambiguous, never as agreement or false-current.
    pub(crate) fn audit(
        &self,
        window_start_rev: u64,
        fresh_document: &Value,
        fresh_complete: bool,
        semantic: &SemanticDocument,
    ) -> AuditReport {
        let fresh = FreshTree::build(fresh_document);
        let mut report = AuditReport {
            coverage: self.coverage.label(),
            window_start_rev,
            window_end_rev: self.rev,
            fresh_complete,
            fresh_nodes: fresh.nodes.len(),
            mirror_nodes: self.nodes.len(),
            ..AuditReport::default()
        };
        let is_submit = |role: &str, name: Option<&str>| role == "button" && name == Some("Submit");
        report.match_set.fresh_count = semantic
            .nodes
            .iter()
            .filter(|node| is_submit(&node.role, node.name.as_deref()))
            .count();
        report.match_set.fresh_actionable_visible = semantic
            .nodes
            .iter()
            .filter(|node| is_submit(&node.role, node.name.as_deref()))
            .filter(|node| {
                matches!(
                    node.visibility,
                    BrowserVisibility::InViewport | BrowserVisibility::NearViewport
                ) && node.actions.contains(&BrowserActionKind::Click)
            })
            .count();
        report.match_set.mirror_status = "unknown".into();
        let seeds: Vec<i64> = semantic
            .nodes
            .iter()
            .filter(|node| {
                is_submit(&node.role, node.name.as_deref())
                    || matches!(node.role.as_str(), "textbox" | "searchbox")
            })
            .filter_map(|node| node.backend_node_id)
            .collect();
        let relevant = fresh.closure(&seeds);
        report.action_relevant_nodes = relevant.len();
        let unestablished = (relevant.len() * UNESTABLISHED_FIELDS.len()) as u64;
        report.action_relevant_field_checks += unestablished;
        report.unknown_action_relevant += unestablished;

        if self.coverage != Coverage::Current || !fresh_complete {
            if self.coverage == Coverage::Current {
                report.coverage = "current_fresh_incomplete".into();
            }
            let covered = (relevant.len() * COVERED_FIELDS.len()) as u64;
            report.action_relevant_field_checks += covered;
            report.unknown_action_relevant += covered;
            return report;
        }
        report.match_set.mirror_dom_estimate = Some(self.dom_submit_estimate());
        report.match_set.estimate_agrees =
            Some(report.match_set.mirror_dom_estimate == Some(report.match_set.fresh_count));

        let mut fc_ids: Vec<i64> = Vec::new();
        let mut false_current = |report: &mut AuditReport, field: &str, backend: i64| {
            report.false_current += 1;
            report.raw_differences_including_window += 1;
            *report
                .false_current_fields
                .entry(field.to_owned())
                .or_default() += 1;
            if relevant.contains(&backend) {
                report.false_current_action_relevant += 1;
            }
            if fc_ids.len() < MAX_REPORTED_IDS && !fc_ids.contains(&backend) {
                fc_ids.push(backend);
            }
        };

        for (backend, f) in &fresh.nodes {
            let ar = relevant.contains(backend);
            if ar {
                report.action_relevant_field_checks += COVERED_FIELDS.len() as u64;
            }
            let Some(node) = self
                .by_backend
                .get(backend)
                .and_then(|id| self.nodes.get(id))
            else {
                match self.nearest_mirrored_ancestor(&fresh, *backend) {
                    Some(anc) if anc.changed_rev > window_start_rev => {
                        report.ambiguous_in_flight += 1;
                        report.raw_differences_including_window += 1;
                    }
                    Some(anc) if anc.children.is_none() => {
                        report.unknown_checks += 1;
                        if ar {
                            report.unknown_action_relevant += COVERED_FIELDS.len() as u64;
                        }
                    }
                    _ => false_current(&mut report, "exists", *backend),
                }
                continue;
            };
            report.compared_nodes += 1;
            if node.changed_rev > window_start_rev {
                report.ambiguous_in_flight += 1;
                if self.differs(node, f) {
                    report.raw_differences_including_window += 1;
                }
                continue;
            }
            report.field_checks += 1;
            if node.name == f.name {
                report.agree += 1;
            } else {
                false_current(&mut report, "node_name", *backend);
            }
            if text_like(f.node_type) {
                report.field_checks += 1;
                if node.value == f.value {
                    report.agree += 1;
                } else {
                    false_current(&mut report, "node_value", *backend);
                }
            }
            let names: BTreeSet<&String> = node.attrs.keys().chain(f.attrs.keys()).collect();
            for name in names {
                report.field_checks += 1;
                if node.uncertain_attrs.contains(name) {
                    report.unknown_checks += 1;
                    if ar {
                        report.unknown_action_relevant += 1;
                    }
                } else if node.attrs.get(name) == f.attrs.get(name) {
                    report.agree += 1;
                } else {
                    false_current(&mut report, "attributes", *backend);
                }
            }
            report.field_checks += 1;
            match self.children_backends(node) {
                None => {
                    report.unknown_checks += 1;
                    if ar {
                        report.unknown_action_relevant += 1;
                    }
                }
                Some(children) if children == f.children => report.agree += 1,
                Some(_) => false_current(&mut report, "children", *backend),
            }
        }
        for node in self.nodes.values() {
            if fresh.nodes.contains_key(&node.backend) {
                continue;
            }
            if node.changed_rev > window_start_rev || self.under_changed(node, window_start_rev) {
                report.ambiguous_in_flight += 1;
                report.raw_differences_including_window += 1;
            } else {
                false_current(&mut report, "exists", node.backend);
            }
        }
        report.false_current_backend_ids = fc_ids;
        report
    }
}

#[derive(Debug)]
struct FreshNode {
    node_type: i64,
    name: String,
    value: String,
    attrs: BTreeMap<String, String>,
    children: Vec<i64>,
    attached: Vec<i64>,
    parent: Option<i64>,
}

/// The normal snapshot's fresh `DOM.getDocument`, keyed by backendNodeId
/// (nodeIds are per session and never compared).
#[derive(Debug, Default)]
struct FreshTree {
    nodes: HashMap<i64, FreshNode>,
}

impl FreshTree {
    fn build(document: &Value) -> Self {
        let mut tree = Self::default();
        let root = document.get("root").cloned().unwrap_or(Value::Null);
        let mut stack: Vec<(Value, Option<i64>)> = vec![(root, None)];
        while let Some((v, parent)) = stack.pop() {
            let Some(backend) = as_i64(&v, "backendNodeId") else {
                continue;
            };
            let children_values: Vec<Value> = v
                .get("children")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            let mut attached_values: Vec<Value> = v
                .get("shadowRoots")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            for key in ["contentDocument", "templateContent"] {
                if let Some(doc) = v.get(key).filter(|d| d.is_object()) {
                    attached_values.push(doc.clone());
                }
            }
            let ids = |values: &[Value]| -> Vec<i64> {
                values
                    .iter()
                    .filter_map(|child| as_i64(child, "backendNodeId"))
                    .collect()
            };
            tree.nodes.insert(
                backend,
                FreshNode {
                    node_type: as_i64(&v, "nodeType").unwrap_or(0),
                    name: v
                        .get("nodeName")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_owned(),
                    value: v
                        .get("nodeValue")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_owned(),
                    attrs: attrs_of(&v),
                    children: ids(&children_values),
                    attached: ids(&attached_values),
                    parent,
                },
            );
            for child in children_values.into_iter().chain(attached_values) {
                stack.push((child, Some(backend)));
            }
        }
        tree
    }

    /// Seeds plus their ancestor chains and descendants: the
    /// action-relevant scope (control, its form/ancestors, its name text).
    fn closure(&self, seeds: &[i64]) -> HashSet<i64> {
        let mut out = HashSet::new();
        for seed in seeds {
            let mut cursor = Some(*seed);
            let mut hops = 0;
            while let Some(id) = cursor {
                out.insert(id);
                cursor = self.nodes.get(&id).and_then(|node| node.parent);
                hops += 1;
                if hops > 4096 {
                    break;
                }
            }
            let mut stack = vec![*seed];
            while let Some(id) = stack.pop() {
                if let Some(node) = self.nodes.get(&id) {
                    for child in node.children.iter().chain(node.attached.iter()) {
                        if out.insert(*child) {
                            stack.push(*child);
                        }
                    }
                }
            }
        }
        out.retain(|id| self.nodes.contains_key(id));
        out
    }
}

#[derive(Debug, Default, Clone, Serialize, PartialEq, Eq)]
pub(crate) struct MatchSet {
    pub(crate) fresh_count: usize,
    pub(crate) fresh_actionable_visible: usize,
    pub(crate) mirror_status: String,
    pub(crate) mirror_dom_estimate: Option<usize>,
    pub(crate) estimate_agrees: Option<bool>,
}

/// One shadow-audit comparison. Counts, field names and backendNodeIds
/// only: no page text, attribute values or control names.
#[derive(Debug, Default, Clone, Serialize, PartialEq, Eq)]
pub(crate) struct AuditReport {
    pub(crate) coverage: String,
    pub(crate) window_start_rev: u64,
    pub(crate) window_end_rev: u64,
    pub(crate) fresh_complete: bool,
    pub(crate) fresh_nodes: usize,
    pub(crate) mirror_nodes: usize,
    pub(crate) compared_nodes: usize,
    pub(crate) field_checks: u64,
    pub(crate) agree: u64,
    pub(crate) false_current: u64,
    pub(crate) false_current_action_relevant: u64,
    pub(crate) false_current_fields: BTreeMap<String, u64>,
    pub(crate) false_current_backend_ids: Vec<i64>,
    pub(crate) ambiguous_in_flight: u64,
    pub(crate) raw_differences_including_window: u64,
    pub(crate) unknown_checks: u64,
    pub(crate) action_relevant_nodes: usize,
    pub(crate) action_relevant_field_checks: u64,
    pub(crate) unknown_action_relevant: u64,
    pub(crate) match_set: MatchSet,
}

impl AuditReport {
    fn void(&mut self, reason: &str) {
        self.coverage = format!("unknown:{reason}");
        self.false_current = 0;
        self.false_current_action_relevant = 0;
        self.false_current_fields.clear();
        self.false_current_backend_ids.clear();
    }
}

// ── DC18 fault injection at the intake seam ─────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum FaultPlan {
    None,
    /// Drop every Nth DOM event of the current session (missing).
    Drop(u64),
    /// Deliver every Nth DOM event twice (duplicate).
    Duplicate(u64),
    /// Hold every Nth DOM event for D ms while later events pass (delayed).
    Delay(u64, u64),
    /// Swap every Nth DOM event with the next one (reordered).
    Swap(u64),
    /// One synthetic DOM event before the bootstrap read completes (early).
    Early,
    /// Add a copy of every Nth event tagged with an unrelated session.
    Foreign(u64),
    /// Add a copy of every Nth event tagged with a previous-generation session.
    Stale(u64),
    /// Simulate one queue overflow after N DOM events.
    Overflow(u64),
    /// Simulate one consumer reconnect after N DOM events.
    Reconnect(u64),
}

impl FaultPlan {
    pub(crate) fn parse(raw: Option<&str>) -> Self {
        let Some(raw) = raw else { return Self::None };
        let mut parts = raw.split(':');
        let kind = parts.next().unwrap_or("");
        let numbers: Vec<u64> = parts.filter_map(|part| part.parse().ok()).collect();
        let n = numbers.first().copied().unwrap_or(0);
        let plan = match (kind, numbers.len()) {
            ("early", 0) => return Self::Early,
            ("drop", 1) => Self::Drop(n),
            ("dup", 1) => Self::Duplicate(n),
            ("delay", 2) => Self::Delay(n, numbers[1]),
            ("swap", 1) => Self::Swap(n),
            ("foreign", 1) => Self::Foreign(n),
            ("stale", 1) => Self::Stale(n),
            ("overflow", 1) => Self::Overflow(n),
            ("reconnect", 1) => Self::Reconnect(n),
            _ => return Self::None,
        };
        if n == 0 {
            Self::None
        } else {
            plan
        }
    }

    fn from_env() -> Self {
        Self::parse(std::env::var(FAULT_ENV).ok().as_deref())
    }
}

#[derive(Debug, Default)]
pub(crate) struct FaultOut {
    pub(crate) deliver: Vec<CdpEvent>,
    pub(crate) injected: Option<String>,
    pub(crate) overflow: bool,
    pub(crate) reconnect: bool,
}

#[derive(Debug)]
pub(crate) struct FaultInjector {
    plan: FaultPlan,
    counter: u64,
    held: VecDeque<(Instant, CdpEvent)>,
    swap_slot: Option<CdpEvent>,
    fired: bool,
    early_pending: bool,
}

impl FaultInjector {
    pub(crate) fn new(plan: FaultPlan) -> Self {
        let early_pending = plan == FaultPlan::Early;
        Self {
            plan,
            counter: 0,
            held: VecDeque::new(),
            swap_slot: None,
            fired: false,
            early_pending,
        }
    }

    fn take_early(&mut self) -> bool {
        std::mem::replace(&mut self.early_pending, false)
    }

    pub(crate) fn next_due(&self) -> Option<Instant> {
        self.held.front().map(|(due, _)| *due)
    }

    pub(crate) fn release_due(&mut self, now: Instant) -> Vec<CdpEvent> {
        let mut out = Vec::new();
        while self.held.front().is_some_and(|(due, _)| *due <= now) {
            if let Some((_, event)) = self.held.pop_front() {
                out.push(event);
            }
        }
        out
    }

    pub(crate) fn filter(&mut self, event: CdpEvent, session: &str, now: Instant) -> FaultOut {
        let mut out = FaultOut::default();
        let counted =
            event.method.starts_with("DOM.") && event.session_id.as_deref() == Some(session);
        if !counted || self.plan == FaultPlan::None || self.plan == FaultPlan::Early {
            out.deliver.push(event);
            return out;
        }
        self.counter += 1;
        let counter = self.counter;
        let nth = |n: u64| n > 0 && counter % n == 0;
        match self.plan.clone() {
            FaultPlan::Drop(n) if nth(n) => out.injected = Some("drop".into()),
            FaultPlan::Duplicate(n) if nth(n) => {
                out.deliver.push(event.clone());
                out.deliver.push(event);
                out.injected = Some("duplicate".into());
            }
            FaultPlan::Delay(n, ms) if nth(n) => {
                self.held
                    .push_back((now + Duration::from_millis(ms), event));
                out.injected = Some("delay".into());
            }
            FaultPlan::Swap(n) => match self.swap_slot.take() {
                Some(previous) => {
                    out.deliver.push(event);
                    out.deliver.push(previous);
                }
                None if nth(n) => {
                    self.swap_slot = Some(event);
                    out.injected = Some("swap".into());
                }
                None => out.deliver.push(event),
            },
            FaultPlan::Foreign(n) if nth(n) => {
                let mut copy = event.clone();
                copy.session_id = Some(format!("{session}-foreign"));
                out.deliver.push(event);
                out.deliver.push(copy);
                out.injected = Some("foreign".into());
            }
            FaultPlan::Stale(n) if nth(n) => {
                let mut copy = event.clone();
                copy.session_id = Some(format!("{session}-previous-generation"));
                out.deliver.push(event);
                out.deliver.push(copy);
                out.injected = Some("stale".into());
            }
            FaultPlan::Overflow(n) if !self.fired && counter >= n => {
                self.fired = true;
                out.overflow = true;
                out.deliver.push(event);
                out.injected = Some("overflow".into());
            }
            FaultPlan::Reconnect(n) if !self.fired && counter >= n => {
                self.fired = true;
                out.reconnect = true;
                out.deliver.push(event);
                out.injected = Some("reconnect".into());
            }
            _ => out.deliver.push(event),
        }
        out
    }
}

// ── owner integration and the event task ────────────────────────────────

#[derive(Debug, Clone)]
struct CutResult {
    rev: u64,
    ping_ok: bool,
}

/// The per-tab handle stored on [`TabRecord`]. Dropping the last handle
/// (session end, generation invalidation, navigation invalidation) stops
/// the event task, which then detaches its event session.
pub(crate) struct TabMirror {
    pub(crate) mode: MirrorMode,
    pub(crate) generation: u64,
    state: Arc<StdMutex<MirrorState>>,
    alive: Arc<AtomicBool>,
    cut_tx: mpsc::UnboundedSender<oneshot::Sender<CutResult>>,
    _stop: oneshot::Sender<()>,
}

impl std::fmt::Debug for TabMirror {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("TabMirror")
            .field("mode", &self.mode)
            .field("generation", &self.generation)
            .field("alive", &self.is_alive())
            .finish()
    }
}

struct Starter {
    conn: Arc<CdpConnection>,
    rx: mpsc::UnboundedReceiver<CdpEvent>,
    cut_rx: mpsc::UnboundedReceiver<oneshot::Sender<CutResult>>,
    stop_rx: oneshot::Receiver<()>,
    fault: FaultInjector,
    label: String,
}

impl TabMirror {
    fn new(
        mode: MirrorMode,
        conn: &Arc<CdpConnection>,
        cdp_target_id: String,
        generation: u64,
        label: &str,
    ) -> (Arc<Self>, Starter) {
        // Rule 1: the subscription exists before any session is attached.
        let rx = conn.subscribe();
        let (cut_tx, cut_rx) = mpsc::unbounded_channel();
        let (stop_tx, stop_rx) = oneshot::channel();
        let mirror = Arc::new(Self {
            mode,
            generation,
            state: Arc::new(StdMutex::new(MirrorState::new(
                mode,
                cdp_target_id,
                generation,
            ))),
            alive: Arc::new(AtomicBool::new(true)),
            cut_tx,
            _stop: stop_tx,
        });
        let starter = Starter {
            conn: conn.clone(),
            rx,
            cut_rx,
            stop_rx,
            fault: FaultInjector::new(FaultPlan::from_env()),
            label: label.to_owned(),
        };
        (mirror, starter)
    }

    fn start(&self, starter: Starter) {
        tokio::spawn(run_mirror(starter, self.state.clone(), self.alive.clone()));
    }

    pub(crate) fn is_alive(&self) -> bool {
        self.alive.load(Ordering::SeqCst)
    }

    pub(crate) fn coverage(&self) -> Coverage {
        self.state.lock().unwrap().coverage.clone()
    }

    /// The bracketing window start, read just before the normal snapshot's
    /// `DOM.getDocument` is sent. `None` unless in `shadow_audit`.
    pub(crate) fn audit_window_start(&self) -> Option<u64> {
        (self.mode == MirrorMode::ShadowAudit).then(|| self.state.lock().unwrap().rev)
    }

    /// Shadow audit against the normal fresh read; trace output only.
    pub(crate) async fn audit(
        &self,
        window_start_rev: u64,
        fresh_document: &Value,
        fresh_complete: bool,
        semantic: &SemanticDocument,
        session: &str,
    ) -> AuditReport {
        let started = Instant::now();
        let (tx, rx) = oneshot::channel();
        let cut = if self.cut_tx.send(tx).is_ok() {
            tokio::time::timeout(CUT_TIMEOUT, rx)
                .await
                .ok()
                .and_then(Result::ok)
        } else {
            None
        };
        let cut_ns = started.elapsed().as_nanos() as u64;
        let compare_started = Instant::now();
        let mut state = self.state.lock().unwrap();
        let mut report = state.audit(window_start_rev, fresh_document, fresh_complete, semantic);
        match &cut {
            None => report.void("cut_unavailable"),
            Some(cut) if !cut.ping_ok && report.coverage == "current" => {
                report.void("cut_ping_failed")
            }
            Some(cut) => report.window_end_rev = report.window_end_rev.max(cut.rev),
        }
        let compare_ns = compare_started.elapsed().as_nanos() as u64;
        state.stats.audits += 1;
        state.stats.cut_ns += cut_ns;
        state.stats.audit_ns += compare_ns;
        drop(state);
        crate::phase_trace::mark_detail("i107.mirror.audit", session, || {
            let mut detail = serde_json::to_value(&report).unwrap_or(Value::Null);
            detail["cut_us"] = json!(cut_ns / 1000);
            detail["compare_us"] = json!(compare_ns / 1000);
            detail
        });
        report
    }

    /// Counters for the trace (both shadow modes); cheap.
    pub(crate) fn emit_stats(&self, session: &str, point: &str) {
        crate::phase_trace::mark_detail("i107.mirror.stats", session, || {
            stats_detail(&self.state.lock().unwrap(), point)
        });
    }
}

fn stats_detail(state: &MirrorState, point: &str) -> Value {
    json!({
        "point": point,
        "mode": state.mode.as_str(),
        "instance": state.instance,
        "generation": state.generation,
        "coverage": state.coverage.label(),
        "rev": state.rev,
        "nodes": state.nodes.len(),
        "stats": serde_json::to_value(&state.stats).unwrap_or(Value::Null),
    })
}

/// Return the tab's mirror, creating and starting it on first use. Off mode
/// returns `None` before touching anything. Existing-profile sockets never
/// get one (their CDP allowlist excludes the event domains: BLOCKED).
#[allow(clippy::too_many_arguments)]
pub(crate) fn ensure_for_tab(
    mode: MirrorMode,
    store: &BrowserStore,
    session: &str,
    target_id: &str,
    tab_id: &str,
    tab: &TabRecord,
    conn: &Arc<CdpConnection>,
    generation: u64,
) -> Option<Arc<TabMirror>> {
    if mode == MirrorMode::Off {
        return None;
    }
    if conn.method_policy() == CdpMethodPolicy::ExistingProfile {
        crate::phase_trace::mark_detail(
            "i107.mirror.blocked",
            session,
            || json!({ "reason": "existing_profile_cdp_allowlist" }),
        );
        return None;
    }
    let usable = |mirror: &Arc<TabMirror>| {
        mirror.is_alive() && mirror.generation == generation && mirror.mode == mode
    };
    if let Some(existing) = tab.i107_mirror.as_ref().filter(|m| usable(m)) {
        return Some(existing.clone());
    }
    let (mirror, starter) =
        TabMirror::new(mode, conn, tab.cdp_target_id.clone(), generation, session);
    let mut installed: Option<Arc<TabMirror>> = None;
    let mut ours = false;
    store.update_target(session, target_id, |record| {
        if let Some(stored) = record.tabs.get_mut(tab_id) {
            match stored.i107_mirror.as_ref().filter(|m| usable(m)) {
                Some(existing) => installed = Some(existing.clone()),
                None => {
                    stored.i107_mirror = Some(mirror.clone());
                    installed = Some(mirror.clone());
                    ours = true;
                }
            }
        }
    });
    if ours {
        crate::phase_trace::mark_detail(
            "i107.mirror.create",
            session,
            || json!({ "mode": mode.as_str(), "generation": generation }),
        );
        mirror.start(starter);
    }
    installed
}

async fn detach(conn: &CdpConnection, session: &str) {
    let _ = tokio::time::timeout(
        DETACH_TIMEOUT,
        conn.call(
            None,
            "Target.detachFromTarget",
            json!({ "sessionId": session }),
        ),
    )
    .await;
}

fn main_frame(tree: &Value) -> Option<(String, String)> {
    let frame = tree.get("frameTree")?.get("frame")?;
    Some((
        frame.get("id")?.as_str()?.to_owned(),
        frame.get("loaderId")?.as_str()?.to_owned(),
    ))
}

struct BootstrapTimes {
    enable: Duration,
    frame_tree: Duration,
    document: Duration,
}

async fn bootstrap_on_session(
    conn: &CdpConnection,
    state: &StdMutex<MirrorState>,
    fault: &mut FaultInjector,
    session: &str,
    label: &str,
) -> Result<BootstrapTimes, String> {
    let t0 = Instant::now();
    conn.call(Some(session), "Page.enable", json!({}))
        .await
        .map_err(|_| "page_enable_failed".to_owned())?;
    // Best effort: crash/detach notifications for this session.
    let _ = conn
        .call(Some(session), "Inspector.enable", json!({}))
        .await;
    let enable = t0.elapsed();
    let t1 = Instant::now();
    let tree = conn
        .call(Some(session), "Page.getFrameTree", json!({}))
        .await
        .map_err(|_| "frame_tree_failed".to_owned())?;
    let frame_tree = t1.elapsed();
    if fault.take_early() {
        let synthetic = CdpEvent {
            method: "DOM.attributeModified".into(),
            session_id: Some(session.to_owned()),
            params: json!({ "nodeId": 1, "name": "data-i107-fault", "value": "early" }),
        };
        let mut st = state.lock().unwrap();
        st.stats.faults_injected += 1;
        st.intake(&synthetic);
        drop(st);
        crate::phase_trace::mark_detail("i107.mirror.fault", label, || json!({ "kind": "early" }));
    }
    let t2 = Instant::now();
    let document = conn
        .call(
            Some(session),
            "DOM.getDocument",
            json!({ "depth": -1, "pierce": true }),
        )
        .await
        .map_err(|_| "get_document_failed".to_owned())?;
    let document_time = t2.elapsed();
    state
        .lock()
        .unwrap()
        .complete_bootstrap(main_frame(&tree), &document)?;
    Ok(BootstrapTimes {
        enable,
        frame_tree,
        document: document_time,
    })
}

async fn bootstrap(
    conn: &CdpConnection,
    state: &StdMutex<MirrorState>,
    fault: &mut FaultInjector,
    label: &str,
) -> Result<String, String> {
    let started = Instant::now();
    let target = state.lock().unwrap().cdp_target_id.clone();
    let attached = match conn
        .call(
            None,
            "Target.attachToTarget",
            json!({ "targetId": target, "flatten": true }),
        )
        .await
    {
        Ok(attached) => attached,
        Err(_) => {
            state.lock().unwrap().bootstrap_failed("attach_failed");
            return Err("attach_failed".into());
        }
    };
    let Some(session) = attached
        .get("sessionId")
        .and_then(Value::as_str)
        .map(str::to_owned)
    else {
        state
            .lock()
            .unwrap()
            .bootstrap_failed("attach_without_session");
        return Err("attach_without_session".into());
    };
    let attach = started.elapsed();
    state.lock().unwrap().begin_bootstrap(session.clone());
    let result = bootstrap_on_session(conn, state, fault, &session, label).await;
    let total = started.elapsed();
    state.lock().unwrap().stats.bootstrap_ns += total.as_nanos() as u64;
    match result {
        Ok(times) => {
            crate::phase_trace::mark_detail("i107.mirror.bootstrap", label, || {
                let st = state.lock().unwrap();
                json!({
                    "ok": true,
                    "attach_us": attach.as_micros() as u64,
                    "enable_us": times.enable.as_micros() as u64,
                    "frame_tree_us": times.frame_tree.as_micros() as u64,
                    "get_document_us": times.document.as_micros() as u64,
                    "total_us": total.as_micros() as u64,
                    "nodes": st.nodes.len(),
                    "bootstraps": st.stats.bootstraps,
                })
            });
            Ok(session)
        }
        Err(reason) => {
            {
                let mut st = state.lock().unwrap();
                if st.bootstrapping {
                    st.bootstrap_failed(&reason);
                }
            }
            crate::phase_trace::mark_detail(
                "i107.mirror.bootstrap",
                label,
                || json!({ "ok": false, "reason": reason, "total_us": total.as_micros() as u64 }),
            );
            detach(conn, &session).await;
            Err(reason)
        }
    }
}

/// Feed events through the intake seam; returns whether a resync is needed.
async fn deliver(
    conn: &CdpConnection,
    state: &StdMutex<MirrorState>,
    session: Option<&str>,
    events: Vec<CdpEvent>,
    label: &str,
) -> bool {
    let mut resync = false;
    for event in events {
        let outcome = state.lock().unwrap().intake(&event);
        if matches!(outcome, Intake::Invalidated(_) | Intake::SessionLost(_))
            && !state.lock().unwrap().node_cap_tripped
        {
            resync = true;
        }
        let (need, ops) = {
            let mut st = state.lock().unwrap();
            (st.take_need_children(), st.take_op_marks())
        };
        for (op, rev) in ops {
            crate::phase_trace::mark_detail(
                "i107.mirror.op_applied",
                label,
                || json!({ "op": op, "rev": rev }),
            );
        }
        if let Some(session) = session {
            for node_id in need {
                state.lock().unwrap().stats.request_children += 1;
                let _ = conn
                    .call(
                        Some(session),
                        "DOM.requestChildNodes",
                        json!({ "nodeId": node_id, "depth": -1, "pierce": true }),
                    )
                    .await;
            }
        }
    }
    resync
}

async fn run_mirror(starter: Starter, state: Arc<StdMutex<MirrorState>>, alive: Arc<AtomicBool>) {
    let Starter {
        conn,
        mut rx,
        mut cut_rx,
        mut stop_rx,
        mut fault,
        label,
    } = starter;
    let label = label.as_str();
    let mut session: Option<String> = None;
    let mut need_bootstrap = true;
    let mut last_bootstrap: Option<Instant> = None;
    let mut resyncs: u32 = 0;
    'outer: loop {
        if need_bootstrap {
            need_bootstrap = false;
            if let Some(old) = session.take() {
                detach(&conn, &old).await;
            }
            let mut allowed = true;
            if let Some(at) = last_bootstrap {
                resyncs += 1;
                if resyncs > MAX_RESYNCS {
                    allowed = false;
                    state.lock().unwrap().invalidate("resync_budget_exhausted");
                } else {
                    state.lock().unwrap().stats.resyncs += 1;
                    let wait = RESYNC_MIN_INTERVAL.saturating_sub(at.elapsed());
                    if !wait.is_zero() {
                        tokio::select! {
                            _ = &mut stop_rx => break 'outer,
                            _ = tokio::time::sleep(wait) => {}
                        }
                    }
                }
            }
            if allowed {
                last_bootstrap = Some(Instant::now());
                match bootstrap(&conn, &state, &mut fault, label).await {
                    Ok(new_session) => session = Some(new_session),
                    // An early-event-poisoned bootstrap retries; any other
                    // failure (or the node cap) stays unknown.
                    Err(reason) => need_bootstrap = reason == "pre_bootstrap_event",
                }
            }
        }
        let due = fault.next_due();
        let sleep_until_due = async move {
            match due {
                Some(at) => tokio::time::sleep_until(tokio::time::Instant::from_std(at)).await,
                None => std::future::pending::<()>().await,
            }
        };
        tokio::select! {
            biased;
            _ = &mut stop_rx => break 'outer,
            event = rx.recv() => {
                let Some(event) = event else {
                    state.lock().unwrap().invalidate("disconnect");
                    break 'outer;
                };
                let queued = rx.len();
                {
                    let mut st = state.lock().unwrap();
                    st.stats.queue_hwm = st.stats.queue_hwm.max(queued + 1);
                }
                if queued >= MAX_QUEUED_EVENTS {
                    let mut discarded = 1u64;
                    while rx.try_recv().is_ok() {
                        discarded += 1;
                    }
                    let mut st = state.lock().unwrap();
                    st.overflow(queued + 1);
                    st.stats.discarded_overflow += discarded;
                    drop(st);
                    need_bootstrap = true;
                    continue;
                }
                let current = session.clone().unwrap_or_default();
                let out = fault.filter(event, &current, Instant::now());
                if let Some(kind) = &out.injected {
                    state.lock().unwrap().stats.faults_injected += 1;
                    crate::phase_trace::mark_detail("i107.mirror.fault", label, || json!({ "kind": kind }));
                }
                if deliver(&conn, &state, session.as_deref(), out.deliver, label).await {
                    need_bootstrap = true;
                }
                if out.overflow {
                    state.lock().unwrap().overflow(MAX_QUEUED_EVENTS + 1);
                    need_bootstrap = true;
                }
                if out.reconnect {
                    // Consumer reconnect: a new subscription and a new session.
                    rx = conn.subscribe();
                    let mut st = state.lock().unwrap();
                    st.stats.reconnects += 1;
                    st.invalidate("reconnect");
                    drop(st);
                    need_bootstrap = true;
                }
            }
            _ = sleep_until_due => {
                let released = fault.release_due(Instant::now());
                if deliver(&conn, &state, session.as_deref(), released, label).await {
                    need_bootstrap = true;
                }
            }
            reply = cut_rx.recv() => {
                let Some(reply) = reply else { continue };
                // An ordered round trip on this session: every event the
                // renderer emitted on it before handling the ping is queued
                // by the time the reply returns.
                let mut ping_ok = false;
                if let Some(s) = &session {
                    if let Ok(tree) = conn.call(Some(s), "Page.getFrameTree", json!({})).await {
                        ping_ok = true;
                        let mut st = state.lock().unwrap();
                        if st.coverage == Coverage::Current && main_frame(&tree) != st.frame {
                            st.invalidate("loader_changed");
                            need_bootstrap = true;
                        }
                    }
                }
                let current = session.clone().unwrap_or_default();
                let mut deliverable = Vec::new();
                let (mut overflow, mut reconnect) = (false, false);
                while let Ok(event) = rx.try_recv() {
                    let out = fault.filter(event, &current, Instant::now());
                    if let Some(kind) = &out.injected {
                        state.lock().unwrap().stats.faults_injected += 1;
                        crate::phase_trace::mark_detail("i107.mirror.fault", label, || json!({ "kind": kind }));
                    }
                    overflow |= out.overflow;
                    reconnect |= out.reconnect;
                    deliverable.extend(out.deliver);
                }
                if deliver(&conn, &state, session.as_deref(), deliverable, label).await {
                    need_bootstrap = true;
                }
                if overflow {
                    state.lock().unwrap().overflow(MAX_QUEUED_EVENTS + 1);
                    need_bootstrap = true;
                }
                if reconnect {
                    rx = conn.subscribe();
                    let mut st = state.lock().unwrap();
                    st.stats.reconnects += 1;
                    st.invalidate("reconnect");
                    drop(st);
                    need_bootstrap = true;
                }
                let rev = state.lock().unwrap().rev;
                let _ = reply.send(CutResult { rev, ping_ok });
            }
        }
    }
    alive.store(false, Ordering::SeqCst);
    let detail = stats_detail(&state.lock().unwrap(), "stop");
    crate::phase_trace::mark_detail("i107.mirror.stats", label, || detail);
    if let Some(s) = session {
        detach(&conn, &s).await;
    }
}

#[cfg(test)]
#[path = "i107_mirror_tests.rs"]
mod tests;
