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

# --- STUDIO ASSETS ---

STUDIO_SCRIPTS_JS = """
<script>
    // --- REMINDER STUDIO CORE LOGIC (v4.0 - Decoupled) ---
    let currentQuoteCardUrl = null;
    let isQuoteCardOutOfDate = false;
    let studioCreationMode = 'preset'; 
    let studioEngine       = 'dalle';  
    let studioGlossy       = false;    
    let selectedAyahId     = null;

    // Structured State
    let studioCardMessage = null; // { eyebrow, headline, supporting_text }
    let studioCaptionMessage = null; // { hook, body, cta, hashtags }

    function openNewPostModal() {
        document.getElementById('newPostModal').classList.remove('hidden');
        switchStudioSection(1);
    }

    function closeNewPostModal() {
        document.getElementById('newPostModal').classList.add('hidden');
    }

    function switchStudioSection(stepIndex) {
        // Step Validation Logic
        if (stepIndex === 2 && !studioCardMessage) {
            alert("Please build your card message first.");
            return;
        }
        if (stepIndex === 4 && (!currentQuoteCardUrl || !studioCaptionMessage)) {
            alert("Please ensure your visual and caption are ready before moving to Manifest.");
            return;
        }

        // Hide all sections
        for(let i=1; i<=4; i++) {
           const el = document.getElementById('studioSection' + i);
           if(el) el.classList.add('hidden');
           
           const nav = document.getElementById('navStep' + i);
           if(nav) {
               nav.classList.remove('active', 'text-brand');
               nav.classList.add('text-text-muted');
               const num = nav.querySelector('.nav-num');
               if (num) {
                   num.classList.remove('border-brand', 'text-white', 'bg-brand', 'shadow-lg', 'shadow-brand/20');
                   num.classList.add('border-brand/10');
               }
           }
        }
        
        // Activate requested section
        const target = document.getElementById('studioSection' + stepIndex);
        if(target) {
            target.classList.remove('hidden');
            target.scrollTo(0, 0);
        }
        
        const targetNav = document.getElementById('navStep' + stepIndex);
        if(targetNav) {
           targetNav.classList.remove('text-text-muted');
           targetNav.classList.add('active');
           const num = targetNav.querySelector('.nav-num');
           if (num) {
               num.classList.remove('border-brand/10');
               num.classList.add('border-brand', 'text-white', 'bg-brand', 'shadow-lg', 'shadow-brand/20');
           }
        }

        if (stepIndex === 4) prepareManifest();
    }

    // --- SEARCH & SOURCE ---
    async function searchQuran() {
        const query = document.getElementById('studioTopic').value;
        const resultsArea = document.getElementById('quranSearchResults');
        if (query.length < 2) {
            resultsArea.classList.add('hidden');
            return;
        }
        resultsArea.innerHTML = '<div class="p-4 text-center text-[8px] font-bold text-brand animate-pulse uppercase tracking-widest">Searching Foundation...</div>';
        resultsArea.classList.remove('hidden');
        try {
            const res = await fetch(`/api/quran/search?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            if (data.length === 0) { resultsArea.classList.add('hidden'); return; }
            resultsArea.innerHTML = data.map(v => `
                <div onclick="selectAyah('${v.id}', '${v.title.replace(/'/g, "\\'")}', '${v.text.replace(/'/g, "\\'")}')" class="p-4 border-b border-brand/5 hover:bg-brand/5 cursor-pointer transition-all">
                    <div class="flex justify-between items-start mb-1">
                        <span class="text-[8px] font-black text-brand uppercase tracking-widest">${v.title}</span>
                    </div>
                    <div class="text-[10px] text-text-muted font-medium italic line-clamp-2">${v.text}</div>
                </div>
            `).join('');
        } catch (e) { console.error(e); }
    }

    function selectAyah(id, title, text) {
        selectedAyahId = id;
        document.getElementById('selectedAyahBadge').classList.remove('hidden');
        document.getElementById('selectedAyahTitle').innerText = title;
        document.getElementById('quranSearchResults').classList.add('hidden');
        document.getElementById('studioTopic').value = title;
    }

    // --- PHASE 1: BUILD CARD MESSAGE ---
    async function buildCardMessage() {
        const topic = document.getElementById('studioTopic').value;
        const intention = document.getElementById('studioIntent').value;
        const tone = document.getElementById('studioTone').value;
        const btn = document.getElementById('btnBuildMessage');
        const icon = btn.querySelector('.btn-icon');
        const text = btn.querySelector('.btn-text');

        if (!topic && !selectedAyahId) {
            alert('Please define a topic or select a verse.');
            return;
        }

        btn.disabled = true;
        if(icon) icon.classList.add('animate-spin');
        if(text) text.innerText = 'Architecting Message...';

        try {
            const res = await fetch('/api/quote-card/build-message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source_type: selectedAyahId ? 'quran' : 'manual',
                    item_id: selectedAyahId,
                    reference: !selectedAyahId ? topic : null,
                    tone: tone,
                    intent: intention
                })
            });
            const data = await res.json();
            if (data.card_message) {
                studioCardMessage = data.card_message;
                // Fill UI fields
                document.getElementById('editEyebrow').value = studioCardMessage.eyebrow;
                document.getElementById('editHeadline').value = studioCardMessage.headline;
                document.getElementById('editSupporting').value = studioCardMessage.supporting_text;
                document.getElementById('cardMessageWorkspace').classList.remove('hidden');
                invalidateQuoteCard();
            }
        } catch (e) {
            alert('Architecture failed. Please try again.');
        } finally {
            btn.disabled = false;
            if(icon) icon.classList.remove('animate-spin');
            if(text) text.innerText = 'Build Quote Card Message';
        }
    }

    function updateStudioCardFromUI() {
        if(!studioCardMessage) studioCardMessage = {};
        studioCardMessage.eyebrow = document.getElementById('editEyebrow').value;
        studioCardMessage.headline = document.getElementById('editHeadline').value;
        studioCardMessage.supporting_text = document.getElementById('editSupporting').value;
        invalidateQuoteCard();
    }

    // --- PHASE 2: GENERATE VISUAL ---
    async function generateQuoteCard() {
        if (!studioCardMessage) { alert("Build a message first."); return; }
        
        const btn = document.getElementById('btnGenerateCard');
        const loader = document.getElementById('cardLoader');
        const preview = document.getElementById('quoteCardPreview');
        const syncBanner = document.getElementById('outOfSyncBanner');

        btn.disabled = true;
        btn.innerText = 'Manifesting Visual...';
        if (loader) loader.classList.remove('hidden');
        if (preview) preview.classList.add('hidden');
        if (syncBanner) syncBanner.classList.add('hidden');

        try {
            const payload = {
                card_message: studioCardMessage,
                style: studioCreationMode === 'custom' ? 'custom' : document.getElementById('studioStyle').value,
                visual_prompt: document.getElementById('studioVisualPrompt')?.value,
                text_style_prompt: document.getElementById('studioTextStylePrompt')?.value,
                engine: studioEngine,
                glossy: studioGlossy,
                mode: studioCreationMode
            };

            const res = await fetch('/generate-quote-card', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.image_url) {
                currentQuoteCardUrl = data.image_url;
                document.getElementById('finalMediaUrl').value = data.image_url;
                preview.src = data.image_url + '?t=' + Date.now();
                preview.classList.remove('hidden');
                if (loader) loader.classList.add('hidden');
                document.getElementById('cardActions').classList.remove('hidden');
                isQuoteCardOutOfDate = false;
            } else {
                alert('Visual generation failed: ' + (data.error || 'Unknown error'));
            }
        } catch (e) {
            console.error(e);
        } finally {
            btn.disabled = false;
            btn.innerText = studioCreationMode === 'custom' ? 'Generate From Description' : 'Generate Cinematic Visual';
        }
    }

    // --- PHASE 3: GENERATE CAPTION ---
    async function generateSocialCaption() {
        const btn = document.getElementById('btnGenerateCaption');
        const icon = btn.querySelector('.btn-icon');
        const text = btn.querySelector('.btn-text');
        
        btn.disabled = true;
        if(icon) icon.classList.add('animate-spin');
        if(text) text.innerText = 'Crafting Social Presence...';

        try {
            const res = await fetch('/api/caption/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source_type: selectedAyahId ? 'quran' : 'manual',
                    item_id: selectedAyahId,
                    tone: document.getElementById('studioTone').value,
                    intent: document.getElementById('studioIntent').value,
                    custom_payload: !selectedAyahId ? { text: studioCardMessage.headline } : null
                })
            });
            const data = await res.json();
            if (data.caption_message) {
                studioCaptionMessage = data.caption_message;
                const fullText = `${studioCaptionMessage.hook}\n\n${studioCaptionMessage.body}\n\n${studioCaptionMessage.cta}\n\n${studioCaptionMessage.hashtags}`;
                document.getElementById('studioCaption').value = fullText;
                document.getElementById('captionResultArea').classList.remove('hidden');
            }
        } catch (e) {
            alert('Social caption generation failed.');
        } finally {
            btn.disabled = false;
            if(icon) icon.classList.remove('animate-spin');
            if(text) text.innerText = 'Generate Social Caption';
        }
    }

    // --- MISC HANDLERS ---
    function invalidateQuoteCard() {
        if (currentQuoteCardUrl) {
            isQuoteCardOutOfDate = true;
            const banner = document.getElementById('outOfSyncBanner');
            if(banner) banner.classList.remove('hidden');
        }
    }

    function setStudioIntent(intent, el) {
        document.getElementById('studioIntent').value = intent;
        document.querySelectorAll('.intent-card').forEach(c => c.classList.remove('active'));
        el.closest('.intent-card').classList.add('active');
    }

    function setStudioTone(tone, el) {
        document.getElementById('studioTone').value = tone;
        document.querySelectorAll('.tone-card').forEach(c => c.classList.remove('active'));
        el.closest('.tone-card').classList.add('active');
    }

    function setStudioStyle(style, el) {
        document.getElementById('studioStyle').value = style;
        document.querySelectorAll('.style-card').forEach(c => c.classList.remove('active'));
        el.closest('.style-card').classList.add('active');
        invalidateQuoteCard();
    }

    function setStudioEngine(engine, el) {
        studioEngine = engine;
        document.querySelectorAll('.engine-chip').forEach(c => {
            c.classList.remove('bg-brand', 'text-white', 'shadow-lg', 'shadow-brand/20');
            c.classList.add('bg-brand/5', 'text-brand');
        });
        el.classList.remove('bg-brand/5', 'text-brand');
        el.classList.add('bg-brand', 'text-white', 'shadow-lg', 'shadow-brand/20');
        invalidateQuoteCard();
    }

    function switchStudioMode(mode) {
        studioCreationMode = mode;
        const presetBtn = document.getElementById('btnModePreset');
        const customBtn = document.getElementById('btnModeCustom');
        const presetContainer = document.getElementById('presetModeContainer');
        const customContainer = document.getElementById('customModeContainer');

        if (mode === 'preset') {
            presetBtn.classList.add('bg-brand', 'text-white', 'shadow-lg', 'shadow-brand/20');
            presetBtn.classList.remove('bg-brand/5', 'text-brand');
            customBtn.classList.remove('bg-brand', 'text-white', 'shadow-lg', 'shadow-brand/20');
            customBtn.classList.add('bg-brand/5', 'text-brand');
            presetContainer.classList.remove('hidden');
            customContainer.classList.add('hidden');
        } else {
            customBtn.classList.add('bg-brand', 'text-white', 'shadow-lg', 'shadow-brand/20');
            customBtn.classList.remove('bg-brand/5', 'text-brand');
            presetBtn.classList.remove('bg-brand', 'text-white', 'shadow-lg', 'shadow-brand/20');
            presetBtn.classList.add('bg-brand/5', 'text-brand');
            customContainer.classList.remove('hidden');
            presetContainer.classList.add('hidden');
        }
        invalidateQuoteCard();
    }

    function prepareManifest() {
        const caption = document.getElementById('studioCaption').value;
        const account = document.getElementById('studioAccount').options[document.getElementById('studioAccount').selectedIndex]?.text || "No Account";
        const timeVal = document.getElementById('studioSchedule').value;
        const timeStr = timeVal ? new Date(timeVal).toLocaleString() : "Next Available Slot";
        const previewImg = document.getElementById('finalPreviewImage');

        document.getElementById('manifestCaption').innerText = caption;
        document.getElementById('manifestAccount').innerText = account;
        document.getElementById('manifestTime').innerText = timeStr;
        
        if (currentQuoteCardUrl) {
            previewImg.src = currentQuoteCardUrl;
        }
    }

    async function submitNewPost(event) {
        event.preventDefault();
        const btn = document.getElementById('studioSubmitBtn');
        const original = btn.innerText;

        if (isQuoteCardOutOfDate && !confirm("Your quote card no longer matches your latest message. Manifest anyway?")) {
            return;
        }

        btn.disabled = true;
        btn.innerHTML = 'MANIFESTING... <span class="animate-pulse">✨</span>';

        const formData = new FormData(event.target);
        formData.append('visual_mode', 'quote_card');
        if (selectedAyahId) formData.append('library_item_id', selectedAyahId);
        formData.append('source_text', document.getElementById('studioTopic').value);
        
        // Add structured messages
        formData.append('card_message', JSON.stringify(studioCardMessage));
        formData.append('caption_message', JSON.stringify(studioCaptionMessage));

        try {
            const res = await fetch('/posts/intake', { method: 'POST', body: formData });
            if (res.ok) {
                window.location.reload();
            } else {
                const data = await res.json().catch(() => ({detail: 'System timeout'}));
                alert('Manifestation Error: ' + (data.detail || 'Unknown error'));
            }
        } catch (e) {
            alert('Manifestation Connection failure: ' + e);
        } finally {
            btn.innerText = original;
            btn.disabled = false;
        }
    }

    // --- LEGACHY / UTILS ---
    async function renderAccountSwitcher() {
        const container = document.getElementById('navbarAccountSwitcher');
        if (!container) return;
        try {
            const res = await fetch('/ig-accounts/me');
            const accounts = await res.json();
            if (accounts.length === 0) {
                container.innerHTML = `<button onclick="openConnectInstagramModal()" class="flex items-center gap-2 px-3 py-1.5 bg-brand text-white rounded-lg text-[10px] font-bold uppercase tracking-widest hover:bg-brand-hover transition-all">Link Meta</button>`;
                return;
            }
            const active = accounts.find(a => a.active) || accounts[0];
            container.innerHTML = `
                <div class="relative inline-block text-left" id="accountSwitcherRoot">
                    <button onclick="toggleSwitcherDropdown()" class="flex items-center gap-3 px-3 py-2 bg-white border border-brand/10 rounded-xl hover:bg-brand/[0.02] transition-all group">
                        <img src="${active.profile_picture_url || 'https://ui-avatars.com/api/?name=' + active.username}" class="w-6 h-6 rounded-full ring-2 ring-brand/10 group-hover:ring-brand/20 transition-all">
                        <div class="text-left hidden lg:block">
                            <div class="text-[9px] font-black text-brand uppercase tracking-wider">@${active.username}</div>
                            <div class="text-[7px] font-bold text-text-muted uppercase tracking-widest">Active Studio</div>
                        </div>
                        <svg class="w-3 h-3 text-text-muted/40 group-hover:text-brand transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
                    </button>
                    <div id="switcherDropdown" class="hidden absolute right-0 mt-2 w-64 bg-white border border-brand/5 rounded-2xl shadow-2xl z-[100] p-2 animate-in fade-in zoom-in-95 duration-200">
                        <div class="px-3 py-2 text-[8px] font-black text-text-muted uppercase tracking-[0.2em] mb-1">Your Workspaces</div>
                        <div class="space-y-1">
                            ${accounts.map(acc => `
                                <button type="button" onclick="setActiveAccount('${acc.id}')" class="w-full flex items-center justify-between p-2 rounded-xl transition-all ${acc.id === active.id ? 'bg-brand/5 border border-brand/5' : 'hover:bg-brand/[0.02]'}">
                                    <div class="flex items-center gap-3">
                                        <img src="${acc.profile_picture_url || 'https://ui-avatars.com/api/?name=' + acc.username}" class="w-8 h-8 rounded-lg">
                                        <div class="text-left">
                                            <div class="text-[10px] font-bold text-brand">@${acc.username}</div>
                                            <div class="text-[8px] text-text-muted font-medium">${acc.fb_page_id ? 'Instagram Business' : 'Personal'}</div>
                                        </div>
                                    </div>
                                    ${acc.id === active.id ? '<div class="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>' : ''}
                                </button>
                            `).join('')}
                        </div>
                    </div>
                </div>`;
        } catch (e) { console.error("Account switcher failed", e); }
    }

    function toggleSwitcherDropdown() {
        const drop = document.getElementById('switcherDropdown');
        if (drop) drop.classList.toggle('hidden');
    }

    async function setActiveAccount(id) {
        try {
            const res = await fetch('/ig-accounts/set-active/' + id, { method: 'POST' });
            if (res.ok) window.location.reload();
        } catch (e) { console.error("Set active account failed", e); }
    }

    // --- PENDING VERSE BRIDGE ---
    window.addEventListener('load', () => {
        const pending = sessionStorage.getItem('sabeel_pending_quote_item');
        if (pending) {
            try {
                const item = JSON.parse(pending);
                sessionStorage.removeItem('sabeel_pending_quote_item');
                openNewPostModal();
                // Select and populate
                selectAyah(item.id, item.reference, item.translation_text);
            } catch (e) { console.error("Failed to load pending verse", e); }
        }
    });
</script>
"""

