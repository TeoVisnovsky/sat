/* Google identity + cloud transport. Local practice is independent of this module. */
window.SATCloud=(function(){
 const config=window.SATCloudConfig,controllers=new Set();
 let session=null,client=null,job=null,timer=null,retryDelay=5000,started=false,lastError='',switching=false;
 const profileKey=id=>'sat-profile:'+id;
 async function timedFetch(url,options={}){
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),15000);controllers.add(controller);
  if(options.signal){if(options.signal.aborted)controller.abort();else options.signal.addEventListener('abort',()=>controller.abort(),{once:true});}
  try{return await fetch(url,{...options,signal:controller.signal});}finally{clearTimeout(timeout);controllers.delete(controller);}
 }
 function message(text){const el=document.getElementById('syncNow');if(el){el.textContent=text;el.title=lastError||text;const detail=document.getElementById('syncDetail');if(detail)detail.textContent=lastError||text;}}
 function identityUI(){
  const owner=window.SATOffline?.owner||localStorage.getItem('sat-owner-v1')||'guest';
  const profile=owner==='guest'?null:JSON.parse(localStorage.getItem(profileKey(owner))||'null');
  const email=document.getElementById('accountEmail');if(!email)return;
  email.textContent=profile?.email|| (owner==='guest'?'Practice stays on this device until you sign in.':'Offline account');
  document.getElementById('googleLogin').hidden=!!session&&session.user.id===owner;
  document.getElementById('googleLogout').hidden=owner==='guest';
  document.getElementById('copyLocalProgress').hidden=owner==='guest';
 }
 async function changeOwner(id,email){
  if(switching)return;switching=true;
  try{
   if(typeof flushNotes==='function')await flushNotes();
   if(email)localStorage.setItem(profileKey(id),JSON.stringify({email}));
   localStorage.setItem('sat-owner-v1',id);location.replace(location.pathname);
  }catch(e){lastError=e.message;message('Save your notes before switching accounts');switching=false;}
 }
 try{
  client=supabase.createClient(config.url,config.publishableKey,{auth:{storageKey:'sat-auth-session-v1',flowType:'pkce',persistSession:true,autoRefreshToken:true,detectSessionInUrl:true},global:{fetch:timedFetch}});
  client.auth.onAuthStateChange((event,value)=>{
   session=value;
   // Do not call SDK methods inside its auth callback: they can wait on the same lock.
   setTimeout(()=>{
    if(value){const id=value.user.id;localStorage.setItem(profileKey(id),JSON.stringify({email:value.user.email||'Google account'}));if(id!==(window.SATOffline?.owner||localStorage.getItem('sat-owner-v1')||'guest')){changeOwner(id,value.user.email);return;}}
    identityUI();if(started)schedule(100);
   },0);
  });
 }catch(e){lastError='Sign-in could not start. Reload while connected.';}
 async function login(){
  if(!navigator.onLine)throw Error('Connect to the internet to sign in. You can keep practicing offline.');
  if(!client)throw Error(lastError);
  await flushNotes();
  const {error}=await client.auth.signInWithOAuth({provider:'google',options:{redirectTo:new URL('./',location.href).href,queryParams:{prompt:'select_account'}}});if(error)throw error;
 }
 async function logout(){
  await flushNotes();clearTimeout(timer);for(const c of controllers)c.abort();
  localStorage.setItem('sat-owner-v1','guest');
  try{if(client){await client.auth.stopAutoRefresh();await client.auth.signOut({scope:'local'});}}finally{localStorage.removeItem('sat-auth-session-v1');localStorage.removeItem('sat-auth-session-v1-code-verifier');location.replace(location.pathname);}
 }
 async function authSession(){
  if(!client)throw Error(lastError||'Sign in to sync');
  const {data,error}=await client.auth.getSession();if(error)throw error;
  if(!data.session)throw Error('Sign in to sync');session=data.session;return session;
 }
 function guard(){if(!session||session.user.id!==SATOffline.owner||(localStorage.getItem('sat-owner-v1')||'guest')!==SATOffline.owner)throw Error('Account changed. Sign in again to sync this account.');}
 async function api(path,body){
  guard();const response=await timedFetch(config.url+'/rest/v1/'+path,{method:body===undefined?'GET':'POST',headers:{apikey:config.publishableKey,Authorization:'Bearer '+session.access_token,'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const value=await response.json();guard();
  if(!response.ok){
   if(['PGRST202','PGRST205','42P01'].includes(value.code))throw Error('Cloud setup is not ready yet. Your progress is saved on this device.');
   if(response.status===401)throw Error('Sign in again to sync. Your progress is saved here.');
   throw Error(value.message||'Sync failed. Your progress is saved here.');
  }return value;
 }
 const remote={
  async list(){const rows=await api('sat_cloud_banks?select=bank_id');return rows.map(r=>r.bank_id);},
  async read(id,localHash,localQuestions){
   const filter='bank_id=eq.'+encodeURIComponent(id);
   let rows=await api('sat_cloud_banks?'+filter+'&select=state,content_hash,revision');if(!rows.length)return null;let row=rows[0];
   if(row.content_hash!==localHash){rows=await api('sat_cloud_banks?'+filter+'&select=state,questions,content_hash,revision');if(!rows.length)return null;row=rows[0];}
   return {revision:row.revision,contentHash:row.content_hash,data:{...row.state,questions:row.questions||localQuestions}};
  },
  put(id,revision,state,contentHash,questions){return api('rpc/sat_put_bank',{p_bank_id:id,p_expected_revision:revision,p_state:state,p_content_hash:contentHash,p_questions:questions});}
 };
 function schedule(delay=5000){clearTimeout(timer);timer=setTimeout(()=>sync().catch(()=>{}),delay);}
 async function sync(){
  if(job)return job;
  if(SATOffline.owner==='guest'){message('Saved on device');return;}
  if(!navigator.onLine){message('Offline · saved here');return;}
  job=(async()=>{
   try{
    await flushNotes();await authSession();guard();lastError='';message('Syncing…');
    const result=await SATSyncEngine.syncAll({store:SATOffline,remote,guard,onBankError:(id,e)=>{lastError=e.message;}});
    if(result.failed)throw Error(lastError);
    retryDelay=5000;message(result.pending?'Changes waiting':'Synced');
    window.dispatchEvent(new Event('sat-cloud-updated'));schedule(result.pending?2000:60000);
   }catch(e){lastError=e.name==='AbortError'?'Connection interrupted. Your changes remain saved here.':e.message;message(/sign in/i.test(lastError)?'Sign in to sync':'Sync pending · retry');retryDelay=Math.min(retryDelay*2,60000);schedule(retryDelay);}
   finally{job=null;identityUI();}
  })();return job;
 }
 async function setup(){
  if(started)return;started=true;
  document.getElementById('accountMenu').hidden=false;document.getElementById('syncNow').hidden=false;
  document.getElementById('googleLogin').onclick=safe(login);document.getElementById('googleLogout').onclick=safe(logout);
  document.getElementById('syncNow').onclick=safe(async()=>{if(SATOffline.owner==='guest'||/sign in/i.test(lastError))await login();else await sync();});
  document.getElementById('copyLocalProgress').onclick=safe(async()=>{
   const banks=await SATOffline.guestBanks();document.getElementById('guestBank').innerHTML=banks.map(b=>`<option value="${esc(b.id)}">${esc(b.name)} (${b.attempts} attempts)</option>`).join('');
   document.getElementById('copyDescription').textContent='Copy device-only progress into '+(JSON.parse(localStorage.getItem(profileKey(SATOffline.owner))||'{}').email||'this account')+' → '+document.getElementById('bankSelect').selectedOptions[0].textContent+'. The device-only copy stays available after signing out.';
   document.getElementById('confirmCopy').disabled=!banks.length;document.getElementById('copyDialog').showModal();
  });
  document.getElementById('cancelCopy').onclick=()=>document.getElementById('copyDialog').close();
  document.getElementById('confirmCopy').onclick=safe(async()=>{await flushNotes();await SATOffline.copyGuest(document.getElementById('guestBank').value,bank);document.getElementById('copyDialog').close();location.reload();});
  window.addEventListener('sat-local-change',()=>{message(SATOffline.owner==='guest'?'Saved on device':'Changes waiting');schedule();});
  window.addEventListener('online',()=>schedule(100));window.addEventListener('offline',()=>message('Offline · saved here'));
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')schedule(100);});
  window.addEventListener('storage',e=>{if(e.key==='sat-owner-v1'&&(e.newValue||'guest')!==SATOffline.owner){for(const c of controllers)c.abort();changeOwner(e.newValue||'guest');}});
  identityUI();message(SATOffline.owner==='guest'?'Saved on device':'Changes waiting');schedule(100);
 }
 return {setup,sync,login,logout};
})();
