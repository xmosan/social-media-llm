# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_, and_
from app.db import get_db
from app.models import User, Org, OrgMember, IGAccount, Post, TopicAutomation, ContentProfile
from app.security.auth import require_user, optional_user
from app.services.prebuilt_loader import load_prebuilt_packs
from app.services.automation_runner import run_automation_once
from app.security.rbac import get_current_org_id
from typing import Optional
from pydantic import BaseModel
import json
import html
import calendar
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

router = APIRouter()

# --- STUDIO ASSETS (Centralized in ui_assets.py) ---
from .ui_assets import *

# --- REMAINING PAGE LOGIC ---

APP_DASHBOARD_CONTENT = """
    <!-- Header -->
    <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-8 mb-16">
      <div>
        <h1 class="heading-premium text-5xl md:text-6xl">Studio <span class="text-accent underline decoration-accent/10 decoration-8 underline-offset-[12px]">Guidance</span></h1>
        <div class="badge-premium mt-6 flex items-center gap-6">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              Interface Active
            </div>
            {connected_account_info}
        </div>
      </div>
      <div class="flex items-center gap-4">
        <button onclick="openNewPostModal()" class="px-10 py-5 bg-brand text-white rounded-2xl font-black text-[11px] uppercase tracking-[0.2em] shadow-2xl shadow-brand/20 hover:bg-brand-hover transition-all flex items-center gap-3 group">
            <svg class="w-4 h-4 group-hover:rotate-90 transition-transform duration-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
            Create Reminder
        </button>
        <button onclick="syncAccounts()" class="w-14 h-14 flex items-center justify-center bg-white border border-brand/10 text-brand rounded-2xl font-bold hover:border-brand/30 transition-all shadow-sm group" title="Sync Status">
            <svg class="w-6 h-6 group-hover:rotate-180 transition-transform duration-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
        </button>
      </div>
    </div>

    <!-- Quick Stats Cluster -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-6 mb-16">
      <div class="card p-8 border-brand/5 bg-white flex flex-col justify-between min-h-[140px]">
        <div class="flex justify-between items-start">
            <div class="badge-premium">Output</div>
            <div class="p-2 bg-brand/5 rounded-xl text-brand"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg></div>
        </div>
        <div>
            <div class="text-3xl font-black text-brand tracking-tight">{weekly_post_count} <span class="text-xs text-text-muted font-bold uppercase tracking-widest ml-1">Posts</span></div>
            <div class="text-[9px] font-black text-emerald-600 uppercase tracking-[0.3em] mt-2">Last 7 Days</div>
        </div>
      </div>
      <div class="card p-8 border-brand/5 bg-white flex flex-col justify-between min-h-[140px]">
        <div class="flex justify-between items-start">
            <div class="badge-premium">Growth</div>
            <div class="p-2 bg-brand/5 rounded-xl text-brand"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg></div>
        </div>
        <div>
            <div class="text-3xl font-black text-brand tracking-tight">{account_count} <span class="text-xs text-text-muted font-bold uppercase tracking-widest ml-1">Platforms</span></div>
            <div class="text-[9px] font-black text-brand uppercase tracking-[0.3em] mt-2">Network Active</div>
        </div>
      </div>
      <div class="card p-8 border-brand/5 bg-white flex flex-col justify-between min-h-[140px]">
        <div class="flex justify-between items-start">
            <div class="badge-premium">Assistant</div>
            <div class="p-2 bg-brand/5 rounded-xl text-brand"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9l-.505.505a4.125 4.125 0 005.758 5.758l.505-.505m9.393-9.393l.505-.505a4.125 4.125 0 10-5.758-5.758l-.505.505" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg></div>
        </div>
        <div>
            <div class="text-3xl font-black text-brand tracking-tight underline decoration-emerald-500/30 decoration-4">Ready</div>
            <div class="text-[9px] font-black text-text-muted uppercase tracking-[0.3em] mt-2">Guidance Engine</div>
        </div>
      </div>
      <div class="card p-8 border-brand/5 bg-white flex flex-col justify-between min-h-[140px]">
        <div class="flex justify-between items-start">
            <div class="badge-premium">Guidance</div>
            <div class="p-2 bg-accent/10 rounded-xl text-accent"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg></div>
        </div>
        <div>
            <div class="text-3xl font-black text-accent tracking-tighter">{next_post_countdown}</div>
            <div class="text-[9px] font-black text-accent uppercase tracking-[0.3em] mt-2">Until Next Reminder</div>
        </div>
      </div>
    </div>

    {get_started_card}

    {connection_cta}

    <!-- System Operations -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-10">
      <!-- Growth Feed -->
      <div class="lg:col-span-1 space-y-6">
        <h2 class="text-[10px] font-bold uppercase tracking-[0.4em] text-text-muted flex items-center gap-2">
            Next Scheduled Reminder
        </h2>
        <div class="card bg-white p-8 space-y-8 border-brand/5 shadow-xl shadow-brand/[0.02] group relative overflow-hidden">
          <div class="absolute top-0 right-0 w-32 h-32 bg-brand/[0.02] rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-700"></div>
          
          <div class="aspect-square rounded-[2rem] overflow-hidden bg-cream relative border border-brand/5 shadow-inner">
            {next_post_media}
            <div class="absolute top-6 right-6 bg-brand/90 backdrop-blur-md px-4 py-2 rounded-2xl text-[9px] font-bold uppercase tracking-widest text-white shadow-2xl shadow-brand/40">
              {next_post_time}
            </div>
            <div class="absolute bottom-6 left-6 flex items-center gap-2 bg-emerald-500/90 backdrop-blur-md px-3 py-1.5 rounded-xl text-[8px] font-bold uppercase tracking-widest text-white">
                <span class="w-1.5 h-1.5 rounded-full bg-white animate-pulse"></span>
                Ready
            </div>
          </div>

          <div class="space-y-6 relative">
            <div>
                <label class="text-[8px] font-bold text-accent uppercase tracking-widest">Planned Guidance</label>
                <p class="text-[13px] text-text-main leading-relaxed font-medium line-clamp-3 mt-1 italic opacity-80 group-hover:opacity-100 transition-opacity">
                  "{next_post_caption}"
                </p>
            </div>
            <div class="flex gap-4 {next_post_actions_class}">
              <button onclick="openEditPostModal('{next_post_id}', {next_post_caption_json}, '{next_post_time_iso}')" class="flex-1 py-4 bg-white border border-brand/10 rounded-2xl font-bold text-[10px] uppercase tracking-widest text-text-muted hover:text-brand hover:border-brand/30 transition-all shadow-sm">Refine</button>
              <button onclick="approvePost('{next_post_id}')" class="flex-1 py-4 bg-brand rounded-2xl text-white font-bold text-[10px] uppercase tracking-widest shadow-xl shadow-brand/20 hover:scale-[1.02] transition-all">Approve</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Weekly Pulse & Operations -->
      <div class="lg:col-span-2 space-y-10">
        <div class="space-y-6">
            <div class="flex justify-between items-center">
              <h2 class="text-[10px] font-bold uppercase tracking-[0.4em] text-text-muted">Guidance Plan</h2>
              <a href="/app/calendar" class="text-[8px] font-bold uppercase tracking-widest text-brand hover:text-accent transition-colors flex items-center gap-2 px-3 py-1.5 bg-brand/5 rounded-lg border border-brand/5">
                Full Plan 
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M17 8l4 4m0 0l-4 4m4-4H3"></path></svg>
              </a>
            </div>
            
            <div class="hidden md:block glass bg-white overflow-hidden border-brand/5 p-8 rounded-[2rem] shadow-sm">
              <div class="grid grid-cols-7 gap-2 mb-4">
                {calendar_headers}
              </div>
              <div class="grid grid-cols-7 gap-2">
                {calendar_days}
              </div>
              <div class="mt-8 flex items-center justify-center gap-8 border-t border-brand/5 pt-6">
                  <div class="flex items-center gap-2">
                      <div class="w-2 h-2 rounded-full bg-brand"></div>
                      <span class="text-[8px] font-bold uppercase tracking-widest text-text-muted">Reminders Planned</span>
                  </div>
                  <div class="flex items-center gap-2 opacity-30">
                      <div class="w-2 h-2 rounded-full bg-brand/10"></div>
                      <span class="text-[8px] font-bold uppercase tracking-widest text-text-muted">Studio Idle</span>
                  </div>
              </div>
            </div>
        </div>

        <!-- Reflection Feed -->
        <!-- Reflection Feed Sections -->
        <div class="space-y-16">
            {dashboard_feed_sections}
        </div>

      </div>
    </div>
"""

