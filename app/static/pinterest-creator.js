/* Creator preparation has no OAuth, scheduling or publishing request path. */
(() => {
  const el = id => document.getElementById('creatorPin' + id);
  let current = null, busy = false, dirty = false, before = null, epoch = 0;
  const initial = document.body.dataset.post;
  const fields = ['Title', 'Description', 'Alt', 'AI', 'Link'];
  async function api(path, options = {}) {
    const response = await fetch('/api/creator/pinterest/' + path, {...options, signal: AbortSignal.timeout(20000)});
    let data;
    try { data = await response.json(); } catch { throw Error('Sabeel could not load this draft. Sign in again if your session expired.'); }
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Check the Pin fields and try again.');
    return data;
  }
  function setBusy(value) {
    busy = value;
    el('Post').disabled = value;
    el('More').disabled = value;
    el('Save').disabled = value || !current || current.locked;
    el('Fields').disabled = value || !current || current.locked;
    el('Reload').disabled = value;
    el('Save').textContent = value ? 'Please wait…' : 'Save draft';
  }
  function copy() {
    return {title: el('Title').value, description: el('Description').value, alt_text: el('Alt').value,
      ai_modified: el('AI').value === '' ? null : el('AI').value === 'yes', link: el('Link').value || null};
  }
  function preview() {
    const value = copy();
    el('PreviewTitle').textContent = value.title || 'Your Pin title';
    el('PreviewDescription').textContent = value.description || 'Your description will appear here.';
    el('PreviewAlt').textContent = value.alt_text || 'Add an image description for accessibility.';
    el('PreviewAI').textContent = value.ai_modified === null ? 'AI image disclosure: Not chosen yet.' : 'AI-generated or AI-modified imagery: ' + (value.ai_modified ? 'Yes' : 'No');
    el('PreviewLink').textContent = value.link || 'No destination link.';
    el('Image').alt = value.alt_text || 'Saved source card — complete text is available below.';
  }
  function tab(name, focus = false) {
    preview();
    for (const item of ['Write', 'Preview']) {
      el(item).hidden = item !== name;
      el(item + 'Tab').setAttribute('aria-selected', String(item === name));
      el(item + 'Tab').tabIndex = item === name ? 0 : -1;
    }
    if (focus) el(name + 'Tab').focus();
  }
  function apply(data) {
    current = data; dirty = false;
    const value = data.copy;
    el('Title').value = value.title; el('Description').value = value.description;
    el('Alt').value = value.alt_text; el('AI').value = value.ai_modified === null ? '' : value.ai_modified ? 'yes' : 'no';
    el('Link').value = value.link || '';
    for (const [id, key] of [['Reference','source_reference'],['SourceReference','source_reference'],['Arabic','arabic'],['Translation','translation'],['SourceDetails','source_details'],['Reflection','reflection']]) el(id).textContent = data[key] || '';
    el('ReflectionBlock').hidden = !data.reflection;
    el('Thumb').src = data.image_url;
    el('ImageStatus').textContent = 'Loading saved image…';
    el('Image').onload = () => { el('ImageStatus').textContent = ''; };
    el('Image').onerror = () => { el('ImageStatus').textContent = 'The saved image could not load. Your copy is kept; reload the page to try again.'; };
    el('Image').src = data.image_url;
    el('Editor').hidden = false;
    el('SaveStatus').textContent = data.locked ? 'Submitted copy · Read-only' : data.saved_at ? 'Saved draft · Not published' : 'Not saved yet';
    el('Notice').hidden = !(data.locked || data.source_changed);
    el('Notice').textContent = data.locked ? 'This card has a Pinterest publishing attempt. Its submitted copy is kept read-only.' : 'The card changed in Studio. Review its latest source and image before saving this copy again.';
    el('Issues').textContent = data.issues.length ? 'You can save an unfinished draft. ' + data.issues.join(' ') : 'Copy prepared. Publishing stays disabled pending approval.';
    el('Reload').hidden = true;
    preview();
  }
  function discard() { return !dirty || window.confirm('Leave your unsaved Pin edits? Cancel to save them first.'); }
  async function load(id) {
    if (!id || busy) return;
    const request = ++epoch;
    current = null; dirty = false; el('Editor').hidden = true; el('LoadStatus').textContent = 'Loading card…';
    el('Retry').hidden = true; setBusy(true);
    try {
      const data = await api('posts/' + encodeURIComponent(id));
      if (request !== epoch) return;
      apply(data); tab('Write'); el('LoadStatus').textContent = '';
      const match = [...el('Post').options].some(option => option.value === String(id));
      if (!match) el('Post').add(new Option(data.source_reference, String(id)));
      el('Post').value = String(id);
      history.replaceState(null, '', '/app/pinterest?post=' + encodeURIComponent(id));
    } catch (error) { el('LoadStatus').textContent = error.message; el('Retry').hidden = false; }
    finally { if (request === epoch) setBusy(false); }
  }
  async function list(older = false) {
    if (busy) return;
    setBusy(true); el('LoadStatus').textContent = 'Loading your saved cards…'; el('Retry').hidden = true;
    try {
      const data = await api('posts' + (older && before ? '?before=' + before : ''));
      if (!older) el('Post').replaceChildren(new Option('Choose a card…', ''));
      for (const row of data.items) el('Post').add(new Option(row.reference + ' · #' + row.id + (row.has_draft ? ' · Pin draft' : ''), String(row.id)));
      before = data.next_before; el('More').hidden = !before;
      el('Empty').hidden = el('Post').options.length > 1 || !!initial;
      el('LoadStatus').textContent = '';
    } catch (error) { el('LoadStatus').textContent = error.message; el('Retry').hidden = false; }
    finally { setBusy(false); }
  }
  el('Post').addEventListener('change', () => {
    const selected = el('Post').value;
    if (!discard()) { el('Post').value = current ? String(current.post_id) : ''; return; }
    if (selected) load(selected);
    else { current = null; dirty = false; el('Editor').hidden = true; }
  });
  el('More').addEventListener('click', () => list(true));
  el('Retry').addEventListener('click', () => { const id = el('Post').value || initial; if (id) load(id); else list(); });
  el('Reload').addEventListener('click', () => { if (current && discard()) load(current.post_id); });
  for (const field of fields) el(field).addEventListener('input', () => {
    dirty = true; el('SaveStatus').textContent = 'Unsaved changes'; el('Issues').textContent = ''; preview();
  });
  for (const name of ['Write','Preview']) {
    el(name + 'Tab').addEventListener('click', () => tab(name));
    el(name + 'Tab').addEventListener('keydown', event => {
      if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) { event.preventDefault(); tab(event.key === 'Home' ? 'Write' : event.key === 'End' ? 'Preview' : name === 'Write' ? 'Preview' : 'Write', true); }
    });
  }
  el('ReviewCard').addEventListener('click', () => { tab('Preview', true); el('PreviewTab').scrollIntoView({block:'start'}); });
  el('Form').addEventListener('submit', async event => {
    event.preventDefault(); if (busy || !current || current.locked) return;
    setBusy(true); el('SaveStatus').textContent = 'Saving…';
    try {
      const data = await api('posts/' + current.post_id, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...copy(), revision: current.revision, source_version: current.source_version})});
      apply(data);
    } catch (error) {
      dirty = true; el('SaveStatus').textContent = 'Not confirmed saved';
      el('Notice').hidden = false; el('Notice').textContent = error.message + ' Your edits are still on this page.';
      el('Reload').hidden = false;
    } finally { setBusy(false); }
  });
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  (async () => { await list(); if (initial) await load(initial); })();
})();
