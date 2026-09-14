const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const {indexedDB}=require('fake-indexeddb');const core=require('./web/bank-core.js');
const seed=JSON.parse(fs.readFileSync('docs/seed.json','utf8'));
function device(owner){
 const events=new EventTarget(),sandbox={indexedDB,localStorage:{getItem:()=>owner},fetch:async()=>({ok:true,json:async()=>structuredClone(seed)}),SATCore:core,Event,console,document:{},setTimeout,clearTimeout,navigator:{}};
 sandbox.window=events;vm.runInNewContext(fs.readFileSync('web/offline.js','utf8'),sandbox);return events.SATOffline;
}
(async()=>{
 const guest=device(null);await guest.ready;await guest.request('main','note',{question_id:seed.questions[0].id,content:'Guest private note'});
 const a=device('user-a');await a.ready;assert.equal((await a.request('main','question/'+seed.questions[0].id)).note,'');
 await a.copyGuest('main','main');assert.equal((await a.request('main','question/'+seed.questions[0].id)).note,'Guest private note');
 const b=device('user-b');await b.ready;assert.equal((await b.request('main','question/'+seed.questions[0].id)).note,'');assert.equal((await b.records()).length,1);
 const again=device('user-a');await again.ready;assert.equal((await again.request('main','question/'+seed.questions[0].id)).note,'Guest private note');
 const concurrent=device('user-a');await concurrent.ready;await Promise.all([a.request('main','attempt',{question_id:seed.questions[0].id,answer:'A',guessed:false}),concurrent.request('main','attempt',{question_id:seed.questions[0].id,answer:'B',guessed:true})]);
 assert.equal((await a.request('main','question/'+seed.questions[0].id)).history.length,2);
 console.log('IndexedDB: guest migration, account isolation, restart persistence and concurrent tab writes passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
