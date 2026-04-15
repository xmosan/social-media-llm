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
            <script>
                async function disconnectMetaAccount() {{
                    if (!confirm("Are you sure you want to disconnect this Instagram account?")) return;
                    const res = await fetch('/auth/instagram/disconnect', {{ method: 'POST' }});
                    const data = await res.json();
                    if (data.ok) window.location.reload();
                    else alert(data.error || "Failed to disconnect");
                }}
            </script>
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
    <script>
      // --- GLOBAL ERROR HANDLING ---
      function showDebugError(msg) {
          const deb = document.getElementById('libraryDebugger');
          const txt = document.getElementById('debugMessage');
          if (deb && txt) {
              txt.textContent = msg;
              deb.classList.remove('hidden');
          }
      }
      window.onerror = (msg, url, line) => {
          console.error("[LIBRARY_CRASH]", msg, "at", line);
          showDebugError(`Runtime Error: ${msg} (Line ${line})`);
      };
      window.onunhandledrejection = (e) => {
          console.error("[LIBRARY_REJECTION]", e);
          showDebugError(`Promise Failure: ${e.reason}`);
      };

      // --- INITIALIZATION ---
      window.isSabeelAdmin = "{is_superadmin_js}" === "true";
      window.sabeelOrgId = parseInt("{org_id_js}" || "0");
      let libraryEntries = {}; 
      let currentSourceId = null;
      let showGlobalOnly = true;
      let entrySearchTimeout = null;
      let currentView = 'browse_surahs'; 

      window.addEventListener('DOMContentLoaded', async () => {
          console.log("Library System: Initializing [Total Reset Mode]");
          await loadSources();
          await loadSurahs();
          await loadRecommendations();
          
          // Sync UI toggles
          const orgBtn = document.getElementById('orgViewBtn');
          const globalBtn = document.getElementById('globalViewBtn');
          const activeClass = "flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter bg-brand text-white shadow-md transition-all";
          const inactiveClass = "flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter text-brand/40 hover:text-brand transition-all";
          if (globalBtn) globalBtn.className = showGlobalOnly ? activeClass : inactiveClass;
          if (orgBtn) orgBtn.className = !showGlobalOnly ? activeClass : inactiveClass;
      });

      function normalizeLibraryEntry(raw) {
          if (!raw) return null;
          return {
              id: raw.id ?? Math.random().toString(36).substr(2, 9),
              item_type: raw.item_type || raw.type || "unknown",
              title: raw.reference || raw.title || "Untitled",
              reference: raw.reference || raw.title || "Untitled",
              text: raw.translation_text || raw.text || raw.content || "",
              arabic_text: raw.arabic_text || "",
              topics: Array.isArray(raw.topics) ? raw.topics : (raw.topics ? [raw.topics] : []),
              meta: raw.meta || {},
              surah_number: raw.surah_number || raw.meta?.surah_number,
              ayah_number: raw.ayah_number || raw.meta?.ayah_number
          };
      }

      function showView(view, data = null) {
          currentView = view;
          const list = document.getElementById('entryList');
          const breadcrumbChild = document.getElementById('libraryBreadcrumbChild');
          const breadcrumbName = document.getElementById('libraryBreadcrumbName');
          
          if (view === 'browse_surahs') {
              if (breadcrumbChild) breadcrumbChild.classList.add('hidden');
              if (breadcrumbName) breadcrumbName.textContent = '';
              loadSurahs();
          } else if (view === 'surah_reading' && data) {
              if (breadcrumbChild) breadcrumbChild.classList.remove('hidden');
              if (breadcrumbName) breadcrumbName.textContent = data.name;
              loadSurahVerses(data.number);
          } else if (view === 'collection_view' && data) {
              if (breadcrumbChild) breadcrumbChild.classList.remove('hidden');
              if (breadcrumbName) breadcrumbName.textContent = data.name;
              loadEntries();
          }
      }

      async function loadSurahs() {
          const canvas = document.getElementById('entryList');
          if (!canvas) return;
          canvas.innerHTML = '<div class="col-span-full py-20 text-center animate-pulse text-[10px] font-black text-brand uppercase tracking-widest">Manifesting Wisdom...</div>';

          try {
              const res = await fetch('/api/quran/surahs');
              const data = await res.json();
              canvas.className = "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 pb-20";
              canvas.innerHTML = data.map(s => {
                  return `
                  <div onclick="showView('surah_reading', {number: ${s.number}, name: '${s.name_en}'})" class="surah-card p-8 rounded-[2.5rem] cursor-pointer group flex items-center justify-between">
                    <div class="flex items-center gap-6">
                        <div class="w-12 h-12 rounded-2xl bg-brand/5 border border-brand/10 text-brand flex items-center justify-center text-[11px] font-black group-hover:bg-brand group-hover:text-white transition-all">${s.number}</div>
                        <div class="text-left">
                            <h4 class="text-sm font-black text-text-main group-hover:text-brand transition-colors">${s.name_en}</h4>
                            <p class="text-[9px] font-bold text-text-muted/40 uppercase tracking-widest">${s.verses_count} Verses</p>
                        </div>
                    </div>
                    <div class="text-2xl font-serif text-brand/10 group-hover:text-brand transition-colors">${s.name_ar}</div>
                  </div>
                `;
              }).join('');
          } catch(e) { canvas.innerHTML = 'Error loading surahs.'; }
      }

      async function loadSurahVerses(num) {
          const canvas = document.getElementById('entryList');
          canvas.innerHTML = '<div class="py-20 text-center animate-pulse text-[10px] font-black text-brand uppercase tracking-widest">Exposing Neural Nodes...</div>';
          try {
              const res = await fetch(`/api/quran/surahs/${num}`);
              const surah = await res.json();
              canvas.className = "flex flex-col gap-8 pb-32";
              canvas.innerHTML = surah.verses.map(v => {
                  libraryEntries[v.id] = v;
                  return `
                  <div class="verse-card bg-white p-12 rounded-[3rem] border border-brand/5 group relative">
                    <div class="absolute top-8 right-10 opacity-0 group-hover:opacity-100 transition-all z-10">
                        <button onclick='useInQuoteCard(${v.id})' class="px-6 py-3 bg-brand text-white rounded-2xl text-[9px] font-black uppercase tracking-widest hover:scale-105 transition-all">Manifest</button>
                    </div>
                    <div class="flex flex-col md:flex-row justify-between items-start gap-10">
                        <div class="w-10 h-10 rounded-xl bg-brand/5 border border-brand/10 flex items-center justify-center text-[10px] font-black text-brand">${v.ayah_number}</div>
                        <p class="dir-rtl font-serif text-3xl text-right flex-1 leading-[2.5]">${v.arabic_text}</p>
                    </div>
                    <p class="text-text-main/90 text-lg leading-relaxed mt-8 pl-20 font-medium">${v.translation_text}</p>
                  </div>
                `;
              }).join('');
          } catch(e) { canvas.innerHTML = 'Error loading verses.'; }
      }

      async function loadSources() {
          const list = document.getElementById('sourceList');
          if (!list) return;
          try {
              const url = showGlobalOnly ? '/api/quran/surahs' : '/library/sources';
              const res = await fetch(url);
              const data = await res.json();
              
              if (showGlobalOnly) {
                  list.innerHTML = `
                    <div onclick="showView('browse_surahs')" class="p-4 px-6 rounded-2xl cursor-pointer bg-brand/5 border-brand/20 border flex items-center gap-4 group">
                        <div class="w-10 h-10 rounded-2xl bg-brand text-white flex items-center justify-center">🏛️</div>
                        <div class="text-left"><div class="text-[10px] font-black text-brand uppercase">Quran Foundation</div><div class="text-[7px] text-text-muted uppercase">Global Wisdom</div></div>
                    </div>
                  `;
                  return;
              }
              
              list.innerHTML = data.map(s => {
                  return `
                  <div onclick="filterBySource(${s.id})" class="p-4 px-6 rounded-2xl cursor-pointer border hover:bg-brand/5 transition-all border-transparent hover:border-brand/10 flex items-center gap-4 group">
                      <div class="w-10 h-10 rounded-2xl bg-brand/5 text-brand flex items-center justify-center uppercase font-black text-[10px]">${(s.name || 'C').substring(0,1)}</div>
                      <div class="text-left overflow-hidden">
                          <div class="text-[10px] font-black truncate uppercase text-brand">${s.name || 'Untitled'}</div>
                          <div class="text-[7px] font-bold text-text-muted uppercase">${s.items_count || 0} Entries</div>
                      </div>
                  </div>
                `;
              }).join('');
          } catch(e) { list.innerHTML = 'Sources Offline'; }
      }

      function useInQuoteCard(id) {
          const entry = libraryEntries[id];
          if (!entry) return;
          sessionStorage.setItem('sabeel_pending_quote_item', JSON.stringify({
              id: entry.id,
              type: 'quran_verse',
              text: entry.translation_text || entry.text,
              arabic_text: entry.arabic_text,
              reference: entry.reference || `${entry.surah_name_en} ${entry.ayah_number}`
          }));

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
          const area = document.getElementById('entryText');
          const counter = document.getElementById('charCount');
          if (area && counter) {
              const text = area.value;
              counter.textContent = `${text.length} / 3000`;
          }
      }

      function setEntryType(type, element) {
          const typeInput = document.getElementById('entryType');
          if (typeInput) typeInput.value = type;
          
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
          const select = document.getElementById('sourceSelect');
          if (!select) return;
          const val = select.value;
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
          console.log("View Switch:", global ? 'System' : 'Org');
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
          
          // Parallel non-blocking refresh
          Promise.allSettled([loadSources(), loadEntries()]).then(() => {
              console.log("View manifested successfully");
          });
      }

      function openEntryModalById(id) {
          const entry = libraryEntries[id];
          if (!entry) return;
          
          const idInput = document.getElementById('entryId');
          const area = document.getElementById('entryText');
          const title = document.getElementById('entryModalTitle');
          const globalCheck = document.getElementById('isGlobalCheckbox');
          const sourceSelect = document.getElementById('sourceSelect');
          const modal = document.getElementById('entryModal');

          if (idInput) idInput.value = entry.id;
          if (area) area.value = entry.text || '';
          if (title) title.innerHTML = `Edit <span class="text-accent">${(entry.item_type || 'Knowledge').toUpperCase()}</span>`;
          
          // Set type
          const type = entry.item_type || 'note';
          const typeBtn = document.querySelector(`.type-btn[onclick*="'${type}'"]`);
          setEntryType(type, typeBtn);

          // Meta / Global
          if (globalCheck) globalCheck.checked = entry.meta?.is_global === true;

          // Select source
          if (sourceSelect) sourceSelect.value = entry.source_id || '';
          checkNewSource();

          if (modal) modal.classList.remove('hidden');
          updateCharCount();
      }

      function openEntryModal() {
          const idInput = document.getElementById('entryId');
          const area = document.getElementById('entryText');
          const title = document.getElementById('entryModalTitle');
          const modal = document.getElementById('entryModal');

          if (idInput) idInput.value = '';
          if (area) area.value = '';
          if (title) title.innerHTML = `Add <span class="text-accent">Knowledge</span>`;
          if (modal) modal.classList.remove('hidden');
          
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
                  if (confirm("Suggested Topic: " + suggestion + "\\nApply filter?")) {
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
