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
    // --- REMINDER STUDIO CORE LOGIC (v3.0) ---
    let currentQuoteCardUrl = null;
    let isQuoteCardOutOfDate = false;
    let studioCreationMode = 'preset'; // 'preset' or 'custom'

    function openNewPostModal() {
        document.getElementById('newPostModal').classList.remove('hidden');
        switchStudioSection(1);
    }

    function closeNewPostModal() {
        document.getElementById('newPostModal').classList.add('hidden');
    }

    function switchStudioSection(stepIndex) {
        // Hide all sections (4 steps)
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
               const txt = nav.querySelector('.nav-text');
               if (txt) {
                   txt.classList.remove('text-brand');
                   txt.classList.add('text-text-muted');
               }
           }
        }
        
        // Activate requested section
        const target = document.getElementById('studioSection' + stepIndex);
        if(target) {
            target.classList.remove('hidden');
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
           const txt = targetNav.querySelector('.nav-text');
           if (txt) {
               txt.classList.remove('text-text-muted');
               txt.classList.add('text-brand');
           }
        }

        // Section Specific Hooks
        if (stepIndex === 4) {
            prepareManifest();
        }
    }

    // --- SELECTION HANDLERS ---
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

    function switchStudioMode(mode) {
        studioCreationMode = mode;
        const presetBtn = document.getElementById('btnModePreset');
        const customBtn = document.getElementById('btnModeCustom');
        const presetContainer = document.getElementById('presetModeContainer');
        const customContainer = document.getElementById('customModeContainer');
        const generateBtn = document.getElementById('btnGenerateCard');

        if (mode === 'preset') {
            presetBtn.classList.add('bg-brand', 'text-white', 'shadow-lg', 'shadow-brand/20');
            presetBtn.classList.remove('bg-brand/5', 'text-brand');
            customBtn.classList.remove('bg-brand', 'text-white', 'shadow-lg', 'shadow-brand/20');
            customBtn.classList.add('bg-brand/5', 'text-brand');
            
            presetContainer.classList.remove('hidden');
            customContainer.classList.add('hidden');
            generateBtn.innerText = 'Generate Visual';
        } else {
            customBtn.classList.add('bg-brand', 'text-white', 'shadow-lg', 'shadow-brand/20');
            customBtn.classList.remove('bg-brand/5', 'text-brand');
            presetBtn.classList.remove('bg-brand', 'text-white', 'shadow-lg', 'shadow-brand/20');
            presetBtn.classList.add('bg-brand/5', 'text-brand');
            
            customContainer.classList.remove('hidden');
            presetContainer.classList.add('hidden');
            generateBtn.innerText = 'Generate From Description';
        }
        invalidateQuoteCard();
    }

    // --- AI GENERATION LOGIC ---
    async function generateAICaption() {
        const topic = document.getElementById('studioTopic').value;
        const intention = document.getElementById('studioIntent').value;
        const tone = document.getElementById('studioTone').value;
        const btn = document.getElementById('btnCraftCaption');
        const icon = document.getElementById('craftIcon');
        const text = document.getElementById('craftText');

        if (!topic) {
            alert('Please define a topic to spark the reminder.');
            return;
        }

        btn.disabled = true;
        icon.classList.add('animate-spin');
        text.innerText = 'Crafting Spiritual Essence...';

        try {
            const res = await fetch('/generate-caption', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ topic, intention, tone })
            });
            const data = await res.json();
            if (data.caption) {
                document.getElementById('studioCaption').value = data.caption;
                document.getElementById('captionResultArea').classList.remove('hidden');
                invalidateQuoteCard(); // New caption = card out of date
            }
        } catch (e) {
            alert('The Spark failed to ignite. Check your connection.');
        } finally {
            btn.disabled = false;
            icon.classList.remove('animate-spin');
            text.innerText = 'Craft Cinematic Caption';
        }
    }

    async function generateQuoteCard() {
        const captionEl      = document.getElementById('studioCaption');
        const visualPromptEl = document.getElementById('studioVisualPrompt');
        const styleEl        = document.getElementById('studioStyle');
        const btn            = document.getElementById('btnGenerateCard');
        const loader         = document.getElementById('cardLoader');
        const loaderText     = loader ? loader.querySelector('span') : null;
        const preview        = document.getElementById('quoteCardPreview');
        const syncBanner     = document.getElementById('outOfSyncBanner');
        const promptErrEl    = document.getElementById('visualPromptError');

        if (!captionEl || !styleEl || !btn) {
            console.error('[Studio] Critical element missing');
            return;
        }

        const caption      = captionEl.value.trim();
        const visualPrompt = visualPromptEl ? visualPromptEl.value.trim() : '';
        const isCustomMode = (studioCreationMode === 'custom');

        // --- Validation ---
        if (!caption) {
            alert('A caption is required. Please complete Step 1 first.');
            return;
        }

        if (isCustomMode && !visualPrompt) {
            if (promptErrEl) {
                promptErrEl.classList.remove('hidden');
                promptErrEl.textContent = 'Please describe your card atmosphere before generating.';
            }
            if (visualPromptEl) visualPromptEl.focus();
            return;
        }
        if (promptErrEl) promptErrEl.classList.add('hidden');

        // --- Build payload ---
        const style   = isCustomMode ? 'custom' : (styleEl.value || 'quran');
        const payload = {
            caption,
            style,
            visual_prompt: isCustomMode ? visualPrompt : '',
            mode:          isCustomMode ? 'custom' : 'preset',
        };
        console.log('🎨 [Studio] Generate payload:', payload);

        // --- UI State: Loading ---
        btn.disabled    = true;
        btn.innerText   = 'Manifesting...';
        if (loader)     loader.classList.remove('hidden');
        if (preview)    preview.classList.add('hidden');
        if (syncBanner) syncBanner.classList.add('hidden');
        if (loaderText) loaderText.innerText = isCustomMode
            ? 'Interpreting Your Vision...'
            : 'Building Atmosphere...';

        try {
            const res  = await fetch('/generate-quote-card', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify(payload),
            });
            const data = await res.json();
            console.log('🖼️ [Studio] Response:', data);

            if (data.image_url) {
                currentQuoteCardUrl = data.image_url;
                document.getElementById('finalMediaUrl').value = data.image_url;
                preview.src = data.image_url + '?t=' + Date.now();
                preview.classList.remove('hidden');
                if (loader)  loader.classList.add('hidden');
                document.getElementById('cardActions').classList.remove('hidden');
                isQuoteCardOutOfDate = false;

                // Show badge if custom prompt was applied
                const badge = document.getElementById('customPromptBadge');
                if (badge) {
                    badge.classList.toggle('hidden', !data.prompt_applied);
                }
            } else {
                const errMsg = data.error || data.hint || 'Generation failed.';
                if (loaderText) loaderText.innerText = 'Failed';
                alert('⚠️ ' + errMsg);
                if (loader)  loader.classList.remove('hidden');
                if (preview) preview.classList.add('hidden');
            }
        } catch (e) {
            console.error('[Studio] Fetch error:', e);
            if (loaderText) loaderText.innerText = 'Connection Error';
        } finally {
            btn.disabled  = false;
            btn.innerText = isCustomMode ? 'Generate From Description' : 'Generate Cinematic Visual';
        }
    }

    function invalidateQuoteCard() {
        if (currentQuoteCardUrl) {
            isQuoteCardOutOfDate = true;
            document.getElementById('outOfSyncBanner').classList.remove('hidden');
        }
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

        if (isQuoteCardOutOfDate && !confirm("Your quote card no longer matches your latest caption. Manifest anyway?")) {
            return;
        }

        btn.disabled = true;
        btn.innerHTML = 'MANIFESTING... <span class="animate-pulse">✨</span>';

        const formData = new FormData(event.target);
        
        // Add library item ID if needed (compatibility)
        formData.append('visual_mode', 'quote_card');
        formData.append('source_text', document.getElementById('studioTopic').value);

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

    // --- ACCOUNT SWITCHER & STATE SYNC (LEGACY SUPPORT) ---
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
        } catch (e) { console.error(e); }
    }

    window.addEventListener('click', function(event) {
        if (!event.target.closest('#accountSwitcherRoot')) {
            const drop = document.getElementById('switcherDropdown');
            if (drop && !drop.classList.contains('hidden')) drop.classList.add('hidden');
        }
    });

    window.addEventListener('load', function() {
        renderAccountSwitcher();
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
          <h3 class="text-3xl font-bold text-brand tracking-tighter italic">Reminder<br><span class="text-accent">Creator</span></h3>
          <p class="text-[9px] font-bold text-text-muted uppercase tracking-[0.3em] mt-2">Guidance Studio v3.0</p>
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
        <input type="hidden" name="intent_type" id="studioIntent" value="wisdom">
        <input type="hidden" name="emotion" id="studioTone" value="calm">
        <input type="hidden" name="visual_style" id="studioStyle" value="quran">
        <input type="hidden" name="media_url" id="finalMediaUrl">

        <div class="flex-1 overflow-y-auto p-6 md:p-12 pb-32 custom-scrollbar">
          
          <!-- PHASE 1: THE SPARK (Caption Generation) -->
          <div id="studioSection1" class="studio-section space-y-10 animate-in slide-in-from-right-8 duration-500">
            <div>
              <label class="text-[9px] font-bold uppercase tracking-[0.3em] text-accent">Studio Phase 01</label>
              <h4 class="text-3xl font-bold text-brand italic">Ignite the Spark</h4>
              <p class="text-xs text-text-muted mt-2 font-medium">Define your topic and spiritual intention to craft a powerful message.</p>
            </div>

            <div class="space-y-8">
                <!-- Topic Input -->
                <div class="space-y-3">
                   <label class="text-[9px] font-black text-brand uppercase tracking-widest ml-1">Reminder Topic</label>
                   <input type="text" id="studioTopic" name="topic" placeholder="e.g. Patience during trials, Gratitude for small blessings..." class="w-full bg-cream/20 border border-brand/5 rounded-2xl px-8 py-6 text-sm font-medium text-brand outline-none focus:border-brand/20 transition-all shadow-inner">
                </div>

                <!-- Intention & Tone Grid -->
                <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <div class="space-y-4">
                        <label class="text-[9px] font-black text-brand uppercase tracking-widest ml-1">Spiritual Intention</label>
                        <div class="grid grid-cols-2 gap-2">
                           <div onclick="setStudioIntent('wisdom', this)" class="intent-card active p-4 rounded-xl border-2 border-brand/5 bg-cream/10 cursor-pointer text-center text-[9px] font-black uppercase tracking-widest">Wisdom</div>
                           <div onclick="setStudioIntent('reminder', this)" class="intent-card p-4 rounded-xl border-2 border-brand/5 bg-cream/10 cursor-pointer text-center text-[9px] font-black uppercase tracking-widest">Reminder</div>
                           <div onclick="setStudioIntent('outreach', this)" class="intent-card p-4 rounded-xl border-2 border-brand/5 bg-cream/10 cursor-pointer text-center text-[9px] font-black uppercase tracking-widest">Outreach</div>
                           <div onclick="setStudioIntent('reflection', this)" class="intent-card p-4 rounded-xl border-2 border-brand/5 bg-cream/10 cursor-pointer text-center text-[9px] font-black uppercase tracking-widest">Reflect</div>
                        </div>
                    </div>
                    <div class="space-y-4">
                        <label class="text-[9px] font-black text-brand uppercase tracking-widest ml-1">Guidance Tone</label>
                        <div class="grid grid-cols-2 gap-2">
                           <div onclick="setStudioTone('calm', this)" class="tone-card active p-4 rounded-xl border-2 border-brand/5 bg-cream/10 cursor-pointer text-center text-[9px] font-black uppercase tracking-widest">Calm</div>
                           <div onclick="setStudioTone('direct', this)" class="tone-card p-4 rounded-xl border-2 border-brand/5 bg-cream/10 cursor-pointer text-center text-[9px] font-black uppercase tracking-widest">Direct</div>
                           <div onclick="setStudioTone('poetic', this)" class="tone-card p-4 rounded-xl border-2 border-brand/5 bg-cream/10 cursor-pointer text-center text-[9px] font-black uppercase tracking-widest">Poetic</div>
                           <div onclick="setStudioTone('scholarly', this)" class="tone-card p-4 rounded-xl border-2 border-brand/5 bg-cream/10 cursor-pointer text-center text-[9px] font-black uppercase tracking-widest">Scholarly</div>
                        </div>
                    </div>
                </div>

                <!-- Craft Action -->
                <div class="pt-4">
                    <button type="button" id="btnCraftCaption" onclick="generateAICaption()" class="w-full py-6 bg-brand text-white rounded-[2rem] font-black text-xs uppercase tracking-widest shadow-xl shadow-brand/20 hover:scale-[1.01] transition-all flex items-center justify-center gap-3 group">
                        <span id="craftIcon">✨</span>
                        <span id="craftText">Craft Cinematic Caption</span>
                    </button>
                </div>

                <!-- Caption Result area -->
                <div id="captionResultArea" class="hidden animate-in fade-in slide-in-from-top-4 duration-500 space-y-4">
                    <div class="flex justify-between items-center ml-1">
                        <label class="text-[9px] font-black text-brand uppercase tracking-widest">Generated Message</label>
                        <button type="button" onclick="generateAICaption()" class="text-[8px] font-bold text-accent uppercase tracking-widest hover:underline">Regenerate</button>
                    </div>
                    <textarea id="studioCaption" name="caption" class="w-full bg-white border border-brand/10 rounded-[2.5rem] p-10 text-sm font-medium text-brand min-h-[220px] outline-none focus:border-brand/30 transition-all shadow-xl leading-relaxed custom-scrollbar" oninput="invalidateQuoteCard()"></textarea>
                    
                    <div class="flex justify-end pt-4">
                       <button type="button" onclick="switchStudioSection(2)" class="px-10 py-5 bg-brand text-white rounded-2xl font-bold text-[11px] uppercase tracking-widest hover:bg-brand-hover transition-all shadow-xl shadow-brand/20">The Vision &rarr;</button>
                    </div>
                </div>
            </div>
          </div>

          <!-- PHASE 2: THE VISION (Quote Card) -->
          <div id="studioSection2" class="studio-section hidden space-y-10 animate-in slide-in-from-right-8 duration-500">
            <div>
              <label class="text-[9px] font-bold uppercase tracking-[0.3em] text-accent">Studio Phase 02</label>
              <h4 class="text-3xl font-bold text-brand italic">Visualize the Wisdom</h4>
              <p class="text-xs text-text-muted mt-2 font-medium">Transform your message into a high-impact cinematic visual.</p>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-10">
                <!-- Style Selector -->
                <div class="space-y-8">
                    <!-- MODE TOGGLE -->
                    <div class="flex p-1.5 bg-brand/[0.03] rounded-2xl border border-brand/5 gap-1">
                        <button type="button" id="btnModePreset" onclick="switchStudioMode('preset')" class="flex-1 py-3 px-4 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all bg-brand text-white shadow-lg shadow-brand/20">Sabeel Presets</button>
                        <button type="button" id="btnModeCustom" onclick="switchStudioMode('custom')" class="flex-1 py-3 px-4 rounded-xl text-[9px] font-black uppercase tracking-widest transition-all bg-brand/5 text-brand">Prophetic Vision</button>
                    </div>

                    <div id="presetModeContainer" class="space-y-6 animate-in fade-in duration-300">
                        <label class="text-[9px] font-black text-brand uppercase tracking-widest ml-1 opacity-60">Choose Your Spiritual Atmosphere</label>
                        <div class="grid grid-cols-2 gap-3">

                            <!-- Qur'an -->
                            <div onclick="setStudioStyle('quran', this)" class="style-card active p-5 rounded-2xl border-2 border-brand/5 bg-cream/10 cursor-pointer transition-all hover:bg-brand/[0.02] text-center space-y-3 group">
                               <div class="w-10 h-10 rounded-xl bg-brand/5 flex items-center justify-center text-brand mx-auto group-[.active]:bg-brand group-[.active]:text-white transition-all">
                                   <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                               </div>
                               <div class="text-[9px] font-black text-brand uppercase tracking-widest">Qur'an</div>
                               <div class="text-[7px] text-brand/40 font-medium">Sacred Emerald</div>
                            </div>

                            <!-- Fajr -->
                            <div onclick="setStudioStyle('fajr', this)" class="style-card p-5 rounded-2xl border-2 border-brand/5 bg-cream/10 cursor-pointer transition-all hover:bg-brand/[0.02] text-center space-y-3 group">
                               <div class="w-10 h-10 rounded-xl bg-brand/5 flex items-center justify-center text-brand mx-auto group-[.active]:bg-brand group-[.active]:text-white transition-all">
                                   <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 3v1m0 16v1M4.22 4.22l.707.707M18.364 18.364l.707.707M1 12h1m20 0h1M4.22 19.78l.707-.707M18.364 5.636l.707-.707M12 8a4 4 0 100 8 4 4 0 000-8z" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"/></svg>
                               </div>
                               <div class="text-[9px] font-black text-brand uppercase tracking-widest">Fajr</div>
                               <div class="text-[7px] text-brand/40 font-medium">Pre-Dawn Navy</div>
                            </div>

                            <!-- Scholar -->
                            <div onclick="setStudioStyle('scholar', this)" class="style-card p-5 rounded-2xl border-2 border-brand/5 bg-cream/10 cursor-pointer transition-all hover:bg-brand/[0.02] text-center space-y-3 group">
                               <div class="w-10 h-10 rounded-xl bg-brand/5 flex items-center justify-center text-brand mx-auto group-[.active]:bg-brand group-[.active]:text-white transition-all">
                                   <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>
                               </div>
                               <div class="text-[9px] font-black text-brand uppercase tracking-widest">Scholar</div>
                               <div class="text-[7px] text-brand/40 font-medium">Old Parchment</div>
                            </div>

                            <!-- Madinah -->
                            <div onclick="setStudioStyle('madinah', this)" class="style-card p-5 rounded-2xl border-2 border-brand/5 bg-cream/10 cursor-pointer transition-all hover:bg-brand/[0.02] text-center space-y-3 group">
                               <div class="w-10 h-10 rounded-xl bg-brand/5 flex items-center justify-center text-brand mx-auto group-[.active]:bg-brand group-[.active]:text-white transition-all">
                                   <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M8 14v3m4-3v3m4-3v3M3 21h18M3 10h18M3 7l9-4 9 4M4 10h16v11H4V10z" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"/></svg>
                               </div>
                               <div class="text-[9px] font-black text-brand uppercase tracking-widest">Madinah</div>
                               <div class="text-[7px] text-brand/40 font-medium">Warm Amber Gold</div>
                            </div>

                            <!-- Kaaba -->
                            <div onclick="setStudioStyle('kaaba', this)" class="style-card p-5 rounded-2xl border-2 border-brand/5 bg-cream/10 cursor-pointer transition-all hover:bg-brand/[0.02] text-center space-y-3 group">
                               <div class="w-10 h-10 rounded-xl bg-brand/5 flex items-center justify-center text-brand mx-auto group-[.active]:bg-brand group-[.active]:text-white transition-all">
                                   <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="1" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 9h18" stroke-width="1.5" stroke-linecap="round"/></svg>
                               </div>
                               <div class="text-[9px] font-black text-brand uppercase tracking-widest">Kaaba</div>
                               <div class="text-[7px] text-brand/40 font-medium">Sacred Black</div>
                            </div>

                            <!-- Laylul Qadr -->
                            <div onclick="setStudioStyle('laylulqadr', this)" class="style-card p-5 rounded-2xl border-2 border-brand/5 bg-cream/10 cursor-pointer transition-all hover:bg-brand/[0.02] text-center space-y-3 group">
                               <div class="w-10 h-10 rounded-xl bg-brand/5 flex items-center justify-center text-brand mx-auto group-[.active]:bg-brand group-[.active]:text-white transition-all">
                                   <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/><path d="M12 3l1 2m-1-2l-1 2M17 6l-1 2m1-2l1 2" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"/></svg>
                               </div>
                               <div class="text-[9px] font-black text-brand uppercase tracking-widest">Laylul Qadr</div>
                               <div class="text-[7px] text-brand/40 font-medium">Night of Power</div>
                            </div>

                        </div>
                    </div>

                    <div id="customModeContainer" class="hidden space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
                        <div class="space-y-2">
                            <label class="text-[9px] font-black text-brand uppercase tracking-widest ml-1 opacity-60">Describe Your Card</label>
                            <textarea id="studioVisualPrompt"
                                placeholder="e.g. black marble with gold borders and a cinematic center light..."
                                class="w-full bg-white border border-brand/10 rounded-3xl p-6 text-sm font-medium text-brand outline-none focus:border-brand/40 placeholder:text-brand/20 transition-all resize-none h-36 shadow-sm custom-scrollbar" oninput="invalidateQuoteCard()"></textarea>
                            <!-- Inline validation error -->
                            <p id="visualPromptError" class="hidden text-[9px] font-black text-red-500 uppercase tracking-widest ml-1">
                                Please describe your card before generating.
                            </p>
                            <p class="text-[8px] font-bold text-text-muted/40 uppercase tracking-widest leading-loose ml-1">
                                Try: marble &bull; emerald forest &bull; navy sky &bull; parchment &bull; moonlit &bull; gold corners
                            </p>
                        </div>
                    </div>

                    <button type="button" id="btnGenerateCard" onclick="generateQuoteCard()" class="w-full py-6 bg-brand text-white rounded-[2rem] font-black text-xs uppercase tracking-widest shadow-xl shadow-brand/20 hover:scale-[1.01] transition-all">
                        Generate Visual
                    </button>
                </div>

                <!-- Card Preview -->
                <div class="flex flex-col items-center gap-6">
                    <div id="cardPreviewContainer" class="w-full max-w-[340px] aspect-square bg-cream rounded-[3rem] border-8 border-brand/5 overflow-hidden relative shadow-2xl flex items-center justify-center transition-all">
                        <img id="quoteCardPreview" class="hidden w-full h-full object-cover">
                        <div id="cardLoader" class="flex flex-col items-center gap-4 text-brand/20">
                            <div class="w-12 h-12 rounded-full border-4 border-t-brand animate-spin"></div>
                            <span class="text-[9px] font-black uppercase tracking-widest">Awaiting Creation</span>
                        </div>
                        <!-- Out of sync warning -->
                        <div id="outOfSyncBanner" class="hidden absolute top-0 inset-x-0 bg-amber-500/90 backdrop-blur-md p-4 flex flex-col items-center gap-1 text-white animate-in slide-in-from-top-full">
                           <span class="text-[8px] font-black uppercase tracking-widest">Caption out of sync</span>
                           <span class="text-[7px] font-bold text-white/80 text-center leading-tight">Your card no longer matches the latest caption.</span>
                        </div>
                    </div>

                    <div id="cardActions" class="hidden flex gap-3 text-brand">
                        <button type="button" onclick="generateQuoteCard()" class="px-5 py-3 border border-brand/10 rounded-xl text-[9px] font-bold uppercase tracking-widest hover:bg-brand/5 transition-all">Refine Visual</button>
                        <button type="button" onclick="switchStudioSection(3)" class="px-8 py-3 bg-brand text-white rounded-xl text-[9px] font-black uppercase tracking-widest shadow-lg shadow-brand/20 hover:scale-[1.02] transition-all">Use This Visual</button>
                    </div>
                    <!-- Custom prompt applied badge -->
                    <div id="customPromptBadge" class="hidden flex items-center gap-2 px-4 py-2 bg-brand/8 border border-brand/15 rounded-full">
                        <span class="text-brand text-[9px]">✦</span>
                        <span class="text-[8px] font-black text-brand uppercase tracking-widest">Generated from your description</span>
                    </div>
                </div>
            </div>

            <div class="pt-8 border-t border-brand/5 flex justify-between">
               <button type="button" onclick="switchStudioSection(1)" class="px-8 py-4 text-text-muted hover:text-brand font-bold text-[10px] uppercase tracking-widest transition-all">&larr; The Spark</button>
            </div>
          </div>

          <!-- PHASE 3: THE PRESENCE (Configuration) -->
          <div id="studioSection3" class="studio-section hidden space-y-12 animate-in slide-in-from-right-8 duration-500">
            <div>
              <label class="text-[9px] font-bold uppercase tracking-[0.3em] text-accent">Studio Phase 03</label>
              <h4 class="text-3xl font-bold text-brand italic">Define the Presence</h4>
              <p class="text-xs text-text-muted mt-2 font-medium">Configure your target workspace and activation parameters.</p>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-10">
                <div class="space-y-6 bg-brand/[0.02] p-10 rounded-[2.5rem] border border-brand/5">
                    <div class="space-y-4">
                        <label class="text-[9px] font-black text-brand uppercase tracking-widest ml-1">Target Account</label>
                        <div class="relative group">
                            <select name="ig_account_id" id="studioAccount" class="w-full bg-white border border-brand/10 rounded-2xl px-6 py-5 text-sm font-bold text-brand outline-none shadow-sm transition-all hover:bg-brand/5 appearance-none focus:border-brand/30">
                                {account_options}
                            </select>
                            <div class="absolute right-6 top-1/2 -translate-y-1/2 pointer-events-none text-brand/20 group-hover:text-brand transition-colors">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M19 9l-7 7-7-7" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
                            </div>
                        </div>
                    </div>
                    <div class="space-y-2">
                        <label class="text-[9px] font-black text-brand uppercase tracking-widest ml-1">Activation Time</label>
                        <input type="datetime-local" id="studioSchedule" name="scheduled_time" class="w-full bg-white border border-brand/10 rounded-2xl px-6 py-5 text-sm font-bold text-brand outline-none shadow-sm focus:border-brand/30">
                    </div>
                </div>

                <div class="flex flex-col justify-center gap-4 p-8 bg-cream/30 rounded-3xl border border-brand/5">
                    <div class="flex items-center gap-4 text-emerald-600">
                        <div class="w-8 h-8 rounded-full bg-emerald-50 flex items-center justify-center"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg></div>
                        <span class="text-[10px] font-black uppercase tracking-widest">Message Integrity Valid</span>
                    </div>
                    <div class="flex items-center gap-4 text-emerald-600">
                        <div class="w-8 h-8 rounded-full bg-emerald-50 flex items-center justify-center"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round" stroke-width="3"/></svg></div>
                        <span class="text-[10px] font-black uppercase tracking-widest">Visual Asset Ready</span>
                    </div>
                </div>
            </div>

            <div class="pt-8 border-t border-brand/5 flex justify-between">
               <button type="button" onclick="switchStudioSection(2)" class="px-8 py-4 text-text-muted hover:text-brand font-bold text-[10px] uppercase tracking-widest transition-all">&larr; The Vision</button>
               <button type="button" onclick="switchStudioSection(4)" class="px-10 py-5 bg-brand text-white rounded-2xl font-bold text-[11px] uppercase tracking-widest hover:bg-brand-hover transition-all shadow-xl shadow-brand/20">Final Review &rarr;</button>
            </div>
          </div>

          <!-- PHASE 4: THE MANIFEST (Final Review) -->
          <div id="studioSection4" class="studio-section hidden space-y-12 animate-in slide-in-from-right-8 duration-500">
            <div class="flex justify-between items-end">
              <div>
                <label class="text-[9px] font-bold uppercase tracking-[0.3em] text-accent">Studio Phase 04</label>
                <h4 class="text-3xl font-bold text-brand italic">The Manifest</h4>
                <p class="text-xs text-text-muted mt-2 font-medium">Review your spiritual architecture before manifestation.</p>
              </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-10">
               <!-- Left: Final Preview -->
               <div class="flex justify-center">
                  <div class="w-full max-w-[320px] aspect-square bg-cream rounded-[3rem] border-8 border-brand/5 overflow-hidden relative shadow-2xl">
                     <img id="finalPreviewImage" class="w-full h-full object-cover">
                  </div>
               </div>

               <!-- Right: Final Actions -->
               <div class="space-y-8 bg-brand/[0.02] p-10 rounded-[2.5rem] border border-brand/5 flex flex-col justify-between">
                  <div class="space-y-6">
                      <div class="space-y-1">
                          <label class="text-[8px] font-black text-brand uppercase tracking-widest opacity-60">Manifesting to</label>
                          <div id="manifestAccount" class="text-xs font-bold text-brand uppercase">@username</div>
                      </div>
                      <div class="space-y-1">
                          <label class="text-[8px] font-black text-brand uppercase tracking-widest opacity-60">Activation</label>
                          <div id="manifestTime" class="text-xs font-bold text-brand uppercase">Tomorrow, 09:00 AM</div>
                      </div>
                      <div class="pt-4 space-y-2">
                        <label class="text-[8px] font-black text-brand uppercase tracking-widest opacity-60">Message Summary</label>
                        <p id="manifestCaption" class="text-[11px] text-text-muted font-medium italic line-clamp-4 leading-relaxed"></p>
                      </div>
                  </div>

                  <div class="space-y-4 pt-6">
                      <button type="submit" id="studioSubmitBtn" class="w-full py-6 bg-brand text-white rounded-3xl font-black text-[12px] uppercase tracking-[0.3em] shadow-2xl shadow-brand/20 hover:bg-brand-hover active:scale-[0.98] transition-all">
                         Schedule Manifestation
                      </button>
                      <button type="button" onclick="switchStudioSection(3)" class="w-full text-center py-2 text-[9px] font-bold text-text-muted uppercase tracking-widest hover:text-brand transition-colors">&larr; Adjust Details</button>
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
        .dir-rtl {{ direction: rtl; unicode-bidi: bidi-override; }}
        .font-serif {{ font-family: 'Amiri', 'Traditional Arabic', serif; }}
        .hide-scrollbar::-webkit-scrollbar {{ display: none; }}
        .hide-scrollbar {{ -ms-overflow-style: none; scrollbar-width: none; }}
    </style>
    
    <div class="space-y-8">
      <div class="flex justify-between items-end">
        <div>
          <h1 class="text-3xl font-bold text-brand tracking-tight">Library</h1>
          <p class="text-[10px] font-bold text-text-muted uppercase tracking-[0.3em]">Knowledge Foundation</p>
        </div>
        <div class="flex gap-4">
          <button onclick="openEntryModal()" class="px-8 py-4 bg-brand rounded-xl font-bold text-[11px] uppercase tracking-widest text-white shadow-xl shadow-brand/20 hover:bg-brand-hover transition-all flex items-center gap-3">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
            Add Wisdom
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
                <span id="sabeelDefaultsLabel" class="hidden text-[8px] font-bold text-accent uppercase tracking-widest mt-1">Sabeel Foundation</span>
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
              <h3 class="hidden md:block text-[10px] font-bold uppercase tracking-[0.2em] text-text-muted shrink-0">Guidance Library</h3>
              <div class="relative w-full md:max-w-md group">
                <input type="text" id="entrySearch" oninput="debounceEntryQuery()" placeholder="Search your wisdom base..." class="w-full bg-cream/50 border border-brand/10 rounded-2xl px-6 py-3.5 text-[11px] font-bold text-brand outline-none focus:border-brand/30 focus:bg-white focus:shadow-lg focus:shadow-brand/5 transition-all placeholder:text-brand/20">
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
          const modal = document.getElementById('libraryPickerModal');
          const context = modal ? modal.dataset.context : '';

          if (context === 'composer') {
              if (entry.media_url) {
                  const preview = document.getElementById('selectedMediaPreview');
                  const img = document.getElementById('libPreviewImg');
                  const hidden = document.getElementById('studioLibraryItemId');
                  if (img) img.src = entry.media_url;
                  if (preview) preview.classList.remove('hidden');
                  if (hidden) hidden.value = entry.id;
                  
                  const checkVisual = document.getElementById('checkVisual');
                  if (checkVisual) {
                      checkVisual.classList.remove('bg-brand/5', 'text-brand/20');
                      checkVisual.classList.add('bg-emerald-50', 'text-emerald-600');
                      checkVisual.parentElement.classList.remove('opacity-30');
                  }
              } else {
                  alert("This library entry has no image. Please select an entry with a visual asset.");
                  return;
              }
          } else {
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
