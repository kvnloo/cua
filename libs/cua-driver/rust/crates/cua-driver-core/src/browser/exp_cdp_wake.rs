//! R2-02 measurement-only CDP wake probe (kvnloo/cua#93). Default off.
//!
//! Armed only when the Driver process has `CUA_DRIVER_EXP_R2_02_CDP_WAKE=1`
//! AND a `browser_click` call on `input_route="dom_event"` carries the
//! `exp_r2_02_cdp_wake` argument. Otherwise nothing here runs.
//!
//! The probe is a function-local subscriber on the existing per-endpoint
//! [`CdpConnection`] demux; it is dropped before the call returns. It waits
//! for a main-frame `Page.frameNavigated` whose loader id differs from the
//! pre-dispatch document identity, or a bounded deadline. The wake is a
//! hint for the caller's next fresh read: the output never claims the
//! application effect.

use std::time::{Duration, Instant};

use serde_json::{json, Map, Value};
use tokio::sync::mpsc;

use super::cdp_ws::{CdpConnection, CdpEvent};

pub(crate) const ENV: &str = "CUA_DRIVER_EXP_R2_02_CDP_WAKE";
pub(crate) const ARG: &str = "exp_r2_02_cdp_wake";
const DEFAULT_DEADLINE_MS: u64 = 1000;
const MAX_DEADLINE_MS: u64 = 10_000;
const INJECTED_EARLY_LOADER: &str = "r2-02-injected-early";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Control {
    None,
    Suppress,
    InjectEarly,
    InjectEarlyUnguarded,
    InjectStale,
    InjectStaleUnguarded,
}

impl Control {
    fn parse(value: &str) -> Option<Self> {
        Some(match value {
            "none" => Self::None,
            "suppress" => Self::Suppress,
            "inject_early" => Self::InjectEarly,
            "inject_early_unguarded" => Self::InjectEarlyUnguarded,
            "inject_stale" => Self::InjectStale,
            "inject_stale_unguarded" => Self::InjectStaleUnguarded,
            _ => return None,
        })
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::None => "none",
            Self::Suppress => "suppress",
            Self::InjectEarly => "inject_early",
            Self::InjectEarlyUnguarded => "inject_early_unguarded",
            Self::InjectStale => "inject_stale",
            Self::InjectStaleUnguarded => "inject_stale_unguarded",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct Config {
    pub deadline: Duration,
    pub control: Control,
}

impl Config {
    /// `None` unless the env gate is set and the call opted in.
    pub(crate) fn from_call(args: &Value) -> Option<Self> {
        Self::from_parts(std::env::var(ENV).ok().as_deref(), args)
    }

    fn from_parts(env: Option<&str>, args: &Value) -> Option<Self> {
        if env != Some("1") {
            return None;
        }
        let cfg = args.get(ARG)?.as_object()?;
        let deadline_ms = cfg
            .get("deadline_ms")
            .and_then(Value::as_u64)
            .unwrap_or(DEFAULT_DEADLINE_MS)
            .clamp(1, MAX_DEADLINE_MS);
        let control = match cfg.get("control").and_then(Value::as_str) {
            None => Control::None,
            Some(value) => Control::parse(value)?,
        };
        Some(Self {
            deadline: Duration::from_millis(deadline_ms),
            control,
        })
    }
}

/// How one delivered event relates to the wake predicate.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum EventClass {
    Wake,
    UnrelatedSession,
    UnrelatedFrame,
    StaleGeneration,
    OtherMethod,
}

/// Pure predicate: a main-frame commit on the call's tab session whose
/// loader id differs from the pre-dispatch document identity.
pub(crate) fn classify(
    event: &CdpEvent,
    session: &str,
    main_frame_id: Option<&str>,
    pre_loader_id: Option<&str>,
    check_generation: bool,
) -> EventClass {
    if event.session_id.as_deref() != Some(session) {
        return EventClass::UnrelatedSession;
    }
    if event.method != "Page.frameNavigated" {
        return EventClass::OtherMethod;
    }
    let frame = &event.params["frame"];
    if frame.get("parentId").is_some_and(|p| !p.is_null()) {
        return EventClass::UnrelatedFrame;
    }
    match (frame["id"].as_str(), main_frame_id) {
        (Some(id), Some(main)) if id == main => {}
        _ => return EventClass::UnrelatedFrame,
    }
    if check_generation && frame["loaderId"].as_str() == pre_loader_id {
        return EventClass::StaleGeneration;
    }
    EventClass::Wake
}

#[derive(Default)]
struct Counts {
    pre_dispatch: u64,
    unrelated_session: u64,
    unrelated_frame: u64,
    stale_generation: u64,
    other_method: u64,
    suppressed: u64,
    early_rejected: u64,
    stale_rejected: u64,
}

pub(crate) struct Armed {
    cfg: Config,
    start: Instant,
    session: String,
    rx: mpsc::UnboundedReceiver<CdpEvent>,
    main_frame_id: Option<String>,
    pre_loader_id: Option<String>,
    page_enable_ok: bool,
    generation_ok: bool,
    marks: Map<String, Value>,
    counts: Counts,
    queued_unguarded: Option<CdpEvent>,
    wake: Option<(&'static str, bool)>,
    end: &'static str,
}

fn ms(since: Instant) -> Value {
    json!((since.elapsed().as_secs_f64() * 1_000_000.0).round() / 1000.0)
}

fn synthetic_commit(session: &str, frame_id: Option<&str>, loader: Option<&str>) -> CdpEvent {
    CdpEvent {
        method: "Page.frameNavigated".into(),
        session_id: Some(session.to_owned()),
        params: json!({ "frame": { "id": frame_id, "loaderId": loader }, "type": "Navigation" }),
    }
}

impl Armed {
    /// Subscribe, enable Page events on the call's tab session, and read the
    /// pre-dispatch document identity. Call before dispatch.
    pub(crate) async fn arm(conn: &CdpConnection, session: &str, cfg: Config) -> Self {
        let start = Instant::now();
        let mut marks = Map::new();
        let rx = conn.subscribe();
        marks.insert("subscribed_ms".into(), ms(start));
        let page_enable_ok = conn
            .call(Some(session), "Page.enable", json!({}))
            .await
            .is_ok();
        marks.insert("page_enabled_ms".into(), ms(start));
        let tree = conn
            .call(Some(session), "Page.getFrameTree", json!({}))
            .await
            .ok();
        let frame = tree.as_ref().map(|t| &t["frameTree"]["frame"]);
        let main_frame_id = frame.and_then(|f| f["id"].as_str()).map(str::to_owned);
        let pre_loader_id = frame
            .and_then(|f| f["loaderId"].as_str())
            .map(str::to_owned);
        marks.insert("generation_read_ms".into(), ms(start));
        Self {
            cfg,
            start,
            session: session.to_owned(),
            rx,
            generation_ok: main_frame_id.is_some() && pre_loader_id.is_some(),
            main_frame_id,
            pre_loader_id,
            page_enable_ok,
            marks,
            counts: Counts::default(),
            queued_unguarded: None,
            wake: None,
            end: "not_waited",
        }
    }

