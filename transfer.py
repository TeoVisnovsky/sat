"""Versioned, device-independent bank snapshots. No network or third-party packages."""
import json, uuid, re
from fractions import Fraction
from datetime import datetime, timezone
from recover_prompts import clean

FIELDS=('id','domain','skill','difficulty','passage_html','prompt_html','answer_type','correct_answer','accepted_answers','explanation_html','choices')
LEVELS=('easy','medium','hard')
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
    columns={r[1] for r in db.execute('PRAGMA table_info(questions)')}
    if 'answer_type' not in columns:db.execute("ALTER TABLE questions ADD COLUMN answer_type TEXT NOT NULL DEFAULT 'choice'")
    if 'accepted_answers' not in columns:
        db.execute("ALTER TABLE questions ADD COLUMN accepted_answers TEXT NOT NULL DEFAULT '[]'")
        db.execute("UPDATE questions SET accepted_answers=json_array(correct_answer)")
    db.execute('INSERT OR IGNORE INTO transfer_meta VALUES (?,?)',('bank_id',uid()))

def numeric(value):
    if not isinstance(value,str):return None
    value=value.strip().replace('\N{MINUS SIGN}','-')
    if len(value)>30 or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+|\d+/[+-]?\d+)',value):return None
    try:return Fraction(value)
    except (ValueError,ZeroDivisionError):return None

def answer_correct(question,answer):
    if question.get('answer_type','choice')=='choice':return answer==question['correct_answer']
    value=numeric(answer)
    return value is not None and any(numeric(x)==value for x in question.get('accepted_answers',[]))

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
        identity=canonical(dict(r))
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
    result={'format':'sat-bank','version':1,'bank':{'id':db.execute("SELECT value FROM transfer_meta WHERE key='bank_id'").fetchone()[0],'name':name},'questions':[],'attempts':[],'notes':[],'ratings':[],'reviews':[],'tags':[]}
    for r in db.execute('SELECT q.*,s.name skill,d.name domain FROM questions q JOIN skills s ON s.id=q.skill_id JOIN domains d ON d.id=s.domain_id ORDER BY q.rowid'):
        q={k:r[k] for k in FIELDS if k not in ('choices','accepted_answers')}
        q['accepted_answers']=json.loads(r['accepted_answers'])
        q['choices']=[dict(c) for c in db.execute('SELECT letter,content_html FROM choices WHERE question_id=? ORDER BY letter',(q['id'],))]
        q['sources']=[dict(s) for s in db.execute('SELECT filename,file_sha256,page_start,page_end FROM sources JOIN question_sources ON source_id=sources.id WHERE question_id=?',(q['id'],))]
        result['questions'].append(q)
    for r in db.execute('SELECT a.*,i.sync_id FROM attempts a JOIN attempt_ids i ON i.attempt_id=a.id'):
        result['attempts'].append(dict(id=r['sync_id'],question_id=r['question_id'],selected_answer=r['selected_answer'],is_correct=r['is_correct'],guessed=r['guessed'],answered_at=stamp(r['answered_at'])))
    for r in db.execute('SELECT * FROM note_versions'):result['notes'].append(dict(r,parents=json.loads(r['parents'])))
    for r in db.execute('SELECT * FROM state_versions'):
        result[r['kind']].append(dict(id=r['id'],question_id=r['question_id'],updated_at=r['updated_at'],**{('rating' if r['kind']=='ratings' else 'needs_review'):json.loads(r['value'])}))
    result['tags']=[dict(r) for r in db.execute('SELECT question_id,name FROM question_tags JOIN tags ON tags.id=tag_id')]
    return result

