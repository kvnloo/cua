//! OWN-09 barrier rows (kvnloo/cua#9, #36, #105): cooperative cancellation and
//! admitted-native-work ownership, measured on the real embedded SDK runtime.
//!
//! Measurement-only. This harness changes no production code. It registers a
//! barrier-backed host tool under the physical-desktop tool name `press_key`
//! through the public `DriverHostOptions::register_host_tools` hook, so every
//! call takes the exact production route:
//!
//! `CuaDriver::call_tool` -> `NativeAbiDriver::invoke` -> `cua_driver_invoke_v1`
//! -> `spawn_completion` (ABI executor) -> `DriverRuntime::invoke*` (lifecycle
//! read guard) -> `ToolRegistry` dispatch (desktop action coordinator) ->
//! `Tool::invoke` -> native closure on the blocking pool.
//!
//! Cancelling a caller drops its `OperationGuard`, which calls
//! `cua_driver_operation_cancel_v1`; `spawn_completion` then aborts the nested
//! work task. The barrier tool's `invocation-dropped` event is therefore the
//! route attribution: the dispatch frame can only be dropped early through that
//! abort, because the work task runs on the ABI executor, not in the caller.
//!
//! Phase is proven by channels and an ordered ledger, never by sleeps. Bounded
//! negative windows only schedule when the harness releases a barrier; every
//! verdict comes from ledger order, the fixture-owned native entry/exit
//! counters, and the target journal written by the native closure itself.

#![allow(dead_code)]

use cua_driver_core::protocol::{Request, ToolResult as CoreToolResult};
use cua_driver_core::server::ToolProvider;
use cua_driver_core::tool::{Tool, ToolDef, ToolRegistry};
use cua_driver_sdk::{
    ConfiguredDriverOptions, CuaDriver, CuaDriverSession, DriverHostOptions,
    RuntimeAuthorizationOptions, SessionPermissionMode, TrustedSessionOptions,
};
use serde_json::{json, Map, Value};
use std::collections::HashMap;
use std::future::Future;
use std::io::Write;
use std::pin::Pin;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Mutex, MutexGuard};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tokio::task::JoinHandle;

/// A real physical-desktop tool name, so dispatch applies the process-wide
/// desktop action coordinator exactly as for a platform `press_key`.
pub const TOOL: &str = "press_key";
/// Failure bound for a positive phase (a barrier that must be reached).
pub const WAIT: Duration = Duration::from_secs(10);
/// Bounded negative window. It only decides when the harness releases a
/// barrier; it is never a verdict on its own.
pub const NEGATIVE_WINDOW: Duration = Duration::from_millis(300);

pub type NativeWork = Box<dyn FnOnce() + Send + 'static>;
pub type NativeFuture = Pin<Box<dyn Future<Output = ()> + Send + 'static>>;
/// How the barrier tool runs its native closure.
pub type NativeSpawn = fn(NativeWork) -> NativeFuture;

/// Production behaviour on current main: a plain blocking-pool closure.
pub fn plain_spawn(work: NativeWork) -> NativeFuture {
    Box::pin(async move {
        tokio::task::spawn_blocking(work)
            .await
            .expect("native closure panicked")
    })
}

#[derive(Clone, Copy)]
pub struct ArmCfg {
    /// "M" (upstream main) or "P" (main + kvnloo/cua#84).
    pub arm: &'static str,
    /// Native closure strategy label recorded in every row.
    pub strategy: &'static str,
    pub spawn: NativeSpawn,
}

pub fn iterations() -> usize {
    std::env::var("OWN09_ITERS")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(20)
}

fn utc_now() -> String {
    let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap();
    format!("{}.{:06}", now.as_secs(), now.subsec_micros())
}

// ---------------------------------------------------------------- ledger ---

pub struct Ledger {
    origin: Instant,
    events: Mutex<Vec<(usize, String, u128)>>,
    changed: tokio::sync::watch::Sender<u64>,
}

impl Ledger {
    fn new() -> Self {
        let (changed, _) = tokio::sync::watch::channel(0);
        Self {
            origin: Instant::now(),
            events: Mutex::new(Vec::new()),
            changed,
        }
    }

    pub fn log(&self, name: impl Into<String>) {
        {
            let mut events = self.events.lock().unwrap();
            let seq = events.len();
            events.push((seq, name.into(), self.origin.elapsed().as_micros()));
        }
        self.changed.send_modify(|version| *version += 1);
    }

    pub fn pos(&self, name: &str) -> Option<usize> {
        self.events
            .lock()
            .unwrap()
            .iter()
            .find(|(_, event, _)| event == name)
            .map(|(seq, _, _)| *seq)
    }

    pub fn has(&self, name: &str) -> bool {
        self.pos(name).is_some()
    }

    pub fn has_prefix(&self, prefix: &str) -> bool {
        self.events
            .lock()
            .unwrap()
            .iter()
            .any(|(_, event, _)| event.starts_with(prefix))
    }

    /// `a` happened and either `b` never happened or `a` came first.
    pub fn before(&self, a: &str, b: &str) -> bool {
        match (self.pos(a), self.pos(b)) {
            (Some(a), Some(b)) => a < b,
            (Some(_), None) => true,
            _ => false,
        }
    }

    pub fn dump(&self) -> Vec<Value> {
        self.events
            .lock()
            .unwrap()
            .iter()
            .map(|(seq, event, t_us)| json!([seq, event, t_us]))
            .collect()
    }

    pub async fn wait_until(
        &self,
        what: &str,
        limit: Duration,
        mut done: impl FnMut() -> bool,
    ) -> Result<(), String> {
        let mut changed = self.changed.subscribe();
        let deadline = tokio::time::Instant::now() + limit;
        loop {
            if done() {
                return Ok(());
            }
            match tokio::time::timeout_at(deadline, changed.changed()).await {
                Ok(Ok(())) => continue,
                Ok(Err(_)) => return Err(format!("ledger closed while waiting for {what}")),
                Err(_) => {
                    return if done() {
                        Ok(())
                    } else {
                        Err(format!("phase barrier never reached: {what}"))
                    }
                }
            }
        }
    }

    pub async fn wait_for(&self, name: &str) -> Result<(), String> {
        self.wait_until(name, WAIT, || self.has(name)).await
    }

    /// True when `name` did not happen inside the negative window.
    pub async fn absent_within(&self, name: &str, window: Duration) -> bool {
        self.wait_until(name, window, || self.has(name))
            .await
            .is_err()
    }
}

// ---------------------------------------------------------------- target ---