    /// Discard everything delivered before dispatch: none of it may wake.
    pub(crate) fn before_dispatch(&mut self) {
        let early = synthetic_commit(
            &self.session,
            self.main_frame_id.as_deref(),
            Some(INJECTED_EARLY_LOADER),
        );
        match self.cfg.control {
            Control::InjectEarly => {
                self.counts.pre_dispatch += 1;
                self.counts.early_rejected += 1;
            }
            Control::InjectEarlyUnguarded => self.queued_unguarded = Some(early),
            _ => {}
        }
        if self.cfg.control != Control::InjectEarlyUnguarded {
            while self.rx.try_recv().is_ok() {
                self.counts.pre_dispatch += 1;
            }
        }
        self.marks.insert("dispatch_sent_ms".into(), ms(self.start));
    }

    pub(crate) fn dispatch_returned(&mut self) {
        self.marks
            .insert("dispatch_returned_ms".into(), ms(self.start));
    }

    fn take(&mut self, event: &CdpEvent, check_generation: bool, injected: bool) -> bool {
        match classify(
            event,
            &self.session,
            self.main_frame_id.as_deref(),
            self.pre_loader_id.as_deref(),
            check_generation,
        ) {
            EventClass::Wake if self.cfg.control == Control::Suppress => {
                self.counts.suppressed += 1;
                false
            }
            EventClass::Wake => {
                self.wake = Some(("Page.frameNavigated", injected));
                true
            }
            EventClass::UnrelatedSession => {
                self.counts.unrelated_session += 1;
                false
            }
            EventClass::UnrelatedFrame => {
                self.counts.unrelated_frame += 1;
                false
            }
            EventClass::StaleGeneration => {
                self.counts.stale_generation += 1;
                if injected {
                    self.counts.stale_rejected += 1;
                }
                false
            }
            EventClass::OtherMethod => {
                self.counts.other_method += 1;
                false
            }
        }
    }

