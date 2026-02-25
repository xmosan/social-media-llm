from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, Org, OrgMember, ContactMessage
from app.security.auth import get_current_user
from app.security.rbac import require_superadmin

router = APIRouter(prefix="/admin", tags=["admin"])

LOGIN_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Login | Social Media LLM</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-slate-50 min-h-screen flex items-center justify-center p-6">
  <div class="max-w-md w-full bg-white rounded-3xl shadow-xl p-8 border border-slate-100">
    <div class="text-center mb-8">
      <h1 class="text-2xl font-black bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">Social SaaS</h1>
      <p class="text-sm text-slate-500 mt-2 font-medium">Sign in to your dashboard</p>
    </div>
    <form id="loginForm" class="space-y-6">
      <div>
        <label class="block text-xs font-bold text-slate-700 uppercase tracking-widest mb-2">Email</label>
        <input type="email" id="email" required class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none text-sm transition-all" placeholder="name@company.com">
      </div>
      <div>
        <label class="block text-xs font-bold text-slate-700 uppercase tracking-widest mb-2">Password</label>
        <input type="password" id="password" required class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none text-sm transition-all" placeholder="••••••••">
      </div>
      <div id="errorMsg" class="hidden text-xs font-bold text-red-600 text-center bg-red-50 p-3 rounded-lg border border-red-100"></div>
      <button type="submit" class="w-full bg-indigo-600 text-white rounded-xl py-3.5 font-black hover:bg-indigo-700 transition-all text-sm shadow-lg shadow-indigo-200 active:scale-[0.98]">
        Authenticate
      </button>
      <div class="text-center mt-4">
        <a href="/admin/register" class="text-xs text-indigo-600 hover:text-indigo-800 font-bold hover:underline">Don't have an account? Sign up</a>
      </div>
      <div class="relative py-2">
        <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-slate-200"></div></div>
        <div class="relative flex justify-center text-xs"><span class="bg-white px-2 text-slate-500">Or</span></div>
      </div>
      <a href="/auth/google/start" class="flex w-full items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white py-3.5 text-sm font-bold text-slate-700 shadow-sm transition-all hover:bg-slate-50 hover:text-slate-900 active:scale-[0.98]">
        <svg class="h-5 w-5" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
        Continue with Google
      </a>
    </form>
  </div>
  <script>
    document.getElementById("loginForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = document.getElementById("email").value;
      const password = document.getElementById("password").value;
      const errorMsg = document.getElementById("errorMsg");
      
      try {
        const formData = new URLSearchParams();
        formData.append("username", email);
        formData.append("password", password);
        
        const res = await fetch("/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: formData
        });
        
        if (res.ok) {
          window.location.href = "/admin";
        } else {
          const data = await res.json();
          errorMsg.textContent = data.detail || "Authentication failed";
          errorMsg.classList.remove("hidden");
        }
      } catch (err) {
        errorMsg.textContent = "Network error occurred";
        errorMsg.classList.remove("hidden");
      }
    });
  </script>
</body>
</html>
"""

REGISTER_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Register | Social Media LLM</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-slate-50 min-h-screen flex items-center justify-center p-6">
  <div class="max-w-md w-full bg-white rounded-3xl shadow-xl p-8 border border-slate-100">
    <div class="text-center mb-8">
      <h1 class="text-2xl font-black bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">Join Social SaaS</h1>
      <p class="text-sm text-slate-500 mt-2 font-medium">Create your administrative account</p>
    </div>
    <form id="registerForm" class="space-y-6">
      <div>
        <label class="block text-xs font-bold text-slate-700 uppercase tracking-widest mb-2">Full Name</label>
        <input type="text" id="name" required class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none text-sm transition-all" placeholder="John Doe">
      </div>
      <div>
        <label class="block text-xs font-bold text-slate-700 uppercase tracking-widest mb-2">Email</label>
        <input type="email" id="email" required class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none text-sm transition-all" placeholder="name@company.com">
      </div>
      <div>
        <label class="block text-xs font-bold text-slate-700 uppercase tracking-widest mb-2">Password</label>
        <input type="password" id="password" required class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none text-sm transition-all" placeholder="••••••••">
      </div>
      <div id="errorMsg" class="hidden text-xs font-bold text-red-600 text-center bg-red-50 p-3 rounded-lg border border-red-100"></div>
      <button type="submit" class="w-full bg-indigo-600 text-white rounded-xl py-3.5 font-black hover:bg-indigo-700 transition-all text-sm shadow-lg shadow-indigo-200 active:scale-[0.98]">
        Create Account
      </button>
      <div class="text-center mt-4">
        <a href="/admin/login" class="text-xs text-indigo-600 hover:text-indigo-800 font-bold hover:underline">Already have an account? Sign in</a>
      </div>
    </form>
  </div>
  <script>
    document.getElementById("registerForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const payload = {
        name: document.getElementById("name").value,
        email: document.getElementById("email").value,
        password: document.getElementById("password").value
      };
      const errorMsg = document.getElementById("errorMsg");
      
      try {
        const res = await fetch("/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        
        if (res.ok) {
          window.location.href = "/admin/login";
        } else {
          const data = await res.json();
          errorMsg.textContent = data.detail || "Registration failed";
          errorMsg.classList.remove("hidden");
        }
      } catch (err) {
        errorMsg.textContent = "Network error occurred";
        errorMsg.classList.remove("hidden");
      }
    });
  </script>
</body>
</html>
  <div class="max-w-md w-full bg-surface rounded-[2.5rem] shadow-2xl p-10 border border-border">
    <div class="text-center mb-10">
      <h1 class="text-3xl font-black italic tracking-tighter text-gradient">Social Media LLM</h1>
      <p class="text-[11px] font-black text-muted uppercase tracking-widest mt-2 italic">Neural Authentication</p>
    </div>
    <form id="registerForm" class="space-y-8">
      <div>
        <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-3 ml-1">Entity Name</label>
        <input type="text" id="name" required class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border focus:ring-1 focus:ring-brand outline-none text-xs font-bold transition-all text-main" placeholder="Jane Doe">
      </div>
      <div>
        <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-3 ml-1">Email Node</label>
        <input type="email" id="email" required class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border focus:ring-1 focus:ring-brand outline-none text-xs font-bold transition-all text-main" placeholder="name@company.com">
      </div>
      <div>
        <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-3 ml-1">Access Key</label>
        <input type="password" id="password" required class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border focus:ring-1 focus:ring-brand outline-none text-xs font-bold transition-all text-main" placeholder="••••••••">
      </div>
      <div id="errorMsg" class="hidden text-[10px] font-black text-rose-500 text-center bg-rose-500/10 p-4 rounded-xl border border-rose-500/20 uppercase tracking-widest"></div>
      <button type="submit" class="btn-primary w-full py-5 text-xs tracking-widest uppercase italic">
        Create Node
      </button>

      <div class="text-center mt-4">
        <a href="/admin/login" class="text-xs text-emerald-600 hover:text-emerald-800 font-bold hover:underline">Already have an account? Log in</a>
      </div>
      <div class="relative py-2">
        <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-border"></div></div>
        <div class="relative flex justify-center text-xs"><span class="bg-surface px-2 text-muted">Or</span></div>
      </div>
      <a href="/auth/google/start" class="flex w-full items-center justify-center gap-3 rounded-xl border border-border bg-white/5 py-3.5 text-sm font-bold text-main shadow-sm transition-all hover:bg-white/10 active:scale-[0.98]">
        <svg class="h-5 w-5" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
        Sign up with Google
      </a>
    </form>
  </div>
  <script>
    document.getElementById("registerForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = document.getElementById("name").value;
      const email = document.getElementById("email").value;
      const password = document.getElementById("password").value;
      const errorMsg = document.getElementById("errorMsg");
      
      try {
        const payload = { name, email, password };
        const res = await fetch("/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        
        if (res.ok) {
          window.location.href = "/admin";
        } else {
          const data = await res.json();
          errorMsg.textContent = data.detail || "Registration failed";
          errorMsg.classList.remove("hidden");
        }
      } catch (err) {
        errorMsg.textContent = "Network error occurred";
        errorMsg.classList.remove("hidden");
      }
    });
  </script>
</body>
</html>
"""

HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Admin Overview | Social Media LLM</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <script src='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.10/index.global.min.js'></script>
  <style>
    :root {
      --brand: #6366f1;
      --brand-hover: #4f46e5;
      --main-bg: #020617;
      --surface: rgba(255, 255, 255, 0.03);
      --text-main: #ffffff;
      --text-muted: #94a3b8;
      --border: rgba(255, 255, 255, 0.1);
      --card-bg: rgba(255, 255, 255, 0.03);
    }
    body { font-family: 'Inter', sans-serif; background-color: var(--main-bg); color: var(--text-main); line-height: 1.5; }
    .ai-bg { background: radial-gradient(circle at top right, #312e81, #020617, #020617); }
    .glass { background: var(--surface); backdrop-filter: blur(12px); border: 1px solid var(--border); }
    .text-gradient { background: linear-gradient(to right, #818cf8, #c084fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .fade-in { animation: fadeIn 0.3s ease-out; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(-5px); } to { opacity: 1; transform: translateY(0); } }
    .nav-link.active { color: var(--brand); border-bottom: 2px solid var(--brand); }
    select option { background-color: #020617; color: white; }
    
    /* Toast System */
    #toast-container { position: fixed; top: 1.5rem; right: 1.5rem; z-index: 200; display: flex; flex-direction: column; gap: 0.75rem; }
    .toast { padding: 1rem 1.5rem; border-radius: 1.25rem; font-size: 0.7rem; font-weight: 900; text-transform: uppercase; letter-spacing: 0.15em; animation: slideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1); box-shadow: 0 20px 40px -10px rgba(0,0,0,0.5); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.1); max-width: 320px; white-space: pre-wrap; line-height: 1.4; }
    @keyframes slideIn { from { transform: translateX(100%) scale(0.9); opacity: 0; } to { transform: translateX(0) scale(1); opacity: 1; } }
    .toast-success { background: rgba(16, 185, 129, 0.15); color: #34d399; border-color: rgba(16, 185, 129, 0.3); }
    .toast-error { background: rgba(244, 63, 94, 0.15); color: #fb7185; border-color: rgba(244, 63, 94, 0.3); }
    .toast-info { background: rgba(99, 102, 241, 0.15); color: #818cf8; border-color: rgba(99, 102, 241, 0.3); }
    
    /* Global Input Overrides */
    select, input, textarea { background-color: rgba(255, 255, 255, 0.05) !important; color: white !important; }
    select option { background-color: #020617 !important; color: white !important; }
    input[type="range"] { -webkit-appearance: none; background: rgba(255,255,255,0.1); border: none !important; }
    
    /* Toggle & Checkbox Refinement */
    .toggle-track { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); }
    .checkbox-box { border: 1px solid rgba(255,255,255,0.3); transition: all 0.2s ease; }
    .checkbox-box:hover { border-color: var(--brand); }
    input:checked + .checkbox-bg { background-color: var(--brand); }
  </style>
</head>
<body class="ai-bg min-h-screen pb-12">
  <!-- Localhost Warning Banner -->
  <div id="localhost_warning" class="hidden bg-amber-500 text-white px-6 py-2 text-center text-xs font-black uppercase tracking-widest shadow-lg fade-in">
      ⚠️ ENVIRONMENT WARNING: LOCALHOST DETECTED. Instagram publishing will fail. Use ngrok for public tunnel.
  </div>
  <nav class="border-b border-white/5 bg-black/20 backdrop-blur-md sticky top-0 z-50 h-16">
    <div class="max-w-7xl mx-auto px-6 h-full flex justify-between items-center">
      <div class="flex items-center gap-8">
        <div class="text-lg font-black italic tracking-tighter text-gradient">SOCIAL MEDIA LLM <span class="text-[9px] text-muted not-italic font-bold tracking-widest ml-2">ADMIN</span></div>
        <div class="h-6 w-px bg-white/10"></div>
        <div class="flex items-center gap-3">
            <label class="text-[9px] font-black text-muted uppercase tracking-[0.2em]">Node</label>
            <select id="account_selector" onchange="onAccountChange()" class="bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-[10px] font-black text-white outline-none focus:ring-1 focus:ring-brand min-w-[200px] transition-all">
                <option value="">No Accounts Registered</option>
            </select>
        </div>
      </div>
      <div class="flex items-center gap-6">
        <div class="hidden md:flex items-center gap-2">
            <label class="text-[9px] font-black text-muted uppercase tracking-[0.2em]">Workspace</label>
            <select id="org_selector" onchange="onOrgChange()" class="bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-[10px] font-black text-white outline-none focus:ring-1 focus:ring-brand min-w-[150px] transition-all">
                <option value="">Loading...</option>
            </select>
        </div>
        <div class="h-6 w-px bg-white/10"></div>
        <div class="flex items-center gap-4 relative group">
           <div class="flex flex-col text-right hidden lg:block">
              <div class="text-[10px] font-black text-white uppercase tracking-wider" id="user_dropdown_name">User</div>
              <div class="text-[8px] font-bold text-muted uppercase tracking-widest" id="user_dropdown_email">email@domain.com</div>
           </div>
           <div class="w-10 h-10 rounded-2xl glass flex items-center justify-center font-black text-xs cursor-pointer text-brand hover:scale-110 transition-transform" id="user_avatar">U</div>
           <div class="absolute right-0 top-12 w-48 glass rounded-2xl shadow-2xl p-2 hidden group-hover:block fade-in z-[60]">
               <button onclick="logout()" class="w-full text-left px-4 py-3 text-[10px] font-black text-rose-400 hover:bg-rose-500/10 rounded-xl transition-all uppercase tracking-widest">
                   Terminate Session
               </button>
           </div>
        </div>
        <div class="h-px w-6 bg-white/10 rotate-90"></div>
        <div class="flex gap-2">
            <button onclick="toggleSettings()" class="w-10 h-10 rounded-2xl glass flex items-center justify-center text-muted hover:text-white hover:scale-110 transition-all" title="Workspace Hub">
                <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"/></svg>
            </button>
            <button id="run_scheduler_btn" onclick="runGlobalScheduler()" class="w-10 h-10 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-500 hover:bg-emerald-500 hover:text-white hover:scale-110 transition-all" title="Force Scheduler">
                <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
            </button>
            <button id="platform_btn" onclick="togglePlatformPanel()" class="hidden w-10 h-10 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 items-center justify-center text-indigo-500 hover:bg-indigo-500 hover:text-white hover:scale-110 transition-all" title="Platform Management">
                <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/></svg>
            </button>
        </div>
      </div>
    </div>
  </nav>
  <main class="max-w-7xl mx-auto px-6 py-10 space-y-10">
    
    <!-- Settings Drawer -->
    <div id="settings_panel" class="hidden fixed inset-0 bg-black/60 z-[100] backdrop-blur-md flex justify-end" onclick="if(event.target === this) toggleSettings()">
        <div class="w-full max-w-md glass h-full shadow-2xl p-8 flex flex-col overflow-y-auto" onclick="event.stopPropagation()">
            <div class="flex justify-between items-center mb-8">
                <div>
                    <h2 class="text-2xl font-black text-white italic tracking-tight">Workspace <span class="text-brand">Hub</span></h2>
                    <p class="text-[10px] font-black text-muted uppercase tracking-widest mt-1">Social Architecture</p>
                </div>
                <button onclick="toggleSettings()" class="p-2 rounded-2xl glass hover:bg-white/10 transition-colors text-muted hover:text-white">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
            <div class="space-y-10">
                <section class="p-5 bg-emerald-500/10 rounded-2xl border border-emerald-500/20 hidden">
                    <div class="flex items-center gap-3 mb-4">
                        <span class="w-6 h-6 rounded-full bg-emerald-600 text-white flex items-center justify-center text-xs font-bold shadow-sm">✓</span>
                        <h3 class="text-sm font-black text-emerald-400 uppercase tracking-widest">Authenticated</h3>
                    </div>
                </section>
                
                <section>
                    <div class="flex items-center gap-3 mb-6">
                        <span class="w-8 h-8 rounded-2xl glass text-brand flex items-center justify-center text-xs font-black">01</span>
                        <h3 class="text-[10px] font-black text-white uppercase tracking-[0.2em]">Active Nodes</h3>
                    </div>
                    <div id="settings_accounts_list" class="space-y-3">
                        <!-- Populated by JS -->
                    </div>
                </section>
                
                <div class="h-px bg-white/5"></div>
                
                <!-- STEP 2: ADD IG -->
                <section>
                    <div class="flex items-center gap-3 mb-6">
                        <span class="w-8 h-8 rounded-2xl glass text-brand flex items-center justify-center text-xs font-black">02</span>
                        <h3 class="text-[10px] font-black text-white uppercase tracking-[0.2em]">Register Slot</h3>
                    </div>
                    <div class="space-y-5">
                        <div>
                            <label class="block text-[9px] font-black text-muted uppercase tracking-[0.2em] mb-2">Display Name</label>
                            <input id="new_acc_name" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-white/10 text-xs font-bold text-white outline-none focus:ring-1 focus:ring-brand transition-all" placeholder="e.g. Luxury Real Estate"/>
                        </div>
                        <div class="grid grid-cols-1 gap-5">
                            <div>
                                <label class="flex items-center gap-2 text-[9px] font-black text-muted uppercase tracking-[0.2em] mb-2">
                                    IG User ID
                                    <button onclick="toggleGuideModal()" class="text-brand hover:text-white transition-colors">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                        </svg>
                                    </button>
                                </label>
                                <input id="new_acc_ig_id" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-white/10 text-xs font-bold text-white outline-none focus:ring-1 focus:ring-brand font-mono transition-all" placeholder="Numerical ID"/>
                            </div>
                            <div>
                                <label class="flex items-center gap-2 text-[9px] font-black text-muted uppercase tracking-[0.2em] mb-2">
                                    Access Token
                                    <button onclick="toggleGuideModal()" class="text-brand hover:text-white transition-colors">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                        </svg>
                                    </button>
                                </label>
                                <textarea id="new_acc_token" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-white/10 text-[10px] font-bold text-white outline-none focus:ring-1 focus:ring-brand font-mono min-h-[120px] transition-all" placeholder="Paste long-lived token..."></textarea>
                            </div>
                        </div>
                        <button id="add_acc_btn" onclick="addAccount()" class="w-full bg-brand text-white rounded-2xl py-5 text-[10px] font-black uppercase tracking-widest italic shadow-xl shadow-brand/20 hover:scale-[1.02] active:scale-95 transition-all">Initialize Slot</button>
                    </div>
                    <div id="add_acc_msg" class="mt-4 text-[10px] font-black text-center h-4 text-brand uppercase tracking-widest italic"></div>
                </section>
                
                <div id="auth_error_box" class="hidden p-5 bg-rose-500/10 text-rose-400 rounded-2xl text-[10px] font-black border border-rose-500/20 uppercase tracking-widest"></div>
            </div>
        </div>
    </div>

    <!-- Instagram Setup Guide Modal -->
    <div id="guide_modal" class="hidden fixed inset-0 bg-black/80 z-[200] backdrop-blur-md flex items-center justify-center p-4">
        <div class="glass rounded-[3rem] shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh] border border-white/10">
            <div class="px-10 py-8 border-b border-white/5 flex justify-between items-center bg-white/5">
                <div class="flex items-center gap-4">
                    <div class="w-12 h-12 rounded-2xl glass text-brand flex items-center justify-center">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    </div>
                    <div>
                        <h3 class="text-2xl font-black text-white italic tracking-tight">Setup <span class="text-brand">Protocol</span></h3>
                        <p class="text-[9px] font-black tracking-[0.3em] text-muted uppercase">Meta API Integration</p>
                    </div>
                </div>
                <button onclick="toggleGuideModal()" class="w-10 h-10 rounded-2xl glass text-muted hover:text-white flex items-center justify-center transition-all">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
            </div>
            
            <div class="p-10 overflow-y-auto space-y-10">
                <div class="flex gap-6">
                    <div class="flex-shrink-0 w-10 h-10 rounded-2xl glass text-brand font-black flex items-center justify-center text-sm">01</div>
                    <div>
                        <h4 class="font-black text-white text-xs uppercase tracking-widest mb-2">Meta Developer App</h4>
                        <p class="text-xs text-muted leading-relaxed">Access <a href="https://developers.facebook.com/" target="_blank" class="text-brand font-bold hover:underline">developers.facebook.com</a>. Initialize a new Professional App with the "Business" type classification.</p>
                    </div>
                </div>

                <div class="flex gap-6">
                    <div class="flex-shrink-0 w-10 h-10 rounded-2xl glass text-brand font-black flex items-center justify-center text-sm">02</div>
                    <div>
                        <h4 class="font-black text-white text-xs uppercase tracking-widest mb-2">Integrate Graph API</h4>
                        <p class="text-xs text-muted leading-relaxed">Link a functioning Facebook Page tied to an Instagram Professional account. Activate the Instagram Graph API product.</p>
                    </div>
                </div>

                <div class="flex gap-6">
                    <div class="flex-shrink-0 w-10 h-10 rounded-2xl glass text-brand font-black flex items-center justify-center text-sm">03</div>
                    <div>
                        <h4 class="font-black text-white text-xs uppercase tracking-widest mb-2">Token Generation</h4>
                        <p class="text-xs text-muted leading-relaxed">In the Explorer tool, generate a token with the following critical permissions:</p>
                        <div class="mt-3 bg-black/40 border border-white/5 p-4 rounded-2xl text-[10px] font-bold text-brand font-mono leading-loose">
                            instagram_basic, instagram_content_publish, pages_show_list, pages_read_engagement
                        </div>
                    </div>
                </div>

                <div class="flex gap-6">
                    <div class="flex-shrink-0 w-10 h-10 rounded-2xl glass text-brand font-black flex items-center justify-center text-sm">04</div>
                    <div>
                        <h4 class="font-black text-white text-xs uppercase tracking-widest mb-2">Token Expansion</h4>
                        <p class="text-xs text-muted leading-relaxed">Use the Access Token Tool to "Extend Access Token". This creates a 60-day persistent variant required for stable background publishing.</p>
                    </div>
                </div>

                <div class="flex gap-6">
                    <div class="flex-shrink-0 w-10 h-10 rounded-2xl glass text-brand font-black flex items-center justify-center text-sm">05</div>
                    <div>
                        <h4 class="font-black text-white text-xs uppercase tracking-widest mb-2">Identity Resolution</h4>
                        <p class="text-xs text-muted leading-relaxed">Query <code>me/accounts?fields=instagram_business_account</code> to obtain your numerical Instagram Business ID. This is the final cryptographic component.</p>
                    </div>
                </div>
            </div>
            
            <div class="p-8 glass border-t border-white/5 flex justify-end">
                <button onclick="toggleGuideModal()" class="px-8 py-4 bg-white/5 border border-white/10 text-white text-[10px] font-black uppercase tracking-widest rounded-2xl hover:bg-white/10 transition-all">
                    Acknowledge Setup
                </button>
            </div>
        </div>
    </div>
    </div>
    <!-- New Automation Modal -->
    <div id="auto_modal" class="hidden fixed inset-0 bg-black/80 z-[110] backdrop-blur-md flex items-center justify-center p-4">
        <div class="glass rounded-[3rem] shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh] border border-white/10">
            <div class="px-10 py-8 border-b border-white/5 flex justify-between items-center bg-white/5">
                <h3 class="text-2xl font-black text-white italic tracking-tight">Topic <span class="text-brand">Automation</span></h3>
                <button onclick="hideCreateAuto()" class="w-10 h-10 rounded-2xl glass text-muted hover:text-white flex items-center justify-center transition-all">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
            </div>
            <div class="p-10 overflow-y-auto space-y-8">
                <input type="hidden" id="edit_auto_id" value=""/>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <div class="space-y-8">
                        <div>
                            <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em] mb-3">Internal Identifier</label>
                            <input id="auto_name" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-white/10 text-xs font-bold text-white outline-none focus:ring-1 focus:ring-brand transition-all" placeholder="e.g. Daily Hadith Series"/>
                        </div>
                        <div>
                            <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em] mb-3">Neural Prompt</label>
                            <textarea id="auto_topic" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-white/10 text-[11px] font-bold text-white outline-none focus:ring-1 focus:ring-brand min-h-[140px] transition-all" placeholder="Specify core logic for AI content generation..."></textarea>
                        </div>
                    </div>
                    
                    <div class="space-y-8">
                        <div>
                            <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em] mb-3">Target Profile</label>
                            <select id="auto_profile_id" class="w-full px-5 py-4 rounded-2xl bg-brand/10 border border-brand/20 text-xs font-black text-brand outline-none transition-all">
                                <option value="">Generic Logic</option>
                            </select>
                        </div>
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-[9px] font-black text-muted uppercase tracking-widest mb-3">Style Preset</label>
                                <select id="auto_style" class="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-[10px] font-bold text-white outline-none">
                                    <option value="islamic_reminder">Islamic Reminder</option>
                                    <option value="educational">Educational</option>
                                    <option value="motivational">Motivational</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-[9px] font-black text-muted uppercase tracking-widest mb-3">Tone</label>
                                <select id="auto_tone" class="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-[10px] font-bold text-white outline-none">
                                    <option value="short">Short & Punchy</option>
                                    <option value="medium" selected>Balanced</option>
                                    <option value="long">Educational</option>
                                </select>
                            </div>
                        </div>
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-[9px] font-black text-muted uppercase tracking-widest mb-3">Linguistics</label>
                                <select id="auto_lang" class="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-[10px] font-bold text-white outline-none">
                                    <option value="english">Pure English</option>
                                    <option value="arabic_mix" selected>Eng + Arb Mix</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-[9px] font-black text-muted uppercase tracking-widest mb-3">Execution Time</label>
                                <input type="time" id="auto_time" class="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-[10px] font-bold text-white outline-none transition-all" value="09:00"/>
                            </div>
                        </div>
                        <div>
                            <label class="block text-[9px] font-black text-muted uppercase tracking-[0.2em] mb-3 flex justify-between">
                                <span>Intelligence Density</span>
                                <span id="creativity_val" class="text-brand font-black tracking-widest">3 / 5</span>
                            </label>
                            <input type="range" id="auto_creativity" min="1" max="5" value="3" oninput="document.getElementById('creativity_val').innerText = this.value + ' / 5'" class="w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer accent-brand">
                        </div>
                    </div>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div class="glass border border-white/5 p-6 rounded-[2rem] space-y-4">
                        <div class="flex items-center justify-between">
                            <div>
                                <div class="text-[10px] font-black text-white uppercase tracking-widest leading-none">Library Core</div>
                                <div class="text-[8px] font-bold text-muted uppercase tracking-widest mt-1">Asset synchronization</div>
                            </div>
                             <label class="relative inline-flex items-center cursor-pointer">
                                 <input type="checkbox" id="auto_use_library" class="sr-only peer" checked>
                                 <div class="w-11 h-6 bg-white/10 border border-white/5 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[3px] after:left-[3px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-brand"></div>
                             </label>
                        </div>
                        <div class="space-y-4 pt-2">
                             <select id="auto_image_mode" class="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-[10px] font-bold text-white outline-none [&_option]:bg-black [&_option]:text-white">
                                <option value="reuse_last_upload">Reuse Last Upload</option>
                                <option value="quote_card" selected>Generate Quote Card</option>
                                <option value="ai_generated">AI Genesis (DALL-E)</option>
                                <option value="library_fixed">Fixed Repository Asset</option>
                             </select>
                             <div class="grid grid-cols-2 gap-3">
                                <input type="text" id="auto_media_tag_query" class="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-[10px] font-bold text-white outline-none" placeholder="Tag Query"/>
                                <input type="number" id="auto_lookback" class="w-full px-4 py-3 rounded-xl bg-white/5 border border-white/10 text-[10px] font-bold text-white outline-none" value="30"/>
                             </div>
                        </div>
                    </div>

                    <div class="bg-brand/5 border border-brand/20 p-6 rounded-[2rem] space-y-4">
                        <div class="flex items-center justify-between">
                            <div>
                                <div class="text-[10px] font-black text-white uppercase tracking-widest leading-none">Neural Filters</div>
                                <div class="text-[8px] font-bold text-muted uppercase tracking-widest mt-1">Logic overrides</div>
                            </div>
                             <label class="relative inline-flex items-center cursor-pointer">
                                 <input type="checkbox" id="auto_enabled" class="sr-only peer" checked>
                                 <div class="w-11 h-6 bg-white/10 border border-white/5 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[3px] after:left-[3px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500"></div>
                             </label>
                        </div>
                        <div class="space-y-3 pt-2">
                             <div class="flex items-center gap-3">
                                 <input type="checkbox" id="auto_arabic" class="sr-only peer">
                                 <label for="auto_arabic" class="flex items-center gap-3 cursor-pointer group">
                                     <div class="w-5 h-5 rounded-lg border border-white/30 flex items-center justify-center group-hover:border-brand/50 transition-all bg-white/5">
                                         <div class="w-2.5 h-2.5 rounded-sm bg-brand opacity-0 peer-checked:opacity-100 transition-all"></div>
                                     </div>
                                     <span class="text-[10px] font-black text-muted uppercase tracking-widest group-hover:text-white transition-all">Enable Arabic Mix</span>
                                 </label>
                             </div>
                        </div>
                    </div>
                </div>

                <div class="bg-indigo-500/5 border border-indigo-500/10 p-6 rounded-[2rem] space-y-4">
                    <div class="flex items-center justify-between">
                        <div>
                            <div class="text-[10px] font-black text-white uppercase tracking-widest leading-none">AI Image Genesis</div>
                            <div class="text-[8px] font-bold text-muted uppercase tracking-widest mt-1">DALL-E Integration</div>
                        </div>
                        <label class="relative inline-flex items-center cursor-pointer">
                            <input type="checkbox" id="auto_use_ai_image" class="sr-only peer">
                            <div class="w-11 h-6 bg-white/10 border border-white/5 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[3px] after:left-[3px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-500"></div>
                        </label>
                    </div>
                    <div id="ai_image_prompt_container" class="hidden animate-in fade-in slide-in-from-top-2 duration-300">
                        <textarea id="auto_ai_image_prompt" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-white/10 text-[10px] font-bold text-white outline-none focus:ring-1 focus:ring-brand min-h-[80px]" placeholder="Visual directives..."></textarea>
                    </div>
                </div>

                <div class="bg-emerald-500/5 border border-emerald-500/10 p-6 rounded-[2rem] space-y-4">
                   <div class="flex items-center justify-between">
                        <div>
                            <div class="text-[10px] font-black text-white uppercase tracking-widest leading-none">Content Seed</div>
                            <div class="text-[8px] font-bold text-muted uppercase tracking-widest mt-1">Direct source text for quoting</div>
                        </div>
                   </div>
                   <div>
                        <textarea id="auto_content_seed" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-white/10 text-[10px] font-bold text-white outline-none focus:ring-1 focus:ring-brand min-h-[100px]" placeholder="Paste a Hadith, Quote, or specific text you want to work with..."></textarea>
                   </div>
                </div>
            </div>
            <div class="p-8 glass border-t border-white/5 flex gap-3">
                <button onclick="hideCreateAuto()" class="flex-1 px-6 py-4 rounded-2xl glass text-[10px] font-black uppercase tracking-widest text-muted hover:text-white transition-all">Decline</button>
                <button onclick="saveAutomation()" class="flex-[2] px-6 py-4 rounded-2xl bg-brand text-white text-[10px] font-black uppercase tracking-widest italic shadow-xl shadow-brand/20 hover:scale-[1.02] active:scale-95 transition-all">Synchronize Logic</button>
            </div>
        </div>
    </div>
    <!-- Post Editor Modal -->
    <div id="post_modal" class="hidden fixed inset-0 bg-black/80 z-[120] backdrop-blur-md flex items-center justify-center p-4">
        <div class="glass rounded-[3rem] shadow-2xl w-full max-w-5xl overflow-hidden flex flex-col max-h-[90vh] border border-white/10">
            <div class="px-10 py-6 border-b border-white/5 flex justify-between items-center bg-white/5">
                <div class="flex items-center gap-4">
                    <h3 class="text-2xl font-black text-white italic tracking-tight">Post <span class="text-brand">Composer</span></h3>
                    <span id="post_edit_status" class="px-4 py-1.5 rounded-full text-[9px] font-black uppercase tracking-[0.2em] bg-white/10 text-muted border border-white/5">Neural Draft</span>
                </div>
                <button onclick="hidePostEditor()" class="w-10 h-10 rounded-2xl glass text-muted hover:text-white flex items-center justify-center transition-all">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
            </div>
            
            <div class="flex-1 overflow-hidden flex flex-col lg:flex-row">
                <!-- Media Preview -->
                <div class="lg:w-[45%] bg-black/40 flex items-center justify-center p-8 group relative border-r border-white/5">
                    <img id="post_edit_img" src="" class="max-w-full max-h-full object-contain shadow-2xl rounded-2xl border border-white/10"/>
                    <div class="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end justify-center pb-10">
                        <div class="flex gap-3 scale-95 group-hover:scale-100 transition-transform">
                            <button onclick="regeneratePostImage()" class="px-6 py-3 bg-brand text-white text-[10px] font-black uppercase tracking-widest rounded-xl shadow-xl hover:bg-indigo-500 transition-all">Synthetic Regen</button>
                            <label class="px-6 py-3 bg-white/10 border border-white/20 text-white text-[10px] font-black uppercase tracking-widest rounded-xl hover:bg-white/20 cursor-pointer backdrop-blur-md transition-all">
                                Replace Source
                                <input type="file" id="post_media_replace" class="hidden" onchange="attachMediaToPost(this)"/>
                            </label>
                        </div>
                    </div>
                </div>
                
                <!-- Content Editor -->
                <div class="lg:w-[55%] p-10 overflow-y-auto space-y-8">
                    <input type="hidden" id="post_edit_id" value=""/>
                    <div class="space-y-4">
                        <div class="flex justify-between items-end">
                            <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em]">Synaptic Caption</label>
                            <button onclick="regeneratePostCaption()" class="text-[9px] font-black text-brand uppercase tracking-widest hover:underline flex items-center gap-2">
                                <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                                AI Refine
                            </button>
                        </div>
                        <textarea id="post_edit_caption" class="w-full px-6 py-5 rounded-[2rem] bg-white/5 border border-white/10 text-xs font-bold text-white outline-none focus:ring-1 focus:ring-brand min-h-[220px] transition-all" placeholder="Enter post narrative..."></textarea>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                        <div>
                            <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em] mb-3">Semantic Index (#)</label>
                            <textarea id="post_edit_hashtags" class="w-full px-5 py-4 rounded-xl bg-white/5 border border-white/10 text-[10px] font-mono text-brand outline-none focus:ring-1 focus:ring-brand min-h-[80px]" placeholder="#tag #index"></textarea>
                        </div>
                        <div class="space-y-6">
                            <div>
                                <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em] mb-3">Alt Description</label>
                                <input id="post_edit_alt" class="w-full px-5 py-4 rounded-xl bg-white/5 border border-white/10 text-[10px] font-bold text-white outline-none transition-all" placeholder="Accessibility data..."/>
                            </div>
                            <div>
                                <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em] mb-3">Temporal Trigger (UTC)</label>
                                <input type="datetime-local" id="post_edit_time" class="w-full px-5 py-4 rounded-xl bg-white/5 border border-white/10 text-[10px] font-bold text-white outline-none transition-all"/>
                            </div>
                        </div>
                    </div>
                    
                    <div id="post_edit_flags" class="flex flex-wrap gap-2 pt-4"></div>
                </div>
            </div>
            
            <div class="p-8 glass border-t border-white/5 flex gap-4 justify-between items-center">
                <button onclick="deletePostUI()" class="px-8 py-4 rounded-2xl border border-rose-500/20 bg-rose-500/5 text-rose-500 text-[10px] font-black uppercase tracking-widest hover:bg-rose-500/10 transition-all">Terminate Post</button>
                <div class="flex gap-3">
                    <button onclick="hidePostEditor()" class="px-8 py-4 rounded-2xl glass text-[10px] font-black uppercase tracking-widest text-muted hover:text-white transition-all">Cancel</button>
                    <button id="post_publish_now_btn" onclick="publishPostNow()" class="hidden px-8 py-4 rounded-2xl bg-white text-black text-[10px] font-black uppercase tracking-widest hover:bg-slate-200 transition-all">Execute Now</button>
                    <button onclick="savePost()" class="px-10 py-4 rounded-2xl bg-brand text-white text-[10px] font-black uppercase tracking-widest italic shadow-xl shadow-brand/20 hover:scale-[1.02] active:scale-95 transition-all">Commit Changes</button>
                </div>
            </div>
        </div>
    </div>
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-10 items-start">
        <!-- 1) Upload Section -->
        <div class="lg:col-span-4 lg:sticky lg:top-28 max-h-[calc(100vh-140px)] overflow-y-auto no-scrollbar space-y-6 pb-10">
          <section class="glass rounded-[3rem] border border-white/5 p-10 shadow-2xl">
            <h2 class="text-2xl font-black mb-8 flex items-center gap-3 text-white italic tracking-tight underline decoration-brand decoration-4 underline-offset-8">
              New Post <span class="text-brand">Composition</span>
            </h2>
            <div class="space-y-8">
              <div id="selected_acc_box" class="p-6 bg-white/5 border border-white/10 rounded-2xl">
                <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em] mb-3">Synaptic Target</label>
                <div id="active_account_display" class="text-xs font-black text-brand italic">Ready for deployment...</div>
              </div>
              <div class="space-y-3">
                  <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em]">Directives</label>
                  <textarea id="source_text" class="w-full px-6 py-5 rounded-[2.5rem] bg-white/5 border border-white/10 text-xs font-bold text-white outline-none focus:ring-1 focus:ring-brand min-h-[160px] resize-none transition-all placeholder:text-white/10" placeholder="What should the AI intelligence generate?"></textarea>
              </div>
              <div class="space-y-4">
                  <div class="flex items-center justify-between">
                      <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em]">Visual Source</label>
                      <div class="flex bg-white/5 p-1 rounded-xl border border-white/10">
                          <button onclick="setIntakeMode('local')" id="intake_mode_local" class="px-3 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-widest transition-all bg-brand text-white">Local</button>
                          <button onclick="setIntakeMode('ai')" id="intake_mode_ai" class="px-3 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-widest transition-all text-muted hover:text-white">AI Genesis</button>
                      </div>
                  </div>
                  
                  <input type="hidden" id="intake_use_ai" value="false">

                  <div id="local_upload_zone" class="relative border-2 border-dashed border-white/10 rounded-[2.5rem] p-10 hover:border-brand/40 transition-all group cursor-pointer bg-white/5">
                      <input id="image" type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer" onchange="updateFileName(this)"/>
                      <div class="text-center">
                          <svg xmlns="http://www.w3.org/2000/svg" class="mx-auto h-10 w-10 text-white/10 mb-4 group-hover:text-brand transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                          </svg>
                          <div id="file_name_display" class="text-[10px] font-black text-muted uppercase tracking-widest">Select Visual Source</div>
                      </div>
                  </div>

                  <div id="ai_genesis_zone" class="hidden relative border-2 border-dashed border-indigo-500/20 rounded-[2.5rem] p-10 bg-indigo-500/5 items-center justify-center flex-col text-center">
                      <div class="w-12 h-12 rounded-2xl bg-indigo-500/20 flex items-center justify-center text-indigo-400 mb-4 mx-auto animate-pulse">
                          <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                      </div>
                      <div class="text-[10px] font-black text-indigo-300 uppercase tracking-widest">Neural Image Manifestation</div>
                      <div class="text-[8px] font-bold text-indigo-400/60 uppercase tracking-widest mt-2">DALL-E will visualize your Directives</div>
                  </div>
              </div>
              <div class="grid grid-cols-1 gap-4 pt-4">
                  <button id="intake_btn" onclick="uploadPost()" class="bg-brand text-white rounded-[2rem] py-6 font-black uppercase tracking-[0.3em] italic hover:scale-[1.02] active:scale-95 transition-all shadow-2xl shadow-brand/20 text-xs">Add New Post</button>
                  <button onclick="resetUpload()" class="glass text-muted rounded-[2rem] py-4 font-black uppercase tracking-widest hover:text-white transition-all text-[9px]">Reset Logical State</button>
              </div>
              <div id="upload_msg" class="text-center text-[9px] font-black uppercase h-4 tracking-[0.2em] text-brand italic"></div>
            </div>
          </section>
        </div>

    <!-- 2) Feed Section -->
    <div class="lg:col-span-8 flex flex-col gap-8">
      <section class="glass rounded-[3rem] border border-white/5 p-10 shadow-2xl min-h-[700px]">
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-8 mb-10 pb-8 border-b border-white/5">
            <div class="flex items-center gap-8 overflow-x-auto no-scrollbar">
                <button onclick="switchTab('feed')" id="tab_feed" class="text-2xl font-black italic tracking-tight text-white border-b-4 border-brand pb-2 transition-all">
                   Feed
                </button>
                <button onclick="switchTab('calendar')" id="tab_calendar" class="text-2xl font-black italic tracking-tight text-muted hover:text-white transition-all pb-2">
                   Schedule
                </button>
                <button onclick="switchTab('automations')" id="tab_automations" class="text-2xl font-black italic tracking-tight text-muted hover:text-white transition-all pb-2">
                   Neural
                </button>
                <button onclick="switchTab('profiles')" id="tab_profiles" class="text-2xl font-black italic tracking-tight text-muted hover:text-white transition-all pb-2">
                   Profiles
                </button>
                <button onclick="switchTab('library')" id="tab_library" class="text-2xl font-black italic tracking-tight text-muted hover:text-white transition-all pb-2">
                   Core
                </button>
                <button onclick="switchTab('media')" id="tab_media" class="text-2xl font-black italic tracking-tight text-muted hover:text-white transition-all pb-2">
                   Assets
                </button>
            </div>
            
            <div id="feed_controls" class="flex items-center gap-3">
                <select id="status_filter" onchange="refreshAll()" class="px-6 py-3 rounded-2xl bg-white/5 border border-white/10 text-[9px] font-black uppercase tracking-widest text-brand outline-none cursor-pointer hover:bg-white/10 transition-all">
                    <option value="">Full Trace</option>
                    <option value="submitted">Ingested</option>
                    <option value="drafted">Neural Draft</option>
                    <option value="needs_review">Human Verification</option>
                    <option value="scheduled">Scheduled</option>
                    <option value="published">Deployed</option>
                    <option value="failed">Error Trace</option>
                </select>
            </div>
            <div id="calendar_controls" class="hidden">
                <button onclick="refreshAll()" class="w-12 h-12 rounded-2xl glass text-muted hover:text-brand flex items-center justify-center transition-all">
                    <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                </button>
            </div>
            <div id="automations_controls" class="hidden">
                <button onclick="showCreateAuto()" class="bg-brand text-white px-8 py-3 rounded-2xl text-[9px] font-black uppercase tracking-widest italic shadow-xl shadow-brand/20 hover:scale-[1.02] active:scale-95 transition-all">New Neural Pattern</button>
            </div>
            <div id="profiles_controls" class="hidden">
                <button onclick="showCreateProfile()" class="bg-brand text-white px-8 py-3 rounded-2xl text-[9px] font-black uppercase tracking-widest italic shadow-xl shadow-brand/20 hover:scale-[1.02] active:scale-95 transition-all">New Profile</button>
            </div>
            <div id="library_controls" class="hidden flex items-center gap-3">
                <input type="text" id="library_search" oninput="loadLibrary()" placeholder="Filter Repository..." class="px-6 py-3 rounded-2xl bg-white/5 border border-white/10 text-[9px] font-black uppercase tracking-widest text-white outline-none focus:ring-1 focus:ring-brand transition-all"/>
                <button onclick="seedDemoContent()" class="bg-brand/10 text-brand px-6 py-3 rounded-2xl text-[9px] font-black uppercase tracking-widest hover:bg-brand/20 transition-all border border-brand/20 italic">Initialize Core</button>
            </div>
            <div id="media_controls" class="hidden">
                <label class="bg-brand text-white px-8 py-3 rounded-2xl text-[9px] font-black uppercase tracking-widest italic cursor-pointer shadow-xl shadow-brand/20 hover:scale-[1.02] active:scale-95 transition-all">
                    Upload Source
                    <input type="file" id="media_upload_input" class="hidden" onchange="uploadMedia(this)"/>
                </label>
            </div>
        </div>

        <div id="feed_view">
            <div id="stats" class="grid grid-cols-2 md:grid-cols-6 gap-4 mb-12"></div>
            <div id="error" class="hidden mb-10 p-6 rounded-[2rem] bg-rose-500/10 text-rose-400 text-[10px] font-black uppercase tracking-[0.2em] border border-rose-500/20 animate-pulse italic"></div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-10" id="list"></div>
        </div>
        <div id="automations_view" class="hidden space-y-10">
            <div id="auto_list" class="grid grid-cols-1 gap-8"></div>
        </div>
        <div id="profiles_view" class="hidden space-y-10">
            <div id="profile_list" class="grid grid-cols-1 md:grid-cols-2 gap-8"></div>
        </div>
        <div id="calendar_view" class="hidden">
            <div id="calendar_el" class="bg-white/5 border border-white/10 p-8 rounded-[2.5rem] min-h-[600px] text-white"></div>
        </div>
        <div id="library_view" class="hidden space-y-10">
            <div id="library_list" class="grid grid-cols-1 md:grid-cols-2 gap-8"></div>
        </div>
        <div id="media_view" class="hidden space-y-10">
            <div id="media_list" class="grid grid-cols-2 md:grid-cols-4 gap-6"></div>
        </div>
      </section>
    </div>
  </div>

  <!-- Custom Dialog Modals -->
  <div id="custom_dialog_container" class="hidden fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <!-- Confirm Dialog -->
      <div id="custom_confirm_box" class="hidden glass rounded-[2.5rem] shadow-2xl w-full max-w-md border border-white/10 p-10 flex flex-col items-center text-center animate-in fade-in zoom-in duration-300">
          <div class="w-16 h-16 rounded-3xl bg-brand/10 flex items-center justify-center text-brand mb-6">
              <svg class="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
          </div>
          <h4 class="text-xl font-black text-white italic tracking-tight mb-4">Confirm Action</h4>
          <p id="custom_confirm_msg" class="text-xs font-bold text-muted leading-relaxed mb-10"></p>
          <div class="flex gap-4 w-full">
              <button id="custom_confirm_cancel" class="flex-1 px-6 py-4 rounded-2xl glass text-[10px] font-black uppercase tracking-widest text-muted hover:text-white transition-all">Decline</button>
              <button id="custom_confirm_ok" class="flex-1 px-6 py-4 rounded-2xl bg-brand text-white text-[10px] font-black uppercase tracking-widest italic shadow-xl shadow-brand/20 hover:scale-[1.05] active:scale-95 transition-all">Sychronize</button>
          </div>
      </div>

      <!-- Prompt Dialog -->
      <div id="custom_prompt_box" class="hidden glass rounded-[2.5rem] shadow-2xl w-full max-w-md border border-white/10 p-10 flex flex-col items-center text-center animate-in fade-in zoom-in duration-300">
          <div class="w-16 h-16 rounded-3xl bg-indigo-500/10 flex items-center justify-center text-indigo-400 mb-6">
              <svg class="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
          </div>
          <h4 class="text-xl font-black text-white italic tracking-tight mb-4">Input Required</h4>
          <p id="custom_prompt_msg" class="text-xs font-bold text-muted leading-relaxed mb-6"></p>
          <input type="text" id="custom_prompt_input" class="w-full px-6 py-4 rounded-2xl bg-white/5 border border-white/10 text-xs font-bold text-white outline-none focus:ring-1 focus:ring-brand mb-10 transition-all" placeholder="Enter logic sequence..."/>
          <div class="flex gap-4 w-full">
              <button id="custom_prompt_cancel" class="flex-1 px-6 py-4 rounded-2xl glass text-[10px] font-black uppercase tracking-widest text-muted hover:text-white transition-all">Abeyance</button>
              <button id="custom_prompt_ok" class="flex-1 px-6 py-4 rounded-2xl bg-indigo-500 text-white text-[10px] font-black uppercase tracking-widest italic shadow-xl shadow-indigo-500/20 hover:scale-[1.05] active:scale-95 transition-all">Fulfill</button>
          </div>
      </div>
  </div>

    <!-- Platform Drawer -->
    <!-- Platform Drawer -->
    <div id="platform_panel" class="hidden fixed inset-0 bg-black/80 z-[130] backdrop-blur-md flex justify-end" onclick="if(event.target === this) togglePlatformPanel()">
        <div class="w-full max-w-4xl glass h-full shadow-2xl p-12 flex flex-col overflow-y-auto border-l border-white/5" onclick="event.stopPropagation()">
            <div class="flex justify-between items-center mb-10">
                <div>
                    <h2 class="text-3xl font-black text-white italic tracking-tight">System <span class="text-brand">Nodes</span></h2>
                    <p class="text-[9px] font-black tracking-[0.3em] text-muted uppercase mt-2">Global Access Management</p>
                </div>
                <button onclick="togglePlatformPanel()" class="w-12 h-12 rounded-2xl glass text-muted hover:text-white flex items-center justify-center transition-all">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
            </div>
            
            <div class="overflow-hidden rounded-[2rem] border border-white/5 bg-white/5">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="bg-white/5 border-b border-white/5">
                            <th class="py-5 px-6 text-[9px] font-black uppercase tracking-[0.2em] text-muted">Entity</th>
                            <th class="py-5 px-6 text-[9px] font-black uppercase tracking-[0.2em] text-muted">Primary Route</th>
                            <th class="py-5 px-6 text-[9px] font-black uppercase tracking-[0.2em] text-muted">Nodes Mapping</th>
                            <th class="py-5 px-6 text-[9px] font-black uppercase tracking-[0.2em] text-muted text-right">Directives</th>
                        </tr>
                    </thead>
                    <tbody id="platform_user_table" class="divide-y divide-white/5 text-[11px] font-bold text-white">
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- Content Profile Modal -->
    <div id="profile_modal" class="hidden fixed inset-0 bg-black/80 z-[140] backdrop-blur-md flex items-center justify-center p-4">
        <div class="glass rounded-[3.5rem] shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh] border border-white/10">
            <div class="px-10 py-8 border-b border-white/5 flex justify-between items-center bg-white/5">
                <h3 class="text-2xl font-black text-white italic tracking-tight">Identity <span class="text-brand">Protocol</span></h3>
                <button onclick="hideCreateProfile()" class="w-10 h-10 rounded-2xl glass text-muted hover:text-white flex items-center justify-center transition-all">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
            </div>
            <div class="p-10 overflow-y-auto space-y-10">
                <input type="hidden" id="edit_profile_id" value=""/>
                
                <div class="bg-brand/10 p-6 rounded-[2rem] border border-brand/20">
                    <label class="block text-[9px] font-black text-brand uppercase tracking-[0.3em] mb-4">Neural Architecture Presets</label>
                    <div class="flex flex-wrap gap-2">
                        <button onclick="seedProfile('islamic_education')" class="px-4 py-2 bg-white/5 border border-white/10 text-white text-[9px] font-black uppercase tracking-widest rounded-xl hover:bg-brand hover:text-white transition-all">Islamic Core</button>
                        <button onclick="seedProfile('fitness_coach')" class="px-4 py-2 bg-white/5 border border-white/10 text-white text-[9px] font-black uppercase tracking-widest rounded-xl hover:bg-brand hover:text-white transition-all">Vitality</button>
                        <button onclick="seedProfile('real_estate')" class="px-4 py-2 bg-white/5 border border-white/10 text-white text-[9px] font-black uppercase tracking-widest rounded-xl hover:bg-brand hover:text-white transition-all">Real Estate</button>
                        <button onclick="seedProfile('small_business')" class="px-4 py-2 bg-white/5 border border-white/10 text-white text-[9px] font-black uppercase tracking-widest rounded-xl hover:bg-brand hover:text-white transition-all">Commerce</button>
                        <button onclick="seedProfile('personal_branding')" class="px-4 py-2 bg-white/5 border border-white/10 text-white text-[9px] font-black uppercase tracking-widest rounded-xl hover:bg-brand hover:text-white transition-all">Creator</button>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-6">
                    <div>
                        <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em] mb-3">Identity Key</label>
                        <input id="prof_name" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-white/10 text-xs font-bold text-white outline-none focus:ring-1 focus:ring-brand transition-all" placeholder="e.g. My Brand Strategy"/>
                    </div>
                    <div>
                        <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em] mb-3">Niche Vector</label>
                        <input id="prof_niche" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-white/10 text-xs font-bold text-white outline-none focus:ring-1 focus:ring-brand transition-all" placeholder="e.g. real_estate, fitness"/>
                    </div>
                </div>
                
                <div>
                    <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em] mb-3">Focus Directive (Aura)</label>
                    <textarea id="prof_focus" class="w-full px-5 py-4 rounded-[2rem] bg-white/5 border border-white/10 text-[11px] font-bold text-white outline-none focus:ring-1 focus:ring-brand min-h-[100px] transition-all" placeholder="Specify core focus..."></textarea>
                </div>
                
                <div class="grid grid-cols-2 gap-6">
                    <div>
                        <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em] mb-3">Strategic Targets</label>
                        <textarea id="prof_goals" class="w-full px-5 py-4 rounded-[2rem] bg-white/5 border border-white/10 text-[10px] font-bold text-white outline-none focus:ring-1 focus:ring-brand min-h-[100px]" placeholder="Educate, Convert..."></textarea>
                    </div>
                    <div>
                        <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em] mb-3">Tonal Resonance</label>
                        <textarea id="prof_tone" class="w-full px-5 py-4 rounded-[2rem] bg-white/5 border border-white/10 text-[10px] font-bold text-white outline-none focus:ring-1 focus:ring-brand min-h-[100px]" placeholder="Professional, Minimalist..."></textarea>
                    </div>
                </div>
                
                <div class="grid grid-cols-2 gap-6">
                    <div>
                        <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em] mb-3">Permitted Nodes</label>
                        <input id="prof_allowed" class="w-full px-5 py-4 rounded-xl bg-white/5 border border-white/10 text-[10px] font-mono text-emerald-400 outline-none" placeholder="topic1, topic2"/>
                    </div>
                    <div>
                        <label class="block text-[9px] font-black text-muted uppercase tracking-[0.3em] mb-3">Redacted Nodes</label>
                        <input id="prof_banned" class="w-full px-5 py-4 rounded-xl bg-white/5 border border-white/10 text-[10px] font-mono text-rose-400 outline-none" placeholder="politics, drama"/>
                    </div>
                </div>
            </div>
            <div class="p-8 glass border-t border-white/5 flex justify-end gap-3">
                <button onclick="hideCreateProfile()" class="px-8 py-4 rounded-2xl glass text-[10px] font-black uppercase tracking-widest text-muted hover:text-white transition-all">Cancel</button>
                <button onclick="saveProfileWrapper()" class="px-10 py-4 bg-brand text-white rounded-2xl text-[10px] font-black uppercase tracking-widest italic shadow-xl shadow-brand/20 hover:scale-[1.02] active:scale-95 transition-all">Sync Identity</button>
            </div>
        </div>
    </div>
  </main>
