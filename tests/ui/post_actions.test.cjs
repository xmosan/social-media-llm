const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../../app/routes/ui_assets.py'), 'utf8');
const actions = source.slice(source.indexOf('    let postEditInFlight = false;'), source.indexOf('    window.refinePostAI ='));
const calendar = source.slice(source.indexOf('    window.syncCalendarTimezone ='), source.indexOf('    window.showStudioConfirm ='));

function fixture(fetch) {
  const elements = {editPostId: {value: '1523'}, editPostCaption: {value: 'Reviewed fixture caption'},
    savePostBtn: {disabled: false}, postNowBtn: {disabled: false, innerText: 'SHARE NOW'}};
  const calls = [], alerts = [];
  let reloads = 0;
  const context = {document: {getElementById: id => elements[id]}, alert: msg => alerts.push(msg),
    window: {closeEditPostModal() {}, location: {reload() {reloads++;}}},
    fetch: async (...args) => {calls.push(args); return fetch(...args);}};
  vm.runInNewContext(actions, context);
  return {context, elements, calls, alerts, reloads: () => reloads};
}
const response = (ok, detail) => ({ok, json: async () => ({detail})});

test('Share Now saves the exact reviewed caption before one publish request', async () => {
  const f = fixture(async () => response(true));
  await f.context.window.publishPostNow();
  assert.deepEqual(f.calls.map(([url, options]) => [url, options.method]), [['/posts/1523', 'PATCH'], ['/posts/1523/publish', 'POST']]);
  assert.equal(JSON.parse(f.calls[0][1].body).caption, 'Reviewed fixture caption');
  assert.equal(f.reloads(), 1);
  assert.equal(f.elements.postNowBtn.disabled, false);
});

test('Rejected save, non-JSON error, and network failure never publish stale content', async () => {
  for (const fetch of [async () => response(false, 'Source validation failed'),
    async () => ({ok: false, json: async () => {throw Error('not JSON');}}),
    async () => {throw Error('offline');}]) {
    const f = fixture(fetch);
    await f.context.window.publishPostNow();
    assert.equal(f.calls.length, 1);
    assert.equal(f.reloads(), 0);
    assert.equal(f.alerts.length, 1);
    assert.equal(f.elements.postNowBtn.disabled, false);
    assert.equal(f.elements.savePostBtn.disabled, false);
  }
});

test('An empty edited caption cannot publish the previously saved caption', async () => {
  const f = fixture(async () => response(true));
  f.elements.editPostCaption.value = ' ';
  await f.context.window.publishPostNow();
  assert.equal(f.calls.length, 0);
  assert.equal(f.alerts.length, 1);
});

test('Duplicate clicks and a competing save cannot overlap publishing', async () => {
  let release;
  const gate = new Promise(resolve => {release = resolve;});
  const f = fixture(async () => {await gate; return response(true);});
  const first = f.context.window.publishPostNow();
  assert.equal(f.elements.postNowBtn.disabled, true);
  assert.equal(f.elements.savePostBtn.disabled, true);
  await f.context.window.publishPostNow();
  await f.context.window.savePostEdit();
  assert.equal(f.calls.length, 1);
  release();
  await first;
  assert.equal(f.calls.length, 2);
});

test('Publication failure restores controls and does not retry automatically', async () => {
  const f = fixture(async url => response(!url.endsWith('/publish'), 'Outcome needs reconciliation'));
  await f.context.window.publishPostNow();
  assert.equal(f.calls.length, 2);
  assert.equal(f.reloads(), 0);
  assert.match(f.alerts[0], /reconciliation/);
  assert.equal(f.elements.postNowBtn.innerText, 'SHARE NOW');
  assert.equal(f.elements.postNowBtn.disabled, false);
});

test('Save Changes also blocks duplicate requests and recovers from failure', async () => {
  let release;
  const gate = new Promise(resolve => {release = resolve;});
  const f = fixture(async () => {await gate; return response(false, 'Cannot edit');});
  const first = f.context.window.savePostEdit();
  await f.context.window.savePostEdit();
  await f.context.window.publishPostNow();
  assert.equal(f.calls.length, 1);
  release(); await first;
  assert.equal(f.elements.savePostBtn.disabled, false);
  assert.equal(f.reloads(), 0);
});

test('Calendar uses the browser timezone, preserves other query values, and does not loop', () => {
  const replacements = [];
  const location = {pathname: '/app/calendar', href: 'https://example.test/app/calendar?view=month', replace: url => replacements.push(url)};
  const context = {window: {location}, URL, Intl: {DateTimeFormat: () => ({resolvedOptions: () => ({timeZone: 'America/Detroit'})})}};
  vm.runInNewContext(calendar, context);
  assert.equal(context.window.syncCalendarTimezone(), true);
  const result = new URL(replacements[0]);
  assert.equal(result.searchParams.get('tz'), 'America/Detroit');
  assert.equal(result.searchParams.get('view'), 'month');
  location.href = replacements[0];
  assert.equal(context.window.syncCalendarTimezone(), false);
  location.pathname = '/app';
  assert.equal(context.window.syncCalendarTimezone(), false);
});
