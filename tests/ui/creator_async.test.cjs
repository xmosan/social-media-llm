const test = require("node:test"),
  assert = require("node:assert/strict"),
  fs = require("node:fs"),
  vm = require("node:vm"),
  path = require("node:path");
const source = fs.readFileSync(
  path.join(__dirname, "../../app/routes/ui_assets.py"),
  "utf8",
);
function setup(fetch) {
  const nodes = {},
    alerts = [],
    suggestions = [];
  const el = (id) =>
    (nodes[id] ||= {
      value: "",
      textContent: "",
      disabled: false,
      children: [],
      classList: { add() {}, remove() {} },
      setAttribute(k, v) {
        this[k] = v;
      },
      append(...v) {
        this.children.push(...v);
      },
      replaceChildren() {
        this.children = [];
      },
      querySelector(s) {
        return el(id + s);
      },
    });
  el("studioTopic").value = "patience";
  el("studioCaption").value = "My caption";
  const c = {
    window: {
      studioSourceContext: { type: "quran", reference: "Fixture" },
      offerCreatorSuggestion: (...a) => suggestions.push(a),
      studioNotice: (m) => alerts.push(m),
    },
    document: {
      getElementById: el,
      createElement: (tag) => ({
        textContent: "",
        children: [],
        setAttribute(k, v) {
          this[k] = v;
        },
        append(...v) {
          this.children.push(...v);
        },
      }),
    },
    fetch,
    AbortController,
    AbortSignal,
    setTimeout,
    clearTimeout,
    console,
    alert: (m) => alerts.push(m),
    studioSourceEpoch: 1,
    studioSessionEpoch: 1,
    activeSourceTab: "quran",
    studioCardMessage: { headline: "Exact source" },
    studioCaptionMessage: null,
  };
  return { c, el, alerts, suggestions, run: (s) => vm.runInNewContext(s, c) };
}
const search = source.slice(
  source.indexOf("    // Latest-query-only"),
  source.indexOf(
    "    window.selectedAyahMetadata",
    source.indexOf("    // Latest-query-only"),
  ),
);
const caption = source.slice(
  source.indexOf("    window.generateSocialCaption ="),
  source.indexOf(
    "    function _renderCaptionPreview",
    source.indexOf("    window.generateSocialCaption ="),
  ),
);
const response = (data) => ({ ok: true, json: async () => data });
test("an older Quran query cannot replace newer results", async () => {
  let first;
  const f = setup(() => new Promise((r) => (first = r)));
  f.run(search);
  const old = f.c.window.searchQuran();
  f.el("studioTopic").value = "gratitude";
  f.c.fetch = async () =>
    response([{ id: 2, reference: "New", translation_text: "Exact new text" }]);
  await f.c.window.searchQuran();
  first(response([{ id: 1, reference: "Old" }]));
  await old;
  assert.equal(
    f.el("quranSearchResults").children[0].children[0].textContent,
    "New",
  );
});
test("closed or switched-source sessions discard a late Quran response", async () => {
  let finish;
  const f = setup(() => new Promise((r) => (finish = r)));
  f.run(search);
  const p = f.c.window.searchQuran();
  f.c.studioSessionEpoch++;
  f.c.activeSourceTab = "hadith";
  finish(response([{ id: 1, reference: "Old" }]));
  await p;
  assert.equal(f.el("quranSearchResults").children.length, 0);
});
test("Quran results render source text as text and retain metadata separately", async () => {
  const record = {
    id: 3,
    reference: "Fixture",
    translation_text: "<img src=x onerror=bad()>",
    arabic_text: "نص",
  };
  const f = setup(async () => response([record]));
  f.run(search);
  await f.c.window.searchQuran();
  const b = f.el("quranSearchResults").children[0];
  assert.equal(b.children[1].textContent, record.translation_text);
  assert.deepEqual(JSON.parse(b["data-meta"]), record);
});
test("caption generation is duplicate-protected and only offers a comparison", async () => {
  let finish,
    calls = 0;
  const f = setup(() => {
    calls++;
    return new Promise((r) => (finish = r));
  });
  f.run(caption);
  const p = f.c.window.generateSocialCaption();
  await f.c.window.generateSocialCaption();
  assert.equal(calls, 1);
  finish(response({ caption: "AI draft" }));
  await p;
  assert.equal(f.el("studioCaption").value, "My caption");
  assert.deepEqual(f.suggestions[0], ["caption", "My caption", "AI draft"]);
  assert.equal(f.el("btnGenerateCaption").disabled, false);
});
test("caption edits made during generation survive the response", async () => {
  let finish;
  const f = setup(() => new Promise((r) => (finish = r)));
  f.run(caption);
  const p = f.c.window.generateSocialCaption();
  f.el("studioCaption").value = "Newer manual edit";
  finish(response({ caption: "AI draft" }));
  await p;
  assert.equal(f.suggestions.length, 0);
  assert.equal(f.el("studioCaption").value, "Newer manual edit");
  assert.match(f.alerts[0], /edit was kept/);
});
test("caption failure restores the action and keeps writing; a late response cannot alter a new session", async () => {
  const f = setup(async () => ({
    ok: false,
    json: async () => ({ detail: "Unavailable" }),
  }));
  f.run(caption);
  await f.c.window.generateSocialCaption();
  assert.equal(f.el("btnGenerateCaption").disabled, false);
  assert.equal(f.el("studioCaption").value, "My caption");
  assert.equal(f.suggestions.length, 0);
  let finish;
  f.c.fetch = () => new Promise((r) => (finish = r));
  const p = f.c.window.generateSocialCaption();
  f.c.studioSessionEpoch++;
  finish(response({ caption: "Old result" }));
  await p;
  assert.equal(f.suggestions.length, 0);
});
