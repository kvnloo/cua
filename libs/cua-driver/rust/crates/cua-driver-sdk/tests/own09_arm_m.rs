//! OWN-09 arm M: upstream main as is. The barrier tool's native closure uses a
//! plain `tokio::task::spawn_blocking`, the same primitive production tools
//! use on main. Verdicts are written to `$OWN09_RAW_DIR/M/*.jsonl`; a row test
//! fails only on harness errors.

#[macro_use]
mod own09_harness;

use own09_harness::*;

const ARM: ArmCfg = ArmCfg {
    arm: "M",
    strategy: "plain_spawn_blocking",
    spawn: plain_spawn,
};

include!("own09_harness/rows.rs");
