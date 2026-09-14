"""Import the supplied College Board answer PDFs. Re-running preserves study history."""
from pathlib import Path
import argparse, hashlib, html, json, re, sqlite3
import pymupdf as fitz

ROOT = Path(__file__).resolve().parent
DOMAINS = {
 'Information and Ideas': ['Central Ideas and Details', 'Inferences', 'Command of Evidence'],
 'Craft and Structure': ['Words in Context', 'Text Structure and Purpose', 'Cross-Text Connections'],
 'Expression of Ideas': ['Transitions', 'Rhetorical Synthesis'],
 'Standard English Conventions': ['Boundaries', 'Form, Structure, and Sense'],
}

def plain(value):
    return re.sub(r'\s+', ' ', value).strip()

def paragraph(value):
    return '<p>' + html.escape(plain(value)) + '</p>'

def lines(page):
    result=[]
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            result.append((line['bbox'], ''.join(s['text'] for s in line['spans']), line['spans']))
    return result

def extract(path, asset_dir):
    doc=fitz.open(path)
    texts=['\n'.join(('@@CHOICE@@' if 35<=b[0]<=45 and re.match(r'^[A-D]\.\s*',t) else '')+t for b,t,_ in lines(p)) for p in doc]
    starts=[]
    for n,t in enumerate(texts):
        ids=re.findall(r'Question ID ([a-f0-9]{8})',t)
        if len(ids)>1: raise ValueError(f'{path.name} page {n+1}: multiple question headers')
        if ids: starts.append((n,ids[0]))
    records=[]
    for ix,(n,qid) in enumerate(starts):
        stop=starts[ix+1][0] if ix+1<len(starts) else len(doc)
        raw='\n\f\n'.join(texts[n:min(stop+1,len(doc))])
        raw=raw[raw.index('Question ID '+qid):]
        raw=re.sub(r'^ID: [a-f0-9]{8}[ \t]*$', '', raw, flags=re.M)
        match=re.search(r'ID: '+qid+r' Answer\s+Correct Answer:\s*([A-D])\s+Rationale\s+(.*?)\s+Question difficulty:\s*(Easy|Medium|Hard)',raw,re.S)
        if not match: raise ValueError(f'{qid}: answer/rationale/difficulty missing')
        answer,explanation,difficulty=match.groups()
        body=raw[:match.start()]
        flat=plain(body)
        domain=next((d for d in DOMAINS if d.lower() in flat.lower()),None)
        if not domain: raise ValueError(f'{qid}: unknown domain')
        skill=next((s for s in DOMAINS[domain] if s.lower() in flat.lower()),None)
        if not skill: raise ValueError(f'{qid}: unknown skill')
        first_a=re.search(r'(?:^|\n)@@CHOICE@@A\.\s*',body)
        if not first_a: raise ValueError(f'{qid}: missing A')
        body=body[first_a.start():]
        opts=list(re.finditer(r'(?:^|\n)@@CHOICE@@([A-D])\.\s*',body))
        if [m[1] for m in opts]!=list('ABCD'): raise ValueError(f'{qid}: invalid choices')
        # The passage precedes choice A; choices and rationale can continue onto later pages.
        page=doc[n]; ls=lines(page)
        candidates=[b[1] for b,t,_ in ls if re.match(r'^A\.\s*',t) and 35<=b[0]<=45]
        if len(candidates)!=1: raise ValueError(f'{qid}: ambiguous A layout')
        badge=[b for b,t,_ in ls if t.strip()==f'ID: {qid}']
        if len(badge)!=1: raise ValueError(f'{qid}: missing question badge')
        top=badge[0][3]+7
        rect=fitz.Rect(27,top,585,candidates[0]-5)
        if rect.height<=0: raise ValueError(f'{qid}: invalid passage crop')
        filename=f'{qid}.png'
        page.get_pixmap(matrix=fitz.Matrix(2,2),clip=rect).save(asset_dir/filename)
        passage=page.get_text(clip=rect).strip()
        choices={letter:html.escape(plain(body[opts[i].end():opts[i+1].start() if i<3 else len(body)])) for i,letter in enumerate('ABCD')}
        if any(not v for v in choices.values()): raise ValueError(f'{qid}: empty choice')
        end_page=n+1+raw[:match.end()].count('\f')
        records.append(dict(id=qid,domain=domain,skill=skill,difficulty=difficulty.lower(),
            passage_html=paragraph(passage),prompt_html='',correct_answer=answer,
            explanation_html=''.join(paragraph(x) for x in re.split(r'\n(?=Choice [A-D])',explanation)),
            choices=choices,asset=f'assets/{filename}',page_start=n+1,page_end=end_page))
    doc.close()
    return records

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--db',default=str(ROOT/'sat.db')); args=parser.parse_args()
    assets=ROOT/'assets';assets.mkdir(exist_ok=True)
    paths=sorted(ROOT.glob('sat-rw-answers-*.pdf'))
    if not paths: raise SystemExit('No answer PDFs found: expected sat-rw-answers-*.pdf')
    report={'files':[],'questions':0,'duplicates':0,'errors':[]}; batches=[];seen={}
    for path in paths:
        print('Extracting',path.name,flush=True)
        try:
            records=extract(path,assets)
            for r in records:
                payload={k:v for k,v in r.items() if k not in ('page_start','page_end')}
                if r['id'] in seen:
                    if seen[r['id']]!=payload: raise ValueError(f"Conflicting duplicate {r['id']}")
                    report['duplicates']+=1
                seen[r['id']]=payload
            batches.append((path,records));report['files'].append({'filename':path.name,'questions':len(records)})
        except Exception as exc: report['errors'].append(str(exc))
    if report['errors']:
        (ROOT/'import-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        raise SystemExit('\n'.join(report['errors']))
    db=sqlite3.connect(args.db);db.executescript((ROOT/'schema.sql').read_text())
    with db:
        for domain,skills in DOMAINS.items():
            db.execute('INSERT OR IGNORE INTO domains(name) VALUES (?)',(domain,))
            did=db.execute('SELECT id FROM domains WHERE name=?',(domain,)).fetchone()[0]
            for s in skills: db.execute('INSERT OR IGNORE INTO skills(domain_id,name) VALUES (?,?)',(did,s))
        for path,records in batches:
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            db.execute('INSERT OR IGNORE INTO sources(filename,file_sha256) VALUES (?,?)',(path.name,digest))
            sid=db.execute('SELECT id FROM sources WHERE file_sha256=?',(digest,)).fetchone()[0]
            for r in records:
                skill_id=db.execute('SELECT s.id FROM skills s JOIN domains d ON d.id=s.domain_id WHERE s.name=? AND d.name=?',(r['skill'],r['domain'])).fetchone()[0]
                cols=['id','skill_id','difficulty','passage_html','prompt_html','correct_answer','explanation_html'];r['skill_id']=skill_id
                db.execute('INSERT INTO questions('+','.join(cols)+') VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET '+','.join(c+'=excluded.'+c for c in cols[1:]),[r[c] for c in cols])
                for letter,value in r['choices'].items(): db.execute('INSERT INTO choices VALUES (?,?,?) ON CONFLICT(question_id,letter) DO UPDATE SET content_html=excluded.content_html',(r['id'],letter,value))
                db.execute('INSERT INTO assets(question_id,file_path,media_type,alt_text) VALUES (?,?,?,?) ON CONFLICT(question_id,file_path) DO UPDATE SET alt_text=excluded.alt_text',(r['id'],r['asset'],'image/png','Passage in original PDF formatting'))
                db.execute('INSERT INTO question_sources VALUES (?,?,?,?) ON CONFLICT(question_id,source_id,page_start) DO UPDATE SET page_end=excluded.page_end',(r['id'],sid,r['page_start'],r['page_end']))
    report['questions']=db.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    report['integrity_check']=db.execute('PRAGMA integrity_check').fetchone()[0]
    report['foreign_key_errors']=db.execute('PRAGMA foreign_key_check').fetchall()
    report['skills']=[dict(zip(['domain','skill','count'],row)) for row in db.execute('SELECT d.name,s.name,count(*) FROM questions q JOIN skills s ON s.id=q.skill_id JOIN domains d ON d.id=s.domain_id GROUP BY s.id')]
    db.close();(ROOT/'import-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
