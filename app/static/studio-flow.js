/* One editor journey; both destinations keep their canonical save/review/publish services. */
(() => {
  const el = id => document.getElementById(id), modal = el('newPostModal');
  if (!modal) return;
  let destination = 'instagram', opening = false, submitted = false, recovery = null;
  const pin = window.createPinterestEditor({embedded:true, caption:()=>el('studioCaption').value, onChange:()=>window.rememberStudio(),
    onPublication:data=>{ submitted=['published','publishing','unknown'].includes(data.status); }});
  const step = () => Number(modal.dataset.step || 1);
  const snapshot = () => window.studioShareSnapshot();
  const notice = message => window.studioNotice(message);
  function blocked() {
    if (opening || pin.busy() || snapshot().busy) { notice('Finishing this step. Your work is kept here.'); return true; }
    return false;
  }
  function panes() {
    el('studioInstagramPanel').hidden = destination !== 'instagram';
    el('studioPinterestPanel').hidden = destination !== 'pinterest';
    document.querySelectorAll('[name="studioDestination"]').forEach(input=>{input.checked=input.value===destination;});
  }
  window.readStudioSharing = () => ({destination, pin:pin.snapshot() || recovery,
    timing:document.querySelector('[name="shareTiming"]:checked')?.value || 'now'});
  window.restoreStudioSharing = data => {
    destination = data?.destination === 'pinterest' ? 'pinterest' : 'instagram'; recovery=data?.pin || null;
    window.setStudioShareTiming(data?.timing === 'later' ? 'later' : 'now'); panes();
  };
  window.resetStudioSharing = () => {
    pin.reset(); destination='instagram'; recovery=null; submitted=false;
    el('studioPinterestEditor').hidden=true; el('studioPinterestStatus').textContent='';
    el('studioInstagramReviewed').checked=false; panes();
  };
  window.invalidateStudioShareReview = () => { el('studioInstagramReviewed').checked=false; pin.invalidate(); };
  window.validateStudioInstagramReview = () => {
    if(destination !== 'instagram' || blocked()) return false;
    if (!el('studioCaption').value.trim() && snapshot().payload.post_format !== 'story_9_16') {
      notice('Add your Instagram caption in the Caption step before publishing or scheduling.'); return false;
    }
    if (!el('studioInstagramReviewed').checked) { notice('Check the image, caption and Instagram account, then confirm below.'); return false; }
    return true;
  };
  el('studioAccount').addEventListener('change', window.invalidateStudioShareReview);
  el('studioInstagramReviewed').addEventListener('change', refresh);
  window.beforeStudioClose = () => {
    if (blocked()) return false;
    // Pin edits are included in device recovery by rememberStudio before closing.
    return true;
  };
  window.beforeStudioStep = target => {
    if (blocked()) return false;
    if(target===4 && el('creatorSuggestion')?.dataset.pending === 'true') { notice('Use the caption suggestion or keep your version before continuing.'); return false; }
    if (submitted && target !== 4) { notice('This post has been submitted. Its saved result is kept read-only. Close Studio to start a new post.'); return false; }
    return true;
  };
  window.chooseStudioDestination = async name => {
    if (!['instagram','pinterest'].includes(name)) return;
    if (blocked()) { panes(); return; }
    if (submitted) { if(name !== destination) notice('This post has been submitted. Close Studio to view its saved result.'); panes(); return; }
    recovery = pin.snapshot() || recovery;
    destination=name; panes(); window.invalidateStudioShareReview(); window.rememberStudio();
    if (name !== 'pinterest') return;
    const state=snapshot();
    el('studioPinterestEditor').hidden=true; el('studioPinterestRetry').hidden=true;
    if (state.pages.length !== 1 || state.payload.post_format !== 'feed_4_5') {
      el('studioPinterestStatus').textContent='Pinterest needs one complete 4:5 card. Your full sequence stays intact: share it to Instagram or use Download above. You can change the format in Design.'; return;
    }
    if (!state.reviewed || state.dirty) { el('studioPinterestStatus').textContent='Review your latest design before preparing this Pin.'; return; }
    opening=true; refresh(); el('studioPinterestStatus').textContent='Saving your card and opening Pinterest options…';
    try {
      const post=await window.persistStudioDraft(); if(!post) throw Error('Your card could not be saved. Try again.');
      el('studioPinterestEditor').hidden=false;
      if (!await pin.open(post.id,recovery)) throw Error('Pinterest options could not load. Your saved card is safe; try again.');
      el('studioPinterestStatus').textContent='Same image and source. Add the copy you want people to see on Pinterest.';
      recovery=pin.snapshot(); window.rememberStudio();
    } catch(error) { el('studioPinterestStatus').textContent=error.message; el('studioPinterestRetry').hidden=false; }
    finally { opening=false; refresh(); }
  };
  const originalSection=window.onCreatorSection;
  window.onCreatorSection = n => {
    originalSection?.(n);
    if(n===4 && destination==='pinterest') window.chooseStudioDestination('pinterest');
    refresh();
  };
  const originalSave=window.saveStudioDraft;
  window.saveStudioDraft = async () => {
    if(blocked()) return;
    if(destination==='pinterest' && step()===4 && !el('studioPinterestEditor').hidden && pin.snapshot()) {
      await pin.save(); window.rememberStudio();
    } else await originalSave();
  };
  // Reuse the actual controls: no parallel source/design/caption state.
  window.studioSharingSubmitted=()=>submitted;
  let action=null, downloadKey='';
  function refresh() {
    const n=step(), state=snapshot(), bar=el('studioStepBar'), next=el('studioStepNext');
    document.querySelectorAll('[name="studioDestination"]').forEach(input=>{const locked=opening || pin.busy() || submitted; if(input.disabled!==locked) input.disabled=locked;});
    const downloads=el('studioDownloadPages'), key=JSON.stringify(state.pages.map(p=>[p.url,p.width,p.height]));
    if(downloads && key!==downloadKey) {
      downloadKey=key;downloads.replaceChildren();
      state.pages.forEach((page,index)=>{const button=document.createElement('button');button.type='button';button.textContent=`Image ${index+1} · ${page.width || 1080} × ${page.height || (state.payload.post_format==='story_9_16' ? 1920 : 1350)} · JPG`;button.onclick=()=>window.downloadStudioImage(index+1);downloads.appendChild(button);});
    }
    const downloadDisabled=!!(opening || pin.busy() || state.busy || state.dirty || !state.payload.media_url);
    for(const button of [el('studioDownloadAll'),...(downloads?.querySelectorAll('button') || [])]) if(button && button.disabled!==downloadDisabled) button.disabled=downloadDisabled;
    const help=el('studioDownloadHelp'), downloadHelp=state.dirty ? 'Apply design changes first.' : state.payload.media_url ? 'On a phone, open the downloaded JPG in Files and choose Save Image to add it to Photos.' : 'Create a design to download your images.';
    if(help && help.textContent!==downloadHelp) help.textContent=downloadHelp;
    const guided = el('creatorGuided') && !el('creatorGuided').hidden;
    const visible=!modal.dataset.brandOnly && (n!==1 || !guided);
    if(bar.hidden===visible) bar.hidden=!visible;
    let target=null, label='', disabled=opening || pin.busy() || state.busy;
    if(n===1) { target=el('btnBuildMessage'); label=target?.disabled ? 'Choose a source to continue' : 'Continue to design'; }
    if(n===2) {
      if(!state.payload.media_url || state.dirty) {target=el('btnGenerateCard'); label=modal.dataset.editPreview==='true' ? 'Finish design' : state.payload.media_url ? 'Apply design changes' : 'Create my design';}
      else { target=el('cardActions')?.querySelector('button'); label='Continue to caption'; disabled ||= !el('sequenceReviewCheck').checked || el('sequenceReviewCheck').disabled; }
    }
    if(n===2 && state.dirty && state.payload.media_url && window.studioPreviewRequest?.().style==='realistic_paper' && !window.studioPreviewRequest().background_token) label='Create new paper background';
    if(n===2 && (!state.payload.media_url || state.dirty) && window.studioSelectedFit?.()?.available === false && !state.generating) { target=el('studioChooseFamily'); label='Choose a fitting style'; }
    if(n===4) {
      if(destination==='instagram') {
        target=el('studioAccount').value ? (el('studioShareNowBtn').hidden ? el('studioSubmitBtn') : el('studioShareNowBtn')) : el('studioSaveDraftButton');
        label=target===el('studioSubmitBtn') ? 'Schedule Instagram post' : target===el('studioShareNowBtn') ? 'Publish to Instagram' : 'Save draft';
        if(target!==el('studioSaveDraftButton')) disabled ||= !el('studioInstagramReviewed').checked;
      } else {
        target=!el('creatorPinCheckStatus').hidden ? el('creatorPinCheckStatus') : !el('creatorPinPublishedLink').hidden ? el('creatorPinPublishedLink') : !el('creatorPinApproval').hidden ? el('creatorPinPublish') : el('creatorPinReview');
        label=target===el('creatorPinReview') ? 'Review Pin' : target.textContent;
        disabled ||= el('studioPinterestEditor').hidden;
      }
    }
    if(n===3) { label='Choose where to share'; action=()=>window.switchStudioSection(4); }
    else action=()=>target?.click();
    disabled ||= !!target?.disabled;
    if(n===2 && state.generating) label='Creating your design…';
    if(n===3 && el('creatorSuggestion')?.dataset.pending==='true') { disabled=true; label='Choose a caption version above'; }
    if(next.textContent!==label) next.textContent=label;
    if(next.disabled!==disabled) next.disabled=disabled;
    const back=el('studioStepBack'); if(back.hidden===(n>1)) back.hidden=n<=1;
    const backLabel=submitted ? 'Done' : 'Back'; if(back.textContent!==backLabel) back.textContent=backLabel;
    const heading=el('studioShareTitle'), title=submitted ? 'Your saved result' : 'Ready to share?'; if(heading && heading.textContent!==title) heading.textContent=title;
    const saveDisabled=!!(opening || pin.busy() || state.busy || submitted);
    if(el('studioSaveDraftButton').disabled!==saveDisabled) el('studioSaveDraftButton').disabled=saveDisabled;
    // Mark only the current primary action as mirrored by the persistent footer.
    for(const button of [el('btnBuildMessage'),el('btnGenerateCard'),el('cardActions')?.querySelector('button'),el('studioCaptionContinue'), el('studioSubmitBtn'),el('studioShareNowBtn'),el('creatorPinReview'),el('creatorPinPublish'),el('creatorPinCheckStatus'),el('creatorPinPublishedLink')]) {
      if(!button) continue;
      const mirror=visible && (button===target || (n===3 && button.id==='studioCaptionContinue'));
      if(button.classList.contains('cw-mirrored-action')!==mirror) button.classList.toggle('cw-mirrored-action',mirror);
    }
    const fresh=!!state.payload.media_url;
    const generateHidden=fresh && !state.dirty;
    if(el('btnGenerateCard').hidden!==generateHidden) el('btnGenerateCard').hidden=generateHidden;
    if(modal.dataset.hasVisual!==String(fresh)) modal.dataset.hasVisual=String(fresh);
  }
  el('studioStepNext').onclick=()=>{if(!el('studioStepNext').disabled) action?.();};
  el('studioStepBack').onclick=()=>{if(submitted) { window.closeNewPostModal(); window.location.href='/app?view=posts'; } else window.switchStudioSection(Math.max(1,step()-1));};
  modal.addEventListener('change',refresh); modal.addEventListener('input',refresh);
  new MutationObserver(refresh).observe(el('composerForm'),{subtree:true,childList:true,attributes:true,attributeFilter:['disabled','hidden','class','data-pending']});
  // Existing management page keeps its card picker. Studio already knows its card.
  for(const selector of ['.choose','#creatorPinEmpty','#creatorPinEditor .card-context']) el('studioPinterestEditor').querySelector(selector)?.setAttribute('hidden','');
  el('creatorPinSave').textContent='Save Pin draft';
  el('creatorPinWriteTab').textContent='Pin details'; el('creatorPinPreviewTab').textContent='Review & publish';
  const params=new URLSearchParams(location.search), returnPost=params.get('studio_post');
  if(returnPost && /^[1-9]\d*$/.test(returnPost)) {
    (async()=>{
      await window.resumeStudioPost(Number(returnPost));
      destination='pinterest'; panes();
      notice(params.get('result')==='connected' ? 'Pinterest connected. Check your saved design, then continue to Share to choose a board.' : 'Pinterest connection was not completed. Your saved design is kept.');
    })();
  }
  window.refreshStudioFlow=refresh;
  refresh();
})();
