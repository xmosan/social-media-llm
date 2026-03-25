with open("app/routes/app_pages.py", "r") as f:
    text = f.read()

target_html = """            </div>
          </div>
          
          <!-- Topic Chips -->
          <div id="topicChips" class="px-8 py-3 border-b border-white/5 flex gap-3 overflow-x-auto hide-scrollbar bg-white/[0.01]\""""

replaced_html = """            </div>
          </div>
          
          <!-- RECOMMENDED TRACK -->
          <div id="recommendedTrackWrapper" class="hidden flex-col border-b border-white/5 bg-gradient-to-b from-brand/5 to-transparent shrink-0">
            <div class="px-6 md:px-8 py-3 flex items-center justify-between">
              <h3 class="text-[9px] font-black uppercase tracking-widest text-brand flex items-center gap-2">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143z"/></svg>
                Recommended For You
              </h3>
            </div>
            <div id="recommendedCards" class="flex gap-4 px-6 md:px-8 pb-4 overflow-x-auto hide-scrollbar">
              <!-- Loaded via JS -->
            </div>
          </div>

          <!-- Topic Chips -->
          <div id="topicChips" class="px-6 md:px-8 py-3 border-b border-white/5 flex gap-3 overflow-x-auto hide-scrollbar bg-white/[0.01]\""""
text = text.replace(target_html, replaced_html)

js_target = """      document.addEventListener("DOMContentLoaded", () => {
          loadSources();
          loadTopics();
          loadEntries();
      });"""

js_repl = """      document.addEventListener("DOMContentLoaded", () => {
          loadSources();
          loadTopics();
          loadEntries();
          loadRecommendations();
      });

      // ---- RECOMMENDATION ENGINE ----
      async function trackInteraction(actionType, entityId, contextId) {
          try {
              fetch('/library/track-use', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                      action_type: actionType,
                      entity_id: entityId,
                      context: contextId
                  })
              });
          } catch(e) {} // Silent background tracking
      }

      async function loadRecommendations() {
          try {
              const res = await fetch('/library/recommendations');
              if (!res.ok) return;
              const items = await res.json();
              
              const wrap = document.getElementById('recommendedTrackWrapper');
              const container = document.getElementById('recommendedCards');
              container.innerHTML = '';
              
              if (items.length === 0) {
                  wrap.classList.add('hidden');
                  return;
              }
              wrap.classList.remove('hidden');
              wrap.classList.add('flex');

              items.forEach(item => {
                  const div = document.createElement('div');
                  div.className = "w-64 max-w-[80vw] flex-shrink-0 glass p-5 rounded-3xl border border-white/10 flex flex-col justify-between group hover:border-brand/40 transition-colors cursor-pointer relative overflow-hidden";
                  
                  // Render Badges
                  let badgeColor = "bg-brand/20 text-brand outline-brand";
                  if(item.item_type === "hadith") badgeColor = "bg-amber-500/20 text-amber-500 outline-amber-500/50";
                  if(item.item_type === "quran") badgeColor = "bg-emerald-500/20 text-emerald-500 outline-emerald-500/50";
                  
                  const rtfText = item.text.replace(/\\n/g, '<br>');
                  const snippet = rtfText.length > 80 ? rtfText.substring(0, 80) + '...' : rtfText;
                  
                  const tagHtml = (item.tags || []).slice(0,2).map(t => `<span class="bg-white/5 px-2 py-0.5 rounded text-[8px] font-black uppercase text-white/50">${t}</span>`).join('');
                  
                  div.innerHTML = `
                      <div class="pointer-events-none">
                          <div class="flex justify-between items-start mb-3">
                              <span class="px-2 py-0.5 rounded text-[8px] font-black uppercase tracking-widest outline outline-1 outline-offset-1 ${badgeColor}">${item.item_type}</span>
                              <div class="flex gap-1">${tagHtml}</div>
                          </div>
                          <h4 class="text-xs font-bold text-white leading-tight mb-2 uppercase tracking-tight">${item.title}</h4>
                          <p class="text-[10px] text-white/70 leading-relaxed italic mb-4">${snippet}</p>
                      </div>
                      <div class="flex gap-2 relative z-10 w-full">
                          <button onclick="viewRecommendedItem(${item.id})" class="flex-1 py-2 bg-white/5 hover:bg-white/10 text-white rounded-xl text-[9px] font-black uppercase tracking-widest transition-colors text-center border border-white/5">View</button>
                      </div>
                  `;
                  container.appendChild(div);
              });
          } catch(e) {}
      }
      
      async function viewRecommendedItem(id) {
          trackInteraction("used_entry", id.toString(), "library");
          await editEntry(id);
      }
"""
text = text.replace(js_target, js_repl)

with open("app/routes/app_pages.py", "w") as f:
    f.write(text)

print("HTML/JS Patched!")