/// Target-owned journal. Only the native closure (or the target's delayed
/// commit thread) writes it; no Driver result is consulted.
#[derive(Default)]
pub struct Target {
    journal: Mutex<Vec<Value>>,
}

impl Target {
    /// Apply one effect. `guard = Some(n)` is a target-side compare-and-set:
    /// the effect lands only if exactly `n` effects have landed so far.
    fn apply(&self, id: u64, guard: Option<u64>) -> bool {
        let mut journal = self.journal.lock().unwrap();
        let landed = journal
            .iter()
            .filter(|entry| entry["effect"] == "applied")
            .count() as u64;
        let applied = guard.is_none_or(|expected| expected == landed);
        journal.push(json!({
            "id": id,
            "effect": if applied { "applied" } else { "refused" },
            "landed_before": landed,
            "guard": guard,
        }));
        applied
    }

    /// A fresh read of the target state: the number of landed effects.
    pub fn landed(&self) -> u64 {
        self.journal
            .lock()
            .unwrap()
            .iter()
            .filter(|entry| entry["effect"] == "applied")
            .count() as u64
    }

    pub fn landed_ids(&self) -> Vec<u64> {
        self.journal
            .lock()
            .unwrap()
            .iter()
            .filter(|entry| entry["effect"] == "applied")
            .filter_map(|entry| entry["id"].as_u64())
            .collect()
    }

    pub fn snapshot(&self) -> Vec<Value> {
        self.journal.lock().unwrap().clone()
    }
}

// ----------------------------------------------------------- shared state ---

pub struct Shared {
    pub ledger: Arc<Ledger>,
    pub target: Target,
    gates: Mutex<HashMap<u64, mpsc::Receiver<()>>>,
    commits: Mutex<HashMap<u64, mpsc::Receiver<()>>>,
    /// Fixture-owned native closure entry/exit counters: id -> [entered, exited].
    counters: Mutex<HashMap<u64, [usize; 2]>>,
    pending_effects: AtomicUsize,
    spawn: NativeSpawn,
}

impl Shared {
    fn count(&self, id: u64, slot: usize) {
        self.counters.lock().unwrap().entry(id).or_insert([0, 0])[slot] += 1;
    }

    pub fn counter(&self, id: u64) -> [usize; 2] {
        self.counters
            .lock()
            .unwrap()
            .get(&id)
            .copied()
            .unwrap_or([0, 0])
    }

    fn balanced(&self) -> bool {
        self.counters
            .lock()
            .unwrap()
            .values()
            .all(|[entered, exited]| entered == exited)
            && self.pending_effects.load(Ordering::SeqCst) == 0
    }

    fn counters_json(&self) -> Value {
        let counters = self.counters.lock().unwrap();
        let mut ids: Vec<_> = counters.keys().copied().collect();
        ids.sort_unstable();
        Value::Object(
            ids.into_iter()
                .map(|id| (id.to_string(), json!(counters[&id])))
                .collect(),
        )
    }
}

static SERIAL: Mutex<()> = Mutex::new(());
static SHARED: Mutex<Option<Arc<Shared>>> = Mutex::new(None);

/// One Driver runtime per process and one process-wide desktop coordinator:
/// iterations are serialized even under `--test-threads=8`.
pub fn serial() -> MutexGuard<'static, ()> {
    SERIAL.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
}

struct InvocationLifetime {
    shared: Arc<Shared>,
    id: u64,
}

impl Drop for InvocationLifetime {
    fn drop(&mut self) {
        self.shared
            .ledger
            .log(format!("invocation-dropped:{}", self.id));
    }
}

struct BarrierTool {
    def: ToolDef,
    shared: Arc<Shared>,
}

#[async_trait::async_trait]
impl Tool for BarrierTool {
    fn def(&self) -> &ToolDef {
        &self.def
    }

    async fn invoke(&self, args: Value) -> CoreToolResult {
        let Some(id) = args["id"].as_u64() else {
            return CoreToolResult::error("own09 barrier tool requires an id");
        };
        let shared = self.shared.clone();
        // Reaching invoke means dispatch admitted the call (coordinator held).
        shared.ledger.log(format!("admitted:{id}"));
        let _lifetime = InvocationLifetime {
            shared: shared.clone(),
            id,
        };
        let Some(gate) = shared.gates.lock().unwrap().remove(&id) else {
            shared.ledger.log(format!("no-gate:{id}"));
            return CoreToolResult::error("own09 barrier gate missing or reused");
        };
        let effect = args["effect"].as_bool().unwrap_or(false);
        let guard = args["guard"].as_u64();
        let commit = shared.commits.lock().unwrap().remove(&id);
        let native = shared.clone();
        let work: NativeWork = Box::new(move || {
            native.count(id, 0);
            native.ledger.log(format!("native-enter:{id}"));
            let released = gate.recv_timeout(WAIT).is_ok();
            if !released {
                native.ledger.log(format!("native-timeout:{id}"));
            }
            if effect && released {
                match commit {
                    None => {
                        let applied = native.target.apply(id, guard);
                        native.ledger.log(format!(
                            "effect-{}:{id}",
                            if applied { "applied" } else { "refused" }
                        ));
                    }
                    Some(commit) => {
                        // The target commits the effect after native exit.
                        native.pending_effects.fetch_add(1, Ordering::SeqCst);
                        native.ledger.log(format!("effect-deferred:{id}"));
                        let target = native.clone();
                        std::thread::spawn(move || {
                            if commit.recv_timeout(WAIT).is_ok() {
                                let applied = target.target.apply(id, guard);
                                target.ledger.log(format!(
                                    "effect-{}:{id}",
                                    if applied { "applied" } else { "refused" }
                                ));
                            } else {
                                target.ledger.log(format!("effect-timeout:{id}"));
                            }
                            target.pending_effects.fetch_sub(1, Ordering::SeqCst);
                            target.ledger.log(format!("effect-settled:{id}"));
                        });
                    }
                }
            }
            native.ledger.log(format!("native-exit:{id}"));
            native.count(id, 1);
        });
        (shared.spawn)(work).await;
        shared.ledger.log(format!("invoke-end:{id}"));
        CoreToolResult::text("native complete")
    }
}

fn register_barrier_tool(registry: &mut ToolRegistry) {
    let shared = SHARED
        .lock()
        .unwrap()
        .clone()
        .expect("own09 fixture installed before runtime creation");
    registry.register(Box::new(BarrierTool {
        def: ToolDef {
            name: TOOL.into(),
            description: "test-only OWN-09 barrier tool under a physical desktop tool name"
                .into(),
            input_schema: json!({"type": "object"}),
            read_only: false,
            destructive: false,
            idempotent: false,
            open_world: false,
        },
        shared,
    }));
}

