// Arm C adapter (read-only): reads the jev-use fixture status through opencli's CDP attach route.
// Credit: opencli is jackwener/opencli (https://github.com/jackwener/opencli). Downstream fork: kvnloo/opencli.
// Install: copy this directory to ~/.opencli/clis/jev/ . Fails closed on any non-loopback origin.
import { cli, Strategy } from '@jackwener/opencli/registry';

cli({
  site: 'jev',
  name: 'read-status',
  description: 'Read the fixture status text (read-only, loopback fixture only)',
  access: 'read',
  example: 'opencli jev read-status --origin http://127.0.0.1:8766',
  domain: '127.0.0.1',
  strategy: Strategy.UI,
  browser: true,
  navigateBefore: false,
  args: [{ name: 'origin', default: 'http://127.0.0.1:8766', help: 'loopback fixture origin (http://127.0.0.1:PORT)' }],
  columns: ['url', 'title', 'status', 'input_label'],
  func: async (page, kwargs) => {
    const origin = String(kwargs.origin);
    if (!/^http:\/\/127\.0\.0\.1:\d{2,5}$/.test(origin)) throw new Error('origin refused (fail closed)');
    await page.goto(origin + '/');
    const r = await page.evaluate(`(() => ({
      url: location.href,
      title: document.title,
      status: document.querySelector('output')?.textContent ?? null,
      input_label: document.querySelector('input[name=value]')?.getAttribute('aria-label') ?? null,
    }))()`);
    if (!r || typeof r.url !== 'string' || !r.url.startsWith(origin + '/') || r.status === null) {
      throw new Error('unexpected page (fail closed)');
    }
    return [r];
  },
});
