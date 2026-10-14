const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../../app/static/studio-design.js'),'utf8');
function setup(){
 const nodes={},timers=[],requests=[];let data={card_message:{headline:'Exact source'},style:'editorial',brand_kit:{palette:'olive'},post_format:'feed_4_5'};
 class Node{
  constructor(){this.children=[];this.dataset={};this.hidden=false;this.value='olive';this.style={};this.attrs={};this.classList={contains:()=>false};}
  set id(v){this._id=v;nodes[v]=this;}get id(){return this._id;}
  append(...items){this.children.push(...items);}before(){}after(){}focus(){}addEventListener(){}removeAttribute(k){delete this.attrs[k];}getAttribute(k){return this.attrs[k]||null;}setAttribute(k,v){this.attrs[k]=v;}
  closest(){return this.label ||= new Node();}querySelector(s){return this.selectors?.[s] || (this.selectors||={})[s] || (this.selectors[s]=new Node());}
  querySelectorAll(){return [];}showModal(){this.open=true;}close(){this.open=false;}
 }
 const el=id=>nodes[id] ||= new Node();el('newPostModal').dataset.step='2';el('quoteCardPreview').src='saved-final.jpg';
 const window={sabeelPhotoFamilies:['midnight_oasis'],studioPreviewRequest:()=>JSON.parse(JSON.stringify(data)),studioShareSnapshot:()=>({generating:false}),changeStudioBrand(){}};
 const context={window,document:{getElementById:el,createElement:()=>new Node(),createComment:()=>new Node()},AbortController,JSON,Error,
 setTimeout:(fn,delay)=>{const t={fn,delay};timers.push(t);return t;},clearTimeout:t=>{if(t)t.cancelled=true;},
 fetch:(url,options)=>new Promise(resolve=>requests.push({url,options,resolve}))};vm.runInNewContext(code,context);
 return {window,nodes,requests,el,setData:d=>{data=d;},tick:()=>{const pending=timers.filter(t=>!t.cancelled&&t.delay===350);pending.forEach(t=>{t.cancelled=true;t.fn();});},flush:()=>new Promise(resolve=>setImmediate(resolve))};
}
const ok=(label='new')=>({ok:true,json:async()=>({preview_only:true,image_data:'data:image/jpeg;base64,'+label,page_index:0,page_count:1})});
test('several choices debounce to one preview and never call image generation',async()=>{
 const f=setup();f.window.queueStudioEditPreview();f.window.queueStudioEditPreview();f.window.queueStudioEditPreview();f.tick();
 assert.equal(f.requests.length,1);assert.equal(f.requests[0].url,'/api/studio/preview-visual');f.requests[0].resolve(ok());await f.flush();
 assert.equal(f.el('quoteCardPreview').src,'saved-final.jpg');assert.match(f.el('studioEditPreview').src,/base64,new/);
});
test('an earlier response cannot replace a newer edit or a closed editor',async()=>{
 const f=setup();f.window.queueStudioEditPreview();f.tick();
 f.setData({card_message:{headline:'Exact source'},style:'editorial',brand_kit:{palette:'night'}});f.window.queueStudioEditPreview();f.tick();
 f.requests[1].resolve(ok('latest'));await f.flush();f.requests[0].resolve(ok('old'));await f.flush();assert.match(f.el('studioEditPreview').src,/latest$/);
 f.window.clearStudioEditPreview();assert.equal(f.el('studioEditPreview').hidden,true);
 f.window.queueStudioEditPreview();f.tick();f.window.clearStudioEditPreview();f.requests[2].resolve(ok('late'));await f.flush();assert.equal(f.el('studioEditPreview').hidden,true);
});
test('missing photographic background never initiates paid work and failures keep the final media',async()=>{
 const f=setup();f.setData({card_message:{headline:'Exact source'},style:'midnight_oasis'});f.window.queueStudioEditPreview();f.tick();assert.equal(f.requests.length,0);
 f.setData({card_message:{headline:'Exact source'},style:'midnight_oasis',background_token:'saved-photo'});f.window.queueStudioEditPreview();f.tick();
 f.requests[0].resolve({ok:false,json:async()=>({detail:'Preview unavailable'})});await f.flush();assert.equal(f.el('quoteCardPreview').src,'saved-final.jpg');assert.equal(f.el('sdRetry').hidden,false);
});
test('opening appearance without an edit keeps the final review available',()=>{
 const f=setup();f.window.studioShareSnapshot=()=>({generating:false,dirty:false,payload:{media_url:'saved-final.jpg'}});
 f.window.queueStudioEditPreview();f.tick();assert.equal(f.requests.length,0);
 assert.equal(f.el('studioEditPreview').hidden,true);assert.equal(f.el('newPostModal').dataset.editPreview,undefined);
});
