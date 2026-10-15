/* Style selection and feedback only; the canonical renderer measures every fit. */
(() => {
  const el=id=>document.getElementById(id), modal=el('newPostModal');
  if(!modal) return;
  const native=el('studioFamilyPicker'), format=el('studioFormat');
  const descriptions={realistic_paper:'Fine paper textures & delicate edge details',luxury_editorial:'Plaster, linen & natural light',desert_glow:'Open dunes & quiet horizons',midnight_oasis:'Stone & deep evening tones',emerald_forest:'Water & open skies · shorter sources',editorial:'Confident type & open space',quiet_photography:'A photograph with a separate reading area',minimal_paper:'Warm paper & restrained type'};
  const families=[...native.options].filter(o=>descriptions[o.value]).map(o=>({id:o.value,label:o.textContent,description:descriptions[o.value]}));
  let fitKey='', fits=new Map(), fitPromise=null, fitController=null, fitEpoch=0, fitTimer=null, progressTimer=null;
  let state='idle';
  const paper=el('brandPaperFinish'), paperChoices=el('studioPaperChoices');
  if(paper && paperChoices) {
    for(const option of paper.options) {
      const button=document.createElement('button');button.type='button';button.dataset.finish=option.value;
      const img=document.createElement('img');img.src=`/static/img/paper/${option.value}.jpg`;img.alt='';img.width=120;img.height=150;img.loading='lazy';
      const label=document.createElement('span');label.textContent=option.textContent;
      button.append(img,label);button.onclick=()=>{if(paper.value===option.value)return;paper.value=option.value;window.changeStudioBrand(true);sync();};paperChoices.append(button);
    }
    paper.hidden=true;
  }
  const selector=document.createElement('section');selector.className='cw-family-choice';
  selector.innerHTML='<span class="cw-field-label">Visual style</span><button type="button" id="studioChooseFamily" class="cw-selected-family" aria-haspopup="dialog"><img alt="" width="88" height="88"><span><strong></strong><small></small><b>Change style →</b></span></button><p id="studioFitNote" class="cw-fit-note" aria-live="polite"></p>';
  el('studioFamilyFallback').hidden=true;el('studioFamilyFallback').after(selector);
  const dialog=document.createElement('dialog');dialog.id='studioFamilyDialog';dialog.setAttribute('aria-labelledby','studioFamilyTitle');
  dialog.innerHTML='<header><div><p class="cw-eyebrow">Make it yours</p><h4 id="studioFamilyTitle">Choose your visual style</h4></div><button type="button" id="studioFamilyClose" aria-label="Close style choices">×</button></header><p class="cw-family-intro">Examples show the mood. Your source, brand and background direction shape the final design.</p><div id="studioFamilyGrid" role="radiogroup" aria-label="Visual style"></div><p class="cw-family-footnote">Choosing a style is free. A background is generated only when you create your design.</p>';
  modal.append(dialog);
  const cards=new Map();
  for(const family of families) {
    const button=document.createElement('button');button.type='button';button.className='cw-family-tile';button.setAttribute('role','radio');button.dataset.family=family.id;
    const img=document.createElement('img');img.src=`/static/img/styles/${family.id}.jpg`;img.alt='';img.width=240;img.height=150;img.loading='lazy';
    const title=document.createElement('strong');title.textContent=family.label;
    const description=document.createElement('span');description.textContent=family.description;
    const fit=document.createElement('small');fit.className='cw-family-fit';
    const check=document.createElement('b');check.className='cw-family-check';check.textContent='✓';check.setAttribute('aria-hidden','true');
    button.append(img,title,description,fit,check);el('studioFamilyGrid').append(button);cards.set(family.id,button);
    button.onclick=()=>{
      if(button.getAttribute('aria-disabled')==='true') return;
      if(native.value!==family.id) window.setStudioScene(family.id,null);
      sync();dialog.close();
    };
    button.onkeydown=event=>{
      if(!['ArrowRight','ArrowLeft','ArrowDown','ArrowUp','Home','End'].includes(event.key)) return;
      event.preventDefault();const list=[...cards.values()].filter(b=>b.getAttribute('aria-disabled')!=='true');
      const delta=['ArrowRight','ArrowDown'].includes(event.key)?1:-1;
      const i=event.key==='Home'?0:event.key==='End'?list.length-1:(list.indexOf(button)+delta+list.length)%list.length;
      list[i]?.focus();
    };
  }
  el('studioChooseFamily').onclick=()=>{sync();dialog.showModal();(cards.get(native.value)||cards.values().next().value)?.focus();};
  el('studioFamilyClose').onclick=()=>dialog.close();
  // Let the native dialog contain focus/Escape without closing the parent editor.
  dialog.addEventListener('keydown',event=>event.stopPropagation());
  dialog.addEventListener('close',()=>el('studioChooseFamily').focus());
  dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
  // Keep native format values as the canonical source of truth.
  const formats=document.createElement('div');formats.className='cw-format-options';formats.setAttribute('role','group');formats.setAttribute('aria-label','Post format');
  for(const [value,label,shape] of [['feed_4_5','Feed','▯'],['story_9_16','Story','▯']]) {
    const button=document.createElement('button');button.type='button';button.dataset.format=value;button.innerHTML=`<span aria-hidden="true" class="cw-format-${value}">${shape}</span>${label}<small>${value==='feed_4_5'?'4:5':'9:16'}</small>`;
    button.onclick=()=>{if(format.value===value)return;format.value=value;window.changeStudioFormat();sync();window.rememberStudio();};formats.append(button);
  }
  format.hidden=true;format.after(formats);
  function requestData() {
    const data=window.studioShareSnapshot().payload;
    if(!data.card_message)return null;
    return {card_message:data.card_message,brand_kit:data.brand_kit,layout:el('studioLayout').value,post_format:format.value};
  }
  function currentFit() { return fits.get(native.value); }
  window.studioSelectedFit=currentFit;
  function sync() {
    if(paperChoices) {
      el('studioPaperOptions').hidden=native.value!=='realistic_paper';
      for(const button of paperChoices.children)button.setAttribute('aria-pressed',String(button.dataset.finish===paper.value));
    }
    const selected=families.find(f=>f.id===native.value), button=el('studioChooseFamily');
    button.querySelector('strong').textContent=selected?.label || 'Saved design';
    button.querySelector('small').textContent=selected?.description || 'Your existing style is preserved';
    const image=button.querySelector('img');image.hidden=!selected;if(selected)image.src=`/static/img/styles/${selected.id}.jpg`;
    for(const [id,card] of cards) {
      const checked=id===native.value, fit=fits.get(id), unavailable=fit?.available===false;
      card.setAttribute('aria-checked',String(checked));card.setAttribute('aria-disabled',String(unavailable));card.tabIndex=checked?0:-1;
      card.querySelector('.cw-family-fit').textContent=unavailable?'Needs more room':fit?.available?`${fit.pages} ${fit.pages===1?'page':'pages'}`:'';
      card.title=unavailable?fit.reason:'';
    }
    for(const button of formats.children)button.setAttribute('aria-pressed',String(button.dataset.format===format.value));
    const fit=currentFit();el('studioFitNote').textContent=fit?.available===false ? fit.reason : fit?.available ? `${fit.pages===1?'One complete card':`${fit.pages} readable pages`}. Your full source stays intact.` : '';
    window.refreshStudioFlow?.();
  }
  async function checkFits() {
    const data=requestData();if(!data)return null;
    const key=JSON.stringify(data);
    if(key===fitKey && fitPromise)return fitPromise;
    if(key===fitKey && fits.size)return fits;
    fitController?.abort();fitController=new AbortController();const controller=fitController, epoch=++fitEpoch;
    fitKey=key;fits.clear();sync();
    const timer=setTimeout(()=>controller.abort(),15000);
    fitPromise=(async()=>{
      try {
        const response=await fetch('/api/studio/visual-fit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data),signal:controller.signal});
        const result=await response.json();if(epoch!==fitEpoch)return null;
        if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'Style check unavailable');
        fits=new Map(result.families.map(f=>[f.family,f]));sync();return fits;
      } catch(error) {
        if(epoch===fitEpoch){fitKey='';el('studioFitNote').textContent='Style preview check unavailable. Create design will still check readability before generating.';}
        return null;
      } finally {clearTimeout(timer);if(epoch===fitEpoch){fitPromise=null;fitController=null;}}
    })();return fitPromise;
  }
  window.checkStudioVisualFit=async()=>{
    await checkFits();const fit=currentFit();
    if(fit?.available===false){window.setStudioVisualState('error',fit.reason);return false;}
    return true;
  };
  function queueFits() {
    clearTimeout(fitTimer);const data=requestData();
    if(!data || JSON.stringify(data)!==fitKey){
      ++fitEpoch;fitController?.abort();fitController=null;fitPromise=null;fitKey='';fits.clear();sync();
    }
    if(!data)return;
    fitTimer=setTimeout(checkFits,180);
  }
  const oldDesign=window.onCreatorDesignChanged;
  window.onCreatorDesignChanged=()=>{oldDesign?.();sync();if(modal.dataset.step==='2')queueFits();};
  const oldSection=window.onCreatorSection;
  window.onCreatorSection=n=>{oldSection?.(n);if(n===2){sync();queueFits();}};
  window.setStudioVisualState=(next,message='')=>{
    state=next;clearTimeout(progressTimer);
    const panel=el('studioVisualStatus');panel.dataset.state=next;panel.hidden=['idle','ready'].includes(next);
    modal.dataset.visualState=next;
    el('studioVisualStatusTitle').textContent={generating:'Creating your design',loading:'Your design is ready',error:'Let’s adjust this', 'image-error':'Reload your preview'}[next]||'';
    el('studioVisualStatusText').textContent=message;
    el('studioStatusReload').hidden=next!=='image-error';
    if(next==='generating') {
      panel.scrollIntoView({block:'nearest',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
      progressTimer=setTimeout(()=>{if(state==='generating')el('studioVisualStatusText').textContent='Still working. A fresh background can take a little longer. Your source is safe; no need to tap again.';},18000);
    }
    if(next==='error'||next==='image-error')panel.focus({preventScroll:false});
    window.refreshStudioFlow?.();
  };
  sync();
})();
