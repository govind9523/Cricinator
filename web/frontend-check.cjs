// Run: node web/frontend-check.cjs. No browser or dependencies required.
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const elements=new Map();
const element=id=>elements.get(id)||elements.set(id,{value:id==='mode'?'classic':'',textContent:'',dataset:{},children:[],classList:{add(){},remove(){}},setAttribute(){},focus(){},append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items}}).get(id);
let remote={phase:'home',revision:4,confidence:.33,engine_path:'legacy_fallback',fallback_reason:'AI has low confidence'};let fail=false;const calls=[];
const context=vm.createContext({console,AbortController,setTimeout,clearTimeout,crypto:require('node:crypto').webcrypto,CustomEvent:class{},window:{dispatchEvent(){}},document:{getElementById:element,body:{dataset:{}},querySelectorAll:()=>[],addEventListener(){},createElement:()=>element(Symbol())},fetch:async(url,options)=>{
 calls.push({url,...options});
 const data=url.includes('/roster')?{players:[{id:'world-123',name:'Example player',country:'Example team'}]}:url.endsWith('/coverage')?{catalog_count:20,playable_count:2}:url.endsWith('/research')?{classic:{clean_accuracy:'100.00%',clean_first_guess:'138/138',players:138,mean_questions:7.93,noisy_accuracy:'90.58%',noisy_first_guess:'250/276',noise_model:'synthetic noise'},world:{records:12559,questions:574,parsed_source_pages:277,sample_accuracy:'23.33%',ambiguous_records:7300},pipeline:['facts','features','posterior']}:remote;
 if(fail&&options.method==='POST'){fail=false;return{ok:false,json:async()=>({error:'Stale revision'})};}
 return{ok:true,json:async()=>data};
}});
(async()=>{
 vm.runInContext(readFileSync(__dirname+'/game.js','utf8'),context);
 await new Promise(resolve=>setTimeout(resolve,0));
 await vm.runInContext('act("start")',context);
 const start=calls.find(c=>c.url.endsWith('/start'));
 assert.equal(JSON.parse(start.body).revision,4);
 assert.equal(JSON.parse(start.body).mode,'classic');
 assert.ok(start.headers['Idempotency-Key']);
 fail=true;remote={phase:'home',revision:5};
 await vm.runInContext('act("undo")',context);
 assert.equal(calls.at(-1).url,'/api/state');
 assert.equal(vm.runInContext('state.revision',context),5);
 assert.equal(element('status').textContent,'Stale revision');
 await vm.runInContext('state = {phase:"home", mode:"world", revision:6, notice:"Round refreshed"}; render(); loadCorrection()',context);
 assert.ok(calls.some(c=>c.url==='/api/roster?mode=world'));
 assert.equal(vm.runInContext('correctionMode',context),'world');
 assert.equal(element('status').textContent,'Round refreshed');
 assert.equal(vm.runInContext('state.revision',context),6);
 assert.equal(element('classic-score').textContent,'100.00%');
 assert.equal(element('world-records').textContent,'12,559');
 assert.equal(element('pipeline').children?.length || 0,3);
 await vm.runInContext('state = {phase:"question", count:1, confidence:.44, engine_path:"legacy_fallback", fallback_reason:"AI has low confidence", question:{id:"q", text:"Question?"}}; render();',context);
 assert.ok(element('engine-note').textContent.includes('Legacy fallback active'));
 const html=readFileSync(__dirname+'/index.html','utf8');
 for(const match of readFileSync(__dirname+'/game.js','utf8').matchAll(/\$\("([\w-]+)"\)/g))assert.ok(html.includes(`id="${match[1]}"`),`Missing DOM element ${match[1]}`);
 console.log('PASS: revision, selected mode, idempotency key, stale-state recovery, mode-specific correction, retired-round notice, DOM bindings');
})().catch(error=>{console.error(error);process.exitCode=1;});
