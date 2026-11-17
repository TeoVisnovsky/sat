"""Versioned, device-independent bank snapshots. No network or third-party packages."""
import json, uuid, re, unicodedata
from fractions import Fraction
from datetime import datetime, timezone
from recover_prompts import clean

FIELDS=('id','domain','skill','difficulty','passage_html','prompt_html','answer_type','correct_answer','accepted_answers','explanation_html','choices','exam_id','year','ordinal','stimulus_id','subcategory','knowledge_source','requires_stimulus','answer_notes')
LEVELS=('easy','medium','hard','introductory','standard','challenging')
PERSONAL_LEVELS=('easy','medium','hard')
def now():return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
def uid():return str(uuid.uuid4())
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def stamp(s):
    if not isinstance(s,str):raise ValueError('Missing timestamp')
    try:
        dt=datetime.fromisoformat(s.replace('Z','+00:00'))
        return (dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat(timespec='milliseconds').replace('+00:00','Z')
    except ValueError:raise ValueError('Invalid timestamp')

def migrate(db):
    db.execute('CREATE TABLE IF NOT EXISTS transfer_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS attempt_ids(attempt_id INTEGER PRIMARY KEY REFERENCES attempts(id),sync_id TEXT NOT NULL UNIQUE)')
    db.execute('CREATE TABLE IF NOT EXISTS note_versions(id TEXT PRIMARY KEY,question_id TEXT NOT NULL REFERENCES questions(id),content TEXT NOT NULL,updated_at TEXT NOT NULL,parents TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS state_versions(kind TEXT NOT NULL,question_id TEXT NOT NULL REFERENCES questions(id),id TEXT NOT NULL,updated_at TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(kind,question_id))')
    db.execute('CREATE TABLE IF NOT EXISTS full_test_sessions(id TEXT PRIMARY KEY,year INTEGER NOT NULL,timed INTEGER NOT NULL CHECK(timed IN (0,1)),started_at TEXT NOT NULL,submitted_at TEXT NOT NULL,elapsed_ms INTEGER NOT NULL,total INTEGER NOT NULL,answered INTEGER NOT NULL,score INTEGER NOT NULL,results TEXT NOT NULL)')
    columns={r[1] for r in db.execute('PRAGMA table_info(questions)')}
    if 'answer_type' not in columns:db.execute("ALTER TABLE questions ADD COLUMN answer_type TEXT NOT NULL DEFAULT 'choice'")
    if 'accepted_answers' not in columns:
        db.execute("ALTER TABLE questions ADD COLUMN accepted_answers TEXT NOT NULL DEFAULT '[]'")
        db.execute("UPDATE questions SET accepted_answers=json_array(correct_answer)")
    if 'elapsed_ms' not in {r[1] for r in db.execute('PRAGMA table_info(attempts)')}:
        db.execute('ALTER TABLE attempts ADD COLUMN elapsed_ms INTEGER')
    db.execute("CREATE TABLE IF NOT EXISTS exams(id TEXT PRIMARY KEY,subject TEXT NOT NULL,year INTEGER NOT NULL,canonical_code TEXT NOT NULL DEFAULT '',level TEXT NOT NULL DEFAULT '',duration_minutes INTEGER,source_url TEXT NOT NULL DEFAULT '',UNIQUE(subject,year,level))")
    db.execute("CREATE TABLE IF NOT EXISTS stimuli(id TEXT PRIMARY KEY,exam_id TEXT NOT NULL REFERENCES exams(id),ordinal INTEGER NOT NULL,title TEXT NOT NULL DEFAULT '',content_html TEXT NOT NULL DEFAULT '',stimulus_type TEXT NOT NULL DEFAULT '',source_page_start INTEGER,source_page_end INTEGER,UNIQUE(exam_id,ordinal))")
    additions={
        'exam_id':'TEXT REFERENCES exams(id)','ordinal':'INTEGER','stimulus_id':'TEXT REFERENCES stimuli(id)',
        'subcategory':"TEXT NOT NULL DEFAULT ''",'knowledge_source':"TEXT NOT NULL DEFAULT ''",
        'requires_stimulus':'INTEGER NOT NULL DEFAULT 0','answer_notes':"TEXT NOT NULL DEFAULT ''",
    }
    columns={r[1] for r in db.execute('PRAGMA table_info(questions)')}
    for name,definition in additions.items():
        if name not in columns:db.execute(f'ALTER TABLE questions ADD COLUMN {name} {definition}')
    db.execute('CREATE INDEX IF NOT EXISTS idx_questions_exam_order ON questions(exam_id,ordinal)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_questions_stimulus ON questions(stimulus_id,ordinal)')
    db.execute('INSERT OR IGNORE INTO transfer_meta VALUES (?,?)',('bank_id',uid()))

ELAPSED_LIMIT=7200000
def elapsed(value):
    """Question timings are optional, but a present value must be a plain, sane millisecond count.
    Booleans are rejected explicitly: isinstance(True,int) is True in Python but not in JavaScript,
    and the two runtimes have to agree on what they accept."""
    if value is None:return None
    if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=ELAPSED_LIMIT:raise ValueError('Invalid question time')
    return value

def numeric(value):
    if not isinstance(value,str):return None
    value=value.strip().replace('\N{MINUS SIGN}','-').replace(' ','').replace(',','.')
    if len(value)>30 or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+|\d+/[+-]?\d+)',value):return None
    try:return Fraction(value)
    except (ValueError,ZeroDivisionError):return None

