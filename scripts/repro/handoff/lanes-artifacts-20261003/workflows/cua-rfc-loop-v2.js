export const meta = {
  name: 'cua-rfc-loop-v2',
  description: 'Continuous CUA RFC loop v2 (resumes at wave 2 with hostless/quiet-timed guards): plan a wave of parallel isolated experiments, run + fresh-verify each, synthesize state, publish to the kvnloo/cua fork, judge the empirical end condition; repeat until two judges confirm E1-E6 or a stop rule fires',
  phases: [
    { title: 'Plan', detail: 'pick the next wave of independent lanes from STATE + issues + last judge' },
    { title: 'Run', detail: 'parallel isolated lanes (experiments, fixes, deliverables)' },
    { title: 'Verify', detail: 'fresh verifier per lane, one fix round' },
    { title: 'Synthesize', detail: 'update STATE.json, components, budget, drafts' },
    { title: 'Publish', detail: 'push accepted branches + fork comments (kvnloo/cua only)' },
    { title: 'Judge', detail: 'score END_CONDITION E1-E6 from packets; confirm twice' },
  ],
}
const isBreach = x => !!x && !/^\s*(none|no|n\/a|empty)\b/i.test(x)

const L = '/mnt/zer0models/github/cua-lanes'
const C = '/mnt/zer0models/github/cua'
const TMP = '/mnt/zer0models/cua-lane-tmp'
const ART = L + '/artifacts/r2'
const LOOP = ART + '/loop'
const MAX_WAVES = 12
const MAX_LANES = 8

