from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.db import get_db
from app.models import User, Org, OrgMember, IGAccount, Post, TopicAutomation, ContentProfile
from app.security.auth import require_user, optional_user
from app.services.prebuilt_loader import load_prebuilt_packs
from app.services.automation_runner import run_automation_once
from app.security.rbac import get_current_org_id
from typing import Optional
import json, calendar
from datetime import datetime, timedelta, timezone

router = APIRouter()

# --- HTML TEMPLATES ---

APP_LAYOUT_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} | Social Media LLM</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root {{
      --brand: #6366f1;
      --brand-hover: #4f46e5;
      --main-bg: #020617;
      --surface: rgba(255, 255, 255, 0.03);
      --text-main: #ffffff;
      --text-muted: #94a3b8;
      --border: rgba(255, 255, 255, 0.1);
      --card-bg: rgba(255, 255, 255, 0.03);
    }}
    body {{ font-family: 'Inter', sans-serif; background-color: var(--main-bg); color: var(--text-main); }}
    .ai-bg {{ background: radial-gradient(circle at top right, #312e81, #020617, #020617); }}
    .glass {{ background: var(--surface); backdrop-filter: blur(12px); border: 1px solid var(--border); }}
    .text-gradient {{ background: linear-gradient(to right, #818cf8, #c084fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
    .nav-link.active {{ color: var(--brand); border-bottom: 2px solid var(--brand); }}
  </style>
</head>
<body class="ai-bg min-h-screen">
  <!-- Top Nav -->
  <nav class="border-b border-white/5 bg-black/20 backdrop-blur-md sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-6 h-16 flex justify-between items-center">
      <div class="flex items-center gap-8">
        <div class="text-lg font-black italic tracking-tighter text-gradient">SOCIAL MEDIA LLM</div>
        <div class="hidden md:flex gap-6">
          <a href="/app" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 {active_dashboard}">Dashboard</a>
          <a href="/app/calendar" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 {active_calendar} text-muted hover:text-white transition-colors">Calendar</a>
          <a href="/app/automations" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 {active_automations} text-muted hover:text-white transition-colors">Automations</a>
          <a href="/app/library" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 {active_library} text-muted hover:text-white transition-colors">Library</a>
          <a href="/app/media" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 {active_media} text-muted hover:text-white transition-colors">Media Library</a>
          {admin_link}
        </div>
      </div>
      <div class="flex items-center gap-4">
        <div class="text-right hidden sm:block">
          <div class="text-[10px] font-black text-white uppercase tracking-wider">{user_name}</div>
          <div class="text-[8px] font-bold text-muted uppercase tracking-widest">{org_name}</div>
        </div>
        <button onclick="logout()" class="p-2 text-muted hover:text-white transition-colors">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
        </button>
      </div>
    </div>
  </nav>

  <main class="max-w-7xl mx-auto px-6 py-10 space-y-10">
    {content}
  </main>

  <script>
    async function logout() {{
      await fetch('/auth/logout', {{ method: 'POST' }});
      window.location.href = '/';
    }}

    function syncAccounts() {{
        const btn = event.currentTarget;
        const originalText = btn.innerText;
        btn.innerText = 'Syncing...';
        btn.disabled = true;
        
        setTimeout(() => {{
            btn.innerText = originalText;
            btn.disabled = false;
            window.location.reload();
        }}, 1500);
    }}

    function openNewPostModal() {{
        document.getElementById('newPostModal').classList.remove('hidden');
    }}

    function closeNewPostModal() {{
        document.getElementById('newPostModal').classList.add('hidden');
    }}

    function openEditPostModal(id, caption, time) {{
        document.getElementById('editPostId').value = id;
        document.getElementById('editPostCaption').value = caption;
        // Format time for datetime-local
        if (time) {{
            const d = new Date(time);
            const iso = d.toISOString().slice(0, 16);
            document.getElementById('editPostTime').value = iso;
        }}
        document.getElementById('editPostModal').classList.remove('hidden');
    }}

    function closeEditPostModal() {{
        document.getElementById('editPostModal').classList.add('hidden');
    }}

    async function savePostEdit() {{
        const id = document.getElementById('editPostId').value;
        const caption = document.getElementById('editPostCaption').value;
        const time = document.getElementById('editPostTime').value;
        const btn = document.getElementById('savePostBtn');

        btn.disabled = true;
        btn.innerText = 'SAVING...';

        try {{
            const res = await fetch(`/posts/${{id}}`, {{
                method: 'PATCH',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ caption: caption, scheduled_time: time }})
            }});
            if (res.ok) window.location.reload();
            else alert('Failed to update post');
        }} catch(e) {{ alert('Error updating post'); }}
        finally {{ btn.disabled = false; btn.innerText = 'Apply Changes'; }}
    }}

    async function approvePost(id) {{
        try {{
            const res = await fetch(`/posts/${{id}}/approve`, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ approve_anyway: true }})
            }});
            if (res.ok) window.location.reload();
            else alert('Approval failed');
        }} catch(e) {{ alert('Error approving'); }}
    }}

    async function submitNewPost(event) {{
        event.preventDefault();
        const btn = event.submitter;
        const originalText = btn.innerText;
        btn.innerText = 'Generating...';
        btn.disabled = true;

        const formData = new FormData(event.target);
        try {{
            const res = await fetch('/posts/intake', {{
                method: 'POST',
                body: formData
            }});
            if (res.ok) {{
                window.location.reload();
            }} else {{
                const err = await res.json();
                alert('Error: ' + (err.detail || 'Failed to create post'));
            }}
        }} catch (e) {{
            alert('Upload failed: ' + e);
        }} finally {{
            btn.innerText = originalText;
            btn.disabled = false;
        }}
    }}
  </script>

  <!-- New Post Modal -->
  <div id="newPostModal" class="fixed inset-0 bg-black/80 backdrop-blur-sm z-[100] flex items-center justify-center p-6 hidden">
    <div class="glass max-w-lg w-full rounded-[2.5rem] p-10 space-y-8 animate-in fade-in zoom-in duration-300">
      <div class="flex justify-between items-center">
        <h3 class="text-2xl font-black italic text-white tracking-tight">Create <span class="text-brand">New Post</span></h3>
        <button onclick="closeNewPostModal()" class="text-muted hover:text-white transition-colors">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
        </button>
      </div>

      <form onsubmit="submitNewPost(event)" class="space-y-6">
        <div class="space-y-2">
          <label class="text-[10px] font-black uppercase tracking-[0.2em] text-muted">Select Account</label>
          <select name="ig_account_id" class="w-full bg-white/5 border border-white/10 rounded-2xl p-4 text-sm font-bold text-white outline-none focus:border-brand/40 transition-all">
            {account_options}
          </select>
        </div>

        <div class="space-y-2">
          <label class="text-[10px] font-black uppercase tracking-[0.2em] text-muted">Topic / Instructions</label>
          <textarea name="source_text" required placeholder="What should we post about?" class="w-full bg-white/5 border border-white/10 rounded-2xl p-4 text-sm font-medium text-white outline-none focus:border-brand/40 transition-all h-32 resize-none"></textarea>
        </div>

        <div class="flex items-center gap-3 p-4 bg-brand/5 rounded-2xl border border-brand/20">
            <input type="checkbox" name="use_ai_image" id="use_ai_image" class="w-4 h-4 rounded bg-white/5 border-white/10 text-brand focus:ring-brand focus:ring-offset-0">
            <label for="use_ai_image" class="text-[10px] font-black uppercase tracking-widest text-brand">Generate AI Image Card</label>
        </div>

        <div class="pt-4">
          <button type="submit" class="w-full py-5 bg-brand rounded-2xl font-black text-sm uppercase tracking-widest text-white shadow-xl shadow-brand/40 hover:scale-[1.02] active:scale-[0.98] transition-all">Create Post &rarr;</button>
        </div>
      </form>
    </div>
  </div>
