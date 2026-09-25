#!/usr/bin/env python3
"""Read-only public-repository census. No target code is executed.
All '#N' edges are mentions, never automatically promoted to dependencies.
The coverage manifest exposes pagination failures, exclusions and scan limits.
"""
from __future__ import annotations
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPO = 'trycua/cua'
PIN = 'a959b2a23f8099769d0d57e4b8c2c8e70bf7d036'
OUT = Path('export')
API = 'https://api.github.com'
MAX_REQUESTS = 850
MAX_TEXT_BYTES = 3_000_000
MAX_DETAIL_PRS = 90
SEEDS = {3963,3931,3915,3916,3961,4052,3971,3972,3946,3488,3489,3490,3492,3493,3494,3924,3928,3929,2958,3903,3904,2969,2794,3473,3616,3873,3630,3942,3796,1757,1755,3906,3787,3882,3817,3815,3814,3907,3813,4009,3984,3373,2238,3834,3658,3391,3996,2349,4038,4039,4012,4013,4014,4094,4118,4120,4142}
TERMS = re.compile(r'jev|verify_state|snapshot|freshness|observation|post.action|settle|latency|perception|cancell?ation|native.*schedul|batch.*action|action.*batch|passive|AX.*walk|walk.*budget|capture.*reuse|revision|action.*outcome|window.*cache|presentation.timestamp|element.*identit', re.I)
LOCAL_REF = re.compile(r'(?<![\w/#])#([1-9][0-9]{0,5})(?![\w])')
URL_REF = re.compile(r'https://github\.com/trycua/cua/(?:issues|pull)/(\d+)')

def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()

def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def references(text: str) -> list[tuple[int, str]]:
    hits: dict[int, str] = {}
    for pattern in (URL_REF, LOCAL_REF):
        for match in pattern.finditer(text):
            n = int(match.group(1))
            hits.setdefault(n, text[max(0, match.start()-100):match.end()+170])
    return sorted(hits.items())

class Reader:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.calls = 0
        self.failures: list[dict] = []
        self.collections: dict = {}
        self.remaining: int | None = None

    def get(self, url: str) -> tuple[object, dict]:
        if not url.startswith(API+'/repos/'+REPO+'/'):
            raise ValueError('Only the fixed public repository GET endpoints are allowed')
        with self.lock:
            if self.calls >= MAX_REQUESTS:
                raise RuntimeError('Explicit request budget exhausted')
            self.calls += 1
        headers = {'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'cua-rfc3963-read-only-census'}
        token = os.environ.get('GH_TOKEN')
        if token:
            headers['Authorization'] = 'Bearer '+token
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers, method='GET'), timeout=45) as r:
                    response_headers = dict(r.headers.items())
                    with self.lock:
                        self.remaining = int(r.headers.get('X-RateLimit-Remaining', '-1'))
                    return json.load(r), response_headers
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(min(30, int(e.headers.get('Retry-After','2')) * (attempt+1)))
                    continue
                raise
        raise RuntimeError('Unreachable retry state')

    def collection(self, endpoint: str, name: str) -> list[dict]:
        url = API+'/repos/'+REPO+'/'+endpoint
        url += ('&' if '?' in url else '?')+'per_page=100'
        rows: list[dict] = []
        urls: list[str] = []
        complete = True
        try:
            data, headers = self.get(url)
            if not isinstance(data, list):
                raise ValueError('Collection did not return an array')
            rows.extend(data); urls.append(url)
            links = {rel:u for u,rel in re.findall(r'<([^>]+)>; rel="([^"]+)"', headers.get('Link', headers.get('link','')))}
            if 'last' in links:
                last = int(urllib.parse.parse_qs(urllib.parse.urlparse(links['last']).query)['page'][0])
                def page(i: int):
                    u = url+'&page='+str(i)
                    try:
                        d, _ = self.get(u)
                        if not isinstance(d,list): raise ValueError('Expected array')
                        return u,d,None
                    except Exception as e:
                        return u,[],type(e).__name__+': '+str(e)
                with cf.ThreadPoolExecutor(max_workers=4) as pool:
                    for u,d,error in pool.map(page, range(2,last+1)):
                        urls.append(u); rows.extend(d)
                        if error:
                            complete=False; self.failures.append({'url':u,'error':error})
            else:
                while 'next' in links:
                    u=links['next']; d,headers=self.get(u)
                    if not isinstance(d,list): raise ValueError('Expected array')
                    urls.append(u); rows.extend(d)
                    links={rel:v for v,rel in re.findall(r'<([^>]+)>; rel="([^"]+)"', headers.get('Link', headers.get('link','')))}
        except Exception as e:
            complete=False; self.failures.append({'url':url,'error':type(e).__name__+': '+str(e)})
        unique={str(x.get('id',x.get('number'))):x for x in rows}
        self.collections[name]={'endpoint':url,'pages_attempted':len(urls),'rows':len(rows),'unique_rows':len(unique),'duplicates':len(rows)-len(unique),'complete':complete,'pagination':'GitHub returned Link last/next; no search result cap'}
        result=sorted(unique.values(),key=lambda x:x.get('id',x.get('number',0)))
        dump(OUT/'raw'/f'{name}.json',result)
        print(name, self.collections[name], flush=True)
        return result