<script>
async function logout() {
    await request("/auth/logout", { method: "POST" });
    window.location.href = "/admin/login";
}

let IS_SUPERADMIN = false;

async function loadProfile() {
    try {
        const j = await request("/auth/me");
        IS_SUPERADMIN = j.is_superadmin;
        if (IS_SUPERADMIN) {
            const btn = document.getElementById("platform_btn");
            btn.classList.remove("hidden");
            btn.classList.add("flex");
        }
    } catch(e) { console.error("Profile load failed", e); }
}

function togglePlatformPanel() {
    const el = document.getElementById("platform_panel");
    const isHidden = el.classList.contains("hidden");
    if (isHidden) {
        el.classList.remove("hidden");
        loadPlatformUsers();
    } else {
        el.classList.add("hidden");
    }
}

function toggleGuideModal() {
    document.getElementById("guide_modal").classList.toggle("hidden");
}

async function loadPlatformUsers() {
    const tbody = document.getElementById("platform_user_table");
    tbody.innerHTML = `<tr><td colspan="4" class="text-center py-12 text-muted font-black uppercase tracking-[0.3em] text-[10px] animate-pulse">Syncing Platform Nodes...</td></tr>`;
    try {
        const users = await request("/admin/users");
        if (users.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="text-center py-12 text-muted font-black uppercase tracking-widest text-[10px]">No active nodes found</td></tr>`;
            return;
        }
        tbody.innerHTML = users.map(u => `
            <tr class="hover:bg-white/5 transition-colors group">
                <td class="py-5 px-6 font-black text-white flex items-center gap-3">
                    <div class="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center text-[10px] border border-white/10 group-hover:border-brand/40 transition-all">${(u.name || "U")[0].toUpperCase()}</div>
                    <div class="flex flex-col">
                        <span class="text-[11px]">${esc(u.name)}</span>
                        ${u.is_superadmin ? '<span class="text-[8px] text-brand font-black uppercase tracking-widest italic">Core Admin</span>' : ''}
                    </div>
                </td>
                <td class="py-5 px-6 text-muted text-[10px] font-mono">${esc(u.email)}</td>
                <td class="py-5 px-6 text-[9px] font-black tracking-widest text-muted uppercase">${esc(u.orgs || 'Unmapped')}</td>
                <td class="py-5 px-6 text-right">
                    ${!u.is_superadmin ? `<button onclick="deleteUser(${u.id})" class="text-[9px] font-black uppercase tracking-widest text-rose-500 hover:text-rose-400 hover:underline transition-all">Terminate</button>` : '<span class="text-[9px] font-black text-white/10 uppercase tracking-widest">Protected</span>'}
                </td>
            </tr>
        `).join("");
    } catch(e) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center py-12 text-rose-500 font-black uppercase tracking-widest text-[10px]">Sync Error: ${e.message}</td></tr>`;
    }
}

async function deleteUser(id) {
    if(!await customConfirm("MANDATORY WARNING: Are you sure you want to completely erase this user? This cannot be undone.")) return;
    try {
        await request(`/admin/users/${id}`, { method: "DELETE" });
        await loadPlatformUsers();
    } catch(e) { showToast("Delete failed: " + e.message, "error"); }
}

let ACCOUNTS = [];
let ACTIVE_ACCOUNT_ID = localStorage.getItem("active_ig_id") || null;
let ACTIVE_ORG_ID = localStorage.getItem("active_org_id") || null;
let ME = null;
let ACTIVE_TAB = "feed";
let calendar = null;

function switchTab(t) {
    ACTIVE_TAB = t;
    const views = ['feed', 'automations', 'profiles', 'library', 'media', 'calendar'];
    views.forEach(v => {
        const el = document.getElementById(v + "_view");
        if(el) el.classList.toggle("hidden", v !== t);
        const ctrl = document.getElementById(v + "_controls");
        if(ctrl) ctrl.classList.toggle("hidden", v !== t);
        const tab = document.getElementById("tab_" + v);
        if(tab) tab.className = v === t ? "text-2xl font-black italic tracking-tight text-white border-b-4 border-brand pb-2 transition-all" : "text-2xl font-black italic tracking-tight text-muted hover:text-white transition-all pb-2";
    });
    
    if (t === 'calendar') {
        initCalendar();
    }
    refreshAll();
}

function showToast(msg, type = "success") {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        document.body.appendChild(container);
    }
    const t = document.createElement("div");
    t.className = `toast toast-${type} glass`;
    t.textContent = msg;
    container.appendChild(t);
    setTimeout(() => {
        t.style.opacity = '0';
        t.style.transform = 'translateX(20px)';
        t.style.transition = 'all 0.4s cubic-bezier(0.16, 1, 0.3, 1)';
        setTimeout(() => t.remove(), 400);
    }, 4000);
}

