"""Integration checks using a disposable copy of the question database."""
import json,sqlite3,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
import server
from contextlib import closing

class TrainerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.path=Path(cls.tmp.name)/'test.db'
        server.BANKS=Path(cls.tmp.name)/'banks';cls.old_math=server.MATH_DB;server.MATH_DB=Path(cls.tmp.name)/'math.db'
        src=sqlite3.connect(server.ROOT/'sat-clean.db');dst=sqlite3.connect(cls.path);src.backup(dst);src.close()
        dst.executescript((server.ROOT/'schema.sql').read_text())
        for table in ['attempts','notes','review_state','question_tags','tags','personal_difficulty']:dst.execute('DELETE FROM '+table)
        dst.commit();dst.close()
        src=sqlite3.connect(server.ROOT/'sat-math-clean.db');dst=sqlite3.connect(server.MATH_DB);src.backup(dst);src.close();dst.close();server.DB=cls.path
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.http.server_port)
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();server.MATH_DB=cls.old_math;cls.tmp.cleanup()
    def request(self,path,data=None,headers=None):
        h={'Content-Type':'application/json'};h.update(headers or {})
        req=urllib.request.Request(self.base+path,data=None if data is None else json.dumps(data).encode(),headers=h)
        try:
            with urllib.request.urlopen(req) as r:return r.status,r.read()
        except urllib.error.HTTPError as e:return e.code,e.read()
    def get(self,path):
        code,raw=self.request('/api/'+path);self.assertEqual(code,200,raw);return json.loads(raw)
    def post(self,path,data):
        code,raw=self.request('/api/'+path,data);self.assertEqual(code,200,raw);return json.loads(raw)
    def test_workflow(self):
        stats=self.get('stats');self.assertEqual(stats['total'],753);self.assertEqual(stats['done'],0)
        meta=self.get('meta');self.assertEqual(len(meta['domains']),4);self.assertEqual(len(meta['skills']),10)
        questions=self.get('questions');q=questions[0];qid=q['id'];detail=self.get('question/'+qid)
        self.assertNotIn('correct_answer',detail);self.assertNotIn('explanation_html',detail)
        self.assertTrue(detail['prompt_html']);self.assertEqual([c['letter'] for c in detail['choices']],list('ABCD'))
        with closing(sqlite3.connect(self.path)) as db:correct=db.execute('SELECT correct_answer FROM questions WHERE id=?',(qid,)).fetchone()[0]
        wrong=next(c for c in 'ABCD' if c!=correct)
        r=self.post('attempt',{'question_id':qid,'answer':wrong,'guessed':False});self.assertFalse(r['is_correct']);self.assertTrue(r['explanation_html']);self.assertEqual(r['correct_answer'],correct)
        self.assertEqual(self.get('questions?status=review')[0]['id'],qid)
        self.post('note',{'question_id':qid,'content':'Rule → check the evidence.\nSecond line.'})
        self.post('tags',{'question_id':qid,'tags':['Evidence','inference']})
        tag=self.get('meta')['tags'][0]['id'];self.assertEqual(len(self.get('questions?tag='+str(tag))),1)
        self.post('attempt',{'question_id':qid,'answer':correct,'guessed':True});self.assertEqual(len(self.get('questions?status=guessed')),1)
        self.post('attempt',{'question_id':qid,'answer':correct,'guessed':False});self.assertEqual(len(self.get('questions?status=review')),0)
        detail=self.get('question/'+qid);self.assertEqual(len(detail['history']),3);self.assertIn('Second line.',detail['note']);self.assertEqual(len(detail['tags']),2)
        stats=self.get('stats');self.assertEqual(stats['done'],1);self.assertEqual(stats['first_correct'],0)
        self.assertEqual(len(self.get('questions?status=unseen')),752)
        self.assertEqual(len(self.get('questions?search='+qid)),1)
        self.post('difficulty',{'question_id':qid,'rating':'hard'})
        self.assertEqual(self.get('question/'+qid)['my_difficulty'],'hard')
        self.assertEqual(len(self.get('questions?my_difficulty=hard')),1)
        self.assertEqual(len(self.get('questions?my_difficulty=unrated')),752)
        self.post('difficulty',{'question_id':qid,'rating':'easy'})
        self.assertEqual(len(self.get('questions?my_difficulty=hard')),0)
        self.assertEqual(len(self.get('questions?my_difficulty=easy')),1)
        self.assertEqual(self.request('/api/difficulty',{'question_id':qid,'rating':'invalid'})[0],400)
        skill=q['skill_id'];filtered=self.get('questions?skill='+str(skill)+'&difficulty='+q['difficulty']);self.assertTrue(all(k['skill_id']==skill and k['difficulty']==q['difficulty'] for k in filtered))
        self.post('review',{'question_id':qid,'needs_review':True});self.assertEqual(self.get('stats')['review'],1)
        for answer in ['','AB',None,'X']:
            self.assertEqual(self.request('/api/attempt',{'question_id':qid,'answer':answer})[0],400)
        self.assertEqual(self.request('/api/attempt',{'question_id':qid,'answer':correct},headers={'Origin':'https://example.org'})[0],403)
        self.assertEqual(self.request('/sat.db')[0],404)
        self.assertEqual(self.request('/assets/../server.py')[0],404)
        self.assertEqual(self.request('/')[0],200)
        code,raw=self.request('/api/backup');self.assertEqual(code,200);backup=Path(self.tmp.name)/'backup.db';backup.write_bytes(raw)
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],3)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_bank_completeness(self):
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM questions WHERE prompt_html='' OR explanation_html='' OR passage_html='' ").fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM choices').fetchone()[0],3012)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM official_references').fetchone()[0],753)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sources').fetchone()[0],8)
            for path, in db.execute('SELECT file_path FROM assets'):self.assertTrue(path.startswith('assets/'))
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_math_numeric_answers(self):
        questions=self.get('questions?bank=math');self.assertEqual(len(questions),536)
        with closing(sqlite3.connect(server.MATH_DB)) as db:
            qid,accepted=db.execute("SELECT id,accepted_answers FROM questions WHERE answer_type='numeric' AND json_array_length(accepted_answers)>1 LIMIT 1").fetchone()
        detail=self.get('question/'+qid+'?bank=math');self.assertEqual(detail['answer_type'],'numeric');self.assertEqual(detail['choices'],[]);self.assertNotIn('correct_answer',detail)
        answer=json.loads(accepted)[-1]
        code,raw=self.request('/api/attempt',{'question_id':qid,'answer':answer,'guessed':False},{'X-SAT-Bank':'math'});self.assertEqual(code,200,raw);self.assertTrue(json.loads(raw)['is_correct'])
        code,raw=self.request('/api/attempt',{'question_id':qid,'answer':'2+2','guessed':False},{'X-SAT-Bank':'math'});self.assertEqual(code,400,raw)

    def test_attempt_records_question_time(self):
        """Runs against the Math bank so the shared English bank stays untouched."""
        math={'X-SAT-Bank':'math'}
        qid=[q for q in self.get('questions?bank=math') if q['answer_type']=='choice'][0]['id']
        code,raw=self.request('/api/attempt',{'question_id':qid,'answer':'A','guessed':False,'elapsed_ms':41000},math);self.assertEqual(code,200,raw)
        self.assertEqual(self.get('question/'+qid+'?bank=math')['history'][0]['elapsed_ms'],41000)
        code,raw=self.request('/api/attempt',{'question_id':qid,'answer':'A','guessed':False},math);self.assertEqual(code,200,raw)
        self.assertIsNone(self.get('question/'+qid+'?bank=math')['history'][0]['elapsed_ms'],'An untimed answer is still accepted')
        for bad in (-1,7200001,'40',1.5,True):
            code,raw=self.request('/api/attempt',{'question_id':qid,'answer':'A','guessed':False,'elapsed_ms':bad},math);self.assertEqual(code,400,'accepted %r: %s'%(bad,raw))
        stats=self.get('stats?bank=math');self.assertEqual(stats['timed'],1);self.assertEqual(stats['average_ms'],41000)
        self.assertEqual(self.get('stats')['timed'],0,'The English bank must be unaffected')

    def test_first_run_preserves_existing_database(self):
        path=Path(self.tmp.name)/'first-run.db'
        server.initialize_database(path)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM questions').fetchone()[0],753)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],0)
            db.execute("INSERT INTO notes(question_id,content) VALUES ('5251e5c9','Keep my note')");db.commit()
        server.initialize_database(path)
        with closing(sqlite3.connect(path)) as db:self.assertEqual(db.execute('SELECT content FROM notes').fetchone()[0],'Keep my note')

    def test_database_import_and_isolation(self):
        code,raw=self.request('/api/backup');self.assertEqual(code,200)
        req=urllib.request.Request(self.base+'/api/banks/import',data=raw,headers={'Content-Type':'application/octet-stream','X-Filename':'Second%20bank.db'})
        with urllib.request.urlopen(req) as response:key=json.load(response)['id']
        self.assertEqual(self.get('banks')[-1]['name'],'Second bank')
        qid='5251e5c9'
        code,_=self.request('/api/note',{'question_id':qid,'content':'Only in the second bank'},headers={'X-SAT-Bank':key});self.assertEqual(code,200)
        self.assertEqual(self.get('question/'+qid+'?bank='+key)['note'],'Only in the second bank')
        self.assertNotEqual(self.get('question/'+qid)['note'],'Only in the second bank')
        self.assertEqual(self.request('/api/questions?bank=../sat')[0],400)
        req=urllib.request.Request(self.base+'/api/banks/import',data=b'not a database',headers={'Content-Type':'application/octet-stream'})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
        self.assertEqual(error.exception.code,400)
        self.assertEqual(len(self.get('banks')),3)

if __name__=='__main__':unittest.main(verbosity=2)
