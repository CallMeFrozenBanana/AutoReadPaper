from __future__ import annotations
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import httpx
from .store import db, one, uid, now, dumps, index_paper, root

NS={'a':'http://www.w3.org/2005/Atom','o':'http://a9.com/-/spec/opensearch/1.1/'}
ID_RE=re.compile(r'^(?:\d{4}\.\d{4,5}|[a-zA-Z.-]+/\d{7})(?:v\d+)?$')


def identifier(value):
    value=value.strip()
    if '://' in value:
        u=urlparse(value)
        if u.hostname not in ('arxiv.org','www.arxiv.org','export.arxiv.org'):
            raise ValueError('首版链接导入仅支持 arXiv；其他论文请上传 PDF')
        value=re.sub(r'^/(abs|pdf)/','',u.path)
        if value.endswith('.pdf'):value=value[:-4]
    if not ID_RE.fullmatch(value): raise ValueError('无效的 arXiv ID 或链接')
    return value


def rate_limit():
    # Shared across API previews and worker; reserving a slot is atomic.
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute("SELECT value FROM meta WHERE key='arxiv_next'").fetchone()
        slot=max(time.time(),float(row[0]) if row else 0)
        c.execute("INSERT OR REPLACE INTO meta VALUES('arxiv_next',?)",(str(slot+3.1),))
    delay=slot-time.time()
    if delay>0:time.sleep(delay)


def query_for(config):
    if config.get('query','').strip():return config['query'].strip()
    words=[w.replace('"','').replace('\\','') for w in config['keywords']]
    q='('+' OR '.join(f'(ti:"{w}" OR abs:"{w}")' for w in words)+')'
    if config.get('categories'):
        q+=' AND ('+' OR '.join('cat:'+c for c in config['categories'])+')'
    return q


def fetch(params):
    rate_limit()
    with httpx.Client(timeout=45,headers={'User-Agent':'AutoReadPaper/0.1 local research reader'}) as client:
        r=client.get('https://export.arxiv.org/api/query',params=params)
        r.raise_for_status()
        if len(r.content)>8_000_000:raise ValueError('arXiv 返回体超出限制')
    doc=ET.fromstring(r.content)
    entries=[]
    for e in doc.findall('a:entry',NS):
        ident=e.findtext('a:id','',NS).split('/abs/')[-1]
        if not ID_RE.fullmatch(ident):raise ValueError('arXiv 返回查询错误或无效记录')
        base=re.sub(r'v\d+$','',ident)
        version=re.search(r'v\d+$',ident)
        entries.append({'identity':'arxiv:'+base,'title':' '.join(e.findtext('a:title','',NS).split()),
            'authors':[a.findtext('a:name','',NS) for a in e.findall('a:author',NS)],
            'abstract':e.findtext('a:summary','',NS).strip(),'source':'arxiv',
            'published':e.findtext('a:published','',NS),'updated':e.findtext('a:updated','',NS),
            'label':version.group() if version else 'v1','url':'https://arxiv.org/abs/'+base,
            'pdf_url':'https://arxiv.org/pdf/'+ident})
    return entries,int(doc.findtext('o:totalResults','0',NS)),r.text


def upsert(entry,topic_id=None,revision=1,reason='手动导入',excluded=False):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        existing=c.execute('SELECT id FROM papers WHERE identity=?',(entry['identity'],)).fetchone()
        pid=existing[0] if existing else uid()
        c.execute('INSERT OR IGNORE INTO papers(id,identity,title,authors,abstract,source,published,url,created) VALUES(?,?,?,?,?,?,?,?,?)',
            (pid,entry['identity'],entry['title'],dumps(entry.get('authors',[])),entry.get('abstract',''),entry['source'],entry.get('published'),entry.get('url'),now()))
        vid=uid()
        c.execute('INSERT OR IGNORE INTO versions(id,paper_id,label,updated,pdf_url,sha256,pdf_path,created,metadata) VALUES(?,?,?,?,?,?,?,?,?)',
            (vid,pid,entry['label'],entry.get('updated'),entry.get('pdf_url'),entry.get('sha256'),entry.get('pdf_path'),now(),dumps(entry)))
        ver=c.execute('SELECT * FROM versions WHERE paper_id=? AND label=?',(pid,entry['label'])).fetchone()
        is_new=ver['id']==vid
        latest=c.execute('SELECT id FROM versions WHERE paper_id=? ORDER BY updated DESC,created DESC LIMIT 1',(pid,)).fetchone()
        if latest[0]==ver['id']:
            c.execute('UPDATE papers SET title=?,authors=?,abstract=? WHERE id=?',(entry['title'],dumps(entry.get('authors',[])),entry.get('abstract',''),pid))
        if topic_id:
            c.execute('INSERT INTO topic_papers VALUES(?,?,?,?,?) ON CONFLICT(topic_id,paper_id) DO UPDATE SET reason=excluded.reason,excluded=excluded.excluded,revision=excluded.revision',
                (topic_id,pid,reason,int(excluded),revision))
    index_paper(pid)
    return pid,dict(ver),is_new,bool(existing)


def download_pdf(url,relative):
    # Only source-owned public URLs are accepted; arbitrary URL fetching is not exposed.
    for _ in range(5):
        u=urlparse(url)
        if u.scheme!='https' or u.hostname not in ('arxiv.org','export.arxiv.org') or u.port not in (None,443):
            raise ValueError('PDF 下载地址必须是 arXiv HTTPS 地址')
        with httpx.Client(timeout=60,follow_redirects=False) as client:
            with client.stream('GET',url) as r:
                if r.is_redirect:
                    from urllib.parse import urljoin
                    url=urljoin(url,r.headers['location']);continue
                r.raise_for_status()
                data=bytearray()
                for part in r.iter_bytes():
                    data.extend(part)
                    if len(data)>50*1024*1024:raise ValueError('PDF 超过 50 MB 限制')
        if not data.startswith(b'%PDF-'):raise ValueError('下载内容不是 PDF')
        path=root()/relative;path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix('.tmp');temp.write_bytes(data);temp.replace(path)
        return hashlib.sha256(data).hexdigest()
    raise ValueError('PDF 下载重定向次数过多')
