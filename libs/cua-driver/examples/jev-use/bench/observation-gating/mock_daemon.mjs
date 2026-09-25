/**
 * Mock cua-driver daemon for the observation-gating live bench.
 *
 * Speaks the daemon's newline-delimited JSON socket protocol (one request per
 * connection, like libs/cua-driver/typescript/test/native-daemon-fixture.mjs)
 * so the bench drives the REAL wire format: real serialization, real socket
 * IPC, real client-side parsing of the visual payload. The driver itself is
 * fake (no browser), but every byte the loop's observation path touches is
 * real.
 *
 * Serves a stateful jev-use fixture: get_browser_state returns a semantic_v2
 * snapshot whose refs depend on the scenario and on prior actions
 * (browser_type fills the verification field, browser_click/click submits).
 *
 * Usage:
 *   node mock_daemon.mjs --socket /tmp/cua-mock.sock \
 *     --scenario dom-complete|visual-fallback --regions 50
 */
import net from "node:net";
import fs from "node:fs";

const args = process.argv.slice(2);
function flag(name, def) {
  const i = args.indexOf(name);
  return i >= 0 && i + 1 < args.length ? args[i + 1] : def;
}
const socketPath = flag("--socket", null);
let scenario = flag("--scenario", "dom-complete");
const regionCount = Math.max(1, parseInt(flag("--regions", "50"), 10));
// --keep-alive: keep each connection open and serve every newline-delimited
// request on it, instead of one request per connection. Fork prototype only;
// the real daemon closes after one request (see REPORT-keepalive.md).
const keepAlive = args.includes("--keep-alive");
if (!socketPath) throw new Error("missing --socket");
if (!["dom-complete", "visual-fallback"].includes(scenario)) {
  throw new Error(`unknown scenario: ${scenario}`);
}

const PID = 4242;
const WINDOW_ID = 7;

// Fixture state, mutated by action calls.
let fieldValue = "other";
let submitted = null;
let captureSeq = 0;

function snapshot() {
  const refs = [
    { role: "textbox", name: "verification value", ref: "r1", value: fieldValue },
  ];
  if (scenario === "dom-complete") {
    refs.push({ role: "button", name: "Submit", ref: "r2" });
  }
  return { target_id: "t", tab_id: "tab", refs };
}

function visualPayload(captureId) {
  const regions = [];
  for (let i = 0; i < regionCount; i += 1) {
    const isSubmit = i === 0;
    // Keep every region inside the 1280x800 screenshot: parseVisualRegions
    // validates bounds, so wrap decoys instead of marching off-canvas.
    const x = 10 + ((i * 37) % 1150);
    const y = 20 + ((i * 53) % 700);
    regions.push({
      id: `v${i}`,
      kind: "text",
      text: isSubmit ? "Submit" : `Decoy label ${i}`,
      confidence: isSubmit ? 0.9 : 0.5 + (i % 40) / 100,
      interactive: true,
      bounds: { x, y, width: 80, height: 30 },
    });
  }
  return {
    schema: "cua.visual_regions_v1",
    capture: {
      capture_id: captureId,
      source: { kind: "window", pid: PID, window_id: WINDOW_ID },
      screenshot: {
        mime_type: "image/png",
        reference: "sha256:bench",
        width: 1280,
        height: 800,
      },
      action_coordinate_space: { kind: "screenshot_pixels" },
    },
    regions,
  };
}

function structuredContent(request) {
  const { name, args: callArgs = {} } = request;
  switch (name) {
    case "get_browser_state":
      return snapshot();
    case "get_window_state": {
      captureSeq += 1;
      return { capture_id: `cap-${captureSeq}` };
    }
    case "parse_visual_regions":
      return visualPayload(String(callArgs.capture_id));
    case "browser_type":
      fieldValue = String(callArgs.text);
      return { ok: true };
    case "browser_click":
    case "click":
      submitted = fieldValue;
      return { ok: true };
    case "observe_visual": {
      // PROTOTYPE protocol extension (fork research artifact): capture and
      // parse in one round trip, daemon-side. No upstream contract change.
      captureSeq += 1;
      const captureId = `cap-${captureSeq}`;
      return { capture_id: captureId, ...visualPayload(captureId) };
    }
    case "fixture_submitted":
      return { submitted };
    case "set_field": {
      // Bench control: preset the verification field so a step's visual need
      // is deterministic (mock-only).
      fieldValue = String(callArgs.value ?? "");
      return { ok: true };
    }
    case "set_scenario": {
      // Bench control: switch the served scenario mid-run so a scripted
      // visual-need sequence can be driven step by step. Mock-only.
      const next = String(callArgs.scenario);
      if (!["dom-complete", "visual-fallback"].includes(next)) {
        return { error: `unknown scenario: ${next}` };
      }
      scenario = next;
      return { ok: true, scenario: next };
    }
    default:
      return { error: `mock daemon has no handler for ${name}` };
  }
}

try {
  fs.unlinkSync(socketPath);
} catch {
  /* first run */
}
const server = net.createServer((connection) => {
  let buffer = "";
  connection.setEncoding("utf8");
  const respond = (payload) => connection.write(`${JSON.stringify(payload)}\n`);
  connection.on("data", (chunk) => {
    buffer += chunk;
    // Keep-alive mode: drain every complete request line in the buffer.
    // One-request-per-connection mode: serve only the first.
    for (;;) {
      const newline = buffer.indexOf("\n");
      if (newline < 0) break;
      const line = buffer.slice(0, newline);
      buffer = buffer.slice(newline + 1);
      let request;
      try {
        request = JSON.parse(line);
      } catch {
        connection.end(`${JSON.stringify({ ok: false, error: "bad json" })}\n`);
        return;
      }
      if (request.method === "metadata") {
        respond({
          ok: true,
          result: {
            driver_version: "mock-0.0.0",
            contract_version: "0.8.0",
            embedded: false,
          },
        });
        continue;
      }
      respond({
        ok: true,
        result: {
          content: [{ type: "text", text: "mock daemon" }],
          structuredContent: structuredContent(request),
          isError: false,
        },
      });
    }
    if (!keepAlive) connection.end();
  });
});

server.listen(socketPath, () => {
  process.stdout.write(`ready ${socketPath}\n`);
});
