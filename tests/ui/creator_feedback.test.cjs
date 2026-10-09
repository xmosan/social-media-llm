const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const code=fs.readFileSync(require('node:path').join(__dirname,'../../app/static/creator-feedback.js'),'utf8');
const event={preventDefault(){}};
function setup(fetch){
 const nodes={};for(const id of ['feedback-form','feedback-submit','device','task','outcome','confidence','notes','feedback-recovery','feedback-saved','status']) nodes[id]={value:id,hidden:false,disabled:false,textContent:'',listeners:{},classList:{remove(){},add(){}},addEventListener(n,f){this.listeners[n]=f},reportValidity(){return true},focus(){}};
 let ids=0;vm.runInNewContext(code,{document:{getElementById:id=>nodes[id]},fetch,crypto:{randomUUID:()=>String(++ids)},AbortController,setTimeout,clearTimeout,TypeError});
 return nodes;
}
const ok={ok:true,json:async()=>({ok:true,feedback_id:12})};
test('duplicate click sends once, waits for confirmation, then clears private answers',async()=>{
 let done,calls=0;const n=setup(async()=>{calls++;return new Promise(r=>done=r)});
 const first=n['feedback-form'].listeners.submit(event);await n['feedback-form'].listeners.submit(event);
 assert.equal(calls,1);assert.equal(n.notes.disabled,true);assert.equal(n['feedback-submit'].disabled,true);
 done(ok);await first;assert.equal(n['feedback-form'].hidden,true);assert.equal(n.notes.value,'');assert.match(n.status.textContent,/#12 saved/);
 await n['feedback-form'].listeners.submit(event);assert.equal(calls,1);
});
test('uncertain response preserves answers and retry identity, editing starts a new report',async()=>{
 const ids=[];const n=setup(async(path,opts)=>{ids.push(JSON.parse(opts.body).request_id);throw new TypeError('Network error')});
 await n['feedback-form'].listeners.submit(event);assert.equal(n.notes.value,'notes');assert.equal(n.notes.disabled,false);assert.match(n.status.textContent,/Retry with the same answers/);
 await n['feedback-form'].listeners.submit(event);assert.equal(ids[0],ids[1]);n.notes.value='changed';await n['feedback-form'].listeners.submit(event);assert.notEqual(ids[1],ids[2]);
});
test('expired access offers sign in, invalid response never claims success',async()=>{
 const n=setup(async()=>({ok:false,status:401,json:async()=>({detail:'Please sign in.'})}));await n['feedback-form'].listeners.submit(event);assert.equal(n['feedback-recovery'].hidden,false);assert.equal(n['feedback-form'].hidden,false);assert.match(n.status.textContent,/sign in/);
 const broken=setup(async()=>({ok:true,json:async()=>({})}));await broken['feedback-form'].listeners.submit(event);assert.match(broken.status.textContent,/confirm/);assert.equal(broken.notes.value,'notes');
});
