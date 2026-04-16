# Copyright (c) 2026 Mohammed Hassan. All rights reserved.
# Proprietary and confidential. Unauthorized copying, modification, distribution, or use is prohibited.

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
from pydantic import BaseModel
import json, calendar, html
from datetime import datetime, timedelta, timezone

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
            Today's Content
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
        <div class="space-y-6">
          <h2 class="text-[10px] font-bold uppercase tracking-[0.4em] text-text-muted">Reflection Feed</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {recent_posts}
            </div>
        </div>
      </div>
    </div>

    <!-- Edit Post Modal (Refinement) -->
    <div id="editPostModal" class="fixed inset-0 bg-brand/40 backdrop-blur-xl z-[200] hidden flex items-center justify-center p-6 animate-in fade-in duration-300">
      <div class="glass max-w-2xl w-full p-8 md:p-12 rounded-[3rem] border border-brand/10 shadow-2xl space-y-8 bg-white max-h-[90vh] overflow-y-auto">
        <div class="flex justify-between items-start">
            <div>
                <h2 class="text-3xl font-bold text-brand tracking-tight">Improve Your <span class="text-accent">Message</span></h2>
                <p class="text-[10px] font-bold text-text-muted uppercase tracking-[0.2em] mt-1">Polish your message before it goes live</p>
            </div>
            <button onclick="closeEditPostModal()" class="w-10 h-10 rounded-2xl bg-brand/5 flex items-center justify-center text-text-muted hover:bg-brand/10 hover:text-brand transition-all">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
            </button>
        </div>

        <input type="hidden" id="editPostId">
        
        <div class="space-y-6">
            <div class="space-y-3">
                <label class="text-[10px] font-bold uppercase tracking-[0.3em] text-brand ml-1">Your Message</label>
                <textarea id="editPostCaption" rows="8" class="w-full bg-cream/50 border border-brand/10 rounded-[2rem] px-8 py-8 text-sm text-brand outline-none focus:ring-2 focus:ring-brand leading-relaxed font-medium italic"></textarea>
            </div>

            <!-- AI Assist Toolbar -->
            <div class="space-y-3">
                <label class="text-[9px] font-bold uppercase tracking-[0.2em] text-text-muted ml-1 italic">AI Enhancements</label>
                <div class="flex flex-wrap gap-2">
                    <button onclick="refinePostAI('emotional')" class="refine-ai-btn px-4 py-2.5 bg-brand/5 border border-brand/5 rounded-xl text-[9px] font-black uppercase tracking-widest text-brand hover:bg-brand hover:text-white transition-all transition-colors flex items-center gap-2">
                        ✨ Emotional
                    </button>
                    <button onclick="refinePostAI('shorter')" class="refine-ai-btn px-4 py-2.5 bg-brand/5 border border-brand/5 rounded-xl text-[9px] font-black uppercase tracking-widest text-brand hover:bg-brand hover:text-white transition-all transition-colors flex items-center gap-2">
                        📏 Shorter
                    </button>
                    <button onclick="refinePostAI('ayah')" class="refine-ai-btn px-4 py-2.5 bg-brand/5 border border-brand/5 rounded-xl text-[9px] font-black uppercase tracking-widest text-brand hover:bg-brand hover:text-white transition-all transition-colors flex items-center gap-2">
                        📖 Add Ayah
                    </button>
                    <button onclick="refinePostAI('hadith')" class="refine-ai-btn px-4 py-2.5 bg-brand/5 border border-brand/5 rounded-xl text-[9px] font-black uppercase tracking-widest text-brand hover:bg-brand hover:text-white transition-all transition-colors flex items-center gap-2">
                        📜 Add Hadith
                    </button>
                    <button onclick="refinePostAI('clarity')" class="refine-ai-btn px-4 py-2.5 bg-brand/5 border border-brand/5 rounded-xl text-[9px] font-black uppercase tracking-widest text-brand hover:bg-brand hover:text-white transition-all transition-colors flex items-center gap-2">
                        ⚖️ Clarity
                    </button>
                </div>
            </div>

            <div id="editPostActions" class="grid grid-cols-2 lg:grid-cols-4 gap-4 pt-6">
                <button onclick="closeEditPostModal()" class="py-5 bg-white border border-brand/10 rounded-2xl font-bold text-[11px] uppercase tracking-[0.2em] text-brand hover:bg-brand/5 transition-all">Cancel</button>
                <button id="savePostBtn" onclick="savePostEdit()" class="py-5 bg-brand/5 border border-brand/10 rounded-2xl font-bold text-[11px] uppercase tracking-[0.2em] text-brand hover:bg-brand hover:text-white transition-all">Save Changes</button>
                <button id="postNowBtn" onclick="publishPostNow()" class="col-span-2 py-5 bg-brand rounded-2xl font-bold text-[11px] uppercase tracking-[0.2em] text-white shadow-2xl shadow-brand/40 hover:bg-brand-hover transition-all flex items-center justify-center gap-3">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                    Share Now
                </button>
            </div>

            <!-- Delete Confirmation Area (Hidden by default) -->
            <div id="deleteConfirmActions" class="hidden flex flex-col gap-4 pt-6 animate-in slide-in-from-top-2">
                <div class="p-6 bg-rose-50 border border-rose-100 rounded-3xl text-center">
                    <p class="text-[10px] font-bold text-rose-600 uppercase tracking-widest">Are you absolutely sure?</p>
                </div>
                <div class="flex gap-4">
                    <button onclick="hideDeleteConfirm()" class="flex-1 py-4 bg-white border border-brand/10 rounded-2xl font-bold text-[10px] uppercase tracking-widest text-brand">No, Keep it</button>
                    <button id="confirmDeleteBtn" onclick="deletePost()" class="flex-1 py-4 bg-rose-600 rounded-2xl font-bold text-[10px] uppercase tracking-widest text-white shadow-xl shadow-rose-200">Yes, Delete</button>
                </div>
            </div>
            
            <div class="flex justify-center pt-2">
                <button onclick="showDeleteConfirm()" class="text-[9px] font-bold uppercase tracking-widest text-rose-500/50 hover:text-rose-500 transition-colors">Discard this piece of reminder</button>
            </div>
        </div>
      </div>
    </div>