SELECT_ACCOUNT_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><title>Connect Instagram · Sabeel Studio</title>
<style>body{margin:0;background:#f7f8f0;color:#143e31;font:16px/1.5 system-ui}main{max-width:520px;margin:6vh auto;padding:24px}h1{font:36px/1.15 Georgia;margin:28px 0 14px}p{color:#52665c}.account{display:flex;gap:14px;align-items:center;padding:18px;border:1px solid #c8d2c5;border-radius:14px;background:white;margin:12px 0;cursor:pointer}.account input{width:22px;height:22px;accent-color:#143e31;flex-shrink:0}.account span{overflow-wrap:anywhere}.account small{display:block;color:#647366}button,.back{display:block;width:100%;min-height:48px;margin:14px 0;padding:14px;border-radius:26px;font:inherit;font-weight:650;box-sizing:border-box;text-align:center}button{background:#143e31;color:white;border:0;cursor:pointer}button:disabled{opacity:.5;cursor:default}[hidden]{display:none!important}.back.primary{background:#143e31;color:white}.back{color:#143e31;background:transparent;border:1px solid #c8d2c5;text-decoration:none}#status{padding:14px 0;min-height:24px}#status.error{color:#963d2d}small{font-size:14px}:focus-visible{outline:3px solid #a76c22;outline-offset:4px}</style></head>
<body><main><strong>Sabeel Studio</strong><h1 id="connection-heading">Choose your Instagram accounts</h1><p id="connection-intro">Select the accounts you want to connect. Existing accounts can be reconnected to refresh access.</p>
<div id="status" role="status" aria-live="polite">Loading your accounts…</div><div id="account-grid"></div>
<button id="continue-btn" type="button" disabled>Connect selected accounts</button>
<a class="back" href="/app">Back to your workspace</a><a id="restart-link" class="back" href="/auth/instagram/login">Start connection again</a>
<small>Your existing accounts and posts stay in place. Nothing will be published by connecting an account.</small></main>
<script src="/static/instagram-connect.js?v=2" defer></script></body></html>"""

ONBOARDING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
  <meta name="theme-color" content="#020617" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <title>Onboarding | Sabeel</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; background: #F8F6F2; color: #1A1A1A; }
    .brand-bg { background: radial-gradient(circle at top right, #0F3D2E, #F8F6F2); }
    .glass { background: rgba(255, 255, 255, 0.8); backdrop-filter: blur(20px); border: 1px solid rgba(15, 61, 46, 0.1); }
    .step-dot.active { background: #0F3D2E; transform: scale(1.2); }
    .step-dot.complete { background: #C9A96E; }
  </style>
</head>
<body class="brand-bg min-h-screen p-4 md:p-6 flex flex-col md:items-center justify-center">
  <div class="max-w-2xl w-full flex-1 md:flex-none flex flex-col justify-center py-6 md:py-0">
    <!-- Progress -->
    <div class="flex justify-center gap-4 mb-8 md:mb-12" id="progress-dots">
      <div class="step-dot active w-3 h-3 rounded-full bg-brand/20 transition-all"></div>
      <div class="step-dot w-3 h-3 rounded-full bg-brand/20 transition-all"></div>
      <div class="step-dot w-3 h-3 rounded-full bg-brand/20 transition-all"></div>
      <div class="step-dot w-3 h-3 rounded-full bg-brand/20 transition-all"></div>
    </div>

    <div class="glass rounded-[2rem] md:rounded-[3rem] p-6 md:p-12 space-y-8 md:space-y-10 min-h-[80vh] md:min-h-[500px] flex flex-col justify-between" id="onboarding-card">
      <!-- Content injected by JS -->
    </div>
  </div>

  <script>
    let currentStep = 1;
    let onboardingData = {
      orgName: '',
      contentMode: 'manual',
      autoTopic: '',
      autoTime: '09:00'
    };

    function updateProgress() {
      const dots = document.querySelectorAll('.step-dot');
      dots.forEach((dot, i) => {
        dot.className = 'step-dot w-3 h-3 rounded-full transition-all';
        if (i + 1 < currentStep) dot.classList.add('complete', 'bg-accent');
        else if (i + 1 === currentStep) dot.classList.add('active', 'bg-brand', 'scale-125');
        else dot.classList.add('bg-brand/10');
      });
    }

    function renderStep() {
      const card = document.getElementById('onboarding-card');
      updateProgress();

      if (currentStep === 1) {
        card.innerHTML = `
          <div class="space-y-6">
            <h2 class="text-sm font-black text-indigo-400 uppercase tracking-widest">Step 1</h2>
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
            <h2 class="text-sm font-black text-indigo-400 uppercase tracking-widest">Step 2</h2>
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
      } else if (currentStep === 3) {
        card.innerHTML = `
          <div class="space-y-6">
            <h2 class="text-sm font-black text-indigo-400 uppercase tracking-widest">Step 3</h2>
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
      } else if (currentStep === 4) {
        card.innerHTML = `
          <div class="space-y-6">
            <h2 class="text-sm font-black text-indigo-400 uppercase tracking-widest">Step 4</h2>
            <h3 class="text-4xl font-black italic text-white tracking-tight">System Ready.</h3>
            <div class="bg-indigo-500/10 border border-indigo-500/20 p-8 rounded-[2rem] space-y-4">
               <div class="flex justify-between text-[10px] font-black uppercase tracking-widest"><span>Workspace</span> <span class="text-white">${onboardingData.orgName}</span></div>
               <div class="flex justify-between text-[10px] font-black uppercase tracking-widest"><span>Intelligence</span> <span class="text-white">${onboardingData.contentMode}</span></div>
               <div class="flex justify-between text-[10px] font-black uppercase tracking-widest"><span>Schedule</span> <span class="text-white">Daily @ ${onboardingData.autoTime}</span></div>
            </div>
            <p class="text-text-muted text-center text-xs font-medium">Click finish to activate your content engine.</p>
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
      if (document.getElementById('autoTopic')) onboardingData.autoTopic = document.getElementById('autoTopic').value;
      if (document.getElementById('autoTime')) onboardingData.autoTime = document.getElementById('autoTime').value;
    }

    function nextStep() {
      syncData();
      if (currentStep < 4) {
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

def get_active_context(db: Session, user: User, org_id: int):
    """Read account context without changing a disconnected/disabled account."""
    accs = db.query(IGAccount).filter(IGAccount.org_id == org_id).order_by(IGAccount.id).all()
    if not accs:
        return None, [], False
    active_acc = next((a for a in accs if a.active), None)
    # Keep saved posts visible for a disconnected account, but never restore access
    # or activation as a side effect of opening a page.
    return active_acc or accs[0], accs, bool(active_acc and active_acc.access_token)


def render_app_page(title, content, user, org, active_tab, db: Session = None, extras=None):
    from .ui_assets import APP_LAYOUT_HTML, STUDIO_COMPONENTS_HTML, STUDIO_SCRIPTS_JS, CONNECT_INSTAGRAM_MODAL_HTML
    from app.models import IGAccount
    
    # Active state map
    active_map = {
        "dashboard": "",
        "calendar": "",
        "automations": "",
        "library": "",
        "media": ""
    }
    if active_tab in active_map:
        active_map[active_tab] = "active"

    # --- Fetch Accounts for Switcher ---
    switcher_html = ""
    active_acc = None
    fallback_avatar_base = "https://ui-avatars.com/api/?background=0F3D2E&color=fff&bold=true&name="
    if db and user:
        # Studio saves and publishes only within the active workspace.
        accs = db.query(IGAccount).filter(IGAccount.org_id == org.id).order_by(IGAccount.active.desc()).all()
        
        active_acc = next((a for a in accs if a.active), accs[0] if accs else None)
        
        if accs:
            acc_list_items = ""
            for a in accs:
                is_active = active_acc and a.id == active_acc.id
                active_indicator = '<div class="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>' if is_active else ""
                
                safe_name = a.username or "Studio"
                acc_avatar = a.profile_picture_url if (a.profile_picture_url and "http" in a.profile_picture_url) else f"{fallback_avatar_base}{safe_name}"
                
                acc_list_items += f"""
                <div onclick="setActiveAccount('{a.id}')" class="flex items-center justify-between p-3 rounded-xl hover:bg-brand/5 cursor-pointer transition-all group">
                    <div class="flex items-center gap-3">
                        <img src="{acc_avatar}" onerror="this.src='{fallback_avatar_base}{safe_name}'" class="w-8 h-8 rounded-full border border-brand/10 shadow-sm object-cover">
                        <div class="flex flex-col">
                            <span class="text-[11px] font-black text-brand group-hover:translate-x-0.5 transition-transform">@{a.username}</span>
                            <span class="text-[9px] font-bold text-brand/30 uppercase tracking-widest leading-none">{(a.name[:15] + '...') if a.name and len(a.name) > 15 else (a.name or 'Sabeel Platform')}</span>
                        </div>
                    </div>
                    {active_indicator}
                </div>
                """
            
            active_avatar = active_acc.profile_picture_url if (active_acc and active_acc.profile_picture_url and "http" in active_acc.profile_picture_url) else f"{fallback_avatar_base}{active_acc.username if active_acc else 'Studio'}"
            switcher_html = f"""
            <div class="relative inline-block text-left" id="accountSwitcherRoot" style="z-index: 99999;">
                <button onclick="toggleAccountSwitcher(event)" type="button" id="switcherToggleButton" class="relative flex items-center gap-3 p-2 pr-4 bg-white border border-brand/10 rounded-2xl transition-all shadow-sm group hover:border-brand/30">
                    <div class="relative">
                        <img src="{active_avatar}" onerror="this.src='{fallback_avatar_base}{active_acc.username if active_acc else 'Studio'}'" class="w-9 h-9 rounded-full border-2 border-brand/5 shadow-inner object-cover bg-brand/5">
                        <div class="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-500 border-2 border-white rounded-full"></div>
                    </div>
                    <div class="hidden md:flex flex-col items-start pr-2">
                        <span class="text-[10px] font-black text-brand tracking-tight">@{active_acc.username if active_acc else 'Studio'}</span>
                        <span class="text-[8px] font-bold text-brand/30 uppercase tracking-widest">Active Platform</span>
                    </div>
                    <svg class="w-3.5 h-3.5 text-brand/30 group-hover:text-brand/60 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
                </button>

                <div id="accountSwitcherDropdown" class="hidden absolute right-0 mt-3 w-72 bg-white border border-brand/5 rounded-3xl shadow-2xl z-[9000] p-3 animate-in fade-in zoom-in-95 duration-200">
                    <div class="px-3 py-2 text-[9px] font-black text-text-muted uppercase tracking-[0.2em] mb-2">Connected Platforms</div>
                    <div class="space-y-1.5">
                        {acc_list_items}
                    </div>
                    <div class="mt-4 pt-4 border-t border-brand/5">
                        <div class="flex items-center gap-2">
                            <button onclick="window.location.href='/auth/instagram/login'" class="flex-1 flex items-center gap-3 p-3 rounded-xl hover:bg-brand/5 transition-all group">
                                <div class="w-8 h-8 rounded-full bg-brand/5 flex items-center justify-center text-brand/40 group-hover:bg-brand/10 group-hover:text-brand transition-all">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
                                </div>
                                <span class="text-[11px] font-black text-brand italic">Connect Another</span>
                            </button>
                            <button onclick="event.stopPropagation(); document.getElementById('dropdownIgHelp').classList.toggle('hidden')" class="w-8 h-8 shrink-0 rounded-full bg-brand/5 text-brand/50 hover:text-brand hover:bg-brand/10 flex items-center justify-center text-[10px] font-black transition-all focus:outline-none" title="Connection Requirements">?</button>
                        </div>
                        
                        <!-- Help Popover -->
                        <div id="dropdownIgHelp" class="hidden mt-3 bg-brand/5 border border-brand/10 rounded-xl p-3.5 relative transition-all animate-in fade-in zoom-in-95 duration-200">
                            <button onclick="event.stopPropagation(); document.getElementById('dropdownIgHelp').classList.add('hidden')" class="absolute top-2.5 right-2.5 text-brand/40 hover:text-brand transition-colors focus:outline-none">
                                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                            </button>
                            <h4 class="text-[9px] font-bold text-brand uppercase tracking-widest mb-2 border-b border-brand/5 pb-2">Requirements</h4>
                            <ul class="text-[9px] text-brand/70 space-y-1.5 list-none p-0 m-0 font-medium leading-tight">
                                <li class="flex items-start gap-1.5"><span class="text-accent shrink-0">→</span><span>Need <strong>Business/Creator</strong> IG.</span></li>
                                <li class="flex items-start gap-1.5"><span class="text-accent shrink-0">→</span><span>Must link a <strong>Facebook Page</strong>.</span></li>
                                <li class="flex items-start gap-1.5"><span class="text-accent shrink-0">→</span><span>Grant <strong>all permissions</strong>.</span></li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
            """
            
            # Global account options for modals
            account_options = "".join([f'<option value="{a.id}" {"selected" if active_acc and a.id == active_acc.id else ""}>@{a.username} ({a.name or "Sabeel Studio"})</option>' for a in accs])
        else:
            switcher_html = f"""
            <div class="flex items-center gap-2 relative z-[9999]">
                <button onclick="window.location.href='/auth/instagram/login'" type="button" class="relative flex items-center gap-3 p-2 pr-4 bg-brand/[0.03] hover:bg-brand/[0.06] border border-brand/10 rounded-2xl transition-all group">
                    <div class="w-9 h-9 rounded-full bg-brand/5 flex items-center justify-center text-brand/30 group-hover:text-brand transition-colors">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
                    </div>
                    <div class="flex flex-col items-start pr-2">
                        <span class="text-[10px] font-black text-brand tracking-tight">Connect Account</span>
                        <span class="text-[8px] font-bold text-brand/30 uppercase tracking-widest">Setup Platform</span>
                    </div>
                </button>
                <button onclick="document.getElementById('headerIgHelp').classList.toggle('hidden')" class="w-8 h-8 shrink-0 rounded-full bg-brand/5 text-brand/50 hover:text-brand hover:bg-brand/10 flex items-center justify-center text-[10px] font-black transition-all focus:outline-none" title="Connection Requirements">?</button>
                
                <!-- Help Popover -->
                <div id="headerIgHelp" class="hidden absolute top-full right-0 mt-3 w-64 bg-white border border-brand/5 rounded-2xl shadow-2xl p-4 text-left animate-in fade-in zoom-in-95 duration-200">
                    <button onclick="document.getElementById('headerIgHelp').classList.add('hidden')" class="absolute top-3 right-3 text-brand/40 hover:text-brand transition-colors focus:outline-none">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                    </button>
                    <h4 class="text-[10px] font-bold text-brand uppercase tracking-widest mb-2 border-b border-brand/5 pb-2">Connection Rules</h4>
                    <ul class="text-[9px] text-brand/70 space-y-2 list-none p-0 m-0 font-medium leading-tight">
                        <li class="flex items-start gap-1.5"><span class="text-accent shrink-0">→</span><span>Must be a <strong>Business</strong> or <strong>Creator</strong> IG account.</span></li>
                        <li class="flex items-start gap-1.5"><span class="text-accent shrink-0">→</span><span>Must be linked to a <strong>Facebook Page</strong>.</span></li>
                        <li class="flex items-start gap-1.5"><span class="text-accent shrink-0">→</span><span>Grant <strong>all requested permissions</strong> in the Meta popup.</span></li>
                    </ul>
                </div>
            </div>
            """
            account_options = '<option value="">No accounts connected</option>'

    return APP_LAYOUT_HTML.format(
        title=title,
        content=content,
        user_name=user.name or user.email,
        org_name=org.name if org else "Personal Workspace",
        admin_link=('<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin</a>' if user.is_superadmin else ""),
        active_dashboard=active_map["dashboard"],
        active_calendar=active_map["calendar"],
        active_automations=active_map["automations"],
        active_library=active_map["library"],
        active_media=active_map["media"],
        studio_modal=STUDIO_COMPONENTS_HTML.replace("{account_options}", account_options).replace("{workspace_key}", f"{org.id}:{user.id}"),
        studio_js=STUDIO_SCRIPTS_JS + '<script src="/static/creator-workspace.js?v=4"></script>',
        connected_account_info=(extras.get("connected_account_info", "") if extras else ""),
        connect_instagram_modal=CONNECT_INSTAGRAM_MODAL_HTML,
        navbar_account_switcher=switcher_html,
        account_options=account_options,
        extra_js=(extras.get("extra_js", "") if extras else ""),
        org_id=str(org.id if org else 0)
    )

@router.get("/app", response_class=HTMLResponse)
async def app_dashboard_page(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    view: str = "home",
):
    # REDIRECT LOGIC
    # REMOVED FORCED ONBOARDING REDIRECT

    # Fetch User's Active Org
    org_id = user.active_org_id
    if not org_id:
        membership = db.query(OrgMember).filter(OrgMember.user_id == user.id).first()
        if not membership:
            # Create a default org if missing to prevent total breakage
            new_org = Org(name=f"{user.name or 'User'}'s Workspace")
            db.add(new_org)
            db.flush()
            membership = OrgMember(org_id=new_org.id, user_id=user.id, role="owner")
            db.add(membership)
            org_id = new_org.id
            user.active_org_id = org_id
            db.commit()
        else:
            org_id = membership.org_id
            user.active_org_id = org_id
            db.commit()

    org = db.query(Org).filter(Org.id == org_id).first()
    
    # --- Unified Account Context ---
    active_acc, all_accs, is_connected = get_active_context(db, user, org_id)
    active_acc_id = active_acc.id if active_acc else 0
    
    from .creator_workspace import render_creator_workspace
    posts = db.query(Post).filter(Post.org_id == org_id, Post.ig_account_id == active_acc_id).order_by(Post.created_at.desc()).limit(30).all()
    return render_app_page(title={"home": "Home", "posts": "Posts", "you": "Your workspace"}.get(view, "Home"),
        content=render_creator_workspace(user, org, posts, active_acc, view, all_accs), user=user, org=org,
        active_tab="dashboard", db=db)

@router.get("/app/select-account", response_class=HTMLResponse)
@router.get("/select-account", response_class=HTMLResponse)
async def app_select_account_page(
    user: User = Depends(require_user)
):
    """Renders the clean account selection page after OAuth discovery."""
    return HTMLResponse(content=SELECT_ACCOUNT_HTML, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

def _calendar_post_time(post, display_tz):
    value = post.published_time if post.status == "published" and post.published_time else (post.scheduled_time or post.published_time)
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(display_tz)


@router.get("/app/calendar", response_class=HTMLResponse)
async def app_calendar_page(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    tz: str = "UTC",
):
    try:
        display_tz = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid calendar timezone") from None
    # REMOVED FORCED ONBOARDING REDIRECT
    org = db.query(Org).filter(Org.id == user.active_org_id).first()
    
    # --- Unified Account Context ---
    active_acc, all_accs, is_connected = get_active_context(db, user, org.id)
    active_acc_id = active_acc.id if active_acc else 0

    admin_link = '<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin</a>' if user.is_superadmin else ""
    
    today = datetime.now(display_tz)
    year = today.year
    month = today.month
    
    # Get calendar days
    cal = calendar.Calendar(firstweekday=6) # Sunday start
    month_days = cal.monthdayscalendar(year, month)
    
    # Range for query
    month_start = datetime(year, month, 1, tzinfo=display_tz)
    if month == 12:
        month_end = datetime(year + 1, 1, 1, tzinfo=display_tz)
    else:
        month_end = datetime(year, month + 1, 1, tzinfo=display_tz)

    # Query UTC instants for this local calendar month, including DST changes.
    query_start = month_start.astimezone(timezone.utc)
    query_end = month_end.astimezone(timezone.utc)
        
    # Filter by Active Account
    posts = db.query(Post).filter(
        Post.org_id == org.id,
        Post.ig_account_id == active_acc_id,
        or_(
            and_(Post.scheduled_time >= query_start, Post.scheduled_time < query_end),
            and_(Post.published_time >= query_start, Post.published_time < query_end)
        )
    ).all()
    
    # Map posts to days
    post_map = {}
    display_times = {p.id: _calendar_post_time(p, display_tz) for p in posts}
    for p in posts:
        dt = display_times[p.id]
        if not dt or (dt.year, dt.month) != (year, month): continue
        day = dt.day
        if day not in post_map: post_map[day] = []
        post_map[day].append(p)
        
    calendar_html = ""
    headers = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    for h in headers:
        calendar_html += f'<div class="py-5 text-[9px] font-black uppercase tracking-[0.4em] text-brand/40 text-center">{h}</div>'
        
    for week in month_days:
        for day in week:
            if day == 0:
                # Ghost cell for padding days (softer)
                calendar_html += '<div class="min-h-[140px] rounded-3xl bg-brand/[0.01] opacity-50"></div>'
            else:
                day_posts = post_map.get(day, [])
                posts_html = ""
                for dp in day_posts[:2]: # Show max 2 to keep it clean
                    # Determine type
                    cap = dp.caption or ""
                    p_type = "REFLECTION"
                    if any(x in cap for x in ["Surah", "Verse", "Ayah", "Quran"]): p_type = "QURAN"
                    elif any(x in cap for x in ["Hadith", "Prophet", "Sahih", "Bukhari", "Muslim"]): p_type = "HADITH"
                    elif "Story" in cap: p_type = "STORY"
                    
                    # Status logic (Stronger Visuals)
                    if dp.status == "published": 
                        status_badge = "bg-emerald-100 text-emerald-800"
                        border_color = "border-l-emerald-500"
                        display_status = "Shared"
                    elif dp.status == "scheduled": 
                        status_badge = "bg-brand text-white shadow-md shadow-brand/20"
                        border_color = "border-l-brand"
                        display_status = "Planned"
                    elif dp.status in {"failed", "publishing", "publish_unknown", "publish_partial"}:
                        status_badge = "bg-rose-100 text-rose-800"
                        border_color = "border-l-rose-500"
                        display_status = {"publishing":"Publishing", "publish_unknown":"Check outcome", "publish_partial":"Partly shared"}.get(dp.status,"Failed")
                    else: # draft
                        status_badge = "bg-amber-100 text-amber-800"
                        border_color = "border-l-amber-400"
                        display_status = "Draft"
                    
                    # Preview (approx 8-12 words in 40-50 chars)
                    preview = (cap[:45] + "...") if len(cap) > 45 else (cap if cap else "Suggested Reminder")
                    
                    time_display = ""
                    if dp.status == "scheduled" and dp.scheduled_time:
                        t_str = display_times[dp.id].strftime("%I:%M %p").lstrip("0").lower()
                        time_display = f'<div class="text-[8px] font-black text-brand/40 uppercase tracking-widest mb-1.5 flex items-center gap-1.5"><svg class="w-3 h-3 text-brand/30" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>{t_str}</div>'
                    
                    # Ensure scheduled_time string is safe for JS
                    sched_time_str = dp.scheduled_time.isoformat() if dp.scheduled_time else ""

                    posts_html += f"""
                    <div class="p-4 rounded-[1.25rem] bg-white border border-brand/5 border-l-[4px] {border_color} flex flex-col gap-1 overflow-hidden group/post cursor-pointer hover:shadow-md hover:-translate-y-1 hover:border-brand/10 transition-all shadow-sm" 
                         onclick="openEditPostModal('{dp.id}', {html.escape(json.dumps(dp.caption or 'Suggested Reminder'))}, '{sched_time_str}', {html.escape(json.dumps(dp.status))})">
                        <div class="flex justify-between items-start mb-1">
                            {time_display}
                            <span class="px-2 py-1 rounded-md {status_badge} text-[7px] font-black uppercase tracking-[0.2em] leading-none ml-auto">{display_status}</span>
                        </div>
                        <div class="text-[7px] font-black uppercase tracking-[0.25em] text-accent/50 mb-0.5">{p_type}</div>
                        <p class="text-[11px] font-bold text-brand leading-snug line-clamp-2 transition-colors">"{html.escape(preview)}"</p>
                    </div>
                    """
                
                is_today = (day == today.day and month == today.month and year == today.year)
                has_posts = len(day_posts) > 0
                
                # Hierarchy styling
                if is_today:
                    cell_class = "border-brand bg-brand/[0.03] shadow-md ring-4 ring-brand/5"
                    day_color = "text-brand"
                elif has_posts:
                    cell_class = "border-brand/10 bg-white shadow-sm hover:border-brand/30"
                    day_color = "text-brand"
                else:
                    cell_class = "border-transparent bg-brand/[0.01] hover:bg-white hover:border-brand/10 hover:shadow-sm group/empty"
                    day_color = "text-brand/30 group-hover/empty:text-brand/60"
                
                # Empty state content
                empty_html = '<div class="flex-1 flex items-center justify-center opacity-0 group-hover/empty:opacity-[0.04] transition-opacity"><svg class="w-8 h-8 text-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6v6m0 0v6m0-6h6m-6 0H6" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></div>'
                
                calendar_html += f"""
                <div class="min-h-[160px] card border rounded-[2rem] p-4 flex flex-col gap-3 transition-all duration-300 {cell_class}">
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-sm font-black {day_color} transition-colors">{day}</span>
                        { '<span class="px-2 py-1 bg-emerald-500 text-white rounded-lg text-[8px] font-black uppercase tracking-widest shadow-lg shadow-emerald-500/20">Today</span>' if is_today else '' }
                    </div>
                    <div class="flex flex-col gap-3 flex-1">
                        {posts_html or empty_html}
                    </div>
                </div>
                """

    # Map posts to a list of HTML snippets
    scheduled_posts_html = []
    # Upcoming reminders (from now onwards)
    upcoming_posts = [p for p in posts if p.status == "scheduled" and display_times[p.id] and display_times[p.id] >= today]
    upcoming_posts.sort(key=lambda x: display_times[x.id])
    
    for p in upcoming_posts[:7]:
        caption = p.caption[:60] if p.caption else "Untitled Post"
        time_str = display_times[p.id].strftime("%b %d, %I:%M %p").lstrip("0").replace(" 0", " ")
        sched_time_str = p.scheduled_time.isoformat() if p.scheduled_time else ""
        scheduled_posts_html.append(f"""
            <div class="flex items-start gap-4 p-4 bg-brand/[0.01] rounded-2xl border border-transparent hover:bg-white hover:shadow-sm hover:border-brand/10 transition-all duration-300 group cursor-pointer" onclick="openEditPostModal('{p.id}', {html.escape(json.dumps(p.caption or 'Suggested Reminder'))}, '{sched_time_str}', {html.escape(json.dumps(p.status))})">
                <div class="w-2 h-2 mt-2 rounded-full bg-brand shrink-0 group-hover:scale-125 transition-transform shadow-sm shadow-brand/30"></div>
                <div class="flex flex-col gap-1.5 min-w-0">
                    <div class="text-[9px] font-black text-brand/40 uppercase tracking-[0.2em]">{time_str}</div>
                    <span class="text-[11px] font-bold text-brand line-clamp-2 leading-relaxed">"{html.escape(caption)}..."</span>
                </div>
            </div>
        """)
        
    scheduled_list_html = "".join(scheduled_posts_html)
    if not scheduled_list_html:
        scheduled_list_html = """
            <div class="py-16 flex flex-col items-center space-y-4 text-center">
                <div class="w-16 h-16 bg-brand/5 rounded-2xl flex items-center justify-center text-brand/20 mb-2">
                    <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
                </div>
                <div class="text-[10px] font-black uppercase tracking-[0.4em] text-brand/20">No Recent Activity</div>
                <p class="text-xs text-text-muted opacity-50 font-medium">Schedule your first piece of guidance to see it here.</p>
            </div>
        """

    content = f"""
    <div class="space-y-8 pb-20 max-w-[1600px] mx-auto">
        <!-- Header -->
        <div class="flex flex-col md:flex-row justify-between items-start md:items-end gap-6 border-b border-brand/5 pb-6">
            <div>
                <h1 class="heading-premium text-4xl tracking-tight">Content Planner</h1>
                <p class="text-premium-muted mt-2 text-sm">Organize and schedule your upcoming guidance</p>
                <p class="text-premium-muted mt-1 text-xs">Times shown in {html.escape(tz)}</p>
            </div>
            <div class="flex items-center gap-4">
                <div class="hidden md:flex items-center gap-6 px-5 py-3 bg-white border border-brand/5 rounded-2xl shadow-sm">
                    <div class="flex items-center gap-2"><div class="w-2.5 h-2.5 rounded bg-brand"></div><span class="text-[8px] font-bold uppercase tracking-widest text-text-muted">Planned</span></div>
                    <div class="flex items-center gap-2"><div class="w-2.5 h-2.5 rounded bg-emerald-400"></div><span class="text-[8px] font-bold uppercase tracking-widest text-text-muted">Shared</span></div>
                    <div class="flex items-center gap-2"><div class="w-2.5 h-2.5 rounded bg-amber-400"></div><span class="text-[8px] font-bold uppercase tracking-widest text-text-muted">Draft</span></div>
                </div>
                <button onclick="openNewPostModal()" class="px-6 py-4 bg-brand text-white rounded-2xl font-black text-[10px] uppercase tracking-[0.2em] shadow-lg shadow-brand/20 hover:bg-brand-hover hover:-translate-y-0.5 transition-all flex items-center gap-3">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
                    New Share
                </button>
            </div>
        </div>
        
        <div class="grid grid-cols-1 xl:grid-cols-4 gap-8 items-start">
            <!-- Main Calendar Area -->
            <div class="cw-calendar-grid xl:col-span-3 space-y-4">
                <!-- Calendar Grid -->
                <div class="grid grid-cols-7 gap-3">
                    {calendar_html}
                </div>
            </div>
            
            <!-- Side Agenda Panel -->
            <div class="cw-calendar-agenda xl:col-span-1 space-y-6 sticky top-8">
                <div class="bg-white rounded-[2rem] border border-brand/5 p-6 shadow-sm flex flex-col min-h-[500px]">
                    <div class="flex items-center justify-between mb-8">
                        <div class="flex items-center gap-3">
                            <div class="w-8 h-8 rounded-xl bg-brand/5 flex items-center justify-center text-brand">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg>
                            </div>
                            <h3 class="text-sm font-black text-brand tracking-tight uppercase tracking-widest">Agenda</h3>
                        </div>
                    </div>
                    
                    <div class="flex flex-col gap-2 flex-1">
                        {scheduled_list_html if len(scheduled_posts_html) > 0 else f'<div class="flex-1 flex flex-col items-center justify-center text-center opacity-40 py-10"><svg class="w-8 h-8 mb-4 text-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg><span class="text-[9px] font-black uppercase tracking-widest">No upcoming<br>reminders</span></div>'}
                    </div>
                </div>
            </div>
        </div>
    </div>
    """
    
    account_options = "".join([f'<option value="{a.id}">@{a.username} ({a.name or "Sabeel Studio"})</option>' for a in all_accs])
    if not all_accs:
        account_options = '<option value="">No accounts connected</option>'
        
    connected_account_info = f"""
        <div class="flex items-center gap-2 border-l border-brand/10 pl-4 ml-2">
            <span class="text-brand font-black text-[10px] tracking-tighter uppercase">@{active_acc.username if active_acc else "Account"}</span>
            <button onclick="disconnectMetaAccount()" class="hover:text-rose-500 transition-colors opacity-60 hover:opacity-100">
                <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
    """ if is_connected else '<div class="flex items-center gap-2 border-l border-brand/10 pl-4 ml-2 opacity-60 italic"><span>No account linked</span></div>'

    return render_app_page(
        title="Planning",
        content=content,
        user=user,
        org=org,
        active_tab="calendar",
        db=db,
        extras={
            "connected_account_info": connected_account_info,
            "extra_js": f'<script>window.hasConnectedInstagram = {"true" if is_connected else "false"};</script>'
        }
    )

@router.get("/app/automations", response_class=HTMLResponse)
async def app_automations_page(
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    # REMOVED FORCED ONBOARDING REDIRECT
    org = db.query(Org).filter(Org.id == user.active_org_id).first()
    
    # --- Unified Account Context ---
    active_acc, all_accs, is_connected = get_active_context(db, user, org.id)
    active_acc_id = active_acc.id if active_acc else 0

    admin_link = '<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin</a>' if user.is_superadmin else ""
    
    # Filter by Active Account
    autos = db.query(TopicAutomation).filter(
        TopicAutomation.org_id == user.active_org_id,
        TopicAutomation.ig_account_id == active_acc_id
    ).all()
    
    # Fetch accounts for "New Automation" selection
    account_options = "".join([f'<option value="{a.id}">@{a.username} ({a.name})</option>' for a in all_accs])
    if not all_accs:
        account_options = '<option value="">No accounts connected</option>'
    
    autos_html = ""
    for a in autos:
        status_color = "text-emerald-600" if a.enabled else "text-rose-600"
        status_bg = "bg-emerald-50" if a.enabled else "bg-rose-50"
        status_label = "Active" if a.enabled else "Paused"
        
        mode_icon = '<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>'
        if a.content_seed_mode == 'auto_library':
            mode_icon = '<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>'
        
        # Consistent, safe JSON mapping for frontend configuration modal
        edit_data_json = html.escape(json.dumps({
            "id": a.id,
            "name": a.name,
            "topic_prompt": a.topic_prompt,
            "topic_pool": a.topic_pool or [],
            "library_topic_slug": a.library_topic_slug,
            "content_seed_mode": a.content_seed_mode,
            "content_seed_text": a.content_seed_text,
            "post_time_local": a.post_time_local,
            "posts_per_day": a.posts_per_day,
            "post_spacing_hours": a.post_spacing_hours,
            "content_provider_scope": a.content_provider_scope,
            "pillars": a.pillars,
            "cadence": a.cadence,
            "custom_days": a.custom_days or [],
            "source_mode": a.source_mode,
            "tone_style": a.tone_style,
            "verification_mode": a.verification_mode,
            "style_dna_id": a.style_dna_id,
            "style_dna_pool": a.style_dna_pool or [],
            "approval_mode": a.approval_mode,
            "ig_account_id": a.ig_account_id
        }), quote=True)

        # Analytics Injection
        last_run_str = a.last_run_at.strftime("%b %d, %H:%M") if a.last_run_at else "Never"
        status_pulse = "bg-emerald-500" if (a.last_run_at and not a.last_error) else ("bg-rose-500 animate-pulse" if a.last_error else "bg-brand/20")
        perf_label = "Healthy" if (a.last_run_at and not a.last_error) else ("Critical Error" if a.last_error else "Awaiting Launch")
        perf_color = "text-emerald-600" if (a.last_run_at and not a.last_error) else ("text-rose-600 font-black italic" if a.last_error else "text-brand/40")

        autos_html += f"""
        <div class="card p-8 md:p-10 bg-white border-brand/5 flex flex-col md:flex-row justify-between items-start md:items-center gap-10 group relative overflow-hidden transition-all">
          <div class="absolute top-0 right-0 w-32 h-32 bg-brand/[0.01] rounded-full -mr-16 -mt-16 group-hover:scale-150 transition-transform duration-700"></div>
          
          <div class="flex items-start md:items-center gap-8 flex-1 min-w-0 relative">
            <div class="w-16 h-16 rounded-[1.5rem] bg-brand/5 flex items-center justify-center text-brand shrink-0 border border-brand/10 shadow-inner group-hover:bg-brand/10 transition-colors">
              {mode_icon}
            </div>
            <div class="min-w-0 space-y-3">
              <div class="flex items-center gap-4">
                <h3 class="text-2xl font-black text-brand tracking-tight italic">{a.name}</h3>
                <button onclick="toggleAuto(event, {a.id}, {str(not a.enabled).lower()})" class="px-3 py-1.5 {status_bg} {status_color} rounded-xl text-[9px] font-black uppercase tracking-[0.2em] border border-brand/5 hover:scale-105 transition-all">{status_label}</button>
                
                <div class="flex items-center gap-2 px-3 py-1 bg-brand/[0.02] border border-brand/5 rounded-full">
                    <span class="w-1.5 h-1.5 rounded-full {status_pulse}"></span>
                    <span class="text-[9px] font-bold uppercase tracking-widest {perf_color}">{perf_label}</span>
                </div>
              </div>
              <p class="text-[13px] text-text-muted font-medium line-clamp-1 italic max-w-xl opacity-80 group-hover:opacity-100 transition-opacity">"{a.topic_prompt}"</p>
              
              <div class="flex flex-wrap gap-8 pt-2">
                <div class="flex items-center gap-6">
                  <div class="flex flex-col">
                      <span class="badge-premium !text-[7px] mb-1">Strategy</span>
                      <div class="flex items-center gap-2">
                          <div class="w-1.5 h-1.5 rounded-full bg-accent"></div>
                          <span class="text-[11px] font-black text-brand uppercase tracking-widest">{ 'Sacred Grounding' if a.content_seed_mode == 'auto_library' else 'Guided Reflection' }</span>
                      </div>
                  </div>
                  <div class="flex flex-col border-l border-brand/5 pl-6">
                      <span class="badge-premium !text-[7px] mb-1">Schedule</span>
                      <div class="flex items-center gap-2 text-brand">
                          <svg class="w-3 h-3 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
                          <span class="text-[11px] font-black uppercase tracking-widest">{a.posts_per_day}x {a.cadence.capitalize() if a.cadence else 'Daily'} @ {a.post_time_local or '09:00'}</span>
                      </div>
                  </div>
                  <div class="flex flex-col border-l border-brand/5 pl-6">
                      <span class="badge-premium !text-[7px] mb-1">Last Sync</span>
                      <span class="text-[10px] font-black text-brand/40 uppercase tracking-widest">{last_run_str}</span>
                  </div>
                </div>
              </div>
              {f'<p class="text-[9px] text-rose-500 font-bold italic mt-2 border-l-2 border-rose-100 pl-3">Error Log: {a.last_error[:100]}...</p>' if a.last_error else ''}
            </div>
          </div>

          <div class="flex items-center gap-4 w-full md:w-auto relative border-t md:border-t-0 border-brand/[0.04] pt-8 md:pt-0">
            <button onclick="showEditModal({edit_data_json})" class="flex-1 md:flex-none px-8 py-5 bg-white border border-brand/10 rounded-2xl font-black text-[10px] uppercase tracking-[0.2em] text-brand/60 hover:text-brand hover:border-brand/30 hover:bg-brand/[0.02] transition-all">Configure</button>
            <button onclick="runNow(event, {a.id})" class="flex-1 md:flex-none px-8 py-5 bg-brand rounded-2xl text-white font-black text-[10px] uppercase tracking-[0.2em] shadow-2xl shadow-brand/20 hover:scale-[1.02] transition-all">Run once</button>
            <button onclick="deleteAutomation({a.id})" class="p-5 bg-rose-50/50 text-rose-500 border border-rose-100 rounded-2xl hover:bg-rose-500 hover:text-white transition-all shadow-sm" title="Delete Strategy">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
            </button>
          </div>
        </div>
        """

    empty_state_html = """
        <div class="card p-24 bg-white border-brand/10 border-dashed border-2 bg-brand/[0.01] text-center flex flex-col items-center justify-center space-y-10">
            <div class="w-24 h-24 rounded-[2.5rem] bg-brand/5 flex items-center justify-center text-brand border border-brand/10 shadow-inner">
              <svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"/></svg>
            </div>
            <div class="space-y-4">
              <h3 class="heading-premium text-4xl">Start your first <span class="text-accent">Reminder Stream</span></h3>
              <p class="text-premium-muted max-w-sm mx-auto">Establish the rhythm of your automated guidance cycles.</p>
            </div>
            <button onclick="showNewAutoModal()" class="px-12 py-5 bg-brand text-white rounded-2xl font-black text-[11px] uppercase tracking-[0.3em] shadow-2xl shadow-brand/40 hover:bg-brand-hover hover:scale-[1.02] transition-all">Start Guidance Stream</button>
        </div>
    """
    
    content = """
    <div class="space-y-12">
      <div class="flex justify-between items-end">
        <div>
        <h1 class="heading-premium text-5xl">Growth</h1>
        <p class="text-premium-muted mt-2">Guidance Refinement Plans</p>
      </div>
      <button onclick="showNewAutoModal()" class="hidden md:flex px-10 py-5 bg-brand rounded-2xl font-black text-[11px] uppercase tracking-[0.3em] text-white shadow-2xl shadow-brand/30 hover:translate-y-[-2px] transition-all items-center gap-3">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
          Initialize Plan
      </button>
      </div>

      <div class="space-y-8">
        {autos_html}
      </div>
    </div>
    """

    account_options = "".join([f'<option value="{a.id}">@{a.username} ({a.name or "Sabeel Studio"})</option>' for a in all_accs])
    if not all_accs:
        account_options = '<option value="">No accounts connected</option>'
        
    connected_account_info = f"""
        <div class="flex items-center gap-2 border-l border-brand/10 pl-4 ml-2">
            <span class="text-brand font-black text-[10px] tracking-tighter uppercase">@{active_acc.username if active_acc else "Account"}</span>
            <button onclick="disconnectMetaAccount()" class="hover:text-rose-500 transition-colors opacity-60 hover:opacity-100">
                <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
    """ if is_connected else '<div class="flex items-center gap-2 border-l border-brand/10 pl-4 ml-2 opacity-60 italic"><span>No account linked</span></div>'

    return render_app_page(
        title="Reminder Streams",
        content=content.replace("{autos_html}", autos_html or empty_state_html),
        user=user,
        org=org,
        active_tab="automations",
        db=db,
        extras={
            "connected_account_info": connected_account_info,
            "extra_js": f'<script>window.hasConnectedInstagram = {"true" if is_connected else "false"};</script>'
        }
    )

@router.get("/app/media", response_class=HTMLResponse)
async def app_media_page(
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    # REMOVED FORCED ONBOARDING REDIRECT
    org = db.query(Org).filter(Org.id == user.active_org_id).first()
    
    # --- Unified Account Context ---
    active_acc, all_accs, is_connected = get_active_context(db, user, org.id)
    active_acc_id = active_acc.id if active_acc else 0

    admin_link = '<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin</a>' if user.is_superadmin else ""
    
    # Filter Media by Active Account
    from app.models import MediaAsset
    media = db.query(MediaAsset).filter(
        MediaAsset.org_id == org.id,
        MediaAsset.ig_account_id == active_acc_id
    ).all()
    
    media_html = ""
    for m in media:
        media_html += f"""
        <div class="card overflow-hidden group/media relative">
            <img src="{m.url}" class="w-full h-48 object-cover">
            <div class="absolute inset-0 bg-brand/40 opacity-0 group-hover/media:opacity-100 transition-opacity flex items-center justify-center gap-3">
                <button onclick="window.open('{m.url}', '_blank')" class="p-3 bg-white text-brand rounded-full hover:scale-110 transition-transform shadow-xl">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" stroke-width="2"/><path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" stroke-width="2"/></svg>
                </button>
            </div>
        </div>
        """
    
    content = f"""
    <div class="space-y-12">
      <div class="flex justify-between items-end">
        <div>
          <h1 class="heading-premium text-5xl">Visuals</h1>
          <p class="text-premium-muted mt-2">Visual Presence & Aesthetic Studio</p>
        </div>
        <div class="flex gap-4">
            <button onclick="document.getElementById('mediaUploadInput').click()" class="px-10 py-5 bg-brand text-white rounded-2xl font-black text-[11px] uppercase tracking-[0.2em] shadow-2xl shadow-brand/20 hover:bg-brand-hover hover:scale-[1.02] transition-all flex items-center gap-3">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
                Ingest Visuals
            </button>
        </div>
      </div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {media_html}
        </div>
        
        {'''
        <div id="mediaEmptyState" class="card p-24 rounded-[3rem] border-brand/10 border-dashed border-2 bg-brand/[0.01] text-center flex flex-col items-center justify-center space-y-10 relative overflow-hidden">
            <div class="absolute top-0 right-0 w-64 h-64 bg-brand/[0.01] rounded-full -mr-32 -mt-32"></div>
            <div class="w-24 h-24 rounded-[2.5rem] bg-brand/5 flex items-center justify-center border border-brand/10 shadow-inner">
              <svg class="w-12 h-12 text-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"/></svg>
            </div>
            <div class="space-y-4 relative">
              <h3 class="heading-premium text-4xl">Your Visual <span class="text-accent">Foundation</span></h3>
              <p class="text-premium-muted max-w-sm mx-auto">Visual assets manifested through your guidance cycles will be archived here.</p>
            </div>
            <div class="badge-premium relative">No manifested assets found</div>
        </div>
        ''' if not media_html else ""}
    </div>
    """
    
    account_options = "".join([f'<option value="{a.id}">@{a.username} ({a.name or "Sabeel Studio"})</option>' for a in all_accs])
    if not all_accs:
        account_options = '<option value="">No accounts connected</option>'
        
    connected_account_info = f"""
        <div class="flex items-center gap-2 border-l border-brand/10 pl-4 ml-2">
            <span class="text-brand font-black text-[10px] tracking-tighter uppercase">@{active_acc.username if active_acc else "Account"}</span>
            <button onclick="disconnectMetaAccount()" class="hover:text-rose-500 transition-colors opacity-60 hover:opacity-100">
                <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
    """ if is_connected else '<div class="flex items-center gap-2 border-l border-brand/10 pl-4 ml-2 opacity-60 italic"><span>No account linked</span></div>'

    return render_app_page(
        title="Visual Library",
        content=content,
        user=user,
        org=org,
        active_tab="media",
        db=db,
        extras={
            "connected_account_info": connected_account_info,
            "extra_js": f'<script>window.hasConnectedInstagram = {"true" if is_connected else "false"};</script>'
        }
    )

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(user: User = Depends(require_user)):
    # REMOVED FORCED ONBOARDING REDIRECT
    return ONBOARDING_HTML
@router.patch("/auth/dismiss-getting-started")
async def dismiss_getting_started(
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    user.dismissed_getting_started = True
    db.commit()
    return {"status": "success"}

from pydantic import BaseModel
class OnboardingFinalize(BaseModel):
    orgName: str
    igUserId: str | None = None
    igAccessToken: str | None = None
    contentMode: str
    autoTopic: str
    autoTime: str

@router.post("/api/onboarding/finalize")
async def finalize_onboarding(
    payload: OnboardingFinalize,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_org_id)
):
    if payload.igUserId or payload.igAccessToken:
        raise HTTPException(400, "Connect Instagram through Meta before choosing an account.")
    # 1. Update only the authorized workspace
    org = db.query(Org).filter(Org.id == org_id).first()
    if not org:
        raise HTTPException(404, "Workspace not found")
    else:
        if payload.orgName: org.name = payload.orgName

    # 2. Use an existing OAuth-connected account only
    ig_acc = db.query(IGAccount).filter(IGAccount.org_id == org.id).first()
    
    # 3. Create Automation (Use existing or create new)
    auto = db.query(TopicAutomation).filter(TopicAutomation.org_id == org.id).first()
    if not auto and ig_acc:
        auto = TopicAutomation(
            org_id=org.id,
            ig_account_id=ig_acc.id,
            name="Daily Intelligence Feed",
            topic_prompt=payload.autoTopic or "Daily wisdom and news relevant to our niche.",
            source_mode=payload.contentMode if payload.contentMode != "auto_library" else "none",
            content_seed_mode="auto_library" if payload.contentMode == "auto_library" else "none",
            post_time_local=payload.autoTime or "09:00",
            enabled=False, # Creator must deliberately enable the finished plan.
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
    db.commit()

    return {"status": "success"}

class RefineRequest(BaseModel):
    text: str
    type: str

@router.post("/api/ai/refine")
def api_refine_content(
    payload: RefineRequest,
    user: User = Depends(require_user),
    org_id: int = Depends(get_current_org_id)
):
    from app.services.llm import refine_caption
    from app.services.text_provider import TextGenerationError
    try:
        refined = refine_caption(payload.text, payload.type)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except TextGenerationError as error:
        raise HTTPException(status_code=503, detail=str(error))
    return {"refined": refined}
