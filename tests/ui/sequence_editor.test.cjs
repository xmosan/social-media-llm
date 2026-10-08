const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../app/routes/ui_assets.py'),'utf8');
const code=source.slice(source.indexOf('    // Sequence editor:'),source.indexOf('    // End sequence editor.'));
function setup(fetch=async()=>({ok:true,json:async()=>({id:51})})) {
  const nodes={}, storage=new Map(),alerts=[];let phase=0;
  const el=id=>nodes[id] ||= {value:'',checked:false,disabled:false,style:{},dataset:{workspace:'1:2'},classList:{add(){},remove(){},toggle(){}}};
  el('studioAccount').value='7';el('studioStyle').value='editorial';el('studioFormat').value='feed_4_5';el('studioCaption').value='Social copy';
  const card={headline:'Exact source',arabic_text:'نص تجريبي',eyebrow:'Fixture reference'};
  const pages=[0,1,2].map(i=>({url:`https://cdn.test/${i}.jpg`,label:`Source part ${i+1}`}));
  const c={window:{selectedAyahMetadata:{id:1,reference:'Fixture reference'},switchStudioSection:p=>phase=p},document:{getElementById:el,querySelectorAll:()=>[]},
    studioCardMessage:card,studioVisualDesign:{family:'editorial',media_manifest:{format:'carousel_4_5',pages}},studioVisualController:null,
    studioBackgroundToken:null,studioCaptionMessage:null,selectedAyahId:1,selectedHadithId:null,currentQuoteCardUrl:pages[0].url,isQuoteCardOutOfDate:false,
    crypto:require('node:crypto').webcrypto,AbortSignal,fetch,alert:m=>alerts.push(m),
    localStorage:{setItem:(k,v)=>storage.set(k,v),getItem:k=>storage.get(k),removeItem:k=>storage.delete(k)}};
  vm.runInNewContext(code,c);vm.runInNewContext('studioDraftKey=crypto.randomUUID()',c);
  return {c,el,alerts,storage,phase:()=>phase,run:s=>vm.runInNewContext(s,c)};
}
test('every page must be visited and explicitly reviewed; preview keeps the correct aspect ratio',()=>{
  const f=setup();f.c.window.showStudioPage(0);f.c.window.confirmStudioSequence();assert.equal(f.phase(),0);
  assert.equal(f.el('sequenceReviewCheck').disabled,true);
  f.c.window.moveStudioPage(1);assert.equal(f.el('quoteCardPreview').src,'https://cdn.test/1.jpg');
  f.c.window.moveStudioPage(1);assert.equal(f.el('sequenceReviewCheck').disabled,false);
  f.el('sequenceReviewCheck').checked=true;f.c.window.confirmStudioSequence();assert.equal(f.phase(),3);
  assert.equal(f.el('cardPreviewContainer').style.aspectRatio,'4 / 5');
  f.c.studioVisualDesign.media_manifest.format='story_9_16';f.c.window.updateStudioFormatPreview();
  assert.equal(f.el('cardPreviewContainer').style.aspectRatio,'9 / 16');
});
test('saving is idempotent across recovery and retains every page with separate source and caption',async()=>{
  const payloads=[];const f=setup(async(url,opts)=>{payloads.push(JSON.parse(opts.body));return {ok:true,json:async()=>({id:51})};});
  await f.c.window.saveStudioDraft();await f.c.window.saveStudioDraft();
  assert.equal(payloads[1].post_id,51);assert.equal(payloads[0].draft_key,payloads[1].draft_key);
  assert.equal(payloads[1].visual_design.media_manifest.pages.length,3);
  assert.equal(payloads[1].card_message.headline,'Exact source');assert.equal(payloads[1].caption_message.caption,'Social copy');
  assert.equal(payloads[1].reviewed,false);
  assert.equal(JSON.parse([...f.storage.values()][0]).payload.post_id,51);
});
test('duplicate saves cannot create two requests; failure preserves draft key and permits retry',async()=>{
  let finish,calls=0;const f=setup(()=>{calls++;return new Promise(r=>finish=r);});
  const pending=f.c.window.saveStudioDraft();await f.c.window.saveStudioDraft();assert.equal(calls,1);
  const key=f.run('studioDraftKey');finish({ok:false,json:async()=>({detail:'Try again'})});await pending;
  assert.equal(f.el('studioSaveStatus').textContent,'Try again');assert.equal(f.run('studioDraftKey'),key);
  assert.equal(f.run('studioSaveBusy'),false);
});
test('restoring unsaved work does not regenerate a background or restore an approval',()=>{
  const f=setup(()=>{throw Error('No provider or save call expected')});f.c.window.rememberStudio();
  f.c.studioCardMessage=null;f.c.studioVisualDesign=null;
  f.c.window.restoreStudioRecovery();
  assert.equal(f.c.studioCardMessage.headline,'Exact source');assert.equal(f.run('sequencePages().length'),3);
  assert.equal(f.run('studioSequenceReviewed'),false);assert.equal(f.phase(),2);
});
test('dirty source or layout cannot save an old visual',async()=>{
  let calls=0;const f=setup(()=>{calls++;});f.c.isQuoteCardOutOfDate=true;
  await f.c.window.saveStudioDraft();assert.equal(calls,0);assert.match(f.el('studioSaveStatus').textContent,/Apply/);
});
test('local recovery preserves edits made after saving while checking the saved publication state',async()=>{
  const f=setup(async()=>({ok:true,json:async()=>({id:51,status:'drafted'})}));
  f.run('studioPostId=51');f.el('studioCaption').value='Unsaved local caption';f.c.window.rememberStudio();
  f.el('studioCaption').value='Server caption';await f.c.window.restoreStudioRecovery();
  assert.equal(f.el('studioCaption').value,'Unsaved local caption');assert.equal(f.run('studioPostId'),51);
});
test('a late save from an older Studio session cannot replace the new draft or clear its busy state',async()=>{
  let finish;const f=setup(()=>new Promise(r=>finish=r));
  const pending=f.c.window.saveStudioDraft();
  f.run('studioSessionEpoch++; studioPostId=99; studioSaveBusy=true');
  finish({ok:true,json:async()=>({id:51})});await pending;
  assert.equal(f.run('studioPostId'),99);assert.equal(f.run('studioSaveBusy'),true);
});