def normalized_text(value):
    value=unicodedata.normalize('NFKC',str(value)).casefold().strip()
    return re.sub(r'[^\w]+',' ',value,flags=re.UNICODE).strip()

def answer_correct(question,answer):
    kind=question.get('answer_type','choice')
    if kind=='choice':return answer in (question.get('accepted_answers') or [question['correct_answer']])
    if kind=='numeric':
        value=numeric(answer)
        return value is not None and any(numeric(x)==value for x in question.get('accepted_answers',[]))
    value=normalized_text(answer)
    return bool(value) and any(normalized_text(x)==value for x in question.get('accepted_answers',[]))

def note_leaves(versions):
    parents={p for v in versions for p in v['parents']}
    return sorted([v for v in versions if v['id'] not in parents],key=lambda v:(v['updated_at'],v['id']))
def note_text(versions):
    texts=list(dict.fromkeys(v['content'] for v in note_leaves(versions)))
    return '\n\n—— Other device’s note ——\n\n'.join(texts)
def versions(db,qid):
    return [dict(r,parents=json.loads(r['parents'])) for r in db.execute('SELECT * FROM note_versions WHERE question_id=?',(qid,))]

def capture(db):
    """Upgrade legacy records once; subsequent local edits get new immutable IDs."""
    migrate(db)
    for r in db.execute('SELECT a.* FROM attempts a LEFT JOIN attempt_ids i ON i.attempt_id=a.id WHERE i.sync_id IS NULL').fetchall():
        # Old, independently copied SQLite backups identify their common legacy rows identically.
        identity=canonical({k:r[k] for k in ('id','question_id','selected_answer','is_correct','guessed','answered_at')})
        legacy_id='legacy-'+str(r['id']).zfill(20)+'-'+uuid.uuid5(uuid.NAMESPACE_URL,'sat-legacy-attempt:'+identity).hex
        db.execute('INSERT INTO attempt_ids VALUES (?,?)',(r['id'],legacy_id))
    for r in db.execute('SELECT * FROM notes').fetchall():
        old=versions(db,r['question_id'])
        if not old or note_text(old)!=r['content']:
            ident=uid() if old else str(uuid.uuid5(uuid.NAMESPACE_URL,'sat-legacy-note:'+canonical(dict(r))))
            db.execute('INSERT OR IGNORE INTO note_versions VALUES (?,?,?,?,?)',(ident,r['question_id'],r['content'],stamp(r['updated_at']),json.dumps([v['id'] for v in note_leaves(old)])))
    for kind,table,col in [('ratings','personal_difficulty','rating'),('reviews','review_state','needs_review')]:
        for r in db.execute('SELECT * FROM '+table).fetchall():
            val=canonical(r[col]);ts=stamp(r['updated_at'])
            old=db.execute('SELECT * FROM state_versions WHERE kind=? AND question_id=?',(kind,r['question_id'])).fetchone()
            if not old or old['value']!=val or old['updated_at']!=ts:
                db.execute('INSERT OR REPLACE INTO state_versions VALUES (?,?,?,?,?)',(kind,r['question_id'],uid(),ts,val))

