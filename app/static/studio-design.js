/* Preview edits use the canonical renderer. Preview pixels are never saved as media. */
(() => {
  const el=id=>document.getElementById(id), modal=el('newPostModal');
  if(!modal || !window.studioPreviewRequest) return;
  let revision=0, timer=null, controller=null, page=0, lastKey='', renderedKey='', previewData=null;
  const photoFamilies=window.sabeelPhotoFamilies || [];
  const brand=el('creatorBrandKit'), home=document.createComment('appearance controls');brand.before(home);
  const launcher=document.createElement('button');launcher.type='button';launcher.className='sd-appearance';
  launcher.innerHTML='<span class="sd-mini-card" aria-hidden="true"><i>ع</i><b>Aa</b><small>────────</small></span><span><strong>Make it yours</strong><small>Colour, typography & layout</small></span><span aria-hidden="true">→</span>';
  brand.before(launcher);
  const sheet=document.createElement('dialog');sheet.id='studioDesignSheet';sheet.setAttribute('aria-labelledby','sdTitle');
  sheet.innerHTML='<header><div><small>Your design</small><h3 id="sdTitle">A little more you.</h3></div><button type="button" class="sd-close" aria-label="Close appearance editor">×</button></header><div class="sd-sheet-preview"><img id="sdSheetImage" alt="Preview of your design changes" hidden><p id="sdSheetEmpty">Choose a source and create a background to preview it here.</p></div><div class="sd-sheet-feedback"><p id="sdSheetStatus" role="status"></p><button type="button" id="sdSheetRetry" hidden>Retry preview</button></div><div class="sd-tabs" role="group" aria-label="Appearance controls"><button type="button" data-appearance="look" aria-pressed="true">Look</button><button type="button" data-appearance="layout" aria-pressed="false">Layout</button><button type="button" data-appearance="identity" aria-pressed="false">Identity</button></div><div class="sd-sheet-controls"></div><footer><button type="button" class="cw-primary" id="sdDone">Keep these choices</button><small>Finish the design in the editor before sharing.</small></footer>';
  modal.append(sheet);
  sheet.dataset.appearance='look';
  for(const button of sheet.querySelectorAll('[data-appearance]'))button.onclick=()=>{sheet.dataset.appearance=button.dataset.appearance;for(const other of sheet.querySelectorAll('[data-appearance]'))other.setAttribute('aria-pressed',String(other===button));};
  for(const [id,area] of [['brandPalette','look'],['brandTypography','look'],['brandComposition','layout'],['brandSignature','identity'],['brandSeries','identity'],['brandVisualIdentity','identity']])el(id).closest('label').dataset.appearanceArea=area;
  const preview=document.createElement('img');preview.id='studioEditPreview';preview.alt='Unsaved design preview';preview.hidden=true;
  el('cardPreviewContainer').append(preview);
  const notice=document.createElement('div');notice.className='sd-preview-status';notice.hidden=true;
  notice.innerHTML='<p id="sdPreviewStatus" role="status"></p><div><button type="button" id="sdPrevious" aria-label="Previous preview page">←</button><span id="sdPage"></span><button type="button" id="sdNext" aria-label="Next preview page">→</button><button type="button" id="sdRetry" hidden>Retry preview</button></div>';
  el('cardPreviewContainer').after(notice);
  const syncImage=()=>{
    const src=previewData?.image_data || el('quoteCardPreview').getAttribute('src');
    el('sdSheetImage').hidden=!src;el('sdSheetEmpty').hidden=!!src;
    if(src)el('sdSheetImage').src=src;
  };
  launcher.onclick=()=>{sheet.querySelector('.sd-sheet-controls').append(brand);brand.open=true;syncPickers();syncImage();sheet.showModal();queue();};
  sheet.querySelector('.sd-close').onclick=()=>sheet.close();el('sdDone').onclick=()=>sheet.close();
  sheet.addEventListener('keydown',event=>event.stopPropagation());
  sheet.addEventListener('close',()=>{home.after(brand);brand.open=false;launcher.focus();});
  function status(message) {el('sdPreviewStatus').textContent=message;el('sdSheetStatus').textContent=message;}
  window.clearStudioEditPreview=()=>{
    ++revision;clearTimeout(timer);controller?.abort();controller=null;previewData=null;lastKey='';renderedKey='';page=0;
    preview.hidden=true;preview.removeAttribute('src');notice.hidden=true;delete modal.dataset.editPreview;
    el('cardPreviewContainer').style.aspectRatio='';
    status('');el('sdRetry').hidden=true;el('sdSheetRetry').hidden=true;if(sheet.open)sheet.close();
  };
  function eligible(data) {return !!data.card_message && (!photoFamilies.includes(data.style) || !!data.background_token);}
  function currentKey() {return JSON.stringify(window.studioPreviewRequest());}
  async function render(rev,key,data) {
    if(rev!==revision)return;
    controller=new AbortController();const active=controller, timeout=setTimeout(()=>active.abort(),20000);
    status('Updating your preview…');el('sdRetry').hidden=true;el('sdSheetRetry').hidden=true;
    try {
      const response=await fetch('/api/studio/preview-visual',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...data,page_index:page}),signal:active.signal});
      const result=await response.json();
      if(rev!==revision || currentKey()!==key)return;
      if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'Preview could not update. Your choices are kept.');
      if(result.preview_only!==true || !/^data:image\/jpeg;base64,/.test(result.image_data))throw Error('Preview unavailable. Finish the design to check your choices.');
      previewData=result;renderedKey=key;preview.src=result.image_data;preview.hidden=false;
      modal.dataset.editPreview='true';notice.hidden=false;
      el('cardPreviewContainer').style.aspectRatio=data.post_format==='story_9_16'?'9/16':'4/5';
      el('sdPage').textContent=`${result.page_index+1} / ${result.page_count} · Preview`;
      el('sdPrevious').disabled=result.page_index===0;el('sdNext').disabled=result.page_index+1>=result.page_count;
      status('Preview updated · finish the design to save these changes.');syncImage();
    } catch(error) {
      if(rev===revision){status(error.name==='AbortError'?'Preview took too long. Your changes are kept.':['TypeError','SyntaxError'].includes(error.name)?'Preview could not connect. Your choices are kept. Try again.':error.message);el('sdRetry').hidden=false;el('sdSheetRetry').hidden=false;notice.hidden=false;}
    } finally {clearTimeout(timeout);if(controller===active)controller=null;}
  }
  function queue(resetPage=true) {
    clearTimeout(timer);controller?.abort();++revision;syncPickers();
    const data=window.studioPreviewRequest(), key=JSON.stringify(data);
    const state=window.studioShareSnapshot();
    if(modal.classList.contains('hidden') || modal.dataset.brandOnly || modal.dataset.step!=='2' || state.generating)return;
    if(state.payload?.media_url && !state.dirty) {
      preview.hidden=true;previewData=null;delete modal.dataset.editPreview;notice.hidden=true;
      el('cardPreviewContainer').style.aspectRatio='';
      status('Your current design. Choose a look to preview a change.');syncImage();return;
    }
    if(!eligible(data)) {
      preview.hidden=true;previewData=null;delete modal.dataset.editPreview;notice.hidden=true;
      status(data.card_message?'Create a background to see these choices on your image.':'Choose a source to preview your design.');syncImage();return;
    }
    if(resetPage && key!==lastKey)page=0;
    lastKey=key;
    if(key===renderedKey && resetPage)return;
    const rev=revision;
    status('Your choices are kept. Updating preview…');notice.hidden=false;
    timer=setTimeout(()=>render(rev,key,data),350);
  }
  window.queueStudioEditPreview=queue;
  el('sdPrevious').onclick=()=>{page=Math.max(0,page-1);queue(false);};
  el('sdNext').onclick=()=>{page++;queue(false);};el('sdRetry').onclick=()=>queue(false);el('sdSheetRetry').onclick=()=>queue(false);
  const oldSection=window.onCreatorSection;
  window.onCreatorSection=n=>{oldSection?.(n);if(n===2 && (window.studioShareSnapshot().dirty || !window.studioShareSnapshot().payload.media_url))queue();else if(n!==2){++revision;clearTimeout(timer);controller?.abort();}};
  modal.addEventListener('input',event=>{if(brand.contains(event.target) || ['editSupporting','studioCustomDirection'].includes(event.target.id))queue();});
  modal.addEventListener('change',event=>{if(brand.contains(event.target) || ['studioLayout','studioFormat','quranBrackets','quranVerseNumber'].includes(event.target.id))queue();});
  const picks=[];
  function choices(id,items,label) {
    const native=el(id), group=document.createElement('div');group.className='sd-choices sd-'+id;group.setAttribute('role','group');group.setAttribute('aria-label',label);
    for(const [value,title,art] of items) {
      const button=document.createElement('button');button.type='button';button.dataset.value=value;button.setAttribute('aria-label',title);button.innerHTML=art+'<span>'+title+'</span>';
      button.onclick=()=>{if(native.value===value)return;native.value=value;window.changeStudioBrand();syncPickers();queue();};group.append(button);
    }
    native.hidden=true;native.after(group);picks.push({native,group});
  }
  choices('brandPalette',[
    ['olive','Olive & chalk','<i style="--paper:#f5f7f1;--ink:#1d3027;--accent:#48633f">Aa</i>'],
    ['ink','Ink & mist','<i style="--paper:#f4f6f9;--ink:#1c2738;--accent:#445978">Aa</i>'],
    ['clay','Clay & cream','<i style="--paper:#fbf5ee;--ink:#432822;--accent:#854532">Aa</i>'],
    ['night','Night & linen','<i style="--paper:#172328;--ink:#f8f6ec;--accent:#a7bfac">Aa</i>']],'Colour palette');
  choices('brandTypography',[
    ['modern','Modern sans','<img class="sd-type-sample" src="/static/img/type-modern.png" alt="A quiet reminder." width="360" height="110">'],['classic','Classic serif','<img class="sd-type-sample" src="/static/img/type-classic.png" alt="A quiet reminder." width="360" height="110">']],'English typography');
  choices('brandComposition',[
    ['varied','Choose for me','<i class="sd-layout sd-varied"><b></b><b></b><b></b></i>'],
    ['airy','Open & spacious','<i class="sd-layout sd-airy"><b></b><b></b><b></b></i>'],
    ['anchored','Top aligned','<i class="sd-layout sd-anchored"><b></b><b></b><b></b></i>']],'Composition');
  function syncPickers(){for(const {native,group} of picks)for(const button of group.children)button.setAttribute('aria-pressed',String(button.dataset.value===native.value));}
  syncPickers();
})();
