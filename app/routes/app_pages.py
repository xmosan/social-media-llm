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
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
  <meta name="theme-color" content="#0F3D2E" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <title>{title} | Sabeel Studio</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            brand: '#0F3D2E',
            'brand-hover': '#0A2D22',
            surface: '#FFFFFF',
            accent: '#C9A96E',
            'text-main': '#1A1A1A',
            'text-muted': '#6B6B6B',
            cream: '#F8F6F2'
          },
          boxShadow: {
            'card': '0 4px 12px rgba(15, 61, 46, 0.04)',
            'card-hover': '0 12px 24px rgba(15, 61, 46, 0.06)'
          },
          borderRadius: {
            'card': '12px'
          }
        }
      }
    }
  </script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root {
      --brand: #0F3D2E;
      --brand-hover: #0A2D22;
      --main-bg: #F8F6F2;
      --surface: #FFFFFF;
      --accent: #C9A96E;
      --text-main: #1A1A1A;
      --text-muted: #6B6B6B;
      --border: rgba(15, 61, 46, 0.08);
      --card-bg: #FFFFFF;
    }
    body { font-family: 'Inter', sans-serif; background-color: var(--main-bg); color: var(--text-main); -webkit-font-smoothing: antialiased; }
    .card { background: var(--card-bg); border: 1px solid var(--border); box-shadow: 0 2px 8px rgba(15, 61, 46, 0.04); border-radius: 12px; transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1); }
    .card:hover { transform: translateY(-1px); box-shadow: 0 12px 24px rgba(15, 61, 46, 0.08); }
    .btn-primary, .bg-brand { transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1); }
    .btn-primary:hover, .bg-brand:hover { transform: translateY(-1px) scale(1.01); box-shadow: 0 10px 20px -5px rgba(15, 61, 46, 0.2); }
    .btn-primary:active, .bg-brand:active { transform: translateY(0) scale(0.98); }
    .glass { background: var(--surface); border: 1px solid var(--border); box-shadow: 0 2px 8px rgba(15, 61, 46, 0.04); border-radius: 12px; }
    .nav-link.active { color: var(--brand); border-bottom: 2px solid var(--brand); font-weight: 700; opacity: 1; }
    .nav-link { transition: all 150ms ease; border-bottom: 2px solid transparent; color: var(--text-muted); opacity: 0.8; }
    .nav-link:hover { color: var(--brand); opacity: 1; }
    .studio-tab.active { background: var(--brand); color: white; border-color: var(--brand); }
    .bg-brand { background-color: var(--brand) !important; }
    .bg-brand-hover:hover { background-color: var(--brand-hover) !important; }
    .text-brand { color: var(--brand) !important; }
    .text-accent { color: var(--accent) !important; }
    .border-brand { border-color: var(--brand) !important; }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(15, 61, 46, 0.1); border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(15, 61, 46, 0.2); }
    .pb-safe { padding-bottom: env(safe-area-inset-bottom); }
    .mobile-tab.active { color: var(--brand); }
    .mobile-tab.active svg { color: var(--brand); stroke-width: 2.5; }
  </style>
