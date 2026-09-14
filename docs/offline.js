/* IndexedDB transactions serialize edits and merges across tabs. No practice data leaves this device. */
window.SATOffline=(function(){
 let database;
 const open=new Promise((resolve,reject)=>{const r=indexedDB.open('sat-offline-v1',1);r.onupgradeneeded=()=>r.result.createObjectStore('banks',{keyPath:'key'});r.onsuccess=()=>{database=r.result;resolve();};r.onerror=()=>reject(Error('Local storage is unavailable. Open in a normal browser tab, outside private browsing.'));});
 async function transaction(key,write,fn){
  await open;
  return new Promise((resolve,reject)=>{const tx=database.transaction('banks',write?'readwrite':'readonly'),store=tx.objectStore('banks');let result,error;
   const req=key===null?store.getAll():store.get(key);
   req.onsuccess=()=>{try{const out=fn(req.result,store);result=out;}catch(e){error=e;tx.abort();}};
   tx.oncomplete=()=>resolve(result);tx.onerror=tx.onabort=()=>reject(error||Error('Could not save locally. Free some device storage and try again.'));
  });
 }
 const ready=(async()=>{
  if(await transaction('main',false,r=>!!r))return;
  const response=await fetch('./seed.json');if(!response.ok)throw Error('Connect once to download the question bank.');const data=SATCore.validate(await response.json());
  await transaction('main',true,(existing,store)=>{if(!existing){data.bank.id=SATCore.uid();store.put({key:'main',name:'SAT English · original bank',data});}});
 })();
 async function request(bank,path,body){await ready;if(path==='banks')return transaction(null,false,rs=>rs.map(r=>({id:r.key,name:r.name})));return transaction(bank,body!==undefined,(r,store)=>{if(!r)throw Error('Database not found. Choose another database.');const result=SATCore.request(r.data,path,body);if(body!==undefined)store.put(r);return result;});}
 async function importFile(bank,file,mode){
  await ready;if(file.size>50*1024*1024)throw Error('Choose a transfer file under 50 MB');
  let incoming;try{incoming=SATCore.validate(JSON.parse(await file.text()));}catch(e){if(/\.db$|\.sqlite3?$/i.test(file.name))throw Error('On your PC, use Export to turn this SQLite database into a transfer file.');throw e;}
  if(mode==='add'){const key=SATCore.uid();incoming.bank.id=SATCore.uid();return transaction(key,true,(_,store)=>{store.add({key,name:incoming.bank.name,data:incoming});return {id:key};});}
  if(mode!=='merge')throw Error('Choose add or merge');
  return transaction(bank,true,(r,store)=>{if(!r)throw Error('Database not found');const merged=SATCore.merge(r.data,incoming);r.data=merged.data;store.put(r);const {data,...report}=merged;return {id:bank,...report};});
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
  const install=document.getElementById('installApp');install.hidden=false;
  let prompt;
  window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();prompt=e;install.textContent='Install on this device';});
  install.onclick=async()=>{if(navigator.storage?.persist)await navigator.storage.persist();if(prompt){await prompt.prompt();prompt=null;}else{document.getElementById('installHelp').hidden=false;}};
 }
 return {request,importFile,setup,ready};
})();