def validate(data):
    if not isinstance(data,dict) or data.get('format')!='sat-bank' or data.get('version')!=1:raise ValueError('Choose a SAT bank transfer file (version 1).')
    def text(x,limit=200000):
        if not isinstance(x,str) or len(x)>limit:raise ValueError('Invalid text in transfer file')
        return x
    def identity(x):
        if not isinstance(x,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',x):raise ValueError('Invalid record ID')
        return x
    identity(data['bank']['id']);text(data['bank']['name'],100)
    for key in ['questions','attempts','notes','ratings','reviews','tags']:
        if not isinstance(data.get(key),list) or len(data[key])>200000:raise ValueError('Invalid or oversized record collection')
    qs={}
    for q in data['questions']:
        identity(q['id'])
        if q['id'] in qs:raise ValueError('Duplicate question ID')
        qs[q['id']]=q
        for key in ['domain','skill']:text(q[key],200)
        q.setdefault('answer_type','choice');q.setdefault('accepted_answers',[q.get('correct_answer')])
        if q['difficulty'] not in LEVELS or q['answer_type'] not in ('choice','numeric'):raise ValueError('Invalid question answer or difficulty')
        if q['answer_type']=='numeric':
            if not isinstance(q['accepted_answers'],list) or not q['accepted_answers'] or any(not isinstance(x,str) or not x.strip() or numeric(x) is None for x in q['accepted_answers']):raise ValueError('Invalid question answer')
        elif q['correct_answer'] not in list('ABCD'):raise ValueError('Invalid question answer')
        for key in ['passage_html','prompt_html','explanation_html']:q[key]=clean(text(q[key]))
        if not q['prompt_html'].strip():raise ValueError('Question prompt is empty')
        expected=list('ABCD') if q['answer_type']=='choice' else []
        if not isinstance(q['choices'],list) or sorted(c['letter'] for c in q['choices'])!=expected:raise ValueError('Answer choices do not match the question type')
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
                if not isinstance(r['selected_answer'],str) or len(r['selected_answer'])>30 or r['guessed'] not in (0,1) or r['is_correct']!=int(answer_correct(qs[r['question_id']],r['selected_answer'])):raise ValueError('Invalid attempt')
                r['guessed']=int(r['guessed']);r['is_correct']=int(r['is_correct'])
            elif key=='notes':
                text(r['content'],20000)
                if not isinstance(r['parents'],list):raise ValueError('Invalid note revisions')
            elif key=='ratings' and r['rating'] not in LEVELS:raise ValueError('Invalid personal difficulty')
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
    for key in ['attempts','notes']:
        records={r['id']:r for r in local[key]}
        for r in incoming[key]:
            if r['id'] in records and canonical(r)!=canonical(records[r['id']]):raise ValueError('Conflicting history ID. Nothing was merged; add this as a separate database.')
            if r['id'] not in records:local[key].append(r);records[r['id']]=r;report['attempts_added']+=int(key=='attempts')
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
    report['note_conflicts']=sum(len(set(v['content'] for v in note_leaves([n for n in local['notes'] if n['question_id']==qid])))>1 for qid in {n['question_id'] for n in local['notes']})
    return local,report

def store(db,data):
    migrate(db)
    for q in data['questions']:
        db.execute('INSERT OR IGNORE INTO domains(name) VALUES (?)',(q['domain'],));did=db.execute('SELECT id FROM domains WHERE name=?',(q['domain'],)).fetchone()[0]
        db.execute('INSERT OR IGNORE INTO skills(domain_id,name) VALUES (?,?)',(did,q['skill']));sid=db.execute('SELECT id FROM skills WHERE domain_id=? AND name=?',(did,q['skill'])).fetchone()[0]
        db.execute('INSERT OR IGNORE INTO questions(id,skill_id,difficulty,passage_html,prompt_html,answer_type,correct_answer,accepted_answers,explanation_html) VALUES (?,?,?,?,?,?,?,?,?)',(q['id'],sid,q['difficulty'],q['passage_html'],q['prompt_html'],q['answer_type'],q['correct_answer'],canonical(q['accepted_answers']),q['explanation_html']))
        for c in q['choices']:db.execute('INSERT OR IGNORE INTO choices VALUES (?,?,?)',(q['id'],c['letter'],c['content_html']))
        for s in q.get('sources',[]):
            db.execute('INSERT OR IGNORE INTO sources(filename,file_sha256) VALUES (?,?)',(s['filename'],s['file_sha256']));sid=db.execute('SELECT id FROM sources WHERE file_sha256=?',(s['file_sha256'],)).fetchone()[0]
            db.execute('INSERT OR IGNORE INTO question_sources VALUES (?,?,?,?)',(q['id'],sid,s['page_start'],s['page_end']))
    ids={r[0] for r in db.execute('SELECT sync_id FROM attempt_ids')}
    for a in sorted(data['attempts'],key=lambda a:(a['answered_at'],a['id'])):
        if a['id'] not in ids:
            cur=db.execute('INSERT INTO attempts(question_id,selected_answer,is_correct,guessed,answered_at) VALUES (?,?,?,?,?)',tuple(a[k] for k in ('question_id','selected_answer','is_correct','guessed','answered_at')))
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
