// Red-on-base tests: the cloud playground adapters must bound every fetch
// with an AbortSignal, so a stalled connection cannot hang the playground
// UI (chat sends, computer picker, model list) forever.
(globalThis as unknown as Record<string, unknown>).__CUA_VERSION__ = 'test';

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const { createCloudAdapter, CLOUD_API_FETCH_TIMEOUT_MS } = await import('../src/adapters/cloud');

function okJson(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as Response;
}

describe('cloud adapter fetch timeouts', () => {
  let seen: { url: string; init?: RequestInit }[];

  beforeEach(() => {
    seen = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        seen.push({ url, init });
        return okJson([]);
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('exports a positive fetch timeout bound', () => {
    expect(CLOUD_API_FETCH_TIMEOUT_MS).toBeGreaterThan(0);
  });

  it('passes an AbortSignal on persistence fetches', async () => {
    const adapters = createCloudAdapter({ apiKey: 'k' });
    await adapters.persistence.loadChats();
    expect(seen).toHaveLength(1);
    expect(seen[0].init?.signal).toBeInstanceOf(AbortSignal);
  });

  it('passes an AbortSignal on computer fetches', async () => {
    const adapters = createCloudAdapter({ apiKey: 'k' });
    await adapters.computer.listComputers();
    expect(seen).toHaveLength(1);
    expect(seen[0].init?.signal).toBeInstanceOf(AbortSignal);
  });

  it('passes an AbortSignal on the model-list fetch', async () => {
    const adapters = createCloudAdapter({ apiKey: 'k' });
    await adapters.inference.getAvailableModels();
    expect(seen).toHaveLength(1);
    expect(seen[0].init?.signal).toBeInstanceOf(AbortSignal);
  });

  it('a stalled computer listing settles instead of hanging forever', async () => {
    // Force the timeout signal to be already aborted: simulates the stall
    // elapsing without waiting out the real 30s bound.
    vi.spyOn(AbortSignal, 'timeout').mockReturnValue(AbortSignal.abort());
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init?: RequestInit) =>
          new Promise<never>((_resolve, reject) => {
            const onAbort = () =>
              reject(new DOMException('The operation was aborted.', 'AbortError'));
            // An already-aborted signal never re-fires the event.
            if (init?.signal?.aborted) onAbort();
            else init?.signal?.addEventListener('abort', onAbort);
            // never resolves on its own: the stalled connection
          })
      )
    );
    const adapters = createCloudAdapter({ apiKey: 'k' });
    const safety = new Promise<string>((resolve) => setTimeout(() => resolve('HUNG'), 3000));
    const outcome = await Promise.race([
      adapters.computer
        .listComputers()
        .then(() => 'RESOLVED')
        .catch(() => 'REJECTED'),
      safety,
    ]);
    // On base there is no signal at all, so the abort never fires and the
    // safety timer wins ('HUNG'). On the fix the aborted signal rejects.
    expect(outcome).not.toBe('HUNG');
  });

  it('a stalled model-list fetch falls back to default models', async () => {
    vi.spyOn(AbortSignal, 'timeout').mockReturnValue(AbortSignal.abort());
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init?: RequestInit) =>
          new Promise<never>((_resolve, reject) => {
            const onAbort = () =>
              reject(new DOMException('The operation was aborted.', 'AbortError'));
            // An already-aborted signal never re-fires the event.
            if (init?.signal?.aborted) onAbort();
            else init?.signal?.addEventListener('abort', onAbort);
            // never resolves on its own: the stalled connection
          })
      )
    );
    const adapters = createCloudAdapter({ apiKey: 'k' });
    const safety = new Promise<string>((resolve) => setTimeout(() => resolve('HUNG'), 3000));
    const outcome = await Promise.race([
      adapters.inference
        .getAvailableModels()
        .then((models) => (models.length > 0 ? 'DEFAULTS' : 'EMPTY')),
      safety,
    ]);
    expect(outcome).toBe('DEFAULTS');
  });
});