function esc(s) { return (s ?? "").toString().replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;"); }
function toggleSettings() { document.getElementById("settings_panel").classList.toggle("hidden"); }
function updateFileName(input) { 
    const file = input.files[0];
    if (file) {
        console.log(`DEBUG: Selected file - ${file.name}, Size: ${file.size} bytes, Type: ${file.type}`);
        document.getElementById("file_name_display").textContent = file.name;
    } else {
        document.getElementById("file_name_display").textContent = "Select Visual Source";
    }
}
function setIntakeMode(mode) {
    const isAi = mode === 'ai';
    document.getElementById("intake_use_ai").value = isAi;
    document.getElementById("local_upload_zone").classList.toggle("hidden", isAi);
    document.getElementById("ai_genesis_zone").classList.toggle("hidden", !isAi);
    
    document.getElementById("intake_mode_local").className = !isAi ? "px-3 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-widest transition-all bg-brand text-white" : "px-3 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-widest transition-all text-muted hover:text-white";
    document.getElementById("intake_mode_ai").className = isAi ? "px-3 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-widest transition-all bg-brand text-white" : "px-3 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-widest transition-all text-muted hover:text-white";
}
async function request(url, opts = {}) {
    console.log(`[API REQUEST] ${opts.method || "GET"} ${url}`, opts.body ? "(with body)" : "");
    let orgHeader = {};
    if (ACTIVE_ORG_ID) {
        orgHeader = { "X-Org-Id": ACTIVE_ORG_ID.toString() };
    }

    opts.headers = { 
        ...opts.headers, 
        ...orgHeader,
        "ngrok-skip-browser-warning": "69420"
    };
    try {
        const r = await fetch(url, opts);
        let j;
        try { j = await r.json(); } catch(e) { j = { detail: "Server Error (Invalid JSON)" }; }
    
    if (!r.ok) {
        if (r.status === 401) {
            document.getElementById("auth_error_box").textContent = "Redirecting to login...";
            window.location.href = "/admin/login";
        }
        throw new Error(j.detail || "Server Error " + r.status);
    }
        document.getElementById("auth_error_box").classList.add("hidden");
        return j;
    } catch(e) {
        console.error(`[API ERROR] ${url}`, e);
        throw e;
    }
}
function setError(msg) {
  const el = document.getElementById("error");
  el.classList.toggle("hidden", !msg);
  el.textContent = msg || "";
}
async function refreshAll() {
    setError("");
    checkLocalhost();
    try {
        await loadAccounts();
        if (ACTIVE_ACCOUNT_ID) {
            if (ACTIVE_TAB === 'feed') {
                await Promise.all([loadStats(), loadPosts()]);
            } else if (ACTIVE_TAB === 'automations') {
                await loadAutomations();
            } else if (ACTIVE_TAB === 'profiles') {
                await loadProfiles();
            } else if (ACTIVE_TAB === 'calendar') {
                await loadCalendarEvents();
            } else if (ACTIVE_TAB === 'media') {
                await loadMediaLibrary();
            } else {
                await loadLibrary();
            }
        } else {
            showEmptyState("no_accounts");
        }
        document.getElementById("intake_btn").disabled = !ACTIVE_ACCOUNT_ID;
    } catch(e) { console.error(e); }
}

async function loadAutomations() {
    const list = document.getElementById("auto_list");
    list.innerHTML = `<div class="py-12 text-center text-muted font-black uppercase text-[10px] tracking-[0.3em] animate-pulse">Scanning Neural Robotics...</div>`;
    try {
        const j = await request(`/automations/?ig_account_id=${ACTIVE_ACCOUNT_ID}`);
        if (!j.length) {
            list.innerHTML = `
            <div class="py-24 text-center border-2 border-dashed border-white/5 rounded-[3rem] bg-white/5">
                <p class="text-[10px] text-muted font-black uppercase tracking-[0.2em] mb-6">No Automations Established</p>
                <button onclick="showCreateAuto()" class="bg-brand text-white px-10 py-5 rounded-2xl text-[10px] font-black uppercase tracking-widest italic shadow-xl shadow-brand/20 hover:scale-105 active:scale-95 transition-all">Initialize First Pattern</button>
            </div>`;
            return;
        }
        list.innerHTML = j.map(a => renderAuto(a)).join("");
    } catch(e) { setError("Auto Error: " + e.message); }
}

function renderAuto(a) {
    const err = a.last_error ? `<p class="mt-4 text-[9px] bg-rose-500/10 text-rose-400 border border-rose-500/20 p-4 rounded-2xl font-black uppercase tracking-widest italic animate-pulse">Trace Error: ${esc(a.last_error)}</p>` : '';
    return `
    <div class="glass border border-white/5 rounded-[2.5rem] p-8 flex flex-col items-stretch group hover:bg-white/10 hover:border-white/20 transition-all duration-500">
        <div class="flex items-start justify-between mb-8">
            <div class="flex-1">
                <div class="flex items-center gap-4 mb-3">
                    <h4 class="text-xl font-black text-white italic tracking-tight">${esc(a.name)}</h4>
                    <span class="px-3 py-1 rounded-full text-[8px] font-black uppercase tracking-widest ${a.enabled ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-white/5 text-muted border border-white/10'}">${a.enabled ? 'Active' : 'Standby'}</span>
                    ${a.enrich_with_hadith ? '<span class="px-3 py-1 rounded-full text-[8px] font-black uppercase tracking-widest bg-brand/10 text-brand border border-brand/20">Enriched</span>' : ''}
                </div>
                <p class="text-[10px] text-muted font-bold tracking-wide line-clamp-1 italic">Pattern Vector: "${esc(a.topic_prompt)}"</p>
                ${err}
            </div>
            <div class="flex items-center gap-3 opacity-60 group-hover:opacity-100 transition-opacity">
                <button onclick="triggerAuto(${a.id})" class="w-12 h-12 rounded-2xl glass text-muted hover:text-emerald-400 hover:border-emerald-500/20 flex items-center justify-center transition-all" title="Execute Once">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                </button>
                <button onclick="testLLM(${a.id}, '${esc(a.topic_prompt)}', '${a.style_preset}')" class="w-12 h-12 rounded-2xl glass text-muted hover:text-brand hover:border-brand/20 flex items-center justify-center transition-all" title="Neural Test">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.341A8.001 8.001 0 0012 4a8.001 8.001 0 00-7.428 11.341c.142.311.23.642.23.978V19a2 2 0 002 2h9a2 2 0 002-2v-2.681c0-.336.088-.667.23-.978z" /></svg>
                </button>
                <button onclick="editAuto(${JSON.stringify(a).replaceAll('"', '&quot;')})" class="w-12 h-12 rounded-2xl glass text-muted hover:text-white flex items-center justify-center transition-all" title="Modify Configuration">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                </button>
                <button onclick="deleteAuto(${a.id})" class="w-12 h-12 rounded-2xl glass text-muted hover:text-rose-500 hover:border-rose-500/20 flex items-center justify-center transition-all" title="Teardown">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                </button>
            </div>
        </div>
        <div class="flex flex-wrap gap-6 text-[10px] font-black uppercase tracking-widest text-muted border-t border-white/5 pt-6">
            <span class="flex items-center gap-2 italic"><svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>${a.post_time_local || '09:00'}</span>
            <span class="flex items-center gap-2 italic"><svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" /></svg>${a.style_preset}</span>
            <span class="flex items-center gap-2 text-brand italic">Last Epoch: ${a.last_run_at ? new Date(a.last_run_at).toLocaleDateString() : 'None'}</span>
        </div>
    </div>`;
}

function showCreateAuto() { 
    document.getElementById("edit_auto_id").value = "";
    document.getElementById("auto_modal").classList.remove("hidden"); 
}
function hideCreateAuto() { document.getElementById("auto_modal").classList.add("hidden"); }

async function saveAutomation() {
    const id = document.getElementById("edit_auto_id").value;
    const getVal = (id) => document.getElementById(id)?.value || "";
    const getNum = (id) => parseInt(document.getElementById(id)?.value) || 0;
    const getCheck = (id) => document.getElementById(id)?.checked || false;

    const payload = {
        ig_account_id: parseInt(ACTIVE_ACCOUNT_ID),
        name: getVal("auto_name"),
        topic_prompt: getVal("auto_topic"),
        style_preset: getVal("auto_style") || "islamic_reminder",
        tone: getVal("auto_tone") || "medium",
        language: getVal("auto_lang") || "english",
        post_time_local: getVal("auto_time") || "09:00",
        enabled: getCheck("auto_enabled"),
        use_content_library: getCheck("auto_use_library"),
        image_mode: getVal("auto_image_mode") || "reuse_last_upload",
        avoid_repeat_days: getNum("auto_lookback") || 30,
        include_arabic: getCheck("auto_arabic"),
        content_seed: document.getElementById("auto_content_seed")?.value || "",
        media_asset_id: getNum("auto_media_asset_id") || null,
        media_tag_query: getVal("auto_media_tag_query").split(",").map(t => t.trim()).filter(t => t),
        media_rotation_mode: "random",
        content_profile_id: getNum("auto_profile_id") || null,
        creativity_level: getNum("auto_creativity") || 3
    };
    try {
        await request(id ? `/automations/${id}` : "/automations", {
            method: id ? "PATCH" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        hideCreateAuto();
        refreshAll();
    } catch(e) { showToast("Save Failed: " + e.message, "error"); }
}

async function triggerAuto(id) {
    if(!await customConfirm("Run this automation once right now? This will create a real post (Draft or Scheduled).")) return;
    try {
        const j = await request(`/automations/${id}/run-once`, { method: "POST" });
        if (await customConfirm("Success! Automation triggered. View it in your feed now?")) {
            switchTab('feed');
        } else {
            refreshAll();
        }
    } catch(e) { showToast("Execution Failed: " + e.message, "error"); }
}

async function runGlobalScheduler() {
    if(!await customConfirm("Force the global scheduler to run immediately? This will check for due posts and publish them to Instagram.")) return;
    const btn = document.getElementById("run_scheduler_btn");
    const originalHtml = btn.innerHTML;
    try {
        btn.innerHTML = `<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg> Running...`;
        btn.disabled = true;

        const j = await request(`/automations/run-scheduler-now`, { method: "POST" });
        showToast(`Success! Published ${j.published} items.`, "success");
        
        btn.innerHTML = originalHtml;
        btn.disabled = false;
        refreshAll();
    } catch(e) { 
        showToast("Scheduler Failed: " + e.message, "error"); 
        btn.innerHTML = originalHtml;
        btn.disabled = false;
    }
}

async function testLLM(id, topic, style) {
    try {
        const btn = event.currentTarget;
        const originalHtml = btn.innerHTML;
        btn.innerHTML = `<svg class="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>`;
        btn.disabled = true;

        const res = await request(`/automations/debug/llm-test?topic=${encodeURIComponent(topic)}&style=${encodeURIComponent(style)}`);
        
        btn.innerHTML = originalHtml;
        btn.disabled = false;

        const preview = `
            AI GENERATION PREVIEW:
            
            CAPTION:
            ${res.caption}
            
            HASHTAGS:
            ${(res.hashtags || []).join(" ")}
            
            ALT TEXT:
            ${res.alt_text}
        `;
        showToast("Preview Manifest Generated", "success");
        console.log(preview);
    } catch(e) { 
        showToast("LLM Test Failed: " + e.message, "error");
        refreshAll();
    }
}

// --- CALENDAR LOGIC ---
async function initCalendar() {
    if (calendar) return;
    const calendarEl = document.getElementById('calendar_el');
    calendar = new FullCalendar.Calendar(calendarEl, {
      initialView: 'dayGridMonth',
      headerToolbar: {
        left: 'prev,next today',
        center: 'title',
        right: 'dayGridMonth,timeGridWeek'
      },
      editable: true,
      eventClick: function(info) {
        openPostEditor(info.event.id);
      },
      eventDrop: async function(info) {
        if(!await customConfirm(`Reschedule to ${info.event.start.toISOString()}?`)) {
            info.revert();
            return;
        }
        try {
            await request(`/posts/${info.event.id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scheduled_time: info.event.start.toISOString() })
            });
            refreshAll();
        } catch(e) { 
            showToast(e.message, "error"); 
            info.revert();
        }
      }
    });
    calendar.render();
}

async function loadCalendarEvents() {
    if (!calendar) return;
    try {
        const j = await request(`/posts?ig_account_id=${ACTIVE_ACCOUNT_ID}&limit=200`);
        const events = j.map(p => ({
            id: p.id,
            title: (p.caption || 'Untitled').substring(0, 30) + '...',
            start: p.scheduled_time || p.created_at,
            backgroundColor: getPostColor(p.status),
            borderColor: 'transparent'
        }));
        calendar.removeAllEvents();
        calendar.addEventSource(events);
    } catch(e) { console.error(e); }
}

function getPostColor(status) {
    const colors = {
        published: '#10b981',
        scheduled: '#6366f1',
        needs_review: '#f43f5e',
        drafted: '#3b82f6',
        failed: '#94a3b8'
    };
    return colors[status] || '#94a3b8';
}

// --- POST EDITOR LOGIC ---
async function openPostEditor(postId) {
    try {
        const p = await request(`/posts/${postId}`);
        document.getElementById("post_edit_id").value = p.id;
        document.getElementById("post_edit_caption").value = p.caption || "";
        document.getElementById("post_edit_hashtags").value = (p.hashtags || []).join(" ");
        document.getElementById("post_edit_alt").value = p.alt_text || "";
        document.getElementById("post_edit_img").src = p.media_url || "";
        
        const statusEl = document.getElementById("post_edit_status");
        if (statusEl) {
            const isEmerald = p.status === 'published';
            statusEl.className = `px-4 py-1.5 rounded-xl border backdrop-blur-xl text-[8px] font-black uppercase tracking-[0.2em] shadow-2xl ${isEmerald ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-white/5 text-muted border-white/10'}`;
            statusEl.textContent = p.status.replace('_', ' ');
        }
        
        if (p.scheduled_time) {
            const d = new Date(p.scheduled_time);
            d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
            document.getElementById("post_edit_time").value = d.toISOString().slice(0, 16);
        } else {
            document.getElementById("post_edit_time").value = "";
        }
        
        const flagsEl = document.getElementById("post_edit_flags");
        flagsEl.innerHTML = Object.entries(p.flags || {}).map(([k,v]) => `
            <span class="px-2 py-1 bg-red-50 text-red-600 border border-red-100 rounded text-[9px] font-bold uppercase">${esc(k)}</span>
        `).join("");
        
        document.getElementById("post_publish_now_btn").classList.toggle("hidden", p.status === 'published');
        document.getElementById("post_modal").classList.remove("hidden");
    } catch(e) { showToast("Load Failed: " + e.message, "error"); }
}

function hidePostEditor() { document.getElementById("post_modal").classList.add("hidden"); }

async function savePost() {
    const id = document.getElementById("post_edit_id").value;
    const payload = {
        caption: document.getElementById("post_edit_caption").value,
        hashtags: document.getElementById("post_edit_hashtags").value.trim().split(/\s+/).filter(t => t.startsWith("#")),
        alt_text: document.getElementById("post_edit_alt").value,
        scheduled_time: document.getElementById("post_edit_time").value || null
    };
    // If it was drafted/needs_review, move to scheduled if time is set
    if (payload.scheduled_time) {
        payload.status = "scheduled";
    }
    
    try {
        await request(`/posts/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        hidePostEditor();
        refreshAll();
    } catch(e) { showToast("Save Failed: " + e.message, "error"); }
}

async function regeneratePostCaption() {
    const id = document.getElementById("post_edit_id").value;
    const inst = await customPrompt("Any special instructions for the AI? (e.g. 'make it shorter', 'more poetic')");
    try {
        const p = await request(`/posts/${id}/regenerate-caption`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ instructions: inst })
        });
        document.getElementById("post_edit_caption").value = p.caption;
        document.getElementById("post_edit_hashtags").value = (p.hashtags || []).join(" ");
    } catch(e) { showToast(e.message, "error"); }
}

async function regeneratePostImage() {
    const id = document.getElementById("post_edit_id").value;
    const mode = await customPrompt("Image Mode? (ai_nature_photo, ai_islamic_pattern, ai_minimal_gradient)", "ai_nature_photo");
    if (mode === null) return;
    try {
        const p = await request(`/posts/${id}/regenerate-image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_mode: mode })
        });
        document.getElementById("post_edit_img").src = p.media_url;
    } catch(e) { showToast(e.message, "error"); }
}

async function attachMediaToPost(input) {
    const id = document.getElementById("post_edit_id").value;
    const file = input.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("image", file);
    try {
        const p = await request(`/posts/${id}/attach-media`, { method: "POST", body: fd });
        document.getElementById("post_edit_img").src = p.media_url;
    } catch(e) { showToast(e.message, "error"); }
}

async function publishPostNow() {
    const id = document.getElementById("post_edit_id").value;
    if (!await customConfirm("Publish this to Instagram immediately?")) return;
    try {
        await request(`/posts/${id}/publish`, { method: "POST" });
        hidePostEditor();
        refreshAll();
    } catch(e) { showToast(e.message, "error"); }
}

async function deletePostUI() {
    const id = document.getElementById("post_edit_id").value;
    if (!await customConfirm("Discard this post entry forever?")) return;
    try {
        await request(`/posts/${id}`, { method: "DELETE" });
        hidePostEditor();
        refreshAll();
    } catch(e) { showToast(e.message, "error"); }
}

// --- MEDIA LIBRARY LOGIC ---
async function loadMediaLibrary() {
    const list = document.getElementById("media_list");
    list.innerHTML = `<div class="col-span-full py-12 text-center text-muted font-black uppercase text-[10px] tracking-[0.3em] animate-pulse">Consulting Neural Gallery...</div>`;
    try {
        const j = await request("/media-assets");
        if (!j.length) {
            list.innerHTML = `<div class="col-span-full py-12 text-center text-muted/40 font-black uppercase tracking-widest text-[9px]">No neural assets found. Upload to manifest.</div>`;
            return;
        }
        list.innerHTML = j.map(m => `
            <div class="relative group rounded-[2rem] overflow-hidden aspect-square border border-white/5 bg-white/5 glass transition-all duration-500 hover:border-brand/40 hover:shadow-2xl hover:shadow-brand/5">
                <img src="${m.url}" class="w-full h-full object-cover transition-transform duration-[2s] group-hover:scale-125"/>
                <div class="absolute inset-0 bg-gradient-to-t from-black via-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 flex flex-col justify-end p-6 gap-4">
                    <div class="flex flex-wrap gap-2 mb-auto">
                        ${(m.tags || []).map(t => `<span class="px-2 py-1 bg-brand/10 backdrop-blur-md rounded-lg text-[8px] text-brand font-black uppercase tracking-widest border border-brand/20">${esc(t)}</span>`).join("")}
                    </div>
                    <button onclick="deleteMedia(${m.id})" class="bg-rose-500 text-white w-full py-4 rounded-xl text-[9px] font-black uppercase tracking-[0.2em] shadow-xl shadow-rose-500/20 hover:bg-rose-600 transition-all active:scale-95">Purge Asset</button>
                </div>
            </div>
        `).join("");
    } catch(e) { console.error(e); }
}

async function uploadMedia(input) {
    const file = input.files[0];
    if (!file) return;
    const tags = await customPrompt("Enter tags (comma separated)", "nature, islamic");
    if (tags === null) return;
    const tagsArray = tags.split(",").map(t => t.trim()).filter(Boolean);
    
    const fd = new FormData();
    fd.append("image", file);
    fd.append("tags", JSON.stringify(tagsArray));
    if (ACTIVE_ACCOUNT_ID) fd.append("ig_account_id", ACTIVE_ACCOUNT_ID);
    
    try {
        await request("/media-assets", { method: "POST", body: fd });
        loadMediaLibrary();
    } catch(e) { showToast(e.message, "error"); }
    input.value = "";
}

async function deleteMedia(id) {
    if(!await customConfirm("Remove this asset from library?")) return;
    try {
        await request(`/media-assets/${id}`, { method: "DELETE" });
        loadMediaLibrary();
    } catch(e) { showToast(e.message, "error"); }
}

async function deleteAuto(id) {
    if(!await customConfirm("Remove this automation forever?")) return;
    try {
        await request(`/automations/${id}`, { method: "DELETE" });
        refreshAll();
    } catch(e) { showToast(e.message, "error"); }
}

function editAuto(a) {
    document.getElementById("edit_auto_id").value = a.id;
    document.getElementById("auto_name").value = a.name;
    document.getElementById("auto_topic").value = a.topic_prompt;
    document.getElementById("auto_style").value = a.style_preset;
    document.getElementById("auto_tone").value = a.tone || "medium";
    document.getElementById("auto_lang").value = a.language || "english";
    document.getElementById("auto_time").value = a.post_time_local || "09:00";
    document.getElementById("auto_enabled").checked = a.enabled;
    
    // Phase 6 new fields
    const useLib = document.getElementById("auto_use_library");
    if(useLib) useLib.checked = !!a.use_content_library;
    
    const imgMode = document.getElementById("auto_image_mode");
    if(imgMode) imgMode.value = a.image_mode || "reuse_last_upload";
    
    const lookback = document.getElementById("auto_lookback");
    if(lookback) lookback.value = a.avoid_repeat_days || 30;
    
    const arabic = document.getElementById("auto_arabic");
    if(arabic) arabic.checked = !!a.include_arabic;

    const contentSeed = document.getElementById("auto_content_seed");
    if(contentSeed) contentSeed.value = a.content_seed || "";
    
    const mAsset = document.getElementById("auto_media_asset_id");
    if(mAsset) mAsset.value = a.media_asset_id || "";
    
    const mTag = document.getElementById("auto_media_tag_query");
    if(mTag) mTag.value = (a.media_tag_query || []).join(", ");
    
    const profId = document.getElementById("auto_profile_id");
    if(profId) profId.value = a.content_profile_id || "";
    
    const creat = document.getElementById("auto_creativity");
    if(creat) {
        creat.value = a.creativity_level || 3;
        const valSpan = document.getElementById("creativity_val");
        if(valSpan) valSpan.textContent = creat.value + " / 5";
    }

    document.getElementById("auto_modal").classList.remove("hidden");
}

async function loadProfiles() {
    const list = document.getElementById("profile_list");
    list.innerHTML = `<div class="col-span-full py-12 text-center text-muted font-black uppercase text-[10px] tracking-[0.3em] animate-pulse">Syncing Identity Matrices...</div>`;
    
    const select = document.getElementById("auto_profile_id");
    if(select) {
        select.innerHTML = `<option value="">-- Neural Seed (No Profile) --</option>`;
    }
    
    try {
        const j = await request(`/profiles`);
        
        if(select) {
            j.forEach(p => {
                select.innerHTML += `<option value="${p.id}">${esc(p.name)}</option>`;
            });
        }
        
        if (!j.length) {
            list.innerHTML = `
            <div class="col-span-full py-24 text-center border-2 border-dashed border-white/5 rounded-[3rem] bg-white/5">
                <p class="text-[10px] text-muted font-black uppercase tracking-[0.2em] mb-6">No Identity Profiles Detected</p>
                <button onclick="showCreateProfile()" class="bg-brand text-white px-10 py-5 rounded-2xl text-[10px] font-black uppercase tracking-widest italic shadow-xl shadow-brand/20 hover:scale-105 active:scale-95 transition-all">Establish First Identity</button>
            </div>`;
            return;
        }
        
        list.innerHTML = j.map(p => {
            return `
            <div class="glass border border-white/5 rounded-[2.5rem] p-8 flex flex-col items-stretch group hover:bg-white/10 hover:border-white/20 transition-all duration-500">
                <div class="flex items-start justify-between mb-8">
                    <div class="flex-1">
                        <div class="flex items-center gap-4 mb-3">
                            <h4 class="text-xl font-black text-white italic tracking-tight">${esc(p.name)}</h4>
                        </div>
                        <p class="text-[9px] uppercase font-black tracking-[0.2em] text-muted mb-4">Vector: <span class="text-brand italic">${esc(p.niche_category || 'General')}</span></p>
                        <p class="text-[11px] text-muted font-bold tracking-wide line-clamp-2 italic">Aura: "${esc(p.focus_description || 'No focus specified.')}"</p>
                    </div>
                </div>
                <div class="mt-auto pt-6 border-t border-white/5 flex justify-end gap-3 opacity-60 group-hover:opacity-100 transition-opacity">
                    <button onclick='editProfile(${JSON.stringify(p).replaceAll("'", "&apos;")})' class="px-6 py-3 rounded-xl glass text-muted text-[9px] font-black uppercase tracking-widest hover:text-white transition-all">Modify</button>
                    <button onclick="deleteProfile(${p.id})" class="px-6 py-3 rounded-xl glass text-muted text-[9px] font-black uppercase tracking-widest hover:text-rose-500 transition-all">Purge</button>
                </div>
            </div>`;
        }).join("");
    } catch(e) { 
        list.innerHTML = `<div class="col-span-full text-center text-rose-500 font-black uppercase tracking-widest text-[10px]">Sync Error: ${e.message}</div>`;
    }
}

function showCreateProfile() {
    document.getElementById("edit_profile_id").value = "";
    document.getElementById("prof_name").value = "";
    document.getElementById("prof_niche").value = "";
    document.getElementById("prof_focus").value = "";
    document.getElementById("prof_goals").value = "";
    document.getElementById("prof_tone").value = "";
    document.getElementById("prof_allowed").value = "";
    document.getElementById("prof_banned").value = "";
    document.getElementById("profile_modal").classList.remove("hidden");
}

function hideCreateProfile() {
    document.getElementById("profile_modal").classList.add("hidden");
}

function editProfile(p) {
    document.getElementById("edit_profile_id").value = p.id;
    document.getElementById("prof_name").value = p.name || "";
    document.getElementById("prof_niche").value = p.niche_category || "";
    document.getElementById("prof_focus").value = p.focus_description || "";
    document.getElementById("prof_goals").value = p.content_goals || "";
    document.getElementById("prof_tone").value = p.tone_style || "";
    document.getElementById("prof_allowed").value = (p.allowed_topics || []).join(", ");
    document.getElementById("prof_banned").value = (p.banned_topics || []).join(", ");
    document.getElementById("profile_modal").classList.remove("hidden");
}

async function saveProfileWrapper() {
    const id = document.getElementById("edit_profile_id").value;
    const getVal = (id) => document.getElementById(id)?.value || null;
    
    // Parse CSV
    const parseList = (val) => val ? val.split(",").map(t => t.trim()).filter(Boolean) : null;
    
    const payload = {
        name: getVal("prof_name"),
        niche_category: getVal("prof_niche"),
        focus_description: getVal("prof_focus"),
        content_goals: getVal("prof_goals"),
        tone_style: getVal("prof_tone"),
        allowed_topics: parseList(getVal("prof_allowed")),
        banned_topics: parseList(getVal("prof_banned"))
    };
    
    if(!payload.name) return showToast("Profile Name is required!", "error");
    
    try {
        await request(id ? `/profiles/${id}` : "/profiles", {
            method: id ? "PATCH" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        hideCreateProfile();
        loadProfiles();
    } catch(e) { showToast("Save Failed: " + e.message, "error"); }
}

async function deleteProfile(id) {
    if(!await customConfirm("Remove this content profile?")) return;
    try {
        await request(`/profiles/${id}`, { method: "DELETE" });
        loadProfiles();
    } catch(e) { showToast(e.message, "error"); }
}

async function seedProfile(presetName) {
    try {
        const res = await request(`/profiles?preset=${encodeURIComponent(presetName)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: "New " + presetName + " Profile" })
        });
        hideCreateProfile();
        loadProfiles();
    } catch(e) { showToast("Failed to apply preset: " + e.message, "error"); }
}

async function loadLibrary() {
    const list = document.getElementById("library_list");
    const query = document.getElementById("library_search")?.value || "";
    list.innerHTML = `<div class="col-span-full py-12 text-center text-muted font-black uppercase text-[10px] tracking-[0.3em] animate-pulse">Browsing Neural Archive...</div>`;
    try {
        const j = await request(`/library/?topic=${encodeURIComponent(query)}`);
        if (!j.length) {
            list.innerHTML = `
            <div class="col-span-full py-24 text-center border-2 border-dashed border-white/5 rounded-[3rem] bg-white/5">
                <p class="text-[10px] text-muted font-black uppercase tracking-[0.2em]">Archive Matrix Empty</p>
                <p class="text-[9px] text-muted/60 mt-3 font-bold italic">Upload or Seed neural seeds to start.</p>
            </div>`;
            return;
        }
        list.innerHTML = j.map(item => `
        <div class="glass border border-white/5 rounded-[2rem] p-6 hover:bg-white/10 hover:border-white/20 transition-all duration-300">
            <div class="flex justify-between items-start mb-4">
                <span class="px-2 py-0.5 rounded-lg bg-brand/10 text-brand text-[8px] font-black uppercase tracking-widest">${esc(item.type)}</span>
                <span class="text-[8px] font-black text-muted uppercase tracking-widest">${item.topics.join(", ")}</span>
            </div>
            <h5 class="text-sm font-black text-white mb-2 line-clamp-1 italic">${esc(item.title || 'Untitled Vector')}</h5>
            <p class="text-[11px] text-muted font-medium line-clamp-3 mb-6 italic leading-relaxed">"${esc(item.text_en)}"</p>
            <div class="flex justify-between items-center pt-4 border-t border-white/5">
                <span class="text-[9px] font-black text-muted/40 uppercase tracking-widest">${esc(item.source_name || 'Personal')}</span>
                <button onclick="deleteLibraryItem(${item.id})" class="text-muted/40 hover:text-rose-500 transition-colors">
                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                </button>
            </div>
        </div>`).join("");
    } catch(e) { setError("Library Error: " + e.message); }
}

async function seedDemoContent() {
    if(!await customConfirm("Seed database with demo Islamic content?")) return;
    try {
        await request("/library/seed-demo/", { method: "POST" });
        await loadLibrary();
        showToast("Demo content seeded successfully.", "success");
    } catch(e) { showToast("Seed Failed: " + e.message, "error"); }
}

async function importLibrary(input) {
    const file = input.files[0];
    if(!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
        await request("/library/import/", { method: "POST", body: fd });
        await loadLibrary();
        showToast("Import Successful!", "success");
    } catch(e) { showToast("Import Failed: " + e.message, "error"); }
    input.value = "";
}

async function deleteLibraryItem(id) {
    if(!await customConfirm("Remove this item from library?")) return;
    try {
        await request(`/library/${id}`, { method: "DELETE" });
        await loadLibrary();
    } catch(e) { showToast(e.message, "error"); }
}
function checkLocalhost() {
    const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
    document.getElementById("localhost_warning").classList.toggle("hidden", !isLocal);
}
async function loadAccounts() {
    try {
        ACCOUNTS = await request("/ig-accounts");
        const sel = document.getElementById("account_selector");
        if (ACCOUNTS.length === 0) {
            sel.innerHTML = `<option value="">No Slots Registered</option>`;
            ACTIVE_ACCOUNT_ID = null;
        } else {
            sel.innerHTML = ACCOUNTS.map(a => `<option value="${a.id}" ${a.id == ACTIVE_ACCOUNT_ID ? 'selected' : ''}>${esc(a.name)}</option>`).join("");
            if (!ACTIVE_ACCOUNT_ID || !ACCOUNTS.find(a => a.id == ACTIVE_ACCOUNT_ID)) {
                ACTIVE_ACCOUNT_ID = ACCOUNTS[0].id;
            }
        }
        localStorage.setItem("active_ig_id", ACTIVE_ACCOUNT_ID);
        updateAccountHeader();
        renderSettingsAccounts();
    } catch(e) { setError("Account Fetch Fail: " + e.message); }
}
function onAccountChange() {
    ACTIVE_ACCOUNT_ID = document.getElementById("account_selector").value;
    localStorage.setItem("active_ig_id", ACTIVE_ACCOUNT_ID);
    updateAccountHeader();
    refreshAll();
}
function updateAccountHeader() {
    const acc = ACCOUNTS.find(a => a.id == ACTIVE_ACCOUNT_ID);
    const display = document.getElementById("active_account_display");
    const box = document.getElementById("selected_acc_box");
    
    if (acc) {
        display.textContent = acc.name;
        display.className = "text-[11px] font-black text-brand uppercase tracking-widest italic fade-in";
        box.className = "p-6 glass border border-brand/20 rounded-3xl shadow-xl shadow-brand/5";
    } else {
        display.textContent = "Connect Primary Hub →";
        display.className = "text-[11px] font-black text-muted/40 uppercase tracking-widest italic";
        box.className = "p-6 glass border border-white/5 rounded-3xl";
    }
}
function showEmptyState(type) {
    const list = document.getElementById("list");
    const stats = document.getElementById("stats");
    stats.innerHTML = "";
    
    let html = "";
    if (type === "no_accounts") {
        html = `
        <div class="col-span-full py-24 text-center">
            <div class="w-20 h-20 glass text-brand rounded-[2rem] flex items-center justify-center mx-auto mb-8 animate-pulse shadow-xl shadow-brand/10">
                <svg class="h-10 w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            </div>
            <h3 class="text-2xl font-black text-white italic tracking-tight mb-3">No Neural Slots</h3>
            <p class="text-[11px] text-muted font-bold max-w-xs mx-auto mb-10 tracking-wide italic">Your core identity is active, but you haven't initialized an Instagram endpoint yet.</p>
            <button onclick="toggleSettings()" class="bg-brand text-white px-10 py-5 rounded-2xl text-[10px] font-black uppercase tracking-widest italic shadow-xl shadow-brand/20 hover:scale-105 active:scale-95 transition-all">Initialize First Slot</button>
        </div>`;
    } else if (type === "no_posts") {
        html = `
        <div class="col-span-full py-24 text-center">
            <div class="w-20 h-20 glass text-brand rounded-[2rem] flex items-center justify-center mx-auto mb-8 animate-bounce shadow-xl shadow-brand/10">
                <svg class="h-10 w-10" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
            </div>
            <h3 class="text-2xl font-black text-white italic tracking-tight mb-3">The Stream is Void</h3>
            <p class="text-[11px] text-muted font-bold max-w-xs mx-auto mb-10 tracking-wide italic">Ready to broadcast? Use the <b>Content Intake</b> matrix on the left to upload your FIRST LOCAL POSTER.</p>
            <div class="flex items-center justify-center gap-3 text-brand font-black text-[10px] uppercase tracking-widest italic animate-pulse">
                <svg class="h-5 w-5 rotate-180" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" /></svg>
                <span>Follow Step 03 to manifest</span>
            </div>
        </div>`;
    }
    list.innerHTML = html;
}
async function addAccount() {
    const btn = document.getElementById("add_acc_btn");
    const msg = document.getElementById("add_acc_msg");
    const payload = {
        name: document.getElementById("new_acc_name").value.trim(),
        ig_user_id: document.getElementById("new_acc_ig_id").value.trim(),
        access_token: document.getElementById("new_acc_token").value.trim()
    };
    if(!payload.name || !payload.ig_user_id || !payload.access_token) return showToast("Fill all fields!", "error");
    
    try {
        btn.disabled = true;
        msg.textContent = "⚙️ REGISTERING EXTENSION...";
        msg.className = "mt-4 text-[10px] font-black tracking-widest text-indigo-500 animate-pulse";
        
        const newAcc = await request("/ig-accounts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        
        msg.textContent = "✅ EXTENSION ACTIVE!";
        msg.className = "mt-4 text-[10px] font-black tracking-widest text-green-600";
        
        document.getElementById("new_acc_name").value = "";
        document.getElementById("new_acc_ig_id").value = "";
        document.getElementById("new_acc_token").value = "";
        
        ACTIVE_ACCOUNT_ID = newAcc.id;
        localStorage.setItem("active_ig_id", ACTIVE_ACCOUNT_ID);
        await loadAccounts();
        await refreshAll();
        setTimeout(() => { toggleSettings(); msg.textContent = ""; }, 1500);
    } catch(e) { 
        msg.textContent = "❌ ERROR"; 
        msg.className = "mt-4 text-[10px] font-black tracking-widest text-red-600";
        showToast("Registration Failed: " + e.message, "error"); 
    } finally { btn.disabled = false; }
}
async function deleteAccount(id) {
    if(!await customConfirm("Are you SURE you want to delete this Instagram account? This will also un-link it from any scheduled posts or automations!")) return;
    try {
        await request(`/ig-accounts/${id}`, { method: "DELETE" });
        showToast("Account deleted.", "success");
        // If we deleted the active account, reset ACTIVE_ACCOUNT_ID
        if (ACTIVE_ACCOUNT_ID == id) {
            ACTIVE_ACCOUNT_ID = null;
        }
        await loadAccounts();
        await refreshAll();
    } catch(e) {
        showToast("Deletion Failed: " + e.message, "error");
    }
}
function renderSettingsAccounts() {
    const list = document.getElementById("settings_accounts_list");
    if(!list) return;
    if(ACCOUNTS.length === 0) {
        list.innerHTML = `<div class="text-[9px] text-muted/40 font-black uppercase tracking-widest text-center py-8 glass border border-white/5 rounded-2xl italic">No neural links established.</div>`;
        return;
    }
    list.innerHTML = ACCOUNTS.map(a => `
        <div class="flex justify-between items-center p-5 rounded-2xl border border-white/5 glass group hover:border-brand/30 transition-all duration-300">
            <div class="flex items-center gap-4">
                <div class="w-10 h-10 rounded-xl bg-brand/10 flex items-center justify-center text-brand text-[8px] font-black border border-brand/20">${(a.name || "U")[0].toUpperCase()}</div>
                <div>
                    <div class="text-[11px] font-black text-white italic tracking-tight">${esc(a.name)}</div>
                    <div class="text-[8px] text-muted font-mono mt-1 opacity-40 uppercase tracking-widest">Node ID: ${esc(a.ig_user_id)}</div>
                </div>
            </div>
            <button onclick="deleteAccount(${a.id})" class="w-10 h-10 rounded-xl glass text-muted hover:text-rose-500 hover:border-rose-500/20 flex items-center justify-center transition-all" title="Unlink Node">
                <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
            </button>
        </div>
    `).join("");
}
async function loadStats() {
    const el = document.getElementById("stats");
    if(!ACTIVE_ACCOUNT_ID || ACTIVE_ACCOUNT_ID === "null" || ACTIVE_ACCOUNT_ID === "undefined") {
        el.innerHTML = "";
        return;
    }
    try {
        const j = await request(`/posts/stats?ig_account_id=${ACTIVE_ACCOUNT_ID || ''}`);
        el.innerHTML = Object.entries(j.counts || {}).map(([k,v]) => `
            <div class="glass border border-white/5 rounded-2xl p-6 text-center shadow-xl shadow-black/20 group hover:border-brand/40 transition-all duration-500">
                <div class="text-[8px] font-black text-muted uppercase tracking-[0.2em] leading-none mb-2 group-hover:text-brand transition-colors">${esc(k)}</div>
                <div class="text-xl font-black text-white italic tracking-tight">${v}</div>
            </div>`).join("");
    } catch(e) { el.innerHTML = ""; }
}
async function loadPosts() {
    const list = document.getElementById("list");
    list.innerHTML = `<div class="col-span-full py-24 text-center"><div class="animate-spin h-8 w-8 border-4 border-indigo-600 border-t-transparent rounded-full mx-auto mb-4"></div><p class="text-xs font-black uppercase text-slate-400">Synchronizing History...</p></div>`;
    try {
        const status = document.getElementById("status_filter").value;
        const qs = new URLSearchParams();
        if (status) qs.set("status", status);
        if (ACTIVE_ACCOUNT_ID) qs.set("ig_account_id", ACTIVE_ACCOUNT_ID);
        
        const j = await request(`/posts?${qs.toString()}`);
        if (!j.length) {
            showEmptyState("no_posts");
            return;
        }
        list.innerHTML = j.map(p => renderPost(p)).join("");
    } catch(e) { list.innerHTML = ""; setError("Stream Error: " + e.message); }
}
function renderPost(p) {
    const colors = { 
        submitted: "bg-white/5 text-muted border-white/10", 
        drafted: "bg-brand/10 text-brand border-brand/20", 
        needs_review: "bg-amber-500/10 text-amber-500 border-amber-500/20", 
        scheduled: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20", 
        published: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20", 
        failed: "bg-rose-500/10 text-rose-400 border-rose-500/20" 
    };
    const c = colors[p.status] || "bg-white/5 text-muted border-white/10";
    
    return `
    <div class="glass border border-white/5 rounded-[2.5rem] overflow-hidden flex flex-col group hover:shadow-[0_0_50px_rgba(99,102,241,0.1)] hover:border-brand/30 transition-all duration-700">
        <div class="relative aspect-square bg-white/5 overflow-hidden cursor-pointer" onclick="openPostEditor(${p.id})">
            <img src="${p.media_url}" class="w-full h-full object-cover transition-transform duration-1000 group-hover:scale-110" loading="lazy" onerror="this.src='https://placehold.co/600x600/0f172a/94a3b8?text=Media+Offline'"/>
            <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
            <div class="absolute top-6 left-6 right-6 flex justify-between items-start">
               <span class="px-4 py-2 rounded-xl border backdrop-blur-xl text-[8px] font-black uppercase tracking-[0.2em] shadow-2xl ${c}">${esc(p.status)}</span>
               <div class="w-10 h-10 rounded-xl glass border border-white/10 text-white shadow-2xl flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all transform translate-y-4 group-hover:translate-y-0 duration-500">
                  <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
               </div>
            </div>
            ${p.scheduled_time ? `<div class="absolute bottom-6 left-6 px-4 py-2 bg-brand text-white rounded-xl text-[8px] font-black uppercase tracking-widest shadow-2xl shadow-brand/20 italic">ETA: ${new Date(p.scheduled_time).toLocaleString()}</div>` : ''}
        </div>
        <div class="p-8 flex flex-col flex-1">
            <p class="text-[11px] text-muted leading-relaxed font-bold tracking-wide mb-6 line-clamp-2 italic">"${esc(p.caption || '(Void Caption)')}"</p>
            <div class="mt-auto flex items-center justify-between border-t border-white/5 pt-6">
                <span class="text-[8px] font-black text-muted/30 uppercase tracking-[0.2em] italic">${esc(p.source_type)}</span>
                <button onclick="openPostEditor(${p.id})" class="text-[9px] font-black text-brand uppercase tracking-widest hover:text-white transition-colors italic">Interface Matrix</button>
            </div>
        </div>
    </div>`;
}
async function uploadPost() {
    if (!ACTIVE_ACCOUNT_ID) return showToast("Select an account first!", "error");
    const useAi = document.getElementById("intake_use_ai").value === "true";
    const file = document.getElementById("image").files[0];
    if (!useAi && !file) return showToast("Pick an image asset or select AI Genesis!", "error");
    
    const sourceText = document.getElementById("source_text").value;
    if (useAi && !sourceText) return showToast("Enter Directives for AI image generation!", "error");

    const btn = document.getElementById("intake_btn");
    const msg = document.getElementById("upload_msg");
    const fd = new FormData();
    fd.append("source_text", sourceText);
    if (file) fd.append("image", file);
    fd.append("ig_account_id", ACTIVE_ACCOUNT_ID);
    fd.append("use_ai_image", useAi);
    try {
        btn.disabled = true;
        msg.textContent = useAi ? "🧠 MANIFESTING AI VISUAL..." : "📡 UPLOADING CONTENT...";
        msg.className = "text-center text-[10px] font-black text-indigo-500 animate-pulse";
        await request("/posts/intake", { method: "POST", body: fd });
        msg.textContent = "SUCCESS!";
        msg.className = "text-center text-[10px] font-black text-green-600";
        resetUpload();
        await refreshAll();
        setTimeout(() => { msg.textContent = ""; }, 3000);
    } catch(e) { 
        msg.textContent = "UPLOAD FAILED"; 
        msg.className = "text-center text-[10px] font-black text-red-600";
        setError("Upload error: " + e.message); 
    } finally { btn.disabled = false; }
}
function resetUpload() {
    document.getElementById("source_text").value = "";
    document.getElementById("image").value = "";
    updateFileName(document.getElementById("image"));
    setError("");
}
async function generatePost(id) {
    const el = document.getElementById(`msg-${id}`);
    if(el) { el.textContent = "🧠 AI ANALYZING..."; el.className = "mt-4 text-[9px] text-center font-black text-indigo-500 animate-pulse"; }
    try { await request(`/posts/${id}/generate`, { method: "POST" }); await refreshAll(); } catch(e) { if(el) { el.textContent = "AI FAILED"; el.className = "mt-4 text-[9px] text-center font-black text-red-600"; } showToast(e.message, "error"); }
}
async function approvePost(id) {
    const el = document.getElementById(`msg-${id}`);
    if(el) { el.textContent = "✔️ ADDING TO QUEUE..."; el.className = "mt-4 text-[9px] text-center font-black text-emerald-500 animate-pulse"; }
    try { await request(`/posts/${id}/approve`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({approve_anyway: true}) }); await refreshAll(); } catch(e) { if(el) { el.textContent = "FAIL"; el.className = "mt-4 text-[9px] text-center font-black text-red-600"; } showToast(e.message, "error"); }
}

async function loadMe() {
    try {
        ME = await request("/auth/me");
        document.getElementById("user_dropdown_name").textContent = ME.name || "User";
        document.getElementById("user_dropdown_email").textContent = ME.email || "";
        document.getElementById("user_avatar").textContent = (ME.name || "U")[0].toUpperCase();
        
        if(ME.is_superadmin) {
            document.getElementById("platform_btn").classList.remove("hidden");
            document.getElementById("platform_btn").classList.add("flex");
        }
        
        const sel = document.getElementById("org_selector");
        if(ME.orgs.length === 0) {
            sel.innerHTML = `<option value="">No Workspaces</option>`;
            ACTIVE_ORG_ID = null;
        } else {
            sel.innerHTML = ME.orgs.map(o => `<option value="${o.id}">${esc(o.name)}</option>`).join("");
            
            // Reconcile saved org id
            if(!ACTIVE_ORG_ID || !ME.orgs.find(o => o.id == ACTIVE_ORG_ID)) {
                ACTIVE_ORG_ID = ME.orgs[0].id;
            }
            sel.value = ACTIVE_ORG_ID;
        }
        localStorage.setItem("active_org_id", ACTIVE_ORG_ID);
    } catch(e) { console.error("Could not load user profile", e); }
}

function onOrgChange() {
    ACTIVE_ORG_ID = document.getElementById("org_selector").value;
    localStorage.setItem("active_org_id", ACTIVE_ORG_ID);
    refreshAll();
}

document.addEventListener("DOMContentLoaded", async () => {
    await loadMe();
    await loadProfile();
    refreshAll();
});

async function customConfirm(msg) {
    return new Promise((resolve) => {
        const container = document.getElementById("custom_dialog_container");
        const box = document.getElementById("custom_confirm_box");
        const msgEl = document.getElementById("custom_confirm_msg");
        const okBtn = document.getElementById("custom_confirm_ok");
        const cancelBtn = document.getElementById("custom_confirm_cancel");

        msgEl.textContent = msg;
        container.classList.remove("hidden");
        box.classList.remove("hidden");

        const cleanup = (val) => {
            container.classList.add("hidden");
            box.classList.add("hidden");
            okBtn.onclick = null;
            cancelBtn.onclick = null;
            resolve(val);
        };

        okBtn.onclick = () => cleanup(true);
        cancelBtn.onclick = () => cleanup(false);
    });
}

async function customPrompt(msg, def = "") {
    return new Promise((resolve) => {
        const container = document.getElementById("custom_dialog_container");
        const box = document.getElementById("custom_prompt_box");
        const msgEl = document.getElementById("custom_prompt_msg");
        const inputEl = document.getElementById("custom_prompt_input");
        const okBtn = document.getElementById("custom_prompt_ok");
        const cancelBtn = document.getElementById("custom_prompt_cancel");

        msgEl.textContent = msg;
        inputEl.value = def;
        container.classList.remove("hidden");
        box.classList.remove("hidden");
        setTimeout(() => inputEl.focus(), 100);

        const cleanup = (val) => {
            container.classList.add("hidden");
            box.classList.add("hidden");
            okBtn.onclick = null;
            cancelBtn.onclick = null;
            resolve(val);
        };

        okBtn.onclick = () => cleanup(inputEl.value);
        cancelBtn.onclick = () => cleanup(null);
        inputEl.onkeydown = (e) => { if (e.key === "Enter") cleanup(inputEl.value); if (e.key === "Escape") cleanup(null); };
    });
}
</script>
</body>
</html>

"""
@router.get("/login", response_class=HTMLResponse)
def login_page():
    return LOGIN_HTML

@router.get("/register", response_class=HTMLResponse)
def register_page():
    return REGISTER_HTML

@router.get("", response_class=HTMLResponse)
def admin_page(request: Request, user = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    if not user.is_superadmin:
        return RedirectResponse(url="/app", status_code=303)
    return HTML

ONBOARDING_HTML = r"""<!doctype html>
<html lang="en" data-theme="startup">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Strategic Initialization | Social Media LLM</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root {
      --radius: 2rem;
    }

    :root[data-theme='startup'] {
      --bg-main: #020617;
      --bg-surface: rgba(255, 255, 255, 0.03);
      --brand: #6366f1;
      --brand-glow: rgba(99, 102, 241, 0.25);
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --border: rgba(255, 255, 255, 0.08);
    }

    :root[data-theme='enterprise'] {
      --bg-main: #f8fafc;
      --bg-surface: #ffffff;
      --brand: #0f172a;
      --brand-glow: rgba(15, 23, 42, 0.12);
      --text-main: #0f172a;
      --text-muted: #64748b;
      --border: #e2e8f0;
    }

    body { 
      font-family: 'Inter', sans-serif; 
      background: var(--bg-main); 
      color: var(--text-main); 
      -webkit-font-smoothing: antialiased;
      transition: background 0.4s ease;
    }
    
    .ai-bg {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      z-index: -1;
    }

    [data-theme='startup'] .ai-bg {
      background: radial-gradient(circle at top right, #1e1b4b, #0f172a, #020617);
    }

    [data-theme='enterprise'] .ai-bg {
      background: radial-gradient(circle at top right, #f1f5f9, #f8fafc);
    }

    .tool-card { 
      background: var(--bg-surface); 
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border: 1px solid var(--border); 
      border-radius: var(--radius); 
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
    }

    .text-gradient {
      background-clip: text;
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    [data-theme='startup'] .text-gradient {
      background-image: linear-gradient(to right, #818cf8, #c084fc);
    }

    [data-theme='enterprise'] .text-gradient {
      background-image: linear-gradient(to right, #0f172a, #334155);
    }

    .btn-primary { 
      background: var(--brand); 
      color: #ffffff; 
      box-shadow: 0 10px 15px -3px var(--brand-glow);
    }
    
    input, select, textarea {
      background: rgba(255, 255, 255, 0.03) !important;
      border: 1px solid var(--border) !important;
      color: var(--text-main) !important;
      transition: all 0.2s ease;
    }
    
    input:focus, select:focus, textarea:focus {
      border-color: var(--brand) !important;
      box-shadow: 0 0 0 2px var(--brand-glow) !important;
    }
    
    [data-theme='enterprise'] input, [data-theme='enterprise'] select, [data-theme='enterprise'] textarea {
      background: #f8fafc !important;
    }
    
    @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
    .animate-in { animation: fadeIn 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
  </style>
</head>
<body class="min-h-screen flex items-center justify-center py-12 px-6">
  <div class="ai-bg"></div>
  
  <div class="max-w-3xl w-full tool-card p-10 lg:p-14 animate-in">
    <div class="mb-12 flex items-center gap-4">
        <div class="w-12 h-12 bg-brand rounded-2xl flex items-center justify-center text-white text-xl font-black shadow-2xl shadow-brand/40">S</div>
        <h1 class="text-3xl font-black italic tracking-tighter text-gradient leading-none">Social Media LLM</h1>
    </div>

    <div class="mb-12">
      <h2 class="text-3xl font-black text-main italic tracking-tight leading-tight">Strategic Initialization</h2>
      <p class="text-[11px] text-muted mt-4 font-black uppercase tracking-[0.2em] leading-relaxed max-w-xl">Configure your neural architecture. This profile will harmonize the AI engine with your brand's unique narrative and creative values.</p>
    </div>
    
    <form id="onboardingForm" class="space-y-10">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-8 pt-8 border-t border-border/50">
        <div class="col-span-full">
            <h3 class="text-xs font-black text-brand uppercase tracking-widest mb-6 opacity-80 flex items-center gap-2">
                <span class="w-8 h-[1px] bg-brand/30"></span> Business Context
            </h3>
        </div>
        
        <div>
            <label class="block text-[10px] font-black text-muted uppercase tracking-[0.2em] mb-3 ml-1">Workspace Identity</label>
            <input type="text" id="name" required class="w-full rounded-2xl px-6 py-4 text-sm font-bold outline-none" placeholder="e.g. Apex Luxury Collective">
        </div>
        
        <div>
            <label class="block text-[10px] font-black text-muted uppercase tracking-[0.2em] mb-3 ml-1">Niche Architecture</label>
            <select id="niche_category" class="w-full rounded-2xl px-6 py-4 text-sm font-bold outline-none cursor-pointer appearance-none">
                <option value="ecommerce">Luxury E-Commerce</option>
                <option value="real_estate">Premium Real Estate</option>
                <option value="fitness">Bespoke Wellness</option>
                <option value="restaurant">Haute Cuisine</option>
                <option value="personal_creator">Thought Leader / Creator</option>
                <option value="b2b_saas">Enterprise SaaS</option>
                <option value="other">Custom Intelligence</option>
            </select>
        </div>
        
        <div class="col-span-full">
            <label class="block text-[10px] font-black text-muted uppercase tracking-[0.2em] mb-3 ml-1">Strategic Objectives</label>
            <textarea id="content_goals" required class="w-full rounded-2xl px-6 py-4 text-sm font-bold outline-none min-h-[120px] leading-relaxed" placeholder="Define the primary focus..."></textarea>
        </div>
        
        <div>
            <label class="block text-[10px] font-black text-muted uppercase tracking-[0.2em] mb-3 ml-1">Narrative Tone</label>
            <input type="text" id="tone_style" required class="w-full rounded-2xl px-6 py-4 text-sm font-bold outline-none" placeholder="e.g. Minimalist, Elite, Sophisticated">
        </div>
        
        <div>
            <label class="block text-[10px] font-black text-muted uppercase tracking-[0.2em] mb-3 ml-1">Linguistic Mode</label>
            <select id="language" class="w-full rounded-2xl px-6 py-4 text-sm font-bold outline-none cursor-pointer appearance-none">
                <option value="english">Standard Global (English)</option>
                <option value="spanish">Continental Spanish</option>
                <option value="french">Premium French</option>
                <option value="arabic">Arabic Essence</option>
            </select>
        </div>
      </div>
      
      <div class="grid grid-cols-1 md:grid-cols-2 gap-8 pt-8 border-t border-border/50">
        <div class="col-span-full">
            <h3 class="text-xs font-black text-brand uppercase tracking-widest mb-6 opacity-80 flex items-center gap-2">
                <span class="w-8 h-[1px] bg-brand/30"></span> Neural Boundaries
            </h3>
        </div>
        
        <div class="col-span-full">
            <label class="block text-[10px] font-black text-muted uppercase tracking-[0.2em] mb-3 ml-1">Restricted Concepts</label>
            <input type="text" id="banned_topics" class="w-full rounded-2xl px-6 py-4 text-sm font-bold outline-none" placeholder="e.g. generic slang, competitors (comma separated)">
        </div>
      </div>

      <div id="errorMsg" class="hidden text-[10px] font-black uppercase tracking-widest text-rose-500 text-center py-4 bg-rose-500/10 rounded-2xl border border-rose-500/20"></div>
      
      <button type="submit" class="btn-primary w-full rounded-2xl py-5 font-black uppercase tracking-[0.3em] italic text-xs transition-all hover:scale-[1.01] active:scale-[0.98]">INITIALIZE NEURAL ARCHITECTURE &rarr;</button>
    </form>
  </div>
  
  <script>
    // Theme Sync
    const theme = localStorage.getItem('admin_theme') || 'startup';
    document.documentElement.setAttribute('data-theme', theme);

    document.getElementById("onboardingForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const payload = {
        name: document.getElementById("name").value,
        niche_category: document.getElementById("niche_category").value,
        content_goals: document.getElementById("content_goals").value,
        tone_style: document.getElementById("tone_style").value,
        language: document.getElementById("language").value,
        banned_topics: document.getElementById("banned_topics").value ? document.getElementById("banned_topics").value.split(",").map(s => s.trim()) : []
      };
      
      const errorMsg = document.getElementById("errorMsg");
      const btn = e.target.querySelector('button');
      
      try {
        btn.disabled = true;
        btn.innerHTML = "PROVISIONING INTELLIGENCE...";
        
        const res = await fetch("/auth/complete-onboarding", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        
        if (res.ok) {
          window.location.href = "/admin";
        } else {
          const data = await res.json();
          errorMsg.textContent = "❌ " + (data.detail || "Error").toUpperCase();
          errorMsg.classList.remove("hidden");
          btn.disabled = false;
          btn.innerHTML = "RETRY INITIALIZATION &rarr;";
        }
      } catch (err) {
        errorMsg.textContent = "❌ NETWORK ANOMALY DETECTED";
        errorMsg.classList.remove("hidden");
        btn.disabled = false;
        btn.innerHTML = "RETRY INITIALIZATION &rarr;";
      }
    });
  </script>
</body>
</html>
"""

@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request, user = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    if user.onboarding_complete:
        return RedirectResponse(url="/admin", status_code=303)
    return ONBOARDING_HTML

@router.get("/users")
def list_users(
    user: User = Depends(require_superadmin),
    db: Session = Depends(get_db)
):
    users = db.query(User).order_by(User.id.desc()).all()
    results = []
    for u in users:
        # get orgs
        memberships = db.query(OrgMember).filter(OrgMember.user_id == u.id).all()
        org_names = []
        for m in memberships:
            org = db.query(Org).filter(Org.id == m.org_id).first()
            if org:
                org_names.append(f"{org.name} ({m.role})")
                
        results.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "is_superadmin": u.is_superadmin,
            "is_active": u.is_active,
            "created_at": u.created_at,
            "orgs": ", ".join(org_names)
        })
    return results

@router.delete("/users/{target_id}")
def delete_user(
    target_id: int,
    user: User = Depends(require_superadmin),
    db: Session = Depends(get_db)
):
    if target_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")
        
    target_user = db.query(User).filter(User.id == target_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found.")
        
    # Delete memberships first
    db.query(OrgMember).filter(OrgMember.user_id == target_id).delete()
    
    # Actually delete the user
    db.delete(target_user)
    db.commit()
    return {"status": "ok"}

@router.get("/inquiries")
def list_inquiries(
    user: User = Depends(require_superadmin),
    db: Session = Depends(get_db)
):
    msgs = db.query(ContactMessage).order_by(ContactMessage.created_at.desc()).all()
    return msgs

@router.delete("/inquiries/{id}")
def delete_inquiry(
    id: int,
    user: User = Depends(require_superadmin),
    db: Session = Depends(get_db)
):
    msg = db.query(ContactMessage).filter(ContactMessage.id == id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    db.delete(msg)
    db.commit()
    return {"status": "ok"}

@router.post("/backup-now")
def trigger_manual_backup(
    user: User = Depends(require_superadmin)
):
    from ..services.backups import backup_postgres_database
    return backup_postgres_database()

@router.get("/config/export")
def export_safe_config(
    user: User = Depends(require_superadmin)
):
    import os
    from datetime import datetime, timezone
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "keys_present": list(os.environ.keys())
    }

@router.get("/debug/logging")
def debug_logging(user: User = Depends(require_superadmin)):
    import logging
    from ..config import settings
    
    logger = logging.getLogger()
    axiom_handler = None
    for h in logger.handlers:
        if type(h).__name__ == "AxiomHandler":
            axiom_handler = h
            break
            
    return {
        "axiom_enabled": bool(settings.axiom_token),
        "dataset": settings.axiom_dataset,
        "queue_size": axiom_handler.queue.qsize() if axiom_handler else 0,
        "last_ship_status": "active" if axiom_handler and axiom_handler.worker.is_alive() else "inactive"
    }

@router.get("/debug/version")
def debug_version():
    return {
        "version": "1.2.0-redesign",
        "env": "production",
        "engine": "Social Media LLM v2"
    }
