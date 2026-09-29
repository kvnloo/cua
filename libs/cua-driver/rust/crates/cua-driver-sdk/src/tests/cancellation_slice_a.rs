//! RFC trycua/cua#3796 Slice A evidence: who owns physical-desktop admission while native work runs?
//!
//! Uses the real embedded SDK runtime (`CuaDriver::call_tool` -> `ToolRegistry::dispatch`) with a
//! barrier-backed test tool registered under a physical-desktop tool name, so dispatch takes the
//! process-wide desktop action coordinator exactly as it does for a real `press_key`.
//! Phase is proven by channels and an ordered event ledger, never by sleeps. The only bounded waits are
//! negative observations ("did not happen within N ms") and each of them is paired with a positive
//! ordering proof once the barrier is released.

use super::{CuaDriver, DriverHostOptions};
use cua_driver_core::protocol::ToolResult;
use cua_driver_core::tool::{spawn_blocking_owned, Tool, ToolDef, ToolRegistry};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::time::Duration;
use tokio::sync::Notify;

const WAIT: Duration = Duration::from_secs(5);
const NEGATIVE_WINDOW: Duration = Duration::from_millis(400);
/// A real physical-desktop tool name so dispatch applies the desktop action coordinator.
const TOOL: &str = "press_key";

#[derive(Default)]
struct Ledger {
    seq: AtomicUsize,
    events: Mutex<Vec<(usize, String)>>,
}

impl Ledger {
    fn log(&self, event: impl Into<String>) {
        let n = self.seq.fetch_add(1, Ordering::SeqCst);
        self.events.lock().unwrap().push((n, event.into()));
    }
    fn position(&self, event: &str) -> Option<usize> {
        self.events
            .lock()
            .unwrap()
            .iter()
            .find(|(_, e)| e == event)
            .map(|(n, _)| *n)
    }
    fn contains(&self, event: &str) -> bool {
        self.position(event).is_some()
    }
    fn dump(&self) -> Vec<String> {
        self.events
            .lock()
            .unwrap()
            .iter()
            .map(|(n, e)| format!("{n:02} {e}"))
            .collect()
    }
}

struct Gate {
    entered: Arc<Notify>,
    dropped: Arc<Notify>,
    release: Option<mpsc::Receiver<()>>,
}

struct Shared {
    ledger: Ledger,
    gates: Mutex<HashMap<u64, Gate>>,
}

static SHARED: Mutex<Option<Arc<Shared>>> = Mutex::new(None);

struct InvocationLifetime(Arc<Shared>, u64);
impl Drop for InvocationLifetime {
    fn drop(&mut self) {
        self.0.ledger.log(format!("invocation-dropped:{}", self.1));
        if let Some(gate) = self.0.gates.lock().unwrap().get(&self.1) {
            gate.dropped.notify_one();
        }
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
        let id = args["id"].as_u64().expect("test id");
        // Reaching invoke means dispatch admitted this call (coordinator taken).
        self.shared.ledger.log(format!("admitted:{id}"));
        let _lifetime = InvocationLifetime(self.shared.clone(), id);
        let (entered, receiver) = {
            let mut gates = self.shared.gates.lock().unwrap();
            let gate = gates.get_mut(&id).expect("gate registered");
            (
                gate.entered.clone(),
                gate.release.take().expect("single use"),
            )
        };
        let shared = self.shared.clone();
        let work = move || {
            shared.ledger.log(format!("native-enter:{id}"));
            entered.notify_one();
            let released = receiver.recv_timeout(WAIT);
            shared.ledger.log(format!("native-exit:{id}"));
            released.expect("test did not release native work");
        };
        if args["owned"].as_bool().unwrap_or(false) {
            // Prototype: the native closure retains the call's admission permit.
            spawn_blocking_owned(work).await.unwrap();
        } else {
            tokio::task::spawn_blocking(work).await.unwrap();
        }
        self.shared.ledger.log(format!("invoke-end:{id}"));
        ToolResult::text("native complete")
    }
}

