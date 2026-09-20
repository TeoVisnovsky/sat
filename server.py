"""SAT Trainer: local-only HTTP service, Python standard library + SQLite."""
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs, unquote
import argparse, json, mimetypes, sqlite3, tempfile, os, traceback, uuid, shutil, threading, webbrowser
import transfer
from contextlib import contextmanager

ROOT=Path(__file__).resolve().parent
DB=ROOT/'sat.db'
MATH_DB=ROOT/'sat-math.db'
BANKS=ROOT/'databases'

def initialize_database(path,template=None):
    """Make a personal working copy on first launch; never replace existing progress."""
    if path.exists():return
    template=template or ROOT/'sat-clean.db'
    if not template.is_file():raise FileNotFoundError(template.name+' is missing. Download and extract the complete repository.')
    # Exclusive creation protects an existing database from concurrent launches.
    with template.open('rb') as source, path.open('xb') as target:shutil.copyfileobj(source,target)

def bank_path(key='main'):
    if key=='main':return DB
    if key=='math':return MATH_DB
    if not isinstance(key,str) or len(key)!=32 or any(c not in '0123456789abcdef' for c in key):raise ValueError('Unknown database')
    path=BANKS/(key+'.db')
    if not path.is_file():raise ValueError('Database not found')
    return path

def import_bank(raw,name):
    if not raw.startswith(b'SQLite format 3\x00'):raise ValueError('Choose a SAT Trainer SQLite database (.db).')
    BANKS.mkdir(exist_ok=True);key=uuid.uuid4().hex;path=BANKS/(key+'.db')
    path.write_bytes(raw)
    try:
        db=sqlite3.connect(path)
        try:
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database is damaged')
            transfer.migrate(db);db.commit()
            expected=sqlite3.connect(':memory:')
            try:
                expected.executescript((ROOT/'schema.sql').read_text())
                for table, in expected.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('official_references','personal_difficulty','transfer_meta','attempt_ids','note_versions','state_versions')"):
                    required={r[1] for r in expected.execute('PRAGMA table_info('+table+')')}
                    entry=db.execute('SELECT type FROM sqlite_master WHERE name=?',(table,)).fetchone()
                    actual={r[1] for r in db.execute('PRAGMA table_info('+table+')')}
                    if not entry or entry[0]!='table' or not required<=actual:raise ValueError('This file is not a compatible SAT Trainer database')
            finally:expected.close()
            if db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type IN ('trigger','view')").fetchone()[0]:raise ValueError('Databases with triggers or views are not supported')
            if db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Database contains broken references')
            if db.execute("SELECT COUNT(*) FROM questions q WHERE prompt_html='' OR (answer_type='choice' AND ((SELECT COUNT(*) FROM choices c WHERE c.question_id=q.id)!=4 OR NOT EXISTS(SELECT 1 FROM choices c WHERE c.question_id=q.id AND c.letter=q.correct_answer))) OR (answer_type='numeric' AND (SELECT COUNT(*) FROM choices c WHERE c.question_id=q.id)!=0)").fetchone()[0]:raise ValueError('Questions have invalid answer controls')
            from recover_prompts import clean
            for qid,passage,prompt,explanation in db.execute('SELECT id,passage_html,prompt_html,explanation_html FROM questions').fetchall():
                if not isinstance(qid,str) or not 1<=len(qid)<=80 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in qid):raise ValueError('Invalid question ID')
                db.execute('UPDATE questions SET passage_html=?,prompt_html=?,explanation_html=? WHERE id=?',(clean(passage),clean(prompt),clean(explanation),qid))
            for qid,letter,content in db.execute('SELECT question_id,letter,content_html FROM choices').fetchall():db.execute('UPDATE choices SET content_html=? WHERE question_id=? AND letter=?',(clean(content),qid,letter))
            transfer.migrate(db)
            db.execute("UPDATE transfer_meta SET value=? WHERE key='bank_id'",(transfer.uid(),))
            db.commit()
        finally:db.close()
        (BANKS/(key+'.json')).write_text(json.dumps({'name':Path(name).stem[:80] or 'Imported bank'}),encoding='utf-8')
        return key
    except Exception:
        path.unlink(missing_ok=True);raise