def export_bank(db,name='SAT English'):
    capture(db)
    result={'format':'sat-bank','version':2,'bank':{'id':db.execute("SELECT value FROM transfer_meta WHERE key='bank_id'").fetchone()[0],'name':name},'exams':[dict(r) for r in db.execute('SELECT * FROM exams ORDER BY subject,year')],'stimuli':[dict(r) for r in db.execute('SELECT * FROM stimuli ORDER BY exam_id,ordinal')],'questions':[],'attempts':[],'notes':[],'ratings':[],'reviews':[],'tags':[],'test_sessions':[]}
    for r in db.execute('SELECT q.*,s.name skill,d.name domain,e.year FROM questions q JOIN skills s ON s.id=q.skill_id JOIN domains d ON d.id=s.domain_id LEFT JOIN exams e ON e.id=q.exam_id ORDER BY q.rowid'):
        q={k:r[k] for k in FIELDS if k not in ('choices','accepted_answers')}
        q['accepted_answers']=json.loads(r['accepted_answers'])
        q['choices']=[dict(c) for c in db.execute('SELECT letter,content_html FROM choices WHERE question_id=? ORDER BY letter',(q['id'],))]
        q['sources']=[dict(s) for s in db.execute('SELECT filename,file_sha256,page_start,page_end FROM sources JOIN question_sources ON source_id=sources.id WHERE question_id=?',(q['id'],))]
        result['questions'].append(q)
    for r in db.execute('SELECT a.*,i.sync_id FROM attempts a JOIN attempt_ids i ON i.attempt_id=a.id'):
        result['attempts'].append(dict(id=r['sync_id'],question_id=r['question_id'],selected_answer=r['selected_answer'],is_correct=r['is_correct'],guessed=r['guessed'],elapsed_ms=elapsed(r['elapsed_ms']),answered_at=stamp(r['answered_at'])))
    for r in db.execute('SELECT * FROM note_versions'):result['notes'].append(dict(r,parents=json.loads(r['parents'])))
    for r in db.execute('SELECT * FROM state_versions'):
        result[r['kind']].append(dict(id=r['id'],question_id=r['question_id'],updated_at=r['updated_at'],**{('rating' if r['kind']=='ratings' else 'needs_review'):json.loads(r['value'])}))
    result['tags']=[dict(r) for r in db.execute('SELECT question_id,name FROM question_tags JOIN tags ON tags.id=tag_id')]
    result['test_sessions']=[dict(r, timed=bool(r['timed']),results=json.loads(r['results'])) for r in db.execute('SELECT * FROM full_test_sessions ORDER BY submitted_at')]
    return result

