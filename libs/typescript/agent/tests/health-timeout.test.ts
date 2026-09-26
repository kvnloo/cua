import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import AgentClient from '../src/index.js';

/**
 * health() must not hang forever on a stalled connection. sendHttpRequest()
 * already bounds its fetch with this.options.timeout via AbortController;
 * health() is held to the same contract.
 */
describe('AgentClient.health timeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('passes an AbortSignal to the health fetch', async () => {
    let seenInit: RequestInit | undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) => {
        seenInit = init;
        return new Response('ok', { status: 200 });
      })
    );
    const client = new AgentClient('https://localhost:8000', { timeout: 5000 });
    await client.health();
    expect(seenInit?.signal).toBeInstanceOf(AbortSignal);
  });

  it('resolves unreachable instead of hanging on a stalled health check', async () => {
    // Models real fetch semantics: a stalled request rejects once aborted.
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () =>
              reject(new DOMException('The operation was aborted.', 'AbortError'))
            );
          })
      )
    );
    const client = new AgentClient('https://localhost:8000', { timeout: 5000 });
    const pending = client.health();
    await vi.advanceTimersByTimeAsync(5000);
    await expect(pending).resolves.toEqual({ status: 'unreachable' });
  });

  it('still reports healthy on a fast ok response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('ok', { status: 200 }))
    );
    const client = new AgentClient('https://localhost:8000');
    await expect(client.health()).resolves.toEqual({ status: 'healthy' });
  });

  it('still reports unhealthy on a fast non-ok response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('no', { status: 503 }))
    );
    const client = new AgentClient('https://localhost:8000');
    await expect(client.health()).resolves.toEqual({ status: 'unhealthy' });
  });
});
