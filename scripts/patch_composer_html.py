import re

def patch_composer():
    with open("app/routes/app_pages.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Define the new HTML for newPostModal
    new_modal_html = """  <div id="newPostModal" class="fixed inset-0 bg-black/95 backdrop-blur-2xl z-[100] flex items-end md:items-center justify-center p-0 md:p-10 hidden">
    <div class="glass w-full h-[100vh] md:h-full md:max-w-7xl rounded-none md:rounded-[3rem] overflow-hidden flex flex-col md:flex-row animate-in slide-in-from-bottom md:zoom-in duration-500 border-0 border-t md:border border-white/5 shadow-2xl">
      
      <!-- Studio Sidebar (Left/Top) -->
      <div class="w-full md:w-80 bg-black/50 border-b md:border-b-0 md:border-r border-white/5 flex flex-col pt-10 md:pt-12 px-8 z-50 shrink-0">
        <div>
          <h3 class="text-3xl font-black italic text-white tracking-tight">Content<br><span class="text-brand">Studio</span></h3>
          <p class="text-[9px] font-black text-muted uppercase tracking-[0.3em] mt-2">Guided Creation Flow</p>
        </div>
        
        <!-- Step Navigation -->
        <div class="flex-1 mt-12 space-y-6">
          <div id="navStep1" class="studio-nav-step active flex items-center gap-4 cursor-pointer" onclick="switchStudioSection(1)">
             <div class="w-8 h-8 rounded-full border-2 border-brand flex items-center justify-center text-[10px] font-black text-brand nav-num transition-all">1</div>
             <div class="text-xs font-black uppercase text-white tracking-widest nav-text transition-all">Intent & Topic</div>
          </div>
          <div id="navStep2" class="studio-nav-step flex items-center gap-4 cursor-pointer text-muted" onclick="switchStudioSection(2)">
             <div class="w-8 h-8 rounded-full border-2 border-white/10 flex items-center justify-center text-[10px] font-black nav-num transition-all">2</div>
             <div class="text-xs font-black uppercase tracking-widest nav-text transition-all">Content Seed</div>
          </div>
          <div id="navStep3" class="studio-nav-step flex items-center gap-4 cursor-pointer text-muted" onclick="switchStudioSection(3)">
             <div class="w-8 h-8 rounded-full border-2 border-white/10 flex items-center justify-center text-[10px] font-black nav-num transition-all">3</div>
             <div class="text-xs font-black uppercase tracking-widest nav-text transition-all">Visuals</div>
          </div>
          <div id="navStep4" class="studio-nav-step flex items-center gap-4 cursor-pointer text-muted" onclick="switchStudioSection(4)">
             <div class="w-8 h-8 rounded-full border-2 border-white/10 flex items-center justify-center text-[10px] font-black nav-num transition-all">4</div>
             <div class="text-xs font-black uppercase tracking-widest nav-text transition-all">Output</div>
          </div>
        </div>
        
        <div class="pb-10 pt-4 border-t border-white/5 mt-auto">
          <button type="button" onclick="closeNewPostModal()" class="w-full py-4 text-[10px] font-black uppercase tracking-widest text-muted hover:text-white transition-all">Close Studio</button>
        </div>
      </div>

      <!-- Studio Main Content Area -->
      <form id="composerForm" onsubmit="submitNewPost(event)" class="flex-1 overflow-hidden flex flex-col relative bg-white/2">
        <input type="hidden" name="visual_mode" id="studioVisualMode" value="upload">
        <input type="hidden" name="library_item_id" id="studioLibraryItemId">

        <div class="flex-1 overflow-y-auto p-6 md:p-12 pb-32">
          
          <!-- SECTION 1: TOPIC & INTENT -->
          <div id="studioSection1" class="studio-section space-y-10 animate-in slide-in-from-right-8 duration-500">
            <div>
              <label class="text-[10px] font-black uppercase tracking-[0.2em] text-brand">Step 01</label>
              <h4 class="text-2xl font-black text-white italic">What's the topic?</h4>
              <p class="text-xs text-muted mt-2 font-medium">Sabeel uses this to suggest high-quality sources and generate relevant content.</p>
            </div>

            <div class="space-y-6 max-w-2xl">
               <div class="space-y-2">
                 <label class="text-[9px] font-black text-white uppercase tracking-widest pl-1">Topic / Message</label>
                 <input type="text" id="composerTopic" name="topic" oninput="debounceComposerSuggest('composerTopic')" placeholder="e.g. The importance of Sabr (Patience)" class="w-full bg-white/5 border border-white/10 rounded-2xl px-6 py-5 text-sm text-white font-bold outline-none focus:border-brand/50 focus:bg-white/10 transition-all shadow-inner">
               </div>

               <div class="grid grid-cols-2 gap-4">
                 <div class="space-y-2">
                   <label class="text-[9px] font-black text-white uppercase tracking-widest pl-1">Tone</label>
                   <select name="tone" class="w-full bg-white/5 border border-white/10 rounded-2xl px-4 py-4 text-xs font-bold text-white outline-none focus:border-brand/40 appearance-none">
                     <option value="philosophical">Philosophical</option>
                     <option value="motivational">Motivational</option>
                     <option value="educational">Educational</option>
                     <option value="gentle">Gentle Reminder</option>
                   </select>
                 </div>
                 <div class="space-y-2">
                   <label class="text-[9px] font-black text-white uppercase tracking-widest pl-1">Post Type</label>
                   <select name="post_type" class="w-full bg-white/5 border border-white/10 rounded-2xl px-4 py-4 text-xs font-bold text-white outline-none focus:border-brand/40 appearance-none">
                     <option value="reflection">Reflection</option>
                     <option value="quote">Quote Card</option>
                     <option value="announcement">Announcement</option>
                   </select>
                 </div>
               </div>

               <div id="topicSuggestionsArea" class="hidden mt-8 pt-8 border-t border-white/5 space-y-4">
                 <div class="flex justify-between items-center">
                    <label class="text-[10px] font-black uppercase tracking-[0.2em] text-brand">Smart Matches Found</label>
                 </div>
                 <div id="topicSuggestionsList" class="flex flex-col gap-3"></div>
               </div>
            </div>
            
            <div class="pt-8 flex justify-end">
               <button type="button" onclick="switchStudioSection(2)" class="px-8 py-4 bg-white text-black rounded-xl font-black text-[10px] uppercase tracking-widest hover:scale-105 active:scale-95 transition-all">Continue to Source &rarr;</button>
            </div>
          </div>

          <!-- SECTION 2: SOURCE & CONTENT SEED -->
          <div id="studioSection2" class="studio-section hidden space-y-10 animate-in slide-in-from-right-8 duration-500">
            <div class="flex justify-between items-end">
              <div>
                <label class="text-[10px] font-black uppercase tracking-[0.2em] text-brand">Step 02</label>
                <h4 class="text-2xl font-black text-white italic">Source Foundation</h4>
                <p class="text-xs text-muted mt-2 font-medium">Your post caption will be grounded in this text.</p>
              </div>
              <button type="button" onclick="openLibraryDrawer()" class="px-4 py-2 bg-brand/10 text-brand border border-brand/20 rounded-lg text-[9px] font-black uppercase tracking-widest hover:bg-brand/20 transition-all flex items-center gap-2">
                 <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"></path></svg>
                 Browse Full Library
              </button>
            </div>

            <div class="max-w-3xl space-y-6">
              <!-- Selected Source Display -->
              <div id="activeSourceCard" class="hidden glass p-6 rounded-2xl border border-brand/30 relative overflow-hidden group">
                 <div class="absolute top-0 right-0 p-4 opacity-10 blur-sm pointer-events-none">
                    <svg class="w-24 h-24" fill="currentColor" viewBox="0 0 24 24"><path d="M14.017 21v-7.391c0-5.704 3.731-9.57 8.983-10.609l.995 2.151c-2.432.917-3.995 3.638-3.995 5.849h4v10h-9.983zm-14.017 0v-7.391c0-5.704 3.748-9.57 9-10.609l.996 2.151c-2.433.917-3.996 3.638-3.996 5.849h3.983v10h-9.983z"></path></svg>
                 </div>
                 <div class="flex justify-between items-start mb-4 relative z-10">
                    <span id="activeSourceBadge" class="px-2.5 py-1 bg-brand text-white rounded-[4px] text-[8px] font-black uppercase tracking-widest">Selected Source</span>
                    <button type="button" onclick="clearSelectedSource()" class="text-rose-400 hover:text-rose-300 text-[9px] font-black uppercase tracking-widest transition-all">Remove</button>
                 </div>
                 <div id="activeSourceText" class="text-sm font-medium text-white/90 leading-relaxed relative z-10 italic"></div>
                 <div id="activeSourceRef" class="mt-4 text-[10px] font-black text-brand uppercase tracking-widest relative z-10"></div>
              </div>

              <!-- Manual / Seed Textarea -->
              <div class="space-y-4">
                 <label id="seedLabel" class="text-[9px] font-black text-white uppercase tracking-widest pl-1">Or write a manual content seed / prompt directives</label>
                 <textarea id="studioSourceText" name="source_text" required placeholder="Type the text you want to feature or directives for the AI to expand upon..." class="w-full bg-white/5 border border-white/10 rounded-2xl p-6 text-sm font-medium text-white outline-none focus:border-brand/40 transition-all h-40 resize-none shadow-inner"></textarea>
                 
                 <div class="flex gap-4">
                    <input type="text" id="studioReference" name="source_reference" placeholder="Reference (Optional, e.g. Bukhari 123)" class="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-xs font-bold text-white outline-none focus:border-brand/40 shadow-inner">
                 </div>
              </div>
            </div>

            <div class="pt-8 flex justify-between">
               <button type="button" onclick="switchStudioSection(1)" class="px-6 py-4 text-muted hover:text-white rounded-xl font-black text-[10px] uppercase tracking-widest transition-all">&larr; Back</button>
               <button type="button" onclick="switchStudioSection(3)" class="px-8 py-4 bg-white text-black rounded-xl font-black text-[10px] uppercase tracking-widest hover:scale-105 active:scale-95 transition-all">Continue to Visuals &rarr;</button>
            </div>
          </div>

          <!-- SECTION 3: VISUALS -->
          <div id="studioSection3" class="studio-section hidden space-y-10 animate-in slide-in-from-right-8 duration-500">
            <div>
              <label class="text-[10px] font-black uppercase tracking-[0.2em] text-brand">Step 03</label>
              <h4 class="text-2xl font-black text-white italic">Visual Aethestics</h4>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl">
                <div onclick="setVisualMode('upload')" id="modeUpload" class="visual-card active p-6 rounded-3xl border border-white/10 bg-white/5 cursor-pointer transition-all hover:bg-white/10 relative overflow-hidden group">
                  <div class="absolute inset-0 bg-gradient-to-tr from-transparent to-brand/20 opacity-0 group-[.active]:opacity-100 transition-opacity"></div>
                  <div class="absolute top-4 right-4 check-icon text-brand opacity-0 group-[.active]:opacity-100 transition-opacity"><svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></div>
                  <div class="w-12 h-12 rounded-2xl bg-white/5 flex items-center justify-center text-white mb-6 relative z-10"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path></svg></div>
                  <div class="text-[11px] font-black text-white uppercase tracking-widest relative z-10">Upload</div>
                  <div class="text-[9px] font-medium text-muted mt-1 relative z-10">From computer</div>
                </div>

                <div onclick="setVisualMode('media_library')" id="modeMedia" class="visual-card p-6 rounded-3xl border border-white/10 bg-white/5 cursor-pointer transition-all hover:bg-white/10 relative overflow-hidden group">
                  <div class="absolute inset-0 bg-gradient-to-tr from-transparent to-brand/20 opacity-0 group-[.active]:opacity-100 transition-opacity"></div>
                  <div class="absolute top-4 right-4 check-icon text-brand opacity-0 group-[.active]:opacity-100 transition-opacity"><svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></div>
                  <div class="w-12 h-12 rounded-2xl bg-white/5 flex items-center justify-center text-white mb-6 relative z-10"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg></div>
                  <div class="text-[11px] font-black text-white uppercase tracking-widest relative z-10">Vault</div>
                  <div class="text-[9px] font-medium text-muted mt-1 relative z-10">Org Assets</div>
                </div>

                <div onclick="setVisualMode('ai_background')" id="modeAI" class="visual-card p-6 rounded-3xl border border-white/10 bg-white/5 cursor-pointer transition-all hover:bg-white/10 relative overflow-hidden group">
                  <div class="absolute inset-0 bg-gradient-to-tr from-transparent to-brand/20 opacity-0 group-[.active]:opacity-100 transition-opacity"></div>
                  <div class="absolute top-4 right-4 check-icon text-brand opacity-0 group-[.active]:opacity-100 transition-opacity"><svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></div>
                  <div class="w-12 h-12 rounded-2xl bg-white/5 flex items-center justify-center text-white mb-6 relative z-10"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg></div>
                  <div class="text-[11px] font-black text-white uppercase tracking-widest relative z-10">AI Gen</div>
                  <div class="text-[9px] font-medium text-muted mt-1 relative z-10">DALLE-3 Scene</div>
                </div>

                <div onclick="setVisualMode('quote_card')" id="modeQuote" class="visual-card p-6 rounded-3xl border border-white/10 bg-white/5 cursor-pointer transition-all hover:bg-white/10 relative overflow-hidden group">
                  <div class="absolute inset-0 bg-gradient-to-tr from-transparent to-emerald-500/20 opacity-0 group-[.active]:opacity-100 transition-opacity"></div>
                  <div class="absolute top-4 right-4 check-icon text-emerald-400 opacity-0 group-[.active]:opacity-100 transition-opacity"><svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></div>
                  <div class="w-12 h-12 rounded-2xl bg-white/5 flex items-center justify-center text-white mb-6 relative z-10"><svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"></path></svg></div>
                  <div class="text-[11px] font-black text-white uppercase tracking-widest relative z-10">Quote Card</div>
                  <div class="text-[9px] font-medium text-muted mt-1 relative z-10">Typographic</div>
                </div>
            </div>

            <!-- Dynamic Config Panes -->
            <div id="visualControls" class="p-8 rounded-[2rem] bg-white/5 border border-white/5 max-w-4xl space-y-6">
                 
                 <!-- Upload UI -->
                 <div id="uiUpload" class="space-y-4 animate-in fade-in">
                    <label class="text-[9px] font-black text-white uppercase tracking-widest pl-1">Selected Media Form</label>
                    <div class="flex items-center gap-6">
                      <div class="w-32 h-32 rounded-2xl bg-white/5 border border-dashed border-white/20 flex flex-col pt-6 items-center flex-start text-white/40 overflow-hidden relative group cursor-pointer" onclick="document.getElementById('studioImageInput').click()">
                        <svg class="w-6 h-6 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                        <span class="text-[8px] font-black uppercase tracking-widest">Select</span>
                        <img id="uploadPreview" class="hidden absolute inset-0 w-full h-full object-cover">
                      </div>
                      <input type="file" name="image" id="studioImageInput" onchange="previewUpload(this)" class="hidden" accept="image/png, image/jpeg, image/webp">
                      <div class="text-xs text-muted font-medium max-w-xs leading-relaxed">Click the box to upload an image from your device. Supported formats: .jpg, .png. Optimal ratio 4:5.</div>
                    </div>
                 </div>

                 <!-- AI Background UI -->
                 <div id="uiAI" class="hidden space-y-6 animate-in fade-in">
                    <div class="space-y-3">
                       <label class="text-[9px] font-black text-white uppercase tracking-widest pl-1">AI Prompt Description</label>
                       <textarea name="visual_prompt" id="studioVisualPrompt" placeholder="Describe the scene... e.g. Minimalist mosque silhouette at sunset, warm tones, high quality photography" class="w-full bg-black/20 border border-white/10 rounded-2xl p-5 text-xs text-white outline-none focus:border-brand/50 h-24 shadow-inner"></textarea>
                    </div>
                    <div class="space-y-3">
                       <label class="text-[9px] font-black text-white uppercase tracking-widest pl-1">Quick Styles</label>
                       <div class="flex flex-wrap gap-2">
                         <button type="button" onclick="setAIPreset('nature')" class="px-5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-[9px] font-black uppercase text-white hover:bg-brand/20 hover:border-brand/40 hover:text-brand transition-all">Nature</button>
                         <button type="button" onclick="setAIPreset('islamic_geo')" class="px-5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-[9px] font-black uppercase text-white hover:bg-brand/20 hover:border-brand/40 hover:text-brand transition-all">Geometric</button>
                         <button type="button" onclick="setAIPreset('minimal')" class="px-5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-[9px] font-black uppercase text-white hover:bg-brand/20 hover:border-brand/40 hover:text-brand transition-all">Minimal</button>
                         <button type="button" onclick="setAIPreset('mosque_sil')" class="px-5 py-2.5 bg-white/5 border border-white/10 rounded-xl text-[9px] font-black uppercase text-white hover:bg-brand/20 hover:border-brand/40 hover:text-brand transition-all">Mosque Silhouette</button>
                       </div>
                    </div>
                 </div>

                 <!-- Quote Card Sub-options (Only appears when Quote Card is selected) -->
                 <div id="uiQuoteMod" class="hidden border-t border-white/10 pt-6 mt-6 animate-in fade-in">
                    <label class="text-[10px] font-black text-white uppercase tracking-[0.2em] mb-4 block">Quote Card Settings</label>
                    <p class="text-xs text-brand font-medium mb-6">The text from Step 02 will be overlaid perfectly on top of the visual foundation chosen above.</p>
                 </div>
            </div>

            <div class="pt-8 flex justify-between">
               <button type="button" onclick="switchStudioSection(2)" class="px-6 py-4 text-muted hover:text-white rounded-xl font-black text-[10px] uppercase tracking-widest transition-all">&larr; Back</button>
               <button type="button" onclick="switchStudioSection(4)" class="px-8 py-4 bg-white text-black rounded-xl font-black text-[10px] uppercase tracking-widest hover:scale-105 active:scale-95 transition-all">Preview & Finalize &rarr;</button>
            </div>
          </div>

          <!-- SECTION 4: OUTPUT & ACTIONS -->
          <div id="studioSection4" class="studio-section hidden space-y-10 animate-in slide-in-from-right-8 duration-500 min-h-full">
            <div class="flex justify-between items-end">
              <div>
                <label class="text-[10px] font-black uppercase tracking-[0.2em] text-brand">Step 04</label>
                <h4 class="text-2xl font-black text-white italic">Output Preview</h4>
              </div>
              <button type="button" onclick="launchLivePreview()" class="px-5 py-3 bg-brand/20 text-brand border border-brand/30 rounded-xl text-[9px] font-black uppercase tracking-widest shadow-lg shadow-brand/10 hover:bg-brand/30 transition-all flex items-center gap-2">
                 <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg>
                 Load Preview
              </button>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-10">
               
               <!-- Preview Phone Mockup -->
               <div class="flex justify-center items-start">
                 <div class="w-full max-w-[340px] bg-black border-[6px] border-[#1e1e1e] rounded-[3rem] overflow-hidden flex flex-col shadow-2xl relative shadow-brand/5">
                    <!-- Nav Bar -->
                    <div class="px-4 py-3 flex items-center justify-between bg-black border-b border-white/10 z-10">
                       <div class="text-[13px] font-bold text-white">Sabeel Post</div>
                       <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z"></path></svg>
                    </div>
                    
                    <!-- Image -->
                    <div class="w-full aspect-[4/5] bg-neutral-900 border-b border-white/5 relative flex items-center justify-center overflow-hidden">
                       <img id="previewImage" class="hidden w-full h-full object-cover">
                       <div id="previewLoader" class="flex flex-col items-center gap-3">
                          <svg class="w-8 h-8 text-white/20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                          <span class="text-[9px] font-black uppercase tracking-widest text-muted">Click Load Preview</span>
                       </div>
                    </div>

                    <!-- Post Data Info -->
                    <div class="p-4 bg-black flex-1 flex flex-col justify-start">
                        <div class="flex gap-3 mb-3 text-white">
                           <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"></path></svg>
                           <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path></svg>
                           <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path></svg>
                        </div>
                        <div class="text-[10px] text-white/40 font-medium">Caption preview unavailable until generation.</div>
                    </div>
                 </div>
               </div>
               
               <!-- Schedule & Settings -->
               <div class="space-y-8">
                  <div class="space-y-6 bg-white/5 border border-white/5 rounded-3xl p-8">
                     <div class="space-y-2">
                       <label class="text-[9px] font-black uppercase tracking-widest text-white pl-1">Target Account</label>
                       <select name="ig_account_id" class="w-full bg-black/40 border border-white/10 rounded-2xl px-5 py-4 text-xs font-bold text-white outline-none focus:border-brand/40 shadow-inner appearance-none">
                         {account_options}
                       </select>
                     </div>
                     <div class="space-y-2">
                       <label class="text-[9px] font-black uppercase tracking-widest text-white pl-1">Schedule Time (UTC)</label>
                       <input type="datetime-local" name="scheduled_time" class="w-full bg-black/40 border border-white/10 rounded-2xl px-5 py-4 text-xs font-bold text-brand outline-none focus:border-brand/40 shadow-inner [color-scheme:dark]">
                       <p class="text-[9px] text-muted font-medium mt-2 px-1">Leave empty to use Account Default posting time.</p>
                     </div>
                  </div>

                  <button type="submit" id="studioSubmitBtn" class="w-full py-5 bg-brand text-white rounded-2xl font-black text-xs uppercase tracking-[0.2em] shadow-xl shadow-brand/20 hover:scale-[1.02] active:scale-[0.98] transition-all flex items-center justify-center gap-3">
                     <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
                     Generate Caption & Schedule
                  </button>
                  <button type="button" onclick="switchStudioSection(3)" class="w-full py-4 text-muted hover:text-white rounded-xl font-black text-[10px] uppercase tracking-widest transition-all">&larr; Back to Visuals</button>

                  <div class="bg-brand/10 border border-brand/20 rounded-2xl p-5 flex gap-4 text-brand">
                    <svg class="w-5 h-5 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    <div class="text-[10px] leading-relaxed font-bold">
                       Submitting this form creates a draft post. A high-converting caption will be automatically generated based on the source seed using AI. You can review the caption in the Drafts list.
                    </div>
                  </div>
               </div>
            </div>

          </div>
        </div>
      </form>
    </div>
  </div>"""

    # Look for the modal start and the end of script tags
    start_tag = '<div id="newPostModal"'
    end_tag = '<!-- Library Explorer Side Drawer -->'

    parts = content.split(start_tag)
    if len(parts) < 2:
        print("Could not find start_tag")
        return

    before_modal = parts[0]
    after_modal_split = parts[1].split(end_tag)
    after_modal = end_tag + after_modal_split[1]

    # Let's insert scripts properly
    scripts = """
<script>
    // JS for Content Studio
    function openNewPostModal() {
        document.getElementById('newPostModal').classList.remove('hidden');
        switchStudioSection(1);
    }
    function closeNewPostModal() {
        document.getElementById('newPostModal').classList.add('hidden');
    }
    function switchStudioSection(stepIndex) {
        // hide all
        for(let i=1; i<=4; i++) {
           const el = document.getElementById('studioSection' + i);
           if(el) el.classList.add('hidden');
           
           const nav = document.getElementById('navStep' + i);
           if(nav) {
               nav.classList.remove('active', 'text-white');
               nav.classList.add('text-muted');
               nav.querySelector('.nav-num').classList.remove('border-brand', 'text-brand');
               nav.querySelector('.nav-num').classList.add('border-white/10');
               nav.querySelector('.nav-text').classList.remove('text-white');
           }
        }
        
        // activate requested
        const target = document.getElementById('studioSection' + stepIndex);
        if(target) target.classList.remove('hidden');
        
        const targetNav = document.getElementById('navStep' + stepIndex);
        if(targetNav) {
           targetNav.classList.remove('text-muted');
           targetNav.classList.add('active');
           targetNav.querySelector('.nav-num').classList.remove('border-white/10');
           targetNav.querySelector('.nav-num').classList.add('border-brand', 'text-brand');
           targetNav.querySelector('.nav-text').classList.add('text-white');
        }
    }

    let suggestTimer;
    function debounceComposerSuggest(inputId) {
        clearTimeout(suggestTimer);
        suggestTimer = setTimeout(() => {
            const val = document.getElementById(inputId).value;
            if (val.length > 5 && inputId === 'composerTopic') {
                fetchComposerSuggestions(val);
            }
        }, 800);
    }

    async function fetchComposerSuggestions(text) {
        const wrap = document.getElementById('topicSuggestionsArea');
        const cont = document.getElementById('topicSuggestionsList');
        // Show spinner
        wrap.classList.remove('hidden');
        cont.innerHTML = '<div class="text-[10px] text-brand/60 uppercase font-black tracking-widest animate-pulse">Scanning Library...</div>';
        
        try {
            const res = await fetch('/library/suggest-entries', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: text, max: 3})
            });
            const data = await res.json();
            
            cont.innerHTML = '';
            if (data.length === 0) {
                cont.innerHTML = '<div class="text-[10px] text-muted font-bold">No exact matches from library.</div>';
            } else {
                data.forEach(item => {
                   const div = document.createElement('div');
                   div.className = "flex justify-between items-center p-4 bg-black/20 hover:bg-white/5 border border-white/5 rounded-xl transition-all group cursor-pointer";
                   
                   let ref = '';
                   if (item.item_type === 'quran') ref = `Quran ${item.meta.surah_number}:${item.meta.verse_start}`;
                   else if (item.item_type === 'hadith') ref = `${item.meta.collection} #${item.meta.hadith_number}`;
                   else ref = item.meta.title || item.item_type;

                   div.innerHTML = `
                     <div class="flex-1 pr-6">
                        <div class="text-[9px] font-black text-brand uppercase tracking-widest mb-1">${ref}</div>
                        <div class="text-xs text-white/80 font-medium line-clamp-2">${item.text}</div>
                     </div>
                     <button class="px-4 py-2 border border-brand/40 text-brand rounded-lg text-[9px] font-black uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-all shrink-0">Use</button>
                   `;
                   div.onclick = () => { applySuggestedSource(item, ref); };
                   cont.appendChild(div);
                });
            }
        } catch(e) {
            cont.innerHTML = '<div class="text-[10px] text-rose-400 font-bold">Error loading suggestions</div>';
        }
    }

    function applySuggestedSource(item, refText) {
        // Set Source Editor
        document.getElementById('studioSourceText').value = item.text || "";
        document.getElementById('studioReference').value = refText || "";
        document.getElementById('studioLibraryItemId').value = item.id;
        
        // Show Active Card
        document.getElementById('activeSourceCard').classList.remove('hidden');
        document.getElementById('activeSourceText').innerText = item.text || "";
        document.getElementById('activeSourceRef').innerText = refText || "";
        
        // Update Label
        document.getElementById('seedLabel').innerText = "Edit source text if needed before AI expansion:";
        
        // Move to Step 2
        switchStudioSection(2);
    }

    function clearSelectedSource() {
        document.getElementById('studioSourceText').value = "";
        document.getElementById('studioReference').value = "";
        document.getElementById('studioLibraryItemId').value = "";
        
        document.getElementById('activeSourceCard').classList.add('hidden');
        document.getElementById('activeSourceText').innerText = "";
        document.getElementById('activeSourceRef').innerText = "";
        document.getElementById('seedLabel').innerText = "Or write a manual content seed / prompt directives";
    }

    function setVisualMode(mode) {
        document.getElementById('studioVisualMode').value = mode;
        const modes = ['Upload', 'Media', 'AI', 'Quote'];
        modes.forEach(m => {
            const el = document.getElementById('mode'+m);
            if(el) el.classList.remove('active', 'border-brand', 'bg-brand/5');
            else {
               // try lower
            }
        });
        
        const target = {
            'upload': 'modeUpload',
            'media_library': 'modeMedia', 
            'ai_background': 'modeAI',
            'quote_card': 'modeQuote'
        }[mode];
        
        if (target) {
           const tel = document.getElementById(target);
           tel.classList.add('active', 'border-brand', 'bg-brand/5');
        }

        // Handle UIs
        document.getElementById('uiUpload').classList.add('hidden');
        document.getElementById('uiAI').classList.add('hidden');
        document.getElementById('uiQuoteMod').classList.add('hidden');
        
        if (mode === 'upload') document.getElementById('uiUpload').classList.remove('hidden');
        if (mode === 'ai_background' || mode === 'quote_card') {
           document.getElementById('uiAI').classList.remove('hidden');
           if (mode === 'quote_card') {
               document.getElementById('uiQuoteMod').classList.remove('hidden');
           }
        }
    }

    function setAIPreset(promptStr) {
        const m = {
            'nature': 'Premium minimalist nature photography, subtle warm tones, empty space',
            'islamic_geo': 'Subtle dark islamic geometric pattern background, elegant, cinematic lighting',
            'minimal': 'Extremely minimalist dark layout, smooth gradient, hyper-realistic texture',
            'mosque_sil': 'Minimalist silhouette of a mosque at dusk, violet and orange sky, cinematic'
        }[promptStr];
        document.getElementById('studioVisualPrompt').value = m || "";
    }

    function previewUpload(input) {
        if (input.files && input.files[0]) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const img = document.getElementById('uploadPreview');
                img.src = e.target.result;
                img.classList.remove('hidden');
            }
            reader.readAsDataURL(input.files[0]);
        }
    }

    async function launchLivePreview() {
        const img = document.getElementById('previewImage');
        const loader = document.getElementById('previewLoader');
        
        img.classList.add('hidden');
        loader.classList.remove('hidden');

        const formData = new FormData(document.getElementById('composerForm'));
        
        try {
            const res = await fetch('/posts/preview_render', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (res.ok) {
                img.src = data.preview_url;
                img.classList.remove('hidden');
                loader.classList.add('hidden');
            } else {
                const detail = data.detail || JSON.stringify(data.detail || data);
                loader.innerHTML = '<span class="text-[9px] font-black text-rose-400">Failed: '+detail+'</span>';
            }
        } catch (e) {
            loader.innerHTML = '<span class="text-[9px] font-black text-rose-400">Preview Error</span>';
        }
    }

    async function submitNewPost(event) {
        event.preventDefault();
        const btn = document.getElementById('studioSubmitBtn');
        const originalText = btn.innerHTML;
        btn.innerHTML = 'GENERATING... <span class="animate-pulse">⏳</span>';
        btn.disabled = true;

        const formData = new FormData(event.target);
        
        try {
            const res = await fetch('/posts/intake', {
                method: 'POST',
                body: formData
            });
            if (res.ok) {
                window.location.reload();
            } else {
                let errDetail = 'Failed to create post';
                try {
                    const err = await res.json();
                    errDetail = err.detail || JSON.stringify(err);
                } catch(e) {
                    errDetail = await res.text();
                }
                alert('Error: ' + errDetail);
            }
        } catch (e) {
            alert('Failure: ' + e);
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    }
</script>
"""

    # We also need to remove the OLD script which contains `submitNewPost` etc.
    # To be safe, we'll strip out everything from `<script>` to `</script>` roughly where it was inside or above the modal
    # Actually, the old script block started around line 337 and went up to line 514.
    # We will just append our script right before `end_tag`.
    
    final_content = before_modal + new_modal_html + "\n\n" + scripts + "\n" + after_modal

    with open("app/routes/app_pages.py", "w", encoding="utf-8") as f:
        f.write(final_content)
    print("Patched successfully")

if __name__ == "__main__":
    patch_composer()
