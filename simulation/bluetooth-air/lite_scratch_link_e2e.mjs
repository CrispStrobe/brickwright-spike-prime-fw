// SPDX-License-Identifier: Apache-2.0
// Brickwright lite in a real browser, reaching the Renode-emulated SPIKE hub
// through the Scratch Link node on the simulated air.
//
//   node lite_scratch_link_e2e.mjs [LITE_URL] [PLAYWRIGHT_MODULE]
//
// Run by test_spike_air.py --then, which provides the hub and the Scratch
// Link node on 127.0.0.1:20111. Lite's own virtual hub stays OFF (its default),
// so the extension dials the real Scratch Link socket. Steps, each checked:
//   1. load lite and its SPIKE Prime extension (id "spikeprime");
//   2. scan: the extension's auto route starts with Scratch Link BLE, which
//      lists the emulated hub;
//   3. connect to it;
//   4. read the hub over the SPIKE 3 protocol: the "hub firmware version"
//      block reports what the hub's InfoResponse carried;
//   5. run the "set pixel" block and the "display text" block (writes on
//      FD02 that the hub must accept).
import { pathToFileURL } from 'node:url';

const liteUrl = process.argv[2] || 'https://brickwright-lite.vercel.app/';
const playwrightModule = process.argv[3] ||
  '/mnt/volume1/code/lego/brickwright-lite/node_modules/playwright/index.mjs';
const { chromium } = await import(pathToFileURL(playwrightModule).href);

const log = (...args) => console.log('[lite-e2e]', ...args);
const browser = await chromium.launch({ args: ['--js-flags=--max-old-space-size=768'] });
let failed = false;
try {
  const page = await browser.newPage();
  page.on('console', message => {
    const text = message.text();
    if (/SPIKE|Scratch Link|scratch-link|peripheral/i.test(text)) log('console:', text.slice(0, 160));
  });
  await page.goto(liteUrl, { waitUntil: 'load', timeout: 240000 });
  await page.waitForFunction(() => {
    const vm = window.__brickwrightStore?.getState?.()?.scratchGui?.vm;
    if (vm) window.__vm = vm;
    return Boolean(vm && vm.extensionManager);
  }, null, { timeout: 240000 });
  log('lite loaded:', liteUrl);

  const loaded = await page.evaluate(async () => {
    await window.__vm.extensionManager.loadExtensionURL('spikeprime');
    const virtual = window.__brickwrightVirtualSpike?.snapshot?.();
    return { virtualHubEnabled: virtual ? virtual.simulationEnabled : null };
  });
  log('extension loaded; virtual hub enabled =', loaded.virtualHubEnabled);
  if (loaded.virtualHubEnabled) throw new Error('lite virtual hub must be off');

  const found = await page.evaluate(() => new Promise((resolve, reject) => {
    const runtime = window.__vm.runtime;
    const timer = setTimeout(() => reject(new Error('no peripheral listed')), 90000);
    runtime.on('PERIPHERAL_LIST_UPDATE', list => {
      const ids = Object.keys(list || {});
      if (ids.length) { clearTimeout(timer); resolve({ ids, list }); }
    });
    runtime.on('PERIPHERAL_REQUEST_ERROR', error => {
      clearTimeout(timer); reject(new Error('request error: ' + JSON.stringify(error)));
    });
    window.__vm.scanForPeripheral('spikeprime');
  }));
  log('scan listed:', JSON.stringify(found.list));

  const connected = await page.evaluate(id => new Promise((resolve, reject) => {
    const runtime = window.__vm.runtime;
    const timer = setTimeout(() => reject(new Error('connect timed out')), 90000);
    runtime.on('PERIPHERAL_CONNECTED', () => { clearTimeout(timer); resolve(true); });
    runtime.on('PERIPHERAL_REQUEST_ERROR', error => {
      clearTimeout(timer); reject(new Error('request error: ' + JSON.stringify(error)));
    });
    window.__vm.connectPeripheral('spikeprime', id);
  }), found.ids[0]);
  log('connected:', connected);

  const firmware = await page.waitForFunction(() => {
    const primitive = window.__vm.runtime._primitives.spikeprime_getFirmwareVersion;
    const value = primitive ? primitive({}, {}) : '';
    return value ? String(value) : false;
  }, null, { timeout: 60000, polling: 500 });
  const hub = await page.evaluate(() => ({
    firmware: String(window.__vm.runtime._primitives.spikeprime_getFirmwareVersion({}, {})),
    hubType: String(window.__vm.runtime._primitives.spikeprime_getHubType?.({}, {}) ?? ''),
    mode: String(window.__vm.runtime._primitives.spikeprime_getConnectionMode?.({}, {}) ?? '')
  }));
  log('hub firmware version block:', JSON.stringify(hub));
  if (!(await firmware.jsonValue())) throw new Error('no firmware version');

  const blocks = await page.evaluate(async () => {
    const p = window.__vm.runtime._primitives;
    const results = {};
    for (const [name, args] of [
      ['spikeprime_setPixel', { X: 3, Y: 3, BRIGHTNESS: 100 }],
      ['spikeprime_displayText', { TEXT: 'Hi' }]
    ]) {
      try {
        const value = await p[name](args, {});
        results[name] = { ok: true, value: value === undefined ? null : String(value) };
      } catch (error) {
        results[name] = { ok: false, error: String(error) };
      }
    }
    return results;
  });
  log('blocks:', JSON.stringify(blocks));
  for (const [name, result] of Object.entries(blocks))
    if (!result.ok) throw new Error(`${name} failed: ${result.error}`);
  log('PASS');
} catch (error) {
  failed = true;
  log('FAIL', error && error.stack ? error.stack : String(error));
} finally {
  await browser.close();
}
process.exit(failed ? 1 : 0);
