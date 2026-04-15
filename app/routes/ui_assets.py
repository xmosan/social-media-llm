# Shared UI Assets for Sabeel Studio
# Copyright (c) 2026 Mohammed Hassan. All rights reserved.

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
        if (stepIndex === 2 && !studioCardMessage) {
            alert("Please build your card message first.");
            return;
        }
        if (stepIndex === 4 && (!currentQuoteCardUrl || !studioCaptionMessage)) {
            alert("Please ensure your visual and caption are ready before moving to Manifest.");
            return;
        }

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
                const fullText = `${studioCaptionMessage.hook}\\n\\n${studioCaptionMessage.body}\\n\\n${studioCaptionMessage.cta}\\n\\n${studioCaptionMessage.hashtags}`;
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
                            \${accounts.map(acc => \`
                                <button type="button" onclick="setActiveAccount('\${acc.id}')" class="w-full flex items-center justify-between p-2 rounded-xl transition-all \${acc.id === active.id ? 'bg-brand/5 border border-brand/5' : 'hover:bg-brand/[0.02]'}">
                                    <div class="flex items-center gap-3">
                                        <img src="\${acc.profile_picture_url || 'https://ui-avatars.com/api/?name=' + acc.username}" class="w-8 h-8 rounded-lg">
                                        <div class="text-left">
                                            <div class="text-[10px] font-bold text-brand">@\${acc.username}</div>
                                            <div class="text-[8px] text-text-muted font-medium">\${acc.fb_page_id ? 'Instagram Business' : 'Personal'}</div>
                                        </div>
                                    </div>
                                    \${acc.id === active.id ? '<div class="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>' : ''}
                                </button>
                            \`).join('')}
                        </div>
                    </div>
                </div>\`;
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

    window.addEventListener('load', () => {
        const pending = sessionStorage.getItem('sabeel_pending_quote_item');
        if (pending) {
            try {
                const item = JSON.parse(pending);
                sessionStorage.removeItem('sabeel_pending_quote_item');
                if (typeof openNewPostModal === 'function') {
                    openNewPostModal();
                    if (item.type === 'quran_verse' || item.type === 'quran') {
                        selectAyah(item.id, item.reference, item.translation_text);
                    } else if (item.type === 'quote') {
                        const topicInput = document.getElementById('studioTopic');
                        if (topicInput) topicInput.value = item.text || item.translation_text || item.reference;
                    }
                }
            } catch (e) { console.error("Studio Bridge Failure:", e); }
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
          <div id="studioSection1" class="studio-section space-y-10 animate-in slide-in-from-right-8 duration-500">
            <div>
              <label class="text-[9px] font-bold uppercase tracking-[0.3em] text-accent">Studio Phase 1</label>
              <h4 class="text-3xl font-bold text-brand italic">Ignite the Spark</h4>
              <p class="text-xs text-text-muted mt-2 font-medium">Search the Qur'an or define a topic to build your card's central message.</p>
            </div>

            <div class="space-y-8">
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
                <div class="pt-4">
                    <button type="button" id="btnBuildMessage" onclick="buildCardMessage()" class="w-full py-6 bg-brand text-white rounded-[2rem] font-black text-xs uppercase tracking-widest shadow-xl shadow-brand/20 hover:scale-[1.01] transition-all flex items-center justify-center gap-3">
                        <span class="btn-icon">✨</span>
                        <span class="btn-text">Build Quote Card Message</span>
                    </button>
                </div>
                <div id="cardMessageWorkspace" class="hidden animate-in fade-in slide-in-from-top-4 duration-500 space-y-6 bg-brand/[0.02] p-8 rounded-[2.5rem] border border-brand/5">
                    <div class="space-y-4">
                        <div class="space-y-2">
                            <label class="text-[8px] font-bold text-text-muted uppercase tracking-widest ml-1">Eyebrow</label>
                            <input type="text" id="editEyebrow" oninput="updateStudioCardFromUI()" class="w-full bg-white border border-brand/10 rounded-xl px-4 py-3 text-xs font-bold text-brand outline-none focus:border-brand/30">
                        </div>
                        <div class="space-y-2">
                            <label class="text-[8px] font-bold text-text-muted uppercase tracking-widest ml-1">Headline</label>
                            <textarea id="editHeadline" oninput="updateStudioCardFromUI()" class="w-full bg-white border border-brand/10 rounded-xl px-4 py-3 text-xs font-medium text-brand outline-none focus:border-brand/30 h-24 resize-none"></textarea>
                        </div>
                        <div class="space-y-2">
                            <label class="text-[8px] font-bold text-text-muted uppercase tracking-widest ml-1">Reference</label>
                            <input type="text" id="editSupporting" oninput="updateStudioCardFromUI()" class="w-full bg-white border border-brand/10 rounded-xl px-4 py-3 text-xs font-bold text-brand outline-none focus:border-brand/30">
                        </div>
                    </div>
                </div>
            </div>
          </div>
          <div id="studioSection2" class="studio-section hidden space-y-10">
             <div class="grid grid-cols-1 lg:grid-cols-2 gap-10">
                <div class="space-y-8">
                    <button type="button" id="btnGenerateCard" onclick="generateQuoteCard()" class="w-full py-6 bg-brand text-white rounded-[2rem] font-black text-xs uppercase tracking-widest shadow-xl shadow-brand/20">Generate Cinematic Visual</button>
                </div>
                <div class="flex flex-col items-center gap-6">
                    <div id="cardPreviewContainer" class="w-full max-w-[340px] aspect-square bg-cream rounded-[3rem] border-8 border-brand/5 overflow-hidden relative shadow-2xl flex items-center justify-center">
                        <img id="quoteCardPreview" class="hidden w-full h-full object-cover">
                        <div id="cardLoader" class="hidden animate-spin w-12 h-12 border-4 border-t-brand rounded-full"></div>
                    </div>
                    <div id="cardActions" class="hidden flex gap-3">
                        <button type="button" onclick="switchStudioSection(3)" class="px-8 py-3 bg-brand text-white rounded-xl text-[9px] font-black uppercase tracking-widest">Confirm Visual &rarr;</button>
                    </div>
                </div>
             </div>
          </div>
          <div id="studioSection3" class="studio-section hidden space-y-10">
                <button type="button" id="btnGenerateCaption" onclick="generateSocialCaption()" class="w-full py-6 bg-brand/5 text-brand border border-brand/10 rounded-[2rem] font-black text-xs uppercase tracking-widest hover:bg-brand/10 transition-all flex items-center justify-center gap-3">
                    <span class="btn-text">Generate Social Caption</span>
                </button>
                <div id="captionResultArea" class="hidden space-y-6">
                    <textarea id="studioCaption" name="caption" class="w-full bg-white border border-brand/10 rounded-[2.5rem] p-10 text-sm font-medium text-brand min-h-[300px] outline-none shadow-xl leading-relaxed custom-scrollbar"></textarea>
                    <div class="flex justify-end pt-4">
                       <button type="button" onclick="switchStudioSection(4)" class="px-10 py-5 bg-brand text-white rounded-2xl font-bold text-[11px] uppercase tracking-widest">Final Review &rarr;</button>
                    </div>
                </div>
          </div>
          <div id="studioSection4" class="studio-section hidden space-y-12">
               <div class="grid grid-cols-1 lg:grid-cols-2 gap-10">
                   <div class="w-full max-w-[320px] aspect-square bg-cream rounded-[3rem] border-8 border-brand/5 overflow-hidden relative shadow-2xl">
                      <img id="finalPreviewImage" class="w-full h-full object-cover">
                   </div>
                   <div class="space-y-8 bg-brand/[0.02] p-10 rounded-[2.5rem] border border-brand/5 flex flex-col justify-between">
                      <div class="space-y-6">
                          <div id="manifestAccount" class="text-xs font-bold text-brand uppercase"></div>
                          <div id="manifestTime" class="text-xs font-bold text-brand uppercase"></div>
                          <p id="manifestCaption" class="text-[11px] text-text-muted font-medium italic line-clamp-6 leading-relaxed"></p>
                      </div>
                      <button type="submit" id="studioSubmitBtn" class="w-full py-6 bg-brand text-white rounded-3xl font-black text-[12px] uppercase tracking-[0.3em] shadow-2xl shadow-brand/20">Schedule Manifestation</button>
                   </div>
               </div>
          </div>
        </div>
      </form>
    </div>
</div>
"""

APP_LAYOUT_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
  <meta name="theme-color" content="#0F3D2E" />
  <title>{title} | Sabeel Studio</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: { brand: '#0F3D2E', 'brand-hover': '#0A2D22', accent: '#C9A96E', 'text-main': '#1A1A1A', 'text-muted': '#6B6B6B', cream: '#F8F6F2' }
        }
      }
    }
  </script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root { --brand: #0F3D2E; --brand-hover: #0A2D22; --main-bg: #F8F6F2; --surface: #FFFFFF; --accent: #C9A96E; --text-main: #1A1A1A; --text-muted: #6B6B6B; --border: rgba(15, 61, 46, 0.08); }
    body { font-family: 'Inter', sans-serif; background-color: var(--main-bg); color: var(--text-main); -webkit-font-smoothing: antialiased; }
    .card { background: #FFFFFF; border: 1px solid var(--border); box-shadow: 0 2px 8px rgba(15, 61, 46, 0.04); border-radius: 12px; transition: all 150ms ease; }
    .card:hover { transform: translateY(-1px); box-shadow: 0 12px 24px rgba(15, 61, 46, 0.08); }
    .nav-link.active { color: var(--brand); border-bottom: 2px solid var(--brand); font-weight: 700; }
    .nav-link { transition: all 150ms ease; border-bottom: 2px solid transparent; color: var(--text-muted); opacity: 0.8; }
    .nav-link:hover { color: var(--brand); opacity: 1; }
  </style>
</head>
<body class="min-h-screen">
  <nav class="border-b border-brand/5 bg-white/80 backdrop-blur-md sticky top-0 z-50 hidden md:block">
    <div class="max-w-7xl mx-auto px-6 h-16 flex justify-between items-center">
      <div class="flex items-center gap-8">
        <div class="text-xl font-bold tracking-tight text-brand">Sabeel <span class="text-accent font-normal">Studio</span></div>
        <div class="hidden md:flex gap-6">
          <a href="/app" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_dashboard}">Home</a>
          <a href="/app/calendar" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_calendar}">Plan</a>
          <a href="/app/automations" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_automations}">Growth Plans</a>
          <a href="/app/library" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_library}">Knowledge Library</a>
          <a href="/app/media" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_media}">Visual Library</a>
          {admin_link}
        </div>
      </div>
      <div class="flex items-center gap-4">
        <div id="navbarAccountSwitcher" class="relative"></div>
        <button onclick="logout()" class="p-2 text-text-muted hover:text-brand transition-colors"><svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg></button>
      </div>
    </div>
  </nav>
  <main class="max-w-7xl mx-auto px-4 md:px-6 py-6 md:py-10 space-y-6 md:space-y-10 pb-24 md:pb-10">
    {content}
  </main>
  <nav class="md:hidden fixed bottom-8 left-1/2 -translate-x-1/2 w-[92%] max-w-[400px] bg-white border border-brand/10 p-2 flex justify-between items-center z-[140] shadow-2xl rounded-[2.5rem] backdrop-blur-xl bg-white/90">
    <a href="/app" class="flex-1 flex flex-col items-center gap-1 py-1 mobile-tab {active_dashboard}"><span class="text-[8px] font-bold uppercase tracking-widest">Home</span></a>
    <a href="/app/library" class="flex-1 flex flex-col items-center gap-1 py-1 mobile-tab {active_library}"><span class="text-[8px] font-bold uppercase tracking-widest">Library</span></a>
  </nav>
  <script>
    async function logout() { await fetch('/auth/logout', { method: 'POST' }); window.location.href = '/'; }
    function openNewPostModal() { document.getElementById('newPostModal').classList.remove('hidden'); }
    function closeNewPostModal() { document.getElementById('newPostModal').classList.add('hidden'); }
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
  </div>
  <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
    <div class="md:col-span-2 card p-8 border-brand/10 bg-brand/[0.02] flex flex-col justify-between group cursor-pointer" onclick="openNewPostModal()">
      <h4 class="text-xl font-bold text-brand">Craft your next reminder</h4>
      <div class="mt-8 flex items-center gap-2 text-xs font-bold text-brand uppercase tracking-widest group-hover:translate-x-2 transition-transform">Begin Your Reminder &rarr;</div>
    </div>
  </div>
</div>"""

CONNECT_INSTAGRAM_MODAL_HTML = """<div id="connectInstagramModal" class="fixed inset-0 bg-brand/10 backdrop-blur-xl z-[200] flex items-center justify-center p-6 hidden">
  <div class="glass max-w-md w-full rounded-[2.5rem] p-8 md:p-10 bg-white shadow-2xl">
    <div class="text-center space-y-6">
      <h3 class="text-2xl font-bold text-brand tracking-tighter">Meta Connection</h3>
      <button onclick="window.location.href='/auth/instagram/login'" class="w-full py-4 bg-brand rounded-2xl font-bold text-xs uppercase tracking-widest text-white">Continue to Secure Login</button>
      <button onclick="closeConnectInstagramModal()" class="w-full py-4 bg-white border border-brand/10 rounded-2xl font-bold text-xs uppercase tracking-widest text-text-muted">Maybe Later</button>
    </div>
  </div>
</div>"""
