const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../app/routes/ui_assets.py'),'utf8');
const code=source.slice(source.indexOf('    // Creator identity and editorial controls.'),source.indexOf('    // End creator controls.'));
function setup(fetch) {
 const nodes={},alerts=[];let invalidated=0,remembered=0;
 const el=id=>nodes[id] ||= {value:'',checked:false,disabled:false,textContent:'',classList:{add(){},toggle(){}},dataset:{}};
 const c={window:{invalidateQuoteCard:()=>invalidated++,rememberStudio:()=>remembered++,updateStudioCardFromUI:()=>{}},document:{getElementById:el,querySelectorAll:()=>[]},
  studioSessionEpoch:1,studioSourceEpoch:1,studioPostId:null,currentQuoteCardUrl:null,studioCardMessage:null,fetch,AbortSignal,alert:m=>alerts.push(m)};
 vm.runInNewContext(code,c);c.window.resetCreatorControls();
 return {c,el,alerts,invalidated:()=>invalidated,run:s=>vm.runInNewContext(s,c)};
}
const kit={version:1,palette:'night',typography:'classic',signature:'@fixture',series_name:'A series',family:'minimal_paper',composition:'airy'};
test('late workspace loading never overwrites the saved draft brand or editor controls',async()=>{
 let finish;const f=setup(()=>new Promise(r=>finish=r));
 const pending=f.c.window.loadStudioBrand();
 f.c.window.restoreCreatorControls({brand_kit:{...kit,palette:'clay'},audience:'new_muslims',purpose:'learn'});
 finish({ok:true,json:async()=>({brand_kit:kit,revision:'r1'})});await pending;
 assert.equal(f.c.window.studioBrandSnapshot().palette,'clay');assert.equal(f.el('studioAudience').value,'new_muslims');
 assert.equal(f.run('studioBrandRevision'),'r1');
});
test('brand save is duplicate-protected, preserves newer edits and remains retryable after conflict',async()=>{
 let finish,calls=0;const f=setup(()=>{calls++;return new Promise(r=>finish=r);});f.run("studioBrandRevision='r1'");
 f.el('brandSignature').value='Original';const pending=f.c.window.saveWorkspaceBrand();await f.c.window.saveWorkspaceBrand();
 f.el('brandSignature').value='Newer edit';finish({ok:false,json:async()=>({detail:'Changed in another session'})});await pending;
 assert.equal(calls,1);assert.equal(f.el('brandSignature').value,'Newer edit');assert.equal(f.el('saveBrandButton').disabled,false);
 assert.match(f.el('brandStatus').textContent,/another session/);
});
test('a late save cannot change a newly opened workspace session',async()=>{
 let finish;const f=setup(()=>new Promise(r=>finish=r));f.run("studioBrandRevision='r1'");const pending=f.c.window.saveWorkspaceBrand();
 f.c.studioSessionEpoch++;f.c.window.resetCreatorControls();finish({ok:true,json:async()=>({revision:'old-result'})});await pending;
 assert.equal(f.run('studioBrandRevision'),null);assert.equal(f.el('brandStatus').textContent,'');
});
test('Arabic excerpt controls keep the complete canonical text and invalidate prior approval',()=>{
 const f=setup();const full='Earlier chain. Full exact narration.';
 f.c.studioCardMessage={arabic_text:full,arabic_display_options:[{start:15,end:full.length,label:'Arabic excerpt'}]};
 f.el('arabicDisplayMode').value='short_chain';f.c.window.changeArabicDisplay();
 assert.equal(f.c.studioCardMessage.arabic_text,full);assert.equal(f.el('arabicExcerptPreview').textContent,full.slice(15));assert.equal(f.invalidated(),1);
 f.el('arabicDisplayMode').value='full';f.c.window.changeArabicDisplay();assert.equal(f.c.studioCardMessage.arabic_display,undefined);
});
test('failed brand loading blocks generation until a usable kit is restored or explicitly edited',async()=>{
 const f=setup(async()=>{throw Error('Offline')});await f.c.window.loadStudioBrand();
 assert.throws(()=>f.c.window.requireStudioBrand(),/Load/);
 f.c.window.changeStudioBrand();assert.doesNotThrow(()=>f.c.window.requireStudioBrand());
});
test('late AI reflection cannot overwrite the creator edit or the chosen Arabic display',async()=>{
 let finish;const f=setup(()=>new Promise(r=>finish=r));
 f.c.studioCardMessage={headline:'Exact',arabic_text:'نص',arabic_display:{start:2,end:3}};
 f.c.window.selectedHadithMetadata={reference:'Fixture'};f.el('editSupporting').value='Before';
 const pending=f.c.window.draftStudioReflection();f.el('editSupporting').value='My own words';
 finish({ok:true,json:async()=>({card_message:{headline:'Exact',arabic_text:'نص',supporting_text:'AI text'}})});await pending;
 assert.equal(f.el('editSupporting').value,'My own words');assert.equal(f.c.studioCardMessage.arabic_display.start,2);
 assert.match(f.alerts[0],/Your edit was kept/);assert.equal(f.el('draftReflectionButton').disabled,false);
});