const RULES = `
HARD RULES (breaking one is a failure: stop and report it as hard_stop instead of continuing):
- Host desktop is off limits. EVERY command that executes code (builds, tests, Python incl. gi/GTK imports, GUI libraries, browsers, cua-driver, MCP clients, model clients) runs under ${L}/bin/hostless, which masks the host X11/Wayland/D-Bus/AT-SPI sockets and strips desktop variables. GUI/Driver work additionally runs inside a private session: ${L}/cua-x11-session.sh (private Xvfb) or, once it exists, ${L}/cua-sway-session.sh (headless sway, built by a parallel track; read ${ART}/stack/SWAY_SETUP.json). AT-SPI in the X11 session needs CUA_SESSION_ATSPI=1 and CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1". The plain host shell is only for git, gh reads, file reads/edits and read-only inspection. Never set WAYLAND_DISPLAY/HYPRLAND_*/the host XDG_RUNTIME_DIR; never use the user's browser profiles; never use *-e2e Driver wrappers, CUA_E2E_BROWSER_NO_SANDBOX, permission-mode overrides or approval-bypass variables. Never kill a process you did not start.
- Breach classes. hard_rule_breach = something actually reached the host desktop/session, a secret was exposed, anything was written upstream, or a reported number was measured outside the quiet lane. near_miss = a rule-violating command that could not have had an effect (command not found, or it ran under hostless). Report both honestly; only hard_rule_breach stops the loop.
- Credentials: never print, read, copy or grep secret values or key files. A provider key may only be forwarded by NAME via CUA_SESSION_FORWARD_SECRETS. Live provider = TypeSafe only, inside the loop budget tracked in ${LOOP}/STATE.json (provider_budget: cap 600 requests that reach the provider across the whole loop). Every lane that uses it records its exact attempts/reached counts, and the planner assigns a per-lane cap that fits the remaining budget.
- Parallel tracks share this machine: a kvnloo/cua#107 experiment track (branches exp/i107-*, state ${ART}/i107/), a CUA x Hermes x z0intelligence stack track with headless sway (exp/stack-*, ${ART}/stack/) and an autoresearch track (ar/*, exp/ar-*, ${ART}/ar/). Do not edit their worktrees, branches or state; coordinate only through the locks. The TypeSafe budget in STATE.json belongs to this loop; reserve what R2-10 needs before other live lanes.
- GitHub: only the Publish agent may write, and only to the kvnloo/cua fork (git push to origin, gh comments on kvnloo/cua issues/PRs). Nothing to trycua/cua, ever. Every other agent is read-only on GitHub. In text posted to the fork, write upstream items as plain text ('trycua/cua PR 4316') so nothing autolinks upstream; fork items as kvnloo/cua#N.
- Git: main clone ${C} (origin = kvnloo/cua, upstream = trycua/cua). Lanes create worktrees under ${L}/<lane-dir> via git -C ${C} worktree add; run ${L}/lane-deps.sh in each new worktree before tests. Never stash; never modify other worktrees, existing branches or refs/heads/main; new branches only with the names the planner assigns. Commit as 'Kevin Rajan <7121943+kvnloo@users.noreply.github.com>' with a trailing 'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>' line. Never commit absolute local paths, the host name or secrets (privacy is checked on EVERY commit of a branch, not just the tip; fix by rewriting the unpublished branch before anything is pushed).
- Temp under ${TMP}, never /tmp. Rust builds (under hostless): flock ${TMP}/locks/cargo-build.lock ${L}/build-driver.sh <wt> <label> <target-dir> with a family target dir name cua-release-<family> (reuse within a family to save disk). Timing phases: ${L}/bin/quiet-timed <label> <cmd> (exclusive quiet-lane lock plus a receipt line in ${TMP}/locks/quiet-lane-ledger.jsonl; that ledger is the lock evidence verifiers check), AB/BA interleaving, loadavg per trial, keep every trial. Never compare across different sources, binaries, providers or environments.
- Product invariants (#73/#93): no new service (shadow state, second verifier, router/decision service, lifecycle registry, batch API, event service, routine engine/route miner). Instrumentation and experimental behaviour stay measurement-only, env-gated and default-off; default Driver behaviour is unchanged unless a lane is explicitly a reviewed product fix. Events are wake hints, never the success oracle. Passive state never mints authority. A possibly landed effect stays unknown until reconciled; never blind-replay it. Logical routine identity may persist; refs, tokens, captures, capabilities and session epochs never become durable authority.
- Evidence: classes SOURCE, UNIT, FIXTURE, REAL, BENCHMARK, LIVE_PROVIDER, BLOCKED, NOT_RUN on every row. Every packet states: forced path, actual route/producer, independent target-owned oracle, negative/fallback controls, tested source SHA, Driver sha256 + version, environment, live PR heads vs tested source vs publication SHA, claim boundary. Work deleted separate from wall-clock saved; every failure in the denominator; PREREG.json committed before the first measured trial. Packet layout as kvnloo/cua PR #106 (docs/experiments/<name>/ with README, raw/, summaries, provenance, verify_artifacts.py). Mirror raw outputs to ${ART}/<lane-id>/. No absolute paths / host name / secrets in packets.
`

const PLAN_SCHEMA = {
  type: 'object',
  properties: {
    wave_goal: { type: 'string' },
    lanes: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string', description: 'e.g. R2-10, R2-07, N-04a, OWN-20, DOC-3963' },
          kind: { type: 'string', enum: ['experiment', 'fix', 'deliverable'] },
          title: { type: 'string' },
          owner_issues: { type: 'string' },
          end_criteria: { type: 'string', description: 'which of E1-E5 this advances and how' },
          spec: { type: 'string', description: 'complete, self-contained spec at #93 standard: hypothesis, arms, forced paths, n, oracle, controls, gates, boundary, base source/binary' },
          base: { type: 'string', description: 'exact base SHA or existing branch to start from' },
          branch: { type: 'string', description: 'new branch name, exp/... or docs/... with -20261001 or later date suffix' },
          lane_dir: { type: 'string', description: 'worktree dir name under cua-lanes' },
          quiet: { type: 'boolean' },
          provider_cap: { type: 'number', description: '0 unless the lane needs TypeSafe' },
        },
        required: ['id', 'kind', 'title', 'owner_issues', 'end_criteria', 'spec', 'base', 'branch', 'lane_dir', 'quiet', 'provider_cap'],
      },
    },
    blocked_recorded: { type: 'array', items: { type: 'string' }, description: 'items marked BLOCKED this wave without running, with exact blocker' },
    notes: { type: 'string' },
  },
  required: ['wave_goal', 'lanes', 'blocked_recorded', 'notes'],
}

