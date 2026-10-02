// OWN-09 row tests shared by both arms. Included by own09_arm_m.rs and
// own09_arm_p.rs, each of which defines `ARM`. Every row runs
// `OWN09_ITERS` (default 20) fresh-runtime iterations.

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r1_cancel_while_queued() {
    own09_row!(ARM, "R1", "cancel_while_queued", |fx| {
        own09_harness::r1_cancel_while_queued(fx, false)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r1_broken_detach_on_cancel() {
    own09_row!(ARM, "R1", "broken_detach_on_cancel", |fx| {
        own09_harness::r1_cancel_while_queued(fx, true)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r1_cancel_race() {
    own09_row!(ARM, "R1", "cancel_race", |fx| own09_harness::r1_cancel_race(fx));
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r2_cancel_after_admission() {
    own09_row!(ARM, "R2", "cancel_after_admission", |fx| {
        own09_harness::r2_capacity_owned_until_native_exit(fx, R2::CancelAfterAdmission)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r2_control_no_cancel() {
    own09_row!(ARM, "R2", "control_no_cancel", |fx| {
        own09_harness::r2_capacity_owned_until_native_exit(fx, R2::ControlNoCancel)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r4_after_completion() {
    own09_row!(ARM, "R4", "after_completion", |fx| {
        own09_harness::r4_late_cancel(fx, R4::AfterCompletion)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r4_after_inflight_cancel() {
    own09_row!(ARM, "R4", "after_inflight_cancel", |fx| {
        own09_harness::r4_late_cancel(fx, R4::AfterInflightCancel)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r4_broken_name_keyed() {
    own09_row!(ARM, "R4", "broken_name_keyed", |fx| {
        own09_harness::r4_late_cancel(fx, R4::BrokenNameKeyed)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r5_foreign_session_and_transport() {
    own09_row!(ARM, "R5", "foreign_session_and_transport", |fx| {
        own09_harness::r5_foreign_cancel(fx, R5::Normal)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r5_broken_session_keyed() {
    own09_row!(ARM, "R5", "broken_session_keyed", |fx| {
        own09_harness::r5_foreign_cancel(fx, R5::BrokenSessionKeyed)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r6_shutdown_no_cancel() {
    own09_row!(ARM, "R6", "shutdown_no_cancel", |fx| {
        own09_harness::r6_readiness(fx, R6::ShutdownNoCancel)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r6_shutdown_after_cancel() {
    own09_row!(ARM, "R6", "shutdown_after_cancel", |fx| {
        own09_harness::r6_readiness(fx, R6::ShutdownAfterCancel)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r6_end_session_no_cancel() {
    own09_row!(ARM, "R6", "end_session_no_cancel", |fx| {
        own09_harness::r6_readiness(fx, R6::EndSessionNoCancel)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r6_end_session_after_cancel() {
    own09_row!(ARM, "R6", "end_session_after_cancel", |fx| {
        own09_harness::r6_readiness(fx, R6::EndSessionAfterCancel)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r6_broken_ready_on_cancel() {
    own09_row!(ARM, "R6", "broken_ready_on_cancel", |fx| {
        own09_harness::r6_readiness(fx, R6::BrokenReadyOnCancel)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r7_ack_lost_guarded_retry() {
    own09_row!(ARM, "R7", "ack_lost_guarded_retry", |fx| {
        own09_harness::r7_delayed_effect(fx, R7::AckLostGuardedRetry)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r7_control_ack() {
    own09_row!(ARM, "R7", "control_ack", |fx| {
        own09_harness::r7_delayed_effect(fx, R7::ControlAck)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r7_broken_blind_retry() {
    own09_row!(ARM, "R7", "broken_blind_retry", |fx| {
        own09_harness::r7_delayed_effect(fx, R7::BrokenBlindRetry)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r7_delayed_after_native_exit() {
    own09_row!(ARM, "R7", "delayed_after_native_exit", |fx| {
        own09_harness::r7_delayed_effect(fx, R7::DelayedAfterNativeExit)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r8_notification_in_flight() {
    own09_row!(ARM, "R8", "notification_in_flight", |fx| {
        own09_harness::r8_mcp_cancelled_notification(fx, R8::Normal)
    });
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn r8_broken_honoring_transport() {
    own09_row!(ARM, "R8", "broken_honoring_transport", |fx| {
        own09_harness::r8_mcp_cancelled_notification(fx, R8::BrokenHonoringTransport)
    });
}
