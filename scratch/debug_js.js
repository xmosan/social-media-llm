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
    
    // Helpers
    const hide = (id) => { const el = document.getElementById(id); if(el) el.classList.add('hidden'); };
    const show = (id) => { const el = document.getElementById(id); if(el) el.classList.remove('hidden'); };

    // Structured State
    let studioCardMessage = null; // { eyebrow, headline, supporting_text }
    let studioCaptionMessage = null; // { hook, body, cta, hashtags }

    // ── Shared Source-of-Truth (Phase 1 → 2 → 3) ──────────────────────────────
    // Single canonical object for the selected source.
    // Set by selectAyah() / _applyHadithSelection().
    // Read by generateSocialCaption() — never re-derived from topic string.
    window.studioSourceContext = null;

    function _setSourceContext(ctx) {
        window.studioSourceContext = ctx;
        // Update the Phase 3 grounding badge whenever source changes
        _renderGroundingBadge();
    }

    function _renderGroundingBadge() {
        const badge = document.getElementById('presenceGroundingBadge');
        const label = document.getElementById('presenceSourceLabel');
        if (!badge || !label) return;
        const ctx = window.studioSourceContext;
        if (ctx && ctx.reference) {
            label.textContent = ctx.reference;
            badge.classList.remove('hidden');
        } else {
            badge.classList.add('hidden');
        }
    }

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
        window.studioSourceContext = null;

        // Reset Physical Elements
        const setVal = (id, v) => { const el = document.getElementById(id); if(el) el.value = v; };

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
        
        // Initialize UI states
        if (typeof updateBuildButtonState === 'function') {
            updateBuildButtonState();
        }
    };

    window.openNewPostModal = function() {
        console.log("[Sabeel Studio] Opening Modal...");
        window.resetStudioSession();
        const modal = document.getElementById('newPostModal');
        if (modal) {
            modal.style.display = 'flex';
            modal.classList.remove('hidden');
        }
        window.switchStudioSection(1);
    }

    window.closeNewPostModal = function() {
        const modal = document.getElementById('newPostModal');
        if (modal) {
            modal.classList.add('hidden');
            modal.style.display = 'none';
        }
        window.resetStudioSession();
    }

    window.switchStudioSection = function(stepIndex) {
        if (stepIndex === 2 && !studioCardMessage) {
            alert("Please build your card message first.");
            return;
        }
        if (stepIndex === 4) {
            const manualCaption = document.getElementById('studioCaption')?.value || "";
            if (!currentQuoteCardUrl || (!studioCaptionMessage && !manualCaption)) {
                alert("Please ensure your visual and caption are ready before moving to Share.");
                return;
            }
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

        // Phase 3: wire mini card thumbnail and re-render grounding badge
        if (stepIndex === 3) {
            _renderGroundingBadge();
            const thumb = document.getElementById('presenceCardThumbImg');
            const thumbContainer = document.getElementById('presenceCardThumb');
            if (thumb && thumbContainer && currentQuoteCardUrl) {
                thumb.src = currentQuoteCardUrl;
                thumbContainer.classList.remove('hidden');
            }
        }
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

    let searchDebounceTimeout = null;
    function onSourceInput() {
        updateBuildButtonState();
        clearTimeout(searchDebounceTimeout);
        searchDebounceTimeout = setTimeout(() => {
            if (activeSourceTab === 'quran') searchQuran();
            else searchHadith();
        }, 300);
    }
    
    function updateBuildButtonState() {
        const topic = document.getElementById('studioTopic').value.trim();
        const btn = document.getElementById('btnBuildMessage');
        const hasSelection = selectedAyahId || selectedHadithId;
        const hasManual = topic.length >= 2;
        
        if (hasSelection || hasManual) {
            btn.classList.remove('opacity-50', 'cursor-not-allowed', 'grayscale');
            btn.classList.add('hover:scale-[1.01]', 'shadow-brand/20');
            btn.disabled = false;
        } else {
            btn.classList.add('opacity-50', 'cursor-not-allowed', 'grayscale');
            btn.classList.remove('hover:scale-[1.01]', 'shadow-brand/20');
            btn.disabled = true;
        }
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
            if (!res.ok) {
                const err = await res.json().catch(()=>({}));
                resultsArea.innerHTML = `<div class="p-4 text-center text-[10px] font-bold text-red-500 uppercase tracking-widest">Error: ${err.detail || res.statusText}</div>`;
                return;
            }
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
        // Populate the shared source-of-truth for Phase 3
        _setSourceContext({ type: 'hadith', reference: meta.reference || '', ...meta });
        document.getElementById('selectedHadithBadge').classList.remove('hidden');
        document.getElementById('selectedAyahBadge').classList.add('hidden');
        document.getElementById('selectedHadithTitle').innerText = meta.reference || '';
        document.getElementById('hadithSearchResults').classList.add('hidden');
        document.getElementById('studioTopic').value = meta.reference || '';
        updateBuildButtonState();

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
            if (!res.ok) {
                const err = await res.json().catch(()=>({}));
                resultsArea.innerHTML = `<div class="p-4 text-center text-[10px] font-bold text-red-500 uppercase tracking-widest">Error: ${err.detail || res.statusText}</div>`;
                return;
            }
            const data = await res.json();
            if (!Array.isArray(data) || data.length === 0) { resultsArea.classList.add('hidden'); return; }
            resultsArea.innerHTML = data.map(v => {
                const ref = v.reference || v.title || '';
                const txt = v.translation_text || v.text || '';
                
                const metaJson = JSON.stringify({
                    id: v.id,
                    reference: ref,
                    translation_text: txt,
                    arabic_text: v.arabic_text || ''
                }).replace(/"/g, '&quot;');
                
                return `
                <div data-meta="${metaJson}" onclick="selectAyahFromEl(this)" class="p-4 border-b border-brand/5 hover:bg-brand/5 cursor-pointer transition-all">
                    <div class="flex justify-between items-start mb-1">
                        <span class="text-[8px] font-black text-brand uppercase tracking-widest">${ref}</span>
                    </div>
                    <div class="text-[10px] text-text-muted font-medium italic line-clamp-2">${txt}</div>
                </div>`;
            }).join('');
        } catch (e) {
            console.error('[STUDIO_QURAN] fetch/parse error:', e);
            resultsArea.innerHTML = `<div class="p-4 text-center text-[10px] font-bold text-red-500 uppercase tracking-widest">Error loading results</div>`;
        }
    }

    window.selectedAyahMetadata = null;

    function selectAyahFromEl(el) {
        try {
            const raw = el.getAttribute('data-meta');
            const meta = JSON.parse(raw.replace(/&quot;/g, '"'));
            selectAyah(meta.id, meta.reference, meta.translation_text, meta.arabic_text);
        } catch(e) {
            console.error('[Studio] selectAyahFromEl parse error:', e);
        }
    }

    function selectAyah(id, title, text, arabic_text = '') {
        selectedAyahId = id;
        selectedHadithId = null;
        window.selectedAyahMetadata = { reference: title, translation_text: text, arabic_text: arabic_text, id: id };
        // Populate the shared source-of-truth for Phase 3
        _setSourceContext({ type: 'quran', reference: title, translation_text: text, arabic_text: arabic_text, id: id });
        document.getElementById('selectedAyahBadge').classList.remove('hidden');
        document.getElementById('selectedHadithBadge').classList.add('hidden');
        document.getElementById('selectedAyahTitle').innerText = title;
        document.getElementById('quranSearchResults').classList.add('hidden');
        document.getElementById('studioTopic').value = title;
        updateBuildButtonState();
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

            if (selectedAyahId) {
                sourceType = 'quran';
                sourcePayload = window.selectedAyahMetadata;
            } else if (selectedHadithId) {
                sourceType = 'hadith';
                sourcePayload = window.selectedHadithMetadata;
            }

            const customPrompt = document.getElementById('studioCustomPrompt')?.value || "";

            const payload = {
                source_type: sourceType,
                source_payload: sourcePayload,
                tone: tone,
                intent: intention,
                custom_payload: {
                    custom_prompt: customPrompt
                }
            };

            const res = await fetch('/api/studio/generate-card-message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.card_message) {
                studioCardMessage = data.card_message;
                document.getElementById('editEyebrow').value = studioCardMessage.eyebrow || '';
                document.getElementById('editHeadline').value = studioCardMessage.headline || '';
                document.getElementById('editSupporting').value = studioCardMessage.supporting_text || '';
                document.getElementById('cardMessageWorkspace').classList.remove('hidden');
                invalidateQuoteCard();
                
                // Automatically advance to Phase 2
                switchStudioSection(2);
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

    window.generateQuoteCard = async function() {
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
                style: studioGalleryImage ? studioGalleryImage : document.getElementById('studioStyle').value,
                visual_prompt: document.getElementById('studioCustomDirection')?.value,
                text_style_prompt: document.getElementById('studioTextStylePrompt')?.value,
                engine: studioEngine,
                glossy: studioGlossy,
                mode: studioGalleryImage ? 'gallery' : 'scene'
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
            btn.innerText = 'Generate Cinematic Visual';
        }
    }

    window.generateSocialCaption = async function() {
        const btn = document.getElementById('btnGenerateCaption');
        const icon = btn.querySelector('.btn-icon');
        const text = btn.querySelector('.btn-text');
        const driftWarning = document.getElementById('presenceDriftWarning');

        btn.disabled = true;
        if(icon) icon.classList.add('animate-spin');
        if(text) text.innerText = 'Crafting Presence...';
        if(driftWarning) driftWarning.classList.add('hidden');

        try {
            // ── Read from the single shared source-of-truth ───────────────────
            // studioSourceContext is set by selectAyah() / _applyHadithSelection().
            // It carries exactly what was used to build the card, preventing drift.
            const ctx = window.studioSourceContext;

            let srcType = 'manual';
            let srcPayload = { text: studioCardMessage ? (studioCardMessage.headline || '') : '' };

            if (ctx && ctx.type === 'hadith') {
                srcType = 'hadith';
                srcPayload = ctx;
            } else if (ctx && ctx.type === 'quran') {
                srcType = 'quran';
                srcPayload = ctx;
            } else if (!ctx) {
                // No source context — show the no-source warning in the UI
                const noSrc = document.getElementById('presenceNoSourceWarning');
                if (noSrc) noSrc.classList.remove('hidden');
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
            let captionText = '';
            if (data.caption_message) {
                studioCaptionMessage = data.caption_message;
                captionText = `${studioCaptionMessage.hook || ''}\n\n${studioCaptionMessage.body || ''}\n\n${studioCaptionMessage.cta || ''}\n\n${(studioCaptionMessage.hashtags || []).join(' ')}`;
            } else if (data.caption) {
                studioCaptionMessage = { caption: data.caption };
                captionText = data.caption;
            }

            if (captionText) {
                captionText = captionText.trim();
                document.getElementById('studioCaption').value = captionText;
                document.getElementById('captionResultArea').classList.remove('hidden');

                // ── Render the premium caption preview ───────────────────────
                _renderCaptionPreview(captionText);

                // ── Soft drift validation ─────────────────────────────────────
                if (ctx && ctx.reference && driftWarning) {
                    // Check if the expected reference appears anywhere in the caption
                    // Extract key identifiers (e.g. "94:5" from "Qur'an 94:5")
                    const refParts = ctx.reference.replace(/[^0-9:a-zA-Z]/g, ' ').trim().split(/\s+/).filter(p => p.length > 1);
                    const captionLower = captionText.toLowerCase();
                    const isGrounded = refParts.some(part => captionLower.includes(part.toLowerCase()));
                    if (!isGrounded) {
                        driftWarning.classList.remove('hidden');
                    }
                }
            }
        } catch (e) {
            console.error('[Studio Phase 3] Caption generation failed:', e);
            alert('Caption generation failed. Please try again.');
        } finally {
            btn.disabled = false;
            if(icon) icon.classList.remove('animate-spin');
            if(text) text.innerText = 'Generate Caption';
        }
    }

    function _renderCaptionPreview(captionText) {
        const preview = document.getElementById('captionPreviewBlock');
        if (!preview) return;
        // Split on double newlines into structured lines
        const lines = captionText.split(/\n\n+/).map(l => l.trim()).filter(Boolean);
        if (lines.length === 0) return;

        let html = '';
        if (lines[0]) html += `<p class="text-[11px] font-bold text-brand leading-relaxed">${lines[0].replace(/\n/g, '<br>')}</p>`;
        if (lines[1]) html += `<p class="text-[11px] font-medium text-text-muted italic leading-relaxed mt-3">${lines[1].replace(/\n/g, '<br>')}</p>`;
        if (lines[2]) html += `<p class="text-[11px] font-black text-brand/80 leading-relaxed mt-3">${lines[2].replace(/\n/g, '<br>')}</p>`;
        if (lines.length > 3) {
            html += `<p class="text-[9px] font-bold text-accent/70 mt-4">${lines.slice(3).join('  ')}</p>`;
        }
        preview.innerHTML = html;
        preview.closest('#captionPreviewContainer')?.classList.remove('hidden');
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
        studioSceneKey = null; // Clear any scene selection
        document.querySelectorAll('.style-card').forEach(c => c.classList.remove('active'));
        el.closest('.style-card').classList.add('active');
        invalidateQuoteCard();
    }

    let studioGalleryImage = null; // null = generate, non-null = bypass DALL-E

    function setStudioScene(sceneKey, el) {
        studioGalleryImage = null;
        document.querySelectorAll('.gallery-thumb').forEach(c => c.classList.remove('border-brand', 'ring-2', 'ring-brand/20'));
        document.getElementById('studioStyle').value = sceneKey;
        document.querySelectorAll('.style-card').forEach(c => c.classList.remove('active'));
        el.closest('.style-card').classList.add('active');
        invalidateQuoteCard();
        // Instant Feedback: Automatically trigger regeneration when style is changed
        if (studioCardMessage) generateQuoteCard();
    }

    function setStudioGallery(filename, el) {
        studioGalleryImage = filename;
        // Visual feedback for gallery selection
        document.querySelectorAll('.style-card').forEach(c => c.classList.remove('active'));
        document.querySelectorAll('.gallery-thumb').forEach(c => c.classList.remove('border-brand', 'ring-2', 'ring-brand/20'));
        el.classList.add('border-brand', 'ring-2', 'ring-brand/20');
        invalidateQuoteCard();
        // Instant Feedback: Automatically trigger regeneration when gallery image is selected
        if (studioCardMessage) generateQuoteCard();
    }

    function setStudioEngine(engine, el) {
        studioEngine = engine;
        document.querySelectorAll('.engine-chip').forEach(c => c.classList.remove('active'));
        el.classList.add('active');
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

    window.submitNewPost = async function(event) {
        if (event) event.preventDefault();
        const btn = document.getElementById('studioSubmitBtn');
        const original = btn.innerText;

        if (isQuoteCardOutOfDate && !confirm("Your quote card no longer matches your latest message. Share anyway?")) {
            return;
        }

        btn.disabled = true;
        btn.innerHTML = 'PREPARING... <span class="animate-pulse">✨</span>';

        const accountId = document.getElementById('studioAccount').value;
        if (!accountId) {
            alert("Please select a target account before scheduling.");
            btn.innerText = original;
            btn.disabled = false;
            return;
        }
        
        const topicVal = document.getElementById('studioTopic').value;
        const editedCaption = document.getElementById('studioCaption').value;

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

        // If the user edited the caption, we should prioritize the edited text.
        // If studioCaptionMessage is an object, we keep it but update the body or similar if needed.
        // For simplicity, if edited, we send it as a plain string or wrap it.
        let finalCaptionMsg = studioCaptionMessage;
        if (editedCaption) {
            // If we have a structured object but the text is different from what was rendered,
            // the backend should probably just take the full string.
            finalCaptionMsg = editedCaption;
        }

        const reqPayload = {
            ig_account_id: parseInt(accountId, 10),
            visual_mode: 'quote_card',
            source_type: srcType,
            source_reference: srcReference,
            source_metadata: srcMetadata,
            topic: topicVal,
            card_message: studioCardMessage,
            caption_message: finalCaptionMsg,
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
                        selectAyah(item.id, item.reference, item.translation_text || item.text, item.arabic_text);
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
    window.approvePost = async function(id, event) {
        const btn = (event && event.target) ? event.target : {};
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
        const modal = document.getElementById('editPostModal');
        if (!modal) {
            alert("Refine feature is being optimized. Please use the Studio to create new reminders.");
            return;
        }
        document.getElementById('editPostId').value = id;
        const captionEl = document.getElementById('editPostCaption');
        if (captionEl) captionEl.value = caption || '';
        modal.classList.remove('hidden');
        modal.style.display = 'flex';
    };

    window.closeEditPostModal = function() {
        const modal = document.getElementById('editPostModal');
        if (modal) {
            modal.classList.add('hidden');
            modal.style.display = 'none';
        }
    };

    window.savePostEdit = async function() {
        const id = document.getElementById('editPostId')?.value;
        const caption = document.getElementById('editPostCaption')?.value;
        if (!id || !caption) return;
        try {
            const res = await fetch(`/posts/${id}`, {
                method: 'PATCH',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ caption })
            });
            if (res.ok) {
                window.closeEditPostModal();
                window.location.reload();
            } else {
                const data = await res.json().catch(() => ({}));
                alert('Save failed: ' + (data.detail || 'Unknown error'));
            }
        } catch (e) {
            alert('Connection error: ' + e.message);
        }
    };

    window.publishPostNow = async function() {
        const id = document.getElementById('editPostId')?.value;
        if (!id) return;
        const btn = document.getElementById('postNowBtn');
        const original = btn ? btn.innerText : '';
        if (btn) { btn.disabled = true; btn.innerText = 'SHARING...'; }
        try {
            // First save any edits
            const caption = document.getElementById('editPostCaption')?.value;
            if (caption) {
                await fetch(`/posts/${id}`, {
                    method: 'PATCH',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ caption })
                });
            }
            // Then publish
            const res = await fetch(`/posts/${id}/publish`, { method: 'POST' });
            if (res.ok) {
                window.closeEditPostModal();
                window.location.reload();
            } else {
                const data = await res.json().catch(() => ({}));
                alert('Publish failed: ' + (data.detail || 'Unknown error'));
            }
        } catch (e) {
            alert('Connection error: ' + e.message);
        } finally {
            if (btn) { btn.disabled = false; btn.innerText = original; }
        }
    };

    window.refinePostAI = async function(style) {
        const id = document.getElementById('editPostId')?.value;
        const captionEl = document.getElementById('editPostCaption');
        if (!id || !captionEl) return;
        const btns = document.querySelectorAll('.refine-ai-btn');
        btns.forEach(b => { b.disabled = true; });
        try {
            const res = await fetch(`/posts/${id}/refine`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ style, current_caption: captionEl.value })
            });
            if (res.ok) {
                const data = await res.json();
                if (data.caption) captionEl.value = data.caption;
            } else {
                const data = await res.json().catch(() => ({}));
                alert('Refinement failed: ' + (data.detail || 'Try again'));
            }
        } catch (e) {
            console.error('Refine error:', e);
        } finally {
            btns.forEach(b => { b.disabled = false; });
        }
    };

    window.showDeleteConfirm = function() {
        const actions = document.getElementById('editPostActions');
        const confirm = document.getElementById('deleteConfirmActions');
        if (actions) actions.classList.add('hidden');
        if (confirm) confirm.classList.remove('hidden');
    };

    window.hideDeleteConfirm = function() {
        const actions = document.getElementById('editPostActions');
        const confirm = document.getElementById('deleteConfirmActions');
        if (actions) actions.classList.remove('hidden');
        if (confirm) confirm.classList.add('hidden');
    };

</script>