// --------------------------------------------------------------- fixture ---

pub type CallOutcome = Result<Value, String>;

pub struct Fixture {
    pub driver: Arc<CuaDriver>,
    pub shared: Arc<Shared>,
    releases: HashMap<u64, mpsc::Sender<()>>,
    commit_senders: HashMap<u64, mpsc::Sender<()>>,
    pub notes: Map<String, Value>,
    finished: bool,
}

fn summarize(result: cua_driver_sdk::ToolResult) -> Value {
    json!({
        "is_error": result.is_error,
        "error_code": result.error_code,
        "text": result.text,
    })
}

impl Fixture {
    /// A fresh Driver runtime for one iteration.
    pub fn new(spawn: NativeSpawn) -> Result<Self, String> {
        let shared = Arc::new(Shared {
            ledger: Arc::new(Ledger::new()),
            target: Target::default(),
            gates: Mutex::new(HashMap::new()),
            commits: Mutex::new(HashMap::new()),
            counters: Mutex::new(HashMap::new()),
            pending_effects: AtomicUsize::new(0),
            spawn,
        });
        *SHARED.lock().unwrap() = Some(shared.clone());
        // Explicit Standard-only ceiling through the trusted-host constructor
        // (no permission environment override); it enables trusted
        // per-session delegation for the R5/R6 session rows.
        let driver = CuaDriver::try_create_configured_for_host(
            ConfiguredDriverOptions {
                claude_code_compatibility: false,
                authorization: RuntimeAuthorizationOptions {
                    allowed_modes: vec![SessionPermissionMode::Standard],
                    compatibility_mode: SessionPermissionMode::Standard,
                    compatibility_capability_manifest_path: None,
                    compatibility_bounded_manifest_path: None,
                    unrestricted_acknowledged: false,
                    max_session_ttl_seconds: 3600,
                    max_idle_ttl_seconds: 3600,
                },
            },
            DriverHostOptions {
                cursor: cursor_overlay::CursorConfig {
                    enabled: false,
                    ..Default::default()
                },
                host_owns_permission_ux: false,
                host_bundle_id: None,
                claude_code_compatibility: false,
                prepare_desktop_environment: false,
                register_host_tools: Some(register_barrier_tool),
                authorization_host: None,
                activity_observer: None,
            },
        )
        .map_err(|error| format!("create runtime: {error}"))?;
        Ok(Self {
            driver,
            shared,
            releases: HashMap::new(),
            commit_senders: HashMap::new(),
            notes: Map::new(),
            finished: false,
        })
    }

    pub fn ledger(&self) -> Arc<Ledger> {
        self.shared.ledger.clone()
    }

    pub fn log(&self, event: impl Into<String>) {
        self.shared.ledger.log(event);
    }

    pub fn note(&mut self, key: &str, value: impl Into<Value>) {
        self.notes.insert(key.into(), value.into());
    }

    pub fn gate(&mut self, id: u64) {
        let (tx, rx) = mpsc::channel();
        self.shared.gates.lock().unwrap().insert(id, rx);
        self.releases.insert(id, tx);
    }

    /// Defer this call's target effect until `commit(id)`, after native exit.
    pub fn defer_effect(&mut self, id: u64) {
        let (tx, rx) = mpsc::channel();
        self.shared.commits.lock().unwrap().insert(id, rx);
        self.commit_senders.insert(id, tx);
    }

    pub fn release(&mut self, id: u64) {
        if let Some(tx) = self.releases.remove(&id) {
            self.shared.ledger.log(format!("release:{id}"));
            let _ = tx.send(());
        }
    }

    pub fn commit(&mut self, id: u64) {
        if let Some(tx) = self.commit_senders.remove(&id) {
            self.shared.ledger.log(format!("commit:{id}"));
            let _ = tx.send(());
        }
    }

    pub async fn wait(&self, event: &str) -> Result<(), String> {
        self.shared.ledger.wait_for(event).await
    }

    pub async fn absent(&self, event: &str) -> bool {
        self.shared
            .ledger
            .absent_within(event, NEGATIVE_WINDOW)
            .await
    }

    fn args(id: u64, extra: Value) -> Value {
        let mut args = json!({ "id": id });
        if let Value::Object(extra) = extra {
            args.as_object_mut().unwrap().extend(extra);
        }
        args
    }

    /// Issue a call through the embedded SDK (C ABI route).
    pub fn call(&self, id: u64, extra: Value) -> JoinHandle<CallOutcome> {
        let driver = self.driver.clone();
        let ledger = self.ledger();
        let args = Self::args(id, extra);
        ledger.log(format!("queued:{id}"));
        tokio::spawn(async move {
            let result = driver.call_tool(TOOL.into(), args.to_string()).await;
            ledger.log(format!("caller-returned:{id}"));
            result.map(summarize).map_err(|error| error.to_string())
        })
    }

    /// Issue a tool call through a trusted session (C ABI session route).
    pub fn session_call(
        &self,
        session: &Arc<CuaDriverSession>,
        tool: &str,
        id: u64,
        extra: Value,
    ) -> JoinHandle<CallOutcome> {
        let session = session.clone();
        let ledger = self.ledger();
        let tool = tool.to_owned();
        let args = if tool == TOOL {
            Self::args(id, extra)
        } else {
            extra
        };
        ledger.log(format!("queued:{id}"));
        tokio::spawn(async move {
            let result = session.call_tool(tool, args.to_string()).await;
            ledger.log(format!("caller-returned:{id}"));
            result.map(summarize).map_err(|error| error.to_string())
        })
    }

    pub fn trusted_session(&self, public_session: &str) -> Result<Arc<CuaDriverSession>, String> {
        self.driver
            .create_trusted_session(TrustedSessionOptions {
                public_session: public_session.into(),
                mode: SessionPermissionMode::Standard,
                ttl_seconds: 600,
                idle_ttl_seconds: 600,
                capability_manifest_path: None,
                bounded_manifest_path: None,
            })
            .map_err(|error| format!("create trusted session {public_session}: {error}"))
    }

    /// Cancel a caller: abort its task, which drops the SDK future and its
    /// `OperationGuard` (-> `cua_driver_operation_cancel_v1`). Returns true
    /// when the waiter observed cancellation (false: it had already finished).
    pub async fn cancel(&self, handle: JoinHandle<CallOutcome>, id: u64) -> Result<bool, String> {
        self.log(format!("cancel-requested:{id}"));
        handle.abort();
        let outcome = tokio::time::timeout(WAIT, handle)
            .await
            .map_err(|_| format!("waiter for {id} did not return after cancel"))?;
        let cancelled = matches!(&outcome, Err(error) if error.is_cancelled());
        self.log(format!(
            "waiter-returned:{id}:{}",
            if cancelled { "cancelled" } else { "completed" }
        ));
        if cancelled {
            self.log(format!("waiter-returned:{id}"));
        }
        Ok(cancelled)
    }

