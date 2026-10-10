const test = require("node:test"),
  assert = require("node:assert/strict"),
  fs = require("node:fs"),
  vm = require("node:vm");
const code = fs.readFileSync(
  require("node:path").join(__dirname, "../../app/static/owner-dashboard.js"),
  "utf8",
);
function element(tag = "div") {
  return {
    tag,
    children: [],
    listeners: {},
    attributes: {},
    disabled: false,
    hidden: false,
    value: "",
    textContent: "",
    dataset: {},
    append(...v) {
      this.children.push(...v);
    },
    replaceChildren(...v) {
      this.children = v;
    },
    addEventListener(k, fn) {
      this.listeners[k] = fn;
    },
    setAttribute(k, v) {
      this.attributes[k] = v;
    },
    removeAttribute(k) {
      delete this.attributes[k];
    },
    focus() {},
    showModal() {
      this.open = true;
    },
  };
}
const keys = [
  "overview",
  "creators",
  "publishing",
  "inbox",
  "waitlist",
  "system",
];
function setup(fetch, hash = "#overview", timers = {}) {
  const nodes = {},
    get = (id) => (nodes[id] ??= element());
  for (const k of keys) {
    get(k + "-data");
    get("panel-" + k);
  }
  get("message-filter").value = "received";
  get("session-error").hidden = true;
  const nav = keys.map((k) => {
    const e = element("a");
    e.dataset.panel = k;
    return e;
  });
  const listeners = {};
  const window = {
    location: { hash, reload() {} },
    addEventListener: (k, v) => (listeners[k] = v),
  };
  const context = {
    document: {
      getElementById: get,
      createElement: element,
      querySelectorAll: (q) =>
        q === "[data-panel]" ? nav : [get("refresh"), get("backup")],
    },
    window,
    fetch,
    AbortController,
    Date,
    TypeError,
    setTimeout: timers.setTimeout || setTimeout,
    clearTimeout: timers.clearTimeout || clearTimeout,
  };
  vm.runInNewContext(code, context);
  return {
    nodes,
    get,
    window,
    nav,
    async go(panel) {
      window.location.hash = "#" + panel;
      listeners.hashchange();
      await settle();
    },
  };
}
const settle = () => new Promise((r) => setImmediate(r));
const ok = (d) => ({ ok: true, status: 200, json: async () => d });
const overview = {
  signup_enabled: false,
  creators: 2,
  posts: { scheduled: 3, published: 4, failed: 0, publish_unknown: 1 },
  inbox: { feedback: 1, support_pending: 2 },
  pilot: { pending: 1, active: 1 },
  automations: 1,
  orgs: 2,
  owner: { email: "owner@fixture.test" },
};
function flatten(n) {
  return [n, ...n.children.flatMap(flatten)];
}
function text(n) {
  return flatten(n)
    .map((e) => e.textContent)
    .join(" ");
}
const emptyFetch = async (path) =>
  ok(
    path.endsWith("/overview")
      ? overview
      : path === "/admin/users"
        ? []
        : path.includes("/waitlist/")
          ? { count: 0, items: [] }
          : { items: [] },
  );