"""

SELECT_ACCOUNT_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
  <title>Choose Account | Sabeel Studio</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            brand: '#0F3D2E',
            'brand-hover': '#0A2D22',
            accent: '#C9A96E',
            cream: '#F8F6F2',
            neutral: '#F8F8F6'
          }
        }
      }
    }
  </script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; background-color: #F8F6F2; color: #1A1A1A; }
    .animate-in { animation: fade-in 0.6s cubic-bezier(0.16, 1, 0.3, 1); }
    @keyframes fade-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
    .card-shadow { box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03); }
    .card-shadow-hover { box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.05), 0 10px 10px -5px rgba(0, 0, 0, 0.02); }
    .selected-card { border-color: #0F3D2E !important; background-color: rgba(15, 61, 46, 0.02) !important; box-shadow: 0 10px 15px -3px rgba(15, 61, 46, 0.1) !important; }
  </style>
</head>
<body class="min-h-screen flex flex-col items-center justify-center p-6 md:p-10 relative bg-cream">
    <!-- Top-Right Cancel -->
    <a href="/app" class="absolute top-8 right-8 text-[11px] font-bold uppercase tracking-widest text-gray-400 hover:text-brand transition-colors flex items-center gap-2 group">
        Cancel
        <svg class="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
    </a>

    <div class="max-w-[560px] w-full space-y-10 animate-in">
        <!-- Header -->
        <div class="space-y-4">
            <div class="w-10 h-10 bg-brand/5 rounded-xl flex items-center justify-center text-brand">
                <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.058-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.791-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.209-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/></svg>
            </div>
            <div class="space-y-1">
                <h1 class="text-3xl font-extrabold text-brand tracking-tight">Connect Your Meta Account</h1>
                <p class="text-[13px] font-medium text-gray-500">Pick which professional accounts to authorize for Sabeel Studio</p>
            </div>
        </div>

        <!-- Account List -->
        <div id="account-grid" class="space-y-4">
            <!-- Loading Skeletons -->
            <div class="bg-white border border-gray-100 rounded-2xl p-5 flex items-center justify-between card-shadow animate-pulse">
                <div class="flex items-center gap-4">
                    <div class="w-12 h-12 bg-gray-50 rounded-full"></div>
                    <div class="space-y-2">
                        <div class="h-4 bg-gray-50 rounded w-32"></div>
                        <div class="h-3 bg-gray-50 rounded w-20"></div>
                    </div>
                </div>
                <div class="h-9 w-24 bg-gray-50 rounded-lg"></div>
            </div>
        </div>

        <!-- Continue Action -->
        <div id="libraryContainer" class="flex flex-col h-full bg-[#F8F6F2]">
        <!-- UI VERSION: 5.2 (ULTRA-HARDENED) -->
            <button id="continue-btn" onclick="saveSelected()" class="w-full py-4 bg-brand text-white rounded-2xl font-bold text-[13px] uppercase tracking-widest hover:bg-brand-hover transition-all shadow-xl shadow-brand/10 hover:shadow-brand/20 disabled:opacity-50 disabled:cursor-not-allowed">
                Continue to Dashboard
            </button>
            <p class="text-[10px] text-gray-400 text-center mt-4">You can always add more accounts later in Settings</p>
        </div>

        <div id="empty-state" class="hidden text-center py-16 space-y-6 bg-white rounded-3xl border border-gray-100 card-shadow">
            <div class="w-14 h-14 bg-rose-50 rounded-2xl flex items-center justify-center text-rose-300 mx-auto">!</div>
            <div class="space-y-2 px-8">
                <h3 class="text-lg font-bold text-brand">No Accounts Found</h3>
                <p class="text-[12px] text-gray-500 max-w-xs mx-auto leading-relaxed">Ensure your Instagram account is set to 'Professional' and linked to a Facebook Page.</p>
            </div>
            <button onclick="window.location.href='/app'" class="px-8 py-3 bg-brand text-white rounded-xl font-bold text-[11px] uppercase tracking-widest hover:bg-brand-hover transition-all">Go Back</button>
        </div>

        <div class="pt-6 flex items-center justify-between text-gray-400">
            <div class="flex items-center gap-2">
                <span class="w-1.5 h-1.5 rounded-full bg-brand"></span>
                <span class="text-[10px] font-bold uppercase tracking-widest">Enhanced Discovery</span>
            </div>
            <div class="text-[9px] font-medium">Step 2 of 2</div>
        </div>
    </div>

<script>
    let discoveredAccounts = [];
    let connectedIds = [];
    let selectedIds = [];

    // Fix Facebook redirect hash issue
    if (window.location.hash === '#_=_') {
        history.replaceState(null, null, window.location.pathname);
    }

    async function initialize() {
        try {
            const [availRes, connRes] = await Promise.all([
                fetch('/accounts/available'),
                fetch('/accounts/connected')
            ]);
            
            discoveredAccounts = await availRes.json();
            connectedIds = await connRes.json();

            // Auto-skip logic: 1 account available and NOT connected
            if (discoveredAccounts.length === 1 && !connectedIds.includes(discoveredAccounts[0].ig_user_id)) {
                selectedIds = [discoveredAccounts[0].ig_user_id];
                await saveSelected();
                return;
            }

            render();
        } catch (e) {
            console.error(e);
            alert('Session expired. Please reconnect Meta.');
        }
    }

    function toggleSelect(igId) {
        if (connectedIds.includes(igId)) return;
        
        if (selectedIds.includes(igId)) {
            selectedIds = selectedIds.filter(id => id !== igId);
        } else {
            selectedIds.push(igId);
        }
        render();
    }

    function render() {
        const grid = document.getElementById('account-grid');
        const emptyState = document.getElementById('empty-state');
        const cta = document.getElementById('cta-container');
        const continueBtn = document.getElementById('continue-btn');
        
        if (!discoveredAccounts || discoveredAccounts.length === 0) {
            emptyState.classList.remove('hidden');
            grid.innerHTML = '';
            cta.classList.add('hidden');
            return;
        }

        cta.classList.remove('hidden');
        continueBtn.disabled = selectedIds.length === 0;

        grid.innerHTML = discoveredAccounts.map(acc => {
            const isConnected = connectedIds.includes(acc.ig_user_id);
            const isSelected = selectedIds.includes(acc.ig_user_id);
            
            let btnLabel = "Connect";
            let btnClass = "bg-brand text-white hover:bg-brand-hover";
            let cardClass = "";

            if (isConnected) {
                btnLabel = `<span class="flex items-center gap-1.5"><svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg> Connected</span>`;
                btnClass = "bg-gray-100 text-gray-400 cursor-not-allowed";
                cardClass = "opacity-75 grayscale-[0.5]";
            } else if (isSelected) {
                btnLabel = "Selected";
                btnClass = "bg-brand text-white ring-4 ring-brand/10";
                cardClass = "selected-card";
            }

            return `
                <div onclick="toggleSelect('${acc.ig_user_id}')" class="bg-white border border-gray-100 rounded-2xl p-5 flex items-center justify-between card-shadow hover:card-shadow-hover hover:-translate-y-0.5 transition-all duration-300 cursor-pointer group ${cardClass}">
                    <div class="flex items-center gap-4">
                        <div class="relative">
                            <img src="${acc.profile_picture_url || 'https://ui-avatars.com/api/?name=' + acc.username}" class="w-12 h-12 rounded-full object-cover">
                            ${isConnected ? `
                                <div class="absolute -bottom-0.5 -right-0.5 w-5 h-5 bg-emerald-500 border-2 border-white rounded-full flex items-center justify-center">
                                    <svg class="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
                                </div>
                            ` : `
                                <div class="absolute -bottom-0.5 -right-0.5 w-4 h-4 bg-gray-200 border-2 border-white rounded-full ${isSelected ? 'bg-brand' : ''}"></div>
                            `}
                        </div>
                        <div>
                            <div class="text-[14px] font-bold text-brand leading-none mb-1">@${acc.username}</div>
                            <div class="text-[11px] font-medium text-gray-400">${acc.name || acc.username}</div>
                        </div>
                    </div>
                    <button class="px-6 py-2.5 rounded-lg font-bold text-[11px] transition-all ${btnClass}">
                        ${btnLabel}
                    </button>
                </div>
            `;
        }).join('');
    }

    async function saveSelected() {
        if (selectedIds.length === 0) return;
        
        const btn = document.getElementById('continue-btn');
        btn.disabled = true;
        btn.innerHTML = `<span class="flex items-center justify-center gap-2"><svg class="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Persisting Connections...</span>`;
        
        const payload = selectedIds.map(id => {
            const acc = discoveredAccounts.find(a => a.ig_user_id === id);
            return { ig_user_id: id, page_id: acc.fb_page_id };
        });

        try {
            const res = await fetch('/accounts/select', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            if (res.ok) {
                window.location.href = '/app';
            } else {
                const data = await res.json();
                alert(data.detail || 'Failed to connect accounts');
                btn.disabled = false;
                btn.innerHTML = 'Continue to Dashboard';
            }
        } catch (e) {
            alert('Service unavailable. Please retry.');
            btn.disabled = false;
            btn.innerHTML = 'Continue to Dashboard';
        }
    }

    window.onload = initialize;
</script>
</body>
</html>
"""

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
    if db and org:
        accs = db.query(IGAccount).filter(IGAccount.org_id == org.id).order_by(IGAccount.active.desc()).all()
        active_acc = next((a for a in accs if a.active), accs[0] if accs else None)
        
        if accs:
            acc_list_items = ""
            for a in accs:
                is_active = a.id == (active_acc.id if active_acc else None)
                active_indicator = '<div class="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>' if is_active else ""
                
                acc_list_items += f"""
                <div onclick="setActiveAccount({a.id})" class="flex items-center justify-between p-3 rounded-xl hover:bg-brand/5 cursor-pointer transition-all group">
                    <div class="flex items-center gap-3">
                        <img src="{a.profile_picture_url or f'https://ui-avatars.com/api/?name={a.username}&background=0F3D2E&color=fff'}" class="w-8 h-8 rounded-full border border-brand/10 shadow-sm">
                        <div class="flex flex-col">
                            <span class="text-[11px] font-black text-brand group-hover:translate-x-0.5 transition-transform">@{a.username}</span>
                            <span class="text-[9px] font-bold text-brand/40 uppercase tracking-widest">{a.name[:15] + "..." if len(a.name) > 15 else a.name}</span>
                        </div>
                    </div>
                    {active_indicator}
                </div>
                """
            
            switcher_html = f"""
            <div class="relative inline-block text-left" id="accountSwitcherRoot">
                <button onclick="toggleAccountSwitcher(event)" class="flex items-center gap-3 p-2 pr-4 bg-white/60 hover:bg-white border border-brand/10 rounded-2xl transition-all shadow-sm group">
                    <div class="relative">
                        <img src="{active_acc.profile_picture_url or f'https://ui-avatars.com/api/?name={active_acc.username}&background=0F3D2E&color=fff'}" class="w-9 h-9 rounded-full border-2 border-brand/5 shadow-inner">
                        <div class="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-500 border-2 border-white rounded-full"></div>
                    </div>
                    <div class="hidden md:flex flex-col items-start pr-2">
                        <span class="text-[10px] font-black text-brand tracking-tight">@{active_acc.username}</span>
                        <span class="text-[8px] font-bold text-brand/30 uppercase tracking-widest">Active Platform</span>
                    </div>
                    <svg class="w-3.5 h-3.5 text-brand/30 group-hover:text-brand/60 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
                </button>
                
                <div id="accountSwitcherDropdown" class="hidden absolute left-0 mt-3 w-64 bg-white/95 backdrop-blur-xl border border-brand/10 rounded-[1.5rem] shadow-2xl p-3 z-[100] animate-in fade-in slide-in-from-top-2 duration-300">
                    <div class="px-3 py-2 mb-2 border-b border-brand/5">
                        <span class="text-[9px] font-black text-brand/30 uppercase tracking-[0.3em]">Switch Platform</span>
                    </div>
                    <div class="space-y-1 max-h-64 overflow-y-auto custom-scrollbar">
                        {acc_list_items}
                    </div>
                    <div class="mt-3 pt-3 border-t border-brand/5">
                        <button onclick="window.location.href='/auth/instagram/login'" class="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-brand/5 text-[10px] font-black text-brand/60 hover:text-brand transition-all uppercase tracking-widest">
                            <div class="w-8 h-8 rounded-full bg-brand/5 flex items-center justify-center">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
                            </div>
                            Connect Another
                        </button>
                    </div>
                </div>
            </div>
            """
        else:
            switcher_html = """
            <button onclick="window.location.href='/auth/instagram/login'" class="flex items-center gap-3 p-2 pr-6 bg-brand/[0.03] hover:bg-brand/5 border border-brand/10 rounded-2xl transition-all shadow-sm group">
                <div class="w-9 h-9 rounded-full bg-brand/5 flex items-center justify-center text-brand/30">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
                </div>
                <div class="flex flex-col items-start pr-2">
                    <span class="text-[10px] font-black text-brand tracking-tight">Connect Account</span>
                    <span class="text-[8px] font-bold text-brand/30 uppercase tracking-widest">Setup Platform</span>
                </div>
            </button>
            """

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
        studio_modal=STUDIO_COMPONENTS_HTML,
        studio_js=STUDIO_SCRIPTS_JS,
        connected_account_info=(extras.get("connected_account_info", "") if extras else ""),
        connect_instagram_modal=CONNECT_INSTAGRAM_MODAL_HTML,
        navbar_account_switcher=switcher_html,
        extra_js=(extras.get("extra_js", "") if extras else ""),
        org_id=str(org.id if org else 0)
    )

