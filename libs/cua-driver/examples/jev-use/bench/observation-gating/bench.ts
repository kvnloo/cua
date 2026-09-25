/**
 * Benchmark: modality-gated observation in the jev-use recipe loop.
 *
 * Mirrors the per-step observation sequence of typescript/run.ts under two
 * policies:
 *   baseline — get_browser_state + (get_window_state + parse_visual_regions)
 *              on EVERY step (pre-change behavior);
 *   gated    — get_browser_state every step; the visual pair only when the
 *              snapshot alone yields no actionable candidate (new behavior).
 *
 * The driver is fake: per-tool latencies are scenario parameters (virtual
 * milliseconds — no sleeping, deterministic), so what is MEASURED is the
 * policy's call pattern (which observations actually run); wall-clock savings
 * are reported as eliminated-calls x per-call cost at three cost points.
 * Gate-predicate CPU overhead is measured separately with real timers.
 *
 * Run: node --import tsx bench/observation-gating/bench.ts
 */
import { buildCandidates, chooseMock, parseVisualRegions } from '../../typescript/core.js';
import { needsVisualObservation, ObservationLedger } from '../../typescript/observation.js';

type LatencyModel = Record<string, number>;

const DEFAULT_LATENCY: LatencyModel = {
  get_browser_state: 180,
  get_window_state: 220,
  parse_visual_regions: 640,
  browser_type: 300,
  browser_click: 150,
};

const TOKEN = 'bench-token';
const PID = 4242;
const WINDOW_ID = 7;

type Scenario = 'dom-complete' | 'visual-fallback';

class FakeDriver {
  calls: { name: string; latencyMs: number }[] = [];
  fieldValue = 'other';
  submitted: string | null = null;
  constructor(
    private readonly latency: LatencyModel,
    private readonly scenario: Scenario,
  ) {}

  async call(name: string, args: Record<string, unknown>): Promise<Record<string, any>> {
    const latencyMs = this.latency[name] ?? 0;
    this.calls.push({ name, latencyMs });
    switch (name) {
      case 'get_browser_state': {
        const refs: Record<string, unknown>[] = [
          { role: 'textbox', name: 'verification value', ref: 'r1', value: this.fieldValue },
        ];
        if (this.scenario === 'dom-complete') {
          refs.push({ role: 'button', name: 'Submit', ref: 'r2' });
        }
        return { target_id: 't', tab_id: 'tab', refs };
      }
      case 'get_window_state':
        return { capture_id: `cap-${this.calls.length}` };
      case 'parse_visual_regions': {
        const captureId = String(args.capture_id);
        return {
          schema: 'cua.visual_regions_v1',
          capture: {
            capture_id: captureId,
            source: { kind: 'window', pid: PID, window_id: WINDOW_ID },
            screenshot: {
              mime_type: 'image/png',
              reference: 'shot-1',
              width: 1280,
              height: 800,
            },
            action_coordinate_space: { kind: 'screenshot_pixels' },
          },
          regions: [
            {
              id: 'v1',
              kind: 'text',
              text: 'Submit',
              confidence: 0.9,
              interactive: true,
              bounds: { x: 100, y: 100, width: 80, height: 30 },
            },
          ],
        };
      }
      case 'browser_type':
        this.fieldValue = String(args.text);
        return { ok: true };
      case 'browser_click':
        this.submitted = this.fieldValue;
        return { ok: true };
      case 'click':
        // Visual-submit fallback clicks the Submit region by coordinates.
        this.submitted = this.fieldValue;
        return { ok: true };
      default:
        throw new Error(`unexpected tool: ${name}`);
    }
  }

  observationLatency(): number {
    return this.calls
      .filter((call) =>
        ['get_browser_state', 'get_window_state', 'parse_visual_regions'].includes(call.name),
      )
      .reduce((sum, call) => sum + call.latencyMs, 0);
  }

  observationCalls(): number {
    return this.calls.filter((call) =>
      ['get_browser_state', 'get_window_state', 'parse_visual_regions'].includes(call.name),
    ).length;
  }
}

async function visualObservation(driver: FakeDriver): Promise<ReturnType<typeof parseVisualRegions>> {
  const capture = await driver.call('get_window_state', { pid: PID, window_id: WINDOW_ID });
  const result = await driver.call('parse_visual_regions', {
    capture_id: capture.capture_id,
    options: { kinds: ['text', 'icon'], min_confidence: 0.8, max_regions: 100 },
  });
  return parseVisualRegions(result, capture.capture_id, PID, WINDOW_ID);
}

