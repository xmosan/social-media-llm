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
test('New Growth Plans select shared cards; editing preserves the existing media mode', async () => {
  const submit = source.slice(source.indexOf('    window.submitNewAutoV2 ='), source.indexOf('    window.showEditModal ='));
  for (const editId of [undefined, '7']) {
    const button = {innerText: 'Save', disabled: false};
    const fields = {btnSubmitAutoV2: button, autoV2ApprovalModeInput: {value: 'needs_manual_approve'}, autoV2CadenceInput: {value: 'daily'}};
    let sent;
    const form = {dataset: {editId}, name: {value: 'Fixture'}, topic_prompt: {value: 'wisdom'}, style_dna_id: {value: '1'}, ig_account_id: {value: '1'}, post_time_local: {value: '17:00'}};
    const context = {document: {getElementById: id => fields[id]}, window: {location: {reload() {}}},
      fetch: async (url, options) => {sent = JSON.parse(options.body); return {ok: true};}};
    vm.runInNewContext(submit, context);
    await context.window.submitNewAutoV2({preventDefault() {}, target: form});
    assert.equal(sent.image_mode, editId ? undefined : 'quote_card');
    assert.equal(sent.approval_mode, 'needs_manual_approve');
    assert.equal(button.disabled, false);
  }
});
test('Pause and resume update the plan once and restore controls after failure', async () => {
  const toggle = source.slice(source.indexOf('    const automationTogglesInFlight'), source.indexOf('    const automationRunsInFlight'));
  for (const enabled of [false, true]) {
    let release, reloads = 0;
    const gate = new Promise(resolve => {release = resolve;});
    const calls = [], alerts = [], button = {disabled: false, innerText: enabled ? 'Paused' : 'Active'};
    const context = {Set, alert: message => alerts.push(message), window: {location: {reload: () => reloads++}},
      fetch: async (...args) => {calls.push(args); await gate; return {ok: true, json: async () => ({enabled})};}};
    vm.runInNewContext(toggle, context);
    const event = {stopPropagation() {}, currentTarget: button, target: {}};
    const first = context.window.toggleAuto(event, 41, enabled);
    await context.window.toggleAuto(event, 41, enabled);
    assert.equal(calls.length, 1);
    assert.equal(button.disabled, true);
    assert.deepEqual(JSON.parse(calls[0][1].body), {enabled});
    assert.equal(calls[0][0], '/automations/41');
    assert.equal(calls[0][1].method, 'PATCH');
    release(); await first;
    assert.equal(reloads, 1);
    assert.equal(button.disabled, false);
    for (const fetch of [async () => {throw Error('offline');}, async () => ({ok: false, json: async () => ({detail: 'Fixture rejection'})})]) {
      context.fetch = fetch;
      await context.window.toggleAuto(event, 41, enabled);
      assert.equal(reloads, 1);
      assert.equal(button.disabled, false);
    }
    assert.equal(alerts.length, 2);
  }
});
