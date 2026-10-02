import { appendFile, writeFile } from 'node:fs/promises';
import process from 'node:process';
import { randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import {
  hasExecutableCandidate,
  parseVisualRegions,
  validateChoice,
  VisualObservationError,
  type BrowserSnapshot,
  type Candidate,
  type HistoryEntry,
  type VisualDelivery,
  type Outcome,
  type VisualObservation,
} from './core.js';
import { driverEnvironment } from './driver_env.js';
import {
  planGuardedCompletion,
  resolveGuardedCompletion,
  type GuardedCompletionPlan,
  type GuardedCompletionTelemetry,
} from './guarded_completion.js';
import { chooseLiveForTask, chooseMockForTask } from './jev_adapter.js';
import { FixtureFormTask, fixtureSources, type Task, type TaskSources } from './tasks.js';

type VisualMode = 'auto' | 'always' | 'off';

// Bounded fresh reads after a possibly landed mutation (R2-06 bounded re-read).
const RECONCILE_INTERVAL_MS = 100;
const RECONCILE_DEADLINE_MS = 3000;
const PRE_WRITE_FAILED = 'pre_write_failed';

/** The receipt of a dispatched mutation whose effect is not verified yet. */
type Pending = { receipt?: Record<string, unknown> };

type Arguments = {
  provider: 'mock' | 'live';
  visualObservation: VisualMode;
  fixtureUrl: string;
  token?: string;
  maxSteps: number;
  dryRun: boolean;
  guardedCompletion: boolean;
  log?: string;
};

function parseArgs(argv: string[]): Arguments {
  const result: Arguments = {
    provider: 'mock',
    visualObservation: 'auto',
    fixtureUrl: 'http://127.0.0.1:8765/',
    maxSteps: 4,
    dryRun: false,
    guardedCompletion: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === '--provider') result.provider = argv[++index] as Arguments['provider'];
    else if (value === '--fixture-url') result.fixtureUrl = argv[++index];
    else if (value === '--token') result.token = argv[++index];
    else if (value === '--max-steps') result.maxSteps = Number(argv[++index]);
    else if (value === '--dry-run') result.dryRun = true;
    else if (value === '--guarded-completion') result.guardedCompletion = true;
    else if (value === '--log') result.log = argv[++index];
    else if (value === '--visual-observation') {
      const mode = argv[++index];
      if (mode !== 'auto' && mode !== 'always' && mode !== 'off') {
        throw new Error('--visual-observation must be auto, always, or off');
      }
      result.visualObservation = mode;
    } else throw new Error(`unknown argument: ${value}`);
  }
  if (!Number.isInteger(result.maxSteps) || result.maxSteps < 1) {
    throw new Error('--max-steps must be a positive integer');
  }
  result.fixtureUrl = validateFixtureUrl(result.fixtureUrl);
  return result;
}

export function validateFixtureUrl(value: string): string {
  const parsed = new URL(value);
  const loopback = new Set(['127.0.0.1', 'localhost', '[::1]']);
  if (
    parsed.protocol !== 'http:' ||
    !loopback.has(parsed.hostname) ||
    parsed.username ||
    parsed.password ||
    (parsed.pathname !== '' && parsed.pathname !== '/') ||
    parsed.search ||
    parsed.hash
  ) {
    throw new Error('fixture URL must be an HTTP loopback origin such as http://127.0.0.1:8765/');
  }
  parsed.pathname = '/';
  return parsed.toString();
}

export function selectTabId(tabs: Record<string, any>[]): string {
  if (!tabs.length) throw new Error('isolated browser has no tabs');
  return String(tabs.find((tab) => tab.active)?.tab_id ?? tabs[0].tab_id);
}

export class DriverToolError extends Error {
  constructor(
    message: string,
    readonly code?: string,
    readonly recommendedDelivery?: string
  ) {
    super(message);
    this.name = 'DriverToolError';
  }
}

export class Driver {
  constructor(
    private readonly client: Client,
    private readonly session: string
  ) {}

  get sessionLabel(): string {
    return this.session;
  }

