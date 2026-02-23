from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User, Org, OrgMember
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
<body class="bg-slate-50 min-h-screen flex items-center justify-center p-6">
  <div class="max-w-md w-full bg-white rounded-3xl shadow-xl p-8 border border-slate-100">
    <div class="text-center mb-8">
      <h1 class="text-2xl font-black bg-gradient-to-r from-emerald-600 to-teal-600 bg-clip-text text-transparent">Join Social SaaS</h1>
      <p class="text-sm text-slate-500 mt-2 font-medium">Create your workspace</p>
    </div>
    <form id="registerForm" class="space-y-6">
      <div>
        <label class="block text-xs font-bold text-slate-700 uppercase tracking-widest mb-2">Full Name</label>
        <input type="text" id="name" required class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-emerald-500 outline-none text-sm transition-all" placeholder="Jane Doe">
      </div>
      <div>
        <label class="block text-xs font-bold text-slate-700 uppercase tracking-widest mb-2">Email</label>
        <input type="email" id="email" required class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-emerald-500 outline-none text-sm transition-all" placeholder="name@company.com">
      </div>
      <div>
        <label class="block text-xs font-bold text-slate-700 uppercase tracking-widest mb-2">Password</label>
        <input type="password" id="password" required class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-emerald-500 outline-none text-sm transition-all" placeholder="••••••••">
      </div>
      <div id="errorMsg" class="hidden text-xs font-bold text-red-600 text-center bg-red-50 p-3 rounded-lg border border-red-100"></div>
      <button type="submit" class="w-full bg-emerald-600 text-white rounded-xl py-3.5 font-black hover:bg-emerald-700 transition-all text-sm shadow-lg shadow-emerald-200 active:scale-[0.98]">
        Create Account
      </button>
      <div class="text-center mt-4">
        <a href="/admin/login" class="text-xs text-emerald-600 hover:text-emerald-800 font-bold hover:underline">Already have an account? Log in</a>
      </div>
      <div class="relative py-2">
        <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-slate-200"></div></div>
        <div class="relative flex justify-center text-xs"><span class="bg-white px-2 text-slate-500">Or</span></div>
      </div>
      <a href="/auth/google/start" class="flex w-full items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white py-3.5 text-sm font-bold text-slate-700 shadow-sm transition-all hover:bg-slate-50 hover:text-slate-900 active:scale-[0.98]">
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
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src='https://cdn.jsdelivr.net/npm/fullcalendar@6.1.10/index.global.min.js'></script>
  <style>
    body { font-family: 'Inter', sans-serif; }
    .glass { background: rgba(255, 255, 255, 0.7); backdrop-filter: blur(10px); }
    .fade-in { animation: fadeIn 0.3s ease-out; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(-5px); } to { opacity: 1; transform: translateY(0); } }
  </style>
