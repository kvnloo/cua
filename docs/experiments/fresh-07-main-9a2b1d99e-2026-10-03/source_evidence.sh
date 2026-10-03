#!/usr/bin/env bash
# FRESH-07 SOURCE evidence for (d) expectation.rs. Read-only git greps.
#   source_evidence.sh <repo> > raw/source/expectation-source.txt
set -uo pipefail
R="$1"; NEW=9a2b1d99ec8044ff58b2a2b46802edd2609c057b
cd "$R"
echo "# FRESH-07 (d) expectation.rs: display_only producers and verify_state consumers on 9a2b1d99e"
echo "## git grep -n display_only $NEW -- libs/cua-driver (every hit):"
git grep -n display_only "$NEW" -- libs/cua-driver
echo "## Linux producers (platform-linux, jev-use, cua-driver, cua-driver-sdk, cua-perception, cua-driver-core other than expectation.rs):"
git grep -n display_only "$NEW" -- libs/cua-driver/rust/crates/platform-linux libs/cua-driver/examples/jev-use \
  libs/cua-driver/rust/crates/cua-driver libs/cua-driver/rust/crates/cua-driver-sdk libs/cua-driver/rust/crates/cua-perception \
  libs/cua-driver/rust/crates/cua-driver-core ':!libs/cua-driver/rust/crates/cua-driver-core/src/expectation.rs' || echo "(none)"
echo "## callers of evaluate_predicates outside its unit tests (expectation.rs:295 is VerifyStateTool::invoke):"
git grep -n "evaluate_predicates(" "$NEW" -- libs/cua-driver/rust/crates | grep -v "let outcomes = evaluate_predicates"
echo "## Linux registration of VerifyStateTool:"
git grep -n "expectation::VerifyStateTool" "$NEW" -- libs/cua-driver/rust/crates/platform-linux
echo "## verify_state in the harness/source of every claim packet (raw/ excluded; 0 = the claim never calls Driver verify_state):"
while read -r b p; do
  n=$(git grep -l verify_state "$b" -- "$p" ":!$p/raw" 2>/dev/null | wc -l)
  echo "$b $(git rev-parse --short=9 "$b") files_with_verify_state=$n"
done <<'EOF'
exp/r2-10r-recert-a2-20261003 docs/experiments/r2-10r-recert-2026-10-03
exp/b-07-transport-residual-rprime-20261003 docs/experiments/b-07-transport-residual-rprime-2026-10-03
exp/b-08-per-process-cold-b7-20261003 docs/experiments/b-08-per-process-cold-b7-2026-10-03
exp/n-04-native-composition-rprime-20261003 docs/experiments/n-04-native-composition-rprime-2026-10-03
exp/n-03-native-closure-axfg-a3-20261003 docs/experiments/n-03-native-closure-axfg-2026-10-03
exp/own-20p-guard-port-a11y-20261003 docs/experiments/own-20p-guard-port-a11y-2026-10-03
exp/own-20q-a11y-triggers-dialog-markfree-20261003 docs/experiments/own-20q-a11y-triggers-dialog-markfree-2026-10-03
exp/fix-03-file-input-toctou-session-routing-20261003 docs/experiments/fix-03-toctou-session-routing-2026-10-03
exp/fix-recert-a3-20261003 docs/experiments/fix-recert-a3-2026-10-03
exp/own-16w-sway-modality-20261002 docs/experiments/own-16w-sway-modality-2026-10-02
EOF
echo "## jev-use (the runner the browser/native harnesses drive) on $NEW: verify_state mentions (comments only):"
git grep -n verify_state "$NEW" -- libs/cua-driver/examples/jev-use
