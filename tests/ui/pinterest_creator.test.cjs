const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const code=fs.readFileSync(require('node:path').join(__dirname,'../../app/static/pinterest-creator.js'),'utf8');
const saved={post_id:1,revision:0,source_version:'a'.repeat(64),source_reference:'Fixture 1',image_url:'https://cdn.test/card.jpg',arabic:'نص تجريبي',translation:'Exact source',reflection:'',source_details:'Fixture provider',issues:[],copy:{title:'Fixture 1',description:'Separate social copy',alt_text:'Image description',ai_modified:false,link:null},locked:false,publishing_enabled:false};
async function setup(handler){
  const nodes={},calls=[],listeners={},events={preventDefault(){}};
  const el=id=>nodes[id] ||= {value:'',textContent:'',hidden:false,disabled:false,options:[],events:{},addEventListener(n,f){this.events[n]=f},setAttribute(n,v){this[n]=v},add(o){this.options.push(o)},replaceChildren(...o){this.options=o},focus(){},scrollIntoView(){}};
  const c={document:{body:{dataset:{post:'1'}},getElementById:id=>el(id.replace('creatorPin',''))},window:{confirm:()=>true,addEventListener:(n,f)=>listeners[n]=f},history:{replaceState(){}},Option:function(text,value){this.text=text;this.value=value},AbortSignal,encodeURIComponent,
    fetch:async(path,options)=>{calls.push({path,options});if(handler){const result=await handler(path,options);if(result)return result}return {ok:true,json:async()=>path.endsWith('/posts')?{items:[{id:1,reference:'Fixture 1'}],next_before:null}:structuredClone(saved)}}};
  vm.runInNewContext(code,c);await new Promise(setImmediate);
  return {el,calls,listeners,submit:()=>el('Form').events.submit(events),c};
}
test('creator writes separate copy, can save incomplete fields, and never calls publishing or OAuth',async()=>{
  const f=await setup((path,opts)=>opts.method==='PUT'?{ok:true,json:async()=>({...saved,revision:1,saved_at:'2026-10-13',copy:JSON.parse(opts.body)})}:null);
  f.el('Description').value='Edited description';f.el('Description').events.input();await f.submit();
  const sent=JSON.parse(f.calls.find(c=>c.options.method==='PUT').options.body);assert.equal(sent.description,'Edited description');assert.equal(sent.source_version,saved.source_version);assert.equal(sent.revision,0);assert.equal(sent.caption,undefined);assert.equal(sent.source_text,undefined);
  assert.match(f.el('SaveStatus').textContent,/Saved draft/);assert.ok(f.calls.every(c=>!c.options.method || !/(publish|connect|schedule)/.test(c.path)));
});
test('a lost save response preserves edits and lets the creator retry',async()=>{
  const f=await setup((path,opts)=>{if(opts.method==='PUT')throw Error('Connection interrupted');});
  f.el('Description').value='Keep my edit';f.el('Description').events.input();await f.submit();
  assert.equal(f.el('Description').value,'Keep my edit');assert.match(f.el('Notice').textContent,/still on this page/);assert.equal(f.el('Reload').hidden,false);assert.equal(f.el('Fields').disabled,false);
  let warned=false;f.listeners.beforeunload({preventDefault(){warned=true}});assert.equal(warned,true);
});
test('duplicate save taps create one request and copy stays locked during that request',async()=>{
  let finish;const f=await setup((path,opts)=>opts.method==='PUT'?new Promise(resolve=>{finish=()=>resolve({ok:true,json:async()=>({...saved,revision:1,saved_at:'now'})})}):null);
  const pending=f.submit();await f.submit();assert.equal(f.calls.filter(c=>c.options.method==='PUT').length,1);assert.equal(f.el('Fields').disabled,true);finish();await pending;assert.equal(f.el('Save').disabled,false);
});
test('submitted Pinterest copy is displayed read-only without enabling creator publishing',async()=>{
  const f=await setup((path,opts)=>path.endsWith('/1')?{ok:true,json:async()=>({...saved,locked:true,publication_status:'published'})}:null);
  assert.equal(f.el('Fields').disabled,true);assert.equal(f.el('Save').disabled,true);assert.match(f.el('SaveStatus').textContent,/Read-only/);await f.submit();assert.equal(f.calls.filter(c=>c.options.method==='PUT').length,0);
});
test('preview shows current edits as text, while source text remains unchanged',async()=>{
  const f=await setup();f.el('Description').value='<img src=x onerror=alert(1)>';f.el('Description').events.input();f.el('PreviewTab').events.click();
  assert.equal(f.el('PreviewDescription').textContent,'<img src=x onerror=alert(1)>');assert.equal(f.el('Translation').textContent,saved.translation);assert.equal(f.el('Preview').hidden,false);assert.equal(f.el('Write').hidden,true);
});

