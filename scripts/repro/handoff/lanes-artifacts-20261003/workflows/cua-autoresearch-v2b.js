export const meta = {
  name: 'cua-autoresearch-v2b',
  description: 'Autoresearch v2b (continuation after a usage-limit stop; the evaluator fix is already committed): re-run the full known-answer calibration, then (only if every row passes) a 10-candidate proposer pilot on the GTK3 checkbox; keeps stay local; fork-only publish',
  phases: [
    { title: 'Fix', detail: 'F1 normaliser, F2 p-value resolution vs LORD++, F3 trace-off check, A/A layout bias' },
    { title: 'Recal', detail: 'full calibration with known answers' },
    { title: 'Pilot', detail: 'gated proposer pilot, <=10 candidates' },
    { title: 'Report', detail: 'packet + fork publish' },
  ],
}

const isBreach = x => !!x && !/^\s*(none|no|n\/a|empty)\b/i.test(x)
const L = '/mnt/zer0models/github/cua-lanes'
const C = '/mnt/zer0models/github/cua'
const TMP = '/mnt/zer0models/cua-lane-tmp'
const ART = L + '/artifacts/ar'
const RULES = `
HARD RULES (hard_rule_breach = stop and report; near_miss = report and continue):
- Host desktop/session off limits: EVERY command that executes code (builds, tests, Python incl. gi/GTK, cua-driver, fixtures) runs under ${L}/bin/hostless, and GUI/Driver work inside a private session (${L}/cua-x11-session.sh with CUA_SESSION_ATSPI=1 and CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1"; see ${L}/artifacts/r2/SETUP.json and the R2-04 packet on branch exp/r2-04-atspi-profile-20261001 for the GTK3 harness). Plain host shell only for git, gh reads, file reads/edits. Never touch WAYLAND_DISPLAY/HYPRLAND_*/host XDG_RUNTIME_DIR, *-e2e wrappers or bypass variables; never kill processes you did not start.
- hard_rule_breach = something actually reached the host desktop/session, a secret exposed, anything written upstream, or a reported number measured outside the quiet lane. near_miss = could not have had an effect.
- Timing: every timed block via ${L}/bin/quiet-timed <label> <cmd> (exclusive lock + ledger). The RFC loop, a #107 track and a stack track share the machine and the lock; keep each timed block short (<= 10 min) so others interleave. Builds under hostless: flock ${TMP}/locks/cargo-build.lock ${L}/build-driver.sh <wt> <label> cua-release-ar (or cargo directly in a lane-private target dir under /mnt/zer0models/cargo-targets/ar-*), nice 19.
- No provider of any kind in this track (scripted/mock caller only).
- GitHub: only the Report agent writes, only to kvnloo/cua (new branches --no-follow-tags, never force; one comment on kvnloo/cua#93). Never upstream. Plain-text upstream refs.
- Git: worktrees ${L}/ar-<name>; branches ar/<tag>/* (local only, never pushed) and exp/ar-harness-20261002, exp/ar-pilot-20261002 (pushable); never stash; never touch other tracks' worktrees/branches/state (${L}/artifacts/r2/loop, ${L}/artifacts/i107, ${L}/artifacts/stack). Commit as 'Kevin Rajan <7121943+kvnloo@users.noreply.github.com>' + 'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'. No absolute paths/host name/secrets in pushable commits.
- Temp under ${TMP}.
- Invariants (kvnloo/cua#73/#93): no new services/threads/listeners/routers/registries; fresh verification retained; no blind replay; feedback code frozen in this pilot (owner default D1/D13).
Design source: the plan doc (sections Objective, Loop design, Keeping it meaningful); its key definitions are restated here so you do not need the doc. Owner defaults in force: D1 freeze feedback; D2 Rust kernel only (caller frozen); D4 no live provider; D6 exclusive quiet lane per timed block; D8 bwrap per-trial sandbox for the candidate Driver; D9 evaluator built and held by evaluator agents, never by proposers; D12 coordinate through the shared lock; D13 feedback files frozen. Single reference task: GTK3 checkbox toggle (libs/cua-driver/tests/fixtures/apps/linux/gtk3). Spot-check fixtures before any keep: GTK3 text entry + save, jev-use browser fill->submit. Segment-1 editable items: platform-linux/src/input/focus_guard.rs SETTLE_WATCH, SETTLE_WATCH_NEW_WINDOW, SETTLE_POLL and their polling function; foreground.rs settle constants + wait loop; targeted.rs OCCLUSION_SETTLE + wait; input/mod.rs EFFECT_SETTLE + wait; atspi/native.rs the four 50 ms post-DoAction sleeps (approx lines 3535, 3654, 4207, 4319 at 229b65b28), their enclosing functions and the 500 ms settle deadline. Everything else frozen (tests, phase_trace lines, Cargo files, contract/safety code, fixtures, harness).
T = harness CLOCK_MONOTONIC from Driver spawn to the frozen caller's verified done (oracle state file confirms; journal mutation timestamp <= done). Decision on ln-ratio paired AB/BA effect Delta with bootstrap CI; tau = max(2%, 97.5th pct |Delta_AA|); n_pairs = 10 (sigma/delta)^2 at delta=tau (one-sided alpha 0.01, 80% power); LORD++ online FDR at 0.05 across candidates; gates in order G0 scope/tamper (item allowlist, test-item hashes, phase_trace lines untouched, manifest sha256, scanner rules), G1 build+tests, G2 observable invariants every arm (no duplicate mutation, no unverified success, no stale dispatch, no blind replay, no new process/socket/file, provenance matches route), G3 controls (negatives stay negative, impossible canary refused/unknown), G4 identical verified counts, G5 latency superiority with LORD++ alpha_i and Delta-hat <= -ln(1+tau), G6 p90 tail guardrail, G7 mechanism (pre-registered phase shrinks >= 70% of the saving; trace-off trials agree within tau), G8 soak >= 300 trials zero failures (1000 for focus_guard/targeted edits), plus spot-check fixtures non-inferior. N-01 (native causal A/B on the same waits) may run concurrently in the RFC loop: read its packet if it exists, never duplicate it, cite it.`


