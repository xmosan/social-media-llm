with open("app/routes/app_pages.py", "r") as f:
    text = f.read()

bad_js = """      // ---- COMPOSER SMART ASSIST ----
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
      }"""

good_js = """      // ---- COMPOSER SMART ASSIST ----
      let composerSuggestTimer;
      function debounceComposerSuggest(inputId, containerId) {{
          clearTimeout(composerSuggestTimer);
          composerSuggestTimer = setTimeout(() => {{
              runComposerSuggest(inputId, containerId);
          }}, 800);
      }}

      async function runComposerSuggest(inputId, containerId) {{
          const text = document.getElementById(inputId).value;
          const container = document.getElementById(containerId);
          
          if (!text || text.length < 3) {{
              container.classList.add('hidden');
              container.innerHTML = '';
              return;
          }}
          
          try {{
              container.innerHTML = '<span class="text-[8px] font-black uppercase tracking-widest text-muted animate-pulse">Scanning library...</span>';
              container.classList.remove('hidden');
              container.classList.add('flex');
              
              const res = await fetch(`/library/suggest?query=${{encodeURIComponent(text)}}`);
              const items = await res.json();
              
              if (items.length === 0) {{
                  container.innerHTML = '<span class="text-[8px] font-black uppercase tracking-widest text-muted">No direct matches found. Try browsing Sabeel Defaults.</span>';
                  return;
              }}
              
              let html = '<span class="text-[8px] font-black uppercase tracking-widest text-brand mb-1">Suggested Sources based on your topic</span>';
              items.forEach((item, idx) => {{
                  if(idx > 2) return; // Show max 3
                  
                  // Clean text for literal insertion
                  const safeText = item.text.replace(/"/g, '&quot;').replace(/\\\\n/g, '\\\\\\\\n');
                  const preview = item.text.length > 70 ? item.text.substring(0, 70) + "..." : item.text;
                  
                  html += `
                  <div class="p-3 bg-white/5 rounded-xl border border-white/10 flex items-center justify-between gap-4">
                      <div class="flex-1 overflow-hidden">
                          <h5 class="text-[9px] font-black text-white uppercase tracking-tight truncate">${{item.title}}</h5>
                          <p class="text-[9px] text-white/50 truncate italic">${{preview}}</p>
                      </div>
                      <button type="button" onclick="insertComposerSuggest('${{inputId}}', '${{safeText}}', ${{item.id}})" class="px-3 py-1.5 bg-brand/20 text-brand rounded-lg text-[8px] font-black uppercase tracking-widest hover:bg-brand hover:text-white transition-all shrink-0">Use This</button>
                  </div>`;
              }});
              container.innerHTML = html;
          }} catch(e) {{ container.classList.add('hidden'); }}
      }}

      function insertComposerSuggest(inputId, textToInsert, entryId) {{
          const input = document.getElementById(inputId);
          // If it's a textarea, append it. If it's a short input, replace or append
          if (input.tagName === 'TEXTAREA') {{
              if (input.value.trim() !== '') input.value += '\\n\\n';
              input.value += textToInsert;
          }} else {{
              // Usually for AI topic or Automation Topic
              if(inputId === 'aiTopic') {{
                  document.getElementById('studioSourceText').value = textToInsert;
                  switchSourceTab('manual'); // Force switch to manual to see it
              }} else if (inputId === 'newTopic') {{
                  document.getElementById('newSeedMode').value = 'manual';
                  toggleNewSeedText();
                  document.getElementById('newSeedText').value = textToInsert;
              }}
          }}
          
          trackInteraction("used_entry", entryId.toString(), "composer");
          
          // Optionally flash the input
          input.classList.add('ring-2', 'ring-brand');
          setTimeout(() => input.classList.remove('ring-2', 'ring-brand'), 1000);
      }}"""

text = text.replace(bad_js, good_js)
with open("app/routes/app_pages.py", "w") as f:
    f.write(text)