    /// Await a caller that must complete; returns its summarized outcome.
    pub async fn outcome(&self, handle: JoinHandle<CallOutcome>, id: u64) -> Result<Value, String> {
        match tokio::time::timeout(WAIT, handle).await {
            Err(_) => Err(format!("caller {id} never returned")),
            Ok(Err(error)) if error.is_cancelled() => Ok(json!({"cancelled": true})),
            Ok(Err(error)) => Err(format!("caller {id} panicked: {error}")),
            Ok(Ok(Err(error))) => Ok(json!({"driver_error": error})),
            Ok(Ok(Ok(summary))) => Ok(summary),
        }
    }

    /// Release every barrier, wait until every entered native closure has
    /// exited and every deferred effect settled, then shut the runtime down.
    pub async fn finish(&mut self) -> Result<(), String> {
        if self.finished {
            return Ok(());
        }
        self.finished = true;
        let ids: Vec<u64> = self.releases.keys().copied().collect();
        for id in ids {
            self.release(id);
        }
        let commits: Vec<u64> = self.commit_senders.keys().copied().collect();
        for id in commits {
            self.commit(id);
        }
        let shared = self.shared.clone();
        let drained = self
            .shared
            .ledger
            .wait_until("all native closures exited", WAIT, || shared.balanced())
            .await;
        let shutdown = tokio::time::timeout(WAIT, self.driver.shutdown()).await;
        self.log("cleanup-complete");
        drained?;
        match shutdown {
            Err(_) => Err("runtime shutdown did not return".into()),
            Ok(Err(error)) => Err(format!("runtime shutdown failed: {error}")),
            Ok(Ok(())) => Ok(()),
        }
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        for (_, tx) in self.releases.drain() {
            let _ = tx.send(());
        }
        for (_, tx) in self.commit_senders.drain() {
            let _ = tx.send(());
        }
        *SHARED.lock().unwrap() = None;
    }
}

// ------------------------------------------------------------- recording ---

pub struct Checks {
    pub verdict: &'static str,
    pub values: Map<String, Value>,
}

impl Checks {
    pub fn new() -> Self {
        Self {
            verdict: "PASS",
            values: Map::new(),
        }
    }

    pub fn set(&mut self, key: &str, value: impl Into<Value>) {
        self.values.insert(key.into(), value.into());
    }

    /// Record a gate condition; any false gate makes the iteration FAIL.
    pub fn gate(&mut self, key: &str, holds: bool) {
        self.values.insert(key.into(), Value::Bool(holds));
        if !holds {
            self.verdict = "FAIL";
        }
    }

    pub fn verdict(mut self, verdict: &'static str) -> Self {
        self.verdict = verdict;
        self
    }
}

impl Default for Checks {
    fn default() -> Self {
        Self::new()
    }
}

pub struct RowLog {
    cfg: ArmCfg,
    row: &'static str,
    variant: &'static str,
    file: Option<std::fs::File>,
    pub verdicts: HashMap<String, usize>,
    pub errors: Vec<String>,
}

impl RowLog {
    pub fn open(cfg: ArmCfg, row: &'static str, variant: &'static str) -> Self {
        let file = std::env::var("OWN09_RAW_DIR").ok().map(|dir| {
            let dir = std::path::Path::new(&dir).join(cfg.arm);
            std::fs::create_dir_all(&dir).expect("create OWN09_RAW_DIR");
            std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(dir.join(format!("{row}__{variant}.jsonl")))
                .expect("open row log")
        });
        Self {
            cfg,
            row,
            variant,
            file,
            verdicts: HashMap::new(),
            errors: Vec::new(),
        }
    }

    pub fn record(
        &mut self,
        iter: usize,
        utc_start: String,
        fx: Option<&Fixture>,
        result: Result<Checks, String>,
        finish: Result<(), String>,
    ) {
        let (verdict, checks, error) = match (&result, &finish) {
            (Ok(checks), Ok(())) => (checks.verdict, Value::Object(checks.values.clone()), None),
            (Ok(checks), Err(error)) => (
                "HARNESS_ERROR",
                Value::Object(checks.values.clone()),
                Some(error.clone()),
            ),
            (Err(error), _) => ("HARNESS_ERROR", Value::Null, Some(error.clone())),
        };
        if let Some(error) = &error {
            self.errors.push(format!("iter {iter}: {error}"));
        }
        *self.verdicts.entry(verdict.to_owned()).or_default() += 1;
        let line = json!({
            "lane": "OWN-09",
            "arm": self.cfg.arm,
            "strategy": self.cfg.strategy,
            "row": self.row,
            "variant": self.variant,
            "iter": iter,
            "utc_start": utc_start,
            "utc_end": utc_now(),
            "verdict": verdict,
            "error": error,
            "checks": checks,
            "notes": fx.map(|fx| Value::Object(fx.notes.clone())).unwrap_or(Value::Null),
            "events": fx.map(|fx| Value::Array(fx.shared.ledger.dump())).unwrap_or(Value::Null),
            "counters": fx.map(|fx| fx.shared.counters_json()).unwrap_or(Value::Null),
            "journal": fx.map(|fx| Value::Array(fx.shared.target.snapshot())).unwrap_or(Value::Null),
        });
        if let Some(file) = self.file.as_mut() {
            writeln!(file, "{line}").expect("write row log");
        }
    }

    /// The row test fails only on harness errors; verdicts are data.
    pub fn finish(self) {
        let mut verdicts: Vec<_> = self.verdicts.iter().collect();
        verdicts.sort();
        println!(
            "OWN09 arm={} strategy={} row={} variant={} verdicts={:?}",
            self.cfg.arm, self.cfg.strategy, self.row, self.variant, verdicts
        );
        assert!(
            self.errors.is_empty(),
            "harness errors in {} {}: {:#?}",
            self.row,
            self.variant,
            self.errors
        );
    }
}

