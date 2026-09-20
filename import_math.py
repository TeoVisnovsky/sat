"""Build the clean SAT Math bank from the supplied College Board answer PDFs.

The PDFs are the authoritative membership, answer-key and provenance source. The
official question-bank API is matched against their rendered text to recover
accessible MathML, tables, diagrams and explanations without OCR damage.
"""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse
import argparse, difflib, hashlib, html, json, re, sqlite3, time, unicodedata, urllib.request
import pymupdf

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / 'source-cache' / 'math'
API = 'https://qbank-api.collegeboard.org/msreportingquestionbank-prod/questionbank/'
DOMAINS = {
    'Algebra': ['Linear equations in one variable', 'Linear equations in two variables', 'Linear functions',
                'Systems of two linear equations in two variables', 'Linear inequalities in one or two variables'],
    'Advanced Math': ['Equivalent expressions', 'Nonlinear equations in one variable and systems of equations in two variables', 'Nonlinear functions'],
    'Problem-Solving and Data Analysis': ['Ratios, rates, proportional relationships, and units', 'Percentages',
                'One-variable data: Distributions and measures of center and spread', 'Two-variable data: Models and scatterplots',
                'Probability and conditional probability', 'Inference from sample statistics and margin of error',
                'Evaluating statistical claims: Observational studies and experiments'],
    'Geometry and Trigonometry': ['Area and volume', 'Lines, angles, and triangles', 'Right triangles and trigonometry', 'Circles'],
}

