const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../../app/static/studio-flow.js'),'utf8');
function setup({pages=1,format='feed_4_5',reviewed=true}={}) {
  const nodes={},events={},calls=[],classes=new Map();let saved=0,remembered=0,pinState=null,pinBusy=false,pinOptions,observer;
  const el=id=>nodes[id] ||= {id,hidden:false,disabled:false,value:'',checked:false,textContent:'',dataset:{},classList:{contains:c=>(classes.get(id)||new Set()).has(c),toggle(c,on){const s=classes.get(id)||new Set();if(on)s.add(c);else s.delete(c);classes.set(id,s);}},addEventListener(n,f){events[id+':'+n]=f},querySelector:()=>null,querySelectorAll:()=>[],replaceChildren(){},appendChild(){},setAttribute(){},click(){calls.push(id);this.onclick?.()}};
  el('newPostModal').dataset.step='4';el('studioAccount').value='7';el('studioCaption').value='Separate caption';el('studioShareNowBtn').hidden=false;
  el('creatorPinApproval').hidden=el('creatorPinCheckStatus').hidden=el('creatorPinPublishedLink').hidden=true;
  el('cardActions').querySelector=()=>el('visualContinue');el('creatorGuided').hidden=true;
  const state={postId:null,payload:{media_url:'https://cdn.test/a.jpg',post_format:format},pages:Array.from({length:pages},()=>({url:'https://cdn.test/a.jpg'})),dirty:false,reviewed};
  const api={busy:()=>pinBusy,snapshot:()=>pinState,reset(){pinState=null;return true},invalidate(){calls.push('invalidate')},save:async()=>{calls.push('savePin');return true},open:async(id,recovery)=>{calls.push({open:id,recovery});pinState=recovery||{post_id:id,revision:0,dirty:false,copy:{}};return true}};
  const c={window:{createPinterestEditor:o=>{pinOptions=o;return api},studioShareSnapshot:()=>state,studioNotice:m=>calls.push({notice:m}),rememberStudio:()=>remembered++,setStudioShareTiming:t=>calls.push({timing:t}),persistStudioDraft:async()=>{saved++;return {id:51}},saveStudioDraft:async()=>calls.push('saveStudio'),switchStudioSection:n=>calls.push({step:n})},document:{getElementById:el,createElement:()=>el('dynamicDownload'),querySelector:()=>({value:'later'}),querySelectorAll:()=>[]},location:{search:''},URLSearchParams,MutationObserver:class{constructor(cb){observer=cb}observe(){}}};
  vm.runInNewContext(code,c);
  return {el,c,calls,state,api,events,refresh:()=>observer(),pinOptions:()=>pinOptions,saved:()=>saved,setBusy:v=>pinBusy=v,setPin:v=>pinState=v,remembered:()=>remembered};
}
test('Pinterest saves the same reviewed card then opens inside Studio without navigating or publishing',async()=>{
 const f=setup();await f.c.window.chooseStudioDestination('pinterest');assert.equal(f.saved(),1);assert.equal(f.el('studioInstagramPanel').hidden,true);assert.equal(f.el('studioPinterestEditor').hidden,false);assert.ok(f.calls.some(c=>c.open===51));assert.equal(f.el('studioStepNext').textContent,'Review Pin');
});
test('Stories, carousels and unreviewed designs never save or discard pages for a Pin',async()=>{
 for(const opts of [{pages:3,format:'carousel_4_5'},{format:'story_9_16'},{reviewed:false}]) {
 const f=setup(opts);await f.c.window.chooseStudioDestination('pinterest');assert.equal(f.saved(),0);assert.equal(f.el('studioPinterestEditor').hidden,true);assert.match(f.el('studioPinterestStatus').textContent,/complete|Review/); }
});
test('duplicate destination taps cannot create overlapping saves and failures can retry',async()=>{
 const f=setup();let finish;f.c.window.persistStudioDraft=()=>new Promise(r=>finish=r);
 const pending=f.c.window.chooseStudioDestination('pinterest');await f.c.window.chooseStudioDestination('pinterest');assert.equal(f.c.window.beforeStudioClose(),false);finish({id:51});await pending;
 assert.equal(f.calls.filter(c=>c.open===51).length,1);assert.equal(f.c.window.beforeStudioClose(),true);
 const g=setup();g.c.window.persistStudioDraft=async()=>{throw Error('Offline')};await g.c.window.chooseStudioDestination('pinterest');assert.equal(g.el('studioPinterestRetry').hidden,false);assert.equal(g.c.window.beforeStudioClose(),true);
});
test('switching destination retains separate unsaved Pin copy and never changes the Instagram caption',async()=>{
 const f=setup();await f.c.window.chooseStudioDestination('pinterest');const copy={post_id:51,dirty:true,copy:{description:'My Pin only'}};f.setPin(copy);
 await f.c.window.chooseStudioDestination('instagram');await f.c.window.chooseStudioDestination('pinterest');
 assert.equal(f.calls.filter(c=>c.open).at(-1).recovery.copy.description,'My Pin only');assert.equal(f.el('studioCaption').value,'Separate caption');assert.equal(f.c.window.readStudioSharing().pin.copy.description,'My Pin only');
});
test('recovery keeps destination and timing but does not restore publishing approval',()=>{
 const f=setup();f.c.window.restoreStudioSharing({destination:'pinterest',timing:'later',pin:{post_id:51,dirty:true,copy:{}}});
 assert.equal(f.el('studioInstagramPanel').hidden,true);assert.ok(f.calls.some(c=>c.timing==='later'));f.c.window.invalidateStudioShareReview();assert.equal(f.el('studioInstagramReviewed').checked,false);
 f.c.window.resetStudioSharing();assert.equal(f.el('studioPinterestPanel').hidden,true);assert.equal(f.c.window.readStudioSharing().pin,null);
});
test('final Instagram review is distinct from visual review and is cleared by caption/account edits',()=>{
 const f=setup();assert.equal(f.c.window.validateStudioInstagramReview(),false);f.el('studioInstagramReviewed').checked=true;assert.equal(f.c.window.validateStudioInstagramReview(),true);
 f.events['studioAccount:change']();assert.equal(f.c.window.validateStudioInstagramReview(),false);assert.equal(f.state.reviewed,true);
 f.el('studioInstagramReviewed').checked=true;f.el('studioCaption').value='';assert.equal(f.c.window.validateStudioInstagramReview(),false);
});
test('new-post footer progresses from design creation to review, then caption and sharing',()=>{
 const f=setup();f.el('newPostModal').dataset.step='2';f.state.payload.media_url=null;f.refresh();assert.equal(f.el('studioStepNext').textContent,'Create my design');f.el('studioStepNext').onclick();assert.ok(f.calls.includes('btnGenerateCard'));
 f.state.payload.media_url='https://cdn.test/a.jpg';f.refresh();assert.equal(f.el('studioStepNext').disabled,true);
 f.el('sequenceReviewCheck').checked=true;f.refresh();assert.equal(f.el('studioStepNext').disabled,false);f.el('studioStepNext').onclick();assert.ok(f.calls.includes('visualContinue'));
 f.el('newPostModal').dataset.step='3';f.refresh();f.el('studioStepNext').onclick();assert.ok(f.calls.some(c=>c.step===4));
});
test('submitted or uncertain Pins cannot switch destination or resume editing',()=>{
 const f=setup();f.pinOptions().onPublication({status:'unknown'});assert.equal(f.c.window.beforeStudioStep(2),false);assert.equal(f.c.window.beforeStudioStep(4),true);assert.equal(f.c.window.beforeStudioClose(),true);
});