const RUN_SCHEMA = {
  type: 'object',
  properties: {
    id: { type: 'string' },
    status: { type: 'string', enum: ['COMPLETE', 'PARTIAL', 'BLOCKED'] },
    branch: { type: 'string' },
    commit: { type: 'string' },
    packet_dir: { type: 'string' },
    headline: { type: 'string' },
    disposition: { type: 'string' },
    provider_attempts: { type: 'number' },
    provider_reached: { type: 'number' },
    components: { type: 'string', description: 'any whole-task component timings measured (name: median ms, share)' },
    blockers: { type: 'array', items: { type: 'string' } },
    hard_rule_breach: { type: 'string', description: 'empty if none' },
    near_miss: { type: 'string', description: 'empty if none' },
    notes: { type: 'string' },
  },
  required: ['id', 'status', 'branch', 'packet_dir', 'headline', 'disposition', 'provider_attempts', 'provider_reached', 'blockers', 'hard_rule_breach', 'notes'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    id: { type: 'string' },
    accept: { type: 'boolean' },
    problems: { type: 'array', items: { type: 'string' }, description: 'prefix BLOCKING: or Advisory:' },
    hard_rule_breach: { type: 'string', description: 'empty if none' },
  },
  required: ['id', 'accept', 'problems', 'hard_rule_breach'],
}

const JUDGE_SCHEMA = {
  type: 'object',
  properties: {
    end_condition_met: { type: 'boolean' },
    E1: { type: 'string' }, E2: { type: 'string' }, E3: { type: 'string' }, E4: { type: 'string' }, E5: { type: 'string' }, E6: { type: 'string' },
    untested_deletable_share: { type: 'string', description: 'per reference task, % of T' },
    composed_speedup: { type: 'string' },
    floor_ratio: { type: 'string' },
    new_terminal_dispositions: { type: 'number' },
    progress_made: { type: 'boolean' },
    remaining: { type: 'array', items: { type: 'string' }, description: 'ranked gaps for the next planner' },
    hard_stop: { type: 'boolean' },
    hard_stop_reason: { type: 'string' },
  },
  required: ['end_condition_met', 'E1', 'E2', 'E3', 'E4', 'E5', 'E6', 'untested_deletable_share', 'composed_speedup', 'floor_ratio', 'new_terminal_dispositions', 'progress_made', 'remaining', 'hard_stop', 'hard_stop_reason'],
}

const judgePrompt = (wave, role) => `You are ${role} for the CUA RFC loop after wave ${wave}. Decide, from evidence, whether the empirical end condition in ${LOOP}/END_CONDITION.md is met. Read it first, then ${LOOP}/STATE.json, but DO NOT trust STATE: verify every claim you rely on against the packets on their branches (git -C ${C} show <branch>:docs/experiments/...), their verify_artifacts.py (run it), and the fork issues (gh read-only: kvnloo/cua #73 #93 #10 #74 and owner issues).
${RULES}
Score E1-E6 one by one, each with the decisive evidence or the exact gap. Compute E2's untested-but-plausibly-deletable share of T per reference task from measured component decompositions (if no decomposition exists for a task, E2 is not met for it). Report the composed speedup S and the floor ratio only if measured on one source; otherwise say 'not measured'. new_terminal_dispositions = experiments whose disposition became terminal in this wave. progress_made = new terminal dispositions > 0 OR the untested share dropped OR a deliverable was accepted. 'remaining' is a ranked list of the next most valuable gaps (critical-path items first, then coverage, then deliverables), each concrete enough for a planner. hard_stop only for a hard-rule breach or something that makes continuing unsafe. Be strict: end_condition_met = true only if every criterion holds.`

let wave = (args && args.startWave) ? args.startWave - 1 : 0
let stalled = 0
let lastJudge = (args && args.seedJudge) ? args.seedJudge : null
const history = []
let stopReason = 'max waves reached'