</body>
</html>
"""

APP_DASHBOARD_CONTENT = """
    <!-- Header -->
    <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div>
        <h1 class="text-3xl font-black italic tracking-tight text-white">System <span class="text-brand">Overview</span></h1>
        <p class="text-xs font-bold text-muted uppercase tracking-widest">Real-time intelligence feed</p>
      </div>
      <div class="flex gap-2">
        {admin_cta}
        <button onclick="openNewPostModal()" class="px-6 py-3 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest text-white hover:bg-white/10 transition-all">New Post</button>
        <button onclick="syncAccounts()" class="px-6 py-3 bg-brand rounded-xl font-black text-[10px] uppercase tracking-widest text-white shadow-xl shadow-brand/20">Sync Accounts</button>
      </div>
    </div>

    <!-- Quick Stats -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="glass p-6 rounded-2xl">
        <div class="text-[8px] font-black text-muted uppercase tracking-[0.2em] mb-1">Weekly Output</div>
        <div class="text-2xl font-black text-white">{weekly_post_count} Posts</div>
      </div>
      <div class="glass p-6 rounded-2xl">
        <div class="text-[8px] font-black text-muted uppercase tracking-[0.2em] mb-1">Active Accounts</div>
        <div class="text-2xl font-black text-white">{account_count} Connected</div>
      </div>
      <div class="glass p-6 rounded-2xl">
        <div class="text-[8px] font-black text-muted uppercase tracking-[0.2em] mb-1">Automation Status</div>
        <div class="text-2xl font-black text-emerald-400">Operational</div>
      </div>
      <div class="glass p-6 rounded-2xl">
        <div class="text-[8px] font-black text-muted uppercase tracking-[0.2em] mb-1">Next Post In</div>
        <div class="text-2xl font-black text-brand">{next_post_countdown}</div>
      </div>
    </div>

    {connection_cta}

    <!-- Main Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <!-- Next Post Preview -->
      <div class="lg:col-span-1 space-y-6">
        <h2 class="text-xs font-black uppercase tracking-[0.3em] text-muted">Next Scheduled Post</h2>
        <div class="glass rounded-[2.5rem] p-8 space-y-6 border-brand/20">
          <div class="aspect-square rounded-2xl overflow-hidden bg-white/5 relative border border-white/10">
            {next_post_media}
            <div class="absolute top-4 right-4 bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-lg border border-white/10 text-[8px] font-black uppercase tracking-widest text-white">
              {next_post_time}
            </div>
          </div>
          <div class="space-y-4">
            <p class="text-sm text-white/90 leading-relaxed font-medium line-clamp-3">
              {next_post_caption}
            </p>
            <div class="pt-4 flex gap-2">
              <button onclick="openEditPostModal('{next_post_id}', \`{next_post_caption_raw}\`, '{next_post_time_iso}')" class="flex-1 py-3 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest hover:bg-white/10 transition-all">Edit</button>
              <button onclick="approvePost('{next_post_id}')" class="flex-1 py-3 bg-brand/20 text-brand rounded-xl font-black text-[10px] uppercase tracking-widest border border-brand/20">Approve</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Feed / Calendar Preview -->
      <div class="lg:col-span-2 space-y-6">
        <div class="flex justify-between items-center">
          <h2 class="text-xs font-black uppercase tracking-[0.3em] text-muted">Upcoming Pipeline</h2>
          <a href="/app/calendar" class="text-[8px] font-black uppercase tracking-widest text-brand hover:underline">View Full Calendar &rarr;</a>
        </div>
        
        <div class="glass rounded-[2.5rem] overflow-hidden border border-white/10">
          <div class="grid grid-cols-7 border-b border-white/5 bg-white/5">
            {calendar_headers}
          </div>
          <div class="grid grid-cols-7 h-48">
            {calendar_days}
          </div>
        </div>

        <!-- Recent Posts List -->
        <div class="space-y-4 pt-4">
          <h2 class="text-xs font-black uppercase tracking-[0.3em] text-muted">Recent Activity</h2>
          <div class="space-y-2">
            {recent_posts}
          </div>
        </div>
      </div>
    </div>
    </div>

    <!-- Edit Post Modal -->
    <div id="editPostModal" class="fixed inset-0 bg-black/80 backdrop-blur-xl z-[100] hidden flex items-center justify-center p-6">
      <div class="glass w-full max-w-xl rounded-[3rem] p-10 space-y-8 animate-in zoom-in-95 duration-300 border-brand/20">
        <div class="flex justify-between items-center">
          <div>
            <h2 class="text-2xl font-black italic text-white tracking-tight">Edit <span class="text-brand">Post</span></h2>
            <p class="text-[10px] font-bold text-muted uppercase tracking-widest">Modify scheduled content</p>
          </div>
          <button onclick="closeEditPostModal()" class="p-2 text-muted hover:text-white"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg></button>
        </div>

        <input type="hidden" id="editPostId">
        
        <div class="space-y-6">
          <div class="space-y-2">
            <label class="text-[10px] font-black text-muted uppercase tracking-widest ml-1">Caption / Content</label>
            <textarea id="editPostCaption" rows="6" class="w-full bg-white/5 border border-white/10 rounded-2xl p-4 text-white text-sm focus:border-brand/50 focus:ring-0 transition-all font-medium"></textarea>
          </div>
          <div class="space-y-2">
            <label class="text-[10px] font-black text-muted uppercase tracking-widest ml-1">Scheduled Time (UTC)</label>
            <input type="datetime-local" id="editPostTime" class="w-full bg-white/5 border border-white/10 rounded-2xl p-4 text-white text-sm focus:border-brand/50 focus:ring-0 transition-all">
          </div>
        </div>

        <div class="flex gap-4 pt-4">
          <button onclick="closeEditPostModal()" class="flex-1 py-4 bg-white/5 border border-white/10 rounded-2xl font-black text-xs uppercase tracking-widest text-white hover:bg-white/10 transition-all">Cancel</button>
          <button id="savePostBtn" onclick="savePostEdit()" class="flex-1 py-4 bg-brand rounded-2xl font-black text-xs uppercase tracking-widest text-white shadow-xl shadow-brand/20 hover:bg-brand-hover transition-all">Apply Changes</button>
        </div>
      </div>
    </div>
