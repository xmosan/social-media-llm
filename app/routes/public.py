from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import ContactMessage, User
from app.security.auth import get_current_user
from typing import Optional

router = APIRouter()

# --- HTML TEMPLATES (Embedded) ---

LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Social Media LLM | Generate. Review. Publish.</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet">
  <style>
    :root {
      --brand: #6366f1;
      --brand-hover: #4f46e5;
      /* AI Luxury (Default Dark) */
      --main-bg: #020617;
      --surface: rgba(255, 255, 255, 0.03);
      --text-main: #ffffff;
      --text-muted: #94a3b8;
      --border: rgba(255, 255, 255, 0.1);
      --card-bg: rgba(255, 255, 255, 0.03);
    }

    [data-theme='enterprise'] {
      --main-bg: #f8fafc;
      --surface: #ffffff;
      --text-main: #0f172a;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --card-bg: #ffffff;
    }

    body { 
        font-family: 'Inter', sans-serif; 
        background-color: var(--main-bg);
        color: var(--text-main);
        transition: background-color 0.3s ease, color 0.3s ease;
    }
    
    .bg-main { background-color: var(--main-bg); }
    .bg-surface { background-color: var(--surface); }
    .text-main { color: var(--text-main); }
    .text-muted { color: var(--text-muted); }
    .border-border { border-color: var(--border); }
    .bg-brand { background-color: var(--brand); }
    .text-brand { color: var(--brand); }

    .ai-bg {
      background: radial-gradient(circle at top right, #312e81, var(--main-bg), var(--main-bg));
    }
    .typing::after {
      content: '|';
      animation: blink 1s infinite;
    }
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
    .glass {
      background: var(--surface);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid var(--border);
    }
    .text-gradient {
      background: linear-gradient(to right, #818cf8, #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      color: transparent;
    }
    .slide-dot.active { background: var(--brand); width: 24px; }
    .fade-in { animation: fadeIn 0.8s ease-out forwards; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  </style>
  <script>
    (function() {
      const saved = localStorage.getItem('admin_theme') || 'startup';
      document.documentElement.setAttribute('data-theme', saved);
    })();
  </script>
</head>
<body class="ai-bg text-main min-h-screen flex flex-col items-center justify-center p-6 text-center">
  
  <div class="max-w-4xl w-full space-y-12">
    <!-- Header -->
    <header class="space-y-4">
      <h1 id="typing-header" class="text-5xl md:text-7xl font-black tracking-tighter typing italic text-gradient"></h1>
      <p id="subheading" class="text-muted font-medium text-lg md:text-xl opacity-0">The ultimate AI engine for hands-free social growth.</p>
    </header>

    <!-- Slideshow -->
    <div class="glass rounded-[2.5rem] p-8 md:p-12 relative min-h-[300px] flex items-center justify-center fade-in" style="animation-delay: 1.5s;">
      <div id="slides-container" class="space-y-6">
        <!-- Slide content injected by JS -->
      </div>
      
      <!-- Nav Dots -->
      <div class="absolute bottom-6 left-1/2 -translate-x-1/2 flex gap-2" id="slide-dots"></div>
    </div>

    <!-- Actions -->
    <div class="flex flex-wrap justify-center gap-4 fade-in" style="animation-delay: 2s;">
      {% if authenticated %}
        <a href="/admin" class="px-10 py-4 bg-indigo-600 hover:bg-indigo-500 rounded-2xl font-black text-sm transition-all shadow-2xl shadow-indigo-900/40 uppercase tracking-widest">Go to Dashboard &rarr;</a>
      {% else %}
        <a href="/login" class="px-10 py-4 bg-indigo-600 hover:bg-indigo-500 rounded-2xl font-black text-sm transition-all shadow-2xl shadow-indigo-900/40 uppercase tracking-widest">Sign In</a>
        <a href="/register" class="px-10 py-4 bg-white/5 hover:bg-white/10 rounded-2xl font-black text-sm transition-all border border-white/10 uppercase tracking-widest">Create Account</a>
      {% endif %}
    </div>

    <div class="flex justify-center gap-8 text-[10px] font-black uppercase tracking-widest text-slate-500 fade-in" style="animation-delay: 2.2s;">
      <a href="/contact" class="hover:text-indigo-400 transition-colors">Contact</a>
      <a href="/auth/google/start" class="hover:text-indigo-400 transition-colors font-bold text-slate-400">Continue with Google</a>
    </div>
  </div>

  <script>
    const SLIDES = [
      { title: "Generate. Review. Publish.", bullets: ["AI creates content in seconds", "Full review cycle built-in", "One-click Instagram publishing"] },
      { title: "Automations that post daily", bullets: ["Set and forget your schedule", "Consistent presence without effort", "Handles multi-account workflows"] },
      { title: "AI captions + AI images", bullets: ["DALL-E 3 visual generation", "LLM-powered contextual captions", "Optimized hashtags automatically"] },
      { title: "Multi-org ready", bullets: ["Manage different brands separately", "Team-based access controls", "Infinite workspace scaling"] }
    ];

    let currentSlide = 0;

    function typeWriter(text, i, cb) {
      const header = document.getElementById('typing-header');
      if (!header) return;
      if (i < text.length) {
        header.innerHTML = text.substring(0, i + 1);
        setTimeout(() => typeWriter(text, i + 1, cb), 100);
      } else {
        header.classList.remove('typing');
        cb();
      }
    }

    function renderSlide(index) {
      const slidesContainer = document.getElementById('slides-container');
      const dotsContainer = document.getElementById('slide-dots');
      if (!slidesContainer || !dotsContainer) return;
      
      const slide = SLIDES[index];
      slidesContainer.innerHTML = `
        <div class="fade-in space-y-4">
          <h3 class="text-2xl md:text-3xl font-black text-main">${slide.title}</h3>
          <ul class="flex flex-wrap justify-center gap-x-6 gap-y-2 text-muted text-sm font-medium">
            ${slide.bullets.map(b => `<li class="flex items-center gap-2"><div class="w-1.5 h-1.5 rounded-full bg-indigo-500"></div>${b}</li>`).join('')}
          </ul>
        </div>
      `;
      
      dotsContainer.innerHTML = SLIDES.map((_, i) => `
        <div class="slide-dot h-1.5 rounded-full bg-white/20 transition-all duration-300 ${i === index ? 'active' : 'w-1.5'}"></div>
      `).join('');
    }

    function nextSlide() {
      currentSlide = (currentSlide + 1) % SLIDES.length;
      renderSlide(currentSlide);
    }

    function init() {
      const subheading = document.getElementById('subheading');
      typeWriter("Social Media LLM", 0, () => {
        if (subheading) {
          subheading.classList.add('fade-in');
          subheading.style.opacity = 1;
        }
        renderSlide(0);
        setInterval(nextSlide, 5000);
      });
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
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
    body { font-family: 'Inter', sans-serif; background: #020617; }
    .ai-bg {
      background: radial-gradient(circle at top right, #312e81, #0f172a, #020617);
    }
    .glass { 
      background: rgba(255, 255, 255, 0.03); 
      backdrop-filter: blur(12px); 
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.1); 
    }
    .text-gradient {
      background: linear-gradient(to right, #818cf8, #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      color: transparent;
    }
  </style>
</head>
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
          window.location.href = '/admin';
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
    body { font-family: 'Inter', sans-serif; background: #020617; }
    .ai-bg {
      background: radial-gradient(circle at top right, #312e81, #0f172a, #020617);
    }
    .glass { 
      background: rgba(255, 255, 255, 0.03); 
      backdrop-filter: blur(12px); 
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.1); 
    }
    .text-gradient {
      background: linear-gradient(to right, #818cf8, #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      color: transparent;
    }
  </style>
</head>
<body class="ai-bg text-white min-h-screen flex items-center justify-center p-6">
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
          window.location.href = '/admin';
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
    body { font-family: 'Inter', sans-serif; background: #020617; }
    .ai-bg {
      background: radial-gradient(circle at top right, #312e81, #0f172a, #020617);
    }
    .glass { 
      background: rgba(255, 255, 255, 0.03); 
      backdrop-filter: blur(12px); 
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.1); 
    }
    .text-gradient {
      background: linear-gradient(to right, #818cf8, #c084fc);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      color: transparent;
    }
  </style>
</head>
<body class="ai-bg text-main min-h-screen flex items-center justify-center p-6">
  <div class="max-w-2xl w-full glass rounded-[2.5rem] p-10 space-y-12">
    <div class="text-center space-y-4">
      <h1 class="text-4xl font-black italic tracking-tighter text-main">Get in <span class="text-brand">touch</span>.</h1>
      <p class="text-muted font-medium">Have questions or need support? Send us a message.</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-10">
      <div class="space-y-8">
        <div class="space-y-2">
          <h3 class="text-[10px] font-black uppercase tracking-widest text-muted">Contact Info</h3>
          <div class="space-y-4">
            <div class="flex items-center gap-4 group">
              <div class="w-10 h-10 rounded-xl bg-brand/10 text-brand flex items-center justify-center group-hover:bg-brand transition-all group-hover:text-white">
                <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
              </div>
              <span class="text-sm font-bold text-muted group-hover:text-main transition-colors">hello@social-llm.ai</span>
            </div>
            <div class="flex items-center gap-4 group">
              <div class="w-10 h-10 rounded-xl bg-brand/10 text-brand flex items-center justify-center group-hover:bg-brand transition-all group-hover:text-white">
                <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
              </div>
              <span class="text-sm font-bold text-muted group-hover:text-main transition-colors">Remote • Detroit, MI</span>
            </div>
          </div>
        </div>

        <div class="p-6 rounded-2xl bg-white/5 border border-border">
          <p class="text-[10px] text-muted font-medium leading-relaxed uppercase tracking-widest">Typical response time is under 12 hours. We're here to help you scale.</p>
        </div>
      </div>

      <form id="contactForm" class="space-y-4">
        <input type="text" id="name" required class="w-full bg-white/5 border border-border rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none transition-all text-main" placeholder="Your Name">
        <input type="email" id="email" required class="w-full bg-white/5 border border-border rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none transition-all text-main" placeholder="Email Address">
        <textarea id="message" required class="w-full bg-white/5 border border-border rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-brand outline-none transition-all text-main min-h-[150px]" placeholder="How can we help?"></textarea>
        
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
def landing_page(user: Optional[User] = Depends(get_current_user)):
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