</head>
<body class="bg-slate-50 text-slate-900 min-h-screen pb-12">
  <div id="localhost_warning" class="hidden bg-amber-500 text-white px-6 py-2 text-center text-xs font-black uppercase tracking-widest shadow-lg fade-in">
      ⚠️ ENVIRONMENT WARNING: LOCALHOST DETECTED. Instagram publishing will fail. Use ngrok for public tunnel.
  </div>
  <!-- Onboarding Banner -->
  <div id="onboarding_banner" class="hidden bg-indigo-600 text-white px-6 py-3 shadow-lg fade-in">
      <div class="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
          <div class="flex items-center gap-3">
              <div class="bg-indigo-500 p-2 rounded-lg">
                  <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
              </div>
              <div>
                  <div class="text-sm font-bold">Your AI Content Engine isn't tailored yet!</div>
                  <div class="text-[10px] opacity-80 font-medium">Complete the 2-minute onboarding to get better AI captions and tailored media.</div>
              </div>
          </div>
          <a href="/admin/onboarding" class="bg-white text-indigo-600 px-6 py-2 rounded-xl text-xs font-black shadow-md hover:bg-slate-100 transition-all uppercase tracking-widest">Start Setup &rarr;</a>
      </div>
  </div>
  <nav class="glass sticky top-0 z-50 border-b border-slate-200 bg-white/80 px-6 py-4 mb-8">
    <div class="max-w-7xl mx-auto flex justify-between items-center">
      <div class="flex items-center gap-6">
            <h1 class="text-xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
            Social SaaS <span class="text-slate-400 font-light">Admin v1.0.2</span>
          </h1>
          <div class="h-6 w-px bg-slate-200"></div>
          <div class="flex items-center gap-2">
              <label class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Account</label>
              <select id="account_selector" onchange="onAccountChange()" class="px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:ring-indigo-500 outline-none bg-slate-50 font-semibold min-w-[200px]">
                  <option value="">No Accounts Found</option>
              </select>
          </div>
      </div>
      <div class="flex items-center gap-4">
        <button id="platform_btn" onclick="togglePlatformPanel()" class="hidden items-center gap-2 bg-emerald-600 text-white px-4 py-2 rounded-xl shadow-md text-sm font-bold hover:bg-emerald-700 transition-all">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
          </svg>
          Platform Management
        </button>
        <div class="h-6 w-px bg-slate-200"></div>
        <div class="flex items-center gap-2">
            <label class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Workspace</label>
            <select id="org_selector" onchange="onOrgChange()" class="px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:ring-indigo-500 outline-none bg-slate-50 font-semibold min-w-[150px]">
                <option value="">Loading...</option>
            </select>
        </div>
        <div class="h-6 w-px bg-slate-200"></div>
        <div class="flex items-center gap-3 relative group">
          <div class="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-black text-xs cursor-pointer" id="user_avatar">U</div>
          <div class="absolute right-0 top-10 w-48 bg-white border border-slate-200 rounded-2xl shadow-xl p-2 hidden group-hover:block fade-in">
              <div class="px-3 py-2 border-b border-slate-100 mb-2">
                  <div class="text-xs font-black text-slate-800" id="user_dropdown_name">User</div>
                  <div class="text-[10px] text-slate-400" id="user_dropdown_email">email@domain.com</div>
              </div>
              <button onclick="logout()" class="w-full text-left px-3 py-2 text-xs font-bold text-red-600 hover:bg-red-50 rounded-xl transition-colors">
                  Sign Out
              </button>
          </div>
        </div>
        <div class="h-6 w-px bg-slate-200"></div>
        <button onclick="toggleSettings()" class="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-xl border border-indigo-700 shadow-md text-sm font-bold hover:bg-indigo-700 transition-all">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
          </svg>
          Account Settings
        </button>
        <button id="run_scheduler_btn" onclick="runGlobalScheduler()" class="flex items-center gap-2 bg-emerald-600 text-white px-4 py-2 rounded-xl border border-emerald-700 shadow-md text-sm font-bold hover:bg-emerald-700 transition-all">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          Run Scheduler
        </button>
      </div>
    </div>
  </nav>
  <main class="max-w-7xl mx-auto px-6 grid grid-cols-1 lg:grid-cols-12 gap-8">
    
    <!-- Settings Drawer -->
    <div id="settings_panel" class="hidden fixed inset-0 bg-black/40 z-[100] backdrop-blur-sm flex justify-end" onclick="if(event.target === this) toggleSettings()">
        <div class="w-full max-w-md bg-white h-full shadow-2xl p-8 flex flex-col overflow-y-auto" onclick="event.stopPropagation()">
            <div class="flex justify-between items-center mb-8">
                <div>
                    <h2 class="text-2xl font-black text-slate-900">Workspace Hub</h2>
                    <p class="text-sm text-slate-500 mt-1">Configure your social environment</p>
                </div>
                <button onclick="toggleSettings()" class="p-2 rounded-lg hover:bg-slate-100 transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
            <div class="space-y-10">
                <!-- STEP 1: AUTH (Superseded by Cookie Login) -->
                <section class="p-5 bg-emerald-50/50 rounded-2xl border border-emerald-100 hidden">
                    <div class="flex items-center gap-3 mb-4">
                        <span class="w-6 h-6 rounded-full bg-emerald-600 text-white flex items-center justify-center text-xs font-bold shadow-sm">✓</span>
                        <h3 class="text-sm font-black text-emerald-900 uppercase tracking-widest">Authenticated Securely</h3>
                    </div>
                    <p class="text-[11px] text-emerald-600/70 mb-4 leading-relaxed font-semibold italic">You are logged in via secure session cookie. API Key entry is no longer required.</p>
                </section>
                <div class="h-px bg-slate-100"></div>
                
                <section>
                    <div class="flex items-center gap-3 mb-6 text-slate-900">
                        <span class="w-6 h-6 rounded-full bg-slate-900 text-white flex items-center justify-center text-xs font-bold">1</span>
                        <h3 class="text-sm font-black uppercase tracking-widest">Active Accounts</h3>
                    </div>
                    <div id="settings_accounts_list" class="space-y-3">
                        <!-- Populated by JS -->
                    </div>
                </section>
                
                <div class="h-px bg-slate-100"></div>
                
                <!-- STEP 2: ADD IG -->
                <section>
                    <div class="flex items-center gap-3 mb-6 text-slate-900">
                        <span class="w-6 h-6 rounded-full bg-slate-900 text-white flex items-center justify-center text-xs font-bold">2</span>
                        <h3 class="text-sm font-black uppercase tracking-widest">Register Instagram Slot</h3>
                    </div>
                    <div class="space-y-5">
                        <div>
                            <label class="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">Display Name</label>
                            <input id="new_acc_name" class="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-sm focus:ring-indigo-500 outline-none" placeholder="e.g. Luxury Real Estate"/>
                        </div>
                        <div class="grid grid-cols-1 gap-5">
                            <div>
                                <label class="flex items-center gap-2 text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">
                                    IG User ID
                                    <button onclick="toggleGuideModal()" class="text-indigo-400 hover:text-indigo-600 transition-colors" title="How to find your ID">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                        </svg>
                                    </button>
                                </label>
                                <input id="new_acc_ig_id" class="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-sm focus:ring-indigo-500 outline-none font-mono" placeholder="Numerical ID (e.g. 1784...)"/>
                            </div>
                            <div>
                                <label class="flex items-center gap-2 text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">
                                    Access Token
                                    <button onclick="toggleGuideModal()" class="text-indigo-400 hover:text-indigo-600 transition-colors" title="How to generate your Token">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                        </svg>
                                    </button>
                                </label>
                                <textarea id="new_acc_token" class="w-full px-4 py-2.5 rounded-xl border border-slate-200 text-xs focus:ring-indigo-500 outline-none font-mono min-h-[100px]" placeholder="Paste long-lived token here..."></textarea>
                            </div>
                        </div>
                        <button id="add_acc_btn" onclick="addAccount()" class="w-full border-2 border-slate-900 text-slate-900 rounded-xl py-4 text-sm font-black hover:bg-slate-900 hover:text-white transition-all active:scale-95">Save Account Extension</button>
                    </div>
                    <div id="add_acc_msg" class="mt-4 text-xs font-bold text-center h-4"></div>
                </section>
                
                <div id="auth_error_box" class="hidden p-4 bg-red-50 text-red-600 rounded-xl text-[11px] font-bold border border-red-100"></div>
            </div>
        </div>
        </div>
    </div>

    <!-- Instagram Setup Guide Modal -->
    <div id="guide_modal" class="hidden fixed inset-0 bg-black/60 z-[200] backdrop-blur-sm flex items-center justify-center p-4">
        <div class="bg-white rounded-3xl shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh]">
            <div class="px-8 py-6 border-b border-slate-100 flex justify-between items-center bg-indigo-50">
                <div class="flex items-center gap-3">
                    <div class="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    </div>
                    <div>
                        <h3 class="text-xl font-black text-slate-800">Connection Guide</h3>
                        <p class="text-[11px] font-bold tracking-widest text-indigo-500 uppercase">Instagram Setup Instructions</p>
                    </div>
                </div>
                <button onclick="toggleGuideModal()" class="w-8 h-8 rounded-full bg-white text-slate-400 hover:text-slate-600 hover:shadow-md flex items-center justify-center transition-all">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
            </div>
            
            <div class="p-8 overflow-y-auto space-y-8 bg-slate-50/50">
                
                <div class="flex gap-4">
                    <div class="flex-shrink-0 w-8 h-8 rounded-full bg-slate-200 text-slate-600 font-black flex items-center justify-center text-sm shadow-inner">1</div>
                    <div>
                        <h4 class="font-bold text-slate-800 text-base mb-1">Create a Meta Developer App</h4>
                        <p class="text-sm text-slate-600 leading-relaxed mb-3">Go to <a href="https://developers.facebook.com/" target="_blank" class="text-indigo-600 font-semibold hover:underline">developers.facebook.com</a>. Log in with your Facebook account and create a new App. Select "Other" then "Business".</p>
                    </div>
                </div>

                <div class="flex gap-4">
                    <div class="flex-shrink-0 w-8 h-8 rounded-full bg-slate-200 text-slate-600 font-black flex items-center justify-center text-sm shadow-inner">2</div>
                    <div>
                        <h4 class="font-bold text-slate-800 text-base mb-1">Set up Instagram Graph API</h4>
                        <p class="text-sm text-slate-600 leading-relaxed mb-3">In the App Dashboard, scroll down to "Add products to your app" and set up the <b>Instagram Graph API</b> (not Basic Display). You will need a functioning Facebook Page linked to an Instagram Professional Account.</p>
                    </div>
                </div>

                <div class="flex gap-4">
                    <div class="flex-shrink-0 w-8 h-8 rounded-full bg-slate-200 text-slate-600 font-black flex items-center justify-center text-sm shadow-inner">3</div>
                    <div>
                        <h4 class="font-bold text-slate-800 text-base mb-1">Generate Access Token</h4>
                        <p class="text-sm text-slate-600 leading-relaxed mb-3">Navigate to <b>Tools > Graph API Explorer</b> in the top navigation bar. In the right panel, generate a User Token with these specific permissions:</p>
                        <div class="bg-indigo-50 border border-indigo-100 p-3 rounded-xl text-xs font-mono text-indigo-800 leading-loose">
                            instagram_basic, instagram_content_publish, pages_show_list, pages_read_engagement
                        </div>
                        <p class="text-sm text-slate-600 leading-relaxed mt-3">Click Generate and approve the Facebook popups to link your specific page.</p>
                    </div>
                </div>

                <div class="flex gap-4">
                    <div class="flex-shrink-0 w-8 h-8 rounded-full bg-slate-200 text-slate-600 font-black flex items-center justify-center text-sm shadow-inner">4</div>
                    <div>
                        <h4 class="font-bold text-slate-800 text-base mb-1">Extend Access Token</h4>
                        <p class="text-sm text-slate-600 leading-relaxed mb-3">The first token expires in an hour. Tap the small `(i)` info icon next to the Access Token box in the Explorer. Click <b>"Open in Access Token Tool"</b>, then scroll down and click <b>"Extend Access Token"</b> to generate a Long-Lived token (valid for 60 days).</p>
                        <p class="text-sm font-bold text-slate-800">Copy this Long-Lived Token and paste it into the dashboard.</p>
                    </div>
                </div>

                <div class="flex gap-4">
                    <div class="flex-shrink-0 w-8 h-8 rounded-full bg-slate-200 text-slate-600 font-black flex items-center justify-center text-sm shadow-inner">5</div>
                    <div>
                        <h4 class="font-bold text-slate-800 text-base mb-1">Find your Instagram User ID</h4>
                        <p class="text-sm text-slate-600 leading-relaxed mb-3">Still in the Graph API Explorer, paste the Long-Lived Token you just generated into the empty Access Token box. In the query bar at the top, type exactly:</p>
                        <div class="bg-slate-900 border border-slate-700 p-3 rounded-xl text-xs font-mono text-green-400 shadow-inner">
                            me/accounts?fields=instagram_business_account
                        </div>
                        <p class="text-sm text-slate-600 leading-relaxed mt-3">Hit Submit. Look in the JSON response for the <code>instagram_business_account.id</code> string (a long number like <code class="bg-slate-200 px-1 rounded">178414...</code>). Paste this numerical ID into the dashboard!</p>
                    </div>
                </div>
            </div>
            
            <div class="p-6 bg-white border-t border-slate-100 flex justify-end">
                <button onclick="toggleGuideModal()" class="px-6 py-2.5 bg-indigo-600 text-white text-sm font-black rounded-xl hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-200">
                    I Understand
                </button>
            </div>
        </div>
    </div>
    <!-- New Automation Modal -->
    <div id="auto_modal" class="hidden fixed inset-0 bg-black/40 z-[110] backdrop-blur-sm flex items-center justify-center p-4">
        <div class="bg-white rounded-3xl shadow-2xl w-full max-w-xl overflow-hidden flex flex-col max-h-[90vh]">
            <div class="px-8 py-6 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                <h3 class="text-xl font-black text-slate-800">New Topic Automation</h3>
                <button onclick="hideCreateAuto()" class="text-slate-400 hover:text-slate-600">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
            </div>
            <div class="p-8 overflow-y-auto space-y-6">
                <input type="hidden" id="edit_auto_id" value=""/>
                <div>
                    <label class="block text-xs font-black text-slate-400 uppercase tracking-widest mb-2">Internal Name</label>
                    <input id="auto_name" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. Daily Hadith Series"/>
                </div>
                <div>
                    <label class="block text-xs font-black text-slate-400 uppercase tracking-widest mb-2">Topic / Prompt</label>
                    <textarea id="auto_topic" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none focus:ring-2 focus:ring-indigo-500 min-h-[100px]" placeholder="Specific topic for the AI (e.g. The importance of gratitude in Islam)"></textarea>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Content Profile Strategy</label>
                        <select id="auto_profile_id" class="w-full px-4 py-3 rounded-xl border border-indigo-200 outline-none bg-indigo-50 text-indigo-900 font-bold shadow-sm">
                            <option value="">-- Generic Setup (No Profile) --</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 flex justify-between">
                            <span>Creative Intensity</span>
                            <span id="creativity_val" class="text-indigo-600 font-black">3 / 5</span>
                        </label>
                        <div class="pt-3">
                            <input type="range" id="auto_creativity" min="1" max="5" value="3" class="w-full accent-indigo-600" oninput="document.getElementById('creativity_val').textContent = this.value + ' / 5'">
                            <div class="flex justify-between text-[8px] font-bold text-slate-300 px-1 uppercase tracking-widest mt-2">
                                <span>1 (Strict)</span><span>3</span><span>5 (Wild)</span>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-black text-slate-400 uppercase tracking-widest mb-2">Style Preset</label>
                        <select id="auto_style" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none bg-slate-50">
                            <option value="islamic_reminder">Islamic Reminder</option>
                            <option value="educational">Educational</option>
                            <option value="motivational">Motivational</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-black text-slate-400 uppercase tracking-widest mb-2">Tone</label>
                        <select id="auto_tone" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none bg-slate-50">
                            <option value="short">Short & Punchy</option>
                            <option value="medium" selected>Medium / Balanced</option>
                            <option value="long">Long / Educational</option>
                        </select>
                    </div>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-black text-slate-400 uppercase tracking-widest mb-2">Language</label>
                        <select id="auto_lang" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none bg-slate-50">
                            <option value="english">Pure English</option>
                            <option value="arabic_mix" selected>English + Arabic Mix</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-black text-slate-400 uppercase tracking-widest mb-2">Post Time (Local)</label>
                        <input type="time" id="auto_time" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none" value="09:00"/>
                    </div>
                </div>
                <div class="p-4 bg-indigo-50 rounded-2xl border border-indigo-100 space-y-4">
                    <div class="flex items-center gap-3">
                        <input type="checkbox" id="auto_use_library" class="w-5 h-5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" checked/>
                        <label for="auto_use_library" class="text-sm font-black text-indigo-900">Use Content Library</label>
                    </div>
                    <div class="grid grid-cols-2 gap-4 pl-8">
                        <div>
                            <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Image Mode</label>
                            <select id="auto_image_mode" class="w-full px-3 py-2 rounded-lg border border-slate-200 outline-none text-xs font-bold bg-white">
                                <option value="reuse_last_upload">Reuse Last Upload</option>
                                <option value="quote_card">Generate Quote Card</option>
                                <option value="ai_generated">AI Generated Image (Nature/Calligraphy)</option>
                                <option value="library_fixed">Fixed Library Asset</option>
                                <option value="library_tag">Library Asset by Tag</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Lookback (Days)</label>
                            <input type="number" id="auto_lookback" class="w-full px-3 py-2 rounded-lg border border-slate-200 outline-none text-xs font-bold" value="30"/>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-4 pl-8">
                        <div>
                            <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Tag Query (CSV)</label>
                            <input type="text" id="auto_media_tag_query" class="w-full px-3 py-2 rounded-lg border border-slate-200 outline-none text-xs font-bold" placeholder="e.g. nature, sunnah"/>
                        </div>
                        <div>
                            <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Fixed Asset ID</label>
                            <input type="number" id="auto_media_asset_id" class="w-full px-3 py-2 rounded-lg border border-slate-200 outline-none text-xs font-bold" placeholder="Optional ID"/>
                        </div>
                    </div>
                    <div class="flex items-center gap-3 pl-8">
                        <input type="checkbox" id="auto_arabic" class="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"/>
                        <label for="auto_arabic" class="text-xs font-bold text-slate-600">Include Arabic Text</label>
                    </div>
                    <div class="h-px bg-indigo-100 mx-[-1rem]"></div>
                    <div class="flex items-center gap-3">
                        <input type="checkbox" id="auto_enabled" class="w-5 h-5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" checked/>
                        <label for="auto_enabled" class="text-sm font-black text-indigo-900">Enable Automation Immediately</label>
                    </div>
                </div>
                <!-- Hadith Enrichment Section -->
                <div class="p-4 bg-purple-50 rounded-2xl border border-purple-100 space-y-4">
                    <div class="flex items-center gap-3">
                        <input type="checkbox" id="auto_enrich_hadith" class="w-5 h-5 rounded border-slate-300 text-purple-600 focus:ring-purple-500"/>
                        <label for="auto_enrich_hadith" class="text-sm font-black text-purple-900">Enrich with Hadith (Sunnah.com)</label>
                    </div>
                    <div class="grid grid-cols-2 gap-4 pl-8">
                        <div>
                            <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Hadith Topic (Optional)</label>
                            <input type="text" id="auto_hadith_topic" class="w-full px-3 py-2 rounded-lg border border-slate-200 outline-none text-xs font-bold bg-white" placeholder="Leave empty to use main topic"/>
                        </div>
                        <div>
                            <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Max Length</label>
                            <input type="number" id="auto_hadith_maxlen" class="w-full px-3 py-2 rounded-lg border border-slate-200 outline-none text-xs font-bold" value="450"/>
                        </div>
                    </div>
                </div>
            </div>
            <div class="p-8 border-t border-slate-100 bg-slate-50 flex gap-4">
                <button onclick="hideCreateAuto()" class="flex-1 px-6 py-4 rounded-xl border border-slate-200 bg-white font-bold text-slate-600 hover:bg-slate-100">Cancel</button>
                <button onclick="saveAutomation()" class="flex-1 px-6 py-4 rounded-xl bg-indigo-600 text-white font-black hover:bg-indigo-700 shadow-xl shadow-indigo-100">Save Intelligence</button>
            </div>
        </div>
    </div>
    <!-- Post Editor Modal -->
    <div id="post_modal" class="hidden fixed inset-0 bg-black/40 z-[120] backdrop-blur-sm flex items-center justify-center p-4">
        <div class="bg-white rounded-3xl shadow-2xl w-full max-w-4xl overflow-hidden flex flex-col max-h-[90vh]">
            <div class="px-8 py-6 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                <div class="flex items-center gap-4">
                    <h3 class="text-xl font-black text-slate-800">Post Editor</h3>
                    <span id="post_edit_status" class="px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest bg-slate-200 text-slate-600">Draft</span>
                </div>
                <button onclick="hidePostEditor()" class="text-slate-400 hover:text-slate-600">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
            </div>
            <div class="flex-1 overflow-hidden flex flex-col lg:flex-row">
                <!-- Media Preview -->
                <div class="lg:w-1/2 bg-slate-900 flex items-center justify-center p-4 group relative">
                    <img id="post_edit_img" src="" class="max-w-full max-h-full object-contain shadow-2xl rounded-lg"/>
                    <div class="absolute bottom-6 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button onclick="regeneratePostImage()" class="bg-indigo-600/90 text-white px-4 py-2 rounded-xl text-xs font-bold backdrop-blur-sm hover:bg-indigo-600">Regenerate AI Image</button>
                        <label class="bg-white/90 text-slate-900 px-4 py-2 rounded-xl text-xs font-bold backdrop-blur-sm hover:bg-white cursor-pointer">
                            Replace File
                            <input type="file" id="post_media_replace" class="hidden" onchange="attachMediaToPost(this)"/>
                        </label>
                    </div>
                </div>
                <!-- Content Editor -->
                <div class="lg:w-1/2 p-8 overflow-y-auto space-y-6 bg-white">
                    <input type="hidden" id="post_edit_id" value=""/>
                    <div>
                        <label class="block text-xs font-black text-slate-400 uppercase tracking-widest mb-2">Caption Content</label>
                        <textarea id="post_edit_caption" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none focus:ring-2 focus:ring-indigo-500 min-h-[180px] text-sm leading-relaxed" placeholder="Write your caption here..."></textarea>
                        <div class="flex justify-end mt-2">
                           <button onclick="regeneratePostCaption()" class="text-[10px] font-black text-indigo-600 uppercase tracking-wider hover:underline">✨ Regenerate with AI</button>
                        </div>
                    </div>
                    <div>
                        <label class="block text-xs font-black text-slate-400 uppercase tracking-widest mb-2">Hashtags</label>
                        <textarea id="post_edit_hashtags" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none focus:ring-2 focus:ring-indigo-500 text-sm font-mono" placeholder="#faith #islam #daily"></textarea>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="block text-xs font-black text-slate-400 uppercase tracking-widest mb-2">Alt Text</label>
                            <input id="post_edit_alt" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none text-sm" placeholder="Describe image for accessibility"/>
                        </div>
                        <div>
                            <label class="block text-xs font-black text-slate-400 uppercase tracking-widest mb-2">Scheduled Time (UTC)</label>
                            <input type="datetime-local" id="post_edit_time" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none text-sm"/>
                        </div>
                    </div>
                    <div id="post_edit_flags" class="flex flex-wrap gap-2"></div>
                </div>
            </div>
            <div class="p-8 border-t border-slate-100 bg-slate-50 flex gap-4 justify-between items-center">
                <div class="flex gap-2">
                    <button onclick="deletePostUI()" class="px-6 py-4 rounded-xl border border-red-200 bg-white font-bold text-red-500 hover:bg-red-50">Delete</button>
                </div>
                <div class="flex gap-4">
                    <button onclick="hidePostEditor()" class="px-6 py-4 rounded-xl border border-slate-200 bg-white font-bold text-slate-600 hover:bg-slate-100">Cancel</button>
                    <button id="post_publish_now_btn" onclick="publishPostNow()" class="hidden px-6 py-4 rounded-xl border border-slate-900 bg-slate-900 text-white font-black hover:bg-slate-800">Publish Now</button>
                    <button onclick="savePost()" class="px-8 py-4 rounded-xl bg-indigo-600 text-white font-black hover:bg-indigo-700 shadow-xl shadow-indigo-100">Save Changes</button>
                </div>
            </div>
        </div>
    </div>
    <!-- 1) Upload Section -->
    <div class="lg:col-span-4 lg:sticky lg:top-28 h-fit space-y-6">
      <section class="bg-white rounded-3xl border border-slate-200 p-8 shadow-sm">
        <h2 class="text-xl font-black mb-6 flex items-center gap-2">
          <span class="w-8 h-8 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center text-sm font-bold">3</span>
          Content Intake
        </h2>
        <div class="space-y-6">
          <div id="selected_acc_box" class="p-4 bg-slate-50 border border-slate-200 rounded-2xl">
            <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Publishing Target</label>
            <div id="active_account_display" class="text-sm font-black text-slate-500 italic">Please Setup Account →</div>
          </div>
          <div>
              <label class="block text-sm font-bold text-slate-600 mb-2">Source Instructions</label>
              <textarea id="source_text" class="w-full px-4 py-4 rounded-2xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none text-sm min-h-[160px] resize-none" placeholder="What should the AI write about? (Topic, tags, style...)"></textarea>
          </div>
          <div>
              <label class="block text-sm font-bold text-slate-600 mb-2">Personal Image Asset</label>
              <div class="relative border-2 border-dashed border-slate-200 rounded-2xl p-8 hover:border-indigo-400 transition-colors group cursor-pointer bg-slate-50/50">
                  <input id="image" type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer" onchange="updateFileName(this)"/>
                  <div class="text-center">
                      <svg xmlns="http://www.w3.org/2000/svg" class="mx-auto h-8 w-8 text-slate-400 mb-3 group-hover:text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                      <div id="file_name_display" class="text-xs font-bold text-slate-500">Upload your own file here</div>
                  </div>
              </div>
              <p class="mt-2 text-[10px] text-slate-400 font-medium">✨ Upload your posters, graphics, or photos (PNG, JPG, WEBP).</p>
          </div>
          <div class="grid grid-cols-1 gap-3 pt-4">
              <button id="intake_btn" onclick="uploadPost()" class="bg-indigo-600 text-white rounded-2xl py-5 font-black hover:bg-indigo-700 transition-all shadow-xl shadow-indigo-100 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed uppercase tracking-widest text-sm">Create Post Entry</button>
              <button onclick="resetUpload()" class="bg-white text-slate-400 rounded-2xl py-3 font-bold hover:bg-slate-50 transition-all text-xs border border-slate-200">Reset Form</button>
          </div>
          <div id="upload_msg" class="text-center text-xs font-bold uppercase h-4"></div>
        </div>
      </section>
    </div>
    <!-- 2) Feed Section -->
    <div class="lg:col-span-8 flex flex-col gap-6">
      <section class="bg-white rounded-3xl border border-slate-200 p-8 shadow-sm min-h-[700px]">
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6 mb-8 pb-6 border-b border-slate-100">
            <div class="flex items-center gap-6">
                <button onclick="switchTab('feed')" id="tab_feed" class="text-2xl font-black flex items-center gap-3 border-b-4 border-slate-900 pb-2">
                    Feed
                </button>
                <button onclick="switchTab('calendar')" id="tab_calendar" class="text-2xl font-black flex items-center gap-3 text-slate-300 hover:text-slate-600 transition-colors pb-2">
                    Calendar
                </button>
                <button onclick="switchTab('automations')" id="tab_automations" class="text-2xl font-black flex items-center gap-3 text-slate-300 hover:text-slate-600 transition-colors pb-2">
                    Automations
                </button>
                <button onclick="switchTab('profiles')" id="tab_profiles" class="text-2xl font-black flex items-center gap-3 text-slate-300 hover:text-slate-600 transition-colors pb-2">
                    Profiles
                </button>
                <button onclick="switchTab('library')" id="tab_library" class="text-2xl font-black flex items-center gap-3 text-slate-300 hover:text-slate-600 transition-colors pb-2">
                    Library
                </button>
                <button onclick="switchTab('media')" id="tab_media" class="text-2xl font-black flex items-center gap-3 text-slate-300 hover:text-slate-600 transition-colors pb-2">
                    Media
                </button>
            </div>
            <div id="feed_controls" class="flex items-center gap-2">
                <select id="status_filter" onchange="refreshAll()" class="px-4 py-2.5 rounded-xl border border-slate-200 text-xs font-bold focus:ring-indigo-500 outline-none bg-slate-50 cursor-pointer">
                    <option value="">All Stages</option>
                    <option value="submitted">1. Submitted</option>
                    <option value="drafted">2. Drafted</option>
                    <option value="needs_review">Review Required</option>
                    <option value="scheduled">3. Scheduled</option>
                    <option value="published">4. Published</option>
                    <option value="failed">Error Trace</option>
                </select>
            </div>
            <div id="calendar_controls" class="hidden flex items-center gap-2">
                <button onclick="refreshAll()" class="p-2.5 rounded-xl border border-slate-200 hover:bg-slate-50 transition-all">
                    <svg class="h-5 w-5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                </button>
            </div>
            <div id="automations_controls" class="hidden flex items-center gap-2">
                <button onclick="showCreateAuto()" class="bg-indigo-600 text-white px-6 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest shadow-lg shadow-indigo-100 hover:bg-indigo-700 transition-all">New Automation</button>
            </div>
            <div id="profiles_controls" class="hidden flex items-center gap-2">
                <button onclick="showCreateProfile()" class="bg-indigo-600 text-white px-6 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest shadow-lg shadow-indigo-100 hover:bg-indigo-700 transition-all">New Profile</button>
            </div>
            <div id="library_controls" class="hidden flex items-center gap-2">
                <input type="text" id="library_search" oninput="loadLibrary()" placeholder="Search Library..." class="px-4 py-2.5 rounded-xl border border-slate-200 text-xs font-bold focus:ring-indigo-500 outline-none bg-slate-50"/>
                <button onclick="seedDemoContent()" class="bg-indigo-100 text-indigo-700 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-indigo-200 transition-all">Seed Demo</button>
                </label>
            </div>
            <div id="media_controls" class="hidden flex items-center gap-2">
                <label class="bg-indigo-600 text-white px-6 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest cursor-pointer shadow-lg shadow-indigo-100 hover:bg-indigo-700 transition-all">
                    Upload Asset
                    <input type="file" id="media_upload_input" class="hidden" onchange="uploadMedia(this)"/>
                </label>
            </div>
        </div>
        <div id="feed_view">
            <div id="stats" class="grid grid-cols-2 md:grid-cols-6 gap-3 mb-10"></div>
            <div id="error" class="hidden mb-6 p-5 rounded-2xl bg-red-50 text-red-600 text-[11px] font-bold border border-red-100 animate-pulse"></div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-8" id="list"></div>
        </div>
        <div id="automations_view" class="hidden space-y-8">
            <div id="auto_list" class="grid grid-cols-1 gap-6"></div>
        </div>
        <div id="profiles_view" class="hidden space-y-8">
            <div id="profile_list" class="grid grid-cols-1 md:grid-cols-2 gap-6"></div>
        </div>
        <div id="calendar_view" class="hidden">
            <div id="calendar_el" class="bg-white p-4 rounded-2xl min-h-[600px]"></div>
        </div>
        <div id="library_view" class="hidden space-y-8">
            <div id="library_list" class="grid grid-cols-1 md:grid-cols-2 gap-6"></div>
        </div>
        <div id="media_view" class="hidden space-y-8">
            <div id="media_list" class="grid grid-cols-2 md:grid-cols-4 gap-4"></div>
        </div>
      </section>
    </div>

    <!-- Platform Drawer -->
    <div id="platform_panel" class="hidden fixed inset-0 bg-black/40 z-[100] backdrop-blur-sm flex justify-end" onclick="if(event.target === this) togglePlatformPanel()">
        <div class="w-full max-w-4xl bg-white h-full shadow-2xl p-8 flex flex-col overflow-y-auto" onclick="event.stopPropagation()">
            <div class="flex justify-between items-center mb-8">
                <div>
                    <h2 class="text-2xl font-black text-slate-900">Platform Users</h2>
                    <p class="text-sm text-slate-500 mt-1">Manage global access and workspaces</p>
                </div>
                <button onclick="togglePlatformPanel()" class="p-2 rounded-lg hover:bg-slate-100 transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
            
            <div class="overflow-x-auto rounded-xl border border-slate-200">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="bg-slate-50 border-b border-slate-200">
                            <th class="py-3 px-4 flex-1 text-xs font-black uppercase tracking-widest text-slate-500">User</th>
                            <th class="py-3 px-4 font-black uppercase tracking-widest text-xs text-slate-500">Contact</th>
                            <th class="py-3 px-4 font-black uppercase tracking-widest text-xs text-slate-500">Workspaces</th>
                            <th class="py-3 px-4 font-black uppercase tracking-widest text-xs text-slate-500 text-right">Actions</th>
                        </tr>
                    </thead>
                    <tbody id="platform_user_table" class="divide-y divide-slate-100 text-sm font-medium text-slate-700">
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- Content Profile Modal -->
    <div id="profile_modal" class="hidden fixed inset-0 bg-black/40 z-[110] backdrop-blur-sm flex items-center justify-center p-4">
        <div class="bg-white rounded-3xl shadow-2xl w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh]">
            <div class="px-8 py-6 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                <h3 class="text-xl font-black text-slate-800">Content Profile</h3>
                <button onclick="hideCreateProfile()" class="text-slate-400 hover:text-slate-600">
                    <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
            </div>
            <div class="p-8 overflow-y-auto space-y-6">
                <input type="hidden" id="edit_profile_id" value=""/>
                
                <div class="bg-indigo-50 p-4 rounded-xl border border-indigo-100 mb-6">
                    <label class="block text-[10px] font-black text-indigo-900 uppercase tracking-widest mb-3">Load Starter Preset Quick-Fill</label>
                    <div class="flex flex-wrap gap-2">
                        <button onclick="seedProfile('islamic_education')" class="px-3 py-1.5 bg-white border border-indigo-200 text-indigo-700 text-[10px] font-bold rounded-lg hover:bg-indigo-600 hover:text-white transition-colors">Islamic Education</button>
                        <button onclick="seedProfile('fitness_coach')" class="px-3 py-1.5 bg-white border border-indigo-200 text-indigo-700 text-[10px] font-bold rounded-lg hover:bg-indigo-600 hover:text-white transition-colors">Fitness</button>
                        <button onclick="seedProfile('real_estate')" class="px-3 py-1.5 bg-white border border-indigo-200 text-indigo-700 text-[10px] font-bold rounded-lg hover:bg-indigo-600 hover:text-white transition-colors">Real Estate Market</button>
                        <button onclick="seedProfile('small_business')" class="px-3 py-1.5 bg-white border border-indigo-200 text-indigo-700 text-[10px] font-bold rounded-lg hover:bg-indigo-600 hover:text-white transition-colors">E-Commerce</button>
                        <button onclick="seedProfile('personal_branding')" class="px-3 py-1.5 bg-white border border-indigo-200 text-indigo-700 text-[10px] font-bold rounded-lg hover:bg-indigo-600 hover:text-white transition-colors">Personal Creator</button>
                    </div>
                </div>

                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-black text-slate-400 uppercase tracking-widest mb-2">Profile Name</label>
                        <input id="prof_name" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. My Brand Strategy"/>
                    </div>
                    <div>
                        <label class="block text-xs font-black text-slate-400 uppercase tracking-widest mb-2">Niche Category</label>
                        <input id="prof_niche" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. real_estate, fitness"/>
                    </div>
                </div>
                
                <div>
                    <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Focus Description (What to post)</label>
                    <textarea id="prof_focus" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none focus:ring-2 focus:ring-indigo-500 min-h-[80px]" placeholder="Specific focus..."></textarea>
                </div>
                
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Content Goals</label>
                        <textarea id="prof_goals" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none focus:ring-2 focus:ring-indigo-500 min-h-[80px]" placeholder="Educate, Sell..."></textarea>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Tone & Style</label>
                        <textarea id="prof_tone" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none focus:ring-2 focus:ring-indigo-500 min-h-[80px]" placeholder="Professional..."></textarea>
                    </div>
                </div>
                
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Allowed Topics (CSV)</label>
                        <input id="prof_allowed" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none text-xs" placeholder="topic1, topic2"/>
                    </div>
                    <div>
                        <label class="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Banned Topics (CSV)</label>
                        <input id="prof_banned" class="w-full px-4 py-3 rounded-xl border border-slate-200 outline-none text-xs" placeholder="politics, drama"/>
                    </div>
                </div>
            </div>
            <div class="p-6 border-t border-slate-100 bg-slate-50 flex justify-end gap-3">
                <button onclick="hideCreateProfile()" class="px-6 py-3 rounded-xl font-bold text-slate-500 hover:bg-slate-200 transition-colors">Cancel</button>
                <button onclick="saveProfileWrapper()" class="px-8 py-3 bg-indigo-600 text-white rounded-xl font-black shadow-lg shadow-indigo-200 hover:bg-indigo-700 transition-transform active:scale-95">Save Profile</button>
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
    tbody.innerHTML = `<tr><td colspan="4" class="text-center py-8 text-slate-400 font-bold uppercase tracking-widest text-xs animate-pulse">Loading Platform Data...</td></tr>`;
    try {
        const users = await request("/admin/users");
        if (users.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="text-center py-8 text-slate-400 font-bold uppercase">No users found</td></tr>`;
            return;
        }
        tbody.innerHTML = users.map(u => `
            <tr class="hover:bg-slate-50 transition-colors">
                <td class="py-4 px-4 font-black text-slate-900 flex items-center gap-2">
                    ${u.is_superadmin ? '<span class="px-2 py-0.5 bg-emerald-100 text-emerald-700 rounded text-[9px] uppercase tracking-widest">Admin</span>' : ''}
                    ${esc(u.name)}
                </td>
                <td class="py-4 px-4">${esc(u.email)}</td>
                <td class="py-4 px-4 text-[10px] font-semibold tracking-wider text-slate-500">${esc(u.orgs || 'None')}</td>
                <td class="py-4 px-4 text-right">
                    ${!u.is_superadmin ? `<button onclick="deleteUser(${u.id})" class="text-xs font-black uppercase tracking-widest text-red-500 hover:text-red-700 hover:underline">Delete</button>` : ''}
                </td>
            </tr>
        `).join("");
    } catch(e) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center py-8 text-red-500 font-bold">${e.message}</td></tr>`;
    }
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
        if(tab) tab.className = v === t ? "text-2xl font-black flex items-center gap-3 border-b-4 border-slate-900 pb-2" : "text-2xl font-black flex items-center gap-3 text-slate-300 hover:text-slate-600 transition-colors pb-2";
    });
    
    if (t === 'calendar') {
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
        document.getElementById("file_name_display").textContent = "Upload your own file here";
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
    list.innerHTML = `<div class="py-12 text-center text-slate-400 font-black uppercase text-xs animate-pulse">Scanning Robotics...</div>`;
    try {
        const j = await request(`/automations/?ig_account_id=${ACTIVE_ACCOUNT_ID}`);
        if (!j.length) {
            list.innerHTML = `
            <div class="py-24 text-center border-2 border-dashed border-slate-200 rounded-3xl">
                <p class="text-sm text-slate-400 font-black uppercase mb-4">No Automations Established</p>
                <button onclick="showCreateAuto()" class="bg-slate-900 text-white px-6 py-2 rounded-xl text-xs font-black">Create First AI Job</button>
            </div>`;
            return;
        }
        list.innerHTML = j.map(a => renderAuto(a)).join("");
    } catch(e) { setError("Auto Error: " + e.message); }
}

