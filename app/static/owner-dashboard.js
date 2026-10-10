/* Private owner console. Sections load independently; opening a page never writes. */
(() => {
  "use strict";
  const labels = {
    overview: ["Overview", "A clear view of your creator pilot."],
    creators: ["Creators", "People using Sabeel and their workspaces."],
    publishing: ["Publishing", "Automation and posts that need attention."],
    inbox: ["Inbox", "Listen, follow up, and close the loop."],
    waitlist: ["Waitlist", "People interested in joining Sabeel."],
    system: ["System", "App checks, connections, and recovery."],
  };
  const $ = (id) => document.getElementById(id);
  const state = {
    panel: "overview",
    users: [],
    accounts: [],
    offset: 0,
    query: "",
    expired: false,
    versions: {},
  };
  function el(tag, text, cls) {
    const n = document.createElement(tag);
    if (text != null) n.textContent = String(text);
    if (cls) n.className = cls;
    return n;
  }
  function date(v) {
    const d = new Date(v);
    return !v || Number.isNaN(d.getTime())
      ? "Not recorded"
      : d.toLocaleString(undefined, {
          dateStyle: "medium",
          timeStyle: "short",
        });
  }
  function badge(text, tone = "") {
    return el("span", text, "badge " + tone);
  }
  function link(text, href) {
    const a = el("a", text, "text-link");
    a.href = href;
    return a;
  }
  function button(text, fn) {
    const b = el("button", text, "secondary");
    b.type = "button";
    b.addEventListener("click", () => fn(b));
    return b;
  }
  function card(title) {
    const n = el("div", null, "card");
    n.append(el("h2", title));
    return n;
  }
  function row(title, detail, status) {
    const n = el("div", null, "row"),
      top = el("div", null, "row-top");
    top.append(el("strong", title));
    if (status) top.append(status);
    n.append(top);
    if (detail) n.append(el("p", detail));
    return n;
  }
  function empty(text) {
    return el("p", text, "empty");
  }
  function details(title, text) {
    const n = el("details");
    n.append(el("summary", title), el("p", text));
    return n;
  }
  function expire() {
    state.expired = true;
    for (const key of Object.keys(labels)) {
      state.versions[key] = (state.versions[key] || 0) + 1;
      $(key + "-data").replaceChildren();
      $(key + "-data").removeAttribute("aria-busy");
    }
    $("session-error").hidden = false;
    document.querySelectorAll("main button").forEach((b) => {
      b.disabled = true;
    });
  }
  async function api(path, options = {}) {
    if (state.expired)
      throw new Error("Sign in with the owner account to continue.");
    const controller = new AbortController(),
      timer = setTimeout(() => controller.abort(), options.timeout || 15000);
    try {
      const res = await fetch(path, {
        credentials: "same-origin",
        cache: "no-store",
        ...options,
        signal: controller.signal,
        headers: {
          Accept: "application/json",
          ...(options.body ? { "Content-Type": "application/json" } : {}),
          ...options.headers,
        },
      });
      if (res.status === 401) {
        expire();
        throw new Error("Sign in with the owner account to continue.");
      }
      if (res.status === 403) {
        const denied = await res.json().catch(() => ({}));
        if (
          denied.detail === "This area is available only to the Sabeel owner."
        ) {
          expire();
          throw new Error("Sign in with the owner account to continue.");
        }
        throw new Error(
          "This action is unavailable. Check the workspace access, or reopen Sabeel and try again.",
        );
      }
      if (res.status === 422 && path.startsWith("/api/admin/automations/"))
        throw new Error(
          "This automation could not be changed. Check its Instagram account and schedule in the creator workspace.",
        );
      if (!res.ok)
        throw new Error(
          options.method
            ? "The change could not be confirmed. Refresh this section before trying again."
            : "This section could not be loaded. Please try again.",
        );
      const d = await res.json();
      if (d.ok === false)
        throw new Error(
          "The request could not be completed. Please try again.",
        );
      return d;
    } catch (e) {
      if (e.name === "AbortError" || e instanceof TypeError)
        throw new Error(
          options.method
            ? "The result is not confirmed. Refresh before trying again; the request may still have completed."
            : "Sabeel is taking too long to respond. Check your connection and try again.",
        );
      throw e;
    } finally {
      clearTimeout(timer);
    }
  }
  function notice(text) {
    $("notice").textContent = text;
    $("notice").hidden = false;
  }
  function confirmAction(title, description, action) {
    $("confirm-title").textContent = title;
    $("confirm-description").textContent = description;
    $("confirm-button").textContent = action;
    const dialog = $("confirmation");
    dialog.returnValue = "";
    return new Promise((resolve) => {
      dialog.addEventListener(
        "close",
        () => resolve(dialog.returnValue === "confirm"),
        { once: true },
      );
      dialog.showModal();
    });
  }
  async function change(b, path, body, success, panel) {
    if (b.disabled) return;
    b.disabled = true;
    try {
      await api(path, { method: "PATCH", body: JSON.stringify(body) });
      notice(success);
      await load(panel);
    } catch (e) {
      notice(e.message);
    } finally {
      if (!state.expired) b.disabled = false;
    }
  }
  function metric(label, value, note) {
    const n = el("div", null, "metric");
    n.append(
      el("span", label, "label"),
      el("strong", Number(value || 0).toLocaleString()),
      el("small", note),
    );
    return n;
  }
  async function overview() {
    const d = await api("/api/admin/overview"),
      root = el("div"),
      metrics = el("div", null, "metrics");
    $("access-mode").textContent = d.signup_enabled
      ? "Public sign-up open"
      : "Invitation-only pilot";
    metrics.append(
      metric("Creator accounts", d.creators, "Excludes your owner account"),
      metric("Scheduled posts", d.posts.scheduled, "Saved with a publish time"),
      metric("Published posts", d.posts.published, "Recorded as published"),
      metric("Creator feedback", d.inbox.feedback, "Private pilot submissions"),
    );
    root.append(metrics);
    const columns = el("div", null, "grid-two"),
      next = card("Your next steps"),
      pulse = card("Publishing at a glance");
    next.append(
      row(
        "Welcome your testers",
        `${d.pilot.pending} pending invitations · ${d.pilot.active} active tester invitations`,
      ),
      link("Manage tester access →", "/admin/testers"),
      row(
        "Review what creators are telling you",
        `${d.inbox.support_pending} support messages waiting for a reply`,
      ),
      link("Open the inbox →", "#inbox"),
    );
    pulse.append(
      row(
        "Automations",
        `${d.automations} configured across ${d.orgs} workspaces`,
      ),
      row(
        "Failed posts",
        `${d.posts.failed} recorded failures`,
        badge(
          d.posts.failed ? "Review" : "None",
          d.posts.failed ? "warn" : "good",
        ),
      ),
      row(
        "Unconfirmed publishing",
        `${d.posts.publish_unknown} attempts need reconciliation`,
        badge(
          d.posts.publish_unknown ? "Check before retrying" : "None",
          d.posts.publish_unknown ? "warn" : "good",
        ),
      ),
      link("Review publishing →", "#publishing"),
    );
    columns.append(next, pulse);
    root.append(
      columns,
      el(
        "p",
        `Signed in as ${d.owner.email}. This console is restricted to your configured owner account.`,
        "muted",
      ),
    );
    return root;
  }
  function creatorList() {
    const q = $("creator-search").value.trim().toLocaleLowerCase(),
      users = state.users.filter((u) =>
        [u.name, u.email, u.orgs].some((v) =>
          String(v || "")
            .toLocaleLowerCase()
            .includes(q),
        ),
      ),
      root = card(
        `${users.length} ${users.length === 1 ? "account" : "accounts"}`,
      );
    if (!users.length)
      root.append(
        empty(
          q
            ? "No matching creators. Try another name or email."
            : "No creator accounts yet. Start by inviting a tester.",
        ),
      );
    for (const u of users) {
      const r = row(
        u.name || u.email,
        u.email,
        badge(
          u.is_superadmin
            ? "Owner account"
            : u.can_sign_in === false
              ? "Access ended"
              : u.is_active
                ? "Active"
                : "Inactive",
          u.can_sign_in !== false && u.is_active ? "good" : "",
        ),
      );
      r.append(
        el("p", u.orgs || "No workspace membership", "detail"),
        el("p", "Joined " + date(u.created_at), "detail"),
      );
      root.append(r);
    }
    const accounts = state.accounts.filter((a) =>
      [a.username, a.name, a.org_name].some((v) =>
        String(v || "")
          .toLocaleLowerCase()
          .includes(q),
      ),
    );
    const connections = card("Instagram accounts");
    connections.append(
      el(
        "p",
        "Saved connection records. A live connection is validated again before publishing.",
        "muted",
      ),
    );
    if (!accounts.length)
      connections.append(
        empty(
          q
            ? "No matching Instagram accounts."
            : "No Instagram accounts linked yet.",
        ),
      );
    for (const a of accounts)
      connections.append(
        row(
          a.username ? "@" + a.username : a.name || "Instagram account",
          a.org_name,
          badge(a.active ? "Enabled" : "Disabled", a.active ? "" : "warn"),
        ),
      );
    const result = el("div");
    result.append(root, connections);
    return result;
  }
  async function creators() {
    const version = state.versions.creators;
    const [users, accounts] = await Promise.all([
      api("/admin/users"),
      api("/api/admin/ig-accounts"),
    ]);
    if (version !== state.versions.creators || state.expired) return el("div");
    state.users = users;
    state.accounts = accounts.items;
    return creatorList();
  }
  async function publishing() {
    const [plans, failures] = await Promise.all([
        api("/api/admin/automations"),
        api("/api/admin/failed-posts?limit=20"),
      ]),
      root = el("div"),
      issues = card("Posts needing attention");
    if (!failures.items.length)
      issues.append(empty("No failed or unconfirmed posts."));
    for (const p of failures.items) {
      const unknown = p.status === "publish_unknown",
        r = row(
          p.topic || `Post #${p.id}`,
          `Workspace ${p.org_id} · ${date(p.created_at)}`,
          badge(
            unknown ? "Publishing unconfirmed" : "Failed",
            unknown ? "warn" : "bad",
          ),
        );
      r.append(
        el(
          "p",
          unknown
            ? "Confirm the result on Instagram before retrying. A second attempt could duplicate the post."
            : "Review this post in its workspace before retrying.",
          "detail",
        ),
        details(
          "View recorded error",
          p.error || "No error detail was recorded for this older post.",
        ),
      );
      issues.append(r);
    }
    if (failures.items.length === 20)
      issues.append(
        el("p", "Showing the 20 most recent posts needing attention.", "muted"),
      );
    const autos = card("Automations");
    if (!plans.items.length)
      autos.append(empty("No automations have been created."));
    for (const a of plans.items) {
      const r = row(
        a.name || `Automation #${a.id}`,
        `${a.org_name} · ${a.ig_username === "Not Linked" ? "No Instagram account linked" : a.ig_username ? "@" + a.ig_username : "Instagram username unavailable"}`,
        badge(a.enabled ? "Enabled" : "Paused", a.enabled ? "good" : ""),
      );
      r.append(el("p", "Last run: " + date(a.last_run), "detail"));
      if (a.last_error) r.append(details("View last error", a.last_error));
      const actions = el("div", null, "row-actions");
      actions.append(
        button(a.enabled ? "Pause" : "Resume", async (b) => {
          if (b.disabled) return;
          b.disabled = true;
          const action = a.enabled ? "Pause" : "Resume",
            confirmed = await confirmAction(
              `${action} this automation?`,
              `${a.name || "This automation"} belongs to ${a.org_name}. ${a.enabled ? "Future runs will stop. Already scheduled posts are unchanged." : "Future runs will follow its saved schedule and approval settings."}`,
              action,
            );
          b.disabled = false;
          b.focus();
          if (!confirmed || state.expired) return;
          await change(
            b,
            `/api/admin/automations/${a.id}`,
            { enabled: !a.enabled },
            `Automation ${a.enabled ? "paused" : "resumed"}.`,
            "publishing",
          );
        }),
      );
      r.append(actions);
      autos.append(r);
    }
    root.append(issues, autos);
    return root;
  }
  async function inbox() {
    const d = await api(
        "/api/admin/messages?limit=50" +
          ($("message-filter").value
            ? "&status=" + encodeURIComponent($("message-filter").value)
            : ""),
      ),
      root = card("Support inbox");
    if (!d.items.length) root.append(empty("No messages in this view."));
    for (const m of d.items) {
      const r = row(
          m.subject || "Support message",
          `${m.name || m.email} · ${date(m.created_at)}`,
          badge(m.status === "received" ? "Needs a reply" : m.status),
        ),
        body = details("Read message", m.message || "No message body."),
        actions = el("div", null, "row-actions");
      body.append(el("p", "From: " + m.email));
      if (m.status !== "resolved")
        actions.append(
          button("Mark resolved", (b) =>
            change(
              b,
              `/api/admin/messages/${m.id}`,
              { status: "resolved" },
              "Message marked resolved. No email was sent.",
              "inbox",
            ),
          ),
        );
      if (m.status !== "received")
        actions.append(
          button("Reopen", (b) =>
            change(
              b,
              `/api/admin/messages/${m.id}`,
              { status: "received" },
              "Message reopened.",
              "inbox",
            ),
          ),
        );
      if (m.status !== "archived")
        actions.append(
          button("Archive", (b) =>
            change(
              b,
              `/api/admin/messages/${m.id}`,
              { status: "archived" },
              "Message archived. It remains in the archived view.",
              "inbox",
            ),
          ),
        );
      body.append(actions);
      r.append(body);
      root.append(r);
    }
    if (d.items.length === 50)
      root.append(
        el("p", "Showing the 50 most recent messages in this view.", "muted"),
      );
    return root;
  }
  async function waitlist() {
    const version = state.versions.waitlist;
    const d = await api(
      `/api/waitlist/all?limit=25&offset=${state.offset}&q=${encodeURIComponent(state.query)}`,
    );
    if (version !== state.versions.waitlist || state.expired) return el("div");
    $("waitlist-prev").disabled = state.offset === 0;
    $("waitlist-next").disabled = state.offset + d.items.length >= d.count;
    $("waitlist-range").textContent = d.count
      ? `${state.offset + 1}–${state.offset + d.items.length} of ${d.count}`
      : "0 people";
    const root = card("Interested creators");
    if (!d.items.length) root.append(empty("No people match this search."));
    for (const w of d.items) {
      const r = row(w.name || w.email, w.email, badge(w.status || "New"));
      r.append(
        el(
          "p",
          `Joined ${date(w.created_at)} · ${w.wants_updates ? "Requested updates" : "No update consent"}`,
          "detail",
        ),
      );
      const edit = el("details");
      edit.append(el("summary", "Manage entry"));
      const statusLabel = el("label", "Status"),
        status = el("select");
      status.id = "waitlist-status-" + w.id;
      statusLabel.htmlFor = status.id;
      const states = {
        active: "New",
        contacted: "Contacted",
        invited: "Invited",
        converted: "Joined",
        archived: "Archived",
      };
      if (w.status && !Object.hasOwn(states, w.status))
        states[w.status] = w.status;
      for (const [value, label] of Object.entries(states)) {
        const option = el("option", label);
        option.value = value;
        status.append(option);
      }
      status.value = w.status || "active";
      const notesLabel = el("label", "Private notes"),
        notes = el("textarea");
      notes.id = "waitlist-notes-" + w.id;
      notesLabel.htmlFor = notes.id;
      notes.value = w.admin_notes || "";
      notes.maxLength = 4000;
      notes.rows = 3;
      edit.append(
        statusLabel,
        status,
        notesLabel,
        notes,
        el(
          "p",
          "This updates your records only. It does not send an invitation or email.",
          "muted",
        ),
        button("Save entry", (b) =>
          change(
            b,
            `/api/waitlist/${w.id}`,
            { status: status.value, admin_notes: notes.value },
            "Waitlist entry saved. No invitation or email was sent.",
            "waitlist",
          ),
        ),
      );
      r.append(edit);
      root.append(r);
    }
    return root;
  }
  async function system() {
    const d = await api("/api/admin/diagnostics"),
      root = el("div", null, "grid-two"),
      runtime = card("Live app checks"),
      connections = card("Connection settings");
    runtime.append(
      row(
        "Database",
        "A read query completed just now.",
        badge("Connected", "good"),
      ),
      row(
        "Scheduler",
        `${d.scheduler.active_jobs} registered jobs. Running does not guarantee that individual posts will publish.`,
        badge(
          d.scheduler.status,
          d.scheduler.status === "running" ? "good" : "warn",
        ),
      ),
      row(
        "Creator registration",
        d.signup_enabled
          ? "Anyone can create an account."
          : "New creators need an invitation.",
        badge(d.signup_enabled ? "Open" : "Invitation only"),
      ),
      row("Owner access", d.owner_email, badge("Restricted", "good")),
    );
    for (const [name, detail, configured] of [
      ["Sabeel Vision", "OpenAI credentials", d.environment.openai_configured],
      [
        "Instagram",
        "Meta app credentials; individual accounts still need a valid connection",
        d.environment.instagram_configured,
      ],
      [
        "Operational logging",
        "Axiom credentials; alert delivery is verified separately",
        d.environment.logging_configured,
      ],
      [
        "Portable backup storage",
        "S3 credentials; backup freshness and restoration are verified separately",
        d.environment.backup_configured,
      ],
    ])
      connections.append(
        row(
          name,
          detail,
          badge(
            configured ? "Configured" : "Missing configuration",
            configured ? "" : "warn",
          ),
        ),
      );
    root.append(runtime, connections);
    return root;
  }
  const loaders = { overview, creators, publishing, inbox, waitlist, system };
  async function load(panel) {
    if (state.expired) return;
    const version = (state.versions[panel] = (state.versions[panel] || 0) + 1),
      target = $(panel + "-data");
    target.setAttribute("aria-busy", "true");
    target.replaceChildren(
      el("p", "Loading " + labels[panel][0].toLowerCase() + "…", "loading"),
    );
    if (panel === "waitlist") {
      $("waitlist-prev").disabled = true;
      $("waitlist-next").disabled = true;
    }
    try {
      const result = await loaders[panel]();
      if (version !== state.versions[panel] || state.expired) return;
      target.replaceChildren(result);
      $("updated").textContent =
        "Last loaded " +
        new Date().toLocaleTimeString(undefined, {
          hour: "numeric",
          minute: "2-digit",
        });
    } catch (e) {
      if (version !== state.versions[panel] || state.expired) return;
      const box = el("div", null, "error");
      box.setAttribute("role", "alert");
      box.append(
        el("p", e.message),
        button("Try again", () => load(panel)),
      );
      target.replaceChildren(box);
    } finally {
      if (version === state.versions[panel])
        target.removeAttribute("aria-busy");
    }
  }
  function navigate(focus = false) {
    const requested = window.location.hash.slice(1);
    state.panel = Object.hasOwn(labels, requested) ? requested : "overview";
    for (const k of Object.keys(labels))
      $("panel-" + k).hidden = k !== state.panel;
    document.querySelectorAll("[data-panel]").forEach((a) => {
      if (a.dataset.panel === state.panel)
        a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    $("page-title").textContent = labels[state.panel][0];
    $("page-description").textContent = labels[state.panel][1];
    $("notice").hidden = true;
    if (focus) $("main").focus({ preventScroll: false });
    load(state.panel);
  }
  $("refresh").addEventListener("click", () => load(state.panel));
  $("creator-search").addEventListener("input", () => {
    if (!state.expired && state.users.length)
      $("creators-data").replaceChildren(creatorList());
  });
  $("message-filter").addEventListener("change", () => load("inbox"));
  $("waitlist-search").addEventListener("submit", (e) => {
    e.preventDefault();
    state.query = $("waitlist-query").value.trim();
    state.offset = 0;
    load("waitlist");
  });
  for (const [id, delta] of [
    ["waitlist-prev", -1],
    ["waitlist-next", 1],
  ])
    $(id).addEventListener("click", () => {
      state.offset = Math.max(0, state.offset + 25 * delta);
      load("waitlist");
    });
  $("backup").addEventListener("click", async () => {
    const b = $("backup");
    if (b.disabled) return;
    b.disabled = true;
    if (
      !(await confirmAction(
        "Create a portable backup?",
        "This creates a new database backup in the configured storage. It does not replace a restore test or change creator data.",
        "Create backup",
      ))
    ) {
      b.disabled = false;
      b.focus();
      return;
    }
    $("backup-result").textContent =
      "Creating the backup. This can take a minute…";
    try {
      const d = await api("/admin/backup-now", {
        method: "POST",
        timeout: 90000,
      });
      $("backup-result").textContent =
        d.status === "success"
          ? "Backup created. Recovery still needs an isolated restore test."
          : "Backup creation was not confirmed. Check the storage before retrying.";
    } catch (e) {
      $("backup-result").textContent = e.message;
    } finally {
      if (!state.expired) b.disabled = false;
    }
  });
  window.addEventListener("hashchange", () => navigate(true));
  window.addEventListener("pageshow", (e) => {
    if (e.persisted) window.location.reload();
  });
  navigate();
})();
