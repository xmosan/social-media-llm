    </div>

    <script>
      // --- GLOBAL ERROR HANDLING (Top Level) ---
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
          console.error("[LIBRARY_HANG]", e);
          showDebugError(`Network Hang: ${e.reason}`);
      };

      console.log("Library System: Ready");
      window.isSabeelAdmin = "{is_superadmin_js}" === "true";
      window.sabeelOrgId = parseInt("{org_id_js}" || "0");
      let libraryEntries = {}; 
      let currentSourceId = null;
      let showGlobalOnly = true;
      let entrySearchTimeout = null;
      let selectedTopic = null;
      let currentView = 'browse_surahs'; 

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
          console.log("Library System: Initializing [Ultra-Hardened Mode]");
          
          const list = document.getElementById('entryList');
          if (list) {
              list.innerHTML = `
                <div class="col-span-full py-20 flex flex-col items-center justify-center space-y-4">
                    <div class="w-16 h-16 border-4 border-brand/10 border-t-brand rounded-full animate-spin"></div>
                    <div class="text-[10px] font-black text-brand uppercase tracking-widest animate-pulse">Manifesting Wisdom...</div>
                </div>
              `;
          }

          try {
              // Forced sync of buttons to match default state
              const orgBtn = document.getElementById('orgViewBtn');
              const globalBtn = document.getElementById('globalViewBtn');
              const activeClass = "flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter bg-brand text-white shadow-md transition-all";
              const inactiveClass = "flex-1 py-1.5 rounded-lg text-[8px] font-black uppercase tracking-tighter text-brand/40 hover:text-brand transition-all";
              
              if (globalBtn) globalBtn.className = showGlobalOnly ? activeClass : inactiveClass;
              if (orgBtn) orgBtn.className = !showGlobalOnly ? activeClass : inactiveClass;

              // 1. Load Sources
              await loadSources();
              
              // 2. Load Initial View
              await loadSurahs();
              
              console.log("Library System: Manifestation Complete");
          } catch (e) {
              console.error("Library System: Initialization Blocked", e);
              showDebugError(`Init Blocked: ${e.message}`);
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

      // --- GLOBAL ERROR HANDLING ---
      window.onerror = function(msg, url, line) {
          const debug = document.getElementById('libraryDebugger');
          const msgEl = document.getElementById('debugMessage');
          if (debug && msgEl) {
              debug.classList.remove('hidden');
              msgEl.textContent = `JS Error: ${msg} (Line ${line})`;
          }
      };

      window.onunhandledrejection = function(event) {
          const debug = document.getElementById('libraryDebugger');
          const msgEl = document.getElementById('debugMessage');
          if (debug && msgEl) {
              debug.classList.remove('hidden');
              msgEl.textContent = `Promise Failed: ${event.reason}`;
          }
      };

      function showView(view, data = null) {
          currentView = view;
          const list = document.getElementById('entryList');
          const breadcrumbChild = document.getElementById('libraryBreadcrumbChild');
          const breadcrumbName = document.getElementById('libraryBreadcrumbName');
          
          if (view === 'browse_surahs') {
              const searchInput = document.getElementById('entrySearch');
              if (searchInput) searchInput.value = '';
              
              if (breadcrumbChild) breadcrumbChild.classList.add('hidden');
              if (breadcrumbName) breadcrumbName.textContent = '';
              
              if (showGlobalOnly) {
                  loadSurahs();
              } else {
                  if (list) list.innerHTML = `
                    <div class="flex flex-col items-center justify-center p-20 text-center space-y-4">
                        <div class="w-16 h-16 rounded-full bg-brand/5 flex items-center justify-center text-2xl">📁</div>
                        <div class="space-y-1">
                            <div class="text-[10px] font-black text-brand uppercase tracking-widest">Your Wisdom Space</div>
                            <div class="text-[8px] text-text-muted uppercase">Select a collection from the sidebar or switch to System view</div>
                        </div>
                    </div>
                  `;
              }
          }
          if (view === 'surah_reading' && data) {
              if (breadcrumbChild) breadcrumbChild.classList.remove('hidden');
              if (breadcrumbName) breadcrumbName.textContent = data.name;
              loadSurahVerses(data.number);
          }
          if (view === 'collection_view' && data) {
              if (breadcrumbChild) breadcrumbChild.classList.remove('hidden');
              if (breadcrumbName) breadcrumbName.textContent = data.name;
              loadEntries();
          }
          if (view === 'search_results') {
              if (breadcrumbChild) breadcrumbChild.classList.remove('hidden');
              if (breadcrumbName) breadcrumbName.textContent = 'Search Results';
          }
      }

      async function loadSurahs() {
          const canvas = document.getElementById('entryList');
          if (!canvas) return;
          
          // High-contrast Loading State
          canvas.className = "flex flex-col items-center justify-center space-y-8 py-32";
          canvas.innerHTML = `
            <div class="flex flex-col items-center gap-6 animate-pulse">
                <div class="w-16 h-16 rounded-3xl bg-brand/5 border border-brand/10 flex items-center justify-center text-3xl">📖</div>
                <div class="space-y-2 text-center">
                    <div class="text-[10px] font-black text-brand uppercase tracking-[0.5em]">Sabeel Foundation</div>
                    <div class="text-[8px] font-bold text-text-muted uppercase tracking-widest">Synchronizing Scripture Database...</div>
                </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 w-full max-w-6xl px-12">
                ${Array(6).fill(0).map(() => `<div class="skeleton h-32 rounded-[2.5rem] bg-white border border-brand/5"></div>`).join('')}
            </div>
          `;

          try {
              console.log("Fetching surahs...");
              const res = await fetch('/api/quran/surahs');
              
              const contentType = res.headers.get("content-type");
              if (contentType && contentType.includes("text/html")) {
                  console.error("API Error: Received HTML instead of JSON (Redirect detected)");
                  showDebugError("Foundation Access Blocked: API Redirected to Login/Landing");
                  throw new Error("API_REDIRECTED");
              }

              const surahs = await res.json();
              
              if (!surahs || !Array.isArray(surahs) || surahs.length === 0) {
                  canvas.className = "flex flex-col items-center justify-center p-32 text-center space-y-6";
                  canvas.innerHTML = `
                    <div class="w-20 h-20 rounded-full bg-rose-50 flex items-center justify-center text-3xl">⚠️</div>
                    <div class="space-y-1">
                        <div class="text-[10px] font-black text-rose-500 uppercase tracking-widest">Foundation Offline</div>
                        <div class="text-[8px] text-text-muted uppercase max-w-xs mx-auto">The Quranic database is currently unreachable or empty. Please ensure your organization has successfully synced with the Sabeel Global Index.</div>
                    </div>
                  `;
                  return;
              }

              canvas.className = "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 pb-20";
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
              
              const contentType = res.headers.get("content-type");
              if (contentType && contentType.includes("text/html")) {
                  console.error("[LIBRARY] Sources API returned HTML. Check middleware whitelist.");
                  showDebugError("Sources Access Blocked (HTML Redirect)");
                  list.innerHTML = `<div class="p-8 text-center text-rose-400 font-bold text-[8px] uppercase tracking-widest">Network Blocked</div>`;
                  return;
              }

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
