# Sabeel Knowledge Library: Neural Hub (v3.0 — Quran Browser Edition)
# Isolated Router with dedicated Quran browsing experience.

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from app.security.auth import require_user
from app.models import User
from .ui_assets import APP_LAYOUT_HTML, STUDIO_SCRIPTS_JS, STUDIO_COMPONENTS_HTML

router = APIRouter(tags=["Neural Hub"])

LIBRARY_HTML = """\
<div id="neuralHub">

<!-- ===== TAB NAVIGATION ===== -->
<div class="flex items-center gap-1 mb-10 border-b border-brand/8 pb-0">
  <button onclick="LibHub.setTab('quran')" id="tab-quran" class="lib-tab active px-6 py-4 text-[11px] font-black uppercase tracking-widest border-b-2 transition-all">Qur'an</button>
  <button onclick="LibHub.setTab('wisdom')" id="tab-wisdom" class="lib-tab px-6 py-4 text-[11px] font-black uppercase tracking-widest border-b-2 transition-all">Wisdom</button>
  <button onclick="LibHub.setTab('org')" id="tab-org" class="lib-tab px-6 py-4 text-[11px] font-black uppercase tracking-widest border-b-2 transition-all">Organization</button>
</div>

<!-- ===== QURAN TAB ===== -->
<div id="panel-quran" class="lib-panel">
  <div class="mb-8 flex flex-col md:flex-row md:items-end justify-between gap-4">
    <div>
      <div class="flex items-center gap-3 mb-2">
        <span class="text-[9px] font-black uppercase tracking-[0.4em] text-brand/40">Foundation</span>
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse inline-block"></span>
        <span class="text-[9px] font-black uppercase tracking-widest text-emerald-600">6,236 Verses Indexed</span>
      </div>
      <h1 class="text-5xl font-black text-brand tracking-tighter italic">The Holy Qur'an</h1>
      <p class="text-sm text-text-muted mt-2 italic">Sahih International Translation</p>
    </div>
    <div class="relative w-full md:w-96">
      <input type="text" id="quranSearch" oninput="QuranBrowser.onSearch()" placeholder="Search verse, surah, or reference (e.g. 2:255)..." class="w-full bg-white border border-brand/10 rounded-2xl pl-10 pr-10 py-3 text-sm font-medium text-brand outline-none focus:border-brand/30 transition-all placeholder:text-brand/25 shadow-sm">
      <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-brand/25" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" stroke-width="2" stroke-linecap="round"/></svg>
      <button onclick="QuranBrowser.clearSearch()" id="searchClear" class="absolute right-3 top-1/2 -translate-y-1/2 hidden text-brand/30 hover:text-brand transition-colors text-xl leading-none">&times;</button>
    </div>
  </div>

  <div id="quranLayout" class="flex gap-6" style="height: calc(100vh - 290px);">

    <!-- LEFT: Surah Index -->
    <div class="w-64 flex-shrink-0 bg-white rounded-2xl border border-brand/8 shadow-sm overflow-hidden flex flex-col">
      <div class="px-4 py-3 border-b border-brand/8 flex items-center justify-between gap-2">
        <span class="text-[10px] font-black uppercase tracking-widest text-brand/50 whitespace-nowrap">114 Surahs</span>
        <input type="text" id="surahFilter" oninput="QuranBrowser.filterSurahs()" placeholder="Filter..." class="w-24 text-xs bg-brand/5 border-0 rounded-lg px-2 py-1 text-brand outline-none placeholder:text-brand/30">
      </div>
      <div id="surahIndex" class="overflow-y-auto flex-1 custom-scrollbar">
        <div class="p-4 text-center text-brand/30 text-xs animate-pulse">Loading...</div>
      </div>
    </div>

    <!-- RIGHT: Verse Reading Panel -->
    <div class="flex-1 bg-white rounded-2xl border border-brand/8 shadow-sm overflow-hidden flex flex-col">

      <div id="surahHeader" class="px-8 py-5 border-b border-brand/8 flex items-start justify-between flex-shrink-0">
        <div>
          <div id="surahHeaderTitle" class="text-xl font-black text-brand tracking-tight">Select a Surah</div>
          <div id="surahHeaderMeta" class="text-xs text-text-muted mt-0.5">Choose from the index on the left to begin reading</div>
        </div>
        <div id="surahHeaderAr" class="text-2xl font-arabic text-brand/60 text-right ml-4"></div>
      </div>

      <div id="searchResultsPanel" class="hidden flex-1 overflow-y-auto custom-scrollbar">
        <div id="searchResults"></div>
      </div>

      <div id="versesPanel" class="flex-1 overflow-y-auto custom-scrollbar">
        <div id="versesContainer">
          <div id="versesPlaceholder" class="flex flex-col items-center justify-center py-24 text-center text-brand/20">
            <div class="text-6xl mb-4">&#x1F4D6;</div>
            <div class="text-sm font-bold uppercase tracking-widest">Select a Surah to Begin Reading</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ===== WISDOM TAB ===== -->
<div id="panel-wisdom" class="lib-panel hidden">
  <div class="mb-8">
    <h1 class="text-5xl font-black text-brand tracking-tighter italic mb-2">Wisdom Archive</h1>
    <p class="text-sm text-text-muted italic">Curated quotes, hadith, and reflections</p>
  </div>
  <div class="relative mb-8">
    <input type="text" id="wisdomSearch" oninput="WisdomLib.search()" placeholder="Search wisdom, quotes, hadith..." class="w-full bg-white border border-brand/10 rounded-2xl pl-10 pr-4 py-4 text-sm font-medium text-brand outline-none focus:border-brand/30 transition-all placeholder:text-brand/25 shadow-sm">
    <svg class="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-brand/25" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" stroke-width="2" stroke-linecap="round"/></svg>
  </div>
  <div id="wisdomGrid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
    <div class="col-span-full py-12 text-center text-brand/30 text-xs uppercase tracking-widest animate-pulse">Loading wisdom archive...</div>
  </div>
</div>

<!-- ===== ORG TAB ===== -->
<div id="panel-org" class="lib-panel hidden">
  <div class="mb-8">
    <h1 class="text-5xl font-black text-brand tracking-tighter italic mb-2">Organization Knowledge</h1>
    <p class="text-sm text-text-muted italic">Your uploaded content, documents, and resource library</p>
  </div>
  <div id="orgGrid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
    <div class="col-span-full py-12 text-center text-brand/30 text-xs uppercase tracking-widest animate-pulse">Loading organization library...</div>
  </div>
</div>

</div>

<style>
  .lib-tab { color: rgba(15,61,46,0.35); border-color: transparent; }
  .lib-tab.active { color: var(--brand); border-color: var(--brand); }
  .lib-tab:hover:not(.active) { color: rgba(15,61,46,0.6); }
  .surah-item { cursor: pointer; transition: all 120ms ease; padding: 10px 16px; display: flex; align-items: center; gap: 10px; }
  .surah-item:hover { background: rgba(15,61,46,0.04); }
  .surah-item.active { background: rgba(15,61,46,0.07); border-right: 3px solid var(--brand); }
  .surah-num { width: 26px; font-size: 9px; font-weight: 900; color: rgba(15,61,46,0.3); text-align: right; flex-shrink: 0; }
  .surah-name-en { font-size: 12px; font-weight: 700; color: var(--brand); flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .surah-name-ar { font-size: 12px; color: rgba(15,61,46,0.55); flex-shrink: 0; font-family: 'Amiri', serif; }
  .verse-row { padding: 22px 32px; display: flex; gap: 20px; transition: background 150ms ease; border-bottom: 1px solid rgba(15,61,46,0.05); }
  .verse-row:hover { background: rgba(15,61,46,0.018); }
  .verse-num-badge { width: 32px; height: 32px; border-radius: 50%; border: 1.5px solid rgba(15,61,46,0.15); display: flex; align-items: center; justify-content: center; font-size: 9px; font-weight: 900; color: rgba(15,61,46,0.4); flex-shrink: 0; margin-top: 6px; }
  .verse-content { flex: 1; min-width: 0; }
  .verse-arabic { font-family: 'Amiri', 'Scheherazade New', 'Noto Naskh Arabic', serif; font-size: 22px; line-height: 2; text-align: right; color: #1a3a2e; direction: rtl; margin-bottom: 10px; }
  .verse-translation { font-size: 14px; line-height: 1.75; color: #4a5568; font-style: italic; margin-bottom: 10px; }
  .verse-translation.missing { color: rgba(15,61,46,0.2); font-style: normal; font-size: 11px; }
  .verse-meta { display: flex; align-items: center; justify-content: space-between; }
  .verse-ref { font-size: 9px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.2em; color: rgba(15,61,46,0.35); }
  .verse-actions { display: flex; gap: 8px; opacity: 0; transition: opacity 150ms ease; }
  .verse-row:hover .verse-actions { opacity: 1; }
  .btn-manifest { background: var(--brand); color: white; border: none; padding: 6px 14px; border-radius: 20px; font-size: 9px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.1em; cursor: pointer; transition: all 150ms ease; white-space: nowrap; }
  .btn-manifest:hover { background: var(--brand-hover); transform: scale(1.03); }
  .btn-copy { background: transparent; border: 1px solid rgba(15,61,46,0.15); color: rgba(15,61,46,0.5); padding: 6px 12px; border-radius: 20px; font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; cursor: pointer; transition: all 150ms ease; white-space: nowrap; }
  .btn-copy:hover { border-color: var(--brand); color: var(--brand); }
  .custom-scrollbar::-webkit-scrollbar { width: 4px; }
  .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
  .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(15,61,46,0.15); border-radius: 4px; }
  .wisdom-card { background: white; border: 1px solid rgba(15,61,46,0.08); border-radius: 16px; padding: 24px; transition: all 200ms ease; }
  .wisdom-card:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(15,61,46,0.08); }
  @import url('https://fonts.googleapis.com/css2?family=Amiri:ital@0;1&display=swap');
</style>

<script>
window.LibHub = {
  currentTab: 'quran',
  setTab(id) {
    this.currentTab = id;
    document.querySelectorAll('.lib-tab').forEach(t => t.classList.remove('active'));
    document.getElementById('tab-' + id).classList.add('active');
    document.querySelectorAll('.lib-panel').forEach(p => p.classList.add('hidden'));
    document.getElementById('panel-' + id).classList.remove('hidden');
    if (id === 'quran' && !QuranBrowser._loaded) QuranBrowser.init();
    if (id === 'wisdom' && !WisdomLib._loaded) WisdomLib.init();
    if (id === 'org' && !OrgLib._loaded) OrgLib.init();
  }
};

window.QuranBrowser = {
  _loaded: false,
  _surahs: [],
  _currentSurah: null,
  _searchTimer: null,

  async init() {
    this._loaded = true;
    await this.loadSurahIndex();
    this.loadSurah(1);
  },

  async loadSurahIndex() {
    try {
      const res = await fetch('/api/quran/surahs');
      const data = await res.json();
      this._surahs = Array.isArray(data) ? data : [];
      this.renderSurahIndex(this._surahs);
    } catch(e) {
      document.getElementById('surahIndex').innerHTML = '<div class="p-4 text-rose-400 text-xs">Failed to load surah list.</div>';
    }
  },

  renderSurahIndex(surahs) {
    const el = document.getElementById('surahIndex');
    if (!surahs.length) {
      el.innerHTML = '<div class="p-4 text-brand/25 text-xs text-center italic">No surahs found</div>';
      return;
    }
    el.innerHTML = surahs.map(s => `
      <div class="surah-item ACTIVE_CLASS" id="surah-item-SURAHNUM" onclick="QuranBrowser.loadSurah(SURAHNUM)"
           style="ACTIVE_CLASS"
      >
        <span class="surah-num">SURAHNUM</span>
        <span class="surah-name-en">NAMEEN</span>
        <span class="surah-name-ar">NAMEAR</span>
      </div>
    `.replace(/SURAHNUM/g, s.number)
     .replace('NAMEEN', (s.name_en || '').replace(/</g,'&lt;'))
     .replace('NAMEAR', (s.name_ar || '').replace(/</g,'&lt;'))
     .replace(/ACTIVE_CLASS/g, this._currentSurah == s.number ? 'active' : '')
    ).join('');
  },

  filterSurahs() {
    const q = (document.getElementById('surahFilter').value || '').toLowerCase();
    const filtered = this._surahs.filter(s =>
      s.name_en.toLowerCase().includes(q) ||
      (s.name_ar || '').includes(q) ||
      String(s.number).startsWith(q)
    );
    this.renderSurahIndex(filtered);
  },

  async loadSurah(num) {
    this._currentSurah = num;
    document.querySelectorAll('.surah-item').forEach(el => el.classList.remove('active'));
    const item = document.getElementById('surah-item-' + num);
    if (item) {
      item.classList.add('active');
      item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    this.hideSearch();

    const container = document.getElementById('versesContainer');
    const placeholder = document.getElementById('versesPlaceholder');
    if (placeholder) placeholder.remove();
    container.innerHTML = '<div class="px-8 py-20 text-center text-brand/20 text-xs animate-pulse uppercase tracking-widest">Loading verses\u2026</div>';
    document.getElementById('surahHeaderTitle').textContent = 'Loading\u2026';
    document.getElementById('surahHeaderMeta').textContent = '';
    document.getElementById('surahHeaderAr').textContent = '';

    try {
      const res = await fetch('/api/quran/surahs/' + num);
      const data = await res.json();
      const verses = data.verses || [];
      const meta = this._surahs.find(s => s.number == num) || {};

      document.getElementById('surahHeaderTitle').textContent = num + '. ' + (data.name_en || meta.name_en || 'Surah ' + num);
      document.getElementById('surahHeaderMeta').textContent = (data.revelation_place || meta.revelation_type || '') + ' \u00b7 ' + (data.total_verses || verses.length) + ' verses \u00b7 Sahih International';
      document.getElementById('surahHeaderAr').textContent = data.name_ar || meta.name_ar || '';

      if (!verses.length) {
        container.innerHTML = '<div class="px-8 py-16 text-center text-brand/30 text-sm italic">No verses found. Translations may still be loading \u2014 please refresh in a moment.</div>';
        return;
      }

      const surahName = data.name_en || 'Surah ' + num;
      container.innerHTML = verses.map(v => this.renderVerse(v, surahName)).join('');
    } catch(e) {
      container.innerHTML = '<div class="px-8 py-16 text-center text-rose-400 text-sm">Failed to load verses. Please try again.</div>';
    }
  },

  renderVerse(v, surahName) {
    const ref = v.reference || v.verse_key || '';
    const arabic = (v.arabic_text || '').replace(/</g, '&lt;');
    const translationRaw = v.translation_text || '';
    const hasTrans = translationRaw && translationRaw !== '[Translation not available]';
    const translation = hasTrans ? translationRaw.replace(/</g, '&lt;') : '';
    const verseNum = v.ayah_number || v.verse_number || '';
    const id = String(v.id || '');

    // Use data-attributes to avoid all JS string escaping issues in onclick
    return [
      '<div class="verse-row">',
        '<div class="verse-num-badge">' + verseNum + '</div>',
        '<div class="verse-content">',
          arabic ? '<div class="verse-arabic">' + arabic + '</div>' : '',
          hasTrans
            ? '<div class="verse-translation">&ldquo;' + translation + '&rdquo;</div>'
            : '<div class="verse-translation missing">Translation loading \u2014 check back shortly</div>',
          '<div class="verse-meta">',
            '<span class="verse-ref">Qur\u02bcaan ' + ref + '</span>',
            '<div class="verse-actions">',
              '<button class="btn-copy" data-ref="' + ref.replace(/"/g,'&quot;') + '" data-text="' + (translation || '').replace(/"/g,'&quot;') + '" onclick="QuranBrowser.handleCopy(this)">Copy</button>',
              '<button class="btn-manifest" data-id="' + id + '" data-ref="' + ref.replace(/"/g,'&quot;') + '" data-text="' + (translation || '').replace(/"/g,'&quot;') + '" data-arabic="' + (v.arabic_text || '').replace(/"/g,'&quot;') + '" onclick="QuranBrowser.handleManifest(this)">Use in Quote Card</button>',
            '</div>',
          '</div>',
        '</div>',
      '</div>'
    ].join('');
  },

  handleCopy(btn) {
    const ref = btn.getAttribute('data-ref');
    const text = btn.getAttribute('data-text');
    const full = '\u201c' + text + '\u201d \u2014 Qur\u02bcaan ' + ref;
    navigator.clipboard.writeText(full).then(() => {
      const orig = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(() => btn.textContent = orig, 1500);
    }).catch(() => {});
  },

  handleManifest(btn) {
    const bridge = {
      type: 'quran_verse',
      id: btn.getAttribute('data-id'),
      text: btn.getAttribute('data-text'),
      reference: btn.getAttribute('data-ref'),
      arabic_text: btn.getAttribute('data-arabic'),
      timestamp: Date.now()
    };
    sessionStorage.setItem('sabeel_pending_quote_item', JSON.stringify(bridge));
    window.location.href = '/app?studio=true';
  },

  onSearch() {
    const q = (document.getElementById('quranSearch').value || '').trim();
    document.getElementById('searchClear').classList.toggle('hidden', !q);
    clearTimeout(this._searchTimer);
    if (!q) { this.hideSearch(); return; }
    if (q.length < 2) return;
    this._searchTimer = setTimeout(() => this.runSearch(q), 350);
  },

  async runSearch(q) {
    document.getElementById('searchResultsPanel').classList.remove('hidden');
    document.getElementById('versesPanel').classList.add('hidden');
    document.getElementById('surahHeader').style.display = 'none';
    const el = document.getElementById('searchResults');
    el.innerHTML = '<div class="px-8 py-12 text-center text-brand/20 text-xs animate-pulse uppercase tracking-widest">Searching\u2026</div>';
    try {
      const res = await fetch('/api/quran/search?q=' + encodeURIComponent(q) + '&limit=20');
      const items = await res.json();
      const arr = Array.isArray(items) ? items : [];
      if (!arr.length) {
        el.innerHTML = '<div class="px-8 py-12 text-center text-brand/25 text-sm italic">No verses found for &ldquo;' + q + '&rdquo;</div>';
        return;
      }
      el.innerHTML = '<div class="px-8 py-3 text-[10px] font-black uppercase tracking-widest text-brand/40">' + arr.length + ' result' + (arr.length !== 1 ? 's' : '') + ' for &ldquo;' + q + '&rdquo;</div>' +
        arr.map(v => this.renderVerse(v, v.surah_name_en || '')).join('');
    } catch(e) {
      el.innerHTML = '<div class="px-8 py-12 text-center text-rose-400 text-sm">Search failed. Please try again.</div>';
    }
  },

  clearSearch() {
    document.getElementById('quranSearch').value = '';
    document.getElementById('searchClear').classList.add('hidden');
    this.hideSearch();
  },

  hideSearch() {
    document.getElementById('searchResultsPanel').classList.add('hidden');
    document.getElementById('versesPanel').classList.remove('hidden');
    document.getElementById('surahHeader').style.display = '';
  }
};

window.WisdomLib = {
  _loaded: false,
  _timer: null,

  async init() {
    this._loaded = true;
    await this.load('');
  },

  search() {
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this.load(document.getElementById('wisdomSearch').value), 300);
  },

  async load(q) {
    const grid = document.getElementById('wisdomGrid');
    grid.innerHTML = '<div class="col-span-full py-12 text-center text-brand/25 text-xs animate-pulse uppercase tracking-widest">Loading\u2026</div>';
    try {
      const url = q ? '/api/library/entries?query=' + encodeURIComponent(q) + '&scope=global' : '/api/library/entries?scope=global';
      const res = await fetch(url);
      const data = await res.json();
      const items = Array.isArray(data) ? data : (data.items || []);
      if (!items.length) {
        grid.innerHTML = '<div class="col-span-full py-12 text-center text-brand/25 text-sm italic">No results found</div>';
        return;
      }
      grid.innerHTML = items.map(item => {
        const txt = (item.content || item.text || item.translation_text || '').replace(/"/g, '&quot;').replace(/</g, '&lt;');
        const ref = (item.reference || item.title || 'Archive').replace(/"/g, '&quot;');
        const id = String(item.id || '');
        return '<div class="wisdom-card"><div class="text-sm leading-relaxed text-text-main italic mb-4">&ldquo;' + txt + '&rdquo;</div><div class="flex items-center justify-between pt-3 border-t border-brand/5"><span class="text-[9px] font-black uppercase tracking-widest text-brand/40">' + ref + '</span><button data-id="' + id + '" data-text="' + txt + '" data-ref="' + ref + '" onclick="WisdomLib.handleManifest(this)" class="btn-manifest text-[8px]">Use in Studio</button></div></div>';
      }).join('');
    } catch(e) { grid.innerHTML = '<div class="col-span-full py-12 text-center text-brand/25 text-sm italic">Failed to load</div>'; }
  },

  manifest(id, text, reference) {
    const bridge = { type: 'quote', id, text, reference, timestamp: Date.now() };
    sessionStorage.setItem('sabeel_pending_quote_item', JSON.stringify(bridge));
    window.location.href = '/app?studio=true';
  },
  handleManifest(btn) {
    this.manifest(btn.getAttribute('data-id'), btn.getAttribute('data-text'), btn.getAttribute('data-ref'));
  }
};

window.OrgLib = {
  _loaded: false,
  async init() {
    this._loaded = true;
    const grid = document.getElementById('orgGrid');
    try {
      const res = await fetch('/api/library/entries?scope=org');
      const data = await res.json();
      const items = Array.isArray(data) ? data : (data.items || []);
      if (!items.length) {
        grid.innerHTML = '<div class="col-span-full py-16 text-center"><p class="text-brand/25 text-sm italic">No organizational content yet.</p><p class="text-brand/20 text-xs mt-2">Upload documents or add content from the admin panel.</p></div>';
        return;
      }
      grid.innerHTML = items.map(item => {
        const txt = (item.content || item.text || '').replace(/"/g, '&quot;').replace(/</g, '&lt;');
        const ref = (item.title || 'Document').replace(/"/g, '&quot;');
        const id = String(item.id || '');
        return '<div class="wisdom-card"><div class="text-sm leading-relaxed text-text-main italic mb-4">&ldquo;' + txt + '&rdquo;</div><div class="flex items-center justify-between pt-3 border-t border-brand/5"><span class="text-[9px] font-black uppercase tracking-widest text-brand/40">' + ref + '</span><button data-id="' + id + '" data-text="' + txt + '" data-ref="' + ref + '" onclick="OrgLib.handleManifest(this)" class="btn-manifest text-[8px]">Use in Studio</button></div></div>';
      }).join('');
    } catch(e) { grid.innerHTML = '<div class="col-span-full py-12 text-center text-brand/25 text-sm italic">Failed to load</div>'; }
  },
  manifest(id, text, reference) {
    const bridge = { type: 'quote', id, text, reference, timestamp: Date.now() };
    sessionStorage.setItem('sabeel_pending_quote_item', JSON.stringify(bridge));
    window.location.href = '/app?studio=true';
  },
  handleManifest(btn) {
    this.manifest(btn.getAttribute('data-id'), btn.getAttribute('data-text'), btn.getAttribute('data-ref'));
  }
};

window.addEventListener('load', () => { LibHub.setTab('quran'); });
</script>
"""

from app.db import get_db
from sqlalchemy.orm import Session
from app.models import Org

@router.get("/library", response_class=HTMLResponse)
@router.get("/app/library", response_class=HTMLResponse)
async def neural_library_page(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    org = db.query(Org).filter(Org.id == user.active_org_id).first()
    org_name = org.name if org else "Foundation"

    return APP_LAYOUT_HTML.format(
        title="Knowledge Library",
        content=LIBRARY_HTML,
        user_name=user.name or user.email,
        org_name=org_name,
        active_dashboard="",
        active_calendar="",
        active_automations="",
        active_library="active",
        active_media="",
        admin_link="",
        connected_account_info="",
        studio_modal=STUDIO_COMPONENTS_HTML,
        connect_instagram_modal="",
        extra_js="",
        studio_js=STUDIO_SCRIPTS_JS,
        org_id=str(user.active_org_id or 0)
    )