class Text(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('style','script'):self.hidden+=1
    def handle_endtag(self,tag):
        if tag in ('style','script') and self.hidden:self.hidden-=1
    def handle_data(self, data):
        if not self.hidden:self.parts.append(data)

def plain_markup(value):
    p=Text();p.feed(value or '');return html.unescape(' '.join(p.parts))

def norm(value):
    value=unicodedata.normalize('NFKD',html.unescape(value or ''))
    return ''.join(c.lower() for c in value if c.isalnum() or c in '.-/%')

def api(path,payload=None):
    request=urllib.request.Request(API+path,data=None if payload is None else json.dumps(payload).encode(),headers={'Content-Type':'application/json','User-Agent':'SAT-offline-trainer'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request,timeout=60) as response:return json.load(response)
        except Exception:
            if attempt==3:raise
            time.sleep(1+attempt)

def official_data():
    CACHE.mkdir(parents=True,exist_ok=True);catalog_file=CACHE/'catalog.json';details_file=CACHE/'details.json'
    if catalog_file.exists():rows=json.loads(catalog_file.read_text(encoding='utf-8'))
    else:
        lookup=api('lookup');codes=','.join(d['primaryClassCd'] for d in lookup['lookupData']['domain']['Math'])
        tests={x['text']:int(x['id']) for x in lookup['lookupData']['test']};assessments={x['text']:int(x['id']) for x in lookup['lookupData']['assessment']}
        rows=api('digital/get-questions',{'asmtEventId':assessments['SAT'],'test':tests['Math'],'domain':codes})
        catalog_file.write_text(json.dumps(rows),encoding='utf-8')
    if details_file.exists():details=json.loads(details_file.read_text(encoding='utf-8'))
    else:
        details=[];ids=sorted({r['external_id'] for r in rows if r.get('external_id')})
        for index in range(0,len(ids),50):
            details.extend(api('pdf-download',{'external_ids':ids[index:index+50]}));print(f'Official Math content: {min(index+50,len(ids))}/{len(ids)}',flush=True)
        details_file.write_text(json.dumps(details),encoding='utf-8')
    by_external={d.get('externalid'):d for d in details};return [(r,by_external[r['external_id']]) for r in rows if r.get('external_id') in by_external]

def pdf_records(paths):
    records=[]
    for path in paths:
        doc=pymupdf.open(path);pages=[p.get_text() for p in doc];stream=''
        offsets=[]
        for page_no,text in enumerate(pages,1):offsets.append((len(stream),page_no));stream+=text+'\n'
        starts=list(re.finditer(r'Question ID ([a-f0-9]{8})\s*\nQuestion \d+',stream))
        for i,start in enumerate(starts):
            qid=start.group(1);end=starts[i+1].start() if i+1<len(starts) else len(stream);raw=stream[start.start():end]
            answer=re.search(r'ID: '+re.escape(qid)+r' Answer\s+Correct Answer:\s*(.*?)\s+Rationale\s+',raw,re.S)
            difficulty=re.search(r'Question difficulty:\s*(Easy|Medium|Hard)',raw,re.I)
            if not answer or not difficulty:raise ValueError(f'{path.name}: incomplete answer block for {qid}')
            correct=re.sub(r'\s+',' ',answer.group(1)).strip();body=raw[:answer.start()]
            flat=re.sub(r'\s+',' ',body)
            domain=next((d for d in DOMAINS if d in flat),None)
            skill=next((s for s in DOMAINS.get(domain,[]) if s in flat),None)
            if not domain or not skill:raise ValueError(f'{path.name}: missing domain or skill for {qid}')
            # Remove the export metadata so matching focuses on the actual exercise.
            skill_match=re.search(re.escape(skill).replace(r'\ ',r'\s+'),body,re.I)
            exercise=body[skill_match.end():] if skill_match else body
            answer_type='choice' if correct in 'ABCD' and len(correct)==1 else 'numeric'
            accepted=[x.strip() for x in correct.split(',') if x.strip()] if answer_type=='numeric' else [correct]
            pos=start.start();page_start=max(p for o,p in offsets if o<=pos)
            answer_pos=start.start()+answer.end();page_end=max(p for o,p in offsets if o<=answer_pos)
            records.append({'id':qid,'domain':domain,'skill':skill,'difficulty':difficulty.group(1).lower(),
                'answer_type':answer_type,'correct_answer':correct,'accepted_answers':accepted,'pdf_body':exercise,
                'source':{'filename':path.name,'file_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'page_start':page_start,'page_end':page_end}})
        doc.close()
    if len({r['id'] for r in records})!=len(records):raise ValueError('Duplicate Math question IDs in PDFs')
    return records

def candidate_text(detail):
    chunks=[detail.get('stimulus',''),detail.get('stem','')]+[a.get('content','') for a in detail.get('answerOptions') or []]
    return norm(' '.join(plain_markup(x) for x in chunks))

def match(records,official):
    prepared=[]
    for row,detail in official:
        prepared.append((row,detail,candidate_text(detail)))
    unmatched=[];ambiguous=[]
    for number,record in enumerate(records,1):
        target=norm(record['pdf_body']);pool=[]
        for row,detail,text in prepared:
            if (row.get('primary_class_cd_desc') or '').strip()!=record['domain'] or (row.get('skill_desc') or '').strip()!=record['skill']:continue
            if {'E':'easy','M':'medium','H':'hard'}.get(row.get('difficulty'))!=record['difficulty']:continue
            dtype=str(detail.get('type','')).lower();is_choice=bool(detail.get('answerOptions')) and dtype not in ('spr','grid-in')
            if is_choice!=(record['answer_type']=='choice'):continue
            if record['answer_type']=='choice' and record['correct_answer'] not in (detail.get('correct_answer') or []):continue
            # Official content should be nearly identical; the PDF adds metadata but may flatten fractions differently.
            ratio=difflib.SequenceMatcher(None,target,text,autojunk=False).ratio()
            contained=min(len(target),len(text)) and difflib.SequenceMatcher(None,target,text,autojunk=False).find_longest_match().size/min(len(target),len(text))
            pool.append((max(ratio,contained),row,detail))
        pool.sort(key=lambda x:x[0],reverse=True)
        if not pool or pool[0][0]<0.42:
            unmatched.append({'id':record['id'],'best':round(pool[0][0],3) if pool else None});continue
        if len(pool)>1 and pool[0][0]-pool[1][0]<0.025 and pool[0][0]<0.50:
            ambiguous.append({'id':record['id'],'scores':[round(x[0],3) for x in pool[:3]]});continue
        score,row,detail=pool[0];record['official_id']=row['questionId'];record['external_id']=row['external_id'];record['match_score']=score
        record['passage_html']=detail.get('stimulus') or ''
        record['prompt_html']=detail.get('stem') or ''
        record['explanation_html']=detail.get('rationale') or ''
        record['choices']=[{'letter':chr(65+i),'content_html':a.get('content','')} for i,a in enumerate(detail.get('answerOptions') or [])]
        if number%50==0:print(f'Matched {number}/{len(records)}',flush=True)
    if unmatched or ambiguous:raise ValueError('Math matching needs review: '+json.dumps({'unmatched':unmatched,'ambiguous':ambiguous},indent=2))
    return records

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--db',default=str(ROOT/'sat-math-clean.db'));args=parser.parse_args()
    paths=sorted(ROOT.glob('sat-math-answers-*.pdf'))
    if len(paths)!=6:raise SystemExit(f'Expected 6 Math answer PDFs, found {len(paths)}')
    records=match(pdf_records(paths),official_data())
    db_path=Path(args.db);db_path.unlink(missing_ok=True);db=sqlite3.connect(db_path);db.executescript((ROOT/'schema.sql').read_text(encoding='utf-8'))
    with db:
        for domain,skills in DOMAINS.items():
            db.execute('INSERT INTO domains(name) VALUES (?)',(domain,));did=db.execute('SELECT id FROM domains WHERE name=?',(domain,)).fetchone()[0]
            for skill in skills:db.execute('INSERT INTO skills(domain_id,name) VALUES (?,?)',(did,skill))
        for r in records:
            sid=db.execute('SELECT s.id FROM skills s JOIN domains d ON d.id=s.domain_id WHERE d.name=? AND s.name=?',(r['domain'],r['skill'])).fetchone()[0]
            db.execute('INSERT INTO questions(id,skill_id,difficulty,passage_html,prompt_html,answer_type,correct_answer,accepted_answers,explanation_html) VALUES (?,?,?,?,?,?,?,?,?)',
                (r['id'],sid,r['difficulty'],r['passage_html'],r['prompt_html'],r['answer_type'],r['correct_answer'],json.dumps(r['accepted_answers']),r['explanation_html']))
            for c in r['choices']:db.execute('INSERT INTO choices VALUES (?,?,?)',(r['id'],c['letter'],c['content_html']))
            s=r['source'];db.execute('INSERT OR IGNORE INTO sources(filename,file_sha256) VALUES (?,?)',(s['filename'],s['file_sha256']));source_id=db.execute('SELECT id FROM sources WHERE file_sha256=?',(s['file_sha256'],)).fetchone()[0]
            db.execute('INSERT INTO question_sources VALUES (?,?,?,?)',(r['id'],source_id,s['page_start'],s['page_end']))
            db.execute('INSERT INTO official_references(question_id,official_id,external_id,match_method) VALUES (?,?,?,?)',(r['id'],r['official_id'],r['external_id'],f"PDF/API text {r['match_score']:.3f}"))
        db.execute("INSERT OR REPLACE INTO transfer_meta VALUES ('bank_id','sat-math-original-v1')")
    report={'files':[{'filename':p.name} for p in paths],'questions':len(records),'choice_questions':sum(r['answer_type']=='choice' for r in records),
        'numeric_questions':sum(r['answer_type']=='numeric' for r in records),'minimum_match_score':round(min(r['match_score'] for r in records),3),
        'domains':dict(db.execute('SELECT d.name,count(*) FROM questions q JOIN skills s ON s.id=q.skill_id JOIN domains d ON d.id=s.domain_id GROUP BY d.id')),
        'integrity_check':db.execute('PRAGMA integrity_check').fetchone()[0],'foreign_key_errors':db.execute('PRAGMA foreign_key_check').fetchall()}
    db.close();(ROOT/'math-import-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