@contextmanager
def connect(path=None):
    db=sqlite3.connect(path or DB,timeout=15);db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute("CREATE TABLE IF NOT EXISTS personal_difficulty(question_id TEXT PRIMARY KEY REFERENCES questions(id),rating TEXT NOT NULL CHECK(rating IN ('easy','medium','hard')),updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    transfer.migrate(db);db.commit()
    try:
        with db:yield db
    finally:db.close()

BASE='''SELECT q.id,q.skill_id,q.difficulty,q.passage_html,q.prompt_html,q.answer_type,s.name skill,d.name domain,d.id domain_id,
 (SELECT rating FROM personal_difficulty WHERE question_id=q.id) my_difficulty,
 a.is_correct latest_correct,a.guessed latest_guessed,a.answered_at last_attempt,
 COALESCE(r.needs_review,0) needs_review,
 (SELECT COUNT(*) FROM attempts WHERE question_id=q.id) attempt_count
 FROM questions q JOIN skills s ON s.id=q.skill_id JOIN domains d ON d.id=s.domain_id
 LEFT JOIN attempts a ON a.id=(SELECT id FROM attempts WHERE question_id=q.id ORDER BY julianday(answered_at) DESC,COALESCE((SELECT sync_id FROM attempt_ids WHERE attempt_id=attempts.id),printf('%020d',id)) DESC LIMIT 1)
 LEFT JOIN review_state r ON r.question_id=q.id'''

class Handler(BaseHTTPRequestHandler):
    def respond(self,data,status=200):
        raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

    def do_GET(self):
        try: self.get()
        except (ValueError,KeyError) as exc: self.respond({'error':str(exc)},400)
        except Exception:
            traceback.print_exc();self.respond({'error':'Unable to load data. Please try again.'},500)

    def get(self):
        parsed=urlsplit(self.path);path=unquote(parsed.path);params=parse_qs(parsed.query)
        if path=='/phone':self.send_response(302);self.send_header('Location','/phone/');self.end_headers();return
        if path=='/api/banks':
            banks=[{'id':'main','name':'SAT English · original bank'}]
            if MATH_DB.is_file():banks.append({'id':'math','name':'SAT Math · original bank'})
            for file in sorted(BANKS.glob('*.db')):
                label=file.with_suffix('.json')
                banks.append({'id':file.stem,'name':json.loads(label.read_text(encoding='utf-8'))['name'] if label.exists() else file.stem})
            self.respond(banks);return
        bank=params.get('bank',['main'])[0]
        with connect(bank_path(bank)) as db:
            if path=='/api/meta':
                self.respond({
                    'domains':[dict(r) for r in db.execute('SELECT * FROM domains')],
                    'skills':[dict(r) for r in db.execute('SELECT * FROM skills')],
                    'tags':[dict(r) for r in db.execute('SELECT * FROM tags ORDER BY name')]
                });return
            if path=='/api/questions':
                conditions=[];values=[]
                for key,column in [('domain','d.id'),('skill','s.id'),('difficulty','q.difficulty')]:
                    if params.get(key,[''])[0]:conditions.append(column+'=?');values.append(params[key][0])
                status=params.get('status',[''])[0]
                statuses={'unseen':'a.id IS NULL','correct':'a.is_correct=1','incorrect':'a.is_correct=0','review':'r.needs_review=1','guessed':'a.guessed=1','done':'a.id IS NOT NULL'}
                if status in statuses:conditions.append(statuses[status])
                personal=params.get('my_difficulty',[''])[0]
                if personal=='unrated':conditions.append('NOT EXISTS(SELECT 1 FROM personal_difficulty WHERE question_id=q.id)')
                elif personal in ('easy','medium','hard'):
                    conditions.append('EXISTS(SELECT 1 FROM personal_difficulty WHERE question_id=q.id AND rating=?)');values.append(personal)
                if params.get('tag',[''])[0]:conditions.append('EXISTS(SELECT 1 FROM question_tags WHERE question_id=q.id AND tag_id=?)');values.append(params['tag'][0])
                search=params.get('search',[''])[0].strip()
                if search:conditions.append('(q.id LIKE ? OR q.passage_html LIKE ?)');values.extend(['%'+search+'%']*2)
                query=BASE+(' WHERE '+' AND '.join(conditions) if conditions else '')+' ORDER BY q.rowid'
                self.respond([dict(r) for r in db.execute(query,values)]);return
            if path=='/api/stats':
                total=db.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
                done=db.execute('SELECT COUNT(DISTINCT question_id) FROM attempts').fetchone()[0]
                first=db.execute("SELECT COUNT(*),COALESCE(SUM(is_correct),0) FROM attempts a WHERE id=(SELECT id FROM attempts WHERE question_id=a.question_id ORDER BY julianday(answered_at),COALESCE((SELECT sync_id FROM attempt_ids WHERE attempt_id=attempts.id),printf('%020d',id)) LIMIT 1)").fetchone()
                review=db.execute('SELECT COUNT(*) FROM review_state WHERE needs_review=1').fetchone()[0]
                timed=db.execute('SELECT COUNT(*),AVG(elapsed_ms) FROM attempts WHERE elapsed_ms IS NOT NULL').fetchone()
                skills=[dict(r) for r in db.execute('''SELECT s.name,s.id,COUNT(q.id) total,
                SUM(CASE WHEN a.id IS NOT NULL THEN 1 ELSE 0 END) done,COALESCE(SUM(a.is_correct),0) correct,
                AVG(a.elapsed_ms) average_ms
                FROM skills s JOIN questions q ON q.skill_id=s.id LEFT JOIN attempts a
                ON a.id=(SELECT id FROM attempts WHERE question_id=q.id ORDER BY julianday(answered_at),COALESCE((SELECT sync_id FROM attempt_ids WHERE attempt_id=attempts.id),printf('%020d',id)) LIMIT 1) GROUP BY s.id''')]
                for k in skills:k['average_ms']=round(k['average_ms']) if k['average_ms'] is not None else None
                self.respond(dict(total=total,done=done,first_correct=first[1],review=review,timed=timed[0],average_ms=round(timed[1]) if timed[1] is not None else None,skills=skills));return
            if path.startswith('/api/question/'):
                qid=path.rsplit('/',1)[-1];row=db.execute(BASE+' WHERE q.id=?',(qid,)).fetchone()
                if not row:self.respond({'error':'Question not found'},404);return
                data=dict(row)
                data['choices']=[dict(r) for r in db.execute('SELECT letter,content_html FROM choices WHERE question_id=? ORDER BY letter',(qid,))]
                data['assets']=[dict(r) for r in db.execute('SELECT file_path,alt_text FROM assets WHERE question_id=?',(qid,)) if (ROOT/r['file_path']).is_file()] if bank=='main' else []
                note=db.execute('SELECT content FROM notes WHERE question_id=?',(qid,)).fetchone();data['note']=note[0] if note else ''
                data['tags']=[r[0] for r in db.execute('SELECT name FROM tags JOIN question_tags ON tag_id=tags.id WHERE question_id=? ORDER BY name',(qid,))]
                data['history']=[dict(r) for r in db.execute("SELECT * FROM attempts WHERE question_id=? ORDER BY julianday(answered_at) DESC,COALESCE((SELECT sync_id FROM attempt_ids WHERE attempt_id=attempts.id),printf('%020d',id)) DESC",(qid,))]
                data['sources']=[dict(r) for r in db.execute('SELECT filename,page_start,page_end FROM sources JOIN question_sources ON source_id=sources.id WHERE question_id=?',(qid,))]
                self.respond(data);return
            if path=='/api/export':
                data=transfer.export_bank(db);self.respond(data);return
            if path=='/api/backup':
                transfer.capture(db);db.commit()
                fd,name=tempfile.mkstemp(suffix='.db');os.close(fd)
                try:
                    target=sqlite3.connect(name);db.backup(target);target.close();raw=Path(name).read_bytes()
                finally:os.unlink(name)
                self.send_response(200);self.send_header('Content-Type','application/vnd.sqlite3');self.send_header('Content-Disposition','attachment; filename="sat-backup.db"');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
        # Explicit public directories only: never expose the database or server source.
        if path in ('/','/index.html'):file=ROOT/'web'/'index.html'
        elif path in ('/phone','/phone/'):file=ROOT/'docs'/'index.html'
        elif path.startswith('/phone/'):file=ROOT/'docs'/path[len('/phone/'):]
        elif path.startswith('/assets/'):file=ROOT/path.lstrip('/')
        elif path.startswith('/web/'):file=ROOT/path.lstrip('/')
        else:self.respond({'error':'Not found'},404);return
        file=file.resolve()
        if not any(file.is_relative_to(ROOT/d) for d in ('web','assets','docs')) or not file.is_file():self.respond({'error':'Not found'},404);return
        raw=file.read_bytes();self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(file.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw)

    def do_POST(self):
        # Prevent other websites from writing to the local trainer.
        origin=self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
            self.respond({'error':'Origin not allowed'},403);return
        if self.path=='/api/banks/import':
            try:
                if self.headers.get('Content-Type')!='application/octet-stream':raise ValueError('Expected a database file')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=50*1024*1024:raise ValueError('Choose a database under 50 MB')
                raw=self.rfile.read(length)
                if len(raw)!=length:raise ValueError('Upload was incomplete')
                filename=unquote(self.headers.get('X-Filename','Imported bank.db'))
                mode=self.headers.get('X-Import-Mode','add')
                if mode not in ('add','merge'):raise ValueError('Choose add or merge')
                if raw.startswith(b'SQLite format 3\x00'):
                    key=import_bank(raw,filename)
                    if mode=='add':self.respond({'id':key});return
                    try:
                        with connect(bank_path(key)) as source:incoming=transfer.export_bank(source)
                    finally:
                        (BANKS/(key+'.db')).unlink(missing_ok=True);(BANKS/(key+'.json')).unlink(missing_ok=True)
                else:incoming=transfer.validate(json.loads(raw))
                report={}
                if mode=='merge':
                    key=self.headers.get('X-SAT-Bank','main')
                    with connect(bank_path(key)) as target:
                        merged,report=transfer.merge(transfer.export_bank(target),incoming);transfer.store(target,merged)
                else:
                    BANKS.mkdir(exist_ok=True);key=uuid.uuid4().hex;path=BANKS/(key+'.db')
                    try:
                        with sqlite3.connect(path) as target:
                            target.row_factory=sqlite3.Row;target.executescript((ROOT/'schema.sql').read_text());transfer.store(target,incoming)
                        (BANKS/(key+'.json')).write_text(json.dumps({'name':incoming['bank']['name'][:80]}),encoding='utf-8')
                    except Exception:path.unlink(missing_ok=True);raise
                self.respond({'id':key,**report});return
            except (ValueError,sqlite3.Error,KeyError,TypeError,RecursionError) as exc:self.respond({'error':str(exc) or 'Invalid transfer file'},400);return
        if not self.headers.get('Content-Type','').startswith('application/json'):
            self.respond({'error':'Expected JSON'},415);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=100000:raise ValueError('Invalid request size')
            data=json.loads(self.rfile.read(length));qid=data.get('question_id')
            with connect(bank_path(self.headers.get('X-SAT-Bank','main'))) as db:
                q=db.execute('SELECT * FROM questions WHERE id=?',(qid,)).fetchone()
                if not q:self.respond({'error':'Question not found'},404);return
                if self.path=='/api/attempt':
                    selected=data.get('answer');guessed=data.get('guessed',False)
                    if not isinstance(selected,str) or len(selected)>30 or (q['answer_type']=='choice' and selected not in ('A','B','C','D')) or (q['answer_type']=='numeric' and transfer.numeric(selected) is None):raise ValueError('Choose A, B, C, or D' if q['answer_type']=='choice' else 'Enter a number, decimal, or fraction')
                    if not isinstance(guessed,bool):raise ValueError('Invalid guessed value')
                    spent=transfer.elapsed(data.get('elapsed_ms'))
                    selected=selected.strip().replace('−','-');question=dict(q);question['accepted_answers']=json.loads(q['accepted_answers']);correct=transfer.answer_correct(question,selected)
                    cur=db.execute('INSERT INTO attempts(question_id,selected_answer,is_correct,guessed,elapsed_ms) VALUES (?,?,?,?,?)',(qid,selected,int(correct),int(guessed),spent))
                    db.execute('UPDATE attempts SET answered_at=? WHERE id=?',(transfer.now(),cur.lastrowid))
                    db.execute('INSERT INTO attempt_ids VALUES (?,?)',(cur.lastrowid,transfer.uid()))
                    review=int(not correct or guessed)
                    db.execute('INSERT INTO review_state(question_id,needs_review) VALUES (?,?) ON CONFLICT(question_id) DO UPDATE SET needs_review=excluded.needs_review,updated_at=CURRENT_TIMESTAMP',(qid,review))
                    result=dict(attempt_id=cur.lastrowid,is_correct=correct,correct_answer=q['correct_answer'],explanation_html=q['explanation_html'],needs_review=review)
                elif self.path=='/api/difficulty':
                    rating=data.get('rating')
                    if rating not in ('easy','medium','hard'):raise ValueError('Choose easy, medium, or hard')
                    db.execute('INSERT INTO personal_difficulty(question_id,rating) VALUES (?,?) ON CONFLICT(question_id) DO UPDATE SET rating=excluded.rating,updated_at=CURRENT_TIMESTAMP',(qid,rating));result={'saved':True}
                elif self.path=='/api/note':
                    content=data.get('content','')
                    if not isinstance(content,str) or len(content)>20000:raise ValueError('Note is too long')
                    db.execute('INSERT INTO notes(question_id,content) VALUES (?,?) ON CONFLICT(question_id) DO UPDATE SET content=excluded.content,updated_at=CURRENT_TIMESTAMP',(qid,content));result={'saved':True}
                elif self.path=='/api/review':
                    value=data.get('needs_review')
                    if not isinstance(value,bool):raise ValueError('Invalid review status')
                    db.execute('INSERT INTO review_state(question_id,needs_review) VALUES (?,?) ON CONFLICT(question_id) DO UPDATE SET needs_review=excluded.needs_review,updated_at=CURRENT_TIMESTAMP',(qid,int(value)));result={'saved':True}
                elif self.path=='/api/tags':
                    tags=data.get('tags',[])
                    if not isinstance(tags,list) or len(tags)>20 or any(not isinstance(t,str) or not 0<len(t.strip())<=60 for t in tags):raise ValueError('Use up to 20 tags, each 1–60 characters')
                    db.execute('DELETE FROM question_tags WHERE question_id=?',(qid,))
                    for tag in tags:
                        db.execute('INSERT OR IGNORE INTO tags(name) VALUES (?)',(tag.strip(),));tid=db.execute('SELECT id FROM tags WHERE name=? COLLATE NOCASE',(tag.strip(),)).fetchone()[0]
                        db.execute('INSERT OR IGNORE INTO question_tags VALUES (?,?)',(qid,tid))
                    result={'saved':True}
                else:self.respond({'error':'Not found'},404);return
                table={'/api/note':'notes','/api/difficulty':'personal_difficulty','/api/review':'review_state','/api/attempt':'review_state'}.get(self.path)
                if table:db.execute('UPDATE '+table+' SET updated_at=? WHERE question_id=?',(transfer.now(),qid))
                transfer.capture(db)
            self.respond(result)
        except (ValueError,TypeError,KeyError) as exc:self.respond({'error':str(exc)},400)
        except Exception:
            traceback.print_exc();self.respond({'error':'Could not save. Please try again.'},500)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--db',type=Path,default=DB);p.add_argument('--open',action='store_true',help='Open the trainer in your default browser');args=p.parse_args();DB=args.db.resolve()
    initialize_database(DB)
    initialize_database(MATH_DB,ROOT/'sat-math-clean.db')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'SAT Trainer running at http://127.0.0.1:{args.port}',flush=True)
    if args.open:threading.Timer(0.5,lambda:webbrowser.open(f'http://127.0.0.1:{args.port}')).start()
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()
