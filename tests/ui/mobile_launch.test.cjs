const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm'), path=require('node:path');
process.env.TZ='America/Detroit';
const source=fs.readFileSync(path.join(__dirname,'../../app/routes/ui_assets.py'),'utf8');
const workspace=fs.readFileSync(path.join(__dirname,'../../app/static/creator-workspace.js'),'utf8');
const section=(start,end)=>source.slice(source.indexOf(start),source.indexOf(end,source.indexOf(start)));
const node=()=>({value:'',textContent:'',innerText:'',innerHTML:'',hidden:false,style:{},classList:{add(){},remove(){},toggle(){}}});
function context(){const nodes={};const el=id=>nodes[id]||=(node());const radios=[{value:'later'},{value:'now'}];return {el,radios,c:{window:{},document:{getElementById:el,querySelectorAll:()=>radios},Date,Intl,AbortSignal,studioSessionEpoch:1,studioSaveBusy:false,currentQuoteCardUrl:null,studioVisualDesign:null,sequencePages:()=>[]}};}
test('timing selection exposes one explicit action; returning to share defaults safely to later',()=>{
 const f=context();vm.runInNewContext(section('    window.setStudioShareTiming =','    window.prepareShare ='),f.c);
 f.c.window.setStudioShareTiming('now');assert.equal(f.el('studioSubmitBtn').hidden,true);assert.equal(f.el('studioScheduleFields').hidden,true);assert.equal(f.el('studioShareNowBtn').hidden,false);assert.equal(f.radios[1].checked,true);
 f.c.window.setStudioShareTiming('later');assert.equal(f.el('studioShareNowBtn').hidden,true);assert.equal(f.el('studioScheduleFields').hidden,false);assert.equal(f.radios[0].checked,true);
});
test('Enter cannot schedule while publish-now is selected or while a save is busy',async()=>{
 const f=context();let called=0;f.c.persistStudioDraft=async()=>{called++};vm.runInNewContext(section('    window.submitNewPost =',"    window.addEventListener('load'"),f.c);
 f.el('studioSubmitBtn').hidden=true;await f.c.window.submitNewPost({preventDefault(){}});assert.equal(called,0);
 f.el('studioSubmitBtn').hidden=false;f.c.studioSaveBusy=true;await f.c.window.submitNewPost({preventDefault(){}});assert.equal(called,0);
});
test('schedule defaults preserve local wall clock near midnight',()=>{
 const RealDate=Date;class FixedDate extends RealDate{constructor(...args){super(...(args.length?args:['2026-10-08T23:45:00-04:00']));}}
 const f=context();f.c.Date=FixedDate;vm.runInNewContext(section('    window.openScheduleModal =','    window.closeScheduleModal ='),f.c);
 f.c.window.openScheduleModal(4);assert.equal(f.el('schedulePostTime').value,'2026-10-09T23:00');
});
test('late account checks never update a different editor session and have a timeout',async()=>{
 const f=context();let resolve,options;
 f.el('studioAccount').value='7';f.el('studioAccount').options=[{text:'Local account'}];f.el('studioAccount').selectedIndex=0;
 f.c.fetch=(_,o)=>{options=o;return new Promise(r=>resolve=r);};f.c.window.setStudioShareTiming=()=>{};f.c.window.updateScheduleConfirmation=()=>{};
 vm.runInNewContext(section('    window.prepareShare =','    window.updateScheduleConfirmation ='),f.c);
 f.c.window.prepareShare();assert.ok(options.signal);f.c.studioSessionEpoch++;f.el('manifestAccountStatus').innerHTML='New session';
 resolve({ok:true,json:async()=>({healthy:true})});await new Promise(r=>setImmediate(r));assert.equal(f.el('manifestAccountStatus').innerHTML,'New session');
});
test('reflection suggestion uses the visible source pane and explicit acceptance/undo',()=>{
 const nodes={},el=id=>nodes[id]||={...node(),children:[],append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},focus(){},remove(){delete nodes[this.id]}};
 let pane,placement,remembered=0,changed=0;
 el('editSupporting').value='My reflection';el('editSupporting').parentNode={before(p){nodes.creatorSuggestion=p;placement=p;}};
 const c={byId:el,showTool:k=>pane=k,suggestion:null,undo:null,window:{studioSourceContext:{reference:'Exact fixture'},rememberStudio:()=>remembered++,updateStudioCardFromUI:()=>changed++},document:{createElement:()=>({...node(),children:[],append(...items){this.children.push(...items)},replaceChildren(){this.children=[]},focus(){},remove(){}})}};
 vm.runInNewContext(workspace.slice(workspace.indexOf('  function suggestionTarget('),workspace.indexOf('  // Focus stays in the editor')),c);
 c.window.offerCreatorSuggestion('reflection','My reflection','Optional suggestion');assert.equal(pane,'words');assert.ok(placement);assert.equal(el('editSupporting').value,'My reflection');
 const actions=placement.children.at(-1);actions.children[1].onclick();assert.equal(el('editSupporting').value,'Optional suggestion');assert.equal(changed,1);
 placement.children[1].onclick();assert.equal(el('editSupporting').value,'My reflection');assert.equal(remembered,2);
});