</head>
<body class="min-h-screen">
  <!-- Top Nav (Desktop) -->
  <nav class="border-b border-brand/5 bg-white/80 backdrop-blur-md sticky top-0 z-50 hidden md:block">
    <div class="max-w-7xl mx-auto px-6 h-16 flex justify-between items-center">
      <div class="flex items-center gap-8">
        <div class="flex items-center gap-2">
            <div class="text-xl font-bold tracking-tight text-brand">Sabeel <span class="text-accent font-normal">Studio</span></div>
        </div>
        <div class="hidden md:flex gap-6">
          <a href="/app" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_dashboard}">Home</a>
          <a href="/app/calendar" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_calendar} text-text-muted hover:text-brand transition-colors">Schedule</a>
          <a href="/app/automations" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_automations} text-text-muted hover:text-brand transition-colors">Content Plans</a>
          <a href="/app/library" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_library} text-text-muted hover:text-brand transition-colors">Content Library</a>
          <a href="/app/media" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_media} text-text-muted hover:text-brand transition-colors">Media Library</a>
          {admin_link}
        </div>
      </div>
      <div class="flex items-center gap-4">
        <!-- Account Switcher Placeholder -->
        <div id="navbarAccountSwitcher" class="relative">
          <div class="animate-pulse h-10 w-32 bg-brand/5 rounded-xl"></div>
        </div>

        <div class="hidden md:flex flex-col text-right">
          <div class="text-[10px] font-bold text-brand uppercase tracking-wider">{user_name}</div>
          <div class="text-[8px] font-bold text-text-muted uppercase tracking-widest leading-none mt-1">{org_name}</div>
        </div>
        <button onclick="logout()" class="p-2 text-text-muted hover:text-brand transition-colors">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
        </button>
      </div>
    </div>
  </nav>

  <!-- Mobile Top Header -->
  <nav class="md:hidden border-b border-brand/5 bg-white/90 backdrop-blur-xl sticky top-0 z-[60] flex justify-between items-center px-4 h-14">
    <div class="flex items-center gap-2">
      <div class="text-lg font-bold tracking-tight text-brand">Sabeel <span class="text-accent font-normal">Studio</span></div>
    </div>
    <div class="flex items-center gap-3">
        <button onclick="logout()" class="p-2 text-text-muted hover:text-brand transition-colors bg-brand/5 rounded-full border border-brand/10">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
        </button>
    </div>
  </nav>

  <main class="max-w-7xl mx-auto px-4 md:px-6 py-6 md:py-10 space-y-6 md:space-y-10 pb-24 md:pb-10">
    {content}
  </main>

  <footer class="hidden md:flex max-w-7xl mx-auto px-6 py-12 border-t border-brand/5 flex flex-col md:flex-row justify-between items-center gap-6 mt-12 mb-12">
    <div class="text-[10px] font-medium text-text-muted uppercase tracking-widest">&copy; 2026 Mohammed Hassan. <span class="text-brand font-bold">Sabeel Studio</span></div>
    <div class="flex gap-6 text-[9px] font-bold uppercase tracking-widest text-text-muted/60">
        <a href="/" class="hover:text-brand transition-colors">Portal</a>
        <a href="/app" class="hover:text-brand transition-colors">Interface</a>
    </div>
  </footer>

  <!-- Mobile Bottom Tab Bar -->
  <nav class="md:hidden fixed bottom-8 left-1/2 -translate-x-1/2 w-[92%] max-w-[400px] bg-white border border-brand/10 p-2 flex justify-between items-center z-[140] shadow-2xl rounded-[2.5rem] backdrop-blur-xl bg-white/90">
    <a href="/app" class="flex-1 flex flex-col items-center gap-1 py-1 mobile-tab {active_dashboard}">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"></path></svg>
        <span class="text-[8px] font-bold uppercase tracking-widest">Home</span>
    </a>
    <a href="/app/calendar" class="flex-1 flex flex-col items-center gap-1 py-1 mobile-tab {active_calendar} text-text-muted">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
        <span class="text-[8px] font-bold uppercase tracking-widest">Plan</span>
    </a>
    <div class="px-1">
        <button onclick="openNewPostModal()" class="w-12 h-12 bg-brand text-white rounded-2xl flex items-center justify-center shadow-lg shadow-brand/20">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 4v16m8-8H4"></path></svg>
        </button>
    </div>
    <a href="/app/automations" class="flex-1 flex flex-col items-center gap-1 py-1 mobile-tab {active_automations} text-text-muted">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
        <span class="text-[8px] font-bold uppercase tracking-widest">Growth</span>
    </a>
    <a href="/app/library" class="flex-1 flex flex-col items-center gap-1 py-1 mobile-tab {active_library} text-text-muted">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"></path></svg>
        <span class="text-[8px] font-bold uppercase tracking-widest">Library</span>
    </a>
  </nav>

  <script>
    async function logout() {
      await fetch('/auth/logout', { method: 'POST' });
      window.location.href = '/';
    }

    async function dismissGettingStarted() {
        try {
            const res = await fetch('/auth/dismiss-getting-started', { method: 'PATCH' });
            if (res.ok) {
                const card = document.getElementById('gettingStartedCard');
                if (card) {
                    card.classList.add('opacity-0', 'scale-95');
                    setTimeout(() => card.remove(), 500);
                }
            }
        } catch(e) { console.error('Failed to dismiss', e); }
    }

    function openConnectInstagramModal() {
        document.getElementById('connectInstagramModal').classList.remove('hidden');
    }

    function closeConnectInstagramModal() {
        document.getElementById('connectInstagramModal').classList.add('hidden');
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
        if (!id || id === 'null' || id === '') {
            console.error("Attempted to open edit modal with no ID");
            return;
        }
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
        
        if (!id) {
            alert('Selection state lost. Please close and reopen the modal.');
            return;
        }

        btn.disabled = true;
        btn.innerText = 'DELETING...';

        try {
            const res = await fetch(`/posts/${id}`, { 
                method: 'DELETE',
                headers: { 'X-Org-Id': '{org_id}' }
            });
            if (res.ok) {
                window.location.reload();
            } else {
                const data = await res.json().catch(() => ({}));
                alert(`Error [${res.status}]: ${data.detail || 'The system could not remove this content. It might have been already removed or access was restricted.'}`);
            }
        } catch(e) { 
            alert('The interface could not reach the server: ' + e.message); 
        } finally { 
            btn.disabled = false; 
            btn.innerText = 'Yes, Delete Content'; 
        }
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
            content.innerHTML = '<div class="text-center py-10 text-rose-400 text-[10px] font-black uppercase">Unable to load your library.</div>';
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
    <div id="newPostModal" class="fixed inset-0 bg-black/95 backdrop-blur-2xl z-[100] flex items-end md:items-center justify-center p-0 md:p-10 hidden">
    <div class="glass w-full h-[100vh] md:h-full md:max-w-7xl rounded-none md:rounded-[3rem] overflow-hidden flex flex-col md:flex-row animate-in slide-in-from-bottom md:zoom-in duration-500 border-0 border-t md:border border-brand/5 shadow-2xl">
      
      <!-- Studio Sidebar (Left/Top) -->
      <div class="w-full md:w-80 bg-brand/5 border-b md:border-b-0 md:border-r border-brand/5 flex flex-col pt-10 md:pt-12 px-8 z-50 shrink-0">
        <div>
          <h3 class="text-3xl font-bold text-brand tracking-tight">Content<br><span class="text-accent">Creator</span></h3>
          <p class="text-[9px] font-bold text-text-muted uppercase tracking-[0.3em] mt-2">Guided Creation Flow</p>
        </div>
        
        <!-- Step Navigation -->
        <div class="flex-1 mt-12 space-y-6">
          <div id="navStep1" class="studio-nav-step active flex items-center gap-4 cursor-pointer" onclick="switchStudioSection(1)">
             <div class="w-8 h-8 rounded-full border-2 border-brand flex items-center justify-center text-[10px] font-bold text-white bg-brand nav-num transition-all">1</div>
             <div class="text-xs font-bold uppercase text-brand tracking-widest nav-text transition-all">Intent & Topic</div>
          </div>
          <div id="navStep2" class="studio-nav-step flex items-center gap-4 cursor-pointer text-text-muted" onclick="switchStudioSection(2)">
             <div class="w-8 h-8 rounded-full border-2 border-brand/10 flex items-center justify-center text-[10px] font-bold nav-num transition-all">2</div>
             <div class="text-xs font-bold uppercase tracking-widest nav-text transition-all">Content Seed</div>
          </div>
          <div id="navStep3" class="studio-nav-step flex items-center gap-4 cursor-pointer text-text-muted" onclick="switchStudioSection(3)">
             <div class="w-8 h-8 rounded-full border-2 border-brand/10 flex items-center justify-center text-[10px] font-bold nav-num transition-all">3</div>
             <div class="text-xs font-bold uppercase tracking-widest nav-text transition-all">Visuals</div>
          </div>
          <div id="navStep4" class="studio-nav-step flex items-center gap-4 cursor-pointer text-text-muted" onclick="switchStudioSection(4)">
             <div class="w-8 h-8 rounded-full border-2 border-brand/10 flex items-center justify-center text-[10px] font-bold nav-num transition-all">4</div>
             <div class="text-xs font-bold uppercase tracking-widest nav-text transition-all">Generate</div>
          </div>
        </div>
        
        <div class="pb-10 pt-4 border-t border-brand/5 mt-auto">
          <button type="button" onclick="closeNewPostModal()" class="w-full py-4 text-[10px] font-bold uppercase tracking-widest text-text-muted hover:text-brand transition-all">Close</button>
        </div>
      </div>

      <!-- Studio Main Content Area -->
      <form id="composerForm" onsubmit="submitNewPost(event)" class="flex-1 overflow-hidden flex flex-col relative bg-white/2">
        <input type="hidden" name="visual_mode" id="studioVisualMode" value="upload">
        <input type="hidden" name="library_item_id" id="studioLibraryItemId">

        <div class="flex-1 overflow-y-auto p-6 md:p-12 pb-32">
          
          <!-- SECTION 1: TOPIC & INTENT -->
          <div id="studioSection1" class="studio-section space-y-10 animate-in slide-in-from-right-8 duration-500">
            <div>
              <label class="text-[10px] font-bold uppercase tracking-[0.2em] text-accent">Step 01</label>
              <h4 class="text-2xl font-bold text-brand">What is your topic?</h4>
              <p class="text-xs text-text-muted mt-2 font-medium">Sabeel uses this to suggest meaningful sources and draft your content.</p>
            </div>

            <div class="space-y-6 max-w-2xl">
               <div class="space-y-2">
                 <label class="text-[9px] font-bold text-brand uppercase tracking-widest pl-1">Topic or Message</label>
                 <input type="text" id="composerTopic" name="topic" oninput="debounceComposerSuggest('composerTopic')" placeholder="e.g. The importance of Sabr (Patience)" class="w-full bg-cream border border-brand/10 rounded-2xl px-6 py-5 text-sm text-brand font-bold outline-none focus:border-brand/30 transition-all">
               </div>

               <div class="grid grid-cols-2 gap-4">
                 <div class="space-y-2">
                   <label class="text-[9px] font-bold text-brand uppercase tracking-widest pl-1">Tone</label>
                   <select name="tone" class="w-full bg-cream border border-brand/10 rounded-2xl px-4 py-4 text-xs font-bold text-brand outline-none focus:border-brand/20 appearance-none">
                     <option value="philosophical">Philosophical</option>
                     <option value="motivational">Motivational</option>
                     <option value="educational">Educational</option>
                     <option value="gentle">Gentle Reminder</option>
                   </select>
                 </div>
                 <div class="space-y-2">
                   <label class="text-[9px] font-bold text-brand uppercase tracking-widest pl-1">Post Type</label>
                   <select name="post_type" class="w-full bg-cream border border-brand/10 rounded-2xl px-4 py-4 text-xs font-bold text-brand outline-none focus:border-brand/20 appearance-none">
                     <option value="reflection">Reflection</option>
                     <option value="quote">Quote Card</option>
                     <option value="announcement">Announcement</option>
                   </select>
                 </div>
               </div>

               <div id="topicSuggestionsArea" class="hidden mt-8 pt-8 border-t border-brand/5 space-y-4">
                 <div class="flex justify-between items-center">
                    <label class="text-[10px] font-bold uppercase tracking-[0.2em] text-brand">Library Inspiration</label>
                 </div>
                 <div id="topicSuggestionsList" class="flex flex-col gap-3"></div>
               </div>
            </div>
            
            <div class="pt-8 flex justify-end">
               <button type="button" onclick="switchStudioSection(2)" class="px-8 py-4 bg-brand text-white rounded-xl font-bold text-[10px] uppercase tracking-widest hover:bg-brand-hover transition-all shadow-lg shadow-brand/10">Continue &rarr;</button>
            </div>
          </div>

          <!-- SECTION 2: SOURCE & CONTENT SEED -->
          <div id="studioSection2" class="studio-section hidden space-y-10 animate-in slide-in-from-right-8 duration-500">
            <div class="flex justify-between items-end">
              <div>
                <label class="text-[10px] font-bold uppercase tracking-[0.2em] text-accent">Step 02</label>
                <h4 class="text-2xl font-bold text-brand">Content Foundation</h4>
                <p class="text-xs text-text-muted mt-2 font-medium">Your content will be thoughtfully drafted based on this foundation.</p>
              </div>
              <button type="button" onclick="openLibraryDrawer()" class="px-4 py-2 bg-brand/5 text-brand border border-brand/10 rounded-lg text-[9px] font-bold uppercase tracking-widest hover:bg-brand/10 transition-all flex items-center gap-2">
                 <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"></path></svg>
                 Explore Library
              </button>
            </div>

            <div class="max-w-3xl space-y-6">
              <!-- Selected Source Display -->
              <div id="activeSourceCard" class="hidden card p-8 border-accent/20 bg-accent/[0.02] relative overflow-hidden group">
                 <div class="absolute top-0 right-0 p-4 opacity-[0.03] blur-sm pointer-events-none">
                    <svg class="w-32 h-32 text-brand" fill="currentColor" viewBox="0 0 24 24"><path d="M14.017 21v-7.391c0-5.704 3.731-9.57 8.983-10.609l.995 2.151c-2.432.917-3.995 3.638-3.995 5.849h4v10h-9.983zm-14.017 0v-7.391c0-5.704 3.748-9.57 9-10.609l.996 2.151c-2.433.917-3.996 3.638-3.996 5.849h3.983v10h-9.983z"></path></svg>
                 </div>
                 <div class="flex justify-between items-start mb-6 relative z-10">
                    <span id="activeSourceBadge" class="px-3 py-1 bg-brand text-white rounded-lg text-[8px] font-bold uppercase tracking-[0.2em]">Foundation Selected</span>
                    <button type="button" onclick="clearSelectedSource()" class="text-rose-600 hover:text-rose-700 text-[9px] font-bold uppercase tracking-widest transition-all">Change Source</button>
                 </div>
                 <div id="activeSourceText" class="text-base font-medium text-brand leading-relaxed relative z-10 italic"></div>
                 <div id="activeSourceRef" class="mt-6 text-[10px] font-bold text-accent uppercase tracking-widest relative z-10"></div>
              </div>

              <!-- Manual / Seed Textarea -->
              <div class="space-y-4">
                 <label id="seedLabel" class="text-[9px] font-bold text-brand uppercase tracking-widest pl-1">Share your core message or directives</label>
                 <textarea id="studioSourceText" name="source_text" required placeholder="Type the message you want to amplify or specific directives for the generation..." class="w-full bg-cream border border-brand/10 rounded-2xl p-6 text-sm font-medium text-brand outline-none focus:border-brand/30 transition-all h-40 resize-none"></textarea>
                 
                 <div class="flex gap-4">
                    <input type="text" id="studioReference" name="source_reference" placeholder="Reference (Optional, e.g. Bukhari 123)" class="flex-1 bg-cream border border-brand/10 rounded-xl px-4 py-3 text-xs font-bold text-brand outline-none focus:border-brand/30">
                 </div>
              </div>
            </div>

            <div class="pt-8 flex justify-between">
               <button type="button" onclick="switchStudioSection(1)" class="px-6 py-4 text-text-muted hover:text-brand rounded-xl font-bold text-[10px] uppercase tracking-widest transition-all">&larr; Back</button>
               <button type="button" onclick="switchStudioSection(3)" class="px-8 py-4 bg-brand text-white rounded-xl font-bold text-[10px] uppercase tracking-widest hover:bg-brand-hover transition-all shadow-lg shadow-brand/10">Continue &rarr;</button>
            </div>
          </div>

          <!-- SECTION 3: VISUALS -->
          <div id="studioSection3" class="studio-section hidden space-y-10 animate-in slide-in-from-right-8 duration-500">
            <div>
              <label class="text-[10px] font-bold uppercase tracking-[0.2em] text-accent">Step 03</label>
              <h4 class="text-2xl font-bold text-brand">Style & Visuals</h4>
              <p class="text-xs text-text-muted mt-1 font-medium">Choose how your content should feel visually.</p>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl">
                <div onclick="setVisualMode('upload')" id="modeUpload" class="visual-card active p-6 rounded-3xl border border-brand/10 bg-white cursor-pointer transition-all hover:bg-brand/5 relative overflow-hidden group">
                  <div class="absolute inset-0 bg-brand/5 opacity-0 group-[.active]:opacity-100 transition-opacity"></div>
                  <div class="absolute top-4 right-4 check-icon text-accent opacity-0 group-[.active]:opacity-100 transition-opacity"><svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></div>
                  <div class="w-12 h-12 rounded-2xl bg-brand/5 flex items-center justify-center text-brand mb-6 relative z-10 transition-colors group-[.active]:bg-brand group-[.active]:text-white"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path></svg></div>
                  <div class="text-[11px] font-bold text-brand uppercase tracking-widest relative z-10">Upload</div>
                  <div class="text-[9px] font-medium text-text-muted mt-1 relative z-10">From device</div>
                </div>

                <div onclick="setVisualMode('media_library')" id="modeMedia" class="visual-card p-6 rounded-3xl border border-brand/10 bg-white cursor-pointer transition-all hover:bg-brand/5 relative overflow-hidden group">
                  <div class="absolute inset-0 bg-brand/5 opacity-0 group-[.active]:opacity-100 transition-opacity"></div>
                  <div class="absolute top-4 right-4 check-icon text-accent opacity-0 group-[.active]:opacity-100 transition-opacity"><svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></div>
                  <div class="w-12 h-12 rounded-2xl bg-brand/5 flex items-center justify-center text-brand mb-6 relative z-10 transition-colors group-[.active]:bg-brand group-[.active]:text-white"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg></div>
                  <div class="text-[11px] font-bold text-brand uppercase tracking-widest relative z-10">Library</div>
                  <div class="text-[9px] font-medium text-text-muted mt-1 relative z-10">Saved assets</div>
                </div>

                <div onclick="setVisualMode('ai_background')" id="modeAI" class="visual-card p-6 rounded-3xl border border-brand/10 bg-white cursor-pointer transition-all hover:bg-brand/5 relative overflow-hidden group">
                  <div class="absolute inset-0 bg-brand/5 opacity-0 group-[.active]:opacity-100 transition-opacity"></div>
                  <div class="absolute top-4 right-4 check-icon text-accent opacity-0 group-[.active]:opacity-100 transition-opacity"><svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></div>
                  <div class="w-12 h-12 rounded-2xl bg-brand/5 flex items-center justify-center text-brand mb-6 relative z-10 transition-colors group-[.active]:bg-brand group-[.active]:text-white"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg></div>
                  <div class="text-[11px] font-bold text-brand uppercase tracking-widest relative z-10">Generate</div>
                  <div class="text-[9px] font-medium text-text-muted mt-1 relative z-10">Visual AI</div>
                </div>

                <div onclick="setVisualMode('quote_card')" id="modeQuote" class="visual-card p-6 rounded-3xl border border-brand/10 bg-white cursor-pointer transition-all hover:bg-brand/5 relative overflow-hidden group">
                  <div class="absolute inset-0 bg-brand/5 opacity-0 group-[.active]:opacity-100 transition-opacity"></div>
                  <div class="absolute top-4 right-4 check-icon text-accent opacity-0 group-[.active]:opacity-100 transition-opacity"><svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></div>
                  <div class="w-12 h-12 rounded-2xl bg-brand/5 flex items-center justify-center text-brand mb-6 relative z-10 transition-colors group-[.active]:bg-brand group-[.active]:text-white"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"></path></svg></div>
                  <div class="text-[11px] font-bold text-brand uppercase tracking-widest relative z-10">Quote Card</div>
                  <div class="text-[9px] font-medium text-text-muted mt-1 relative z-10">Typographic</div>
                </div>
            </div>

            <!-- Dynamic Config Panes -->
            <div id="visualControls" class="p-8 rounded-[2rem] bg-brand/5 border border-brand/10 max-w-4xl space-y-6">
                 
                 <!-- Upload UI -->
                 <div id="uiUpload" class="space-y-4 animate-in fade-in">
                    <label class="text-[9px] font-bold text-brand uppercase tracking-widest pl-1">Media Selection</label>
                    <div class="flex items-center gap-6">
                      <div class="w-32 h-32 rounded-2xl bg-cream border border-dashed border-brand/20 flex flex-col pt-6 items-center flex-start text-brand/40 overflow-hidden relative group cursor-pointer" onclick="document.getElementById('studioImageInput').click()">
                        <svg class="w-6 h-6 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                        <span class="text-[8px] font-bold uppercase tracking-widest">Select</span>
                        <img id="uploadPreview" class="hidden absolute inset-0 w-full h-full object-cover">
                      </div>
                      <input type="file" name="image" id="studioImageInput" onchange="previewUpload(this)" class="hidden" accept="image/png, image/jpeg, image/webp">
                      <div class="text-xs text-text-muted font-medium max-w-xs leading-relaxed">Supported formats: .jpg, .png. Optimal ratio 4:5.</div>
                    </div>
                 </div>

                 <!-- AI Background UI -->
                 <div id="uiAI" class="hidden space-y-6 animate-in fade-in">
                    <div class="space-y-3">
                       <label class="text-[9px] font-bold text-brand uppercase tracking-widest pl-1">Visual Inspiration (Prompt)</label>
                       <textarea name="visual_prompt" id="studioVisualPrompt" placeholder="Describe the scene... e.g. Minimalist mosque silhouette at sunset, warm tones" class="w-full bg-cream border border-brand/10 rounded-2xl p-5 text-xs text-brand outline-none focus:border-brand/30 h-24"></textarea>
                    </div>
                    <div class="space-y-3">
                       <label class="text-[9px] font-bold text-brand uppercase tracking-widest pl-1">Theme Presets</label>
                       <div class="flex flex-wrap gap-2">
                         <button type="button" onclick="setAIPreset('nature')" class="px-5 py-2.5 bg-white border border-brand/10 rounded-xl text-[9px] font-bold uppercase text-brand hover:bg-brand hover:text-white transition-all">Nature</button>
                         <button type="button" onclick="setAIPreset('islamic_geo')" class="px-5 py-2.5 bg-white border border-brand/10 rounded-xl text-[9px] font-bold uppercase text-brand hover:bg-brand hover:text-white transition-all">Geometric</button>
                         <button type="button" onclick="setAIPreset('minimal')" class="px-5 py-2.5 bg-white border border-brand/10 rounded-xl text-[9px] font-bold uppercase text-brand hover:bg-brand hover:text-white transition-all">Minimal</button>
                         <button type="button" onclick="setAIPreset('mosque_sil')" class="px-5 py-2.5 bg-white border border-brand/10 rounded-xl text-[9px] font-bold uppercase text-brand hover:bg-brand hover:text-white transition-all">Silhouette</button>
                       </div>
                    </div>
                 </div>

                 <!-- Quote Card Sub-options -->
                 <div id="uiQuoteMod" class="hidden border-t border-brand/10 pt-6 mt-6 animate-in fade-in">
                    <label class="text-[10px] font-bold text-brand uppercase tracking-[0.2em] mb-4 block">Quote Card Styling</label>
                    <p class="text-xs text-brand font-medium mb-6">Your content will be thoughtfully overlaid on the selected visual background.</p>
                 </div>
            </div>

            <div class="pt-8 flex justify-between">
               <button type="button" onclick="switchStudioSection(2)" class="px-6 py-4 text-text-muted hover:text-brand rounded-xl font-bold text-[10px] uppercase tracking-widest transition-all">&larr; Back</button>
               <button type="button" onclick="switchStudioSection(4)" class="px-8 py-4 bg-brand text-white rounded-xl font-bold text-[10px] uppercase tracking-widest hover:bg-brand-hover transition-all shadow-lg shadow-brand/10">Continue &rarr;</button>
            </div>
          </div>

          <!-- SECTION 4: OUTPUT & ACTIONS -->
          <div id="studioSection4" class="studio-section hidden space-y-10 animate-in slide-in-from-right-8 duration-500 min-h-full">
            <div class="flex justify-between items-end">
              <div>
                <label class="text-[10px] font-bold uppercase tracking-[0.2em] text-accent">Step 04</label>
                <h4 class="text-2xl font-bold text-brand">Final Review</h4>
                <p class="text-xs text-text-muted mt-2 font-medium">Review your visual foundation before generating your content.</p>
              </div>
              <button type="button" onclick="launchLivePreview()" class="px-5 py-3 bg-brand/5 text-brand border border-brand/10 rounded-xl text-[9px] font-bold uppercase tracking-widest shadow-sm hover:bg-brand/10 transition-all flex items-center gap-2">
                 <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg>
                 Preview Visuals
              </button>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-10">
               
               <!-- Preview Phone Mockup -->
               <div class="flex justify-center items-start">
                 <div class="w-full max-w-[340px] bg-white border-[8px] border-brand rounded-[3.5rem] overflow-hidden flex flex-col shadow-2xl relative">
                    <!-- Nav Bar -->
                    <div class="px-4 py-4 flex items-center justify-between bg-white border-b border-brand/5 z-10">
                       <div class="text-[12px] font-bold text-brand">Sabeel Studio</div>
                       <svg class="w-5 h-5 text-brand/40" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z"></path></svg>
                    </div>
                    
                    <!-- Image -->
                    <div class="w-full aspect-[4/5] bg-cream relative flex items-center justify-center overflow-hidden">
                       <img id="previewImage" class="hidden w-full h-full object-cover">
                       <div id="previewLoader" class="flex flex-col items-center gap-3">
                          <svg class="w-8 h-8 text-brand/10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                          <span class="text-[9px] font-bold uppercase tracking-widest text-text-muted">Load Preview</span>
                       </div>
                    </div>

                    <!-- Post Data Info -->
                    <div class="p-4 bg-white flex-1 flex flex-col justify-start">
                        <div class="flex gap-3 mb-3 text-brand/20">
                           <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"></path></svg>
                           <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path></svg>
                           <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path></svg>
                        </div>
                        <div class="text-[10px] text-text-muted font-medium italic">Content will be generated here...</div>
                    </div>
                 </div>
               </div>
               
                <!-- Schedule & Settings -->
                <div class="space-y-8">
                   <div class="space-y-6 bg-cream border border-brand/5 rounded-3xl p-8">
                      <div class="space-y-2">
                        <label class="text-[9px] font-bold uppercase tracking-widest text-brand pl-1">Share To</label>
                        <select name="ig_account_id" class="w-full bg-white border border-brand/10 rounded-2xl px-5 py-4 text-xs font-bold text-brand outline-none focus:border-brand/30 appearance-none">
                          {account_options}
                        </select>
                      </div>
                      <div class="space-y-2">
                        <label class="text-[9px] font-bold uppercase tracking-widest text-brand pl-1">Preferred Time (Local)</label>
                        <input type="datetime-local" name="scheduled_time" class="w-full bg-white border border-brand/10 rounded-2xl px-5 py-4 text-xs font-bold text-brand outline-none focus:border-brand/30">
                        <p class="text-[9px] text-text-muted font-medium mt-2 px-1 italic">Consistency is the bridge between goals and accomplishment.</p>
                      </div>
                   </div>

                   <button type="submit" id="studioSubmitBtn" class="w-full py-5 bg-brand text-white rounded-2xl font-bold text-[10px] uppercase tracking-[0.25em] shadow-xl shadow-brand/20 hover:bg-brand-hover transition-all flex items-center justify-center gap-3">
                      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
                      ACTIVATE GENERATION
                   </button>
                   <button type="button" onclick="switchStudioSection(3)" class="w-full py-4 text-text-muted hover:text-brand rounded-xl font-bold text-[10px] uppercase tracking-widest transition-all">&larr; Refine Visuals</button>
                </div>

                  <div class="bg-brand/5 border border-brand/10 rounded-2xl p-5 flex gap-4 text-brand">
                    <svg class="w-5 h-5 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    <div class="text-[10px] leading-relaxed font-medium">
                       Your post will be carefully drafted using your foundation. You'll be able to review and refine the high-converting content once it's ready.
                    </div>
                  </div>
               </div>
            </div>

          </div>
        </div>
      </form>
    </div>
  </div>


<script>
    // JS for Content Studio
    function openNewPostModal() {
        document.getElementById('newPostModal').classList.remove('hidden');
        switchStudioSection(1);
    }
    function closeNewPostModal() {
        document.getElementById('newPostModal').classList.add('hidden');
    }
    function switchStudioSection(stepIndex) {
        // hide all
        for(let i=1; i<=4; i++) {
           const el = document.getElementById('studioSection' + i);
           if(el) el.classList.add('hidden');
           
           const nav = document.getElementById('navStep' + i);
           if(nav) {
               nav.classList.remove('active', 'text-brand');
               nav.classList.add('text-text-muted');
               nav.querySelector('.nav-num').classList.remove('border-brand', 'text-white', 'bg-brand');
               nav.querySelector('.nav-num').classList.add('border-brand/10');
               nav.querySelector('.nav-text').classList.remove('text-brand');
           }
        }
        
        // activate requested
        const target = document.getElementById('studioSection' + stepIndex);
        if(target) target.classList.remove('hidden');
        
        const targetNav = document.getElementById('navStep' + stepIndex);
        if(targetNav) {
           targetNav.classList.remove('text-text-muted');
           targetNav.classList.add('active');
           targetNav.querySelector('.nav-num').classList.remove('border-brand/10');
           targetNav.querySelector('.nav-num').classList.add('border-brand', 'text-white', 'bg-brand');
           targetNav.querySelector('.nav-text').classList.add('text-brand');
        }
    }

    let suggestTimer;
    function debounceComposerSuggest(inputId) {
        clearTimeout(suggestTimer);
        suggestTimer = setTimeout(() => {
            const val = document.getElementById(inputId).value;
            if (val.length > 5 && inputId === 'composerTopic') {
                fetchComposerSuggestions(val);
            }
        }, 800);
    }

    async function fetchComposerSuggestions(text) {
        const wrap = document.getElementById('topicSuggestionsArea');
        const cont = document.getElementById('topicSuggestionsList');
        // Show spinner
        wrap.classList.remove('hidden');
        cont.innerHTML = '<div class="text-[10px] text-brand/60 uppercase font-black tracking-widest animate-pulse">Scanning Library...</div>';
        
        try {
            const res = await fetch('/library/suggest-entries', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: text, max: 3})
            });
            const data = await res.json();
            
            cont.innerHTML = '';
            if (data.length === 0) {
                cont.innerHTML = '<div class="text-[10px] text-muted font-bold">No exact matches from library.</div>';
            } else {
                data.forEach(item => {
                   const div = document.createElement('div');
                    div.className = "flex justify-between items-center p-4 bg-cream hover:bg-brand/5 border border-brand/5 rounded-xl transition-all group cursor-pointer";
                   
                   let ref = '';
                   if (item.item_type === 'quran') ref = `Quran ${item.meta.surah_number}:${item.meta.verse_start}`;
                   else if (item.item_type === 'hadith') ref = `${item.meta.collection} #${item.meta.hadith_number}`;
                   else ref = item.meta.title || item.item_type;

                   div.innerHTML = `
                     <div class="flex-1 pr-6">
                        <div class="text-[9px] font-bold text-accent uppercase tracking-widest mb-1">${ref}</div>
                        <div class="text-xs text-brand font-medium line-clamp-2">${item.text}</div>
                     </div>
                     <button class="px-4 py-2 border border-brand/20 text-brand rounded-lg text-[9px] font-bold uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-all shrink-0">Use</button>
                   `;
                   div.onclick = () => { applySuggestedSource(item, ref); };
                   cont.appendChild(div);
                });
            }
        } catch(e) {
            cont.innerHTML = '<div class="text-[10px] text-rose-400 font-bold">Error loading suggestions</div>';
        }
    }

    function applySuggestedSource(item, refText) {
        // Set Source Editor
        document.getElementById('studioSourceText').value = item.text || "";
        document.getElementById('studioReference').value = refText || "";
        document.getElementById('studioLibraryItemId').value = item.id;
        
        // Show Active Card
        document.getElementById('activeSourceCard').classList.remove('hidden');
        document.getElementById('activeSourceText').innerText = item.text || "";
        document.getElementById('activeSourceRef').innerText = refText || "";
        
        // Update Label
        document.getElementById('seedLabel').innerText = "Edit source text if needed before AI expansion:";
        
        // Move to Step 2
        switchStudioSection(2);
    }

    function clearSelectedSource() {
        document.getElementById('studioSourceText').value = "";
        document.getElementById('studioReference').value = "";
        document.getElementById('studioLibraryItemId').value = "";
        
        document.getElementById('activeSourceCard').classList.add('hidden');
        document.getElementById('activeSourceText').innerText = "";
        document.getElementById('activeSourceRef').innerText = "";
        document.getElementById('seedLabel').innerText = "Or write a manual content seed / prompt directives";
    }

    function setVisualMode(mode) {
        document.getElementById('studioVisualMode').value = mode;
        const modes = ['Upload', 'Media', 'AI', 'Quote'];
        modes.forEach(m => {
            const el = document.getElementById('mode'+m);
            if(el) el.classList.remove('active', 'border-brand', 'bg-brand/5');
            else {
               // try lower
            }
        });
        
        const target = {
            'upload': 'modeUpload',
            'media_library': 'modeMedia', 
            'ai_background': 'modeAI',
            'quote_card': 'modeQuote'
        }[mode];
        
        if (target) {
           const tel = document.getElementById(target);
           tel.classList.add('active', 'border-brand', 'bg-brand/5');
        }

        // Handle UIs
        document.getElementById('uiUpload').classList.add('hidden');
        document.getElementById('uiAI').classList.add('hidden');
        document.getElementById('uiQuoteMod').classList.add('hidden');
        
        if (mode === 'upload') document.getElementById('uiUpload').classList.remove('hidden');
        if (mode === 'ai_background' || mode === 'quote_card') {
           document.getElementById('uiAI').classList.remove('hidden');
           if (mode === 'quote_card') {
               document.getElementById('uiQuoteMod').classList.remove('hidden');
           }
        }
    }

    function setAIPreset(promptStr) {
        const m = {
            'nature': 'Premium minimalist nature photography, subtle warm tones, empty space',
            'islamic_geo': 'Subtle dark islamic geometric pattern background, elegant, cinematic lighting',
            'minimal': 'Extremely minimalist dark layout, smooth gradient, hyper-realistic texture',
            'mosque_sil': 'Minimalist silhouette of a mosque at dusk, violet and orange sky, cinematic'
        }[promptStr];
        document.getElementById('studioVisualPrompt').value = m || "";
    }

    function previewUpload(input) {
        if (input.files && input.files[0]) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const img = document.getElementById('uploadPreview');
                img.src = e.target.result;
                img.classList.remove('hidden');
            }
            reader.readAsDataURL(input.files[0]);
        }
    }

    async function launchLivePreview() {
        const img = document.getElementById('previewImage');
        const loader = document.getElementById('previewLoader');
        
        img.classList.add('hidden');
        loader.classList.remove('hidden');

        const formData = new FormData(document.getElementById('composerForm'));
        
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
                loader.innerHTML = '<span class="text-[9px] font-black text-rose-400">Failed: '+detail+'</span>';
            }
        } catch (e) {
            loader.innerHTML = '<span class="text-[9px] font-black text-rose-400">Preview Error</span>';
        }
    }

    async function submitNewPost(event) {
        event.preventDefault();
        const btn = document.getElementById('studioSubmitBtn');
        const originalText = btn.innerHTML;
        btn.innerHTML = 'GENERATING... <span class="animate-pulse">⏳</span>';
        btn.disabled = true;

        const formData = new FormData(event.target);
        
        // CHECK FOR CONNECTED ACCOUNT
        const accountId = formData.get('account_id');
        if (!accountId || accountId === "") {
            btn.innerHTML = originalText;
            btn.disabled = false;
            openConnectInstagramModal();
            return;
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
            alert('Failure: ' + e);
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    }
</script>

<!-- Library Explorer Side Drawer -->
  <div id="libraryDrawer" class="fixed inset-y-0 right-0 w-full max-w-md bg-white z-[150] shadow-2xl border-l border-brand/10 transform translate-x-full transition-transform duration-500 overflow-hidden flex flex-col">
    <div class="p-8 pb-4 border-b border-brand/5 flex justify-between items-center">
      <div>
        <h3 class="text-xl font-bold text-brand">Content <span class="text-accent">Library</span></h3>
        <p class="text-[8px] font-bold text-text-muted uppercase tracking-widest">Find inspiration from verified sources</p>
      </div>
      <button onclick="closeLibraryDrawer()" class="p-2 text-text-muted hover:text-brand transition-all"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg></button>
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
          <p class="text-[10px] font-black text-brand uppercase tracking-[0.3em]">Generating content...</p>
      </div>
      
      <img id="previewImage" class="hidden max-w-full max-h-full rounded-3xl shadow-2xl border border-white/10 animate-in fade-in zoom-in duration-700">
      
      <div class="mt-8 flex gap-4 text-white">
          <button type="button" onclick="closePreviewModal()" class="px-10 py-4 bg-white/5 border border-white/10 rounded-2xl font-black text-[10px] uppercase tracking-widest hover:bg-white/10 transition-all">Close Preview</button>
          <button type="button" onclick="closePreviewModal()" class="px-10 py-4 bg-emerald-500 rounded-2xl font-black text-[10px] uppercase tracking-widest shadow-lg shadow-emerald-500/20 hover:scale-105 transition-all">Looks Good</button>
      </div>
  </div>
  {connect_instagram_modal}
  {extra_js}
</body>
</html>
"""

GET_STARTED_CARD_HTML = """<div id="gettingStartedCard" class="card p-8 md:p-10 mb-8 animate-in slide-in-from-top-4 duration-500">
  <div class="flex justify-between items-start mb-6">
    <div>
      <h3 class="text-2xl md:text-3xl font-bold text-brand tracking-tight">Assalamu Alaykum, <span class="text-accent">{user_name}</span></h3>
      <p class="text-xs text-text-muted mt-1 font-medium">Your content workspace is ready.</p>
    </div>
    <button onclick="dismissGettingStarted()" class="text-[9px] font-bold uppercase tracking-widest text-text-muted hover:text-brand transition-colors px-4 py-2 bg-brand/5 rounded-lg border border-brand/10">Dismiss</button>
  </div>
  
  <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
    <!-- Focal Point: Create Post -->
    <div class="md:col-span-2 card p-8 border-brand/10 bg-brand/[0.02] flex flex-col justify-between group cursor-pointer" onclick="openNewPostModal()">
      <div class="space-y-4">
        <div class="w-12 h-12 rounded-2xl bg-brand text-white flex items-center justify-center shadow-lg shadow-brand/20 group-hover:scale-110 transition-transform">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 4v16m8-8H4"></path></svg>
        </div>
        <div>
          <h4 class="text-xl font-bold text-brand">Create your next post</h4>
          <p class="text-sm text-text-muted mt-1 font-medium italic">"The best of people are those who are most beneficial to others."</p>
        </div>
      </div>
      <div class="mt-8 flex items-center gap-2 text-xs font-bold text-brand uppercase tracking-widest group-hover:translate-x-2 transition-transform">
        Start Drafting <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M17 8l4 4m0 0l-4 4m4-4H3"></path></svg>
      </div>
    </div>

    <!-- Quick Links Sidebar -->
    <div class="space-y-4">
       <a href="/app/library" class="card p-5 flex items-center gap-4 hover:border-brand/20 transition-all group">
         <div class="w-10 h-10 rounded-xl bg-brand/5 text-brand flex items-center justify-center group-hover:bg-brand group-hover:text-white transition-all">
           <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"></path></svg>
         </div>
         <div>
           <div class="text-[10px] font-bold text-brand uppercase tracking-widest">Library</div>
           <div class="text-[9px] font-medium text-text-muted uppercase tracking-tighter">Find Sparks</div>
         </div>
       </a>
       <a href="/app/automations" class="card p-5 flex items-center gap-4 hover:border-brand/20 transition-all group">
         <div class="w-10 h-10 rounded-xl bg-brand/5 text-brand flex items-center justify-center group-hover:bg-brand group-hover:text-white transition-all">
           <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
         </div>
         <div>
           <div class="text-[10px] font-bold text-brand uppercase tracking-widest">Plans</div>
           <div class="text-[9px] font-medium text-text-muted uppercase tracking-tighter">Stay Consistent</div>
         </div>
       </a>
       <button onclick="openConnectInstagramModal()" class="w-full card p-5 flex items-center gap-4 hover:border-brand/20 transition-all group text-left">
         <div class="w-10 h-10 rounded-xl bg-brand/5 text-brand flex items-center justify-center group-hover:bg-brand group-hover:text-white transition-all">
           <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
         </div>
         <div>
           <div class="text-[10px] font-bold text-brand uppercase tracking-widest">Accounts</div>
           <div class="text-[9px] font-medium text-text-muted uppercase tracking-tighter">Expand Reach</div>
         </div>
       </button>
    </div>
  </div>
</div>"""

CONNECT_INSTAGRAM_MODAL_HTML = """

<div id="connectInstagramModal" class="fixed inset-0 bg-brand/10 backdrop-blur-xl z-[200] flex items-center justify-center p-6 hidden">
  <div class="glass max-w-md w-full rounded-[2.5rem] p-8 md:p-10 border-brand/10 bg-white shadow-2xl animate-in zoom-in duration-300">
    <div class="text-center space-y-6">
      <div class="w-20 h-20 bg-brand/5 rounded-3xl flex items-center justify-center text-brand mx-auto">
        <svg class="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
      </div>
      <div>
        <h3 class="text-2xl font-bold text-brand tracking-tighter">Instagram Connection</h3>
        <p class="text-[10px] text-text-muted mt-2 font-bold uppercase tracking-widest leading-relaxed italic">To connect your Instagram, Meta requires a secure login. This may appear as a Facebook login screen. This is a standard security procedure to verify your Professional account.</p>
      </div>
      <div class="flex flex-col gap-3 pt-2">
        <button onclick="window.location.href='/auth/instagram/login'" class="w-full py-4 bg-brand rounded-2xl font-bold text-xs uppercase tracking-widest text-white shadow-xl shadow-brand/20 hover:bg-brand-hover transition-all flex items-center justify-center gap-2">
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.791-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.209-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/></svg>
          Continue to Secure Login
        </button>
        <button onclick="closeConnectInstagramModal()" class="w-full py-4 bg-white border border-brand/10 rounded-2xl font-bold text-xs uppercase tracking-widest text-text-muted hover:text-brand transition-all">Maybe Later</button>
      </div>
    </div>
  </div>
</div>
"""

APP_DASHBOARD_CONTENT = """
    <!-- Header -->
    <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 mb-12">
      <div>
        <h1 class="text-4xl font-bold text-brand tracking-tighter">Studio <span class="text-accent underline decoration-accent/20 decoration-4 underline-offset-8">Intelligence</span></h1>
        <div class="text-[10px] font-bold text-text-muted uppercase tracking-[0.4em] mt-3 flex items-center gap-4">
            <div class="flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              Interface Active
            </div>
            {connected_account_info}
        </div>
      </div>
      <div class="flex items-center gap-4">
        <button onclick="openNewPostModal()" class="px-8 py-4 bg-brand text-white rounded-2xl font-bold text-[11px] uppercase tracking-widest shadow-2xl shadow-brand/20 hover:bg-brand-hover transition-all flex items-center gap-3 group">
            <svg class="w-4 h-4 group-hover:rotate-90 transition-transform duration-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
            Create Post
        </button>
        <button onclick="syncAccounts()" class="w-12 h-12 flex items-center justify-center bg-white border border-brand/10 text-brand rounded-2xl font-bold hover:border-brand/30 transition-all shadow-sm" title="Sync Status">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
        </button>
      </div>
    </div>

    <!-- Quick Stats Cluster -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-12">
      <div class="card p-6 border-brand/5 bg-white flex flex-col justify-between min-h-[120px]">
        <div class="flex justify-between items-start">
            <div class="text-[9px] font-bold text-text-muted uppercase tracking-widest">Output</div>
            <div class="p-1.5 bg-brand/5 rounded-lg text-brand"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></div>
        </div>
        <div>
            <div class="text-2xl font-bold text-brand tracking-tight">{weekly_post_count} <span class="text-xs text-text-muted font-medium">Posts</span></div>
            <div class="text-[8px] font-bold text-emerald-600 uppercase tracking-widest mt-1">Last 7 Days</div>
        </div>
      </div>
      <div class="card p-6 border-brand/5 bg-white flex flex-col justify-between min-h-[120px]">
        <div class="flex justify-between items-start">
            <div class="text-[9px] font-bold text-text-muted uppercase tracking-widest">Growth</div>
            <div class="p-1.5 bg-brand/5 rounded-lg text-brand"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></div>
        </div>
        <div>
            <div class="text-2xl font-bold text-brand tracking-tight">{account_count} <span class="text-xs text-text-muted font-medium">Platforms</span></div>
            <div class="text-[8px] font-bold text-brand uppercase tracking-widest mt-1">Network Active</div>
        </div>
      </div>
      <div class="card p-6 border-brand/5 bg-white flex flex-col justify-between min-h-[120px]">
        <div class="flex justify-between items-start">
            <div class="text-[9px] font-bold text-text-muted uppercase tracking-widest">AI Status</div>
            <div class="p-1.5 bg-brand/5 rounded-lg text-brand"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9l-.505.505a4.125 4.125 0 005.758 5.758l.505-.505m9.393-9.393l.505-.505a4.125 4.125 0 10-5.758-5.758l-.505.505" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></div>
        </div>
        <div>
            <div class="text-2xl font-bold text-brand tracking-tight underline decoration-emerald-500/30 decoration-2">Ready</div>
            <div class="text-[8px] font-bold text-text-muted uppercase tracking-widest mt-1">Creation Engine</div>
        </div>
      </div>
      <div class="card p-6 border-brand/5 bg-white flex flex-col justify-between min-h-[120px]">
        <div class="flex justify-between items-start">
            <div class="text-[9px] font-bold text-text-muted uppercase tracking-widest">Intelligence</div>
            <div class="p-1.5 bg-accent/10 rounded-lg text-accent"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></div>
        </div>
        <div>
            <div class="text-2xl font-bold text-accent tracking-tighter">{next_post_countdown}</div>
            <div class="text-[8px] font-bold text-accent uppercase tracking-widest mt-1">Until Next Pulse</div>
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
            Growth Preview
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
                <label class="text-[8px] font-bold text-accent uppercase tracking-widest">Scheduled Logic</label>
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
              <h2 class="text-[10px] font-bold uppercase tracking-[0.4em] text-text-muted">Content Pulse</h2>
              <a href="/app/calendar" class="text-[8px] font-bold uppercase tracking-widest text-brand hover:text-accent transition-colors flex items-center gap-2 px-3 py-1.5 bg-brand/5 rounded-lg border border-brand/5">
                Full Strategy 
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
                      <span class="text-[8px] font-bold uppercase tracking-widest text-text-muted">Operations Scheduled</span>
                  </div>
                  <div class="flex items-center gap-2 opacity-30">
                      <div class="w-2 h-2 rounded-full bg-brand/10"></div>
                      <span class="text-[8px] font-bold uppercase tracking-widest text-text-muted">System Idle</span>
                  </div>
              </div>
            </div>
        </div>

        <!-- Intelligence Feed -->
        <div class="space-y-6">
          <h2 class="text-[10px] font-bold uppercase tracking-[0.4em] text-text-muted">Intelligence Feed</h2>
          <div class="space-y-3">
            {recent_posts}
          </div>
        </div>
      </div>
    </div>

    <!-- Edit Post Modal -->
    <div id="editPostModal" class="fixed inset-0 bg-brand/20 backdrop-blur-xl z-[100] hidden flex flex-col items-center justify-center p-0 md:p-6">
      <div class="glass w-full h-[90vh] md:h-auto md:max-w-xl pb-safe rounded-t-[2.5rem] md:rounded-[3rem] p-6 md:p-10 space-y-8 animate-in slide-in-from-bottom md:zoom-in-95 duration-300 border-t md:border border-brand/10 bg-white overflow-y-auto">
        <div class="flex justify-between items-center">
          <div>
            <h2 class="text-2xl font-bold text-brand tracking-tight">Refine <span class="text-accent">Post</span></h2>
            <p class="text-[10px] font-bold text-text-muted uppercase tracking-widest">Thoughtfully adjust your content</p>
          </div>
          <button onclick="closeEditPostModal()" class="w-10 h-10 flex items-center justify-center rounded-full hover:bg-brand/5 text-text-muted hover:text-brand transition-all"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg></button>
        </div>

        <input type="hidden" id="editPostId">
        
        <div class="space-y-6">
          <div class="space-y-2">
            <label class="text-[10px] font-bold text-brand uppercase tracking-widest ml-1">Content Caption</label>
            <textarea id="editPostCaption" rows="6" class="w-full bg-cream/40 border border-brand/10 rounded-2xl p-6 text-brand text-sm focus:border-brand/30 focus:bg-white transition-all font-medium italic outline-none leading-relaxed"></textarea>
        </div>
        <div class="flex flex-col gap-4">
            <button onclick="updatePost()" class="w-full py-4 bg-brand rounded-2xl font-bold text-xs uppercase tracking-widest text-white shadow-xl shadow-brand/20 hover:bg-brand-hover transition-all">Apply Refinement</button>
            <button onclick="closeEditPostModal()" class="w-full py-4 bg-white border border-brand/10 rounded-2xl font-bold text-xs uppercase tracking-widest text-text-muted hover:text-brand transition-all">Cancel</button>
        </div>
      </div>
    </div>
"""

SELECT_ACCOUNT_HTML = """
<div class="min-h-screen bg-cream flex flex-col items-center justify-center p-6 bg-gradient-to-br from-cream via-cream to-brand/5">
    <div class="max-w-2xl w-full space-y-12 animate-in fade-in slide-in-from-bottom-6 duration-1000">
        <!-- Header -->
        <div class="text-center space-y-6">
            <div class="w-24 h-24 bg-brand rounded-[3rem] flex items-center justify-center text-white mx-auto shadow-2xl shadow-brand/20 rotate-3 border-4 border-white">
                <svg class="w-12 h-12" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.791-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.209-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/></svg>
            </div>
            <div class="space-y-3">
                <h1 class="text-4xl font-bold text-brand tracking-tighter">Choose Your <span class="text-accent underline decoration-accent/20 decoration-8 underline-offset-8">Presence</span></h1>
                <p class="text-[11px] font-bold text-text-muted uppercase tracking-[0.4em] opacity-80">Final Selection Required</p>
            </div>
        </div>

        <!-- Account List -->
        <div id="account-grid" class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Loading Skeletons -->
            <div class="card p-10 bg-white shadow-xl shadow-brand/5 border-brand/5 animate-pulse flex flex-col items-center gap-6 rounded-[2.5rem]">
                <div class="w-16 h-16 bg-brand/5 rounded-2xl"></div>
                <div class="h-4 bg-brand/5 rounded w-32"></div>
                <div class="h-10 bg-brand/5 rounded-xl w-full mt-4"></div>
            </div>
        </div>

        <div id="empty-state" class="hidden text-center py-24 space-y-8 bg-white rounded-[3rem] border border-brand/5 shadow-2xl">
            <div class="w-24 h-24 bg-rose-50 rounded-[2.5rem] flex items-center justify-center text-rose-300 mx-auto border border-rose-100 italic">
                !
            </div>
            <div class="space-y-3 px-10">
                <h3 class="text-2xl font-bold text-brand tracking-tight">Access Restricted</h3>
                <p class="text-sm text-text-muted font-medium max-w-sm mx-auto leading-relaxed">We couldn't verify any professional Instagram Business accounts linked to this Meta profile. Please ensure your account is switched to 'Professional' in Instagram settings.</p>
            </div>
            <button onclick="window.location.href='/app'" class="px-10 py-4 bg-brand rounded-2xl font-bold text-[11px] uppercase tracking-widest text-white shadow-xl shadow-brand/10 hover:shadow-brand/20 transition-all">Go Back</button>
        </div>

        <div class="text-center pt-8">
            <div class="inline-flex items-center gap-3 px-4 py-2 bg-brand/5 rounded-full border border-brand/10 transition-all">
                <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <p class="text-[9px] font-bold text-brand uppercase tracking-widest opacity-80">Meta Authorization Active</p>
            </div>
        </div>
    </div>
</div>

<script>
    // Fix Facebook redirect hash issue
    if (window.location.hash === '#_=_') {
        history.replaceState(null, null, window.location.pathname);
    }

    async function loadAccounts() {
        const grid = document.getElementById('account-grid');
        const emptyState = document.getElementById('empty-state');
        
        try {
            const res = await fetch('/accounts/available');
            const accounts = await res.json();
            
            if (!accounts || accounts.length === 0) {
                emptyState.classList.remove('hidden');
                grid.innerHTML = '';
                return;
            }

            grid.innerHTML = accounts.map(acc => `
                <div class="flex items-center justify-between p-6 bg-white border border-brand/5 rounded-3xl hover:border-brand/20 hover:shadow-xl hover:shadow-brand/5 transition-all group">
                    <div class="flex items-center gap-5">
                        <div class="relative">
                            <img src="${acc.profile_picture_url || 'https://ui-avatars.com/api/?name=' + acc.username}" class="w-16 h-16 rounded-2xl ring-4 ring-brand/5 group-hover:ring-brand/10 transition-all object-cover">
                            <div class="absolute -bottom-1 -right-1 w-6 h-6 bg-emerald-500 rounded-lg flex items-center justify-center border-2 border-white shadow-lg">
                                <svg class="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
                            </div>
                        </div>
                        <div>
                            <div class="text-xs font-black text-brand uppercase tracking-widest mb-1">@${acc.username}</div>
                            <h3 class="text-base font-bold text-text-muted tracking-tight">${acc.name || acc.username}</h3>
                        </div>
                    </div>
                    <button onclick="selectAccount('${acc.ig_user_id}', '${acc.fb_page_id}', this)" class="px-8 py-4 bg-brand text-white rounded-2xl font-black text-[10px] uppercase tracking-[0.2em] shadow-lg shadow-brand/20 hover:scale-[1.02] active:scale-95 transition-all">
                        Connect
                    </button>
                </div>
            `).join('');
        } catch (e) {
            console.error(e);
            alert('Session expired. Please reconnect Meta.');
        }
    }

    async function selectAccount(igId, pageId, btn) {
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = 'Connecting...';
        
        try {
            const res = await fetch('/accounts/select', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ig_user_id: igId, page_id: pageId })
            });
            
            if (res.redirected) {
                window.location.href = res.url;
            } else if (res.ok) {
                window.location.href = '/app';
            } else {
                const data = await res.json();
                alert(data.detail || 'Failed to select account');
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        } catch (e) {
            alert('Service unavailable. Please retry.');
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }

    window.onload = loadAccounts;
