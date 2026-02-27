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
        if (tab === 'my_library') {
            myLibTab.classList.add('text-white', 'border-brand');
            myLibTab.classList.remove('text-muted', 'border-transparent');
            defaultTab.classList.add('text-muted', 'border-transparent');
            defaultTab.classList.remove('text-white', 'border-brand');
        } else {
            defaultTab.classList.add('text-white', 'border-brand');
            defaultTab.classList.remove('text-muted', 'border-transparent');
            myLibTab.classList.add('text-muted', 'border-transparent');
            myLibTab.classList.remove('text-white', 'border-brand');
        }

        const content = document.getElementById('libraryDrawerContent');
        content.innerHTML = '<div class="text-center py-10"><div class="animate-spin w-6 h-6 border-2 border-brand border-t-transparent rounded-full mx-auto"></div></div>';
        
        try {
            const endpoint = tab === 'my_library' ? '/library' : '/library/all_prebuilt';
            const res = await fetch(endpoint);
            const docs = await res.json();
            
            content.innerHTML = '';
            docs.forEach(doc => {
                const div = document.createElement('div');
                div.className = 'glass p-4 rounded-xl border border-white/5 hover:border-brand/40 cursor-pointer transition-all';
                
                // Handle different schemas between My Library (db) and Prebuilt (json)
                const docTitle = doc.title || doc.name || 'Untitled';
                const docSource = doc.source_type || 'prebuilt pack';
                const docText = doc.text || doc.description || '';
                
                div.innerHTML = `
                    <div class="text-[10px] font-black text-white uppercase tracking-wider">${docTitle}</div>
                    <div class="text-[8px] font-bold text-muted uppercase mt-1">${docSource} source</div>
                `;
                div.onclick = () => selectLibraryDoc({
                    id: doc.id || doc.name, 
                    title: docTitle, 
                    text: docText
                });
                content.appendChild(div);
            });

            if (docs.length === 0) {
                content.innerHTML = `<div class="text-center py-10 text-muted text-[10px] font-black uppercase">No ${tab === 'my_library' ? 'custom documents' : 'prebuilt packs'} found.</div>`;
            }
        } catch(e) {
            content.innerHTML = '<div class="text-center py-10 text-rose-400 text-[10px] font-black uppercase">Failed to load library.</div>';
        }
    }

    function closeLibraryDrawer() {
        document.getElementById('libraryDrawer').classList.add('translate-x-full');
    }

    function selectLibraryDoc(doc) {
        document.getElementById('studioSourceText').value = doc.text || "";
        document.getElementById('studioReference').value = doc.title || "";
        document.getElementById('studioLibraryItemId').value = doc.id;
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
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Core Topic Prompt</label>
              <textarea id="editTopic" rows="3" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand"></textarea>
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
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Manual Seed Text</label>
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
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Core Topic Prompt</label>
              <textarea id="newTopic" rows="3" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand" placeholder="Describe the focus of this automation..."></textarea>
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
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Manual Seed Text</label>
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
        document.getElementById('editSeedMode').value = data.seed_mode || 'none';
        document.getElementById('editSeedText').value = data.seed_text;
        document.getElementById('editTime').value = data.time;
        
        const scope = data.library_scope || [];
        document.getElementById('editScopePrebuilt').checked = scope.includes('prebuilt');
        document.getElementById('editScopeOrg').checked = scope.includes('org_library');

        toggleSeedText();
        document.getElementById('editModal').classList.remove('hidden');
      }}

      function hideEditModal() {{
        document.getElementById('editModal').classList.add('hidden');
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
    if is_admin:
        manage_btn = f"""
        <button onclick="toggleManageMode()" id="manageToggleBtn" class="px-6 py-3 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest text-brand hover:bg-brand/10 transition-all flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
            Manager Mode
        </button>
        """

    content = f"""
    <style>
        .dir-rtl {{ direction: rtl; unicode-bidi: bidi-override; }}
        .font-serif {{ font-family: 'Amiri', 'Traditional Arabic', serif; }}
    </style>
    <div id="standardView" class="space-y-8">
      <div class="flex justify-between items-end">
        <div>
          <h1 class="text-3xl font-black italic tracking-tight text-white">Source <span class="text-brand">Library</span></h1>
          <p class="text-[10px] font-black text-muted uppercase tracking-[0.3em]">Knowledge Base Management</p>
        </div>
        <div id="actionButtons" class="flex gap-4">
          {manage_btn}
          <input type="file" id="pdfUpload" class="hidden" accept=".pdf,.txt" onchange="handleFileUpload(this)">
          <button onclick="document.getElementById('pdfUpload').click()" class="px-6 py-3 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest text-white hover:bg-white/10 transition-all">Upload PDF/TXT</button>
          <button onclick="showUrlModal()" class="px-6 py-3 bg-brand rounded-xl font-black text-[10px] uppercase tracking-widest text-white shadow-xl shadow-brand/20">Add URL Source</button>
        </div>
      </div>

      <!-- Tab Switcher -->
      <div class="flex border-b border-white/5">
        <button onclick="switchTab('user')" id="tabUser" class="px-8 py-4 text-[10px] font-black uppercase tracking-[0.2em] text-white border-b-2 border-brand relative transition-all">My Knowledge Base</button>
        <button onclick="switchTab('default')" id="tabDefault" class="px-8 py-4 text-[10px] font-black uppercase tracking-[0.2em] text-muted border-b-2 border-transparent hover:text-white transition-all">Default Library</button>
      </div>

      <div id="paneUser" class="space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 gap-4">
          {docs_html or '<div class="col-span-full py-20 text-center glass rounded-3xl"><p class="text-muted font-black text-[10px] uppercase tracking-widest">Your library is empty. Upload your first source to begin grounded generation.</p></div>'}
        </div>
      </div>

      <div id="paneDefault" class="hidden animate-in fade-in slide-in-from-bottom-2 duration-500">
        <div class="max-w-3xl">
          {prebuilt_html or '<div class="py-20 text-center glass rounded-3xl"><p class="text-muted font-black text-[10px] uppercase tracking-widest">Default prebuilt packs are currently unavailable.</p></div>'}
        </div>
      </div>
    </div>

    <!-- ADMIN MANAGER VIEW -->
    <div id="manageView" class="hidden space-y-8">
        <div class="flex justify-between items-end">
            <div>
              <h1 class="text-3xl font-black italic tracking-tight text-white">Admin <span class="text-brand">Library Manager</span></h1>
              <p class="text-[10px] font-black text-muted uppercase tracking-[0.3em]">System Content Curation</p>
            </div>
            <button onclick="toggleManageMode()" class="px-6 py-3 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest text-white hover:bg-white/10 transition-all">Return to Library</button>
        </div>

        <div class="flex gap-8 h-[70vh]">
            <!-- Left Pane: Sources -->
            <div class="w-1/3 glass rounded-[2.5rem] flex flex-col overflow-hidden">
                <div class="p-6 border-b border-white/10 flex justify-between items-center">
                    <h3 class="text-xs font-black uppercase tracking-widest text-white">Content Sources</h3>
                    <button onclick="openSourceModal()" class="w-8 h-8 bg-brand/20 text-brand rounded-lg flex items-center justify-center hover:bg-brand/30 transition-all">+</button>
                </div>
                <div id="sourceList" class="flex-1 overflow-y-auto p-4 space-y-2">
                    <!-- Loaded via JS -->
                </div>
            </div>

            <!-- Right Pane: Entries -->
            <div class="flex-1 glass rounded-[2.5rem] flex flex-col overflow-hidden">
                <div class="p-6 border-b border-white/10 flex justify-between items-center">
                    <div class="flex items-center gap-6">
                        <h3 class="text-xs font-black uppercase tracking-widest text-white">Library Entries</h3>
                        <div class="relative">
                            <input type="text" id="entrySearch" oninput="debounceEntryQuery()" placeholder="Search entries..." class="bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-[10px] font-bold text-white outline-none focus:border-brand/40 w-48">
                        </div>
                    </div>
                    <button id="addEntryBtn" onclick="openEntryModal()" class="px-4 py-2 bg-brand rounded-xl font-black text-[10px] uppercase tracking-widest text-white disabled:opacity-50" disabled>+ Add Entry</button>
                </div>
                <div id="entryList" class="flex-1 overflow-y-auto p-4 space-y-3">
                    <div class="h-full flex items-center justify-center text-muted font-black text-[10px] uppercase tracking-widest">Select a source to view entries</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Source Modal -->
    <div id="sourceModal" class="fixed inset-0 bg-black/80 backdrop-blur-sm z-[200] hidden flex items-center justify-center p-6">
      <div class="glass max-w-lg w-full p-10 rounded-[2.5rem] space-y-6">
        <h2 id="sourceModalTitle" class="text-2xl font-black italic text-white tracking-tight">Add <span class="text-brand">Source</span></h2>
        <input type="hidden" id="sourceId">
        <div class="space-y-4">
          <div class="space-y-1">
            <label class="text-[10px] font-black uppercase tracking-widest text-muted">Reference Book / Source Name</label>
            <input type="text" id="sourceName" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand" placeholder="e.g. Quran, Sahih al-Bukhari, or Book Title">
          </div>
          <div class="space-y-1">
            <label class="text-[10px] font-black uppercase tracking-widest text-muted">Category</label>
            <input type="text" id="sourceCategory" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand" placeholder="e.g. Hadith">
          </div>
          <div class="space-y-1">
            <label class="text-[10px] font-black uppercase tracking-widest text-muted">Source Type</label>
            <select id="sourceType" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand text-white appearance-none">
              <option value="manual_library">Manual Library</option>
              <option value="rss">RSS Feed</option>
              <option value="url_list">URL List</option>
            </select>
          </div>
          <div class="flex items-center gap-3">
            <input type="checkbox" id="sourceIsGlobal" class="w-4 h-4 rounded border-white/10 bg-white/5 text-brand focus:ring-brand">
            <label for="sourceIsGlobal" class="text-[10px] font-black uppercase tracking-widest text-white">Make Global (Admin Only)</label>
          </div>
        </div>
        <div class="flex gap-4 pt-4">
          <button onclick="hideSourceModal()" class="flex-1 py-4 bg-white/5 border border-white/10 rounded-xl font-black text-[10px] uppercase tracking-widest">Cancel</button>
          <button onclick="saveSource()" class="flex-[2] py-4 bg-brand rounded-xl font-black text-[10px] uppercase tracking-widest text-white shadow-lg shadow-brand/20">Save Source</button>
        </div>
      </div>
    </div>

    <!-- Entry Modal -->
    <div id="entryModal" class="fixed inset-0 bg-black/80 backdrop-blur-sm z-[200] hidden flex items-center justify-center p-6">
      <div class="glass max-w-4xl w-full p-10 rounded-[2.5rem] space-y-6 max-h-[95vh] overflow-y-auto">
        <div class="flex justify-between items-center mb-4">
            <h2 id="entryModalTitle" class="text-2xl font-black italic text-white tracking-tight">Add <span class="text-brand">Library Entry</span></h2>
            <div class="flex items-center gap-4">
                <label class="text-[10px] font-black uppercase tracking-widest text-muted">Type</label>
                <select id="entryType" onchange="updateEntryFields()" class="bg-white/5 border border-white/10 rounded-xl px-4 py-2 text-xs outline-none focus:ring-2 focus:ring-brand text-white appearance-none">
                    <option value="note">Basic Note</option>
                    <option value="quran">Quran Verse</option>
                    <option value="hadith">Hadith Narration</option>
                    <option value="book">Book Excerpt</option>
                </select>
            </div>
        </div>
        
        <input type="hidden" id="entryId">
        
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <!-- Main Content Pane (Chat Style) -->
          <div class="lg:col-span-2 space-y-6">
            <div class="space-y-1">
              <label id="mainTextLabel" class="text-[10px] font-black uppercase tracking-widest text-muted">Primary Knowledge (English)</label>
              <div class="relative">
                <textarea id="entryText" rows="12" class="w-full bg-white/5 border border-white/10 rounded-3xl px-8 py-6 text-sm outline-none focus:ring-2 focus:ring-brand leading-relaxed placeholder:text-white/10" placeholder="Type or paste the primary knowledge resource here..."></textarea>
                <div class="absolute bottom-4 right-6 text-[8px] font-bold text-white/20 uppercase tracking-widest pointer-events-none">Spectral Node</div>
              </div>
            </div>
            
            <div class="space-y-1">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Original Scripture (Arabic / Optional)</label>
              <textarea id="entryArabic" rows="5" class="w-full bg-white/5 border border-white/10 rounded-3xl px-8 py-6 text-lg min-h-[120px] outline-none focus:ring-2 focus:ring-brand text-right dir-rtl font-serif leading-loose" placeholder="أدخل النص الأصلي هنا..."></textarea>
            </div>
          </div>

          <!-- Metadata Pane -->
          <div class="space-y-6 flex flex-col">
            <div id="metaFields" class="flex-1 bg-white/5 p-8 rounded-[2.5rem] border border-white/5 space-y-6">
                <!-- Dynamic fields -->
            </div>
            
            <div class="bg-brand/10 p-4 rounded-2xl border border-brand/20">
                <p class="text-[9px] font-bold text-brand uppercase tracking-widest leading-relaxed">
                    <span class="text-white">Note:</span> Knowledge nodes added here will be used for grounded AI generation and social content.
                </p>
            </div>
            
            <div class="flex flex-col gap-3 pt-4">
                <button onclick="saveEntry()" class="w-full py-5 bg-brand rounded-2xl font-black text-[10px] uppercase tracking-widest text-white shadow-xl shadow-brand/30 hover:bg-brand-hover transition-all">Save Entry</button>
                <button onclick="hideEntryModal()" class="w-full py-4 bg-white/5 border border-white/10 rounded-2xl font-black text-[10px] uppercase tracking-widest hover:bg-white/10 transition-all">Cancel</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <script>
      let currentSourceId = null;
      let manageMode = false;
      let entrySearchTimeout;

      function toggleManageMode() {{
          manageMode = !manageMode;
          if (manageMode) {{
              document.getElementById('standardView').classList.add('hidden');
              document.getElementById('manageView').classList.remove('hidden');
              loadSources();
          }} else {{
              document.getElementById('standardView').classList.remove('hidden');
              document.getElementById('manageView').classList.add('hidden');
          }}
      }}

      async function loadSources() {{
          const list = document.getElementById('sourceList');
          list.innerHTML = '<div class="text-center py-10 text-[10px] text-muted font-bold uppercase animate-pulse">Loading sources...</div>';
          
          try {{
              const res = await fetch('/api/admin/library/sources?scope=all');
              const sources = await res.json();
              
              list.innerHTML = '';
              sources.forEach(s => {{
                  const el = document.createElement('div');
                  el.className = `p-5 rounded-3xl cursor-pointer transition-all border ${{currentSourceId == s.id ? 'bg-brand border-brand ring-4 ring-brand/20' : 'bg-white/5 border-white/5 hover:bg-white/10'}}`;
                  el.onclick = () => selectSource(s);
                  el.innerHTML = `
                      <div class="flex justify-between items-start mb-1">
                          <span class="text-[10px] font-black ${{currentSourceId == s.id ? 'text-white' : 'text-white'}} uppercase tracking-wider">${{s.name}}</span>
                          <span class="text-[8px] font-black ${{s.org_id ? 'text-amber-400 bg-amber-400/10' : 'text-brand bg-brand/10'}} px-2 py-0.5 rounded-full uppercase">${{s.org_id ? 'Org' : 'Global'}}</span>
                      </div>
                      <div class="text-[8px] font-bold text-muted uppercase tracking-widest mb-3">${{s.category || 'Uncategorized'}}</div>
                      <div class="flex gap-4 pt-2 border-t border-white/10">
                           <button onclick="event.stopPropagation(); openSourceModal(${{JSON.stringify(s).replace(/"/g, '&quot;')}})" class="text-[8px] font-black text-muted hover:text-white uppercase transition-colors">Edit</button>
                           <button onclick="event.stopPropagation(); deleteSource(${{s.id}})" class="text-[8px] font-black text-rose-400 hover:text-rose-200 uppercase transition-colors">Delete</button>
                      </div>
                  `;
                  list.appendChild(el);
              }});
          }} catch(e) {{
              list.innerHTML = '<div class="text-rose-400 text-[10px] font-bold p-4">Failed to load sources</div>';
          }}
      }}

      function selectSource(source) {{
          currentSourceId = source.id;
          document.getElementById('addEntryBtn').disabled = false;
          loadSources();
          loadEntries();
      }}

      async function loadEntries() {{
          const list = document.getElementById('entryList');
          const query = document.getElementById('entrySearch').value;
          list.innerHTML = '<div class="text-center py-20 text-[10px] text-muted font-bold uppercase animate-pulse">Scanning knowledge nodes...</div>';

          try {{
              const res = await fetch(`/api/admin/library/entries?source_id=${{currentSourceId}}&query=${{encodeURIComponent(query)}}`);
              const entries = await res.json();
              
              if (entries.length === 0) {{
                  list.innerHTML = '<div class="h-full flex items-center justify-center text-muted font-black text-[10px] uppercase tracking-widest">No spectral matches in this source</div>';
                  return;
              }}

              list.innerHTML = '';
              entries.forEach(e => {{
                  const el = document.createElement('div');
                  el.className = 'glass p-6 rounded-[2rem] border border-white/5 hover:border-brand/30 transition-all group relative';
                  
                  let metaTitle = 'Reference';
                  if (e.item_type === 'quran') metaTitle = `Surah ${{e.meta.surah_number}}:${{e.meta.verse_start}}${{e.meta.verse_end ? '-' + e.meta.verse_end : ''}}`;
                  else if (e.item_type === 'hadith') metaTitle = `${{e.meta.collection}} #${{e.meta.hadith_number}}`;
                  else if (e.item_type === 'book') metaTitle = e.title || 'Excerpt';

                  el.innerHTML = `
                      <div class="flex justify-between items-start mb-4">
                          <span class="text-[9px] font-black text-brand uppercase tracking-[0.25em]">${{e.item_type}} • ${{metaTitle}}</span>
                          <div class="flex gap-3 opacity-0 group-hover:opacity-100 transition-all transform translate-x-2 group-hover:translate-x-0">
                              <button onclick="openEntryModal(${{JSON.stringify(e).replace(/"/g, '&quot;')}})" class="p-2 bg-white/5 rounded-lg text-white hover:bg-brand hover:text-white transition-all"><svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></button>
                              <button onclick="deleteEntry(${{e.id}})" class="p-2 bg-white/5 rounded-lg text-rose-400 hover:bg-rose-500 hover:text-white transition-all"><svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></button>
                          </div>
                      </div>
                      <p class="text-[11px] font-medium text-white/90 leading-relaxed">${{e.text}}</p>
                      ${{e.arabic_text ? `<div class="mt-4 p-4 bg-white/2 rounded-2xl border-r-4 border-brand/40"><p class="text-sm text-right font-serif text-white/70 dir-rtl leading-loose">${{e.arabic_text}}</p></div>` : ''}}
                  `;
                  list.appendChild(el);
              }});
          }} catch(e) {{
              list.innerHTML = '<div class="text-rose-400 text-[10px] font-bold p-10">Neural transmission error</div>';
          }}
      }}

      function debounceEntryQuery() {{
          clearTimeout(entrySearchTimeout);
          entrySearchTimeout = setTimeout(() => {{ if (currentSourceId) loadEntries(); }}, 500);
      }}

      // --- SOURCE HELPERS ---
      function openSourceModal(source = null) {{
          document.getElementById('sourceModal').classList.remove('hidden');
          if (source) {{
              document.getElementById('sourceModalTitle').innerHTML = 'Edit <span class="text-brand">Source</span>';
              document.getElementById('sourceId').value = source.id;
              document.getElementById('sourceName').value = source.name;
              document.getElementById('sourceCategory').value = source.category || '';
              document.getElementById('sourceType').value = source.source_type;
              document.getElementById('sourceIsGlobal').checked = source.org_id === null;
          }} else {{
              document.getElementById('sourceModalTitle').innerHTML = 'Add <span class="text-brand">Source</span>';
              document.getElementById('sourceId').value = '';
              document.getElementById('sourceName').value = '';
              document.getElementById('sourceCategory').value = '';
              document.getElementById('sourceIsGlobal').checked = false;
          }}
      }}

      function hideSourceModal() {{ document.getElementById('sourceModal').classList.add('hidden'); }}

      async function saveSource() {{
          const id = document.getElementById('sourceId').value;
          const payload = {{
              name: document.getElementById('sourceName').value,
              category: document.getElementById('sourceCategory').value,
              source_type: document.getElementById('sourceType').value,
              enabled: true
          }};
          const isGlobal = document.getElementById('sourceIsGlobal').checked;
          
          const method = id ? 'PATCH' : 'POST';
          const url = id ? `/api/admin/library/sources/${{id}}` : `/api/admin/library/sources?is_global=${{isGlobal}}`;

          try {{
              const res = await fetch(url, {{
                  method: method,
                  headers: {{ 'Content-Type': 'application/json' }},
                  body: JSON.stringify(payload)
              }});
              if (res.ok) {{
                  hideSourceModal();
                  loadSources();
              }} else alert('Operation failed');
          }} catch(e) {{ alert('Network error'); }}
      }}

      async function deleteSource(id) {{
          if (!confirm('Destroy this source and all its knowledge children?')) return;
          try {{
              const res = await fetch(`/api/admin/library/sources/${{id}}`, {{ method: 'DELETE' }});
              if (res.ok) loadSources();
          }} catch(e) {{ alert('Network error'); }}
      }}

      // --- ENTRY HELPERS ---
      function openEntryModal(entry = null) {{
          document.getElementById('entryModal').classList.remove('hidden');
          if (entry) {{
              document.getElementById('entryModalTitle').innerHTML = 'Edit <span class="text-brand">Entry</span>';
              document.getElementById('entryId').value = entry.id;
              document.getElementById('entryType').value = entry.item_type;
              document.getElementById('entryText').value = entry.text;
              document.getElementById('entryArabic').value = entry.arabic_text || '';
              updateEntryFields(entry.meta);
          }} else {{
              document.getElementById('entryModalTitle').innerHTML = 'Add <span class="text-brand">Entry</span>';
              document.getElementById('entryId').value = '';
              document.getElementById('entryType').value = 'note';
              document.getElementById('entryText').value = '';
              document.getElementById('entryArabic').value = '';
              updateEntryFields();
          }}
      }}

      function hideEntryModal() {{ document.getElementById('entryModal').classList.add('hidden'); }}

      function updateEntryFields(meta = {{}}) {{
          const type = document.getElementById('entryType').value;
          const container = document.getElementById('metaFields');
          container.innerHTML = `<h4 class="text-[10px] font-black uppercase tracking-widest text-brand mb-4">Node Metadata</h4>`;
          
          if (type === 'quran') {{
              container.innerHTML += `
                  <div class="space-y-1">
                      <label class="text-[8px] font-black uppercase text-muted">Surah / Book Name</label>
                      <input type="text" id="meta_surah_name" value="${{meta.surah_name || 'Quran'}}" class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-xs outline-none focus:ring-1 focus:ring-brand">
                  </div>
                  <div class="grid grid-cols-2 gap-4">
                    <div class="space-y-1">
                        <label class="text-[8px] font-black uppercase text-muted">Surah #</label>
                        <input type="number" id="meta_surah_number" value="${{meta.surah_number || ''}}" class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-xs outline-none focus:ring-1 focus:ring-brand">
                    </div>
                    <div class="space-y-1">
                        <label class="text-[8px] font-black uppercase text-muted">Verse #</label>
                        <input type="number" id="meta_verse_start" value="${{meta.verse_start || ''}}" class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-xs outline-none focus:ring-1 focus:ring-brand">
                    </div>
                  </div>
                  <div class="space-y-1">
                      <label class="text-[8px] font-black uppercase text-muted">Translator</label>
                      <input type="text" id="meta_translator" value="${{meta.translator || ''}}" class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-xs outline-none focus:ring-1 focus:ring-brand" placeholder="e.g. Sahih International">
                  </div>
              `;
          }} else if (type === 'hadith') {{
              container.innerHTML += `
                  <div class="space-y-1">
                      <label class="text-[8px] font-black uppercase text-muted">Collection / Source Name</label>
                      <input type="text" id="meta_collection" value="${{meta.collection || ''}}" class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-xs outline-none focus:ring-1 focus:ring-brand" placeholder="e.g. Sahih Al-Bukhari">
                  </div>
                  <div class="space-y-1">
                      <label class="text-[8px] font-black uppercase text-muted">Hadith #</label>
                      <input type="text" id="meta_hadith_number" value="${{meta.hadith_number || ''}}" class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-xs outline-none focus:ring-1 focus:ring-brand">
                  </div>
                  <div class="space-y-1">
                      <label class="text-[8px] font-black uppercase text-muted">Narrator</label>
                      <input type="text" id="meta_narrator" value="${{meta.narrator || ''}}" class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-xs outline-none focus:ring-1 focus:ring-brand" placeholder="e.g. Abu Huraira">
                  </div>
              `;
          }} else if (type === 'book' || type === 'article') {{
               container.innerHTML += `
                  <div class="space-y-1">
                      <label class="text-[8px] font-black uppercase text-muted">Title / Source Name</label>
                      <input type="text" id="meta_title" value="${{meta.title || ''}}" class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-xs outline-none focus:ring-1 focus:ring-brand">
                  </div>
                  <div class="space-y-1">
                      <label class="text-[8px] font-black uppercase text-muted">Author</label>
                      <input type="text" id="meta_author" value="${{meta.author || ''}}" class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-xs outline-none focus:ring-1 focus:ring-brand">
                  </div>
                  <div class="space-y-1">
                      <label class="text-[8px] font-black uppercase text-muted">Page #</label>
                      <input type="text" id="meta_page_start" value="${{meta.page_start || ''}}" class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-xs outline-none focus:ring-1 focus:ring-brand">
                  </div>
              `;
          }} else {{
              container.innerHTML += `
                  <p class="text-[8px] font-bold text-muted uppercase leading-relaxed">Basic notes do not require structured metadata fields.</p>
              `;
          }}
      }}

      async function saveEntry() {{
          const id = document.getElementById('entryId').value;
          const type = document.getElementById('entryType').value;
          
          const meta = {{}};
          if (type === 'quran') {{
              meta.surah_name = document.getElementById('meta_surah_name').value;
              meta.surah_number = parseInt(document.getElementById('meta_surah_number').value);
              meta.verse_start = parseInt(document.getElementById('meta_verse_start').value);
              meta.translator = document.getElementById('meta_translator').value;
          }} else if (type === 'hadith') {{
              meta.collection = document.getElementById('meta_collection').value;
              meta.hadith_number = document.getElementById('meta_hadith_number').value;
              meta.narrator = document.getElementById('meta_narrator').value;
          }} else if (type === 'book' || type === 'article') {{
              meta.title = document.getElementById('meta_title').value;
              meta.author = document.getElementById('meta_author').value;
              meta.page_start = document.getElementById('meta_page_start').value;
          }}

          const payload = {{
              source_id: currentSourceId,
              item_type: type,
              text: document.getElementById('entryText').value,
              arabic_text: document.getElementById('entryArabic').value,
              meta: meta
          }};

          const method = id ? 'PATCH' : 'POST';
          const url = id ? `/api/admin/library/entries/${{id}}` : `/api/admin/library/entries`;

          try {{
              const res = await fetch(url, {{
                  method: method,
                  headers: {{ 'Content-Type': 'application/json' }},
                  body: JSON.stringify(payload)
              }});
              if (res.ok) {{
                  hideEntryModal();
                  loadEntries();
              }} else alert('Operation failed');
          }} catch(e) {{ alert('Network error'); }}
      }}

      async function deleteEntry(id) {{
          if (!confirm('Erase this knowledge node?')) return;
          try {{
              const res = await fetch(`/api/admin/library/entries/${{id}}`, {{ method: 'DELETE' }});
              if (res.ok) loadEntries();
          }} catch(e) {{ alert('Network error'); }}
      }}

      function showUrlModal() {{ document.getElementById('urlModal').classList.remove('hidden'); }}
      function hideUrlModal() {{ document.getElementById('urlModal').classList.add('hidden'); }}

      function switchTab(tab) {{
        const userTab = document.getElementById('tabUser');
        const defaultTab = document.getElementById('tabDefault');
        const userPane = document.getElementById('paneUser');
        const defaultPane = document.getElementById('paneDefault');
        const actionBtn = document.getElementById('actionButtons');

        if (tab === 'user') {{
          userTab.classList.add('text-white', 'border-brand');
          userTab.classList.remove('text-muted', 'border-transparent');
          defaultTab.classList.add('text-muted', 'border-transparent');
          defaultTab.classList.remove('text-white', 'border-brand');
          userPane.classList.remove('hidden');
          defaultPane.classList.add('hidden');
          actionBtn.classList.remove('opacity-0', 'pointer-events-none');
        }} else {{
          defaultTab.classList.add('text-white', 'border-brand');
          defaultTab.classList.remove('text-muted', 'border-transparent');
          userTab.classList.add('text-muted', 'border-transparent');
          userTab.classList.remove('text-white', 'border-brand');
          defaultPane.classList.remove('hidden');
          userPane.classList.add('hidden');
          actionBtn.classList.add('opacity-0', 'pointer-events-none');
        }}
      }}

      async function submitUrl() {{
        const title = document.getElementById('urlTitle').value;
        const url = document.getElementById('urlAddress').value;
        if (!url) return alert('URL is required');

        const btn = event.target;
        btn.disabled = true;
        btn.textContent = 'INGESTING...';

        try {{
          const res = await fetch('/library/add_url', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ title: title, source_type: 'url', original_url: url }})
          }});
          if (res.ok) window.location.reload();
          else alert('Extraction failed');
        }} catch(e) {{ alert('Network error'); }}
        finally {{ btn.disabled = false; btn.textContent = 'Extract & Ingest'; }}
      }}

      async function handleFileUpload(input) {{
        if (!input.files.length) return;
        const file = input.files[0];
        const formData = new FormData();
        formData.append('file', file);
        
        try {{
          const res = await fetch('/library/upload', {{
            method: 'POST',
            body: formData
          }});
          if (res.ok) window.location.reload();
          else alert('Upload failed');
        }} catch(e) {{ alert('Network error'); }}
      }}

      async function deleteDoc(id) {{
        if (!confirm('Are you sure you want to delete this source and all its knowledge chunks?')) return;
        try {{
          const res = await fetch(`/library/${{id}}`, {{ method: 'DELETE' }});
          if (res.ok) window.location.reload();
        }} catch(e) {{ alert('Network error'); }}
      }}
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
                          .replace("{content}", content)\
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
