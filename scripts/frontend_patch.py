import re

with open("app/routes/app_pages.py", "r") as f:
    html = f.read()

# 1. Replace Edit HTML
edit_html_target = """            <div class="space-y-2 pt-2">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Library Sourcing Scope</label>
              <div class="flex gap-4">
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" id="editScopePrebuilt" class="w-4 h-4 rounded border-white/10 bg-white/5 text-brand focus:ring-brand">
                  <span class="text-[10px] font-bold text-white uppercase">Prebuilt Packs</span>
                </label>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" id="editScopeOrg" class="w-4 h-4 rounded border-white/10 bg-white/5 text-brand focus:ring-brand">
                  <span class="text-[10px] font-bold text-white uppercase">Org Library</span>
                </label>
              </div>
            </div>"""

edit_html_replacement = """            <div class="space-y-1 pt-2">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Content Provider Source</label>
              <select id="editProviderScope" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand appearance-none text-white">
                <option value="all_sources">All Sources</option>
                <option value="system_library">System Library (Sabeel Default)</option>
                <option value="user_library">My Library (Custom Organization)</option>
              </select>
            </div>"""

html = html.replace(edit_html_target, edit_html_replacement)


# 2. Replace New HTML
new_html_target = """            <div class="space-y-2 pt-2">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Library Sourcing Scope</label>
              <div class="flex gap-4">
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" id="newScopePrebuilt" checked class="w-4 h-4 rounded border-white/10 bg-white/5 text-brand focus:ring-brand">
                  <span class="text-[10px] font-bold text-white uppercase">Prebuilt Packs</span>
                </label>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" id="newScopeOrg" checked class="w-4 h-4 rounded border-white/10 bg-white/5 text-brand focus:ring-brand">
                  <span class="text-[10px] font-bold text-white uppercase">Org Library</span>
                </label>
              </div>
            </div>"""

new_html_replacement = """            <div class="space-y-1 pt-2">
              <label class="text-[10px] font-black uppercase tracking-widest text-muted">Content Provider Source</label>
              <select id="newProviderScope" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-4 text-sm outline-none focus:ring-2 focus:ring-brand appearance-none text-white">
                <option value="all_sources">All Sources</option>
                <option value="system_library">System Library (Sabeel Default)</option>
                <option value="user_library">My Library (Custom Organization)</option>
              </select>
            </div>"""

html = html.replace(new_html_target, new_html_replacement)


# 3. Replace JS Payload for saveNewAutomation
js_new_target = """        const scope = [];
        if (document.getElementById('newScopePrebuilt').checked) scope.push('prebuilt');
        if (document.getElementById('newScopeOrg').checked) scope.push('org_library');

        const payload = {
          name: document.getElementById('newName').value,
          ig_account_id: parseInt(document.getElementById('newAccount').value),
          topic_prompt: document.getElementById('newTopic').value,
          content_seed_mode: document.getElementById('newSeedMode').value,
          content_seed_text: document.getElementById('newSeedText').value,
          post_time_local: document.getElementById('newTime').value,
          library_scope: scope,"""

js_new_replacement = """        const providerScope = document.getElementById('newProviderScope').value;

        const payload = {
          name: document.getElementById('newName').value,
          ig_account_id: parseInt(document.getElementById('newAccount').value),
          topic_prompt: document.getElementById('newTopic').value,
          content_seed_mode: document.getElementById('newSeedMode').value,
          content_seed_text: document.getElementById('newSeedText').value,
          post_time_local: document.getElementById('newTime').value,
          content_provider_scope: providerScope,"""

html = html.replace(js_new_target, js_new_replacement)


# 4. Replace JS Payload for updateAutomation
js_edit_target = """        const scope = [];
        if (document.getElementById('editScopePrebuilt').checked) scope.push('prebuilt');
        if (document.getElementById('editScopeOrg').checked) scope.push('org_library');

        const payload = {
          name: document.getElementById('editName').value,
          topic_prompt: document.getElementById('editTopic').value,
          content_seed_mode: document.getElementById('editSeedMode').value,
          content_seed_text: document.getElementById('editSeedText').value,
          post_time_local: document.getElementById('editTime').value,
          library_scope: scope
        };"""

js_edit_replacement = """        const providerScope = document.getElementById('editProviderScope').value;

        const payload = {
          name: document.getElementById('editName').value,
          topic_prompt: document.getElementById('editTopic').value,
          content_seed_mode: document.getElementById('editSeedMode').value,
          content_seed_text: document.getElementById('editSeedText').value,
          post_time_local: document.getElementById('editTime').value,
          content_provider_scope: providerScope
        };"""

html = html.replace(js_edit_target, js_edit_replacement)


# 5. Replace openEditModal UI populate
js_populate_target = """        document.getElementById('editName').value = auto.name;
        document.getElementById('editTopic').value = auto.topic_prompt;
        document.getElementById('editSeedMode').value = auto.content_seed_mode || 'none';
        document.getElementById('editSeedText').value = auto.content_seed_text || '';
        document.getElementById('editTime').value = auto.post_time_local || '09:00';
        
        const scope = auto.library_scope || [];
        document.getElementById('editScopePrebuilt').checked = scope.includes('prebuilt');
        document.getElementById('editScopeOrg').checked = scope.includes('org_library');"""

js_populate_replacement = """        document.getElementById('editName').value = auto.name;
        document.getElementById('editTopic').value = auto.topic_prompt;
        document.getElementById('editSeedMode').value = auto.content_seed_mode || 'none';
        document.getElementById('editSeedText').value = auto.content_seed_text || '';
        document.getElementById('editTime').value = auto.post_time_local || '09:00';
        document.getElementById('editProviderScope').value = auto.content_provider_scope || 'all_sources';"""

html = html.replace(js_populate_target, js_populate_replacement)


with open("app/routes/app_pages.py", "w") as f:
    f.write(html)
print("SUCCESS: HTML and JS payload patches applied.")
