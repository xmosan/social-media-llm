    // --- ACCOUNT SWITCHER LOGIC ---
    window.toggleAccountSwitcher = function(ev) {
        const dropdown = document.getElementById('accountSwitcherDropdown');
        if (dropdown) {
            dropdown.classList.toggle('hidden');
            // Force high z-index on open
            if (!dropdown.classList.contains('hidden')) {
                dropdown.style.display = 'block';
                dropdown.style.zIndex = '99999';
            } else {
                dropdown.style.display = 'none';
            }
        }
    };

    window.setActiveAccount = async function(accountId) {
        if (!accountId) return;
        try {
            const res = await fetch(`/ig-accounts/set-active/${accountId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            if (res.ok) {
                window.location.reload();
            } else {
                alert('Connection to Platform failed. Re-syncing...');
                window.location.reload();
            }
        } catch (e) {
            console.error('Account Switch Critical Failure:', e);
        }
    };

    // Handle clicks outside the switcher
    document.addEventListener('mousedown', (e) => {
        const dropdown = document.getElementById('accountSwitcherDropdown');
        const trigger = id => document.getElementById(id);
        const root = trigger('accountSwitcherRoot');
        if (dropdown && !dropdown.classList.contains('hidden')) {
            if (root && !root.contains(e.target)) {
                dropdown.classList.add('hidden');
                dropdown.style.display = 'none';
            }
        }
    });

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

    window.resetStudioSession = function() {
        // Reset Logic state
        currentQuoteCardUrl = null;
        isQuoteCardOutOfDate = false;
        studioCreationMode = 'preset';
        studioEngine = 'dalle';
        studioGlossy = false;
        selectedAyahId = null;
        studioCardMessage = null;
        studioCaptionMessage = null;
        window.selectedAyahMetadata = null;

        // Reset Physical Elements
        const setVal = (id, v) => { const el = document.getElementById(id); if(el) el.value = v; };
        const hide = (id) => { const el = document.getElementById(id); if(el) el.classList.add('hidden'); };

        setVal('studioTopic', '');
        setVal('editEyebrow', '');
        setVal('editHeadline', '');
        setVal('editSupporting', '');
        setVal('studioCaption', '');
        setVal('finalMediaUrl', '');
        setVal('studioVisualPrompt', '');
        
        hide('quranSearchResults');
        hide('selectedAyahBadge');
        hide('cardMessageWorkspace');
        hide('captionResultArea');
        hide('cardActions');
        hide('outOfSyncBanner');

        const preview = document.getElementById('quoteCardPreview');
        if (preview) { preview.src = ''; preview.classList.add('hidden'); }
    };

    function openNewPostModal() {
        window.resetStudioSession();
        document.getElementById('newPostModal').classList.remove('hidden');
        switchStudioSection(1);
    }

    function closeNewPostModal() {
        document.getElementById('newPostModal').classList.add('hidden');
        window.resetStudioSession();
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

    window.selectedAyahMetadata = null;
    function selectAyah(id, title, text) {
        selectedAyahId = id;
        window.selectedAyahMetadata = { reference: title, translation_text: text, id: id };
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
            const payload = {
                source_type: selectedAyahId ? 'quran' : 'manual',
                source_payload: selectedAyahId ? window.selectedAyahMetadata : { text: topic, reference: topic },
                tone: tone,
                intent: intention
            };

            const res = await fetch('/api/studio/generate-card-message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
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

            const res = await fetch('/api/studio/generate-visual', {
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
            const payload = {
                source_type: selectedAyahId ? 'quran' : 'manual',
                source_payload: selectedAyahId ? window.selectedAyahMetadata : { text: studioCardMessage.headline },
                topic: document.getElementById('studioTopic').value,
                tone: document.getElementById('studioTone').value,
                intent: document.getElementById('studioIntent').value
            };

            const res = await fetch('/api/studio/generate-caption', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
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

        const accountId = document.getElementById('studioAccount').value;
        const topicVal = document.getElementById('studioTopic').value;

        const reqPayload = {
            ig_account_id: parseInt(accountId, 10),
            visual_mode: 'quote_card',
            source_type: selectedAyahId ? 'quran' : 'manual',
            source_reference: selectedAyahId && window.selectedAyahMetadata ? window.selectedAyahMetadata.reference : topicVal,
            source_metadata: selectedAyahId ? window.selectedAyahMetadata : null,
            topic: topicVal,
            card_message: studioCardMessage,
            caption_message: studioCaptionMessage,
            media_url: document.getElementById('finalMediaUrl')?.value || currentQuoteCardUrl,
            intent_type: document.getElementById('studioIntent').value,
            visual_style: studioCreationMode === 'custom' ? 'custom' : document.getElementById('studioStyle').value
        };

        try {
            const res = await fetch('/api/studio/create-post', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(reqPayload)
            });
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

    // --- PHASE 2: AUTOMATION V2 UI LOGIC ---
    let v2DnaPresets = [];

    async function loadStyleDnaPresets() {
        if (v2DnaPresets.length > 0) return;
        try {
            const res = await fetch('/automations/meta/style-presets');
            const data = await res.json();
            v2DnaPresets = data.presets || [];
            
            const container = document.getElementById('autoV2StyleDNAContainer');
            if (container) {
                container.innerHTML = v2DnaPresets.map(p => `
                    <div onclick="selectV2StyleDna('${p.id || ''}', this)" class="auto-style-card cursor-pointer bg-cream/30 border border-brand/5 rounded-2xl p-4 hover:border-brand/30 hover:shadow-lg transition-all flex flex-col">
                        <div class="text-[10px] uppercase font-black tracking-widest text-brand mb-2">${p.label}</div>
                        <div class="text-[9px] text-text-muted font-bold leading-tight">Visual: <span class="italic text-brand/70">${p.atmosphere}</span></div>
                        <div class="text-[9px] text-text-muted font-bold leading-tight mt-1">Tone: <span class="italic text-brand/70">${p.tone_style}</span></div>
                    </div>
                `).join('');
                if (v2DnaPresets.length > 0 && !document.getElementById('autoV2StyleDNAInput').value) {
                    setTimeout(() => selectV2StyleDna(v2DnaPresets[0].id || '', container.children[0]), 50);
                }
            }
        } catch (e) {
            console.error('Failed to load style DNA presets: ', e);
        }
    }

    window.updateAutoV2VisualPreview = function(dnaId) {
        const swatches = {
            'dark_sacred': { name: 'Dark Sacred', color: 'bg-[#0F172A]', secondary: 'border-amber-400/50', atmosphere: 'Sacred & Deep' },
            'emerald_calm': { name: 'Emerald Calm', color: 'bg-emerald-900', secondary: 'border-emerald-400/30', atmosphere: 'Peaceful & Soft' },
            'celestial_night': { name: 'Celestial Night', color: 'bg-indigo-950', secondary: 'border-blue-400/40', atmosphere: 'Deep & Celestial' },
            'warm_parchment': { name: 'Warm Parchment', color: 'bg-orange-50', secondary: 'border-brand/10', atmosphere: 'Classic & Scholarly' }
        };
        const active = swatches[dnaId] || swatches['dark_sacred'];
        const swatchEl = document.getElementById('visualStyleSwatch');
        const nameEl = document.getElementById('visualStyleName');
        const previewBlock = document.getElementById('autoV2VisualPreview');
        
        if (swatchEl && nameEl) {
            swatchEl.className = `w-16 h-16 rounded-xl shadow-inner border-2 ${active.color} ${active.secondary}`;
            nameEl.innerText = active.name;
            previewBlock.classList.remove('hidden');
        }
    };

    window.updateAutoV2Summary = function() {
        const cadence = document.getElementById('autoV2CadenceInput')?.value || 'daily';
        const mode = document.getElementById('autoV2ApprovalModeInput')?.value || 'auto_approve';
        const timeInput = document.querySelector('input[name="post_time_local"]')?.value || '09:00';
        
        const cadenceText = document.getElementById('summaryCadenceText');
        const modeText = document.getElementById('summaryModeText');
        const timeText = document.getElementById('summaryTimeText');
        
        if (cadenceText) cadenceText.innerText = cadence === 'daily' ? 'Daily Stream' : 'Weekly Momentum';
        if (modeText) modeText.innerText = mode === 'auto_approve' ? 'Auto-Pilot (Direct Launch)' : 'Drafting Mode (Requires Approval)';
        
        if (timeText) {
            try {
                const [h, m] = timeInput.split(':');
                const hh = parseInt(h);
                const period = hh >= 12 ? 'PM' : 'AM';
                const displayH = hh % 12 || 12;
                timeText.innerText = `${displayH}:${m} ${period}`;
            } catch(e) { timeText.innerText = timeInput; }
        }
    };

    window.selectV2StyleDna = function(id, el) {
        const input = document.getElementById('autoV2StyleDNAInput');
        if(input) input.value = id;
        document.querySelectorAll('.auto-style-card').forEach(c => {
            c.classList.remove('ring-2', 'ring-brand', 'bg-brand/5', 'shadow-xl');
        });
        if(el) el.classList.add('ring-2', 'ring-brand', 'bg-brand/5', 'shadow-xl');
        window.updateAutoV2VisualPreview(id);
    };

    window.selectApprovalMode = function(mode, el) {
        const input = document.getElementById('autoV2ApprovalModeInput');
        if(input) input.value = mode;
        document.querySelectorAll('.approval-card').forEach(c => {
            c.classList.remove('ring-2', 'ring-brand', 'shadow-xl');
        });
        if(el) el.classList.add('ring-2', 'ring-brand', 'shadow-xl');
        window.updateAutoV2Summary();
    };

    window.selectCadenceMode = function(mode, el) {
        const input = document.getElementById('autoV2CadenceInput');
        if(input) input.value = mode;
        document.querySelectorAll('.cadence-card').forEach(c => {
            c.classList.remove('ring-2', 'ring-brand', 'shadow-xl');
        });
        if(el) el.classList.add('ring-2', 'ring-brand', 'shadow-xl');
        window.updateAutoV2Summary();
    };

    window.showNewAutoModal = async function() {
        const modal = document.getElementById('newAutoModalV2');
        if (modal) {
            modal.classList.remove('hidden');
            await loadStyleDnaPresets();
            document.getElementById('autoV2Form').dataset.editId = "";
            document.getElementById('autoV2Form').reset();
            window.updateAutoV2Summary();
        }
    };

    window.testAutoV2Preview = async function() {
        const btn = document.getElementById('btnPreviewAutoV2');
        const form = document.getElementById('autoV2Form');
        const topic = form.topic_prompt.value;
        if (!topic) { alert("Please provide a CORE TOPIC before testing the engine."); return; }
        
        btn.innerHTML = '<svg class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>';
        btn.disabled = true;
        
        const container = document.getElementById('autoV2PreviewContainer');
        const content = document.getElementById('autoV2PreviewContent');
        
        try {
            let styleStr = 'islamic_reminder';
            const selectedDnaId = document.getElementById('autoV2StyleDNAInput').value;
            if(selectedDnaId) {
                 const match = v2DnaPresets.find(p => p.id == selectedDnaId);
                 if(match) styleStr = match.id || match.label;
            }

            const reqUrl = `/automations/debug/llm-test?topic=${encodeURIComponent(topic)}&style=${encodeURIComponent(styleStr)}`;
            const responses = await Promise.all([
                fetch(reqUrl).then(r => r.json()),
                fetch(reqUrl).then(r => r.json())
            ]);
            
            container.classList.remove('hidden');
            content.innerHTML = responses.map((data, i) => {
                const type = data.grounding?.item_type || 'reflection';
                const badgeColor = type === 'quran' ? 'bg-emerald-500' : (type === 'hadith' ? 'bg-indigo-500' : 'bg-brand/40');
                const typeLabel = type.charAt(0).toUpperCase() + type.slice(1);
                
                return `
                    <div class="bg-white border border-brand/5 rounded-2xl p-6 shadow-sm hover:shadow-md transition-all flex flex-col space-y-4">
                        <div class="flex items-center justify-between">
                            <div class="flex items-center gap-2">
                                <span class="w-1.5 h-1.5 rounded-full ${badgeColor}"></span>
                                <span class="text-[9px] font-black text-brand uppercase tracking-widest">${typeLabel} Based</span>
                            </div>
                            <span class="text-[8px] font-bold text-text-muted uppercase tracking-tighter italic">Sample ${i+1}</span>
                        </div>
                        
                        <div class="space-y-2">
                             <div class="text-[10px] font-black text-brand italic leading-tight">${data.grounding?.source || 'Perspective Reflection'}</div>
                             <p class="text-[11px] text-brand/80 font-medium leading-relaxed italic border-l-2 border-brand/5 pl-3">
                                ${data.caption.split('\\n')[0]}
                             </p>
                             <div class="text-[10px] text-text-muted leading-relaxed line-clamp-3 opacity-60">
                                ${data.caption.split('\\n').slice(1).join(' ')}
                             </div>
                        </div>

                        ${data.hashtags ? `
                        <div class="pt-2 flex flex-wrap gap-1">
                            ${data.hashtags.slice(0, 3).map(h => `<span class="text-[8px] font-bold text-accent uppercase tracking-tighter">#${h}</span>`).join('')}
                        </div>` : ''}
                    </div>
                `;
            }).join('');
            
            // Smoothly scroll to preview
            container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

        } catch(e) {
            alert('Preview Engine disconnected: ' + e.message);
        } finally {
            btn.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg><span class="text-[10px]">Preview Samples</span>';
            btn.disabled = false;
        }
    };
    
    window.closeNewAutoModal = function() {
        const modal = document.getElementById('newAutoModalV2');
        if (modal) modal.classList.add('hidden');
    };

    window.submitNewAutoV2 = async function(event) {
        event.preventDefault();
        const btn = document.getElementById('btnSubmitAutoV2');
        const original = btn.innerText;
        btn.disabled = true;
        btn.innerText = 'Initializing Plan...';

        const form = event.target;
        const payload = {
            name: form.name.value,
            topic_prompt: form.topic_prompt.value,
            style_dna_id: form.style_dna_id.value ? parseInt(form.style_dna_id.value) : null,
            automation_version: 2,
            approval_mode: document.getElementById('autoV2ApprovalModeInput') ? document.getElementById('autoV2ApprovalModeInput').value : 'auto_approve',
            cadence: document.getElementById('autoV2CadenceInput') ? document.getElementById('autoV2CadenceInput').value : 'daily',
            post_time_local: form.post_time_local.value,
            posts_per_day: form.posts_per_day ? parseInt(form.posts_per_day.value) : 1,
            post_spacing_hours: form.post_spacing_hours ? parseInt(form.post_spacing_hours.value) : 4
        };

        if (!form.dataset.editId) {
            payload.ig_account_id = parseInt(document.getElementById('studioAccount') ? document.getElementById('studioAccount').value : form.ig_account_id_hidden.value);
            payload.posting_mode = 'schedule';
            payload.enabled = true;
        }

        try {
            const endpoint = form.dataset.editId ? `/automations/${form.dataset.editId}` : `/automations`;
            const method = form.dataset.editId ? 'PATCH' : 'POST';
            const res = await fetch(endpoint, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                window.location.reload();
            } else {
                const err = await res.json();
                alert('Plan Initialization Failed: ' + (err.detail || 'Unknown error'));
            }
        } catch(e) {
            alert('Request Failed: ' + e);
        } finally {
            btn.innerText = original;
            btn.disabled = false;
        }
    };

    window.showEditModal = async function(data) {
        await loadStyleDnaPresets();
        const modal = document.getElementById('newAutoModalV2');
        if (!modal) return;
        
        const form = document.getElementById('autoV2Form');
        form.dataset.editId = data.id;
        
        form.name.value = data.name || '';
        if(form.ig_account_id_hidden) form.ig_account_id_hidden.value = data.ig_account_id || '';
        form.topic_prompt.value = data.topic_prompt || '';
        form.post_time_local.value = data.post_time_local || '';
        if(form.posts_per_day) form.posts_per_day.value = data.posts_per_day || 1;
        if(form.post_spacing_hours) form.post_spacing_hours.value = data.post_spacing_hours || 4;
        
        if (data.style_dna_id) {
            const input = document.getElementById('autoV2StyleDNAInput');
            if(input) input.value = data.style_dna_id;
            // Best effort visual selection
            setTimeout(() => {
                const container = document.getElementById('autoV2StyleDNAContainer');
                if(container) {
                    const cards = container.querySelectorAll('.auto-style-card');
                    const index = v2DnaPresets.findIndex(p => p.id == data.style_dna_id);
                    if(index >= 0 && cards[index]) selectV2StyleDna(data.style_dna_id, cards[index]);
                }
            }, 100);
        }

        if (data.approval_mode) {
            const modeInput = document.getElementById('autoV2ApprovalModeInput');
            if (modeInput) modeInput.value = data.approval_mode;
            setTimeout(() => {
                const cards = document.querySelectorAll('.approval-card');
                if (data.approval_mode === 'needs_manual_approve') {
                    selectApprovalMode('needs_manual_approve', cards[0]);
                } else {
                    selectApprovalMode('auto_approve', cards[1]);
                }
            }, 100);
        }

        if (data.cadence) {
            const cadInput = document.getElementById('autoV2CadenceInput');
            if (cadInput) cadInput.value = data.cadence;
            setTimeout(() => {
                const cards = document.querySelectorAll('.cadence-card');
                if (data.cadence === 'weekly') {
                    selectCadenceMode('weekly', cards[1]);
                } else {
                    selectCadenceMode('daily', cards[0]);
                }
            }, 100);
        }

        modal.classList.remove('hidden');
    };