const PRIOR = `Prior run (read ${ART}/SYNTHESIS.md, ${ART}/HARNESS.json, ${ART}/AA.json, ${ART}/CALIBRATION.json and the packets on exp/ar-harness-20261002 first):
- Phase 0 evaluator built (harness commits 34530c6d8, 4b5195c09, 2615af74f; champion base 457bc65d4, binary sha256 8464c444...c35209). Browser spot runner spot_browser_fill_submit now exists.
- A/A: whole-task T sigma_ln 0.0592, tau 3.11%, n_pairs 38 by power, BUT the A/A CI-includes-0 check FAILED: the env-padded rebuild of the same commit was 1.7% slower (build-layout bias). T_act passed.
- Calibration FAILED 9/10: R3 (real deletion of the 50 ms post-DoAction sleep) kept 0/10 because of evaluator defects:
  F1 (G2): each soak session binds a randomly named /tmp/dbus-<random> socket into the sandbox and G2's file-name normaliser reports it as a new file, so nothing reaching the soak can be kept.
  F2 (G5): after two tests with no rejection, the LORD++ alpha_i (2.3e-4) falls below the smallest p-value the 4000-resample bootstrap can produce (1/4001), so nothing can be kept afterwards.
  F3 (G7): the trace-off agreement check compares single values over about 8 pairs and rejects candidates when the host is loaded.
  Every R3 repeat ranked at screen with Delta -7% to -11% and all 2700 soak trials verified, so the defect is in the evaluator, not the candidate.`

const OUT = { type: 'object', properties: { ok: { type: 'boolean' }, summary: { type: 'string' }, artifacts: { type: 'string' }, hard_rule_breach: { type: 'string' }, near_miss: { type: 'string' } }, required: ['ok', 'summary', 'artifacts', 'hard_rule_breach', 'near_miss'] }

