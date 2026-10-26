// Arm C adapter (WRITE; phase synthetic_write only, after read-only proof and owner authority).
// Credit: opencli is jackwener/opencli. Fills the fixture input and clicks Submit exactly once.
// Never retries. The caller must confirm the effect through the independent /state and /audit oracle.
import { cli, Strategy } from '@jackwener/opencli/registry';

cli({
  site: 'jev',
  name: 'submit-value',
  description: 'Submit one verification value to the loopback fixture (synthetic write, single attempt)',
  access: 'write',
  example: 'opencli jev submit-value --value v1 --confirm-write yes',
  domain: '127.0.0.1',
  strategy: Strategy.UI,
  browser: true,
  navigateBefore: false,
  args: [
    { name: 'value', required: true, help: 'verification value' },
    { name: 'origin', default: 'http://127.0.0.1:8766', help: 'loopback fixture origin' },
    { name: 'confirm-write', default: 'no', help: 'must be "yes"; otherwise nothing is touched' },
  ],
  columns: ['url', 'status'],
  func: async (page, kwargs) => {
    const origin = String(kwargs.origin);
    if (!/^http:\/\/127\.0\.0\.1:\d{2,5}$/.test(origin)) throw new Error('origin refused (fail closed)');
    if (String(kwargs['confirm-write']) !== 'yes') throw new Error('write not confirmed (fail closed)');
    const value = String(kwargs.value);
    if (!value || value.length > 200) throw new Error('invalid value (fail closed)');
    await page.goto(origin + '/');
    const found = await page.evaluate(`(() => {
      const inputs = document.querySelectorAll('input[name=value][aria-label="verification value"]');
      const buttons = document.querySelectorAll('form button[type=submit]');
      return { inputs: inputs.length, buttons: buttons.length, url: location.href };
    })()`);
    if (!found || found.inputs !== 1 || found.buttons !== 1 || !found.url.startsWith(origin + '/')) {
      throw new Error('target not unique or origin changed (fail closed)');
    }
    // One submission. A throw after this click is an UNKNOWN effect: the caller reads /audit and never replays.
    await page.evaluate(`(() => {
      const input = document.querySelector('input[name=value][aria-label="verification value"]');
      input.value = ${JSON.stringify(value)};
      document.querySelector('form button[type=submit]').click();
    })()`);
    await page.wait(1);
    const r = await page.evaluate(`(() => ({ url: location.href, status: document.querySelector('output')?.textContent ?? null }))()`);
    return [r];
  },
});
