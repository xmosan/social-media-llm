# Shared UI Assets for Sabeel Studio
# Copyright (c) 2026 Mohammed Hassan. All rights reserved.

STUDIO_SCRIPTS_JS = """
<script>
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
            // Null check root to prevent script crash if switcher isn't rendered
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
    let selectedHadithId   = null;
    let activeSourceTab    = 'quran'; // quran or hadith

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
        selectedHadithId = null;
        studioCardMessage = null;
        studioCaptionMessage = null;
        window.selectedAyahMetadata = null;
        window.selectedHadithMetadata = null;

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
        const modal = document.getElementById('newPostModal');
        if (modal) {
            modal.style.display = 'flex';
            modal.classList.remove('hidden');
        }
        switchStudioSection(1);
    }

    function closeNewPostModal() {
        const modal = document.getElementById('newPostModal');
        if (modal) {
            modal.classList.add('hidden');
            modal.style.display = 'none';
        }
        window.resetStudioSession();
    }

    function switchStudioSection(stepIndex) {
        if (stepIndex === 2 && !studioCardMessage) {
            alert("Please build your card message first.");
            return;
        }
        if (stepIndex === 4 && (!currentQuoteCardUrl || !studioCaptionMessage)) {
            alert("Please ensure your visual and caption are ready before moving to Share.");
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

        if (stepIndex === 4) prepareShare();
    }

    function switchSourceTab(tab) {
        activeSourceTab = tab;
        const qBtn = document.getElementById('tabBtnQuran');
        const hBtn = document.getElementById('tabBtnHadith');
        
        if (tab === 'quran') {
            qBtn.classList.add('bg-brand', 'text-white');
            qBtn.classList.remove('bg-brand/5', 'text-brand');
            hBtn.classList.add('bg-brand/5', 'text-brand');
            hBtn.classList.remove('bg-brand', 'text-white');
            hide('hadithSearchResults');
            
            // Clear Hadith selection when switching to Quran
            selectedHadithId = null;
            window.selectedHadithMetadata = null;
            hide('selectedHadithBadge');
            
            document.getElementById('studioTopic').placeholder = "e.g. Patience, 70:5, or Gratitude...";
        } else {
            hBtn.classList.add('bg-brand', 'text-white');
            hBtn.classList.remove('bg-brand/5', 'text-brand');
            qBtn.classList.add('bg-brand/5', 'text-brand');
            qBtn.classList.remove('bg-brand', 'text-white');
            hide('quranSearchResults');
            
            // Clear Quran selection when switching to Hadith
            selectedAyahId = null;
            window.selectedAyahMetadata = null;
            hide('selectedAyahBadge');
            
            document.getElementById('studioTopic').placeholder = "e.g. Intention, Charity, or Kindness...";
        }
        
        // Reset topic if it was a reference from the other tab
        // But only if it matches a reference pattern to avoid clearing manual topic ideas
        const currentTopic = document.getElementById('studioTopic').value;
        if (currentTopic.includes(':') || currentTopic.toLowerCase().includes('bukhari') || currentTopic.toLowerCase().includes('muslim')) {
            document.getElementById('studioTopic').value = '';
        }

        onSourceInput();
    }

    function onSourceInput() {
        if (activeSourceTab === 'quran') searchQuran();
        else searchHadith();
    }

    async function searchHadith() {
        const query = document.getElementById('studioTopic').value;
        const resultsArea = document.getElementById('hadithSearchResults');
        if (query.length < 2) {
            resultsArea.classList.add('hidden');
            return;
        }
        resultsArea.innerHTML = '<div class="p-4 text-center text-[8px] font-bold text-brand animate-pulse uppercase tracking-widest">Searching Wisdom...</div>';
        resultsArea.classList.remove('hidden');
        try {
            const res = await fetch(`/api/library/hadith/search?query=${encodeURIComponent(query)}`);
            const data = await res.json();
            if (!data.items || data.items.length === 0) { resultsArea.classList.add('hidden'); return; }
            // Store full hadith objects on the results elements via data attributes
            resultsArea.innerHTML = data.items.map((h, idx) => {
                const safeRef = (h.reference || '').replace(/"/g, '&quot;');
                const metaJson = JSON.stringify({
                    source_type: 'hadith',
                    id: h.hadith_number,
                    collection: h.collection || '',
                    collection_key: h.collection_key || '',
                    reference: h.reference || '',
                    hadith_number: h.hadith_number,
                    arabic_text: h.arabic_text || '',
                    translation_text: h.translation_text || '',
                    card_text: h.card_text || '',
                    narrator: h.narrator || null,
                    grade: h.grade || null,
                    api_source: h.api_source || '',
                    was_excerpted: !!h.was_excerpted
                }).replace(/"/g, '&quot;');
                return `
                <div data-meta="${metaJson}" onclick="selectHadithFromEl(this)" class="p-4 border-b border-brand/5 hover:bg-brand/5 cursor-pointer transition-all">
                    <div class="flex justify-between items-start mb-1">
                        <span class="text-[8px] font-black text-brand uppercase tracking-widest">${safeRef}</span>
                        ${h.narrator ? `<span class="text-[7px] font-bold text-accent uppercase tracking-widest">${h.narrator.replace(/</g,'&lt;')}</span>` : ''}
                    </div>
                    <div class="text-[10px] text-text-muted font-medium italic line-clamp-2">${(h.card_text || h.translation_text || '').replace(/</g,'&lt;')}</div>
                </div>`;
            }).join('');
        } catch (e) { console.error(e); }
    }

    window.selectedHadithMetadata = null;

    // selectHadithFromEl — reads full metadata from the clicked result element
    function selectHadithFromEl(el) {
        try {
            const raw = el.getAttribute('data-meta');
            const meta = JSON.parse(raw.replace(/&quot;/g, '"'));
            _applyHadithSelection(meta);
        } catch(e) {
            console.error('[Studio] selectHadithFromEl parse error:', e);
        }
    }

    // Legacy wrapper kept for any existing inline callers
    function selectHadith(id, collection, reference, text) {
        _applyHadithSelection({
            source_type: 'hadith',
            id: id,
            collection: collection,
            reference: reference,
            translation_text: text,
            card_text: text
        });
    }

    function _applyHadithSelection(meta) {
        selectedHadithId = meta.hadith_number || meta.id;
        selectedAyahId = null;
        window.selectedHadithMetadata = meta;
        document.getElementById('selectedHadithBadge').classList.remove('hidden');
        document.getElementById('selectedAyahBadge').classList.add('hidden');
        document.getElementById('selectedHadithTitle').innerText = meta.reference || '';
        document.getElementById('hadithSearchResults').classList.add('hidden');
        document.getElementById('studioTopic').value = meta.reference || '';

        // Arabic preview (first ~60 chars of arabic_text)
        const arabicEl = document.getElementById('selectedHadithArabicPreview');
        if (arabicEl) {
            const ar = (meta.arabic_text || '').trim();
            arabicEl.textContent = ar ? (ar.length > 80 ? ar.slice(0, 80) + '…' : ar) : '';
        }
        // English snippet (card_text or translation_text, truncated)
        const textEl = document.getElementById('selectedHadithTextPreview');
        if (textEl) {
            const en = (meta.card_text || meta.translation_text || '').trim();
            textEl.textContent = en ? (en.length > 110 ? en.slice(0, 110) + '…' : en) : '';
        }
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
        selectedHadithId = null;
        window.selectedAyahMetadata = { reference: title, translation_text: text, id: id };
        document.getElementById('selectedAyahBadge').classList.remove('hidden');
        document.getElementById('selectedHadithBadge').classList.add('hidden');
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

        if (!topic && !selectedAyahId && !selectedHadithId) {
            alert('Please define a topic or select a source.');
            return;
        }

        btn.disabled = true;
        if(icon) icon.classList.add('animate-spin');
        if(text) text.innerText = 'Architecting Message...';

        try {
            let sourceType = 'manual';
            let sourcePayload = { text: topic, reference: topic };

            if (activeSourceTab === 'quran' && selectedAyahId) {
                sourceType = 'quran';
                sourcePayload = window.selectedAyahMetadata;
            } else if (activeSourceTab === 'hadith' && selectedHadithId) {
                sourceType = 'hadith';
                sourcePayload = window.selectedHadithMetadata;
            }

            const payload = {
                source_type: sourceType,
                source_payload: sourcePayload,
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
        btn.innerText = 'Preparing Visual...';
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
            // Determine correct source type and payload
            let srcType = 'manual';
            let srcPayload = { text: studioCardMessage ? studioCardMessage.headline : '' };

            if (selectedHadithId && window.selectedHadithMetadata) {
                // Hadith: pass full metadata so caption is grounded in exact Hadith text
                srcType = 'hadith';
                srcPayload = window.selectedHadithMetadata;
            } else if (selectedAyahId && window.selectedAyahMetadata) {
                srcType = 'quran';
                srcPayload = window.selectedAyahMetadata;
            }

            const payload = {
                source_type: srcType,
                source_payload: srcPayload,
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
            // Handle both structured caption_message and plain caption string
            if (data.caption_message) {
                studioCaptionMessage = data.caption_message;
                const fullText = `${studioCaptionMessage.hook || ''}\n\n${studioCaptionMessage.body || ''}\n\n${studioCaptionMessage.cta || ''}\n\n${(studioCaptionMessage.hashtags || []).join(' ')}`;
                document.getElementById('studioCaption').value = fullText.trim();
                document.getElementById('captionResultArea').classList.remove('hidden');
            } else if (data.caption) {
                // Plain string caption from Hadith / fallback path
                studioCaptionMessage = { caption: data.caption };
                document.getElementById('studioCaption').value = data.caption;
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

    function prepareShare() {
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

        if (isQuoteCardOutOfDate && !confirm("Your quote card no longer matches your latest message. Share anyway?")) {
            return;
        }

        btn.disabled = true;
        btn.innerHTML = 'PREPARING... <span class="animate-pulse">✨</span>';

        const accountId = document.getElementById('studioAccount').value;
        const topicVal = document.getElementById('studioTopic').value;

        // ── Determine source type and metadata ──────────────────────────────────
        let srcType = 'manual';
        let srcReference = topicVal;
        let srcMetadata = null;

        if (selectedHadithId && window.selectedHadithMetadata) {
            srcType = 'hadith';
            srcReference = window.selectedHadithMetadata.reference || topicVal;
            srcMetadata = window.selectedHadithMetadata;
        } else if (selectedAyahId && window.selectedAyahMetadata) {
            srcType = 'quran';
            srcReference = window.selectedAyahMetadata.reference || topicVal;
            srcMetadata = window.selectedAyahMetadata;
        }

        const reqPayload = {
            ig_account_id: parseInt(accountId, 10),
            visual_mode: 'quote_card',
            source_type: srcType,
            source_reference: srcReference,
            source_metadata: srcMetadata,
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
                alert('Creation Error: ' + (data.detail || 'Unknown error'));
            }
        } catch (e) {
            alert('Connection failure: ' + e);
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
                        if (typeof switchSourceTab === 'function') switchSourceTab('quran');
                        selectAyah(item.id, item.reference, item.translation_text);
                    } else if (item.type === 'hadith' || item.source_type === 'hadith') {
                        // Switch source tab to Hadith and load the item
                        if (typeof switchSourceTab === 'function') switchSourceTab('hadith');
                        _applyHadithSelection(item);
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
    window.currentAutoStylePool = [];

    async function loadStyleDnaPresets() {
        if (v2DnaPresets.length > 0 && document.getElementById('autoV2StyleDNAContainer')?.children.length > 1) return;
        try {
            console.log("[Sabeel Studio] Loading Style DNA presets...");
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
                    setTimeout(() => {
                        if (container.children[0]) selectV2StyleDna(v2DnaPresets[0].id || '', container.children[0]);
                    }, 50);
                }
            }
        } catch (e) {
            console.error('[Sabeel Studio] Failed to load style DNA presets: ', e);
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
        const topicRaw = document.querySelector('textarea[name="topic_prompt"]')?.value || '';
        
        // Topic Pool Parsing
        const topics = topicRaw.split(',').map(t => t.trim()).filter(t => t.length > 0);
        const uniqueTopics = [...new Set(topics)];
        window.currentAutoTopicPool = uniqueTopics;

        // Render Chips
        const chipContainer = document.getElementById('autoV2TopicChips');
        if (chipContainer) {
            if (uniqueTopics.length > 0) {
                chipContainer.innerHTML = uniqueTopics.map(t => `
                    <span class="px-3 py-1 bg-brand/10 border border-brand/20 rounded-full text-[9px] font-bold text-brand uppercase tracking-widest flex items-center gap-2 animate-in zoom-in duration-200">
                        <span class="w-1.5 h-1.5 rounded-full bg-accent"></span>
                        ${t}
                    </span>
                `).join('');
            } else {
                chipContainer.innerHTML = '<p class="text-[8px] text-text-muted italic px-1 font-medium">Enter multiple topics separated by commas...</p>';
            }
        }

        const cadence = document.getElementById('autoV2CadenceInput')?.value || 'daily';
        const mode = document.getElementById('autoV2ApprovalModeInput')?.value || 'needs_manual_approve';
        const timeInput = document.querySelector('input[name="post_time_local"]')?.value || '09:00';
        const postsPerDay = document.querySelector('input[name="posts_per_day"]')?.value || 1;
        const spacing = document.querySelector('input[name="post_spacing_hours"]')?.value || 4;
        
        let dnaLabel = 'Atmospheric';
        if (window.currentAutoStylePool && window.currentAutoStylePool.length > 0) {
            const labels = window.currentAutoStylePool.map(id => {
                const match = v2DnaPresets.find(p => p.id == id);
                return match ? match.label : 'Style';
            });
            dnaLabel = labels.join(' + ');
        }

        const summaryEl = document.getElementById('autoV2BehaviorSummary');
        if (summaryEl) {
            let timeStr = timeInput;
            try {
                const [h, m] = timeInput.split(':');
                const hh = parseInt(h);
                const period = hh >= 12 ? 'PM' : 'AM';
                const displayH = hh % 12 || 12;
                timeStr = `${displayH}:${m} ${period}`;
            } catch(e) {}

            const topicSummary = uniqueTopics.length > 1 
                ? `${uniqueTopics.length} Rotational Topics` 
                : (uniqueTopics[0] || 'Not defined');

            summaryEl.innerHTML = `
                <div class="space-y-4 w-full">
                    <div class="flex items-center justify-between border-b border-brand/5 pb-2">
                        <span class="text-[10px] font-black text-brand uppercase tracking-widest">Growth Plan Summary</span>
                        <span class="text-[9px] font-bold text-accent uppercase tracking-tighter italic">Dynamic Configuration</span>
                    </div>
                    <div class="grid grid-cols-2 gap-x-8 gap-y-3">
                        <div class="flex flex-col">
                            <span class="text-[8px] font-bold text-text-muted uppercase tracking-widest leading-none">Topic Pool</span>
                            <span class="text-[11px] font-black text-brand line-clamp-1 italic mt-1">"${topicSummary}"</span>
                        </div>
                        <div class="flex flex-col">
                            <span class="text-[8px] font-bold text-text-muted uppercase tracking-widest leading-none">Style DNA</span>
                            <span class="text-[11px] font-black text-brand mt-1">${dnaLabel}</span>
                        </div>
                        <div class="flex flex-col">
                            <span class="text-[8px] font-bold text-text-muted uppercase tracking-widest leading-none">Frequency</span>
                            <span class="text-[11px] font-black text-brand mt-1">${cadence === 'daily' ? 'Daily Stream' : 'Weekly Sync'} @ ${timeStr}</span>
                        </div>
                        <div class="flex flex-col">
                            <span class="text-[8px] font-bold text-text-muted uppercase tracking-widest leading-none">Volume & Spacing</span>
                            <span class="text-[11px] font-black text-brand mt-1">${postsPerDay} post${postsPerDay > 1 ? 's' : ''}/${cadence === 'daily' ? 'day' : 'week'} (${spacing}h buffer)</span>
                        </div>
                        <div class="flex flex-col col-span-full pt-1">
                            <span class="text-[8px] font-bold text-text-muted uppercase tracking-widest leading-none">Approval Protocol</span>
                            <span class="text-[11px] font-black ${mode === 'auto_approve' ? 'text-rose-600' : 'text-emerald-600'} mt-1">
                                ${mode === 'auto_approve' ? 'Auto-Pilot: Publishes automatically' : 'Drafting Engine: Requires your review'}
                            </span>
                        </div>
                    </div>
                </div>
            `;
        }
    };

    window.selectV2StyleDna = function(id, el) {
        const dnaId = parseInt(id, 10);
        const pool = window.currentAutoStylePool || [];
        const index = pool.indexOf(dnaId);

        if (index > -1) {
            // Remove if already present
            pool.splice(index, 1);
        } else {
            // Add if limit not reached
            if (pool.length < 3) {
                pool.push(dnaId);
            } else {
                alert("Reminder: You can select up to 3 visual directions to maintain consistency.");
                return;
            }
        }
        window.currentAutoStylePool = pool;

        // Backward compatibility: style_dna_id is the first one in the pool
        const input = document.getElementById('autoV2StyleDNAInput');
        if(input) input.value = pool.length > 0 ? pool[0] : "";

        // Update UI
        const container = document.getElementById('autoV2StyleDNAContainer');
        if (container) {
            container.querySelectorAll('.auto-style-card').forEach(c => {
                const cardIdAttr = c.getAttribute('onclick');
                const isSelected = pool.some(pid => cardIdAttr.includes(`'${pid}'`) || cardIdAttr.includes(`${pid}`));
                
                if (isSelected) {
                    c.classList.add('ring-2', 'ring-brand', 'bg-brand/5', 'shadow-xl');
                } else {
                    c.classList.remove('ring-2', 'ring-brand', 'bg-brand/5', 'shadow-xl');
                }
            });
        }
        
        if (pool.length > 0) {
            window.updateAutoV2VisualPreview(pool[pool.length - 1]);
        }
        window.updateAutoV2Summary();
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
        console.log("[Sabeel Studio] Initializing Growth Plan Modal...");
        const modal = document.getElementById('newAutoModalV2');
        if (modal) {
            modal.style.display = 'flex';
            modal.classList.remove('hidden');
            try {
                await loadStyleDnaPresets();
                const form = document.getElementById('autoV2Form');
                if (form) {
                    form.dataset.editId = "";
                    form.reset();
                    window.currentAutoStylePool = [];
                }
                window.updateAutoV2Summary();
            } catch (e) {
                console.error("[Sabeel Studio] Modal Init Warning:", e);
            }
        } else {
            console.error("[Sabeel Studio] Critical: newAutoModalV2 not found in DOM");
        }
    };

    window.testAutoV2Preview = async function() {
        const btn = document.getElementById('btnPreviewAutoV2');
        const form = document.getElementById('autoV2Form');
        
        // Data Extraction
        const topicPool = window.currentAutoTopicPool || [];
        const stylePool = window.currentAutoStylePool || [];
        const language = document.getElementById('autoV2LanguageInput')?.value || 'english';

        if (topicPool.length === 0) { 
            alert("Please provide at least one topic in your Topic Pool before simulating."); 
            return; 
        }

        const originalText = btn.innerHTML;
        btn.innerHTML = '<span class="flex items-center gap-2 text-[10px] pr-2"><svg class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg> Generating previews...</span>';
        btn.disabled = true;
        
        const container = document.getElementById('autoV2PreviewContainer');
        const content = document.getElementById('autoV2PreviewContent');
        
        // Show Loading Skeleton / Cinematic Spinner
        content.innerHTML = `
            <div class="col-span-full py-12 flex flex-col items-center justify-center space-y-6">
                <div class="relative">
                    <div class="w-20 h-20 rounded-full border-4 border-brand/5 border-t-brand animate-spin"></div>
                    <div class="absolute inset-0 flex items-center justify-center">
                        <svg class="w-6 h-6 text-brand/20 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                    </div>
                </div>
                <div class="text-center">
                    <div class="text-[11px] font-black text-brand uppercase tracking-widest animate-pulse">Consulting Wisdom Libraries...</div>
                    <div class="text-[9px] font-bold text-text-muted italic mt-1">Generating grounded samples and rendering visuals</div>
                </div>
            </div>
        `;
        container.classList.remove('hidden');
        
        try {
            const res = await fetch('/automations/v2/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    topic_pool: topicPool,
                    style_dna_pool: stylePool,
                    language: language
                })
            });
            
            if (!res.ok) throw new Error(await res.text());
            const responses = await res.json();
            
            container.classList.remove('hidden');
            content.innerHTML = responses.map((data, i) => {
                const topicLabel = data.topic;
                
                // Color mapping for badges
                const isQuran = data.source_type === 'quran' && !data.fallback_mode;
                const badgeColor = isQuran ? 'bg-emerald-500' : 'bg-brand/40';
                
                let badgeText = isQuran ? "Verified Qur'an Reference" : "Reflection Preview";
                if (data.fallback_mode) {
                    badgeText = "No direct source found • Reflection Mode";
                }
                
                return `
                    <div class="bg-white border border-brand/5 rounded-3xl overflow-hidden shadow-sm hover:shadow-xl transition-all duration-500 flex flex-col group">
                        <!-- Header Meta -->
                        <div class="px-6 py-4 bg-brand/[0.02] flex items-center justify-between border-b border-brand/[0.03]">
                            <div class="flex flex-col gap-0.5">
                                <div class="flex items-center gap-2">
                                    <span class="w-1.5 h-1.5 rounded-full ${badgeColor} animate-pulse"></span>
                                    <span class="text-[9px] font-black text-brand uppercase tracking-widest">${badgeText}</span>
                                </div>
                                <div class="text-[10px] font-bold text-text-muted italic ml-3.5">Topic: ${topicLabel} • Vision: ${data.style_name}</div>
                            </div>
                            <span class="text-[9px] font-black text-brand/20 uppercase tracking-tighter">Sample ${data.sample_index}</span>
                        </div>
                        
                        <!-- Visual Area -->
                        <div class="aspect-square bg-gray-100 relative group-hover:scale-[1.01] transition-transform duration-700">
                             ${data.visual_url ? `
                                <img src="${data.visual_url}" class="w-full h-full object-cover" alt="Post Preview">
                             ` : `
                                <div class="w-full h-full flex flex-col items-center justify-center p-8 text-center space-y-3 opacity-60">
                                    <div class="w-16 h-16 rounded-2xl bg-brand/5 border border-brand/10 flex items-center justify-center">
                                         <svg class="w-6 h-6 text-brand/30" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                                    </div>
                                    <div>
                                        <div class="text-[10px] font-black text-brand uppercase tracking-widest">Visual Representative</div>
                                        <div class="text-[9px] font-bold text-text-muted italic">Rendering occurs during live streams</div>
                                    </div>
                                </div>
                             `}
                             
                             <div class="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"></div>
                        </div>

                        <!-- Caption Area -->
                        <div class="p-6 space-y-4">
                             <div class="bg-brand/[0.02] border-l-4 border-brand/10 p-4 rounded-r-2xl">
                                 <p class="text-[11px] text-brand font-black leading-relaxed italic line-clamp-3">
                                    "${data.caption || 'Insight flowing from the selected wisdom pool...'}"
                                 </p>
                                 <div class="text-[9px] font-black text-brand uppercase tracking-widest text-right mt-3 opacity-60">— ${data.source_reference || 'Reflection'}</div>
                             </div>

                             ${data.hashtags && data.hashtags.length > 0 ? `
                             <div class="pt-2 flex flex-wrap gap-1.5">
                                 ${data.hashtags.slice(0, 5).map(h => `<span class="px-2 py-0.5 bg-brand/[0.03] rounded-md text-[8px] font-bold text-brand uppercase tracking-tighter opacity-50 hover:opacity-100 transition-opacity cursor-default">#${h}</span>`).join('')}
                             </div>` : ''}
                        </div>
                    </div>
                `;
            }).join('');
            
            container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } catch(e) {
            console.error(e);
            alert('Preview Engine error: ' + e.message);
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    };
    
    window.closeNewAutoModal = function() {
        const modal = document.getElementById('newAutoModalV2');
        if (modal) {
            modal.classList.add('hidden');
            modal.style.display = 'none';
        }
    };

    window.submitNewAutoV2 = async function(event) {
        event.preventDefault();
        const btn = document.getElementById('btnSubmitAutoV2');
        const original = btn.innerText;
        btn.disabled = true;
        btn.innerHTML = '<span class="flex items-center justify-center gap-2">Launching Plan... <svg class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg></span>';

        const form = event.target;
        const payload = {
            name: form.name.value,
            topic_prompt: form.topic_prompt.value,
            topic_pool: window.currentAutoTopicPool || [],
            style_dna_id: form.style_dna_id.value ? parseInt(form.style_dna_id.value) : null,
            style_dna_pool: window.currentAutoStylePool || [],
            automation_version: 2,
            approval_mode: document.getElementById('autoV2ApprovalModeInput') ? document.getElementById('autoV2ApprovalModeInput').value : 'auto_approve',
            cadence: document.getElementById('autoV2CadenceInput') ? document.getElementById('autoV2CadenceInput').value : 'daily',
            post_time_local: form.post_time_local.value,
            posts_per_day: form.posts_per_day ? parseInt(form.posts_per_day.value) : 1,
            post_spacing_hours: form.post_spacing_hours ? parseInt(form.post_spacing_hours.value) : 4
        };

        if (!form.dataset.editId) {
            payload.ig_account_id = parseInt(form.ig_account_id.value);
            payload.posting_mode = 'schedule';
            payload.enabled = true;
        } else {
            payload.ig_account_id = parseInt(form.ig_account_id.value);
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
        console.log("[Sabeel Studio] Configuring Existing Plan:", data.id);
        await loadStyleDnaPresets();
        const modal = document.getElementById('newAutoModalV2');
        if (!modal) return;
        
        const form = document.getElementById('autoV2Form');
        form.dataset.editId = data.id;
        
        form.name.value = data.name || '';
        if(form.ig_account_id) form.ig_account_id.value = data.ig_account_id || '';
        form.topic_prompt.value = data.topic_prompt || '';
        
        // Safari normalization: HH:mm format is strict
        if (data.post_time_local) {
            form.post_time_local.value = data.post_time_local.split(':')[0].padStart(2, '0') + ':' + data.post_time_local.split(':')[1].padStart(2, '0');
        } else {
            form.post_time_local.value = '';
        }
        if(form.posts_per_day) form.posts_per_day.value = data.posts_per_day || 1;
        if(form.post_spacing_hours) form.post_spacing_hours.value = data.post_spacing_hours || 4;
        
        if (data.style_dna_id || (data.style_dna_pool && data.style_dna_pool.length > 0)) {
            const input = document.getElementById('autoV2StyleDNAInput');
            const pool = data.style_dna_pool || (data.style_dna_id ? [data.style_dna_id] : []);
            window.currentAutoStylePool = pool;
            
            if(input) input.value = pool.length > 0 ? pool[0] : "";
            
            setTimeout(() => {
                const container = document.getElementById('autoV2StyleDNAContainer');
                if(container) {
                    const cards = container.querySelectorAll('.auto-style-card');
                    const cardsArr = Array.from(cards);
                    
                    pool.forEach(pid => {
                        const targetCard = cardsArr.find(c => c.getAttribute('onclick')?.includes(`'${pid}'`) || c.getAttribute('onclick')?.includes(`${pid}`));
                        if(targetCard) {
                            targetCard.classList.add('ring-2', 'ring-brand', 'bg-brand/5', 'shadow-xl');
                        }
                    });
                    
                    if (pool.length > 0) window.updateAutoV2VisualPreview(pool[pool.length-1]);
                }
            }, 150);
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
        modal.style.display = 'flex';
        
        // Final Summary Update
        setTimeout(() => { window.updateAutoV2Summary(); }, 200);
    };

    window.runNow = async function(event, id) {
        event.stopPropagation();
        const btn = event.target;
        const original = btn.innerText;
        
        btn.disabled = true;
        btn.innerText = 'SHARING...';
        
        try {
            const res = await fetch(`/automations/${id}/run-once`, { method: 'POST' });
            if (res.ok) {
                alert('Reminder stream triggered successfully.');
                window.location.reload();
            } else {
                const err = await res.json();
                alert('Failed to trigger: ' + (err.detail || 'System Error'));
            }
        } catch (e) {
            alert('Connection failed.');
        } finally {
            btn.disabled = false;
            btn.innerText = original;
        }
    };

    window.deleteAutomation = async function(id) {
        if (!confirm("Are you sure you want to delete this Reminder Stream strategy? This action cannot be undone.")) return;
        
        try {
            const res = await fetch(`/automations/${id}`, { method: 'DELETE' });
            if (res.ok) {
                window.location.reload();
            } else {
                const err = await res.json();
                alert('Deletion Failed: ' + (err.detail || 'Unknown error'));
            }
        } catch (e) {
            alert('Connection failure during deletion.');
        }
    };

    window.deletePost = async function(id) {
        if (!confirm("Discard this piece of reminder?")) return;
        try {
            const res = await fetch(`/posts/${id}`, { method: 'DELETE' });
            if (res.ok) {
                window.location.reload();
            } else {
                alert('Failed to discard post.');
            }
        } catch (e) {
            alert('Connection failure.');
        }
    };
    window.approvePost = async function(id) {
        const btn = event?.target || {};
        const originalText = btn.innerText || 'Share Now';
        
        try {
            if(btn.innerText) {
                btn.disabled = true;
                btn.innerText = 'CHECKING...';
                btn.classList.add('animate-pulse');
            }

            console.log(`🚀 [SHARE_NOW] Starting flow for post_id=${id}`);

            // 1. Preflight
            const checkRes = await fetch(`/posts/${id}/preflight-check`);
            const integrity = await checkRes.json();
            
            if (integrity.stale) {
                console.log(`🔄 [MEDIA_RECOVERY] Stale media detected for ${id}. Triggering restoration...`);
                if(btn.innerText) btn.innerText = 'RESTORING...';
                const recRes = await fetch(`/posts/${id}/recover`, { method: 'POST' });
                if (!recRes.ok) {
                    const err = await recRes.json();
                    throw new Error(err.detail || "Recovery failed.");
                }
                console.log(`✅ [MEDIA_RECOVERY] Post ${id} restored successfully.`);
            }

            // 2. Approve/Schedule
            if(btn.innerText) btn.innerText = 'SHARING...';
            console.log(`📡 [IG_PUBLISH] Approving & Publishing post_id=${id}`);
            
            const approveRes = await fetch(`/posts/${id}/approve`, { 
                method: 'POST', 
                headers: {'Content-Type':'application/json'}, 
                body: JSON.stringify({approve_anyway: true}) 
            });
            
            if (!approveRes.ok) {
                const data = await approveRes.json();
                throw new Error(data.detail || "Approval failed.");
            }

            // 3. Immediate Publish (Since it was 'Share Now')
            const pubRes = await fetch(`/posts/${id}/publish`, { method: 'POST' });
            if (pubRes.ok) {
                console.log(`✨ [IG_PUBLISH] Success for post_id=${id}`);
                window.location.reload();
            } else {
                const data = await pubRes.json();
                throw new Error(data.detail || "Publishing failed.");
            }
        } catch (e) {
            console.error(`❌ [SHARE_NOW] Failure:`, e);
            alert('Share Failed: ' + e.message);
        } finally {
            if(btn.innerText) {
                btn.disabled = false;
                btn.innerText = originalText;
                btn.classList.remove('animate-pulse');
            }
        }
    };

    window.openEditPostModal = function(id, caption, time) {
        // Simple stub for now to prevent crashes, or we could redirect to a dedicated editor
        console.log("Edit Post:", id, caption, time);
        alert("Refine feature is being optimized. Please use the Studio to create new reminders.");
    };

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
             <div class="text-xs font-bold uppercase tracking-widest nav-text">The Share</div>
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
              <p class="text-xs text-text-muted mt-2 font-medium">Search the Qur'an or Hadith to build your card's central message.</p>
            </div>

            <div class="space-y-8">
                <div class="space-y-4">
                    <div class="space-y-3">
                       <div class="flex items-center justify-between mb-2">
                           <label class="text-[9px] font-black text-brand uppercase tracking-widest ml-1">Foundation Source</label>
                           <div class="flex gap-1 bg-brand/5 p-1 rounded-xl">
                               <button type="button" id="tabBtnQuran" onclick="switchSourceTab('quran')" class="px-4 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-widest bg-brand text-white transition-all">Qur'an</button>
                               <button type="button" id="tabBtnHadith" onclick="switchSourceTab('hadith')" class="px-4 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-widest bg-brand/5 text-brand hover:bg-brand/10 transition-all">Hadith</button>
                           </div>
                       </div>
                       <div class="relative">
                            <input type="text" id="studioTopic" name="topic" oninput="onSourceInput()" placeholder="e.g. Patience, 70:5, or Gratitude..." class="w-full bg-cream/20 border border-brand/5 rounded-2xl px-8 py-6 text-sm font-medium text-brand outline-none focus:border-brand/20 transition-all shadow-inner">
                            <div class="absolute right-6 top-1/2 -translate-y-1/2 text-brand/20">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                            </div>
                       </div>
                    </div>
                    <div class="space-y-3">
                        <label class="text-[9px] font-black text-brand uppercase tracking-widest ml-1">Target Account</label>
                        <select id="studioAccount" name="ig_account_id" class="w-full bg-cream/20 border border-brand/5 rounded-2xl px-6 py-4 text-xs font-bold text-brand outline-none focus:border-brand/20 transition-all">
                            {account_options}
                        </select>
                    </div>
                    <div id="quranSearchResults" class="hidden max-h-48 overflow-y-auto bg-white border border-brand/10 rounded-2xl shadow-xl custom-scrollbar z-[120]"></div>
                    <div id="hadithSearchResults" class="hidden max-h-48 overflow-y-auto bg-white border border-brand/10 rounded-2xl shadow-xl custom-scrollbar z-[120]"></div>
                    
                    <div id="selectedAyahBadge" class="hidden p-4 bg-emerald-50 border border-emerald-100 rounded-2xl flex items-center justify-between shadow-sm">
                        <div class="flex items-center gap-3">
                            <div class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                            <span id="selectedAyahTitle" class="text-[10px] font-black text-emerald-800 uppercase tracking-widest"></span>
                        </div>
                        <button type="button" onclick="selectedAyahId=null; window.selectedAyahMetadata=null; document.getElementById('selectedAyahBadge').classList.add('hidden');" class="text-[8px] font-bold text-emerald-600 uppercase hover:underline">Change</button>
                    </div>

                    <div id="selectedHadithBadge" class="hidden p-4 bg-accent/5 border border-accent/20 rounded-2xl shadow-sm">
                        <div class="flex items-start justify-between gap-3">
                          <div class="flex items-start gap-3 min-w-0">
                            <div class="w-2 h-2 rounded-full bg-accent animate-pulse mt-1 shrink-0"></div>
                            <div class="min-w-0">
                              <span id="selectedHadithTitle" class="block text-[10px] font-black text-brand uppercase tracking-widest truncate"></span>
                              <span id="selectedHadithArabicPreview" class="block text-[13px] text-brand/60 mt-1 leading-relaxed font-normal" style="font-family:'Amiri',serif;direction:rtl;text-align:right;"></span>
                              <span id="selectedHadithTextPreview" class="block text-[9px] text-brand/45 mt-0.5 italic line-clamp-2"></span>
                            </div>
                          </div>
                          <button type="button" onclick="selectedHadithId=null; window.selectedHadithMetadata=null; document.getElementById('selectedHadithBadge').classList.add('hidden');" class="text-[8px] font-bold text-brand uppercase hover:underline shrink-0">Change</button>
                        </div>
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
                      <button type="submit" id="studioSubmitBtn" class="w-full py-6 bg-brand text-white rounded-3xl font-black text-[12px] uppercase tracking-[0.3em] shadow-2xl shadow-brand/20">Schedule Reminder</button>
                   </div>
               </div>
          </div>
        </div>
      </form>
    </div>
</div>

<!-- AUTOMATION V2 MODAL -->
<div id="newAutoModalV2" class="fixed inset-0 bg-black/95 backdrop-blur-2xl z-[100] flex items-center justify-center p-4 md:p-10 hidden">
    <div class="w-full max-w-2xl max-h-full bg-white rounded-3xl overflow-hidden flex flex-col animate-in zoom-in duration-300 shadow-2xl relative">
        <button type="button" onclick="closeNewAutoModal()" class="absolute top-6 right-6 z-10 w-10 h-10 rounded-full bg-brand/5 border border-brand/10 flex items-center justify-center text-brand hover:bg-brand hover:text-white transition-all">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path></svg>
        </button>
        <div class="p-8 md:p-10 border-b border-brand/5">
            <h3 class="text-2xl font-black text-brand tracking-tight">Establish <span class="text-accent italic">Reminder Path</span></h3>
            <p class="text-sm font-medium text-text-muted mt-2 leading-relaxed">Establish a continuous rhythm of authentic guidance, grounded in sacred knowledge and atmospheric design.</p>
        </div>
        <div class="p-8 md:p-10 flex-1 overflow-y-auto">
            <form id="autoV2Form" onsubmit="submitNewAutoV2(event)" class="space-y-6">
                <div class="space-y-2">
                    <label class="text-[10px] font-black text-brand uppercase tracking-widest ml-1">Target Account</label>
                    <select name="ig_account_id" id="autoV2AccountSelector" class="w-full bg-brand/5 border border-brand/10 rounded-xl px-4 py-3 text-sm font-bold text-brand outline-none focus:border-brand/30">
                        {account_options}
                    </select>
                </div>
                <div class="space-y-2">
                    <label class="text-[10px] font-black text-brand uppercase tracking-widest ml-1">Plan Name</label>
                    <input type="text" name="name" required oninput="updateAutoV2Summary()" placeholder="e.g. Daily Friday Sunnah" class="w-full bg-brand/5 border border-brand/10 rounded-xl px-4 py-3 text-sm font-bold text-brand outline-none focus:border-brand/30">
                </div>
                <div class="space-y-2">
                    <label class="text-[10px] font-black text-brand uppercase tracking-widest ml-1">Core Topic / Guidance</label>
                    <textarea name="topic_prompt" required oninput="updateAutoV2Summary()" placeholder="e.g. Sabr, Gratitude, Daily Prayers..." class="w-full bg-brand/5 border border-brand/10 rounded-xl px-4 py-3 text-sm font-medium text-brand min-h-[100px] outline-none focus:border-brand/30"></textarea>
                    <div id="autoV2TopicChips" class="flex flex-wrap gap-2 mt-2"></div>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div class="space-y-4 col-span-full">
                        <label class="text-[10px] font-black text-brand uppercase tracking-widest ml-1">Visual Directions (Style DNA)</label>
                        <p class="text-[8px] text-text-muted px-1 font-medium mb-2">Select up to 3 visual directions. The engine will rotate through your pool for each post.</p>
                        <input type="hidden" name="style_dna_id" id="autoV2StyleDNAInput" required>
                        <div id="autoV2StyleDNAContainer" class="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <div class="p-8 text-center text-brand/30 animate-pulse text-[10px] font-bold uppercase tracking-widest col-span-full">Refining Guidance Reminders...</div>
                        </div>
                    </div>
                    <div class="space-y-4 col-span-full pt-4 border-t border-brand/5">
                        <label class="text-[10px] font-black text-brand uppercase tracking-widest ml-1">Stream Frequency (Cadence)</label>
                        <input type="hidden" name="cadence" id="autoV2CadenceInput" value="daily">
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                            <div onclick="selectCadenceMode('daily', this)" class="cadence-card ring-2 ring-brand shadow-xl cursor-pointer bg-cream border border-brand/5 rounded-2xl p-6 hover:border-brand/30 transition-all flex flex-col relative overflow-hidden">
                                <div class="text-[11px] uppercase font-black tracking-widest text-brand mb-2">Daily Stream</div>
                                <div class="text-[10px] text-text-muted font-bold leading-relaxed pr-6">Continuously generates native content every single day.</div>
                            </div>
                            <div onclick="selectCadenceMode('weekly', this)" class="cadence-card cursor-pointer bg-cream border border-brand/5 rounded-2xl p-6 hover:border-brand/30 transition-all flex flex-col relative overflow-hidden">
                                <div class="text-[11px] uppercase font-black tracking-widest text-brand mb-2">Weekly Stream</div>
                                <div class="text-[10px] text-text-muted font-bold leading-relaxed pr-6">A slower, deliberate schedule processing one instance per week.</div>
                            </div>
                        </div>
                    </div>
                    <div class="space-y-4">
                        <label class="text-[10px] font-black text-brand uppercase tracking-widest ml-1 flex items-center gap-2">
                             <svg class="w-3 h-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
                             Posting Time
                        </label>
                        <input type="time" name="post_time_local" oninput="updateAutoV2Summary()" step="60" required class="w-full bg-brand/[0.03] border border-brand/10 rounded-2xl px-6 py-4 text-sm font-black text-brand outline-none focus:border-brand/40 focus:ring-4 focus:ring-brand/5 transition-all max-w-xs shadow-inner">
                        <p class="text-[8px] text-text-muted mt-1 px-1 font-medium">The specific time your daily reflection cycle begins.</p>
                    </div>
                    <div class="grid grid-cols-2 gap-4 col-span-full">
                        <div class="space-y-2">
                            <label class="text-[10px] font-black text-brand uppercase tracking-widest ml-1">Posts Per Day</label>
                            <input type="number" name="posts_per_day" min="1" max="5" value="1" oninput="updateAutoV2Summary()" class="w-full bg-brand/5 border border-brand/10 rounded-xl px-4 py-3 text-sm font-bold text-brand outline-none focus:border-brand/30">
                            <p class="text-[8px] text-text-muted mt-1 px-1 font-medium">Guidance items generated per cycle.</p>
                        </div>
                        <div class="space-y-2">
                            <label class="text-[10px] font-black text-brand uppercase tracking-widest ml-1">Min. Spacing Between Posts</label>
                            <input type="number" name="post_spacing_hours" min="1" max="12" value="4" oninput="updateAutoV2Summary()" class="w-full bg-brand/5 border border-brand/10 rounded-xl px-4 py-3 text-sm font-bold text-brand outline-none focus:border-brand/30">
                            <p class="text-[8px] text-text-muted mt-1 px-1 font-medium">Hours buffer between automated jobs.</p>
                        </div>
                    </div>
                    <div class="space-y-4 pt-4 border-t border-brand/5 col-span-full">
                        <label class="text-[10px] font-black text-brand uppercase tracking-widest ml-1">Approval Protocol</label>
                        <input type="hidden" name="approval_mode" id="autoV2ApprovalModeInput" value="needs_manual_approve">
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div onclick="selectApprovalMode('needs_manual_approve', this)" class="approval-card ring-2 ring-brand shadow-xl cursor-pointer bg-cream border border-brand/5 rounded-2xl p-6 hover:border-brand/30 transition-all flex flex-col relative overflow-hidden">
                                <div class="absolute top-0 right-0 p-4 text-brand opacity-5"><svg class="w-16 h-16" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd"></path></svg></div>
                                <div class="text-[11px] uppercase font-black tracking-widest text-brand mb-2">Drafting Engine</div>
                                <div class="text-[10px] text-text-muted font-bold leading-relaxed pr-8">Creates posts as drafts. You approve them before publishing.</div>
                            </div>
                            <div onclick="selectApprovalMode('auto_approve', this)" class="approval-card cursor-pointer bg-cream border border-brand/5 rounded-2xl p-6 hover:border-brand/30 transition-all flex flex-col relative overflow-hidden">
                                <div class="absolute top-0 right-0 p-4 text-brand opacity-5"><svg class="w-16 h-16" fill="currentColor" viewBox="0 0 20 20"><path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"></path></svg></div>
                                <div class="text-[11px] uppercase font-black tracking-widest text-brand mb-2">Auto-Pilot</div>
                                <div class="text-[10px] text-text-muted font-bold leading-relaxed pr-8">Publishes automatically at the scheduled time.</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="pt-6 flex flex-col gap-4">
                    <div id="autoV2BehaviorSummary" class="p-6 bg-brand/[0.03] border border-brand/5 rounded-[2rem] flex flex-col gap-4">
                         <div class="text-[10px] font-black text-brand/30 uppercase tracking-widest text-center animate-pulse">Awaiting Configuration...</div>
                    </div>

                    <div class="flex gap-4">
                        <button type="submit" id="btnSubmitAutoV2" class="flex-1 py-5 bg-brand text-white rounded-2xl font-black text-xs uppercase tracking-widest shadow-xl shadow-brand/20 hover:scale-[1.01] transition-all">Activate Reminder Stream</button>
                        <button type="button" onclick="testAutoV2Preview()" id="btnPreviewAutoV2" class="px-8 py-5 bg-brand/5 text-brand rounded-2xl font-black text-xs uppercase tracking-widest hover:bg-brand/10 transition-all flex items-center justify-center gap-2">
                           <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg>
                           <span class="text-[10px]">Simulate Growth</span>
                        </button>
                    </div>
                </div>

                <div id="autoV2PreviewContainer" class="hidden mt-6 space-y-4">
                    <div class="flex items-center gap-3">
                        <div class="h-px flex-1 bg-brand/5"></div>
                        <div class="text-[9px] font-black text-text-muted uppercase tracking-[0.3em] px-2 flex items-center gap-2">
                             <span class="w-1.5 h-1.5 rounded-full bg-accent animate-pulse"></span> Guidance Preview
                        </div>
                        <div class="h-px flex-1 bg-brand/5"></div>
                    </div>
                    
                    <div id="autoV2VisualPreview" class="hidden rounded-2xl overflow-hidden border border-brand/5 bg-cream/50 p-4">
                         <div class="flex items-center gap-4">
                              <div id="visualStyleSwatch" class="w-16 h-16 rounded-xl shadow-inner border border-white/20"></div>
                              <div class="flex-1">
                                   <div id="visualStyleName" class="text-[11px] font-black text-brand uppercase tracking-widest">Dark Sacred</div>
                                   <div id="visualStyleDesc" class="text-[9px] text-text-muted font-medium italic mt-1">Aesthetic direction based on selected Style DNA.</div>
                              </div>
                         </div>
                    </div>

                    <div id="autoV2PreviewContent" class="grid grid-cols-1 md:grid-cols-2 gap-4"></div>
                </div>
            </form>
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
  <title>{title} | Sabeel Studio</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          colors: {{ brand: '#0F3D2E', 'brand-hover': '#0A2D22', accent: '#C9A96E', 'text-main': '#1A1A1A', 'text-muted': '#6B6B6B', cream: '#F8F6F2' }}
        }}
      }}
    }}
  </script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>
    :root {{ 
      --brand: #0F3D2E; 
      --brand-hover: #0A2D22; 
      --main-bg: #F8F6F2; 
      --surface: #FFFFFF; 
      --accent: #C9A96E; 
      --text-main: #1A1A1A; 
      --text-muted: #6B6B6B; 
      --border: rgba(15, 61, 46, 0.08); 
    }}
    body {{ font-family: 'Inter', sans-serif; background-color: var(--main-bg); color: var(--text-main); -webkit-font-smoothing: antialiased; }}
    
    /* Premium Design System */
    .card {{ background: #FFFFFF; border: 1px solid var(--border); box-shadow: 0 1px 4px rgba(15, 61, 46, 0.02); border-radius: 20px; transition: all 250ms cubic-bezier(0.16, 1, 0.3, 1); }}
    .card:hover {{ transform: translateY(-3px); box-shadow: 0 12px 32px rgba(15, 61, 46, 0.08); border-color: rgba(15,61,46,0.12); }}
    
    .nav-link.active {{ color: var(--brand); border-bottom: 2px solid var(--brand); font-weight: 900; }}
    .nav-link {{ transition: all 150ms ease; border-bottom: 2px solid transparent; color: var(--text-muted); opacity: 0.65; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.15em; }}
    .nav-link:hover {{ color: var(--brand); opacity: 1; }}
    
    .heading-premium {{ font-family: 'Inter', sans-serif !important; font-weight: 950 !important; font-style: italic !important; letter-spacing: -0.05em !important; color: var(--brand) !important; line-height: 0.9 !important; }}
    .text-premium-muted {{ font-size: 13px; font-weight: 500; font-style: italic; color: var(--text-muted); opacity: 0.8; }}
    .badge-premium {{ font-size: 9px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.3em; color: var(--brand); opacity: 0.4; }}
    
    /* Utility Overrides for Brand */
    .bg-brand-premium {{ background-color: var(--brand) !important; }}
    .bg-brand {{ background-color: var(--brand) !important; }}
    .bg-brand-hover {{ background-color: var(--brand-hover) !important; }}
    .text-brand {{ color: var(--brand) !important; }}
    .border-brand {{ border-color: var(--brand) !important; }}
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
          <a href="/app/automations" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_automations}">Reminder Streams</a>
          <a href="/app/library" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_library}">Knowledge Library</a>
          <a href="/app/media" class="text-[10px] font-bold uppercase tracking-widest nav-link py-5 {active_media}">Visual Library</a>
          {admin_link}
        </div>
      </div>
      <div class="flex items-center gap-4">
        <!-- Account Switcher Integration -->
        <div id="navbarAccountSwitcher" class="relative">
            {navbar_account_switcher}
        </div>
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
    async function logout() {{ await fetch('/auth/logout', {{ method: 'POST' }}); window.location.href = '/'; }}
  </script>
  {studio_modal}
  {connect_instagram_modal}
  {extra_js}
  {studio_js}
</body>
</html>
"""