"""

ONBOARDING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Onboarding | Social Media LLM</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; background: #020617; color: #ffffff; }
    .ai-bg { background: radial-gradient(circle at top right, #312e81, #0f172a, #020617); }
    .glass { background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.1); }
    .step-dot.active { background: #6366f1; transform: scale(1.2); }
    .step-dot.complete { background: #10b981; }
  </style>
</head>
<body class="ai-bg min-h-screen p-6 flex items-center justify-center">
  <div class="max-w-2xl w-full">
    <!-- Progress -->
    <div class="flex justify-center gap-4 mb-12" id="progress-dots">
      <div class="step-dot active w-3 h-3 rounded-full bg-white/20 transition-all"></div>
      <div class="step-dot w-3 h-3 rounded-full bg-white/20 transition-all"></div>
      <div class="step-dot w-3 h-3 rounded-full bg-white/20 transition-all"></div>
      <div class="step-dot w-3 h-3 rounded-full bg-white/20 transition-all"></div>
      <div class="step-dot w-3 h-3 rounded-full bg-white/20 transition-all"></div>
    </div>

    <div class="glass rounded-[3rem] p-12 space-y-10 min-h-[500px] flex flex-col justify-between" id="onboarding-card">
      <!-- Content injected by JS -->
    </div>
  </div>

  <script>
    let currentStep = 1;
    let onboardingData = {
      orgName: '',
      igUserId: '',
      igAccessToken: '',
      contentMode: 'manual',
      autoTopic: '',
      autoTime: '09:00'
    };

    function updateProgress() {
      const dots = document.querySelectorAll('.step-dot');
      dots.forEach((dot, i) => {
        dot.className = 'step-dot w-3 h-3 rounded-full transition-all';
        if (i + 1 < currentStep) dot.classList.add('complete', 'bg-emerald-500');
        else if (i + 1 === currentStep) dot.classList.add('active', 'bg-indigo-500', 'scale-125');
        else dot.classList.add('bg-white/20');
      });
    }

    function renderStep() {
      const card = document.getElementById('onboarding-card');
      updateProgress();

      if (currentStep === 1) {
        card.innerHTML = `
          <div class="space-y-6">
            <h2 class="text-sm font-black text-indigo-400 uppercase tracking-widest">Step 01</h2>
            <h3 class="text-4xl font-black italic text-white tracking-tight">Name your workspace.</h3>
            <p class="text-muted text-sm font-medium">This is where your brands and teams will live.</p>
            <div class="pt-4">
              <input type="text" id="orgName" value="${onboardingData.orgName}" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. Acme Marketing">
            </div>
          </div>
          <button onclick="nextStep()" class="w-full bg-indigo-500 py-5 rounded-2xl font-black text-sm uppercase tracking-widest shadow-xl shadow-indigo-500/20">Continue &rarr;</button>
        `;
      } else if (currentStep === 2) {
        card.innerHTML = `
          <div class="space-y-6">
            <h2 class="text-sm font-black text-indigo-400 uppercase tracking-widest">Step 02</h2>
            <h3 class="text-4xl font-black italic text-white tracking-tight">Connect Instagram.</h3>
            <p class="text-muted text-sm font-medium">Enter your professional account details to enable publishing.</p>
            <div class="space-y-4 pt-4">
              <input type="text" id="igUserId" value="${onboardingData.igUserId}" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Instagram User ID">
              <input type="password" id="igAccessToken" value="${onboardingData.igAccessToken}" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Access Token">
            </div>
            <p class="text-[9px] text-muted font-bold uppercase tracking-widest text-center mt-4 italic">Required for automated posting. Skipping will enter browse-only mode.</p>
          </div>
          <div class="flex flex-col gap-3">
            <div class="flex gap-4">
              <button onclick="prevStep()" class="flex-1 bg-white/5 py-5 rounded-2xl font-black text-sm uppercase tracking-widest border border-white/10">Back</button>
              <button onclick="nextStep()" class="flex-[2] bg-indigo-500 py-5 rounded-2xl font-black text-sm uppercase tracking-widest shadow-xl shadow-indigo-500/20">Verify & Continue</button>
            </div>
            <button onclick="nextStep()" class="w-full py-4 text-[10px] font-black uppercase tracking-widest text-muted hover:text-white transition-colors">Skip for now &rarr;</button>
          </div>
        `;
      } else if (currentStep === 3) {
        card.innerHTML = `
          <div class="space-y-6">
            <h2 class="text-sm font-black text-indigo-400 uppercase tracking-widest">Step 03</h2>
            <h3 class="text-4xl font-black italic text-white tracking-tight">Intelligence Mode.</h3>
            <p class="text-muted text-sm font-medium">How should we source your daily inspiration?</p>
            <div class="grid grid-cols-1 gap-4 pt-4">
              <div onclick="onboardingData.contentMode='manual'; renderStep()" class="p-6 rounded-2xl border ${onboardingData.contentMode==='manual' ? 'border-indigo-500 bg-indigo-500/10' : 'border-white/10 bg-white/5'} cursor-pointer">
                <h4 class="font-black italic text-sm">Manual Uploads</h4>
                <p class="text-[10px] text-muted uppercase mt-1">You provide the topics, AI does the rest.</p>
              </div>
              <div onclick="onboardingData.contentMode='rss'; renderStep()" class="p-6 rounded-2xl border ${onboardingData.contentMode==='rss' ? 'border-indigo-500 bg-indigo-500/10' : 'border-white/10 bg-white/5'} cursor-pointer">
                <h4 class="font-black italic text-sm">Automated Feed (RSS/URL)</h4>
                <p class="text-[10px] text-muted uppercase mt-1">Pull knowledge from external websites.</p>
              </div>
              <div onclick="onboardingData.contentMode='auto_library'; renderStep()" class="p-6 rounded-2xl border ${onboardingData.contentMode==='auto_library' ? 'border-indigo-500 bg-indigo-500/10' : 'border-white/10 bg-white/5'} cursor-pointer">
                <h4 class="font-black italic text-sm">Organizational Library (BYOS)</h4>
                <p class="text-[10px] text-muted uppercase mt-1">Ground content in your own documents and sources.</p>
              </div>
            </div>
            <p class="text-[9px] text-muted font-bold uppercase tracking-widest text-center mt-2 italic text-indigo-400">Can be changed later in configuration.</p>
          </div>
          <div class="flex flex-col gap-3 pt-4">
            <div class="flex gap-4">
              <button onclick="prevStep()" class="flex-1 bg-white/5 py-5 rounded-2xl font-black text-sm uppercase tracking-widest border border-white/10">Back</button>
              <button onclick="nextStep()" class="flex-[2] bg-indigo-500 py-5 rounded-2xl font-black text-sm uppercase tracking-widest shadow-xl shadow-indigo-500/20">Continue &rarr;</button>
            </div>
          </div>
        `;
      } else if (currentStep === 4) {
        card.innerHTML = `
          <div class="space-y-6">
            <h2 class="text-sm font-black text-indigo-400 uppercase tracking-widest">Step 04</h2>
            <h3 class="text-4xl font-black italic text-white tracking-tight">First Automation.</h3>
            <p class="text-muted text-sm font-medium">Let's configure your first daily posting cycle.</p>
            <div class="space-y-4 pt-4">
              <div class="space-y-1">
                <label class="text-[10px] font-black uppercase tracking-widest text-muted">Core Topic/Theme</label>
                <input type="text" id="autoTopic" value="${onboardingData.autoTopic}" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. Daily Motivation & Productivity">
              </div>
              <div class="space-y-1">
                <label class="text-[10px] font-black uppercase tracking-widest text-muted">Daily Posting Time</label>
                <input type="time" id="autoTime" value="${onboardingData.autoTime}" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-indigo-500">
              </div>
            </div>
          </div>
          <div class="flex gap-4 pt-8">
            <button onclick="prevStep()" class="flex-1 bg-white/5 py-5 rounded-2xl font-black text-sm uppercase tracking-widest border border-white/10">Back</button>
            <button onclick="nextStep()" class="flex-[2] bg-indigo-500 py-5 rounded-2xl font-black text-sm uppercase tracking-widest">Initialize Protocol</button>
          </div>
        `;
      } else if (currentStep === 5) {
        card.innerHTML = `
          <div class="space-y-6">
            <h2 class="text-sm font-black text-indigo-400 uppercase tracking-widest">Step 05</h2>
            <h3 class="text-4xl font-black italic text-white tracking-tight">System Ready.</h3>
            <div class="bg-indigo-500/10 border border-indigo-500/20 p-8 rounded-[2rem] space-y-4">
               <div class="flex justify-between text-[10px] font-black uppercase tracking-widest"><span>Workspace</span> <span class="text-white">${onboardingData.orgName}</span></div>
               <div class="flex justify-between text-[10px] font-black uppercase tracking-widest"><span>Account</span> <span class="text-white">${onboardingData.igUserId}</span></div>
               <div class="flex justify-between text-[10px] font-black uppercase tracking-widest"><span>Intelligence</span> <span class="text-white">${onboardingData.contentMode}</span></div>
               <div class="flex justify-between text-[10px] font-black uppercase tracking-widest"><span>Schedule</span> <span class="text-white">Daily @ ${onboardingData.autoTime}</span></div>
            </div>
            <p class="text-muted text-center text-xs font-medium">Click finish to activate your neural automation engine.</p>
          </div>
          <div class="flex gap-4 pt-8">
            <button onclick="prevStep()" class="flex-1 bg-white/5 py-5 rounded-2xl font-black text-sm uppercase tracking-widest border border-white/10">Review</button>
            <button onclick="finishOnboarding()" id="finishBtn" class="flex-[2] bg-emerald-500 py-5 rounded-2xl font-black text-sm uppercase tracking-widest shadow-xl shadow-emerald-500/20">Finalize & Launch</button>
          </div>
        `;
      }
    }

    function syncData() {
      if (document.getElementById('orgName')) onboardingData.orgName = document.getElementById('orgName').value;
      if (document.getElementById('igUserId')) onboardingData.igUserId = document.getElementById('igUserId').value;
      if (document.getElementById('igAccessToken')) onboardingData.igAccessToken = document.getElementById('igAccessToken').value;
      if (document.getElementById('autoTopic')) onboardingData.autoTopic = document.getElementById('autoTopic').value;
      if (document.getElementById('autoTime')) onboardingData.autoTime = document.getElementById('autoTime').value;
    }

    function nextStep() {
      syncData();
      if (currentStep < 5) {
        currentStep++;
        renderStep();
      }
    }

    function prevStep() {
      syncData();
      if (currentStep > 1) {
        currentStep--;
        renderStep();
      }
    }

    async function finishOnboarding() {
      const btn = document.getElementById('finishBtn');
      btn.disabled = true;
      btn.textContent = "ACTIVATING...";
      
      try {
        const res = await fetch('/api/onboarding/finalize', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(onboardingData)
        });
        if (res.ok) {
          window.location.href = '/app';
        } else {
          const data = await res.json();
          alert(data.detail || "Onboarding failed");
          btn.disabled = false;
          btn.textContent = "Finalize & Launch";
        }
      } catch (e) {
        alert("Connection error");
        btn.disabled = false;
        btn.textContent = "Finalize & Launch";
      }
    }

    renderStep();
  </script>
</body>
</html>
"""

