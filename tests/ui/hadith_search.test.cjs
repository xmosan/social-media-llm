const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../app/routes/ui_assets.py'), 'utf8');
const code = source.slice(source.indexOf('    // Hadith search is resumable'), source.indexOf('    // Legacy wrapper kept'));
function element() {
  return {children: [], attributes: {}, textContent: '', classList: {add() {}, remove() {}},
    append(...nodes) {this.children.push(...nodes);}, replaceChildren(...nodes) {this.children = nodes;},
    setAttribute(key, value) {this.attributes[key] = value;}, getAttribute(key) {return this.attributes[key];}};
}
function fixture(fetch) {
  const area = element(), topic = {value: 'intentions'}, collection = {value: 'bukhari'};
  let selected;
  const calls = [];
  const context = {console, AbortController, URLSearchParams, Set, setTimeout, clearTimeout,
    activeSourceTab: 'hadith', window: {_applyHadithSelection: x => {selected = x;}},
    document: {getElementById: id => ({studioTopic: topic, hadithSearchResults: area, hadithCollection: collection})[id], createElement: element},
    fetch: (...args) => {calls.push(args); return fetch(...args);}};
  vm.runInNewContext(code, context);
  return {area, topic, context, calls, selected: () => selected,
    search: more => context.window.searchHadith(more),
    reset: () => vm.runInNewContext('invalidateHadithSearch()', context)};
}
const response = data => ({ok: true, json: async () => data});
const record = {collection_key: 'bukhari', hadith_number: 9999, provider_page: 4,
  reference: 'Fixture <b>&quot;</b>', translation_text: 'Exact &quot; text (ﷺ) <script>fixture</script>', grade: null,
  provider_metadata: {returned: 'fixture'}};
const text = node => [node.textContent, ...node.children.map(text)].join(' ');

test('More search resumes cursor and preserves exact metadata without HTML interpretation', async () => {
  const f = fixture(async () => f.calls.length === 1 ? response({items: [], next_cursor: 'page4', pages_scanned: 3, complete: false}) :
    response({items: [record], next_cursor: null, pages_scanned: 1, complete: true}));
  await f.search();
  assert.match(text(f.area), /0 matches.*More narrations/);
  await f.area.children.at(-1).onclick();
  assert.match(f.calls[1][0], /cursor=page4/);
  assert.match(text(f.area), /Search complete/);
  const button = f.area.children[0];
  assert.equal(button.children[1].textContent, record.translation_text);
  button.onclick();
  assert.equal(f.selected().translation_text, record.translation_text);
  assert.equal(f.selected().provider_page, 4);
  assert.equal(f.selected().grade, null);
});

test('Network and HTTP failures end loading, expose retry, and keep previous cursor', async () => {
  let fail = false;
  const f = fixture(async () => {if (fail) throw Error('offline'); return response({items: [record], next_cursor: 'next', pages_scanned: 1});});
  await f.search(); fail = true;
  await f.search(true);
  assert.match(text(f.area), /offline.*Retry search/);
  assert.match(text(f.area), /Exact &quot;/);
  fail = false;
  await f.search(true);
  assert.match(f.calls[2][0], /cursor=next/);
  assert.equal(f.area.children.filter(n => n.attributes['data-meta']).length, 1);
  f.context.fetch = async () => ({ok: false, json: async () => ({detail: '<img onerror=fixture>'})});
  await f.search(true);
  assert.match(text(f.area), /<img onerror=fixture>.*Retry search/);
});

test('Out-of-order responses and closed sessions cannot replace the current search', async () => {
  let release;
  const f = fixture(async () => {if (f.calls.length === 1) return new Promise(resolve => release = resolve); return response({items: [record], complete: true});});
  const old = f.search();
  f.topic.value = 'new query';
  await f.search();
  release(response({items: [{...record, reference: 'STALE'}], complete: true}));
  await old;
  assert.doesNotMatch(text(f.area), /STALE/);
  f.context.fetch = async () => new Promise(resolve => release = resolve);
  const pending = f.search();
  f.reset(); f.context.activeSourceTab = 'quran';
  const before = text(f.area);
  release(response({items: [{...record, reference: 'CLOSED'}], complete: true}));
  await pending;
  assert.equal(text(f.area), before);
});

test('Repeated continuation clicks make only one request', async () => {
  let release;
  const f = fixture(async () => new Promise(resolve => release = resolve));
  const first = f.search();
  await f.search(true);
  assert.equal(f.calls.length, 1);
  release(response({items: [], complete: true})); await first;
});