/// Run `iterations()` fresh-runtime iterations of one row variant.
#[macro_export]
macro_rules! own09_row {
    ($cfg:expr, $row:literal, $variant:literal, |$fx:ident| $body:expr) => {{
        let cfg: $crate::own09_harness::ArmCfg = $cfg;
        let mut log = $crate::own09_harness::RowLog::open(cfg, $row, $variant);
        for iter in 0..$crate::own09_harness::iterations() {
            let _serial = $crate::own09_harness::serial();
            let utc_start = $crate::own09_harness::utc_stamp();
            match $crate::own09_harness::Fixture::new(cfg.spawn) {
                Err(error) => log.record(iter, utc_start, None, Err(error), Ok(())),
                Ok(mut fixture) => {
                    let result = {
                        let $fx = &mut fixture;
                        $body.await
                    };
                    let finish = fixture.finish().await;
                    log.record(iter, utc_start, Some(&fixture), result, finish);
                }
            }
        }
        log.finish();
    }};
}

pub fn utc_stamp() -> String {
    utc_now()
}

// ------------------------------------------------------------------ rows ---

pub async fn absent_then_release(fx: &mut Fixture, event: &str) -> bool {
    fx.absent(event).await
}

/// R1. Cancel while queued behind an admitted holder: the queued call never
/// enters the native closure. `detach` is the broken control: the waiter
/// returns but the queued work is left running ("cancel signals only the
/// waiter").
pub async fn r1_cancel_while_queued(fx: &mut Fixture, detach: bool) -> Result<Checks, String> {
    let (holder, queued, witness) = (1, 2, 3);
    fx.gate(holder);
    fx.gate(queued);
    fx.gate(witness);
    let first = fx.call(holder, json!({}));
    fx.wait(&format!("native-enter:{holder}")).await?;
    let second = fx.call(queued, json!({}));
    let queued_not_admitted = fx.absent(&format!("admitted:{queued}")).await;
    // Pre-release the queued gate so a wrongly admitted call cannot wedge the
    // run: if it ever enters native work the counter records it.
    fx.release(queued);
    let mut detached = None;
    if detach {
        fx.log(format!("cancel-requested:{queued}"));
        fx.log(format!("waiter-returned:{queued}"));
        detached = Some(second);
    } else {
        fx.cancel(second, queued).await?;
    }
    fx.release(holder);
    let first = fx.outcome(first, holder).await?;
    fx.wait(&format!("native-exit:{holder}")).await?;
    if let Some(handle) = detached {
        // The detached call proceeds once the holder releases capacity.
        let _ = fx.outcome(handle, queued).await?;
    }
    let third = fx.call(witness, json!({}));
    fx.wait(&format!("native-enter:{witness}")).await?;
    fx.release(witness);
    let third = fx.outcome(third, witness).await?;
    let ledger = fx.ledger();
    let mut checks = Checks::new();
    checks.set("queued_not_admitted_within_window", queued_not_admitted);
    checks.set("holder_outcome", first);
    checks.set("witness_outcome", third);
    checks.set("queued_counter", json!(fx.shared.counter(queued)));
    checks.gate("queued_never_admitted", !ledger.has(&format!("admitted:{queued}")));
    checks.gate(
        "queued_never_entered_native",
        fx.shared.counter(queued) == [0, 0],
    );
    checks.gate(
        "witness_admitted_after_holder_native_exit",
        ledger.before(&format!("native-exit:{holder}"), &format!("admitted:{witness}")),
    );
    Ok(checks)
}