STUDIO_COMPONENTS_HTML = """
<!-- CONTENT STUDIO MODAL -->
<div id="newPostModal" class="fixed inset-0 bg-black/95 backdrop-blur-2xl z-[100] flex items-end md:items-center justify-center p-0 md:p-10 hidden">
    <div class="w-full h-[100vh] md:h-full md:max-w-7xl rounded-none md:rounded-[3rem] overflow-hidden flex flex-col md:flex-row animate-in slide-in-from-bottom md:zoom-in duration-500 border-0 border-t md:border border-brand/5 shadow-2xl bg-white">
      
      <!-- Studio Sidebar -->
      <div class="w-full md:w-80 bg-brand/5 border-b md:border-b-0 md:border-r border-brand/5 flex flex-col pt-10 md:pt-12 px-8 z-50 shrink-0">
        <div>
          <h3 class="text-3xl font-bold text-brand tracking-tighter italic">Sabeel<br><span class="text-accent">Studio</span></h3>
          <p class="text-[9px] font-bold text-text-muted uppercase tracking-[0.3em] mt-2">Decoupled Pipeline v4.0</p>
        </div>
        
        <div class="flex-1 mt-12 space-y-6">
          <div id="navStep1" class="studio-nav-step active flex items-center gap-4 cursor-pointer" onclick="switchStudioSection(1)">
             <div class="w-8 h-8 rounded-full border-2 border-brand flex items-center justify-center text-[10px] font-bold text-white bg-brand shadow-lg shadow-brand/20 nav-num">1</div>
             <div class="text-xs font-bold uppercase text-brand tracking-widest nav-text">The Spark</div>
          </div>
          <div id="navStep2" class="studio-nav-step flex items-center gap-4 cursor-pointer text-text-muted transition-all hover:translate-x-1" onclick="switchStudioSection(2)">
             <div class="w-8 h-8 rounded-full border-2 border-brand/10 flex items-center justify-center text-[10px] font-bold nav-num">2</div>
             <div class="text-xs font-bold uppercase tracking-widest nav-text">The Vision</div>
          </div>
          <div id="navStep3" class="studio-nav-step flex items-center gap-4 cursor-pointer text-text-muted transition-all hover:translate-x-1" onclick="switchStudioSection(3)">
             <div class="w-8 h-8 rounded-full border-2 border-brand/10 flex items-center justify-center text-[10px] font-bold nav-num">3</div>
             <div class="text-xs font-bold uppercase tracking-widest nav-text">The Presence</div>
          </div>
          <div id="navStep4" class="studio-nav-step flex items-center gap-4 cursor-pointer text-text-muted transition-all hover:translate-x-1" onclick="switchStudioSection(4)">
             <div class="w-8 h-8 rounded-full border-2 border-brand/10 flex items-center justify-center text-[10px] font-bold nav-num">4</div>
             <div class="text-xs font-bold uppercase tracking-widest nav-text">The Manifest</div>
          </div>
        </div>
      </div>

      <button type="button" onclick="closeNewPostModal()" class="absolute top-6 right-6 z-[110] w-10 h-10 rounded-full bg-white/10 backdrop-blur-md border border-white/20 flex items-center justify-center text-white hover:bg-white hover:text-brand transition-all">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg>
      </button>

      <form id="composerForm" onsubmit="submitNewPost(event)" class="flex-1 overflow-hidden flex flex-col relative bg-white">
        <input type="hidden" name="visual_mode" id="studioVisualMode" value="quote_card">
        <input type="hidden" name="visual_style" id="studioStyle" value="quran">
        <input type="hidden" name="media_url" id="finalMediaUrl">

        <div class="flex-1 overflow-y-auto p-6 md:p-12 pb-32 custom-scrollbar">
          
          <!-- PHASE 1: THE SPARK (Card Message Generation) -->
          <div id="studioSection1" class="studio-section space-y-10 animate-in slide-in-from-right-8 duration-500">
            <div>
              <label class="text-[9px] font-bold uppercase tracking-[0.3em] text-accent">Studio Phase 1</label>
              <h4 class="text-3xl font-bold text-brand italic">Ignite the Spark</h4>
              <p class="text-xs text-text-muted mt-2 font-medium">Search the Qur'an or define a topic to build your card's central message.</p>
            </div>

            <div class="space-y-8">
                <!-- Unified Topic & Quran Input -->
                <div class="space-y-4">
                    <div class="space-y-3">
                       <label class="text-[9px] font-black text-brand uppercase tracking-widest ml-1">Foundation Source</label>
                       <div class="relative">
                            <input type="text" id="studioTopic" name="topic" oninput="searchQuran()" placeholder="e.g. Patience, 70:5, or Gratitude..." class="w-full bg-cream/20 border border-brand/5 rounded-2xl px-8 py-6 text-sm font-medium text-brand outline-none focus:border-brand/20 transition-all shadow-inner">
                            <div class="absolute right-6 top-1/2 -translate-y-1/2 text-brand/20">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                            </div>
                       </div>
                    </div>

                    <div id="quranSearchResults" class="hidden max-h-48 overflow-y-auto bg-white border border-brand/10 rounded-2xl shadow-xl custom-scrollbar z-[120]"></div>
                    
                    <div id="selectedAyahBadge" class="hidden p-4 bg-emerald-50 border border-emerald-100 rounded-2xl flex items-center justify-between shadow-sm">
                        <div class="flex items-center gap-3">
                            <div class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                            <span id="selectedAyahTitle" class="text-[10px] font-black text-emerald-800 uppercase tracking-widest"></span>
                        </div>
                        <button type="button" onclick="selectedAyahId=null; document.getElementById('selectedAyahBadge').classList.add('hidden');" class="text-[8px] font-bold text-emerald-600 uppercase hover:underline">Change</button>
                    </div>
                </div>

                <!-- Build Card Message Action -->
                <div class="pt-4">
                    <button type="button" id="btnBuildMessage" onclick="buildCardMessage()" class="w-full py-6 bg-brand text-white rounded-[2rem] font-black text-xs uppercase tracking-widest shadow-xl shadow-brand/20 hover:scale-[1.01] transition-all flex items-center justify-center gap-3">
                        <span class="btn-icon">✨</span>
                        <span class="btn-text">Build Quote Card Message</span>
                    </button>
                </div>

                <!-- Editable Workspace for Card Content -->
                <div id="cardMessageWorkspace" class="hidden animate-in fade-in slide-in-from-top-4 duration-500 space-y-6 bg-brand/[0.02] p-8 rounded-[2.5rem] border border-brand/5">
                    <div class="flex justify-between items-center px-2">
                        <label class="text-[9px] font-black text-brand uppercase tracking-widest">Quote Card Workspace</label>
                        <span class="text-[7px] font-bold text-accent uppercase tracking-widest">Verified Grounding</span>
                    </div>
                    
                    <div class="space-y-4">
                        <div class="space-y-2">
                            <label class="text-[8px] font-bold text-text-muted uppercase tracking-widest ml-1">Eyebrow (Top Label)</label>
                            <input type="text" id="editEyebrow" oninput="updateStudioCardFromUI()" class="w-full bg-white border border-brand/10 rounded-xl px-4 py-3 text-xs font-bold text-brand outline-none focus:border-brand/30">
                        </div>
                        <div class="space-y-2">
                            <label class="text-[8px] font-bold text-text-muted uppercase tracking-widest ml-1">Headline (The Quote)</label>
                            <textarea id="editHeadline" oninput="updateStudioCardFromUI()" class="w-full bg-white border border-brand/10 rounded-xl px-4 py-3 text-xs font-medium text-brand outline-none focus:border-brand/30 h-24 resize-none"></textarea>
                        </div>
                        <div class="space-y-2">
                            <label class="text-[8px] font-bold text-text-muted uppercase tracking-widest ml-1">Supporting Text (Reference)</label>
                            <input type="text" id="editSupporting" oninput="updateStudioCardFromUI()" class="w-full bg-white border border-brand/10 rounded-xl px-4 py-3 text-xs font-bold text-brand outline-none focus:border-brand/30">
                        </div>
                    </div>

                    <div class="flex justify-end pt-2">
                       <button type="button" onclick="switchStudioSection(2)" class="px-10 py-5 bg-brand text-white rounded-2xl font-bold text-[11px] uppercase tracking-widest hover:bg-brand-hover transition-all shadow-xl shadow-brand/20">Design The Vision &rarr;</button>
                    </div>
                </div>
            </div>
          </div>

          <!-- PHASE 2: THE VISION (Quote Card) -->
          <div id="studioSection2" class="studio-section hidden space-y-10 animate-in slide-in-from-right-8 duration-500">
            <div>
              <label class="text-[9px] font-bold uppercase tracking-[0.3em] text-accent">Studio Phase 2</label>
              <h4 class="text-3xl font-bold text-brand italic">Visualize the Wisdom</h4>
              <p class="text-xs text-text-muted mt-2 font-medium">Select your palette and engine to manifest the card's visual identity.</p>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-10">
                <div class="space-y-8">
                    <div class="flex p-1.5 bg-brand/[0.03] rounded-2xl border border-brand/5 gap-1">
                        <button type="button" id="btnModePreset" onclick="switchStudioMode('preset')" class="flex-1 py-3 px-4 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all bg-brand text-white shadow-lg shadow-brand/20">Sabeel Presets</button>
                        <button type="button" id="btnModeCustom" onclick="switchStudioMode('custom')" class="flex-1 py-3 px-4 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all bg-brand/5 text-brand">Prophetic Vision</button>
                    </div>

                    <div id="presetModeContainer" class="space-y-4 animate-in fade-in duration-300">
                        <div class="grid grid-cols-2 gap-3">
                            <div onclick="setStudioStyle('quran', this)" class="style-card active p-5 rounded-2xl border-2 border-brand/5 bg-cream/10 cursor-pointer transition-all hover:bg-brand/[0.02] text-center space-y-3 group">
                               <div class="w-10 h-10 rounded-xl bg-brand/5 flex items-center justify-center text-brand mx-auto group-[.active]:bg-brand group-[.active]:text-white transition-all">
                                   <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                               </div>
                               <div class="text-[9px] font-black text-brand uppercase tracking-widest">Qur'an</div>
                            </div>
                            <div onclick="setStudioStyle('madinah', this)" class="style-card p-5 rounded-2xl border-2 border-brand/5 bg-cream/10 cursor-pointer transition-all hover:bg-brand/[0.02] text-center space-y-3 group">
                               <div class="w-10 h-10 rounded-xl bg-brand/5 flex items-center justify-center text-brand mx-auto group-[.active]:bg-brand group-[.active]:text-white transition-all">
                                   <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M8 14v3m4-3v3m4-3v3M3 21h18M3 10h18M3 7l9-4 9 4M4 10h16v11H4V10z" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"/></svg>
                               </div>
                               <div class="text-[9px] font-black text-brand uppercase tracking-widest">Madinah</div>
                            </div>
                        </div>
                    </div>

                    <div id="customModeContainer" class="hidden space-y-4">
                        <textarea id="studioVisualPrompt" placeholder="Describe atmosphere..." class="w-full bg-white border border-brand/10 rounded-3xl p-6 text-sm font-medium text-brand outline-none h-32"></textarea>
                    </div>

                    <button type="button" id="btnGenerateCard" onclick="generateQuoteCard()" class="w-full py-6 bg-brand text-white rounded-[2rem] font-black text-xs uppercase tracking-widest shadow-xl shadow-brand/20 hover:scale-[1.01] transition-all">
                        Generate Cinematic Visual
                    </button>
                </div>

                <div class="flex flex-col items-center gap-6">
                    <div id="cardPreviewContainer" class="w-full max-w-[340px] aspect-square bg-cream rounded-[3rem] border-8 border-brand/5 overflow-hidden relative shadow-2xl flex items-center justify-center">
                        <img id="quoteCardPreview" class="hidden w-full h-full object-cover">
                        <div id="cardLoader" class="hidden flex flex-col items-center gap-4 text-brand/20">
                            <div class="w-12 h-12 rounded-full border-4 border-t-brand animate-spin"></div>
                            <span class="text-[9px] font-black uppercase tracking-widest">Manifesting...</span>
                        </div>
                        <div id="outOfSyncBanner" class="hidden absolute top-0 inset-x-0 bg-amber-500/90 backdrop-blur-md p-4 flex flex-col items-center gap-1 text-white">
                           <span class="text-[8px] font-black uppercase tracking-widest">Out of Sync</span>
                        </div>
                    </div>

                    <div id="cardActions" class="hidden flex gap-3">
                        <button type="button" onclick="switchStudioSection(3)" class="px-8 py-3 bg-brand text-white rounded-xl text-[9px] font-black uppercase tracking-widest shadow-lg shadow-brand/20">Confirm Visual &rarr;</button>
                    </div>
                </div>
            </div>
            
            <div class="pt-8 border-t border-brand/5 flex justify-between">
               <button type="button" onclick="switchStudioSection(1)" class="px-8 py-4 text-text-muted hover:text-brand font-bold text-[10px] uppercase tracking-widest transition-all">&larr; Back to Spark</button>
            </div>
          </div>

          <!-- PHASE 3: THE PRESENCE (Social Caption) -->
          <div id="studioSection3" class="studio-section hidden space-y-10 animate-in slide-in-from-right-8 duration-500">
            <div>
              <label class="text-[9px] font-bold uppercase tracking-[0.3em] text-accent">Studio Phase 3</label>
              <h4 class="text-3xl font-bold text-brand italic">The Social Presence</h4>
              <p class="text-xs text-text-muted mt-2 font-medium">Draft your social engagement copy (Hook, Body, CTA).</p>
            </div>

            <div class="space-y-8">
                <button type="button" id="btnGenerateCaption" onclick="generateSocialCaption()" class="w-full py-6 bg-brand/5 text-brand border border-brand/10 rounded-[2rem] font-black text-xs uppercase tracking-widest hover:bg-brand/10 transition-all flex items-center justify-center gap-3">
                    <span class="btn-icon">💬</span>
                    <span class="btn-text">Generate Social Caption</span>
                </button>

                <div id="captionResultArea" class="hidden space-y-6">
                    <textarea id="studioCaption" name="caption" class="w-full bg-white border border-brand/10 rounded-[2.5rem] p-10 text-sm font-medium text-brand min-h-[300px] outline-none shadow-xl leading-relaxed custom-scrollbar"></textarea>
                    
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 bg-brand/[0.02] p-8 rounded-[2rem] border border-brand/5">
                        <div class="space-y-2">
                            <label class="text-[9px] font-black text-brand uppercase tracking-widest ml-1">Activation Account</label>
                            <select name="ig_account_id" id="studioAccount" class="w-full bg-white border border-brand/10 rounded-xl px-4 py-3 text-xs font-bold text-brand outline-none appearance-none">
                                {account_options}
                            </select>
                        </div>
                        <div class="space-y-2">
                            <label class="text-[9px] font-black text-brand uppercase tracking-widest ml-1">Schedule Time</label>
                            <input type="datetime-local" id="studioSchedule" name="scheduled_time" class="w-full bg-white border border-brand/10 rounded-xl px-4 py-3 text-xs font-bold text-brand outline-none">
                        </div>
                    </div>

                    <div class="flex justify-end pt-4">
                       <button type="button" onclick="switchStudioSection(4)" class="px-10 py-5 bg-brand text-white rounded-2xl font-bold text-[11px] uppercase tracking-widest shadow-xl shadow-brand/20">Final Review &rarr;</button>
                    </div>
                </div>
            </div>
          </div>

          <!-- PHASE 4: THE MANIFEST (Review) -->
          <div id="studioSection4" class="studio-section hidden space-y-12 animate-in slide-in-from-right-8 duration-500">
            <div>
              <label class="text-[9px] font-bold uppercase tracking-[0.3em] text-accent">Studio Phase 4</label>
              <h4 class="text-3xl font-bold text-brand italic">The Manifest</h4>
              <p class="text-xs text-text-muted mt-2 font-medium">Confirm your manifestation parameters.</p>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-10">
               <div class="flex justify-center">
                  <div class="w-full max-w-[320px] aspect-square bg-cream rounded-[3rem] border-8 border-brand/5 overflow-hidden relative shadow-2xl">
                     <img id="finalPreviewImage" class="w-full h-full object-cover">
                  </div>
               </div>

               <div class="space-y-8 bg-brand/[0.02] p-10 rounded-[2.5rem] border border-brand/5 flex flex-col justify-between">
                  <div class="space-y-6">
                      <div>
                          <label class="text-[8px] font-black text-brand uppercase tracking-widest opacity-60">Manifesting to</label>
                          <div id="manifestAccount" class="text-xs font-bold text-brand uppercase"></div>
                      </div>
                      <div>
                          <label class="text-[8px] font-black text-brand uppercase tracking-widest opacity-60">Activation</label>
                          <div id="manifestTime" class="text-xs font-bold text-brand uppercase"></div>
                      </div>
                      <div class="pt-4 space-y-2">
                        <label class="text-[8px] font-black text-brand uppercase tracking-widest opacity-60">Presence Summary</label>
                        <p id="manifestCaption" class="text-[11px] text-text-muted font-medium italic line-clamp-6 leading-relaxed"></p>
                      </div>
                  </div>

                  <div class="space-y-4 pt-6">
                      <button type="submit" id="studioSubmitBtn" class="w-full py-6 bg-brand text-white rounded-3xl font-black text-[12px] uppercase tracking-[0.3em] shadow-2xl shadow-brand/20">
                         Schedule Manifestation
                      </button>
                  </div>
               </div>
            </div>
          </div>
        </div>
      </form>
    </div>
</div>

<!-- LIBRARY PICKER MODAL -->
<div id="libraryPickerModal" class="fixed inset-0 bg-black/90 backdrop-blur-xl z-[160] flex items-center justify-center p-6 hidden">
    <div class="glass w-full max-w-4xl max-h-[85vh] rounded-[3rem] bg-white border border-brand/10 flex flex-col overflow-hidden animate-in zoom-in duration-300">
        <div class="p-10 pb-6 border-b border-brand/5 flex justify-between items-start">
            <div>
                <h3 class="text-2xl font-bold text-brand italic">Sabeel <span class="text-accent underline decoration-brand/10 decoration-4 underline-offset-4">Library</span></h3>
                <p class="text-[10px] font-black text-text-muted uppercase tracking-widest mt-2">Surface authenticated knowledge and media</p>
            </div>
            <button onclick="document.getElementById('libraryPickerModal').classList.add('hidden')" class="w-10 h-10 flex items-center justify-center rounded-xl bg-brand/5 text-text-muted hover:text-brand transition-all">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
            </button>
        </div>

        <div class="p-8 bg-brand/[0.02] border-b border-brand/5 flex flex-wrap gap-4 items-center">
            <input type="text" id="pickerSearch" placeholder="Search knowledge..." oninput="debouncePickerSearch()" class="flex-1 min-w-[200px] bg-white border border-brand/10 rounded-2xl px-6 py-4 text-xs font-bold text-brand outline-none focus:border-brand/30 shadow-sm transition-all">
            <select id="pickerTopic" onchange="loadPickerEntries()" class="bg-white border border-brand/10 rounded-2xl px-6 py-4 text-[10px] font-bold text-brand uppercase outline-none shadow-sm cursor-pointer hover:bg-brand/5">
                <option value="">All Topics</option>
            </select>
            <select id="pickerType" onchange="loadPickerEntries()" class="bg-white border border-brand/10 rounded-2xl px-6 py-4 text-[10px] font-bold text-brand uppercase outline-none shadow-sm cursor-pointer hover:bg-brand/5">
                <option value="">All Types</option>
                <option value="quran">Qur’an</option>
                <option value="hadith">Hadith</option>
                <option value="media">Visual Media</option>
            </select>
        </div>

        <div id="pickerResults" class="flex-1 overflow-y-auto p-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 custom-scrollbar">
            <div class="col-span-full py-20 text-center text-text-muted opacity-40 font-bold uppercase tracking-widest text-xs italic">
                Scanning intelligence archives...
            </div>
        </div>
        </div>
</div>
"""

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
    .bg-brand { background-color: var(--brand); }
    .bg-brand-hover:hover { background-color: var(--brand-hover); }
    .text-brand { color: var(--brand); }
    .text-accent { color: var(--accent); }
    .border-brand { border-color: var(--brand); }
    .refine-ai-btn:hover { color: white !important; background-color: var(--brand); }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(15, 61, 46, 0.1); border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(15, 61, 46, 0.2); }
    .pb-safe { padding-bottom: env(safe-area-inset-bottom); }
    .mobile-tab.active { color: var(--brand); }
    .mobile-tab.active svg { color: var(--brand); stroke-width: 2.5; }

    /* Content Studio Styles */
    .refine-ai-btn.loading-ai {
        background-color: var(--brand-color, #0f3d2e) !important;
        color: white !important;
    }
    .refine-ai-btn:disabled {
        opacity: 0.7;
        cursor: not-allowed;
    }
    .studio-nav-step.active .nav-text {
        color: #0f3d2e !important;
    }
    .studio-nav-step .nav-text {
        color: rgba(15, 61, 46, 0.4);
    }
    .studio-nav-step.active .nav-num { background: var(--brand); color: white; border-color: var(--brand); }
    .intent-card.active, .foundation-card.active, .emotion-card.active, 
    .depth-card.active, .hook-card.active, .strict-card.active,
    .tone-card.active, .style-card.active { 
      border-color: var(--brand) !important; 
      background-color: rgba(15, 61, 46, 0.06) !important;
      transform: translateY(-2px);
      box-shadow: 0 10px 20px -5px rgba(15, 61, 46, 0.12);
    }
    .tone-card.active, .style-card.active {
      color: var(--brand) !important;
      font-weight: 900;
    }
    .intent-card.active .text-brand, .foundation-card.active .text-brand { color: var(--brand); }
    .strict-card.active { border-color: var(--brand) !important; background-color: rgba(15, 61, 46, 0.03) !important; }
    .strict-card.active[onclick*="strict"] { border-color: #EF4444 !important; background-color: rgba(239, 68, 68, 0.03) !important; }
    .strict-card.active[onclick*="strict"] .nav-num { background-color: #EF4444 !important; }
    /* Style card icon fill on active */
    .style-card.active .group-\[\.active\]\:bg-brand,
    .style-card.active [class*="group-[.active]:bg-brand"] { background-color: var(--brand) !important; }
    .style-card.active [class*="group-[.active]:text-white"] { color: white !important; }
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
          <a href="/app/calendar" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_calendar} text-text-muted hover:text-brand transition-colors">Plan</a>
          <a href="/app/automations" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_automations} text-text-muted hover:text-brand transition-colors">Growth Plans</a>
          <a href="/app/library" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_library} text-text-muted hover:text-brand transition-colors">Knowledge Library</a>
          <a href="/app/media" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_media} text-text-muted hover:text-brand transition-colors">Visual Library</a>
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
        document.getElementById('editPostModal').classList.remove('hidden');
    }

    function closeEditPostModal() {
        if (typeof hideDeleteConfirm === 'function') hideDeleteConfirm();
        document.getElementById('editPostModal').classList.add('hidden');
    }

    async function refinePostAI(type) {
        const text = document.getElementById('editPostCaption').value;
        const btn = event.currentTarget;
        const originalContent = btn.innerHTML;
        
        // Disable all refine buttons
        const allBtns = document.querySelectorAll('.refine-ai-btn');
        allBtns.forEach(b => b.disabled = true);
        btn.classList.add('loading-ai');
        btn.innerHTML = '<svg class="animate-spin -ml-1 mr-2 h-3 w-3 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Crafting...';

        try {
            const res = await fetch('/api/ai/refine', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, type })
            });
            const data = await res.json();
            if (data.refined) {
                document.getElementById('editPostCaption').value = data.refined;
            } else {
                alert('Refinement failed. Try again.');
            }
        } catch(e) {
            alert('Error connecting to AI service.');
        } finally {
            allBtns.forEach(b => b.disabled = false);
            btn.classList.remove('loading-ai');
            btn.innerHTML = originalContent;
        }
    }

    async function publishPostNow() {
        const id = document.getElementById('editPostId').value;
        const postBtn = document.getElementById('postNowBtn');
        if(!id) return;
        
        postBtn.disabled = true;
        postBtn.innerHTML = 'SHARING...';

        try {
            // 1. Save changes first
            await savePostEdit(false); // pass false to avoid double reload

            // 2. Publish immediately
            const res = await fetch(`/posts/${id}/publish`, { method: 'POST' });
            if (res.ok) {
                window.location.reload();
            } else {
                const data = await res.json();
                alert('Connection to Platform failed: ' + (data.detail || 'check connection.'));
            }
        } catch(e) {
            alert('Error updating reminder');
        } finally {
            postBtn.disabled = false;
            postBtn.innerHTML = 'Share Now';
        }
    }

    async function savePostEdit(reload = true) {
        const id = document.getElementById('editPostId').value;
        const caption = document.getElementById('editPostCaption').value;
        const btn = document.getElementById('savePostBtn');

        btn.disabled = true;
        btn.innerText = 'SAVING...';

        try {
            const res = await fetch(`/posts/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ caption: caption })
            });
            if (res.ok) {
                if(reload) window.location.reload();
            } else alert('Failed to update reminder');
        } catch(e) { alert('Error updating reminder'); }
        finally { btn.disabled = false; btn.innerText = 'Save Changes'; }
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
                alert(`Error [${res.status}]: ${data.detail || 'The system could not remove this reminder. It might have been already removed or access was restricted.'}`);
            }
        } catch(e) { 
            alert('The interface could not reach the server: ' + e.message); 
        } finally { 
            btn.disabled = false; 
            btn.innerText = 'Yes, Remove Reminder'; 
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

  </script>

  {studio_modal}
  {connect_instagram_modal}
  {extra_js}
  {studio_js}
</body>
</html>
"""

GET_STARTED_CARD_HTML = """<div id="gettingStartedCard" class="card p-8 md:p-10 mb-8 animate-in slide-in-from-top-4 duration-500">
  <div class="flex justify-between items-start mb-6">
    <div>
      <h3 class="text-2xl md:text-3xl font-bold text-brand tracking-tight">Assalamu Alaykum, <span class="text-accent">{user_name}</span></h3>
      <p class="text-xs text-text-muted mt-1 font-medium">Your space for meaningful reminders is ready.</p>
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
          <h4 class="text-xl font-bold text-brand">Craft your next reminder</h4>
          <p class="text-sm text-text-muted mt-1 font-medium italic">"The best of people are those who are most beneficial to others."</p>
        </div>
      </div>
      <div class="mt-8 flex items-center gap-2 text-xs font-bold text-brand uppercase tracking-widest group-hover:translate-x-2 transition-transform">
        Begin Your Reminder <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M17 8l4 4m0 0l-4 4m4-4H3"></path></svg>
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
        <h3 class="text-2xl font-bold text-brand tracking-tighter">Meta Connection</h3>
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
        <h1 class="text-4xl font-bold text-brand tracking-tighter">Studio <span class="text-accent underline decoration-accent/20 decoration-4 underline-offset-8">Guidance</span></h1>
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
            Create Reminder
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
            <div class="text-[9px] font-bold text-text-muted uppercase tracking-widest">Assistant</div>
            <div class="p-1.5 bg-brand/5 rounded-lg text-brand"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9l-.505.505a4.125 4.125 0 005.758 5.758l.505-.505m9.393-9.393l.505-.505a4.125 4.125 0 10-5.758-5.758l-.505.505" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></div>
        </div>
        <div>
            <div class="text-2xl font-bold text-brand tracking-tight underline decoration-emerald-500/30 decoration-2">Ready</div>
            <div class="text-[8px] font-bold text-text-muted uppercase tracking-widest mt-1">Guidance Engine</div>
        </div>
      </div>
      <div class="card p-6 border-brand/5 bg-white flex flex-col justify-between min-h-[120px]">
        <div class="flex justify-between items-start">
            <div class="text-[9px] font-bold text-text-muted uppercase tracking-widest">Guidance</div>
            <div class="p-1.5 bg-accent/10 rounded-lg text-accent"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg></div>
        </div>
        <div>
            <div class="text-2xl font-bold text-accent tracking-tighter">{next_post_countdown}</div>
            <div class="text-[8px] font-bold text-accent uppercase tracking-widest mt-1">Until Next Reminder</div>
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
        <div id="cta-container" class="pt-6 hidden">
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
        <div class="card p-5 bg-white border-brand/5 flex flex-col gap-5 hover:shadow-xl hover:shadow-brand/[0.03] transition-all group">
          <div class="flex items-start justify-between">
            <div class="flex items-center gap-4">
                <div class="w-10 h-10 rounded-xl bg-cream overflow-hidden border border-brand/5 shrink-0 shadow-inner">
                    {f'<img src="{p.media_url}" class="w-full h-full object-cover">' if p.media_url else '<div class="w-full h-full flex items-center justify-center text-[7px] font-bold text-text-muted/40 uppercase">Null</div>'}
                </div>
                <div>
                   <div class="text-[7px] font-black text-accent uppercase tracking-[0.2em] mb-1">{p_type}</div>
                   <div class="px-2 py-0.5 {status_bg} {status_color} rounded-md text-[6px] font-black uppercase tracking-widest inline-block">{status_label}</div>
                </div>
            </div>
            <div class="text-[8px] font-bold text-text-muted/40 uppercase tracking-widest">{date_str}</div>
          </div>

          <div class="space-y-3">
              <p class="text-[11px] font-bold text-brand leading-relaxed line-clamp-3 italic opacity-80 group-hover:opacity-100 transition-opacity">
                "{p.caption[:120] if p.caption else "Suggested Reminder"}"
              </p>
          </div>

          <div class="flex items-center gap-2 pt-2 border-t border-brand/[0.03]">
             <button onclick="openEditPostModal('{p.id}', {caption_json}, '{p.scheduled_time.isoformat() if p.scheduled_time else ''}')" class="flex-1 py-2.5 bg-white border border-brand/5 rounded-xl text-[8px] font-black uppercase tracking-widest text-text-muted hover:text-brand hover:border-brand/20 transition-all">Edit</button>
             {approve_btn}
             <button onclick="document.getElementById('editPostId').value='{p.id}'; showDeleteConfirm(); openEditPostModal('{p.id}', {caption_json})" class="p-2.5 text-rose-300 hover:text-rose-500 hover:bg-rose-50 rounded-xl transition-all">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
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
    accs = db.query(IGAccount).filter(IGAccount.org_id == org_id).all()
    account_options = "".join([f'<option value="{a.id}">@{a.username} ({a.name or "Sabeel Studio"})</option>' for a in accs])
    if not accs:
        account_options = '<option value="">No accounts connected</option>'

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
                          .replace("{studio_modal}", STUDIO_COMPONENTS_HTML)\
                          .replace("{studio_js}", STUDIO_SCRIPTS_JS)\
                          .replace("{account_options}", account_options)\
                          .replace("{connected_account_info}", connected_account_info)\
                          .replace("{connect_instagram_modal}", CONNECT_INSTAGRAM_MODAL_HTML)\
                          .replace("{extra_js}", f'<script>window.hasConnectedInstagram = {"true" if is_connected else "false"};</script>'))

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
                    if dp.status == "published": status_class = "bg-emerald-50 text-emerald-600 border border-emerald-100"
                    elif dp.status == "draft": status_class = "bg-amber-50 text-amber-600 border border-amber-100"
                    else: status_class = "bg-brand/5 text-brand border border-brand/10"
                    
                    # Preview (approx 8-12 words in 40-50 chars)
                    preview = (cap[:45] + "...") if len(cap) > 45 else (cap if cap else "Suggested Reminder")
                    display_status = dp.status.capitalize()
                    if dp.status == "published": display_status = "Shared"
                    elif dp.status == "scheduled": display_status = "Planned"
                    elif dp.status == "draft": display_status = "Reflection Draft"
                    
                    posts_html += f"""
                    <div class="p-2 rounded-xl border border-brand/5 bg-white/40 space-y-1.5 overflow-hidden group/post cursor-pointer hover:bg-white transition-colors" onclick="openEditPostModal('{dp.id}', `{dp.caption}`, '{dp.scheduled_time.isoformat()}')">
                        <div class="flex justify-between items-center">
                            <span class="text-[6px] font-black uppercase tracking-widest text-accent/60 group-hover/post:text-accent">{p_type}</span>
                            <span class="px-1 py-0.5 rounded-md {status_class} text-[5px] font-black uppercase tracking-tighter">{display_status}</span>
                        </div>
                        <p class="text-[8px] font-bold text-brand/60 group-hover/post:text-brand leading-snug line-clamp-2 italic">"{preview}"</p>
                    </div>
                    """
                
                is_today = (day == today.day and month == today.month and year == today.year)
                today_class = "border-brand/40 bg-brand/[0.02] shadow-[inner_0_0_20px_rgba(15,61,46,0.02)]" if is_today else "border-brand/5 hover:border-brand/10 bg-white"
                
                calendar_html += f"""
                <div class="min-h-[140px] glass border rounded-3xl p-3 flex flex-col gap-2 transition-all {today_class}">
                    <div class="flex justify-between items-center mb-1">
                        <span class="text-[10px] font-black { 'text-brand' if is_today else 'text-text-muted/30' }">{day}</span>
                        { '<span class="text-[7px] font-black bg-brand text-white px-2 py-0.5 rounded-full uppercase tracking-widest">Today</span>' if is_today else '' }
                    </div>
                    <div class="flex flex-col gap-2">
                        {posts_html or '<div class="py-4 text-center opacity-10"><div class="text-[10px] font-black tracking-widest uppercase">Empty</div></div>'}
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
                          .replace("{studio_modal}", STUDIO_COMPONENTS_HTML)\
                          .replace("{studio_js}", STUDIO_SCRIPTS_JS)\
                          .replace("{account_options}", account_options)\
                          .replace("{connected_account_info}", connected_account_info)\
                          .replace("{connect_instagram_modal}", CONNECT_INSTAGRAM_MODAL_HTML)\
                          .replace("{extra_js}", f'<script>window.hasConnectedInstagram = {"true" if is_connected else "false"};</script>')

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
            <button onclick="runNow(event, {a.id})" class="flex-1 md:flex-none px-6 py-4 bg-brand rounded-2xl text-white font-bold text-[10px] uppercase tracking-widest shadow-xl shadow-brand/20 hover:scale-[1.02] transition-all">Prepare Now</button>
          </div>
        </div>
        """

    empty_state_html = """
        <div class="card p-24 bg-white border-brand/5 border-dashed border-2 bg-brand/[0.01] text-center flex flex-col items-center justify-center space-y-8">
            <div class="w-24 h-24 rounded-[2.5rem] bg-brand/5 flex items-center justify-center text-brand border border-brand/10 shadow-inner">
              <svg class="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"/></svg>
            </div>
            <div class="space-y-3">
              <h3 class="text-2xl font-bold text-brand tracking-tight italic">Start your first Growth Plan</h3>
              <p class="text-text-muted text-sm max-w-sm font-medium">Set up how and when your reminders come to life.</p>
            </div>
            <button onclick="showNewAutoModal()" class="px-10 py-4 bg-brand text-white rounded-2xl font-bold text-[11px] uppercase tracking-widest shadow-xl shadow-brand/20 hover:bg-brand-hover transition-all">Start Plan</button>
        </div>
    """
    
    content = """
    <div class="space-y-10">
      <div class="flex justify-between items-end">
        <div>
        <h1 class="text-3xl font-bold text-brand tracking-tight italic">Growth</h1>
        <p class="text-[10px] font-bold text-text-muted uppercase tracking-[0.4em]">Reminder Growth Plans</p>
      </div>
      <button onclick="showNewAutoModal()" class="hidden md:flex px-8 py-4 bg-brand rounded-2xl font-bold text-[10px] uppercase tracking-[0.2em] text-white shadow-2xl shadow-brand/30 hover:translate-y-[-2px] transition-all items-center gap-3">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
          Start New Plan
      </button>
      </div>

      <div class="space-y-6">
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

    return APP_LAYOUT_HTML.replace("{content}", content.replace("{autos_html}", autos_html or empty_state_html))\
                          .replace("{title}", "Growth Plans")\
                          .replace("{user_name}", user.name or user.email)\
                          .replace("{org_name}", org.name if org else "Personal Workspace")\
                          .replace("{admin_link}", admin_link)\
                          .replace("{active_dashboard}", "")\
                          .replace("{active_calendar}", "")\
                          .replace("{active_automations}", "active")\
                          .replace("{active_library}", "")\
                          .replace("{active_media}", "")\
                          .replace("{studio_modal}", STUDIO_COMPONENTS_HTML)\
                          .replace("{studio_js}", STUDIO_SCRIPTS_JS)\
                          .replace("{account_options}", account_options)\
                          .replace("{connected_account_info}", connected_account_info)\
                          .replace("{connect_instagram_modal}", CONNECT_INSTAGRAM_MODAL_HTML)\
                          .replace("{extra_js}", f'<script>window.hasConnectedInstagram = {"true" if is_connected else "false"};</script>')

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
          <h1 class="text-3xl font-bold text-brand tracking-tight">Visuals</h1>
          <p class="text-[10px] font-bold text-text-muted uppercase tracking-[0.3em]">Visual Presence Studio</p>
        </div>
        <div class="flex gap-4">
            <button onclick="document.getElementById('mediaUploadInput').click()" class="px-8 py-4 bg-brand text-white rounded-xl font-bold text-[11px] uppercase tracking-widest shadow-xl shadow-brand/20 hover:bg-brand-hover transition-all flex items-center gap-3">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
                Add Visuals
            </button>
        </div>
      </div>
        <div id="mediaEmptyState" class="glass p-20 rounded-[3rem] border border-brand/5 bg-white text-center flex flex-col items-center justify-center space-y-6">
            <div class="w-20 h-20 rounded-[2rem] bg-brand/5 flex items-center justify-center border border-brand/10">
              <svg class="w-10 h-10 text-brand" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"/></svg>
            </div>
            <div>
              <h3 class="text-[11px] font-bold uppercase tracking-[0.3em] text-brand">Visual Library</h3>
              <p class="text-xs text-text-muted mt-2">Your visuals will appear here after you share reminders</p>
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

    return APP_LAYOUT_HTML.replace("{content}", content)\
                          .replace("{title}", "Visual Library")\
                          .replace("{user_name}", user.name or user.email)\
                          .replace("{org_name}", org.name if org else "Personal Workspace")\
                          .replace("{admin_link}", admin_link)\
                          .replace("{active_dashboard}", "")\
                          .replace("{active_calendar}", "")\
                          .replace("{active_automations}", "")\
                          .replace("{active_library}", "")\
                          .replace("{active_media}", "active")\
                          .replace("{studio_modal}", STUDIO_COMPONENTS_HTML)\
                          .replace("{studio_js}", STUDIO_SCRIPTS_JS)\
                          .replace("{account_options}", account_options)\
                          .replace("{connected_account_info}", connected_account_info)\
                          .replace("{connect_instagram_modal}", CONNECT_INSTAGRAM_MODAL_HTML)\
                          .replace("{extra_js}", f'<script>window.hasConnectedInstagram = {"true" if is_connected else "false"};</script>')

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
        :root {
            --library-bg: #F8F6F2;
            --library-surface: #FFFFFF;
            --library-border: rgba(15, 61, 46, 0.06);
            --library-text: #1A1A1A;
            --library-accent: #0F3D2E;
        }
        
        .dir-rtl { direction: rtl; unicode-bidi: bidi-override; }
        .font-serif { font-family: 'Amiri', 'Traditional Arabic', serif; }
        .hide-scrollbar::-webkit-scrollbar { display: none; }
        .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
        
        .library-container {
            background-color: var(--library-bg);
            min-height: 100vh;
            color: var(--library-text);
        }

        .glass-card {
            background: var(--library-surface);
            border: 1px solid var(--library-border);
            box-shadow: 0 4px 12px rgba(15, 61, 46, 0.04);
            transition: all 0.3s ease;
        }

        .surah-card {
            background: #FFFFFF;
            border: 1px solid rgba(15, 61, 46, 0.05);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .surah-card:hover {
            border-color: var(--brand);
            transform: translateY(-2px);
            box-shadow: 0 12px 24px rgba(15, 61, 46, 0.08);
        }
        
        .verse-card {
            border-left: 4px solid transparent;
        }
        .verse-card:hover {
            border-left-color: var(--brand);
            background: rgba(15, 61, 46, 0.02);
        }

        .skeleton {
            background: linear-gradient(90deg, #F0EDE8 25%, #F8F6F2 50%, #F0EDE8 75%);
            background-size: 200% 100%;
            animation: skeleton-loading 1.5s infinite;
        }
        @keyframes skeleton-loading {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }
    </style>
    
    <div class="library-container -m-6 md:-m-10 p-6 md:p-10 space-y-8 h-full flex flex-col">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 px-2">
        <div>
          <h1 class="text-4xl font-black text-text-main tracking-tighter flex items-center gap-4">
            <span id="libraryBreadcrumbRoot" onclick="showView('browse_surahs')" class="cursor-pointer hover:text-brand transition-all">Library</span>
            <span id="libraryBreadcrumbChild" class="hidden text-brand/20 font-light">&rsaquo;</span>
            <span id="libraryBreadcrumbName" class="text-brand text-3xl font-bold"></span>
          </h1>
          <p id="librarySubtitle" class="text-[10px] font-black text-brand uppercase tracking-[0.4em] mt-2">Foundation Wisdom • Organizational Intelligence</p>
        </div>
        <div class="flex gap-4">
          <button onclick="openEntryModal()" class="px-8 py-4 bg-brand rounded-2xl font-black text-[10px] uppercase tracking-widest text-white shadow-xl shadow-brand/20 hover:bg-brand-hover hover:scale-105 active:scale-95 transition-all flex items-center gap-3">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg>
            Add Wisdom
          </button>
        </div>
      </div>

      <!-- RECOMMENDED TRACK -->
      <div id="recommendedTrackWrapper" class="hidden flex-col border-y border-brand/5 bg-white shrink-0 shadow-sm">
        <div class="px-6 md:px-10 py-4 flex items-center justify-between">
          <h3 class="text-[10px] font-black uppercase tracking-[0.2em] text-brand flex items-center gap-3">
            <div class="w-1.5 h-1.5 rounded-full bg-brand animate-ping"></div>
            Curated For Your Voice
          </h3>
        </div>
        <div id="recommendedCards" class="flex gap-6 px-6 md:px-10 pb-8 overflow-x-auto hide-scrollbar">
          <!-- Loaded via JS -->
        </div>
      </div>

      <!-- Main Layout -->
      <div class="flex flex-col lg:flex-row gap-10 flex-1 overflow-hidden min-h-0">
        <!-- Sidebar Navigation -->
        <div class="w-full lg:w-80 flex flex-col gap-8 shrink-0">
            <!-- Source Selector -->
            <div class="glass-card rounded-[2.5rem] overflow-hidden">
                <div class="p-8 border-b border-brand/5 bg-brand/[0.01] flex justify-between items-center">
                    <h3 class="text-[10px] font-black uppercase tracking-widest text-text-muted">Collections</h3>
                    <div id="sourceCount" class="text-[9px] font-black text-brand bg-brand/5 px-3 py-1 rounded-full border border-brand/10">0</div>
                </div>
                <div id="sourceList" class="p-4 space-y-2 overflow-y-auto max-h-[400px] hide-scrollbar">
                    <!-- Loaded via JS -->
                </div>
                
                <div class="p-6 bg-brand/[0.01] border-t border-brand/5">
                    {library_controls}
                </div>
            </div>
            
            <!-- Quick Filters (Topics) -->
            <div class="glass-card rounded-[2.5rem] overflow-hidden flex-1 flex flex-col min-h-0">
                <div class="p-8 border-b border-brand/5 bg-brand/[0.01] flex justify-between items-center">
                    <h3 class="text-[10px] font-black uppercase tracking-widest text-text-muted">Knowledge Tags</h3>
                    <button onclick="suggestTopicFromSearch()" class="text-brand hover:scale-125 transition-all"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg></button>
                </div>
                <div id="sidebarTopicList" class="p-6 flex flex-wrap gap-2.5 overflow-y-auto hide-scrollbar">
                    <!-- Populated via JS -->
                </div>
            </div>
        </div>

        <!-- Main Workspace -->
        <!-- Search & Content Area -->
        <div class="flex-1 flex flex-col min-w-0 gap-8">
            <div class="relative group">
                <div class="absolute inset-y-0 left-8 flex items-center pointer-events-none">
                    <svg class="w-5 h-5 text-text-muted/30 group-focus-within:text-brand transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
                </div>
                <input type="text" id="entrySearch" oninput="debounceSearch()" 
                       class="w-full bg-white border border-brand/10 rounded-3xl pl-16 pr-8 py-6 text-sm text-text-main outline-none focus:ring-2 focus:ring-brand/10 transition-all placeholder:text-text-muted/40 shadow-sm" 
                       placeholder="Search through scripture, wisdom, and organization intelligence...">
            </div>
            
            <div id="entryList" class="flex-1 overflow-y-auto hide-scrollbar">
                <!-- Loaded via JS -->
            </div>

            <!-- Hidden State Storage to prevent JS crashes -->
            <input type="hidden" id="filterCategory" value="">
            <input type="hidden" id="filterTopic" value="">
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
      let entrySearchTimeout = null;
      let selectedTopic = null;
      const isSuperAdmin = {is_superadmin_js};
      const orgId = {org_id_js};
      let currentView = 'browse_surahs'; // 'browse_surahs' | 'surah_reading' | 'search_results'

      // --- DEFENSIVE NORMALIZATION (Emergency Stabilization) ---
      function normalizeLibraryEntry(raw) {
          if (!raw) return null;
          try {
              return {
                  id: raw.id ?? Math.random().toString(36).substring(2, 9),
                  item_type: raw.item_type || raw.type || "unknown",
                  title: raw.reference || raw.title || "Untitled Entry",
                  reference: raw.reference || raw.title || "Untitled Entry",
                  text: raw.translation_text || raw.text || raw.content || "Content unavailable",
                  arabic_text: raw.arabic_text || "",
                  topics: Array.isArray(raw.topics) ? raw.topics : (raw.topics ? [raw.topics] : []),
                  meta: raw.meta || {},
                  surah_number: raw.surah_number || raw.meta?.surah_number || null,
                  ayah_number: raw.ayah_number || raw.meta?.ayah_number || null,
                  surah_name_en: raw.surah_name_en || raw.meta?.surah_name_en || "",
                  surah_name_ar: raw.surah_name_ar || raw.meta?.surah_name_ar || ""
              };
          } catch (e) {
              console.error("[LIBRARY][NORMALIZE_CRASH]", e, raw);
              return null;
          }
      }

      // --- INITIALIZATION ---
      window.addEventListener('DOMContentLoaded', async () => {
          console.log("Library System: Initializing [Premium Mode]");
          
          try { checkPendingVerse(); } catch (e) { console.warn("Init Error: pending", e); }
          
          // Parallel non-blocking init
          const parallelInits = [
              { name: 'Topics', fn: loadTopics },
              { name: 'Sources', fn: loadSources },
              { name: 'Recommendations', fn: loadRecommendations }
          ];

          parallelInits.forEach(async step => {
              try {
                  await step.fn();
              } catch (e) {
                  console.error(`Library: ${step.name} failed to load`, e);
              }
          });

          // Core view init
          try {
              showView('browse_surahs');
          } catch (e) {
              console.error("Library: Failed to manifest main view", e);
              document.getElementById('entryList').innerHTML = `<div class="p-20 text-center text-rose-500 font-bold uppercase tracking-widest">Library Manifestation Failed. Check Foundation Connection.</div>`;
          }
      });

      function checkPendingVerse() {
          const pending = sessionStorage.getItem('sabeel_pending_quote_item');
          if (pending) {
              console.log("Bridge: Found pending verse, opening Studio...");
              setTimeout(() => {
                  if (typeof openStudio === 'function') {
                      openStudio();
                  }
              }, 500);
          }
      }

      async function loadRecommendations() {
          const track = document.getElementById('recommendedTrackWrapper');
          const cards = document.getElementById('recommendedCards');
          if (!track || !cards) return;

          try {
              const res = await fetch('/library/recommendations');
              const data = await res.json();
              if (!data || data.length === 0) {
                  track.classList.add('hidden');
                  return;
              }
              track.classList.remove('hidden');
              cards.innerHTML = data.map(item => {
                  libraryEntries[item.id] = item;
                  return `
                    <div onclick="selectRecommendation(${item.id})" class="min-w-[280px] p-6 bg-white border border-brand/5 rounded-[2rem] hover:border-brand/20 hover:shadow-lg transition-all cursor-pointer group">
                        <div class="flex items-center gap-3 mb-4">
                            <div class="w-8 h-8 rounded-lg bg-brand/5 text-brand flex items-center justify-center text-[10px] font-black">${(item.item_type || 'K').substring(0,1).toUpperCase()}</div>
                            <div class="text-[9px] font-black text-brand uppercase tracking-widest truncate">${item.reference || item.title || 'Wisdom Entry'}</div>
                        </div>
                        <p class="text-[11px] text-text-muted font-medium line-clamp-2 leading-relaxed italic">"${item.text}"</p>
                    </div>
                  `;
              }).join('');
          } catch (e) {
              console.error("Recommendations failed:", e);
              track.classList.add('hidden');
          }
      }

      function selectRecommendation(id) {
          const entry = libraryEntries[id];
          if (!entry) return;
          trackInteraction('selected_recommendation', id, 'library_track');
          if (entry.item_type === 'quran') {
              useInQuoteCard(id);
          } else {
              openEntryModalById(id);
          }
      }

      async function trackInteraction(type, entityId, context) {
          try {
              await fetch('/library/track-use', {
                  method: 'POST',
                  headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({ action_type: type, entity_id: String(entityId), context: context || 'library' })
              });
          } catch(e) { console.warn("Interaction tracking failed", e); }
      }

      function showView(view, data = null) {
          currentView = view;
          const breadcrumbChild = document.getElementById('libraryBreadcrumbChild');
          const breadcrumbName = document.getElementById('libraryBreadcrumbName');
          
          console.log("[LIBRARY] Navigating to view:", view);

          // Clear Search if navigating back to surahs
          if (view === 'browse_surahs') {
              document.getElementById('entrySearch').value = '';
              if (breadcrumbChild) breadcrumbChild.classList.add('hidden');
              if (breadcrumbName) breadcrumbName.textContent = '';
              loadSurahs();
          } else if (view === 'surah_reading') {
              if (breadcrumbChild) breadcrumbChild.classList.remove('hidden');
              if (breadcrumbName) breadcrumbName.textContent = data.name;
              loadSurahVerses(data.number);
          } else if (view === 'search_results') {
              if (breadcrumbChild) breadcrumbChild.classList.remove('hidden');
              if (breadcrumbName) breadcrumbName.textContent = 'Search Results';
              // loadEntries handles the canvas
          }
      }

      async function loadSurahs() {
          const canvas = document.getElementById('entryList');
          if (!canvas) return;
          // Loading Skeleton
          canvas.className = "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 pb-20";
          canvas.innerHTML = Array(9).fill(0).map(() => `<div class="skeleton h-32 rounded-[2.5rem] bg-white border border-brand/5"></div>`).join('');

          try {
              console.log("Fetching surahs...");
              const res = await fetch('/api/quran/surahs');
              if (!res.ok) throw new Error("API Status: " + res.status);
              const surahs = await res.json();
              
              if (!surahs || !Array.isArray(surahs) || surahs.length === 0) {
                  canvas.innerHTML = `<div class="col-span-full py-32 text-center text-text-muted font-black uppercase tracking-[0.5em]">No Foundation Records Found</div>`;
                  return;
              }

              canvas.innerHTML = surahs.map(s => `
                <div onclick="showView('surah_reading', {number: ${s.number}, name: '${(s.name_en || '').replace(/'/g, "\\'")}'})" 
                     class="surah-card p-8 rounded-[2.5rem] cursor-pointer group flex items-center justify-between">
                    <div class="flex items-center gap-6 overflow-hidden">
                        <div class="surah-number w-12 h-12 rounded-2xl bg-brand/5 border border-brand/10 text-brand flex items-center justify-center text-[11px] font-black tracking-tighter transition-all group-hover:bg-brand group-hover:text-white group-hover:scale-110">
                            ${s.number}
                        </div>
                        <div class="overflow-hidden">
                            <h4 class="text-sm font-black text-text-main group-hover:text-brand transition-colors truncate">${s.name_en}</h4>
                            <p class="text-[9px] font-bold text-text-muted/40 uppercase tracking-widest mt-1">${s.verses_count} Verses • ${s.revelation_type}</p>
                        </div>
                    </div>
                    <div class="text-2xl font-serif text-brand/10 group-hover:text-brand transition-colors pl-4">${s.name_ar}</div>
                </div>
              `).join('');
          } catch(e) {
              console.error("Surah load failed", e);
              canvas.innerHTML = `<div class="col-span-full py-20 text-center text-rose-500 font-bold uppercase text-[10px]">Critical Error: ${e.message}</div>`;
          }
      }

      async function loadSurahVerses(surahNumber) {
          try {
              const res = await fetch(`/api/quran/surahs/${surahNumber}`);
              const surah = await res.json();
              
              const canvas = document.getElementById('entryList');
              canvas.className = "flex-1 space-y-8 pb-32";
              
              let versesHtml = `
                <div class="bg-white p-12 rounded-[3rem] shadow-sm mb-12 flex flex-col md:flex-row justify-between items-center gap-8 border-l-8 border-l-brand">
                    <div class="text-center md:text-left">
                        <h2 class="text-4xl font-black text-text-main tracking-tighter mb-2">${surah.name_en}</h2>
                        <p class="text-[10px] font-black text-brand uppercase tracking-[0.4em]">${surah.total_verses} Ayahs • Revealed in ${surah.revelation_place}</p>
                    </div>
                    <div class="text-6xl font-serif text-brand/10">${surah.name_ar}</div>
                </div>
              `;

              if (surahNumber !== 1 && surahNumber !== 9) {
                  versesHtml += `
                    <div class="text-center py-16 opacity-80">
                        <p class="font-serif text-4xl text-brand tracking-widest leading-loose">بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ</p>
                    </div>
                  `;
              }

              versesHtml += surah.verses.map(v => {
                  libraryEntries[v.id] = v;
                  return `
                <div class="verse-card bg-white p-12 rounded-[3rem] transition-all hover:shadow-lg border border-brand/5 relative group">
                    <!-- Actions -->
                    <div class="absolute top-8 right-10 opacity-0 group-hover:opacity-100 transition-all flex gap-3 z-10">
                         <button onclick='useInQuoteCard(${v.id})' class="px-6 py-3 bg-brand text-white rounded-2xl text-[9px] font-black uppercase tracking-[0.2em] shadow-xl shadow-brand/20 hover:scale-105 active:scale-95 transition-all">
                            Manifest in Card
                        </button>
                    </div>

                    <div class="space-y-10">
                        <div class="flex flex-col md:flex-row justify-between items-start gap-10">
                            <div class="w-12 h-12 shrink-0 rounded-2xl border border-brand/10 flex items-center justify-center text-[10px] font-black text-brand/20 bg-brand/5 transition-all group-hover:bg-brand group-hover:text-white">
                                ${v.ayah_number}
                            </div>
                            <p class="dir-rtl font-serif text-4xl text-text-main leading-[2.2] text-right flex-1 tracking-tight">
                                ${v.arabic_text}
                            </p>
                        </div>
                        <div class="pl-20">
                            <p class="text-text-main/90 text-xl leading-[1.8] font-medium mb-6">
                                ${v.translation_text}
                            </p>
                            <div class="flex items-center gap-6">
                               <span class="text-[9px] font-black text-brand uppercase tracking-[0.3em]">Ref: ${v.reference}</span>
                               <div class="w-1 h-1 rounded-full bg-brand/10"></div>
                               <span class="text-[9px] font-bold text-text-muted uppercase tracking-widest">${v.translator}</span>
                            </div>
                        </div>
                    </div>
                </div>
              `).join('');
              
              canvas.innerHTML = versesHtml;
              canvas.scrollTo(0, 0);
          } catch(e) {
              console.error("Verses load failed", e);
              document.getElementById('entryList').innerHTML = '<div class="col-span-full py-20 text-center text-rose-500 font-bold uppercase text-[10px]">Failed to load verses</div>';
          }
      }

      function useInQuoteCard(id) {
          const entry = libraryEntries[id];
          if (!entry) return;

          console.log("Bridge: Setting pending verse...", entry);
          trackInteraction('used_entry', id, 'library');

          sessionStorage.setItem('sabeel_pending_quote_item', JSON.stringify({
              id: entry.id,
              type: 'quran_verse',
              text: entry.translation_text || entry.text,
              arabic_text: entry.arabic_text,
              reference: entry.reference || entry.title,
              meta: entry
          }));
          
          if (typeof openNewPostModal === 'function') {
              openNewPostModal();
          } else {
              window.location.href = '/app?studio=true'; // Better fallback for app-wide studio trigger
          }
      }

      async function loadTopics() {
          try {
              const res = await fetch('/library/topics');
              const topics = await res.json();
              const chips = document.getElementById('sidebarTopicList');
              if (!Array.isArray(topics)) {
                  console.warn("[LIBRARY] Topics payload is not an array");
                  chips.innerHTML = '';
                  return;
              }
              chips.innerHTML = topics.slice(0, 25).map(t => {
                  try {
                      return `
                        <button onclick="filterByTopic('${t.slug || ''}')" class="px-4 py-2 rounded-xl bg-brand/5 border border-brand/10 text-[9px] font-black uppercase tracking-[0.2em] text-brand/60 hover:bg-brand hover:text-white transition-all">
                            ${(t.slug || 'unknown').replace(/_/g, ' ')}
                        </button>
                      `;
                  } catch (e) { return ''; }
              }).join('');
          } catch(e) { console.error("Topic load failed", e); }
      }

      function filterByTopic(slug) {
          document.getElementById('entrySearch').value = slug;
          trackInteraction('selected_topic', slug, 'library_filters');
          loadEntries();
      }

      async function loadSources() {
          const list = document.getElementById('sourceList');
          if (!list) return;
          list.innerHTML = Array(3).fill(0).map(() => `<div class="skeleton h-14 rounded-2xl mb-2 opacity-30"></div>`).join('');
          
          try {
              const url = showGlobalOnly ? '/api/quran/surahs' : '/library/sources';
              const res = await fetch(url);
              if (!res.ok) throw new Error("Sources API error: " + res.status);
              const sources = await res.json();
              
              if (!Array.isArray(sources)) {
                console.warn("[LIBRARY] Sources payload is not an array:", sources);
                list.innerHTML = `<div class="p-8 text-center text-white/10 font-bold text-[8px] uppercase tracking-widest">Format Error</div>`;
                return;
              }

              if (showGlobalOnly) {
                  document.getElementById('sourceCount').textContent = "∞";
                  list.innerHTML = `
                    <div onclick="showView('browse_surahs')" class="p-4 px-6 rounded-2xl cursor-pointer transition-all border flex items-center gap-4 group bg-brand/5 border-brand/20 shadow-sm">
                        <div class="w-10 h-10 rounded-2xl bg-brand text-white flex items-center justify-center shrink-0">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
                        </div>
                        <div class="flex-1 overflow-hidden">
                            <div class="text-[10px] font-black truncate text-brand uppercase tracking-wider">Quran Foundation</div>
                            <div class="text-[8px] font-bold text-text-muted uppercase mt-0.5">Global Wisdom</div>
                        </div>
                    </div>
                  `;
                  return;
              }

              document.getElementById('sourceCount').textContent = sources.length;
              const mapHtml = sources.map(s => {
                const isActive = s && s.id === currentSourceId;
                if (!s) return '';
                return `
                <div onclick="filterBySource(${s.id})" class="p-4 px-6 rounded-2xl cursor-pointer transition-all border flex items-center gap-4 group ${isActive ? 'bg-brand/5 border-brand/20 shadow-sm' : 'hover:bg-brand/[0.02] border-transparent hover:border-brand/10'}">
                    <div class="w-10 h-10 rounded-2xl bg-brand/5 border border-brand/10 flex items-center justify-center shrink-0 transition-all group-hover:scale-110">
                        <span class="text-xs">📂</span>
                    </div>
                    <div class="flex-1 overflow-hidden">
                        <div class="text-[10px] font-black truncate ${isActive ? 'text-brand' : 'text-text-muted'} group-hover:text-brand uppercase tracking-wider">${s.name || 'Untitled'}</div>
                        <div class="text-[7px] font-bold text-text-muted/50 uppercase mt-0.5 tracking-[0.2em]">${s.source_type || 'Unknown'} • ${s.items_count || 0} Entries</div>
                    </div>
                </div>
                `;
              }).join('');

              list.innerHTML = mapHtml;

              // Populate Modal Dropdown
              const modalSelect = document.getElementById('sourceSelect');
              if (modalSelect) {
                  const options = sources.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
                  modalSelect.innerHTML = `<option value="">Create New...</option>${options}`;
              }

              if (sources.length === 0) {
                  list.innerHTML = `<div class="p-8 text-center text-white/10 font-bold text-[8px] uppercase tracking-widest">No Private Collections</div>`;
              }
          } catch(e) {
              list.innerHTML = '<div class="text-rose-400 text-[10px] font-bold p-10">Sync failed.</div>';
          }
      }

      function selectSource(id) {
          currentSourceId = id;
          showView('search_results');
          loadSources();
          loadEntries();
      }

      async function loadEntries() {
          const list = document.getElementById('entryList');
          if (!list) return;
          const query = document.getElementById('entrySearch')?.value || '';
          const category = document.getElementById('filterCategory')?.value || '';
          
          if (!query && !category && !currentSourceId) {
              // Forced refresh of surahs if in global mode
              showView('browse_surahs');
              return;
          }

          showView('search_results');
          list.innerHTML = '<div class="text-center py-20 text-[10px] text-brand font-black uppercase tracking-[0.4em] animate-pulse">Scanning Neural Nodes...</div>';
          list.className = "flex-1 space-y-6 pb-20";

          try {
              let url = `/library/entries?query=${encodeURIComponent(query)}`;
              if (currentSourceId) url += `&source_id=${currentSourceId}`;
              if (category) url += `&item_type=${encodeURIComponent(category)}`;
              url += `&scope=${showGlobalOnly ? 'global' : 'org'}`;
              
              const res = await fetch(url);
              const entries = await res.json();
              
              if (entries.length === 0) {
                  list.innerHTML = '<div class="py-20 text-center text-[10px] font-black uppercase text-text-muted">No nodes found in this scope</div>';
                  return;
              }

              list.innerHTML = entries.map(raw => {
                const e = normalizeLibraryEntry(raw);
                if (!e) return '';
                
                try {
                    libraryEntries[e.id] = e;
                    return `
                    <div class="bg-white p-10 rounded-[3rem] group relative hover:shadow-xl transition-all border border-brand/5 border-l-4 border-l-transparent hover:border-l-brand">
                        <div class="absolute top-8 right-10 opacity-0 group-hover:opacity-100 transition-all flex gap-3 z-10">
                             ${e.item_type === 'quran' || e.item_type === 'quote' ? `<button onclick='useInQuoteCard(${e.id})' class="px-6 py-3 bg-brand text-white rounded-2xl text-[9px] font-black uppercase tracking-[0.2em] shadow-xl shadow-brand/20 hover:scale-105 active:scale-95 transition-all">Manifest in Card</button>` : ''}
                             <button onclick="openEntryModalById(${e.id})" class="p-3 bg-brand/5 border border-brand/10 rounded-2xl text-brand hover:bg-brand hover:text-white transition-all"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg></button>
                        </div>
                        <div class="flex items-center gap-6 mb-8">
                            <div class="w-12 h-12 rounded-2xl bg-brand/5 text-brand flex items-center justify-center border border-brand/10 uppercase text-[9px] font-black tracking-tighter">${(e.item_type || "NOD").substring(0,3)}</div>
                            <div>
                                <div class="text-[8px] font-black uppercase text-text-muted/60 tracking-widest">${e.item_type} Intelligence</div>
                                <div class="text-[11px] font-black text-text-main uppercase tracking-wider truncate">${e.reference || e.title}</div>
                            </div>
                        </div>
                        <p class="text-text-main/80 text-lg leading-relaxed font-medium mb-8 line-clamp-4 italic">
                            "${e.text}"
                        </p>
                        <div class="flex flex-wrap gap-2.5 pt-8 border-t border-brand/5">
                            ${(e.topics || []).map(t => `<span class="px-3 py-1.5 bg-brand/5 border border-brand/10 rounded-xl text-[8px] font-black uppercase tracking-widest text-brand/60 hover:text-brand transition-colors cursor-pointer">${t}</span>`).join('')}
                        </div>
                    </div>
                  `;
                } catch (err) {
                    console.error("[LIBRARY][CARD_RENDER_FAIL]", err, raw);
                    return '';
                }
              }).join('');
          } catch(e) { console.error("Entries load failed", e); }
      }

      function debounceSearch() {
          clearTimeout(entrySearchTimeout);
          entrySearchTimeout = setTimeout(() => loadEntries(), 500);
      }

      function updateCharCount() {
          const text = document.getElementById('entryText').value;
          document.getElementById('charCount').textContent = `${text.length} / 3000`;
      }

      function setEntryType(type, element) {
          document.getElementById('entryType').value = type;
          // Toggle UI state
          document.querySelectorAll('.type-btn').forEach(btn => {
              btn.classList.remove('bg-brand', 'text-white', 'shadow-xl', 'shadow-brand/20');
              btn.classList.add('bg-white', 'text-text-muted');
          });
          if (element) {
              element.classList.remove('bg-white', 'text-text-muted');
              element.classList.add('bg-brand', 'text-white', 'shadow-xl', 'shadow-brand/20');
          }
          
          // Show/Hide global toggle only for certain types if needed
          const globalToggle = document.getElementById('globalToggleContainer');
          if (globalToggle) {
              globalToggle.classList.toggle('hidden', !['quran', 'hadith', 'quote'].includes(type));
          }
      }

      function checkNewSource() {
          const val = document.getElementById('sourceSelect').value;
          const container = document.getElementById('newSourceFields');
          if (container) {
              container.classList.toggle('hidden', val !== '');
          }
      }

      async function saveEntry() {
          const btn = event?.currentTarget;
          if (btn) {
              btn.disabled = true;
              btn.textContent = "Committing...";
          }

          try {
              const id = document.getElementById('entryId').value;
              const sourceId = document.getElementById('sourceSelect').value;
              const payload = {
                  source_id: sourceId || null,
                  source_name: sourceId ? null : document.getElementById('newSourceName').value,
                  item_type: document.getElementById('entryType').value,
                  text: document.getElementById('entryText').value,
                  meta: {
                    is_global: document.getElementById('isGlobalCheckbox').checked
                  }
              };

              const url = id ? `/api/admin/library/entries/${id}` : '/api/admin/library/entries';
              const method = id ? 'PATCH' : 'POST';

              const res = await fetch(url, {
                  method: method,
                  headers: { 'Content-Type': 'application/json', 'X-Org-Id': orgId },
                  body: JSON.stringify(payload)
              });

              if (!res.ok) {
                  const err = await res.json();
                  throw new Error(err.detail || "Failed to save knowledge");
              }

              hideEntryModal();
              loadSources();
              loadEntries();
              
              if (typeof showToast === 'function') showToast("Knowledge persisted successfully", "success");
          } catch (e) {
              console.error("Save failed", e);
              alert("Error: " + e.message);
          } finally {
              if (btn) {
                  btn.disabled = false;
                  btn.textContent = "Commit Knowledge";
              }
          }
      }

      function toggleGlobalView(global) {
          showGlobalOnly = global;
          const orgBtn = document.getElementById('orgViewBtn');
          const globalBtn = document.getElementById('globalViewBtn');
          const activeClass = "flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter bg-brand text-white shadow-md transition-all";
          const inactiveClass = "flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter text-brand/40 hover:text-brand transition-all";
          
          if (globalBtn) globalBtn.className = global ? activeClass : inactiveClass;
          if (orgBtn) orgBtn.className = !global ? activeClass : inactiveClass;
          
          currentSourceId = null;
          
          // Reset UI state to trigger fresh manifestation
          const query = document.getElementById('entrySearch');
          if (query) query.value = '';
          
          loadSources();
          loadEntries();
      }

      function openEntryModalById(id) {
          const entry = libraryEntries[id];
          if (!entry) return;
          
          document.getElementById('entryId').value = entry.id;
          document.getElementById('entryText').value = entry.text || '';
          document.getElementById('entryModalTitle').innerHTML = `Edit <span class="text-accent">${(entry.item_type || 'Knowledge').toUpperCase()}</span>`;
          
          // Set type
          const type = entry.item_type || 'note';
          const typeBtn = document.querySelector(`.type-btn[onclick*="'${type}'"]`);
          setEntryType(type, typeBtn);

          // Meta / Global
          const globalCheck = document.getElementById('isGlobalCheckbox');
          if (globalCheck) globalCheck.checked = entry.meta?.is_global === true;

          // Select source
          const sourceSelect = document.getElementById('sourceSelect');
          if (sourceSelect) sourceSelect.value = entry.source_id || '';
          checkNewSource();

          document.getElementById('entryModal').classList.remove('hidden');
          updateCharCount();
      }

      function openEntryModal() {
          document.getElementById('entryId').value = '';
          document.getElementById('entryText').value = '';
          document.getElementById('entryModalTitle').innerHTML = `Add <span class="text-accent">Knowledge</span>`;
          document.getElementById('entryModal').classList.remove('hidden');
          
          // Reset to default type
          const noteBtn = document.querySelector(`.type-btn[onclick*="'note'"]`);
          setEntryType('note', noteBtn);
          
          updateCharCount();
      }
      async function saveSynonym() {
          const slug = document.getElementById('syn_slug').value;
          const list = document.getElementById('syn_list').value;
          if (!slug || !list) return;

          try {
              const res = await fetch('/api/admin/library/synonyms', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ slug, synonyms: list.split(',').map(s => s.trim()) })
              });
              if (res.ok) {
                  document.getElementById('syn_slug').value = '';
                  document.getElementById('syn_list').value = '';
                  loadSynonyms();
              }
          } catch (e) { console.error(e); }
      }

      async function loadSynonyms() {
          try {
              const res = await fetch('/api/admin/library/synonyms');
              const data = await res.json();
              const table = document.getElementById('synonymTable');
              table.innerHTML = (data || []).map(s => `
                  <div class="flex justify-between items-center p-4 bg-brand/5 rounded-xl border border-brand/10 mb-2">
                      <div class="overflow-hidden">
                          <div class="text-[10px] font-black text-brand uppercase truncate">${s.slug}</div>
                          <div class="text-[8px] text-text-muted truncate">${(s.synonyms || []).join(', ')}</div>
                      </div>
                      <button onclick="deleteSynonym('${s.slug}')" class="text-rose-500 hover:scale-125 transition-all ml-4 shrink-0">
                          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                      </button>
                  </div>
              `).join('');
          } catch (e) { console.error(e); }
      }

      async function deleteSynonym(slug) {
          if (!confirm("Delete synonyms for " + slug + "?")) return;
          try {
              await fetch(`/api/admin/library/synonyms/${slug}`, { method: 'DELETE' });
              loadSynonyms();
          } catch (e) { console.error(e); }
      }

      function openSynonymModal() {
          document.getElementById('synonymModal').classList.remove('hidden');
          loadSynonyms();
      }
      async function suggestTopicFromSearch() {
          const query = document.getElementById('entrySearch').value;
          if (!query || query.length < 3) return;

          try {
              const res = await fetch('/library/topic-suggest', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ text: query, max: 1 })
              });
              const data = await res.json();
              if (data.suggestions && data.suggestions.length > 0) {
                  const suggestion = data.suggestions[0].topic;
                  if (confirm("Suggested Topic: " + suggestion + "\nApply filter?")) {
                      document.getElementById('entrySearch').value = suggestion;
                      loadEntries();
                  }
              }
          } catch (e) {
              console.warn("Topic suggestion failed", e);
          }
      }

      function hideEntryModal() {
          document.getElementById('entryModal').classList.add('hidden');
      }

      function closeSynonymModal() {
          document.getElementById('synonymModal').classList.add('hidden');
      }

      // Add character count listener for the search bar as well if needed
      document.addEventListener('DOMContentLoaded', () => {
          const area = document.getElementById('entryText');
          if (area) area.addEventListener('input', updateCharCount);
      });
    </script>
    """
    
    return APP_LAYOUT_HTML.replace("{content}", content.replace("{library_controls}", f"""
            <div class="flex p-1 bg-brand/5 rounded-xl border border-brand/10 gap-2">
                <button onclick="toggleGlobalView(false)" id="orgViewBtn" class="flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter transition-all bg-brand text-white shadow-md">Org</button>
                <button onclick="toggleGlobalView(true)" id="globalViewBtn" class="flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter transition-all text-brand/40 hover:text-brand">System</button>
                <button onclick="openSynonymModal()" class="px-3 py-1.5 border border-brand/10 rounded-lg text-brand hover:bg-white hover:shadow-sm transition-all focus:ring-2 focus:ring-brand/20">
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
                          .replace("{org_id_js}", str(user.active_org_id or 0))\
                          .replace("{studio_modal}", STUDIO_COMPONENTS_HTML)\
                          .replace("{account_options}", "")\
                          .replace("{connect_instagram_modal}", CONNECT_INSTAGRAM_MODAL_HTML)\
                          .replace("{studio_js}", STUDIO_SCRIPTS_JS)\
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
