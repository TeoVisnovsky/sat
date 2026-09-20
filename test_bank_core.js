/* node test_bank_core.js [roundtrip|merge] — real offline logic, no browser mocks. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const core=require('./web/bank-core.js');
if(process.argv[2]){
 const input=JSON.parse(fs.readFileSync(0,'utf8'));
 if(process.argv[2]==='merge'){process.stdout.write(JSON.stringify(core.merge(core.validate(input[0]),core.validate(input[1])).data));}
 else {const data=core.validate(input),q=data.questions[0];core.request(data,'attempt',{question_id:q.id,answer:q.correct_answer,guessed:true});core.request(data,'note',{question_id:q.id,content:'Phone note'});core.request(data,'difficulty',{question_id:q.id,rating:'hard'});core.request(data,'tags',{question_id:q.id,tags:['phone']});process.stdout.write(JSON.stringify(data));}
}else{
 const base=core.validate(JSON.parse(fs.readFileSync('docs/seed.json','utf8'))),q=base.questions[0],a=structuredClone(base),b=structuredClone(base);
 assert.equal(base.questions.length,753);assert.equal(core.request(a,'stats').done,0);
 core.request(a,'attempt',{question_id:q.id,answer:q.correct_answer,guessed:false});core.request(a,'note',{question_id:q.id,content:'PC note'});
 core.request(b,'attempt',{question_id:q.id,answer:q.correct_answer==='A'?'B':'A',guessed:true});core.request(b,'note',{question_id:q.id,content:'Phone note'});core.request(b,'difficulty',{question_id:q.id,rating:'hard'});
 const merged=core.merge(a,b),again=core.merge(merged.data,b);
 assert.equal(merged.attempts_added,1);assert.equal(again.attempts_added,0);assert.equal(merged.note_conflicts,1);
 assert.equal(core.request(merged.data,'questions?my_difficulty=hard').length,1);
 const detail=core.request(merged.data,'question/'+q.id);assert.equal(detail.history.length,2);assert(!('correct_answer' in detail));assert(detail.note.includes('PC note')&&detail.note.includes('Phone note'));
 core.request(merged.data,'note',{question_id:q.id,content:'Resolved note'});
 const resolved=core.merge(merged.data,b).data;assert.equal(core.request(resolved,'question/'+q.id).note,'Resolved note');
 const bad=structuredClone(b);bad.questions[0].prompt_html='Different prompt';assert.throws(()=>core.merge(a,bad),/Nothing was merged/);
 const idClash=structuredClone(a);idClash.attempts[0].guessed=1;assert.throws(()=>core.merge(a,idClash),/Conflicting history/);
 const badParent=structuredClone(a);badParent.notes[0].parents=['missing'];assert.throws(()=>core.validate(badParent),/Broken note/);
 assert.throws(()=>core.request(a,'attempt',{question_id:q.id,answer:'X',guessed:false}));
 const math=core.validate(JSON.parse(fs.readFileSync('docs/math-seed.json','utf8'))),numeric=math.questions.find(q=>q.answer_type==='numeric'&&q.accepted_answers.length>1);
 assert.equal(math.questions.length,536);assert(numeric);const equivalent=numeric.accepted_answers.at(-1);
 assert(core.request(math,'attempt',{question_id:numeric.id,answer:equivalent,guessed:false}).is_correct);
 assert(!core.request(math,'attempt',{question_id:numeric.id,answer:'999999',guessed:false}).is_correct);
 assert.throws(()=>core.request(math,'attempt',{question_id:numeric.id,answer:'2+2',guessed:false}),/number/);
 assert.equal(base.attempts.length,0);console.log('Offline core: idempotency, note resolution, filters, conflicts and validation passed.');
}