@router.get("/app", response_class=HTMLResponse)
async def app_dashboard_page(
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    # REDIRECT LOGIC
    if not user.onboarding_complete:
        return RedirectResponse(url="/onboarding")

    # Fetch User's Active Org
    org_id = user.active_org_id
    if not org_id:
        membership = db.query(OrgMember).filter(OrgMember.user_id == user.id).first()
        if not membership:
            return RedirectResponse(url="/onboarding")
        org_id = membership.org_id
        user.active_org_id = org_id
        db.commit()

    org = db.query(Org).filter(Org.id == org_id).first()
    
    # Stats Calculation
    weekly_post_count = db.query(func.count(Post.id)).filter(
        Post.org_id == org_id,
        Post.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
    ).scalar() or 0
    
    account_count = db.query(func.count(IGAccount.id)).filter(IGAccount.org_id == org_id).scalar() or 0
    
    # Accounts for modal
    accounts = db.query(IGAccount).filter(IGAccount.org_id == org_id).all()
    account_options = "".join([f'<option value="{a.id}">{a.name} (@{a.ig_user_id})</option>' for a in accounts])
    if not accounts:
        account_options = '<option value="">No accounts connected</option>'
    
    # Next Post
    now_utc = datetime.now(timezone.utc)
    next_post = db.query(Post).filter(
        Post.org_id == org_id,
        Post.status == "scheduled",
        Post.scheduled_time > now_utc
    ).order_by(Post.scheduled_time.asc()).first()

    next_post_countdown = "No posts scheduled"
    next_post_time = "--:--"
    next_post_caption = "Create your first automation to see content here."
    next_post_media = '<div class="w-full h-full flex items-center justify-center text-muted font-black text-xs uppercase italic">No Media</div>'
    
    next_post_id = ""
    next_post_caption_raw = ""
    next_post_time_iso = ""
    
    if next_post:
        diff = next_post.scheduled_time - now_utc
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        next_post_countdown = f"{diff.days}d {hours}h {minutes}m"
        next_post_time = next_post.scheduled_time.strftime("%b %d, %H:%M")
        next_post_caption = next_post.caption or "No caption generated."
        
        next_post_id = str(next_post.id)
        next_post_caption_raw = (next_post.caption or "").replace("`", "\\`").replace("${", "\\${")
        next_post_time_iso = next_post.scheduled_time.isoformat()
        
        if next_post.media_url:
            next_post_media = f'<img src="{next_post.media_url}" class="w-full h-full object-cover">'

    # Calendar Construction (Next 7 days)
    calendar_headers = ""
    calendar_days = ""
    today = datetime.now(timezone.utc)
    for i in range(7):
        day = today + timedelta(days=i)
        calendar_headers += f'<div class="py-2 text-[8px] font-black text-center uppercase tracking-widest text-muted">{day.strftime("%a")}</div>'
        
        # Count posts for this day
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        post_count = db.query(func.count(Post.id)).filter(
            Post.org_id == org_id,
            Post.scheduled_time >= day_start,
            Post.scheduled_time < day_end
        ).scalar() or 0
        
        indicator = ""
        if post_count > 0:
            indicator = f'<div class="mt-2 w-1.5 h-1.5 rounded-full bg-brand"></div>'
            
        calendar_days += f"""
        <div class="border-r border-b border-white/5 flex flex-col items-center justify-center relative">
          <span class="text-[10px] font-black text-white/40">{day.day}</span>
          {indicator}
        </div>
        """

    # Recent Posts
    posts = db.query(Post).filter(Post.org_id == org_id).order_by(Post.created_at.desc()).limit(5).all()
    recent_posts_html = ""
    for p in posts:
        status_color = "text-muted"
        if p.status == "published": status_color = "text-emerald-400"
        if p.status == "scheduled": status_color = "text-brand"
        
        escaped_caption = (p.caption or "").replace('`', '\\`').replace('${', '\\${')
        
        recent_posts_html += f"""
        <div class="glass p-4 rounded-2xl flex justify-between items-center">
          <div class="flex items-center gap-4">
            <div class="w-8 h-8 rounded-lg bg-white/5 overflow-hidden border border-white/10">
                {f'<img src="{p.media_url}" class="w-full h-full object-cover">' if p.media_url else ''}
            </div>
            <div>
              <div class="text-[10px] font-black text-white uppercase tracking-wider truncate max-w-[200px]">{p.caption[:40] if p.caption else "Untitled Post"}...</div>
              <div class="text-[8px] font-bold text-muted uppercase tracking-widest">{p.created_at.strftime("%b %d, %H:%M")}</div>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button onclick="openEditPostModal('{p.id}', \`{escaped_caption}\`, '{p.scheduled_time.isoformat() if p.scheduled_time else ''}')" class="p-2 text-muted hover:text-white transition-colors">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
            </button>
            <div class="text-[8px] font-black uppercase tracking-widest {status_color}">{p.status}</div>
          </div>
        </div>
        """
    
    # Connection CTA for empty states
    connection_cta = ""
    if account_count == 0:
        connection_cta = f"""
        <div class="glass p-12 rounded-[3rem] border-brand/20 bg-brand/5 text-center space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-1000">
          <div class="w-16 h-16 bg-brand/20 rounded-2xl flex items-center justify-center text-brand mx-auto">
            <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
          </div>
          <div class="space-y-2">
            <h3 class="text-xl font-black italic text-white">Neural Engine Offline</h3>
            <p class="text-muted text-sm max-w-md mx-auto">Your account is active, but no publishing destinations are linked. Connect your first Instagram account to activate the automation loop.</p>
          </div>
          <button onclick="alert('Instagram connection flow coming in next update. For now, use Admin Console or re-run onboarding.')" class="px-10 py-4 bg-brand rounded-2xl font-black text-xs uppercase tracking-widest text-white shadow-xl shadow-brand/40">Initialize IG Connection</button>
        </div>
        """
    
    # Check if superadmin for admin link and prominent CTA
    admin_link = ""
    admin_cta = ""
    if user.is_superadmin:
        admin_link = '<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin Console</a>'
        admin_cta = '<a href="/admin" class="px-6 py-3 bg-rose-500/10 border border-rose-500/20 rounded-xl font-black text-[10px] uppercase tracking-widest text-rose-400 hover:bg-rose-500/20 transition-all flex items-center gap-2"><svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>Owner Ops</a>'

    content = APP_DASHBOARD_CONTENT.format(
        admin_cta=admin_cta,
        connection_cta=connection_cta,
        weekly_post_count=weekly_post_count,
        account_count=account_count,
        next_post_countdown=next_post_countdown,
        next_post_time=next_post_time,
        next_post_caption=next_post_caption,
        next_post_media=next_post_media,
        calendar_headers=calendar_headers,
        calendar_days=calendar_days,
        recent_posts=recent_posts_html or '<div class="text-center py-6 text-[10px] font-black uppercase text-muted italic">No recent activity</div>',
        next_post_id=next_post_id,
        next_post_caption_raw=next_post_caption_raw,
        next_post_time_iso=next_post_time_iso
    )
    
    return APP_LAYOUT_HTML.format(
        title="Dashboard",
        user_name=user.name or user.email,
        org_name=org.name if org else "Personal Workspace",
        admin_link=admin_link,
        active_media="",
        content=content,
        account_options=account_options
    )

@router.get("/app/calendar", response_class=HTMLResponse)
async def app_calendar_page(
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    if not user.onboarding_complete: return RedirectResponse(url="/onboarding")
    org = db.query(Org).filter(Org.id == user.active_org_id).first()
    admin_link = '<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin Console</a>' if user.is_superadmin else ""
    
    today = datetime.now(timezone.utc)
    year = today.year
    month = today.month
    
    # Get calendar days
    cal = calendar.Calendar(firstweekday=6) # Sunday start
    month_days = cal.monthdayscalendar(year, month)
    
    # Range for query
    month_start = datetime(year, month, 1)
    if month == 12:
        month_end = datetime(year + 1, 1, 1)
    else:
        month_end = datetime(year, month + 1, 1)

    # Use a wider range to avoid TZ boundary issues
    query_start = month_start - timedelta(days=1)
    query_end = month_end + timedelta(days=1)
        
    posts = db.query(Post).filter(
        Post.org_id == org.id,
        Post.scheduled_time >= query_start,
        Post.scheduled_time < query_end
    ).all()
    
    # Map posts to days
    post_map = {}
    for p in posts:
        day = p.scheduled_time.day
        if day not in post_map: post_map[day] = []
        post_map[day].append(p)
        
    calendar_html = ""
    headers = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    for h in headers:
        calendar_html += f'<div class="py-4 text-[10px] font-black uppercase tracking-[0.2em] text-muted text-center">{h}</div>'
        
    for week in month_days:
        for day in week:
            if day == 0:
                calendar_html += '<div class="aspect-square glass/5 border border-white/5 opacity-20"></div>'
            else:
                day_posts = post_map.get(day, [])
                indicators = ""
                for dp in day_posts[:3]:
                    color = "bg-brand" if dp.status == "scheduled" else "bg-emerald-400"
                    indicators += f'<div class="w-1.5 h-1.5 rounded-full {color}"></div>'
                
                is_today = (day == today.day)
                today_class = "border-brand/40 bg-brand/5 shadow-[0_0_20px_rgba(99,102,241,0.1)]" if is_today else "border-white/5 hover:border-white/20"
                
                calendar_html += f"""
                <div class="aspect-square glass border rounded-xl p-3 flex flex-col justify-between transition-all {today_class}">
                    <span class="text-xs font-black { 'text-brand' if is_today else 'text-white/40' }">{day}</span>
                    <div class="flex gap-1 flex-wrap">
                        {indicators}
                    </div>
                </div>
                """

    content = f"""
    <div class="space-y-8">
        <div class="flex justify-between items-end">
            <div>
                <h1 class="text-3xl font-black italic tracking-tight text-white">{today.strftime('%B')} <span class="text-brand">{year}</span></h1>
                <p class="text-[10px] font-black text-muted uppercase tracking-[0.2em]">Automated Content Distribution Hub</p>
            </div>
            <div class="flex gap-2">
                <button class="px-4 py-2 glass rounded-lg text-[10px] font-black uppercase text-white opacity-50 cursor-not-allowed">&larr; Prev</button>
                <button class="px-4 py-2 glass rounded-lg text-[10px] font-black uppercase text-white opacity-50 cursor-not-allowed">Next &rarr;</button>
            </div>
        </div>
        
        <div class="grid grid-cols-7 gap-3">
            {calendar_html}
        </div>
        
        <div class="glass p-8 rounded-[2rem] border-white/5 space-y-4">
            <h3 class="text-xs font-black uppercase tracking-widest text-white">Upcoming Pipeline</h3>
            <div class="space-y-2">
                { "".join([f'<div class="flex items-center justify-between p-3 bg-white/5 rounded-xl border border-white/5 text-[10px] font-bold text-white"><div class="flex items-center gap-3"><div class="w-1.5 h-1.5 rounded-full bg-brand"></div>{p.caption[:60] if p.caption else "No Caption"}...</div><div class="text-muted tracking-widest">{p.scheduled_time.strftime("%b %d, %H:%M")}</div></div>' for p in posts if p.status == "scheduled"][:5]) or '<div class="text-center py-4 text-muted italic">No upcoming posts</div>' }
            </div>
        </div>
    </div>
    """
    
    return APP_LAYOUT_HTML.format(
        title="Calendar",
        user_name=user.name or user.email,
        org_name=org.name if org else "Personal Workspace",
        admin_link=admin_link,
        active_media="",
        content=content,
        account_options=""
    )

@router.get("/app/automations", response_class=HTMLResponse)
async def app_automations_page(
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    if not user.onboarding_complete: return RedirectResponse(url="/onboarding")
    org = db.query(Org).filter(Org.id == user.active_org_id).first()
    admin_link = '<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin Console</a>' if user.is_superadmin else ""
    
    autos = db.query(TopicAutomation).filter(TopicAutomation.org_id == user.active_org_id).all()
    
    # Fetch accounts for "New Automation" selection
    accounts = db.query(IGAccount).filter(IGAccount.org_id == user.active_org_id).all()
    account_options = "".join([f'<option value="{a.id}">{a.name} (@{a.ig_user_id})</option>' for a in accounts])
    if not accounts:
        account_options = '<option value="">No accounts connected</option>'
    
    autos_html = ""
    for a in autos:
        status_btn = f'<button onclick="toggleAuto({a.id}, {str(not a.enabled).lower()})" class="px-3 py-1 rounded-lg text-[8px] font-black uppercase tracking-widest { "bg-emerald-500/20 text-emerald-400" if a.enabled else "bg-rose-500/20 text-rose-400" }">{ "Enabled" if a.enabled else "Disabled" }</button>'
        
        autos_html += f"""
        <div class="glass p-8 rounded-[2.5rem] flex flex-col md:flex-row justify-between items-start md:items-center gap-6 group border border-white/5 hover:border-brand/40 transition-all">
          <div class="space-y-2 flex-1">
            <div class="flex items-center gap-3">
              <h3 class="text-xl font-black italic text-white tracking-tight">{a.name}</h3>
              {status_btn}
            </div>
            <p class="text-xs text-muted font-medium line-clamp-1">{a.topic_prompt}</p>
            <div class="flex gap-4 pt-2">
              <div class="text-[8px] font-black uppercase tracking-widest text-muted">Mode: <span class="text-white">{a.content_seed_mode or 'Default'}</span></div>
              <div class="text-[8px] font-black uppercase tracking-widest text-muted">Schedule: <span class="text-white">Daily @ {a.post_time_local or '09:00'}</span></div>
            </div>
          </div>
          <div class="flex gap-3">
            <button onclick='showEditModal({{
              "id": a.id, 
              "name": a.name, 
              "topic": a.topic_prompt, 
              "seed_mode": a.content_seed_mode, 
              "seed_text": a.content_seed_text or "", 
              "time": a.post_time_local or "09:00",
              "library_scope": a.library_scope
            }})' class="px-6 py-3 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest text-white hover:bg-white/10 transition-all">Configure</button>
            <button onclick="runNow({a.id})" class="px-6 py-3 bg-brand/20 text-brand rounded-xl font-black text-[10px] uppercase tracking-widest border border-brand/20 hover:bg-brand/30 transition-all">Run Now</button>
          </div>
        </div>
        """

    content = f"""
    <div class="space-y-8">
      <div class="flex justify-between items-end">
        <div>
          <h1 class="text-3xl font-black italic tracking-tight text-white">Neural <span class="text-brand">Automations</span></h1>
          <p class="text-[10px] font-black text-muted uppercase tracking-[0.3em]">Neural Loop Configuration</p>
        </div>
        <button onclick="showNewAutoModal()" class="px-8 py-4 bg-brand rounded-2xl font-black text-xs uppercase tracking-widest text-white shadow-xl shadow-brand/20">+ New Automation</button>
      </div>

      <div class="space-y-4">
        {autos_html or '<div class="py-20 text-center glass rounded-[3rem]"><p class="text-muted font-black text-[10px] uppercase tracking-widest">No active automations. Run the onboarding wizard or create one manually.</p></div>'}
      </div>
    </div>

    <!-- Edit Modal -->
    <div id="editModal" class="fixed inset-0 bg-black/80 backdrop-blur-sm z-[100] hidden flex items-center justify-center p-6">
      <div class="glass max-w-2xl w-full p-10 rounded-[2.5rem] space-y-6 max-h-[90vh] overflow-y-auto">
        <h2 class="text-2xl font-black italic text-white tracking-tight">Configure <span class="text-brand">Intelligence</span></h2>
        
        <input type="hidden" id="editId">
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="space-y-4">
            <div class="space-y-1">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Automation Name</label>
              <input type="text" id="editName" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand">
            </div>
            <div class="space-y-1">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Core Topic Prompt</label>
              <textarea id="editTopic" rows="3" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand"></textarea>
            </div>
            <div class="space-y-1">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Posting Time (Local)</label>
              <input type="time" id="editTime" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand">
            </div>
          </div>

          <div class="space-y-4">
            <div class="space-y-1">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Content Seed Strategy (BYOS)</label>
              <select id="editSeedMode" onchange="toggleSeedText()" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand appearance-none text-white">
                <option value="none">None (Pure AI Generation)</option>
                <option value="manual">Manual Seed (Provide text below)</option>
                <option value="auto_library">Auto-Library (Retrieve from knowledge base)</option>
              </select>
            </div>
            <div id="seedTextGroup" class="space-y-1 hidden">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Manual Seed Text</label>
              <textarea id="editSeedText" rows="5" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-[10px] outline-none focus:ring-2 focus:ring-brand placeholder-white/20" placeholder="Paste the content you want the AI to ground its generation on..."></textarea>
            </div>
            
            <div class="space-y-2 pt-2">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Library Sourcing Scope</label>
              <div class="flex gap-4">
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" id="editScopePrebuilt" class="w-4 h-4 rounded border-white/10 bg-white/5 text-brand focus:ring-brand">
                  <span class="text-[10px] font-bold text-white uppercase">Prebuilt Packs</span>
                </label>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" id="editScopeOrg" class="w-4 h-4 rounded border-white/10 bg-white/5 text-brand focus:ring-brand">
                  <span class="text-[10px] font-bold text-white uppercase">Org Library</span>
                </label>
              </div>
            </div>
            <div class="p-4 bg-brand/10 border border-brand/20 rounded-xl">
              <p class="text-[9px] font-bold text-brand uppercase tracking-widest leading-relaxed">
                <svg class="w-3 h-3 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                Tip: Auto-Library performs semantic keyword retrieval from your uploaded documents to ground the LLM.
              </p>
            </div>
          </div>
        </div>

        <div class="flex gap-4 pt-4 border-t border-white/5">
          <button onclick="hideEditModal()" class="flex-1 py-4 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest">Discard</button>
          <button onclick="saveAutomation()" class="flex-[2] py-4 bg-brand rounded-xl font-black text-[10px] uppercase tracking-widest text-white shadow-lg shadow-brand/20">Apply Changes</button>
        </div>
      </div>
    </div>

    <!-- New Automation Modal -->
    <div id="newAutoModal" class="fixed inset-0 bg-black/80 backdrop-blur-sm z-[100] hidden flex items-center justify-center p-6">
      <div class="glass max-w-2xl w-full p-10 rounded-[2.5rem] space-y-6 max-h-[90vh] overflow-y-auto">
        <h2 class="text-2xl font-black italic text-white tracking-tight">New <span class="text-brand">Neural Automation</span></h2>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div class="space-y-4">
            <div class="space-y-1">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Automation Name</label>
              <input type="text" id="newName" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand" placeholder="e.g. Daily Motivation">
            </div>
            <div class="space-y-1">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Target Instagram Account</label>
              <select id="newAccount" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand appearance-none text-white">
                {account_options}
              </select>
            </div>
            <div class="space-y-1">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Core Topic Prompt</label>
              <textarea id="newTopic" rows="3" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand" placeholder="Describe the focus of this automation..."></textarea>
            </div>
          </div>

          <div class="space-y-4">
            <div class="space-y-1">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Posting Time (Local)</label>
              <input type="time" id="newTime" value="09:00" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand">
            </div>
            <div class="space-y-1">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Content Strategy</label>
              <select id="newSeedMode" onchange="toggleNewSeedText()" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand appearance-none text-white">
                <option value="none">None (Pure AI Generation)</option>
                <option value="manual">Manual Seed (Provide text below)</option>
                <option value="auto_library">Auto-Library (Knowledge Base)</option>
              </select>
            </div>
            <div id="newSeedTextGroup" class="space-y-1 hidden">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Manual Seed Text</label>
              <textarea id="newSeedText" rows="5" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-[10px] outline-none focus:ring-2 focus:ring-brand placeholder-white/20" placeholder="Paste the content you want the AI to ground its generation on..."></textarea>
            </div>
            
            <div class="space-y-2 pt-2">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Library Sourcing Scope</label>
              <div class="flex gap-4">
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" id="newScopePrebuilt" checked class="w-4 h-4 rounded border-white/10 bg-white/5 text-brand focus:ring-brand">
                  <span class="text-[10px] font-bold text-white uppercase">Prebuilt Packs</span>
                </label>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" id="newScopeOrg" checked class="w-4 h-4 rounded border-white/10 bg-white/5 text-brand focus:ring-brand">
                  <span class="text-[10px] font-bold text-white uppercase">Org Library</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        <div class="flex gap-4 pt-4 border-t border-white/5">
          <button onclick="hideNewAutoModal()" class="flex-1 py-4 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest">Discard</button>
          <button onclick="saveNewAutomation()" class="flex-[2] py-4 bg-brand rounded-xl font-black text-[10px] uppercase tracking-widest text-white shadow-lg shadow-brand/20">Create Intelligence</button>
        </div>
      </div>
    </div>

    <script>
      function showNewAutoModal() {{
        document.getElementById('newAutoModal').classList.remove('hidden');
      }}

      function hideNewAutoModal() {{
        document.getElementById('newAutoModal').classList.add('hidden');
      }}

      function toggleNewSeedText() {{
        const mode = document.getElementById('newSeedMode').value;
        const group = document.getElementById('newSeedTextGroup');
        if (mode === 'manual') group.classList.remove('hidden');
        else group.classList.add('hidden');
      }}

      async function saveNewAutomation() {{
        const scope = [];
        if (document.getElementById('newScopePrebuilt').checked) scope.push('prebuilt');
        if (document.getElementById('newScopeOrg').checked) scope.push('org_library');

        const payload = {{
          name: document.getElementById('newName').value,
          ig_account_id: parseInt(document.getElementById('newAccount').value),
          topic_prompt: document.getElementById('newTopic').value,
          content_seed_mode: document.getElementById('newSeedMode').value,
          content_seed_text: document.getElementById('newSeedText').value,
          post_time_local: document.getElementById('newTime').value,
          library_scope: scope,
          enabled: true
        }};

        if (!payload.name || !payload.topic_prompt || isNaN(payload.ig_account_id)) {{
          alert('Please fill Name, Topic, and select an Account');
          return;
        }}
        
        const btn = event.target;
        btn.disabled = true;
        btn.textContent = 'CREATING...';

        try {{
          const res = await fetch('/automations', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(payload)
          }});
          if (res.ok) window.location.reload();
          else alert('Creation failed');
        }} catch(e) {{ alert('Network error'); }}
        finally {{ btn.disabled = false; btn.textContent = 'Create Intelligence'; }}
      }}

      function showEditModal(data) {{
        document.getElementById('editId').value = data.id;
        document.getElementById('editName').value = data.name;
        document.getElementById('editTopic').value = data.topic;
        document.getElementById('editSeedMode').value = data.seed_mode || 'none';
        document.getElementById('editSeedText').value = data.seed_text;
        document.getElementById('editTime').value = data.time;
        
        const scope = data.library_scope || [];
        document.getElementById('editScopePrebuilt').checked = scope.includes('prebuilt');
        document.getElementById('editScopeOrg').checked = scope.includes('org_library');

        toggleSeedText();
        document.getElementById('editModal').classList.remove('hidden');
      }}

      function hideEditModal() {{
        document.getElementById('editModal').classList.add('hidden');
      }}

      function toggleSeedText() {{
        const mode = document.getElementById('editSeedMode').value;
        const group = document.getElementById('seedTextGroup');
        if (mode === 'manual') group.classList.remove('hidden');
        else group.classList.add('hidden');
      }}

      async function saveAutomation() {{
        const id = document.getElementById('editId').value;
        const scope = [];
        if (document.getElementById('editScopePrebuilt').checked) scope.push('prebuilt');
        if (document.getElementById('editScopeOrg').checked) scope.push('org_library');

        const payload = {{
          name: document.getElementById('editName').value,
          topic_prompt: document.getElementById('editTopic').value,
          content_seed_mode: document.getElementById('editSeedMode').value,
          content_seed_text: document.getElementById('editSeedText').value,
          post_time_local: document.getElementById('editTime').value,
          library_scope: scope
        }};
        
        const btn = event.target;
        btn.disabled = true;
        btn.textContent = 'SAVING...';

        try {{
          const res = await fetch(`/automations/${{id}}`, {{
            method: 'PATCH',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(payload)
          }});
          if (res.ok) window.location.reload();
          else alert('Save failed');
        }} catch(e) {{ alert('Network error'); }}
        finally {{ btn.disabled = false; btn.textContent = 'Apply Changes'; }}
      }}

      async function toggleAuto(id, enabled) {{
        try {{
          const res = await fetch(`/automations/${{id}}`, {{
            method: 'PATCH',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ enabled: enabled }})
          }});
          if (res.ok) window.location.reload();
        }} catch(e) {{ alert('Error toggling'); }}
      }}

      async function runNow(id) {{
        if (!confirm('Run this automation immediately? This will create a post in your pipeline.')) return;
        const btn = event.target;
        btn.disabled = true;
        btn.textContent = 'RUNNING...';
        try {{
          const res = await fetch(`/automations/${{id}}/run`, {{ method: 'POST' }});
          if (res.ok) alert('Neural loop triggered. Check dashboard for the new post.');
          else alert('Run failed');
        }} catch(e) {{ alert('Network error'); }}
        finally {{ btn.disabled = false; btn.textContent = 'Run Now'; }}
      }}
    </script>
    """
    
    return APP_LAYOUT_HTML.format(
        title="Automations",
        user_name=user.name or user.email,
        org_name=org.name if org else "Personal Workspace",
        admin_link=admin_link,
        active_dashboard="",
        active_calendar="",
        active_automations="active",
        active_library="",
        active_media="",
        content=content,
        account_options=account_options
    )

@router.get("/app/media", response_class=HTMLResponse)
async def app_media_page(
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    if not user.onboarding_complete: return RedirectResponse(url="/onboarding")
    org = db.query(Org).filter(Org.id == user.active_org_id).first()
    admin_link = '<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin Console</a>' if user.is_superadmin else ""
    
    content = """
    <div class="space-y-6">
        <h1 class="text-3xl font-black italic tracking-tight text-white">Media <span class="text-brand">Vault</span></h1>
        <div class="glass p-12 rounded-[3rem] border-brand/20 bg-brand/5 text-center">
            <h3 class="text-xl font-black italic text-white mb-2">Asset Intelligence</h3>
            <p class="text-muted text-sm max-w-md mx-auto">The media library is being synchronized with your generated assets. Check back shortly for full access.</p>
        </div>
    </div>
    """
    
    return APP_LAYOUT_HTML.format(
        title="Media",
        user_name=user.name or user.email,
        org_name=org.name if org else "Personal Workspace",
        admin_link=admin_link,
        active_dashboard="",
        active_calendar="",
        active_automations="",
        active_library="",
        active_media="active",
        content=content,
        account_options=""
    )

@router.get("/app/library", response_class=HTMLResponse)
async def app_library_page(
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db)
):
    if not user:
        return RedirectResponse(url="/login")
    if not user.onboarding_complete: return RedirectResponse(url="/onboarding")
    org_id = user.active_org_id
    org = db.query(Org).filter(Org.id == org_id).first()
    admin_link = '<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin Console</a>' if user.is_superadmin else ""
    
    from app.models import SourceDocument
    docs = db.query(SourceDocument).filter(SourceDocument.org_id == org_id).order_by(SourceDocument.created_at.desc()).all()
    
    # 1. User Knowledge Base (Docs)
    docs_html = ""
    for d in docs:
        icon = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>'
        if d.source_type == "url":
            icon = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>'
        
        docs_html += f"""
        <div class="glass p-6 rounded-2xl flex justify-between items-center group">
          <div class="flex items-center gap-4">
            <div class="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center text-brand border border-white/10">
              {icon}
            </div>
            <div>
              <div class="text-xs font-black text-white uppercase tracking-wider">{d.title}</div>
              <div class="text-[8px] font-bold text-muted uppercase tracking-[0.2em]">{d.source_type} • {d.created_at.strftime("%b %d, %Y")}</div>
            </div>
          </div>
          <div class="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <button onclick="deleteDoc({d.id})" class="p-2 text-rose-400 hover:text-rose-300"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></button>
          </div>
        </div>
        """

    # 2. Default System Library (Prebuilt Packs)
    prebuilt_packs = load_prebuilt_packs()
    prebuilt_html = ""
    for pack in prebuilt_packs:
        items_html = ""
        for item in pack.get("items", []):
            tags_html = "".join([f'<span class="px-2 py-0.5 bg-brand/10 text-brand rounded text-[8px] font-bold uppercase mr-1">{t}</span>' for t in item.get("tags", [])])
            items_html += f"""
            <div class="p-5 border-b border-white/5 last:border-0 hover:bg-white/2 transition-colors">
              <p class="text-[11px] text-white/90 leading-relaxed font-medium">"{item['text']}"</p>
              <div class="flex justify-between items-end mt-3">
                <div class="text-[9px] font-black text-brand uppercase tracking-widest">{item.get('reference')}</div>
                <div class="flex">{tags_html}</div>
              </div>
            </div>
            """
        
        prebuilt_html += f"""
        <div class="glass overflow-hidden rounded-3xl mb-6">
          <div class="px-6 py-4 bg-white/5 border-b border-white/10">
            <h3 class="text-sm font-black italic text-white tracking-tight">{pack['name']}</h3>
            <p class="text-[9px] font-bold text-muted uppercase tracking-widest">{pack.get('description')}</p>
          </div>
          <div class="divide-y divide-white/5">
            {items_html}
          </div>
        </div>
        """

    content = f"""
    <div class="space-y-8">
      <div class="flex justify-between items-end">
        <div>
          <h1 class="text-3xl font-black italic tracking-tight text-white">Source <span class="text-brand">Library</span></h1>
          <p class="text-[10px] font-black text-muted uppercase tracking-[0.3em]">Knowledge Base Management</p>
        </div>
        <div id="actionButtons" class="flex gap-4">
          <input type="file" id="pdfUpload" class="hidden" accept=".pdf,.txt" onchange="handleFileUpload(this)">
          <button onclick="document.getElementById('pdfUpload').click()" class="px-6 py-3 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest text-white hover:bg-white/10 transition-all">Upload PDF/TXT</button>
          <button onclick="showUrlModal()" class="px-6 py-3 bg-brand rounded-xl font-black text-[10px] uppercase tracking-widest text-white shadow-xl shadow-brand/20">Add URL Source</button>
        </div>
      </div>

      <!-- Tab Switcher -->
      <div class="flex border-b border-white/5">
        <button onclick="switchTab('user')" id="tabUser" class="px-8 py-4 text-[10px] font-black uppercase tracking-[0.2em] text-white border-b-2 border-brand relative transition-all">My Knowledge Base</button>
        <button onclick="switchTab('default')" id="tabDefault" class="px-8 py-4 text-[10px] font-black uppercase tracking-[0.2em] text-muted border-b-2 border-transparent hover:text-white transition-all">Default Library</button>
      </div>

      <div id="paneUser" class="space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 gap-4">
          {docs_html or '<div class="col-span-full py-20 text-center glass rounded-3xl"><p class="text-muted font-black text-[10px] uppercase tracking-widest">Your library is empty. Upload your first source to begin grounded generation.</p></div>'}
        </div>
      </div>

      <div id="paneDefault" class="hidden animate-in fade-in slide-in-from-bottom-2 duration-500">
        <div class="max-w-3xl">
          {prebuilt_html or '<div class="py-20 text-center glass rounded-3xl"><p class="text-muted font-black text-[10px] uppercase tracking-widest">Default prebuilt packs are currently unavailable.</p></div>'}
        </div>
      </div>
    </div>

    <!-- URL Modal -->
    <div id="urlModal" class="fixed inset-0 bg-black/80 backdrop-blur-sm z-[100] hidden flex items-center justify-center p-6">
      <div class="glass max-w-lg w-full p-10 rounded-[2.5rem] space-y-6">
        <h2 class="text-2xl font-black italic text-white tracking-tight">Add <span class="text-brand">URL Source</span></h2>
        <div class="space-y-4">
          <div class="space-y-1">
            <label class="text-[10px] font-black uppercase tracking-widest text-muted">Document Title</label>
            <input type="text" id="urlTitle" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand" placeholder="e.g. My Organization Handbook">
          </div>
          <div class="space-y-1">
            <label class="text-[10px] font-black uppercase tracking-widest text-muted">URL Address</label>
            <input type="url" id="urlAddress" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand" placeholder="https://example.com/source">
          </div>
        </div>
        <div class="flex gap-4 pt-4">
          <button onclick="hideUrlModal()" class="flex-1 py-4 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest">Cancel</button>
          <button onclick="submitUrl()" class="flex-[2] py-4 bg-brand rounded-xl font-black text-[10px] uppercase tracking-widest text-white">Extract & Ingest</button>
        </div>
      </div>
    </div>

    <script>
      function showUrlModal() {{ document.getElementById('urlModal').classList.remove('hidden'); }}
      function hideUrlModal() {{ document.getElementById('urlModal').classList.add('hidden'); }}

      function switchTab(tab) {{
        const userTab = document.getElementById('tabUser');
        const defaultTab = document.getElementById('tabDefault');
        const userPane = document.getElementById('paneUser');
        const defaultPane = document.getElementById('paneDefault');
        const actionBtn = document.getElementById('actionButtons');

        if (tab === 'user') {{
          userTab.classList.add('text-white', 'border-brand');
          userTab.classList.remove('text-muted', 'border-transparent');
          defaultTab.classList.add('text-muted', 'border-transparent');
          defaultTab.classList.remove('text-white', 'border-brand');
          userPane.classList.remove('hidden');
          defaultPane.classList.add('hidden');
          actionBtn.classList.remove('opacity-0', 'pointer-events-none');
        }} else {{
          defaultTab.classList.add('text-white', 'border-brand');
          defaultTab.classList.remove('text-muted', 'border-transparent');
          userTab.classList.add('text-muted', 'border-transparent');
          userTab.classList.remove('text-white', 'border-brand');
          defaultPane.classList.remove('hidden');
          userPane.classList.add('hidden');
          actionBtn.classList.add('opacity-0', 'pointer-events-none');
        }}
      }}

      async function submitUrl() {{
        const title = document.getElementById('urlTitle').value;
        const url = document.getElementById('urlAddress').value;
        if (!url) return alert('URL is required');

        const btn = event.target;
        btn.disabled = true;
        btn.textContent = 'INGESTING...';

        try {{
          const res = await fetch('/library/add_url', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ title: title, source_type: 'url', original_url: url }})
          }});
          if (res.ok) window.location.reload();
          else alert('Extraction failed');
        }} catch(e) {{ alert('Network error'); }}
        finally {{ btn.disabled = false; btn.textContent = 'Extract & Ingest'; }}
      }}

      async function handleFileUpload(input) {{
        if (!input.files.length) return;
        const file = input.files[0];
        const formData = new FormData();
        formData.append('file', file);
        
        try {{
          const res = await fetch('/library/upload', {{
            method: 'POST',
            body: formData
          }});
          if (res.ok) window.location.reload();
          else alert('Upload failed');
        }} catch(e) {{ alert('Network error'); }}
      }}

      async function deleteDoc(id) {{
        if (!confirm('Are you sure you want to delete this source and all its knowledge chunks?')) return;
        try {{
          const res = await fetch(`/library/${{id}}`, {{ method: 'DELETE' }});
          if (res.ok) window.location.reload();
        }} catch(e) {{ alert('Network error'); }}
      }}
    </script>
    """
    
    return APP_LAYOUT_HTML.format(
        title="Library",
        user_name=user.name or user.email,
        org_name=org.name if org else "Personal Workspace",
        admin_link=admin_link,
        active_dashboard="",
        active_calendar="",
        active_automations="",
        active_library="active",
        active_media="",
        content=content,
        account_options=""
    )

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(user: User = Depends(require_user)):
    if user.onboarding_complete:
        return RedirectResponse(url="/app")
    return ONBOARDING_HTML

from pydantic import BaseModel
class OnboardingFinalize(BaseModel):
    orgName: str
    igUserId: str
    igAccessToken: str
    contentMode: str
    autoTopic: str
    autoTime: str

@router.post("/api/onboarding/finalize")
async def finalize_onboarding(
    payload: OnboardingFinalize,
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    # 1. Ensure Org exists or create it
    org = db.query(Org).filter(OrgMember.user_id == user.id).first()
    if not org:
        org = Org(name=payload.orgName or f"{user.name}'s Workspace")
        db.add(org)
        db.flush()
        membership = OrgMember(org_id=org.id, user_id=user.id, role="owner")
        db.add(membership)
    else:
        # Update existing org name if provided
        org = db.query(Org).filter(Org.id == OrgMember.org_id).filter(OrgMember.user_id == user.id).first()
        if payload.orgName: org.name = payload.orgName

    # 2. Connect IG Account (Optional)
    if payload.igUserId or payload.igAccessToken:
        ig_acc = db.query(IGAccount).filter(IGAccount.org_id == org.id).first()
        if not ig_acc:
            ig_acc = IGAccount(
                org_id=org.id,
                name=f"IG: {payload.igUserId}" if payload.igUserId else "IG Account",
                ig_user_id=payload.igUserId,
                access_token=payload.igAccessToken,
                daily_post_time=payload.autoTime or "09:00"
            )
            db.add(ig_acc)
            db.flush()
        
        # 3. Create Automation
        auto = db.query(TopicAutomation).filter(TopicAutomation.org_id == org.id).first()
        if not auto:
            auto = TopicAutomation(
                org_id=org.id,
                ig_account_id=ig_acc.id,
                name="Daily Intelligence Feed",
                topic_prompt=payload.autoTopic or "Daily wisdom and news relevant to our niche.",
                source_mode=payload.contentMode if payload.contentMode != "auto_library" else "none",
                content_seed_mode="auto_library" if payload.contentMode == "auto_library" else "none",
                post_time_local=payload.autoTime or "09:00",
                enabled=True,
                approval_mode="needs_manual_approve"
            )
            db.add(auto)

    # 4. Create Content Profile
    profile = db.query(ContentProfile).filter(ContentProfile.org_id == org.id).first()
    if not profile:
        profile = ContentProfile(
            org_id=org.id,
            name="Default Brand Voice",
            focus_description=payload.autoTopic or "General focus",
            source_mode=payload.contentMode
        )
        db.add(profile)

    # 5. Mark Onboarding Complete
    user.onboarding_complete = True
    user.active_org_id = org.id
    db.commit()

    return {"status": "success"}