  async call(name: string, args: Record<string, unknown>): Promise<Record<string, any>> {
    const result = await this.client.callTool({
      name,
      arguments: { ...args, session: this.session },
    });
    if (result.isError) {
      const structured = result.structuredContent as Record<string, unknown> | undefined;
      const refusalCode = (structured?.refusal as Record<string, unknown> | undefined)?.code;
      const code =
        typeof structured?.code === 'string' && structured.code
          ? structured.code
          : typeof refusalCode === 'string' && refusalCode
            ? refusalCode
            : undefined;
      const escalation = structured?.escalation as Record<string, unknown> | undefined;
      const recommended =
        typeof escalation?.recommended === 'string' && escalation.recommended
          ? escalation.recommended
          : undefined;
      throw new DriverToolError(
        `${name} failed: ${JSON.stringify(result.content)}`,
        code,
        recommended
      );
    }
    const data = result.structuredContent as Record<string, any> | undefined;
    if (!data) throw new Error(`${name} returned no structured result`);
    if (data.status === 'refused' || data.refusal) {
      const code = data.refusal?.code;
      // DriverToolError is an Error, so existing handlers still match.
      throw new DriverToolError(
        `${name} refused: ${JSON.stringify(data.refusal ?? data)}`,
        typeof code === 'string' && code ? code : undefined
      );
    }
    return data;
  }
}

/**
 * Caller-side record of whether the last tools/call request was written. Only
 * a send that rejected proves the request never left the caller: in SDK 1.30.0
 * StdioClientTransport.send rejects only before it writes to stdin. A call that
 * never reached this send proves nothing.
 */
export function recordToolCallWrites(transport: {
  send(message: any, options?: any): Promise<void>;
}): { toolCall?: 'sending' | 'written' | 'not_written' } {
  const ledger: { toolCall?: 'sending' | 'written' | 'not_written' } = {};
  const send = transport.send.bind(transport);
  transport.send = async (message, options) => {
    if (message?.method !== 'tools/call') return send(message, options);
    ledger.toolCall = 'sending';
    try {
      await send(message, options);
    } catch (error: unknown) {
      ledger.toolCall = 'not_written';
      throw error;
    }
    ledger.toolCall = 'written';
  };
  return ledger;
}

export function supportsCaptureBoundClick(
  tools: readonly { name: string; inputSchema?: Record<string, any> }[]
): boolean {
  const click = tools.find((tool) => tool.name === 'click');
  return Boolean(click?.inputSchema?.properties?.capture_id);
}

/**
 * Return Driver's code when it refused a background visual click. Only a
 * structured refusal counts: a background_* error code or an explicit
 * escalation.recommended === 'foreground'. Anything else stays a failure.
 */
export function backgroundRefusalCode(candidate: Candidate, error: unknown): string | undefined {
  if (candidate.tool !== 'click' || candidate.arguments.delivery_mode !== 'background') {
    return undefined;
  }
  if (!(error instanceof DriverToolError)) return undefined;
  if (error.code?.startsWith('background_')) return error.code;
  if (error.recommendedDelivery === 'foreground') return error.code ?? 'foreground_recommended';
  return undefined;
}

export type VisualStatus = {
  status: 'ok' | 'not_installed' | 'error' | 'unavailable' | 'skipped';
  reason?: string;
  error_code?: string;
  capture_id?: string;
  region_count?: number;
};

export type CandidatePhaseTiming = {
  visualObserveMs: number;
  candidateBuildMs: number;
};

/**
 * Build the redacted per-step visual record written to the JSONL log. It never
 * contains screenshots, screenshot references, region text, or secrets.
 */
export function visualStatus(
  status: VisualStatus['status'],
  errorCode?: string,
  visual?: VisualObservation,
  reason?: string
): VisualStatus {
  const result: VisualStatus = { status };
  if (reason) result.reason = reason;
  if (errorCode) result.error_code = errorCode;
  if (visual) {
    result.capture_id = visual.captureId;
    result.region_count = visual.regions.length;
  }
  return result;
}

/**
 * Take an optional visual observation and report what happened. Failures never
 * stop the run: the caller continues on the page-structure path, but the
 * returned status makes the fallback observable.
 */