while (wave < MAX_WAVES) {
  wave++
  phase('Plan')
  const plan = await agent(`You are the planner for wave ${wave} of the continuous CUA RFC loop. Goal: finish the downstream RFC per ${LOOP}/END_CONDITION.md, maximizing parallel progress.
${RULES}
Read: ${LOOP}/END_CONDITION.md; ${LOOP}/STATE.json; the latest ${ART}/SYNTHESIS*.md; gh issue view 73, 93, 10, 74 -R kvnloo/cua with comments (the owner may have added directives since: obey the newest); the owner issues you consider (#9 #16 #20 #36 #75 #78 #105 #94 and any new ones); the prior packets' README 'next' sections.
Last judge report: ${lastJudge ? JSON.stringify(lastJudge) : 'none yet (first loop wave). Known ranked follow-ups are in STATE.followups_ranked.'}
Pick at most ${MAX_LANES} lanes for this wave that are independent of each other (no shared mutable desktop/session/branch; timing lanes serialize on the quiet lock anyway, so mix timing and correctness/doc lanes). Priority: (1) items that move E2/E3 (critical-path decomposition per reference task, causal A/Bs of the biggest remaining components such as the cursor glide/reveal and native waits, R2-10 composition on one source, R2-07 compiled routine with its six gates), (2) E1 coverage (R2-08, R2-09 if justified, Linux owner rows #9 #16 #20 #36 #75 #78, #105 runner reconcile, the two suspected Driver bugs from wave 0), (3) E5 deliverables only once the evidence they summarise is stable (the #3963 rewrite draft, the #74 queue, the #10 final table); deliverable lanes write docs on a docs/... branch, verified like experiments. Do not repeat accepted experiments unless recertifying a changed source. Mark hardware/owner-decision items BLOCKED in blocked_recorded with the exact blocker instead of planning them. Live provider lanes must fit the remaining TypeSafe budget (cap - used in STATE). Use the current upstream main (git -C ${C} fetch upstream main read-only is fine) or the exact source a lane must measure; say which. Each spec must be complete and self-contained at the #93 standard (hypothesis, arms, forced paths, n >= 20 or as the issue requires, AB/BA, oracle, negative/fallback controls, pre-registered gates, claim boundary). Assign unique branch names and lane dirs (prefix lane dirs with w${wave}-). If nothing runnable remains, return zero lanes and explain in notes.`, { label: `plan:w${wave}`, phase: 'Plan', schema: PLAN_SCHEMA, effort: 'high' })

  if (!plan) { stopReason = 'planner failed'; break }
  const lanesIn = (plan.lanes || []).slice(0, MAX_LANES)
  log(`wave ${wave}: ${lanesIn.length} lanes — ${plan.wave_goal}`)

  const lanes = lanesIn.length === 0 ? [] : await pipeline(
    lanesIn,
    (lane) => agent(`You own lane ${lane.id} (${lane.kind}) in wave ${wave} of the CUA RFC loop: ${lane.title}. Owners: ${lane.owner_issues}. Advances: ${lane.end_criteria}.
${RULES}
Context: ${LOOP}/END_CONDITION.md, ${LOOP}/STATE.json (binaries, pins, budget), ${ART}/SETUP.json (working smoke commands), prior packets on the exp/r2-* branches. Provider cap for this lane: ${lane.provider_cap} requests reaching TypeSafe (0 = do not use the provider).
Spec (follow exactly):
${lane.spec}
Procedure: worktree ${L}/${lane.lane_dir} from ${lane.base}, branch ${lane.branch}; run lane-deps.sh. For experiments: commit docs/experiments/<packet>/PREREG.json before any measured trial; measurement-only env-gated instrumentation only; lane binary via the cargo lock if Driver code changes; run touched unit suites; run inside the isolated session${lane.quiet ? ', timing phases under the quiet-lane lock' : ''}; raw JSONL per trial; README (provenance with all SHAs separate, method, results N of M with evidence class per row, component timings, work deleted vs wall-clock saved, controls, deviations, limits, claim boundary, disposition); summary JSON; verify_artifacts.py; privacy scan of every commit. For deliverables: write the document(s) on the branch citing only accepted packets by branch + commit, every claim traceable, and a verify script that checks each cited SHA/number exists in its packet. For fixes: smallest change with a red-before/green-after test. Commit on the branch; leave the worktree for the verifier. Report exact provider attempts/reached. Return the schema.`, { label: `run:w${wave}:${lane.id}`, phase: 'Run', schema: RUN_SCHEMA, effort: 'high' }),
    async (run, lane) => {
      if (!run) return { id: lane.id, lane, run: null, verdict: null }
      const vprompt = (round) => `You are a FRESH, skeptical verifier (round ${round}) for lane ${lane.id} (${lane.kind}) in wave ${wave} of the CUA RFC loop. Re-derive; do not trust the README.
${RULES}
Lane result: ${JSON.stringify(run)}
Spec it had to follow: ${lane.spec}
Check in ${L}/${lane.lane_dir} on ${run.branch}: PREREG committed before the first measured trial (experiments) and followed, deviations disclosed; verify_artifacts.py passes and you independently recompute headline numbers from raw/; all failures in denominators; interleaving and quiet lock where required; forced path, route attribution, independent oracle and negative/fallback controls real (spot-check raw); claim boundary and evidence classes not overstated (FIXTURE vs REAL, simulated vs live, work deleted vs wall-clock, Linux not generalized); instrumentation env-gated/default-off, no new service, default behaviour unchanged (inspect the diff); provenance SHAs separate; provider counts within the lane cap; privacy on EVERY commit of the branch (git log -p base..branch); for deliverables every cited SHA/number exists in an accepted packet. You may re-run a small subset inside the isolated session${lane.quiet ? ' under the quiet lock' : ''}. Report any hard-rule breach you find. Accept only if no BLOCKING problem remains (a BLOCKED lane can be accepted if the blocker is real and exact).`
      let v = await agent(vprompt(1), { label: `verify:w${wave}:${lane.id}`, phase: 'Verify', schema: VERDICT_SCHEMA })
      let fix = null
      if (v && !v.accept && !isBreach(v.hard_rule_breach)) {
        fix = await agent(`Fix the BLOCKING problems a fresh verifier found in lane ${lane.id} (wave ${wave}); advisories too if cheap and clearly right.
${RULES}
Spec: ${lane.spec}
Your earlier result: ${JSON.stringify(run)}
Verifier problems: ${JSON.stringify(v.problems)}
Work in ${L}/${lane.lane_dir} on ${run.branch}. Never edit PREREG.json; extra trials are a disclosed extension. Re-run verify_artifacts.py and the privacy scan of every commit; commit. Return a short summary with the updated headline and commit.`, { label: `fix:w${wave}:${lane.id}`, phase: 'Verify', effort: 'high' })
        v = await agent(vprompt(2), { label: `reverify:w${wave}:${lane.id}`, phase: 'Verify', schema: VERDICT_SCHEMA })
      }
      return { id: lane.id, lane: { id: lane.id, kind: lane.kind, title: lane.title, branch: lane.branch, owner_issues: lane.owner_issues }, run, fix, verdict: v }
    },
  )
  const done = lanes.filter(Boolean)
  const accepted = done.filter(l => l.verdict && l.verdict.accept)
  const breaches = done.map(l => [l.run && l.run.hard_rule_breach, l.verdict && l.verdict.hard_rule_breach].find(isBreach)).filter(isBreach)
  log(`wave ${wave}: accepted ${accepted.length}/${done.length}${breaches.length ? ' — BREACH reported' : ''}`)

  phase('Synthesize')
  const synth = await agent(`You are the synthesizer for wave ${wave} of the CUA RFC loop (#10 accounting owner).
${RULES}
Lane results with verdicts: ${JSON.stringify(done.map(l => ({ id: l.id, lane: l.lane, run: l.run, fix: l.fix, verdict: l.verdict })))}
Planner blocked items: ${JSON.stringify(plan.blocked_recorded)}
1. Update ${LOOP}/STATE.json (keep it valid JSON, schema unchanged plus new keys as needed): dispositions for accepted lanes (branch, final commit = current branch head, class, one_line), BLOCKED items with exact blockers, owner rows, provider_budget ledger (add each lane's reached/attempts; recompute used), components per reference task (measured medians and shares, which source/binary), followups_ranked, and append a waves entry {wave, accepted ids, rejected ids, published:false}. Rejected lanes stay PENDING with the verifier's blocking problems noted.
2. Write ${ART}/SYNTHESIS-w${wave}.md: what changed this wave, the current per-reference-task component decomposition and the untested share as best known, dispositions table, what remains for E1-E6.
3. Write fork comment drafts to ${ART}/drafts/w${wave}/: one progress comment for kvnloo/cua#93 (table of this wave's accepted results with links https://github.com/kvnloo/cua/blob/<branch>/<packet>/README.md and commits, rejected lanes listed honestly, budget used, what is next) and one per owner issue that got new accepted evidence. Plain-text upstream references only.
Return a short summary.`, { label: `synth:w${wave}`, phase: 'Synthesize', effort: 'high' })

  phase('Publish')
  const pub = await agent(`You are the publisher for wave ${wave} of the CUA RFC loop. You are the ONLY agent allowed to write to GitHub, and only to the kvnloo/cua fork.
${RULES}
Accepted lanes: ${JSON.stringify(accepted.map(l => ({ id: l.id, branch: (l.run && l.run.branch) || l.lane.branch })))}
Steps:
1. For each accepted branch in ${C}: confirm the branch head is what the verifier accepted (its commit is in the verified worktree), check git ls-remote origin for name collisions (a collision with different content: append -v2, never force-push), and scan EVERY commit from its merge-base with upstream/main to the head for absolute local paths (~, /mnt/zer0models, /tmp/claude-1000), the host name and secret patterns. If any commit leaks, do NOT push that branch; record it.
2. Push clean branches: git -C ${C} push --no-follow-tags origin refs/heads/<b>:refs/heads/<b>.
3. Post the drafts in ${ART}/drafts/w${wave}/ with gh issue comment / gh pr comment -R kvnloo/cua, after replacing any placeholder with real values and checking: no autolinks to trycua (no 'trycua/cua#N', no github.com/trycua/cua/pull|issues URLs), no absolute paths or host name. Skip a draft that references an unpushed branch, or fix its links.
4. Set published:true (with pushed branch heads and comment URLs) on this wave's entry in ${LOOP}/STATE.json.
If pushing or commenting is refused by the environment (permission denial), do not retry around it: record 'publish_blocked' with the exact error in STATE.json and continue. Return what was pushed and posted.`, { label: `publish:w${wave}`, phase: 'Publish' })

  phase('Judge')
  const judge = await agent(judgePrompt(wave, 'the independent end-condition judge'), { label: `judge:w${wave}`, phase: 'Judge', schema: JUDGE_SCHEMA, effort: 'high' })
  history.push({ wave, goal: plan.wave_goal, lanes: lanesIn.map(l => l.id), accepted: accepted.map(l => l.id), breaches, synth: (synth || '').slice(0, 1500), publish: (pub || '').slice(0, 800), judge })

  if (breaches.length || (judge && judge.hard_stop)) { stopReason = 'hard stop: ' + (breaches.join('; ') || judge.hard_stop_reason); lastJudge = judge; break }
  if (judge && judge.end_condition_met) {
    const confirm = await agent(judgePrompt(wave, 'a SECOND, fully independent end-condition judge (the first judge said met; try hard to find any unmet criterion)'), { label: `confirm:w${wave}`, phase: 'Judge', schema: JUDGE_SCHEMA, effort: 'high' })
    history[history.length - 1].confirm = confirm
    if (confirm && confirm.end_condition_met) { stopReason = 'END CONDITION MET (confirmed by two judges)'; lastJudge = confirm; break }
    lastJudge = confirm || judge
  } else {
    lastJudge = judge
  }
  if (!judge || !judge.progress_made) stalled++
  else stalled = 0
  if (stalled >= 2) { stopReason = 'stalled: two consecutive waves without progress'; break }
}

log(`loop finished after ${wave} wave(s): ${stopReason}`)
return { waves: wave, stopReason, lastJudge, history }
