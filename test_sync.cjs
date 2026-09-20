const assert=require('node:assert/strict');
global.SATCore=require('./web/bank-core.js');const engine=require('./web/sync-engine.js');
const seed=()=>({format:'sat-bank',version:1,bank:{id:'main',name:'Test'},questions:[{id:'q1',domain:'Reading',skill:'Inference',difficulty:'easy',passage_html:'Text',prompt_html:'Which?',explanation_html:'Why',answer_type:'choice',correct_answer:'A',accepted_answers:['A'],choices:'ABCD'.split('').map(letter=>({letter,content_html:letter})),sources:[]}],attempts:[],notes:[],ratings:[],reviews:[],tags:[]});
function store(data=seed()){
 const rows=new Map([['main',{id:'main',name:'Test',data:structuredClone(data),generation:1,syncedGeneration:0}]]);
 return {rows,async records(){return [...rows.values()].map(r=>structuredClone(r));},async record(id){return rows.has(id)?structuredClone(rows.get(id)):undefined;},async applyRemote(id,data){let r=rows.get(id);if(!r){r={id,name:data.bank.name,data:structuredClone(data),generation:1,syncedGeneration:0};rows.set(id,r);}else{const result=SATCore.merge(r.data,data).data;if(SATCore.canonical(result)!==SATCore.canonical(r.data)){r.data=result;r.generation++;}}return structuredClone(r);},async acknowledge(id,generation){rows.get(id).syncedGeneration=Math.max(rows.get(id).syncedGeneration,generation);},edit(content){SATCore.request(rows.get('main').data,'note',{question_id:'q1',content});rows.get('main').generation++;}};
}
function remote(){let row=null;return {async list(){return row?['main']:[];},async read(){return row?structuredClone(row):null;},async put(id,expected,state,contentHash,questions){if(expected!==(row?.revision||0))return {accepted:false};row={data:{...structuredClone(state),questions:questions||row.data.questions},revision:expected+1,contentHash};return {accepted:true,revision:row.revision};},get row(){return row;}};}
const guard=()=>{};
(async()=>{
 const cloud=remote(),a=store(),b=store();a.edit('PC note');b.edit('Phone note');
 await Promise.all([engine.syncAll({store:a,remote:cloud,guard}),engine.syncAll({store:b,remote:cloud,guard})]);
 await engine.syncAll({store:a,remote:cloud,guard});assert(SATCore.noteText(a.rows.get('main').data.notes).includes('Phone note'));assert.equal(cloud.row.data.notes.length,2);
 // A committed upload with a lost response is retried without duplicating history.
 const c=store(),loss=remote(),put=loss.put;let fail=true;loss.put=async(...args)=>{const result=await put(...args);if(fail){fail=false;throw Error('connection lost');}return result;};c.edit('Pending');
 await assert.rejects(()=>engine.syncAll({store:c,remote:loss,guard}),/connection lost/);assert.equal(c.rows.get('main').syncedGeneration,0);
 await engine.syncAll({store:c,remote:loss,guard});assert.equal(loss.row.data.notes.length,1);
 // Edits made while an upload is in flight must stay pending after its acknowledgement.
 const d=store(),inflight=remote(),send=inflight.put;let edit=true;inflight.put=async(...args)=>{if(edit){edit=false;d.edit('Typed during upload');}return send(...args);};
 const result=await engine.syncAll({store:d,remote:inflight,guard});assert.equal(result.pending,true);await engine.syncAll({store:d,remote:inflight,guard});assert.equal(SATCore.noteText(inflight.row.data.notes),'Typed during upload');
 // A stale editor must not resolve an incoming note that the person has not seen.
 const stale=seed();SATCore.request(stale,'note',{question_id:'q1',content:'Initial'});const parents=SATCore.request(stale,'question/q1').note_parents;
 SATCore.request(stale,'note',{question_id:'q1',content:'Other device'});SATCore.request(stale,'note',{question_id:'q1',content:'Still typing',parents});assert.equal(SATCore.leaves(stale.notes).length,2);
 // Account changes during a request never acknowledge another account's data.
 const isolated=store(),r=remote();let valid=true;r.put=async()=>{valid=false;return {accepted:true,revision:1};};await assert.rejects(()=>engine.syncAll({store:isolated,remote:r,guard:()=>{if(!valid)throw Error('Account changed');}}),/Account changed/);assert.equal(isolated.rows.get('main').syncedGeneration,0);
 console.log('Sync engine: concurrent devices, lost acknowledgements, in-flight edits, stale notes and account guards passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});

