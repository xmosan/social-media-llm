from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["admin"])

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Social Media LLM Admin</title>
  <style>
    body { font-family: -apple-system, system-ui, Segoe UI, Roboto, Arial; margin: 24px; }
    h1 { margin: 0 0 8px; }
    .row { display: flex; gap: 16px; flex-wrap: wrap; }
    .card { border: 1px solid #ddd; border-radius: 10px; padding: 14px; max-width: 520px; flex: 1; min-width: 320px; }
    input, textarea, select, button { font: inherit; }
    textarea { width: 100%; min-height: 90px; }
    input[type="file"] { width: 100%; }
    button { padding: 8px 12px; border-radius: 8px; border: 1px solid #ccc; background: #fff; cursor: pointer; }
    button.primary { background: #111; color: #fff; border-color: #111; }
    button.danger { background: #b00020; color: #fff; border-color: #b00020; }
    .muted { color: #666; font-size: 0.92em; }
    .pill { display:inline-block; padding: 2px 8px; border:1px solid #ddd; border-radius: 999px; font-size: 0.85em; }
    .list { display: grid; gap: 10px; }
    .post { border: 1px solid #eee; border-radius: 10px; padding: 12px; }
    .post h3 { margin: 0 0 6px; font-size: 1.05em; }
    .post pre { white-space: pre-wrap; word-break: break-word; background: #fafafa; padding: 10px; border-radius: 8px; border: 1px solid #eee; }
    .actions { display:flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
    .topbar { display:flex; gap: 12px; align-items: center; flex-wrap: wrap; margin: 12px 0 8px; }
    .right { margin-left:auto; }
    .ok { color: #0a7; }
    .err { color: #c00; white-space: pre-wrap; }
    .img { max-width: 100%; border-radius: 10px; border: 1px solid #eee; }
  </style>
</head>
<body>
  <h1>Social Media LLM — Admin</h1>
  <div class="muted">Upload → Generate → Approve (schedule) → Daily scheduler posts automatically.</div>

  <div class="row" style="margin-top:16px;">
    <div class="card">
      <h2 style="margin-top:0;">1) Upload new post</h2>
      <div class="muted">Image + short source text. (You can paste a reminder/quote/topic.)</div>
      <div style="height:10px;"></div>
      <label>Source text</label>
      <textarea id="source_text" placeholder="Example: Reminder about صلاة / a short Islamic reminder..."></textarea>
      <div style="height:10px;"></div>
      <label>Image</label>
      <input id="image" type="file" accept="image/png,image/jpeg,image/webp" />
      <div style="height:12px;"></div>
      <button class="primary" onclick="uploadPost()">Upload</button>
      <span id="upload_msg" class="muted"></span>
    </div>

    <div class="card">
      <h2 style="margin-top:0;">2) Queue & Stats</h2>
      <div class="topbar">
        <label>Status:</label>
        <select id="status_filter" onchange="refreshAll()">
          <option value="">All</option>
          <option value="submitted">submitted</option>
          <option value="drafted">drafted</option>
          <option value="needs_review">needs_review</option>
          <option value="scheduled">scheduled</option>
          <option value="published">published</option>
          <option value="failed">failed</option>
        </select>

        <label>Limit:</label>
        <select id="limit" onchange="refreshAll()">
          <option>10</option>
          <option selected>25</option>
          <option>50</option>
          <option>100</option>
        </select>

        <button class="right" onclick="refreshAll()">Refresh</button>
      </div>

      <div id="stats" class="muted">Loading stats...</div>
      <div style="height:10px;"></div>

      <div id="error" class="err"></div>
      <div class="list" id="list"></div>
    </div>
  </div>

<script>
const API = ""; // same origin

function esc(s) {
  return (s ?? "").toString()
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function setError(msg) {
  document.getElementById("error").textContent = msg || "";
}

async function refreshAll() {
  setError("");
  await Promise.all([loadStats(), loadPosts()]);
}

async function loadStats() {
  const el = document.getElementById("stats");
  try {
    const r = await fetch(`${API}/posts/stats`);
    const j = await r.json();
    if (!r.ok) throw new Error(JSON.stringify(j));
    const counts = j.counts || {};
    const parts = Object.entries(counts).map(([k,v]) => `<span class="pill">${esc(k)}: <b>${v}</b></span>`);
    el.innerHTML = parts.length ? parts.join(" ") : "<span class='muted'>No posts yet.</span>";
  } catch (e) {
    el.textContent = "Stats error";
    setError("Stats failed: " + e);
  }
}

async function loadPosts() {
  const list = document.getElementById("list");
  list.innerHTML = "<div class='muted'>Loading…</div>";
  try {
    const status = document.getElementById("status_filter").value;
    const limit = document.getElementById("limit").value;
    const qs = new URLSearchParams();
    if (status) qs.set("status", status);
    if (limit) qs.set("limit", limit);

    const r = await fetch(`${API}/posts?${qs.toString()}`);
    const j = await r.json();
    if (!r.ok) throw new Error(JSON.stringify(j));

    if (!Array.isArray(j) || j.length === 0) {
      list.innerHTML = "<div class='muted'>No posts in this view.</div>";
      return;
    }

    list.innerHTML = j.map(p => renderPost(p)).join("");
  } catch (e) {
    list.innerHTML = "";
    setError("Load posts failed: " + e);
  }
}

function renderPost(p) {
  const caption = p.caption ? `<pre>${esc(p.caption)}${p.hashtags?.length ? "\\n\\n" + esc(p.hashtags.join(" ")) : ""}</pre>` : `<div class="muted">No caption yet. Click Generate.</div>`;
  const img = p.media_url ? `<a href="${esc(p.media_url)}" target="_blank"><img class="img" src="${esc(p.media_url)}" alt="media"/></a>` : "";
  const flags = p.flags ? `<div class="muted">flags: ${esc(JSON.stringify(p.flags))}</div>` : "";

  return `
    <div class="post" id="post-${p.id}">
      <h3>#${p.id} <span class="pill">${esc(p.status)}</span></h3>
      <div class="muted">${esc(p.created_at || "")}</div>
      <div style="height:8px;"></div>
      <div><b>Source:</b> ${esc(p.source_text || "")}</div>
      <div style="height:8px;"></div>
      ${img}
      <div style="height:8px;"></div>
      ${caption}
      ${flags}
      <div class="actions">
        <button onclick="generate(${p.id})">Generate</button>
        <button class="primary" onclick="approve(${p.id})">Approve (schedule)</button>
        <button onclick="view(${p.id})">Reload</button>
      </div>
      <div class="muted" id="msg-${p.id}"></div>
    </div>
  `;
}

function setMsg(id, msg, ok=true) {
  const el = document.getElementById(`msg-${id}`);
  if (!el) return;
  el.className = ok ? "muted ok" : "muted err";
  el.textContent = msg;
}

async function uploadPost() {
  setError("");
  const msg = document.getElementById("upload_msg");
  msg.textContent = "Uploading…";

  const sourceText = document.getElementById("source_text").value || "";
  const file = document.getElementById("image").files[0];
  if (!file) {
    msg.textContent = "";
    setError("Please choose an image file.");
    return;
  }

  const fd = new FormData();
  fd.append("source_text", sourceText);
  fd.append("image", file);

  try {
    const r = await fetch(`${API}/posts/intake`, { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(JSON.stringify(j));
    msg.textContent = `Uploaded! Post ID = ${j.id}`;
    document.getElementById("source_text").value = "";
    document.getElementById("image").value = "";
    await refreshAll();
  } catch (e) {
    msg.textContent = "";
    setError("Upload failed: " + e);
  }
}

async function generate(id) {
  setMsg(id, "Generating…");
  try {
    const r = await fetch(`${API}/posts/${id}/generate`, { method: "POST" });
    const j = await r.json();
    if (!r.ok) throw new Error(JSON.stringify(j));
    setMsg(id, "Generated ✓");
    await refreshAll();
  } catch (e) {
    setMsg(id, "Generate failed: " + e, false);
  }
}

async function approve(id) {
  setMsg(id, "Approving…");
  try {
    const r = await fetch(`${API}/posts/${id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approve_anyway: true })
    });
    const j = await r.json();
    if (!r.ok) throw new Error(JSON.stringify(j));
    setMsg(id, "Approved ✓ (scheduled)");
    await refreshAll();
  } catch (e) {
    setMsg(id, "Approve failed: " + e, false);
  }
}

async function view(id) {
  setMsg(id, "Reloading…");
  try {
    const r = await fetch(`${API}/posts/${id}`);
    const j = await r.json();
    if (!r.ok) throw new Error(JSON.stringify(j));
    setMsg(id, "Loaded ✓");
    await refreshAll();
  } catch (e) {
    setMsg(id, "Reload failed: " + e, false);
  }
}

refreshAll();
</script>
</body>
</html>
"""

@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return HTML
    