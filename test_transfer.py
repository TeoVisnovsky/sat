"""Cross-device compatibility and HTTP merge regression tests. Uses disposable banks."""
import copy,json,sqlite3,tempfile,unittest,subprocess,shutil,threading,urllib.request,urllib.error
from pathlib import Path
import server,transfer

class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.old_db=server.DB;self.old_banks=server.BANKS
        server.DB=self.root/'main.db';server.BANKS=self.root/'banks';server.initialize_database(server.DB)
        with server.connect() as db:self.base=transfer.export_bank(db)
        self.qid=self.base['questions'][0]['id']
    def tearDown(self):server.DB=self.old_db;server.BANKS=self.old_banks;self.temp.cleanup()
    def node(self,mode,data):
        if not shutil.which('node'):self.skipTest('Node is required for cross-runtime checks')
        result=subprocess.run(['node','test_bank_core.js',mode],input=json.dumps(data),text=True,encoding='utf-8',capture_output=True,check=True,cwd=server.ROOT)
        return json.loads(result.stdout)
    def test_question_timing_survives_upgrade_and_transfer(self):
        with server.connect() as db:
            self.assertIn('elapsed_ms',{r[1] for r in db.execute('PRAGMA table_info(attempts)')})
            db.execute('INSERT INTO attempts(question_id,selected_answer,is_correct,guessed,elapsed_ms,answered_at) VALUES (?,?,?,?,?,?)',(self.qid,'A',0,0,41000,transfer.now()))
            db.execute('INSERT INTO attempts(question_id,selected_answer,is_correct,guessed,answered_at) VALUES (?,?,?,?,?)',(self.qid,'A',0,0,transfer.now()))
            exported=transfer.export_bank(db)
        times=sorted(a['elapsed_ms'] for a in exported['attempts'] if a['elapsed_ms'] is not None)
        self.assertEqual(times,[41000])
        self.assertEqual(sum(a['elapsed_ms'] is None for a in exported['attempts']),1,'Untimed attempts export as null')
        self.assertEqual(transfer.validate(copy.deepcopy(exported)),exported)
        # A file written before timing existed omits the field entirely; it must merge without a conflict.
        legacy=copy.deepcopy(exported)
        for a in legacy['attempts']:a.pop('elapsed_ms')
        legacy=transfer.validate(legacy)
        merged,report=transfer.merge(copy.deepcopy(exported),copy.deepcopy(legacy))
        self.assertEqual(report['attempts_added'],0,'The same attempts must not be duplicated by the upgrade')
        self.assertEqual(sorted(a['elapsed_ms'] for a in merged['attempts'] if a['elapsed_ms'] is not None),[41000],'Merging an untimed copy must not erase a known time')
        filled,_=transfer.merge(copy.deepcopy(legacy),copy.deepcopy(exported))
        self.assertEqual(sorted(a['elapsed_ms'] for a in filled['attempts'] if a['elapsed_ms'] is not None),[41000],'A known time fills in a missing one')
        self.assertEqual(self.node('merge',[copy.deepcopy(exported),copy.deepcopy(legacy)])['attempts'],merged['attempts'])
        # Storing the merge back preserves the recorded time.
        fresh=self.root/'timed.db';server.initialize_database(fresh)
        with server.connect(fresh) as db:
            transfer.store(db,merged)
            self.assertEqual(sorted(r[0] for r in db.execute('SELECT elapsed_ms FROM attempts') if r[0] is not None),[41000])
        for bad in (-1,7200001,'40',1.5):
            with self.assertRaises(ValueError):transfer.elapsed(bad)

    def test_phone_pc_roundtrip_and_note_resolution(self):
        with server.connect() as db:
            db.execute('INSERT INTO notes(question_id,content) VALUES (?,?)',(self.qid,'PC note'));pc=transfer.export_bank(db)
        phone=self.node('roundtrip',copy.deepcopy(self.base))
        validated=transfer.validate(copy.deepcopy(phone));self.assertEqual(validated,phone)
        merged,report=transfer.merge(copy.deepcopy(pc),phone);self.assertEqual(report['note_conflicts'],1)
        js=self.node('merge',[pc,phone])
        for key in ['attempts','notes','ratings','reviews','tags']:self.assertEqual(sorted(merged[key],key=transfer.canonical),sorted(js[key],key=transfer.canonical))
        with server.connect() as db:
            transfer.store(db,merged);exported=transfer.export_bank(db)
            self.assertEqual(len(exported['attempts']),1);self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            note=db.execute('SELECT content FROM notes').fetchone()[0];self.assertIn('Phone note',note);self.assertIn('PC note',note)
            again,report=transfer.merge(exported,phone);self.assertEqual(report['attempts_added'],0);transfer.store(db,again)
            db.execute('UPDATE notes SET content=?,updated_at=? WHERE question_id=?',('Resolved on PC',transfer.now(),self.qid));resolved=transfer.export_bank(db)
        on_phone=self.node('merge',[phone,resolved]);self.assertEqual(transfer.note_text(on_phone['notes']),'Resolved on PC')
        repeated,_=transfer.merge(resolved,phone);self.assertEqual(transfer.note_text(repeated['notes']),'Resolved on PC')
    def test_new_questions_and_conflicts(self):
        incoming=copy.deepcopy(self.base);q=copy.deepcopy(incoming['questions'][0]);q['id']='new-question';incoming['questions'].append(q)
        merged,report=transfer.merge(copy.deepcopy(self.base),incoming);self.assertEqual(report['questions_added'],1)
        with server.connect() as db:transfer.store(db,merged);self.assertEqual(db.execute('SELECT COUNT(*) FROM questions').fetchone()[0],754)
        incoming['questions'][0]['correct_answer']='A' if incoming['questions'][0]['correct_answer']!='A' else 'B'
        with self.assertRaisesRegex(ValueError,'Nothing was merged'):transfer.merge(copy.deepcopy(self.base),incoming)
    def test_http_import_is_atomic_and_supports_old_sqlite(self):
        http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
        def upload(raw,mode='merge'):
            req=urllib.request.Request(f'http://127.0.0.1:{http.server_port}/api/banks/import',data=raw,headers={'Content-Type':'application/octet-stream','X-Import-Mode':mode})
            try:
                with urllib.request.urlopen(req) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as e:return e.code,json.load(e)
        try:
            phone=self.node('roundtrip',self.base)
            code,result=upload(json.dumps(phone).encode());self.assertEqual(code,200,result);self.assertEqual(result['attempts_added'],1)
            code,result=upload(json.dumps(phone).encode());self.assertEqual(result['attempts_added'],0)
            bad=copy.deepcopy(phone);bad['questions'][0]['prompt_html']='Changed'
            code,result=upload(json.dumps(bad).encode());self.assertEqual(code,400);self.assertIn('Nothing was merged',result['error'])
            with server.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],1)
            code,result=upload(json.dumps(bad).encode(),'add');self.assertEqual(code,200,result);self.assertNotEqual(result['id'],'main')
            code,result=upload((server.ROOT/'sat-clean.db').read_bytes());self.assertEqual(code,200,result);self.assertEqual(result['attempts_added'],0)
            self.assertEqual(len(list(server.BANKS.glob('*.db'))),1)
        finally:http.shutdown();http.server_close()
    def test_timestamp_offsets_and_broken_records(self):
        self.assertEqual(transfer.stamp('2026-09-14T12:00:00+02:00'),'2026-09-14T10:00:00.000Z')
        bad=copy.deepcopy(self.base);bad['notes']=[dict(id='one',question_id=self.qid,content='note',updated_at=transfer.now(),parents=['one'])]
        with self.assertRaisesRegex(ValueError,'Cyclic'):transfer.validate(bad)

    def test_history_order_is_stable_after_importing_older_attempts(self):
        q=self.base['questions'][0];latest=copy.deepcopy(self.base)
        latest['attempts']=[dict(id='z-later',question_id=self.qid,selected_answer=q['correct_answer'],is_correct=1,guessed=0,answered_at='2026-09-14T10:00:00.000Z')]
        with server.connect() as db:transfer.store(db,latest)
        older=copy.deepcopy(self.base);older['attempts']=[dict(id='a-earlier',question_id=self.qid,selected_answer='A' if q['correct_answer']!='A' else 'B',is_correct=0,guessed=0,answered_at='2026-09-14T10:00:00.000Z')]
        with server.connect() as db:
            merged,_=transfer.merge(transfer.export_bank(db),older);transfer.store(db,merged)
            self.assertEqual(db.execute(server.BASE+' WHERE q.id=?',(self.qid,)).fetchone()['latest_correct'],1)
        http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{http.server_port}/api/stats') as r:stats=json.load(r)
            self.assertEqual(stats['first_correct'],0);self.assertEqual(stats['done'],1)
        finally:http.shutdown();http.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
