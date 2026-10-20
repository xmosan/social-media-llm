const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const code = fs.readFileSync(require('node:path').join(__dirname, '../../app/static/owner-security.js'), 'utf8');
const settle = () => new Promise(r => setImmediate(r));
const ok = data => ({ok:true, status:200, json:async () => data});
function setup(fetch, timers={}) {
  const nodes={}, listeners={}, redirects=[];
  const get = id => nodes[id] ??= {hidden:true, disabled:false, value:'', textContent:'', checked:false,
    children:[], listeners:{}, addEventListener(k, fn) {this.listeners[k]=fn;},
    removeAttribute(k) {delete this[k];}, replaceChildren() {this.children=[];},
    appendChild(n) {this.children.push(n);}, focus() {}};
  const window = {location:{assign:v=>redirects.push(v),reload:()=>redirects.push('reload')},
    addEventListener:(k,fn)=>listeners[k]=fn};
  vm.runInNewContext(code, {document:{getElementById:get,
    createElement:()=>({textContent:''}),querySelectorAll:()=>['start','verify','finish','revoke'].map(get)},
    window,fetch,AbortController,TypeError,setTimeout:timers.setTimeout||setTimeout,
    clearTimeout:timers.clearTimeout||clearTimeout});
  return {get, listeners, redirects};
}
test('enrollment is explicit; repeated taps make one request and secrets disappear on leave', async () => {
  let done, calls=0;
  const s=setup(async path => path.endsWith('/status') ? ok({mode:'enroll'}) :
    (++calls,new Promise(r=>done=r)));
  await settle();
  assert.equal(calls,0); assert.equal(s.get('enroll').hidden,false);
  s.get('start').listeners.click(); s.get('start').listeners.click();
  assert.equal(calls,1); assert.equal(s.get('start').disabled,true);
  done(ok({setup_key:'synthetic-key',qr:'data:image/png;base64,synthetic'}));
  await settle();
  assert.equal(s.get('setup-key').textContent,'synthetic-key');
  s.listeners.pagehide();
  assert.equal(s.get('setup-key').textContent,''); assert.equal(s.get('qr').src,undefined);
  s.listeners.pageshow({persisted:true}); assert.deepEqual(s.redirects,['reload']);
});
test('recovery codes require acknowledgment and never use server-supplied navigation', async () => {
  const s=setup(async p=> p.endsWith('/status') ? ok({mode:'verify'}) :
    ok({recovery_codes:['fixture-only'],next:'https://evil.example'}));
  await settle();
  s.get('code').value='123456';
  s.get('verification').listeners.submit({preventDefault(){}});
  await settle();
  assert.equal(s.get('code').value,'');
  assert.equal(s.get('recovery').hidden,false);
  s.get('finish').listeners.click(); assert.equal(s.redirects.length,0);
  s.get('saved').checked=true; s.get('saved').listeners.change();
  s.get('finish').listeners.click(); assert.deepEqual(s.redirects,['/admin']);
});
test('expired challenge returns to sign-in and clears the entered code', async () => {
  const s=setup(async p=>p.endsWith('/status') ? ok({mode:'verify'}) :
    {ok:false,status:401,json:async()=>({detail:'Verification expired. Sign in again.'})});
  await settle(); s.get('code').value='123456';
  s.get('verification').listeners.submit({preventDefault(){}});
  await settle();
  assert.equal(s.get('sign-in').hidden,false); assert.equal(s.get('code').value,'');
  assert.match(s.get('message').textContent,/expired/); assert.equal(s.get('verify').disabled,false);
});
test('network timeout stops loading without silently retrying verification', async () => {
  let timeout, calls=0;
  const s=setup(async (p,o)=>{ calls++; return new Promise((resolve,reject)=>
    o.signal.addEventListener('abort',()=>reject(Object.assign(new Error(),{name:'AbortError'})))); },
    {setTimeout:fn=>(timeout=fn,1),clearTimeout(){}});
  timeout(); await settle();
  assert.equal(calls,1); assert.equal(s.get('verify').disabled,false);
  assert.match(s.get('message').textContent,/Refresh this page/);
});
