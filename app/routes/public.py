# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import ContactMessage, User, TopicAutomation
from app.security.auth import get_current_user
from typing import Optional
from fastapi.templating import Jinja2Templates
import os

templates = Jinja2Templates(directory="app/templates")

router = APIRouter()

# --- HTML TEMPLATES (Embedded) ---

LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Sabeel Studio | Authentic Islamic Content Creation</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary: #0F3D2E;
      --primary-hover: #0a2d22;
      --bg-cream: #F8F6F2;
      --accent: #C9A96E;
      --text-main: #1A1A1A;
      --text-muted: #4A4A4A;
      --border: rgba(15, 61, 46, 0.1);
    }
    body { 
      font-family: 'Inter', sans-serif; 
      background-color: var(--bg-cream); 
      color: var(--text-main);
      -webkit-font-smoothing: antialiased;
    }
    .text-primary { color: var(--primary); }
    .bg-primary { background-color: var(--primary); }
    .border-primary { border-color: var(--border); }
    .text-accent { color: var(--accent); }
    .bg-cream { background-color: var(--bg-cream); }
    
    .btn-primary {
      background-color: var(--primary);
      color: white;
      transition: all 0.3s ease;
    }
    .btn-primary:hover {
      background-color: var(--primary-hover);
      transform: translateY(-2px);
    }
    .btn-secondary {
      background-color: transparent;
      color: var(--primary);
      border: 1px solid var(--border);
      transition: all 0.3s ease;
    }
    .btn-secondary:hover {
      background-color: rgba(15, 61, 46, 0.03);
      transform: translateY(-2px);
    }
    
    .card {
      background: white;
      border: 1px solid var(--border);
      transition: all 0.3s ease;
    }
    .card:hover {
      border-color: var(--accent);
      transform: translateY(-4px);
    }
    
    .mockup-shadow {
      box-shadow: 0 20px 50px rgba(0,0,0,0.05);
    }
  </style>