def scan_source() -> dict:
    src=Path('source')
    src.mkdir(exist_ok=True)
    commands=[['git','init','source'],['git','-C','source','remote','add','origin','https://github.com/'+REPO+'.git'],['git','-C','source','fetch','--depth=1','origin',PIN],['git','-C','source','checkout','--detach','FETCH_HEAD']]
    for command in commands:
        subprocess.run(command, check=True, timeout=420)
    actual=subprocess.check_output(['git','-C','source','rev-parse','HEAD'],text=True).strip()
    if actual!=PIN: raise RuntimeError('Source SHA mismatch')
    tree=subprocess.check_output(['git','-C','source','ls-tree','-rz','-l','HEAD']).decode('utf-8')
    inventory=[]; refs=[]; relevant=[]; text_count=0
    with zipfile.ZipFile(OUT/'source_text.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for record in tree.split('\0'):
            if not record: continue
            info,path=record.split('\t',1)
            mode,kind,sha,size=info.split()
            row={'path':path,'mode':mode,'kind':kind,'sha':sha,'size':int(size) if size!='-' else None}
            inventory.append(row)
            p=src/path
            if kind!='blob' or mode=='120000': row['scan']='non-regular'; continue
            if int(size)>MAX_TEXT_BYTES: row['scan']='over-text-size-limit'; continue
            raw=p.read_bytes()
            if b'\0' in raw: row['scan']='binary'; continue
            try: text=raw.decode('utf-8')
            except UnicodeDecodeError: row['scan']='non-UTF8'; continue
            if p.suffix.lower() in {'.ttf','.otf','.woff','.woff2','.eot'}:
                row['scan']='font-excluded'; continue
            row['scan']='text-scanned'; row['lines']=len(text.splitlines()); text_count+=1
            archive.writestr(path,raw)
            for n,context in references(text): refs.append({'path':path,'number':n,'relation':'mentions','context':context})
            hits=sorted(set(x.group(0).lower() for x in TERMS.finditer(text)))
            if hits: relevant.append({'path':path,'terms':hits,'sha':sha})
    dump(OUT/'source_inventory.json',inventory)
    dump(OUT/'source_references.json',refs)
    dump(OUT/'source_candidates.json',relevant)
    return {'pin':actual,'tracked_entries':len(inventory),'text_files_scanned':text_count,'text_byte_limit':MAX_TEXT_BYTES,'classifications':{s:sum(r['scan']==s for r in inventory) for s in sorted(set(r['scan'] for r in inventory))},'candidate_files':len(relevant),'method':'Every regular UTF-8 tracked file up to explicit byte limit, no target code execution. Binary/font/non-UTF8/oversize files inventoried but not semantically inspected.'}

def main() -> None:
    OUT.mkdir(exist_ok=True)
    reader=Reader()
    manifest={'repository':REPO,'source_pin':PIN,'started_at':now(),'mode':'read-only upstream GET + static source read','semantic_dependency_claim':'None: mechanically extracted reference edges are mentions only','request_limit':MAX_REQUESTS,'detail_pr_limit':MAX_DETAIL_PRS,'uninspected':['Binary images/videos','Deleted/private issue content','GitHub Discussions','Unreferenced non-default branches','Every historical commit and complete PR diff','Maintainer intent not stated in a source']}
    try:
        issues=reader.collection('issues?state=all&sort=created&direction=asc','issues')
        prs=reader.collection('pulls?state=all&sort=created&direction=asc','pulls')
        comments=reader.collection('issues/comments?sort=created&direction=asc','issue_comments')
        review_comments=reader.collection('pulls/comments?sort=created&direction=asc','review_comments')
        by_number={x['number']:x for x in issues}
        per_thread:dict[int,list[dict]]={}
        edges=[]
        def add(n:int, text:str, source_url:str, kind:str):
            per_thread.setdefault(n,[]).append({'text':text,'url':source_url,'kind':kind})
            for target,context in references(text):
                if target!=n and target in by_number:
                    edges.append({'source':n,'target':target,'type':'mentions','evidence_url':source_url,'source_kind':kind,'context':context,'verified_dependency':False})
        for x in issues: add(x['number'],x.get('body') or '',x['html_url'],'body')
        for x in comments:
            n=int(x['issue_url'].rsplit('/',1)[1]); add(n,x.get('body') or '',x['html_url'],'issue_comment')
        for x in review_comments:
            n=int(x['pull_request_url'].rsplit('/',1)[1]); add(n,x.get('body') or '',x['html_url'],'review_comment')
        seeds=SEEDS & by_number.keys()
        first_hop={e['target'] for e in edges if e['source'] in seeds}|{e['source'] for e in edges if e['target'] in seeds}
        candidate_scores=[]
        for n,x in by_number.items():
            title=x.get('title',''); body=x.get('body') or ''
            hits=sorted(set(m.group(0).lower() for m in TERMS.finditer(title+'\n'+body)))
            score=1000*(n in seeds)+100*(n in first_hop)+15*len(list(TERMS.finditer(title)))+min(len(hits),10)
            if score: candidate_scores.append({'number':n,'title':title,'score':score,'seed':n in seeds,'one_hop':n in first_hop,'keyword_hits':hits,'url':x['html_url']})
        candidate_scores.sort(key=lambda r:(-r['score'],-r['number']))
        dump(OUT/'all_reference_edges.json',edges)
        dump(OUT/'candidate_ranking.json',candidate_scores)
        dump(OUT/'thread_text.json',per_thread)
        pr_numbers={x['number'] for x in prs}
        selected=[x['number'] for x in candidate_scores if x['number'] in pr_numbers][:MAX_DETAIL_PRS]
        detail_manifest=[]
        for n in selected:
            if reader.calls>MAX_REQUESTS-40:
                detail_manifest.append({'number':n,'status':'request-budget-deferred'});continue
            files=reader.collection(f'pulls/{n}/files',f'pr_{n}_files')
            reviews=reader.collection(f'pulls/{n}/reviews',f'pr_{n}_reviews')
            for x in reviews: add(n,x.get('body') or '',x.get('html_url',''),'review_submission')
            detail_manifest.append({'number':n,'files':len(files),'reviews':len(reviews),'status':'fetched'})
        dump(OUT/'detail_manifest.json',detail_manifest)
        dump(OUT/'all_reference_edges.json',edges)
        dump(OUT/'thread_text.json',per_thread)
        manifest['source']=scan_source()
        manifest['candidate_count']=len(candidate_scores)
        manifest['seed_count']=len(seeds)
        manifest['all_reference_edges']=len(edges)
    except Exception as e:
        manifest['fatal_error']=type(e).__name__+': '+str(e)
        print(manifest['fatal_error'],flush=True)
    finally:
        manifest.update({'finished_at':now(),'requests':reader.calls,'rate_remaining_last':reader.remaining,'collections':reader.collections,'failures':reader.failures})
        dump(OUT/'coverage.json',manifest)
        hashes={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.rglob('*')) if p.is_file()}
        dump(OUT/'SHA256.json',hashes)
        print(json.dumps({k:v for k,v in manifest.items() if k!='collections'},indent=2),flush=True)

if __name__=='__main__': main()