GET_STARTED_CARD_HTML = """<div id="gettingStartedCard" class="card shadow-2xl shadow-brand/[0.03] p-10 md:p-14 mb-12 animate-in slide-in-from-top-6 duration-700 bg-white relative overflow-hidden">
  <div class="absolute top-0 right-0 w-64 h-64 bg-brand/[0.01] rounded-full -mr-32 -mt-32"></div>
  <div class="flex justify-between items-start mb-10 relative">
    <div>
      <h3 class="heading-premium text-4xl md:text-5xl">Assalamu Alaykum, <span class="text-accent">{user_name}</span></h3>
      <p class="text-premium-muted mt-3">Your dedicated space for meaningful reminders is now ready.</p>
    </div>
  </div>
  <div class="grid grid-cols-1 md:grid-cols-1 gap-8 relative">
    <div class="card p-10 border-brand/10 bg-brand/[0.02] flex flex-col md:flex-row justify-between items-center group cursor-pointer hover:bg-brand/[0.04]" onclick="openNewPostModal()">
      <div class="space-y-2 text-center md:text-left">
          <h4 class="text-2xl font-black text-brand tracking-tight italic">Craft your first reminder</h4>
          <p class="text-[11px] font-bold text-text-muted uppercase tracking-widest">Ignite the spark of guidance</p>
      </div>
      <div class="mt-6 md:mt-0 px-8 py-4 bg-brand text-white rounded-2xl text-[10px] font-black uppercase tracking-[0.2em] shadow-xl shadow-brand/20 group-hover:translate-x-2 transition-all">Begin Your Reminder &rarr;</div>
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
