/* Portable bank v1. Pure merge functions shared by the offline adapter and tests. */
(function(root){
 'use strict';
 const fields=['id','domain','skill','difficulty','passage_html','prompt_html','answer_type','correct_answer','accepted_answers','explanation_html','choices'];
 const levels=['easy','medium','hard'];
 const uid=()=>crypto.randomUUID(),now=()=>new Date().toISOString();
 const canonical=x=>JSON.stringify(x&&typeof x==='object'?Array.isArray(x)?x.map(v=>JSON.parse(canonical(v))):Object.fromEntries(Object.keys(x).sort().map(k=>[k,JSON.parse(canonical(x[k]))])):x);
 function numeric(value){
  value=String(value??'').trim().replace(/−/g,'-');if(value.length>30||!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+|\d+\/[+-]?\d+)$/.test(value))return null;
  let n,d;if(value.includes('/')){[n,d]=value.split('/').map(BigInt);}else{const sign=value.startsWith('-')?-1n:1n,clean=value.replace(/^[+-]/,'');const [whole='',part='']=clean.split('.');d=10n**BigInt(part.length);n=sign*BigInt((whole||'0')+part);}
  if(!d)return null;if(d<0n){n=-n;d=-d;}const gcd=(a,b)=>{a=a<0n?-a:a;while(b){[a,b]=[b,a%b];}return a;},g=gcd(n,d);return [n/g,d/g];
 }
 function answerCorrect(q,value){if((q.answer_type||'choice')==='choice')return value===q.correct_answer;const n=numeric(value);return !!n&&q.accepted_answers.some(x=>{const a=numeric(x);return a&&a[0]*n[1]===n[0]*a[1];});}
 const leaves=vs=>{const parents=new Set(vs.flatMap(v=>v.parents));return vs.filter(v=>!parents.has(v.id)).sort((a,b)=>a.updated_at.localeCompare(b.updated_at)||a.id.localeCompare(b.id));};
 const noteText=vs=>[...new Set(leaves(vs).map(v=>v.content))].join('\n\n—— Other device’s note ——\n\n');
 function validate(data){
  const check=(condition,message)=>{if(!condition)throw Error(message||'Invalid transfer file');};
  const text=(x,max=200000)=>check(typeof x==='string'&&x.length<=max,'Invalid text in transfer file');
  const identity=x=>check(typeof x==='string'&&/^[a-zA-Z0-9_-]{1,80}$/.test(x),'Invalid record ID');
  check(data?.format==='sat-bank'&&data.version===1,'Choose a SAT bank transfer file (version 1).');
  identity(data.bank?.id);text(data.bank?.name,100);
  for(const key of ['questions','attempts','notes','ratings','reviews','tags'])check(Array.isArray(data[key])&&data[key].length<=200000);
  const qs=new Map();
  for(const q of data.questions){
   identity(q.id);check(!qs.has(q.id),'Duplicate question ID');qs.set(q.id,q);
   q.answer_type=q.answer_type||'choice';q.accepted_answers=q.accepted_answers||[q.correct_answer];
   text(q.domain,200);text(q.skill,200);check(levels.includes(q.difficulty)&&['choice','numeric'].includes(q.answer_type));
   check(q.answer_type==='choice'?['A','B','C','D'].includes(q.correct_answer):Array.isArray(q.accepted_answers)&&q.accepted_answers.length&&q.accepted_answers.every(x=>typeof x==='string'&&numeric(x)),'Invalid question answer');
   for(const key of ['passage_html','prompt_html','explanation_html'])text(q[key]);check(q.prompt_html.trim());
   check(Array.isArray(q.choices)&&q.choices.map(c=>c.letter).sort().join('')===(q.answer_type==='choice'?'ABCD':''),'Answer choices do not match the question type');q.choices.sort((a,b)=>a.letter.localeCompare(b.letter));
   for(const c of q.choices)text(c.content_html);
   for(const s of q.sources||[]){text(s.filename,250);text(s.file_sha256,100);check(Number.isInteger(s.page_start)&&Number.isInteger(s.page_end)&&s.page_start>=1&&s.page_end>=s.page_start);}
  }
  for(const key of ['attempts','notes','ratings','reviews','tags']){
   const seen=new Set();
   for(const r of data[key]){
    check(qs.has(r.question_id),'Record refers to an absent question');
    if(key==='tags'){text(r.name,60);check(r.name.trim(),'Empty tag');continue;}
    identity(r.id);const unique=['ratings','reviews'].includes(key)?r.question_id:r.id;check(!seen.has(unique),'Duplicate record ID');seen.add(unique);
    const date=key==='attempts'?'answered_at':'updated_at';check(typeof r[date]==='string'&&Number.isFinite(Date.parse(r[date])),'Invalid timestamp');r[date]=new Date(r[date]).toISOString();
    if(key==='attempts'){check(typeof r.selected_answer==='string'&&r.selected_answer.length<=30&&[0,1,false,true].includes(r.guessed)&&[0,1,false,true].includes(r.is_correct)&&+r.is_correct===+answerCorrect(qs.get(r.question_id),r.selected_answer),'Invalid attempt');r.guessed=+r.guessed;r.is_correct=+r.is_correct;}
    if(key==='notes'){text(r.content,20000);check(Array.isArray(r.parents));}
    if(key==='ratings')check(levels.includes(r.rating));
    if(key==='reviews'){check([0,1,false,true].includes(r.needs_review));r.needs_review=+r.needs_review;}
   }
  }
  const notes=new Map(data.notes.map(n=>[n.id,n])),done=new Set(),active=new Set();
  function visit(id){check(!active.has(id),'Cyclic note history');if(done.has(id))return;active.add(id);for(const p of notes.get(id).parents){check(notes.has(p)&&notes.get(p).question_id===notes.get(id).question_id,'Broken note history');visit(p);}active.delete(id);done.add(id);}
  for(const id of notes.keys())visit(id);
  return data;
 }
 function merge(original,incoming){
  const local=structuredClone(original),questions=new Map(local.questions.map(q=>[q.id,q]));
  const conflicts=incoming.questions.filter(q=>questions.has(q.id)&&fields.some(k=>canonical(q[k])!==canonical(questions.get(q.id)[k]))).map(q=>q.id);
  if(conflicts.length)throw Error('Question content differs for '+conflicts.slice(0,12).join(', ')+'. Nothing was merged. Import as a separate database to review both versions.');
  const report={questions_added:0,attempts_added:0,note_conflicts:0};
  for(const q of incoming.questions){if(!questions.has(q.id)){local.questions.push(q);questions.set(q.id,q);report.questions_added++;}else{const old=questions.get(q.id);old.sources=[...new Map([...(old.sources||[]),...(q.sources||[])].map(s=>[canonical(s),s])).values()];}}
  for(const key of ['attempts','notes']){const records=new Map(local[key].map(r=>[r.id,r]));for(const r of incoming[key]){if(records.has(r.id)&&canonical(r)!==canonical(records.get(r.id)))throw Error('Conflicting history ID. Nothing was merged; add this as a separate database.');if(!records.has(r.id)){local[key].push(r);records.set(r.id,r);if(key==='attempts')report.attempts_added++;}}}
  for(const key of ['ratings','reviews']){const records=new Map(local[key].map(r=>[r.question_id,r]));for(const r of incoming[key]){const old=records.get(r.question_id);if(old&&r.id===old.id&&canonical(r)!==canonical(old))throw Error('Conflicting state ID. Nothing was merged; add this as a separate database.');if(!old||r.updated_at>old.updated_at||(r.updated_at===old.updated_at&&r.id>old.id))records.set(r.question_id,r);}local[key]=[...records.values()];}
  local.tags=[...new Map([...incoming.tags,...local.tags].map(t=>[t.question_id+'\0'+t.name.toLowerCase(),t])).values()];
  report.note_conflicts=[...new Set(local.notes.map(n=>n.question_id))].filter(id=>new Set(leaves(local.notes.filter(n=>n.question_id===id)).map(n=>n.content)).size>1).length;
  return {data:local,...report};
 }
 function metadata(data){
  const domains=[],skills=[],tags=[];
  for(const q of data.questions){let d=domains.find(d=>d.name===q.domain);if(!d){d={id:domains.length+1,name:q.domain};domains.push(d);}if(!skills.some(s=>s.domain_id===d.id&&s.name===q.skill))skills.push({id:skills.length+1,domain_id:d.id,name:q.skill});}
  for(const t of data.tags)if(!tags.some(x=>x.name.toLowerCase()===t.name.toLowerCase()))tags.push({id:tags.length+1,name:t.name});
  return {domains,skills,tags:tags.sort((a,b)=>a.name.localeCompare(b.name))};
 }
 const attempts=(data,id)=>data.attempts.filter(a=>a.question_id===id).sort((a,b)=>a.answered_at.localeCompare(b.answered_at)||a.id.localeCompare(b.id));
 function row(data,q,meta){const history=attempts(data,q.id),last=history.at(-1),domain=meta.domains.find(d=>d.name===q.domain),skill=meta.skills.find(s=>s.domain_id===domain.id&&s.name===q.skill);return {id:q.id,skill_id:skill.id,domain_id:domain.id,skill:q.skill,domain:q.domain,difficulty:q.difficulty,passage_html:q.passage_html,prompt_html:q.prompt_html,answer_type:q.answer_type||'choice',my_difficulty:data.ratings.find(r=>r.question_id===q.id)?.rating||null,latest_correct:last?+last.is_correct:null,latest_guessed:last?+last.guessed:null,last_attempt:last?.answered_at,needs_review:+(data.reviews.find(r=>r.question_id===q.id)?.needs_review||0),attempt_count:history.length};}
 function request(data,path,body){
  const url=new URL(path,'https://sat.invalid/'),p=url.searchParams,meta=metadata(data);
  if(body===undefined){
   if(url.pathname==='/meta')return meta;
   if(url.pathname==='/export')return data;
   if(url.pathname==='/questions')return data.questions.map(q=>row(data,q,meta)).filter(q=>{
    for(const [key,col] of [['domain','domain_id'],['skill','skill_id'],['difficulty','difficulty']])if(p.get(key)&&String(q[col])!==p.get(key))return false;
    const status=p.get('status');if(({unseen:!q.attempt_count,done:!!q.attempt_count,correct:q.latest_correct===1,incorrect:q.latest_correct===0,guessed:!!q.latest_guessed,review:!!q.needs_review})[status]===false)return false;
    const rating=p.get('my_difficulty');if(rating&&(rating==='unrated'?q.my_difficulty!==null:q.my_difficulty!==rating))return false;
    if(p.get('tag')){const t=meta.tags.find(t=>String(t.id)===p.get('tag'));if(!t||!data.tags.some(x=>x.question_id===q.id&&x.name.toLowerCase()===t.name.toLowerCase()))return false;}
    const search=(p.get('search')||'').trim().toLowerCase();return !search||q.id.toLowerCase().includes(search)||q.passage_html.toLowerCase().includes(search);
   });
   if(url.pathname==='/stats'){const rows=data.questions.map(q=>row(data,q,meta)),first=data.questions.map(q=>attempts(data,q.id)[0]).filter(Boolean);return {total:rows.length,done:first.length,first_correct:first.reduce((n,a)=>n+(+a.is_correct),0),review:rows.filter(q=>q.needs_review).length,skills:meta.skills.map(s=>{const qs=rows.filter(q=>q.skill_id===s.id),as=qs.map(q=>attempts(data,q.id)[0]).filter(Boolean);return {...s,total:qs.length,done:as.length,correct:as.reduce((n,a)=>n+(+a.is_correct),0)};})};}
   if(url.pathname.startsWith('/question/')){const q=data.questions.find(q=>q.id===url.pathname.split('/').at(-1));if(!q)throw Error('Question not found');const vs=data.notes.filter(n=>n.question_id===q.id);return {...row(data,q,meta),choices:q.choices,assets:[],note:noteText(vs),note_parents:leaves(vs).map(n=>n.id),tags:data.tags.filter(t=>t.question_id===q.id).map(t=>t.name),history:attempts(data,q.id).reverse(),sources:q.sources||[]};}
   throw Error('Unknown request');
  }
  const q=data.questions.find(q=>q.id===body.question_id);if(!q)throw Error('Question not found');
  const setState=(key,value)=>{data[key]=data[key].filter(r=>r.question_id!==q.id);data[key].push({id:uid(),question_id:q.id,updated_at:now(),...value});};
  if(path==='attempt'){
   if(typeof body.answer!=='string'||body.answer.length>30||typeof body.guessed!=='boolean'||((q.answer_type||'choice')==='choice'&&!['A','B','C','D'].includes(body.answer))||((q.answer_type||'choice')==='numeric'&&!numeric(body.answer)))throw Error((q.answer_type||'choice')==='choice'?'Choose A, B, C, or D':'Enter a number, decimal, or fraction');
   body.answer=body.answer.trim().replace(/−/g,'-');const correct=answerCorrect(q,body.answer),review=+(!correct||body.guessed),id=uid();data.attempts.push({id,question_id:q.id,selected_answer:body.answer,is_correct:+correct,guessed:+body.guessed,answered_at:now()});setState('reviews',{needs_review:review});return {attempt_id:id,is_correct:correct,correct_answer:q.correct_answer,explanation_html:q.explanation_html,needs_review:review};
  }
  if(path==='note'){if(typeof body.content!=='string'||body.content.length>20000)throw Error('Note is too long');const vs=data.notes.filter(n=>n.question_id===q.id),parents=body.parents===undefined?leaves(vs).map(v=>v.id):body.parents;if(!Array.isArray(parents)||parents.some(id=>!vs.some(n=>n.id===id)))throw Error('Note history changed. Reopen the question before editing.');if(noteText(vs)===body.content)return {saved:true,note_parents:leaves(vs).map(n=>n.id)};const id=uid();data.notes.push({id,question_id:q.id,content:body.content,updated_at:now(),parents});return {saved:true,note_parents:[id]};}
  else if(path==='difficulty'){if(!levels.includes(body.rating))throw Error('Invalid difficulty');setState('ratings',{rating:body.rating});}
  else if(path==='review'){if(typeof body.needs_review!=='boolean')throw Error('Invalid review status');setState('reviews',{needs_review:+body.needs_review});}
  else if(path==='tags'){if(!Array.isArray(body.tags)||body.tags.length>20||body.tags.some(t=>typeof t!=='string'||!t.trim()||t.length>60))throw Error('Use up to 20 tags, each 1–60 characters');data.tags=data.tags.filter(t=>t.question_id!==q.id);for(const name of new Set(body.tags.map(t=>t.trim())))data.tags.push({question_id:q.id,name});}
  else throw Error('Unknown request');
  return {saved:true};
 }
 // Keep imported markup inert while retaining SAT tables, emphasis and inline SVG charts.
 function html(value){
  const template=document.createElement('template');template.innerHTML=String(value||'');
  const allowed=new Set('p span em strong i b u sup sub br ul ol li cite figure figcaption blockquote div table caption thead tbody tfoot tr th td svg g defs pattern line text rect marker polygon polyline path circle ellipse use clippath math mrow mi mo mn mfrac msup msub msubsup msqrt mroot mtable mtr mtd mtext mspace mfenced mover munder munderover mmultiscripts mprescripts none menclose mstyle semantics annotation'.split(' '));
  const attrs=new Set('aria-label aria-hidden role viewbox width height xmlns xmlns:xlink version id x y dx dy x1 x2 y1 y2 cx cy rx ry r d points transform fill stroke stroke-width stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray opacity isolation dominant-baseline text-anchor font-family font-size patterntransform patternunits markerunits markerwidth markerheight refx refy orient marker-end marker-start colspan rowspan scope alttext display displaystyle mathvariant stretchy fence separator form notation bevelled columnalign rowalign clip-path href xlink:href'.split(' '));
 // <mfenced> was dropped from MathML Core, so brackets would silently vanish. Rebuild them as <mrow><mo>…</mo></mrow>.
  const MATHML='http://www.w3.org/1998/Math/MathML';
  for(let el;(el=template.content.querySelector('mfenced'));){
   const mo=text=>{const node=document.createElementNS(MATHML,'mo');node.textContent=text;return node;};
   const row=document.createElementNS(MATHML,'mrow'),opener=el.getAttribute('open')??'(',closer=el.getAttribute('close')??')';
   const seps=(el.getAttribute('separators')??',').replace(/\s+/g,''),kids=[...el.children];
   if(opener)row.appendChild(mo(opener));
   kids.forEach((kid,i)=>{if(i&&seps)row.appendChild(mo(seps[Math.min(i-1,seps.length-1)]));row.appendChild(kid);});
   if(closer)row.appendChild(mo(closer));
   el.replaceWith(row);
  }
  const safeStyle=value=>value.split(';').map(x=>x.trim()).filter(x=>/^(?:fill|stroke|stroke-width|stroke-linecap|stroke-linejoin|stroke-miterlimit|stroke-dasharray|opacity|isolation|font-size|font-family|text-anchor|text-decoration)\s*:\s*[-#(),.%\w\s]+$/i.test(x)).join(';');
  for(const el of [...template.content.querySelectorAll('*')]){if(['style','script'].includes(el.localName.toLowerCase())){el.remove();continue;}if(!allowed.has(el.localName.toLowerCase())){el.replaceWith(document.createTextNode(el.textContent));continue;}for(const a of [...el.attributes]){const name=a.name.toLowerCase();if(name==='style'){const value=safeStyle(a.value);if(value)el.setAttribute('style',value);else el.removeAttribute(a.name);continue;}if(name==='class'&&a.value==='sr-only')continue;if(!attrs.has(name)||/javascript:|https?:|data:/i.test(a.value))el.removeAttribute(a.name);}}
  return template.innerHTML;
 }
 const api={uid,now,validate,merge,leaves,noteText,request,canonical,html,numeric,answerCorrect};root.SATCore=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
