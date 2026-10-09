const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../../app/routes/ui_assets.py'), 'utf8');
const code = source.slice(source.indexOf('    // Feed visual requests:'), source.indexOf('    // End feed visual requests.'));
function setup(fetch) {
  const nodes = {};
  const el = id => nodes[id] ||= {value: '', disabled: false, src: '', textContent: '', querySelector: () => null, classList: {add(){},remove(){}}};
  el('studioStyle').value = 'quiet_photography'; el('studioLayout').value = 'english_first';
  const context = {window: {showStudioPage(){},rememberStudio(){}}, studioViewedPages:new Set(), studioSequenceReviewed:false, document: {getElementById: el}, fetch, AbortController, setTimeout, clearTimeout,
    studioCardMessage: {headline: 'Exact fixture'}, studioGalleryImage: null, studioEngine: 'openai',
    currentQuoteCardUrl: null, isQuoteCardOutOfDate: true, alert: () => {throw Error('unexpected alert');}};
  vm.runInNewContext(code, context);
  return {context, el, generate: () => context.window.generateQuoteCard(), cancel: () => vm.runInNewContext('cancelStudioVisual()',context)};
}
const response = data => ({ok: true, json: async () => data});
test('layout change sends same source and background receipt without replacing the photograph', async () => {
  const requests = [];
  const f = setup(async (url, opts) => {requests.push(JSON.parse(opts.body)); return response({image_url:'https://cdn.test/card.jpg',visual_design:{background_token:'receipt',background_reused:requests.length>1,quality:{status:'passed'}}});});
  await f.generate(); f.el('studioLayout').value = 'bilingual'; await f.generate();
  assert.equal(requests[1].background_token,'receipt');
  assert.equal(requests[1].layout,'bilingual');
  assert.deepEqual(requests[0].card_message,requests[1].card_message);
  assert.match(f.el('visualQualityNote').textContent,/photograph was reused/);
  assert.equal(f.el('btnGenerateCard').disabled,false);
});
test('duplicate clicks and late responses cannot replace a newer or closed session', async () => {
  let resolve, calls=0;
  const f=setup(() => {calls++; return new Promise(r=>resolve=r);});
  const first=f.generate(); await f.generate(); assert.equal(calls,1);
  f.cancel(); resolve(response({image_url:'old'})); await first;
  assert.equal(f.context.currentQuoteCardUrl,null);
  assert.equal(f.el('btnGenerateCard').disabled,false);
});
test('failed layout and HTTP errors preserve the previous preview and allow retry', async () => {
  const f=setup(async()=>({ok:false,json:async()=>({error:'Complete source needs a sequence.'})}));
  f.context.currentQuoteCardUrl='previous'; f.el('quoteCardPreview').src='previous';
  await f.generate();
  assert.equal(f.el('quoteCardPreview').src,'previous');
  assert.equal(f.context.isQuoteCardOutOfDate,true);
  assert.match(f.el('visualQualityNote').textContent,/sequence/);
  assert.equal(f.el('btnGenerateCard').disabled,false);
});

test('changing the source clears its outputs and discards an in-flight visual', async () => {
  let resolve;
  const f=setup(() => new Promise(r=>resolve=r));
  const generation=f.generate();
  f.context.window.resetStudioSourceOutput();
  resolve(response({image_url:'stale-source-card'})); await generation;
  assert.equal(f.context.studioCardMessage,null);
  assert.equal(f.context.currentQuoteCardUrl,null);
  assert.equal(f.el('finalMediaUrl').value,'');
});

test('rejected scene retains its raw background for a free layout retry but never a publishable manifest', async () => {
  const requests=[];
  const f=setup(async(url,opts)=>{
    requests.push(JSON.parse(opts.body));
    return {ok:false,json:async()=>({error:'Choose a quieter layout.',visual_design:{family:'luxury_editorial',background_token:'saved-raw',quality:{status:'rejected'}}})};
  });
  f.el('studioStyle').value='luxury_editorial';
  await f.generate();f.el('studioLayout').value='bilingual';await f.generate();
  assert.equal(requests[1].background_token,'saved-raw');
  assert.equal(f.context.currentQuoteCardUrl,null);
  assert.equal(f.context.isQuoteCardOutOfDate,true);
  assert.equal(f.el('btnGenerateCard').disabled,false);
  assert.match(f.el('visualQualityNote').textContent,/quieter layout/);
});

test('direction changes drop the receipt and update the generation action', async () => {
  const requests=[];
  const f=setup(async(url,opts)=>{requests.push(JSON.parse(opts.body));return response({image_url:'https://cdn.test/card.jpg',visual_design:{background_token:'old-photo'}});});
  f.context.window.invalidateQuoteCard=()=>{};
  await f.generate();
  f.el('studioCustomDirection').value='night light';
  f.context.window.changeStudioBackground();
  assert.equal(f.el('btnGenerateCard').innerText,'Generate background & design');
  assert.equal(f.el('newStudioPhotoButton').hidden,true);
  await f.generate();
  assert.equal(requests[1].background_token,null);
  assert.equal(requests[1].visual_prompt,'night light');
});
test('budget denial retains a valid previous image and its review actions without automatic retry',async()=>{
 let calls=0,hidden=false;
 const f=setup(async()=>{calls++;return {ok:false,json:async()=>({detail:"Your workspace has reached today's image generation limit."})}});
 f.context.currentQuoteCardUrl='saved-image';f.context.isQuoteCardOutOfDate=false;f.context.studioSequenceReviewed=true;
 f.el('quoteCardPreview').src='saved-image';f.el('cardActions').classList={add:()=>hidden=true,remove:()=>hidden=false};
 await f.generate();assert.equal(calls,1);assert.equal(hidden,false);assert.equal(f.context.studioSequenceReviewed,true);
 assert.equal(f.el('quoteCardPreview').src,'saved-image');assert.match(f.el('visualQualityNote').textContent,/generation limit/);assert.equal(f.el('btnGenerateCard').disabled,false);
});