export async function observeVisual(
  driver: Driver,
  pid: number,
  windowId: number,
  availableTools: ReadonlySet<string>,
  captureBoundClick: boolean
): Promise<{ visual?: VisualObservation; status: VisualStatus }> {
  if (!captureBoundClick) {
    return { status: visualStatus('unavailable', 'capture_bound_click_unsupported') };
  }
  if (!availableTools.has('get_window_state') || !availableTools.has('parse_visual_regions')) {
    return { status: visualStatus('unavailable', 'tool_not_advertised') };
  }
  try {
    const capture = await driver.call('get_window_state', {
      pid,
      window_id: windowId,
      include_accessibility_tree: false,
    });
    if (typeof capture.capture_id !== 'string') {
      return { status: visualStatus('error', 'capture_missing') };
    }
    const result = await driver.call('parse_visual_regions', {
      capture_id: capture.capture_id,
      options: { kinds: ['text', 'icon'], min_confidence: 0.8, max_regions: 100 },
    });
    const visual = parseVisualRegions(result, capture.capture_id, pid, windowId);
    return { visual, status: visualStatus('ok', undefined, visual) };
  } catch (error: unknown) {
    if (error instanceof DriverToolError) {
      if (error.code === 'not_installed') {
        return { status: visualStatus('not_installed', 'not_installed') };
      }
      return { status: visualStatus('error', error.code ?? 'driver_error') };
    }
    if (error instanceof VisualObservationError) {
      return { status: visualStatus('error', error.code) };
    }
    // parseVisualRegions reports other contract violations as plain errors.
    if (
      error instanceof Error &&
      /^(visual (result|region)|unsupported visual)/.test(error.message)
    ) {
      return { status: visualStatus('error', 'invalid_visual_result') };
    }
    return { status: visualStatus('error', 'driver_error') };
  }
}

export async function optionalVisualObservation(
  driver: Driver,
  pid: number,
  windowId: number,
  availableTools: ReadonlySet<string>,
  captureBoundClick: boolean
): Promise<VisualObservation | undefined> {
  return (await observeVisual(driver, pid, windowId, availableTools, captureBoundClick)).visual;
}

/**
 * Build one step's sources and candidates, parsing visual regions only when
 * useful. In auto mode the capture and parse run only when the page structure
 * offers no executable candidate, because only then can a visual region add
 * one. always restores the per-step parse; off never parses.
 */
export async function taskCandidatesForStep(
  driver: Driver,
  task: Task,
  snapshot: BrowserSnapshot,
  pid: number,
  windowId: number,
  availableTools: ReadonlySet<string>,
  captureBoundClick: boolean,
  visualMode: VisualMode = 'auto',
  visualDelivery: VisualDelivery = 'background'
): Promise<{
  candidates: Candidate[];
  sources: TaskSources;
  status: VisualStatus;
  timing: CandidatePhaseTiming;
}> {
  // Whether a control missing from the page structure can still be found
  // through a capture-bound visual region; reported in the task state.
  const visualPath = captureBoundClick && visualMode !== 'off';
  let candidateBuildStarted = performance.now();
  let sources = fixtureSources(snapshot, undefined, captureBoundClick, visualDelivery, visualPath);
  let candidates = task.candidates(sources);
  let candidateBuildMs = performance.now() - candidateBuildStarted;
  let visualObserveMs = 0;
  if (visualMode === 'off') {
    return {
      candidates,
      sources,
      status: visualStatus('skipped', undefined, undefined, 'disabled'),
      timing: { visualObserveMs, candidateBuildMs },
    };
  }
  if (visualMode === 'auto' && hasExecutableCandidate(candidates)) {
    return {
      candidates,
      sources,
      status: visualStatus('skipped', undefined, undefined, 'page_structure_candidate'),
      timing: { visualObserveMs, candidateBuildMs },
    };
  }
  const visualStarted = performance.now();
  const { visual, status } = await observeVisual(
    driver,
    pid,
    windowId,
    availableTools,
    captureBoundClick
  );
  visualObserveMs = performance.now() - visualStarted;
  if (visual) {
    candidateBuildStarted = performance.now();
    sources = fixtureSources(snapshot, visual, captureBoundClick, visualDelivery, visualPath);
    candidates = task.candidates(sources);
    candidateBuildMs += performance.now() - candidateBuildStarted;
  }
  return { candidates, sources, status, timing: { visualObserveMs, candidateBuildMs } };
}

