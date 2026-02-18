from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/admin", tags=["admin"])

HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Admin Dashboard | Social Media LLM</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; }
    .glass { background: rgba(255, 255, 255, 0.7); backdrop-filter: blur(10px); }
  </style>
</head>
<body class="bg-slate-50 text-slate-900 min-h-screen pb-12">
  <nav class="glass sticky top-0 z-50 border-b border-slate-200 bg-white/80 px-6 py-4 mb-8">
    <div class="max-w-7xl mx-auto flex justify-between items-center">
      <h1 class="text-xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
        Social Media <span class="text-slate-400 font-light">LLM</span> Admin
      </h1>
      <div class="flex items-center gap-4">
        <div id="api_key_status" class="text-xs font-medium px-2 py-1 rounded border border-slate-200 bg-slate-100 text-slate-500">
          API Key Required
        </div>
        <button onclick="toggleSettings()" class="text-slate-500 hover:text-slate-800 transition-colors">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </button>
      </div>
    </div>
  </nav>

  <main class="max-w-7xl mx-auto px-6 grid grid-cols-1 lg:grid-cols-12 gap-8">
    
    <!-- Settings Drawer (Hidden by default) -->
    <div id="settings_panel" class="hidden fixed inset-0 bg-black/20 z-[60] backdrop-blur-sm flex justify-end">
        <div class="w-full max-w-sm bg-white h-full shadow-2xl p-8 flex flex-col">
            <div class="flex justify-between items-center mb-6">
                <h2 class="text-xl font-bold">Admin Settings</h2>
                <button onclick="toggleSettings()" class="text-slate-400 hover:text-slate-600">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
            <div class="space-y-4">
                <div>
                    <label class="block text-sm font-medium text-slate-700 mb-1">X-API-Key</label>
                    <input type="password" id="admin_key_input" class="w-full px-4 py-2 rounded-lg border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="Enter API Key" />
                </div>
                <button onclick="saveApiKey()" class="w-full bg-slate-900 text-white rounded-lg py-3 font-medium hover:bg-slate-800 transition-colors">Save Key</button>
                <div id="save_msg" class="text-sm text-center"></div>
            </div>
        </div>
    </div>

    <!-- 1) Upload Section -->
    <div class="lg:col-span-4 space-y-6">
      <section class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
        <h2 class="text-lg font-bold mb-4 flex items-center gap-2">
          <span class="w-8 h-8 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center text-sm font-bold">1</span>
          Upload Content
        </h2>
        <div class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-slate-500 mb-1">Source Text</label>
            <textarea id="source_text" class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none text-sm min-h-[120px]" placeholder="Ideas, reminders, or topics for the LLM to process..."></textarea>
          </div>
          <div>
            <label class="block text-sm font-medium text-slate-500 mb-1">Image Asset</label>
            <div class="relative border-2 border-dashed border-slate-200 rounded-xl p-6 hover:border-indigo-400 transition-colors group">
                <input id="image" type="file" accept="image/png,image/jpeg,image/webp" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer" onchange="updateFileName(this)"/>
                <div class="text-center">
                    <svg xmlns="http://www.w3.org/2000/svg" class="mx-auto h-12 w-12 text-slate-400 group-hover:text-indigo-500 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    <div id="file_name_display" class="mt-2 text-xs font-medium text-slate-600">Click or drag image here</div>
                    <div class="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">PNG, JPG or WebP</div>
                </div>
            </div>
          </div>
          <button onclick="uploadPost()" class="w-full bg-indigo-600 text-white rounded-xl py-4 font-bold hover:bg-indigo-700 shadow-lg shadow-indigo-100 transition-all active:scale-[0.98]">
            Process and Intake
          </button>
          <div id="upload_msg" class="text-center text-sm font-medium"></div>
        </div>
      </section>

      <section class="bg-indigo-900 rounded-2xl p-6 text-white overflow-hidden relative">
          <div class="relative z-10">
              <h3 class="font-bold mb-2">Pro Tip</h3>
              <p class="text-indigo-200 text-sm leading-relaxed">Generated captions are checked against your custom content policy automatically.</p>
          </div>
          <div class="absolute -right-4 -bottom-4 opacity-10">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-24 w-24 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
          </div>
      </section>
    </div>

    <!-- 2) Queue Section -->
    <div class="lg:col-span-8 space-y-6">
      <section class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
            <h2 class="text-lg font-bold flex items-center gap-2">
                <span class="w-8 h-8 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center text-sm font-bold">2</span>
                Feed & Statitics
            </h2>
            <div class="flex gap-2">
                <select id="status_filter" onchange="refreshAll()" class="px-3 py-2 rounded-lg border border-slate-200 text-sm focus:ring-indigo-500 outline-none bg-slate-50 font-medium">
                    <option value="">All Statuses</option>
                    <option value="submitted">Submitted</option>
                    <option value="drafted">Drafted</option>
                    <option value="needs_review">Needs Review</option>
                    <option value="scheduled">Scheduled</option>
                    <option value="published">Published</option>
                    <option value="failed">Failed</option>
                </select>
                <select id="limit" onchange="refreshAll()" class="px-3 py-2 rounded-lg border border-slate-200 text-sm focus:ring-indigo-500 outline-none bg-slate-50 font-medium">
                    <option value="10">10</option>
                    <option value="25" selected>25</option>
                    <option value="50">50</option>
                </select>
                <button onclick="refreshAll()" class="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                </button>
            </div>
        </div>

        <div id="stats" class="flex flex-wrap gap-2 mb-8 animate-pulse">
            <div class="h-8 w-24 bg-slate-100 rounded-full"></div>
            <div class="h-8 w-24 bg-slate-100 rounded-full"></div>
            <div class="h-8 w-24 bg-slate-100 rounded-full"></div>
        </div>

        <div id="error" class="hidden mb-4 p-4 rounded-xl bg-red-50 text-red-600 text-sm font-medium border border-red-100"></div>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6" id="list">
            <!-- Posts go here -->
        </div>
      </section>
    </div>

  </main>