test("loads only the requested section, with no automatic writes or health claims", async () => {
  const calls = [];
  const s = setup(async (...args) => {
    calls.push(args);
    return emptyFetch(...args);
  });
  await settle();
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "/api/admin/overview");
  assert.equal(calls[0][1].method, undefined);
  assert.match(text(s.get("overview-data")), /1 attempts need reconciliation/);
  await s.go("creators");
  assert.equal(calls.length, 3);
  assert.equal(s.get("panel-overview").hidden, true);
  assert.equal(s.get("panel-creators").hidden, false);
  assert.match(text(s.get("creators-data")), /No creator accounts/);
});
test("a failed section offers retry and does not disable other sections", async () => {
  let fails = true;
  const s = setup(async (p) =>
    p.endsWith("/overview") && fails
      ? { ok: false, status: 500 }
      : emptyFetch(p),
  );
  await settle();
  assert.match(text(s.get("overview-data")), /could not be loaded/);
  fails = false;
  await flatten(s.get("overview-data"))
    .find((n) => n.tag === "button")
    .listeners.click();
  assert.match(text(s.get("overview-data")), /Creator accounts/);
  await s.go("inbox");
  assert.match(text(s.get("inbox-data")), /No messages/);
});
test("session expiration clears loaded private data and prevents further reads", async () => {
  let calls = 0;
  const s = setup(async (p) => {
    calls++;
    return p.endsWith("/overview") ? ok(overview) : { ok: false, status: 401 };
  });
  await settle();
  await s.go("creators");
  assert.equal(s.get("overview-data").children.length, 0);
  assert.equal(s.get("session-error").hidden, false);
  await s.go("waitlist");
  assert.equal(calls, 3);
});
test("legacy admin denial is handled as an owner access error", async () => {
  const s = setup(async () => ({
    ok: false,
    status: 403,
    json: async () => ({
      detail: "This area is available only to the Sabeel owner.",
    }),
  }));
  await settle();
  assert.equal(s.get("session-error").hidden, false);
  assert.equal(s.get("refresh").disabled, true);
});
test("support text is rendered as text; duplicate status writes are locked", async () => {
  let resolveWrite,
    writes = 0;
  const s = setup(async (p, o) => {
    if (o.method) {
      writes++;
      return new Promise((r) => (resolveWrite = r));
    }
    return ok({
      items: [
        {
          id: 7,
          subject: "<img src=x onerror=alert(1)>",
          message: "<script>fixture</script>",
          email: "fixture@test",
          status: "received",
        },
      ],
    });
  }, "#inbox");
  await settle();
  const root = s.get("inbox-data");
  assert.match(text(root), /<script>fixture/);
  assert.ok(flatten(root).every((n) => !("innerHTML" in n)));
  const b = flatten(root).find((n) => n.textContent === "Mark resolved");
  const pending = b.listeners.click();
  await b.listeners.click();
  assert.equal(writes, 1);
  assert.equal(b.disabled, true);
  resolveWrite(ok({ ok: true }));
  await pending;
  assert.match(s.get("notice").textContent, /No email was sent/);
});
test("cancelling a resume confirmation makes no request and restores the button", async () => {
  const calls = [];
  const s = setup(async (p, o) => {
    calls.push([p, o]);
    return ok({
      items: p.includes("automations")
        ? [
            {
              id: 1,
              name: "Fixture",
              org_name: "Synthetic",
              enabled: false,
              ig_username: "test",
            },
          ]
        : [],
    });
  }, "#publishing");
  await settle();
  const b = flatten(s.get("publishing-data")).find(
    (n) => n.textContent === "Resume",
  );
  const pending = b.listeners.click();
  assert.equal(s.get("confirmation").open, true);
  assert.equal(b.disabled, true);
  s.get("confirmation").returnValue = "cancel";
  s.get("confirmation").listeners.close();
  await pending;
  assert.equal(b.disabled, false);
  assert.equal(calls.length, 2);
});
test("unknown publication warns about duplicates and offers no retry button", async () => {
  const s = setup(
    async (p) =>
      ok({
        items: p.includes("failed-posts")
          ? [{ id: 12, org_id: 2, status: "publish_unknown" }]
          : [],
      }),
    "#publishing",
  );
  await settle();
  assert.match(
    text(s.get("publishing-data")),
    /second attempt could duplicate/,
  );
  assert.equal(
    flatten(s.get("publishing-data")).filter((n) => n.tag === "button").length,
    0,
  );
});
test("waitlist supports search and pagination without granting app access", async () => {
  const paths = [];
  const s = setup(async (p) => {
    paths.push(p);
    return ok({
      count: 40,
      items: Array.from({ length: 25 }, (_, i) => ({
        id: i,
        email: "fixture@test",
      })),
    });
  }, "#waitlist");
  await settle();
  assert.equal(s.get("waitlist-next").disabled, false);
  s.get("waitlist-next").listeners.click();
  await settle();
  assert.match(paths[1], /offset=25/);
  s.get("waitlist-query").value = "one+two@test";
  s.get("waitlist-search").listeners.submit({ preventDefault() {} });
  await settle();
  assert.match(paths[2], /offset=0/);
  assert.match(paths[2], /one%2Btwo%40test/);
});
test("read timeout ends loading and offers retry", async () => {
  let timeout;
  const s = setup(
    async (p, o) =>
      new Promise((resolve, reject) =>
        o.signal.addEventListener("abort", () =>
          reject(Object.assign(new Error(), { name: "AbortError" })),
        ),
      ),
    "#overview",
    { setTimeout: (fn) => ((timeout = fn), 1), clearTimeout() {} },
  );
  timeout();
  await settle();
  assert.match(text(s.get("overview-data")), /taking too long/);
  assert.equal(s.get("overview-data").attributes["aria-busy"], undefined);
});
test("older refresh cannot overwrite a newer successful response", async () => {
  let finish,
    calls = 0;
  const s = setup(async () =>
    ++calls === 1
      ? new Promise((r) => (finish = r))
      : ok({ ...overview, creators: 17 }),
  );
  await s.get("refresh").listeners.click();
  finish(ok({ ...overview, creators: 99 }));
  await settle();
  assert.match(text(s.get("overview-data")), /17/);
  assert.doesNotMatch(text(s.get("overview-data")), /99/);
});
test("waitlist editing saves separate status and notes once, then reloads persisted values", async () => {
  let entry = {
      id: 1,
      email: "fixture@test",
      status: "active",
      admin_notes: "",
    },
    writes = 0,
    finish;
  const s = setup(async (p, o) => {
    if (o.method) {
      writes++;
      entry = { ...entry, ...JSON.parse(o.body) };
      return new Promise((r) => (finish = r));
    }
    return ok({ count: 1, items: [entry] });
  }, "#waitlist");
  await settle();
  const all = flatten(s.get("waitlist-data"));
  all.find((n) => n.tag === "textarea").value = "Private fixture note";
  all.find((n) => n.tag === "select").value = "contacted";
  const b = all.find((n) => n.textContent === "Save entry");
  const pending = b.listeners.click();
  await b.listeners.click();
  assert.equal(writes, 1);
  finish(ok({ ok: true }));
  await pending;
  assert.equal(
    flatten(s.get("waitlist-data")).find((n) => n.tag === "textarea").value,
    "Private fixture note",
  );
  assert.match(s.get("notice").textContent, /No invitation or email was sent/);
});