/** Build one step's fixture-task candidates; see taskCandidatesForStep. */
export async function candidatesForStep(
  driver: Driver,
  snapshot: BrowserSnapshot,
  token: string,
  pid: number,
  windowId: number,
  availableTools: ReadonlySet<string>,
  captureBoundClick: boolean,
  visualMode: VisualMode = 'auto',
  visualDelivery: VisualDelivery = 'background'
): Promise<{ candidates: Candidate[]; visual?: VisualObservation; status: VisualStatus }> {
  const { candidates, sources, status } = await taskCandidatesForStep(
    driver,
    new FixtureFormTask(token),
    snapshot,
    pid,
    windowId,
    availableTools,
    captureBoundClick,
    visualMode,
    visualDelivery
  );
  return { candidates, visual: sources.visual?.observation, status };
}

async function waitForWindow(driver: Driver, pid: number) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const response = await driver.call('list_windows', { pid });
    const visible = (response.windows as Record<string, any>[]).filter(
      (window) => window.is_on_screen
    );
    if (visible.length) {
      return visible.sort(
        (left, right) =>
          right.bounds.width * right.bounds.height - left.bounds.width * left.bounds.height
      )[0];
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error('isolated browser window did not become ready');
}

async function writeEvent(path: string | undefined, event: Record<string, unknown>) {
  const line = JSON.stringify(event);
  console.log(line);
  if (path) await appendFile(path, `${line}\n`, 'utf8');
}

export function ambiguousMutationReceipt(args: {
  session: string;
  step: number;
  candidateId: string;
}): Record<string, unknown> {
  // A tool error after dispatch does not prove the target stayed unchanged.
  // The acknowledgement may have been lost after the mutation landed.
  return {
    receiptKind: 'mutation-outcome/v0',
    mutationKey: `${args.step}:${args.candidateId}`,
    authorityScope: args.session,
    attempted: true,
    effect: 'unknown',
    verification: 'unverified',
    retryDisposition: 'observe',
  };
}

/** Record what fresh oracle reads established about a dispatched mutation. */
export function resolvedReceipt(
  receipt: Record<string, unknown>,
  outcome: Outcome
): Record<string, unknown> {
  if (outcome === 'verified') {
    return {
      ...receipt,
      effect: 'applied',
      verification: 'verified',
      retryDisposition: 'none',
      resolution: outcome,
    };
  }
  if (outcome === 'refuted') {
    return { ...receipt, verification: 'refuted', retryDisposition: 'none', resolution: outcome };
  }
  return { ...receipt, resolution: 'unresolved_unknown' };
}

/**
 * Read the target oracle until it decides or the deadline passes. It never
 * dispatches: one negative read is not authority to act again.
 */
async function reconcile(task: Task): Promise<Outcome> {
  const deadline = performance.now() + RECONCILE_DEADLINE_MS;
  for (;;) {
    let outcome: Outcome = 'unknown';
    try {
      outcome = task.classify(await task.readOracle(), 0);
    } catch {
      // A failed read is no evidence either way.
    }
    if (outcome === 'verified' || outcome === 'refuted') return outcome;
    if (performance.now() >= deadline) return 'unknown';
    await new Promise((resolve) => setTimeout(resolve, RECONCILE_INTERVAL_MS));
  }
}

/**
 * Write the terminal outcome event. A dispatched mutation whose effect is not
 * verified yet ends with bounded reconciliation, and the event carries its
 * content-free receipt.
 */
async function finish(
  task: Task,
  log: string | undefined,
  pending: Pending,
  outcome: Outcome,
  fields: Record<string, unknown> = {}
): Promise<Outcome> {
  const receipt = pending.receipt;
  delete pending.receipt;
  if (receipt) {
    if (outcome !== 'verified' && outcome !== 'refuted') outcome = await reconcile(task);
    fields = { ...fields, mutation_outcome: resolvedReceipt(receipt, outcome) };
  }
  await writeEvent(log, { event: 'outcome', outcome, ...fields });
  return outcome;
}