</script>
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
            <h2 class="text-sm font-black text-indigo-400 uppercase tracking-widest">Step 03</h2>
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
            <h2 class="text-sm font-black text-indigo-400 uppercase tracking-widest">Step 04</h2>
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
    posts = db.query(Post).filter(Post.org_id == org_id).order_by(Post.created_at.desc()).limit(5).all()
    recent_posts_html = ""
    for p in posts:
        status_color = "text-text-muted"
        status_bg = "bg-brand/5"
        if p.status == "published": 
            status_color = "text-emerald-600"
            status_bg = "bg-emerald-50"
        elif p.status == "scheduled": 
            status_color = "text-brand"
            status_bg = "bg-brand/5"
        
        caption_json = html.escape(json.dumps(p.caption or ""), quote=True)
        
        recent_posts_html += f"""
        <div class="card p-4 bg-white flex justify-between items-center hover:shadow-lg hover:shadow-brand/[0.02] transition-all border-brand/5">
          <div class="flex items-center gap-4">
            <div class="w-12 h-12 rounded-xl bg-cream overflow-hidden border border-brand/5 shrink-0 shadow-inner">
                {f'<img src="{p.media_url}" class="w-full h-full object-cover">' if p.media_url else '<div class="w-full h-full flex items-center justify-center text-[7px] font-bold text-text-muted/40 uppercase">Null</div>'}
            </div>
            <div class="min-w-0">
              <div class="text-[11px] font-bold text-brand uppercase tracking-wider truncate max-w-[140px] md:max-w-[200px]">{p.caption[:50] if p.caption else "System Draft"}</div>
              <div class="flex items-center gap-2 mt-1">
                <div class="text-[8px] font-bold text-text-muted uppercase tracking-widest">{p.created_at.strftime("%b %d")}</div>
                <div class="w-1 h-1 rounded-full bg-text-muted/20"></div>
                <div class="px-2 py-0.5 {status_bg} {status_color} rounded-md text-[7px] font-black uppercase tracking-widest">{p.status}</div>
              </div>
            </div>
          </div>
          <div class="flex items-center">
            <button onclick="openEditPostModal('{p.id}', {caption_json}, '{p.scheduled_time.isoformat() if p.scheduled_time else ''}')" class="p-3 text-text-muted hover:text-brand hover:bg-brand/5 rounded-xl transition-all">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
            </button>
          </div>
        </div>
        """
    
    # Connection CTA for empty states
    connection_cta = ""
    if account_count == 0:
        connection_cta = f"""
        <div class="card p-12 text-center space-y-8 animate-in slide-in-from-bottom-4 duration-1000 border-dashed border-2 border-brand/10 bg-brand/[0.01]">
          <div class="w-20 h-20 bg-brand/5 rounded-[2rem] flex items-center justify-center text-brand mx-auto">
            <svg class="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
          </div>
          <div class="space-y-3">
            <h3 class="text-2xl font-bold text-brand tracking-tighter">Connect Instagram</h3>
            <p class="text-text-muted text-sm max-w-lg mx-auto font-medium leading-relaxed">Your studio is ready to create. Link your Instagram account to start sharing your content automatically with your community.</p>
          </div>
          <button onclick="openConnectInstagramModal()" class="px-10 py-4 bg-brand rounded-2xl font-bold text-xs uppercase tracking-widest text-white shadow-xl shadow-brand/20 hover:bg-brand-hover transition-all">Link Now</button>
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
    accs = db.query(IGAccount).filter(IGAccount.org_id == user.active_org_id).all()
    account_options = "".join([f'<option value="{a.id}">{a.name} (@{a.ig_user_id})</option>' for a in accs])

    return HTMLResponse(content=APP_LAYOUT_HTML.replace("{content}", content)\
                          .replace("{title}", "Dashboard")\
                          .replace("{user_name}", user.name or user.email)\
                          .replace("{org_name}", org.name if org else "Personal Workspace")\
                          .replace("{admin_link}", admin_link)\
                          .replace("{active_dashboard}", "active")\
                          .replace("{active_calendar}", "")\
                          .replace("{active_automations}", "")\
                          .replace("{active_library}", "")\
                          .replace("{active_media}", "")\
                          .replace("{account_options}", account_options)\
                          .replace("{connect_instagram_modal}", CONNECT_INSTAGRAM_MODAL_HTML)\
                          .replace("{extra_js}", f"""
