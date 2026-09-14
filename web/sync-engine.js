/* Optimistic concurrency: pull, merge locally, compare-and-swap, acknowledge that generation only. */
(function(root){
 async function hash(questions){const bytes=new TextEncoder().encode(SATCore.canonical(questions));return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');}
 async function syncOne({id,store,remote,guard}){
  for(let retry=0;retry<5;retry++){
   guard();let local=await store.record(id);const localHash=local?await hash(local.data.questions):null;
   const cloud=await remote.read(id,localHash,local?.data.questions);guard();
   if(cloud)local=await store.applyRemote(id,SATCore.validate(cloud.data));
   else local=await store.record(id);
   if(!local)return;
   // applyRemote runs inside an IndexedDB transaction, merging writes made during the pull.
   const sent=structuredClone(local.data);sent.bank.id=id;sent.bank.name=local.name;
   const contentHash=await hash(sent.questions),generation=local.generation||0;
   const {questions,...state}=sent;
   guard();const reply=await remote.put(id,cloud?.revision||0,state,contentHash,contentHash===cloud?.contentHash?null:questions);guard();
   if(!reply.accepted)continue;
   // If another answer was saved during upload, its higher generation remains pending.
   await store.acknowledge(id,generation,reply.revision);return;
  }
  throw Error('Another device is syncing. Your changes are saved here; retry shortly.');
 }
 async function syncAll({store,remote,guard,onBankError}){
  guard();const [locals,ids]=await Promise.all([store.records(),remote.list()]);guard();let failed=false;
  for(const id of new Set([...locals.map(r=>r.id||r.key),...ids])){try{await syncOne({id,store,remote,guard});}catch(e){failed=true;if(onBankError)onBankError(id,e);else throw e;}}
  return {failed,pending:(await store.records()).some(r=>(r.generation||0)>(r.syncedGeneration||0))};
 }
 const api={hash,syncOne,syncAll};root.SATSyncEngine=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