export function decisionTimingFields(args: {
  decisionMs: number;
  semanticObserveMs: number;
  visualObserveMs: number;
  candidateBuildMs: number;
  providerDecisionMs: number;
}): Record<string, number> {
  return {
    decision_ms: args.decisionMs,
    semantic_observe_ms: Math.round(args.semanticObserveMs * 100) / 100,
    visual_observe_ms: Math.round(args.visualObserveMs * 100) / 100,
    candidate_build_ms: Math.round(args.candidateBuildMs * 100) / 100,
    provider_decision_ms: Math.round(args.providerDecisionMs * 100) / 100,
  };
}

async function run(args: Arguments): Promise<Outcome> {
  const token = args.token ?? `jev-${randomUUID().replaceAll('-', '').slice(0, 10)}`;
  const task: Task = new FixtureFormTask(token, args.fixtureUrl, args.maxSteps);
  if (args.log) await writeFile(args.log, '', 'utf8');
  await task.reset();
  // Lives only for this run and is never authority to act again.
  const pending: Pending = {};

  const attempt = async (mayReconsider: boolean) => {
    let outcome: Outcome | typeof PRE_WRITE_FAILED;
    try {
      outcome = await runAttempt(args, task, pending, mayReconsider);
    } catch (error: unknown) {
      if (!pending.receipt) throw error;
      // A read failed after an unverified completion: end with a receipt.
      return finish(task, args.log, pending, 'unknown', {
        phase: 'observe',
        error: error instanceof Error ? error.name : 'UnknownError',
      });
    }
    if (pending.receipt) return finish(task, args.log, pending, 'unknown', { phase: 'observe' });
    return outcome;
  };

  const outcome = await attempt(true);
  // The mutation request was never written: reconsider once from fresh state.
  return outcome === PRE_WRITE_FAILED ? ((await attempt(false)) as Outcome) : outcome;
}