<script>
    window.hasConnectedInstagram = {"true" if is_connected else "false"};
       async function renderAccountSwitcher() {{
        const container = document.getElementById('navbarAccountSwitcher');
        if (!container) return;

        try {{
            const res = await fetch('/ig-accounts/me');
            const accounts = await res.json();
            
            if (accounts.length === 0) {{
                container.innerHTML = `
                    <button onclick="openConnectInstagramModal()" class="flex items-center gap-2 px-3 py-1.5 bg-brand text-white rounded-lg text-[10px] font-bold uppercase tracking-widest hover:bg-brand-hover transition-all">
                        Link Meta
                    </button>
                `;
                return;
            }}

            const active = accounts.find(a => a.active) || accounts[0];
            const others = accounts.filter(a => a.id !== active.id);

            container.innerHTML = `
                <div class="relative inline-block text-left" id="accountSwitcherRoot">
                    <button onclick="toggleSwitcherDropdown()" class="flex items-center gap-3 px-3 py-2 bg-white border border-brand/10 rounded-xl hover:bg-brand/[0.02] transition-all group">
                        <img src="${{active.profile_picture_url || 'https://ui-avatars.com/api/?name=' + active.username}}" class="w-6 h-6 rounded-full ring-2 ring-brand/10 group-hover:ring-brand/20 transition-all">
                        <div class="text-left hidden lg:block">
                            <div class="text-[9px] font-black text-brand uppercase tracking-wider">@${{active.username}}</div>
                            <div class="text-[7px] font-bold text-text-muted uppercase tracking-widest">Active Studio</div>
                        </div>
                        <svg class="w-3 h-3 text-text-muted/40 group-hover:text-brand transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
                    </button>

                    <div id="switcherDropdown" class="hidden absolute right-0 mt-2 w-64 bg-white border border-brand/5 rounded-2xl shadow-2xl z-[100] p-2 animate-in fade-in zoom-in-95 duration-200">
                        <div class="px-3 py-2 text-[8px] font-black text-text-muted uppercase tracking-[0.2em] mb-1">Your Workspaces</div>
                        
                        <div class="space-y-1">
                            ${{accounts.map(acc => `
                                <button onclick="setActiveAccount('${{acc.id}}')" class="w-full flex items-center justify-between p-2 rounded-xl transition-all ${{acc.id === active.id ? 'bg-brand/5 border border-brand/5' : 'hover:bg-brand/[0.02]'}}">
                                    <div class="flex items-center gap-3">
                                        <img src="${{acc.profile_picture_url || 'https://ui-avatars.com/api/?name=' + acc.username}}" class="w-8 h-8 rounded-lg">
                                        <div class="text-left">
                                            <div class="text-[10px] font-bold text-brand">@${{acc.username}}</div>
                                            <div class="text-[8px] text-text-muted font-medium">${{acc.fb_page_id ? 'Instagram Business' : 'Personal'}}</div>
                                        </div>
                                    </div>
                                    ${{acc.id === active.id ? '<div class="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>' : ''}}
                                </button>
                            `).join('')}}
                        </div>

                        <div class="mt-2 pt-2 border-t border-brand/5">
                            <button onclick="openConnectInstagramModal()" class="w-full flex items-center gap-3 p-2 rounded-xl hover:bg-brand/5 transition-all text-brand">
                                <div class="w-8 h-8 rounded-lg bg-brand/5 flex items-center justify-center">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
                                </div>
                                <div class="text-[10px] font-black uppercase tracking-widest">Connect New</div>
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }} catch (e) {{
            console.error("Account switcher failed", e);
        }}
    }}

    function toggleSwitcherDropdown() {{
        const drop = document.getElementById('switcherDropdown');
        drop.classList.toggle('hidden');
    }}

    async function setActiveAccount(id) {{
        try {{
            const res = await fetch(`/ig-accounts/set-active/${{id}}`, {{ method: 'POST' }});
            if (res.ok) {{
                window.location.reload();
            }}
        }} catch (e) {{ console.error(e); }}
    }}

    async function syncAccountState() {{
        try {{
            const res = await fetch('/ig-accounts/me');
            const accounts = await res.json();
            const actuallyConnected = accounts.length > 0;
            
            if (actuallyConnected !== window.hasConnectedInstagram) {{
                console.log("State mismatch detected, refreshing to sync UI...");
                window.location.reload();
            }}
        }} catch(e) {{
            console.error("Failed to sync account state", e);
        }}
    }}

    // Close on click outside
    window.onclick = function(event) {{
        if (!event.target.closest('#accountSwitcherRoot')) {{
            const drop = document.getElementById('switcherDropdown');
            if (drop && !drop.classList.contains('hidden')) drop.classList.add('hidden');
        }}
    }};

    window.onload = function() {{
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('error')) {{
            alert(urlParams.get('error'));
        }}
        // Run checks
        syncAccountState();
        renderAccountSwitcher();
    }};
</script>
"""))

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
                today_class = "border-brand/40 bg-brand/5 shadow-[0_0_20px_rgba(15,61,46,0.05)]" if is_today else "border-brand/5 hover:border-brand/20 bg-white"
                
                calendar_html += f"""
                <div class="aspect-square glass border rounded-3xl p-4 flex flex-col justify-between transition-all {today_class}">
                    <span class="text-xs font-bold { 'text-brand' if is_today else 'text-text-muted' }">{day}</span>
                    <div class="flex gap-1 flex-wrap">
                        {indicators}
                    </div>
                </div>
                """

    # Map posts to a list of HTML snippets
    scheduled_posts_html = []
    for p in [p for p in posts if p.status == "scheduled"][:5]:
        caption = p.caption[:60] if p.caption else "Untitled Post"
        time_str = p.scheduled_time.strftime("%b %d, %H:%M")
        scheduled_posts_html.append(f"""
            <div class="flex items-center justify-between p-4 bg-cream rounded-xl border border-brand/5 text-[10px] font-bold text-brand">
                <div class="flex items-center gap-3">
                    <div class="w-1.5 h-1.5 rounded-full bg-brand"></div>
                    {caption}...
                </div>
                <div class="text-text-muted tracking-widest">{time_str}</div>
            </div>
        """)
        
    scheduled_list_html = "".join(scheduled_posts_html)
    if not scheduled_list_html:
        scheduled_list_html = """
            <div class="py-12 flex flex-col items-center space-y-3">
                <div class="text-[11px] font-bold uppercase tracking-[0.3em] text-brand">No posts scheduled yet</div>
                <p class="text-xs text-text-muted">Create your first post to begin</p>
            </div>
        """

    content = f"""
    <div class="space-y-8">
        <div class="flex justify-between items-end">
            <div>
                <h1 class="text-3xl font-bold text-brand tracking-tight">Planning</h1>
                <p class="text-[10px] font-bold text-text-muted uppercase tracking-[0.3em]">Content Scheduler</p>
            </div>
            <div class="flex gap-4">
                <button onclick="openNewPostModal()" class="px-8 py-4 bg-brand text-white rounded-xl font-bold text-[11px] uppercase tracking-widest shadow-xl shadow-brand/20 hover:bg-brand-hover transition-all flex items-center gap-3">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
                    Schedule Post
                </button>
            </div>
        </div>
        
        <div class="grid grid-cols-7 gap-3">
            {calendar_html}
        </div>
        
        <div class="card p-10 bg-white border border-brand/5 text-center flex flex-col items-center justify-center space-y-6">
            <h3 class="text-[10px] font-bold uppercase tracking-[0.3em] text-accent">Planned Content</h3>
            <div class="space-y-4 w-full max-w-lg">
                {scheduled_list_html}
            </div>
        </div>
    </div>
    """
    
    return APP_LAYOUT_HTML.replace("{content}", content)\
                          .replace("{title}", "Calendar")\
                          .replace("{user_name}", user.name or user.email)\
                          .replace("{org_name}", org.name if org else "Personal Workspace")\
                          .replace("{admin_link}", admin_link)\
                          .replace("{active_dashboard}", "")\
                          .replace("{active_calendar}", "active")\
                          .replace("{active_automations}", "")\
                          .replace("{active_library}", "")\
                          .replace("{active_media}", "")\
                          .replace("{account_options}", "")\
                          .replace("{connect_instagram_modal}", CONNECT_INSTAGRAM_MODAL_HTML)\
                          .replace("{extra_js}", "")

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
    # Default status values to prevent scoping crashes (NameError)
    status_color = "text-text-muted"
    status_bg = "bg-brand/5"
    status_label = "Active"
    
    for a in autos:
        status_color = "text-emerald-600" if a.enabled else "text-rose-600"
        status_bg = "bg-emerald-50" if a.enabled else "bg-rose-50"
        status_label = "Active" if a.enabled else "Paused"
        
        mode_icon = '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>'
        if a.content_seed_mode == 'auto_library':
            mode_icon = '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>'
        
        # Consistent, safe JSON escaping for HTML attribute
        edit_data_json = html.escape(json.dumps({
            "id": a.id,
            "name": a.name,
            "topic": a.topic_prompt,
            "library_topic_slug": a.library_topic_slug,
            "seed_mode": a.content_seed_mode,
            "seed_text": a.content_seed_text,
            "time": a.post_time_local,
            "content_provider_scope": a.content_provider_scope
        }), quote=True)

        autos_html += f"""
        <div class="card p-8 bg-white border-brand/5 flex flex-col md:flex-row justify-between items-start md:items-center gap-8 group relative overflow-hidden transition-all hover:translate-y-[-2px]">
          <div class="absolute top-0 right-0 w-24 h-24 bg-brand/[0.01] rounded-full -mr-12 -mt-12 group-hover:scale-150 transition-transform duration-700"></div>
          
          <div class="flex items-start md:items-center gap-6 flex-1 min-w-0 relative">
            <div class="w-14 h-14 rounded-2xl bg-brand/5 flex items-center justify-center text-brand shrink-0 border border-brand/10 shadow-inner group-hover:bg-brand/10 transition-colors">
              {mode_icon}
            </div>
            <div class="min-w-0 space-y-2">
              <div class="flex items-center gap-3">
                <h3 class="text-xl font-bold text-brand tracking-tight truncate">{a.name}</h3>
                <button onclick="toggleAuto(event, {a.id}, {str(not a.enabled).lower()})" class="px-3 py-1 {status_bg} {status_color} rounded-lg text-[8px] font-black uppercase tracking-widest border border-brand/5">{status_label}</button>
              </div>
              <p class="text-xs text-text-muted font-medium line-clamp-1 italic max-w-xl opacity-70 group-hover:opacity-100 transition-opacity">"{a.topic_prompt}"</p>
              
              <div class="flex flex-wrap gap-5 pt-1">
                <div class="flex items-center gap-2">
                    <span class="text-[8px] font-bold text-accent uppercase tracking-widest">Strategy:</span>
                    <span class="text-[9px] font-black text-brand uppercase tracking-wider">{ 'Verified Context' if a.content_seed_mode == 'auto_library' else 'Guided Script' }</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="text-[8px] font-bold text-accent uppercase tracking-widest">Schedule:</span>
                    <span class="text-[9px] font-black text-brand uppercase tracking-wider">Daily @ {a.post_time_local or '09:00'}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="flex items-center gap-3 w-full md:w-auto relative border-t md:border-t-0 border-brand/5 pt-6 md:pt-0">
            <button onclick="showEditModal({edit_data_json})" class="flex-1 md:flex-none px-6 py-4 bg-white border border-brand/10 rounded-2xl font-bold text-[10px] uppercase tracking-widest text-text-muted hover:text-brand hover:border-brand/30 hover:bg-brand/[0.02] transition-all shadow-sm">Configure</button>
            <button onclick="runNow(event, {a.id})" class="flex-1 md:flex-none px-6 py-4 bg-brand rounded-2xl text-white font-bold text-[10px] uppercase tracking-widest shadow-xl shadow-brand/20 hover:scale-[1.02] transition-all">Manifest Now</button>
          </div>
        </div>
        """

    empty_state_html = """
        <div class="card p-24 bg-white border-brand/5 border-dashed border-2 bg-brand/[0.01] text-center flex flex-col items-center justify-center space-y-8">
            <div class="w-24 h-24 rounded-[2.5rem] bg-brand/5 flex items-center justify-center text-brand border border-brand/10 shadow-inner">
              <svg class="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"/></svg>
            </div>
            <div class="space-y-3">
              <h3 class="text-2xl font-bold text-brand tracking-tight italic">Establish your first Growth Plan</h3>
              <p class="text-text-muted text-sm max-w-sm font-medium">Set up how and when your creative vision comes to life.</p>
            </div>
            <button onclick="showNewAutoModal()" class="px-10 py-4 bg-brand text-white rounded-2xl font-bold text-[11px] uppercase tracking-widest shadow-xl shadow-brand/20 hover:bg-brand-hover transition-all">Establish Plan</button>
        </div>
    """
    
    content = """
    <div class="space-y-10">
      <div class="flex justify-between items-end">
        <div>
        <h1 class="text-3xl font-bold text-brand tracking-tight italic">Studio</h1>
        <p class="text-[10px] font-bold text-text-muted uppercase tracking-[0.4em]">Content Growth Plans</p>
      </div>
      <button onclick="showNewAutoModal()" class="hidden md:flex px-8 py-4 bg-brand rounded-2xl font-bold text-[10px] uppercase tracking-[0.2em] text-white shadow-2xl shadow-brand/30 hover:translate-y-[-2px] transition-all items-center gap-3">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
          Establish New Plan
      </button>
      </div>

      <div class="space-y-6">
        {autos_html}
      </div>
    </div>

    <!-- Edit Modal -->
    <div id="editModal" class="fixed inset-0 bg-brand/20 backdrop-blur-xl z-[100] hidden flex flex-col items-center justify-center p-0 md:p-6">
      <div class="glass w-full h-[90vh] md:h-auto md:max-w-xl pb-safe rounded-t-[2.5rem] md:rounded-[3rem] p-6 md:p-10 space-y-10 animate-in slide-in-from-bottom md:zoom-in-95 duration-300 border-t md:border border-brand/10 bg-white overflow-y-auto">
        <div class="flex justify-between items-center">
          <div>
            <h2 class="text-2xl font-bold text-brand tracking-tight italic">Refine Your <span class="text-accent font-normal">Creative Strategy</span></h2>
            <p class="text-[10px] font-bold text-text-muted uppercase tracking-widest">Adjust this growth plan</p>
          </div>
          <button onclick="hideEditModal()" class="w-10 h-10 flex items-center justify-center rounded-full hover:bg-brand/5 text-text-muted hover:text-brand transition-all"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg></button>
        </div>
        
        <input type="hidden" id="editId">
        
        <div class="space-y-10 max-w-lg mx-auto">
          <!-- SECTION 1 -->
          <div class="space-y-4">
            <div>
              <h3 class="text-sm font-bold text-brand italic">Identity & Naming</h3>
              <p class="text-[10px] text-text-muted font-medium uppercase tracking-wider">Give your plan a simple name</p>
            </div>
            <input type="text" id="editName" class="w-full bg-cream/30 border border-brand/5 rounded-2xl p-5 text-brand text-sm focus:border-brand/20 focus:bg-white transition-all font-bold outline-none shadow-sm" placeholder="e.g. Ramadan Reminders">
          </div>

          <!-- SECTION 2 -->
          <div class="space-y-4">
            <div>
              <div class="flex justify-between items-end">
                <div>
                  <h3 class="text-sm font-bold text-brand">What content do you want to share?</h3>
                  <p class="text-[10px] text-text-muted font-medium uppercase tracking-wider">Describe the themes you want your content to focus on</p>
                </div>
                <button onclick="suggestAutomationTopic('editTopic', 'editLibraryTopic')" class="text-[9px] font-bold text-accent uppercase hover:text-brand transition-all pb-1">Browse Ideas</button>
              </div>
            </div>
            <textarea id="editTopic" rows="3" class="w-full bg-cream/30 border border-brand/5 rounded-2xl p-5 text-brand text-sm focus:border-brand/20 focus:bg-white transition-all font-medium italic outline-none shadow-sm" placeholder="e.g. Daily reminders on patience and gratitude..."></textarea>
            <input type="hidden" id="editLibraryTopic">
          </div>

          <!-- SECTION 3 -->
          <div class="space-y-4">
            <div>
              <h3 class="text-sm font-bold text-brand italic">Generation Strategy</h3>
              <p class="text-[10px] text-text-muted font-medium uppercase tracking-wider">Choose your preferred drafting approach</p>
            </div>
            <select id="editSeedMode" onchange="toggleSeedText()" class="w-full bg-cream/30 border border-brand/5 rounded-2xl p-5 text-brand text-sm font-bold outline-none appearance-none shadow-sm">
                <option value="auto_library">Verified Content (Research Synthesis)</option>
                <option value="manual">Guided Drafting (Seed Text)</option>
            </select>
          </div>

          <div id="seedTextGroup" class="space-y-4 hidden">
            <div class="flex justify-between items-center px-1">
              <label class="text-[10px] font-bold text-brand uppercase tracking-widest">Grounding Text</label>
              <button onclick="openLibraryPicker('editSeedText')" class="text-[9px] font-bold text-accent hover:text-brand transition-all">Select From Library</button>
            </div>
            <textarea id="editSeedText" rows="4" class="w-full bg-cream/40 border border-brand/10 rounded-2xl p-5 text-brand text-[10px] outline-none h-[120px]"></textarea>
          </div>

          <!-- SECTION 4 -->
          <div class="space-y-4">
            <div>
              <h3 class="text-sm font-bold text-brand italic">Knowledge Pool</h3>
              <p class="text-[10px] text-text-muted font-medium uppercase tracking-wider">Which repository should we pull from?</p>
            </div>
            <select id="editProviderScope" class="w-full bg-cream/30 border border-brand/5 rounded-2xl p-5 text-brand text-sm font-bold outline-none appearance-none shadow-sm">
                <option value="all_sources">Unified Knowledge (Both Libraries)</option>
                <option value="system_library">Sabeel Studio Defaults</option>
                <option value="user_library">Your Personal Knowledge</option>
            </select>
          </div>

          <!-- SECTION 5 -->
          <div class="space-y-4">
            <div>
              <h3 class="text-sm font-bold text-brand italic">Manifestation Schedule</h3>
              <p class="text-[10px] text-text-muted font-medium uppercase tracking-wider">When should new drafts be crafted?</p>
            </div>
            <input type="time" id="editTime" class="w-full bg-cream/30 border border-brand/5 rounded-2xl p-5 text-brand text-sm font-bold outline-none shadow-sm">
          </div>
        </div>

        <div class="flex gap-4 pt-4 border-t border-brand/5 max-w-lg mx-auto w-full">
          <button onclick="hideEditModal()" class="flex-1 py-5 bg-cream/30 border border-brand/5 rounded-2xl font-bold text-[10px] uppercase tracking-widest text-text-muted hover:bg-cream/50 transition-all">Discard</button>
          <button id="btnSaveEdit" onclick="saveAutomation()" class="flex-[2] py-5 bg-brand rounded-2xl font-bold text-[10px] uppercase tracking-widest text-white shadow-xl shadow-brand/20 hover:scale-[1.01] transition-all">Save Plan</button>
        </div>
      </div>
    </div>

    <!-- New Automation Modal -->
    <div id="newAutoModal" class="fixed inset-0 bg-brand/20 backdrop-blur-xl z-[100] hidden flex flex-col items-center justify-center p-0 md:p-6">
      <div class="glass w-full h-[90vh] md:h-auto md:max-w-xl pb-safe rounded-t-[2.5rem] md:rounded-[3rem] p-6 md:p-10 space-y-10 animate-in slide-in-from-bottom md:zoom-in-95 duration-300 border-t md:border border-brand/10 bg-white overflow-y-auto">
        <div class="flex justify-between items-center">
          <div>
            <h2 class="text-2xl font-bold text-brand tracking-tight italic">Establish Your <span class="text-accent font-normal">Growth Plan</span></h2>
            <p class="text-[10px] font-bold text-text-muted uppercase tracking-widest">Architect a new creative stream</p>
          </div>
          <button onclick="hideNewAutoModal()" class="w-10 h-10 flex items-center justify-center rounded-full hover:bg-brand/5 text-text-muted hover:text-brand transition-all"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg></button>
        </div>
        
        <div class="space-y-10 max-w-lg mx-auto">
          <!-- Step 1: Blueprint -->
          <div class="space-y-4">
            <div>
              <h3 class="text-sm font-bold text-brand italic">Identity & Naming</h3>
              <p class="text-[10px] text-text-muted font-medium uppercase tracking-wider">Give this growth plan a clear, inspiring name</p>
            </div>
            <input type="text" id="newName" class="w-full bg-cream/30 border border-brand/5 rounded-2xl p-5 text-brand text-sm focus:border-brand/20 focus:bg-white transition-all font-bold outline-none shadow-sm" placeholder="e.g. Daily Wisdom Pool">
          </div>

          <!-- SECTION 2 -->
          <div class="space-y-4">
            <div class="space-y-1">
              <h3 class="text-sm font-bold text-brand">Choose Account</h3>
              <p class="text-[10px] text-text-muted font-medium uppercase tracking-wider">Target delivery account</p>
            </div>
            <select id="newAccount" class="w-full bg-cream/30 border border-brand/5 rounded-2xl p-5 text-brand text-sm font-bold outline-none appearance-none shadow-sm">
                {account_options}
            </select>
          </div>

          <!-- SECTION 3 -->
          <div class="space-y-4">
            <div>
              <div class="flex justify-between items-end">
                <div>
                  <h3 class="text-sm font-bold text-brand">What content do you want to share?</h3>
                  <p class="text-[10px] text-text-muted font-medium uppercase tracking-wider">Describe the themes for this plan</p>
                </div>
                <button onclick="suggestAutomationTopic('newTopic', 'newLibraryTopic')" class="text-[9px] font-bold text-accent uppercase hover:text-brand transition-all pb-1">Link Source</button>
              </div>
            </div>
            <textarea id="newTopic" oninput="debounceComposerSuggest('newTopic', 'autoSuggestions')" rows="3" class="w-full bg-cream/30 border border-brand/5 rounded-2xl p-5 text-brand text-sm focus:border-brand/20 focus:bg-white transition-all font-medium outline-none shadow-sm" placeholder="e.g. Deep-dive into Quranic patient persistence..."></textarea>
            <input type="hidden" id="newLibraryTopic">
            <div id="autoSuggestions" class="hidden flex-col gap-2 pt-2"></div>
          </div>

          <!-- SECTION 4 -->
          <div class="space-y-4">
            <div>
              <h3 class="text-sm font-bold text-brand italic">Generation Strategy</h3>
              <p class="text-[10px] text-text-muted font-medium uppercase tracking-wider">Choose your preferred drafting approach</p>
            </div>
            <select id="newSeedMode" onchange="toggleNewSeedText()" class="w-full bg-cream/30 border border-brand/5 rounded-2xl p-5 text-brand text-sm font-bold outline-none appearance-none shadow-sm">
                <option value="auto_library">Verified Content (Knowledge Pool)</option>
                <option value="manual">Guided Drafting (Manual Seed)</option>
            </select>
          </div>

          <div id="newSeedTextGroup" class="space-y-4 hidden">
            <div class="flex justify-between items-center px-1">
              <label class="text-[10px] font-bold text-brand uppercase tracking-widest">Grounding Text</label>
              <button onclick="openLibraryPicker('newSeedText')" class="text-[9px] font-bold text-accent hover:text-brand transition-all">Import Knowledge</button>
            </div>
            <textarea id="newSeedText" rows="4" class="w-full bg-cream/40 border border-brand/10 rounded-2xl p-5 text-brand text-[10px] outline-none h-[120px]"></textarea>
          </div>

          <!-- SECTION 5 -->
          <div class="space-y-4">
            <div>
              <h3 class="text-sm font-bold text-brand">Content Library</h3>
              <p class="text-[10px] text-text-muted font-medium uppercase tracking-wider">Which repository should we pull from?</p>
            </div>
            <select id="newProviderScope" class="w-full bg-cream/30 border border-brand/5 rounded-2xl p-5 text-brand text-sm font-bold outline-none appearance-none shadow-sm">
                <option value="all_sources">Unified Knowledge (Both Libraries)</option>
                <option value="system_library">Sabeel Studio Defaults</option>
                <option value="user_library">Your Personal Knowledge</option>
            </select>
          </div>

          <!-- Step 6: Manifestation Cycle -->
          <div class="space-y-4">
            <div>
              <h3 class="text-sm font-bold text-brand italic">Manifestation Schedule</h3>
              <p class="text-[10px] text-text-muted font-medium uppercase tracking-wider">When should new drafts be crafted?</p>
            </div>
            <input type="time" id="newTime" value="09:00" class="w-full bg-cream/30 border border-brand/5 rounded-2xl p-5 text-brand text-sm font-bold outline-none shadow-sm">
          </div>
        </div>

        <div class="flex gap-4 pt-4 border-t border-brand/5 max-w-lg mx-auto w-full">
          <button onclick="hideNewAutoModal()" class="flex-1 py-5 bg-cream/30 border border-brand/5 rounded-2xl font-bold text-[10px] uppercase tracking-widest text-text-muted hover:bg-cream/50 transition-all">Discard</button>
          <button id="btnSaveNew" onclick="saveNewAutomation()" class="flex-[2] py-5 bg-brand rounded-2xl font-bold text-[10px] uppercase tracking-widest text-white shadow-xl shadow-brand/20 hover:scale-[1.01] transition-all">Save Plan</button>
        </div>
      </div>
    </div>

    <!-- Library Picker Modal -->
    <div id="libraryPickerModal" class="fixed inset-0 bg-black/90 backdrop-blur-md z-[150] hidden flex items-end md:items-center justify-center p-0 md:p-6">
      <div class="glass w-full md:max-w-2xl pb-safe rounded-t-[2.5rem] md:rounded-[2.5rem] p-6 md:p-8 space-y-6 border-t md:border border-white/10 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
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
      function showNewAutoModal() {
        document.getElementById('newAutoModal').classList.remove('hidden');
      }

      function hideNewAutoModal() {
        document.getElementById('newAutoModal').classList.add('hidden');
      }

      function toggleNewSeedText() {
        const mode = document.getElementById('newSeedMode').value;
        const group = document.getElementById('newSeedTextGroup');
        if (mode === 'manual') group.classList.remove('hidden');
        else group.classList.add('hidden');
      }

      async function saveNewAutomation() {
        const providerScope = document.getElementById('newProviderScope').value;
        const btn = document.getElementById('btnSaveNew');
        if (!btn) return;

        const payload = {
          name: document.getElementById('newName').value,
          ig_account_id: parseInt(document.getElementById('newAccount').value),
          topic_prompt: document.getElementById('newTopic').value,
          content_seed_mode: document.getElementById('newSeedMode').value,
          content_seed_text: document.getElementById('newSeedText').value,
          post_time_local: document.getElementById('newTime').value,
          content_provider_scope: providerScope,
          enabled: true
        };

        if (!payload.name || !payload.topic_prompt || isNaN(payload.ig_account_id)) {
          alert('Please provide a Name, Topic, and select a Target Account.');
          return;
        }
        
        btn.disabled = true;
        const originalText = btn.textContent;
        btn.innerHTML = '<span class="flex items-center gap-2"><svg class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> ESTABLISHING...</span>';

        try {
          const res = await fetch('/automations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
          if (res.ok) {
            btn.innerHTML = 'SUCCESS!';
            btn.className = btn.className.replace('bg-brand', 'bg-emerald-500');
            setTimeout(() => window.location.reload(), 1000);
          } else {
            const err = await res.text();
            alert('Failed to establish plan: ' + err);
            btn.disabled = false; 
            btn.textContent = originalText; 
          }
        } catch(e) { 
          alert('Network disruption occurred. Please check your connection.'); 
          btn.disabled = false; 
          btn.textContent = originalText; 
        }
      }

      function showEditModal(data) {
        document.getElementById('editId').value = data.id;
        document.getElementById('editName').value = data.name;
        document.getElementById('editTopic').value = data.topic;
        document.getElementById('editLibraryTopic').value = data.library_topic_slug || '';
        document.getElementById('editSeedMode').value = (data.seed_mode === 'none' ? 'auto_library' : data.seed_mode);
        document.getElementById('editSeedText').value = data.seed_text;
        document.getElementById('editTime').value = data.time;
        document.getElementById('editProviderScope').value = data.content_provider_scope || 'all_sources';

        toggleSeedText();
        document.getElementById('editModal').classList.remove('hidden');
      }

      function hideEditModal() {
        document.getElementById('editModal').classList.add('hidden');
      }

      function toggleSeedText() {
        const mode = document.getElementById('editSeedMode').value;
        const group = document.getElementById('seedTextGroup');
        if (mode === 'manual') group.classList.remove('hidden');
        else group.classList.add('hidden');
      }

      async function saveAutomation() {
        const id = document.getElementById('editId').value;
        const providerScope = document.getElementById('editProviderScope').value;
        const btn = document.getElementById('btnSaveEdit');
        if (!btn) return;

        const payload = {
          name: document.getElementById('editName').value,
          topic_prompt: document.getElementById('editTopic').value,
          library_topic_slug: document.getElementById('editLibraryTopic').value,
          content_seed_mode: document.getElementById('editSeedMode').value,
          content_seed_text: document.getElementById('editSeedText').value,
          post_time_local: document.getElementById('editTime').value,
          content_provider_scope: providerScope
        };
        
        btn.disabled = true;
        const originalText = btn.textContent;
        btn.innerHTML = '<span class="flex items-center gap-2"><svg class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> SAVING...</span>';

        try {
          const res = await fetch(`/automations/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
          if (res.ok) {
            btn.innerHTML = 'SYNCED!';
            btn.className = btn.className.replace('bg-brand', 'bg-emerald-500');
            setTimeout(() => window.location.reload(), 1000);
          } else {
            const err = await res.text();
            alert('Save failed: ' + err);
            btn.disabled = false; 
            btn.textContent = originalText; 
          }
        } catch(e) { 
          alert('Failed to transmit update. Verify your connection.'); 
          btn.disabled = false; 
          btn.textContent = originalText; 
        }
      }

      async function suggestAutomationTopic(inputId, hiddenId) {
          const prompt = document.getElementById(inputId).value;
          if (!prompt) return alert("Please enter a topic overview first.");
          
          const btn = event.target;
          const originalText = btn.textContent;
          btn.textContent = 'SEARCHING...';
          btn.disabled = true;
          
          try {
              const res = await fetch('/library/topic-suggest', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ text: prompt, max: 1 })
              });
              const data = await res.json();
              if (data.suggestions && data.suggestions.length > 0) {
                  const s = data.suggestions[0];
                  if (confirm(`Suggested Library Source: ${s.topic}\n(${s.reason})\n\nLink this context for safer drafting?`)) {
                      document.getElementById(hiddenId).value = s.slug;
                      btn.textContent = `LINKED: ${s.topic.toUpperCase()}`;
                      btn.classList.add('text-green-500');
                  } else { btn.textContent = originalText; }
              } else {
                  alert("No direct source matches found. Generator will rely on broader library defaults.");
                  btn.textContent = originalText;
              }
          } catch(e) { btn.textContent = originalText; }
          finally { btn.disabled = false; }
      }

      // ---- COMPOSER SMART ASSIST ----
      let composerSuggestTimer;
      function debounceComposerSuggest(inputId, containerId) {
          clearTimeout(composerSuggestTimer);
          composerSuggestTimer = setTimeout(() => {
              runComposerSuggest(inputId, containerId);
          }, 800);
      }

      async function runComposerSuggest(inputId, containerId) {
          const text = document.getElementById(inputId).value;
          const container = document.getElementById(containerId);
          
          if (!text || text.length < 3) {
              container.classList.add('hidden');
              container.innerHTML = '';
              return;
          }
          
          try {
              container.innerHTML = '<span class="text-[8px] font-black uppercase tracking-widest text-muted animate-pulse">Scanning library for context...</span>';
              container.classList.remove('hidden');
              container.classList.add('flex');
              
              const res = await fetch(`/library/suggest?query=${encodeURIComponent(text)}`);
              const items = await res.json();
              
              if (items.length === 0) {
                  container.innerHTML = '<span class="text-[8px] font-black uppercase tracking-widest text-muted">No specific grounding found. Sabeel will use verified defaults.</span>';
                  return;
              }
              
              let html = '<span class="text-[8px] font-black uppercase tracking-widest text-brand mb-1">Recommended Grounding</span>';
              items.forEach((item, idx) => {
                  if(idx > 2) return; 
                  
                  const safeText = item.text.replace(/"/g, '&quot;').replace(/\\n/g, '\\\\n');
                  const preview = item.text.length > 70 ? item.text.substring(0, 70) + "..." : item.text;
                  
                  html += `
                  <div class="p-3 bg-white/5 rounded-xl border border-white/10 flex items-center justify-between gap-4">
                      <div class="flex-1 overflow-hidden">
                          <h5 class="text-[9px] font-black text-white uppercase tracking-tight truncate">${item.title}</h5>
                          <p class="text-[9px] text-white/50 truncate italic">${preview}</p>
                      </div>
                      <button type="button" onclick="insertComposerSuggest('${inputId}', '${safeText}', ${item.id})" class="px-3 py-1.5 bg-brand/20 text-brand rounded-lg text-[8px] font-black uppercase tracking-widest hover:bg-brand hover:text-white transition-all shrink-0">Use This</button>
                  </div>`;
              });
              container.innerHTML = html;
          } catch(e) { container.classList.add('hidden'); }
      }

      function insertComposerSuggest(inputId, textToInsert, entryId) {
          const input = document.getElementById(inputId);
          const nl = String.fromCharCode(10);
          if (input.tagName === 'TEXTAREA') {
              if (input.value.trim() !== '') input.value += nl + nl;
              input.value += textToInsert;
          } else {
              if (inputId === 'newTopic') {
                  document.getElementById('newSeedMode').value = 'manual';
                  toggleNewSeedText();
                  document.getElementById('newSeedText').value = textToInsert;
              }
          }
          
          trackInteraction("used_entry", entryId.toString(), "composer");
          input.classList.add('ring-2', 'ring-brand');
          setTimeout(() => input.classList.remove('ring-2', 'ring-brand'), 1000);
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
          list.innerHTML = '<div class="text-center py-10 text-[9px] font-black uppercase text-muted animate-pulse">Consulting Library...</div>';
          try {
              let url = `/library/entries?query=${encodeURIComponent(query)}`;
              if (topic) url += `&topic=${encodeURIComponent(topic)}`;
              if (type) url += `&item_type=${encodeURIComponent(type)}`;
              const res = await fetch(url);
              const entries = await res.json();
              if (entries.length === 0) {
                  list.innerHTML = '<div class="text-center py-10 text-[9px] font-black uppercase text-muted opacity-40">No entries found</div>';
                  return;
              }
              list.innerHTML = '';
              entries.forEach(e => {
                  const div = document.createElement('div');
                  div.className = "p-4 bg-white/5 border border-white/5 rounded-2xl hover:bg-white/10 hover:border-brand/30 transition-all cursor-pointer space-y-2";
                  div.onclick = () => selectPickerEntry(e);
                  div.innerHTML = `
                      <div class="flex justify-between items-center">
                        <span class="text-[7px] font-black text-brand uppercase tracking-widest">${e.item_type}</span>
                        <span class="text-[8px] font-black text-muted">${e.topic || ''}</span>
                      </div>
                      <p class="text-[10px] text-white/70 line-clamp-2">${e.text.substring(0, 150)}...</p>
                  `;
                  list.appendChild(div);
              });
          } catch(e) {}
      }
      function selectPickerEntry(entry) {
          const target = document.getElementById(pickerTargetId);
          if (target) {
              const nl = String.fromCharCode(10);
              let credit = "";
              if (entry.item_type === 'hadith') credit = nl + nl + "[Ref: " + entry.meta.collection + " #" + entry.meta.hadith_number + "]";
              else if (entry.item_type === 'quran') credit = nl + nl + "[Quran " + entry.meta.surah_number + ":" + entry.meta.verse_start + "]";
              target.value = entry.text + credit;
          }
          closeLibraryPicker();
      }

      async function toggleAuto(event, id, enabled) {
        const btn = event.currentTarget;
        const originalText = btn.innerText;
        btn.disabled = true;
        btn.innerText = 'WAIT...';

        try {
          const res = await fetch(`/automations/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enabled })
          });
          if (res.ok) window.location.reload();
          else alert('Operation failed. Please try again.');
        } catch(e) { alert('Network error. Check your connection.'); }
        finally { btn.disabled = false; btn.innerText = originalText; }
      }

      async function runNow(event, id) {
        // Safety Sync: Ensure UI matches DB state
        try {
            const res = await fetch('/ig-accounts/me');
            const accounts = await res.json();
            if (accounts.length > 0 && !window.hasConnectedInstagram) {
                window.location.reload();
                return;
            }
        } catch(e) {}

        if (!window.hasConnectedInstagram) {
          openConnectInstagramModal();
          return;
        }
        if (!confirm('Start growth stream now? A new draft will be crafted immediately based on your verified strategy.')) return;
        const btn = event.target || event.currentTarget;
        btn.disabled = true;
        const originalText = btn.textContent;
        btn.innerHTML = '<span class="flex items-center gap-2"><svg class="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> DRAFTING...</span>';
        
        try {
          const res = await fetch(`/automations/${id}/run-once`, { method: 'POST' });
          if (res.ok) {
            btn.innerHTML = 'MANIFESTED!';
            btn.className = btn.className.replace('bg-brand', 'bg-emerald-500');
            setTimeout(() => {
                btn.disabled = false;
                btn.innerHTML = originalText;
                btn.className = btn.className.replace('bg-emerald-500', 'bg-brand');
                // Redirect user to home or notify them
                if(confirm('Draft generated! Open dashboard to review?')) window.location.href = '/app';
            }, 2000);
          } else {
            const err = await res.json();
            alert('Manifestation failed: ' + (err.detail || 'Limit reached or technical void.'));
            btn.disabled = false; 
            btn.innerHTML = originalText; 
          }
        } catch(e) { 
            alert('Network interruption during drafting.'); 
            btn.disabled = false; 
            btn.innerHTML = originalText; 
        }
      }
    </script>
    """
    
    return APP_LAYOUT_HTML.replace("{content}", content.replace("{autos_html}", autos_html or empty_state_html))\
                          .replace("{title}", "Automations")\
                          .replace("{user_name}", user.name or user.email)\
                          .replace("{org_name}", org.name if org else "Personal Workspace")\
                          .replace("{admin_link}", admin_link)\
                          .replace("{active_dashboard}", "")\
                          .replace("{active_calendar}", "")\
                          .replace("{active_automations}", "active")\
                          .replace("{active_library}", "")\
                          .replace("{active_media}", "")\
                          .replace("{account_options}", account_options)\
                          .replace("{connect_instagram_modal}", CONNECT_INSTAGRAM_MODAL_HTML)\
                          .replace("{extra_js}", "")

@router.get("/app/media", response_class=HTMLResponse)
async def app_media_page(
    user: User = Depends(require_user),
    db: Session = Depends(get_db)
):
    # REMOVED FORCED ONBOARDING REDIRECT
    org = db.query(Org).filter(Org.id == user.active_org_id).first()
    admin_link = '<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin</a>' if user.is_superadmin else ""
    
    content = """
    <div class="space-y-8">
      <div class="flex justify-between items-end">
        <div>
          <h1 class="text-3xl font-bold text-brand tracking-tight">Assets</h1>
          <p class="text-[10px] font-bold text-text-muted uppercase tracking-[0.3em]">Creative Media Studio</p>
        </div>
        <div class="flex gap-4">
            <button onclick="document.getElementById('mediaUploadInput').click()" class="px-8 py-4 bg-brand text-white rounded-xl font-bold text-[11px] uppercase tracking-widest shadow-xl shadow-brand/20 hover:bg-brand-hover transition-all flex items-center gap-3">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
                Upload Assets
            </button>
        </div>
      </div>
        <div id="mediaEmptyState" class="glass p-20 rounded-[3rem] border border-brand/5 bg-white text-center flex flex-col items-center justify-center space-y-6">
            <div class="w-20 h-20 rounded-[2rem] bg-brand/5 flex items-center justify-center border border-brand/10">
              <svg class="w-10 h-10 text-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"/></svg>
            </div>
            <div>
              <h3 class="text-[11px] font-bold uppercase tracking-[0.3em] text-brand">Media Library</h3>
              <p class="text-xs text-text-muted mt-2">Your media will appear here after you create posts</p>
            </div>
        </div>
    </div>
    """
    
    return APP_LAYOUT_HTML.replace("{content}", content)\
                          .replace("{title}", "Media Studio")\
                          .replace("{user_name}", user.name or user.email)\
                          .replace("{org_name}", org.name if org else "Personal Workspace")\
                          .replace("{admin_link}", admin_link)\
                          .replace("{active_dashboard}", "")\
                          .replace("{active_calendar}", "")\
                          .replace("{active_automations}", "")\
                          .replace("{active_library}", "")\
                          .replace("{active_media}", "active")\
                          .replace("{account_options}", "")\
                          .replace("{connect_instagram_modal}", CONNECT_INSTAGRAM_MODAL_HTML)\
                          .replace("{extra_js}", "")

@router.get("/app/library", response_class=HTMLResponse)
async def app_library_page(
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db)
):
    if not user:
        return RedirectResponse(url="/login")
    # REMOVED FORCED ONBOARDING REDIRECT
    org_id = user.active_org_id
    org = db.query(Org).filter(Org.id == org_id).first()
    
    # Check if user is admin for this org or superadmin
    is_admin = user.is_superadmin
    if not is_admin:
        membership = db.query(OrgMember).filter(OrgMember.user_id == user.id, OrgMember.org_id == org_id).first()
        if membership and membership.role in ["admin", "owner"]:
            is_admin = True

    admin_link = '<a href="/admin" class="text-[10px] font-black uppercase tracking-widest nav-link py-5 text-rose-400 hover:text-white transition-colors">Admin</a>' if user.is_superadmin else ""
    
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

    content = """
    <style>
        .dir-rtl {{ direction: rtl; unicode-bidi: bidi-override; }}
        .font-serif {{ font-family: 'Amiri', 'Traditional Arabic', serif; }}
        .hide-scrollbar::-webkit-scrollbar {{ display: none; }}
        .hide-scrollbar {{ -ms-overflow-style: none; scrollbar-width: none; }}
    </style>
    
    <div class="space-y-8">
      <div class="flex justify-between items-end">
        <div>
          <h1 class="text-3xl font-bold text-brand tracking-tight">Knowledge</h1>
          <p class="text-[10px] font-bold text-text-muted uppercase tracking-[0.3em]">Structured Library</p>
        </div>
        <div class="flex gap-4">
          <button onclick="openEntryModal()" class="px-8 py-4 bg-brand rounded-xl font-bold text-[11px] uppercase tracking-widest text-white shadow-xl shadow-brand/20 hover:bg-brand-hover transition-all flex items-center gap-3">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
            Add Knowledge
          </button>
        </div>
      </div>

      <!-- Main Layout: Sidebar + List -->
      <div class="flex flex-col md:flex-row gap-4 md:gap-8 flex-1 overflow-hidden min-h-0">
        <!-- Sidebar: Sources -->
        <div class="w-full md:w-80 glass rounded-[1.5rem] md:rounded-[2.5rem] bg-white flex flex-col overflow-hidden border border-brand/5 shrink-0">
          <div class="p-4 md:p-6 border-b border-brand/5 flex flex-col md:flex-col gap-4 bg-brand/5 items-start md:items-stretch justify-between">
            <div class="flex flex-col">
                <div class="flex items-center gap-3">
                    <h3 class="text-xs font-bold uppercase tracking-widest text-text-muted">Collections</h3>
                    <span id="sourceCount" class="text-[9px] font-bold text-brand bg-brand/10 px-2 py-0.5 rounded-full">0</span>
                </div>
                <span id="sabeelDefaultsLabel" class="hidden text-[8px] font-bold text-accent uppercase tracking-widest mt-1">Sabeel Recommendations</span>
            </div>
            
            {library_controls}
          </div>
          <div id="sourceList" class="flex flex-row md:flex-col overflow-x-auto md:overflow-y-auto p-4 gap-2 md:space-y-2 bg-white">
            <!-- Loaded via JS -->
          </div>
        </div>

        <!-- Main Content: Entries Grid -->
        <div class="flex-1 glass rounded-[2.5rem] bg-white flex flex-col overflow-hidden border border-brand/5">
          <div class="p-6 border-b border-brand/5 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 md:gap-0">
            <div class="flex flex-col md:flex-row items-start md:items-center gap-4 md:gap-6 w-full md:flex-1">
              <h3 class="hidden md:block text-[10px] font-bold uppercase tracking-[0.2em] text-text-muted shrink-0">Intelligence Engine</h3>
              <div class="relative w-full md:max-w-md group">
                <input type="text" id="entrySearch" oninput="debounceEntryQuery()" placeholder="Search your knowledge base..." class="w-full bg-cream/50 border border-brand/10 rounded-2xl px-6 py-3.5 text-[11px] font-bold text-brand outline-none focus:border-brand/30 focus:bg-white focus:shadow-lg focus:shadow-brand/5 transition-all placeholder:text-brand/20">
                <svg class="w-4 h-4 absolute right-4 top-1/2 -translate-y-1/2 text-brand/20 group-focus-within:text-brand transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
              </div>
            </div>
            <div class="flex items-center gap-4 ml-4">
                <div class="flex items-center gap-2 bg-cream border border-brand/10 rounded-xl px-4 py-2 relative">
                    <span class="text-[9px] font-bold uppercase text-text-muted">Topic:</span>
                    <select id="filterTopic" onchange="loadEntries()" class="bg-transparent text-[10px] font-bold uppercase tracking-widest text-brand outline-none cursor-pointer">
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
          
          <!-- RECOMMENDED TRACK -->
          <div id="recommendedTrackWrapper" class="hidden flex-col border-b border-brand/5 bg-gradient-to-b from-brand/5 to-transparent shrink-0">
            <div class="px-6 md:px-8 py-3 flex items-center justify-between">
              <h3 class="text-[9px] font-bold uppercase tracking-widest text-brand flex items-center gap-2">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143z"/></svg>
                Recommended For You
              </h3>
            </div>
            <div id="recommendedCards" class="flex gap-4 px-6 md:px-8 pb-4 overflow-x-auto hide-scrollbar">
              <!-- Loaded via JS -->
            </div>
          </div>

          <!-- Topic Chips -->
          <div id="topicChips" class="px-6 md:px-8 py-3 border-b border-brand/5 flex gap-3 overflow-x-auto hide-scrollbar bg-cream/50">
                <!-- Populated via JS -->
          </div>
          <div id="entryList" class="flex-1 overflow-y-auto p-8 grid grid-cols-1 xl:grid-cols-2 gap-6 items-start content-start hide-scrollbar bg-white">
            <!-- Loaded via JS -->
            <div class="col-span-full h-full flex flex-col items-center justify-center text-center space-y-6 py-20 animate-in fade-in duration-500">
                <div class="w-16 h-16 rounded-3xl bg-brand/5 flex items-center justify-center border border-brand/10">
                    <svg class="w-8 h-8 text-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"/></svg>
                </div>
                <div>
                  <h3 class="text-[11px] font-bold uppercase tracking-[0.3em] text-brand">Knowledge Collection</h3>
                  <p class="text-xs text-text-muted mt-2">Select a collection to begin browsing</p>
                </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Unified Entry Modal -->
    <div id="entryModal" class="fixed inset-0 bg-brand/20 backdrop-blur-xl z-[500] hidden flex items-center justify-center p-6 animate-in fade-in duration-300">
      <div class="glass max-w-5xl w-full p-10 rounded-[3rem] border border-brand/10 shadow-2xl space-y-8 max-h-[90vh] overflow-y-auto hide-scrollbar bg-white">
        <div class="flex justify-between items-center">
            <div>
                <h2 id="entryModalTitle" class="text-3xl font-bold text-brand tracking-tight">Add <span class="text-accent">Knowledge</span></h2>
                <p class="text-[10px] font-bold text-text-muted uppercase tracking-[0.2em] mt-1">Thoughtfully populate your database</p>
            </div>
            <button onclick="hideEntryModal()" class="w-10 h-10 rounded-2xl bg-brand/5 flex items-center justify-center text-text-muted hover:bg-brand/10 hover:text-brand transition-all">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
            </button>
        </div>

        <input type="hidden" id="entryId">
        
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-10">
            <!-- Left Side: Source & Settings -->
            <div class="lg:col-span-4 space-y-6 bg-brand/5 p-8 rounded-[2.5rem] border border-brand/5">
                <div class="space-y-4">
                    <label class="text-[10px] font-bold uppercase tracking-[0.3em] text-brand">Collection Name</label>
                    <select id="sourceSelect" onchange="checkNewSource()" class="w-full bg-white border border-brand/10 rounded-2xl px-6 py-4 text-sm text-brand outline-none focus:ring-2 focus:ring-brand font-bold appearance-none">
                        <option value="">Select or Create New...</option>
                        <!-- Populated via JS -->
                    </select>
                </div>

                <div id="newSourceFields" class="space-y-6 hidden animate-in slide-in-from-top-2">
                    <div class="space-y-2">
                        <label class="text-[9px] font-bold uppercase tracking-[0.2em] text-text-muted">New Collection Title</label>
                        <input type="text" id="newSourceName" class="w-full bg-white border border-brand/10 rounded-2xl px-6 py-4 text-sm text-brand outline-none focus:ring-2 focus:ring-accent/50" placeholder="e.g. My Personal Journal">
                    </div>
                </div>

                <div class="space-y-4">
                    <label class="text-[10px] font-bold uppercase tracking-[0.3em] text-brand">Knowledge Type</label>
                    <div class="grid grid-cols-2 gap-2">
                        <button onclick="setEntryType('quran', this)" class="type-btn p-4 rounded-2xl border border-brand/5 bg-white hover:bg-brand/5 text-[10px] font-bold uppercase tracking-wider text-text-muted transition-all flex flex-col items-center gap-2">
                            <span class="text-xs">📖</span> Quran
                        </button>
                        <button onclick="setEntryType('hadith', this)" class="type-btn p-4 rounded-2xl border border-brand/5 bg-white hover:bg-brand/5 text-[10px] font-bold uppercase tracking-wider text-text-muted transition-all flex flex-col items-center gap-2">
                            <span class="text-xs">📜</span> Hadith
                        </button>
                        <button onclick="setEntryType('quote', this)" class="type-btn p-4 rounded-2xl border border-brand/5 bg-white hover:bg-brand/5 text-[10px] font-bold uppercase tracking-wider text-text-muted transition-all flex flex-col items-center gap-2">
                            <span class="text-xs">💬</span> Quote
                        </button>
                        <button onclick="setEntryType('book', this)" class="type-btn p-4 rounded-2xl border border-brand/5 bg-white hover:bg-brand/5 text-[10px] font-bold uppercase tracking-wider text-text-muted transition-all flex flex-col items-center gap-2">
                            <span class="text-xs">📚</span> Book
                        </button>
                    </div>
                    <input type="hidden" id="entryType" value="note">
                </div>
                <div id="globalToggleContainer" class="hidden py-4 border-t border-brand/5 mt-6 animate-in slide-in-from-bottom-2">
                    <label class="flex items-center gap-3 cursor-pointer group">
                        <div class="relative">
                            <input type="checkbox" id="isGlobalCheckbox" class="sr-only peer">
                            <div class="w-11 h-6 bg-brand/10 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
                        </div>
                        <span class="text-[10px] font-bold uppercase tracking-widest text-text-muted group-hover:text-brand transition-colors">Sabeel Recommendation (Global)</span>
                    </label>
                </div>
            </div>

            <!-- Right Side: Content & Metadata -->
            <div class="lg:col-span-8 space-y-8">
                <div class="space-y-4">
                    <div class="flex justify-between items-end">
                        <label class="text-[10px] font-bold uppercase tracking-[0.3em] text-brand">Knowledge Content</label>
                        <span id="charCount" class="text-[9px] font-bold text-text-muted tracking-widest">0 / 3000</span>
                    </div>
                    <textarea id="entryText" oninput="updateCharCount()" rows="8" class="w-full bg-cream border border-brand/10 rounded-[2rem] px-8 py-8 text-sm text-brand outline-none focus:ring-2 focus:ring-brand leading-relaxed placeholder:text-brand/10" placeholder="Paste the verse, hadith, or quote text here..."></textarea>
                </div>

                <div id="dynamicMetadata" class="grid grid-cols-1 md:grid-cols-2 gap-6 animate-in fade-in">
                    <!-- Dynamic fields based on type -->
                </div>

                <div class="flex gap-4 pt-10">
                    <button onclick="hideEntryModal()" class="flex-1 py-5 bg-white border border-brand/10 rounded-2xl font-bold text-[11px] uppercase tracking-[0.2em] text-brand hover:bg-brand/5 transition-all">Cancel</button>
                    <button onclick="saveEntry()" class="flex-[2] py-5 bg-brand rounded-2xl font-bold text-[11px] uppercase tracking-[0.2em] text-white shadow-2xl shadow-brand/40 hover:bg-brand-hover transition-all">Commit Knowledge</button>
                </div>
            </div>
        </div>
      </div>
    </div>

    <!-- Library Picker Modal (Reused) -->
    <div id="libraryPickerModal" class="fixed inset-0 bg-black/90 backdrop-blur-md z-[150] hidden flex items-end md:items-center justify-center p-0 md:p-6">
      <div class="glass w-full md:max-w-2xl pb-safe rounded-t-[2.5rem] md:rounded-[2.5rem] p-6 md:p-8 space-y-6 border-t md:border border-white/10 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
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
      console.log("Library System: Ready");
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
                  chip.className = "flex-shrink-0 px-4 py-2 rounded-xl bg-white border border-brand/5 text-[9px] font-bold uppercase tracking-widest text-brand/40 hover:border-brand/30 hover:bg-brand/5 hover:text-brand transition-all shadow-sm";
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
              
              const defaultsLabel = document.getElementById('sabeelDefaultsLabel');
              if (showGlobalOnly) {
                  if (defaultsLabel) defaultsLabel.classList.remove('hidden');
              } else {
                  if (defaultsLabel) defaultsLabel.classList.add('hidden');
              }

              if (sources.length === 0 && !showGlobalOnly) {
                  // Wait! If org is empty, automatically swap to SYSTEM
                  toggleGlobalView(true);
                  return;
              }

              document.getElementById('sourceCount').textContent = sources.length;
              
              const select = document.getElementById('sourceSelect');
              if (select) select.innerHTML = '<option value="">Select or Create New...</option>';
              
              list.innerHTML = '';
              
              if (sources.length === 0) {
                  list.innerHTML = '<div class="p-10 text-center text-muted font-black text-[9px] uppercase tracking-widest">No collections found</div>';
              }
              
              sources.forEach(s => {
                  // Update sidebar list
                  const isActive = currentSourceId == s.id;
                  const el = document.createElement('div');
                  el.className = `p-4 px-5 rounded-2xl cursor-pointer transition-all border flex items-center gap-4 group ${isActive ? 'bg-brand/5 border-brand/20 shadow-sm' : 'bg-white border-transparent hover:bg-brand/[0.02] hover:border-brand/10'}`;
                  el.onclick = () => selectSource(s);
                  
                  const folderIcon = `
                    <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors ${isActive ? 'bg-brand text-white' : 'bg-brand/5 text-brand group-hover:bg-brand/10'}">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                    </div>`;

                  el.innerHTML = `
                      ${folderIcon}
                      <div class="flex-1 overflow-hidden">
                          <div class="text-[10px] font-bold truncate ${isActive ? 'text-brand' : 'text-text-main group-hover:text-brand'} uppercase tracking-wider">${s.name}</div>
                          <div class="text-[8px] font-bold text-muted uppercase tracking-widest mt-0.5 flex items-center gap-2">
                            ${s.category || 'Collection'}
                            ${s.org_id ? '' : '<span class="text-[7px] text-accent px-1.5 py-0 bg-accent/10 border border-accent/10 rounded-full">SYSTEM</span>'}
                          </div>
                      </div>
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
              list.innerHTML = '<div class="text-rose-400 text-[10px] font-bold p-10">Something went wrong.</div>';
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
               libraryEntries = {};
               entries.forEach(e => {
                     libraryEntries[e.id] = e;
                     const isGlobal = e.org_id === null;
                     const el = document.createElement('div');
                     el.className = `card p-8 group relative flex flex-col h-full bg-white border border-brand/5 hover:border-brand/30 hover:shadow-xl hover:shadow-brand/5 transition-all animate-in zoom-in-95 duration-300`;
                     
                     let typeIcon = '📝';
                     let typeColor = 'brand';
                     let typeDetail = '';

                     if (e.item_type === 'quran') {
                        typeIcon = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>';
                        typeColor = 'emerald-600';
                        typeDetail = `Surah ${e.meta.surah_number}:${e.meta.verse_start}${e.meta.verse_end ? '-' + e.meta.verse_end : ''}`;
                     } else if (e.item_type === 'hadith') {
                        typeIcon = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>';
                        typeColor = 'amber-600';
                        typeDetail = `${e.meta.collection} #${e.meta.hadith_number}`;
                     } else if (e.item_type === 'quote') {
                        typeIcon = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>';
                        typeColor = 'indigo-600';
                        typeDetail = e.meta.author || 'Wise Words';
                     } else if (e.item_type === 'book') {
                        typeIcon = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>';
                        typeColor = 'brand';
                        typeDetail = e.meta.title || 'Excerpt';
                     } else {
                        typeIcon = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>';
                        typeDetail = e.title || 'Research Node';
                     }

                     let actionsHtml = `<div class="absolute top-6 right-6 flex gap-2 opacity-0 group-hover:opacity-100 translate-x-2 group-hover:translate-x-0 transition-all pointer-events-none group-hover:pointer-events-auto">`;
                     if (isGlobal) {
                        actionsHtml += `<button onclick="cloneEntry(${e.id})" title="Clone to my Org" class="w-10 h-10 bg-white shadow-xl border border-brand/10 rounded-2xl text-brand hover:scale-110 transition-all flex items-center justify-center"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></button>`;
                        if (isSuperAdmin) {
                            actionsHtml += `
                                <button onclick="openEntryModalById(${e.id})" class="w-10 h-10 bg-white shadow-xl border border-brand/10 rounded-2xl text-brand hover:scale-110 transition-all flex items-center justify-center"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></button>
                                <button onclick="deleteEntry(${e.id})" class="w-10 h-10 bg-white shadow-xl border border-rose-100 rounded-2xl text-rose-500 hover:scale-110 transition-all flex items-center justify-center"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></button>
                            `;
                        }
                     } else {
                        actionsHtml += `
                            <button onclick="openEntryModalById(${e.id})" class="w-10 h-10 bg-white shadow-xl border border-brand/10 rounded-2xl text-brand hover:scale-110 transition-all flex items-center justify-center"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></button>
                            <button onclick="deleteEntry(${e.id})" class="w-10 h-10 bg-white shadow-xl border border-rose-100 rounded-2xl text-rose-500 hover:scale-110 transition-all flex items-center justify-center"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></button>
                        `;
                     }
                     actionsHtml += `</div>`;

                     el.innerHTML = `
                        ${actionsHtml}
                        <div class="flex flex-col h-full space-y-8">
                            <div class="space-y-6">
                                <div class="flex items-center gap-4">
                                    <div class="w-10 h-10 rounded-xl bg-brand/5 text-brand flex items-center justify-center border border-brand/10">
                                        ${typeIcon}
                                    </div>
                                    <div>
                                        <div class="text-[8px] font-bold uppercase tracking-[0.2em] text-text-muted">Knowledge Node</div>
                                        <div class="text-[10px] font-bold uppercase tracking-widest text-brand truncate max-w-[140px]">${typeDetail}</div>
                                    </div>
                                </div>
                                <div class="relative group/text">
                                    <p class="text-text-main text-sm leading-relaxed font-medium line-clamp-6 opacity-90 group-hover/text:opacity-100 transition-opacity">
                                        <span class="text-brand/20 font-serif text-3xl absolute -left-2 -top-4 pointer-events-none select-none">“</span>
                                        ${e.text}
                                    </p>
                                </div>
                            </div>
                            <div class="pt-6 border-t border-brand/5 flex flex-wrap gap-2 items-end mt-auto">
                                ${ (e.topics || []).map(t => `<span class="px-2.5 py-1 bg-cream border border-brand/5 rounded-lg text-[8px] font-bold uppercase tracking-tighter text-brand/60 transition-all hover:bg-brand/5 hover:text-brand cursor-default">${t}</span>`).join('') }
                            </div>
                        </div>
                     `;
                     list.appendChild(el);
              });
          } catch(e) {
              console.error("Library System Error:", e);
              list.innerHTML = '<div class="col-span-full py-20 text-center"><div class="text-[10px] font-black text-rose-500/50 uppercase tracking-widest">Something went wrong.</div><p class="text-[8px] text-white/20 mt-2 uppercase font-bold">' + e.message + '</p></div>';
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
                  alert(`Save failed: ${err.detail || 'Unknown error'}`);
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
          
          list.innerHTML = '<div class="text-center py-10 text-[9px] font-black uppercase text-muted animate-pulse">Scanning Sabeel Library...</div>';
          
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
                  
                  let scope = "Sabeel Default";
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
          console.log("Admin interface restricted to system authorized users");
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
    
    return APP_LAYOUT_HTML.replace("{content}", content.replace("{library_controls}", f"""
            <div class="flex p-1 bg-white/5 rounded-xl border border-white/10 gap-2">
                <button onclick="toggleGlobalView(false)" id="orgViewBtn" class="flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter transition-all bg-brand text-white shadow-lg">Org</button>
                <button onclick="toggleGlobalView(true)" id="globalViewBtn" class="flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter transition-all text-white/40 hover:text-white">System</button>
                <button onclick="openSynonymModal()" class="px-3 py-1.5 border border-brand/20 rounded-lg text-brand hover:bg-brand hover:text-white transition-all">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                </button>
            </div>
            """ if user.is_superadmin else ""))\
                          .replace("{title}", "Library")\
                          .replace("{user_name}", user.name or user.email)\
                          .replace("{org_name}", org.name if org else "Personal Workspace")\
                          .replace("{admin_link}", admin_link)\
                          .replace("{admin_mobile}", "hidden" if not user.is_superadmin else "")\
                          .replace("{active_dashboard}", "")\
                          .replace("{active_calendar}", "")\
                          .replace("{active_automations}", "")\
                          .replace("{active_library}", "active")\
                          .replace("{active_media}", "")\
                          .replace("{is_superadmin_js}", "true" if user.is_superadmin else "false")\
                          .replace("{account_options}", "")\
                          .replace("{connect_instagram_modal}", CONNECT_INSTAGRAM_MODAL_HTML)\
                          .replace("{extra_js}", "")

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

    return {"status": "success"}