test('returning to a submitted Pinterest result never resaves or clears the result',async()=>{
 const f=setup();await f.c.window.chooseStudioDestination('pinterest');f.pinOptions().onPublication({status:'published'});
 const count=f.saved();await f.c.window.chooseStudioDestination('pinterest');await f.c.window.chooseStudioDestination('instagram');
 assert.equal(f.saved(),count);assert.equal(f.el('studioInstagramPanel').hidden,true);assert.equal(f.c.window.readStudioSharing().destination,'pinterest');
});

test('footer refresh is idempotent for attributes observed by MutationObserver',()=>{
 const f=setup();f.refresh();let mutations=0;
 for(const id of ['studioSaveDraftButton','btnGenerateCard','studioStepBar','studioStepNext','studioStepBack']) {
   for(const key of ['hidden','disabled']) {let value=f.el(id)[key];Object.defineProperty(f.el(id),key,{get:()=>value,set:v=>{mutations++;value=v}});}
 }
 f.refresh();f.refresh();assert.equal(mutations,0);
});

test('saving after a Story format change saves Studio, not stale Pinterest copy',async()=>{
 const f=setup();await f.c.window.chooseStudioDestination('pinterest');f.state.payload.post_format='story_9_16';
 await f.c.window.chooseStudioDestination('pinterest');await f.c.window.saveStudioDraft();
 assert.ok(f.calls.includes('saveStudio'));assert.ok(!f.calls.includes('savePin'));
 f.el('studioPinterestEditor').hidden=false;f.el('newPostModal').dataset.step='3';await f.c.window.saveStudioDraft();
 assert.equal(f.calls.filter(c=>c==='saveStudio').length,2);
});


test('visual generation locks navigation and the footer until the operation settles',()=>{
 const f=setup();f.el('newPostModal').dataset.step='2';f.state.busy=true;f.state.generating=true;f.refresh();
 assert.equal(f.el('studioStepNext').textContent,'Creating your design…');assert.equal(f.el('studioStepNext').disabled,true);
 assert.equal(f.c.window.beforeStudioStep(3),false);assert.equal(f.c.window.beforeStudioClose(),false);
 f.state.busy=false;f.state.generating=false;f.refresh();assert.equal(f.c.window.beforeStudioStep(3),true);
});
test('an ineligible style leads directly to suitable choices instead of a rejected generation',()=>{
 const f=setup();f.el('newPostModal').dataset.step='2';f.state.payload.media_url=null;
 f.c.window.studioSelectedFit=()=>({available:false});f.refresh();
 assert.equal(f.el('studioStepNext').textContent,'Choose a fitting style');f.el('studioStepNext').onclick();assert.ok(f.calls.includes('studioChooseFamily'));
});

test('an existing unchanged reviewed image remains usable even if a new fit estimate differs',()=>{
 const f=setup();f.el('newPostModal').dataset.step='2';f.el('sequenceReviewCheck').checked=true;
 f.c.window.studioSelectedFit=()=>({available:false});f.refresh();
 assert.equal(f.el('studioStepNext').textContent,'Continue to caption');assert.equal(f.el('studioStepNext').disabled,false);
});

test('changed paper finish clearly requests a new background while typography edits keep the finish action',()=>{
 const f=setup();f.el('newPostModal').dataset.step='2';f.state.dirty=true;
 f.c.window.studioPreviewRequest=()=>({style:'realistic_paper',background_token:null});f.refresh();
 assert.equal(f.el('studioStepNext').textContent,'Create new paper background');
 f.c.window.studioPreviewRequest=()=>({style:'realistic_paper',background_token:'retained'});f.el('newPostModal').dataset.editPreview='true';f.refresh();
 assert.equal(f.el('studioStepNext').textContent,'Finish design');
});