    /// Wait for the first post-dispatch wake event or the deadline.
    pub(crate) async fn wait(&mut self) {
        let waited = Instant::now();
        if !self.generation_ok {
            self.end = "no_generation";
            return;
        }
        if let Some(event) = self.queued_unguarded.take() {
            if self.take(&event, true, true) {
                self.end = "wake";
            }
        }
        if matches!(
            self.cfg.control,
            Control::InjectStale | Control::InjectStaleUnguarded
        ) && self.wake.is_none()
        {
            let stale = synthetic_commit(
                &self.session,
                self.main_frame_id.as_deref(),
                self.pre_loader_id.as_deref(),
            );
            let guarded = self.cfg.control == Control::InjectStale;
            if self.take(&stale, guarded, true) {
                self.end = "wake";
            }
        }
        let deadline = tokio::time::Instant::from_std(waited + self.cfg.deadline);
        while self.wake.is_none() {
            match tokio::time::timeout_at(deadline, self.rx.recv()).await {
                Ok(Some(event)) => {
                    if self.take(&event, true, false) {
                        self.end = "wake";
                    }
                }
                Ok(None) => {
                    self.end = "socket_closed";
                    break;
                }
                Err(_) => {
                    self.end = "deadline";
                    break;
                }
            }
        }
        self.marks.insert("wait_end_ms".into(), ms(self.start));
        self.marks.insert("wait_ms".into(), ms(waited));
    }

