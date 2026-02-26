from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import ContactMessage, User, TopicAutomation
from app.security.auth import get_current_user
from typing import Optional

router = APIRouter()

# --- HTML TEMPLATES (Embedded) ---

LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Social Media LLM | AI Social Posting, Human Control</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root {
      --brand: #6366f1;
      --brand-hover: #4f46e5;
      --main-bg: #020617;
      --surface: rgba(255, 255, 255, 0.03);
      --text-main: #ffffff;
      --text-muted: #94a3b8;
      --border: rgba(255, 255, 255, 0.1);
    }
    body { font-family: 'Inter', sans-serif; background-color: var(--main-bg); color: var(--text-main); }
    .ai-bg { background: radial-gradient(circle at top right, #312e81, #020617, #020617); }
    .glass { background: var(--surface); backdrop-filter: blur(12px); border: 1px solid var(--border); }
    .text-gradient {
      background: linear-gradient(to right, #818cf8, #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .feature-card:hover { transform: translateY(-5px); border-color: var(--brand); }
  </style>
</head>
<body class="ai-bg min-h-screen">
  <!-- Navbar -->
  <nav class="max-w-7xl mx-auto px-6 py-8 flex justify-between items-center">
    <div class="text-xl font-black italic tracking-tighter text-gradient">SOCIAL MEDIA LLM</div>
    <div class="flex items-center gap-6">
      <a href="/demo" class="text-xs font-black uppercase tracking-widest text-muted hover:text-white transition-colors">See Demo</a>
      {% if authenticated %}
        <a href="/app" class="px-6 py-3 bg-brand rounded-xl font-black text-xs uppercase tracking-widest text-white shadow-xl shadow-brand/20">Go to App</a>
      {% else %}
        <a href="/login" class="text-xs font-black uppercase tracking-widest text-muted hover:text-white transition-colors">Sign In</a>
        <a href="/register" class="px-6 py-3 bg-brand rounded-xl font-black text-xs uppercase tracking-widest text-white shadow-xl shadow-brand/20">Get Started</a>
      {% endif %}
    </div>
  </nav>

  <!-- Hero Section -->
  <section class="max-w-7xl mx-auto px-6 pt-20 pb-32 text-center space-y-8">
    <h1 class="text-6xl md:text-8xl font-black tracking-tighter italic text-white leading-[0.9]">
      AI SOCAL <span class="text-gradient">POSTING.</span><br/>
      HUMAN <span class="text-gradient">CONTROL.</span>
    </h1>
    <p class="max-w-2xl mx-auto text-muted text-lg md:text-xl font-medium">
      The ultimate engine for high-output social media strategy. Generate, review, and schedule verified content with pluggable knowledge sources.
    </p>
    <div class="pt-4 flex flex-wrap justify-center gap-4">
      <a href="/register" class="px-10 py-5 bg-brand rounded-2xl font-black text-sm uppercase tracking-widest text-white shadow-2xl shadow-brand/40">Launch Your Presence Now</a>
      <a href="/demo" class="px-10 py-5 bg-white/5 border border-white/10 rounded-2xl font-black text-sm uppercase tracking-widest text-white hover:bg-white/10 transition-all">Interactive Preview</a>
    </div>
  </section>

  <!-- How It Works -->
  <section class="max-w-7xl mx-auto px-6 py-32 space-y-16">
    <div class="text-center space-y-4">
      <h2 class="text-sm font-black text-brand uppercase tracking-[0.3em]">The Protocol</h2>
      <p class="text-4xl font-black italic text-white tracking-tight">Three steps to dominance.</p>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
      <div class="glass p-10 rounded-[3rem] space-y-6">
        <div class="w-12 h-12 bg-brand/20 rounded-2xl flex items-center justify-center text-brand font-black text-xl italic">01</div>
        <h3 class="text-xl font-black italic text-white">Import Knowledge</h3>
        <p class="text-muted text-sm leading-relaxed">Connect RSS feeds, URL lists, or upload manual libraries to ground your AI in real data.</p>
      </div>
      <div class="glass p-10 rounded-[3rem] space-y-6">
        <div class="w-12 h-12 bg-brand/20 rounded-2xl flex items-center justify-center text-brand font-black text-xl italic">02</div>
        <h3 class="text-xl font-black italic text-white">Refine Genius</h3>
        <p class="text-muted text-sm leading-relaxed">Review AI-generated captions and DALL-E 3 visuals. Tweak, edit, and approve in one click.</p>
      </div>
      <div class="glass p-10 rounded-[3rem] space-y-6">
        <div class="w-12 h-12 bg-brand/20 rounded-2xl flex items-center justify-center text-brand font-black text-xl italic">03</div>
        <h3 class="text-xl font-black italic text-white">Auto-Post</h3>
        <p class="text-muted text-sm leading-relaxed">The scheduler takes over, dispatching your content to Instagram exactly when your audience is active.</p>
      </div>
    </div>
  </section>

  <!-- Feature Grid -->
  <section class="max-w-7xl mx-auto px-6 py-32 space-y-16 bg-white/[0.02] rounded-[4rem] border border-white/[0.05]">
    <div class="text-center space-y-4">
      <h2 class="text-sm font-black text-brand uppercase tracking-[0.3em]">Features</h2>
      <p class="text-4xl font-black italic text-white tracking-tight">Built for modern scale.</p>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      <div class="glass p-8 rounded-3xl feature-card border border-white/5 transition-all">
        <h4 class="font-black italic text-white mb-2">Calendar View</h4>
        <p class="text-xs text-muted">Visualize your entire month's content strategy in a sleek global calendar.</p>
      </div>
      <div class="glass p-8 rounded-3xl feature-card border border-white/5 transition-all">
        <h4 class="font-black italic text-white mb-2">Multi-Account</h4>
        <p class="text-xs text-muted">Manage dozens of Instagram profiles from a single unified workspace.</p>
      </div>
      <div class="glass p-8 rounded-3xl feature-card border border-white/5 transition-all">
        <h4 class="font-black italic text-white mb-2">Knowledge Sourcing</h4>
        <p class="text-xs text-muted">Pluggable sources ensure your AI never hallucinates and stays on message.</p>
      </div>
      <div class="glass p-8 rounded-3xl feature-card border border-white/5 transition-all">
        <h4 class="font-black italic text-white mb-2">Neural Guardrails</h4>
        <p class="text-xs text-muted">Islamic policy alignment ensures your content is always compliant and respectful.</p>
      </div>
    </div>
  </section>

  <!-- Footer -->
  <footer class="max-w-7xl mx-auto px-6 py-20 border-t border-white/5 mt-20 flex flex-col md:flex-row justify-between items-center gap-8">
    <div class="text-muted font-bold text-xs uppercase tracking-widest italic">&copy; 2026 Social Media LLM. All Rights Reserved.</div>
    <div class="flex gap-8 text-[10px] font-black uppercase tracking-widest text-muted">
      <a href="/contact" class="hover:text-brand transition-colors">Support</a>
      <a href="/demo" class="hover:text-brand transition-colors">Demo</a>
      <a href="/login" class="hover:text-brand transition-colors">Sign In</a>
    </div>
  </footer>
</body>
</html>
"""

DEMO_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Interactive Demo | Social Media LLM</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; background: #020617; color: #ffffff; }
    .ai-bg { background: radial-gradient(circle at top right, #312e81, #0f172a, #020617); }
    .glass { background: rgba(255, 255, 255, 0.05); backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.1); }
    .text-gradient { background: linear-gradient(to right, #818cf8, #c084fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  </style>
</head>
<body class="ai-bg min-h-screen p-6">
  <div class="max-w-6xl mx-auto space-y-8">
    <div class="flex justify-between items-center">
      <div class="text-xl font-black italic tracking-tighter text-gradient">DEMO MODE</div>
      <a href="/" class="text-[10px] font-black uppercase tracking-widest text-muted hover:text-white transition-colors">&larr; Exit Demo</a>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <!-- Sidebar/Controls -->
      <div class="space-y-6">
        <div class="glass p-8 rounded-[2.5rem] space-y-6">
          <h2 class="text-sm font-black uppercase tracking-widest text-brand">Simulation Controls</h2>
          <div class="space-y-4">
            <div class="space-y-2">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Topic Prompt</label>
              <input type="text" value="The importance of patience (Sabr) in difficult times" class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-xs outline-none focus:ring-1 focus:ring-brand">
            </div>
            <div class="space-y-2">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Aesthetic Mode</label>
              <select class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-xs outline-none focus:ring-1 focus:ring-brand">
                <option>Islamic Minimalist</option>
                <option>Modern Corporate</option>
                <option>Abstract Neural</option>
              </select>
            </div>
            <button onclick="simulateGeneration()" class="w-full bg-brand py-4 rounded-xl font-black text-xs uppercase tracking-widest shadow-xl shadow-brand/20">Generate Preview</button>
          </div>
        </div>

        <div class="glass p-8 rounded-[2.5rem] border-brand/20">
          <p class="text-[10px] font-bold text-muted uppercase tracking-widest leading-relaxed">
            Note: This is a real-time simulation using mock neural weights. No actual Instagram API calls are made in demo mode.
          </p>
        </div>
      </div>

      <!-- Preview Area -->
      <div class="lg:col-span-2 space-y-6">
        <div id="preview-stage" class="glass rounded-[3rem] p-10 min-h-[500px] flex items-center justify-center relative overflow-hidden">
          <div id="loading-spinner" class="hidden animate-pulse text-brand font-black text-xs uppercase tracking-widest">Synthesizing Neural Visuals...</div>
          
          <div id="demo-post" class="w-full max-w-md space-y-6">
            <div class="aspect-square rounded-3xl overflow-hidden bg-white/5 border border-white/10 relative">
              <img id="demo-image" src="https://images.unsplash.com/photo-1519817650390-64a93447v?auto=format&fit=crop&q=80&w=800" class="w-full h-auto opacity-40 grayscale">
              <div class="absolute inset-0 flex items-center justify-center p-8 text-center bg-black/40">
                <p id="overlay-text" class="text-2xl font-black italic text-white tracking-tight drop-shadow-2xl">Patience is the key to every relief.</p>
              </div>
            </div>
            <div class="space-y-2">
              <div class="flex gap-2">
                <div class="h-1.5 w-12 bg-brand rounded-full"></div>
                <div class="h-1.5 w-4 bg-white/20 rounded-full"></div>
              </div>
              <p id="demo-caption" class="text-sm text-muted leading-relaxed font-medium">
                Verily, with hardship comes ease. Remember that your current struggle is shaping you for a beautiful destination. Stay steadfast. #Sabr #Patience #Faith
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    function simulateGeneration() {
      const stage = document.getElementById('preview-stage');
      const loader = document.getElementById('loading-spinner');
      const post = document.getElementById('demo-post');
      
      post.classList.add('opacity-0', 'scale-95');
      loader.classList.remove('hidden');
      
      setTimeout(() => {
        loader.classList.add('hidden');
        post.classList.remove('opacity-0', 'scale-95');
        post.classList.add('transition-all', 'duration-700', 'opacity-100', 'scale-100');
        
        const quotes = ["Verily, Allah is with the patient.", "Turn your wounds into wisdom.", "The best way to find yourself is to lose yourself in the service of others."];
        document.getElementById('overlay-text').textContent = quotes[Math.floor(Math.random() * quotes.length)];
      }, 1500);
    }
  </script>
</body>
</html>
"""

LOGIN_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sign In | Social Media LLM</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; background: var(--bg-main, #020617); color: var(--text-main, #ffffff); transition: all 0.3s ease; }
    .ai-bg {
      background: radial-gradient(circle at top right, #312e81, #0f172a, #020617);
    }
    .glass { 
      background: rgba(255, 255, 255, 0.05); 
      backdrop-filter: blur(20px); 
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.15); 
    }
    .text-gradient {
      display: inline-block;
      padding-right: 0.15em;
      padding-bottom: 0.1em;
      background: linear-gradient(to right, #818cf8, #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      color: transparent;
    }
    [data-theme='enterprise'] {
      --bg-main: #f8fafc;
      --text-main: #0f172a;
      --border: #e2e8f0;
      --surface: #ffffff;
    }
  </style>
  <script>
    (function() {
      const saved = localStorage.getItem('admin_theme') || 'startup';
      document.documentElement.setAttribute('data-theme', saved);
    })();
  </script>
</head>
<body class="ai-bg text-main min-h-screen flex items-center justify-center p-6">
  <div class="max-w-md w-full glass rounded-[2.5rem] p-10 space-y-8">
    <div class="text-center space-y-2">
      <h1 class="text-2xl font-black italic tracking-tighter text-gradient">Social Media LLM</h1>
      <h2 class="text-xl font-bold">Welcome back</h2>
    </div>

    <form id="loginForm" class="space-y-4">
      <div class="space-y-1">
        <label class="text-[10px] font-black uppercase tracking-widest text-muted ml-3">Email Address</label>
        <input type="email" id="email" required class="w-full bg-white/5 border border-border rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none transition-all text-main" placeholder="name@company.com">
      </div>
      <div class="space-y-1">
        <label class="text-[10px] font-black uppercase tracking-widest text-muted ml-3">Password</label>
        <input type="password" id="password" required class="w-full bg-white/5 border border-border rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none transition-all text-main" placeholder="••••••••">
      </div>
      
      <div id="errorMsg" class="hidden text-xs font-bold text-rose-500 bg-rose-500/10 p-4 rounded-xl border border-rose-500/20 text-center"></div>

      <button type="submit" class="w-full bg-brand hover:bg-brand/90 py-4 rounded-2xl font-black text-sm uppercase tracking-widest transition-all shadow-xl shadow-brand/20 text-white">Sign In</button>
    </form>

    <div class="relative flex items-center justify-center py-2">
      <div class="w-full border-t border-border"></div>
      <span class="absolute bg-surface px-4 text-[10px] font-black uppercase tracking-widest text-muted">OR</span>
    </div>

    <a href="/auth/google/start" class="w-full flex items-center justify-center gap-3 bg-white/5 hover:bg-white/10 py-4 rounded-2xl font-black text-sm uppercase tracking-widest transition-all border border-border text-main">
      <img src="https://www.gstatic.com/images/branding/product/1x/gsa_512dp.png" class="w-5 h-5" alt="Google">
      Continue with Google
    </a>

    <p class="text-center text-xs font-medium text-muted mt-6">
      Don't have an account? <a href="/register" class="text-brand font-bold hover:underline">Create one</a>
    </p>

    <div class="text-center">
      <a href="/" class="text-[10px] font-black uppercase tracking-widest text-muted hover:text-main transition-colors">&larr; Back to Home</a>
    </div>
  </div>


  <script>
    document.getElementById('loginForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('email').value;
      const password = document.getElementById('password').value;
      const errorMsg = document.getElementById('errorMsg');
      
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', password);

      try {
        const res = await fetch('/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: formData
        });

        if (res.ok) {
          window.location.href = '/app';
        } else {
          const data = await res.json();
          errorMsg.textContent = data.detail || "Invalid credentials";
          errorMsg.classList.remove('hidden');
        }
      } catch (err) {
        errorMsg.textContent = "Connection error";
        errorMsg.classList.remove('hidden');
      }
    });
  </script>
</body>
</html>
"""

REGISTER_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Create Account | Social Media LLM</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; background: #020617; color: #ffffff; }
    .ai-bg {
      background: radial-gradient(circle at top right, #312e81, #0f172a, #020617);
    }
    .glass { 
      background: rgba(255, 255, 255, 0.05); 
      backdrop-filter: blur(20px); 
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.15); 
    }
    .text-gradient {
      display: inline-block;
      padding-right: 0.15em;
      padding-bottom: 0.1em;
      background: linear-gradient(to right, #818cf8, #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      color: transparent;
    }
    [data-theme='enterprise'] {
      --bg-main: #f8fafc;
      --text-main: #0f172a;
      --border: #e2e8f0;
      --surface: #ffffff;
    }
  </style>
  <script>
    (function() {
      const saved = localStorage.getItem('admin_theme') || 'startup';
      document.documentElement.setAttribute('data-theme', saved);
    })();
  </script>
</head>
<body class="ai-bg text-main min-h-screen flex items-center justify-center p-6">
  <div class="max-w-md w-full glass rounded-[2.5rem] p-10 space-y-8">
    <div class="text-center space-y-2">
      <h1 class="text-2xl font-black italic tracking-tighter text-gradient">Social Media LLM</h1>
      <h2 class="text-xl font-bold">Start Automating</h2>
    </div>

    <form id="registerForm" class="space-y-4">
      <div class="space-y-1">
        <label class="text-[10px] font-black uppercase tracking-widest text-muted ml-3">Full Name</label>
        <input type="text" id="name" required class="w-full bg-white/5 border border-border rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none transition-all text-main" placeholder="John Doe">
      </div>
      <div class="space-y-1">
        <label class="text-[10px] font-black uppercase tracking-widest text-muted ml-3">Email Address</label>
        <input type="email" id="email" required class="w-full bg-white/5 border border-border rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none transition-all text-main" placeholder="name@company.com">
      </div>
      <div class="space-y-1">
        <label class="text-[10px] font-black uppercase tracking-widest text-muted ml-3">Password</label>
        <input type="password" id="password" required class="w-full bg-white/5 border border-border rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none transition-all text-main" placeholder="At least 8 characters">
      </div>
      
      <div id="errorMsg" class="hidden text-xs font-bold text-rose-500 bg-rose-500/10 p-4 rounded-xl border border-rose-500/20 text-center"></div>

      <button type="submit" class="w-full bg-brand hover:bg-brand/90 py-4 rounded-2xl font-black text-sm uppercase tracking-widest transition-all shadow-xl shadow-brand/20 text-white">Create Account</button>
    </form>

    <div class="relative flex items-center justify-center py-2">
      <div class="w-full border-t border-border"></div>
      <span class="absolute bg-surface px-4 text-[10px] font-black uppercase tracking-widest text-muted">OR</span>
    </div>

    <a href="/auth/google/start" class="w-full flex items-center justify-center gap-3 bg-white/5 hover:bg-white/10 py-4 rounded-2xl font-black text-sm uppercase tracking-widest transition-all border border-border text-main">
      <img src="https://www.gstatic.com/images/branding/product/1x/gsa_512dp.png" class="w-5 h-5" alt="Google">
      Continue with Google
    </a>

    <p class="text-center text-xs font-medium text-muted mt-6">
      Already have an account? <a href="/login" class="text-brand font-bold hover:underline">Sign in</a>
    </p>

    <div class="text-center">
      <a href="/" class="text-[10px] font-black uppercase tracking-widest text-muted hover:text-main transition-colors">&larr; Back to Home</a>
    </div>
  </div>


  <script>
    document.getElementById('registerForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {
        name: document.getElementById('name').value,
        email: document.getElementById('email').value,
        password: document.getElementById('password').value
      };
      
      const errorMsg = document.getElementById('errorMsg');

      try {
        const res = await fetch('/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          window.location.href = '/app';
        } else {
          const data = await res.json();
          errorMsg.textContent = data.detail || "Registration failed";
          errorMsg.classList.remove('hidden');
        }
      } catch (err) {
        errorMsg.textContent = "Connection error";
        errorMsg.classList.remove('hidden');
      }
    });
  </script>
</body>
</html>
"""

CONTACT_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Contact Us | Social Media LLM</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; background: #020617; color: #ffffff; }
    .ai-bg {
      background: radial-gradient(circle at top right, #312e81, #0f172a, #020617);
    }
    .glass { 
      background: rgba(255, 255, 255, 0.05); 
      backdrop-filter: blur(20px); 
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.15); 
    }
    .text-gradient {
      display: inline-block;
      padding-right: 0.15em;
      padding-bottom: 0.1em;
      background: linear-gradient(to right, #818cf8, #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      color: transparent;
    }
    [data-theme='enterprise'] {
      --bg-main: #f8fafc;
      --text-main: #0f172a;
      --border: #e2e8f0;
      --surface: #ffffff;
    }
  </style>
  <script>
    (function() {
      const saved = localStorage.getItem('admin_theme') || 'startup';
      document.documentElement.setAttribute('data-theme', saved);
    })();
  </script>
</head>
<body class="ai-bg text-main min-h-screen flex items-center justify-center p-6">
  <div class="max-w-2xl w-full glass rounded-[2.5rem] p-10 space-y-12">
    <div class="text-center space-y-4">
      <h1 class="text-4xl font-black italic tracking-tighter text-white">Get in <span class="text-brand">touch</span>.</h1>
      <p class="text-white/70 font-bold uppercase tracking-widest text-[10px]">Strategic support & platform inquiries</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-10">
      <div class="space-y-8">
        <div class="space-y-2">
          <h3 class="text-[10px] font-black uppercase tracking-widest text-muted">Contact Info</h3>
          <div class="space-y-4">
            <div class="flex items-center gap-4 group">
              <div class="w-10 h-10 rounded-xl bg-brand/20 text-brand flex items-center justify-center group-hover:bg-brand transition-all group-hover:text-white shadow-lg shadow-brand/10">
                <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
              </div>
              <span class="text-sm font-black text-white group-hover:text-brand transition-colors">hello@social-llm.ai</span>
            </div>
            <div class="flex items-center gap-4 group">
              <div class="w-10 h-10 rounded-xl bg-brand/20 text-brand flex items-center justify-center group-hover:bg-brand transition-all group-hover:text-white shadow-lg shadow-brand/10">
                <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
              </div>
              <span class="text-sm font-black text-white group-hover:text-brand transition-colors">Remote • Detroit, MI</span>
            </div>
          </div>
        </div>

        <div class="p-6 rounded-2xl bg-white/5 border border-border">
          <p class="text-[10px] text-muted font-medium leading-relaxed uppercase tracking-widest">Typical response time is under 12 hours. We're here to help you scale.</p>
        </div>
      </div>

      <form id="contactForm" class="space-y-4">
        <div class="space-y-1">
          <label class="text-[10px] font-black uppercase tracking-widest text-white/50 ml-3">Identity</label>
          <input type="text" id="name" required class="w-full bg-white/5 border border-white/10 rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none transition-all text-white placeholder:text-white/20" placeholder="Your Name">
        </div>
        <div class="space-y-1">
          <label class="text-[10px] font-black uppercase tracking-widest text-white/50 ml-3">Coordinates</label>
          <input type="email" id="email" required class="w-full bg-white/5 border border-white/10 rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none transition-all text-white placeholder:text-white/20" placeholder="Email Address">
        </div>
        <div class="space-y-1">
          <label class="text-[10px] font-black uppercase tracking-widest text-white/50 ml-3">Message Buffer</label>
          <textarea id="message" required class="w-full bg-white/5 border border-white/10 rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none transition-all text-white min-h-[150px] placeholder:text-white/20" placeholder="How can we help?"></textarea>
        </div>
        
        <div id="statusMsg" class="hidden text-xs font-bold p-4 rounded-xl text-center"></div>

        <button type="submit" class="w-full bg-brand hover:bg-brand/90 py-4 rounded-2xl font-black text-sm uppercase tracking-widest transition-all shadow-xl shadow-brand/20 text-white">Send Message</button>
      </form>
    </div>

    <div class="text-center pt-8 border-t border-border">
      <a href="/" class="text-[10px] font-black uppercase tracking-widest text-muted hover:text-main transition-colors">&larr; Back to Home</a>
    </div>
  </div>


  <script>
    document.getElementById('contactForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {
        name: document.getElementById('name').value,
        email: document.getElementById('email').value,
        message: document.getElementById('message').value
      };
      const statusMsg = document.getElementById('statusMsg');
      const btn = e.target.querySelector('button');

      try {
        btn.disabled = true;
        btn.textContent = "SENDING...";
        const res = await fetch('/api/contact', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          statusMsg.textContent = "Message sent successfully!";
          statusMsg.className = "text-xs font-bold text-emerald-400 bg-emerald-500/10 p-4 rounded-xl border border-emerald-500/20 text-center";
          statusMsg.classList.remove('hidden');
          e.target.reset();
        } else {
          throw new Error();
        }
      } catch (err) {
        statusMsg.textContent = "Error sending message. Try again later.";
        statusMsg.className = "text-xs font-bold text-red-500 bg-red-500/10 p-4 rounded-xl border border-red-500/20 text-center";
        statusMsg.classList.remove('hidden');
      } finally {
        btn.disabled = false;
        btn.textContent = "SEND MESSAGE";
      }
    });
  </script>
</body>
</html>
"""

# --- ROUTES ---

@router.get("/", response_class=HTMLResponse)
def landing_page(user: Optional[User] = Depends(get_current_user), db: Session = Depends(get_db)):
    html = LANDING_HTML

    if user:
        html = html.replace("{% if authenticated %}", "")
        html = html.replace("{% else %}", "<!--")
        html = html.replace("{% endif %}", "-->")
    else:
        html = html.replace("{% if authenticated %}", "<!--")
        html = html.replace("{% else %}", "-->")
        html = html.replace("{% endif %}", "")
    return html

@router.get("/login", response_class=HTMLResponse)
def login_page():
    return LOGIN_HTML

@router.get("/register", response_class=HTMLResponse)
def register_page():
    return REGISTER_HTML

@router.get("/demo", response_class=HTMLResponse)
def demo_page():
    return DEMO_HTML

@router.get("/contact", response_class=HTMLResponse)
def contact_page():
    return CONTACT_HTML

from pydantic import BaseModel
class ContactPayload(BaseModel):
    name: str
    email: str
    message: str

@router.post("/api/contact")
async def process_contact(payload: ContactPayload, db: Session = Depends(get_db)):
    msg = ContactMessage(
        name=payload.name,
        email=payload.email,
        message=payload.message
    )
    db.add(msg)
    db.commit()
    return {"status": "success"}

@router.get("/api/debug-automations")
def api_debug_automations(db: Session = Depends(get_db)):
    autos = db.query(TopicAutomation).all()
    return [{"id": a.id, "name": a.name, "topic": a.topic_prompt, "last_error": a.last_error} for a in autos]
