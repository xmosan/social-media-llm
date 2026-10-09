const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const code=fs.readFileSync(require('node:path').join(__dirname,'../../app/static/tester-access.js'),'utf8');
function element(){return {children:[],listeners:{},disabled:false,hidden:true,value:'',textContent:'',classList:{toggle(){}},append(...n){this.children.push(...n)},replaceChildren(){this.children=[]},addEventListener(n,fn){this.listeners[n]=fn},setAttribute(){},focus(){},select(){}}}
function setup(fetch,page='join',hash='#invite='+'x'.repeat(43)){
 const nodes=Object.fromEntries(['status','list-status','recovery','join-form','join-submit','pilot-summary','pilot-details','password','name','email','continue','invite-form','invite-submit','issued','invite-link','copy-link','refresh','invitations','invitation-days','pilot-days'].map(id=>[id,element()]));
 nodes.password.value='synthetic-pilot-password';nodes.name.value='Fixture';nodes.email.value='fixture@example.test';nodes['invitation-days'].value='7';nodes['pilot-days'].value='30';
 const histories=[];const context={document:{body:{dataset:{page}},getElementById:id=>nodes[id],createElement:element},location:{hash,pathname:'/join'},history:{replaceState:(...v)=>histories.push(v)},fetch,URLSearchParams,AbortController,TextEncoder,Intl,Date,setTimeout,clearTimeout,confirm:()=>true,navigator:{clipboard:{writeText:async()=>{}}}};
 vm.runInNewContext(code,context);return {nodes,histories};
}
const settle=()=>new Promise(r=>setImmediate(r));const event={preventDefault(){}};
const info={pilot_days:30,daily_images:20,daily_text:200,expires_at:'2026-10-16T00:00:00Z'};
const ok=data=>({ok:true,json:async()=>data});
test('secret removed before network and missing link offers recovery without fetch',async()=>{
 let calls=0;const {nodes,histories}=setup(async()=>{calls++;return ok(info)},'join','');await settle();assert.equal(calls,0);assert.equal(histories.length,1);assert.equal(histories[0][2],'/join');assert.equal(nodes.recovery.hidden,false);
});
test('valid link loads limits then submits once and clears password on success',async()=>{
 let finish,posts=0;const {nodes}=setup(async(path,options)=>{if(path.endsWith('check'))return ok(info);posts++;return await new Promise(r=>finish=r)});await settle();assert.equal(nodes['join-form'].hidden,false);assert.match(nodes['pilot-summary'].textContent,/20 image/);
 nodes.recovery.hidden=false; const first=nodes['join-form'].listeners.submit(event);await nodes['join-form'].listeners.submit(event);assert.equal(posts,1);assert.equal(nodes['join-submit'].disabled,true);
 finish(ok({access_expires_at:'2026-11-08T00:00:00Z'}));await first;assert.equal(nodes.password.value,'');assert.equal(nodes['join-form'].hidden,true);assert.equal(nodes.continue.hidden,false);assert.equal(nodes.recovery.hidden,true);
});
test('expired link cannot reveal join form',async()=>{const {nodes}=setup(async()=>({ok:false,json:async()=>({detail:'This invitation expired.'})}));await settle();assert.equal(nodes['join-form'].hidden,true);assert.match(nodes.status.textContent,/expired/);assert.equal(nodes.recovery.hidden,false)});
test('rejected redemption keeps fields and unlocks retry without navigating',async()=>{const {nodes}=setup(async path=>path.endsWith('check')?ok(info):({ok:false,json:async()=>({detail:'Use the invited email.'})}));await settle();await nodes['join-form'].listeners.submit(event);assert.equal(nodes['join-submit'].disabled,false);assert.equal(nodes['join-form'].hidden,false);assert.match(nodes.status.textContent,/invited email/);assert.equal(nodes.continue.hidden,true)});
test('multibyte password over bcrypt byte limit is rejected before dispatch',async()=>{let calls=0;const {nodes}=setup(async()=>{calls++;return ok(info)});await settle();nodes.password.value='أ'.repeat(40);await nodes['join-form'].listeners.submit(event);assert.equal(calls,1);assert.match(nodes.status.textContent,/72 UTF-8/)});
test('admin renders recipient as text and revocation is guarded from duplicate requests',async()=>{
 let finish,posts=0;const {nodes}=setup(async(path,options)=>{if(options.body){posts++;return await new Promise(r=>finish=r)}return ok({items:[{id:'fixture',email:'<fixture>@example.test',status:'pending',expires_at:info.expires_at,pilot_days:30}]})},'admin');await settle();
 const row=nodes.invitations.children[0];assert.equal(row.children[0].children[0].textContent,'<fixture>@example.test');assert.equal('innerHTML' in row,false);const button=row.children[1];const first=button.listeners.click();await button.listeners.click();assert.equal(posts,1);finish(ok({status:'revoked'}));await first;assert.match(nodes.status.textContent,/revoked/);
});
test('issue shows link once with explicit no email sent and refresh does not duplicate issue',async()=>{
 let posts=0;const {nodes}=setup(async(path,options)=>{if(options.body){posts++;return ok({invitation:{id:'one',email:'fixture@example.test'},link:'https://fixture.test/join#invite=synthetic'})}return ok({items:[]})},'admin');await settle();await nodes['invite-form'].listeners.submit(event);assert.equal(posts,1);assert.equal(nodes.issued.hidden,false);assert.match(nodes.status.textContent,/No email was sent/);assert.equal(nodes['invite-submit'].disabled,false);await nodes.refresh.listeners.click();assert.equal(posts,1);
});