    /// Drop the subscriber and disable Page events on the call's session.
    pub(crate) async fn finish(mut self, conn: &CdpConnection) -> Value {
        let cleanup = Instant::now();
        self.rx.close();
        drop(self.rx);
        let page_disable_ok = if self.page_enable_ok {
            Some(
                conn.call(Some(&self.session), "Page.disable", json!({}))
                    .await
                    .is_ok(),
            )
        } else {
            None
        };
        self.marks.insert("cleanup_ms".into(), ms(cleanup));
        self.marks.insert("total_ms".into(), ms(self.start));
        let c = &self.counts;
        json!({
            "schema": "cua.r2_02.cdp_wake_probe.v1",
            "semantics": "wake_hint_only; application effect not verified",
            "control": self.cfg.control.as_str(),
            "deadline_ms": self.cfg.deadline.as_millis() as u64,
            "page_enable_ok": self.page_enable_ok,
            "page_disable_ok": page_disable_ok,
            "generation_ok": self.generation_ok,
            "end": self.end,
            "wake_method": self.wake.map(|(m, _)| m),
            "wake_injected": self.wake.map(|(_, injected)| injected),
            "counts": {
                "pre_dispatch": c.pre_dispatch,
                "unrelated_session": c.unrelated_session,
                "unrelated_frame": c.unrelated_frame,
                "stale_generation": c.stale_generation,
                "other_method": c.other_method,
                "suppressed": c.suppressed,
                "early_rejected": c.early_rejected,
                "stale_rejected": c.stale_rejected,
            },
            "marks": Value::Object(self.marks),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::browser::mock_cdp::{MockCdpServer, MockEvent, MockReply};
    use std::sync::Arc;

    fn commit(session: &str, frame: &str, loader: &str, parent: Option<&str>) -> CdpEvent {
        let mut f = json!({ "id": frame, "loaderId": loader });
        if let Some(p) = parent {
            f["parentId"] = json!(p);
        }
        CdpEvent {
            method: "Page.frameNavigated".into(),
            session_id: Some(session.into()),
            params: json!({ "frame": f }),
        }
    }

    #[test]
    fn env_gate_and_argument_are_both_required() {
        let args = json!({ ARG: { "deadline_ms": 50, "control": "suppress" } });
        assert!(Config::from_parts(None, &args).is_none());
        assert!(Config::from_parts(Some("0"), &args).is_none());
        assert!(Config::from_parts(Some("1"), &json!({})).is_none());
        let cfg = Config::from_parts(Some("1"), &args).unwrap();
        assert_eq!(cfg.deadline, Duration::from_millis(50));
        assert_eq!(cfg.control, Control::Suppress);
        assert!(Config::from_parts(Some("1"), &json!({ ARG: { "control": "bogus" } })).is_none());
        let clamped = Config::from_parts(Some("1"), &json!({ ARG: { "deadline_ms": 0 } })).unwrap();
        assert_eq!(clamped.deadline, Duration::from_millis(1));
    }

    #[test]
    fn predicate_classes() {
        let s = "tab";
        let c = |e: &CdpEvent, gen: bool| classify(e, s, Some("main"), Some("L0"), gen);
        assert_eq!(c(&commit(s, "main", "L1", None), true), EventClass::Wake);
        assert_eq!(
            c(&commit(s, "main", "L0", None), true),
            EventClass::StaleGeneration
        );
        assert_eq!(c(&commit(s, "main", "L0", None), false), EventClass::Wake);
        assert_eq!(
            c(&commit(s, "child", "L9", Some("main")), true),
            EventClass::UnrelatedFrame
        );
        assert_eq!(
            c(&commit(s, "other", "L9", None), true),
            EventClass::UnrelatedFrame
        );
        assert_eq!(
            c(&commit("other-session", "main", "L1", None), true),
            EventClass::UnrelatedSession
        );
        let mut load = commit(s, "main", "L1", None);
        load.method = "Page.loadEventFired".into();
        assert_eq!(c(&load, true), EventClass::OtherMethod);
    }

    fn server() -> Arc<dyn Fn(&crate::browser::mock_cdp::MockCall) -> MockReply + Send + Sync> {
        Arc::new(|call| {
            match call.method.as_str() {
            "Page.getFrameTree" => MockReply::ok(json!({
                "frameTree": { "frame": { "id": "main", "loaderId": "L0" } }
            })),
            "Runtime.callFunctionOn" => MockReply::ok(json!({})).with_events(vec![
                MockEvent {
                    method: "Page.frameNavigated".into(),
                    session_id: call.session_id.clone(),
                    params: json!({ "frame": { "id": "child", "parentId": "main", "loaderId": "C1" } }),
                },
                MockEvent {
                    method: "Page.frameNavigated".into(),
                    session_id: call.session_id.clone(),
                    params: json!({ "frame": { "id": "main", "loaderId": "L0" } }),
                },
                MockEvent {
                    method: "Page.frameNavigated".into(),
                    session_id: call.session_id.clone(),
                    params: json!({ "frame": { "id": "main", "loaderId": "L1" } }),
                },
            ]),
            _ => MockReply::ok(json!({})),
        }
        })
    }

    async fn run(control: Control) -> Value {
        let mock = MockCdpServer::start(server()).await;
        let conn = CdpConnection::connect(&mock.ws_url()).await.unwrap();
        let cfg = Config {
            deadline: Duration::from_millis(200),
            control,
        };
        let mut armed = Armed::arm(&conn, "tab", cfg).await;
        armed.before_dispatch();
        conn.call(Some("tab"), "Runtime.callFunctionOn", json!({}))
            .await
            .unwrap();
        armed.dispatch_returned();
        armed.wait().await;
        armed.finish(&conn).await
    }

    #[tokio::test]
    async fn wakes_only_on_new_main_frame_generation() {
        let out = run(Control::None).await;
        assert_eq!(out["end"], "wake");
        assert_eq!(out["wake_injected"], false);
        assert_eq!(out["counts"]["unrelated_frame"], 1);
        assert_eq!(out["counts"]["stale_generation"], 1);
        assert_eq!(out["page_disable_ok"], true);
    }

    #[tokio::test]
    async fn suppressed_wake_reaches_the_deadline() {
        let out = run(Control::Suppress).await;
        assert_eq!(out["end"], "deadline");
        assert_eq!(out["counts"]["suppressed"], 1);
        assert!(out["wake_method"].is_null());
    }

    #[tokio::test]
    async fn guarded_injections_are_rejected_and_unguarded_ones_wake() {
        let early = run(Control::InjectEarly).await;
        assert_eq!(early["counts"]["early_rejected"], 1);
        assert_eq!(early["wake_injected"], false);
        let stale = run(Control::InjectStale).await;
        assert_eq!(stale["counts"]["stale_rejected"], 1);
        assert_eq!(stale["wake_injected"], false);
        assert_eq!(
            run(Control::InjectEarlyUnguarded).await["wake_injected"],
            true
        );
        assert_eq!(
            run(Control::InjectStaleUnguarded).await["wake_injected"],
            true
        );
    }
}
