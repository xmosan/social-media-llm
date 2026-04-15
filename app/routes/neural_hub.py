# Sabeel Knowledge Library: Neural Hub (v2.0)
# Isolated Router for high-fidelity knowledge discovery and Studio manifestation.

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from app.security.auth import require_user
from app.models import User
from .ui_assets import APP_LAYOUT_HTML, STUDIO_SCRIPTS_JS, STUDIO_COMPONENTS_HTML

router = APIRouter(tags=["Neural Hub"])

LIBRARY_HTML = """
<div id="neuralHub" class="min-h-screen animate-in fade-in duration-700">
    <!-- Header: Glass Hub -->
    <div class="glass p-12 mb-12 relative overflow-hidden group">
        <div class="absolute top-0 right-0 w-96 h-96 bg-brand/[0.02] rounded-full -mr-48 -mt-48 transition-transform duration-1000 group-hover:scale-110"></div>
        <div class="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-end gap-8">
            <div class="space-y-4">
                <div class="flex items-center gap-3">
                    <span class="px-3 py-1 bg-brand text-white text-[8px] font-black uppercase tracking-[0.3em] rounded-full">Foundation v2</span>
                    <span id="syncStatus" class="flex items-center gap-2 text-[8px] font-bold text-emerald-600 uppercase tracking-widest bg-emerald-50 px-3 py-1 rounded-full">
                        <span class="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span>
                        Neural Nodes Active
                    </span>
                </div>
                <h1 class="text-6xl font-black text-brand tracking-tighter italic leading-none">Knowledge<br><span class="text-accent underline decoration-brand/5 decoration-8 underline-offset-[12px]">Library</span></h1>
                <p class="text-sm text-text-muted font-medium max-w-xl leading-relaxed italic opacity-80">"Surface authenticated wisdom from the Sabeel archives and manifest it directly into your Studio workspace."</p>
            </div>
            
            <div class="flex items-center gap-6">
                <div class="text-right">
                    <div id="collectionCount" class="text-4xl font-black text-brand italic leading-none">0</div>
                    <div class="text-[9px] font-bold text-text-muted uppercase tracking-[0.3em] mt-2">Active Collections</div>
                </div>
                <div class="w-px h-12 bg-brand/10"></div>
                <div class="text-right">
                    <div id="usagePercent" class="text-4xl font-black text-accent italic leading-none">0%</div>
                    <div class="text-[9px] font-bold text-text-muted uppercase tracking-[0.3em] mt-2">Storage Usage</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Interface Controls -->
    <div class="flex flex-col md:flex-row gap-8 mb-12">
        <!-- Sidebar Navigation -->
        <div class="w-full md:w-64 space-y-8">
            <div class="space-y-3">
                <label class="text-[10px] font-black text-brand uppercase tracking-widest ml-1">Scope Intelligence</label>
                <div class="flex flex-col gap-2">
                    <button onclick="NeuralLibrary.setScope('global')" id="scopeGlobal" class="scope-btn active w-full flex items-center justify-between p-4 rounded-2xl border transition-all">
                        <span class="text-[11px] font-bold uppercase tracking-widest">Foundation</span>
                        <div class="dot w-2 h-2 rounded-full bg-brand"></div>
                    </button>
                    <button onclick="NeuralLibrary.setScope('org')" id="scopeOrg" class="scope-btn w-full flex items-center justify-between p-4 rounded-2xl border transition-all text-text-muted group">
                        <span class="text-[11px] font-bold uppercase tracking-widest">Organizational</span>
                        <div class="dot w-2 h-2 rounded-full bg-brand/10"></div>
                    </button>
                </div>
            </div>

            <div class="space-y-4">
                <label class="text-[10px] font-black text-brand uppercase tracking-widest ml-1">Knowledge Sources</label>
                <div id="sourcesList" class="space-y-2 max-h-[400px] overflow-y-auto custom-scrollbar pr-2">
                    <!-- Dynamic Sources -->
                </div>
            </div>
        </div>

        <!-- Main Workspace -->
        <div class="flex-1 space-y-10">
            <!-- Global Search -->
            <div class="relative group">
                <input type="text" id="libSearch" oninput="NeuralLibrary.search()" placeholder="Search through scriptures, archives, and wisdom nodes..." class="w-full bg-white border-2 border-brand/5 rounded-[2.5rem] px-12 py-8 text-lg font-medium text-brand outline-none focus:border-brand/20 transition-all shadow-xl shadow-brand/[0.02] placeholder:text-brand/20">
                <div class="absolute left-12 top-1/2 -translate-y-1/2 text-brand/20 group-focus-within:text-brand transition-colors">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5"/></svg>
                </div>
            </div>

            <!-- Content Grid -->
            <div id="libraryGrid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                <!-- Dynamic Entry Cards -->
            </div>
        </div>
    </div>
</div>

<style>
    .scope-btn.active { border-color: var(--brand); background: rgba(15, 61, 46, 0.05); color: var(--brand); }
    .scope-btn { border-color: transparent; }
    .source-item { transition: all 150ms ease; }
    .source-item:hover { transform: translateX(4px); }
    .entry-card { transition: all 300ms cubic-bezier(0.16, 1, 0.3, 1); }
    .entry-card:hover { transform: translateY(-8px); }
</style>

<script>
    const NeuralLibrary = {
        state: {
            scope: 'global', // global | org
            sourceId: null,
            loading: false
        },

        init() {
            console.log("Neural Hub: Initializing discovery engine...");
            this.loadSources();
            this.loadEntries();
        },

        setScope(s) {
            this.state.scope = s;
            document.querySelectorAll('.scope-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('scope' + s.charAt(0).toUpperCase() + s.slice(1)).classList.add('active');
            this.state.sourceId = null;
            this.loadSources();
            this.loadEntries();
        },

        async loadSources() {
            const list = document.getElementById('sourcesList');
            if (!list) return;
            try {
                const url = this.state.scope === 'global' ? '/api/quran/surahs' : '/api/library/sources';
                const res = await fetch(url);
                const data = await res.json();
                
                list.innerHTML = data.map(s => `
                    <button onclick="NeuralLibrary.setSource('${s.id}')" class="source-item w-full text-left p-4 rounded-xl border border-brand/5 hover:bg-brand/5 transition-all group \${this.state.sourceId == s.id ? 'bg-brand/5 border-brand/20' : ''}">
                        <div class="text-[11px] font-bold text-brand uppercase tracking-widest opacity-60 group-hover:opacity-100">\${s.title || s.name}</div>
                        \${s.english_name ? \`<div class="text-[9px] text-text-muted italic">\${s.english_name}</div>\` : ''}
                    </button>
                `).join('');
                
                document.getElementById('collectionCount').innerText = data.length;
            } catch (e) {
                console.error("Neural Hub Source Error:", e);
            }
        },

        setSource(id) {
            this.state.sourceId = id;
            this.loadSources();
            this.loadEntries();
        },

        async loadEntries() {
            const grid = document.getElementById('libraryGrid');
            if (!grid) return;
            grid.innerHTML = '<div class="col-span-full py-20 text-center animate-pulse text-[10px] font-black text-brand uppercase tracking-[0.4em]">Synthesizing Neural Nodes...</div>';
            
            try {
                const url = this.state.scope === 'global' 
                    ? \`/api/quran/surahs/\${this.state.sourceId || 1}\`
                    : \`/api/library/entries?scope=org\${this.state.sourceId ? '&source_id='+this.state.sourceId : ''}\`;
                
                const res = await fetch(url);
                const data = await res.json();
                
                const items = this.state.scope === 'global' ? data.verses : data;
                
                grid.innerHTML = items.map((v, idx) => \`
                    <div class="entry-card card p-8 group relative overflow-hidden bg-white hover:bg-brand/[0.01]">
                        <div class="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-30 transition-opacity">
                            <span class="text-4xl font-black text-brand italic">#\${v.verse_number || idx + 1}</span>
                        </div>
                        <div class="space-y-6 relative z-10">
                            \${v.text_arabic ? \`<div class="text-2xl text-right font-arabic leading-loose text-brand/80">\${v.text_arabic}</div>\` : ''}
                            <div class="text-[13px] text-text-main font-medium leading-relaxed italic opacity-80 group-hover:opacity-100 transition-opacity">
                                "\${v.text || v.translation_text || v.content}"
                            </div>
                            <div class="pt-6 border-t border-brand/5 flex justify-between items-center">
                                <div>
                                    <div class="text-[10px] font-black text-brand uppercase tracking-widest">\${v.reference || data.title || 'ARCHIVE'}</div>
                                    <div class="text-[8px] font-bold text-accent uppercase tracking-[0.2em] mt-1">\${this.state.scope === 'global' ? 'Foundation Intelligence' : 'Organizational Node'}</div>
                                </div>
                                <button onclick="NeuralLibrary.manifest('${this.state.scope === 'quran' ? 'quran' : 'entry'}', '\${v.id}', \`\${(v.text || v.translation_text || v.content).replace(/\`/g, "\\'").replace(/"/g, '&quot;')}\`, '\${v.reference || data.title}')" class="px-6 py-3 bg-brand text-white rounded-xl text-[9px] font-black uppercase tracking-widest shadow-xl shadow-brand/10 hover:scale-[1.05] active:scale-95 transition-all">Manifest</button>
                            </div>
                        </div>
                    </div>
                \`).join('');
                
            } catch (e) {
                console.error("Neural Hub Entry Error:", e);
                grid.innerHTML = '<div class="col-span-full py-20 text-center text-rose-500 font-bold uppercase tracking-widest">Neural Link Severed • Retry in T-minus 5s</div>';
            }
        },

        async search() {
            const grid = document.getElementById('libraryGrid');
            const query = document.getElementById('libSearch').value;
            if (query.length < 3) {
                if (query.length === 0) this.loadEntries();
                return;
            }

            grid.innerHTML = '<div class="col-span-full py-20 text-center animate-pulse text-[10px] font-black text-brand uppercase tracking-[0.4em]">Filtering Foundational Matrices...</div>';
            
            try {
                const url = this.state.scope === 'global'
                    ? \`/api/quran/search?q=\${encodeURIComponent(query)}\`
                    : \`/api/library/entries?query=\${encodeURIComponent(query)}&scope=org\`;
                
                const res = await fetch(url);
                const data = await res.json();
                
                grid.innerHTML = data.map((v, idx) => \`
                    <div class="entry-card card p-8 group relative bg-white">
                        <div class="space-y-6">
                            <div class="text-[13px] text-text-main font-medium leading-relaxed italic opacity-80 group-hover:opacity-100 transition-opacity">
                                "\${v.text || v.translation_text || v.content}"
                            </div>
                            <div class="pt-6 border-t border-brand/5 flex justify-between items-center">
                                <div class="text-[10px] font-black text-brand uppercase tracking-widest">\${v.title || v.reference || 'ARCHIVE'}</div>
                                <button onclick="NeuralLibrary.manifest('entry', '\${v.id}', \`\${(v.text || v.translation_text || v.content).replace(/\`/g, "\\'").replace(/"/g, '&quot;')}\`, '\${v.title || v.reference}')" class="px-6 py-3 bg-brand text-white rounded-xl text-[9px] font-black uppercase tracking-widest shadow-xl shadow-brand/10 hover:scale-[1.05] transition-all">Manifest</button>
                            </div>
                        </div>
                    </div>
                \`).join('');
            } catch (e) { console.error(e); }
        },

        manifest(type, id, text, reference) {
            console.log("Neural Hub: Manifesting Node " + id);
            const bridge = {
                type: type === 'quran' ? 'quran_verse' : 'quote',
                id: id,
                text: text,
                reference: reference,
                timestamp: Date.now()
            };
            sessionStorage.setItem('sabeel_pending_quote_item', JSON.stringify(bridge));
            window.location.href = '/app?studio=true';
        }
    };

    window.addEventListener('load', () => NeuralLibrary.init());
</script>
"""

@router.get("/library", response_class=HTMLResponse)
@router.get("/app/library", response_class=HTMLResponse)
async def neural_library_page(request: Request, user: User = Depends(require_user)):
    # Render with the isolated layout and core components
    final_content = LIBRARY_HTML
    
    # Bundle components and scripts into the layout
    return APP_LAYOUT_HTML.format(
        title="Knowledge Library",
        content=final_content,
        user_name=user.name or user.email,
        org_name=getattr(user.organization, 'name', 'Foundation'),
        active_dashboard="",
        active_calendar="",
        active_automations="",
        active_library="active",
        active_media="",
        admin_link="", # Admin check can be added
        connected_account_info="",
        studio_modal=STUDIO_COMPONENTS_HTML,
        connect_instagram_modal="",
        extra_js="",
        studio_js=STUDIO_SCRIPTS_JS,
        org_id=user.organization_id or "0"
    )
