//! OWN-09 arm P: upstream main + kvnloo/cua#84 (AdmissionHold +
//! `spawn_blocking_owned`). The barrier tool's native closure retains the
//! call's admission permit through `spawn_blocking_owned`, the opt-in
//! primitive #84 adds. This file compiles only on a tree that contains #84;
//! build it with `--test own09_arm_p`. Verdicts go to `$OWN09_RAW_DIR/P/`.

#[macro_use]
mod own09_harness;

use own09_harness::*;

fn owned_spawn(work: NativeWork) -> NativeFuture {
    Box::pin(async move {
        cua_driver_core::tool::spawn_blocking_owned(work)
            .await
            .expect("native closure panicked")
    })
}

const ARM: ArmCfg = ArmCfg {
    arm: "P",
    strategy: "spawn_blocking_owned",
    spawn: owned_spawn,
};

/// Broken control on the same #84 tree: a plain closure releases the permit
/// with the dropped dispatch frame ("release on cancel, not native exit").
const ARM_PLAIN: ArmCfg = ArmCfg {
    arm: "P",
    strategy: "plain_spawn_blocking",
    spawn: plain_spawn,
};

include!("own09_harness/rows.rs");

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r2_broken_plain_closure() {
    own09_row!(ARM_PLAIN, "R2", "broken_plain_closure", |fx| {
        own09_harness::r2_capacity_owned_until_native_exit(fx, R2::CancelAfterAdmission)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r6_broken_plain_closure_shutdown() {
    own09_row!(ARM_PLAIN, "R6", "broken_plain_closure_shutdown_after_cancel", |fx| {
        own09_harness::r6_readiness(fx, R6::ShutdownAfterCancel)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r7_broken_plain_closure() {
    own09_row!(ARM_PLAIN, "R7", "broken_plain_closure", |fx| {
        own09_harness::r7_delayed_effect(fx, R7::AckLostGuardedRetry)
    });
}
