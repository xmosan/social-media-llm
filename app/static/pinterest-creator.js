/* Saved drafts enter the shared publisher only after an explicit review. */
window.createPinterestEditor = (options = {}) => {
  const el = id => document.getElementById('creatorPin' + id);
  let current = null, busy = false, dirty = false, before = null, epoch = 0;
  const initial = options.embedded ? null : document.body.dataset.post;
  const fields = ['Title', 'Description', 'Alt', 'AI', 'Link'];
  let unappliedRecovery = null;
  let account = null, receipt = null, imageReady = false, deliveryUncertain = false, boardBookmark = null;
  async function api(path, options = {}) {
    const response = await fetch('/api/creator/pinterest/' + path, {...options, signal: AbortSignal.timeout(90000)});
    let data;
    try { data = await response.json(); } catch { throw Error('Sabeel could not load this draft. Sign in again if your session expired.'); }
    if (!response.ok) throw Object.assign(Error(typeof data.detail === 'string' ? data.detail : 'Check the Pin fields and try again.'), {status:response.status});
    return data;
  }
  function setBusy(value) {
    busy = value;
    el('Post').disabled = value;
    el('More').disabled = value;
    el('Save').disabled = value || !current || current.locked;
    el('Fields').disabled = value || !current || current.locked;
    el('Reload').disabled = value;
    el('Save').textContent = value ? 'Please wait…' : options.embedded ? 'Save Pin draft' : 'Save draft';
    for (const id of ['LoadBoards','MoreBoards','Board','UseBoard','Disconnect','CheckStatus','Verify']) if (el(id)) el(id).disabled = value;
    controls();
    options.onBusy?.(value);
  }
  function controls() {
    const ready = !unappliedRecovery && account?.enabled && account?.connected && account?.board_id && current && !current.locked && !deliveryUncertain;
    el('Review').hidden=!!receipt || !!current?.locked;
    el('Review').disabled = busy || !ready || !imageReady;
    el('Publish').disabled = busy || !ready || !receipt || dirty || !imageReady || !el('Reviewed').checked;
  }
  function invalidateReview() { receipt = null; el('Approval').hidden = true; el('Reviewed').checked = false; controls(); }
  function version() { return {revision:current.revision, source_version:current.source_version}; }
  function json(method, value) { return {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(value)}; }
  function publication(data) {
    const locked = ['published','publishing','unknown'].includes(data.status);
    if (current && data.status) current.locked = locked;
    el('PublishedLink').hidden = data.status !== 'published';
    if (data.status === 'published') el('PublishedLink').href = data.url;
    options.onPublication?.(data);
    el('PublishedLink').textContent = data.sandbox ? 'View sandbox result ↗' : 'View on Pinterest ↗';
    el('Verify').hidden = data.status !== 'published' || !account?.enabled || data.sandbox;
    el('CheckStatus').hidden = !deliveryUncertain && !['publishing','unknown'].includes(data.status);
    const messages = {published:'Published to ' + (data.board_name || 'your board') + '. Your saved result is kept here.',
      publishing:'Pinterest delivery is pending. Do not send again; check the saved result.',
      unknown:'Pinterest delivery is uncertain. Do not send again. Check Pinterest and contact Sabeel support if needed.',
      failed:data.error || 'Pinterest rejected this Pin. Review the details before trying again.'};
    if (data.sandbox && data.status === 'published') messages.published = 'Sandbox test result. This was not published publicly. Create a new card for a public Pin.';
    el('PublishStatus').textContent = messages[data.status] || (deliveryUncertain ? 'Delivery could not be confirmed. Check the saved result before taking further action.' : 'Save your copy and review the image before publishing.');
    if (locked) { invalidateReview(); el('Fields').disabled = true; el('Save').disabled = true; }
    controls();
  }
  function applyAccount(data) {
    account = data;
    el('AccountStatus').textContent = data.connected ? 'Connected as @' + data.username : data.enabled ? 'Connect your Pinterest' : 'Draft access';
    if (el('Connect')) el('Connect').hidden = !data.enabled || data.connected;
    if (el('Connected')) el('Connected').hidden = !data.enabled || !data.connected;
    el('AccountStatus').textContent += !data.enabled ? ' · Publishing unavailable' : '';
    if (el('BoardSummary')) el('BoardSummary').textContent = data.board_name ? 'Publishing to ' + data.board_name : 'Choose a public board';
    invalidateReview();
  }
  async function loadAccount() {
    try { applyAccount(await api('connection')); return true; }
    catch (error) { account=null; controls(); el('AccountStatus').textContent = 'Connection could not load. Try again to check your account.'; return false; }
  }
  async function boards(more = false) {
    if (busy) return; setBusy(true); el('ConnectionNotice').textContent = 'Loading your boards…';
    try {
      const data = await api('boards' + (more && boardBookmark ? '?bookmark=' + encodeURIComponent(boardBookmark) : ''));
      if (!more) el('Board').replaceChildren(new Option('Choose a public board…',''));
      for (const board of data.items) if (![...el('Board').options].some(o => o.value === board.id)) el('Board').add(new Option(board.name,board.id));
      boardBookmark = data.bookmark; el('MoreBoards').hidden = !boardBookmark;
      el('ConnectionNotice').textContent = data.items.length ? '' : 'No boards on this page. Load more if available, or create a public board in Pinterest.';
    } catch (error) { el('ConnectionNotice').textContent = error.message; }
    finally { setBusy(false); }
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
    invalidateReview(); imageReady = false;
    const value = data.copy;
    el('Title').value = value.title; el('Description').value = value.description;
    el('Alt').value = value.alt_text; el('AI').value = value.ai_modified === null ? '' : value.ai_modified ? 'yes' : 'no';
    el('Link').value = value.link || '';
    for (const [id, key] of [['Reference','source_reference'],['SourceReference','source_reference'],['Arabic','arabic'],['Translation','translation'],['SourceDetails','source_details'],['Reflection','reflection']]) el(id).textContent = data[key] || '';
    el('ReflectionBlock').hidden = !data.reflection;
    el('Thumb').src = data.image_url;
    el('ImageStatus').textContent = 'Loading saved image…';
    el('Image').onload = () => { if(current !== data || el('Image').src !== data.image_url) return; imageReady = true; el('ImageStatus').textContent = ''; controls(); };
    el('Image').onerror = () => { imageReady = false; controls(); el('ImageStatus').textContent = 'The saved image could not load. Your copy is kept; reload the page to try again.'; };
    el('Image').src = data.image_url;
    if(el('Image').complete && el('Image').naturalWidth > 0) el('Image').onload();
    el('Editor').hidden = false;
    el('SaveStatus').textContent = data.locked ? 'Submitted copy · Read-only' : data.saved_at ? 'Saved draft · Not published' : 'Not saved yet';
    el('Notice').hidden = !(data.locked || data.source_changed);
    el('Notice').textContent = data.locked ? 'This card has a Pinterest publishing attempt. Its submitted copy is kept read-only.' : 'The card changed in Studio. Review its latest source and image before saving this copy again.';
    el('Issues').textContent = data.issues.length ? 'You can save an unfinished draft. ' + data.issues.join(' ') : 'Copy prepared. Review the full card before sharing.';
    el('Reload').hidden = true;
    preview();
    publication(data.publication || {status:data.publication_status});
  }
  function discard() { return !dirty || window.confirm('Leave your unsaved Pin edits? Cancel to save them first.'); }
  async function load(id) {
    if (!id || busy) return;
    const request = ++epoch;
    current = null; dirty = false; deliveryUncertain = false; invalidateReview(); el('Editor').hidden = true; el('LoadStatus').textContent = 'Loading card…';
    el('Retry').hidden = true; setBusy(true);
    try {
      const data = await api('posts/' + encodeURIComponent(id));
      if (request !== epoch) return;
      apply(data); tab('Write'); el('LoadStatus').textContent = '';
      const match = [...el('Post').options].some(option => option.value === String(id));
      if (!match) el('Post').add(new Option(data.source_reference, String(id)));
      el('Post').value = String(id);
      if (!options.embedded) history.replaceState(null, '', '/app/pinterest?post=' + encodeURIComponent(id));
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
    dirty = true; invalidateReview(); options.onChange?.(); el('SaveStatus').textContent = 'Unsaved changes'; el('Issues').textContent = ''; preview();
  });
  for (const name of ['Write','Preview']) {
    el(name + 'Tab').addEventListener('click', () => tab(name));
    el(name + 'Tab').addEventListener('keydown', event => {
      if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) { event.preventDefault(); tab(event.key === 'Home' ? 'Write' : event.key === 'End' ? 'Preview' : name === 'Write' ? 'Preview' : 'Write', true); }
    });
  }
  el('ReviewCard').addEventListener('click', () => { tab('Preview', true); el('PreviewTab').scrollIntoView({block:'start'}); });
  async function save() {
    if (busy) return false;
    if (!current || current.locked || (!dirty && current.saved_at)) return true;
    setBusy(true); el('SaveStatus').textContent = 'Saving…';
    try {
      const data = await api('posts/' + current.post_id, json('PUT',{...copy(), ...version()}));
      apply(data); options.onChange?.(); return true;
    } catch (error) {
      dirty = true; el('SaveStatus').textContent = 'Not confirmed saved';
      el('Notice').hidden = false; el('Notice').textContent = error.message + ' Your edits are still on this page.';
      el('Reload').hidden = false; return false;
    } finally { setBusy(false); }
  }
  el('Form').addEventListener('submit', async event => { event.preventDefault(); await save(); });
  window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  if (el('LoadBoards')) el('LoadBoards').addEventListener('click', () => boards());
  if (el('MoreBoards')) el('MoreBoards').addEventListener('click', () => boards(true));
  if (el('Board')) el('Board').addEventListener('change', invalidateReview);
  if (el('UseBoard')) el('UseBoard').addEventListener('click', async () => {
    if (busy || !el('Board').value) return; invalidateReview(); setBusy(true);
    try { applyAccount(await api('board',json('POST',{board_id:el('Board').value}))); el('BoardDetails').open = false; el('ConnectionNotice').textContent = 'Board saved.'; }
    catch (error) { el('ConnectionNotice').textContent = error.message; }
    finally { setBusy(false); }
  });
  for (const id of ['Connect','Reconnect']) if (el(id)) el(id).addEventListener('submit', event => {
    if (busy || !discard()) { event.preventDefault(); return; }
    if (options.embedded) {
      if (!current || dirty) { event.preventDefault(); el('ConnectionNotice').textContent = 'Save your Pin edits before connecting. They are kept here.'; return; }
      event.target.action = '/api/creator/pinterest/connect?studio_post=' + current.post_id;
    }
    dirty = false; setBusy(true); el('ConnectionNotice').textContent = 'Opening Pinterest…';
  });
  if (el('Disconnect')) el('Disconnect').addEventListener('click', async () => {
    if (busy || !window.confirm('Disconnect Pinterest from Sabeel? Your drafts will stay saved.')) return;
    invalidateReview(); setBusy(true);
    try { await api('disconnect',{method:'POST'}); await loadAccount(); el('ConnectionNotice').textContent = 'Disconnected. Your drafts are kept.'; }
    catch (error) { el('ConnectionNotice').textContent = error.message; }
    finally { setBusy(false); }
  });
  el('Reviewed').addEventListener('change', controls);
  el('Review').addEventListener('click', async () => {
    if (busy || !current || current.locked || deliveryUncertain) return;
    invalidateReview(); setBusy(true); el('PublishStatus').textContent = 'Checking the saved card and destination…';
    try {
      if (dirty || !current.saved_at) { apply(await api('posts/' + current.post_id,json('PUT',{...copy(),...version()}))); options.onChange?.(); }
      const data = await api('posts/' + current.post_id + '/review',json('POST',version()));
      receipt = data.receipt; if(options.embedded) { tab('Preview'); el('PreviewTab').scrollIntoView({block:'start'}); } el('Destination').textContent = '@' + data.username + ' → ' + data.board_name;
      el('Approval').hidden = false; el('PublishStatus').textContent = 'Review your image and copy above, then confirm below.';
    } catch (error) { el('PublishStatus').textContent = error.message; el('Notice').hidden=false; el('Notice').textContent=error.message; el('Notice').scrollIntoView({block:'center'}); }
    finally { setBusy(false); }
  });
  el('Publish').addEventListener('click', async () => {
    if (el('Publish').disabled || busy || !receipt || !el('Reviewed').checked || dirty) return;
    const payload = {...version(), receipt, reviewed:true}; setBusy(true); el('PublishStatus').textContent = 'Publishing your Pin…';
    try {
      const data = await api('posts/' + current.post_id + '/publish',json('POST',payload));
      invalidateReview(); publication(data);
      if (data.status === 'published') { current.locked = true; el('SaveStatus').textContent = 'Published · Read-only'; }
    } catch (error) {
      invalidateReview();
      if (error.status >= 400 && error.status < 500) {
        try { publication(await api('posts/' + current.post_id + '/status')); }
        catch { deliveryUncertain = true; publication({status:'unknown'}); }
      } else { deliveryUncertain = true; publication({status:'unknown'}); }
      el('PublishStatus').textContent = error.message + (current.locked || deliveryUncertain ? ' Check the saved result before trying anything else.' : ' Review this Pin again before publishing.');
    } finally { setBusy(false); }
  });
  el('CheckStatus').addEventListener('click', async () => {
    if (busy || !current) return; setBusy(true);
    try { const data = await api('posts/' + current.post_id + '/status'); deliveryUncertain = false; publication(data); }
    catch (error) { el('PublishStatus').textContent = error.message; }
    finally { setBusy(false); }
  });
  el('Verify').addEventListener('click', async () => {
    if (busy || !current) return; setBusy(true);
    try { const data = await api('posts/' + current.post_id + '/verify'); el('PublishStatus').textContent = data.message; }
    catch (error) { el('PublishStatus').textContent = error.message; }
    finally { setBusy(false); }
  });
  function recoverCopy(record) {
    const v=record.copy;
    el('Title').value=v.title; el('Description').value=v.description; el('Alt').value=v.alt_text;
    el('AI').value=v.ai_modified === null ? '' : v.ai_modified ? 'yes' : 'no'; el('Link').value=v.link || '';
    dirty=true; invalidateReview(); preview(); el('SaveStatus').textContent='Restored unsaved Pin edits';
  }
  el('KeepSaved')?.addEventListener('click',()=>{ if(busy) return; unappliedRecovery=null; el('Recovered').hidden=true; controls(); options.onChange?.(); });
  el('UseRecovered')?.addEventListener('click',()=>{
    if(busy || current?.locked || !unappliedRecovery) return;
    recoverCopy(unappliedRecovery); unappliedRecovery=null; el('Recovered').hidden=true; options.onChange?.();
  });
  if (!options.embedded) (async () => { await loadAccount(); await list(); if (initial) await load(initial); })();
  return {
    save, busy:()=>busy, dirty:()=>dirty, locked:()=>!!current?.locked,
    invalidate:invalidateReview,
    snapshot:()=>current ? {post_id:current.post_id, source_version:current.source_version, revision:current.revision, copy:copy(), dirty, recovered:unappliedRecovery} : null,
    async open(id, recovery) {
      if (busy) return;
      if (!await loadAccount()) return false;
      await load(id);
      if (options.embedded && current && !current.locked && !current.saved_at && !current.copy.description && !recovery?.dirty) {
        const caption=options.caption?.() || '';
        if(caption && caption.length<=800) { el('Description').value=caption; dirty=true; preview(); el('SaveStatus').textContent='Caption copied · edit it for Pinterest'; }
      }
      recovery=recovery?.recovered || recovery;
      unappliedRecovery=null; el('Recovered').hidden=true;
      if (current && recovery?.post_id === current.post_id && recovery.dirty && !current.locked) {
        if (recovery.revision === current.revision) {
          recoverCopy(recovery);
          if(recovery.source_version !== current.source_version) {el('Notice').hidden=false;el('Notice').textContent='Your design changed. Your Pin copy is kept; review it against the new image and source.';}
        } else {
          unappliedRecovery=recovery; el('Recovered').hidden=false;
          el('RecoveredCopy').textContent=JSON.stringify(recovery.copy,null,2);
          el('Notice').hidden=false;el('Notice').textContent='A newer version is saved. Your previous copy is available below. Choose which version to keep before publishing.';
        }
      }
      if (options.embedded && account?.connected && !account.board_id) { el('BoardDetails').open=true; await boards(); }
      controls(); return !!current;
    },
    reset() { if(busy) return false; epoch++; current=null; dirty=false; receipt=null; unappliedRecovery=null; deliveryUncertain=false; el('Editor').hidden=true; return true; }
  };
};
if (document.body.dataset.post !== undefined) window.createPinterestEditor();
