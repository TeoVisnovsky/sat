"""Recover missing instruction lines from the official College Board API.

The supplied export uses different IDs. Match the full set of answer-choice text,
verify the correct answer and passage, then retain both IDs for provenance.
"""
import json,sqlite3,re,html,urllib.request,time,unicodedata,difflib
from pathlib import Path
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parent
BASE='https://qbank-api.collegeboard.org/msreportingquestionbank-prod/questionbank/'

def request(path,payload):
    req=urllib.request.Request(BASE+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    for attempt in range(3):
        try:return json.load(urllib.request.urlopen(req,timeout=45))
        except Exception:
            if attempt==2:raise
            time.sleep(1+attempt)

def norm(s):
    s=re.sub(r'<span[^>]*class=["\']sr-only["\'][^>]*>.*?</span>','',s,flags=re.S)
    s=html.unescape(re.sub('<[^>]+>','',s));s=unicodedata.normalize('NFKD',s)
    return ''.join(c.lower() for c in s if c.isalnum())

def choice_norm(s):
    s=re.sub(r'<span[^>]*class=["\']sr-only["\'][^>]*>.*?</span>','',s,flags=re.S)
    return re.sub(r'\s+','',unicodedata.normalize('NFC',html.unescape(re.sub('<[^>]+>','',s))))

class Cleaner(HTMLParser):
    allowed={'p','span','em','strong','i','b','u','sup','sub','br','img','ul','ol','li','cite','figure','figcaption','blockquote','div','table','caption','thead','tbody','tfoot','tr','th','td','svg','g','defs','pattern','line','text','rect','marker','polygon','polyline','path','circle','ellipse','use','clippath','math','mrow','mi','mo','mn','mfrac','msup','msub','msubsup','msqrt','mroot','mtable','mtr','mtd','mtext','mspace','mfenced','mover','munder','munderover','mmultiscripts','mprescripts','none','menclose','mstyle','semantics','annotation'}
    attrs={'aria-label','aria-hidden','role','viewbox','width','height','xmlns','xmlns:xlink','version','id','x','y','dx','dy','x1','x2','y1','y2','cx','cy','rx','ry','r','d','points','transform','fill','stroke','stroke-width','stroke-linecap','stroke-linejoin','stroke-miterlimit','stroke-dasharray','opacity','isolation','dominant-baseline','text-anchor','font-family','font-size','patterntransform','patternunits','markerunits','markerwidth','markerheight','refx','refy','orient','marker-end','marker-start','colspan','rowspan','scope','alt','alttext','display','displaystyle','mathvariant','stretchy','fence','separator','form','notation','bevelled','columnalign','rowalign','clip-path','href','xlink:href','src','loading'}
    cases={'viewbox':'viewBox','patterntransform':'patternTransform','patternunits':'patternUnits','markerwidth':'markerWidth','markerheight':'markerHeight','refx':'refX','refy':'refY'}
    def __init__(self):super().__init__(convert_charrefs=True);self.out=[];self.blocked=0;self.fences=[]
    def fence_separator(self):
        """Emit the separator that precedes the next direct child of an open <mfenced>."""
        if not self.fences:return
        fence=self.fences[-1]
        if fence['depth']:return
        if fence['count']:
            seps=fence['separators']
            if seps:self.out.append('<mo>'+html.escape(seps[min(fence['count']-1,len(seps)-1)])+'</mo>')
        fence['count']+=1
    def handle_starttag(self,tag,attrs):
        if tag in ('style','script'):self.blocked+=1;return
        if self.blocked:return
        if tag=='mfenced':
            values={k:v for k,v in attrs}
            self.fence_separator()
            for fence in self.fences:fence['depth']+=1
            opener=values.get('open','(') or ''
            self.fences.append({'close':values.get('close',')') or '','separators':''.join((values.get('separators',',') if values.get('separators') is not None else ',').split()),'depth':0,'count':0})
            self.out.append('<mrow>'+('<mo>'+html.escape(opener)+'</mo>' if opener else ''))
            return
        if tag in self.allowed:
            self.fence_separator()
            if tag!='br':
                for fence in self.fences:fence['depth']+=1
            styles=[]
            for k,v in attrs:
                if k=='style':styles=[x.strip() for x in v.split(';') if re.fullmatch(r'(?:fill|stroke|stroke-width|stroke-linecap|stroke-linejoin|stroke-miterlimit|stroke-dasharray|opacity|isolation|font-size|font-family|text-anchor)\s*:\s*[-#(),.%\w\s]+',x.strip(),re.I)]
            underline=any(k=='style' and 'underline' in v for k,v in attrs)
            safe=''.join(' '+self.cases.get(k,k)+'="'+html.escape(v,quote=True)+'"' for k,v in attrs if k in self.attrs and v is not None and not re.search(r'javascript:|https?:|data:|^//',v,re.I))
            if any(k=='class' and v=='sr-only' for k,v in attrs):safe+=' class="sr-only"'
            style=';'.join(styles+(['text-decoration:underline'] if underline else []))
            self.out.append('<'+tag+safe+(' style="'+html.escape(style,quote=True)+'"' if style else '')+'>')
    def handle_endtag(self,tag):
        if tag in ('style','script'):
            if self.blocked:self.blocked-=1
            return
        if self.blocked:return
        if tag=='mfenced':
            if not self.fences:return
            fence=self.fences.pop()
            self.out.append(('<mo>'+html.escape(fence['close'])+'</mo>' if fence['close'] else '')+'</mrow>')
            for open_fence in self.fences:open_fence['depth']-=1
            return
        if tag in self.allowed and tag!='br':
            for fence in self.fences:fence['depth']-=1
            self.out.append('</'+tag+'>')
    def handle_data(self,data):
        if not self.blocked:self.out.append(html.escape(data))

def clean(s):
    s=re.sub(r'<span[^>]*class=["\']sr-only["\'][^>]*>.*?</span>','',s,flags=re.S)
    p=Cleaner();p.feed(s);return ''.join(p.out)

def main():
    cache=ROOT/'source-cache';cache.mkdir(exist_ok=True)
    catalog=cache/'catalog.json'
    if not catalog.exists():catalog.write_text(json.dumps(request('digital/get-questions',{'asmtEventId':99,'test':1,'domain':'INI,CAS,EOI,SEC'})))
    rows=json.loads(catalog.read_text());ext_to_id={r['external_id']:r['questionId'] for r in rows if r.get('external_id')}
    ext=list(ext_to_id);details=[]
    for i in range(0,len(ext),100):
        file=cache/f'batch-{i//100:02}.json'
        if not file.exists():file.write_text(json.dumps(request('pdf-download',{'external_ids':ext[i:i+100]})))
        details.extend(json.loads(file.read_text()));print(f'Official content: {min(i+100,len(ext))}/{len(ext)}',flush=True)
    db=sqlite3.connect(ROOT/'sat.db');db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS official_references(question_id TEXT PRIMARY KEY REFERENCES questions(id),official_id TEXT NOT NULL,external_id TEXT NOT NULL,match_method TEXT NOT NULL,recovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
    candidates=[]
    for d in details:
        if len(d.get('answerOptions',[]))!=4:continue
        choices=tuple(choice_norm(c['content']) for c in d['answerOptions'])
        candidates.append((choices,d))
    index={}
    for choices,d in candidates:index.setdefault(choices,[]).append(d)
    report={'matched':0,'unmatched':[],'conflicts':[],'fuzzy':[]}
    for q in db.execute('SELECT * FROM questions').fetchall():
        choices=tuple(choice_norm(r[0]) for r in db.execute('SELECT content_html FROM choices WHERE question_id=? ORDER BY letter',(q['id'],)))
        matches=index.get(choices,[]);method='exact choices'
        valid=[]
        for d in matches:
            source_passage=norm(q['passage_html']);official=norm(d.get('stimulus',''))
            # Graph labels may precede the passage in PDFs, but prose must overlap.
            overlap=difflib.SequenceMatcher(None,source_passage,official,autojunk=False).find_longest_match().size
            if overlap < min(80,max(15,len(source_passage)*.35)):continue
            answer=d.get('correct_answer',[])
            if isinstance(answer,str):answer=[answer]
            if not answer and d.get('keys'):answer=[chr(65+i) for i,c in enumerate(d['answerOptions']) if c.get('id') in d['keys']]
            if answer!=[q['correct_answer']]:continue
            if d.get('stem'):valid.append(d)
        stems={norm(d['stem']) for d in valid}
        if len(stems)!=1:
            report['unmatched' if not valid else 'conflicts'].append(q['id']);continue
        d=valid[0];external=d.get('externalid') or d.get('external_id');official_id=ext_to_id.get(external)
        if not external or not official_id:raise ValueError('Missing official provenance')
        db.execute('UPDATE questions SET prompt_html=?,passage_html=?,explanation_html=? WHERE id=?',(clean(d['stem']),clean(d['stimulus']),clean(d['rationale']),q['id']))
        for i,c in enumerate(d['answerOptions']):db.execute('UPDATE choices SET content_html=? WHERE question_id=? AND letter=?',(clean(c['content']),q['id'],chr(65+i)))
        db.execute('INSERT INTO official_references(question_id,official_id,external_id,match_method) VALUES (?,?,?,?) ON CONFLICT(question_id) DO UPDATE SET official_id=excluded.official_id,external_id=excluded.external_id,match_method=excluded.match_method',(q['id'],official_id,external,method))
        report['matched']+=1
        if method!='exact choices':report['fuzzy'].append({'id':q['id'],'method':method})
    db.commit();db.close();(ROOT/'prompt-recovery-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