async function runAttempt(
  args: Arguments,
  task: Task,
  pending: Pending,
  mayReconsider: boolean
): Promise<Outcome | typeof PRE_WRITE_FAILED> {
  const transport = new StdioClientTransport({
    command: process.env.CUA_DRIVER_BIN ?? 'cua-driver',
    args: ['mcp'],
    env: driverEnvironment(),
  });
  const ledger = recordToolCallWrites(transport);
  const client = new Client({ name: 'cua-driver-jev-use-example', version: '0.1.0' });
  // Compact what-happened record for the decision model. The full telemetry
  // events (timings, probabilities) go only to the JSONL log.
  const history: HistoryEntry[] = [];
  let visualDelivery: VisualDelivery = 'background';
  let pendingCompletion: GuardedCompletionPlan | undefined;

  try {
    await client.connect(transport);
    const advertisedTools = (await client.listTools()).tools;
    const availableTools = new Set(advertisedTools.map((tool) => tool.name));
    const captureBoundClick = supportsCaptureBoundClick(advertisedTools);
    const driver = new Driver(client, `jev-typescript-${randomUUID().slice(0, 8)}`);
    const prepared = await driver.call('browser_prepare', {
      allow_launch: true,
      profile: { mode: 'isolated_new' },
    });
    const pid = Number(prepared.prepared_pid);
    const window = await waitForWindow(driver, pid);
    const bound = await driver.call('get_browser_state', {
      pid,
      window_id: window.window_id,
    });
    const targetId = String(bound.target_id);
    const tabId = selectTabId(bound.tabs as Record<string, any>[]);
    await driver.call('browser_navigate', {
      target_id: targetId,
      tab_id: tabId,
      url: args.fixtureUrl,
    });

    for (let step = 1; step <= task.maxSteps; step += 1) {
      const current = task.classify(await task.readOracle(), step - 1);
      if (current === 'verified' || current === 'refuted') {
        return finish(task, args.log, pending, current);
      }

      const decisionStarted = performance.now();
      const semanticStarted = performance.now();
      const snapshot = (await driver.call('get_browser_state', {
        target_id: targetId,
        tab_id: tabId,
        snapshot_format: 'semantic_v2',
      })) as BrowserSnapshot;
      const semanticObserveMs = performance.now() - semanticStarted;
      const {
        candidates,
        sources,
        status: visualRecord,
        timing: candidateTiming,
      } = await taskCandidatesForStep(
        driver,
        task,
        snapshot,
        pid,
        Number(window.window_id),
        availableTools,
        captureBoundClick,
        args.visualObservation,
        visualDelivery
      );
      if (!candidates.length) {
        return finish(task, args.log, pending, 'abstained', { step, visual: visualRecord });
      }
      const visual = sources.visual?.observation;
      let guardedCandidate: Candidate | undefined;
      let guardedTelemetry: GuardedCompletionTelemetry | undefined;
      if (args.guardedCompletion && pendingCompletion) {
        const resolution = resolveGuardedCompletion(
          pendingCompletion,
          task,
          sources,
          candidates,
          driver.sessionLabel
        );
        guardedCandidate = resolution.candidate;
        guardedTelemetry = resolution.telemetry;
        // A failed proof never keeps authority alive. The ordinary chooser
        // handles this fresh step instead.
        pendingCompletion = undefined;
      }
      const guardedFields = guardedTelemetry ? { guarded_completion: guardedTelemetry } : {};

      let candidate: Candidate;
      let confidence: number | null;
      let probabilities: Record<string, number> | null;
      let decisionRoute: 'provider' | 'guarded-completion';
      let providerDecisionMs = 0;
      if (guardedCandidate) {
        candidate = guardedCandidate;
        confidence = null;
        probabilities = null;
        decisionRoute = 'guarded-completion';
      } else {
        const providerStarted = performance.now();
        try {
          const answer =
            args.provider === 'mock'
              ? chooseMockForTask(task, sources, candidates, history)
              : await chooseLiveForTask(task, sources, candidates, history);
          providerDecisionMs = performance.now() - providerStarted;
          if (!answer.choice) {
            if (guardedTelemetry) {
              await writeEvent(args.log, {
                event: 'outcome',
                outcome: 'abstained',
                decision_route: 'provider',
                step,
                visual: visualRecord,
                ...guardedFields,
              });
            }
            return 'abstained';
          }
          candidate = validateChoice(answer.choice, candidates, visual?.captureId);
          confidence = answer.confidence;
          probabilities = answer.probabilities;
          decisionRoute = 'provider';
        } catch (error: unknown) {
          if (!guardedTelemetry) throw error;
          await writeEvent(args.log, {
            event: 'outcome',
            outcome: 'unknown',
            step,
            phase: 'provider',
            decision_route: 'provider',
            error: error instanceof Error ? error.name : 'UnknownError',
            visual: visualRecord,
            ...guardedFields,
          });
          return 'unknown';
        }
      }
      const nextCompletion =
        args.guardedCompletion && decisionRoute === 'provider'
          ? planGuardedCompletion(task, sources, candidate, driver.sessionLabel)
          : undefined;
      const decisionMs = Math.round((performance.now() - decisionStarted) * 100) / 100;
      const timing = decisionTimingFields({
        decisionMs,
        semanticObserveMs,
        visualObserveMs: candidateTiming.visualObserveMs,
        candidateBuildMs: candidateTiming.candidateBuildMs,
        providerDecisionMs,
      });

      if (candidate.id === 'reobserve') {
        const event = {
          event: 'step',
          step,
          candidate: candidate.id,
          confidence,
          probabilities,
          ...timing,
          action_ms: 0,
          total_step_ms: Math.round((performance.now() - decisionStarted) * 100) / 100,
          dry_run: args.dryRun,
          tool: null,
          decision_route: decisionRoute,
          visual: visualRecord,
          ...guardedFields,
        };
        history.push(task.historyEntry(step, candidate.id));
        await writeEvent(args.log, event);
        continue;
      }

      if (candidate.id === 'abstain') {
        return finish(task, args.log, pending, 'abstained', {
          decision_route: decisionRoute,
          step,
          confidence,
          probabilities,
          visual: visualRecord,
          ...guardedFields,
        });
      }

      if (pending.receipt && task.completionCandidateIds.has(candidate.id)) {
        // Never dispatch a second completion while the first may land.
        return finish(task, args.log, pending, 'unknown', {
          step,
          phase: 'completion_blocked',
          decision_route: decisionRoute,
          candidate: candidate.id,
        });
      }

      let actionMs = 0;
      if (!args.dryRun) {
        const actionStarted = performance.now();
        try {
          if (!candidate.tool) throw new Error('selected candidate has no executable tool');
          ledger.toolCall = undefined;
          await driver.call(candidate.tool, candidate.arguments);
        } catch (error: unknown) {
          const refusal = backgroundRefusalCode(candidate, error);
          if (refusal) {
            // Do not retry background. The next step takes a fresh capture and
            // offers a distinct foreground candidate.
            visualDelivery = 'foreground';
            const event = {
              event: 'step',
              step,
              candidate: candidate.id,
              confidence,
              probabilities,
              ...timing,
              decision_route: decisionRoute,
              action_ms: Math.round((performance.now() - actionStarted) * 100) / 100,
              total_step_ms: Math.round((performance.now() - decisionStarted) * 100) / 100,
              dry_run: args.dryRun,
              tool: candidate.tool,
              delivery_mode: 'background',
              action_error: refusal,
              escalation: { from: 'background', to: 'foreground', reason: refusal },
              visual: visualRecord,
              ...guardedFields,
            };
            history.push(task.historyEntry(step, candidate.id, refusal));
            await writeEvent(args.log, event);
            continue;
          }
          const fields = {
            step,
            phase: 'action',
            decision_route: decisionRoute,
            error: error instanceof Error ? error.name : 'UnknownError',
            tool: candidate.tool,
            visual: visualRecord,
            ...guardedFields,
          };
          const receipt = ambiguousMutationReceipt({
            session: driver.sessionLabel,
            step,
            candidateId: candidate.id,
          });
          if (ledger.toolCall === 'not_written' && !pending.receipt) {
            // The request's own write raised, so nothing was sent.
            await writeEvent(args.log, {
              ...(mayReconsider ? { event: 'reconsider' } : { event: 'outcome', outcome: 'unknown' }),
              ...fields,
              mutation_outcome: {
                ...receipt,
                attempted: false,
                effect: 'none',
                retryDisposition: mayReconsider ? 'reconsider' : 'none',
                resolution: PRE_WRITE_FAILED,
              },
            });
            return mayReconsider ? PRE_WRITE_FAILED : 'unknown';
          }
          pending.receipt ??= receipt;
          return finish(task, args.log, pending, 'unknown', fields);
        }
        actionMs = Math.round((performance.now() - actionStarted) * 100) / 100;
        pendingCompletion = nextCompletion;
      }
      const event = {
        event: 'step',
        step,
        candidate: candidate.id,
        confidence,
        probabilities,
        ...timing,
        action_ms: actionMs,
        total_step_ms: Math.round((performance.now() - decisionStarted) * 100) / 100,
        dry_run: args.dryRun,
        tool: candidate.tool,
        delivery_mode: candidate.arguments.delivery_mode ?? null,
        decision_route: decisionRoute,
        visual: visualRecord,
        ...guardedFields,
      };
      history.push(task.historyEntry(step, candidate.id));
      await writeEvent(args.log, event);
      if (args.dryRun) return 'unknown';
      if (task.completionCandidateIds.has(candidate.id)) {
        pending.receipt = ambiguousMutationReceipt({
          session: driver.sessionLabel,
          step,
          candidateId: candidate.id,
        });
        for (let attempt = 0; attempt < 20; attempt += 1) {
          const outcome = task.classify(await task.readOracle(), step);
          if (outcome === 'verified' || outcome === 'refuted') {
            return finish(task, args.log, pending, outcome);
          }
          await new Promise((resolve) => setTimeout(resolve, 100));
        }
      }
    }

    const outcome = task.classify(await task.readOracle(), task.maxSteps);
    return finish(task, args.log, pending, outcome);
  } finally {
    await client.close();
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const args = parseArgs(process.argv.slice(2));
  run(args)
    .then((outcome) => {
      process.exitCode = outcome === 'verified' || args.dryRun ? 0 : 1;
    })
    .catch((error: unknown) => {
      console.error(error instanceof Error ? error.message : error);
      process.exitCode = 1;
    });
}
