/* Local saves never wait for the network. Signed-in accounts have separate namespaces. */
window.SATOffline=(function(){
 let database;
 const owner=localStorage.getItem('sat-owner-v1')||'guest';
 const storageKey=id=>owner==='guest'?id:'user:'+owner+':'+id;
 const belongs=r=>(r.owner||'guest')===owner;
 const changed=()=>window.dispatchEvent(new Event('sat-local-change'));
 function touch(r){r.generation=(r.generation||0)+1;return r;}
 function makeRecord(id,name,data,seedRevision){data.bank.id=id;return {key:storageKey(id),id,owner,name,data,generation:1,syncedGeneration:0,seedRevision};}
 const open=new Promise((resolve,reject)=>{const r=indexedDB.open('sat-offline-v1',1);r.onupgradeneeded=()=>r.result.createObjectStore('banks',{keyPath:'key'});r.onsuccess=()=>{database=r.result;resolve();};r.onerror=()=>reject(Error('Local storage is unavailable. Open in a normal browser tab, outside private browsing.'));});
 async function transaction(key,write,fn){
  await open;
  return new Promise((resolve,reject)=>{const tx=database.transaction('banks',write?'readwrite':'readonly'),store=tx.objectStore('banks');let result,error;
   const req=key===null?store.getAll():store.get(key);
   req.onsuccess=()=>{try{const out=fn(req.result,store);result=out;}catch(e){error=e;tx.abort();}};
   tx.oncomplete=()=>resolve(result);tx.onerror=tx.onabort=()=>reject(error||Error('Could not save locally. Free some device storage and try again.'));
  });
 }
 const seeds=[{id:'main',file:'seed.json',name:'SAT English',revision:'sat-en-v2'},{id:'math',file:'math-seed.json',name:'SAT Math',revision:'sat-math-v2'},{id:'maturita-slovak',file:'maturita-slovak-seed.json',name:'Maturita · Slovenský jazyk a literatúra',revision:'maturita-slovak-v3'},{id:'maturita-math',file:'maturita-math-seed.json',name:'Maturita · Matematika',revision:'maturita-math-v2'}];
 const ready=open;
 async function ensureBank(id){await ready;const seed=seeds.find(s=>s.id===id);if(!seed)return;
  if(await transaction(storageKey(seed.id),true,(r,store)=>{if(!r)return false;const before=SATCore.canonical(r.data);SATCore.validate(r.data);if(SATCore.canonical(r.data)!==before)store.put(touch(r));return r.seedRevision===seed.revision;}))return;
  const response=await fetch('./'+seed.file);if(!response.ok)throw Error('Connect once to download this question bank.');const data=SATCore.validate(await response.json());
  await transaction(storageKey(seed.id),true,(existing,store)=>{if(!existing){store.put(makeRecord(seed.id,seed.name,data,seed.revision));return;}const ids=new Set(data.questions.map(q=>q.id)),questions=new Map(data.questions.map(q=>[q.id,q]));data.attempts=existing.data.attempts.filter(r=>ids.has(r.question_id)).map(r=>({...r,is_correct:+SATCore.answerCorrect(questions.get(r.question_id),r.selected_answer)}));for(const key of ['notes','ratings','reviews','tags'])data[key]=existing.data[key].filter(r=>ids.has(r.question_id));data.test_sessions=existing.data.test_sessions||[];existing.data=SATCore.validate(data);existing.seedRevision=seed.revision;store.put(touch(existing));});
 }
 async function request(bank,path,body){await ready;if(path==='banks')return transaction(null,false,rs=>{const custom=rs.filter(belongs).filter(r=>!seeds.some(s=>s.id===(r.id||r.key))).map(r=>({id:r.id||r.key,name:r.name}));return [...seeds.map(({id,name})=>({id,name})),...custom];});await ensureBank(bank);const result=await transaction(storageKey(bank),body!==undefined,(r,store)=>{if(!r||!belongs(r))throw Error('Database not found. Choose another database.');const result=SATCore.request(r.data,path,body);if(body!==undefined)store.put(touch(r));return result;});if(body!==undefined)changed();return result;}
 async function importFile(bank,file,mode){
  await ready;if(file.size>50*1024*1024)throw Error('Choose a transfer file under 50 MB');
  let incoming;try{incoming=SATCore.validate(JSON.parse(await file.text()));}catch(e){if(/\.db$|\.sqlite3?$/i.test(file.name))throw Error('On your PC, use Export to turn this SQLite database into a transfer file.');throw e;}
  if(mode==='add'){const key=SATCore.uid();const result=await transaction(storageKey(key),true,(_,store)=>{store.add(makeRecord(key,incoming.bank.name,incoming,null));return {id:key};});changed();return result;}
  if(mode!=='merge')throw Error('Choose add or merge');
  const result=await transaction(storageKey(bank),true,(r,store)=>{if(!r||!belongs(r))throw Error('Database not found');const merged=SATCore.merge(r.data,incoming);r.data=merged.data;store.put(touch(r));const {data,...report}=merged;return {id:bank,...report};});changed();return result;
 }
 async function records(){await ready;return transaction(null,false,rs=>rs.filter(belongs));}
 async function record(id){await ready;return transaction(storageKey(id),false,r=>{if(r&&!belongs(r))throw Error('Account changed');return r;});}
 async function applyRemote(id,data){
  await ready;return transaction(storageKey(id),true,(r,store)=>{
   if(!r){r=makeRecord(id,data.bank.name,data,null);store.add(r);return r;}
   if(!belongs(r))throw Error('Account changed');
   const merged=SATCore.merge(r.data,data).data;merged.bank.id=id;
   if(SATCore.canonical(merged)!==SATCore.canonical(r.data)){r.data=merged;store.put(touch(r));}
   return r;
  });
 }
 async function acknowledge(id,generation,revision){return transaction(storageKey(id),true,(r,store)=>{if(!r||!belongs(r))throw Error('Account changed');r.syncedGeneration=Math.max(r.syncedGeneration||0,generation||0);r.cloudRevision=Math.max(r.cloudRevision||0,revision);r.lastSynced=SATCore.now();store.put(r);return r;});}
 async function guestBanks(){return transaction(null,false,rs=>rs.filter(r=>(r.owner||'guest')==='guest').map(r=>({id:r.id||r.key,name:r.name,attempts:r.data.attempts.length})));}
 async function copyGuest(source,target){
  if(owner==='guest')throw Error('Sign in first');
  const data=await transaction(source,false,r=>{if(!r||(r.owner||'guest')!=='guest')throw Error('Device-only bank not found');return r.data;});
  const result=await applyRemote(target,data);changed();return result;
 }
 async function setup(){
  await ready;
  const status=document.getElementById('offlineStatus');status.hidden=false;status.textContent='Preparing offline access…';
  if(!('serviceWorker' in navigator)){status.textContent='Offline installation needs HTTPS and a supported browser.';return;}
  try{const registration=await navigator.serviceWorker.register('./sw.js');await navigator.serviceWorker.ready;status.textContent='Ready offline · saved on this device';
   const offerUpdate=()=>{if(!registration.waiting||document.getElementById('updateApp'))return;const b=document.createElement('button');b.id='updateApp';b.textContent='Update app';status.after(b);b.onclick=async()=>{try{await flushNotes();if(busy)return;navigator.serviceWorker.addEventListener('controllerchange',()=>location.reload(),{once:true});registration.waiting.postMessage('activate-update');}catch(e){status.textContent=e.message;}};};
   offerUpdate();registration.addEventListener('updatefound',()=>{registration.installing?.addEventListener('statechange',offerUpdate);});
  }
  catch(e){status.textContent='Offline setup failed. Reconnect and reload to try again.';}
  const install=document.getElementById('installApp');install.hidden=false;const download=document.getElementById('downloadOfflineBank');download.hidden=false;
  let prompt;
  window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();prompt=e;install.textContent='Install on this device';});
  install.onclick=async()=>{if(navigator.storage?.persist)await navigator.storage.persist();if(prompt){await prompt.prompt();prompt=null;}else{document.getElementById('installHelp').hidden=false;}};
  download.onclick=async()=>{const id=new URLSearchParams(location.search).get('bank')||'main';download.disabled=true;download.textContent='Preparing offline pack…';try{await ensureBank(id);const worker=registration.active||registration.waiting||registration.installing;if(!worker)throw Error('Offline worker is not ready');worker.postMessage({type:'cache-bank',bank:id});}catch(e){download.disabled=false;download.textContent='Download this bank for offline use';status.textContent=e.message;}};
  navigator.serviceWorker.addEventListener('message',e=>{if(e.data?.type!=='cache-bank-progress')return;if(e.data.done){download.disabled=false;if(e.data.failed){download.textContent='Retry offline download';status.textContent=`Offline pack incomplete (${e.data.failed} file${e.data.failed===1?'':'s'} failed). Reconnect and retry.`;}else{download.textContent='Offline pack ready';status.textContent='This bank is ready offline';}}else download.textContent=`Downloading… ${e.data.loaded} / ${e.data.total}`;});
 }
 return {request,importFile,setup,ready,owner,records,record,applyRemote,acknowledge,guestBanks,copyGuest,ensureBank};
})();
