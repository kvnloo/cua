# Exact successful commands used, from indicated worktrees. No publication commands.
# Head cwd: ${HEAD_WORKTREE}
PYTHONPATH=libs/cua-bench CUA_TELEMETRY=0 EXPECT_ENVELOPES=1 RECEIPT_DIR=${HEAD_WORKTREE}/evidence/cua-4990-reward-paths-20261012/head ${VENV_ROOT}/bin/python -m pytest libs/cua-bench/cua_bench/tests/test_reward.py libs/cua-bench/cua_bench/tests/test_unified_runner.py libs/cua-bench/cua_bench/tests/test_interact_display.py libs/cua-bench/cua_bench/tests/test_4990_reward_paths_evidence.py --basetemp=${TEST_OUTPUT_ROOT}/cua-4990-head-final -q
# Base cwd: ${BASE_WORKTREE}
PYTHONPATH=libs/cua-bench CUA_TELEMETRY=0 EXPECT_ENVELOPES=0 RECEIPT_DIR=${HEAD_WORKTREE}/evidence/cua-4990-reward-paths-20261012/base ${VENV_ROOT}/bin/python -m pytest libs/cua-bench/cua_bench/tests/test_unified_runner.py libs/cua-bench/cua_bench/tests/test_interact_display.py libs/cua-bench/cua_bench/tests/test_4990_reward_paths_evidence.py --basetemp=${TEST_OUTPUT_ROOT}/cua-4990-base-final -q
# Head cwd: ${HEAD_WORKTREE}; expected pytest exit 1
PYTHONPATH=libs/cua-bench CUA_TELEMETRY=0 EXPECT_ENVELOPES=1 ASSERT_MEAN=1 RECEIPT_DIR=${HEAD_WORKTREE}/evidence/cua-4990-reward-paths-20261012/contract ${VENV_ROOT}/bin/python -m pytest libs/cua-bench/cua_bench/tests/test_4990_reward_paths_evidence.py --basetemp=${TEST_OUTPUT_ROOT}/cua-4990-contract -q