<script>
let API_KEY = localStorage.getItem("social_admin_key") || "";

function esc(s) {
  return (s ?? "").toString()
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function updateFileName(input) {
    const el = document.getElementById("file_name_display");
    el.textContent = input.files[0] ? input.files[0].name : "Click or drag image here";
}

function toggleSettings() {
    document.getElementById("settings_panel").classList.toggle("hidden");
}

function saveApiKey() {
    const val = document.getElementById("admin_key_input").value;
    API_KEY = val;
    localStorage.setItem("social_admin_key", val);
    document.getElementById("save_msg").className = "text-sm text-center text-green-600";
    document.getElementById("save_msg").textContent = "Key saved successfully!";
    updateKeyStatus();
    setTimeout(() => {
        document.getElementById("save_msg").textContent = "";
        toggleSettings();
        refreshAll();
    }, 1000);
}

function updateKeyStatus() {
    const el = document.getElementById("api_key_status");
    if (API_KEY) {
        el.className = "text-xs font-medium px-2 py-1 rounded border border-green-200 bg-green-50 text-green-700";
        el.textContent = "API Key Active";
    } else {
        el.className = "text-xs font-medium px-2 py-1 rounded border border-slate-200 bg-slate-100 text-slate-500";
        el.textContent = "API Key Required";
    }
}

async function request(url, opts = {}) {
    opts.headers = {
        ...opts.headers,
        "X-API-Key": API_KEY
    };
    const r = await fetch(url, opts);
    const j = await r.json();
    if (!r.ok) {
        if (r.status === 401) {
            setError("Unauthorized: Invalid API Key. Please check settings.");
            toggleSettings();
        }
        throw new Error(j.detail || JSON.stringify(j));
    }
    return j;
}

function setError(msg) {
  const el = document.getElementById("error");
  if (!msg) {
      el.classList.add("hidden");
  } else {
      el.classList.remove("hidden");
      el.textContent = msg;
  }
}

async function refreshAll() {
  setError("");
  updateKeyStatus();
  await Promise.all([loadStats(), loadPosts()]);
}

async function loadStats() {
  const el = document.getElementById("stats");
  try {
    const j = await request(`/posts/stats`);
    const counts = j.counts || {};
    el.classList.remove("animate-pulse");
    const parts = Object.entries(counts).map(([k,v]) => `
        <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold border border-slate-200 bg-slate-50 text-slate-600">
            ${esc(k)} <span class="ml-2 text-indigo-600">${v}</span>
        </span>
    `);
    el.innerHTML = parts.length ? parts.join("") : "<div class='text-slate-400 text-sm italic'>No activity recorded yet.</div>";
  } catch (e) {
    el.innerHTML = "<div class='text-red-400 text-xs font-bold'>Failed to load statistics</div>";
  }
}

async function loadPosts() {
  const list = document.getElementById("list");
  list.innerHTML = `
    <div class="col-span-full py-20 text-center space-y-4">
        <div class="animate-spin inline-block w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full"></div>
        <div class="text-slate-400 font-medium">Retrieving feed...</div>
    </div>
  `;
  try {
    const status = document.getElementById("status_filter").value;
    const limit = document.getElementById("limit").value;
    const qs = new URLSearchParams();
    if (status) qs.set("status", status);
    if (limit) qs.set("limit", limit);

    const j = await request(`/posts?${qs.toString()}`);

    if (!Array.isArray(j) || j.length === 0) {
      list.innerHTML = `
        <div class="col-span-full py-20 text-center bg-slate-50 rounded-2xl border-2 border-dashed border-slate-200">
            <div class="text-slate-400 font-medium">No posts found matching filter.</div>
        </div>
      `;
      return;
    }

    list.innerHTML = j.map(p => renderPost(p)).join("");
  } catch (e) {
    list.innerHTML = "";
    setError("Post feed error: " + e.message);
  }
}

function renderPost(p) {
  const statusColors = {
      submitted: "bg-slate-100 text-slate-600 border-slate-200",
      drafted: "bg-blue-50 text-blue-600 border-blue-100",
      needs_review: "bg-amber-50 text-amber-600 border-amber-100",
      scheduled: "bg-indigo-50 text-indigo-600 border-indigo-100",
      published: "bg-green-50 text-green-600 border-green-100",
      failed: "bg-red-50 text-red-600 border-red-100"
  }[p.status] || "bg-slate-50 text-slate-500";

  const captionFull = (p.caption || "") + (p.hashtags?.length ? "\\n\\n" + p.hashtags.join(" ") : "");
  
  const contentSection = p.caption
    ? `<div class="bg-slate-50 rounded-xl p-4 border border-slate-100 text-xs text-slate-700 leading-relaxed max-h-40 overflow-y-auto whitespace-pre-wrap">${esc(captionFull)}</div>`
    : `<div class="bg-slate-50 rounded-xl p-4 border border-slate-100 text-xs text-slate-400 italic">No caption generated yet.</div>`;

  const img = p.media_url
    ? `<div class="relative group aspect-square rounded-xl overflow-hidden mb-4 bg-slate-900 border border-slate-200 shadow-inner">
        <img class="w-full h-full object-cover transition-transform group-hover:scale-105" src="${esc(p.media_url)}" alt="Post asset"/>
        <a href="${esc(p.media_url)}" target="_blank" class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
            <span class="text-white text-xs font-bold ring-2 ring-white px-3 py-1 rounded-lg">View Full</span>
        </a>
       </div>`
    : "";

  const flags = p.flags && Object.keys(p.flags).length > 0 
    ? `<div class="mt-3 text-[10px] bg-red-50 text-red-700 p-2 rounded-lg border border-red-100">
        <span class="font-bold flex items-center gap-1 uppercase tracking-tighter"><svg class="h-3 w-3" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path></svg> Policy Flags</span>
        <div class="opacity-80 mt-1">${esc(JSON.stringify(p.flags))}</div>
       </div>` 
    : "";

  return `
    <article class="bg-white border border-slate-200 rounded-2xl overflow-hidden transition-all hover:shadow-md h-fit" id="post-${p.id}">
      <div class="p-5">
          <div class="flex justify-between items-start mb-4">
              <div>
                  <h3 class="font-bold text-slate-900 flex items-center gap-2">
                    #${p.id}
                  </h3>
                  <time class="text-[10px] font-semibold text-slate-400 uppercase tracking-widest">${esc(new Date(p.created_at).toLocaleString())}</time>
              </div>
              <span class="px-2 py-1 rounded text-[10px] font-bold border ${statusColors} uppercase tracking-tight">${esc(p.status)}</span>
          </div>
          
          <div class="space-y-3">
              <div class="text-xs text-slate-600 bg-slate-50/50 p-3 rounded-xl border border-dotted border-slate-200 italic">
                "${esc(p.source_text || "No source text provided")}"
              </div>
              
              ${img}
              ${contentSection}
              ${flags}
          </div>

          <div class="grid grid-cols-2 gap-2 mt-6">
            <button onclick="generate(${p.id})" class="text-[11px] font-bold py-2 px-3 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors flex items-center justify-center gap-1">
                <svg class="h-4 w-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.644.322a6 6 0 00-3.86.517l-2.387.477a2 2 0 00-1.022.547l-.34.34a2 2 0 000 2.828l1.245 1.245a2 2 0 002.828 0l.34-.34a2 2 0 00.547-1.022l.477-2.387a6 6 0 00-.517-3.86l-.322-.644a6 6 0 00-.517-3.86l.477-2.387a2 2 0 00-.547-1.022l-.34-.34a2 2 0 00-2.828 0l-1.245 1.245a2 2 0 000 2.828l.34.34z" /></svg>
                Generate
            </button>
            <button onclick="approve(${p.id})" class="text-[11px] font-bold py-2 px-3 rounded-lg border border-slate-200 hover:bg-slate-50 transition-colors flex items-center justify-center gap-1">
                <svg class="h-4 w-4 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                Approve
            </button>
            <button onclick="publishNow(${p.id})" class="col-span-2 bg-slate-900 text-white text-[11px] font-bold py-2.5 px-3 rounded-lg hover:bg-slate-800 transition-all shadow-md flex items-center justify-center gap-2">
                <svg class="h-4 w-4 text-indigo-400" fill="currentColor" viewBox="0 0 20 20"><path d="M15 8a3 3 0 10-2.977-2.63l-4.94 2.47a3 3 0 100 4.319l4.94 2.47a3 3 0 10.895-1.789l-4.94-2.47a3.027 3.027 0 000-.74l4.94-2.47C13.456 7.68 14.19 8 15 8z"></path></svg>
                Publish Now
            </button>
          </div>
          <div class="mt-4 text-[10px] text-center font-bold uppercase transition-all" id="msg-${p.id}"></div>
      </div>
    </article>
  `;
}

function setMsg(id, msg, type='info') {
  const el = document.getElementById(\`msg-\${id}\`);
  if (!el) return;
  
  const colors = {
      info: "text-indigo-600",
      success: "text-green-600",
      error: "text-red-600"
  };
  
  el.className = \`mt-4 text-[10px] text-center font-bold uppercase \${colors[type]}\`;
  el.textContent = msg;
}

async function uploadPost() {
  setError("");
  const msg = document.getElementById("upload_msg");
  msg.className = "text-center text-sm font-medium text-slate-500 animate-pulse";
  msg.textContent = "Processing upload...";

  const sourceText = document.getElementById("source_text").value || "";
  const file = document.getElementById("image").files[0];
  if (!file) {
    msg.textContent = "";
    setError("No image asset selected.");
    return;
  }

  const fd = new FormData();
  fd.append("source_text", sourceText);
  fd.append("image", file);

  try {
    const j = await request(\`/posts/intake\`, { method: "POST", body: fd });
    msg.className = "text-center text-sm font-bold text-green-600";
    msg.textContent = \`Intake successful: #\${j.id}\`;
    document.getElementById("source_text").value = "";
    document.getElementById("image").value = "";
    document.getElementById("file_name_display").textContent = "Click or drag image here";
    await refreshAll();
    setTimeout(() => { msg.textContent = ""; }, 3000);
  } catch (e) {
    msg.textContent = "";
    setError("Intake failed: " + e.message);
  }
}

async function generate(id) {
  setMsg(id, "Generation in progress...", 'info');
  try {
    await request(\`/posts/\${id}/generate\`, { method: "POST" });
    setMsg(id, "Successfully generated", 'success');
    await refreshAll();
  } catch (e) {
    setMsg(id, "Generation error", 'error');
    setError("Generate failed: " + e.message);
  }
}

async function approve(id) {
  setMsg(id, "Approving content...", 'info');
  try {
    await request(\`/posts/\${id}/approve\`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approve_anyway: true })
    });
    setMsg(id, "Content approved", 'success');
    await refreshAll();
  } catch (e) {
    setMsg(id, "Approval error", 'error');
    setError("Approve failed: " + e.message);
  }
}

async function publishNow(id) {
    setMsg(id, "Publishing to Instagram...", 'info');
    try {
        await request(\`/posts/\${id}/publish\`, { method: "POST" });
        setMsg(id, "Published ✓", 'success');
        await refreshAll();
    } catch (e) {
        setMsg(id, "Publish failed", 'error');
        setError("Manual publish failed: " + e.message);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    refreshAll();
    if(API_KEY) document.getElementById("admin_key_input").value = API_KEY;
});
</script>
</body>
</html>
"""

@router.get("", response_class=HTMLResponse)
def admin_page():
    return HTML