// Red-on-base test: connect() must reject instead of hanging forever when
// the WebSocket opening handshake stalls (TCP accepted, handshake never
// answered). Without handshakeTimeout the connect promise never settles and
// waitForReady()'s retry loop hangs with it.
import net from 'node:net';
import { describe, it, expect } from 'vitest';
import { MacOSComputerInterface } from '../../src/interface/macos.ts';
import { WS_HANDSHAKE_TIMEOUT_MS } from '../../src/interface/base.ts';

describe('websocket handshake timeout', () => {
  it('exports a positive handshake timeout bound', () => {
    expect(WS_HANDSHAKE_TIMEOUT_MS).toBeGreaterThan(0);
  });

  it('connect() rejects instead of hanging on a stalled handshake', async () => {
    // Accept TCP connections but never speak HTTP: the WS handshake stalls.
    const server = net.createServer(() => {});
    await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
    const port = (server.address() as net.AddressInfo).port;
    try {
      const iface = new MacOSComputerInterface(`127.0.0.1:${port}`, 'u', 'p');
      const outcome = await Promise.race([
        iface
          .connect()
          .then(() => 'RESOLVED')
          .catch(() => 'REJECTED'),
        // Generous ceiling: the bound is 10s, so a hang past 20s is a fail.
        new Promise<string>((resolve) => setTimeout(() => resolve('HUNG'), 20000)),
      ]);
      // On base there is no handshake bound, the safety timer wins ('HUNG').
      expect(outcome).toBe('REJECTED');
    } finally {
      server.close();
    }
  }, 25000);
});