/// R1 race sub-variant: the queued call's cancellation races the holder's
/// release. Exactly one side wins; a cancelled-before-admission call never
/// enters native work later.
pub async fn r1_cancel_race(fx: &mut Fixture) -> Result<Checks, String> {
    let (holder, contender, witness) = (1, 2, 3);
    fx.gate(holder);
    fx.gate(contender);
    fx.gate(witness);
    let first = fx.call(holder, json!({}));
    fx.wait(&format!("native-enter:{holder}")).await?;
    let queued = fx.call(contender, json!({}));
    let _ = fx.absent(&format!("admitted:{contender}")).await;
    fx.release(contender);
    let releaser = fx
        .releases
        .remove(&holder)
        .ok_or("holder gate missing")?;
    let start = Arc::new(std::sync::Barrier::new(2));
    let thread_start = start.clone();
    let ledger = fx.ledger();
    let release_thread = std::thread::spawn(move || {
        thread_start.wait();
        ledger.log(format!("release:{holder}"));
        let _ = releaser.send(());
    });
    start.wait();
    let cancelled = fx.cancel(queued, contender).await?;
    release_thread.join().map_err(|_| "release thread panicked")?;
    let first = fx.outcome(first, holder).await?;
    let ledger = fx.ledger();
    let admitted = ledger.has(&format!("admitted:{contender}"));
    if admitted {
        fx.wait(&format!("native-exit:{contender}")).await?;
    }
    let third = fx.call(witness, json!({}));
    fx.wait(&format!("native-enter:{witness}")).await?;
    fx.release(witness);
    let third = fx.outcome(third, witness).await?;
    let mut checks = Checks::new();
    checks.set("winner", if admitted { "admission" } else { "cancel" });
    checks.set("waiter_observed_cancel", cancelled);
    checks.set("holder_outcome", first);
    checks.set("witness_outcome", third);
    checks.set("contender_counter", json!(fx.shared.counter(contender)));
    checks.gate(
        "cancel_winner_never_entered_native",
        admitted || fx.shared.counter(contender) == [0, 0],
    );
    Ok(checks)
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum R2 {
    CancelAfterAdmission,
    ControlNoCancel,
}

/// R2. After admission, capacity stays owned until the native closure exits.
pub async fn r2_capacity_owned_until_native_exit(
    fx: &mut Fixture,
    variant: R2,
) -> Result<Checks, String> {
    let (owner, probe) = (1, 2);
    fx.gate(owner);
    fx.gate(probe);
    let first = fx.call(owner, json!({}));
    fx.wait(&format!("native-enter:{owner}")).await?;
    let mut first = Some(first);
    let mut route = Value::Null;
    if variant == R2::CancelAfterAdmission {
        fx.cancel(first.take().unwrap(), owner).await?;
        // Route attribution: the abort reached the dispatch frame.
        let reached = fx
            .wait(&format!("invocation-dropped:{owner}"))
            .await
            .is_ok();
        route = json!(reached);
    }
    let native_running_after_cancel = !fx.ledger().has(&format!("native-exit:{owner}"));
    let second = fx.call(probe, json!({}));
    let probe_admitted_in_window = !fx.absent(&format!("admitted:{probe}")).await;
    fx.release(owner);
    fx.wait(&format!("native-exit:{owner}")).await?;
    fx.wait(&format!("native-enter:{probe}")).await?;
    fx.release(probe);
    let second = fx.outcome(second, probe).await?;
    let first = match first {
        Some(handle) => fx.outcome(handle, owner).await?,
        None => json!({"cancelled": true}),
    };
    let ledger = fx.ledger();
    let mut checks = Checks::new();
    checks.set("cancel_reached_dispatch_frame", route);
    checks.set("native_running_after_cancel", native_running_after_cancel);
    checks.set("probe_admitted_within_window", probe_admitted_in_window);
    checks.set("owner_outcome", first);
    checks.set("probe_outcome", second);
    checks.gate(
        "permit_not_reusable_before_native_exit",
        ledger.before(&format!("native-exit:{owner}"), &format!("admitted:{probe}")),
    );
    Ok(checks)
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum R4 {
    AfterCompletion,
    AfterInflightCancel,
    /// Broken control: a cancel registry keyed by tool name.
    BrokenNameKeyed,
}

/// R4. A late cancel of issuance 1 cannot reach a later issuance 2.
pub async fn r4_late_cancel(fx: &mut Fixture, variant: R4) -> Result<Checks, String> {
    let (early, later) = (1, 2);
    fx.gate(early);
    fx.gate(later);
    let mut by_name: HashMap<&'static str, tokio::task::AbortHandle> = HashMap::new();
    let first = fx.call(early, json!({"effect": true}));
    let early_abort = first.abort_handle();
    by_name.insert(TOOL, first.abort_handle());
    fx.wait(&format!("native-enter:{early}")).await?;
    let first_outcome = match variant {
        R4::AfterCompletion | R4::BrokenNameKeyed => {
            fx.release(early);
            fx.outcome(first, early).await?
        }
        R4::AfterInflightCancel => {
            fx.cancel(first, early).await?;
            json!({"cancelled": true})
        }
    };
    let second = fx.call(later, json!({"effect": true}));
    by_name.insert(TOOL, second.abort_handle());
    if fx.absent(&format!("admitted:{later}")).await {
        // Arm P keeps capacity owned by the cancelled early call.
        fx.release(early);
        fx.wait(&format!("native-exit:{early}")).await?;
    }
    fx.wait(&format!("native-enter:{later}")).await?;
    fx.log(format!("late-cancel:{early}"));
    match variant {
        R4::BrokenNameKeyed => {
            if let Some(handle) = by_name.get(TOOL) {
                handle.abort();
            }
        }
        _ => early_abort.abort(),
    }
    let later_not_dropped_in_window = fx.absent(&format!("invocation-dropped:{later}")).await;
    fx.release(early);
    fx.release(later);
    let second_outcome = fx.outcome(second, later).await?;
    fx.wait(&format!("native-exit:{later}")).await?;
    let ledger = fx.ledger();
    let mut checks = Checks::new();
    checks.set("early_outcome", first_outcome);
    checks.set("later_outcome", second_outcome.clone());
    checks.set("later_not_dropped_within_window", later_not_dropped_in_window);
    checks.gate(
        "later_completed_ok",
        second_outcome.get("is_error") == Some(&Value::Bool(false)),
    );
    checks.gate(
        "later_dispatch_not_dropped_early",
        ledger.before(&format!("invoke-end:{later}"), &format!("invocation-dropped:{later}")),
    );
    checks.gate("later_native_once", fx.shared.counter(later) == [1, 1]);
    Ok(checks)
}

/// Adapter from the core MCP dispatcher to the public SDK (barrier tool).
pub struct SdkProvider {
    driver: Arc<CuaDriver>,
    tools: Value,
}

impl SdkProvider {
    pub async fn new(driver: Arc<CuaDriver>) -> Result<Self, String> {
        let tools = driver
            .list_tools_json()
            .await
            .map_err(|error| format!("list tools: {error}"))?;
        let tools = serde_json::from_str(&tools).map_err(|error| error.to_string())?;
        Ok(Self { driver, tools })
    }
}

#[async_trait::async_trait]
impl ToolProvider for SdkProvider {
    fn tools_list(&self) -> Value {
        self.tools.clone()
    }

    async fn invoke_tool(&self, name: &str, arguments: Value) -> Result<Value, String> {
        let result = self
            .driver
            .call_tool(name.to_owned(), arguments.to_string())
            .await
            .map_err(|error| error.to_string())?;
        serde_json::from_str(&result.raw_json).map_err(|error| error.to_string())
    }
}

fn mcp_request(id: Option<Value>, method: &str, params: Value) -> Result<Request, String> {
    let mut raw = json!({"jsonrpc": "2.0", "method": method, "params": params});
    if let Some(id) = id {
        raw["id"] = id;
    }
    serde_json::from_value(raw).map_err(|error| error.to_string())
}

async fn mcp_notify_cancelled(
    provider: &SdkProvider,
    request_id: u64,
    transport: &str,
) -> Result<Value, String> {
    let request = mcp_request(
        None,
        "notifications/cancelled",
        json!({"requestId": request_id, "reason": "own09 cancel"}),
    )?;
    let response = cua_driver_core::server::handle_request_with_transport_session(
        request,
        Value::Null,
        provider,
        transport,
    )
    .await;
    serde_json::to_value(&response).map_err(|error| error.to_string())
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum R5 {
    Normal,
    /// Broken control: a cancel registry keyed by the claimed public session.
    BrokenSessionKeyed,
}

/// R5 (also kvnloo/cua#36 cancellation cross-session row). A foreign session
/// or transport cannot cancel, end or substitute into this operation.
pub async fn r5_foreign_cancel(fx: &mut Fixture, variant: R5) -> Result<Checks, String> {
    let (own, foreign_mutation) = (1, 2);
    fx.gate(own);
    fx.gate(foreign_mutation);
    fx.release(foreign_mutation);
    let session_a = fx.trusted_session("own09-a")?;
    let session_b = fx.trusted_session("own09-b")?;
    let mut by_session: HashMap<String, tokio::task::AbortHandle> = HashMap::new();
    let first = fx.session_call(&session_a, TOOL, own, json!({"effect": true}));
    by_session.insert("own09-a".into(), first.abort_handle());
    fx.wait(&format!("native-enter:{own}")).await?;

    // f1: foreign session substitutes A's public session into a mutation.
    let f1 = fx.session_call(
        &session_b,
        TOOL,
        foreign_mutation,
        json!({"effect": true, "session": "own09-a"}),
    );
    let f1 = fx.outcome(f1, foreign_mutation).await?;
    // f2: foreign session tries to end A.
    let f2 = fx.session_call(&session_b, "end_session", 90, json!({"session": "own09-a"}));
    let f2 = fx.outcome(f2, 90).await?;
    // f3: foreign MCP transport sends notifications/cancelled for A's id.
    let provider = SdkProvider::new(fx.driver.clone()).await?;
    let f3 = mcp_notify_cancelled(&provider, own, "own09-transport-b").await?;
    // f4: broken control acts on the foreign claim.
    if variant == R5::BrokenSessionKeyed {
        fx.log("foreign-session-cancel-accepted:own09-a");
        if let Some(handle) = by_session.get("own09-a") {
            handle.abort();
        }
    }
    // f5: foreign session ends itself and closes its handle.
    let f5 = fx.session_call(&session_b, "end_session", 91, json!({}));
    let f5 = fx.outcome(f5, 91).await?;
    session_b.close();
    fx.log("foreign-actions-complete");
    let own_not_dropped_in_window = fx.absent(&format!("invocation-dropped:{own}")).await;
    fx.release(own);
    let own_outcome = fx.outcome(first, own).await?;
    fx.wait(&format!("native-exit:{own}")).await?;
    session_a.close();
    let ledger = fx.ledger();
    let mut checks = Checks::new();
    checks.set("foreign_substituted_mutation", f1.clone());
    checks.set("foreign_end_of_a", f2.clone());
    checks.set("foreign_mcp_cancel_response", f3);
    checks.set("foreign_self_end", f5);
    checks.set("own_outcome", own_outcome.clone());
    checks.set("own_not_dropped_within_window", own_not_dropped_in_window);
    checks.gate(
        "own_completed_ok",
        own_outcome.get("is_error") == Some(&Value::Bool(false)),
    );
    checks.gate(
        "own_dispatch_not_dropped_early",
        ledger.before(&format!("invoke-end:{own}"), &format!("invocation-dropped:{own}")),
    );
    checks.gate(
        "foreign_mutation_never_admitted",
        !ledger.has(&format!("admitted:{foreign_mutation}"))
            && fx.shared.counter(foreign_mutation) == [0, 0],
    );
    checks.gate(
        "foreign_end_refused",
        f2.get("is_error") == Some(&Value::Bool(true)) || f2.get("driver_error").is_some(),
    );
    checks.gate(
        "target_has_exactly_own_effect",
        fx.shared.target.landed_ids() == vec![own],
    );
    Ok(checks)
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum R6 {
    ShutdownNoCancel,
    ShutdownAfterCancel,
    EndSessionNoCancel,
    EndSessionAfterCancel,
    /// Broken control: the host treats the cancelled waiter's return as drained.
    BrokenReadyOnCancel,
}

/// R6. Session end or shutdown does not claim readiness before admitted
/// native work exits.
pub async fn r6_readiness(fx: &mut Fixture, variant: R6) -> Result<Checks, String> {
    let own = 1;
    fx.gate(own);
    let session_variant = matches!(variant, R6::EndSessionNoCancel | R6::EndSessionAfterCancel);
    let cancel = matches!(
        variant,
        R6::ShutdownAfterCancel | R6::EndSessionAfterCancel | R6::BrokenReadyOnCancel
    );
    let session = if session_variant {
        Some(fx.trusted_session("own09-end")?)
    } else {
        None
    };
    let mut _hook = None;
    if let Some(prefix) = fx.driver.runtime_scope_prefix() {
        let key = format!("{prefix}own09-end");
        let ledger = fx.ledger();
        _hook = Some(cua_driver_core::session::register_scoped_session_end_hook(
            move |ended| {
                if ended == key {
                    ledger.log("session-cleanup");
                } else if ended.contains("own09") {
                    ledger.log(format!("session-end-hook-other:{ended}"));
                }
            },
        ));
    }
    let first = match &session {
        Some(session) => fx.session_call(session, TOOL, own, json!({})),
        None => fx.call(own, json!({})),
    };
    fx.wait(&format!("native-enter:{own}")).await?;
    let mut first = Some(first);
    let mut route = Value::Null;
    if cancel {
        fx.cancel(first.take().unwrap(), own).await?;
        route = json!(fx
            .wait(&format!("invocation-dropped:{own}"))
            .await
            .is_ok());
    }
    let ready_event = if session_variant {
        "session-cleanup"
    } else {
        "shutdown-returned"
    };
    let mut readiness_task = None;
    let mut end_result = Value::Null;
    match variant {
        R6::BrokenReadyOnCancel => fx.log("shutdown-returned"),
        R6::ShutdownNoCancel | R6::ShutdownAfterCancel => {
            let driver = fx.driver.clone();
            let ledger = fx.ledger();
            fx.log("shutdown-requested");
            readiness_task = Some(tokio::spawn(async move {
                let result = driver.shutdown().await;
                ledger.log("shutdown-returned");
                json!({"ok": result.is_ok()})
            }));
        }
        R6::EndSessionNoCancel | R6::EndSessionAfterCancel => {
            let session = session.as_ref().unwrap();
            fx.log("end-session-requested");
            let end = fx.session_call(session, "end_session", 70, json!({}));
            end_result = fx.outcome(end, 70).await?;
            fx.log("end-session-returned");
        }
    }
    let ready_within_window = !fx.absent(ready_event).await;
    let native_running_at_readiness = !fx.ledger().has(&format!("native-exit:{own}"));
    fx.release(own);
    fx.wait(&format!("native-exit:{own}")).await?;
    let readiness_result = match readiness_task {
        Some(task) => tokio::time::timeout(WAIT, task)
            .await
            .map_err(|_| "shutdown never returned")?
            .map_err(|error| error.to_string())?,
        None => Value::Null,
    };
    let readiness_seen = fx.wait(ready_event).await.is_ok();
    let first = match first {
        Some(handle) => fx.outcome(handle, own).await?,
        None => json!({"cancelled": true}),
    };
    let ledger = fx.ledger();
    let mut checks = Checks::new();
    checks.set("cancel_reached_dispatch_frame", route);
    checks.set("readiness_event", ready_event);
    checks.set("readiness_within_window", ready_within_window);
    checks.set("native_running_when_window_closed", native_running_at_readiness);
    checks.set("shutdown_result", readiness_result);
    checks.set("end_session_result", end_result);
    checks.set("own_outcome", first);
    checks.set(
        "end_session_returned_before_native_exit",
        ledger.has("end-session-returned")
            && ledger.before("end-session-returned", &format!("native-exit:{own}")),
    );
    checks.gate("readiness_eventually_observed", readiness_seen);
    checks.gate(
        "readiness_not_before_native_exit",
        ledger.before(&format!("native-exit:{own}"), ready_event),
    );
    drop(_hook);
    Ok(checks)
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum R7 {
    /// Ack lost; reconciling caller issues a target-guarded retry.
    AckLostGuardedRetry,
    /// Positive control: the ack arrives, no retry.
    ControlAck,
    /// Broken control: the unchanged read authorizes an unguarded retry.
    BrokenBlindRetry,
    /// Characterization: the original's effect lands after native exit.
    DelayedAfterNativeExit,
}

/// R7 (with R2-05 / kvnloo/cua#105). admitted -> caller loses the ack ->
/// first fresh read unchanged -> native work exits and the effect lands later.
/// The unchanged read must not free capacity or authorize a second mutation.
pub async fn r7_delayed_effect(fx: &mut Fixture, variant: R7) -> Result<Checks, String> {
    let (original, retry) = (1, 2);
    fx.gate(original);
    fx.gate(retry);
    if variant == R7::DelayedAfterNativeExit {
        fx.defer_effect(original);
    }
    // The original is an ordinary (unguarded) mutation.
    let first = fx.call(original, json!({"effect": true}));
    fx.wait(&format!("native-enter:{original}")).await?;
    let mut checks = Checks::new();
    if variant == R7::ControlAck {
        fx.release(original);
        let outcome = fx.outcome(first, original).await?;
        let read = fx.shared.target.landed();
        fx.log(format!("first-read:{read}"));
        checks.set("original_outcome", outcome);
        checks.set("first_read_landed", read);
        checks.set("retry_issued", false);
        checks.gate("target_exactly_one_effect", fx.shared.target.landed() == 1);
        return Ok(checks);
    }
    fx.cancel(first, original).await?;
    let first_read = fx.shared.target.landed();
    fx.log(format!("first-read:{first_read}"));
    let guard = match variant {
        R7::BrokenBlindRetry => Value::Null,
        _ => json!(first_read),
    };
    let second = fx.call(retry, json!({"effect": true, "guard": guard}));
    let retry_admitted_early = !fx.absent(&format!("admitted:{retry}")).await;
    if retry_admitted_early {
        // The stuck original lands after any work allowed to run past it.
        fx.wait(&format!("native-enter:{retry}")).await?;
        fx.release(retry);
        fx.wait(&format!("native-exit:{retry}")).await?;
        fx.release(original);
        fx.wait(&format!("native-exit:{original}")).await?;
    } else {
        fx.release(original);
        fx.wait(&format!("native-exit:{original}")).await?;
        fx.wait(&format!("native-enter:{retry}")).await?;
        fx.release(retry);
        fx.wait(&format!("native-exit:{retry}")).await?;
    }
    if variant == R7::DelayedAfterNativeExit {
        fx.commit(original);
        fx.wait(&format!("effect-settled:{original}")).await?;
    }
    let retry_outcome = fx.outcome(second, retry).await?;
    let ledger = fx.ledger();
    checks.set("first_read_landed", first_read);
    checks.set("retry_guard", guard);
    checks.set("retry_admitted_within_window", retry_admitted_early);
    checks.set("retry_outcome", retry_outcome);
    checks.set("landed_ids", json!(fx.shared.target.landed_ids()));
    checks.gate("first_read_unchanged", first_read == 0);
    checks.gate(
        "unchanged_read_did_not_free_capacity",
        ledger.before(&format!("native-exit:{original}"), &format!("admitted:{retry}")),
    );
    checks.gate("target_exactly_one_effect", fx.shared.target.landed() == 1);
    Ok(checks)
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum R8 {
    Normal,
    /// Broken control: a transport that honors notifications/cancelled by
    /// aborting the in-flight request future.
    BrokenHonoringTransport,
}

/// R8. notifications/cancelled during an in-flight tools/call, through the
/// shared core MCP dispatcher over the SDK (the stdio loop itself lives in
/// the binary crate and drops notifications before dispatch).
pub async fn r8_mcp_cancelled_notification(fx: &mut Fixture, variant: R8) -> Result<Checks, String> {
    let own: u64 = 801;
    fx.gate(own);
    let provider = Arc::new(SdkProvider::new(fx.driver.clone()).await?);
    let request = mcp_request(
        Some(json!(own)),
        "tools/call",
        json!({"name": TOOL, "arguments": {"id": own, "effect": true}}),
    )?;
    let call_provider = provider.clone();
    fx.log(format!("queued:{own}"));
    let ledger = fx.ledger();
    let call = tokio::spawn(async move {
        let response = cua_driver_core::server::handle_request_with_transport_session(
            request,
            json!(own),
            call_provider.as_ref(),
            "own09-transport-a",
        )
        .await;
        ledger.log(format!("mcp-response:{own}"));
        serde_json::to_value(&response).unwrap_or(Value::Null)
    });
    fx.wait(&format!("native-enter:{own}")).await?;
    let mut checks = Checks::new();
    let mut call = Some(call);
    match variant {
        R8::Normal => {
            let same = mcp_notify_cancelled(&provider, own, "own09-transport-a").await?;
            fx.log("notification-dispatched:same-transport");
            let foreign = mcp_notify_cancelled(&provider, own, "own09-transport-b").await?;
            fx.log("notification-dispatched:foreign-transport");
            checks.set("same_transport_notification_response", same);
            checks.set("foreign_transport_notification_response", foreign);
        }
        R8::BrokenHonoringTransport => {
            fx.log("notification-honored:same-transport");
            let handle = call.take().unwrap();
            handle.abort();
            let _ = tokio::time::timeout(WAIT, handle).await;
        }
    }
    let not_dropped_in_window = fx.absent(&format!("invocation-dropped:{own}")).await;
    fx.release(own);
    fx.wait(&format!("native-exit:{own}")).await?;
    let response = match call {
        Some(handle) => tokio::time::timeout(WAIT, handle)
            .await
            .map_err(|_| "mcp tools/call never responded")?
            .map_err(|error| error.to_string())?,
        None => Value::Null,
    };
    let ledger = fx.ledger();
    let dropped_early =
        !ledger.before(&format!("invoke-end:{own}"), &format!("invocation-dropped:{own}"));
    let delivered = response.pointer("/result").is_some()
        && response.pointer("/result/isError") != Some(&Value::Bool(true));
    let outcome = if !dropped_early && delivered {
        "ignored"
    } else {
        "honored"
    };
    checks.set("in_flight_response", response);
    checks.set("not_dropped_within_window", not_dropped_in_window);
    checks.set("landed", fx.shared.target.landed());
    checks.set("outcome", outcome);
    // Characterization row: the verdict is the observed classification.
    Ok(checks.verdict(if outcome == "ignored" {
        "IGNORED"
    } else {
        "HONORED"
    }))
}
