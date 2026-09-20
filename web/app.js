const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bank=new URLSearchParams(location.search).get('bank')||'main';
let selectedAnswer=null;
let meta,questions=[],current=null,answered=false,busy=false,loadVersion=0,listVersion=0;
let noteTimer,searchTimer,toastTimer,noteQueue=Promise.resolve();
const pendingNotes=new Map();
// One tap moves between English and Math; the open bank is always visible in the header.
const SUBJECTS=[{id:'main',label:'English'},{id:'math',label:'Math'}];
const shortName=name=>name.replace(/^SAT\s*/i,'').split('·')[0].trim()||name;
const switchBank=safe(async next=>{
 if(next===bank)return;
 if(busy){$('bankSelect').value=bank;toast('Wait for your answer to finish saving.');return;}
 try{await flushNotes();location.href=location.pathname+'?bank='+encodeURIComponent(next);}
 catch(e){$('bankSelect').value=bank;throw e;}
});
function fillSubjects(banks){
 const items=SUBJECTS.filter(s=>banks.some(b=>b.id===s.id));
 const extra=banks.find(b=>b.id===bank&&!items.some(s=>s.id===b.id));
 if(extra)items.push({id:extra.id,label:shortName(extra.name)});
 const box=$('subjectSwitch');
 box.innerHTML=items.length>1?items.map(s=>`<button type="button" data-bank="${esc(s.id)}"${s.id===bank?' class="active" aria-current="page"':''}>${esc(s.label)}</button>`).join(''):'';
 box.querySelectorAll('[data-bank]').forEach(b=>b.onclick=()=>switchBank(b.dataset.bank));
 document.title='SAT · '+(shortName(banks.find(b=>b.id===bank)?.name||'')||'practice')+' practice';
}
const fillBanks=banks=>{$('bankSelect').innerHTML=banks.map(b=>`<option value="${esc(b.id)}">${esc(b.name)}</option>`).join('');$('bankSelect').value=bank;fillSubjects(banks);};
const noteParents=new Map();
async function api(path,data){
 if(window.SATOffline)return SATOffline.request(bank,path,data);
 const r=await fetch('/api/'+path+(data===undefined?(path.includes('?')?'&':'?')+'bank='+encodeURIComponent(bank):''),data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-SAT-Bank':bank},body:JSON.stringify(data)});
 const value=await r.json();if(!r.ok)throw Error(value.error||'Something went wrong');return value;
}
function fail(e){$('error').textContent=e.message||String(e);$('error').hidden=false;}
function safe(fn){return (...args)=>Promise.resolve(fn(...args)).catch(fail);}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,2300);}
function state(q){return q.needs_review?'review':q.latest_correct===1?'correct':q.latest_correct===0?'incorrect':'unseen';}
function stateLabel(q){return {review:'Needs review',correct:'Correct',incorrect:'Incorrect',unseen:'Unseen'}[state(q)];}
function fillSkills(){const selected=$('skill').value;$('skill').innerHTML='<option value="">All skills</option>'+meta.skills.filter(s=>!$('domain').value||s.domain_id==$('domain').value).map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');$('skill').value=selected;}
function fillTags(){const selected=$('tag').value;$('tag').innerHTML='<option value="">All tags</option>'+meta.tags.map(t=>`<option value="${t.id}">${esc(t.name)}</option>`).join('');$('tag').value=selected;}
function renderList(){
 $('matchCount').textContent=`${questions.length} question${questions.length===1?'':'s'}`;
 $('questionList').innerHTML=questions.map(q=>`<button class="question-row ${current?.id===q.id?'selected':''}" data-id="${q.id}" aria-label="${q.id}, ${esc(q.skill)}, ${stateLabel(q)}"><span class="state-icon ${state(q)}" aria-hidden="true">${{review:'↺',correct:'✓',incorrect:'×',unseen:'○'}[state(q)]}</span><span><strong>${esc(q.skill)}</strong><small>${q.id} · ${q.difficulty}</small></span></button>`).join('')||'<p class="secondary-info">No questions match these filters.</p>';
 $('questionList').querySelectorAll('button').forEach(b=>b.onclick=safe(()=>openQuestion(b.dataset.id)));
}
async function loadList(selectFirst=true){
 const version=++listVersion;const params=new URLSearchParams();for(const key of ['domain','skill','difficulty','status','my_difficulty','tag','search'])if($(key).value)params.set(key,$(key).value);
 const result=await api('questions?'+params);if(version!==listVersion)return;questions=result;renderList();
 if(selectFirst){if(questions.length)await openQuestion(questions[0].id);else{await flushNotes();current=null;++loadVersion;history.replaceState(null,'',location.pathname+location.search);$('workspace').innerHTML='<div class="empty"><h2>Nothing here yet.</h2><p>Try another filter, or come back after a little practice.</p></div>';}}
}
async function stats(){
 const s=await api('stats');$('totalCount').textContent=s.total;$('doneCount').textContent=`${s.done} of ${s.total} completed`;$('completion').max=s.total;$('completion').value=s.done;
 $('statsCards').innerHTML=`<div class="stat"><strong>${s.done}<small class="secondary-info"> / ${s.total}</small></strong><span>Questions completed</span></div><div class="stat"><strong>${s.done?Math.round(100*s.first_correct/s.done)+'%':'—'}</strong><span>First-attempt accuracy</span></div><div class="stat"><strong>${s.review}</strong><span>Need another look</span></div>`;
 $('skillStats').innerHTML=s.skills.map(k=>`<div class="skill-stat"><button data-skill="${k.id}">${esc(k.name)}</button><div><small>${k.done} / ${k.total} completed</small><progress value="${k.done}" max="${k.total}"></progress></div><div class="accuracy">${k.done?Math.round(100*k.correct/k.done)+'%':'—'}<br><small>accuracy</small></div></div>`).join('');
 $('skillStats').querySelectorAll('button').forEach(b=>b.onclick=safe(async()=>{showView(false);$('domain').value='';fillSkills();$('skill').value=b.dataset.skill;for(const k of ['difficulty','status','my_difficulty','tag','search'])$(k).value='';await loadList();}));
}
async function flushNotes(){clearTimeout(noteTimer);await noteQueue;if(pendingNotes.size){const batch=[...pendingNotes];noteQueue=(async()=>{for(const [question_id,content] of batch){const result=await api('note',{question_id,content,parents:noteParents.get(question_id)});if(result.note_parents)noteParents.set(question_id,result.note_parents);if(pendingNotes.get(question_id)===content)pendingNotes.delete(question_id);if(current?.id===question_id&&$('saveStatus'))$('saveStatus').textContent=pendingNotes.has(question_id)?'Saving…':'Saved';}})();try{await noteQueue;}catch(e){noteQueue=Promise.resolve();if($('saveStatus'))$('saveStatus').textContent='Not saved — retry below';throw e;}}}
async function openQuestion(id){
 await flushNotes();const version=++loadVersion;busy=false;answered=false;selectedAnswer=null;$('workspace').setAttribute('aria-busy','true');
 const q=await api('question/'+id);if(version!==loadVersion)return;current=q;noteParents.set(id,q.note_parents);history.replaceState(null,'','#q='+id);renderList();renderQuestion();$('workspace').removeAttribute('aria-busy');
}
function renderQuestion(){
 const q=current;const pos=questions.findIndex(x=>x.id===q.id);
 const answerControl=q.answer_type==='numeric'?`<div class="numeric-answer"><label for="numericAnswer">Your answer</label><input id="numericAnswer" inputmode="decimal" autocomplete="off" placeholder="Enter a number, decimal, or fraction" aria-describedby="numericHelp"><small id="numericHelp">Examples: 12, -3.5, or 2/3</small></div>`:`<div class="choices">${q.choices.map(c=>`<button class="choice" aria-pressed="false" data-letter="${c.letter}"><span class="letter">${c.letter}</span><span>${SATCore.html(c.content_html)}</span></button>`).join('')}</div>`;
 $('workspace').innerHTML=`<div class="question-top"><span>${pos>=0?`${pos+1} of ${questions.length} · `:''}${q.id}</span><div class="question-actions"><button id="copyLink">Copy link</button><button id="reviewToggle">${q.needs_review?'✓ In review':'Mark for review'}</button></div></div>
 <p class="eyebrow">${esc(q.domain)}</p><div class="question-title"><h2>${esc(q.skill)}</h2><span class="badge">${q.difficulty[0].toUpperCase()+q.difficulty.slice(1)}</span><span class="badge" id="stateBadge">${stateLabel(q)}</span></div>
 <div class="passage-text">${SATCore.html(q.passage_html)}</div>
 <details class="transcript" ${q.assets.length?'':'hidden'}><summary>Original PDF passage</summary>${q.assets.map(a=>`<img class="passage-image" src="/${esc(a.file_path)}" alt="${esc(a.alt_text)}">`).join('')}</details>
 <div class="instruction${q.passage_html.trim()?'':' stem'}">${SATCore.html(q.prompt_html)||'Choose the best answer.'}</div>${answerControl}
 <div class="check-row"><label class="confidence"><input type="checkbox" id="guessed"> I am unsure / guessing</label><button id="checkAnswer" class="primary" disabled>Check</button></div><div id="feedback" aria-live="polite"></div>
 <div class="next-row"><span class="secondary-info" id="attemptInfo">${q.attempt_count?`${q.attempt_count} previous attempt${q.attempt_count===1?'':'s'} · answer again to check`:'Not attempted yet'}</span><button id="nextQuestion" class="primary">Next question →</button></div>
 <button id="showNotes" class="text-button">Show notes without answering</button><div id="notesPanel" hidden><div class="notes-heading"><label for="note">Your notes</label><span class="save-status" id="saveStatus">${q.note?'Saved':'Autosaves'}</span></div>
 <textarea id="note" placeholder="What did I miss? What rule or clue will help next time?">${esc(q.note)}</textarea><button class="text-button" id="saveNote">Save now</button></div>
 <label for="personalTags">Personal tags</label><div class="tag-editor"><input id="personalTags" placeholder="comma splice, vocabulary…" value="${esc(q.tags.join(', '))}"><button id="saveTags">Save tags</button></div>
 <details class="history"><summary>Attempt history (${q.history.length}) & source</summary><ul>${q.history.map(h=>`<li>${esc(h.answered_at)} UTC · ${h.selected_answer} · ${h.is_correct?'Correct':'Incorrect'}${h.guessed?' · Guessed':''}</li>`).join('')||'<li>No attempts yet.</li>'}</ul>${q.sources.map(s=>`<p>${esc(s.filename)} · page ${s.page_start}${s.page_end!==s.page_start?'–'+s.page_end:''}</p>`).join('')}</details>`;
 $('workspace').querySelectorAll('.choice').forEach(b=>b.onclick=()=>selectAnswer(b.dataset.letter));
 if(q.answer_type==='numeric'){$('numericAnswer').oninput=()=>{selectedAnswer=$('numericAnswer').value.trim();$('checkAnswer').disabled=!selectedAnswer;};$('numericAnswer').onkeydown=e=>{if(e.key==='Enter'&&!$('checkAnswer').disabled){e.preventDefault();$('checkAnswer').click();}};}
 $('checkAnswer').onclick=safe(()=>answer(selectedAnswer));
 $('showNotes').onclick=()=>{$('notesPanel').hidden=false;$('showNotes').hidden=true;};
 $('note').oninput=()=>{pendingNotes.set(q.id,$('note').value);$('saveStatus').textContent='Saving…';clearTimeout(noteTimer);noteTimer=setTimeout(safe(flushNotes),600);};
 $('saveNote').onclick=safe(flushNotes);
 $('saveTags').onclick=safe(async()=>{await api('tags',{question_id:q.id,tags:$('personalTags').value.split(',').map(x=>x.trim()).filter(Boolean)});meta=await api('meta');fillTags();toast('Tags saved');});
 $('reviewToggle').onclick=safe(async()=>{const value=!q.needs_review;await api('review',{question_id:q.id,needs_review:value});q.needs_review=+value;$('reviewToggle').textContent=value?'✓ In review':'Mark for review';$('stateBadge').textContent=stateLabel(q);await refreshProgress();});
 $('copyLink').onclick=safe(async()=>{await navigator.clipboard.writeText(location.href);toast('Question link copied');});
 $('nextQuestion').onclick=safe(nextQuestion);
}
async function refreshProgress(){await Promise.all([loadList(false),stats()]);}
function selectAnswer(letter){
 if(busy||answered||!current)return;
 selectedAnswer=letter;
 $('workspace').querySelectorAll('.choice').forEach(b=>{const selected=b.dataset.letter===letter;b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',String(selected));});
 $('checkAnswer').disabled=false;
}
async function answer(letter){
 if(busy||answered||!current||!letter)return;busy=true;$('checkAnswer').disabled=true;const qid=current.id;const version=loadVersion;
 $('workspace').querySelectorAll('.choice').forEach(b=>b.disabled=true);if($('numericAnswer'))$('numericAnswer').disabled=true;$('guessed').disabled=true;
 try{
  const result=await api('attempt',{question_id:qid,answer:letter,guessed:$('guessed').checked});
  if(version!==loadVersion){await refreshProgress();return;}answered=true;$('checkAnswer').textContent='Checked';$('notesPanel').hidden=false;$('showNotes').hidden=true;current.needs_review=result.needs_review;current.latest_correct=+result.is_correct;
  $('workspace').querySelectorAll('.choice').forEach(b=>{if(b.dataset.letter===result.correct_answer)b.classList.add('correct');if(b.dataset.letter===letter&&!result.is_correct)b.classList.add('wrong');});
  const correctLabel=current.answer_type==='numeric'?result.correct_answer.split(',').map(x=>x.trim()).filter(Boolean).join(' or '):result.correct_answer;
  $('feedback').innerHTML=`<div class="feedback"><h3>${result.is_correct?'Correct.':`Not quite. The correct answer is ${esc(correctLabel)}.`}</h3><span class="secondary-info">${result.needs_review?'Saved to your review queue.':'Attempt saved.'}</span><details ${result.is_correct?'':'open'}><summary>Why this answer works</summary>${SATCore.html(result.explanation_html)}</details></div>`;
  $('feedback').querySelector('.feedback details').insertAdjacentHTML('beforebegin',`<fieldset class="difficulty-rating"><legend>How did this feel?</legend><div>${['easy','medium','hard'].map(r=>`<button type="button" data-rating="${r}" aria-pressed="${current.my_difficulty===r}">${r[0].toUpperCase()+r.slice(1)}</button>`).join('')}</div><span id="ratingStatus" role="status">${current.my_difficulty?'Previous rating: '+current.my_difficulty+'. Change it if needed.':'Your rating is separate from the official difficulty.'}</span></fieldset>`);
  $('feedback').querySelectorAll('[data-rating]').forEach(b=>b.onclick=safe(async()=>{
   const rating=b.dataset.rating;
   $('feedback').querySelectorAll('[data-rating]').forEach(x=>x.disabled=true);
   try{await api('difficulty',{question_id:qid,rating});if(version!==loadVersion)return;current.my_difficulty=rating;$('feedback').querySelectorAll('[data-rating]').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.rating===rating)));$('ratingStatus').textContent='Saved: '+rating;await refreshProgress();}
   finally{if(version===loadVersion)$('feedback').querySelectorAll('[data-rating]').forEach(x=>x.disabled=false);}
  }));
  $('reviewToggle').textContent=result.needs_review?'✓ In review':'Mark for review';$('stateBadge').textContent=stateLabel(current);$('attemptInfo').textContent='Answer saved';
  const updated=await api('question/'+qid);if(version===loadVersion){current.history=updated.history;current.attempt_count=updated.attempt_count;const history=$('workspace').querySelector('.history');history.querySelector('summary').textContent=`Attempt history (${updated.history.length}) & source`;history.querySelector('ul').innerHTML=updated.history.map(h=>`<li>${esc(h.answered_at)} UTC · ${h.selected_answer} · ${h.is_correct?'Correct':'Incorrect'}${h.guessed?' · Guessed':''}</li>`).join('');}
  await refreshProgress();
 }catch(e){if(version===loadVersion&&!answered){$('workspace').querySelectorAll('.choice').forEach(b=>b.disabled=false);if($('numericAnswer'))$('numericAnswer').disabled=false;$('guessed').disabled=false;$('checkAnswer').disabled=false;}throw e;}finally{if(version===loadVersion)busy=false;}
}
async function nextQuestion(){
 if(busy)return;await flushNotes();const pos=questions.findIndex(q=>q.id===current?.id);let next=pos>=0?questions[pos+1]:questions[0];
 if(!next){if(questions.length>1)next=questions.find(q=>q.id!==current?.id);else if(questions.length===1&&questions[0].id!==current?.id)next=questions[0];}
 if(next){await openQuestion(next.id);if(innerWidth<720)$('workspace').scrollIntoView({behavior:'smooth'});}else toast('You’ve reached the end of this selection. Try another filter.');
}
function showView(progress){$('practiceView').hidden=progress;$('progressView').hidden=!progress;$('progressTab').classList.toggle('active',progress);$('progressTab').textContent=progress?'← Practice':'Progress';}
async function init(){
 document.addEventListener('click',e=>{if(!$('bankMenu').contains(e.target))$('bankMenu').open=false;});
 document.addEventListener('click',e=>{if(!$('accountMenu').contains(e.target))$('accountMenu').open=false;});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('bankMenu').open=false;}});
 const banks=await api('banks');
 fillBanks(banks);
 $('sqliteBackup').href='/api/backup?bank='+encodeURIComponent(bank);$('sqliteBackup').hidden=!!window.SATOffline;
 $('openWebApp').hidden=!!window.SATOffline;
 $('sqliteBackup').onclick=safe(async e=>{e.preventDefault();if(busy){toast('Wait for your answer to finish saving.');return;}await flushNotes();location.href=$('sqliteBackup').href;});
 $('exportBank').onclick=safe(async()=>{if(busy){toast('Wait for your answer to finish saving.');return;}await flushNotes();const data=await api('export');data.bank.name=$('bankSelect').selectedOptions[0].textContent;const blob=new Blob([JSON.stringify(data)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='sat-'+new Date().toISOString().slice(0,10)+'.satbank.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);toast('Export ready. Keep the file for transfer or backup.');});
 $('bankSelect').onchange=()=>switchBank($('bankSelect').value);
 $('uploadBank').onclick=()=>$('bankFile').click();
 let importFile=null,importing=false;
 $('bankFile').onchange=()=>{importFile=$('bankFile').files[0];if(!importFile)return;$('importDescription').textContent=importFile.name+' → '+$('bankSelect').selectedOptions[0].textContent;$('importStatus').textContent='';$('importDialog').showModal();};
 $('cancelImport').onclick=()=>{$('importDialog').close();$('bankFile').value='';importFile=null;};
 $('importDialog').addEventListener('cancel',e=>{if(importing)e.preventDefault();});
 async function importSelected(mode){
  if(!importFile||importing)return;if(busy){toast('Wait for your answer to finish saving.');return;}await flushNotes();importing=true;
  for(const id of ['mergeBank','addBank','cancelImport'])$(id).disabled=true;$('importStatus').textContent='Importing…';
  try{let data;if(window.SATOffline)data=await SATOffline.importFile(bank,importFile,mode);else{const response=await fetch('/api/banks/import',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Filename':encodeURIComponent(importFile.name),'X-Import-Mode':mode,'X-SAT-Bank':bank},body:importFile});data=await response.json();if(!response.ok)throw Error(data.error);}
   sessionStorage.setItem('sat-import-result',mode==='merge'?`Merged: ${data.questions_added} new questions, ${data.attempts_added} new attempts.${data.note_conflicts?' Both note versions kept on '+data.note_conflicts+' question(s). Open notes to review and edit them.':''}`:'Database added.');location.href=location.pathname+'?bank='+encodeURIComponent(data.id);
  }catch(e){$('importStatus').textContent=e.message;}finally{importing=false;for(const id of ['mergeBank','addBank','cancelImport'])$(id).disabled=false;}
 }
 $('mergeBank').onclick=safe(()=>importSelected('merge'));$('addBank').onclick=safe(()=>importSelected('add'));
 if(window.SATOffline)SATOffline.setup().catch(fail);
 $('mobileFilters').onclick=()=>{const open=$('practiceView').classList.toggle('filters-open');$('mobileFilters').setAttribute('aria-expanded',String(open));};
 meta=await api('meta');$('domain').innerHTML+=[...meta.domains].map(d=>`<option value="${d.id}">${esc(d.name)}</option>`).join('');fillSkills();fillTags();
 for(const k of ['domain','skill','difficulty','status','my_difficulty','tag'])$(k).onchange=safe(async()=>{if(k==='domain'){$('skill').value='';fillSkills();}await loadList();});
 $('search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(safe(()=>loadList()),250);};
 $('unseen').onclick=safe(async()=>{$('status').value='unseen';await loadList();});$('mistakes').onclick=safe(async()=>{$('status').value='review';await loadList();});
 $('clear').onclick=safe(async()=>{for(const k of ['domain','skill','difficulty','status','my_difficulty','tag','search'])$(k).value='';fillSkills();await loadList();});
 $('progressTab').onclick=safe(async()=>{if(!$('progressView').hidden){showView(false);return;}await flushNotes();showView(true);await stats();});
 const initial=new URLSearchParams(location.hash.slice(1)).get('q');await loadList(false);await stats();if(initial)await openQuestion(initial);else if(questions.length)await openQuestion(questions[0].id);else $('workspace').innerHTML='<div class="empty"><h2>This bank is empty.</h2><p>Choose another database to start practicing.</p></div>';
 window.addEventListener('hashchange',safe(async()=>{const id=new URLSearchParams(location.hash.slice(1)).get('q');if(id&&id!==current?.id)await openQuestion(id);}));
 window.addEventListener('beforeunload',e=>{if(pendingNotes.size){e.preventDefault();e.returnValue='';}});
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&pendingNotes.size)flushNotes().catch(fail);});
 document.addEventListener('keydown',e=>{if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)||e.ctrlKey||e.metaKey||e.altKey||$('practiceView').hidden)return;if(/^[a-d]$/i.test(e.key)&&current?.answer_type!=='numeric'&&!answered)selectAnswer(e.key.toUpperCase());});
 const imported=sessionStorage.getItem('sat-import-result');if(imported){sessionStorage.removeItem('sat-import-result');$('error').textContent=imported;$('error').classList.add('success');$('error').hidden=false;}
 if(window.SATCloud&&window.SATOffline){
  window.addEventListener('sat-cloud-updated',safe(async()=>{
   const banks=await api('banks');fillBanks(banks);
   meta=await api('meta');fillSkills();fillTags();await refreshProgress();
   if(current){const id=current.id,version=loadVersion,q=await api('question/'+id);if(version!==loadVersion)return;
    if(!pendingNotes.has(id)&&document.activeElement!==$('note')){$('note').value=q.note;noteParents.set(id,q.note_parents);}
    current.my_difficulty=q.my_difficulty;current.needs_review=q.needs_review;
   }
  }));
  await SATCloud.setup();
 }
}
safe(init)();
