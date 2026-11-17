const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const {indexedDB}=require('fake-indexeddb');const core=require('./web/bank-core.js');
const seed=JSON.parse(fs.readFileSync('docs/seed.json','utf8'));const mathSeed=JSON.parse(fs.readFileSync('docs/math-seed.json','utf8'));const slovakSeed=JSON.parse(fs.readFileSync('docs/maturita-slovak-seed.json','utf8'));const maturitaMathSeed=JSON.parse(fs.readFileSync('docs/maturita-math-seed.json','utf8'));
function device(owner){
 const events=new EventTarget(),sandbox={indexedDB,localStorage:{getItem:()=>owner},fetch:async url=>({ok:true,json:async()=>structuredClone(String(url).includes('maturita-slovak')?slovakSeed:String(url).includes('maturita-math')?maturitaMathSeed:String(url).includes('math')?mathSeed:seed)}),SATCore:core,Event,console,document:{},setTimeout,clearTimeout,navigator:{}};
 sandbox.window=events;vm.runInNewContext(fs.readFileSync('web/offline.js','utf8'),sandbox);return events.SATOffline;
}
(async()=>{
 const guest=device(null);await guest.ready;await guest.request('main','note',{question_id:seed.questions[0].id,content:'Guest private note'});
 const a=device('user-a');await a.ready;assert.equal((await a.request('main','question/'+seed.questions[0].id)).note,'');
 await a.copyGuest('main','main');assert.equal((await a.request('main','question/'+seed.questions[0].id)).note,'Guest private note');
 const b=device('user-b');await b.ready;assert.equal((await b.request('main','question/'+seed.questions[0].id)).note,'');assert.equal((await b.records()).length,1,'Only the opened bank should download initially');
 const again=device('user-a');await again.ready;assert.equal((await again.request('main','question/'+seed.questions[0].id)).note,'Guest private note');
 const concurrent=device('user-a');await concurrent.ready;await Promise.all([a.request('main','attempt',{question_id:seed.questions[0].id,answer:'A',guessed:false}),concurrent.request('main','attempt',{question_id:seed.questions[0].id,answer:'B',guessed:true})]);
 assert.equal((await a.request('main','question/'+seed.questions[0].id)).history.length,2);
 const banks=await a.request('main','banks');assert.equal(banks.map(x=>x.id).sort().join(','),'main,math,maturita-math,maturita-slovak');
 const numeric=mathSeed.questions.find(q=>q.answer_type==='numeric'&&q.accepted_answers.length>1);
 assert.equal((await a.request('math','question/'+numeric.id)).answer_type,'numeric');
 assert.equal((await a.request('math','attempt',{question_id:numeric.id,answer:numeric.accepted_answers.at(-1),guessed:false})).is_correct,true);
 assert.equal((await a.request('main','question/'+seed.questions[0].id)).history.length,2,'Math attempt must not touch the English bank');
 const section=await a.request('maturita-slovak','questions?year=2009&section=3');assert.equal(section.length,8);assert.deepEqual(section.map(q=>q.ordinal),[17,18,19,20,21,22,23,24]);
 assert.equal((await a.request('maturita-slovak','meta')).is_slovak,true);
 console.log('IndexedDB: guest migration, account isolation, restart persistence, dual banks and concurrent tab writes passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
