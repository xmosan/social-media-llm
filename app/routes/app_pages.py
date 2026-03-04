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
import json, calendar, html
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
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          colors: {{
            brand: '#6366f1',
            'brand-hover': '#4f46e5',
            surface: 'rgba(255, 255, 255, 0.03)',
            'text-main': '#ffffff',
            'text-muted': '#94a3b8',
          }}
        }}
      }}
    }}
  </script>
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
      --card-bg: rgba(255, 255, 255, 0.03);
    }
    body { font-family: 'Inter', sans-serif; background-color: var(--main-bg); color: var(--text-main); }
    .ai-bg { background: radial-gradient(circle at top right, #312e81, #020617, #020617); }
    .glass { background: var(--surface); backdrop-filter: blur(12px); border: 1px solid var(--border); }
    .text-gradient { background: linear-gradient(to right, #818cf8, #c084fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .nav-link.active { color: var(--brand); border-bottom: 2px solid var(--brand); }
    .studio-tab.active { background: var(--brand); color: white; border-color: var(--brand); }
    .visual-card.active { border-color: var(--brand); background: rgba(99, 102, 241, 0.1); }
    .visual-card.active .check-icon { display: block; }
    .visual-card .check-icon { display: none; }
    .bg-brand { background-color: var(--brand) !important; }
    .bg-brand-hover:hover { background-color: var(--brand-hover) !important; }
    .text-brand { color: var(--brand) !important; }
    .border-brand { border-color: var(--brand) !important; }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.2); }
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

  <footer class="max-w-7xl mx-auto px-6 py-12 border-t border-white/5 flex flex-col md:flex-row justify-between items-center gap-6 mt-12 mb-12">
    <div class="text-[10px] font-black text-muted uppercase tracking-widest italic">&copy; 2026 Mohammed Hassan. All rights reserved. <span class="text-white/40 lowercase">Proprietary software.</span></div>
    <div class="flex gap-6 text-[9px] font-black uppercase tracking-widest text-muted/60">
        <a href="/" class="hover:text-brand transition-colors">Portal</a>
        <a href="/app" class="hover:text-brand transition-colors">Interface</a>
    </div>
  </footer>

  <script>
    async function logout() {
      await fetch('/auth/logout', { method: 'POST' });
      window.location.href = '/';
    }

    function syncAccounts() {
        const btn = event.currentTarget;
        const originalText = btn.innerText;
        btn.innerText = 'Syncing...';
        btn.disabled = true;
        
        setTimeout(() => {
            btn.innerText = originalText;
            btn.disabled = false;
            window.location.reload();
        }, 1500);
    }

    function openNewPostModal() {
        document.getElementById('newPostModal').classList.remove('hidden');
    }

    function closeNewPostModal() {
        document.getElementById('newPostModal').classList.add('hidden');
    }

    function openEditPostModal(id, caption, time) {
        document.getElementById('editPostId').value = id;
        document.getElementById('editPostCaption').value = caption;
        // Format time for datetime-local
        if (time) {
            const d = new Date(time);
            const iso = d.toISOString().slice(0, 16);
            document.getElementById('editPostTime').value = iso;
        }
        document.getElementById('editPostModal').classList.remove('hidden');
    }

    function closeEditPostModal() {
        hideDeleteConfirm();
        document.getElementById('editPostModal').classList.add('hidden');
    }

    async function savePostEdit() {
        const id = document.getElementById('editPostId').value;
        const caption = document.getElementById('editPostCaption').value;
        const time = document.getElementById('editPostTime').value;
        const btn = document.getElementById('savePostBtn');

        btn.disabled = true;
        btn.innerText = 'SAVING...';

        try {
            const res = await fetch(`/posts/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ caption: caption, scheduled_time: time })
            });
            if (res.ok) window.location.reload();
            else alert('Failed to update post');
        } catch(e) { alert('Error updating post'); }
        finally { btn.disabled = false; btn.innerText = 'Apply Changes'; }
    }

    async function deletePost() {
        const btn = document.getElementById('confirmDeleteBtn');
        const id = document.getElementById('editPostId').value;
        
        btn.disabled = true;
        btn.innerText = 'DELETING...';

        try {
            const res = await fetch(`/posts/${id}`, { method: 'DELETE' });
            if (res.ok) window.location.reload();
            else alert('Failed to delete post');
        } catch(e) { alert('Error deleting post'); }
        finally { btn.disabled = false; btn.innerText = 'Yes, Delete Post'; }
    }

    function showDeleteConfirm() {
        document.getElementById('editPostActions').classList.add('hidden');
        document.getElementById('deleteConfirmActions').classList.remove('hidden');
    }

    function hideDeleteConfirm() {
        document.getElementById('deleteConfirmActions').classList.add('hidden');
        document.getElementById('editPostActions').classList.remove('hidden');
    }

    async function approvePost(id) {
        try {
            const res = await fetch(`/posts/${id}/approve`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ approve_anyway: true })
            });
            if (res.ok) window.location.reload();
            else alert('Approval failed');
        } catch(e) { alert('Error approving'); }
    }

    let currentStudioStep = 1;

    function switchStudioSection(step) {
        currentStudioStep = step;
        // Update Tabs
        for (let i=1; i<=3; i++) {
            const tab = document.getElementById(`sectionTab${i}`);
            const section = document.getElementById(`studioSection${i}`);
            if (i === step) {
                tab.classList.add('studio-tab', 'active');
                tab.classList.remove('text-muted');
                section.classList.remove('hidden');
            } else {
                tab.classList.remove('studio-tab', 'active');
                tab.classList.add('text-muted');
                section.classList.add('hidden');
            }
        }

        // Update Counter
        document.getElementById('stepCounter').innerHTML = `0${step}<span class="text-brand/40">/03</span>`;
        
        // Update Buttons
        document.getElementById('studioPrevBtn').classList.toggle('hidden', step === 1);
        document.getElementById('studioNextBtn').classList.toggle('hidden', step === 3);
        document.getElementById('studioSubmitBtn').classList.toggle('hidden', step !== 3);
    }

    function nextStudioStep() {
        if (currentStudioStep < 3) switchStudioSection(currentStudioStep + 1);
    }

    function prevStudioStep() {
        if (currentStudioStep > 1) switchStudioSection(currentStudioStep - 1);
    }

    function switchSourceTab(tab) {
        const manual = document.getElementById('srcPaneManual');
        const ai = document.getElementById('srcPaneAI');
        const tabManual = document.getElementById('srcTabManual');
        const tabAI = document.getElementById('srcTabAI');

        if (tab === 'manual') {
            manual.classList.remove('hidden');
            ai.classList.add('hidden');
            tabManual.classList.add('studio-tab', 'active');
            tabAI.classList.remove('studio-tab', 'active');
            document.getElementById('summaryFoundation').innerText = 'Manual';
        } else {
            manual.classList.add('hidden');
            ai.classList.remove('hidden');
            tabManual.classList.remove('studio-tab', 'active');
            tabAI.classList.add('studio-tab', 'active');
            document.getElementById('summaryFoundation').innerText = 'AI Gen';
        }
    }

    function setVisualMode(mode) {
        document.getElementById('studioVisualMode').value = mode;
        document.getElementById('summaryVisual').innerText = mode.replace('_', ' ').toUpperCase();
        
        // Update Active Cards
        document.querySelectorAll('.visual-card').forEach(card => card.classList.remove('active'));
        
        if (mode === 'upload') document.getElementById('modeUpload').classList.add('active');
        if (mode === 'media_library') document.getElementById('modeMedia').classList.add('active');
        if (mode === 'ai_background') document.getElementById('modeAI').classList.add('active');
        if (mode === 'quote_card') document.getElementById('modeQuote').classList.add('active');

        // Toggle UI Panels
        document.getElementById('uiUpload').classList.toggle('hidden', mode !== 'upload' && mode !== 'quote_card');
        document.getElementById('uiAI').classList.toggle('hidden', mode !== 'ai_background');
    }

    function setAIPreset(preset) {
        const area = document.querySelector('textarea[name="visual_prompt"]');
        const presets = {
            'nature': 'Minimalist nature scene, lush greenery, realistic landscape photography, 8k',
            'mosque': 'Grand masjid silhouette, golden hour, soft light, spiritual atmosphere',
            'abstract': 'Dynamic abstract patterns, Islamic geometric influence, vibrant gradients',
            'minimal': 'Minimalist composition, neutral tones, high fashion aesthetic, professional'
        };
        area.value = presets[preset] || '';
    }

    function previewUpload(input) {
        if (input.files && input.files[0]) {
            const reader = new FileReader();
            reader.onload = function(e) {
                document.getElementById('uploadPreview').src = e.target.result;
                document.getElementById('uploadPreview').classList.remove('hidden');
                document.getElementById('uploadHint').classList.add('hidden');
            }
            reader.readAsDataURL(input.files[0]);
        }
    }

    async function openLibraryDrawer(tab = 'my_library') {
        document.getElementById('libraryDrawer').classList.remove('translate-x-full');
        
        // Update tab styling
        const myLibTab = document.getElementById('drawerTabMyLib');
        const defaultTab = document.getElementById('drawerTabDefault');
        if (tab === 'all') {
            defaultTab.classList.add('text-white', 'border-brand');
            defaultTab.classList.remove('text-muted', 'border-transparent');
            myLibTab.classList.add('text-muted', 'border-transparent');
            myLibTab.classList.remove('text-white', 'border-brand');
        } else {
            myLibTab.classList.add('text-white', 'border-brand');
            myLibTab.classList.remove('text-muted', 'border-transparent');
            defaultTab.classList.add('text-muted', 'border-transparent');
            defaultTab.classList.remove('text-white', 'border-brand');
        }

        const content = document.getElementById('libraryDrawerContent');
        content.innerHTML = '<div class="text-center py-10"><div class="animate-spin w-6 h-6 border-2 border-brand border-t-transparent rounded-full mx-auto"></div></div>';
        
        try {
            // New structured endpoint
            const res = await fetch('/library/entries');
            const entries = await res.json();
            
            content.innerHTML = '';
            entries.forEach(e => {
                const div = document.createElement('div');
                div.className = 'glass p-5 rounded-2xl border border-white/5 hover:border-brand/40 cursor-pointer transition-all space-y-2';
                
                let metaInfo = '';
                if (e.item_type === 'quran') metaInfo = `Surah ${e.meta.surah_number}:${e.meta.verse_start}`;
                else if (e.item_type === 'hadith') metaInfo = `${e.meta.collection} #${e.meta.hadith_number}`;
                else metaInfo = e.meta.title || e.item_type;

                div.innerHTML = `
                    <div class="flex justify-between items-start">
                        <span class="text-[9px] font-black text-brand uppercase tracking-widest">${e.item_type}</span>
                        <span class="text-[8px] font-bold text-muted uppercase tracking-tighter">${metaInfo}</span>
                    </div>
                    <div class="text-[11px] text-white/80 line-clamp-3 font-medium italic">"${e.text}"</div>
                `;
                div.onclick = () => selectLibraryDoc(e);
                content.appendChild(div);
            });

            if (entries.length === 0) {
                content.innerHTML = `<div class="text-center py-20 opacity-40"><p class="text-[10px] font-black uppercase tracking-widest">Knowledge Base Empty</p></div>`;
            }
        } catch(e) {
            content.innerHTML = '<div class="text-center py-10 text-rose-400 text-[10px] font-black uppercase">Neural link failure.</div>';
        }
    }

    function closeLibraryDrawer() {
        document.getElementById('libraryDrawer').classList.add('translate-x-full');
    }

    function selectLibraryDoc(e) {
        document.getElementById('studioSourceText').value = e.text || "";
        
        let ref = '';
        if (e.item_type === 'quran') ref = `Quran ${e.meta.surah_number}:${e.meta.verse_start}`;
        else if (e.item_type === 'hadith') ref = `${e.meta.collection} #${e.meta.hadith_number}`;
        else ref = e.meta.title || e.item_type;

        document.getElementById('studioReference').value = ref;
        document.getElementById('studioLibraryItemId').value = e.id;
        document.getElementById('summaryFoundation').innerText = 'LIBRARY';
        document.getElementById('srcTabLibrary').classList.add('studio-tab', 'active');
        document.getElementById('srcTabManual').classList.remove('studio-tab', 'active');
        closeLibraryDrawer();
    }
    async function submitNewPost(event) {
        event.preventDefault();
        const btn = document.getElementById('studioSubmitBtn');
        const originalText = (btn ? btn.innerText : 'FINALIZING...');
        if (btn) {
            btn.innerText = 'GENERATING...';
            btn.disabled = true;
        }

        const formData = new FormData(event.target);
        const visualMode = formData.get('visual_mode') || document.getElementById('studioVisualMode').value;
        
        if (!formData.has('visual_mode')) {
            formData.set('visual_mode', visualMode);
        }
        
        if (visualMode === 'ai_background') {
            formData.set('use_ai_image', 'true');
        }

        try {
            const res = await fetch('/posts/intake', {
                method: 'POST',
                body: formData
            });
            if (res.ok) {
                window.location.reload();
            } else {
                let errDetail = 'Failed to create post';
                try {
                    const err = await res.json();
                    errDetail = err.detail || JSON.stringify(err);
                } catch(e) {
                    errDetail = await res.text();
                }
                alert('Error: ' + errDetail);
            }
        } catch (e) {
            alert('Upload failed: ' + e);
        } finally {
            if (btn) {
                btn.innerText = originalText;
                btn.disabled = false;
            }
        }
    }

    async function launchLivePreview() {
        const modal = document.getElementById('previewModal');
        const img = document.getElementById('previewImage');
        const loader = document.getElementById('previewLoader');
        
        modal.classList.remove('hidden');
        img.classList.add('hidden');
        loader.classList.remove('hidden');

        const formData = new FormData(document.querySelector('#newPostModal form'));
        
        try {
            const res = await fetch('/posts/preview_render', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (res.ok) {
                img.src = data.preview_url;
                img.classList.remove('hidden');
                loader.classList.add('hidden');
            } else {
                const detail = data.detail || JSON.stringify(data.detail || data);
                alert('Preview failed: ' + detail);
                modal.classList.add('hidden');
            }
        } catch (e) {
            alert('Network error: ' + e);
            modal.classList.add('hidden');
        }
    }

    function closePreviewModal() {
        document.getElementById('previewModal').classList.add('hidden');
    }
  </script>

  <!-- Content Studio Modal (Overhauled New Post) -->
  <div id="newPostModal" class="fixed inset-0 bg-black/90 backdrop-blur-xl z-[100] flex items-center justify-center p-4 md:p-10 hidden">
    <div class="glass w-full h-full max-w-7xl rounded-[3rem] overflow-hidden flex flex-col animate-in fade-in zoom-in duration-500 border-white/5 shadow-2xl">
      <!-- Studio Header -->
      <div class="px-10 py-6 border-b border-white/5 flex justify-between items-center bg-white/2">
        <div>
          <h3 class="text-2xl font-black italic text-white tracking-tight">Content <span class="text-brand">Studio</span></h3>
          <p class="text-[10px] font-black text-muted uppercase tracking-[0.3em]">Neural Creator Engine v2.0</p>
        </div>
        <div class="flex items-center gap-6">
          <div class="flex gap-2 p-1 bg-white/5 rounded-xl border border-white/10">
            <button type="button" onclick="switchStudioSection(1)" id="sectionTab1" class="px-6 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all studio-tab active">1. Content</button>
            <button type="button" onclick="switchStudioSection(2)" id="sectionTab2" class="px-6 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all text-muted hover:text-white">2. Visuals</button>
            <button type="button" onclick="switchStudioSection(3)" id="sectionTab3" class="px-6 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all text-muted hover:text-white">3. Publish</button>
          </div>
          <button onclick="closeNewPostModal()" class="p-3 bg-white/5 hover:bg-rose-500/10 hover:text-rose-400 rounded-full transition-all">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
          </button>
        </div>
      </div>

      <form onsubmit="submitNewPost(event)" class="flex-1 overflow-hidden flex flex-col md:flex-row">
        <!-- Main Configuration Area -->
        <div class="flex-1 overflow-y-auto p-10 space-y-12">
          
          <!-- SECTION 1: CONTENT SOURCE -->
          <div id="studioSection1" class="space-y-8 animate-in slide-in-from-left-4 duration-500">
            <div class="space-y-4">
              <div class="flex justify-between items-end">
                <div>
                  <label class="text-[10px] font-black uppercase tracking-[0.2em] text-brand">Content Source</label>
                  <h4 class="text-lg font-black text-white italic">Choose your foundation</h4>
                </div>
                <div class="flex gap-1 p-1 bg-white/5 rounded-xl border border-white/5">
                  <button type="button" onclick="switchSourceTab('manual')" id="srcTabManual" class="px-4 py-2 rounded-lg text-[8px] font-black uppercase tracking-widest transition-all studio-tab active">Manual</button>
                  <button type="button" id="srcTabLibrary" class="px-4 py-2 rounded-lg text-[8px] font-black uppercase tracking-widest transition-all text-muted hover:text-white" onclick="openLibraryDrawer()">From Library</button>
                  <button type="button" onclick="switchSourceTab('ai')" id="srcTabAI" class="px-4 py-2 rounded-lg text-[8px] font-black uppercase tracking-widest transition-all text-muted hover:text-white">AI Gen</button>
                </div>
              </div>
              
              <!-- Manual Tab Area -->
              <div id="srcPaneManual" class="space-y-4">
                <textarea id="studioSourceText" name="source_text" required placeholder="Type your custom caption or directives here..." class="w-full bg-white/5 border border-white/10 rounded-2xl p-6 text-sm font-medium text-white outline-none focus:border-brand/40 transition-all h-48 resize-none"></textarea>
                <div class="flex gap-4">
                    <input type="text" id="studioReference" name="reference" placeholder="Reference (Optional, e.g. Bukhari 123)" class="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-[10px] font-bold text-white outline-none focus:border-brand/40">
                    <button type="button" onclick="openLibraryDrawer()" class="px-4 bg-brand/10 text-brand border border-brand/20 rounded-xl text-[10px] font-black uppercase tracking-widest flex items-center gap-2 hover:bg-brand/20 transition-all">
                      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"></path></svg>
                      Browse Library
                    </button>
                </div>
              </div>

              <!-- AI Gen Area (Hidden by default) -->
              <div id="srcPaneAI" class="hidden space-y-6">
                <div class="p-6 rounded-2xl bg-brand/5 border border-brand/20 space-y-4">
                  <div class="space-y-1">
                    <label class="text-[8px] font-black text-brand uppercase tracking-widest">Post Topic</label>
                    <input type="text" id="aiTopic" placeholder="e.g. The importance of gratitude in Islam" class="w-full bg-transparent border-b border-white/10 py-2 text-sm text-white font-medium outline-none focus:border-brand">
                  </div>
                  <div class="grid grid-cols-2 gap-4">
                    <div class="space-y-1">
                      <label class="text-[8px] font-black text-brand uppercase tracking-widest">Tone</label>
                      <select id="aiTone" class="w-full bg-transparent text-[10px] text-white font-bold outline-none">
                        <option>Philosophical</option>
                        <option>Motivational</option>
                        <option>Educational</option>
                        <option>Deep Reflection</option>
                      </select>
                    </div>
                    <div class="space-y-1">
                      <label class="text-[8px] font-black text-brand uppercase tracking-widest">Creativity Slider</label>
                      <input type="range" class="w-full accent-brand">
                    </div>
                  </div>
                  <button type="button" onclick="generateAISource()" class="w-full py-3 bg-brand/20 text-brand rounded-xl font-black text-[10px] uppercase tracking-widest border border-brand/20">Analyze & Preview Ideas</button>
                </div>
              </div>
            </div>
          </div>

          <!-- SECTION 2: VISUAL CONTROL -->
          <div id="studioSection2" class="hidden space-y-8 animate-in slide-in-from-right-4 duration-500">
            <div class="space-y-6">
              <div>
                <label class="text-[10px] font-black uppercase tracking-[0.2em] text-brand">Visual Selector</label>
                <h4 class="text-lg font-black text-white italic">Define the aesthetic</h4>
              </div>

              <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div onclick="setVisualMode('upload')" id="modeUpload" class="visual-card active p-6 rounded-3xl border border-white/10 bg-white/2 cursor-pointer transition-all hover:bg-white/5 relative">
                  <div class="absolute top-3 right-3 check-icon text-brand"><svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></div>
                  <div class="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center text-white mb-4"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path></svg></div>
                  <div class="text-[10px] font-black text-white uppercase tracking-widest">Upload</div>
                  <div class="text-[8px] font-bold text-muted uppercase mt-1">Manual File</div>
                </div>

                <div onclick="setVisualMode('media_library')" id="modeMedia" class="visual-card p-6 rounded-3xl border border-white/10 bg-white/2 cursor-pointer transition-all hover:bg-white/5 relative">
                  <div class="absolute top-3 right-3 check-icon text-brand"><svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></div>
                  <div class="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center text-white mb-4"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg></div>
                  <div class="text-[10px] font-black text-white uppercase tracking-widest">Vault</div>
                  <div class="text-[8px] font-bold text-muted uppercase mt-1">From assets</div>
                </div>

                <div onclick="setVisualMode('ai_background')" id="modeAI" class="visual-card p-6 rounded-3xl border border-white/10 bg-white/2 cursor-pointer transition-all hover:bg-white/5 relative">
                  <div class="absolute top-3 right-3 check-icon text-brand"><svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></div>
                  <div class="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center text-white mb-4"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg></div>
                  <div class="text-[10px] font-black text-white uppercase tracking-widest">Gen AI</div>
                  <div class="text-[8px] font-bold text-muted uppercase mt-1">DALL-E 3</div>
                </div>

                <div onclick="setVisualMode('quote_card')" id="modeQuote" class="visual-card p-6 rounded-3xl border border-white/10 bg-white/2 cursor-pointer transition-all hover:bg-white/5 relative">
                  <div class="absolute top-3 right-3 check-icon text-brand"><svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></div>
                  <div class="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center text-white mb-4"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"></path></svg></div>
                  <div class="text-[10px] font-black text-white uppercase tracking-widest">Quote Card</div>
                  <div class="text-[8px] font-bold text-muted uppercase mt-1">Text Overlay</div>
                </div>
              </div>

              <!-- Specific Control Panels -->
              <div id="visualControls" class="p-8 rounded-2xl bg-white/2 border border-white/5 space-y-4">
                 <!-- Upload UI -->
                 <div id="uiUpload" class="space-y-4">
                    <label class="text-[8px] font-black text-muted uppercase tracking-widest">Selected Image</label>
                    <div class="flex items-center gap-6">
                      <div class="w-24 h-24 rounded-2xl bg-white/5 border border-dashed border-white/10 flex items-center justify-center text-muted overflow-hidden">
                        <img id="uploadPreview" class="hidden w-full h-full object-cover">
                        <span id="uploadHint">?</span>
                      </div>
                      <input type="file" name="image" id="studioImageInput" onchange="previewUpload(this)" class="hidden">
                      <button type="button" onclick="document.getElementById('studioImageInput').click()" class="px-6 py-3 bg-white/5 border border-white/10 rounded-xl text-[10px] font-black uppercase text-white">Select File</button>
                    </div>
                 </div>

                 <!-- AI Background UI -->
                 <div id="uiAI" class="hidden space-y-4">
                    <div class="space-y-2">
                       <label class="text-[8px] font-black text-muted uppercase tracking-widest">Visual Prompt</label>
                       <textarea name="visual_prompt" placeholder="Describe the scene... e.g. Minimalist mosque silhouette at sunset, warm tones, high quality photography" class="w-full bg-white/5 border border-white/10 rounded-xl p-4 text-[10px] text-white outline-none focus:border-brand h-24"></textarea>
                    </div>
                    <div class="grid grid-cols-4 gap-2">
                       <button type="button" onclick="setAIPreset('nature')" class="py-2 bg-white/2 border border-white/5 rounded-lg text-[8px] font-black uppercase text-muted hover:text-white">Nature</button>
                       <button type="button" onclick="setAIPreset('mosque')" class="py-2 bg-white/2 border border-white/5 rounded-lg text-[8px] font-black uppercase text-muted hover:text-white">Mosque</button>
                       <button type="button" onclick="setAIPreset('abstract')" class="py-2 bg-white/2 border border-white/5 rounded-lg text-[8px] font-black uppercase text-muted hover:text-white">Abstract</button>
                       <button type="button" onclick="setAIPreset('minimal')" class="py-2 bg-white/2 border border-white/5 rounded-lg text-[8px] font-black uppercase text-muted hover:text-white">Minimal</button>
                    </div>
                 </div>
              </div>
            </div>
          </div>

          <!-- SECTION 3: PUBLISH SETTINGS -->
          <div id="studioSection3" class="hidden space-y-8 animate-in slide-in-from-right-4 duration-500">
            <div class="space-y-6">
              <div>
                <label class="text-[10px] font-black uppercase tracking-[0.2em] text-brand">Final Settings</label>
                <h4 class="text-lg font-black text-white italic">Confirm distribution</h4>
              </div>

              <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                 <div class="space-y-4">
                    <div class="space-y-2">
                      <label class="text-[10px] font-black uppercase tracking-[0.2em] text-muted">Select Target Account</label>
                      <select name="ig_account_id" class="w-full bg-white/5 border border-white/10 rounded-2xl p-4 text-sm font-bold text-white outline-none focus:border-brand/40 transition-all">
                        {account_options}
                      </select>
                    </div>
                    <div class="space-y-2">
                      <label class="text-[10px] font-black uppercase tracking-[0.2em] text-muted">Schedule Time (UTC)</label>
                      <input type="datetime-local" name="scheduled_time" class="w-full bg-white/5 border border-white/10 rounded-2xl p-4 text-sm font-bold text-white outline-none focus:border-brand/40 transition-all">
                    </div>
                 </div>

                 <!-- Preview / Summary -->
                 <div class="p-8 rounded-[2rem] bg-brand/5 border border-brand/20 flex flex-col items-center justify-center text-center space-y-4">
                    <div class="w-16 h-16 rounded-full bg-brand/20 flex items-center justify-center text-brand">
                        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg>
                    </div>
                    <p class="text-[10px] font-bold text-brand uppercase tracking-widest">Review your composition</p>
                    <button type="button" onclick="launchLivePreview()" class="text-xs font-black text-white hover:underline transition-all">Launch Live Preview &rarr;</button>
                 </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Static Sidebar Control -->
        <input type="hidden" name="visual_mode" id="studioVisualMode" value="upload">
        <input type="hidden" name="library_item_id" id="studioLibraryItemId">

        <div class="w-full md:w-80 bg-black/40 border-l border-white/5 p-8 flex flex-col justify-between">
           <div class="space-y-8">
              <div class="space-y-1">
                <div class="text-[8px] font-black text-muted uppercase tracking-[0.2em]">Current Step</div>
                <div id="stepCounter" class="text-3xl font-black italic text-white tracking-widest">01<span class="text-brand/40">/03</span></div>
              </div>

              <div class="space-y-4 pt-4">
                 <h5 class="text-[10px] font-black text-white uppercase tracking-widest">Composition Summary</h5>
                 <div class="space-y-2">
                    <div class="flex justify-between text-[8px] font-bold text-muted uppercase"><span>Status</span> <span class="text-white">Drafting</span></div>
                    <div class="flex justify-between text-[8px] font-bold text-muted uppercase"><span>Foundation</span> <span id="summaryFoundation" class="text-white">Manual</span></div>
                    <div class="flex justify-between text-[8px] font-bold text-muted uppercase"><span>Visual</span> <span id="summaryVisual" class="text-white">Upload</span></div>
                 </div>
              </div>
           </div>

           <div class="space-y-3">
              <button type="button" onclick="prevStudioStep()" id="studioPrevBtn" class="w-full py-4 text-[10px] font-black uppercase tracking-widest text-muted hover:text-white transition-all hidden">Back</button>
              <button type="button" onclick="nextStudioStep()" id="studioNextBtn" class="w-full py-5 bg-brand rounded-2xl font-black text-xs uppercase tracking-widest text-white shadow-xl shadow-brand/20 hover:scale-[1.02] active:scale-[0.98] transition-all">Continue Composition &rarr;</button>
              <button type="submit" id="studioSubmitBtn" class="w-full py-5 bg-emerald-500 rounded-2xl font-black text-xs uppercase tracking-widest text-white shadow-xl shadow-emerald-500/20 hover:scale-[1.02] active:scale-[0.98] transition-all hidden">Finalize & Schedule</button>
           </div>
        </div>
      </form>
    </div>
  </div>

  <!-- Library Explorer Side Drawer -->
  <div id="libraryDrawer" class="fixed inset-y-0 right-0 w-full max-w-md bg-black/95 backdrop-blur-2xl z-[150] shadow-2xl border-l border-white/10 transform translate-x-full transition-transform duration-500 overflow-hidden flex flex-col">
    <div class="p-8 pb-4 border-b border-white/5 flex justify-between items-center">
      <div>
        <h3 class="text-xl font-black italic text-white">Neural <span class="text-brand">Library</span></h3>
        <p class="text-[8px] font-black text-muted uppercase tracking-widest">Extract source materials</p>
      </div>
      <button onclick="closeLibraryDrawer()" class="p-2 text-muted hover:text-white transition-all"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg></button>
    </div>
    
    <!-- Drawer Tabs -->
    <div class="flex px-8 border-b border-white/5">
        <button id="drawerTabMyLib" onclick="openLibraryDrawer('my_library')" class="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-white border-b-2 border-brand transition-all">My Library</button>
        <button id="drawerTabDefault" onclick="openLibraryDrawer('default_packs')" class="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-muted border-b-2 border-transparent hover:text-white transition-all">Default Packs</button>
    </div>

    <div class="p-6 border-b border-white/5">
        <input type="text" placeholder="Search library quotes..." class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-xs text-white focus:border-brand/40 outline-none">
    </div>
    <div class="flex-1 overflow-y-auto p-6">
        <div id="libraryDrawerContent" class="space-y-4">
            <!-- Populated via Javascript -->
        </div>
    </div>
  </div>

  <!-- Preview Modal Overlay -->
  <div id="previewModal" class="fixed inset-0 bg-black/95 z-[200] hidden flex flex-col items-center justify-center p-6 md:p-20">
      <button type="button" onclick="closePreviewModal()" class="absolute top-10 right-10 p-4 bg-white/5 hover:bg-white/10 rounded-full text-white transition-all">
          <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
      </button>
      
      <div id="previewLoader" class="flex flex-col items-center gap-4">
          <div class="animate-spin w-12 h-12 border-4 border-brand border-t-transparent rounded-full"></div>
          <p class="text-[10px] font-black text-brand uppercase tracking-[0.3em]">Rendering Intelligence...</p>
      </div>
      
      <img id="previewImage" class="hidden max-w-full max-h-full rounded-3xl shadow-2xl border border-white/10 animate-in fade-in zoom-in duration-700">
      
      <div class="mt-8 flex gap-4 text-white">
          <button type="button" onclick="closePreviewModal()" class="px-10 py-4 bg-white/5 border border-white/10 rounded-2xl font-black text-[10px] uppercase tracking-widest hover:bg-white/10 transition-all">Close Preview</button>
          <button type="button" onclick="closePreviewModal()" class="px-10 py-4 bg-emerald-500 rounded-2xl font-black text-[10px] uppercase tracking-widest shadow-lg shadow-emerald-500/20 hover:scale-105 transition-all">Looks Good</button>
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
              <button onclick="openEditPostModal('{next_post_id}', {next_post_caption_json}, '{next_post_time_iso}')" class="flex-1 py-3 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest hover:bg-white/10 transition-all">Edit</button>
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

        <div id="editPostActions" class="flex gap-4 pt-4">
          <button id="deletePostBtn" onclick="showDeleteConfirm()" class="flex-1 py-4 bg-rose-500/10 border border-rose-500/20 rounded-2xl font-black text-xs uppercase tracking-widest text-rose-400 hover:bg-rose-500/20 transition-all">Delete Post</button>
          <div class="flex-1 flex gap-2">
            <button onclick="closeEditPostModal()" class="flex-1 py-4 bg-white/5 border border-white/10 rounded-2xl font-black text-xs uppercase tracking-widest text-white hover:bg-white/10 transition-all">Cancel</button>
            <button id="savePostBtn" onclick="savePostEdit()" class="flex-[2] py-4 bg-brand rounded-2xl font-black text-xs uppercase tracking-widest text-white shadow-xl shadow-brand/20 hover:bg-brand-hover transition-all">Apply</button>
          </div>
        </div>

        <div id="deleteConfirmActions" class="hidden pt-4">
          <div class="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/20 mb-4 hstack gap-3">
             <div class="w-10 h-10 rounded-full bg-rose-500/20 flex items-center justify-center text-rose-400 shrink-0">
               <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
             </div>
             <div>
               <h4 class="text-sm font-black text-white">Delete Scheduled Post?</h4>
               <p class="text-[10px] font-bold text-muted uppercase tracking-widest mt-1">This action cannot be undone.</p>
             </div>
          </div>
          <div class="flex gap-4">
            <button onclick="hideDeleteConfirm()" class="flex-1 py-4 bg-white/5 border border-white/10 rounded-2xl font-black text-xs uppercase tracking-widest text-white hover:bg-white/10 transition-all">Cancel</button>
            <button id="confirmDeleteBtn" onclick="deletePost()" class="flex-1 py-4 bg-rose-500 hover:bg-rose-600 rounded-2xl font-black text-xs uppercase tracking-widest text-white shadow-xl shadow-rose-500/20 transition-all">Yes, Delete Post</button>
          </div>
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
    next_post_caption_json = "null"
    next_post_time_iso = ""
    
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
        
        caption_json = html.escape(json.dumps(p.caption or ""), quote=True)
        
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
            <button onclick="openEditPostModal('{p.id}', {caption_json}, '{p.scheduled_time.isoformat() if p.scheduled_time else ''}')" class="p-2 text-muted hover:text-white transition-colors">
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

    content = APP_DASHBOARD_CONTENT.replace("{admin_cta}", admin_cta)\
                                   .replace("{connection_cta}", connection_cta)\
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
                                   .replace("{next_post_time_iso}", str(next_post_time_iso))
    
    # --- GET ACCOUNT OPTIONS FOR STUDIO MODAL ---
    accs = db.query(IGAccount).filter(IGAccount.org_id == user.active_org_id).all()
    account_options = "".join([f'<option value="{a.id}">{a.name} (@{a.ig_user_id})</option>' for a in accs])

    return APP_LAYOUT_HTML.replace("{title}", "Dashboard")\
                          .replace("{user_name}", user.name or user.email)\
                          .replace("{org_name}", org.name if org else "Personal Workspace")\
                          .replace("{admin_link}", admin_link)\
                          .replace("{active_dashboard}", "active")\
                          .replace("{active_calendar}", "")\
                          .replace("{active_automations}", "")\
                          .replace("{active_library}", "")\
                          .replace("{active_media}", "")\
                          .replace("{content}", content)\
                          .replace("{account_options}", account_options)

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
    
    return APP_LAYOUT_HTML.replace("{title}", "Calendar")\
                          .replace("{user_name}", user.name or user.email)\
                          .replace("{org_name}", org.name if org else "Personal Workspace")\
                          .replace("{admin_link}", admin_link)\
                          .replace("{active_dashboard}", "")\
                          .replace("{active_calendar}", "active")\
                          .replace("{active_automations}", "")\
                          .replace("{active_library}", "")\
                          .replace("{active_media}", "")\
                          .replace("{content}", content)\
                          .replace("{account_options}", "")

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
        
        edit_data = {
            "id": a.id, 
            "name": a.name, 
            "topic": a.topic_prompt, 
            "seed_mode": a.content_seed_mode, 
            "seed_text": a.content_seed_text or "", 
            "time": a.post_time_local or "09:00",
            "library_scope": a.library_scope
        }
        edit_data_json = html.escape(json.dumps(edit_data), quote=True)

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
            <button onclick="showEditModal({edit_data_json})" class="px-6 py-3 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest text-white hover:bg-white/10 transition-all">Configure</button>
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
              <div class="flex justify-between items-center">
                <label class="text-[10px] font-black uppercase tracking-widest text-muted">Core Topic Prompt</label>
                <button onclick="suggestAutomationTopic('editTopic', 'editLibraryTopic')" class="text-[8px] font-bold text-brand uppercase hover:text-white transition-all">Suggest Library Topic</button>
              </div>
              <textarea id="editTopic" rows="3" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand"></textarea>
              <input type="hidden" id="editLibraryTopic">
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
              <div class="flex justify-between items-center">
                <label class="text-[10px] font-black uppercase tracking-widest text-muted">Manual Seed Text</label>
                <button onclick="openLibraryPicker('editSeedText')" class="text-[9px] font-black uppercase text-brand hover:text-white transition-colors flex items-center gap-1">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                    Insert from Library
                </button>
              </div>
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
              <div class="flex justify-between items-center">
                <label class="text-[10px] font-black uppercase tracking-widest text-muted">Core Topic Prompt</label>
                <button onclick="suggestAutomationTopic('newTopic', 'newLibraryTopic')" class="text-[8px] font-bold text-brand uppercase hover:text-white transition-all">Suggest Library Topic</button>
              </div>
              <textarea id="newTopic" rows="3" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand" placeholder="Describe the focus of this automation..."></textarea>
              <input type="hidden" id="newLibraryTopic">
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
              <div class="flex justify-between items-center">
                <label class="text-[10px] font-black uppercase tracking-widest text-muted">Manual Seed Text</label>
                <button onclick="openLibraryPicker('newSeedText')" class="text-[9px] font-black uppercase text-brand hover:text-white transition-colors flex items-center gap-1">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                    Insert from Library
                </button>
              </div>
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

    <!-- Library Picker Modal -->
    <div id="libraryPickerModal" class="fixed inset-0 bg-black/90 backdrop-blur-md z-[150] hidden flex items-center justify-center p-6">
      <div class="glass max-w-2xl w-full p-8 rounded-[2.5rem] space-y-6 border border-white/10 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        <div class="flex justify-between items-center">
            <h2 class="text-xl font-black italic text-white tracking-tight">Insert <span class="text-brand">Knowledge</span></h2>
            <button onclick="closeLibraryPicker()" class="p-2 hover:bg-white/10 rounded-full transition-all text-white/40">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
            </button>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="relative flex-1">
                <input type="text" id="pickerSearch" oninput="loadPickerEntries()" placeholder="Filter knowledge..." class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-[10px] font-bold text-white outline-none focus:border-brand/40 transition-all placeholder:text-white/20">
            </div>
            <div class="flex gap-2">
                <select id="pickerTopic" onchange="loadPickerEntries()" class="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-[10px] font-bold text-white outline-none appearance-none">
                    <option value="">All Topics</option>
                </select>
                <select id="pickerType" onchange="loadPickerEntries()" class="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-[10px] font-bold text-white outline-none appearance-none font-black uppercase">
                    <option value="">All Types</option>
                    <option value="quran">Quran</option>
                    <option value="hadith">Hadith</option>
                    <option value="quote">Quote</option>
                </select>
            </div>
        </div>
        
        <div class="flex justify-end px-2">
            <button onclick="suggestPickerTopic()" class="text-[9px] font-black uppercase text-brand flex items-center gap-2 hover:text-white transition-all">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                Suggest from my prompt
            </button>
        </div>

        <div id="pickerResults" class="flex-1 overflow-y-auto space-y-3 min-h-[300px] pr-2 custom-scrollbar">
            <!-- Results via JS -->
        </div>
        
        <div class="text-[8px] font-bold text-muted uppercase tracking-widest text-center">
            Click an entry to insert its text and auto-formatted citation.
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
        document.getElementById('editLibraryTopic').value = data.library_topic_slug || '';
        document.getElementById('editSeedMode').value = data.seed_mode || 'none';
        document.getElementById('editSeedText').value = data.seed_text;
        document.getElementById('editTime').value = data.time;
        
        const scope = data.library_scope || [];
        document.getElementById('editScopePrebuilt').checked = scope.includes('prebuilt');
        document.getElementById('editScopeOrg').checked = scope.includes('org_library');

        toggleSeedText();
        document.getElementById('editModal').classList.remove('hidden');
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
          library_topic_slug: document.getElementById('editLibraryTopic').value,
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

      async function suggestAutomationTopic(inputId, hiddenId) {{
          const prompt = document.getElementById(inputId).value;
          if (!prompt) return alert("Please enter a prompt first");
          
          const btn = event.target;
          const originalText = btn.textContent;
          btn.textContent = 'SUGGESTING...';
          btn.disabled = true;
          
          try {{
              const res = await fetch('/library/topic-suggest', {{
                  method: 'POST',
                  headers: {{ 'Content-Type': 'application/json' }},
                  body: JSON.stringify({{ text: prompt, max: 1 }})
              }});
              const data = await res.json();
              if (data.suggestions && data.suggestions.length > 0) {{
                  const s = data.suggestions[0];
                  if (confirm(`Suggested Library Topic: ${{s.topic}}\\n(${{s.reason}})\\n\\nApply this for grounding?`)) {{
                      document.getElementById(hiddenId).value = s.slug;
                      btn.textContent = `LINKED: ${{s.topic.toUpperCase()}}`;
                      btn.classList.add('text-green-400');
                  }} else {{ btn.textContent = originalText; }}
              }} else {{
                  alert("No direct library topic matches found. AI will generate freely.");
                  btn.textContent = originalText;
              }}
          }} catch(e) {{ btn.textContent = originalText; }}
          finally {{ btn.disabled = false; }}
      }}

      // REUSED from library to support picker across pages
      let pickerTargetId = null;
      function openLibraryPicker(targetId) {{
          pickerTargetId = targetId;
          document.getElementById('libraryPickerModal').classList.remove('hidden');
          loadPickerTopics();
          loadPickerEntries();
      }}
      function closeLibraryPicker() {{
          document.getElementById('libraryPickerModal').classList.add('hidden');
          pickerTargetId = null;
      }}
      async function loadPickerTopics() {{
          try {{
              const res = await fetch('/library/topics');
              const topics = await res.json();
              const select = document.getElementById('pickerTopic');
              select.innerHTML = '<option value="">All Topics</option>';
              topics.forEach(t => {{
                  const opt = document.createElement('option');
                  opt.value = t.slug;
                  opt.textContent = t.slug.replace(/_/g, ' ').toUpperCase();
                  select.appendChild(opt);
              }});
          }} catch(e) {{}}
      }}
      async function loadPickerEntries() {{
          const query = document.getElementById('pickerSearch').value;
          const topic = document.getElementById('pickerTopic').value;
          const type = document.getElementById('pickerType').value;
          const list = document.getElementById('pickerResults');
          list.innerHTML = '<div class="text-center py-10 text-[9px] font-black uppercase text-muted animate-pulse">Scanning Library...</div>';
          try {{
              let url = `/library/entries?query=${{encodeURIComponent(query)}}`;
              if (topic) url += `&topic=${{encodeURIComponent(topic)}}`;
              if (type) url += `&item_type=${{encodeURIComponent(type)}}`;
              const res = await fetch(url);
              const entries = await res.json();
              if (entries.length === 0) {{
                  list.innerHTML = '<div class="text-center py-10 text-[9px] font-black uppercase text-muted opacity-40">No entries found</div>';
                  return;
              }}
              list.innerHTML = '';
              entries.forEach(e => {{
                  const div = document.createElement('div');
                  div.className = "p-4 bg-white/5 border border-white/5 rounded-2xl hover:bg-white/10 hover:border-brand/30 transition-all cursor-pointer space-y-2";
                  div.onclick = () => selectPickerEntry(e);
                  div.innerHTML = `
                      <div class="flex justify-between items-center">
                        <span class="text-[7px] font-black text-brand uppercase tracking-widest">${{e.item_type}}</span>
                        <span class="text-[8px] font-black text-muted">${{e.topic || ''}}</span>
                      </div>
                      <p class="text-[10px] text-white/70 line-clamp-2">${{e.text.substring(0, 150)}}...</p>
                  `;
                  list.appendChild(div);
              }});
          }} catch(e) {{}}
      }}
      async function suggestPickerTopic() {{
          const query = document.getElementById('pickerSearch').value;
          if (!query) return;
          try {{
              const res = await fetch('/library/topic-suggest', {{
                  method: 'POST',
                  headers: {{ 'Content-Type': 'application/json' }},
                  body: JSON.stringify({{ text: query, max: 1 }})
              }});
              const data = await res.json();
              if (data.suggestions && data.suggestions.length > 0) {{
                  document.getElementById('pickerTopic').value = data.suggestions[0].slug;
                  loadPickerEntries();
              }}
          }} catch(e) {{}}
      }}
      function selectPickerEntry(entry) {{
          const target = document.getElementById(pickerTargetId);
          if (target) {{
              let credit = "";
              if (entry.item_type === 'hadith') credit = `\\n\\n[Ref: ${{entry.meta.collection}} #${{entry.meta.hadith_number}}]`;
              else if (entry.item_type === 'quran') credit = `\\n\\n[Quran ${{entry.meta.surah_number}}:${{entry.meta.verse_start}}]`;
              target.value = entry.text + credit;
          }}
          closeLibraryPicker();
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
        finally {{ btn.disabled = false; btn.textContent = 'Run Now'; }}
      }}
    </script>
    """
    
    return APP_LAYOUT_HTML.replace("{title}", "Automations")\
                          .replace("{user_name}", user.name or user.email)\
                          .replace("{org_name}", org.name if org else "Personal Workspace")\
                          .replace("{admin_link}", admin_link)\
                          .replace("{active_dashboard}", "")\
                          .replace("{active_calendar}", "")\
                          .replace("{active_automations}", "active")\
                          .replace("{active_library}", "")\
                          .replace("{active_media}", "")\
                          .replace("{content}", content)\
                          .replace("{account_options}", account_options)

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
    
    return APP_LAYOUT_HTML.replace("{title}", "Media")\
                          .replace("{user_name}", user.name or user.email)\
                          .replace("{org_name}", org.name if org else "Personal Workspace")\
                          .replace("{admin_link}", admin_link)\
                          .replace("{active_dashboard}", "")\
                          .replace("{active_calendar}", "")\
                          .replace("{active_automations}", "")\
                          .replace("{active_library}", "")\
                          .replace("{active_media}", "active")\
                          .replace("{content}", content)\
                          .replace("{account_options}", "")

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
    
    # Check if user is admin for this org or superadmin
    is_admin = user.is_superadmin
    if not is_admin:
        membership = db.query(OrgMember).filter(OrgMember.user_id == user.id, OrgMember.org_id == org_id).first()
        if membership and membership.role in ["admin", "owner"]:
            is_admin = True

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

    manage_btn = ""
    # Removed unused manage_btn logic as it's handled by superadmin_controls

    content = """
    <style>
        .dir-rtl {{ direction: rtl; unicode-bidi: bidi-override; }}
        .font-serif {{ font-family: 'Amiri', 'Traditional Arabic', serif; }}
        .hide-scrollbar::-webkit-scrollbar {{ display: none; }}
        .hide-scrollbar {{ -ms-overflow-style: none; scrollbar-width: none; }}
    </style>
    
    <div class="space-y-8 h-full flex flex-col">
      <div class="flex justify-between items-end flex-shrink-0">
        <div>
          <h1 class="text-3xl font-black italic tracking-tight text-white">Source <span class="text-brand">Library</span></h1>
          <p class="text-[10px] font-black text-muted uppercase tracking-[0.3em]">Knowledge Base Management</p>
        </div>
        <div class="flex gap-4">
          <button onclick="openEntryModal()" class="px-8 py-4 bg-brand rounded-2xl font-black text-[11px] uppercase tracking-widest text-white shadow-xl shadow-brand/20 hover:scale-[1.02] active:scale-[0.98] transition-all flex items-center gap-3">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
            Add Library Entry
          </button>
        </div>
      </div>

      <!-- Main Layout: Sidebar + List -->
      <div class="flex gap-8 flex-1 overflow-hidden min-h-0">
        <!-- Sidebar: Sources -->
        <div class="w-80 glass rounded-[2.5rem] flex flex-col overflow-hidden border border-white/5">
          <div class="p-6 border-b border-white/10 flex flex-col gap-4 bg-white/2">
            <div class="flex justify-between items-center">
                <h3 class="text-xs font-black uppercase tracking-widest text-white/50">Collections</h3>
                <span id="sourceCount" class="text-[9px] font-black text-brand bg-brand/10 px-2 py-0.5 rounded-full">0</span>
            </div>
            
            {superadmin_controls}
          </div>
          <div id="sourceList" class="flex-1 overflow-y-auto p-4 space-y-2 hide-scrollbar">
            <!-- Loaded via JS -->
          </div>
        </div>

        <!-- Main Content: Entries Grid -->
        <div class="flex-1 glass rounded-[2.5rem] flex flex-col overflow-hidden border border-white/5 bg-white/2">
          <div class="p-6 border-b border-white/10 flex justify-between items-center">
            <div class="flex items-center gap-6 flex-1">
              <h3 class="text-xs font-black uppercase tracking-widest text-white/50">Knowledge Nodes</h3>
              <div class="relative flex-1 max-w-md">
                <input type="text" id="entrySearch" oninput="debounceEntryQuery()" placeholder="Search through your library..." class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-3 text-[11px] font-bold text-white outline-none focus:border-brand/40 transition-all placeholder:text-white/10">
                <svg class="w-4 h-4 absolute right-4 top-1/2 -translate-y-1/2 text-white/20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
              </div>
            </div>
            <div class="flex items-center gap-4 ml-4">
                <div class="flex items-center gap-2 bg-white/5 border border-white/10 rounded-xl px-4 py-2 relative">
                    <span class="text-[9px] font-black uppercase text-white/30">Topic:</span>
                    <select id="filterTopic" onchange="loadEntries()" class="bg-transparent text-[10px] font-black uppercase tracking-widest text-white outline-none cursor-pointer">
                        <option value="">All Topics</option>
                        <!-- Populated via JS -->
                    </select>
                    <button onclick="suggestTopicFromSearch()" class="text-brand hover:text-white transition-all ml-2" title="Suggest Topic">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                    </button>
                    <div id="topicSuggestDropdown" class="absolute top-full left-0 right-0 mt-2 bg-black/95 backdrop-blur-xl border border-white/10 rounded-2xl p-3 hidden z-[200] shadow-2xl min-w-[200px]"></div>
                </div>
                <select id="filterCategory" onchange="loadEntries()" class="bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-[10px] font-black uppercase tracking-widest text-white outline-none cursor-pointer hover:bg-white/10">
                    <option value="">All Types</option>
                    <option value="quran">Quran</option>
                    <option value="hadith">Hadith</option>
                    <option value="book">Book</option>
                    <option value="quote">Quote</option>
                </select>
            </div>
          </div>
          
          <!-- Topic Chips -->
          <div id="topicChips" class="px-8 py-3 border-b border-white/5 flex gap-3 overflow-x-auto hide-scrollbar bg-white/[0.01]">
                <!-- Populated via JS -->
          </div>
          <div id="entryList" class="flex-1 overflow-y-auto p-8 grid grid-cols-1 xl:grid-cols-2 gap-6 items-start content-start hide-scrollbar">
            <!-- Loaded via JS -->
            <div class="col-span-full h-full flex flex-col items-center justify-center text-center space-y-4 opacity-50 py-20">
                <div class="w-16 h-16 rounded-3xl bg-white/5 flex items-center justify-center border border-white/10">
                    <svg class="w-8 h-8 text-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                </div>
                <p class="text-[11px] font-black uppercase tracking-[0.3em] text-white">Select a collection to browse</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Unified Entry Modal -->
    <div id="entryModal" class="fixed inset-0 bg-black/90 backdrop-blur-md z-[500] hidden flex items-center justify-center p-6 animate-in fade-in duration-300">
      <div class="glass max-w-5xl w-full p-10 rounded-[3rem] border border-white/10 shadow-2xl space-y-8 max-h-[90vh] overflow-y-auto hide-scrollbar">
        <div class="flex justify-between items-center">
            <div>
                <h2 id="entryModalTitle" class="text-3xl font-black italic text-white tracking-tight">Add <span class="text-brand">Library Entry</span></h2>
                <p class="text-[10px] font-bold text-muted uppercase tracking-[0.2em] mt-1">Populate your intelligence database</p>
            </div>
            <button onclick="hideEntryModal()" class="w-10 h-10 rounded-2xl bg-white/5 flex items-center justify-center text-white/40 hover:bg-white/10 hover:text-white transition-all">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
            </button>
        </div>

        <input type="hidden" id="entryId">
        
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-10">
            <!-- Left Side: Source & Settings -->
            <div class="lg:col-span-4 space-y-6 bg-white/5 p-8 rounded-[2.5rem] border border-white/5">
                <div class="space-y-4">
                    <label class="text-[10px] font-black uppercase tracking-[0.3em] text-brand">Collection Name</label>
                    <select id="sourceSelect" onchange="checkNewSource()" class="w-full bg-white/10 border border-white/10 rounded-2xl px-6 py-4 text-sm text-white outline-none focus:ring-2 focus:ring-brand font-bold appearance-none">
                        <option value="">Select or Create New...</option>
                        <!-- Populated via JS -->
                    </select>
                </div>

                <div id="newSourceFields" class="space-y-6 hidden animate-in slide-in-from-top-2">
                    <div class="space-y-2">
                        <label class="text-[9px] font-black uppercase tracking-[0.2em] text-white/30">New Collection Title</label>
                        <input type="text" id="newSourceName" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm text-white outline-none focus:ring-2 focus:ring-amber-500/50" placeholder="e.g. My Personal Journal">
                    </div>
                </div>

                <div class="space-y-4">
                    <label class="text-[10px] font-black uppercase tracking-[0.3em] text-brand">Knowledge Type</label>
                    <div class="grid grid-cols-2 gap-2">
                        <button onclick="setEntryType('quran', this)" class="type-btn p-4 rounded-2xl border border-white/5 bg-white/2 hover:bg-white/5 text-[10px] font-black uppercase tracking-wider text-white/40 transition-all flex flex-col items-center gap-2">
                            <span class="text-xs">📖</span> Quran
                        </button>
                        <button onclick="setEntryType('hadith', this)" class="type-btn p-4 rounded-2xl border border-white/5 bg-white/2 hover:bg-white/5 text-[10px] font-black uppercase tracking-wider text-white/40 transition-all flex flex-col items-center gap-2">
                            <span class="text-xs">📜</span> Hadith
                        </button>
                        <button onclick="setEntryType('quote', this)" class="type-btn p-4 rounded-2xl border border-white/5 bg-white/2 hover:bg-white/5 text-[10px] font-black uppercase tracking-wider text-white/40 transition-all flex flex-col items-center gap-2">
                            <span class="text-xs">💬</span> Quote
                        </button>
                        <button onclick="setEntryType('book', this)" class="type-btn p-4 rounded-2xl border border-white/5 bg-white/2 hover:bg-white/5 text-[10px] font-black uppercase tracking-wider text-white/40 transition-all flex flex-col items-center gap-2">
                            <span class="text-xs">📚</span> Book
                        </button>
                    </div>
                    <input type="hidden" id="entryType" value="note">
                </div>
                <div id="globalToggleContainer" class="hidden py-4 border-t border-white/5 mt-6 animate-in slide-in-from-bottom-2">
                    <label class="flex items-center gap-3 cursor-pointer group">
                        <div class="relative">
                            <input type="checkbox" id="isGlobalCheckbox" class="sr-only peer">
                            <div class="w-11 h-6 bg-white/10 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
                        </div>
                        <span class="text-[10px] font-black uppercase tracking-widest text-white/40 group-hover:text-white transition-colors">System Default (Global)</span>
                    </label>
                </div>
            </div>

            <!-- Right Side: Content & Metadata -->
            <div class="lg:col-span-8 space-y-8">
                <div class="space-y-4">
                    <div class="flex justify-between items-end">
                        <label class="text-[10px] font-black uppercase tracking-[0.3em] text-brand">Knowledge Content</label>
                        <span id="charCount" class="text-[9px] font-bold text-muted tracking-widest">0 / 3000</span>
                    </div>
                    <textarea id="entryText" oninput="updateCharCount()" rows="8" class="w-full bg-white/5 border border-white/10 rounded-[2rem] px-8 py-8 text-sm text-white outline-none focus:ring-2 focus:ring-brand leading-relaxed placeholder:text-white/5" placeholder="Paste the verse, hadith, or quote text here..."></textarea>
                </div>

                <div id="dynamicMetadata" class="grid grid-cols-1 md:grid-cols-2 gap-6 animate-in fade-in">
                    <!-- Dynamic fields based on type -->
                </div>

                <div class="flex gap-4 pt-10">
                    <button onclick="hideEntryModal()" class="flex-1 py-5 bg-white/5 border border-white/10 rounded-2xl font-black text-[11px] uppercase tracking-[0.2em] text-white hover:bg-white/10 transition-all">Cancel</button>
                    <button onclick="saveEntry()" class="flex-[2] py-5 bg-brand rounded-2xl font-black text-[11px] uppercase tracking-[0.2em] text-white shadow-2xl shadow-brand/40 hover:scale-[1.02] active:scale-[0.98] transition-all">Commit Knowledge</button>
                </div>
            </div>
        </div>
      </div>
    </div>

    <!-- Library Picker Modal (Reused) -->
    <div id="libraryPickerModal" class="fixed inset-0 bg-black/90 backdrop-blur-md z-[150] hidden flex items-center justify-center p-6">
      <div class="glass max-w-2xl w-full p-8 rounded-[2.5rem] space-y-6 border border-white/10 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        <div class="flex justify-between items-center">
            <h2 class="text-xl font-black italic text-white tracking-tight">Insert <span class="text-brand">Knowledge</span></h2>
            <button onclick="closeLibraryPicker()" class="p-2 hover:bg-white/10 rounded-full transition-all text-white/40">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
            </button>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="relative flex-1">
                <input type="text" id="pickerSearch" oninput="loadPickerEntries()" placeholder="Filter knowledge..." class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-[10px] font-bold text-white outline-none focus:border-brand/40 transition-all placeholder:text-white/20">
            </div>
            <div class="flex gap-2">
                <select id="pickerTopic" onchange="loadPickerEntries()" class="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-[10px] font-bold text-white outline-none appearance-none">
                    <option value="">All Topics</option>
                </select>
                <select id="pickerType" onchange="loadPickerEntries()" class="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-[10px] font-bold text-white outline-none appearance-none font-black uppercase">
                    <option value="">All Types</option>
                    <option value="quran">Quran</option>
                    <option value="hadith">Hadith</option>
                    <option value="quote">Quote</option>
                </select>
            </div>
        </div>
        
        <div class="flex justify-end px-2">
            <button onclick="suggestPickerTopic()" class="text-[9px] font-black uppercase text-brand flex items-center gap-2 hover:text-white transition-all">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                Suggest from my prompt
            </button>
        </div>

        <div id="pickerResults" class="flex-1 overflow-y-auto space-y-3 min-h-[300px] pr-2 custom-scrollbar">
            <!-- Results via JS -->
        </div>
      </div>
    </div>

    <!-- Synonym Management Modal (Admin Only) -->
    <div id="synonymModal" class="fixed inset-0 bg-black/90 backdrop-blur-md z-[150] hidden flex items-center justify-center p-6">
      <div class="glass max-w-xl w-full p-8 rounded-[2.5rem] space-y-6 border border-brand/20 shadow-2xl flex flex-col max-h-[80vh]">
        <div class="flex justify-between items-center">
            <h2 class="text-xl font-black italic text-white tracking-tight">Topic <span class="text-brand">Synonyms</span></h2>
            <button onclick="closeSynonymModal()" class="p-2 hover:bg-white/10 rounded-full transition-all text-white/40">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
            </button>
        </div>
        
        <div class="bg-white/5 p-6 rounded-2xl border border-white/5 space-y-4">
            <div class="grid grid-cols-2 gap-4">
                <input type="text" id="syn_slug" placeholder="topic_slug" class="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-[10px] font-bold text-white outline-none">
                <input type="text" id="syn_list" placeholder="comma, separated, synonyms" class="bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-[10px] font-bold text-white outline-none">
            </div>
            <button onclick="saveSynonym()" class="w-full py-3 bg-brand text-white rounded-xl font-black text-[9px] uppercase tracking-widest hover:scale-105 transition-all">Register Synonyms</button>
        </div>

        <div id="synonymTable" class="flex-1 overflow-y-auto space-y-2 pr-2 custom-scrollbar">
            <!-- List via JS -->
        </div>
      </div>
    </div>

    <script>
      console.log("Library Neural Interface: Online");
      let libraryEntries = {}; // Global entry map for safer access
      let currentSourceId = null;
      let showGlobalOnly = false;
      let entrySearchTimeout;
      let selectedTopic = null;
      const isSuperAdmin = {is_superadmin_js};

      // --- INITIALIZATION ---
      window.addEventListener('DOMContentLoaded', () => {
          loadTopics();
          loadSources();
          loadEntries();
      });

      async function loadTopics() {
          try {
              const res = await fetch('/library/topics');
              const topics = await res.json();
              const select = document.getElementById('filterTopic');
              const chips = document.getElementById('topicChips');
              
              select.innerHTML = '<option value="">All Topics</option>';
              chips.innerHTML = '';
              
              topics.slice(0, 15).forEach(t => {
                  const opt = document.createElement('option');
                  opt.value = t.slug;
                  opt.textContent = t.slug.replace(/_/g, ' ').toUpperCase();
                  select.appendChild(opt);
                  
                  const chip = document.createElement('button');
                  chip.onclick = () => { select.value = t.slug; loadEntries(); };
                  chip.className = "flex-shrink-0 px-4 py-1.5 rounded-full bg-white/5 border border-white/10 text-[9px] font-black uppercase tracking-widest text-white/40 hover:bg-brand/20 hover:text-brand transition-all";
                  chip.textContent = t.slug.replace(/_/g, ' ');
                  chips.appendChild(chip);
              });
          } catch(e) { console.error("Topic load failed", e); }
      }
      async function loadSources() {
          const list = document.getElementById('sourceList');
          list.innerHTML = '<div class="text-center py-20 text-[10px] text-muted font-black uppercase animate-pulse">Scanning Collections...</div>';
          
          try {
              const res = await fetch(`/library/sources?scope=${showGlobalOnly ? 'global' : 'org'}`);
              const sources = await res.json();
              document.getElementById('sourceCount').textContent = sources.length;
              
              const select = document.getElementById('sourceSelect');
              if (select) select.innerHTML = '<option value="">Select or Create New...</option>';
              
              list.innerHTML = '';
              sources.forEach(s => {
                  // Update sidebar list
                  const el = document.createElement('div');
                  el.className = `p-5 rounded-3xl cursor-pointer transition-all border ${currentSourceId == s.id ? 'bg-brand border-brand ring-4 ring-brand/10' : 'bg-white/5 border-white/5 hover:bg-white/10 hover:border-white/20'}`;
                  el.onclick = () => selectSource(s);
                  el.innerHTML = `
                      <div class="flex justify-between items-start mb-1">
                          <span class="text-[10px] font-black ${currentSourceId == s.id ? 'text-white' : 'text-white'} uppercase tracking-wider">${s.name}</span>
                          ${s.org_id ? '' : '<span class="text-[7px] font-black text-brand bg-brand/10 px-2 py-0.5 rounded-full uppercase">Global</span>'}
                      </div>
                      <div class="text-[8px] font-bold text-muted uppercase tracking-widest">${s.category || 'Uncategorized'}</div>
                  `;
                  list.appendChild(el);

                   // Update select dropdown in modal
                   if (select) {
                       const opt = document.createElement('option');
                       opt.value = s.id;
                       opt.textContent = s.name;
                       select.appendChild(opt);
                   }
               });

              if (sources.length === 0) {
                  list.innerHTML = '<div class="p-10 text-center text-muted font-black text-[9px] uppercase tracking-widest">No collections found</div>';
              }
          } catch(e) {
              list.innerHTML = '<div class="text-rose-400 text-[10px] font-bold p-10">Neural transmission error</div>';
          }
      }

      function selectSource(source) {
          currentSourceId = source.id;
          loadSources();
          loadEntries();
      }

      async function loadEntries() {
          const list = document.getElementById('entryList');
          const query = document.getElementById('entrySearch').value;
          const category = document.getElementById('filterCategory').value;
          const topic = document.getElementById('filterTopic').value;
          
          list.innerHTML = '<div class="col-span-full text-center py-20 text-[10px] text-muted font-bold uppercase animate-pulse">Retrieving Knowledge Nodes...</div>';

          try {
              let url = `/library/entries?query=${encodeURIComponent(query)}`;
              if (currentSourceId) url += `&source_id=${currentSourceId}`;
              if (topic) url += `&topic=${encodeURIComponent(topic)}`;
              if (category) url += `&item_type=${encodeURIComponent(category)}`;
              if (showGlobalOnly) url += `&scope=global`;
              else url += `&scope=org`;
              
              const res = await fetch(url);
              if (!res.ok) {
                  const errData = await res.json().catch(() => ({}));
                  throw new Error(errData.detail || `HTTP ${res.status}`);
              }
              const entries = await res.json();
              
              if (!Array.isArray(entries)) {
                  console.error("API returned non-array:", entries);
                  throw new Error("Invalid response format from server");
              }

              if (entries.length === 0) {
                  list.innerHTML = `
                    <div class="col-span-full h-full flex flex-col items-center justify-center text-center space-y-4 opacity-50 py-20">
                        <p class="text-[10px] font-black uppercase tracking-[0.3em] text-white">No knowledge matches found</p>
                    </div>`;
                  return;
              }

               list.innerHTML = '';
               libraryEntries = {}; // Reset map
               entries.forEach(e => {
                    libraryEntries[e.id] = e;
                    const isGlobal = e.org_id === null;
                    const el = document.createElement('div');
                    el.className = `glass p-8 rounded-[2.5rem] border ${isGlobal ? 'border-brand/20 bg-brand/2' : 'border-white/5'} hover:border-brand/40 transition-all group relative animate-in zoom-in-95 duration-300`;
                    
                    let metaHtml = '';
                    if (e.item_type === 'quran') metaHtml = `Surah ${e.meta.surah_number}:${e.meta.verse_start}${e.meta.verse_end ? '-' + e.meta.verse_end : ''}`;
                    else if (e.item_type === 'hadith') metaHtml = `${e.meta.collection} #${e.meta.hadith_number}`;
                    else if (e.item_type === 'book') metaHtml = e.title || 'Excerpt';
                    else metaHtml = e.title || 'Note';

                    let actionsHtml = `<div class="absolute top-6 right-6 flex gap-3 opacity-0 group-hover:opacity-100 transition-all">`;
                    if (isGlobal) {
                        actionsHtml += `<button onclick="cloneEntry(${e.id})" title="Clone to my Org" class="w-10 h-10 bg-brand/10 rounded-2xl text-brand hover:bg-brand hover:text-white transition-all flex items-center justify-center shadow-lg"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></button>`;
                        if (isSuperAdmin) {
                            actionsHtml += `
                                <button onclick="openEntryModalById(${e.id})" class="w-10 h-10 bg-white/5 rounded-2xl text-white hover:bg-brand hover:text-white transition-all flex items-center justify-center shadow-lg"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></button>
                                <button onclick="deleteEntry(${e.id})" class="w-10 h-10 bg-white/5 rounded-2xl text-rose-400 hover:bg-rose-500 hover:text-white transition-all flex items-center justify-center shadow-lg"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></button>
                            `;
                        }
                    } else {
                        actionsHtml += `
                            <button onclick="openEntryModalById(${e.id})" class="w-10 h-10 bg-brand/10 rounded-2xl text-brand hover:bg-brand hover:text-white transition-all flex items-center justify-center shadow-lg"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></button>
                            <button onclick="deleteEntry(${e.id})" class="w-10 h-10 bg-white/5 rounded-2xl text-rose-400 hover:bg-rose-500 hover:text-white transition-all flex items-center justify-center shadow-lg"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></button>
                        `;
                    }
                    actionsHtml += `</div>`;

                    el.innerHTML = `
                        ${actionsHtml}
                        <div class="flex flex-col h-full justify-between space-y-6">
                            <div class="space-y-4">
                                <div class="flex items-center gap-3">
                                    <span class="w-8 h-8 rounded-xl ${isGlobal ? 'bg-brand/10 text-brand' : 'bg-white/5 text-muted'} flex items-center justify-center text-[10px] font-black">${e.item_type[0].toUpperCase()}</span>
                                    <span class="text-[10px] font-black uppercase tracking-widest ${isGlobal ? 'text-brand' : 'text-muted'}">${metaHtml}</span>
                                </div>
                                <p class="text-white/80 text-sm leading-relaxed font-medium line-clamp-6">${e.text}</p>
                            </div>
                            <div class="flex flex-wrap gap-2">
                                ${ (e.topics || []).map(t => `<span class="px-3 py-1 bg-white/5 rounded-lg text-[8px] font-black uppercase tracking-tighter text-muted transition-all hover:bg-white/10 hover:text-white cursor-default">${t}</span>`).join('') }
                            </div>
                        </div>
                    `;
                    list.appendChild(el);
              });
          } catch(e) {
              console.error("Library Neural Transmission Error (Entries):", e);
              list.innerHTML = '<div class="col-span-full py-20 text-center"><div class="text-[10px] font-black text-rose-500/50 uppercase tracking-widest">Neural transmission error</div><p class="text-[8px] text-white/20 mt-2 uppercase font-bold">' + e.message + '</p></div>';
          }
      }

      function debounceEntryQuery() {
          clearTimeout(entrySearchTimeout);
          entrySearchTimeout = setTimeout(() => loadEntries(), 500);
      }

      // --- MODAL HELPERS ---
       function openEntryModalById(id) {
           openEntryModal(libraryEntries[id]);
       }

       function openEntryModal(entry = null) {
           if (isSuperAdmin) {
               document.getElementById('globalToggleContainer').classList.remove('hidden');
               document.getElementById('isGlobalCheckbox').checked = entry ? entry.org_id === null : showGlobalOnly;
           } else {
               document.getElementById('globalToggleContainer').classList.add('hidden');
               document.getElementById('isGlobalCheckbox').checked = false;
           }
           
           document.getElementById('entryModal').classList.remove('hidden');
          const titleEl = document.getElementById('entryModalTitle');
          const idInput = document.getElementById('entryId');
          const textInput = document.getElementById('entryText');
          const sourceSelect = document.getElementById('sourceSelect');
          
          if (entry) {
              titleEl.innerHTML = 'Edit <span class="text-brand">Knowledge Node</span>';
              idInput.value = entry.id;
              textInput.value = entry.text;
              sourceSelect.value = entry.source_id;
              setEntryType(entry.item_type || 'note');
              // Populate meta based on type
              setTimeout(() => populateMetaFields(entry.meta, entry.arabic_text, entry.topics), 50);
          } else {
              titleEl.innerHTML = 'Add <span class="text-brand">Knowledge Node</span>';
              idInput.value = '';
              textInput.value = '';
              sourceSelect.value = currentSourceId || '';
              setEntryType('note');
          }
          checkNewSource();
          updateCharCount();
      }

      function hideEntryModal() { document.getElementById('entryModal').classList.add('hidden'); }

      function checkNewSource() {
          const select = document.getElementById('sourceSelect');
          const fields = document.getElementById('newSourceFields');
          if (select.value === "") {
              fields.classList.remove('hidden');
          } else {
              fields.classList.add('hidden');
          }
      }

      function setEntryType(type, btn = null) {
          document.getElementById('entryType').value = type;
          
          // Style buttons
          document.querySelectorAll('.type-btn').forEach(b => {
              b.classList.remove('bg-brand', 'text-white', 'border-brand');
              b.classList.add('bg-white/2', 'text-white/40', 'border-white/5');
          });
          
          if (btn) {
              btn.classList.add('bg-brand', 'text-white', 'border-brand');
              btn.classList.remove('text-white/40', 'border-white/5');
          } else {
              // Find button by type
              const btns = document.querySelectorAll('.type-btn');
              btns.forEach(b => {
                  if (b.textContent.toLowerCase().includes(type)) {
                      b.classList.add('bg-brand', 'text-white', 'border-brand');
                      b.classList.remove('text-white/40', 'border-white/5');
                  }
              });
          }

          renderMetaInputs(type);
      }

      function renderMetaInputs(type) {
          const container = document.getElementById('dynamicMetadata');
          container.innerHTML = '';
          
          const inputClass = "w-full bg-white/10 border border-white/10 rounded-2xl px-6 py-4 text-xs font-bold text-white outline-none focus:ring-1 focus:ring-brand placeholder:text-white/10";
          const labelClass = "text-[9px] font-black uppercase tracking-[0.2em] text-white/30 mb-2 block";
          const fullColClass = "lg:col-span-2 space-y-2";

          if (type === 'quran') {
              container.innerHTML = `
                  <div class="space-y-2">
                      <label class="${labelClass}">Surah Number</label>
                      <input type="number" id="meta_surah" class="${inputClass}" placeholder="e.g. 1">
                  </div>
                  <div class="space-y-2">
                      <label class="${labelClass}">Verse Number</label>
                      <input type="number" id="meta_verse" class="${inputClass}" placeholder="e.g. 1">
                  </div>
                  <div class="space-y-2">
                      <label class="${labelClass}">Arabic Text (Optional)</label>
                      <textarea id="meta_arabic" rows="4" class="${inputClass} text-right dir-rtl font-serif text-lg" placeholder="بسم الله..."></textarea>
                  </div>
                  <div class="space-y-2">
                      <label class="${labelClass}">Translator / Edition</label>
                      <input type="text" id="meta_translator" class="${inputClass}" placeholder="e.g. Sahih International">
                  </div>
              `;
          } else if (type === 'hadith') {
              container.innerHTML = `
                  <div class="space-y-2">
                      <label class="${labelClass}">Collection Name</label>
                      <input type="text" id="meta_collection" class="${inputClass}" placeholder="e.g. Bukhari">
                  </div>
                  <div class="space-y-2">
                      <label class="${labelClass}">Hadith Number</label>
                      <input type="text" id="meta_number" class="${inputClass}" placeholder="e.g. 1234">
                  </div>
                  <div class="space-y-2">
                      <label class="${labelClass}">Narrator</label>
                      <input type="text" id="meta_narrator" class="${inputClass}" placeholder="e.g. Abu Huraira">
                  </div>
                  <div class="space-y-2">
                      <label class="${labelClass}">Arabic Text (Optional)</label>
                      <textarea id="meta_arabic" rows="4" class="${inputClass} text-right dir-rtl font-serif text-lg" placeholder="قال رسول الله..."></textarea>
                  </div>
              `;
          } else if (type === 'book' || type === 'quote') {
              container.innerHTML = `
                  <div class="space-y-2">
                      <label class="${labelClass}">Source Title</label>
                      <input type="text" id="meta_title" class="${inputClass}" placeholder="e.g. Beyond Good and Evil">
                  </div>
                  <div class="space-y-2">
                      <label class="${labelClass}">Author / Speaker</label>
                      <input type="text" id="meta_author" class="${inputClass}" placeholder="e.g. Nietzsche">
                  </div>
                  <div class="space-y-2">
                      <label class="${labelClass}">Reference (Page/URL)</label>
                      <input type="text" id="meta_ref" class="${inputClass}" placeholder="e.g. Page 42">
                  </div>
              `;
          }
          
          // Shared Topics/Keywords field for all types
          const topicsDiv = document.createElement('div');
          topicsDiv.className = fullColClass + " pt-4 border-t border-white/5";
          topicsDiv.innerHTML = `
              <label class="${labelClass}">Semantic Topics / Keywords (for AI retrieval)</label>
              <input type="text" id="entryTopics" class="${inputClass}" placeholder="e.g. patience, gratitude, afterlife (comma separated)">
              <p class="text-[8px] font-bold text-muted uppercase mt-2 italic">Separated by commas. These help the AI find this entry for specific post themes.</p>
          `;
          container.appendChild(topicsDiv);
      }

      function populateMetaFields(meta, arabic, topics) {
          const type = document.getElementById('entryType').value;
          if (type === 'quran') {
              document.getElementById('meta_surah').value = meta.surah_number || '';
              document.getElementById('meta_verse').value = meta.verse_start || '';
              document.getElementById('meta_arabic').value = arabic || '';
              document.getElementById('meta_translator').value = meta.translator || '';
          } else if (type === 'hadith') {
              document.getElementById('meta_collection').value = meta.collection || '';
              document.getElementById('meta_number').value = meta.hadith_number || '';
              document.getElementById('meta_narrator').value = meta.narrator || '';
              document.getElementById('meta_arabic').value = arabic || '';
          } else if (type === 'book' || type === 'quote') {
              document.getElementById('meta_title').value = meta.title || '';
              document.getElementById('meta_author').value = meta.author || '';
              document.getElementById('meta_ref').value = meta.page_start || meta.url || '';
          }
      }

      function updateCharCount() {
          const text = document.getElementById('entryText').value;
          document.getElementById('charCount').textContent = `${text.length} / 3000`;
          if (text.length > 3000) {
              document.getElementById('charCount').classList.add('text-rose-400');
          } else {
              document.getElementById('charCount').classList.remove('text-rose-400');
          }
      }

      async function suggestTopicFromSearch() {
          const query = document.getElementById('entrySearch').value;
          if (!query) return alert("Type something in search first to get suggestions");
          
          const dropdown = document.getElementById('topicSuggestDropdown');
          dropdown.innerHTML = '<div class="text-[9px] font-black uppercase text-muted animate-pulse">Analyzing Library...</div>';
          dropdown.classList.remove('hidden');
          
          try {
              const res = await fetch('/library/topic-suggest', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ text: query, max: 3 })
              });
              const data = await res.json();
              if (data.suggestions && data.suggestions.length > 0) {
                  dropdown.innerHTML = data.suggestions.map(s => `
                      <button onclick="applySuggestedTopic('${s.slug}')" class="w-full text-left p-2 hover:bg-brand/10 rounded-lg group transition-all">
                          <div class="flex justify-between items-center">
                              <span class="text-[10px] font-black uppercase text-white group-hover:text-brand">${s.topic}</span>
                              <span class="text-[8px] font-bold text-muted">${Math.round(s.score * 100)}%</span>
                          </div>
                          <div class="text-[7px] font-medium text-muted uppercase tracking-tighter">${s.reason}</div>
                      </button>
                  `).join('');
              } else {
                  dropdown.innerHTML = '<div class="text-[9px] font-black uppercase text-muted">No matches found</div>';
                  setTimeout(() => dropdown.classList.add('hidden'), 2000);
              }
          } catch(e) { dropdown.classList.add('hidden'); }
      }

      function applySuggestedTopic(slug) {
          document.getElementById('filterTopic').value = slug;
          document.getElementById('topicSuggestDropdown').classList.add('hidden');
          loadEntries();
      }


      // Synonym Management
      function openSynonymModal() {
          document.getElementById('synonymModal').classList.remove('hidden');
          loadSynonyms();
      }
      function closeSynonymModal() {
          document.getElementById('synonymModal').classList.add('hidden');
      }
      async function loadSynonyms() {
          const table = document.getElementById('synonymTable');
          table.innerHTML = '<div class="text-center py-4 text-muted animate-pulse font-black text-[9px] uppercase">Retrieving Map...</div>';
          try {
              const res = await fetch('/library/synonyms');
              if (!res.ok) throw new Error(`HTTP ${res.status}`);
              const data = await res.json();
              table.innerHTML = data.map(s => `
                  <div class="flex justify-between items-center p-4 bg-white/5 rounded-xl border border-white/5 group">
                      <div>
                          <div class="text-[9px] font-black text-brand uppercase">${s.slug}</div>
                          <div class="text-[8px] font-bold text-white/40 uppercase">${s.synonyms.join(', ')}</div>
                      </div>
                      <button onclick="deleteSynonym('${s.slug}')" class="p-2 text-rose-400 opacity-0 group-hover:opacity-100 transition-all hover:bg-rose-500/20 rounded-lg">
                          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                      </button>
                  </div>
              `).join('');
          } catch(e) { console.error("Synonym load failed", e); }
      }
      async function saveSynonym() {
          const slug = document.getElementById('syn_slug').value.trim();
          const list = document.getElementById('syn_list').value.split(',').map(s => s.trim()).filter(s => s);
          if (!slug || !list.length) return alert("Slug and synonyms required");
          try {
              const res = await fetch('/library/synonyms', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ slug, synonyms: list })
              });
              if (res.ok) {
                  document.getElementById('syn_slug').value = '';
                  document.getElementById('syn_list').value = '';
                  loadSynonyms();
              } else {
                  const err = await res.json();
                  alert(`Failed to save synonym: ${err.detail || 'Unknown error'}`);
              }
          } catch(e) { console.error("Synonym save failed", e); }
      }
      async function deleteSynonym(slug) {
          if (!confirm(`Delete synonyms for ${slug}?`)) return;
          try {
              const res = await fetch(`/library/synonyms/${slug}`, { method: 'DELETE' });
              if (res.ok) loadSynonyms();
              else {
                  const err = await res.json();
                  alert(`Failed to delete synonym: ${err.detail || 'Unknown error'}`);
              }
          } catch(e) { console.error("Synonym delete failed", e); }
      }

      async function saveEntry() {
          const id = document.getElementById('entryId').value;
          const type = document.getElementById('entryType').value;
          const sourceId = document.getElementById('sourceSelect').value;
          const newSourceName = document.getElementById('newSourceName').value;
          
          const meta = {};
          let arabic = "";
          
          if (type === 'quran') {
              meta.surah_number = parseInt(document.getElementById('meta_surah').value);
              meta.verse_with_number = document.getElementById('meta_verse').value; // Keep as string for flexibility
              meta.verse_start = parseInt(document.getElementById('meta_verse').value);
              meta.translator = document.getElementById('meta_translator').value;
              arabic = document.getElementById('meta_arabic').value;
          } else if (type === 'hadith') {
              meta.collection = document.getElementById('meta_collection').value;
              meta.hadith_number = document.getElementById('meta_number').value;
              meta.narrator = document.getElementById('meta_narrator').value;
              arabic = document.getElementById('meta_arabic').value;
          } else if (type === 'book' || type === 'quote') {
              meta.title = document.getElementById('meta_title').value;
              meta.author = document.getElementById('meta_author').value;
              meta.page_start = document.getElementById('meta_ref').value;
          }

          const payload = {
              source_id: sourceId ? parseInt(sourceId) : null,
              source_name: sourceId ? null : newSourceName,
              item_type: type,
              text: document.getElementById('entryText').value,
              arabic_text: arabic,
              meta: meta,
              topics: document.getElementById('entryTopics').value.split(',').map(t => t.trim()).filter(t => t !== "")
          };

          if (!payload.source_id && !payload.source_name) return alert("Please select or name a collection");
          if (!payload.text) return alert("Content text is required");

           const isGlobal = document.getElementById('isGlobalCheckbox').checked;
           const method = id ? 'PATCH' : 'POST';
           let url = id ? `/library/entries/${id}` : `/library/entries`;
           
           if (isGlobal && isSuperAdmin) {
               url = id ? `/api/admin/library/global/entries/${id}` : `/api/admin/library/global/entries`;
           }

          try {
              const res = await fetch(url, {
                  method: method,
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify(payload)
              });
              if (res.ok) {
                  const saved = await res.json();
                  currentSourceId = saved.source_id;
                  hideEntryModal();
                  loadSources();
                  loadEntries();
              } else {
                  const err = await res.json();
                  alert(`Neural sync failed: ${err.detail || 'Unknown error'}`);
              }
          } catch(e) { alert('Transmission error: ' + e.message); }
      }

      let pickerTargetId = null;

      function openLibraryPicker(targetId) {
          pickerTargetId = targetId;
          document.getElementById('libraryPickerModal').classList.remove('hidden');
          loadPickerTopics();
          loadPickerEntries();
      }
      
      function closeLibraryPicker() {
          document.getElementById('libraryPickerModal').classList.add('hidden');
          pickerTargetId = null;
      }

      async function loadPickerTopics() {
          try {
              const res = await fetch('/library/topics');
              const topics = await res.json();
              const select = document.getElementById('pickerTopic');
              select.innerHTML = '<option value="">All Topics</option>';
              topics.forEach(t => {
                  const opt = document.createElement('option');
                  opt.value = t.slug;
                  opt.textContent = t.slug.replace(/_/g, ' ').toUpperCase();
                  select.appendChild(opt);
              });
          } catch(e) {}
      }

      async function loadPickerEntries() {
          const query = document.getElementById('pickerSearch').value;
          const topic = document.getElementById('pickerTopic').value;
          const type = document.getElementById('pickerType').value;
          const list = document.getElementById('pickerResults');
          
          list.innerHTML = '<div class="text-center py-10 text-[9px] font-black uppercase text-muted animate-pulse">Scanning Neural Library...</div>';
          
          try {
              let url = `/library/entries?query=${encodeURIComponent(query)}&scope=all`;
              if (topic) url += `&topic=${encodeURIComponent(topic)}`;
              if (type) url += `&item_type=${encodeURIComponent(type)}`;
              
              const res = await fetch(url);
              let entries = await res.json();
              
              if (entries.length === 0) {
                  list.innerHTML = '<div class="text-center py-10 text-[9px] font-black uppercase text-muted opacity-40">No knowledge found for this topic</div>';
                  return;
              }
              
              list.innerHTML = '';
              entries.forEach(e => {
                  const div = document.createElement('div');
                  div.className = "p-4 bg-white/5 border border-white/5 rounded-2xl hover:bg-white/10 hover:border-brand/30 transition-all cursor-pointer space-y-2";
                  
                  let scope = "SYSTEM";
                  let scopeClass = "bg-brand/10 text-brand";
                  if (e.org_id) { scope = "WORKSPACE"; scopeClass = "bg-white/10 text-white/40"; }
                  if (e.owner_user_id) { scope = "PERSONAL"; scopeClass = "bg-amber-500/10 text-amber-500"; }

                  div.onclick = () => selectPickerEntry(e);
                  div.innerHTML = `
                      <div class="flex justify-between items-center">
                        <div class="flex gap-2">
                            <span class="px-2 py-0.5 rounded-md ${scopeClass} text-[7px] font-black uppercase">${scope}</span>
                            <span class="text-[7px] font-black text-white/30 uppercase tracking-widest">${e.item_type}</span>
                        </div>
                        <span class="text-[8px] font-black text-muted">${e.topic || ''}</span>
                      </div>
                      <p class="text-[10px] text-white/70 line-clamp-2 leading-relaxed font-medium">${e.text.substring(0, 150)}...</p>
                  `;
                  list.appendChild(div);
              });
          } catch(e) {}
      }

      function selectPickerEntry(entry) {
          const target = document.getElementById(pickerTargetId);
          if (target) {
              let credit = "";
              if (entry.item_type === 'hadith') {
                  credit = `\n\n[Reference: ${entry.meta.collection || 'Hadith'} - #${entry.meta.hadith_number || 'N/A'}]`;
              } else if (entry.item_type === 'quran') {
                  credit = `\n\n[Quran ${entry.meta.surah_number}:${entry.meta.verse_with_number || entry.meta.verse_start}]`;
              } else if (entry.item_type === 'book') {
                  credit = `\n\n[Source: ${entry.meta.title || 'Book'} by ${entry.meta.author || 'Unknown'}]`;
              }
              
              target.value = entry.text + credit;
          }
          closeLibraryPicker();
      }

       function toggleGlobalView(global) {
          showGlobalOnly = global;
          const orgBtn = document.getElementById('orgViewBtn');
          const globalBtn = document.getElementById('globalViewBtn');
          
          if (global) {
              if (globalBtn) globalBtn.className = "flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter transition-all bg-brand text-white shadow-lg";
              if (orgBtn) orgBtn.className = "flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter transition-all text-white/40 hover:text-white";
          } else {
              if (orgBtn) orgBtn.className = "flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter transition-all bg-brand text-white shadow-lg";
              if (globalBtn) globalBtn.className = "flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter transition-all text-white/40 hover:text-white";
          }
          
          currentSourceId = null;
          loadSources();
          loadEntries();
      }

      function toggleManageMode() {
          console.log("Manager mode restricted to superadmin neural interface");
      }

      async function deleteEntry(id) {
          if (!confirm('Permanently purge this knowledge node?')) return;
          try {
              const res = await fetch(`/library/entries/${id}`, { method: 'DELETE' });
              if (res.ok) loadEntries();
          } catch(e) { alert('Network error'); }
      }

      async function cloneEntry(id) {
          if (!confirm('Copy this global template to your organization?')) return;
          try {
              const res = await fetch(`/library/entries/${id}/clone`, { method: 'POST' });
              if (res.ok) {
                  alert('Cloned successfully! You can now find it in your collection.');
                  loadEntries();
              } else {
                  const err = await res.json();
                  alert(`Clone failed: ${err.detail}`);
              }
          } catch(e) { alert('Network error'); }
      }
    </script>
    """
    
    return APP_LAYOUT_HTML.replace("{title}", "Library")\
                          .replace("{user_name}", user.name or user.email)\
                          .replace("{org_name}", org.name if org else "Personal Workspace")\
                          .replace("{admin_link}", admin_link)\
                          .replace("{active_dashboard}", "")\
                          .replace("{active_calendar}", "")\
                          .replace("{active_automations}", "")\
                          .replace("{active_library}", "active")\
                          .replace("{active_media}", "")\
                          .replace("{content}", content.replace("{superadmin_controls}", f"""
            <div class="flex p-1 bg-white/5 rounded-xl border border-white/10 gap-2">
                <button onclick="toggleGlobalView(false)" id="orgViewBtn" class="flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter transition-all bg-brand text-white shadow-lg">Org</button>
                <button onclick="toggleGlobalView(true)" id="globalViewBtn" class="flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter transition-all text-white/40 hover:text-white">System</button>
                <button onclick="openSynonymModal()" class="px-3 py-1.5 border border-brand/20 rounded-lg text-brand hover:bg-brand hover:text-white transition-all">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                </button>
            </div>
            """ if user.is_superadmin else ""))\
                          .replace("{is_superadmin_js}", "true" if user.is_superadmin else "false")\
                          .replace("{account_options}", "")

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