fn register_barrier_tool(registry: &mut ToolRegistry) {
    let shared = SHARED.lock().unwrap().clone().expect("shared fixture");
    registry.register(Box::new(BarrierTool {
        def: ToolDef {
            name: TOOL.into(),
            description: "test-only barrier tool under a physical desktop tool name".into(),
            input_schema: json!({"type": "object"}),
            read_only: false,
            destructive: false,
            idempotent: false,
            open_world: false,
        },
        shared,
    }));
}

struct Fixture {
    driver: Arc<CuaDriver>,
    shared: Arc<Shared>,
    releases: HashMap<u64, mpsc::Sender<()>>,
    _serial: std::sync::MutexGuard<'static, ()>,
}

impl Fixture {
    fn new(ids: &[u64]) -> Self {
        let serial = crate::runtime::TEST_RUNTIME_LOCK.lock().unwrap();
        let shared = Arc::new(Shared {
            ledger: Ledger::default(),
            gates: Mutex::new(HashMap::new()),
        });
        let mut releases = HashMap::new();
        for id in ids {
            let (tx, rx) = mpsc::channel();
            shared.gates.lock().unwrap().insert(
                *id,
                Gate {
                    entered: Arc::new(Notify::new()),
                    dropped: Arc::new(Notify::new()),
                    release: Some(rx),
                },
            );
            releases.insert(*id, tx);
        }
        *SHARED.lock().unwrap() = Some(shared.clone());
        let driver = CuaDriver::try_create_for_host(DriverHostOptions {
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
        })
        .unwrap();
        Self {
            driver,
            shared,
            releases,
            _serial: serial,
        }
    }

    fn add_gate(&mut self, id: u64) {
        let (tx, rx) = mpsc::channel();
        self.shared.gates.lock().unwrap().insert(
            id,
            Gate {
                entered: Arc::new(Notify::new()),
                dropped: Arc::new(Notify::new()),
                release: Some(rx),
            },
        );
        self.releases.insert(id, tx);
    }

    fn entered(&self, id: u64) -> Arc<Notify> {
        self.shared.gates.lock().unwrap()[&id].entered.clone()
    }
    fn dropped(&self, id: u64) -> Arc<Notify> {
        self.shared.gates.lock().unwrap()[&id].dropped.clone()
    }
    fn release(&mut self, id: u64) {
        // Dropping the sender wakes recv_timeout with a disconnect; send() is the explicit release.
        if let Some(tx) = self.releases.remove(&id) {
            let _ = tx.send(());
        }
    }
    fn call(&self, id: u64) -> tokio::task::JoinHandle<Result<bool, String>> {
        self.call_with(id, false)
    }

    fn call_with(&self, id: u64, owned: bool) -> tokio::task::JoinHandle<Result<bool, String>> {
        let driver = self.driver.clone();
        self.shared.ledger.log(format!("queued:{id}"));
        tokio::spawn(async move {
            driver
                .call_tool(TOOL.into(), json!({ "id": id, "owned": owned }).to_string())
                .await
                .map(|result| result.is_error)
                .map_err(|e| e.to_string())
        })
    }
}

/// Registered ids that never released must not wedge later tests.
impl Drop for Fixture {
    fn drop(&mut self) {
        for (_, tx) in self.releases.drain() {
            let _ = tx.send(());
        }
    }
}

async fn phase(notify: &Notify, what: &str) {
    tokio::time::timeout(WAIT, notify.notified())
        .await
        .unwrap_or_else(|_| panic!("phase barrier never reached: {what}"));
}

/// True when the event did NOT happen inside the negative-observation window.
async fn did_not_happen(notify: &Notify) -> bool {
    tokio::time::timeout(NEGATIVE_WINDOW, notify.notified())
        .await
        .is_err()
}

async fn finish(handle: tokio::task::JoinHandle<Result<bool, String>>) {
    let result = tokio::time::timeout(WAIT, handle).await.unwrap().unwrap();
    assert_eq!(result, Ok(false), "barrier tool call should succeed");
}

