import { afterEach, describe, expect, it, vi } from 'vitest';
// Import the cloud provider module directly: importing '../../src' would also
// pull in the fleet provider's @trycua/fleet native binding (unbuilt in this
// sandbox), which is irrelevant to the host-lookup path under test.
import { CloudComputer } from '../../src/computer/providers/cloud';
import { CLOUD_VM_LIST_FETCH_TIMEOUT_MS } from '../../src/computer/providers/cloud';
import { OSType } from '../../src/types';

const NAME = 's-linux-1234';
const FALLBACK_HOST = `${NAME}.sandbox.cua.ai`;

function makeComputer() {
  return new CloudComputer({
    apiKey: 'asdf',
    name: NAME,
    osType: OSType.LINUX,
  });
}

/**
 * A fetch stub that hangs forever unless the caller aborts: mirrors a stalled
 * TCP connection on the wire, where no bytes arrive and no error is raised.
 */
function hangingFetch() {
  return vi.fn((_url: unknown, init?: RequestInit) => {
    return new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => {
        reject(new DOMException('The operation was aborted.', 'AbortError'));
      });
    });
  });
}

describe('Computer Cloud fetchAndCacheHost', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('passes an AbortSignal to the VM-list fetch', async () => {
    vi.useFakeTimers();
    const fetch = hangingFetch();
    vi.stubGlobal('fetch', fetch);
    const p = (makeComputer() as any).fetchAndCacheHost();
    // fetch() is invoked synchronously inside fetchAndCacheHost before its
    // first await, so the assertion is valid immediately.
    expect(fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    await vi.advanceTimersByTimeAsync(CLOUD_VM_LIST_FETCH_TIMEOUT_MS);
    await expect(p).resolves.toBe(FALLBACK_HOST);
  });

  it('aborts a stalled VM-list lookup and falls back to the default host', async () => {
    vi.stubGlobal('fetch', hangingFetch());
    vi.useFakeTimers();
    const p = (makeComputer() as any).fetchAndCacheHost();
    // On a stalled connection no abort fires before the bound: still pending.
    let settled = false;
    void p.then(
      () => (settled = true),
      () => (settled = true)
    );
    await vi.advanceTimersByTimeAsync(CLOUD_VM_LIST_FETCH_TIMEOUT_MS - 1);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await expect(p).resolves.toBe(FALLBACK_HOST);
  });

  it('still resolves the API-provided host on a fast successful lookup', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        return {
          ok: true,
          json: async () => [{ name: NAME, host: '10.0.0.9' }],
        } as Response;
      })
    );
    await expect((makeComputer() as any).fetchAndCacheHost()).resolves.toBe('10.0.0.9');
  });

  it('falls back to the default host when the API omits the VM', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, json: async () => [] }) as Response)
    );
    await expect((makeComputer() as any).fetchAndCacheHost()).resolves.toBe(FALLBACK_HOST);
  });
});