phase('Fix')
const fix = (args && args.fixFile) ? { ok: true, summary: `Evaluator fix ALREADY DONE and committed on exp/ar-harness-20261002 (f56422868 fix, 9cd19cfe4 prereg, 75abf40d2 packet, 48e031709 logs). Full result: read ${args.fixFile}. Key points: F1 G2 collapses only harness-recorded session binds; F2 G5 uses a one-sided paired sign-flip test with max(20000, ceil(20/alpha_i)) resamples; F3 G7 trace-off mean must fall inside the traced CI95 widened by ln(1+tau); decision metric is now T_act (whole-task T is a G6 guardrail); short A/A passed (T_act Delta +0.23%, CI -0.26..+0.71%). 103 python + 14 itemcheck tests pass; manifest 836a646e; selfcheck passes. Note: the old calibration packet's verifier imports the live harness and now needs the metric field; run it against its own evaluator 2615af74f.`, artifacts: args.fixFile, hard_rule_breach: 'none', near_miss: '' } : await agent(`Evaluator builder: fix the defects the calibration found, test-first, without weakening any gate.
${RULES}
${PRIOR}
In worktree ${L}/ar-harness on exp/ar-harness-20261002:
F1: make G2's footprint normaliser collapse per-session random names that the harness itself creates (the /tmp/dbus-<random> socket and any similar session-owned names you can enumerate from the soak raw logs), keyed on the harness's own session manifest, never by blanket-ignoring /tmp; a genuinely new file, socket or listener created by the candidate must still fail. Add unit tests for both (planted new socket still fails; session dbus socket passes).
F2: make G5 able to reject at the LORD++ levels it will actually face: use a test whose p-value resolution is finer than the smallest alpha_i the run can reach (for example an exact or large-sample paired sign-flip/permutation test sized to at least 10/alpha_min resamples, or a t-test on the paired ln-ratios with its normality checked on A/A data); keep LORD++ at FDR 0.05 and record why the chosen initial wealth W0 is reasonable for ~30 tests per night. Pre-register the change. Unit-test: a synthetic -8% effect with n=38 is rejected at alpha_i=2e-4; a null effect is not.
F3: replace G7's single-value trace-off comparison with a paired estimate: the trace-unset pairs' Delta must lie within the traced pairs' Delta CI widened by tau (or an equivalence test), computed on all trace-unset pairs; unit-test with loaded-host synthetic rows.
Layout bias: decide with evidence between (a) T_act as the decision metric (A/A passed) with whole-task T as a guardrail, and (b) a build design that randomises layout padding within each arm (each arm built twice with different padding, builds alternated across pairs) so the bias averages out; re-run a short A/A (2 sessions x 24 pairs) under the chosen design through quiet-timed and show the CI includes 0. Record the decision in the pre-registration.
Run all unit tests (python and itemcheck) under hostless; update the manifest; selfcheck passes. Commit. Write ${ART}/FIX.json. Return the schema.`, { label: 'fix', phase: 'Fix', schema: OUT, effort: 'high' })
if (!fix || !fix.ok || isBreach(fix.hard_rule_breach)) return { stop: 'fix not ready or breach', fix }

phase('Recal')
const cal = await agent(`Re-run the FULL Phase 1 known-answer calibration with the fixed evaluator (no proposer), exactly as pre-registered before, plus any new rows the fixes need (planted new socket must fail G2; trace-off agreement passes on a real deletion under load).
${RULES}
${PRIOR}
Fix result: ${JSON.stringify(fix)}
Candidates (branches ar/calib2/<name> from the champion, local only): +20 ms sleep (REVERT); +50 ms sleep (REVERT); real deletion of the 50 ms post-DoAction sleep (KEEP in >= 8 of 10 independent repeats, each a fresh screen+confirm+soak+spot); success reported before the effect lands (G2 fail); a frozen-item/test-item/phase_trace edit (G0 fail); a scanner-rule trigger (G0 fail); a candidate that adds a new socket/listener (G2 fail); 10 no-op diffs (<= 1 false KEEP); feedback ON vs OFF positive control (large effect in the R2-01/R2-04 direction). Write the pre-registration before any trial. Record each verdict, failed gate, cost per candidate and throughput, in a separate calibration ledger. Gate: every row matches. Write ${ART}/CALIBRATION2.json and the packet docs/experiments/ar-calibration2-2026-10-02/ (README, raw, verify_artifacts.py). Return pass (bool), summary, per_candidate_minutes, hard_rule_breach, near_miss.`, { label: 'recal', phase: 'Recal', schema: { type: 'object', properties: { pass: { type: 'boolean' }, summary: { type: 'string' }, per_candidate_minutes: { type: 'number' }, hard_rule_breach: { type: 'string' }, near_miss: { type: 'string' } }, required: ['pass', 'summary', 'per_candidate_minutes', 'hard_rule_breach', 'near_miss'] }, effort: 'high' })
if (!cal || isBreach(cal.hard_rule_breach)) return { stop: 'recal breach or failure', fix, cal }

