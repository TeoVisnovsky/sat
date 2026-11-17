const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bank=new URLSearchParams(location.search).get('bank')||'main';
let selectedAnswer=null;
let meta,questions=[],current=null,answered=false,busy=false,loadVersion=0,listVersion=0;
let noteTimer,searchTimer,toastTimer,noteQueue=Promise.resolve();
const pendingNotes=new Map();
const TEST_KEY='sat-full-test-v3:'+bank;
const readTest=()=>{try{const value=JSON.parse(localStorage.getItem(TEST_KEY));return value&&['active','review'].includes(value.status)?value:null;}catch(e){return null;}};
let fullTest=readTest();
const saveTest=(test=fullTest)=>{if(test)localStorage.setItem(TEST_KEY,JSON.stringify(test));else localStorage.removeItem(TEST_KEY);};
const testEntry=id=>fullTest?.answers?.[id];
const inTest=()=>!!fullTest;
const activeTest=()=>fullTest?.status==='active';
const difficultyLabel=value=>({easy:'Easy',medium:'Medium',hard:'Hard',introductory:'Introductory',standard:'Standard',challenging:'Challenging'})[value]||value;
const shortName=name=>name.replace(/\s*·\s*(original|fresh) bank$/i,'').trim()||name;
const switchBank=safe(async next=>{
 if(next===bank)return;
 if(busy){$('bankSelect').value=bank;toast('Wait for your answer to finish saving.');return;}
 try{await flushNotes();location.href=location.pathname+'?bank='+encodeURIComponent(next);}
 catch(e){$('bankSelect').value=bank;throw e;}
});
const fillBanks=banks=>{const name=shortName(banks.find(b=>b.id===bank)?.name||'Question bank');$('bankSelect').innerHTML=banks.map(b=>`<option value="${esc(b.id)}">${esc(shortName(b.name))}</option>`).join('');$('bankSelect').value=bank;$('currentBankName').textContent=name;document.title=name+' · Practice';};
const noteParents=new Map();
async function api(path,data){
 if(window.SATOffline)return SATOffline.request(bank,path,data);
 const r=await fetch('/api/'+path+(data===undefined?(path.includes('?')?'&':'?')+'bank='+encodeURIComponent(bank):''),data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-SAT-Bank':bank},body:JSON.stringify(data)});
 const value=await r.json();if(!r.ok)throw Error(value.error||'Something went wrong');return value;
}
function fail(e){$('error').textContent=e.message||String(e);$('error').hidden=false;}
function safe(fn){return (...args)=>Promise.resolve(fn(...args)).catch(fail);}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,2300);}
function state(q){if(activeTest()){const entry=testEntry(q.id);return invalidTestDraft(entry)?'test-incomplete':entry?.flagged?'test-flagged':entry?.answer?'test-done':'unseen';}if(fullTest?.status==='review')return fullTest.results?.[q.id]?.is_correct?'correct':fullTest.results?.[q.id]?'incorrect':'blank';return q.needs_review?'review':q.latest_correct===1?'correct':q.latest_correct===0?'incorrect':'unseen';}
function stateLabel(q){return {review:'Needs review',correct:'Correct',incorrect:'Incorrect',blank:'Left blank',unseen:activeTest()?'Not answered':'Unseen','test-done':'Answered','test-flagged':'Flagged','test-incomplete':'Needs a valid number'}[state(q)];}
function fillSkills(){const selected=$('skill').value,domain=$('domain').value,skills=domain?meta.skills.filter(s=>s.domain_id==domain):[...new Map(meta.skills.map(s=>[s.name,s])).values()];$('skill').innerHTML='<option value="">All skills</option>'+skills.map(s=>`<option value="${domain?s.id:'name:'+s.name}">${esc(s.name)}</option>`).join('');$('skill').value=[...$('skill').options].some(o=>o.value===selected)?selected:'';}
function fillTags(){const selected=$('tag').value;$('tag').innerHTML='<option value="">All tags</option>'+meta.tags.map(t=>`<option value="${t.id}">${esc(t.name)}</option>`).join('');$('tag').value=selected;}
const filterControls=['sideYear','domain','skill','difficulty','status','my_difficulty','tag','answer_type','text_mode','section'];
function renderActiveFilters(){
 const labels=[];for(const id of filterControls){const el=$(id);if(el&&!el.hidden&&el.value)labels.push({id,label:el.selectedOptions?.[0]?.textContent||el.value});}
 if($('search').value.trim())labels.push({id:'search',label:'Search: '+$('search').value.trim()});if($('shuffle').checked)labels.push({id:'shuffle',label:'Shuffled'});
 $('activeFilters').innerHTML=labels.map(x=>`<button class="active-filter" data-filter="${x.id}" title="Remove filter">${esc(x.label)} ×</button>`).join('');
 $('activeFilters').querySelectorAll('button').forEach(button=>button.onclick=safe(async()=>{const id=button.dataset.filter;if(id==='shuffle')$('shuffle').checked=false;else $(id).value='';if(id==='domain'){ $('skill').value='';fillSkills();}await loadList();}));
}
function listTitle(q){return meta.is_maturita?(q.subcategory||q.domain):q.skill;}
function renderList(){
 $('matchCount').textContent=`${questions.length} question${questions.length===1?'':'s'}`;
 $('questionList').innerHTML=questions.map(q=>`<button class="question-row ${current?.id===q.id?'selected':''}" data-id="${q.id}" aria-label="${q.id}, ${esc(listTitle(q))}, ${stateLabel(q)}"><span class="state-icon ${state(q)}" aria-hidden="true">${{review:'↺',correct:'✓',incorrect:'×',blank:'—',unseen:'○','test-done':'●','test-flagged':'⚑','test-incomplete':'!'}[state(q)]}</span><span><strong class="row-title">${esc(listTitle(q))}</strong>${meta.is_maturita?`<span class="row-category">${esc(q.domain)}</span>`:''}<small>${meta.is_maturita?`${q.year} · Question ${q.ordinal}${meta.is_slovak?` · Section ${Math.floor((q.ordinal-1)/8)+1}`:''}`:`${q.id} · ${difficultyLabel(q.difficulty)}`}</small></span></button>`).join('')||'<p class="secondary-info">No questions match these filters.</p>';
 $('questionList').querySelectorAll('button').forEach(b=>b.onclick=safe(()=>openQuestion(b.dataset.id)));
 renderActiveFilters();$('mobileQuestionState').textContent=current?`${Math.max(1,questions.findIndex(q=>q.id===current.id)+1)} / ${questions.length}`:`${questions.length}`;
}
async function loadList(selectFirst=true){
 const version=++listVersion;const params=new URLSearchParams();for(const key of ['domain','skill','difficulty','status','my_difficulty','tag','search','answer_type','text_mode','section'])if($(key)&&$(key).value){const value=$(key).value;if(key==='skill'&&value.startsWith('name:'))params.set('skill_name',value.slice(5));else params.set(key,value);}if($('sideYear')?.value)params.set('year',$('sideYear').value);if(inTest()){params.set('year',fullTest.year);params.delete('section');params.delete('status');params.delete('difficulty');params.delete('my_difficulty');params.delete('tag');}if($('shuffle')?.checked&&!inTest())params.set('shuffle','1');
 const result=await api('questions?'+params);if(version!==listVersion)return;questions=result;renderList();
 if(selectFirst){if(questions.length)await openQuestion(questions[0].id);else{await flushNotes();current=null;++loadVersion;history.replaceState(null,'',location.pathname+location.search);$('workspace').innerHTML='<div class="empty"><h2>Nothing here yet.</h2><p>Try another filter, or come back after a little practice.</p></div>';}}
}
async function stats(){
 const s=await api('stats');$('totalCount').textContent=s.total;$('doneCount').textContent=`${s.done} of ${s.total} completed`;$('completion').max=s.total;$('completion').value=s.done;
 $('statsCards').innerHTML=`<div class="stat"><strong>${s.done}<small class="secondary-info"> / ${s.total}</small></strong><span>Questions completed</span></div><div class="stat"><strong>${s.done?Math.round(100*s.first_correct/s.done)+'%':'—'}</strong><span>First-attempt accuracy</span></div><div class="stat"><strong>${s.review}</strong><span>Need another look</span></div><div class="stat"><strong>${s.average_ms==null?'—':Timers.clock(s.average_ms)}</strong><span>Average per question${s.timed?` · ${s.timed} timed`:''}</span></div>`;
 const tests=s.tests||[];$('testHistory').hidden=!tests.length;$('testHistoryRows').innerHTML=tests.map(t=>`<div class="test-history-row"><span><strong>${t.year}</strong><small>${t.timed?'Timed':'Untimed'} · ${new Date(t.submitted_at).toLocaleDateString()}</small></span><span>${t.score} / ${t.total}</span><span>${Timers.clock(t.elapsed_ms)}</span></div>`).join('');
 const byCategory=meta.is_maturita&&Array.isArray(s.categories),rows=byCategory?s.categories:s.skills;$('progressBreakdownTitle').textContent=byCategory?'Progress by category':'Progress by skill';
 $('skillStats').innerHTML=rows.map(k=>`<div class="skill-stat"><button data-${byCategory?'domain':'skill'}="${k.id}">${esc(k.name)}</button><div><small>${k.done} / ${k.total} completed</small><progress value="${k.done}" max="${k.total}"></progress></div><div class="accuracy">${k.done?Math.round(100*k.correct/k.done)+'%':'—'}<br><small>accuracy</small></div><div class="accuracy">${k.average_ms==null?'—':Timers.clock(k.average_ms)}<br><small>average</small></div></div>`).join('');
 $('skillStats').querySelectorAll('button').forEach(b=>b.onclick=safe(async()=>{showView(false);for(const k of ['difficulty','status','my_difficulty','tag','search'])$(k).value='';if(byCategory){$('domain').value=b.dataset.domain;$('skill').value='';fillSkills();}else{$('domain').value='';fillSkills();$('skill').value=b.dataset.skill;}await loadList();}));
}
async function flushNotes(){clearTimeout(noteTimer);await noteQueue;if(pendingNotes.size){const batch=[...pendingNotes];noteQueue=(async()=>{for(const [question_id,content] of batch){const result=await api('note',{question_id,content,parents:noteParents.get(question_id)});if(result.note_parents)noteParents.set(question_id,result.note_parents);if(pendingNotes.get(question_id)===content)pendingNotes.delete(question_id);if(current?.id===question_id&&$('saveStatus'))$('saveStatus').textContent=pendingNotes.has(question_id)?'Saving…':'Saved';}})();try{await noteQueue;}catch(e){noteQueue=Promise.resolve();if($('saveStatus'))$('saveStatus').textContent='Not saved — retry below';throw e;}}}
async function openQuestion(id){
 await flushNotes();const version=++loadVersion;busy=false;$('workspace').setAttribute('aria-busy','true');
 const q=await api('question/'+id);if(version!==loadVersion)return;current=q;answered=false;selectedAnswer=null;noteParents.set(id,q.note_parents);history.replaceState(null,'','#q='+id);renderList();renderQuestion();$('workspace').removeAttribute('aria-busy');
 if(innerWidth<720){$('practiceView').classList.remove('filters-open');$('mobileFilters').setAttribute('aria-expanded','false');$('drawerBackdrop').hidden=true;}
}
function renderQuestion(){
 const q=current;const pos=questions.findIndex(x=>x.id===q.id);
 const examEntry=testEntry(q.id),reviewing=fullTest?.status==='review',testing=activeTest();
 const answerControl=q.answer_type==='choice'?`<div class="choices">${q.choices.map(c=>`<button class="choice" aria-pressed="false" data-letter="${c.letter}"><span class="letter">${c.letter}</span><span>${SATCore.html(c.content_html)}</span></button>`).join('')}</div>`:`<div class="numeric-answer"><label for="numericAnswer">${q.answer_type==='text'?'Your short answer':'Your answer'}</label><input id="numericAnswer" ${testing?'maxlength="500"':''} ${q.answer_type==='numeric'?'inputmode="decimal"':''} autocomplete="off" placeholder="${q.answer_type==='text'?'Type the answer':'Enter a number, decimal, or fraction'}" aria-describedby="numericHelp"><small id="numericHelp">${q.answer_type==='text'?(testing?'Your answer saves as you type.':'The official rubric checks common accepted forms. You can override a strict mismatch after checking.'):'Examples: 12, -3.5, 3,5, or 2/3'}</small></div>`;
 const metadata=meta.is_maturita?'':`<p class="eyebrow">${esc(q.domain)}</p><div class="question-title"><h2>${esc(q.skill)}</h2><span class="badge">${difficultyLabel(q.difficulty)}</span></div>`;
 const passage=q.passage_html?(q.requires_stimulus?`<div class="passage-text">${SATCore.html(q.passage_html)}</div>`:`<details class="optional-passage" open><summary>Source passage · optional for this question</summary><div class="passage-text">${SATCore.html(q.passage_html)}</div></details>`):'';
 $('workspace').classList.toggle('test-review',reviewing);
 $('workspace').innerHTML=`<div class="question-top"><span>${pos>=0?`${pos+1} of ${questions.length} · `:''}${meta.is_maturita?`${q.year} · Question ${q.ordinal}`:q.id}</span><div class="question-actions"><details class="question-action-menu"><summary aria-label="Question actions">•••</summary><div><button id="copyLink">Copy link</button><button id="reviewToggle" ${inTest()?'hidden':''}>${q.needs_review?'✓ In review':'Mark for review'}</button><button id="flagTest" class="test-flag" ${inTest()?'':'hidden'} aria-pressed="${!!examEntry?.flagged}">${examEntry?.flagged?'✓ Flagged':'Flag for review'}</button></div></details></div></div>
 ${metadata}<span class="badge" id="stateBadge">${stateLabel(q)}</span>
 ${passage}
 <details class="transcript" ${q.assets.length?'':'hidden'}><summary>Original PDF passage</summary>${q.assets.map(a=>`<img class="passage-image" src="/${esc(a.file_path)}" alt="${esc(a.alt_text)}">`).join('')}</details>
 <div class="instruction${q.passage_html.trim()?'':' stem'}">${SATCore.html(q.prompt_html)||'Choose the best answer.'}</div>${answerControl}
 <div class="check-row" ${reviewing?'hidden':''}><label class="confidence"><input type="checkbox" id="guessed"> I am unsure / guessing</label>${inTest()?'':'<button id="checkAnswer" class="primary" disabled>Check</button>'}</div><div id="feedback" aria-live="polite"></div>
 <div class="next-row"><span class="secondary-info" id="attemptInfo" ${testing?'role="status"':''}>${testing?testAnswerMessage(examEntry):reviewing?'Test submitted · review your result':q.attempt_count?`${q.attempt_count} previous attempt${q.attempt_count===1?'':'s'} · answer again to check`:'Not attempted yet'}</span><button id="nextQuestion" class="primary">Next question →</button></div>
 <div ${inTest()?'hidden':''}><button id="showNotes" class="text-button">Show notes without answering</button><div id="notesPanel" hidden><div class="notes-heading"><label for="note">Your notes</label><span class="save-status" id="saveStatus">${q.note?'Saved':'Autosaves'}</span></div>
 <textarea id="note" placeholder="What did I miss? What rule or clue will help next time?">${esc(q.note)}</textarea><button class="text-button" id="saveNote">Save now</button></div>
 <details class="question-details"><summary>Question details</summary><div class="revealed-metadata"><span class="badge">${esc(q.domain)}</span><span class="badge">${esc(q.skill)}</span>${meta.is_slovak?`<span class="badge">Section ${Math.floor((q.ordinal-1)/8)+1}</span>`:''}</div><div id="personalTagEditor" ${meta.is_maturita?'hidden':''}><label for="personalTags">Personal tags</label><div class="tag-editor"><input id="personalTags" placeholder="comma splice, vocabulary…" value="${esc(q.tags.join(', '))}"><button id="saveTags">Save tags</button></div></div><div class="history"><strong>Attempt history (${q.history.length})</strong><ul>${q.history.map(h=>`<li>${esc(h.answered_at)} UTC · ${h.selected_answer} · ${h.is_correct?'Correct':'Incorrect'}${h.guessed?' · Guessed':''}${h.elapsed_ms==null?'':' · '+Timers.clock(h.elapsed_ms)}</li>`).join('')||'<li>No attempts yet.</li>'}</ul>${q.sources.map(s=>`<p>${esc(s.filename)} · page ${s.page_start}${s.page_end!==s.page_start?'–'+s.page_end:''}</p>`).join('')}</div></details></div>`;
 Timers.startQuestion(q.id);
 $('workspace').querySelectorAll('.choice').forEach(b=>b.onclick=()=>selectAnswer(b.dataset.letter));
 if(q.answer_type!=='choice'&&!reviewing){const input=$('numericAnswer');input.oninput=()=>{if(testing)saveTestAnswer(input.value);else{selectedAnswer=input.value.trim();$('checkAnswer').disabled=!selectedAnswer;}};input.onkeydown=e=>{if(e.key!=='Enter'||e.isComposing)return;if(testing&&testEntry(q.id)?.answer){e.preventDefault();$('nextQuestion').click();}else if(!testing&&!$('checkAnswer').disabled){e.preventDefault();$('checkAnswer').click();}};}
 if(testing)$('guessed').onchange=()=>saveTestAnswer();
 if(!inTest()){
  $('checkAnswer').onclick=safe(()=>answer(selectedAnswer));
  $('showNotes').onclick=()=>{$('notesPanel').hidden=false;$('showNotes').hidden=true;};
  $('note').oninput=()=>{pendingNotes.set(q.id,$('note').value);$('saveStatus').textContent='Saving…';clearTimeout(noteTimer);noteTimer=setTimeout(safe(flushNotes),600);};
  $('saveNote').onclick=safe(flushNotes);
  if(!meta.is_maturita)$('saveTags').onclick=safe(async()=>{await api('tags',{question_id:q.id,tags:$('personalTags').value.split(',').map(x=>x.trim()).filter(Boolean)});meta=await api('meta');fillTags();toast('Tags saved');});
  $('reviewToggle').onclick=safe(async()=>{const value=!q.needs_review;await api('review',{question_id:q.id,needs_review:value});q.needs_review=+value;$('reviewToggle').textContent=value?'✓ In review':'Mark for review';$('stateBadge').textContent=stateLabel(q);await refreshProgress();});
 }
 $('copyLink').onclick=safe(async()=>{await navigator.clipboard.writeText(location.href);toast('Question link copied');});
 if(inTest())$('flagTest').onclick=()=>{const entry=testEntry(q.id)||{};entry.flagged=!entry.flagged;fullTest.answers[q.id]=entry;saveTest();$('flagTest').setAttribute('aria-pressed',String(entry.flagged));$('flagTest').textContent=entry.flagged?'✓ Flagged':'Flag for review';$('stateBadge').textContent=stateLabel(q);renderList();};
 $('nextQuestion').onclick=safe(nextQuestion);
 if(examEntry){selectedAnswer=examEntry.answer||null;$('guessed').checked=!!examEntry.guessed;if(q.answer_type==='choice')$('workspace').querySelectorAll('.choice').forEach(b=>{const selected=b.dataset.letter===selectedAnswer;b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',String(selected));});else $('numericAnswer').value=examEntry.draft??examEntry.answer??'';}
 if(reviewing)showTestResult(q,fullTest.results?.[q.id]);
}
async function refreshProgress(){await Promise.all([loadList(false),stats()]);}
function selectAnswer(letter){
 if(busy||answered||!current||inTest()&&!activeTest())return;
 selectedAnswer=letter;
 $('workspace').querySelectorAll('.choice').forEach(b=>{const selected=b.dataset.letter===letter;b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',String(selected));});
 if(activeTest())saveTestAnswer(letter);else $('checkAnswer').disabled=false;
}
function updateTestUI(){
 const bar=$('testModeBar');if(!bar)return;bar.hidden=!inTest();
 $('practiceView').classList.toggle('test-active',inTest());
 $('filterPanel').hidden=inTest();
 $('fullTestSetup').hidden=inTest();$('activeTestCard').hidden=!inTest();
 if(!inTest())return;
 const done=Object.values(fullTest.answers||{}).filter(entry=>entry.answer).length,total=questions.length||fullTest.total||0;
 if(activeTest())Timers.setAnswerCount(done);
 $('testModeProgress').textContent=fullTest.status==='active'?`Full test · ${done}/${total} answered`:`Results · ${fullTest.score}/${fullTest.total} correct`;
 $('activeTestTitle').textContent=`${fullTest.year} · ${total} questions`;$('activeTestProgress').textContent=fullTest.status==='active'?`${done} answered · ${Math.max(0,total-done)} remaining`:`${fullTest.score} of ${fullTest.total} correct`;
 $('submitFullTest').textContent=fullTest.status==='active'?'Finish test':'Exit review';
 $('submitFullTestMenu').textContent=fullTest.status==='active'?'Finish and submit test':'Exit test review';
 const finish=fullTest.status==='active'?openSubmitDialog:exitTestReview;
 $('submitFullTest').onclick=$('submitFullTestMenu').onclick=safe(finish);
}
async function openSubmitDialog(){
 if(!activeTest()||busy)return;const invalid=questions.find(q=>invalidTestDraft(testEntry(q.id)));
 if(invalid){$('testMenu').open=false;showView(false);if(current?.id!==invalid.id)await openQuestion(invalid.id);$('numericAnswer')?.focus();toast('Fix or clear this answer before submitting.');return;}
 const done=Object.values(fullTest.answers||{}).filter(entry=>entry.answer).length,total=questions.length||fullTest.total||0,missing=Math.max(0,total-done);
 $('submitTestDescription').textContent=`${done} of ${total} questions answered${missing?` · ${missing} left blank`:''}.`;$('submitTestDialog').showModal();
}
async function exitTestReview(){fullTest=null;saveTest();updateTestUI();await loadList();toast('Test review closed.');}
const invalidTestDraft=entry=>!entry?.answer&&!!entry?.draft?.trim();
const testAnswerMessage=entry=>invalidTestDraft(entry)?'Enter a number, decimal, or fraction':entry?.answer?'Answer saved':'Answers save automatically';
function saveTestAnswer(draft){
 if(!activeTest()||busy||!current||current.year!==fullTest.year)return;
 const previous=testEntry(current.id)||{},entry={...previous,guessed:$('guessed').checked};
 if(draft!==undefined){
  let answer=draft.trim();
  if(current.answer_type==='numeric'&&answer){
   answer=answer.replace(/\s+/g,'').replace(/−/g,'-').replace(/^([+-]?)(\d+)\/([+-])(\d+)$/,(_,nSign,n,dSign,d)=>((nSign==='-')!==(dSign==='-')?'-':'')+n+'/'+d);
   if(!SATCore.numeric(answer))answer='';
  }
  entry.answer=answer;
  if(draft!==answer)entry.draft=draft;else delete entry.draft;
  if(previous.answer!==answer)entry.elapsed_ms=answer?Timers.questionElapsed():null;
 }
 const test={...fullTest,answers:{...fullTest.answers,[current.id]:entry}};
 try{saveTest(test);}catch(e){$('attemptInfo').textContent='Could not save this answer on this device';fail(e);return;}
 fullTest=test;
 const status=$('attemptInfo'),message=testAnswerMessage(entry);if(status.textContent!==message)status.textContent=message;
 if(!!previous.answer!==!!entry.answer||invalidTestDraft(previous)!==invalidTestDraft(entry)){$('stateBadge').textContent=stateLabel(current);renderList();updateTestUI();}
}
function showTestResult(q,result){
 const entry=testEntry(q.id);$('workspace').querySelectorAll('.choice').forEach(b=>{b.disabled=true;if(result&&b.dataset.letter===result.correct_answer)b.classList.add('correct');if(entry&&b.dataset.letter===entry.answer&&!result?.is_correct)b.classList.add('wrong');});
 if($('numericAnswer'))$('numericAnswer').disabled=true;
 if(!result){$('feedback').innerHTML='<div class="feedback"><h3>Not answered.</h3><p>This question was left blank when the test was submitted.</p></div>';return;}
 $('feedback').innerHTML=`<div class="feedback"><h3>${result.is_correct?'Correct.':`Not quite. The correct answer is ${esc(result.correct_answer)}.`}</h3><details ${result.is_correct?'':'open'}><summary>Why this answer works</summary>${SATCore.html(result.explanation_html)}</details></div>`;
}
function renderTestResultsOverview(){
 if(fullTest?.status!=='review')return;current=null;renderList();history.replaceState(null,'',location.pathname+location.search);
 const total=fullTest.total||questions.length,answeredCount=fullTest.answered||0,blank=total-answeredCount,elapsed=fullTest.elapsed_ms||0;
 const groups=new Map();for(const q of questions){const name=meta.is_slovak?`Section ${Math.floor((q.ordinal-1)/8)+1}`:q.domain;const item=groups.get(name)||{total:0,correct:0};item.total++;item.correct+=+!!fullTest.results?.[q.id]?.is_correct;groups.set(name,item);}
 $('workspace').innerHTML=`<div class="test-results"><div class="test-results-header"><p class="eyebrow">${fullTest.year} FULL TEST</p><h1>${fullTest.score} of ${total} correct</h1><p class="secondary-info">Answers are now available for review.</p></div><div class="result-summary"><div><strong>${fullTest.score}</strong><span>Correct</span></div><div><strong>${answeredCount-fullTest.score}</strong><span>Incorrect</span></div><div><strong>${blank}</strong><span>Blank</span></div><div><strong>${Timers.clock(elapsed)}</strong><span>Time</span></div></div><h2>Breakdown</h2><div class="result-breakdown">${[...groups].map(([name,item])=>`<div class="result-breakdown-row"><span>${esc(name)}</span><strong>${item.correct} / ${item.total}</strong><progress value="${item.correct}" max="${item.total}"></progress></div>`).join('')}</div><div class="result-actions"><button id="reviewIncorrect">Review incorrect and blank</button><button id="reviewAll">Review all questions</button><button id="closeTestReview">Close results</button></div></div>`;
 const openFirst=list=>{const q=list[0];if(q)openQuestion(q.id);else toast('No questions in this group.');};
 $('reviewIncorrect').onclick=()=>openFirst(questions.filter(q=>!fullTest.results?.[q.id]?.is_correct));$('reviewAll').onclick=()=>openFirst(questions);$('closeTestReview').onclick=safe(exitTestReview);
}
async function submitTest(){
 if(!activeTest()||busy)return;busy=true;$('confirmSubmitTest').disabled=true;$('cancelSubmitTest').disabled=true;
 try{
  const elapsed=Timers.finishExam(),payload={session_id:fullTest.id,year:fullTest.year,timed:!!fullTest.timed,started_at:fullTest.started_at,elapsed_ms:elapsed,total:questions.length,answers:Object.entries(fullTest.answers||{}).filter(([,entry])=>entry.answer).map(([question_id,entry])=>({question_id,answer:entry.answer,guessed:!!entry.guessed,elapsed_ms:entry.elapsed_ms}))};
  const submitted=await api('test-submit',payload);fullTest.status='review';fullTest.results=submitted.results;fullTest.score=submitted.score;fullTest.answered=submitted.answered;fullTest.total=submitted.total;fullTest.elapsed_ms=submitted.elapsed_ms;saveTest();$('submitTestDialog').close();updateTestUI();await loadList(false);await stats();renderTestResultsOverview();toast(`Test submitted · ${fullTest.score}/${fullTest.total} correct.`);
 }finally{busy=false;$('confirmSubmitTest').disabled=false;$('cancelSubmitTest').disabled=false;}
}
async function answer(letter){
 if(busy||answered||!current||!letter)return;busy=true;$('checkAnswer').disabled=true;const qid=current.id;const version=loadVersion;
 $('workspace').querySelectorAll('.choice').forEach(b=>b.disabled=true);if($('numericAnswer'))$('numericAnswer').disabled=true;$('guessed').disabled=true;
 try{
  const spent=Timers.stopQuestion();
  const result=await api('attempt',{question_id:qid,answer:letter,guessed:$('guessed').checked,elapsed_ms:spent});
  Timers.countAnswer();
  if(version!==loadVersion){await refreshProgress();return;}answered=true;$('checkAnswer').textContent='Checked';$('notesPanel').hidden=false;$('showNotes').hidden=true;current.needs_review=result.needs_review;current.latest_correct=+result.is_correct;
  $('workspace').querySelectorAll('.choice').forEach(b=>{if(b.dataset.letter===result.correct_answer)b.classList.add('correct');if(b.dataset.letter===letter&&!result.is_correct)b.classList.add('wrong');});
  const correctLabel=current.answer_type==='choice'?result.correct_answer:result.correct_answer;
  $('feedback').innerHTML=`<div class="feedback"><h3>${result.is_correct?'Correct.':`Not quite. The correct answer is ${esc(correctLabel)}.`}</h3><span class="secondary-info">${spent===null?'':'Answered in '+Timers.clock(spent)+' · '}${result.needs_review?'Saved to your review queue.':'Attempt saved.'}</span><details ${result.is_correct?'':'open'}><summary>Why this answer works</summary>${SATCore.html(result.explanation_html)}</details></div>`;
  if(current.answer_type==='text'&&!result.is_correct){const button=document.createElement('button');button.type='button';button.id='acceptMyAnswer';button.textContent='My answer should count as correct';$('feedback').querySelector('.feedback').append(button);button.onclick=safe(async()=>{await api('attempt-override',{question_id:qid,attempt_id:result.attempt_id});button.disabled=true;button.textContent='Marked correct';current.needs_review=0;current.latest_correct=1;$('reviewToggle').textContent='Mark for review';$('stateBadge').textContent='Correct';await refreshProgress();});}
  $('feedback').querySelector('.feedback details').insertAdjacentHTML('beforebegin',`<fieldset class="difficulty-rating"><legend>How did this feel?</legend><div>${['easy','medium','hard'].map(r=>`<button type="button" data-rating="${r}" aria-pressed="${current.my_difficulty===r}">${r[0].toUpperCase()+r.slice(1)}</button>`).join('')}</div><span id="ratingStatus" role="status">${current.my_difficulty?'Previous rating: '+current.my_difficulty+'. Change it if needed.':'Your rating is separate from the official difficulty.'}</span></fieldset>`);
  $('feedback').querySelectorAll('[data-rating]').forEach(b=>b.onclick=safe(async()=>{
   const rating=b.dataset.rating;
   $('feedback').querySelectorAll('[data-rating]').forEach(x=>x.disabled=true);
   try{await api('difficulty',{question_id:qid,rating});if(version!==loadVersion)return;current.my_difficulty=rating;$('feedback').querySelectorAll('[data-rating]').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.rating===rating)));$('ratingStatus').textContent='Saved: '+rating;await refreshProgress();}
   finally{if(version===loadVersion)$('feedback').querySelectorAll('[data-rating]').forEach(x=>x.disabled=false);}
  }));
  $('reviewToggle').textContent=result.needs_review?'✓ In review':'Mark for review';$('stateBadge').textContent=stateLabel(current);$('attemptInfo').textContent='Answer saved';
  const updated=await api('question/'+qid);if(version===loadVersion){current.history=updated.history;current.attempt_count=updated.attempt_count;const history=$('workspace').querySelector('.history');history.querySelector('strong').textContent=`Attempt history (${updated.history.length})`;history.querySelector('ul').innerHTML=updated.history.map(h=>`<li>${esc(h.answered_at)} UTC · ${h.selected_answer} · ${h.is_correct?'Correct':'Incorrect'}${h.guessed?' · Guessed':''}${h.elapsed_ms==null?'':' · '+Timers.clock(h.elapsed_ms)}</li>`).join('');}
  await refreshProgress();
 }catch(e){if(version===loadVersion&&!answered){$('workspace').querySelectorAll('.choice').forEach(b=>b.disabled=false);if($('numericAnswer'))$('numericAnswer').disabled=false;$('guessed').disabled=false;$('checkAnswer').disabled=false;}throw e;}finally{if(version===loadVersion)busy=false;}
}
async function nextQuestion(){
 if(busy)return;await flushNotes();const pos=questions.findIndex(q=>q.id===current?.id);let next=pos>=0?questions[pos+1]:questions[0];
 if(!next){if(questions.length>1)next=questions.find(q=>q.id!==current?.id);else if(questions.length===1&&questions[0].id!==current?.id)next=questions[0];}
 if(next){await openQuestion(next.id);if(innerWidth<720)$('workspace').scrollIntoView({behavior:'smooth'});}else toast('You’ve reached the end of this selection. Try another filter.');
}
/* Timers. A per-question stopwatch with a pace bar, plus a set timer that spans questions.
   Both survive reloads (switching banks reloads the page), pause when the tab is hidden, and
   never count time while the app was closed: each tick records when it was last seen alive. */
const Timers=(function(){
 const QKEY='sat-question-timer-v1:'+bank,PACE_KEY='sat-pace-v1:'+bank,SKEY='sat-set-timer-v1';
 const DEFAULTS={main:{minutes:64,questions:54},math:{minutes:70,questions:44},'maturita-slovak':{minutes:100,questions:64},'maturita-math':{minutes:150,questions:30}};
 const fallback=()=>DEFAULTS[bank]||DEFAULTS.main;
 const read=(k,f)=>{try{const v=JSON.parse(localStorage.getItem(k));return v&&typeof v==='object'?v:f;}catch(e){return f;}};
 const save=(k,v)=>{try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}};
 const clamp=(n,lo,hi)=>Math.min(hi,Math.max(lo,n));
 let pace=read(PACE_KEY,null)||{...fallback()};
 let q=read(QKEY,null)||{qid:null,ms:0,since:null,seen:0,manual:false,done:false};
 let set=read(SKEY,null)||{mode:'up',ms:0,since:null,seen:0,answered:0,locked:false};
 let ticker=null,writes=0;
 const live=s=>s.ms+(s.since?Math.max(0,Date.now()-s.since):0);
 const paceMs=()=>Math.round(pace.minutes*60000/pace.questions);
 const targetMs=()=>Math.round(pace.minutes*60000);
 function clock(ms){const t=Math.max(0,Math.round(ms/1000));return Math.floor(t/60)+':'+String(t%60).padStart(2,'0');}
 // A gap larger than a quick reload means the app was shut, so that time is not the user's.
 function hydrate(s){
  if(s.since&&s.locked){s.ms+=Math.max(0,Date.now()-s.since);s.since=Date.now();}
  else if(s.since){s.ms+=Math.max(0,(s.seen||s.since)-s.since);s.since=Date.now()-(s.seen||0)<10000?Date.now():null;}
  return s;
 }
 function persist(force){if(force||++writes%4===0){q.seen=set.seen=Date.now();save(QKEY,q);save(SKEY,set);}}
 function loop(){if(!ticker)ticker=setInterval(()=>{paint();persist();},500);}
 function paint(){
  const ms=live(q),target=paceMs(),over=ms-target,chip=$('questionTimer'),paused=!q.since&&!q.done;
  $('timerTime').textContent=clock(ms);
  $('timerIcon').textContent=q.done?'\u2713':q.since?'\u275A\u275A':'\u25B6';
  chip.classList.toggle('paused',paused);
  chip.classList.toggle('over',over>0);
  chip.classList.toggle('close',over<=0&&target>0&&ms/target>=.75);
  $('timerToggle').setAttribute('aria-label',(q.done?'Answered in ':'Question timer ')+clock(ms)+(q.done?'':q.since?', running. Press to pause.':', paused. Press to resume.'));
  $('timerFill').style.width=(clamp(target?ms/target:0,0,1)*100).toFixed(1)+'%';
  $('timerDelta').textContent=target?(over>0?'+'+clock(over):'\u2212'+clock(-over)):'';
  $('timerDelta').disabled=!paused;
  $('timerDelta').title=paused?'Reset this question to 0:00':'';
  const running=!!set.since||set.ms>0,elapsed=live(set),left=targetMs()-elapsed;
  $('timerSummary').textContent=running?(set.mode==='down'?clock(Math.max(0,left))+' left':clock(elapsed)):'Timer';
  $('timerMenu').classList.toggle('warning',running&&set.mode==='down'&&left<=300000&&left>0);
  $('timerMenu').classList.toggle('over',running&&set.mode==='down'&&left<=0);
  $('setStatus').textContent=running?clock(elapsed)+' elapsed \u00b7 '+set.answered+' answered'+(set.answered?' \u00b7 '+clock(elapsed/set.answered)+' average':'')+(set.mode==='down'&&left<=0?' \u00b7 time is up':''):'Not started.';
  $('setStart').textContent=set.locked&&set.since?'Running · no pausing':set.since?'Pause':(set.ms?'Resume':'Start');
  $('setStart').disabled=!!(set.locked&&set.since);
  $('setMode').disabled=!!set.locked;
  for(const id of ['paceMinutes','paceQuestions'])$(id).disabled=!!set.locked;
  $('paceInfo').textContent=clock(paceMs())+' per question · '+clock(targetMs())+' total';
 }
 function startQuestion(id){
  // Reopening an answered question starts a new sitting, otherwise a second attempt would
  // inherit the first one's time. A reload mid-question resumes instead.
  if(q.qid!==id||q.done)q={qid:id,ms:0,since:Date.now(),seen:Date.now(),manual:false,done:false};
  else if(!q.since&&!q.manual)q.since=Date.now();
  persist(true);paint();
 }
 function stopQuestion(){
  if(q.since){q.ms+=Math.max(0,Date.now()-q.since);q.since=null;}
  q.done=true;persist(true);paint();
  return clamp(Math.round(q.ms),0,7200000);
 }
 function toggleQuestion(){
  if(q.done)return;
  if(q.since){q.ms+=Math.max(0,Date.now()-q.since);q.since=null;q.manual=true;}
  else{q.since=Date.now();q.manual=false;}
  persist(true);paint();
 }
 // Resetting changes the number, never whether the clock is running.
 function resetQuestion(){q={qid:q.qid,ms:0,since:q.since?Date.now():null,seen:Date.now(),manual:q.manual,done:false};persist(true);paint();}
 function countAnswer(){if(set.since){set.answered++;persist(true);paint();}}
 function setAnswerCount(count){if(set.answered!==count){set.answered=count;persist(true);paint();}}
 function toggleSet(){
  if(set.locked&&set.since)return;
  if(set.since){set.ms+=Math.max(0,Date.now()-set.since);set.since=null;}
  else set.since=Date.now();
  persist(true);paint();
 }
 function resetSet(){set={mode:set.mode,ms:0,since:null,seen:Date.now(),answered:0,locked:false};persist(true);paint();}
 function startExam(timed){
  pace={...fallback()};save(PACE_KEY,pace);fillPace();
  set={mode:timed?'down':'up',ms:0,since:Date.now(),seen:Date.now(),answered:0,locked:!!timed};
  $('setMode').value=set.mode;persist(true);paint();
 }
 function finishExam(){if(set.since){set.ms+=Math.max(0,Date.now()-set.since);set.since=null;}set.locked=false;persist(true);paint();return set.ms;}
 function fillPace(){$('paceMinutes').value=pace.minutes;$('paceQuestions').value=pace.questions;}
 function init(){
  hydrate(q);hydrate(set);
  fillPace();$('setMode').value=set.mode;
  $('timerToggle').onclick=toggleQuestion;
  $('timerDelta').onclick=resetQuestion;
  $('setStart').onclick=toggleSet;
  $('setReset').onclick=resetSet;
  $('setMode').onchange=()=>{set.mode=$('setMode').value;persist(true);paint();};
  for(const id of ['paceMinutes','paceQuestions'])$(id).oninput=()=>{
   pace={minutes:clamp(Math.round(+$('paceMinutes').value||1),1,600),questions:clamp(Math.round(+$('paceQuestions').value||1),1,200)};
   save(PACE_KEY,pace);paint();
  };
  document.addEventListener('visibilitychange',()=>{
   if(document.hidden){if(q.since){q.ms+=Math.max(0,Date.now()-q.since);q.since=null;q.away=true;}persist(true);paint();}
   else{if(q.away&&!q.manual&&!q.done)q.since=Date.now();q.away=false;persist(true);paint();}
  });
  addEventListener('pagehide',()=>persist(true));
  loop();paint();
 }
 return {init,startQuestion,stopQuestion,questionElapsed:()=>clamp(Math.round(live(q)),0,7200000),countAnswer,setAnswerCount,clock,startExam,finishExam,examElapsed:()=>live(set)};
})();
function showView(progress){$('practiceView').hidden=progress;$('progressView').hidden=!progress;$('progressTab').classList.toggle('active',progress);$('progressTab').textContent=progress?'← Practice':'Progress';}
async function init(){
 Timers.init();
 for(const id of ['timerMenu','testMenu','bankMenu','dataMenu','accountMenu'])document.addEventListener('click',e=>{if(!$(id).contains(e.target))$(id).open=false;});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){for(const id of ['bankMenu','timerMenu','testMenu','dataMenu','accountMenu'])$(id).open=false;closeDrawer();}});
 const banks=await api('banks');
 fillBanks(banks);
 $('sqliteBackup').href='/api/backup?bank='+encodeURIComponent(bank);$('sqliteBackup').hidden=!!window.SATOffline;
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
 const closeDrawer=()=>{$('practiceView').classList.remove('filters-open');$('mobileFilters').setAttribute('aria-expanded','false');$('drawerBackdrop').hidden=true;};
 $('mobileFilters').onclick=()=>{const open=!$('practiceView').classList.contains('filters-open');$('practiceView').classList.toggle('filters-open',open);$('mobileFilters').setAttribute('aria-expanded',String(open));$('drawerBackdrop').hidden=!open;};$('closeMobileFilters').onclick=closeDrawer;$('drawerBackdrop').onclick=closeDrawer;
 meta=await api('meta');$('domain').innerHTML+=[...meta.domains].map(d=>`<option value="${d.id}">${esc(d.name)}</option>`).join('');fillSkills();fillTags();
 $('startFullTest').hidden=!meta.is_maturita;
 $('officialDifficultyWrap').hidden=meta.is_maturita;$('tagFilterWrap').hidden=meta.is_maturita;
 $('sideYearWrap').hidden=!meta.is_maturita;
 const years='<option value="">All years</option>'+meta.years.map(y=>`<option value="${y}">${y}</option>`).join('');$('sideYear').innerHTML=years;$('fullTestYear').innerHTML=meta.years.map(y=>`<option value="${y}">${y}</option>`).join('');
 $('sectionWrap').hidden=!meta.is_slovak;$('section').innerHTML='<option value="">All 8 sections</option>'+Array.from({length:8},(_,i)=>`<option value="${i+1}">Section ${i+1} · questions ${i*8+1}–${i*8+8}</option>`).join('');
 for(const k of ['domain','skill','difficulty','status','my_difficulty','tag','answer_type','text_mode','section','sideYear'])$(k).onchange=safe(async()=>{if(k==='domain'){$('skill').value='';fillSkills();}await loadList();});$('shuffle').onchange=safe(()=>loadList());
 $('startFullTest').onclick=()=>{const selected=$('sideYear').value||String(meta.years.at(-1));$('fullTestYear').value=selected;const pace=bank==='maturita-slovak'?'100 minutes · 64 questions':'150 minutes · 30 questions';$('fullTestDescription').textContent=`${pace} · official question order · answers stay hidden until submission.`;$('timedTestDescription').textContent=(bank==='maturita-slovak'?'100':'150')+' minutes · no pausing';$('fullTestDialog').showModal();};
 for(const [id,timed] of [['startTimedTest',true],['startUntimedTest',false]])$(id).onclick=safe(async()=>{const year=$('fullTestYear').value;for(const k of ['domain','skill','difficulty','status','my_difficulty','tag','search','answer_type','text_mode','section'])$(k).value='';$('sideYear').value=year;$('shuffle').checked=false;fillSkills();fullTest={id:crypto.randomUUID(),status:'active',year:+year,timed,answers:{},results:{},started_at:new Date().toISOString()};saveTest();$('fullTestDialog').close();await loadList();fullTest.total=questions.length;saveTest();Timers.startExam(timed);updateTestUI();$('testMenu').open=false;toast(`Full ${year} test started. Answers stay hidden until submission.`);});$('cancelFullTest').onclick=()=>$('fullTestDialog').close();
 $('cancelSubmitTest').onclick=()=>$('submitTestDialog').close();$('confirmSubmitTest').onclick=safe(submitTest);
 $('nextUnanswered').onclick=safe(async()=>{const next=questions.find(q=>!testEntry(q.id)?.answer);if(next){await openQuestion(next.id);$('testMenu').open=false;}else toast('Every question has an answer.');});
 const askExit=restart=>{if(!inTest())return;$('exitTestTitle').textContent=restart?'Restart this test?':'Exit this test?';$('exitTestDescription').textContent=restart?'Your current answers will be cleared and the same year will start again.':'Your current test answers will be removed.';$('confirmExitTest').dataset.restart=String(restart);$('exitTestDialog').showModal();};$('restartFullTest').onclick=()=>askExit(true);$('exitFullTest').onclick=()=>askExit(false);$('cancelExitTest').onclick=()=>$('exitTestDialog').close();$('confirmExitTest').onclick=safe(async()=>{const restart=$('confirmExitTest').dataset.restart==='true',year=fullTest?.year,timed=fullTest?.timed;$('exitTestDialog').close();fullTest=null;saveTest();Timers.finishExam();updateTestUI();if(restart){fullTest={id:crypto.randomUUID(),status:'active',year,timed,answers:{},results:{},started_at:new Date().toISOString()};saveTest();await loadList();fullTest.total=questions.length;saveTest();Timers.startExam(timed);updateTestUI();}else await loadList();});
 $('search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(safe(()=>loadList()),250);};
 $('unseen').onclick=safe(async()=>{$('status').value='unseen';await loadList();});$('mistakes').onclick=safe(async()=>{$('status').value='review';await loadList();});
 $('clear').onclick=safe(async()=>{for(const k of ['domain','skill','difficulty','status','my_difficulty','tag','search','sideYear','answer_type','text_mode','section'])if($(k))$(k).value='';if($('shuffle'))$('shuffle').checked=false;fillSkills();await loadList();});
 $('progressTab').onclick=safe(async()=>{if(!$('progressView').hidden){showView(false);return;}await flushNotes();showView(true);await stats();});
 if(fullTest&&meta.is_maturita){$('sideYear').value=String(fullTest.year);$('fullTestYear').value=String(fullTest.year);}else if(fullTest){fullTest=null;saveTest();}
 const initial=new URLSearchParams(location.hash.slice(1)).get('q');await loadList(false);updateTestUI();await stats();if(fullTest?.status==='review')renderTestResultsOverview();else if(initial&&questions.some(q=>q.id===initial))await openQuestion(initial);else if(questions.length)await openQuestion(questions[0].id);else $('workspace').innerHTML='<div class="empty"><h2>This bank is empty.</h2><p>Choose another database to start practicing.</p></div>';
 window.addEventListener('hashchange',safe(async()=>{const id=new URLSearchParams(location.hash.slice(1)).get('q');if(id&&id!==current?.id)await openQuestion(id);}));
 window.addEventListener('beforeunload',e=>{if(pendingNotes.size){e.preventDefault();e.returnValue='';}});
 document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&pendingNotes.size)flushNotes().catch(fail);});
 document.addEventListener('keydown',e=>{if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)||e.ctrlKey||e.metaKey||e.altKey||e.isComposing||$('practiceView').hidden||document.querySelector('dialog[open]'))return;if(/^[a-e]$/i.test(e.key)&&current?.answer_type==='choice'&&!answered&&current.choices.some(c=>c.letter===e.key.toUpperCase()))selectAnswer(e.key.toUpperCase());});
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