</head>
<body class="min-h-screen">
  <!-- Navbar -->
  <nav class="max-w-7xl mx-auto px-6 py-8 flex justify-between items-center relative z-50">
    <a href="/" class="flex flex-col">
      <div class="text-xl font-extrabold tracking-tighter text-primary inline-block">SABEEL</div>
      <div class="text-[9px] font-bold text-primary uppercase tracking-[0.3em] pl-1 leading-none -mt-0.5">Studio</div>
    </a>
    
    <div class="flex items-center gap-8">
      <a href="/demo" class="text-xs font-bold uppercase tracking-widest text-muted hover:text-primary transition-colors">Demo</a>
      <a href="/contact" class="text-xs font-bold uppercase tracking-widest text-muted hover:text-primary transition-colors">Contact</a>
      {% if authenticated %}
        <a href="/app" class="px-6 py-3 btn-primary rounded-xl font-bold text-xs uppercase tracking-widest">Go to App</a>
      {% else %}
        <a href="/register" class="px-6 py-3 btn-primary rounded-xl font-bold text-xs uppercase tracking-widest">Get Started</a>
      {% endif %}
    </div>
  </nav>

  <!-- Hero Section -->
  <section class="max-w-7xl mx-auto px-6 pt-16 md:pt-24 pb-24 text-center space-y-8">
    <h1 class="text-5xl md:text-7xl font-extrabold tracking-tight text-primary leading-[1.05]">
      Create authentic Islamic content <br class="hidden md:block"/> 
      <span class="text-accent">—</span> without compromising accuracy
    </h1>
    <p class="max-w-2xl mx-auto text-text-muted text-lg md:text-xl font-medium leading-relaxed italic opacity-80">
      Generate captions, reminders, and posts grounded in real Quran and Hadith — built for creators who value trust.
    </p>
    <div class="pt-4 flex flex-col md:flex-row justify-center gap-4">
      <a href="/register" class="px-10 py-5 btn-primary rounded-2xl font-bold text-sm uppercase tracking-widest shadow-xl shadow-primary/10">Get Started</a>
      <a href="/demo" class="px-10 py-5 btn-secondary rounded-2xl font-bold text-sm uppercase tracking-widest">View Demo</a>
    </div>

    <!-- UI Mockup / Visual -->
    <div class="pt-20 max-w-4xl mx-auto px-4">
      <div class="card p-8 md:p-12 rounded-[2.5rem] mockup-shadow text-left space-y-8">
        <div class="flex items-center gap-4 border-b border-gray-100 pb-6">
          <div class="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold">S</div>
          <div>
            <div class="text-sm font-bold">Islamic Reminders</div>
            <div class="text-[10px] text-muted font-bold uppercase tracking-widest">Content Strategy</div>
          </div>
        </div>
        <div class="space-y-6">
          <div class="aspect-[4/5] bg-cream rounded-3xl overflow-hidden flex items-center justify-center p-12 border border-gray-50">
            <div class="text-center space-y-6">
              <div class="text-accent text-3xl opacity-50 italic">"</div>
              <p class="text-2xl font-black text-primary leading-tight italic">Verily, with hardship comes ease.</p>
              <div class="text-[10px] font-bold text-muted uppercase tracking-[0.2em]">— Quran 94:6</div>
            </div>
          </div>
          <div class="space-y-2">
            <div class="h-1.5 w-12 bg-accent rounded-full"></div>
            <p class="text-sm text-text-muted font-medium leading-relaxed">
              A reminder for when times feel heavy. Allah promises that ease is always close by. Stay patient, stay steadfast. #Faith #Quran #Sabr
            </p>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Trust Section -->
  <section class="bg-primary py-24 text-white">
    <div class="max-w-7xl mx-auto px-6">
      <div class="text-center space-y-4 mb-16">
        <h2 class="text-accent text-xs font-bold uppercase tracking-[0.4em]">Trust First</h2>
        <p class="text-3xl md:text-4xl font-extrabold tracking-tight italic">Built on trusted sources</p>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-12">
        <div class="space-y-4 text-center md:text-left">
          <div class="w-12 h-12 bg-white/5 rounded-2xl flex items-center justify-center text-accent">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"></path></svg>
          </div>
          <h3 class="text-xl font-bold italic">Verified Collections</h3>
          <p class="text-white/60 text-sm leading-relaxed">Content sourced from verified Quran and Hadith collections, ensuring every post is grounded in truth.</p>
        </div>
        <div class="space-y-4 text-center md:text-left">
          <div class="w-12 h-12 bg-white/5 rounded-2xl flex items-center justify-center text-accent">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.040L3 9v6c0 5.523 4.477 10 10 10s10-4.477 10-10V9l-1.382-1.016z"></path></svg>
          </div>
          <h3 class="text-xl font-bold italic">No Hallucinations</h3>
          <p class="text-white/60 text-sm leading-relaxed">Our system is designed to prevent "religious hallucinations." What you see is what is written in the sources.</p>
        </div>
        <div class="space-y-4 text-center md:text-left">
          <div class="w-12 h-12 bg-white/5 rounded-2xl flex items-center justify-center text-accent">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16m-7 6h7"></path></svg>
          </div>
          <h3 class="text-xl font-bold italic">Structured Content</h3>
          <p class="text-white/60 text-sm leading-relaxed">A strategic content system, not random generation. Maintain control over your message and impact.</p>
        </div>
      </div>
    </div>
  </section>

  <!-- Features Section -->
  <section class="max-w-7xl mx-auto px-6 py-32 space-y-16">
    <div class="text-center space-y-4">
      <h2 class="text-accent text-xs font-bold uppercase tracking-[0.4em]">Capabilities</h2>
      <p class="text-4xl font-extrabold tracking-tight text-primary italic">Meaningful tools for creators.</p>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
      <div class="card p-10 rounded-[2.5rem] flex gap-6 items-start">
        <div class="w-10 h-10 shrink-0 bg-primary/5 rounded-xl flex items-center justify-center text-primary">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
        </div>
        <div>
          <h3 class="text-xl font-bold italic text-primary mb-2">Meaningful Captions</h3>
          <p class="text-text-muted text-sm leading-relaxed">Draft reflections and captions that resonate with your audience while staying true to the message.</p>
        </div>
      </div>
      <div class="card p-10 rounded-[2.5rem] flex gap-6 items-start">
        <div class="w-10 h-10 shrink-0 bg-primary/5 rounded-xl flex items-center justify-center text-primary">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2"></path></svg>
        </div>
        <div>
          <h3 class="text-xl font-bold italic text-primary mb-2">Quote-Based Posts</h3>
          <p class="text-text-muted text-sm leading-relaxed">Quickly generate beautiful image-based posts from Quran and Hadith citations.</p>
        </div>
      </div>
      <div class="card p-10 rounded-[2.5rem] flex gap-6 items-start">
        <div class="w-10 h-10 shrink-0 bg-primary/5 rounded-xl flex items-center justify-center text-primary">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
        </div>
        <div>
          <h3 class="text-xl font-bold italic text-primary mb-2">Content Library</h3>
          <p class="text-text-muted text-sm leading-relaxed">Organize your inspirations, drafts, and archives in a simple, unified library system.</p>
        </div>
      </div>
      <div class="card p-10 rounded-[2.5rem] flex gap-6 items-start">
        <div class="w-10 h-10 shrink-0 bg-primary/5 rounded-xl flex items-center justify-center text-primary">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"></path></svg>
        </div>
        <div>
          <h3 class="text-xl font-bold italic text-primary mb-2">Ease of Publishing</h3>
          <p class="text-text-muted text-sm leading-relaxed">Schedule and publish your content to Instagram directly, allowing for consistent growth.</p>
        </div>
      </div>
    </div>
  </section>

  <!-- How It Works -->
  <section class="max-w-7xl mx-auto px-6 py-32 space-y-16 border-t border-primary/5">
    <div class="text-center space-y-4">
      <h2 class="text-accent text-xs font-bold uppercase tracking-[0.4em]">The Process</h2>
      <p class="text-4xl font-extrabold tracking-tight text-primary italic">Simple, calm workflow.</p>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-12 text-center">
      <div class="space-y-6">
        <div class="w-16 h-16 bg-accent/10 text-accent rounded-full flex items-center justify-center mx-auto text-xl font-black italic">1</div>
        <h3 class="text-xl font-bold text-primary italic">Select Source</h3>
        <p class="text-text-muted text-sm leading-relaxed">Choose from verified collections or your own curated library.</p>
      </div>
      <div class="space-y-6">
        <div class="w-16 h-16 bg-accent/10 text-accent rounded-full flex items-center justify-center mx-auto text-xl font-black italic">2</div>
        <h3 class="text-xl font-bold text-primary italic">Generate Post</h3>
        <p class="text-text-muted text-sm leading-relaxed">Review and refine the generated caption and visual design.</p>
      </div>
      <div class="space-y-6">
        <div class="w-16 h-16 bg-accent/10 text-accent rounded-full flex items-center justify-center mx-auto text-xl font-black italic">3</div>
        <h3 class="text-xl font-bold text-primary italic">Publish</h3>
        <p class="text-text-muted text-sm leading-relaxed">Schedule your content to be dispatched exactly when you want.</p>
      </div>
    </div>
  </section>

  <!-- Footer -->
  <footer class="max-w-7xl mx-auto px-6 py-20 border-t border-primary/5 flex flex-col md:flex-row justify-between items-center gap-8">
    <div class="text-text-muted font-bold text-[10px] uppercase tracking-[0.2em] italic">&copy; 2026 Mohammed Hassan. Sabeel Studio&trade;</div>
    <div class="flex flex-wrap justify-center gap-8 text-[10px] font-bold uppercase tracking-widest text-text-muted">
      <a href="/demo" class="hover:text-primary transition-colors">Demo</a>
      <a href="/contact" class="hover:text-primary transition-colors">Contact</a>
      <a href="/privacy" class="hover:text-primary transition-colors">Privacy</a>
      <a href="/terms" class="hover:text-primary transition-colors">Terms</a>
      <a href="/login" class="hover:text-primary transition-colors">Sign In</a>
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
  <title>Interactive Demo | Sabeel</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary: #0F3D2E;
      --bg-cream: #F8F6F2;
      --accent: #C9A96E;
      --text-main: #1A1A1A;
      --text-muted: #4A4A4A;
      --border: rgba(15, 61, 46, 0.1);
    }
    body { font-family: 'Inter', sans-serif; background: var(--bg-cream); color: var(--text-main); }
    .card { background: white; border: 1px solid var(--border); }
    .btn-primary { background-color: var(--primary); color: white; transition: all 0.3s ease; }
    .btn-primary:hover { background-color: #0a2d22; transform: translateY(-2px); }
  </style>
</head>
<body class="min-h-screen p-4 md:p-6 pb-20 md:pb-6">
  <div class="max-w-6xl mx-auto space-y-6 md:space-y-8">
    <div class="flex justify-between items-center">
      <div class="text-xl font-extrabold tracking-tighter text-primary">DEMO MODE</div>
      <a href="/" class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A] hover:text-[#0F3D2E] transition-colors">&larr; Exit Demo</a>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-8">
      <!-- Sidebar/Controls -->
      <div class="space-y-4 md:space-y-6">
        <div class="card p-6 md:p-8 rounded-[2rem] md:rounded-[2.5rem] space-y-6">
          <h2 class="text-xs font-bold uppercase tracking-widest text-[#C9A96E]">Simulation Controls</h2>
          <div class="space-y-4">
            <div class="space-y-2">
              <label class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A]">Topic Prompt</label>
              <input type="text" value="The importance of patience (Sabr) in difficult times" class="w-full bg-[#F8F6F2] border border-gray-200 rounded-xl px-4 py-3 text-xs outline-none focus:ring-1 focus:ring-[#0F3D2E]">
            </div>
            <div class="space-y-2">
              <label class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A]">Aesthetic Mode</label>
              <select class="w-full bg-[#F8F6F2] border border-gray-200 rounded-xl px-4 py-3 text-xs outline-none focus:ring-1 focus:ring-[#0F3D2E]">
                <option>Islamic Minimalist</option>
                <option>Elegant Script</option>
                <option>Modern Clean</option>
              </select>
            </div>
            <button onclick="simulateGeneration()" class="w-full btn-primary py-4 rounded-xl font-bold text-xs uppercase tracking-widest shadow-xl shadow-[#0F3D2E]/10">Generate Preview</button>
          </div>
        </div>

        <div class="card p-6 md:p-8 rounded-[2rem] md:rounded-[2.5rem]">
          <p class="text-[10px] font-bold text-[#4A4A4A] uppercase tracking-widest leading-relaxed opacity-60">
            Note: This is a real-time simulation using verified Islamic content sources. No actual Instagram API calls are made in demo mode.
          </p>
        </div>
      </div>

      <!-- Preview Area -->
      <div class="lg:col-span-2 space-y-6">
        <div id="preview-stage" class="card rounded-[2.5rem] md:rounded-[3rem] p-6 md:p-10 min-h-[400px] md:min-h-[500px] flex items-center justify-center relative overflow-hidden bg-white">
          <div id="loading-spinner" class="hidden animate-pulse text-[#0F3D2E] font-bold text-xs uppercase tracking-widest">Sourcing verified content...</div>
          
          <div id="demo-post" class="w-full max-w-md space-y-6 mt-4 md:mt-0">
            <div class="aspect-[4/5] rounded-[2rem] overflow-hidden bg-[#F8F6F2] border border-gray-100 relative">
              <div class="absolute inset-0 flex items-center justify-center p-12 text-center">
                <div class="space-y-6">
                  <div class="text-[#C9A96E] text-3xl opacity-50 italic">"</div>
                  <p id="overlay-text" class="text-2xl font-black italic text-[#0F3D2E] tracking-tight">Verily, Allah is with the patient.</p>
                  <div id="overlay-source" class="text-[10px] font-bold text-[#4A4A4A] uppercase tracking-[0.2em]">— Quran 2:153</div>
                </div>
              </div>
            </div>
            <div class="space-y-2">
              <div class="flex gap-2">
                <div class="h-1.5 w-12 bg-[#0F3D2E] rounded-full"></div>
                <div class="h-1.5 w-4 bg-gray-200 rounded-full"></div>
              </div>
              <p id="demo-caption" class="text-sm text-[#4A4A4A] leading-relaxed font-medium">
                Patience is not just waiting; it is how we act while we wait. Ground yourself in faith and know that Allah's timing is perfect. #Sabr #Faith #Reminders
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
        
        const content = [
          { q: " Allah does not burden a soul beyond that it can bear.", s: "Quran 2:286" },
          { q: "The best among you are those who have the best manners.", s: "Bukhari" },
          { q: "And He found you lost and guided you.", s: "Quran 93:7" }
        ];
        const selected = content[Math.floor(Math.random() * content.length)];
        document.getElementById('overlay-text').textContent = selected.q;
        document.getElementById('overlay-source').textContent = "— " + selected.s;
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
  <title>Sign In | Sabeel Studio</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary: #0F3D2E;
      --bg-cream: #F8F6F2;
      --accent: #C9A96E;
      --text-main: #1A1A1A;
      --text-muted: #4A4A4A;
      --border: rgba(15, 61, 46, 0.1);
    }
    body { font-family: 'Inter', sans-serif; background: var(--bg-cream); color: var(--text-main); }
    .card { background: white; border: 1px solid var(--border); }
    .btn-primary { background-color: var(--primary); color: white; transition: all 0.3s ease; }
    .btn-primary:hover { background-color: #0a2d22; transform: translateY(-2px); }
  </style>
</head>
<body class="min-h-screen flex items-center justify-center p-6 text-main">
  <div class="max-w-md w-full card rounded-[2rem] md:rounded-[2.5rem] p-6 md:p-10 space-y-6 md:space-y-8 shadow-xl shadow-black/5">
    <div class="text-center space-y-2">
      <h1 class="text-2xl font-extrabold tracking-tighter text-primary">Sabeel Studio</h1>
      <h2 class="text-xl font-bold italic opacity-80">Welcome back</h2>
    </div>

    <form id="loginForm" class="space-y-4">
      <div class="space-y-1">
        <label class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A] ml-3">Email Address</label>
        <input type="email" id="email" required class="w-full bg-[#F8F6F2] border border-gray-200 rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-[#0F3D2E] outline-none transition-all text-[#1A1A1A]" placeholder="name@company.com">
      </div>
      <div class="space-y-1">
        <label class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A] ml-3">Password</label>
        <input type="password" id="password" required class="w-full bg-[#F8F6F2] border border-gray-200 rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-[#0F3D2E] outline-none transition-all text-[#1A1A1A]" placeholder="••••••••">
      </div>
      
      <div id="errorMsg" class="hidden text-xs font-bold text-rose-500 bg-rose-500/10 p-4 rounded-xl border border-rose-500/20 text-center"></div>

      <button type="submit" class="w-full btn-primary py-4 rounded-2xl font-bold text-sm uppercase tracking-widest transition-all shadow-xl shadow-[#0F3D2E]/10 text-white">Sign In</button>
    </form>

    <div class="relative flex items-center justify-center py-2">
      <div class="w-full border-t border-gray-100"></div>
      <span class="absolute bg-white px-4 text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A] opacity-40">OR</span>
    </div>

    <a href="/auth/google/login" class="w-full flex items-center justify-center gap-3 bg-white hover:bg-gray-50 py-4 rounded-2xl font-bold text-sm uppercase tracking-widest transition-all border border-gray-200 text-[#1A1A1A]">
      <img src="https://www.gstatic.com/images/branding/product/1x/gsa_512dp.png" class="w-5 h-5" alt="Google">
      Continue with Google
    </a>

    <p class="text-center text-xs font-medium text-[#4A4A4A] mt-6">
      Don't have an account? <a href="/register" class="text-[#0F3D2E] font-bold hover:underline">Create one</a>
    </p>

    <div class="text-center">
      <a href="/" class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A] hover:text-[#0F3D2E] transition-colors">&larr; Back to Home</a>
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
  <title>Create Account | Sabeel Studio</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary: #0F3D2E;
      --bg-cream: #F8F6F2;
      --accent: #C9A96E;
      --text-main: #1A1A1A;
      --text-muted: #4A4A4A;
      --border: rgba(15, 61, 46, 0.1);
    }
    body { font-family: 'Inter', sans-serif; background: var(--bg-cream); color: var(--text-main); }
    .card { background: white; border: 1px solid var(--border); }
    .btn-primary { background-color: var(--primary); color: white; transition: all 0.3s ease; }
    .btn-primary:hover { background-color: #0a2d22; transform: translateY(-2px); }
  </style>
</head>
<body class="min-h-screen flex items-center justify-center p-6 text-main">
  <div class="max-w-md w-full card rounded-[2rem] md:rounded-[2.5rem] p-6 md:p-10 space-y-6 md:space-y-8 shadow-xl shadow-black/5">
    <div class="text-center space-y-2">
      <h1 class="text-2xl font-extrabold tracking-tighter text-primary">Sabeel Studio</h1>
      <h2 class="text-xl font-bold italic opacity-80">Start your journey</h2>
    </div>

    <form id="registerForm" class="space-y-4">
      <div class="space-y-1">
        <label class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A] ml-3">Full Name</label>
        <input type="text" id="name" required class="w-full bg-[#F8F6F2] border border-gray-200 rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-[#0F3D2E] outline-none transition-all text-[#1A1A1A]" placeholder="John Doe">
      </div>
      <div class="space-y-1">
        <label class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A] ml-3">Email Address</label>
        <input type="email" id="email" required class="w-full bg-[#F8F6F2] border border-gray-200 rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-[#0F3D2E] outline-none transition-all text-[#1A1A1A]" placeholder="name@company.com">
      </div>
      <div class="space-y-1">
        <label class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A] ml-3">Password</label>
        <input type="password" id="password" required class="w-full bg-[#F8F6F2] border border-gray-200 rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-[#0F3D2E] outline-none transition-all text-[#1A1A1A]" placeholder="At least 8 characters">
      </div>
      
      <div id="errorMsg" class="hidden text-xs font-bold text-rose-500 bg-rose-500/10 p-4 rounded-xl border border-rose-500/20 text-center"></div>

      <button type="submit" class="w-full btn-primary py-4 rounded-2xl font-bold text-sm uppercase tracking-widest transition-all shadow-xl shadow-[#0F3D2E]/10 text-white">Create Account</button>
    </form>

    <div class="relative flex items-center justify-center py-2">
      <div class="w-full border-t border-gray-100"></div>
      <span class="absolute bg-white px-4 text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A] opacity-40">OR</span>
    </div>

    <a href="/auth/google/login" class="w-full flex items-center justify-center gap-3 bg-white hover:bg-gray-50 py-4 rounded-2xl font-bold text-sm uppercase tracking-widest transition-all border border-gray-200 text-[#1A1A1A]">
      <img src="https://www.gstatic.com/images/branding/product/1x/gsa_512dp.png" class="w-5 h-5" alt="Google">
      Continue with Google
    </a>

    <p class="text-center text-xs font-medium text-[#4A4A4A] mt-6">
      Already have an account? <a href="/login" class="text-[#0F3D2E] font-bold hover:underline">Sign in</a>
    </p>

    <div class="text-center">
      <a href="/" class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A] hover:text-[#0F3D2E] transition-colors">&larr; Back to Home</a>
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
  <title>Contact Us | Sabeel Studio</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --primary: #0F3D2E;
      --bg-cream: #F8F6F2;
      --accent: #C9A96E;
      --text-main: #1A1A1A;
      --text-muted: #4A4A4A;
      --border: rgba(15, 61, 46, 0.1);
    }
    body { font-family: 'Inter', sans-serif; background: var(--bg-cream); color: var(--text-main); }
    .card { background: white; border: 1px solid var(--border); }
    .btn-primary { background-color: var(--primary); color: white; transition: all 0.3s ease; }
    .btn-primary:hover { background-color: #0a2d22; transform: translateY(-2px); }
  </style>
</head>
<body class="min-h-screen flex items-center justify-center p-6 text-main">
  <div class="max-w-4xl w-full card rounded-[2rem] md:rounded-[2.5rem] p-6 md:p-10 space-y-8 md:space-y-12 shadow-xl shadow-black/5">
    <div class="text-center space-y-4">
      <h1 class="text-4xl font-extrabold tracking-tighter text-primary italic">Get in <span class="text-accent">touch</span>.</h1>
      <p class="text-[#4A4A4A] font-bold uppercase tracking-widest text-[10px] opacity-60">Strategic support & platform inquiries</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-10">
      <div class="space-y-8">
        <div class="space-y-2 text-center md:text-left">
          <h3 class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A]">Contact Info</h3>
          <div class="space-y-4">
            <div class="flex items-center gap-4 group justify-center md:justify-start">
              <div class="w-10 h-10 rounded-xl bg-[#0F3D2E]/5 text-primary flex items-center justify-center group-hover:bg-primary transition-all group-hover:text-white shadow-lg shadow-[#0F3D2E]/5">
                <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
              </div>
              <span class="text-sm font-bold text-primary">hello@sabeel.studio</span>
            </div>
            <div class="flex items-center gap-4 group justify-center md:justify-start">
              <div class="w-10 h-10 rounded-xl bg-[#0F3D2E]/5 text-primary flex items-center justify-center group-hover:bg-primary transition-all group-hover:text-white shadow-lg shadow-[#0F3D2E]/5">
                <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
              </div>
              <span class="text-sm font-bold text-primary text-center md:text-left">Remote • Detroit, MI</span>
            </div>
          </div>
        </div>

        <div class="p-6 rounded-2xl bg-[#F8F6F2] border border-gray-100 italic">
          <p class="text-[10px] text-[#4A4A4A] font-bold leading-relaxed uppercase tracking-widest opacity-60">Typical response time is under 12 hours. We're here to help you scale your impact.</p>
        </div>
      </div>

      <form id="contactForm" class="space-y-4">
        <div class="space-y-1">
          <label class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A] ml-3">Identity</label>
          <input type="text" id="name" required class="w-full bg-[#F8F6F2] border border-gray-200 rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-[#0F3D2E] outline-none transition-all text-[#1A1A1A] placeholder:text-gray-300" placeholder="Your Name">
        </div>
        <div class="space-y-1">
          <label class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A] ml-3">Coordinates</label>
          <input type="email" id="email" required class="w-full bg-[#F8F6F2] border border-gray-200 rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-[#0F3D2E] outline-none transition-all text-[#1A1A1A] placeholder:text-gray-300" placeholder="Email Address">
        </div>
        <div class="space-y-1">
          <label class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A] ml-3">Message Buffer</label>
          <textarea id="message" required class="w-full bg-[#F8F6F2] border border-gray-200 rounded-2xl px-5 py-3.5 text-sm focus:ring-2 focus:ring-[#0F3D2E] outline-none transition-all text-[#1A1A1A] min-h-[150px] placeholder:text-gray-300" placeholder="How can we help?"></textarea>
        </div>
        
        <div id="statusMsg" class="hidden text-xs font-bold p-4 rounded-xl text-center"></div>

        <button type="submit" class="w-full btn-primary py-4 rounded-2xl font-bold text-sm uppercase tracking-widest transition-all shadow-xl shadow-[#0F3D2E]/10 text-white">Send Message</button>
      </form>
    </div>

    <div class="text-center pt-8 border-t border-gray-100">
      <a href="/" class="text-[10px] font-bold uppercase tracking-widest text-[#4A4A4A] hover:text-[#0F3D2E] transition-colors">&larr; Back to Home</a>
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
          statusMsg.className = "text-xs font-bold text-emerald-600 bg-emerald-500/10 p-4 rounded-xl border border-emerald-500/20 text-center";
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