function renderAuto(a) {
    const err = a.last_error ? `<p class="mt-2 text-[10px] bg-red-50 text-red-600 border border-red-100 p-2 rounded-xl font-bold uppercase tracking-tight">Error: ${esc(a.last_error)}</p>` : '';
    return `
    <div class="bg-slate-50 border border-slate-200 rounded-3xl p-6 flex flex-col items-stretch group hover:bg-white hover:shadow-xl transition-all duration-300">
        <div class="flex items-start justify-between mb-4">
            <div class="flex-1">
                <div class="flex items-center gap-3 mb-2">
                    <h4 class="text-lg font-black text-slate-800">${esc(a.name)}</h4>
                    <span class="px-2 py-0.5 rounded-full text-[8px] font-black uppercase tracking-tighter ${a.enabled ? 'bg-green-100 text-green-700 border border-green-200' : 'bg-slate-200 text-slate-500 border border-slate-300'}">${a.enabled ? 'Enabled' : 'Paused'}</span>
                    ${a.enrich_with_hadith ? '<span class="px-2 py-0.5 rounded-full text-[8px] font-black uppercase tracking-tighter bg-purple-100 text-purple-700 border border-purple-200">Enriched</span>' : ''}
                </div>
                <p class="text-xs text-slate-500 font-medium line-clamp-1 italic">Prompt: "${esc(a.topic_prompt)}"</p>
                ${err}
            </div>
            <div class="flex items-center gap-2">
                <button onclick="triggerAuto(${a.id})" class="p-3 rounded-2xl bg-white border border-slate-200 text-slate-400 hover:text-indigo-600 hover:border-indigo-200 hover:shadow-lg transition-all" title="Run Once (Create Post)">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                </button>
                <button onclick="testLLM(${a.id}, '${esc(a.topic_prompt)}', '${a.style_preset}')" class="p-3 rounded-2xl bg-white border border-slate-200 text-slate-400 hover:text-indigo-600 hover:border-indigo-200 hover:shadow-lg transition-all" title="Test AI Generation">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.341A8.001 8.001 0 0012 4a8.001 8.001 0 00-7.428 11.341c.142.311.23.642.23.978V19a2 2 0 002 2h9a2 2 0 002-2v-2.681c0-.336.088-.667.23-.978z" /></svg>
                </button>
                <button onclick="editAuto(${JSON.stringify(a).replaceAll('"', '&quot;')})" class="p-3 rounded-2xl bg-white border border-slate-200 text-slate-400 hover:text-slate-600 hover:border-slate-300 hover:shadow-lg transition-all" title="Edit Automation Settings">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
                </button>
                <button onclick="deleteAuto(${a.id})" class="p-3 rounded-2xl bg-white border border-slate-200 text-slate-400 hover:text-red-600 hover:border-red-200 hover:shadow-lg transition-all" title="Delete Automation">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                </button>
            </div>
        </div>
        <div class="flex flex-wrap gap-4 text-[10px] font-black uppercase tracking-widest text-slate-400 border-t border-slate-100 pt-4">
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
        statusEl.className = `px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest ${getPostColor(p.status).includes('#') ? 'bg-slate-200 text-slate-600' : ''}`;
        
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
    list.innerHTML = `<div class="col-span-full py-12 text-center text-slate-400 font-black uppercase text-xs animate-pulse">Consulting Gallery...</div>`;
    try {
        const j = await request("/media-assets");
        if (!j.length) {
            list.innerHTML = `<div class="col-span-full py-12 text-center text-slate-400 font-bold">No assets found. Upload some!</div>`;
            return;
        }
        list.innerHTML = j.map(m => `
            <div class="relative group rounded-2xl overflow-hidden aspect-square border border-slate-200 bg-slate-100">
                <img src="${m.url}" class="w-full h-full object-cover"/>
                <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-end p-3 gap-2">
                    <div class="flex flex-wrap gap-1 mb-auto">
                        ${(m.tags || []).map(t => `<span class="px-1.5 py-0.5 bg-white/20 backdrop-blur-md rounded text-[8px] text-white font-bold uppercase">${esc(t)}</span>`).join("")}
                    </div>
                    <button onclick="deleteMedia(${m.id})" class="bg-red-500 text-white w-full py-2 rounded-xl text-[10px] font-black uppercase">Delete</button>
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
    list.innerHTML = `<div class="col-span-full py-12 text-center text-slate-400 font-black uppercase text-xs animate-pulse">Loading Profiles...</div>`;
    
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
            <div class="col-span-full py-24 text-center border-2 border-dashed border-slate-200 rounded-3xl">
                <p class="text-sm text-slate-400 font-black uppercase mb-4">No Profiles Found</p>
                <button onclick="showCreateProfile()" class="bg-indigo-600 text-white px-6 py-2 rounded-xl text-xs font-black">Create First Profile</button>
            </div>`;
            return;
        }
        
        list.innerHTML = j.map(p => {
            return `
            <div class="bg-white border border-slate-200 rounded-3xl p-6 flex flex-col items-stretch group hover:bg-slate-50 hover:shadow-xl transition-all duration-300">
                <div class="flex items-start justify-between mb-4">
                    <div class="flex-1">
                        <div class="flex items-center gap-3 mb-2">
                            <h4 class="text-lg font-black text-slate-800">${esc(p.name)}</h4>
                        </div>
                        <p class="text-[10px] uppercase font-black tracking-widest text-slate-400 mb-2">Niche: <span class="text-indigo-600">${esc(p.niche_category || 'N/A')}</span></p>
                        <p class="text-xs text-slate-500 font-medium line-clamp-2">${esc(p.focus_description || 'No focus specified.')}</p>
                    </div>
                </div>
                <div class="mt-auto pt-4 border-t border-slate-100 flex justify-end gap-2">
                    <button onclick='editProfile(${JSON.stringify(p).replaceAll("'", "&apos;")})' class="p-3 rounded-2xl bg-white border border-slate-200 text-slate-400 hover:text-indigo-600 hover:border-indigo-200 transition-all font-bold text-xs">Edit</button>
                    <button onclick="deleteProfile(${p.id})" class="p-3 rounded-2xl bg-white border border-slate-200 text-slate-400 hover:text-red-600 hover:border-red-200 transition-all font-bold text-xs">Delete</button>
                </div>
            </div>`;
        }).join("");
    } catch(e) { 
        list.innerHTML = `<div class="col-span-full text-center text-red-500 font-bold">${e.message}</div>`;
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
    list.innerHTML = `<div class="col-span-full py-12 text-center text-slate-400 font-black uppercase text-xs animate-pulse">Browsing Archive...</div>`;
    try {
        const j = await request(`/library/?topic=${encodeURIComponent(query)}`);
        if (!j.length) {
            list.innerHTML = `
            <div class="col-span-full py-24 text-center border-2 border-dashed border-slate-200 rounded-3xl">
                <p class="text-sm text-slate-400 font-black uppercase">Archive Empty</p>
                <p class="text-[10px] text-slate-400 mt-2">Upload or Seed some content to start.</p>
            </div>`;
            return;
        }
        list.innerHTML = j.map(item => `
        <div class="bg-slate-50 border border-slate-200 rounded-2xl p-5 hover:bg-white hover:shadow-lg transition-all">
            <div class="flex justify-between items-start mb-3">
                <span class="px-2 py-0.5 rounded-lg bg-indigo-100 text-indigo-700 text-[8px] font-black uppercase tracking-widest">${esc(item.type)}</span>
                <span class="text-[9px] font-bold text-slate-400">${item.topics.join(", ")}</span>
            </div>
            <h5 class="text-sm font-black text-slate-800 mb-2 line-clamp-1">${esc(item.title || 'Untitled')}</h5>
            <p class="text-xs text-slate-500 line-clamp-3 mb-4 italic">"${esc(item.text_en)}"</p>
            <div class="flex justify-between items-center pt-3 border-t border-slate-100">
                <span class="text-[9px] font-bold text-slate-400">${esc(item.source_name || 'Personal')}</span>
                <button onclick="deleteLibraryItem(${item.id})" class="text-slate-300 hover:text-red-500 transition-colors">
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
        display.className = "text-sm font-black text-indigo-700 uppercase fade-in";
        box.className = "p-4 bg-indigo-50 border border-indigo-200 rounded-2xl shadow-inner";
    } else {
        display.textContent = "Please Setup Account →";
        display.className = "text-sm font-black text-slate-400 italic";
        box.className = "p-4 bg-slate-50 border border-slate-200 rounded-2xl shadow-none";
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
            <div class="w-16 h-16 bg-slate-100 text-slate-600 rounded-full flex items-center justify-center mx-auto mb-6">
                <svg class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            </div>
            <h3 class="text-xl font-black text-slate-800 mb-2">No Instagram Slots</h3>
            <p class="text-sm text-slate-500 max-w-xs mx-auto mb-8">Your account is connected, but you haven't added an Instagram account slot yet.</p>
            <button onclick="toggleSettings()" class="border-2 border-slate-900 text-slate-900 px-8 py-3 rounded-xl font-black hover:bg-slate-900 hover:text-white transition-all">Register First Slot</button>
        </div>`;
    } else if (type === "no_posts") {
        html = `
        <div class="col-span-full py-24 text-center">
            <div class="w-16 h-16 bg-indigo-50 text-indigo-400 rounded-full flex items-center justify-center mx-auto mb-6">
                <svg class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
            </div>
            <h3 class="text-xl font-black text-slate-800 mb-2">The Stream is Empty</h3>
            <p class="text-sm text-slate-500 max-w-xs mx-auto mb-8">Ready to publish? Use the <b>Content Intake</b> form on the left to upload your FIRST LOCAL POSTER or personal file.</p>
            <div class="flex items-center justify-center gap-2 text-indigo-600 font-bold animate-bounce">
                <svg class="h-4 w-4 rotate-180" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" /></svg>
                <span>Follow Step 3 to start</span>
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
        list.innerHTML = `<div class="text-xs text-slate-400 font-bold italic text-center py-4 bg-slate-50 rounded-xl">No accounts linked yet.</div>`;
        return;
    }
    list.innerHTML = ACCOUNTS.map(a => `
        <div class="flex justify-between items-center p-3 rounded-xl border border-slate-200 bg-slate-50">
            <div>
                <div class="text-sm font-bold text-slate-800">${esc(a.name)}</div>
                <div class="text-[10px] text-slate-500 font-mono mt-0.5">ID: ${esc(a.ig_user_id)}</div>
            </div>
            <button onclick="deleteAccount(${a.id})" class="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors" title="Delete Account">
                <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
            </button>
        </div>
    `).join("");
}
async function loadStats() {
    const el = document.getElementById("stats");
    try {
        const j = await request(`/posts/stats?ig_account_id=${ACTIVE_ACCOUNT_ID || ''}`);
        el.innerHTML = Object.entries(j.counts || {}).map(([k,v]) => `
            <div class="bg-white border-2 border-slate-100 rounded-2xl p-4 text-center fade-in shadow-sm">
                <div class="text-[8px] font-black text-slate-300 uppercase leading-none mb-1">${esc(k)}</div>
                <div class="text-lg font-black text-slate-800">${v}</div>
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
        submitted: "bg-slate-100 text-slate-600 border-slate-200", 
        drafted: "bg-blue-50 text-blue-600 border-blue-200", 
        needs_review: "bg-rose-50 text-rose-600 border-rose-200", 
        scheduled: "bg-indigo-50 text-indigo-600 border-indigo-200", 
        published: "bg-emerald-50 text-emerald-600 border-emerald-200", 
        failed: "bg-red-50 text-red-600 border-red-200" 
    };
    const c = colors[p.status] || "bg-slate-100 text-slate-500 border-slate-200";
    
    return `
    <div class="bg-white border border-slate-200 rounded-3xl overflow-hidden flex flex-col group hover:shadow-2xl hover:border-indigo-100 transition-all duration-500 fade-in">
        <div class="relative aspect-square bg-slate-100 overflow-hidden cursor-pointer" onclick="openPostEditor(${p.id})">
            <img src="${p.media_url}" class="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110" loading="lazy" onerror="this.src='https://placehold.co/600x600?text=Media+Missing'"/>
            <div class="absolute top-4 left-4 right-4 flex justify-between items-start">
               <span class="px-3 py-1.5 rounded-xl border backdrop-blur-md text-[9px] font-black uppercase tracking-widest shadow-lg ${c}">${esc(p.status)}</span>
               <div class="p-2 rounded-xl bg-white/90 border border-slate-200 text-slate-900 shadow-xl opacity-0 group-hover:opacity-100 transition-all transform translate-y-2 group-hover:translate-y-0">
                  <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>
               </div>
            </div>
            ${p.scheduled_time ? `<div class="absolute bottom-4 left-4 px-3 py-1 bg-indigo-600 text-white rounded-lg text-[8px] font-black uppercase tracking-tighter shadow-lg">Due: ${new Date(p.scheduled_time).toLocaleString()}</div>` : ''}
        </div>
        <div class="p-5 flex flex-col flex-1">
            <p class="text-[12px] text-slate-700 leading-relaxed font-medium mb-4 line-clamp-2">${esc(p.caption || '(No Caption Generated)')}</p>
            <div class="mt-auto flex items-center justify-between border-t border-slate-100 pt-4">
                <span class="text-[10px] font-bold text-slate-300 uppercase italic">${esc(p.source_type)}</span>
                <button onclick="openPostEditor(${p.id})" class="text-[10px] font-black text-indigo-600 uppercase tracking-widest hover:underline">Manage Post</button>
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
    try { await request(`/posts/${id}/generate`, { method: "POST" }); await refreshAll(); } catch(e) { if(el) { el.textContent = "AI FAILED"; el.className = "mt-4 text-[9px] text-center font-black text-red-600"; } alert(e.message); }
}
async function approvePost(id) {
    const el = document.getElementById(`msg-${id}`);
    if(el) { el.textContent = "✔️ ADDING TO QUEUE..."; el.className = "mt-4 text-[9px] text-center font-black text-emerald-500 animate-pulse"; }
    try { await request(`/posts/${id}/approve`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({approve_anyway: true}) }); await refreshAll(); } catch(e) { if(el) { el.textContent = "FAIL"; el.className = "mt-4 text-[9px] text-center font-black text-red-600"; } alert(e.message); }
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
        
        const welcomeBanner = document.getElementById("onboarding_banner");
        if (!ME.onboarding_complete) {
            welcomeBanner.classList.remove("hidden");
        } else {
            welcomeBanner.classList.add("hidden");
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
<body class="bg-slate-50 min-h-screen flex py-12 px-6 justify-center">
  <div class="max-w-2xl w-full bg-white rounded-3xl shadow-xl p-8 lg:p-12 border border-slate-100">
    <div class="text-center mb-10">
      <h1 class="text-3xl font-black bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">Welcome to Social SaaS</h1>
      <p class="text-sm text-slate-500 mt-3 font-medium">Let's set up your first AI Content strategy. This will tailor how the system generates captions and media for your brand.</p>
    </div>
    
    <form id="onboardingForm" class="space-y-8">
      <!-- Business Info -->
      <div class="space-y-6">
        <h3 class="text-lg font-black text-slate-800 border-b border-slate-100 pb-2">Business Profile</h3>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-widest mb-2">Workspace Name</label>
                <input type="text" id="name" required class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none text-sm transition-all" placeholder="e.g. Apex Fitness, John's Real Estate">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-widest mb-2">Niche / Category</label>
                <select id="niche_category" required class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none text-sm bg-white">
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
            <label class="block text-xs font-bold text-slate-700 uppercase tracking-widest mb-2">Content Strategy & Goals</label>
            <textarea id="content_goals" required class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none text-sm min-h-[100px]" placeholder="What is the goal of your page? (e.g. 'Educate local homebuyers and showcase premium listings to generate leads')"></textarea>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-widest mb-2">Tone & Style</label>
                <input type="text" id="tone_style" required class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none text-sm transition-all" placeholder="e.g. Professional, Witty, High-Energy">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-widest mb-2">Language</label>
                 <select id="language" class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none text-sm bg-white">
                    <option value="english">English</option>
                    <option value="spanish">Spanish</option>
                    <option value="french">French</option>
                    <option value="arabic">Arabic</option>
                </select>
            </div>
        </div>
      </div>
      
      <!-- AI Boundaries -->
      <div class="space-y-6 pt-4 border-t border-slate-100">
        <h3 class="text-lg font-black text-slate-800 border-b border-slate-100 pb-2">AI Boundaries</h3>
        
        <div>
            <label class="block text-xs font-bold text-slate-700 uppercase tracking-widest mb-2">Banned Topics / Phrases (Optional)</label>
            <textarea id="banned_topics" class="w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500 outline-none text-sm min-h-[80px]" placeholder="e.g. 'Never mention competitors, avoid politics, don't use the word cheap'"></textarea>
            <p class="text-[10px] text-slate-400 font-medium mt-1">The AI will strictly avoid these concepts when generating content.</p>
        </div>
      </div>

      <div id="errorMsg" class="hidden text-xs font-bold text-red-600 text-center bg-red-50 p-3 rounded-lg border border-red-100"></div>
      
      <button type="submit" class="w-full bg-indigo-600 text-white rounded-xl py-4 font-black hover:bg-indigo-700 transition-all text-sm shadow-xl shadow-indigo-200 active:scale-[0.98]">
        Initialize Workspace &rarr;
      </button>
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