fn write_ledger(name: &str, fx: &Fixture, extra: Value) {
    if let Ok(dir) = std::env::var("CUA_SLICE_A_LEDGER_DIR") {
        let body =
            json!({ "scenario": name, "events": fx.shared.ledger.dump(), "observed": extra });
        let _ = std::fs::create_dir_all(&dir);
        let _ = std::fs::write(
            std::path::Path::new(&dir).join(format!("{name}.json")),
            serde_json::to_string_pretty(&body).unwrap(),
        );
    }
}

/// A. Abandon while queued behind an admitted call: the queued call must never enter native work,
/// not now and not after the permit is released and a later call is admitted.
#[tokio::test]
async fn slice_a_cancel_before_admission_never_enters_native_work() {
    let mut fx = Fixture::new(&[1, 2, 3]);
    let first = fx.call(1);
    phase(&fx.entered(1), "call 1 native-enter").await;

    let queued = fx.call(2);
    assert!(
        did_not_happen(&fx.entered(2)).await,
        "call 2 entered native work while call 1 was admitted"
    );
    queued.abort();
    assert!(queued.await.unwrap_err().is_cancelled());
    fx.shared.ledger.log("cancel-observed:2");

    fx.release(1);
    finish(first).await;
    let third = fx.call(3);
    phase(&fx.entered(3), "call 3 native-enter after release").await;
    fx.release(3);
    finish(third).await;
    fx.shared.ledger.log("cleanup-complete");

    let ledger = &fx.shared.ledger;
    write_ledger("A_cancel_before_admission", &fx, json!({}));
    assert!(!ledger.contains("admitted:2"), "{:#?}", ledger.dump());
    assert!(!ledger.contains("native-enter:2"), "{:#?}", ledger.dump());
    assert!(ledger.position("native-exit:1") < ledger.position("admitted:3"));
}

/// Observation shared by the B characterization and the B invariant.
async fn cancel_after_admission_observation(owned: bool) -> (bool, Vec<String>, Value) {
    let mut fx = Fixture::new(&[1, 2]);
    let first = fx.call_with(1, owned);
    phase(&fx.entered(1), "call 1 native-enter").await;
    first.abort();
    assert!(first.await.unwrap_err().is_cancelled());
    fx.shared
        .ledger
        .log("cancel-observed:1 (public caller returned)");
    phase(&fx.dropped(1), "call 1 invocation dropped").await;
    let native_1_still_blocked = !fx.shared.ledger.contains("native-exit:1");

    let second = fx.call_with(2, owned);
    // Positive proof if it happens: native-enter:2 while native 1 has not exited.
    let reusable_before_native_exit =
        !did_not_happen(&fx.entered(2)).await && !fx.shared.ledger.contains("native-exit:1");
    fx.release(1);
    fx.release(2);
    finish(second).await;
    fx.shared.ledger.log("cleanup-complete");
    let observed = json!({
        "public_caller_returned_before_native_exit": native_1_still_blocked,
        "next_call_admitted_before_native_exit": reusable_before_native_exit,
    });
    write_ledger(
        if owned {
            "B_prototype_owned_blocking"
        } else {
            "B_cancel_after_admission"
        },
        &fx,
        observed.clone(),
    );
    (
        reusable_before_native_exit,
        fx.shared.ledger.dump(),
        observed,
    )
}

/// B. CURRENT MAIN (characterization): aborting an admitted call returns the public caller at once,
/// and the coordinator permit is released with the dropped future while the native closure is still
/// running.
#[tokio::test]
async fn slice_a_current_main_cancel_after_admission_releases_permit_before_native_exit() {
    let (reusable_before_native_exit, ledger, observed) =
        cancel_after_admission_observation(false).await;
    assert!(
        reusable_before_native_exit,
        "current main no longer releases the permit before native exit; update the RFC evidence: {observed} {ledger:#?}"
    );
    assert_eq!(
        observed["public_caller_returned_before_native_exit"],
        json!(true)
    );
}