test('an idea is recoverable before a source, card, image, or Instagram account exists',async()=>{
 const f=setup(()=>{throw Error('Early recovery must not call a production route')});
 f.c.studioCardMessage=null;f.c.studioVisualDesign=null;f.c.currentQuoteCardUrl=null;f.el('studioAccount').value='';f.el('studioTopic').value='';
 f.c.window.readCreatorBrief=()=>({idea:'A reminder for difficult days',mode:'guided',sourceType:'quran'});
 let restored;f.c.window.restoreCreatorBrief=e=>restored=e;
 await f.c.window.saveStudioDraft();const saved=JSON.parse([...f.storage.values()][0]);assert.equal(saved.entry.idea,'A reminder for difficult days');assert.equal(saved.payload.card_message,null);
 await f.c.window.restoreStudioRecovery();assert.equal(restored.idea,saved.entry.idea);assert.equal(f.phase(),1);
});
test('storage failure is reported instead of claiming that early work is safe',()=>{
 const f=setup();let success;f.c.window.creatorRecoveryStatus=ok=>success=ok;
 f.c.localStorage.setItem=()=>{throw Error('Quota');};assert.equal(f.c.window.rememberStudio(),false);assert.equal(success,false);
});
test('editing a caption clears prior publishing approval without invalidating the background',()=>{
 const f=setup();f.run('studioSequenceReviewed=true');f.el('sequenceReviewCheck').checked=true;
 f.el('studioCaption').value='My edited caption';f.c.window.captionChanged();
 assert.equal(f.run('studioSequenceReviewed'),false);assert.equal(f.el('sequenceReviewCheck').checked,false);assert.equal(f.c.isQuoteCardOutOfDate,false);
 assert.equal(JSON.parse([...f.storage.values()][0]).payload.caption_message.caption,'My edited caption');
});
test('starting another idea preserves the previous local draft and can recover it',async()=>{
 const f=setup();f.run("studioDraftKey='first'");f.el('studioCaption').value='First draft';f.c.window.rememberStudio();
 f.run("studioDraftKey='second'");f.el('studioCaption').value='Second draft';f.c.window.rememberStudio();
 const archive=JSON.parse(f.storage.get('sabeel-studio-v2:1:2:drafts'));
 assert.equal(archive.length,1);assert.equal(archive[0].payload.caption_message.caption,'First draft');
 await f.c.window.restoreStudioRecovery('first');assert.equal(f.el('studioCaption').value,'First draft');
 f.c.window.rememberStudio();assert.equal(JSON.parse(f.storage.get('sabeel-studio-v2:1:2:drafts'))[0].payload.caption_message.caption,'Second draft');
});
test('recovery keeps planned date and time as editor preferences, never as a scheduling command',async()=>{
 const f=setup();f.el('scheduleDate').value='2026-12-20';f.el('scheduleTime').value='09:15';f.c.window.rememberStudio();
 const saved=JSON.parse(f.storage.get('sabeel-studio-v2:1:2'));assert.equal(saved.schedule.date,'2026-12-20');assert.equal(saved.payload.scheduled_at,undefined);
 f.el('scheduleDate').value='';await f.c.window.restoreStudioRecovery();assert.equal(f.el('scheduleDate').value,'2026-12-20');assert.equal(f.el('scheduleTime').value,'09:15');
});
