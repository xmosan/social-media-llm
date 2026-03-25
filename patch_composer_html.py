with open("app/routes/app_pages.py", "r") as f:
    text = f.read()

# PATCH 1: Add suggestions div under Manual Source Text
target1 = """              <!-- Manual Tab Area -->
              <div id="srcPaneManual" class="space-y-4">
                <textarea id="studioSourceText" name="source_text" required placeholder="Type your custom caption or directives here..." class="w-full bg-white/5 border border-white/10 rounded-2xl p-6 text-sm font-medium text-white outline-none focus:border-brand/40 transition-all h-48 resize-none"></textarea>
                <div class="flex gap-4">"""

repl1 = """              <!-- Manual Tab Area -->
              <div id="srcPaneManual" class="space-y-4">
                <textarea id="studioSourceText" oninput="debounceComposerSuggest('studioSourceText', 'composerSuggestionsManual')" name="source_text" required placeholder="Type your custom caption or directives here... The library will automatically suggest matching scholarly content." class="w-full bg-white/5 border border-white/10 rounded-2xl p-6 text-sm font-medium text-white outline-none focus:border-brand/40 transition-all h-48 resize-none"></textarea>
                <div id="composerSuggestionsManual" class="hidden flex-col gap-2 pt-2"></div>
                <div class="flex gap-4">"""

text = text.replace(target1, repl1)

# PATCH 2: Add suggestions div under AI Topic
target2 = """                  <div class="space-y-1">
                    <label class="text-[8px] font-black text-brand uppercase tracking-widest">Post Topic</label>
                    <input type="text" id="aiTopic" placeholder="e.g. The importance of gratitude in Islam" class="w-full bg-transparent border-b border-white/10 py-2 text-sm text-white font-medium outline-none focus:border-brand">
                  </div>"""

repl2 = """                  <div class="space-y-1">
                    <label class="text-[8px] font-black text-brand uppercase tracking-widest">Post Topic</label>
                    <input type="text" id="aiTopic" oninput="debounceComposerSuggest('aiTopic', 'composerSuggestionsAI')" placeholder="e.g. The importance of gratitude in Islam" class="w-full bg-transparent border-b border-white/10 py-2 text-sm text-white font-medium outline-none focus:border-brand">
                    <div id="composerSuggestionsAI" class="hidden flex-col gap-2 pt-4"></div>
                  </div>"""

text = text.replace(target2, repl2)

# PATCH 3: Add suggestions div under Automation Topic
target3 = """              <textarea id="newTopic" rows="3" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand" placeholder="Describe the focus of this automation..."></textarea>
              <input type="hidden" id="newLibraryTopic">
            </div>"""

repl3 = """              <textarea id="newTopic" oninput="debounceComposerSuggest('newTopic', 'autoSuggestions')" rows="3" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand" placeholder="Describe the focus of this automation..."></textarea>
              <input type="hidden" id="newLibraryTopic">
              <div id="autoSuggestions" class="hidden flex-col gap-2 pt-2"></div>
            </div>"""

text = text.replace(target3, repl3)

# PATCH 4: Inject Javascript logic for suggest
js_target = """      // REUSED from library to support picker across pages"""

js_repl = """      // ---- COMPOSER SMART ASSIST ----
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
              container.innerHTML = '<span class="text-[8px] font-black uppercase tracking-widest text-muted animate-pulse">Scanning library...</span>';
              container.classList.remove('hidden');
              container.classList.add('flex');
              
              const res = await fetch(`/library/suggest?query=${encodeURIComponent(text)}`);
              const items = await res.json();
              
              if (items.length === 0) {
                  container.innerHTML = '<span class="text-[8px] font-black uppercase tracking-widest text-muted">No direct matches found. Try browsing Sabeel Defaults.</span>';
                  return;
              }
              
              let html = '<span class="text-[8px] font-black uppercase tracking-widest text-brand mb-1">Suggested Sources based on your topic</span>';
              items.forEach((item, idx) => {
                  if(idx > 2) return; // Show max 3
                  
                  // Clean text for literal insertion
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
          // If it's a textarea, append it. If it's a short input, replace or append
          if (input.tagName === 'TEXTAREA') {
              if (input.value.trim() !== '') input.value += '\\n\\n';
              input.value += textToInsert;
          } else {
              // Usually for AI topic or Automation Topic
              if(inputId === 'aiTopic') {
                  document.getElementById('studioSourceText').value = textToInsert;
                  switchSourceTab('manual'); // Force switch to manual to see it
              } else if (inputId === 'newTopic') {
                  document.getElementById('newSeedMode').value = 'manual';
                  toggleNewSeedText();
                  document.getElementById('newSeedText').value = textToInsert;
              }
          }
          
          trackInteraction("used_entry", entryId.toString(), "composer");
          
          // Optionally flash the input
          input.classList.add('ring-2', 'ring-brand');
          setTimeout(() => input.classList.remove('ring-2', 'ring-brand'), 1000);
      }

      // REUSED from library to support picker across pages"""

text = text.replace(js_target, js_repl)

with open("app/routes/app_pages.py", "w") as f:
    f.write(text)

print("Composer suggestions injected.")