type StepResult = { verified: boolean; steps: number };

async function runTask(
  policy: 'baseline' | 'gated',
  scenario: Scenario,
  latency: LatencyModel,
  maxSteps = 4,
): Promise<{ result: StepResult; driver: FakeDriver; ledger: ObservationLedger }> {
  const driver = new FakeDriver(latency, scenario);
  const ledger = new ObservationLedger();
  const captureBoundClick = true;
  let steps = 0;
  for (let step = 1; step <= maxSteps; step += 1) {
    steps = step;
    if (driver.submitted === TOKEN) return { result: { verified: true, steps }, driver, ledger };
    const snapshot: any = await driver.call('get_browser_state', {
      target_id: 't',
      tab_id: 'tab',
      snapshot_format: 'semantic_v2',
    });
    ledger.record({ kind: 'snapshot', latencyMs: latency.get_browser_state }, step);

    let visual: ReturnType<typeof parseVisualRegions> | undefined;
    let candidates = buildCandidates(snapshot, TOKEN, undefined, captureBoundClick);
    const gateApplies = policy === 'gated';
    if (!gateApplies || needsVisualObservation(candidates)) {
      visual = await visualObservation(driver);
      ledger.record(
        {
          kind: 'visual',
          captureId: visual.captureId,
          latencyMs: latency.get_window_state + latency.parse_visual_regions,
        },
        step,
      );
      if (gateApplies) {
        candidates = buildCandidates(snapshot, TOKEN, visual, captureBoundClick);
      } else {
        candidates = buildCandidates(snapshot, TOKEN, visual, captureBoundClick);
      }
    }
    const answer = chooseMock(candidates);
    if (!answer.choice || answer.choice === 'abstain' || answer.choice === 'reobserve') {
      return { result: { verified: false, steps }, driver, ledger };
    }
    const candidate = candidates.find((item) => item.id === answer.choice)!;
    if (!candidate.tool) return { result: { verified: false, steps }, driver, ledger };
    await driver.call(candidate.tool, candidate.arguments as Record<string, unknown>);
  }
  return { result: { verified: driver.submitted === TOKEN, steps }, driver, ledger };
}

function measureGateOverhead(): number {
  const snapshot: any = {
    target_id: 't',
    tab_id: 'tab',
    refs: [{ role: 'textbox', name: 'verification value', ref: 'r1', value: 'other' }],
  };
  const candidates = buildCandidates(snapshot, TOKEN, undefined, true);
  const iterations = 200_000;
  const started = process.hrtime.bigint();
  for (let i = 0; i < iterations; i += 1) needsVisualObservation(candidates);
  const elapsedNs = Number(process.hrtime.bigint() - started);
  return elapsedNs / iterations;
}

async function main(): Promise<void> {
  const scenarios: Scenario[] = ['dom-complete', 'visual-fallback'];
  const rows: Record<string, unknown>[] = [];
  for (const scenario of scenarios) {
    for (const policy of ['baseline', 'gated'] as const) {
      const { result, driver, ledger } = await runTask(policy, scenario, DEFAULT_LATENCY);
      if (!result.verified) throw new Error(`${policy}/${scenario} did not verify`);
      rows.push({
        scenario,
        policy,
        steps: result.steps,
        observation_calls: driver.observationCalls(),
        visual_observations: ledger.count('visual'),
        observation_ms_virtual: driver.observationLatency(),
      });
    }
  }
  const gateNs = measureGateOverhead();
  console.log(JSON.stringify({ latencies_ms: DEFAULT_LATENCY, rows, gate_overhead_ns: Math.round(gateNs) }, null, 2));

  // Sensitivity: savings as a function of visual-path cost.
  console.log('--- sensitivity (saved observation ms per task vs visual-path cost) ---');
  for (const visualMs of [200, 860, 2000]) {
    const latency = { ...DEFAULT_LATENCY, get_window_state: Math.round(visualMs * 0.26), parse_visual_regions: Math.round(visualMs * 0.74) };
    const parts: string[] = [];
    for (const scenario of scenarios) {
      const base = await runTask('baseline', scenario, latency);
      const gated = await runTask('gated', scenario, latency);
      parts.push(`${scenario}: ${base.driver.observationLatency() - gated.driver.observationLatency()}ms`);
    }
    console.log(`visual_path=${visualMs}ms -> ${parts.join(', ')}`);
  }
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