const connected={enabled:true,connected:true,username:'fixture',board_id:'123',board_name:'Reminders'};
const ready={...saved,revision:1,saved_at:'now',publishing_enabled:true,publication:{status:'not_sent'}};
const ok=data=>({ok:true,json:async()=>structuredClone(data)});
async function publishingSetup(handler){
  const f=await setup(async(path,opts)=>{
    const override=handler&&await handler(path,opts);if(override)return override;
    if(path.endsWith('/connection'))return ok(connected);
    if(path.endsWith('/1'))return ok(ready);
    if(path.endsWith('/review'))return ok({receipt:'signed-fixture',username:'fixture',board_name:'Reminders'});
    if(path.endsWith('/status'))return ok({status:'not_sent'});
  });
  f.el('Image').onload();return f;
}
async function approve(f){await f.el('Review').events.click();f.el('Reviewed').checked=true;f.el('Reviewed').events.change();}
test('Standard review needs a loaded image and explicit confirmation; duplicate publish taps send once',async()=>{
  let finish;const f=await publishingSetup((path,opts)=>path.endsWith('/publish')?new Promise(resolve=>{finish=()=>resolve(ok({status:'published',url:'https://www.pinterest.com/pin/456/'}))}):null);
  assert.equal(f.el('Publish').disabled,true);await f.el('Review').events.click();assert.equal(f.el('Publish').disabled,true);
  f.el('Reviewed').checked=true;f.el('Reviewed').events.change();assert.equal(f.el('Publish').disabled,false);
  const pending=f.el('Publish').events.click();await f.el('Publish').events.click();assert.equal(f.calls.filter(c=>c.path.endsWith('/publish')).length,1);
  finish();await pending;assert.equal(f.el('Fields').disabled,true);assert.equal(f.el('PublishedLink').hidden,false);
  const payload=JSON.parse(f.calls.find(c=>c.path.endsWith('/publish')).options.body);assert.deepEqual(Object.keys(payload).sort(),['receipt','reviewed','revision','source_version']);
});
test('editing copy or changing board invalidates approval and requires another review',async()=>{
  const f=await publishingSetup();await approve(f);assert.equal(f.el('Publish').disabled,false);
  f.el('Description').value='Changed Fixture 1';f.el('Description').events.input();assert.equal(f.el('Approval').hidden,true);assert.equal(f.el('Publish').disabled,true);
  const g=await publishingSetup();await approve(g);g.el('Board').events.change();assert.equal(g.el('Publish').disabled,true);assert.equal(g.el('Reviewed').checked,false);
});
test('lost publish response only checks saved status, never repeats the write, and recovers confirmed success',async()=>{
  const f=await publishingSetup((path,opts)=>{if(path.endsWith('/publish'))throw Error('Response lost');if(path.endsWith('/status'))return ok({status:'published',url:'https://www.pinterest.com/pin/456/'});});
  await approve(f);await f.el('Publish').events.click();assert.equal(f.el('Publish').disabled,true);assert.equal(f.el('CheckStatus').hidden,false);
  await f.el('CheckStatus').events.click();assert.equal(f.el('PublishedLink').hidden,false);assert.equal(f.calls.filter(c=>c.path.endsWith('/publish')).length,1);assert.equal(f.el('Fields').disabled,true);
});
test('a confirmed unsubmitted result can be reviewed again after a connection failure',async()=>{
  const f=await publishingSetup((path,opts)=>{if(path.endsWith('/publish'))throw Error('Offline before request');});
  await approve(f);await f.el('Publish').events.click();await f.el('CheckStatus').events.click();assert.equal(f.el('Fields').disabled,false);assert.equal(f.el('Review').disabled,false);assert.equal(f.el('Publish').disabled,true);
});
test('sandbox result stays read-only and is explicitly distinct from a public Pin',async()=>{
  const f=await publishingSetup(path=>path.endsWith('/1')?ok({...ready,locked:true,publication:{status:'published',sandbox:true,url:'https://www.pinterest.com/pin/456/'}}):null);
  assert.match(f.el('PublishStatus').textContent,/not published publicly/);assert.equal(f.el('Verify').hidden,true);assert.equal(f.el('Review').disabled,true);
});
test('board request failure keeps the current destination and offers a usable retry',async()=>{
  let attempts=0;const f=await publishingSetup(path=>{if(path.endsWith('/boards')){if(++attempts===1)throw Error('Pinterest unavailable');return ok({items:[{id:'789',name:'Other board'}],bookmark:null})}});
  await f.el('LoadBoards').events.click();assert.match(f.el('ConnectionNotice').textContent,/unavailable/);assert.equal(f.el('LoadBoards').disabled,false);
  await f.el('LoadBoards').events.click();assert.equal(f.el('Board').options[1].value,'789');assert.equal(f.el('BoardSummary').textContent,'Publishing to Reminders');
});