/// B. RFC #3796 kill-gate invariant: admitted capacity stays owned until native exit.
/// Fails on current main (see the characterization test above); flip `ignore` off with the fix.
#[tokio::test]
#[ignore = "RFC #3796 kill gate: fails on current main until admitted work is owned until native exit"]
async fn slice_a_rfc_admitted_capacity_is_owned_until_native_exit() {
    let (reusable_before_native_exit, ledger, _) = cancel_after_admission_observation(false).await;
    assert!(
        !reusable_before_native_exit,
        "admitted capacity became reusable before native exit: {ledger:#?}"
    );
}

/// B. Prototype: a native closure that retains the admission permit (`spawn_blocking_owned`) makes the
/// same abort keep capacity owned until native exit, while the public caller still returns at once.
#[tokio::test]
async fn slice_a_prototype_owned_blocking_keeps_permit_until_native_exit() {
    let (reusable_before_native_exit, ledger, observed) =
        cancel_after_admission_observation(true).await;
    assert!(
        !reusable_before_native_exit,
        "prototype still released capacity early: {ledger:#?}"
    );
    assert_eq!(
        observed["public_caller_returned_before_native_exit"],
        json!(true)
    );
    let native_exit = ledger
        .iter()
        .position(|e| e.ends_with("native-exit:1"))
        .unwrap();
    let next_admitted = ledger
        .iter()
        .position(|e| e.ends_with("admitted:2"))
        .unwrap();
    assert!(native_exit < next_admitted, "{ledger:#?}");
}

/// C. Cancel racing the moment the permit becomes available: exactly one side wins per iteration, and a
/// queued call whose cancellation won never enters native work later.
#[tokio::test]
async fn slice_a_cancel_vs_native_entry_race_has_exactly_one_winner() {
    const ROUNDS: u64 = 60;
    let mut fx = Fixture::new(&[]);
    let (mut cancel_won, mut admission_won) = (0, 0);
    for round in 0..ROUNDS {
        let (holder, contender, witness) = (10 * round + 1, 10 * round + 2, 10 * round + 3);
        for id in [holder, contender, witness] {
            fx.add_gate(id);
        }
        let first = fx.call(holder);
        phase(&fx.entered(holder), "holder native-enter").await;
        let queued = fx.call(contender);
        assert!(did_not_happen(&fx.entered(contender)).await);

        let releaser = fx.releases.remove(&holder).unwrap();
        let start = Arc::new(std::sync::Barrier::new(2));
        let thread_start = start.clone();
        let release_thread = std::thread::spawn(move || {
            thread_start.wait();
            let _ = releaser.send(());
        });
        start.wait();
        queued.abort();
        let outcome = queued.await;
        release_thread.join().unwrap();
        finish(first).await;

        let admitted = fx.shared.ledger.contains(&format!("admitted:{contender}"));
        if admitted {
            // Admission won: the call ran to native work and must be released and drained.
            admission_won += 1;
            phase(&fx.entered(contender), "contender native-enter").await;
            fx.release(contender);
            phase(&fx.dropped(contender), "contender drained").await;
        } else {
            cancel_won += 1;
            assert!(outcome.unwrap_err().is_cancelled());
        }
        // A later call must be admitted; a cancelled-while-queued contender must not sneak in first.
        let later = fx.call(witness);
        phase(&fx.entered(witness), "witness native-enter").await;
        fx.release(witness);
        finish(later).await;
        if !admitted {
            assert!(
                !fx.shared
                    .ledger
                    .contains(&format!("native-enter:{contender}")),
                "queued-cancelled call {contender} entered native work later"
            );
        }
    }
    write_ledger(
        "C_cancel_vs_native_entry_race",
        &fx,
        json!({ "rounds": ROUNDS, "cancel_won": cancel_won, "admission_won": admission_won }),
    );
    assert_eq!(cancel_won + admission_won, ROUNDS);
}