def validate(data):
    if not isinstance(data,dict) or data.get('format')!='sat-bank' or data.get('version') not in (1,2):raise ValueError('Choose a SAT bank transfer file (version 1 or 2).')
    data.setdefault('exams',[]);data.setdefault('stimuli',[]);data.setdefault('test_sessions',[])
    def text(x,limit=200000):
        if not isinstance(x,str) or len(x)>limit:raise ValueError('Invalid text in transfer file')
        return x
    def identity(x):
        if not isinstance(x,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',x):raise ValueError('Invalid record ID')
        return x
    identity(data['bank']['id']);text(data['bank']['name'],100)
    for key in ['questions','attempts','notes','ratings','reviews','tags']:
        if not isinstance(data.get(key),list) or len(data[key])>200000:raise ValueError('Invalid or oversized record collection')
    if not isinstance(data['test_sessions'],list) or len(data['test_sessions'])>10000:raise ValueError('Invalid test history')
    qs={}
    for q in data['questions']:
        identity(q['id'])
        if q['id'] in qs:raise ValueError('Duplicate question ID')
        qs[q['id']]=q
        for key in ['domain','skill']:text(q[key],200)
        q.setdefault('answer_type','choice');q.setdefault('accepted_answers',[q.get('correct_answer')])
        for key,default in [('exam_id',None),('year',None),('ordinal',None),('stimulus_id',None),('subcategory',''),('knowledge_source',''),('requires_stimulus',False),('answer_notes','')]:q.setdefault(key,default)
        if q['difficulty'] not in LEVELS or q['answer_type'] not in ('choice','numeric','text'):raise ValueError('Invalid question answer or difficulty')
        if q['answer_type']=='numeric':
            if not isinstance(q['accepted_answers'],list) or not q['accepted_answers'] or any(not isinstance(x,str) or not x.strip() or numeric(x) is None for x in q['accepted_answers']):raise ValueError('Invalid question answer')
        elif q['answer_type']=='text':
            if not isinstance(q['accepted_answers'],list) or not q['accepted_answers'] or any(not isinstance(x,str) or not x.strip() for x in q['accepted_answers']):raise ValueError('Invalid text answer')
        elif q['correct_answer'] not in list('ABCDE'):raise ValueError('Invalid question answer')
        for key in ['passage_html','prompt_html','explanation_html']:q[key]=clean(text(q[key]))
        if not q['prompt_html'].strip():raise ValueError('Question prompt is empty')
        letters=sorted(c['letter'] for c in q['choices']) if isinstance(q.get('choices'),list) else []
        if (q['answer_type']=='choice' and letters not in (list('ABCD'),list('ABCDE'))) or (q['answer_type']!='choice' and letters):raise ValueError('Answer choices do not match the question type')
        q['choices']=sorted([{'letter':c['letter'],'content_html':clean(text(c['content_html']))} for c in q['choices']],key=lambda c:c['letter'])
        for s in q.get('sources',[]):
            text(s['filename'],250);text(s['file_sha256'],100)
            if not isinstance(s['page_start'],int) or not isinstance(s['page_end'],int) or not 1<=s['page_start']<=s['page_end']:raise ValueError('Invalid source page')
    for key in ['attempts','notes','ratings','reviews','tags']:
        seen=set()
        for r in data[key]:
            if r['question_id'] not in qs:raise ValueError('Record refers to an absent question')
            if key=='tags':
                text(r['name'],60)
                if not r['name'].strip():raise ValueError('Empty tag')
                continue
            ident=identity(r['id'])
            unique=r['question_id'] if key in ('ratings','reviews') else ident
            if unique in seen:raise ValueError('Duplicate record ID')
            seen.add(unique)
            date='answered_at' if key=='attempts' else 'updated_at';r[date]=stamp(r[date])
            if key=='attempts':
                if not isinstance(r['selected_answer'],str) or len(r['selected_answer'])>500 or r['guessed'] not in (0,1) or r['is_correct']!=int(answer_correct(qs[r['question_id']],r['selected_answer'])):raise ValueError('Invalid attempt')
                r['guessed']=int(r['guessed']);r['is_correct']=int(r['is_correct']);r['elapsed_ms']=elapsed(r.get('elapsed_ms'))
            elif key=='notes':
                text(r['content'],20000)
                if not isinstance(r['parents'],list):raise ValueError('Invalid note revisions')
            elif key=='ratings' and r['rating'] not in PERSONAL_LEVELS:raise ValueError('Invalid personal difficulty')
            elif key=='reviews':
                if r['needs_review'] not in (0,1):raise ValueError('Invalid review state')
                r['needs_review']=int(r['needs_review'])
    notes={v['id']:v for v in data['notes']};done=set();active=set()
    def visit(ident):
        if ident in active:raise ValueError('Cyclic note history')
        if ident in done:return
        active.add(ident)
        for parent in notes[ident]['parents']:
            if parent not in notes or notes[parent]['question_id']!=notes[ident]['question_id']:raise ValueError('Broken note history')
            visit(parent)
        active.remove(ident);done.add(ident)
    for ident in notes:visit(ident)
    session_ids=set()
    for s in data['test_sessions']:
        identity(s['id'])
        if s['id'] in session_ids:raise ValueError('Duplicate test session')
        session_ids.add(s['id'])
        if not isinstance(s.get('year'),int) or not isinstance(s.get('timed'),bool) or not all(isinstance(s.get(k),int) and s[k]>=0 for k in ('elapsed_ms','total','answered','score')) or s['answered']>s['total'] or s['score']>s['answered']:raise ValueError('Invalid test result')
        s['started_at']=stamp(s['started_at']);s['submitted_at']=stamp(s['submitted_at'])
        if not isinstance(s.get('results'),list) or any(r.get('question_id') not in qs or not isinstance(r.get('selected_answer'),str) or not isinstance(r.get('correct_answer'),str) or r.get('is_correct') not in (0,1) or r.get('guessed') not in (0,1) for r in s['results']):raise ValueError('Invalid test answers')
    return data

def merge(local,incoming):
    """Atomic conflict rejection; all other records merge idempotently."""
    questions={q['id']:q for q in local['questions']};conflicts=[]
    for q in incoming['questions']:
        if q['id'] in questions and any(canonical(q[k])!=canonical(questions[q['id']][k]) for k in FIELDS):conflicts.append(q['id'])
    if conflicts:raise ValueError('Question content differs for '+', '.join(conflicts[:12])+'. Nothing was merged. Import as a separate database to review both versions.')
    report={'questions_added':0,'attempts_added':0,'note_conflicts':0}
    for q in incoming['questions']:
        if q['id'] not in questions:local['questions'].append(q);questions[q['id']]=q;report['questions_added']+=1
        else:
            sources={canonical(s):s for s in questions[q['id']].get('sources',[])+q.get('sources',[])};questions[q['id']]['sources']=list(sources.values())
    # A question time is additive metadata: one side may simply not know it, so it is
    # filled in rather than treated as history that disagrees.
    bare=lambda key,r:{**r,'elapsed_ms':None} if key=='attempts' else r
    for key in ['attempts','notes']:
        records={r['id']:r for r in local[key]}
        for r in incoming[key]:
            old=records.get(r['id'])
            if old is not None:
                if key=='attempts' and old.get('elapsed_ms') is None and r.get('elapsed_ms') is not None:old['elapsed_ms']=r['elapsed_ms']
                if canonical(bare(key,r))!=canonical(bare(key,old)):raise ValueError('Conflicting history ID. Nothing was merged; add this as a separate database.')
                continue
            local[key].append(r);records[r['id']]=r;report['attempts_added']+=int(key=='attempts')
    for key in ['ratings','reviews']:
        records={r['question_id']:r for r in local[key]}
        for r in incoming[key]:
            old=records.get(r['question_id'])
            if old and r['id']==old['id'] and canonical(r)!=canonical(old):raise ValueError('Conflicting state ID. Nothing was merged; add this as a separate database.')
            if old is None or (r['updated_at'],r['id'])>(old['updated_at'],old['id']):records[r['question_id']]=r
        local[key]=list(records.values())
    tags={(r['question_id'],r['name'].lower()):r for r in local['tags']}
    for r in incoming['tags']:tags.setdefault((r['question_id'],r['name'].lower()),r)
    local['tags']=list(tags.values())
    local.setdefault('test_sessions',[]);sessions={s['id']:s for s in local['test_sessions']}
    for s in incoming.get('test_sessions',[]):
        if s['id'] in sessions and canonical(sessions[s['id']])!=canonical(s):raise ValueError('Conflicting test session. Nothing was merged; add this as a separate database.')
        if s['id'] not in sessions:local['test_sessions'].append(s);sessions[s['id']]=s
    report['note_conflicts']=sum(len(set(v['content'] for v in note_leaves([n for n in local['notes'] if n['question_id']==qid])))>1 for qid in {n['question_id'] for n in local['notes']})
    return local,report

def store(db,data):
    migrate(db)
    for e in data.get('exams',[]):
        db.execute('INSERT OR IGNORE INTO exams(id,subject,year,canonical_code,level,duration_minutes,source_url) VALUES (?,?,?,?,?,?,?)',tuple(e.get(k) for k in ('id','subject','year','canonical_code','level','duration_minutes','source_url')))
    for s in data.get('stimuli',[]):
        db.execute('INSERT OR IGNORE INTO stimuli(id,exam_id,ordinal,title,content_html,stimulus_type,source_page_start,source_page_end) VALUES (?,?,?,?,?,?,?,?)',tuple(s.get(k) for k in ('id','exam_id','ordinal','title','content_html','stimulus_type','source_page_start','source_page_end')))
    for q in data['questions']:
        db.execute('INSERT OR IGNORE INTO domains(name) VALUES (?)',(q['domain'],));did=db.execute('SELECT id FROM domains WHERE name=?',(q['domain'],)).fetchone()[0]
        db.execute('INSERT OR IGNORE INTO skills(domain_id,name) VALUES (?,?)',(did,q['skill']));sid=db.execute('SELECT id FROM skills WHERE domain_id=? AND name=?',(did,q['skill'])).fetchone()[0]
        db.execute('INSERT OR IGNORE INTO questions(id,skill_id,difficulty,passage_html,prompt_html,answer_type,correct_answer,accepted_answers,explanation_html,exam_id,ordinal,stimulus_id,subcategory,knowledge_source,requires_stimulus,answer_notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(q['id'],sid,q['difficulty'],q['passage_html'],q['prompt_html'],q['answer_type'],q['correct_answer'],canonical(q['accepted_answers']),q['explanation_html'],q.get('exam_id'),q.get('ordinal'),q.get('stimulus_id'),q.get('subcategory',''),q.get('knowledge_source',''),int(bool(q.get('requires_stimulus'))),q.get('answer_notes','')))
        for c in q['choices']:db.execute('INSERT OR IGNORE INTO choices VALUES (?,?,?)',(q['id'],c['letter'],c['content_html']))
        for s in q.get('sources',[]):
            db.execute('INSERT OR IGNORE INTO sources(filename,file_sha256) VALUES (?,?)',(s['filename'],s['file_sha256']));sid=db.execute('SELECT id FROM sources WHERE file_sha256=?',(s['file_sha256'],)).fetchone()[0]
            db.execute('INSERT OR IGNORE INTO question_sources VALUES (?,?,?,?)',(q['id'],sid,s['page_start'],s['page_end']))
    ids={r[0] for r in db.execute('SELECT sync_id FROM attempt_ids')}
    for a in sorted(data['attempts'],key=lambda a:(a['answered_at'],a['id'])):
        if a['id'] not in ids:
            cur=db.execute('INSERT INTO attempts(question_id,selected_answer,is_correct,guessed,elapsed_ms,answered_at) VALUES (?,?,?,?,?,?)',tuple(a.get(k) for k in ('question_id','selected_answer','is_correct','guessed','elapsed_ms','answered_at')))
            db.execute('INSERT INTO attempt_ids VALUES (?,?)',(cur.lastrowid,a['id']));ids.add(a['id'])
    for n in data['notes']:db.execute('INSERT OR IGNORE INTO note_versions VALUES (?,?,?,?,?)',(n['id'],n['question_id'],n['content'],n['updated_at'],json.dumps(n['parents'])))
    for qid in {n['question_id'] for n in data['notes']}:
        vs=versions(db,qid)
        db.execute('INSERT OR REPLACE INTO notes(question_id,content,updated_at) VALUES (?,?,?)',(qid,note_text(vs),max(v['updated_at'] for v in vs)))
    for kind,table,col in [('ratings','personal_difficulty','rating'),('reviews','review_state','needs_review')]:
        for r in data[kind]:
            db.execute('INSERT OR REPLACE INTO '+table+'(question_id,'+col+',updated_at) VALUES (?,?,?)',(r['question_id'],r[col],r['updated_at']))
            db.execute('INSERT OR REPLACE INTO state_versions VALUES (?,?,?,?,?)',(kind,r['question_id'],r['id'],r['updated_at'],canonical(r[col])))
    for t in data['tags']:
        db.execute('INSERT OR IGNORE INTO tags(name) VALUES (?)',(t['name'],));tid=db.execute('SELECT id FROM tags WHERE name=? COLLATE NOCASE',(t['name'],)).fetchone()[0]
        db.execute('INSERT OR IGNORE INTO question_tags VALUES (?,?)',(t['question_id'],tid))
    for s in data.get('test_sessions',[]):db.execute('INSERT OR IGNORE INTO full_test_sessions VALUES (?,?,?,?,?,?,?,?,?,?)',(s['id'],s['year'],int(s['timed']),s['started_at'],s['submitted_at'],s['elapsed_ms'],s['total'],s['answered'],s['score'],canonical(s['results'])))