PRIVACY_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Privacy Policy | Sabeel Studio</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet">
  <style>
    :root { --primary: #0F3D2E; --bg-cream: #F8F6F2; --accent: #C9A96E; --text-muted: #4A4A4A; }
    body { font-family: 'Inter', sans-serif; background-color: var(--bg-cream); color: #1A1A1A; line-height: 1.6; }
  </style>
</head>
<body class="p-8 md:p-20">
  <div class="max-w-3xl mx-auto space-y-12">
    <a href="/" class="text-[10px] font-bold uppercase tracking-widest text-text-muted hover:text-primary transition-colors">&larr; Back to Home</a>
    <div class="space-y-4">
        <h1 class="text-4xl font-black text-primary tracking-tight">Privacy Policy</h1>
        <p class="text-[10px] font-bold uppercase tracking-widest text-accent italic">Last updated: April 2026</p>
    </div>
    <div class="space-y-8 text-sm font-medium text-gray-700">
        <section class="space-y-3">
            <h2 class="text-lg font-bold text-primary">1. Information We Collect</h2>
            <p>We collect information you provide directly to us (name, email, organization) and data from third-party services you connect, specifically Meta (Facebook/Instagram) for the purpose of content management and publishing.</p>
        </section>
        <section class="space-y-3">
            <h2 class="text-lg font-bold text-primary">2. How We Use Information</h2>
            <p>Your data is used to provide, maintain, and improve Sabeel Studio. We use your connected Instagram data solely to facilitate content drafting, scheduling, and publishing at your explicit request.</p>
        </section>
        <section class="space-y-3">
            <h2 class="text-lg font-bold text-primary">3. Data Security</h2>
            <p>All data is transmitted via secure HTTPS and stored using industry-standard encryption. We do not sell your personal data to third parties.</p>
        </section>
        <section class="space-y-3">
            <h2 class="text-lg font-bold text-primary">4. Contact</h2>
            <p>For any privacy-related inquiries, contact <span class="text-primary font-bold">hello@sabeel.studio</span>.</p>
        </section>
    </div>
    <footer class="pt-12 border-t border-primary/5 text-[10px] font-bold uppercase tracking-widest text-text-muted">
       &copy; 2026 Mohammed Hassan. Sabeel Studio&trade;
    </footer>
  </div>
</body>
</html>
"""

TERMS_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Terms of Service | Sabeel Studio</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet">
  <style>
    :root { --primary: #0F3D2E; --bg-cream: #F8F6F2; --accent: #C9A96E; --text-muted: #4A4A4A; }
    body { font-family: 'Inter', sans-serif; background-color: var(--bg-cream); color: #1A1A1A; line-height: 1.6; }
  </style>
</head>
<body class="p-8 md:p-20">
  <div class="max-w-3xl mx-auto space-y-12">
    <a href="/" class="text-[10px] font-bold uppercase tracking-widest text-text-muted hover:text-primary transition-colors">&larr; Back to Home</a>
    <div class="space-y-4">
        <h1 class="text-4xl font-black text-primary tracking-tight">Terms of Service</h1>
        <p class="text-[10px] font-bold uppercase tracking-widest text-accent italic">Last updated: April 2026</p>
    </div>
    <div class="space-y-8 text-sm font-medium text-gray-700">
        <section class="space-y-3">
            <h2 class="text-lg font-bold text-primary">1. Acceptable Use</h2>
            <p>Sabeel Studio is designed for the creation of authentic Islamic content. Users are responsible for ensuring the accuracy and integrity of the content they produce and publish using our tools.</p>
        </section>
        <section class="space-y-3">
            <h2 class="text-lg font-bold text-primary">2. Intellectual Property</h2>
            <p>The platform, its design, and proprietary algorithms are the property of Mohammed Hassan. User-generated content remains the property of the creator.</p>
        </section>
        <section class="space-y-3">
            <h2 class="text-lg font-bold text-primary">3. Disclaimer</h2>
            <p>While we provide tools to reference verified sources, the final responsibility for content accuracy lies with the user. Sabeel Studio is not responsible for any impact resulting from published content.</p>
        </section>
    </div>
    <footer class="pt-12 border-t border-primary/5 text-[10px] font-bold uppercase tracking-widest text-text-muted">
       &copy; 2026 Mohammed Hassan. Sabeel Studio&trade;
    </footer>
  </div>
</body>
</html>
"""

COMING_SOON_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Coming Soon | Sabeel Studio</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet">
  <style>
    :root { --primary: #0F3D2E; --bg-cream: #F8F6F2; --accent: #C9A96E; --text-muted: #4A4A4A; }
    body { font-family: 'Inter', sans-serif; background-color: var(--bg-cream); color: #1A1A1A; }
    .btn-primary { background-color: var(--primary); color: white; transition: all 0.3s ease; }
    .btn-primary:hover { background-color: #0a2d22; transform: translateY(-2px); }
  </style>
</head>
<body class="min-h-screen flex items-center justify-center p-6 text-center">
  <div class="max-w-2xl w-full space-y-12">
    <div class="flex flex-col items-center">
      <div class="text-3xl font-extrabold tracking-tighter text-primary">SABEEL</div>
      <div class="text-[10px] font-bold text-primary uppercase tracking-[0.3em] pl-1">Studio</div>
    </div>
    <div class="space-y-6">
      <h1 class="text-5xl md:text-7xl font-black tracking-tight text-primary">Something <span class="text-accent underline decoration-accent/30 underline-offset-8">Meaningful</span> is coming.</h1>
      <p class="text-text-muted text-lg font-medium italic opacity-80">Authentic Islamic content creation, grounded in truth. We're refining the engine.</p>
    </div>
    <div class="max-w-md mx-auto w-full flex gap-3">
        <input type="email" placeholder="Enter your email" class="flex-1 bg-white border border-gray-100 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-primary transition-all shadow-sm">
        <button class="btn-primary px-8 py-4 rounded-2xl font-bold text-xs uppercase tracking-widest shadow-xl shadow-primary/10 transition-all">Notify Me</button>
    </div>
    <footer class="pt-12 border-t border-primary/5 text-[10px] font-bold uppercase tracking-widest text-text-muted/40">© 2026 Sabeel Studio</footer>
  </div>
</body>
</html>
"""

# --- ROUTES ---

@router.get("/privacy", response_class=HTMLResponse)
def privacy_page():
    return PRIVACY_HTML

@router.get("/terms", response_class=HTMLResponse)
def terms_page():
    return TERMS_HTML

@router.get("/", response_class=HTMLResponse)
def landing_page(user: Optional[User] = Depends(get_current_user)):
    from app.config import settings
    # COMING SOON LOGIC
    if settings.coming_soon_mode and not user:
        return COMING_SOON_HTML

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
def login_page(error: Optional[str] = None):
    html = LOGIN_HTML
    if error == "google_config_missing":
        error_banner = '<div class="text-xs font-bold text-rose-500 bg-rose-500/10 p-4 rounded-xl border border-rose-500/20 text-center mb-6">Google Sign-In is not configured on this server. Please check your Railway environment variables.</div>'
        html = html.replace('<h2 class="text-xl font-bold">Welcome back</h2>', error_banner + '<h2 class="text-xl font-bold">Welcome back</h2>')
    return html

@router.get("/register", response_class=HTMLResponse)
def register_page(error: Optional[str] = None):
    html = REGISTER_HTML
    if error == "google_config_missing":
        error_banner = '<div class="text-xs font-bold text-rose-500 bg-rose-500/10 p-4 rounded-xl border border-rose-500/20 text-center mb-6">Google Sign-In is not configured on this server. Please check your Railway environment variables.</div>'
        html = html.replace('<h2 class="text-xl font-bold">Start Automating</h2>', error_banner + '<h2 class="text-xl font-bold">Start Automating</h2>')
    return html

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

@router.get("/api/auth-debug")
def api_auth_debug(db: Session = Depends(get_db)):
    from app.models import User, Org
    from app.config import settings
    from app.main import STARTUP_LOG
    import os
    
    users = db.query(User).all()
    user_list = [
        {
            "id": u.id, 
            "email": u.email, 
            "is_superadmin": u.is_superadmin, 
            "is_active": u.is_active,
            "google_id": bool(u.google_id),
            "has_password": bool(u.password_hash)
        } for u in users
    ]
    
    orgs = db.query(Org).all()
    
    return {
        "status": "ready",
        "startup_log": STARTUP_LOG,
        "user_count": len(users),
        "users": user_list,
        "org_count": len(orgs),
        "env": {
            "SUPERADMIN_EMAIL": bool(os.environ.get("SUPERADMIN_EMAIL")),
            "SUPERADMIN_PASSWORD": bool(os.environ.get("SUPERADMIN_PASSWORD")),
            "GOOGLE_CLIENT_ID": bool(os.environ.get("GOOGLE_CLIENT_ID")),
            "GOOGLE_CLIENT_SECRET": bool(os.environ.get("GOOGLE_CLIENT_SECRET")),
            "GOOGLE_REDIRECT_URI": bool(os.environ.get("GOOGLE_REDIRECT_URI")),
            "DATABASE_URL": bool(os.environ.get("DATABASE_URL")),
        },
        "settings": {
            "superadmin_email": settings.superadmin_email,
            "google_client_id_present": bool(settings.google_client_id),
            "google_client_secret_present": bool(settings.google_client_secret),
            "google_redirect_uri": settings.google_redirect_uri,
            "database_url_type": "sqlite" if "sqlite" in str(settings.database_url) else "postgres"
        }
    }

@router.get("/api/debug-automations")
def api_debug_automations(db: Session = Depends(get_db)):
    autos = db.query(TopicAutomation).all()
    return [{"id": a.id, "name": a.name, "topic": a.topic_prompt, "last_error": a.last_error} for a in autos]

@router.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@router.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request):
    return templates.TemplateResponse("terms.html", {"request": request})
