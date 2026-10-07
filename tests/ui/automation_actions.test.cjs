const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../../app/routes/ui_assets.py'), 'utf8');
const code = source.slice(source.indexOf('    const automationRunsInFlight'), source.indexOf('    window.deleteAutomation'));
function fixture(fetch) {
  const alerts = [], calls = [];
  let reloads = 0;
  const button = {innerText: 'Run once', disabled: false};
  const context = {Set, alert: text => alerts.push(text), window: {location: {reload: () => reloads++}},
    fetch: async (...args) => {calls.push(args); return fetch(...args);}};
  vm.runInNewContext(code, context);
  return {alerts, calls, button, reloads: () => reloads,
    run: () => context.window.runNow({stopPropagation() {}, currentTarget: button, target: {}}, 7)};
}
test('Run once reports actual draft/schedule/review/publication outcome', async () => {
  for (const [status, expected] of [['drafted', /draft.*approve/], ['scheduled', /scheduled/], ['needs_review', /needs review/], ['published', /published successfully/], ['publish_unknown', /not yet confirmed/]]) {
    const f = fixture(async () => ({ok: true, json: async () => ({status})}));
    await f.run();
    assert.match(f.alerts[0], expected);
    assert.equal(f.reloads(), 1);
    assert.equal(f.button.disabled, false);
  }
});
test('Run once blocks duplicate clicks until the original request completes', async () => {
  let release;
  const gate = new Promise(resolve => {release = resolve;});
  const f = fixture(async () => {await gate; return {ok: true, json: async () => ({status: 'drafted'})};});
  const first = f.run();
  assert.equal(f.button.disabled, true);
  await f.run();
  assert.equal(f.calls.length, 1);
  release(); await first;
  assert.equal(f.button.innerText, 'Run once');
  assert.equal(f.button.disabled, false);
});
test('Failures restore controls and advise checking history before retrying', async () => {
  for (const fetch of [async () => {throw Error('offline');}, async () => ({ok: false, json: async () => {throw Error('not JSON');}})]) {
    const f = fixture(fetch);
    await f.run();
    assert.match(f.alerts[0], /history/);
    assert.equal(f.reloads(), 0);
    assert.equal(f.button.disabled, false);
    assert.equal(f.button.innerText, 'Run once');
  }
});
