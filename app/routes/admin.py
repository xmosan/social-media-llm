from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, Org, OrgMember, ContactMessage
from app.security.auth import get_current_user
from app.security.rbac import require_superadmin

router = APIRouter(prefix="/admin", tags=["admin"])

LOGIN_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Login | Social Media LLM</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-main min-h-screen flex py-12 px-6 justify-center text-main">
  <div class="max-w-md w-full bg-surface rounded-[2.5rem] shadow-2xl p-10 border border-border">
    <div class="text-center mb-10">
      <h1 class="text-3xl font-black italic tracking-tighter text-gradient">Social Media LLM</h1>
      <p class="text-[11px] font-black text-muted uppercase tracking-widest mt-2 italic">Neural Authentication</p>
    </div>
    <form id="loginForm" class="space-y-8">
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
        Initialize Session
      </button>

      <div class="text-center mt-4">
        <a href="/admin/register" class="text-xs text-indigo-600 hover:text-indigo-800 font-bold hover:underline">Don't have an account? Sign up</a>
      </div>
      <div class="relative py-2">
        <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-border"></div></div>
        <div class="relative flex justify-center text-xs"><span class="bg-surface px-2 text-muted">Or</span></div>
      </div>
      <a href="/auth/google/start" class="flex w-full items-center justify-center gap-3 rounded-xl border border-border bg-white/5 py-3.5 text-sm font-bold text-main shadow-sm transition-all hover:bg-white/10 active:scale-[0.98]">
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
</html>
"""

REGISTER_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Register | Social Media LLM</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-main min-h-screen flex items-center justify-center p-6 text-main">
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

HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SaaS Dashboard | Social Media LLM</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <script src='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.10/index.global.min.js'></script>
  <style>
    :root {
      --radius: 1.5rem;
    }

    :root[data-theme='startup'] {
      --bg-main: #020617;
      --bg-sidebar: rgba(255, 255, 255, 0.02);
      --bg-surface: rgba(255, 255, 255, 0.03);
      --brand: #6366f1;
      --brand-glow: rgba(99, 102, 241, 0.15);
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --border: rgba(255, 255, 255, 0.08);
    }

    :root[data-theme='enterprise'] {
      --bg-main: #f8fafc;
      --bg-sidebar: #ffffff;
      --bg-surface: #ffffff;
      --brand: #0f172a;
      --brand-glow: rgba(15, 23, 42, 0.08);
      --text-main: #0f172a;
      --text-muted: #64748b;
      --border: #e2e8f0;
    }

    body { 
      font-family: 'Inter', sans-serif; 
      background: var(--bg-main); 
      color: var(--text-main); 
      -webkit-font-smoothing: antialiased; 
      overflow-x: hidden;
      transition: background 0.3s ease, color 0.3s ease;
    }
    
    .ai-bg {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      z-index: -1;
      transition: opacity 0.5s ease;
    }

    [data-theme='startup'] .ai-bg {
      background: radial-gradient(circle at top right, #1e1b4b, #0f172a, #020617);
      opacity: 1;
    }

    [data-theme='enterprise'] .ai-bg {
      background: radial-gradient(circle at top right, #f1f5f9, #f8fafc);
      opacity: 1;
    }

    .sidebar { 
      width: 260px; 
      height: 100vh; 
      position: fixed; 
      left: 0; top: 0; 
      background: var(--bg-sidebar); 
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border-right: 1px solid var(--border); 
      z-index: 50; 
      padding: 24px; 
      display: flex; 
      flex-direction: column; 
      transition: background 0.3s ease, border-color 0.3s ease;
    }

    .tool-card { 
      background: var(--bg-surface); 
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid var(--border); 
      border-radius: var(--radius); 
      padding: 24px; 
      transition: all 0.3s ease; 
    }
    
    [data-theme='startup'] .tool-card:hover { 
      border-color: var(--brand); 
      background: rgba(255, 255, 255, 0.05);
      box-shadow: 0 0 20px var(--brand-glow);
    }

    [data-theme='enterprise'] .tool-card {
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
    }
    
    [data-theme='enterprise'] .tool-card:hover { 
      border-color: var(--brand); 
      box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.08);
    }

    .text-gradient {
      display: inline-block;
      padding-right: 0.15em;
      padding-bottom: 0.1em;
      background-clip: text;
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      transition: all 0.3s ease;
    }

    [data-theme='startup'] .text-gradient {
      background-image: linear-gradient(to right, #818cf8, #c084fc);
    }

    [data-theme='enterprise'] .text-gradient {
      background-image: linear-gradient(to right, #0f172a, #334155);
    }

    .main-content { margin-left: 260px; min-height: 100vh; display: flex; flex-direction: column; }
    .content-area { padding: 40px; flex: 1; max-width: 1200px; width: 100%; margin: 0 auto; }

    .btn-primary { 
      background: var(--brand); 
      color: #ffffff; 
      border-radius: 12px; 
      padding: 10px 20px; 
      font-size: 14px; 
      font-weight: 700; 
      transition: all 0.2s; 
      border: none; 
      cursor: pointer; 
      display: inline-flex; 
      align-items: center; 
      justify-content: center; 
      box-shadow: 0 4px 12px var(--brand-glow);
    }
    .btn-primary:hover { 
      transform: translateY(-1px);
      box-shadow: 0 6px 20px var(--brand-glow);
    }

    .nav-item { 
      display: flex; 
      align-items: center; 
      gap: 12px; 
      padding: 12px; 
      border-radius: 12px; 
      font-size: 14px; 
      font-weight: 600; 
      color: var(--text-muted); 
      transition: all 0.2s; 
      cursor: pointer; 
    }
    .nav-item:hover { background: rgba(255, 255, 255, 0.05); color: var(--text-main); }
    .nav-item.active { background: var(--brand); color: #ffffff; box-shadow: 0 4px 12px var(--brand-glow); }

    .stat-card { 
      padding: 24px; 
      border-radius: var(--radius); 
      border: 1px solid var(--border); 
      background: var(--bg-surface); 
      backdrop-filter: blur(10px);
      transition: all 0.3s ease;
    }
    .stat-card:hover {
      transform: translateY(-2px);
      border-color: var(--brand);
    }

    /* Theme Utility Classes */
    .text-muted { color: var(--text-muted) !important; }
    .text-main { color: var(--text-main) !important; }
    .border-main { border-color: var(--border) !important; }
    .bg-main { background-color: var(--bg-main) !important; }
    .bg-surface { background-color: var(--bg-surface) !important; }


    @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
    .fade-in { animation: fadeIn 0.4s ease-out forwards; }

    /* Custom Scrollbar */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }
  </style>
</head>
<body class="min-h-screen">
  <div class="ai-bg"></div>

  <aside class="sidebar">
    <div class="mb-10 flex items-center gap-3">
        <div class="w-9 h-9 bg-brand rounded-xl flex items-center justify-center text-white font-black shadow-lg shadow-indigo-500/20">S</div>
        <span class="font-black text-xl tracking-tighter italic text-gradient">Social Media LLM</span>
    </div>

    <nav class="flex-1 space-y-2">
        <div onclick="switchTab('dashboard')" id="nav_dashboard" class="nav-item active">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/></svg>
            Dashboard
        </div>
        <div onclick="switchTab('feed')" id="nav_feed" class="nav-item">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
            Posts
        </div>
        <div onclick="switchTab('calendar')" id="nav_calendar" class="nav-item">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 00-2 2z"/></svg>
            Calendar
        </div>
        <div onclick="switchTab('automations')" id="nav_automations" class="nav-item">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
            Automations
        </div>
        <div onclick="switchTab('profiles')" id="nav_profiles" class="nav-item">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5.121 17.804A13.937 13.937 0 0112 16c2.5 0 4.847.655 6.879 1.804M15 10a3 3 0 11-6 0 3 3 0 016 0zm6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            Profiles
        </div>
        <div onclick="switchTab('media')" id="nav_media" class="nav-item">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
            MediaLibrary
        </div>
    </nav>

    <div class="mt-auto pt-6 border-t border-border">
        <div id="platform_btn" onclick="togglePlatformPanel()" class="nav-item hidden text-brand">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>
            Platform OS
        </div>
        <div onclick="toggleSettings()" class="nav-item">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
            Settings
        </div>
        <div onclick="logout()" class="nav-item text-rose-400 hover:bg-rose-500/10">
            <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/></svg>
            Logout
        </div>
    </div>
  </aside>

  <main class="main-content">
    <header class="flex items-center justify-between px-10 py-6 border-b border-border bg-transparent backdrop-blur-md sticky top-0 z-40">
        <div class="flex items-center gap-6">
            <select id="org_selector" onchange="onOrgChange()" class="bg-transparent font-black text-sm outline-none cursor-pointer text-brand">
                <option value="">Select Workspace</option>
            </select>
            <div class="h-4 w-px bg-border"></div>
            <select id="account_selector" onchange="onAccountChange()" class="bg-transparent font-black text-sm outline-none cursor-pointer text-[var(--text-main)]">
                <option value="">Select Account</option>
            </select>
            <div class="h-4 w-px bg-border"></div>
            <span class="text-sm font-bold text-text-muted uppercase tracking-widest" id="breadcrumb_tab">Dashboard Overview</span>
        </div>
        
        <div class="flex items-center gap-4">
            <button id="run_scheduler_btn" onclick="runGlobalScheduler()" class="text-[10px] font-black uppercase tracking-widest px-4 py-2 border border-border rounded-xl hover:bg-brand transition-all flex items-center gap-2 group">
                <div class="w-2 h-2 rounded-full bg-emerald-500 shadow-lg shadow-emerald-500/50 group-hover:bg-white"></div>
                Run Scheduler
            </button>
            <div class="w-9 h-9 rounded-xl bg-white/5 border border-white/10 text-[var(--text-main)] flex items-center justify-center text-xs font-black" id="user_avatar_top">U</div>
        </div>
    </header>



    <div class="content-area">
      <div id="onboarding_banner" class="hidden mb-8 p-6 rounded-[2rem] bg-brand/10 border border-brand/20 flex items-center justify-between group">
          <div class="flex items-center gap-6">
              <div class="w-12 h-12 rounded-2xl bg-brand text-white flex items-center justify-center shadow-lg shadow-brand/20">
                  <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
              </div>
              <div>
                  <h3 class="text-sm font-black text-main uppercase tracking-widest">Neural Onboarding Required</h3>
                  <p class="text-[10px] text-muted font-bold uppercase tracking-widest mt-1">Configure your first content DNA profile to activate the engine.</p>
              </div>
          </div>
          <button onclick="window.location.href='/admin/onboarding'" class="px-6 py-2.5 bg-brand text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:scale-[1.02] active:scale-[0.98] transition-all">Initialize Identity</button>
      </div>

      <!-- Dashboard Tab (New) -->
      <div id="tab_dashboard" class="space-y-8 fade-in">
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div class="stat-card">
            <div class="text-muted text-[10px] font-black uppercase tracking-widest mb-3 italic">Today's Pulse</div>
            <div class="text-3xl font-black text-main" id="dash_today_posts">0</div>
          </div>
          <div class="stat-card border-brand/20">
            <div class="text-muted text-[10px] font-black uppercase tracking-widest mb-3 italic">Scheduled Nodes</div>
            <div class="text-3xl font-black text-brand" id="dash_scheduled">0</div>
          </div>
          <div class="stat-card border-emerald-500/20">
            <div class="text-muted text-[10px] font-black uppercase tracking-widest mb-3 italic">Successfully Dispatched</div>
            <div class="text-3xl font-black text-emerald-500" id="dash_published">0</div>
          </div>
          <div class="stat-card border-brand/20">
            <div class="text-muted text-[10px] font-black uppercase tracking-widest mb-3 italic">Active Automations</div>
            <div class="text-3xl font-black text-brand" id="dash_automations">0</div>
          </div>
        </div>


        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div class="lg:col-span-2 tool-card">
                 <h3 class="font-bold text-lg mb-4">Performance Overview</h3>
                 <div class="h-64 flex items-center justify-center text-text-muted italic border-2 border-dashed border-border rounded-xl">
                    Performance Chart Visualization (Placeholder)
                 </div>
            </div>
            <div class="tool-card">
                 <h3 class="font-bold text-lg mb-4">Quick Actions</h3>
                 <div class="space-y-2">
                    <button onclick="switchTab('feed')" class="w-full text-left px-5 py-4 rounded-2xl hover:bg-brand/10 hover:text-brand hover:border-brand/40 border border-border text-xs font-black uppercase tracking-widest transition-all">Create New Post</button>
                    <button onclick="switchTab('automations')" class="w-full text-left px-5 py-4 rounded-2xl hover:bg-brand/10 hover:text-brand hover:border-brand/40 border border-border text-xs font-black uppercase tracking-widest transition-all">Setup Automation</button>
                    <button onclick="toggleSettings()" class="w-full text-left px-5 py-4 rounded-2xl hover:bg-brand/10 hover:text-brand hover:border-brand/40 border border-border text-xs font-black uppercase tracking-widest transition-all">Workspace Settings</button>
                 </div>
            </div>
        </div>
      </div>


    <!-- Settings Drawer -->
    <div id="settings_panel" class="hidden fixed inset-0 bg-black/60 z-[200] backdrop-blur-md flex justify-end" onclick="if(event.target === this) toggleSettings()">
        <div class="w-full max-w-md bg-[var(--bg-main)] h-full shadow-2xl p-8 flex flex-col overflow-y-auto border-l border-border" onclick="event.stopPropagation()">
            <div class="flex justify-between items-center mb-10">
                <div>
                    <h2 class="text-2xl font-black text-[var(--text-main)] italic tracking-tighter text-gradient pb-1">Workspace Matrix</h2>
                    <p class="text-[11px] font-black text-text-muted uppercase tracking-widest mt-1">Operational Environment Configuration</p>
                </div>
                <button onclick="toggleSettings()" class="w-10 h-10 rounded-xl bg-white/5 text-text-muted hover:text-[var(--text-main)] hover:bg-white/10 flex items-center justify-center transition-all border border-border">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
            <div class="space-y-12">
                <!-- Theme Switcher -->
                <section>
                    <div class="flex items-center gap-3 mb-6">
                        <div class="w-8 h-8 rounded-lg bg-brand/10 text-brand flex items-center justify-center border border-brand/20">
                            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01"/></svg>
                        </div>
                        <h3 class="text-sm font-black text-[var(--text-main)] uppercase tracking-widest">Interface Theme</h3>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                        <button onclick="setTheme('startup')" class="p-5 rounded-[2rem] border border-border bg-white/5 hover:border-brand transition-all text-left flex flex-col gap-3 group">
                            <div class="w-full h-20 rounded-2xl bg-[#020617] border border-white/10 relative overflow-hidden">
                                <div class="absolute inset-0 bg-gradient-to-tr from-indigo-500/20 to-transparent"></div>
                                <div class="absolute bottom-2 left-2 flex gap-1">
                                    <div class="w-4 h-1 bg-brand rounded-full"></div>
                                    <div class="w-2 h-1 bg-white/10 rounded-full"></div>
                                </div>
                            </div>
                            <div>
                                <div class="text-[10px] font-black text-white uppercase tracking-widest">AI Luxury</div>
                                <div class="text-[9px] text-text-muted font-bold">Dark Command Center</div>
                            </div>
                        </button>
                        <button onclick="setTheme('enterprise')" class="p-5 rounded-[2rem] border border-border bg-white/5 hover:border-brand transition-all text-left flex flex-col gap-3 group">
                            <div class="w-full h-20 rounded-2xl bg-[#f8fafc] border border-border relative overflow-hidden shadow-inner">
                                <div class="absolute bottom-2 left-2 flex gap-1">
                                    <div class="w-4 h-1 bg-slate-900 rounded-full"></div>
                                    <div class="w-2 h-1 bg-border rounded-full"></div>
                                </div>
                            </div>
                            <div>
                                <div class="text-[10px] font-black text-[var(--text-main)] uppercase tracking-widest">Enterprise</div>
                                <div class="text-[9px] text-text-muted font-bold">Professional Light</div>
                            </div>
                        </button>
                    </div>
                </section>

                <div class="h-px bg-border/20"></div>
                
                <section>
                    <div class="flex items-center gap-3 mb-6">
                        <div class="w-8 h-8 rounded-lg bg-brand/10 text-brand flex items-center justify-center border border-brand/20 text-xs font-black">1</div>
                        <h3 class="text-sm font-black text-main uppercase tracking-widest">Active Accounts</h3>
                    </div>
                    <div id="settings_accounts_list" class="space-y-3">
                        <!-- Populated by JS -->
                    </div>
                </section>
                
                <div class="h-px bg-border/20"></div>
                
                <!-- STEP 2: ADD IG -->
                <section>
                    <div class="flex items-center gap-3 mb-6">
                        <div class="w-8 h-8 rounded-lg bg-brand/10 text-brand flex items-center justify-center border border-brand/20 text-xs font-black">2</div>
                        <h3 class="text-sm font-black text-main uppercase tracking-widest">Register Instagram Slot</h3>
                    </div>
                    <div class="space-y-6">
                        <div>
                            <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-3 ml-1">Display Name</label>
                            <input id="new_acc_name" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border focus:ring-1 focus:ring-brand outline-none text-xs font-bold transition-all text-main" placeholder="e.g. Luxury Real Estate"/>
                        </div>
                        <div class="grid grid-cols-1 gap-6">
                            <div>
                                <label class="flex items-center gap-2 text-[10px] font-black text-muted uppercase tracking-widest mb-3 ml-1">
                                    IG Hub ID
                                    <button onclick="toggleGuideModal()" class="text-brand hover:text-white transition-colors">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                    </button>
                                </label>
                                <input id="new_acc_ig_id" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border focus:ring-1 focus:ring-brand outline-none text-xs font-bold transition-all text-main font-mono" placeholder="1784..."/>
                            </div>
                            <div>
                                <label class="flex items-center gap-2 text-[10px] font-black text-muted uppercase tracking-widest mb-3 ml-1">
                                    Access Key
                                    <button onclick="toggleGuideModal()" class="text-brand hover:text-white transition-colors">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                    </button>
                                </label>
                                <textarea id="new_acc_token" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border focus:ring-1 focus:ring-brand outline-none text-[10px] font-bold transition-all text-main font-mono min-h-[100px]" placeholder="Paste long-lived token here..."></textarea>
                            </div>
                        </div>
                        <button id="add_acc_btn" onclick="addAccount()" class="btn-primary w-full py-5 text-xs tracking-widest uppercase italic">Register Enterprise Slot</button>
                    </div>
                    <div id="add_acc_msg" class="mt-4 text-xs font-bold text-center h-4"></div>
                </section>
                
                <div id="auth_error_box" class="hidden p-4 bg-red-50 text-red-600 rounded-xl text-[11px] font-bold border border-red-100"></div>
            </div>
        </div>
        </div>
    </div>

    <!-- Instagram Setup Guide Modal -->
    <div id="guide_modal" class="hidden fixed inset-0 bg-black/60 z-[200] backdrop-blur-md flex items-center justify-center p-4">
        <div class="tool-card w-full max-w-2xl flex flex-col max-h-[90vh] overflow-hidden">
            <div class="px-8 py-6 border-b border-border flex justify-between items-center bg-brand/5">
                <div class="flex items-center gap-4">
                    <div class="w-10 h-10 rounded-xl bg-brand text-white flex items-center justify-center shadow-lg shadow-brand/20">
                        <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    </div>
                    <div>
                        <h3 class="text-xl font-black text-main italic tracking-tighter text-gradient pb-1">Neural Bridge Config</h3>
                        <p class="text-[10px] font-black tracking-widest text-brand uppercase">Meta API Integration Protocol</p>
                    </div>
                </div>
                <button onclick="toggleGuideModal()" class="w-10 h-10 rounded-xl bg-white/5 text-text-muted hover:text-main hover:bg-white/10 flex items-center justify-center transition-all border border-border">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
            </div>
            
            <div class="p-10 overflow-y-auto space-y-10 bg-transparent">
                
                <div class="flex gap-6 group">
                    <div class="flex-shrink-0 w-10 h-10 rounded-2xl bg-white/5 text-text-muted font-black flex items-center justify-center text-sm border border-border group-hover:border-brand transition-all">01</div>
                    <div class="space-y-2">
                        <h4 class="font-black text-main text-base uppercase tracking-tight italic">Initialize Meta App</h4>
                        <p class="text-sm text-muted leading-relaxed">Access <a href="https://developers.facebook.com/" target="_blank" class="text-brand font-black hover:underline">Meta Developers Console</a>. Create a new "Business" orchestration layer to enable Graph API communication.</p>
                    </div>
                </div>

                <div class="flex gap-6">
                    <div class="flex-shrink-0 w-10 h-10 rounded-2xl bg-white/5 text-text-muted font-black flex items-center justify-center text-sm border border-border">02</div>
                    <div class="space-y-2">
                        <h4 class="font-black text-main text-base uppercase tracking-tight italic">Setup Content Engine</h4>
                        <p class="text-sm text-muted leading-relaxed">Add the <b>Instagram Graph API</b> product. Link your Professional Instagram node to your primary Facebook organizational page.</p>
                    </div>
                </div>

                <div class="flex gap-6">
                    <div class="flex-shrink-0 w-10 h-10 rounded-2xl bg-white/5 text-text-muted font-black flex items-center justify-center text-sm border border-border">03</div>
                    <div class="space-y-2">
                        <h4 class="font-black text-main text-base uppercase tracking-tight italic">Authorize Neural Access</h4>
                        <p class="text-sm text-muted leading-relaxed">In the explorer, generate a token with <code>instagram_content_publish</code> and <code>pages_read_engagement</code> scopes.</p>
                        <div class="bg-white/5 border border-brand/20 p-5 rounded-2xl text-[10px] font-mono text-brand leading-relaxed">
                            instagram_basic, instagram_content_publish, pages_show_list, pages_read_engagement
                        </div>
                    </div>
                </div>

                <div class="flex gap-6">
                    <div class="flex-shrink-0 w-10 h-10 rounded-2xl bg-white/5 text-text-muted font-black flex items-center justify-center text-sm border border-border">04</div>
                    <div class="space-y-2">
                        <h4 class="font-black text-main text-base uppercase tracking-tight italic">Persistence Upgrade</h4>
                        <p class="text-sm text-muted leading-relaxed">Use the <b>Access Token Tool</b> to extend your session validity. Click <b>"Extend Access Token"</b> to generate a 60-day persistent key.</p>
                    </div>
                </div>

                <div class="flex gap-6">
                    <div class="flex-shrink-0 w-10 h-10 rounded-2xl bg-white/5 text-text-muted font-black flex items-center justify-center text-sm border border-border">05</div>
                    <div class="space-y-2">
                        <h4 class="font-black text-main text-base uppercase tracking-tight italic">Entity Identification</h4>
                        <p class="text-sm text-muted leading-relaxed">Execute the identity query to find your <code>instagram_business_account.id</code>. This is the unique node ID required for publishing.</p>
                        <div class="bg-white/5 border border-border p-5 rounded-2xl text-[10px] font-mono text-emerald-500">
                            me/accounts?fields=instagram_business_account
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="p-8 border-t border-border bg-white/5 flex justify-end">
                <button onclick="toggleGuideModal()" class="btn-primary px-12">Intelligence Synchronized</button>
            </div>
        </div>
    </div>

    <!-- New Automation Modal -->
    <div id="auto_modal" class="hidden fixed inset-0 bg-black/60 z-[110] backdrop-blur-md flex items-center justify-center p-4">
        <div class="tool-card w-full max-w-xl flex flex-col max-h-[90vh] overflow-hidden">
            <div class="px-8 py-7 border-b border-border flex justify-between items-center bg-white/5">
                <h3 class="text-xl font-black text-main italic tracking-tighter text-gradient">Content Automation Matrix</h3>
                <button onclick="hideCreateAuto()" class="w-10 h-10 rounded-xl bg-white/5 text-text-muted hover:text-main hover:bg-white/10 flex items-center justify-center transition-all border border-border">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
            </div>
            <div class="p-8 overflow-y-auto space-y-6">
                <input type="hidden" id="edit_auto_id" value=""/>
                <div>
                    <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-2 ml-1">Internal Reference Name</label>
                    <input id="auto_name" class="w-full px-4 py-3 rounded-xl border border-border outline-none focus:ring-1 focus:ring-brand bg-white/5 text-sm font-bold text-main" placeholder="e.g. Daily Hadith Series"/>
                </div>
                <div>
                    <label class="block text-[10px] font-black text-white/50 uppercase tracking-widest mb-2 ml-1">Strategic Topic / Prompt</label>
                    <textarea id="auto_topic" class="w-full px-4 py-3 rounded-xl border border-border outline-none focus:ring-1 focus:ring-brand min-h-[100px] bg-white/5 text-sm leading-relaxed text-white placeholder:text-white/20" placeholder="Define the AI mandate..."></textarea>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-2 ml-1">Strategy Profile</label>
                        <select id="auto_profile_id" class="w-full px-4 py-3 rounded-xl border border-border outline-none bg-white/5 text-white font-bold text-xs appearance-none cursor-pointer hover:border-brand transition-colors">
                            <option value="" class="bg-[#0f172a]">-- Direct Synthesis --</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-text-muted uppercase tracking-widest mb-2 flex justify-between px-1">
                            <span>Creative Variance</span>
                            <span id="creativity_val" class="text-brand font-black">3 / 5</span>
                        </label>
                        <div class="pt-2">
                            <input type="range" id="auto_creativity" min="1" max="5" value="3" class="w-full accent-brand cursor-pointer h-1 bg-white/10 rounded-full appearance-none" oninput="document.getElementById('creativity_val').textContent = this.value + ' / 5'">
                        </div>
                    </div>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-[10px] font-black text-text-muted uppercase tracking-widest mb-2 ml-1">Style Matrix</label>
                        <select id="auto_style" class="w-full px-4 py-3 rounded-xl border border-border outline-none bg-white/5 text-xs text-white appearance-none cursor-pointer">
                            <option value="islamic_reminder" class="bg-[#0f172a]">Islamic Aesthetic</option>
                            <option value="educational" class="bg-[#0f172a]">Pro-Educational</option>
                            <option value="motivational" class="bg-[#0f172a]">High Energy</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-text-muted uppercase tracking-widest mb-2 ml-1">Narrative Tone</label>
                        <select id="auto_tone" class="w-full px-4 py-3 rounded-xl border border-border outline-none bg-white/5 text-xs text-white appearance-none cursor-pointer">
                            <option value="short" class="bg-[#0f172a]">Punchy / Modern</option>
                            <option value="medium" selected class="bg-[#0f172a]">Balanced Hybrid</option>
                            <option value="long" class="bg-[#0f172a]">Deep Dive / Story</option>
                        </select>
                    </div>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-[10px] font-black text-text-muted uppercase tracking-widest mb-2 ml-1">Linguistic Mode</label>
                        <select id="auto_lang" class="w-full px-4 py-3 rounded-xl border border-border outline-none bg-white/5 text-xs text-white appearance-none cursor-pointer">
                            <option value="english" class="bg-[#0f172a]">Standard Global</option>
                            <option value="arabic_mix" selected class="bg-[#0f172a]">English + Arabic Lexicon</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-2 ml-1">Deployment Time (Local)</label>
                        <input type="time" id="auto_time" class="w-full px-4 py-3 rounded-xl border border-border outline-none bg-white/5 text-xs text-white [color-scheme:dark]" value="09:00"/>
                    </div>
                </div>
                <div class="p-6 bg-brand/5 rounded-[2rem] border border-brand/10 space-y-6">
                    <div class="flex items-center gap-3">
                        <input type="checkbox" id="auto_use_library" class="w-5 h-5 rounded border-border bg-white/5 text-brand focus:ring-brand" checked/>
                        <label for="auto_use_library" class="text-sm font-black text-main">Sync with Content Library</label>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-2 ml-1">Asset Mode</label>
                            <select id="auto_image_mode" class="w-full px-5 py-4 rounded-xl border border-border outline-none text-[10px] font-black uppercase tracking-widest bg-white/5 text-main appearance-none cursor-pointer">
                                <option value="reuse_last_upload" class="bg-[#0f172a]">Reuse Last Delta</option>
                                <option value="quote_card" class="bg-[#0f172a]">Auto Quote Frame</option>
                                <option value="generate" class="bg-[#0f172a]">Neural Synthesis (AI)</option>
                                <option value="none" class="bg-[#0f172a]">No Visual (Meta Only)</option>
                                <option value="library_tag" class="bg-[#0f172a]">Logic-Based Tag</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-2 ml-1">Entropy Lookback</label>
                            <input type="number" id="auto_lookback" class="w-full px-5 py-4 rounded-xl border border-border bg-white/5 text-main" value="30"/>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                        <div class="flex items-center gap-3">
                            <input type="checkbox" id="auto_arabic" class="w-4 h-4 rounded border-border bg-white/5 text-brand focus:ring-brand"/>
                            <label for="auto_arabic" class="text-[10px] font-black text-muted uppercase tracking-widest">Arabic Script</label>
                        </div>
                        <div class="flex items-center gap-3">
                            <input type="checkbox" id="auto_enabled" class="w-4 h-4 rounded border-border bg-white/5 text-brand focus:ring-brand" checked/>
                            <label for="auto_enabled" class="text-[10px] font-black text-brand uppercase tracking-widest">Live Switch</label>
                        </div>
                    </div>
                </div>
                <!-- Hadith Enrichment Section -->
                <div class="p-6 bg-brand/5 rounded-[2rem] border border-brand/10 space-y-4">
                    <div class="flex items-center gap-3">
                        <input type="checkbox" id="auto_enrich_hadith" class="w-5 h-5 rounded border-border bg-white/5 text-brand focus:ring-brand"/>
                        <label for="auto_enrich_hadith" class="text-sm font-black text-brand tracking-tight">Sunnah.com Deep Enrichment</label>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-2 ml-1">Niche Topic</label>
                            <input type="text" id="auto_hadith_topic" class="w-full px-5 py-4 rounded-xl border border-border bg-white/5 outline-none text-xs text-main" placeholder="Auto-detecting..."/>
                        </div>
                        <div>
                            <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-2 ml-1">Max Tokens</label>
                            <input type="number" id="auto_hadith_maxlen" class="w-full px-5 py-4 rounded-xl border border-border bg-white/5 outline-none text-xs text-main" value="450"/>
                        </div>
                    </div>
                </div>
                <div id="auto_msg" class="text-[10px] font-black italic tracking-widest text-center h-4"></div>
            </div>
            <div class="p-8 border-t border-border bg-white/5 flex gap-4">
                <button onclick="hideCreateAuto()" class="flex-1 px-8 py-4 rounded-xl border border-border bg-transparent font-black text-muted hover:bg-white/5 transition-all text-xs tracking-widest uppercase italic">Cancel</button>
                <button onclick="saveAutomation()" class="flex-1 btn-primary text-xs tracking-widest uppercase italic py-4">Deploy Automation</button>
            </div>
        </div>
    </div>

    <!-- Post Editor Modal -->
    <div id="post_modal" class="hidden fixed inset-0 bg-black/60 z-[120] backdrop-blur-md flex items-center justify-center p-4">
        <div class="tool-card w-full max-w-4xl overflow-hidden flex flex-col max-h-[90vh]">
            <div class="px-8 py-7 border-b border-border flex justify-between items-center bg-white/5">
                <div class="flex items-center gap-4">
                    <h3 class="text-xl font-black text-main italic tracking-tighter text-gradient">Post Intelligence Lab</h3>
                    <span id="post_edit_status" class="px-4 py-1.5 rounded-full text-[9px] font-black uppercase tracking-widest bg-brand/10 text-brand border border-brand/20">Active Node</span>
                </div>
                <button onclick="hidePostEditor()" class="w-10 h-10 rounded-xl bg-white/5 text-text-muted hover:text-main hover:bg-white/10 flex items-center justify-center transition-all border border-border">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
            </div>
            <div class="flex-1 overflow-hidden flex flex-col lg:flex-row">
                <!-- Media Preview -->
                <div class="lg:w-1/2 bg-main flex items-center justify-center p-6 group relative overflow-hidden">
                    <div class="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent z-0"></div>
                    <img id="post_edit_img" src="" class="max-w-full max-h-full object-contain shadow-2xl rounded-2xl z-10 relative border border-border"/>
                    <div class="absolute bottom-8 flex gap-3 opacity-0 group-hover:opacity-100 transition-all z-20 translate-y-4 group-hover:translate-y-0">
                        <button onclick="regeneratePostImage()" class="btn-primary text-[10px] py-4 px-6 uppercase italic tracking-widest">✨ AI Regenerate</button>
                        <label class="bg-white/10 text-white px-6 py-4 rounded-xl text-[10px] font-black uppercase tracking-widest backdrop-blur-md border border-white/10 hover:bg-white/20 cursor-pointer transition-all">
                            Replace File
                            <input type="file" id="post_media_replace" class="hidden" onchange="attachMediaToPost(this)"/>
                        </label>
                    </div>
                </div>
                <!-- Content Editor -->
                <div class="lg:w-1/2 p-10 overflow-y-auto space-y-8 bg-transparent">
                    <input type="hidden" id="post_edit_id" value=""/>
                    <div>
                        <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-3 ml-1">Narrative Content</label>
                        <textarea id="post_edit_caption" class="w-full px-5 py-5 rounded-2xl bg-white/5 border border-border outline-none focus:ring-1 focus:ring-brand min-h-[220px] text-sm leading-relaxed text-main" placeholder="Write your content here..."></textarea>
                        <div class="flex justify-end mt-4">
                           <button onclick="regeneratePostCaption()" class="text-[9px] font-black text-brand uppercase tracking-widest hover:brightness-125 transition-all flex items-center gap-1.5 italic">✨ Optimize with AI</button>
                        </div>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-white/50 uppercase tracking-widest mb-3 ml-1">Growth Keywords</label>
                        <textarea id="post_edit_hashtags" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border outline-none focus:ring-1 focus:ring-brand text-xs font-mono text-brand placeholder:text-brand/30" placeholder="#faith #socialsaas #ai"></textarea>
                    </div>
                    <div class="grid grid-cols-2 gap-6">
                        <div>
                            <label class="block text-[10px] font-black text-white/50 uppercase tracking-widest mb-3 ml-1">Vision Alt Text</label>
                            <input id="post_edit_alt" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border outline-none text-xs text-white placeholder:text-white/20" placeholder="AI accessibility description"/>
                        </div>
                        <div>
                            <label class="block text-[10px] font-black text-white/50 uppercase tracking-widest mb-3 ml-1">Deployment Clock (UTC)</label>
                            <input type="datetime-local" id="post_edit_time" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border outline-none text-xs text-white [color-scheme:dark]"/>
                        </div>
                    </div>
                    <div id="post_edit_flags" class="flex flex-wrap gap-2 pt-2"></div>
                </div>
            </div>
            <div class="p-8 border-t border-border bg-white/5 flex gap-4 justify-between items-center">
                <button onclick="deletePostUI()" class="px-8 py-4 rounded-xl border border-rose-500/20 bg-rose-500/5 font-black text-rose-500 text-[10px] uppercase tracking-widest hover:bg-rose-500/10 transition-all">Delete Node</button>
                <div class="flex gap-4">
                    <button onclick="hidePostEditor()" class="px-8 py-4 rounded-xl border border-border bg-transparent font-black text-muted text-[10px] uppercase tracking-widest hover:bg-white/5 transition-all">Cancel</button>
                    <button id="post_publish_now_btn" onclick="publishPostNow()" class="hidden px-8 py-4 rounded-xl border border-brand bg-brand/10 text-brand font-black text-[10px] uppercase tracking-widest hover:bg-brand/20 transition-all">🚀 Sync Now</button>
                    <button onclick="savePost()" class="btn-primary px-10">Commit Changes</button>
                </div>
            </div>
        </div>
    </div>

    <!-- 1) Upload Section -->
    <div class="lg:col-span-4 lg:sticky lg:top-24 h-fit space-y-8">
      <!-- Posts Tab -->
      <div id="tab_feed" class="hidden space-y-8 fade-in">
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-8">
            <!-- Content Engine (Left/Top) -->
            <div class="lg:col-span-4 space-y-8">
                <section class="tool-card">
                    <h2 class="text-lg font-black italic tracking-tighter mb-6 flex items-center gap-3">
                        <div class="w-8 h-8 rounded-lg bg-brand/10 flex items-center justify-center">
                            <svg class="w-4 h-4 text-brand" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
                        </div>
                        Content Factory
                    </h2>
                    <div id="intake_steps" class="space-y-6 text-sm">
                        <!-- Step 1: Target -->
                        <div id="step_1" class="space-y-6">
                            <div class="space-y-2">
                                <label class="text-[10px] font-black text-muted uppercase tracking-widest pl-1">Configuration Step 1: Destination</label>
                                <div id="selected_acc_box" class="p-5 bg-white/5 border border-border rounded-2xl flex items-center justify-between cursor-pointer hover:bg-white/10 transition-all group">
                                    <div class="flex items-center gap-4">
                                        <div class="w-10 h-10 rounded-xl bg-brand/10 flex items-center justify-center text-brand font-black group-hover:scale-110 transition-transform">IG</div>
                                        <div>
                                            <div id="active_account_display" class="font-bold text-main">Select Account</div>
                                            <div class="text-[10px] text-muted font-bold uppercase tracking-widest">Active Workspace</div>
                                        </div>
                                    </div>
                                    <svg class="w-5 h-5 text-muted transition-transform group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M9 5l7 7-7 7"/></svg>
                                </div>
                            </div>
                            <button onclick="goToStep(2)" class="btn-primary w-full py-4 uppercase tracking-widest text-xs">Analyze Source &rarr;</button>
                        </div>

                        <!-- Step 2: Source -->
                        <div id="step_2" class="hidden space-y-6 fade-in">
                            <div class="space-y-2">
                                <label class="text-[10px] font-black text-muted uppercase tracking-widest pl-1">Configuration Step 2: Intelligence</label>
                                <textarea id="source_text" class="w-full p-5 rounded-2xl border border-border bg-white/5 focus:bg-white/10 focus:ring-1 focus:ring-brand outline-none min-h-[160px] resize-none text-sm leading-relaxed" placeholder="Brief the AI on established goals, niche themes, and specific creative constraints..."></textarea>
                            </div>
                            <div class="flex gap-3">
                                <button onclick="goToStep(1)" class="flex-1 px-4 py-4 border border-border rounded-xl text-xs font-black uppercase tracking-widest hover:bg-white/5 transition-all">Back</button>
                                <button onclick="goToStep(3)" class="flex-1 btn-primary text-xs uppercase tracking-widest">Next Phase &rarr;</button>
                            </div>
                        </div>

                        <!-- Step 3: Media -->
                        <div id="step_3" class="hidden space-y-6 fade-in">
                            <div class="space-y-2">
                                <label class="text-[10px] font-black text-muted uppercase tracking-widest pl-1">Configuration Step 3: Assets</label>
                                <div class="relative border-2 border-dashed border-border rounded-2xl p-10 flex flex-col items-center justify-center gap-4 hover:border-brand/40 hover:bg-white/5 transition-all cursor-pointer group">
                                    <input id="image" type="file" accept="image/*" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer" onchange="updateFileName(this)"/>
                                    <div id="upload_preview_container" class="hidden w-20 h-20 rounded-2xl border border-border overflow-hidden shadow-2xl scale-110">
                                        <img id="upload_preview_img" class="w-full h-full object-cover"/>
                                    </div>
                                    <div id="upload_prompt_ui" class="text-center">
                                        <div class="w-12 h-12 rounded-full bg-brand/10 flex items-center justify-center text-brand mb-3 mx-auto group-hover:bg-brand group-hover:text-main transition-all">
                                            <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                                        </div>
                                        <div id="file_name_display" class="text-xs font-black uppercase tracking-widest text-muted">Inject Reference Image</div>
                                        <div class="text-[10px] text-muted mt-1 uppercase font-bold">Optional Enhancement</div>
                                    </div>
                                </div>
                            </div>
                            <div class="flex flex-col gap-3 pt-2">
                                <button id="intake_btn" onclick="uploadPost()" class="btn-primary w-full py-5 text-xs uppercase tracking-widest shadow-2xl shadow-brand/20">✨ Synthesize & Deploy</button>
                                <button onclick="goToStep(1)" class="text-[10px] uppercase font-black tracking-widest text-muted hover:text-main transition-colors">Abort & Restart</button>
                            </div>
                            <div id="upload_msg" class="text-center text-xs font-black uppercase tracking-widest text-brand h-4 animate-pulse"></div>
                        </div>
                    </div>
                </section>
            </div>


            <!-- Feed Section (Right) -->
            <div class="lg:col-span-8 space-y-8">
                <div class="flex items-center justify-between">
                    <h2 class="text-lg font-black italic tracking-tighter text-gradient">Intelligence Stream</h2>
                    <div class="flex items-center gap-3">
                        <select id="status_filter" onchange="refreshAll()" class="px-4 py-2 rounded-xl border border-border bg-white/5 text-xs font-black uppercase tracking-widest outline-none focus:ring-1 focus:ring-brand text-muted">
                            <option value="">All Streams</option>
                            <option value="submitted">Submitted</option>
                            <option value="drafted">Drafted</option>
                            <option value="needs_review">Review Filter</option>
                            <option value="scheduled">Scheduled</option>
                            <option value="published">Published</option>
                            <option value="failed">Critical Failures</option>
                        </select>
                    </div>
                </div>
                <div id="stats" class="grid grid-cols-2 lg:grid-cols-4 gap-4"></div>
                <div id="error" class="hidden p-5 rounded-2xl bg-rose-500/10 text-rose-400 text-[10px] font-black uppercase tracking-widest border border-rose-500/20 animate-pulse"></div>
                <div id="list" class="grid grid-cols-1 md:grid-cols-2 gap-6"></div>
            </div>

        </div>
      </div>

      <!-- Calendar Tab -->
      <div id="tab_calendar" class="hidden space-y-6 fade-in">
        <div class="tool-card min-h-[600px]">
            <div id="calendar_el"></div>
        </div>
      </div>

      <!-- Automations Tab -->
      <div id="tab_automations" class="hidden space-y-6 fade-in">
        <div class="flex items-center justify-between mb-4">
            <h2 class="text-xl font-black text-main italic tracking-tighter text-gradient">Content Automations</h2>
            <button onclick="showCreateAuto()" class="btn-primary py-4 px-8 text-[10px] tracking-widest uppercase italic">New Stream</button>
        </div>
        <div id="auto_list" class="grid grid-cols-1 gap-4"></div>
      </div>

      <!-- Profiles Tab -->
      <div id="tab_profiles" class="hidden space-y-6 fade-in">
        <div class="flex items-center justify-between mb-4">
            <h2 class="text-xl font-black text-main italic tracking-tighter text-gradient">Neural DNA Profiles</h2>
            <button onclick="showCreateProfile()" class="btn-primary py-4 px-8 text-[10px] tracking-widest uppercase italic">New Identity</button>
        </div>
        <div id="profile_list" class="grid grid-cols-1 md:grid-cols-2 gap-4"></div>
      </div>

      <!-- Media Tab -->
      <div id="tab_media" class="hidden space-y-6 fade-in">
        <div class="flex items-center justify-between mb-4">
            <h2 class="text-xl font-black text-main italic tracking-tighter text-gradient">Asset Repository</h2>
            <label class="btn-primary cursor-pointer hover:opacity-90 transition-all py-4 px-8 text-[10px] tracking-widest uppercase italic">
                Siphon Asset
                <input type="file" id="media_upload_input" class="hidden" onchange="uploadMedia(this)"/>
            </label>
        </div>
        <div id="media_list" class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4"></div>
      </div>

    </div>

    <!-- Platform Drawer -->
    <div id="platform_panel" class="hidden fixed inset-0 bg-black/60 z-[100] backdrop-blur-md flex justify-end" onclick="if(event.target === this) togglePlatformPanel()">
        <div class="w-full max-w-4xl bg-surface h-full shadow-2xl p-10 flex flex-col overflow-y-auto border-l border-border" onclick="event.stopPropagation()">
            <div class="flex justify-between items-center mb-10">
                <div>
                    <h2 class="text-3xl font-black text-main italic tracking-tighter text-gradient">Platform OS</h2>
                    <div class="flex gap-8 mt-6">
                        <button id="tab_btn_users" onclick="switchPlatformTab('users')" class="text-[10px] font-black uppercase tracking-widest border-b-2 border-brand pb-2 text-main">Neural Network Users</button>
                        <button id="tab_btn_inquiries" onclick="switchPlatformTab('inquiries')" class="text-[10px] font-black uppercase tracking-widest text-muted hover:text-main transition-colors pb-2">External Inquiries</button>
                    </div>
                </div>
                <button onclick="togglePlatformPanel()" class="w-12 h-12 rounded-xl bg-white/5 border border-border flex items-center justify-center text-muted hover:text-main hover:bg-white/10 transition-all">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
            
            <div class="overflow-x-auto rounded-[2rem] border border-border bg-white/5 backdrop-blur-sm">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="bg-white/5 border-b border-border">
                            <th class="py-4 px-6 text-[10px] font-black uppercase tracking-widest text-text-muted">Entity / Avatar</th>
                            <th class="py-4 px-6 text-[10px] font-black uppercase tracking-widest text-text-muted">Communication</th>
                            <th class="py-4 px-6 text-[10px] font-black uppercase tracking-widest text-text-muted">Nodes</th>
                            <th class="py-4 px-6 text-[10px] font-black uppercase tracking-widest text-text-muted text-right">Operations</th>
                        </tr>
                    </thead>
                    <tbody id="platform_user_table" class="divide-y divide-border/20 text-sm font-medium text-main">
                    </tbody>
                </table>
            </div>

            <!-- Inquiries View -->
            <div id="inquiries_container" class="hidden">
                <div class="overflow-x-auto rounded-[2rem] border border-border bg-white/5 backdrop-blur-sm">
                    <table class="w-full text-left border-collapse">
                        <thead>
                            <tr class="bg-white/5 border-b border-border">
                                <th class="py-4 px-6 text-[10px] font-black uppercase tracking-widest text-muted">Origin User</th>
                                <th class="py-4 px-6 text-[10px] font-black uppercase tracking-widest text-muted">Channel</th>
                                <th class="py-4 px-6 text-[10px] font-black uppercase tracking-widest text-muted">Message Payload</th>
                                <th class="py-4 px-6 text-[10px] font-black uppercase tracking-widest text-muted text-right">Resolution</th>
                            </tr>
                        </thead>
                        <tbody id="platform_inquiry_table" class="divide-y divide-border/20 text-sm font-medium text-main">
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>


    <!-- Content Profile Modal -->
    <div id="profile_modal" class="hidden fixed inset-0 bg-black/60 z-[110] backdrop-blur-md flex items-center justify-center p-4">
        <div class="tool-card w-full max-w-2xl flex flex-col max-h-[90vh] overflow-hidden">
            <div class="px-8 py-7 border-b border-border flex justify-between items-center bg-white/5 text-gradient">
                <div class="flex items-center gap-4">
                    <div class="w-10 h-10 rounded-xl bg-brand/10 text-brand flex items-center justify-center border border-brand/20">
                        <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" /></svg>
                    </div>
                    <div>
                        <h3 class="text-xl font-black text-main italic tracking-tighter text-gradient">Content DNA Profile</h3>
                        <p class="text-[10px] font-black text-muted uppercase tracking-widest mt-0.5">Define Neural Voice & Constraints</p>
                    </div>
                </div>
                <button onclick="hideCreateProfile()" class="w-10 h-10 rounded-xl bg-white/5 text-text-muted hover:text-main hover:bg-white/10 flex items-center justify-center transition-all border border-border">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
            </div>
            <div class="p-10 overflow-y-auto space-y-8">
                <input type="hidden" id="edit_profile_id" value=""/>
                
                <div class="bg-brand/5 p-6 rounded-[2.5rem] border border-brand/10">
                    <label class="block text-[10px] font-black text-brand uppercase tracking-widest mb-4 italic ml-1">Neural Baseline Presets</label>
                    <div class="flex flex-wrap gap-2">
                        <button onclick="seedProfile('islamic_education')" class="px-5 py-2.5 bg-white/5 border border-border text-muted text-[10px] font-black uppercase tracking-widest rounded-xl hover:bg-brand hover:border-brand hover:text-white transition-all">Islamic Edu</button>
                        <button onclick="seedProfile('fitness_coach')" class="px-5 py-2.5 bg-white/5 border border-border text-muted text-[10px] font-black uppercase tracking-widest rounded-xl hover:bg-brand hover:border-brand hover:text-white transition-all">Physique Pro</button>
                        <button onclick="seedProfile('real_estate')" class="px-5 py-2.5 bg-white/5 border border-border text-muted text-[10px] font-black uppercase tracking-widest rounded-xl hover:bg-brand hover:border-brand hover:text-white transition-all">Prime Assets</button>
                        <button onclick="seedProfile('small_business')" class="px-5 py-2.5 bg-white/5 border border-border text-muted text-[10px] font-black uppercase tracking-widest rounded-xl hover:bg-brand hover:border-brand hover:text-white transition-all">E-Commerce</button>
                        <button onclick="seedProfile('personal_branding')" class="px-5 py-2.5 bg-white/5 border border-border text-muted text-[10px] font-black uppercase tracking-widest rounded-xl hover:bg-brand hover:border-brand hover:text-white transition-all">Identity</button>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-6">
                    <div>
                        <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-3 ml-1">Profile Designation</label>
                        <input id="prof_name" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border outline-none focus:ring-1 focus:ring-brand text-xs font-bold text-main" placeholder="e.g. Modern Minimalist"/>
                    </div>

                    <div>
                        <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-3 ml-1">Niche Category</label>
                        <input id="prof_niche" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border outline-none focus:ring-1 focus:ring-brand text-xs font-bold text-main" placeholder="e.g. real_estate, fitness"/>
                    </div>
                </div>
                
                <div>
                    <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-3 ml-1">Focus Description (What to post)</label>
                    <textarea id="prof_focus" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border outline-none focus:ring-1 focus:ring-brand min-h-[80px] text-xs font-bold text-main leading-relaxed" placeholder="Specific focus..."></textarea>
                </div>
                
                <div class="grid grid-cols-2 gap-6">
                    <div>
                        <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-3 ml-1">Content Goals</label>
                        <textarea id="prof_goals" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border outline-none focus:ring-1 focus:ring-brand min-h-[80px] text-xs font-bold text-main leading-relaxed" placeholder="Educate, Sell..."></textarea>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-3 ml-1">Tone & Style</label>
                        <textarea id="prof_tone" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border outline-none focus:ring-1 focus:ring-brand min-h-[80px] text-xs font-bold text-main leading-relaxed" placeholder="Professional..."></textarea>
                    </div>
                </div>
                
                <div class="grid grid-cols-2 gap-6">
                    <div>
                        <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-3 ml-1">Allowed Vectors (CSV)</label>
                        <input id="prof_allowed" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border outline-none focus:ring-1 focus:ring-brand text-xs font-bold text-main" placeholder="topic1, topic2"/>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-3 ml-1">Banned Vectors (CSV)</label>
                        <input id="prof_banned" class="w-full px-5 py-4 rounded-2xl bg-white/5 border border-border outline-none focus:ring-1 focus:ring-brand text-xs font-bold text-main" placeholder="politics, drama"/>
                    </div>
                </div>
            </div>
            <div class="p-8 border-t border-border bg-white/5 flex justify-end gap-3">
                <button onclick="hideCreateProfile()" class="px-8 py-4 rounded-xl border border-border text-muted font-black text-[10px] uppercase tracking-widest hover:bg-white/5 transition-all">Cancel</button>
                <button onclick="saveProfileWrapper()" class="btn-primary px-10 text-[10px] py-4 italic uppercase tracking-widest">Save Synthesis DNA</button>
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

// --- THEME LOGIC ---
function setTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('admin_theme', t);
}

// --- INTAKE STEP LOGIC ---
function goToStep(s) {
    const steps = [1, 2, 3];
    steps.forEach(step => {
        const el = document.getElementById('step_' + step);
        if (el) el.classList.toggle('hidden', step !== s);
    });
}

// Global initialization
(function() {
    const saved = localStorage.getItem('admin_theme') || 'startup';
    document.documentElement.setAttribute('data-theme', saved);
    setTimeout(() => {
        goToStep(1);
        loadProfile();
    }, 100);
})();

function togglePlatformPanel() {
    const el = document.getElementById("platform_panel");
    const isHidden = el.classList.contains("hidden");
    if (isHidden) {
        el.classList.remove("hidden");
        switchPlatformTab('users');
    } else {
        el.classList.add("hidden");
    }
}

function switchPlatformTab(tab) {
    const usersTable = document.querySelector("#platform_user_table").closest('.overflow-x-auto');
    const inquiriesContainer = document.getElementById("inquiries_container");
    const btnUsers = document.getElementById("tab_btn_users");
    const btnInquiries = document.getElementById("tab_btn_inquiries");

    if (tab === 'users') {
        usersTable.classList.remove("hidden");
        inquiriesContainer.classList.add("hidden");
        btnUsers.className = "text-[10px] font-black uppercase tracking-widest border-b-2 border-brand pb-1 text-main";
        btnInquiries.className = "text-[10px] font-black uppercase tracking-widest text-muted hover:text-main transition-colors pb-1";
        loadPlatformUsers();
    } else {
        usersTable.classList.add("hidden");
        inquiriesContainer.classList.remove("hidden");
        btnUsers.className = "text-[10px] font-black uppercase tracking-widest text-muted hover:text-main transition-colors pb-1";
        btnInquiries.className = "text-[10px] font-black uppercase tracking-widest border-b-2 border-brand pb-1 text-main";
        loadPlatformInquiries();
    }
}


function toggleGuideModal() {
    document.getElementById("guide_modal").classList.toggle("hidden");
}

async function loadPlatformUsers() {
    const tbody = document.getElementById("platform_user_table");
    tbody.innerHTML = `<tr><td colspan="4" class="text-center py-8 text-muted font-bold uppercase tracking-widest text-xs animate-pulse">Loading Platform Data...</td></tr>`;
    try {
        const users = await request("/admin/users");
        if (users.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="text-center py-8 text-muted font-bold uppercase">No users found</td></tr>`;
            return;
        }
        tbody.innerHTML = users.map(u => `
            <tr class="hover:bg-white/5 transition-colors">
                <td class="py-4 px-4 font-black text-main flex items-center gap-2">
                    ${u.is_superadmin ? '<span class="px-2 py-0.5 bg-brand/10 text-brand border border-brand/20 rounded text-[9px] uppercase tracking-widest">Admin</span>' : ''}
                    ${esc(u.name)}
                </td>
                <td class="py-4 px-4 text-muted">${esc(u.email)}</td>
                <td class="py-4 px-4 text-[10px] font-black uppercase tracking-widest text-muted opacity-60">${esc(u.orgs || 'None')}</td>

                <td class="py-4 px-4 text-right">
                    ${!u.is_superadmin ? `<button onclick="deleteUser(${u.id})" class="text-xs font-black uppercase tracking-widest text-rose-500 hover:text-rose-700 hover:underline">Delete</button>` : ''}
                </td>
            </tr>
        `).join("");
    } catch(e) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center py-8 text-rose-500 font-bold">${e.message}</td></tr>`;
    }
}

async function loadPlatformInquiries() {
    const tbody = document.getElementById("platform_inquiry_table");
    tbody.innerHTML = `<tr><td colspan="4" class="text-center py-8 text-muted font-bold uppercase tracking-widest text-xs animate-pulse">Scanning Inbox...</td></tr>`;
    try {
        const data = await request("/admin/inquiries");
        if (data.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="text-center py-8 text-muted font-bold uppercase tracking-widest text-[10px]">No messages yet</td></tr>`;
            return;
        }
    tbody.innerHTML = data.map(m => `
        <tr class="hover:bg-white/5 transition-colors group">
            <td class="py-6 px-6 align-top">
                <div class="font-black text-main italic tracking-tight">${esc(m.name)}</div>
                <div class="text-[9px] text-muted uppercase tracking-widest font-black mt-1">${new Date(m.created_at).toLocaleString()}</div>
            </td>
            <td class="py-6 px-6 align-top text-xs font-black text-brand uppercase tracking-widest">${esc(m.email)}</td>
            <td class="py-6 px-6 align-top">
                <p class="text-muted leading-relaxed max-w-lg text-sm italic font-medium">"${esc(m.message)}"</p>
            </td>
            <td class="py-6 px-6 align-top text-right">
                <button onclick="deleteInquiry(${m.id})" class="text-[10px] font-black uppercase tracking-widest text-muted hover:text-rose-500 transition-colors opacity-0 group-hover:opacity-100">Delete</button>
            </td>
        </tr>
    `).join("");

    } catch(e) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center py-8 text-rose-500 font-bold">${e.message}</td></tr>`;
    }
}

async function deleteInquiry(id) {
    if(!confirm("Are you sure you want to delete this inquiry?")) return;
    try {
        await request(`/admin/inquiries/${id}`, { method: "DELETE" });
        await loadPlatformInquiries();
    } catch(e) { alert("Delete failed: " + e.message); }
}

async function deleteUser(id) {
    if(!confirm("MANDATORY WARNING: Are you sure you want to completely erase this user? This cannot be undone.")) return;
    try {
        await request(`/admin/users/${id}`, { method: "DELETE" });
        await loadPlatformUsers();
    } catch(e) { alert("Delete failed: " + e.message); }
}

let ACCOUNTS = [];
let ACTIVE_ACCOUNT_ID = localStorage.getItem("active_ig_id") || null;
let ACTIVE_ORG_ID = localStorage.getItem("active_org_id") || null;
let ME = null;
let ACTIVE_TAB = "dashboard";
let calendar = null;

function switchTab(t) {
    ACTIVE_TAB = t;
    const views = ['dashboard', 'feed', 'calendar', 'automations', 'profiles', 'media'];
    views.forEach(v => {
        // Content areas
        const el = document.getElementById("tab_" + v);
        if(el) el.classList.toggle("hidden", v !== t);
        
        // Sidebar items
        const nav = document.getElementById("nav_" + v);
        if(nav) nav.classList.toggle("active", v === t);
    });
    
    // Breadcrumb
    const breadcrumb = document.getElementById("breadcrumb_tab");
    if (breadcrumb) {
        breadcrumb.textContent = t.charAt(0).toUpperCase() + t.slice(1);
    }

    if (t === 'calendar' && typeof initCalendar === 'function') {
        initCalendar();
    }
    refreshAll();
}

function esc(s) { return (s ?? "").toString().replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;"); }
function toggleSettings() { document.getElementById("settings_panel").classList.toggle("hidden"); }
function updateFileName(input) { 
    const file = input.files[0];
    if (file) {
        console.log(`DEBUG: Selected file - ${file.name}, Size: ${file.size} bytes, Type: ${file.type}`);
        document.getElementById("file_name_display").textContent = file.name;
    } else {
        document.getElementById("file_name_display").textContent = "Inject Reference Image";
    }
}
async function request(url, opts = {}) {
    let orgHeader = {};
    if (ACTIVE_ORG_ID) {
        orgHeader = { "X-Org-Id": ACTIVE_ORG_ID.toString() };
    }

    opts.headers = { 
        ...opts.headers, 
        ...orgHeader,
        "ngrok-skip-browser-warning": "69420"
    };
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
            if (ACTIVE_TAB === 'dashboard') {
                await loadStats();
            } else if (ACTIVE_TAB === 'feed') {
                await loadPosts();
            } else if (ACTIVE_TAB === 'automations') {
                await loadAutomations();
            } else if (ACTIVE_TAB === 'profiles') {
                await loadProfiles();
            } else if (ACTIVE_TAB === 'calendar') {
                await loadCalendarEvents();
            } else if (ACTIVE_TAB === 'media') {
                await loadMediaLibrary();
            }
        } else {
            // Optional: show empty state
        }
    } catch(e) { console.error(e); }
}


async function loadAutomations() {
    const list = document.getElementById("auto_list");
    list.innerHTML = `<div class="py-12 text-center text-muted font-black uppercase text-xs animate-pulse">Scanning Robotics...</div>`;
    try {
        const j = await request(`/automations/?ig_account_id=${ACTIVE_ACCOUNT_ID}`);
        if (!j.length) {
            list.innerHTML = `
            <div class="col-span-full py-24 text-center border-2 border-dashed border-border rounded-[2.5rem] bg-white/5 fade-in">
                <div class="w-16 h-16 bg-white/5 rounded-3xl shadow-xl flex items-center justify-center mx-auto mb-8 border border-border">
                    <svg class="w-8 h-8 text-brand" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
                </div>
                <h3 class="text-sm font-black text-main mb-2 uppercase tracking-widest">No Automations Found</h3>
                <p class="text-[10px] text-muted font-bold uppercase tracking-widest max-w-xs mx-auto mb-8">Initialize your first AI job to start auto-content delivery.</p>
                <button onclick="showCreateAuto()" class="btn-primary px-6 py-2.5 text-[10px] font-black uppercase tracking-widest">Initialize First AI Job</button>
            </div>`;
            return;
        }
        list.innerHTML = j.map(a => renderAuto(a)).join("");
    } catch(e) { setError("Auto Error: " + e.message); }
}

function renderAuto(a) {
    const err = a.last_error ? `<p class="mt-2 text-[10px] bg-red-50 text-red-600 border border-red-100 p-2 rounded-xl font-bold uppercase tracking-tight">Error: ${esc(a.last_error)}</p>` : '';
    return `
    <div class="bg-white/5 border border-border rounded-3xl p-6 flex flex-col items-stretch group hover:bg-white/10 hover:shadow-xl transition-all duration-300 fade-in">
        <div class="flex items-start justify-between mb-4">
            <div class="flex-1">
                <div class="flex items-center gap-3 mb-2">
                    <h4 class="text-lg font-black text-main">${esc(a.name)}</h4>
                    <span class="px-2 py-0.5 rounded-full text-[8px] font-black uppercase tracking-tighter ${a.enabled ? 'bg-brand/10 text-brand border border-brand/20' : 'bg-white/10 text-muted border border-border'}">${a.enabled ? 'Enabled' : 'Paused'}</span>
                    ${a.enrich_with_hadith ? '<span class="px-2 py-0.5 rounded-full text-[8px] font-black uppercase tracking-tighter bg-brand/10 text-brand border border-brand/20">Enriched</span>' : ''}
                </div>
                <p class="text-xs text-muted font-medium line-clamp-1 italic">Prompt: "${esc(a.topic_prompt)}"</p>
                ${err}
            </div>
            <div class="flex items-center gap-2">
                <button onclick="triggerAuto(${a.id})" class="p-3 rounded-2xl bg-white/5 border border-border text-muted hover:text-brand hover:border-brand hover:shadow-lg transition-all" title="Run Once (Create Post)">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                </button>
                <button onclick="testLLM(${a.id}, '${esc(a.topic_prompt)}', '${a.style_preset}')" class="p-3 rounded-2xl bg-white/5 border border-border text-muted hover:text-brand hover:border-brand hover:shadow-lg transition-all" title="Test AI Generation">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.341A8.001 8.001 0 0012 4a8.001 8.001 0 00-7.428 11.341c.142.311.23.642.23.978V19a2 2 0 002 2h9a2 2 0 002-2v-2.681c0-.336.088-.667.23-.978z" /></svg>
                </button>
                <button onclick="editAuto(${JSON.stringify(a).replaceAll('"', '&quot;')})" class="p-3 rounded-2xl bg-white/5 border border-border text-muted hover:text-brand hover:border-brand hover:shadow-lg transition-all" title="Edit Automation Settings">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                </button>
                <button onclick="deleteAuto(${a.id})" class="p-3 rounded-2xl bg-white/5 border border-border text-muted hover:text-rose-500 hover:border-rose-500 transition-all" title="Delete Automation">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                </button>
            </div>
        </div>
        <div class="flex flex-wrap gap-4 text-[10px] font-black uppercase tracking-widest text-muted border-t border-border pt-4">
            <span class="flex items-center gap-1.5"><svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg> ${a.post_time_local || '09:00'}</span>
            <span class="flex items-center gap-1.5"><svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" /></svg> ${a.style_preset} (${a.tone})</span>
            <span class="flex items-center gap-1.5 text-indigo-500">Last Run: ${a.last_run_at ? new Date(a.last_run_at).toLocaleDateString() : 'Never'}</span>
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
        enrich_with_hadith: getCheck("auto_enrich_hadith"),
        hadith_topic: getVal("auto_hadith_topic"),
        hadith_max_len: getNum("auto_hadith_maxlen") || 450,
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
    } catch(e) { alert("Save Failed: " + e.message); }
}

async function triggerAuto(id) {
    if(!confirm("Run this automation once right now? This will create a real post (Draft or Scheduled).")) return;
    try {
        const j = await request(`/automations/${id}/run-once`, { method: "POST" });
        if (confirm("Success! Automation triggered. View it in your feed now?")) {
            switchTab('feed');
        } else {
            refreshAll();
        }
    } catch(e) { alert("Execution Failed: " + e.message); }
}

async function runGlobalScheduler() {
    if(!confirm("Force the global scheduler to run immediately? This will check for due posts and publish them to Instagram.")) return;
    const btn = document.getElementById("run_scheduler_btn");
    const originalHtml = btn.innerHTML;
    try {
        btn.innerHTML = `<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg> Running...`;
        btn.disabled = true;

        const j = await request(`/automations/run-scheduler-now`, { method: "POST" });
        alert(`Success! Published ${j.published} items.`);
        
        btn.innerHTML = originalHtml;
        btn.disabled = false;
        refreshAll();
    } catch(e) { 
        alert("Scheduler Failed: " + e.message); 
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
        alert(preview);
    } catch(e) { 
        alert("LLM Test Failed: " + e.message);
        refreshAll();
    }
}

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
        if(!confirm(`Reschedule to ${info.event.start.toISOString()}?`)) {
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
            alert(e.message); 
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
        if(!confirm(`Reschedule to ${info.event.start.toISOString()}?`)) {
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
            alert(e.message); 
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
        statusEl.textContent = p.status.toUpperCase();
        statusEl.className = `px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest ${getPostColor(p.status).includes('#') ? 'bg-white/5 text-main' : ''}`;
        
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
    } catch(e) { alert("Load Failed: " + e.message); }
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
    } catch(e) { alert("Save Failed: " + e.message); }
}

async function regeneratePostCaption() {
    const id = document.getElementById("post_edit_id").value;
    const inst = prompt("Any special instructions for the AI? (e.g. 'make it shorter', 'more poetic')");
    try {
        const p = await request(`/posts/${id}/regenerate-caption`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ instructions: inst })
        });
        document.getElementById("post_edit_caption").value = p.caption;
        document.getElementById("post_edit_hashtags").value = (p.hashtags || []).join(" ");
    } catch(e) { alert(e.message); }
}

async function regeneratePostImage() {
    const id = document.getElementById("post_edit_id").value;
    const mode = prompt("Image Mode? (ai_nature_photo, ai_islamic_pattern, ai_calligraphy_no_text, ai_minimal_gradient)", "ai_nature_photo");
    if (!mode) return;
    try {
        const p = await request(`/posts/${id}/regenerate-image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_mode: mode })
        });
        document.getElementById("post_edit_img").src = p.media_url;
    } catch(e) { alert(e.message); }
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
    } catch(e) { alert(e.message); }
}

async function publishPostNow() {
    const id = document.getElementById("post_edit_id").value;
    if (!confirm("Publish this to Instagram immediately?")) return;
    try {
        await request(`/posts/${id}/publish`, { method: "POST" });
        hidePostEditor();
        refreshAll();
    } catch(e) { alert(e.message); }
}

async function deletePostUI() {
    const id = document.getElementById("post_edit_id").value;
    if (!confirm("Discard this post entry forever?")) return;
    try {
        await request(`/posts/${id}`, { method: "DELETE" });
        hidePostEditor();
        refreshAll();
    } catch(e) { alert(e.message); }
}

// --- MEDIA LIBRARY LOGIC ---
async function loadMediaLibrary() {
    const list = document.getElementById("media_list");
    list.innerHTML = `<div class="col-span-full py-24 text-center">
        <div class="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center mx-auto mb-4 animate-pulse">
            <svg class="w-8 h-8 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
        </div>
        <div class="text-[10px] font-black uppercase tracking-widest text-muted">Archiving Assets...</div>
    </div>`;
    try {
        const j = await request("/media-assets");
        if (!j.length) {
            list.innerHTML = `
                <div class="col-span-full py-32 text-center border-2 border-dashed border-border rounded-[2rem] bg-white/5">
                    <div class="text-muted mb-6">
                        <svg class="w-16 h-16 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
                    </div>
                    <div class="text-sm font-black text-main">No media found</div>
                    <div class="text-[10px] text-muted font-bold uppercase mt-2 mb-8">Upload your assets to power the engine.</div>
                    <label class="btn-primary px-8 py-3 rounded-2xl text-[10px] uppercase tracking-widest cursor-pointer hover:opacity-90">
                        Select First Asset
                        <input type="file" onchange="uploadMedia(this)" class="hidden"/>
                    </label>
                </div>
            `;
            return;
        }
        list.innerHTML = j.map(m => `
            <div class="relative group rounded-[1.5rem] overflow-hidden aspect-square border-4 border-white/5 bg-white/5 shadow-sm hover:shadow-xl hover:scale-[1.02] transition-all duration-300">
                <img src="${m.url}" class="w-full h-full object-cover"/>
                <div class="absolute inset-0 bg-white/10 opacity-0 group-hover:opacity-100 transition-all duration-300 flex flex-col justify-end p-4">
                    <div class="flex flex-wrap gap-1 mb-auto">
                        ${(m.tags || []).map(t => `<span class="px-2 py-1 bg-white/20 backdrop-blur-md rounded-lg text-[8px] text-white font-black uppercase tracking-widest">${esc(t)}</span>`).join("")}
                    </div>
                    <div class="flex gap-2">
                        <button onclick="window.open('${m.url}', '_blank')" class="flex-1 bg-white/10 hover:bg-white/20 text-white p-2 rounded-xl backdrop-blur-md transition-all">
                            <svg class="w-4 h-4 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                        </button>
                        <button onclick="deleteMedia(${m.id})" class="flex-1 bg-rose-500/80 hover:bg-rose-600 text-white p-2 rounded-xl backdrop-blur-md transition-all">
                            <svg class="w-4 h-4 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                        </button>
                    </div>
                </div>
            </div>
        `).join("");
    } catch(e) { console.error(e); }
}

async function uploadMedia(input) {
    const file = input.files[0];
    if (!file) return;
    const tags = prompt("Enter tags (comma separated)", "nature, islamic");
    const tagsArray = tags ? tags.split(",").map(t => t.trim()) : [];
    
    const fd = new FormData();
    fd.append("image", file);
    fd.append("tags", JSON.stringify(tagsArray));
    if (ACTIVE_ACCOUNT_ID) fd.append("ig_account_id", ACTIVE_ACCOUNT_ID);
    
    try {
        await request("/media-assets", { method: "POST", body: fd });
        loadMediaLibrary();
    } catch(e) { alert(e.message); }
    input.value = "";
}

async function deleteMedia(id) {
    if(!confirm("Remove this asset from library?")) return;
    try {
        await request(`/media-assets/${id}`, { method: "DELETE" });
        loadMediaLibrary();
    } catch(e) { alert(e.message); }
}

async function deleteAuto(id) {
    if(!confirm("Remove this automation forever?")) return;
    try {
        await request(`/automations/${id}`, { method: "DELETE" });
        refreshAll();
    } catch(e) { alert(e.message); }
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

    // Hadith Enrichment
    const enrich = document.getElementById("auto_enrich_hadith");
    if(enrich) enrich.checked = !!a.enrich_with_hadith;
    
    const hTopic = document.getElementById("auto_hadith_topic");
    if(hTopic) hTopic.value = a.hadith_topic || "";
    
    const hMax = document.getElementById("auto_hadith_maxlen");
    if(hMax) hMax.value = a.hadith_max_len || 450;
    
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
    list.innerHTML = `<div class="col-span-full py-12 text-center text-muted font-black uppercase text-xs animate-pulse">Loading Profiles...</div>`;
    
    const select = document.getElementById("auto_profile_id");
    if(select) {
        select.innerHTML = `<option value="">-- Generic Setup (No Profile) --</option>`;
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
            <div class="col-span-full py-24 text-center border-2 border-dashed border-border rounded-3xl bg-white/5">
                <p class="text-sm text-muted font-black uppercase mb-4">No Profiles Found</p>
                <button onclick="showCreateProfile()" class="btn-primary px-6 py-2 rounded-xl text-xs font-black">Create First Profile</button>
            </div>`;
            return;
        }
        
        list.innerHTML = j.map(p => {
            return `
            <div class="bg-white/5 border border-border rounded-3xl p-6 flex flex-col items-stretch group hover:bg-white/10 hover:shadow-xl transition-all duration-300">
                <div class="flex items-start justify-between mb-4">
                    <div class="flex-1">
                        <div class="flex items-center gap-3 mb-2">
                            <h4 class="text-lg font-black text-main">${esc(p.name)}</h4>
                        </div>
                        <p class="text-[10px] uppercase font-black tracking-widest text-muted mb-2">Niche: <span class="text-brand">${esc(p.niche_category || 'N/A')}</span></p>
                        <p class="text-xs text-muted font-medium line-clamp-2">${esc(p.focus_description || 'No focus specified.')}</p>
                    </div>
                </div>
                <div class="mt-auto pt-4 border-t border-border flex justify-end gap-2">
                    <button onclick='editProfile(${JSON.stringify(p).replaceAll("'", "&apos;")})' class="p-3 rounded-2xl bg-white/5 border border-border text-muted hover:text-brand hover:border-brand transition-all font-bold text-xs">Edit</button>
                    <button onclick="deleteProfile(${p.id})" class="p-3 rounded-2xl bg-white/5 border border-border text-muted hover:text-rose-500 hover:border-rose-500 transition-all font-bold text-xs">Delete</button>
                </div>
            </div>`;
        }).join("");
    } catch(e) { 
        list.innerHTML = `<div class="col-span-full text-center text-rose-500 font-bold">${e.message}</div>`;
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
    
    if(!payload.name) return alert("Profile Name is required!");
    
    try {
        await request(id ? `/profiles/${id}` : "/profiles", {
            method: id ? "PATCH" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        hideCreateProfile();
        loadProfiles();
    } catch(e) { alert("Save Failed: " + e.message); }
}

async function deleteProfile(id) {
    if(!confirm("Remove this content profile?")) return;
    try {
        await request(`/profiles/${id}`, { method: "DELETE" });
        loadProfiles();
    } catch(e) { alert(e.message); }
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
    } catch(e) { alert("Failed to apply preset: " + e.message); }
}

async function loadLibrary() {
    const list = document.getElementById("library_list");
    const query = document.getElementById("library_search")?.value || "";
    list.innerHTML = `<div class="col-span-full py-12 text-center text-muted font-black uppercase text-xs animate-pulse">Browsing Archive...</div>`;
    try {
        const j = await request(`/library/?topic=${encodeURIComponent(query)}`);
        if (!j.length) {
            list.innerHTML = `
            <div class="col-span-full py-24 text-center border-2 border-dashed border-border rounded-3xl bg-white/5">
                <p class="text-sm text-muted font-black uppercase">Archive Empty</p>
                <p class="text-[10px] text-muted mt-2">Upload or Seed some content to start.</p>
            </div>`;
            return;
        }
        list.innerHTML = j.map(item => `
        <div class="bg-white/5 border border-border rounded-2xl p-5 hover:bg-white/10 hover:shadow-lg transition-all">
            <div class="flex justify-between items-start mb-3">
                <span class="px-2 py-0.5 rounded-lg bg-brand/10 text-brand text-[8px] font-black uppercase tracking-widest">${esc(item.type)}</span>
                <span class="text-[9px] font-bold text-muted">${item.topics.join(", ")}</span>
            </div>
            <h5 class="text-sm font-black text-main mb-2 line-clamp-1">${esc(item.title || 'Untitled')}</h5>
            <p class="text-xs text-muted line-clamp-3 mb-4 italic">"${esc(item.text_en)}"</p>
            <div class="flex justify-between items-center pt-3 border-t border-border">
                <span class="text-[9px] font-bold text-muted">${esc(item.source_name || 'Personal')}</span>
                <button onclick="deleteLibraryItem(${item.id})" class="text-muted hover:text-rose-500 transition-colors">
                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                </button>
            </div>
        </div>`).join("");
    } catch(e) { setError("Library Error: " + e.message); }
}

async function seedDemoContent() {
    if(!confirm("Seed database with demo Islamic content?")) return;
    try {
        await request("/library/seed-demo/", { method: "POST" });
        await loadLibrary();
        alert("Demo content seeded successfully.");
    } catch(e) { alert("Seed Failed: " + e.message); }
}

async function importLibrary(input) {
    const file = input.files[0];
    if(!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
        await request("/library/import/", { method: "POST", body: fd });
        await loadLibrary();
        alert("Import Successful!");
    } catch(e) { alert("Import Failed: " + e.message); }
    input.value = "";
}

async function deleteLibraryItem(id) {
    if(!confirm("Remove this item from library?")) return;
    try {
        await request(`/library/${id}`, { method: "DELETE" });
        await loadLibrary();
    } catch(e) { alert(e.message); }
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
            sel.innerHTML = ACCOUNTS.map(a => `<option value="${a.id}" ${String(a.id) === String(ACTIVE_ACCOUNT_ID) ? 'selected' : ''}>${esc(a.name)}</option>`).join("");
            if (!ACTIVE_ACCOUNT_ID || !ACCOUNTS.find(a => String(a.id) === String(ACTIVE_ACCOUNT_ID))) {
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
        display.className = "text-sm font-black text-brand uppercase fade-in";
        box.className = "p-4 bg-brand/5 border border-brand/20 rounded-2xl shadow-inner";
    } else {
        display.textContent = "Please Setup Account →";
        display.className = "text-sm font-black text-muted italic";
        box.className = "p-4 bg-white/5 border border-border rounded-2xl shadow-none";
    }
}
function showEmptyState(type) {
    const list = document.getElementById("list");
    const stats = document.getElementById("stats");
    stats.innerHTML = "";
    
    let html = "";
    if (type === "no_accounts") {
        html = `
        <div class="col-span-full py-32 text-center border-2 border-dashed border-border rounded-[2.5rem] bg-white/5 fade-in max-w-2xl mx-auto">
            <div class="w-20 h-20 bg-white/5 rounded-3xl shadow-xl flex items-center justify-center mx-auto mb-8 border border-border">
                <svg class="w-10 h-10 text-rose-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            </div>
            <h3 class="text-lg font-black text-main mb-2">No Social Profiles</h3>
            <p class="text-[11px] text-muted font-bold uppercase tracking-widest max-w-xs mx-auto leading-relaxed mb-10">Connect an Instagram account to start using the content engine.</p>
            <button onclick="toggleSettings()" class="btn-primary px-10 py-4 text-[11px] font-black uppercase tracking-widest transition-all">Setup First Workspace</button>
        </div>`;
    } else if (type === "no_posts") {
        html = `
        <div class="col-span-full py-32 text-center border-2 border-dashed border-border rounded-[2.5rem] bg-white/5 fade-in max-w-2xl mx-auto">
            <div class="w-16 h-16 bg-white/5 rounded-3xl shadow-xl flex items-center justify-center mx-auto mb-8 border border-border">
                <svg class="w-8 h-8 text-brand" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
            </div>
            <h3 class="text-sm font-black text-main mb-2 uppercase tracking-widest">No Intelligence Nodes Found</h3>
            <p class="text-[10px] text-muted font-bold uppercase tracking-widest max-w-xs mx-auto mb-8">Post intake required to generate neural streams.</p>
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
    if(!payload.name || !payload.ig_user_id || !payload.access_token) return alert("Fill all fields!");
    
    try {
        btn.disabled = true;
        msg.textContent = "⚙️ REGISTERING EXTENSION...";
        msg.className = "mt-4 text-[10px] font-black tracking-widest text-indigo-500 animate-pulse";
        
        const newAcc = await request("/ig-accounts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        
        console.log("Registered Account:", newAcc);
        msg.textContent = "✅ EXTENSION ACTIVE!";
        msg.className = "mt-4 text-[10px] font-black tracking-widest text-emerald-500";
        
        document.getElementById("new_acc_name").value = "";
        document.getElementById("new_acc_ig_id").value = "";
        document.getElementById("new_acc_token").value = "";
        
        ACTIVE_ACCOUNT_ID = newAcc.id;
        localStorage.setItem("active_ig_id", ACTIVE_ACCOUNT_ID);
        
        // Immediate UI refresh
        await loadAccounts();
        await refreshAll();
        
        setTimeout(() => { toggleSettings(); msg.textContent = ""; }, 1500);
    } catch(e) { 
        msg.textContent = "❌ ERROR"; 
        msg.className = "mt-4 text-[10px] font-black tracking-widest text-rose-600";
        alert("Registration Failed: " + e.message); 
    } finally { btn.disabled = false; }
}
async function deleteAccount(id) {
    if(!confirm("Are you SURE you want to delete this Instagram account? This will also un-link it from any scheduled posts or automations!")) return;
    try {
        await request(`/ig-accounts/${id}`, { method: "DELETE" });
        alert("Account deleted.");
        // If we deleted the active account, reset ACTIVE_ACCOUNT_ID
        if (ACTIVE_ACCOUNT_ID == id) {
            ACTIVE_ACCOUNT_ID = null;
        }
        await loadAccounts();
        await refreshAll();
    } catch(e) {
        alert("Deletion Failed: " + e.message);
    }
}
function renderSettingsAccounts() {
    const list = document.getElementById("settings_accounts_list");
    if(!list) return;
    if(ACCOUNTS.length === 0) {
        list.innerHTML = `<div class="text-xs text-muted font-bold italic text-center py-4 bg-white/5 rounded-xl border border-border">No accounts linked yet.</div>`;
        return;
    }
    list.innerHTML = ACCOUNTS.map(a => `
            <div class="flex justify-between items-center p-3 rounded-xl border border-border bg-white/5">
                <div class="flex items-center gap-3">
                    <img src="${a.profile_picture_url}" class="w-10 h-10 rounded-full border border-border" onerror="this.src='https://placehold.co/100x100?text=IG'"/>
                    <div>
                        <p class="text-xs font-black text-main underline cursor-pointer" onclick="window.open('https://instagram.com/${a.username}', '_blank')">@${esc(a.username)}</p>
                        <p class="text-[8px] font-black uppercase text-brand tracking-widest">${esc(a.full_name || 'Instagram User')}</p>
                    </div>
                </div>
                <button onclick="deleteAccount(${a.id})" class="p-2 text-muted hover:text-rose-500 transition-colors">
                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7M4 7h16" /></svg>
                </button>
            </div>
    `).join("");
}
async function loadStats() {
    const el = document.getElementById("stats");
    try {
        const j = await request(`/posts/stats?ig_account_id=${ACTIVE_ACCOUNT_ID || ''}`);
        
        // Update Dashboard (if exists)
        if (document.getElementById("dash_today_posts")) {
            const counts = j.counts || {};
            document.getElementById("dash_today_posts").textContent = (counts.published || 0) + (counts.scheduled || 0);
            document.getElementById("dash_scheduled").textContent = counts.scheduled || 0;
            document.getElementById("dash_published").textContent = counts.published || 0;
            document.getElementById("dash_automations").textContent = j.auto_count || 0;
        }

        // Update Feed Stats
        if (el) {
            el.innerHTML = Object.entries(j.counts || {}).map(([k,v]) => `
                <div class="stat-card p-3">
                    <div class="text-[9px] font-bold text-text-muted uppercase tracking-wider mb-1">${esc(k)}</div>
                    <div class="text-lg font-bold text-text-main">${v}</div>
                </div>`).join("");
        }
    } catch(e) { if(el) el.innerHTML = ""; }
}

async function loadPosts() {
    const list = document.getElementById("list");
    list.innerHTML = `<div class="col-span-full py-24 text-center"><div class="animate-spin h-8 w-8 border-4 border-brand border-t-transparent rounded-full mx-auto mb-4"></div><p class="text-xs font-black uppercase text-muted">Synchronizing History...</p></div>`;
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
        submitted: "bg-white/10 text-muted border-border", 
        drafted: "bg-brand/10 text-brand border-brand/20", 
        needs_review: "bg-rose-500/10 text-rose-500 border-rose-500/20", 
        scheduled: "bg-brand/10 text-brand border-brand/20", 
        published: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20", 
        failed: "bg-red-500/10 text-red-500 border-red-500/20" 
    };
    const c = colors[p.status] || "bg-white/10 text-muted border-border";
    
    return `
    <div class="bg-white/5 border border-border rounded-3xl overflow-hidden flex flex-col group hover:shadow-2xl hover:border-brand/40 transition-all duration-500 fade-in">
        <div class="relative aspect-square bg-white/5 overflow-hidden cursor-pointer" onclick="openPostEditor(${p.id})">
            <img src="${p.media_url}" class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110" loading="lazy" onerror="this.src='https://placehold.co/600x600?text=Media+Missing'"/>
            <div class="absolute top-4 left-4 right-4 flex justify-between items-start">
               <span class="px-3 py-1.5 rounded-xl border border-white/10 backdrop-blur-md text-[9px] font-black uppercase tracking-widest shadow-lg ${c}">${esc(p.status)}</span>
               <div class="p-2 rounded-xl bg-white/5 border border-border text-main shadow-xl opacity-0 group-hover:opacity-100 transition-all transform translate-y-2 group-hover:translate-y-0">
                  <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
               </div>
            </div>
            ${p.scheduled_time ? `<div class="absolute bottom-4 left-4 px-3 py-1 bg-brand text-white rounded-lg text-[8px] font-black uppercase tracking-tighter shadow-lg">Due: ${new Date(p.scheduled_time).toLocaleString()}</div>` : ''}
        </div>
        <div class="p-5 flex flex-col flex-1">
            <p class="text-[12px] text-main leading-relaxed font-medium mb-4 line-clamp-2">${esc(p.caption || '(No Caption Generated)')}</p>
            <div class="mt-auto flex items-center justify-between border-t border-border pt-4">
                <span class="text-[10px] font-bold text-muted uppercase italic">${esc(p.source_type)}</span>
                <button onclick="openPostEditor(${p.id})" class="text-[10px] font-black text-brand uppercase tracking-widest hover:underline">Manage Post</button>
            </div>
        </div>
    </div>`;
}
async function uploadPost() {
    if (!ACTIVE_ACCOUNT_ID) return alert("Select an account first!");
    const file = document.getElementById("image").files[0];
    if (!file) return alert("Pick an image asset first!");
    const btn = document.getElementById("intake_btn");
    const msg = document.getElementById("upload_msg");
    const fd = new FormData();
    fd.append("source_text", document.getElementById("source_text").value);
    fd.append("image", file);
    fd.append("ig_account_id", ACTIVE_ACCOUNT_ID);
    try {
        btn.disabled = true;
        msg.textContent = "📡 UPLOADING CONTENT...";
        msg.className = "text-center text-[10px] font-black text-brand animate-pulse";
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
    if(el) { el.textContent = "🧠 AI ANALYZING..."; el.className = "mt-4 text-[9px] text-center font-black text-brand animate-pulse"; }
    try { await request(`/posts/${id}/generate`, { method: "POST" }); await refreshAll(); } catch(e) { if(el) { el.textContent = "AI FAILED"; el.className = "mt-4 text-[9px] text-center font-black text-red-600"; } alert(e.message); }
}
async function approvePost(id) {
    const el = document.getElementById(`msg-${id}`);
    if(el) { el.textContent = "✔️ ADDING TO QUEUE..."; el.className = "mt-4 text-[9px] text-center font-black text-emerald-500 animate-pulse"; }
    try { await request(`/posts/${id}/approve`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({approve_anyway: true}) }); await refreshAll(); } catch(e) { if(el) { el.textContent = "FAIL"; el.className = "mt-4 text-[9px] text-center font-black text-red-600"; } alert(e.message); }
}

async function initializeAdmin() {
    try {
        ME = await request("/auth/me");
        const isAdmin = ME.is_superadmin;
        
        // Update User info
        const avatarTop = document.getElementById("user_avatar_top");
        if (avatarTop) avatarTop.textContent = (ME.name || "U")[0].toUpperCase();

        // Platform access
        const platBtn = document.getElementById("platform_btn");
        if (platBtn && isAdmin) {
            platBtn.classList.remove("hidden");
            platBtn.classList.add("flex");
        }

        // Onboarding checks
        const banner = document.getElementById("onboarding_banner");
        if (banner) banner.classList.toggle("hidden", !!ME.onboarding_complete);
        
        // Organizations
        const orgSel = document.getElementById("org_selector");
        if (orgSel) {
            if (ME.orgs.length === 0) {
                orgSel.innerHTML = `<option value="">No Workspaces</option>`;
                ACTIVE_ORG_ID = null;
            } else {
                orgSel.innerHTML = ME.orgs.map(o => `<option value="${o.id}" ${o.id == ACTIVE_ORG_ID ? 'selected' : ''}>${esc(o.name)}</option>`).join("");
                if (!ACTIVE_ORG_ID || !ME.orgs.find(o => o.id == ACTIVE_ORG_ID)) {
                    ACTIVE_ORG_ID = ME.orgs[0].id;
                }
                orgSel.value = ACTIVE_ORG_ID;
            }
            localStorage.setItem("active_org_id", ACTIVE_ORG_ID);
        }

        // Finalize
        refreshAll();

    } catch(e) { 
        console.error("Initialization failed", e);
        if (e.message.includes("401")) window.location.href = "/admin/login";
    }
}

function onOrgChange() {
    ACTIVE_ORG_ID = document.getElementById("org_selector").value;
    localStorage.setItem("active_org_id", ACTIVE_ORG_ID);
    refreshAll();
}

document.addEventListener("DOMContentLoaded", () => {
    const saved = localStorage.getItem('admin_theme') || 'startup';
    document.documentElement.setAttribute('data-theme', saved);
    setTimeout(() => {
        goToStep(1);
        initializeAdmin();
    }, 100);
});
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
    return HTML

ONBOARDING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Onboarding | Social SaaS</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-main min-h-screen flex py-12 px-6 justify-center text-main">
  <div class="max-w-2xl w-full bg-surface rounded-3xl shadow-xl p-8 lg:p-12 border border-border transition-all">
    <div class="mb-10 flex items-center gap-3">
        <div class="w-10 h-10 bg-brand rounded-xl flex items-center justify-center text-white font-black shadow-lg shadow-brand/20">S</div>
        <h1 class="text-3xl font-black italic tracking-tighter text-gradient">Social Media LLM</h1>
    </div>
    <div class="mb-10">
      <h2 class="text-2xl font-black text-main italic">Strategic Initialization</h2>
      <p class="text-sm text-muted mt-3 font-medium">Let's set up your first AI Content strategy. This will tailor how the system generates captions and media for your brand.</p>
    </div>
    
    <form id="onboardingForm" class="space-y-8">
      <!-- Business Info -->
      <div class="space-y-6">
        
      <div class="space-y-6 pt-4 border-t border-border">
        <h3 class="text-lg font-black text-main border-b border-border pb-2 italic">Business Context</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
                <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-2 ml-1">Workspace Identity</label>
                <input type="text" id="edit_org_name" required class="w-full bg-white/5 border border-border rounded-xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none transition-all text-main" placeholder="e.g. Apex Fitness">
            </div>
            <div>
                <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-2 ml-1">Niche Architecture</label>
                 <select id="edit_org_niche" class="w-full bg-white/5 border border-border rounded-xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none text-main cursor-pointer">
                    <option value="ecommerce">E-Commerce Brand</option>
                    <option value="real_estate">Real Estate</option>
                    <option value="fitness">Fitness Coaching</option>
                    <option value="restaurant">Restaurant & Food</option>
                    <option value="personal_creator">Personal Brand / Creator</option>
                    <option value="b2b_saas">B2B SaaS / Tech</option>
                    <option value="other">Other / Custom</option>
                 </select>
            </div>
        </div>
        
        <div>
            <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-2 ml-1">Strategic Objectives</label>
            <textarea id="edit_org_goals" required class="w-full bg-white/5 border border-border rounded-xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none text-main min-h-[100px]" placeholder="What is the goal of your page?"></textarea>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
                <label class="block text-xs font-bold text-muted uppercase tracking-widest mb-2">Tone & Style</label>
                <input type="text" id="tone_style" required class="w-full px-4 py-3 rounded-xl border border-border focus:ring-2 focus:ring-brand outline-none text-sm transition-all text-main" placeholder="e.g. Professional, Witty, High-Energy">
            </div>
            <div>
                <label class="block text-xs font-bold text-muted uppercase tracking-widest mb-2">Language</label>
                 <select id="language" class="w-full px-4 py-3 rounded-xl border border-border focus:ring-2 focus:ring-brand outline-none text-sm bg-white text-main cursor-pointer">
                    <option value="english">English</option>
                    <option value="spanish">Spanish</option>
                    <option value="french">French</option>
                    <option value="arabic">Arabic</option>
                </select>
            </div>
        </div>
      </div>
      
      <!-- AI Boundaries -->
      <div class="space-y-6 pt-4 border-t border-border">
        <h3 class="text-lg font-black text-main border-b border-border pb-2 italic">Neural Boundaries</h3>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
                <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-2 ml-1">Restricted Concepts</label>
                <input type="text" id="edit_org_restricted" class="w-full bg-white/5 border border-border rounded-xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none transition-all text-main" placeholder="e.g. politics, competitors">
            </div>
            <div>
                <label class="block text-[10px] font-black text-muted uppercase tracking-widest mb-2 ml-1">Preferred Lexicon</label>
                <input type="text" id="edit_org_lexicon" class="w-full bg-white/5 border border-border rounded-xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none transition-all text-main" placeholder="e.g. luxury, bespoke, exclusive">
            </div>
        </div>
      </div>

      <div id="errorMsg" class="hidden text-xs font-bold text-red-600 text-center bg-red-50 p-3 rounded-lg border border-red-100"></div>
      
      <button type="submit" class="w-full bg-brand text-white rounded-xl py-4 font-black hover:opacity-90 transition-all text-sm shadow-xl shadow-brand/20 active:scale-[0.98]">COMPLETE INITIALIZATION &rarr;</button>
    </form>
  </div>
  
  <script>
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
        btn.innerHTML = "Provisioning AI Profile...";
        
        const res = await fetch("/auth/complete-onboarding", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        
        if (res.ok) {
          window.location.href = "/admin";
        } else {
          const data = await res.json();
          errorMsg.textContent = data.detail || "Onboarding failed";
          errorMsg.classList.remove("hidden");
          btn.disabled = false;
          btn.innerHTML = "Initialize Workspace &rarr;";
        }
      } catch (err) {
        errorMsg.textContent = "Network error occurred";
        errorMsg.classList.remove("hidden");
        btn.disabled = false;
        btn.innerHTML = "Initialize Workspace &rarr;";
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
