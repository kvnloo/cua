//! OWN-09R C ABI rows (kvnloo/cua#9), measured through the exported C entry
//! points `cua_driver_invoke_v1`, `cua_driver_operation_cancel_v1` and
//! `cua_driver_operation_release_v1`, with raw operation tokens retained by the
//! "host" exactly as a C, Python or TypeScript embedder holds them.
//!
//! Mounted from `abi.rs` under `cfg(test)` only, so it can wrap a runtime that
//! has a barrier-backed host tool in a `CuaDriverHandle` (the public C
//! constructor builds only the platform registry). No production code path is
//! changed by this file.
//!
//! - R4C: a late cancel issued on a retained token of an earlier operation
//!   (after it completed, or after it was already cancelled in flight) never
//!   reaches a later operation. Broken control: a host registry that resolves
//!   "cancel the press_key call" to the latest token.
//! - R1D: the admission window made deterministic. The queued operation's
//!   cancel flag is set while the asynchronous `work.abort()` is withheld (the
//!   state between `cua_driver_operation_cancel_v1` returning and the abort
//!   landing on the ABI executor). The queued call must never be admitted.
//!   Control: the same sequence without the flag is admitted after the holder.
//!
//! Oracle: fixture-owned native entry/exit counters, a target journal written
//! only by the native closure, and a callback journal written by the C
//! completion callback (count, status, result). Verdicts are data; a row test
//! fails only on harness errors. Raw lines go to `$OWN09R_RAW_DIR/<arm>/`.

