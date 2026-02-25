from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.db import get_db
from app.models import User, Org, OrgMember, IGAccount, Post, TopicAutomation, ContentProfile
from app.security.auth import require_user
from app.security.rbac import get_current_org_id
from typing import Optional
import json
from datetime import datetime, timedelta

router = APIRouter()

# --- HTML TEMPLATES ---

APP_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Dashboard | Social Media LLM</title>
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
          <a href="/app" class="text-[10px] font-black uppercase tracking-widest nav-link active py-5">Dashboard</a>
          <a href="/app/calendar" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-muted hover:text-white transition-colors">Calendar</a>
          <a href="/app/automations" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-muted hover:text-white transition-colors">Automations</a>
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
    <!-- Header -->
    <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div>
        <h1 class="text-3xl font-black italic tracking-tight text-white">System <span class="text-brand">Overview</span></h1>
        <p class="text-xs font-bold text-muted uppercase tracking-widest">Real-time intelligence feed</p>
      </div>
      <div class="flex gap-2">
        {admin_cta}
        <button class="px-6 py-3 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest text-white hover:bg-white/10 transition-all">New Post</button>
        <button class="px-6 py-3 bg-brand rounded-xl font-black text-[10px] uppercase tracking-widest text-white shadow-xl shadow-brand/20">Sync Accounts</button>
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
              <button class="flex-1 py-3 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest hover:bg-white/10 transition-all">Edit</button>
              <button class="flex-1 py-3 bg-brand/20 text-brand rounded-xl font-black text-[10px] uppercase tracking-widest border border-brand/20">Approve</button>
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
  </main>

  <script>
    async function logout() {
      await fetch('/auth/logout', { method: 'POST' });
      window.location.href = '/';
    }
  </script>
</body>
</html>
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
              <div onclick="onboardingData.contentMode='sunnah'; renderStep()" class="p-6 rounded-2xl border ${onboardingData.contentMode==='sunnah' ? 'border-indigo-500 bg-indigo-500/10' : 'border-white/10 bg-white/5'} cursor-pointer">
                <h4 class="font-black italic text-sm">Sunnah Library</h4>
                <p class="text-[10px] text-muted uppercase mt-1">Ground content in authentic Islamic wisdom.</p>
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

# --- ROUTES ---

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
        Post.created_at >= datetime.now() - timedelta(days=7)
    ).scalar() or 0
    
    account_count = db.query(func.count(IGAccount.id)).filter(IGAccount.org_id == org_id).scalar() or 0
    
    # Next Post
    next_post = db.query(Post).filter(
        Post.org_id == org_id,
        Post.status == "scheduled",
        Post.scheduled_time > datetime.now()
    ).order_by(Post.scheduled_time.asc()).first()

    next_post_countdown = "No posts scheduled"
    next_post_time = "--:--"
    next_post_caption = "Create your first automation to see content here."
    next_post_media = '<div class="w-full h-full flex items-center justify-center text-muted font-black text-xs uppercase italic">No Media</div>'
    
    if next_post:
        diff = next_post.scheduled_time - datetime.now()
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        next_post_countdown = f"{diff.days}d {hours}h {minutes}m"
        next_post_time = next_post.scheduled_time.strftime("%b %d, %H:%M")
        next_post_caption = next_post.caption or "No caption generated."
        if next_post.media_url:
            next_post_media = f'<img src="{next_post.media_url}" class="w-full h-full object-cover">'

    # Calendar Construction (Next 7 days)
    calendar_headers = ""
    calendar_days = ""
    today = datetime.now()
    for i in range(7):
        day = today + timedelta(days=i)
        calendar_headers += f'<div class="py-2 text-[8px] font-black text-center uppercase tracking-widest text-muted">{day.strftime("%a")}</div>'
        
        # Count posts for this day
        day_start = datetime(day.year, day.month, day.day)
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
          <div class="text-[8px] font-black uppercase tracking-widest {status_color}">{p.status}</div>
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

    html = APP_DASHBOARD_HTML.format(
        user_name=user.name or user.email,
        admin_link=admin_link,
        admin_cta=admin_cta,
        connection_cta=connection_cta,
        org_name=org.name if org else "Personal Workspace",
        weekly_post_count=weekly_post_count,
        account_count=account_count,
        next_post_countdown=next_post_countdown,
        next_post_time=next_post_time,
        next_post_caption=next_post_caption,
        next_post_media=next_post_media,
        calendar_headers=calendar_headers,
        calendar_days=calendar_days,
        recent_posts=recent_posts_html or '<div class="text-center py-6 text-[10px] font-black uppercase text-muted italic">No recent activity</div>'
    )
    return html

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
                source_mode=payload.contentMode,
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