@router.get("/app", response_class=HTMLResponse)
async def app_dashboard_page(
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
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
    next_post_caption_json = "null"
    next_post_time_iso = ""
    next_post_actions_class = "hidden"
    
    if next_post:
        diff = next_post.scheduled_time - now_utc
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        next_post_countdown = f"{diff.days}d {hours}h {minutes}m"
        next_post_time = next_post.scheduled_time.strftime("%b %d, %H:%M")
        next_post_caption = next_post.caption or "No caption generated."
        
        next_post_id = str(next_post.id)
        next_post_caption_json = html.escape(json.dumps(next_post.caption or ""), quote=True)
        next_post_time_iso = next_post.scheduled_time.isoformat()
        next_post_actions_class = ""
        
        if next_post.media_url:
            next_post_media = f'<img src="{next_post.media_url}" class="w-full h-full object-cover">'

    # Content Pipeline (Next 7 Days)
    calendar_headers = ""
    calendar_days = ""
    today = datetime.now(timezone.utc)
    for i in range(7):
        day = today + timedelta(days=i)
        is_today = (i == 0)
        day_label = day.strftime("%a")
        
        calendar_headers += f'<div class="py-3 text-[9px] font-black text-center uppercase tracking-[0.3em] {"text-brand" if is_today else "text-text-muted/40"}">{day_label}</div>'
        
        # Count posts for this day
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        post_count = db.query(func.count(Post.id)).filter(
            Post.org_id == org_id,
            Post.scheduled_time >= day_start,
            Post.scheduled_time < day_end
        ).scalar() or 0
        
        state_html = ""
        if post_count > 0:
            state_html = f"""
            <div class="flex flex-col items-center gap-1.5">
                <div class="text-[14px] font-black text-brand">{post_count}</div>
                <div class="w-full h-1.5 rounded-full bg-brand shadow-sm shadow-brand/20"></div>
            </div>
            """
        else:
            state_html = f"""
            <div class="flex flex-col items-center gap-1.5 opacity-10">
                <div class="text-[14px] font-black text-brand">0</div>
                <div class="w-full h-1.5 rounded-full bg-brand/20"></div>
            </div>
            """
            
        calendar_days += f"""
        <div class="flex flex-col items-center justify-center p-3 rounded-2xl transition-all {"bg-brand/[0.03] border border-brand/5 shadow-inner" if is_today else "hover:bg-brand/[0.01]"}">
          <span class="text-[8px] font-black {"text-brand" if is_today else "text-text-muted/30"} uppercase tracking-widest mb-3">{day.day}</span>
          {state_html}
        </div>
        """

    # Intelligence Feed (Recent Content)
    posts = db.query(Post).filter(Post.org_id == org_id).order_by(Post.created_at.desc()).limit(6).all()
    recent_posts_html = ""
    for p in posts:
        # Determine Type
        cap = p.caption or ""
        p_type = "REFLECTION"
        if any(x in cap for x in ["Surah", "Verse", "Ayah", "Quran"]): p_type = "QURAN"
        elif any(x in cap for x in ["Hadith", "Prophet", "Sahih", "Bukhari", "Muslim"]): p_type = "HADITH"
        
        status_color = "text-text-muted"
        status_bg = "bg-brand/5"
        status_label = "Reflection Draft" if p.status == "draft" else p.status.capitalize()
        
        if p.status == "published": 
            status_color = "text-emerald-600"
            status_bg = "bg-emerald-50"
            status_label = "Shared"
        elif p.status == "scheduled": 
            status_color = "text-brand"
            status_bg = "bg-brand/10 shadow-sm"
            status_label = "Planned"
        elif p.status == "ready":
            status_color = "text-accent"
            status_bg = "bg-accent/10"
            status_label = "Review Ready"
        
        caption_json = html.escape(json.dumps(p.caption or ""), quote=True)
        date_str = p.created_at.strftime("%b %d")
        
        approve_btn = ""
        if p.status in ["draft", "ready"]:
            approve_btn = f"""
                <button onclick="approvePost('{p.id}')" class="px-4 py-2 bg-brand/5 text-brand rounded-xl font-bold text-[8px] uppercase tracking-widest hover:bg-brand hover:text-white transition-all">Share Now</button>
            """

        recent_posts_html += f"""
        <div class="card p-6 bg-white border-brand/5 flex flex-col gap-6 group">
          <div class="flex items-start justify-between">
            <div class="flex items-center gap-4">
                <div class="w-12 h-12 rounded-2xl bg-cream overflow-hidden border border-brand/8 shrink-0 shadow-inner">
                    {f'<img src="{p.media_url}" class="w-full h-full object-cover">' if p.media_url else '<div class="w-full h-full flex items-center justify-center text-[8px] font-black text-brand/20 uppercase tracking-widest">NULL</div>'}
                </div>
                <div>
                   <div class="badge-premium mb-1">{p_type}</div>
                   <div class="px-2.5 py-1 {status_bg} {status_color} rounded-lg text-[7px] font-black uppercase tracking-[0.2em] inline-block border border-brand/5">{status_label}</div>
                </div>
            </div>
            <div class="text-[9px] font-black text-brand/20 uppercase tracking-[0.3em]">{date_str}</div>
          </div>

          <div class="space-y-4">
              <p class="text-[12px] font-bold text-brand/80 leading-relaxed line-clamp-3 italic group-hover:text-brand transition-colors">
                "{p.caption[:120] if p.caption else "Suggested Reminder"}"
              </p>
          </div>

          <div class="flex items-center gap-3 pt-4 border-t border-brand/[0.04]">
             <button onclick="openEditPostModal('{p.id}', {caption_json}, '{p.scheduled_time.isoformat() if p.scheduled_time else ''}')" class="flex-1 py-3 bg-white border border-brand/10 rounded-xl text-[9px] font-black uppercase tracking-[0.2em] text-brand/60 hover:text-brand hover:border-brand/30 transition-all">Refine</button>
             {approve_btn.replace('rounded-xl', 'rounded-xl border border-brand/5 py-3 flex-1').replace('text-[8px]', 'text-[9px]')}
             <button onclick="document.getElementById('editPostId').value='{p.id}'; showDeleteConfirm(); openEditPostModal('{p.id}', {caption_json})" class="p-3 text-rose-300 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition-all">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
             </button>
          </div>
        </div>
        """
    
    # Connection CTA for empty states
    connection_cta = ""
    if account_count == 0:
        connection_cta = f"""
        <div class="card p-16 text-center space-y-10 animate-in slide-in-from-bottom-6 duration-1000 border-dashed border-2 border-brand/10 bg-brand/[0.01]">
          <div class="w-24 h-24 bg-brand/5 rounded-[2.5rem] flex items-center justify-center text-brand mx-auto border border-brand/5 shadow-inner">
            <svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
          </div>
          <div class="space-y-4">
            <h3 class="heading-premium text-4xl">Connect <span class="text-accent">Instagram</span></h3>
            <p class="text-premium-muted max-w-lg mx-auto opacity-70">Your studio is ready to manifest. Link your Professional Meta account to begin automated guidance cycles.</p>
          </div>
          <button onclick="openConnectInstagramModal()" class="px-12 py-5 bg-brand rounded-2xl font-black text-[11px] uppercase tracking-[0.3em] text-white shadow-2xl shadow-brand/40 hover:bg-brand-hover hover:scale-[1.02] transition-all">Link Foundation Now</button>
        </div>
        """
    
    # Check if superadmin for admin link and prominent CTA
    admin_link = ""
    # --- GET STARTED CHECKLIST LOGIC ---
    automation_count = db.query(func.count(TopicAutomation.id)).filter(TopicAutomation.org_id == org_id).scalar() or 0
    primary_acc = db.query(IGAccount).filter(IGAccount.org_id == org_id).first()
    is_connected = primary_acc is not None
    
    # Update user flags if they have activity
    if weekly_post_count > 0 and not user.has_created_first_post:
        user.has_created_first_post = True
    if automation_count > 0 and not user.has_created_first_automation:
        user.has_created_first_automation = True
    if is_connected and not user.has_connected_instagram:
        user.has_connected_instagram = True
    
    # Connected account info for header
    if is_connected:
        connected_account_info = f"""
            <div class="flex items-center gap-2 border-l border-brand/10 pl-4 ml-2">
                <span class="text-brand font-black text-[10px] tracking-tighter uppercase">@{primary_acc.name}</span>
                <button onclick="disconnectMetaAccount()" class="hover:text-rose-500 transition-colors opacity-60 hover:opacity-100">
                    <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>
            <script>
                async function disconnectMetaAccount() {{
                    if (!confirm("Are you sure you want to disconnect this Instagram account?")) return;
                    const res = await fetch('/auth/instagram/disconnect', {{ method: 'POST' }});
                    const data = await res.json();
                    if (data.ok) window.location.reload();
                    else alert(data.error || "Failed to disconnect");
                }}
            </script>
        """
    else:
        connected_account_info = f"""
            <div class="flex items-center gap-2 border-l border-brand/10 pl-4 ml-2 opacity-60 italic">
                <span>No account linked</span>
            </div>
        """

    # Hide checklist if all items are complete
    all_done = user.has_created_first_post and user.has_created_first_automation and user.has_connected_instagram
    show_checklist = not user.dismissed_getting_started and not all_done
    
    get_started_card = ""
    if show_checklist:
        get_started_card = GET_STARTED_CARD_HTML.replace("{user_name}", user.name or user.email)

    if user.is_superadmin:
        admin_link = '<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin</a>'

    content = APP_DASHBOARD_CONTENT.replace("{connection_cta}", connection_cta)\
                                   .replace("{get_started_card}", get_started_card)\
                                   .replace("{connected_account_info}", connected_account_info)\
                                   .replace("{weekly_post_count}", str(weekly_post_count))\
                                   .replace("{account_count}", str(account_count))\
                                   .replace("{next_post_countdown}", next_post_countdown)\
                                   .replace("{next_post_time}", next_post_time)\
                                   .replace("{next_post_caption}", next_post_caption)\
                                   .replace("{next_post_media}", next_post_media)\
                                   .replace("{calendar_headers}", calendar_headers)\
                                   .replace("{calendar_days}", calendar_days)\
                                   .replace("{recent_posts}", recent_posts_html or '<div class="text-center py-6 text-[10px] font-black uppercase text-muted italic">No recent activity</div>')\
                                   .replace("{next_post_id}", str(next_post_id))\
                                   .replace("{next_post_caption_json}", str(next_post_caption_json))\
                                   .replace("{next_post_time_iso}", str(next_post_time_iso))\
                                   .replace("{next_post_actions_class}", next_post_actions_class)\
                                   .replace("{org_id}", str(org_id))
    
    # --- GET ACCOUNT OPTIONS FOR STUDIO MODAL ---
    accs = db.query(IGAccount).filter(IGAccount.org_id == org_id).all()
    account_options = "".join([f'<option value="{a.id}">@{a.username} ({a.name or "Sabeel Studio"})</option>' for a in accs])
    if not accs:
        account_options = '<option value="">No accounts connected</option>'

    return render_app_page(
        title="Dashboard",
        content=content,
        user=user,
        org=org,
        active_tab="dashboard",
        db=db,
        extras={
            "connected_account_info": connected_account_info,
            "extra_js": f'<script>window.hasConnectedInstagram = {"true" if is_connected else "false"};</script>'
        }
    )

@router.get("/app/select-account", response_class=HTMLResponse)
@router.get("/select-account", response_class=HTMLResponse)
async def app_select_account_page(
    user: User = Depends(require_user)
):
    """Renders the clean account selection page after OAuth discovery."""
    return HTMLResponse(content=SELECT_ACCOUNT_HTML)

@router.get("/app/calendar", response_class=HTMLResponse)
async def app_calendar_page(
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    # REMOVED FORCED ONBOARDING REDIRECT
    org = db.query(Org).filter(Org.id == user.active_org_id).first()
    admin_link = '<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin</a>' if user.is_superadmin else ""
    
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
        calendar_html += f'<div class="py-5 text-[9px] font-black uppercase tracking-[0.4em] text-brand/40 text-center">{h}</div>'
        
    for week in month_days:
        for day in week:
            if day == 0:
                calendar_html += '<div class="aspect-square bg-brand/[0.01] border border-brand/5 rounded-[2rem] opacity-20"></div>'
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
                    
                    # Status logic
                    status_class = "bg-brand/5 text-brand"
                    if dp.status == "published": status_class = "bg-emerald-50 text-emerald-600 border border-emerald-100/50"
                    elif dp.status == "draft": status_class = "bg-amber-50 text-amber-600 border border-amber-100/50"
                    else: status_class = "bg-brand/5 text-brand border border-brand/10"
                    
                    # Preview (approx 8-12 words in 40-50 chars)
                    preview = (cap[:45] + "...") if len(cap) > 45 else (cap if cap else "Suggested Reminder")
                    display_status = dp.status.capitalize()
                    if dp.status == "published": display_status = "Shared"
                    elif dp.status == "scheduled": display_status = "Planned"
                    elif dp.status == "draft": display_status = "Reflection Draft"
                    
                    posts_html += f"""
                    <div class="p-3 rounded-2xl border border-brand/5 bg-white/60 space-y-2 overflow-hidden group/post cursor-pointer hover:bg-white transition-all shadow-sm" onclick="openEditPostModal('{dp.id}', `{dp.caption}`, '{dp.scheduled_time.isoformat()}')">
                        <div class="flex justify-between items-center mb-1">
                            <span class="text-[7px] font-black uppercase tracking-[0.2em] text-accent/60 group-hover/post:text-accent transition-colors">{p_type}</span>
                            <span class="px-1.5 py-0.5 rounded-lg {status_class} text-[6px] font-black uppercase tracking-widest">{display_status}</span>
                        </div>
                        <p class="text-[9px] font-bold text-brand/60 group-hover/post:text-brand leading-snug line-clamp-2 italic transition-colors">"{preview}"</p>
                    </div>
                    """
                
                is_today = (day == today.day and month == today.month and year == today.year)
                today_cell_class = "border-brand/40 bg-brand/[0.03] shadow-inner" if is_today else "border-brand/5 hover:border-brand/10 bg-white"
                
                calendar_html += f"""
                <div class="min-h-[160px] card border rounded-[2rem] p-4 flex flex-col gap-3 transition-all {today_cell_class}">
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-xs font-black { 'text-brand' if is_today else 'text-brand/20' }">{day}</span>
                        { '<span class="badge-premium !text-emerald-500 !opacity-100">Today</span>' if is_today else '' }
                    </div>
                    <div class="flex flex-col gap-3">
                        {posts_html or '<div class="py-8 flex flex-col items-center justify-center opacity-10"><div class="text-[8px] font-black tracking-[0.4em] uppercase">Empty</div></div>'}
                    </div>
                </div>
                """

    # Map posts to a list of HTML snippets
    scheduled_posts_html = []
    for p in [p for p in posts if p.status == "scheduled"][:5]:
        caption = p.caption[:60] if p.caption else "Untitled Post"
        time_str = p.scheduled_time.strftime("%b %d, %H:%M")
        scheduled_posts_html.append(f"""
            <div class="flex items-center justify-between p-5 bg-brand/[0.02] rounded-2xl border border-brand/5 text-[11px] font-bold text-brand hover:bg-white transition-all group">
                <div class="flex items-center gap-4">
                    <div class="w-2 h-2 rounded-full bg-brand group-hover:scale-125 transition-transform"></div>
                    <span class="opacity-80 group-hover:opacity-100 transition-opacity">"{caption}..."</span>
                </div>
                <div class="badge-premium !text-[8px]">{time_str}</div>
            </div>
        """)
        
    scheduled_list_html = "".join(scheduled_posts_html)
    if not scheduled_list_html:
        scheduled_list_html = """
            <div class="py-16 flex flex-col items-center space-y-4 text-center">
                <div class="w-16 h-16 bg-brand/5 rounded-2xl flex items-center justify-center text-brand/20 mb-2">
                    <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
                </div>
                <div class="text-[10px] font-black uppercase tracking-[0.4em] text-brand/20">Empty Manifestation Log</div>
                <p class="text-xs text-text-muted opacity-50 font-medium">Schedule your first piece of guidance to see it here.</p>
            </div>
        """

    content = f"""
    <div class="space-y-12">
        <div class="flex justify-between items-end">
            <div>
                <h1 class="heading-premium text-5xl">Planning</h1>
                <p class="text-premium-muted mt-2">Content Foundation Scheduler</p>
            </div>
            <div class="flex gap-4">
                <button onclick="openNewPostModal()" class="px-10 py-5 bg-brand text-white rounded-2xl font-black text-[11px] uppercase tracking-[0.2em] shadow-2xl shadow-brand/20 hover:bg-brand-hover hover:scale-[1.02] transition-all flex items-center gap-3">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
                    Schedule Manifest
                </button>
            </div>
        </div>
        
        <div class="grid grid-cols-7 gap-4">
            {calendar_html}
        </div>
        
        <div class="card p-12 bg-white border border-brand/5 text-center flex flex-col items-center justify-center space-y-10 relative overflow-hidden">
            <div class="absolute top-0 left-0 w-64 h-64 bg-brand/[0.01] rounded-full -ml-32 -mt-32"></div>
            <div class="badge-premium relative">Upcoming Manifestations</div>
            <div class="space-y-4 w-full max-w-2xl relative">
                {scheduled_list_html}
            </div>
        </div>
    </div>
    """
    
    # --- COMMON LAYOUT DATA ---
    org_id = user.active_org_id if user.active_org_id else org.id
    accs = db.query(IGAccount).filter(IGAccount.org_id == org_id).all()
    primary_acc = accs[0] if accs else None
    is_connected = primary_acc is not None
    
    account_options = "".join([f'<option value="{a.id}">@{a.username} ({a.name or "Sabeel Studio"})</option>' for a in accs])
    if not accs:
        account_options = '<option value="">No accounts connected</option>'
        
    connected_account_info = f"""
        <div class="flex items-center gap-2 border-l border-brand/10 pl-4 ml-2">
            <span class="text-brand font-black text-[10px] tracking-tighter uppercase">@{primary_acc.username if primary_acc else "Account"}</span>
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
    admin_link = '<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin</a>' if user.is_superadmin else ""
    
    autos = db.query(TopicAutomation).filter(TopicAutomation.org_id == user.active_org_id).all()
    
    # Fetch accounts for "New Automation" selection
    accounts = db.query(IGAccount).filter(IGAccount.org_id == user.active_org_id).all()
    account_options = "".join([f'<option value="{a.id}">{a.name} (@{a.ig_user_id})</option>' for a in accounts])
    if not accounts:
        account_options = '<option value="">No accounts connected</option>'
    
    autos_html = ""
    for a in autos:
        status_color = "text-emerald-600" if a.enabled else "text-rose-600"
        status_bg = "bg-emerald-50" if a.enabled else "bg-rose-50"
        status_label = "Active" if a.enabled else "Paused"
        
        mode_icon = '<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>'
        if a.content_seed_mode == 'auto_library':
            mode_icon = '<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>'
        
        # Consistent, safe JSON escaping for HTML attribute
        edit_data_json = html.escape(json.dumps({
            "id": a.id,
            "name": a.name,
            "topic": a.topic_prompt,
            "library_topic_slug": a.library_topic_slug,
            "seed_mode": a.content_seed_mode,
            "seed_text": a.content_seed_text,
            "time": a.post_time_local,
            "content_provider_scope": a.content_provider_scope,
            "pillars": a.pillars,
            "frequency": a.frequency,
            "custom_days": a.custom_days,
            "source_mode": a.source_mode,
            "tone_style": a.tone_style,
            "verification_mode": a.verification_mode,
            "ig_account_id": a.ig_account_id
        }), quote=True)

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
              </div>
              <p class="text-[13px] text-text-muted font-medium line-clamp-1 italic max-w-xl opacity-80 group-hover:opacity-100 transition-opacity">"{a.topic_prompt}"</p>
              
              <div class="flex flex-wrap gap-8 pt-2">
                <div class="flex items-center gap-2">
                    <span class="badge-premium !text-[8px]">Strategy</span>
                    <span class="text-[11px] font-black text-brand uppercase tracking-wider">{ 'Verified Context' if a.content_seed_mode == 'auto_library' else 'Guided Script' }</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="badge-premium !text-[8px]">Pulse</span>
                    <span class="text-[11px] font-black text-brand uppercase tracking-wider">Daily @ {a.post_time_local or '09:00'}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="flex items-center gap-4 w-full md:w-auto relative border-t md:border-t-0 border-brand/[0.04] pt-8 md:pt-0">
            <button onclick="showEditModal({edit_data_json})" class="flex-1 md:flex-none px-8 py-5 bg-white border border-brand/10 rounded-2xl font-black text-[10px] uppercase tracking-[0.2em] text-brand/60 hover:text-brand hover:border-brand/30 hover:bg-brand/[0.02] transition-all">Configure</button>
            <button onclick="runNow(event, {a.id})" class="flex-1 md:flex-none px-8 py-5 bg-brand rounded-2xl text-white font-black text-[10px] uppercase tracking-[0.2em] shadow-2xl shadow-brand/20 hover:scale-[1.02] transition-all">Incarnate Now</button>
          </div>
        </div>
        """

    empty_state_html = """
        <div class="card p-24 bg-white border-brand/10 border-dashed border-2 bg-brand/[0.01] text-center flex flex-col items-center justify-center space-y-10">
            <div class="w-24 h-24 rounded-[2.5rem] bg-brand/5 flex items-center justify-center text-brand border border-brand/10 shadow-inner">
              <svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"/></svg>
            </div>
            <div class="space-y-4">
              <h3 class="heading-premium text-4xl">Start your first <span class="text-accent">Growth Plan</span></h3>
              <p class="text-premium-muted max-w-sm mx-auto">Establish the rhythm of your automated guidance cycles.</p>
            </div>
            <button onclick="showNewAutoModal()" class="px-12 py-5 bg-brand text-white rounded-2xl font-black text-[11px] uppercase tracking-[0.3em] shadow-2xl shadow-brand/40 hover:bg-brand-hover hover:scale-[1.02] transition-all">Begin Manifestation Plan</button>
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

    # --- COMMON LAYOUT DATA ---
    org_id = user.active_org_id if user.active_org_id else org.id
    accs = db.query(IGAccount).filter(IGAccount.org_id == org_id).all()
    primary_acc = accs[0] if accs else None
    is_connected = primary_acc is not None
    
    account_options = "".join([f'<option value="{a.id}">@{a.username} ({a.name or "Sabeel Studio"})</option>' for a in accs])
    if not accs:
        account_options = '<option value="">No accounts connected</option>'
        
    connected_account_info = f"""
        <div class="flex items-center gap-2 border-l border-brand/10 pl-4 ml-2">
            <span class="text-brand font-black text-[10px] tracking-tighter uppercase">@{primary_acc.username if primary_acc else "Account"}</span>
            <button onclick="disconnectMetaAccount()" class="hover:text-rose-500 transition-colors opacity-60 hover:opacity-100">
                <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
    """ if is_connected else '<div class="flex items-center gap-2 border-l border-brand/10 pl-4 ml-2 opacity-60 italic"><span>No account linked</span></div>'

    return render_app_page(
        title="Growth Plans",
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
    admin_link = '<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin</a>' if user.is_superadmin else ""
    
    content = """
    <div class="space-y-12">
      <div class="flex justify-between items-end">
        <div>
          <h1 class="heading-premium text-5xl">Visuals</h1>
          <p class="text-premium-muted mt-2">Visual Presence Manifestation Studio</p>
        </div>
        <div class="flex gap-4">
            <button onclick="document.getElementById('mediaUploadInput').click()" class="px-10 py-5 bg-brand text-white rounded-2xl font-black text-[11px] uppercase tracking-[0.2em] shadow-2xl shadow-brand/20 hover:bg-brand-hover hover:scale-[1.02] transition-all flex items-center gap-3">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
                Ingest Visuals
            </button>
        </div>
      </div>
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
    </div>
    """
    
    # --- COMMON LAYOUT DATA ---
    org_id = user.active_org_id if user.active_org_id else org.id
    accs = db.query(IGAccount).filter(IGAccount.org_id == org_id).all()
    primary_acc = accs[0] if accs else None
    is_connected = primary_acc is not None
    
    account_options = "".join([f'<option value="{a.id}">@{a.username} ({a.name or "Sabeel Studio"})</option>' for a in accs])
    if not accs:
        account_options = '<option value="">No accounts connected</option>'

    connected_account_info = f"""
        <div class="flex items-center gap-2 border-l border-brand/10 pl-4 ml-2">
            <span class="text-brand font-black text-[10px] tracking-tighter uppercase">@{primary_acc.username if primary_acc else "Account"}</span>
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
    db: Session = Depends(get_db)
):
    # 1. Ensure Org exists or create it
    org = db.query(Org).filter(Org.id == user.active_org_id).first()
    if not org:
        org = Org(name=payload.orgName or f"{user.name}'s Workspace")
        db.add(org)
        db.flush()
        membership = OrgMember(org_id=org.id, user_id=user.id, role="owner")
        db.add(membership)
        user.active_org_id = org.id
    else:
        if payload.orgName: org.name = payload.orgName

    # 2. Connect IG Account (Optional - though UI usually skips this now)
    ig_acc = db.query(IGAccount).filter(IGAccount.org_id == org.id).first()
    if not ig_acc and (payload.igUserId or payload.igAccessToken):
        ig_acc = IGAccount(
            org_id=org.id,
            name=f"IG: {payload.igUserId}" if payload.igUserId else "IG Account",
            ig_user_id=payload.igUserId,
            access_token=payload.igAccessToken,
            daily_post_time=payload.autoTime or "09:00"
        )
        db.add(ig_acc)
        db.flush()
    
    # 3. Create Automation (Use existing or create new)
    auto = db.query(TopicAutomation).filter(TopicAutomation.org_id == org.id).first()
    if not auto:
        auto = TopicAutomation(
            org_id=org.id,
            ig_account_id=ig_acc.id if ig_acc else 0, # 0 if not yet connected
            name="Daily Intelligence Feed",
            topic_prompt=payload.autoTopic or "Daily wisdom and news relevant to our niche.",
            source_mode=payload.contentMode if payload.contentMode != "auto_library" else "none",
            content_seed_mode="auto_library" if payload.contentMode == "auto_library" else "none",
            post_time_local=payload.autoTime or "09:00",
            enabled=True if ig_acc else False, # Only enable if connected
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
async def api_refine_content(
    payload: RefineRequest,
    user: User = Depends(require_user)
):
    from app.services.llm import refine_caption
    refined = refine_caption(payload.text, payload.type)
    return {"refined": refined}