use super::{
    copy_and_free_buffer, cua_driver_invoke_v1, cua_driver_operation_cancel_v1,
    cua_driver_operation_release_v1, CuaDriverBuffer, CuaDriverHandle, CuaDriverOperation,
    CuaDriverStatus,
};
use crate::runtime::{DriverRuntime, RuntimeOptions};
use cua_driver_core::protocol::ToolResult;
use cua_driver_core::tool::{Tool, ToolDef, ToolRegistry};
use serde_json::{json, Map, Value};
use std::collections::HashMap;
use std::ffi::c_void;
use std::io::Write;
use std::sync::atomic::Ordering;
use std::sync::{mpsc, Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const TOOL: &str = "press_key";
const WAIT: Duration = Duration::from_secs(10);
const NEGATIVE_WINDOW: Duration = Duration::from_millis(300);

fn iterations() -> usize {
    std::env::var("OWN09R_ITERS")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(40)
}

fn arm() -> String {
    std::env::var("OWN09R_ARM").unwrap_or_else(|_| "unlabelled".into())
}

fn utc_now() -> String {
    let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap();
    format!("{}.{:06}", now.as_secs(), now.subsec_micros())
}

// ---------------------------------------------------------------- ledger ---

struct Ledger {
    origin: Instant,
    events: Mutex<Vec<(usize, String, u128)>>,
    changed: tokio::sync::watch::Sender<u64>,
}

impl Ledger {
    fn new() -> Self {
        Self {
            origin: Instant::now(),
            events: Mutex::new(Vec::new()),
            changed: tokio::sync::watch::channel(0).0,
        }
    }

    fn log(&self, name: impl Into<String>) {
        {
            let mut events = self.events.lock().unwrap();
            let seq = events.len();
            events.push((seq, name.into(), self.origin.elapsed().as_micros()));
        }
        self.changed.send_modify(|version| *version += 1);
    }

    fn pos(&self, name: &str) -> Option<usize> {
        self.events
            .lock()
            .unwrap()
            .iter()
            .find(|(_, event, _)| event == name)
            .map(|(seq, _, _)| *seq)
    }

    fn has(&self, name: &str) -> bool {
        self.pos(name).is_some()
    }

    /// Both happened and `a` came first (strict: an absent `b` is not "after").
    fn strictly_before(&self, a: &str, b: &str) -> bool {
        matches!((self.pos(a), self.pos(b)), (Some(a), Some(b)) if a < b)
    }

    fn dump(&self) -> Value {
        Value::Array(
            self.events
                .lock()
                .unwrap()
                .iter()
                .map(|(seq, event, t_us)| json!([seq, event, t_us]))
                .collect(),
        )
    }

    async fn wait_until(
        &self,
        what: &str,
        limit: Duration,
        mut done: impl FnMut() -> bool,
    ) -> bool {
        let mut changed = self.changed.subscribe();
        let deadline = tokio::time::Instant::now() + limit;
        loop {
            if done() {
                return true;
            }
            match tokio::time::timeout_at(deadline, changed.changed()).await {
                Ok(Ok(())) => continue,
                _ => {
                    let _ = what;
                    return done();
                }
            }
        }
    }

    async fn wait_for(&self, name: &str) -> Result<(), String> {
        if self.wait_until(name, WAIT, || self.has(name)).await {
            Ok(())
        } else {
            Err(format!("phase barrier never reached: {name}"))
        }
    }

    async fn absent_within(&self, name: &str) -> bool {
        !self
            .wait_until(name, NEGATIVE_WINDOW, || self.has(name))
            .await
    }
}

// --------------------------------------------------------------- fixture ---

struct Shared {
    ledger: Arc<Ledger>,
    gates: Mutex<HashMap<u64, mpsc::Receiver<()>>>,
    counters: Mutex<HashMap<u64, [usize; 2]>>,
    journal: Mutex<Vec<Value>>,
}

impl Shared {
    fn count(&self, id: u64, slot: usize) {
        self.counters.lock().unwrap().entry(id).or_insert([0, 0])[slot] += 1;
    }
    fn counter(&self, id: u64) -> [usize; 2] {
        self.counters
            .lock()
            .unwrap()
            .get(&id)
            .copied()
            .unwrap_or([0, 0])
    }
    fn balanced(&self) -> bool {
        self.counters.lock().unwrap().values().all(|[a, b]| a == b)
    }
    fn landed_ids(&self) -> Vec<u64> {
        self.journal
            .lock()
            .unwrap()
            .iter()
            .filter_map(|entry| entry["id"].as_u64())
            .collect()
    }
}

static SHARED: Mutex<Option<Arc<Shared>>> = Mutex::new(None);

struct InvocationLifetime(Arc<Shared>, u64);
impl Drop for InvocationLifetime {
    fn drop(&mut self) {
        self.0.ledger.log(format!("invocation-dropped:{}", self.1));
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

    async fn invoke(&self, args: Value) -> ToolResult {
        let Some(id) = args["id"].as_u64() else {
            return ToolResult::error("own09r barrier tool requires an id");
        };
        let shared = self.shared.clone();
        shared.ledger.log(format!("admitted:{id}"));
        let _lifetime = InvocationLifetime(shared.clone(), id);
        let Some(gate) = shared.gates.lock().unwrap().remove(&id) else {
            return ToolResult::error("own09r barrier gate missing or reused");
        };
        let effect = args["effect"].as_bool().unwrap_or(false);
        let native = shared.clone();
        // Plain blocking closure on both arms: R4C/R1D are about operation
        // identity and the admission point, not about ownership after abort.
        let joined = tokio::task::spawn_blocking(move || {
            native.count(id, 0);
            native.ledger.log(format!("native-enter:{id}"));
            let released = gate.recv_timeout(WAIT).is_ok();
            if effect && released {
                native
                    .journal
                    .lock()
                    .unwrap()
                    .push(json!({"id": id, "effect": "applied"}));
                native.ledger.log(format!("effect-applied:{id}"));
            }
            native.ledger.log(format!("native-exit:{id}"));
            native.count(id, 1);
        })
        .await;
        if joined.is_err() {
            return ToolResult::error("own09r native closure panicked");
        }
        shared.ledger.log(format!("invoke-end:{id}"));
        ToolResult::text("native complete")
    }
}

fn register_barrier_tool(registry: &mut ToolRegistry) {
    let shared = SHARED.lock().unwrap().clone().expect("fixture installed");
    registry.register(Box::new(BarrierTool {
        def: ToolDef {
            name: TOOL.into(),
            description: "test-only OWN-09R barrier tool under a physical desktop tool name".into(),
            input_schema: json!({"type": "object"}),
            read_only: false,
            destructive: false,
            idempotent: false,
            open_world: false,
        },
        shared,
    }));
}

/// Completion slot owned by the "host": the C callback is its only writer.
struct Slot {
    id: u64,
    ledger: Arc<Ledger>,
    completions: Mutex<Vec<Value>>,
}

extern "C" fn on_complete(
    context: *mut c_void,
    status: CuaDriverStatus,
    mut result: CuaDriverBuffer,
    mut error: CuaDriverBuffer,
) {
    // SAFETY: the context is an `Arc<Slot>` leaked by `Fixture::invoke` and
    // reclaimed only after the fixture has observed this callback.
    let slot = unsafe { &*(context as *const Slot) };
    let result = unsafe { copy_and_free_buffer(&mut result) };
    let error = unsafe { copy_and_free_buffer(&mut error) };
    let parsed: Value = serde_json::from_str(&result).unwrap_or(Value::Null);
    slot.completions.lock().unwrap().push(json!({
        "status": format!("{status:?}"),
        "is_error": if parsed.is_object() {
            Value::Bool(parsed["isError"].as_bool().unwrap_or(false))
        } else {
            Value::Null
        },
        "refusal_code": parsed
            .pointer("/structuredContent/refusal/code")
            .cloned()
            .unwrap_or(Value::Null),
        "error": error,
    }));
    slot.ledger.log(format!("callback:{}:{status:?}", slot.id));
}

struct Op {
    token: *mut CuaDriverOperation,
    slot: Arc<Slot>,
    context: *const Slot,
}

struct Fixture {
    handle: *mut CuaDriverHandle,
    runtime: Arc<DriverRuntime>,
    shared: Arc<Shared>,
    releases: HashMap<u64, mpsc::Sender<()>>,
    ops: HashMap<u64, Op>,
    notes: Map<String, Value>,
}

impl Fixture {
    fn new() -> Result<Self, String> {
        let shared = Arc::new(Shared {
            ledger: Arc::new(Ledger::new()),
            gates: Mutex::new(HashMap::new()),
            counters: Mutex::new(HashMap::new()),
            journal: Mutex::new(Vec::new()),
        });
        *SHARED.lock().unwrap() = Some(shared.clone());
        let runtime = DriverRuntime::create(RuntimeOptions {
            prepare_desktop_environment: false,
            register_host_tools: Some(register_barrier_tool),
            ..RuntimeOptions::embedded(false)
        })
        .map_err(|error| format!("create runtime: {error}"))?;
        let handle = Box::into_raw(Box::new(CuaDriverHandle {
            runtime: runtime.clone(),
        }));
        Ok(Self {
            handle,
            runtime,
            shared,
            releases: HashMap::new(),
            ops: HashMap::new(),
            notes: Map::new(),
        })
    }

    fn ledger(&self) -> Arc<Ledger> {
        self.shared.ledger.clone()
    }

    fn log(&self, event: impl Into<String>) {
        self.shared.ledger.log(event);
    }

    fn gate(&mut self, id: u64) {
        let (tx, rx) = mpsc::channel();
        self.shared.gates.lock().unwrap().insert(id, rx);
        self.releases.insert(id, tx);
    }

    fn release(&mut self, id: u64) {
        if let Some(tx) = self.releases.remove(&id) {
            self.log(format!("release:{id}"));
            let _ = tx.send(());
        }
    }

    /// `cua_driver_invoke_v1`; the host retains the raw token.
    fn invoke(&mut self, id: u64, extra: Value) -> Result<*mut CuaDriverOperation, String> {
        let mut args = json!({ "id": id });
        if let Value::Object(extra) = extra {
            args.as_object_mut().unwrap().extend(extra);
        }
        let args = args.to_string();
        let slot = Arc::new(Slot {
            id,
            ledger: self.ledger(),
            completions: Mutex::new(Vec::new()),
        });
        let context = Arc::into_raw(slot.clone());
        let mut token = std::ptr::null_mut();
        let mut error = CuaDriverBuffer::empty();
        self.log(format!("queued:{id}"));
        let status = unsafe {
            cua_driver_invoke_v1(
                self.handle,
                TOOL.as_ptr(),
                TOOL.len(),
                args.as_ptr(),
                args.len(),
                Some(on_complete),
                context as *mut c_void,
                &mut token,
                &mut error,
            )
        };
        let error = unsafe { copy_and_free_buffer(&mut error) };
        if status != CuaDriverStatus::Ok || token.is_null() {
            unsafe { drop(Arc::from_raw(context)) };
            return Err(format!("invoke {id}: {status:?} {error}"));
        }
        self.ops.insert(
            id,
            Op {
                token,
                slot,
                context,
            },
        );
        Ok(token)
    }

    /// `cua_driver_operation_cancel_v1` on a retained raw token.
    fn cancel_token(&self, label: &str, token: *mut CuaDriverOperation) {
        self.log(format!("cancel-token:{label}"));
        unsafe { cua_driver_operation_cancel_v1(token) };
        self.log(format!("cancel-returned:{label}"));
    }

    fn completions(&self, id: u64) -> Vec<Value> {
        self.ops
            .get(&id)
            .map(|op| op.slot.completions.lock().unwrap().clone())
            .unwrap_or_default()
    }

    async fn wait_callback(&self, id: u64) -> Result<(), String> {
        let prefix = format!("callback:{id}:");
        let ledger = self.ledger();
        if ledger
            .wait_until(&prefix, WAIT, || {
                ledger
                    .events
                    .lock()
                    .unwrap()
                    .iter()
                    .any(|(_, event, _)| event.starts_with(&prefix))
            })
            .await
        {
            Ok(())
        } else {
            Err(format!("no completion callback for {id}"))
        }
    }

    async fn finish(&mut self) -> Result<(), String> {
        let ids: Vec<u64> = self.releases.keys().copied().collect();
        for id in ids {
            self.release(id);
        }
        let shared = self.shared.clone();
        let drained = self
            .ledger()
            .wait_until("native drained", WAIT, || shared.balanced())
            .await;
        for id in self.ops.keys().copied().collect::<Vec<_>>() {
            let _ = self.wait_callback(id).await;
        }
        tokio::time::timeout(WAIT, self.runtime.shutdown())
            .await
            .map_err(|_| "runtime shutdown did not return".to_string())?;
        self.log("cleanup-complete");
        if drained {
            Ok(())
        } else {
            Err("native closures did not drain".into())
        }
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        for (_, tx) in self.releases.drain() {
            let _ = tx.send(());
        }
        for (_, mut op) in self.ops.drain() {
            unsafe {
                cua_driver_operation_release_v1(&mut op.token);
                // Reclaim the callback context only once its callback ran;
                // otherwise leak it rather than race a late callback.
                if !op.slot.completions.lock().unwrap().is_empty() {
                    drop(Arc::from_raw(op.context));
                }
            }
        }
        unsafe {
            drop(Box::from_raw(self.handle));
        }
        *SHARED.lock().unwrap() = None;
    }
}

// ------------------------------------------------------------- recording ---

struct Checks {
    verdict: &'static str,
    values: Map<String, Value>,
}

impl Checks {
    fn new() -> Self {
        Self {
            verdict: "PASS",
            values: Map::new(),
        }
    }
    fn set(&mut self, key: &str, value: impl Into<Value>) {
        self.values.insert(key.into(), value.into());
    }
    fn gate(&mut self, key: &str, holds: bool) {
        self.values.insert(key.into(), Value::Bool(holds));
        if !holds {
            self.verdict = "FAIL";
        }
    }
}

async fn run_row<F, Fut>(row: &str, variant: &str, body: F)
where
    F: Fn(*mut Fixture) -> Fut,
    Fut: std::future::Future<Output = Result<Checks, String>>,
{
    let _serial = crate::runtime::TEST_RUNTIME_LOCK.lock().await;
    let arm = arm();
    let mut file = std::env::var("OWN09R_RAW_DIR").ok().map(|dir| {
        let dir = std::path::Path::new(&dir).join(&arm);
        std::fs::create_dir_all(&dir).expect("create raw dir");
        std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(dir.join(format!("{row}__{variant}.jsonl")))
            .expect("open row log")
    });
    let mut verdicts: HashMap<String, usize> = HashMap::new();
    let mut errors = Vec::new();
    for iter in 0..iterations() {
        let utc_start = utc_now();
        let mut fixture = match Fixture::new() {
            Ok(fixture) => fixture,
            Err(error) => {
                errors.push(format!("iter {iter}: {error}"));
                continue;
            }
        };
        let result = body(&mut fixture as *mut Fixture).await;
        let finish = fixture.finish().await;
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
            errors.push(format!("iter {iter}: {error}"));
        }
        *verdicts.entry(verdict.to_owned()).or_default() += 1;
        let callbacks: Map<String, Value> = fixture
            .ops
            .keys()
            .map(|id| (id.to_string(), Value::Array(fixture.completions(*id))))
            .collect();
        let counters: Map<String, Value> = fixture
            .shared
            .counters
            .lock()
            .unwrap()
            .iter()
            .map(|(id, c)| (id.to_string(), json!(c)))
            .collect();
        let line = json!({
            "lane": "OWN-09R",
            "route": "c_abi",
            "arm": arm,
            "strategy": "plain_spawn_blocking",
            "row": row,
            "variant": variant,
            "iter": iter,
            "utc_start": utc_start,
            "utc_end": utc_now(),
            "verdict": verdict,
            "error": error,
            "checks": checks,
            "notes": Value::Object(fixture.notes.clone()),
            "events": fixture.shared.ledger.dump(),
            "counters": Value::Object(counters),
            "journal": Value::Array(fixture.shared.journal.lock().unwrap().clone()),
            "callbacks": Value::Object(callbacks),
        });
        if let Some(file) = file.as_mut() {
            writeln!(file, "{line}").expect("write row log");
        }
    }
    let mut sorted: Vec<_> = verdicts.into_iter().collect();
    sorted.sort();
    println!("OWN09R arm={arm} route=c_abi row={row} variant={variant} verdicts={sorted:?}");
    assert!(
        errors.is_empty(),
        "harness errors in {row} {variant}: {errors:#?}"
    );
}

// ------------------------------------------------------------------ rows ---

#[derive(Clone, Copy, PartialEq, Eq)]
enum R4c {
    AfterCompletion,
    AfterInflightCancel,
    /// Broken control: the host resolves "cancel the press_key call" through a
    /// registry keyed by tool name, i.e. to the latest token.
    BrokenLatestToken,
}

async fn r4c_late_cancel_on_retained_token(
    fx: &mut Fixture,
    variant: R4c,
) -> Result<Checks, String> {
    let (early, later) = (1, 2);
    fx.gate(early);
    fx.gate(later);
    let mut by_name: HashMap<&'static str, *mut CuaDriverOperation> = HashMap::new();
    let early_token = fx.invoke(early, json!({"effect": true}))?;
    by_name.insert(TOOL, early_token);
    fx.ledger()
        .wait_for(&format!("native-enter:{early}"))
        .await?;
    match variant {
        R4c::AfterCompletion | R4c::BrokenLatestToken => {
            fx.release(early);
            fx.wait_callback(early).await?;
        }
        R4c::AfterInflightCancel => {
            fx.cancel_token("early-inflight", early_token);
            fx.wait_callback(early).await?;
        }
    }
    let later_token = fx.invoke(later, json!({"effect": true}))?;
    by_name.insert(TOOL, later_token);
    if fx
        .ledger()
        .absent_within(&format!("admitted:{later}"))
        .await
    {
        // Capacity is still owned by the cancelled early call's native work.
        fx.release(early);
        fx.ledger()
            .wait_for(&format!("native-exit:{early}"))
            .await?;
    }
    fx.ledger()
        .wait_for(&format!("native-enter:{later}"))
        .await?;
    // The late cancel: the host still holds the early token (not yet released).
    match variant {
        R4c::BrokenLatestToken => fx.cancel_token("late-by-name", by_name[TOOL]),
        _ => fx.cancel_token("late-retained-early", early_token),
    }
    let later_not_dropped = fx
        .ledger()
        .absent_within(&format!("invocation-dropped:{later}"))
        .await;
    fx.release(early);
    fx.release(later);
    fx.wait_callback(later).await?;
    fx.ledger()
        .wait_for(&format!("native-exit:{later}"))
        .await?;
    let ledger = fx.ledger();
    let early_callbacks = fx.completions(early);
    let later_callbacks = fx.completions(later);
    let mut checks = Checks::new();
    checks.set("later_not_dropped_within_window", later_not_dropped);
    checks.set("early_callbacks", Value::Array(early_callbacks.clone()));
    checks.set("later_callbacks", Value::Array(later_callbacks.clone()));
    checks.gate(
        "later_completed_ok_exactly_once",
        later_callbacks.len() == 1
            && later_callbacks[0]["status"] == "Ok"
            && later_callbacks[0]["is_error"] == Value::Bool(false),
    );
    checks.gate("early_completed_exactly_once", early_callbacks.len() == 1);
    checks.gate(
        "later_dispatch_not_dropped_early",
        ledger.strictly_before(
            &format!("invoke-end:{later}"),
            &format!("invocation-dropped:{later}"),
        ),
    );
    checks.gate("later_native_once", fx.shared.counter(later) == [1, 1]);
    checks.gate(
        "later_effect_landed_once",
        fx.shared
            .landed_ids()
            .iter()
            .filter(|id| **id == later)
            .count()
            == 1,
    );
    Ok(checks)
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum R1d {
    FlagBeforeAdmission,
    ControlNoCancel,
}

async fn r1d_admission_window(fx: &mut Fixture, variant: R1d) -> Result<Checks, String> {
    let (holder, queued, witness) = (1, 2, 3);
    fx.gate(holder);
    fx.gate(queued);
    fx.gate(witness);
    fx.invoke(holder, json!({}))?;
    fx.ledger()
        .wait_for(&format!("native-enter:{holder}"))
        .await?;
    let queued_token = fx.invoke(queued, json!({"effect": true}))?;
    let queued_waited = fx
        .ledger()
        .absent_within(&format!("admitted:{queued}"))
        .await;
    // A wrongly admitted call must complete instead of wedging the run.
    fx.release(queued);
    if variant == R1d::FlagBeforeAdmission {
        // The state right after `cua_driver_operation_cancel_v1` returned and
        // before `work.abort()` landed: the flag is set, the abort withheld.
        fx.log(format!("cancel-flag-set:{queued}"));
        let state = unsafe { &(*queued_token).state };
        state.cancelled.store(true, Ordering::Release);
    }
    fx.release(holder);
    fx.wait_callback(holder).await?;
    fx.ledger()
        .wait_for(&format!("native-exit:{holder}"))
        .await?;
    fx.wait_callback(queued).await?;
    fx.invoke(witness, json!({}))?;
    fx.ledger()
        .wait_for(&format!("native-enter:{witness}"))
        .await?;
    fx.release(witness);
    fx.wait_callback(witness).await?;
    let ledger = fx.ledger();
    let queued_callbacks = fx.completions(queued);
    let mut checks = Checks::new();
    checks.set("queued_waited_behind_holder", queued_waited);
    checks.set("queued_callbacks", Value::Array(queued_callbacks.clone()));
    checks.set("queued_counter", json!(fx.shared.counter(queued)));
    checks.gate(
        "witness_admitted_after_holder_native_exit",
        ledger.strictly_before(
            &format!("native-exit:{holder}"),
            &format!("admitted:{witness}"),
        ),
    );
    checks.gate("queued_completed_exactly_once", queued_callbacks.len() == 1);
    match variant {
        R1d::FlagBeforeAdmission => {
            checks.gate(
                "queued_never_admitted",
                !ledger.has(&format!("admitted:{queued}")),
            );
            checks.gate(
                "queued_never_entered_native",
                fx.shared.counter(queued) == [0, 0],
            );
            checks.gate(
                "queued_no_effect",
                !fx.shared.landed_ids().contains(&queued),
            );
            checks.set(
                "queued_refusal_code",
                queued_callbacks
                    .first()
                    .map(|c| c["refusal_code"].clone())
                    .unwrap_or(Value::Null),
            );
        }
        R1d::ControlNoCancel => {
            checks.gate(
                "queued_admitted_after_holder_native_exit",
                ledger.strictly_before(
                    &format!("native-exit:{holder}"),
                    &format!("admitted:{queued}"),
                ),
            );
            checks.gate("queued_effect_once", fx.shared.landed_ids() == vec![queued]);
        }
    }
    Ok(checks)
}

// Each row runs `OWN09R_ITERS` fresh-runtime iterations. The raw pointer only
// crosses the closure boundary; the fixture outlives every awaited body.
macro_rules! row {
    ($name:ident, $row:literal, $variant:literal, $body:ident, $arg:expr) => {
        #[tokio::test(flavor = "multi_thread", worker_threads = 4)]
        async fn $name() {
            run_row($row, $variant, |fx: *mut Fixture| {
                let fx = unsafe { &mut *fx };
                $body(fx, $arg)
            })
            .await;
        }
    };
}

row!(
    own09r_r4c_after_completion,
    "R4C",
    "after_completion_retained_token",
    r4c_late_cancel_on_retained_token,
    R4c::AfterCompletion
);
row!(
    own09r_r4c_after_inflight_cancel,
    "R4C",
    "after_inflight_cancel_retained_token",
    r4c_late_cancel_on_retained_token,
    R4c::AfterInflightCancel
);
row!(
    own09r_r4c_broken_latest_token,
    "R4C",
    "broken_latest_token",
    r4c_late_cancel_on_retained_token,
    R4c::BrokenLatestToken
);
row!(
    own09r_r1d_flag_before_admission,
    "R1D",
    "flag_before_admission",
    r1d_admission_window,
    R1d::FlagBeforeAdmission
);
row!(
    own09r_r1d_control_no_cancel,
    "R1D",
    "control_no_cancel",
    r1d_admission_window,
    R1d::ControlNoCancel
);

/// Unit gate for the revision (not a counted row): a call whose cancellation
/// was requested while it waited for admission is refused at the admission
/// point with `cancelled_before_admission`, even while the abort is withheld.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn revision_cancel_requested_before_admission_is_refused() {
    let _serial = crate::runtime::TEST_RUNTIME_LOCK.lock().await;
    let mut fx = Fixture::new().expect("fixture");
    let checks = r1d_admission_window(&mut fx, R1d::FlagBeforeAdmission)
        .await
        .expect("phases");
    fx.finish().await.expect("finish");
    assert_eq!(checks.verdict, "PASS", "{:#?}", checks.values);
    assert_eq!(
        checks.values["queued_refusal_code"],
        json!("cancelled_before_admission")
    );
}