let pilot = []
if (cal.pass) {
  phase('Pilot')
  const N = 10
  const history = []
  for (let k = 0; k < N; k += 2) {
    const batch = await parallel([0, 1].map(i => () => agent(`You are an autoresearch PROPOSER (candidate ${k + i + 1} of ${N}). You never grade your own work and never read the harness, fixtures, results history, holdout or evaluator code (harness/ar, ${ART}); you may read the kernel source and the public R2/N-01R packets (N-01R on branch exp/n-01r-native-wait-ab-20261002 already measured: 50 ms post-DoAction sleep DELETED scoped to GTK3 background delivery; focus-guard settle IRREDUCIBLE; cursor reveal OWNER_DECISION, frozen here).
${RULES}
Goal: lower whole-task verified time (per the pre-registered decision metric, feedback OFF) on the GTK3 checkbox task without changing what the kernel does. Editable items only (segment 1); nothing else, including existing tests in those files and any phase_trace line; new test files allowed.
Past attempts (status, Delta, CI, failed gate only): ${JSON.stringify(history)}
Steps: write 3 ideas, compare each with past attempts, pick one (never retry a discarded idea unchanged); record hypothesis, target traced phase, expected ms saved; make ONE change in a fresh worktree ${L}/ar2-cand-${k + i + 1} on branch ar/pilot2/cand-${k + i + 1} from the champion; cargo check under hostless; call ar-submit (command in ${ART}/HARNESS.json only). Return {branch, hypothesis, target_phase, expected_ms}.`, { label: `propose:${k + i + 1}`, phase: 'Pilot', schema: { type: 'object', properties: { branch: { type: 'string' }, hypothesis: { type: 'string' }, target_phase: { type: 'string' }, expected_ms: { type: 'number' } }, required: ['branch', 'hypothesis', 'target_phase', 'expected_ms'] } })))
    let halt = false
    for (const cand of batch.filter(Boolean)) {
      const ev = await agent(`Evaluator: run ar-eval on candidate ${cand.branch} (hypothesis: ${cand.hypothesis}; target ${cand.target_phase}; expected ${cand.expected_ms} ms) exactly as calibrated (G0 -> G1 -> screen -> confirm if it ranks -> soak -> spot checks), LORD++ accounting continuing from the pilot ledger.
${RULES}
Fix: ${fix.summary}
Calibration: ${cal.summary}
Return {branch, verdict (KEEP/REVERT/MARGINAL), failed_gate, delta, ci, summary, hard_rule_breach}. KEEP advances the local champion branch ar/pilot2/champion (never pushed).`, { label: `eval:${cand.branch}`, phase: 'Pilot', schema: { type: 'object', properties: { branch: { type: 'string' }, verdict: { type: 'string' }, failed_gate: { type: 'string' }, delta: { type: 'string' }, ci: { type: 'string' }, summary: { type: 'string' }, hard_rule_breach: { type: 'string' } }, required: ['branch', 'verdict', 'failed_gate', 'delta', 'ci', 'summary', 'hard_rule_breach'] }, effort: 'high' })
      if (ev) { pilot.push(ev); history.push({ status: ev.verdict, delta: ev.delta, ci: ev.ci, failed_gate: ev.failed_gate, hypothesis: cand.hypothesis }) }
      if (ev && isBreach(ev.hard_rule_breach)) { halt = true; break }
    }
    if (halt) break
  }
}

phase('Report')
const report = await agent(`Report autoresearch v2 and publish to the kvnloo/cua fork (you are the ONLY agent allowed to write to GitHub).
${RULES}
Fix: ${JSON.stringify(fix)}; calibration: ${JSON.stringify(cal)}; pilot evaluations: ${JSON.stringify(pilot)}
1. Update ${ART}/SYNTHESIS.md (v2 section): defects fixed and how, A/A under the chosen design, calibration table, pilot table (every candidate with verdict and failed gate), keeps with mechanism/soak/spot results, throughput, and next step.
2. Commit the v2 packet(s) on exp/ar-harness-20261002 (calibration2) and a pilot packet docs/experiments/ar-pilot2-2026-10-02/ on branch exp/ar-pilot2-20261002 (from the harness branch). Keep ar/* branches LOCAL for owner review.
3. Scan every commit since the upstream merge-base of each branch you push for absolute local paths, host name, secrets; push exp/ar-harness-20261002 (fast-forward of the already-pushed branch, never force) and exp/ar-pilot2-20261002 to origin with --no-follow-tags.
4. One comment on kvnloo/cua#93 with the v2 summary and packet links. Plain-text upstream refs.
If a write is refused, record it in ${ART}/PUBLISH.md and stop retrying. Return a concise summary.`, { label: 'report', phase: 'Report', effort: 'high' })

return { fix, cal, pilot, report }
