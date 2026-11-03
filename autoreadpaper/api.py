from __future__ import annotations
import hashlib
from datetime import datetime,timezone
import json
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
import httpx
import pymupdf
from fastapi import FastAPI,HTTPException,UploadFile,File,Form,Request,Query
from fastapi.responses import FileResponse,JSONResponse,Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from . import sources
from .config import Topic,Settings,settings,save_settings,next_run,options,model_ready
from .store import init,root,db,one,all_rows,execute,enqueue,now,uid,dumps,index_paper,asset_lock
from .worker import queue_read
from .exporting import export_zip
from .assessment import queue_assessments,current_assessments


@asynccontextmanager
async def lifespan(app):
    init()
    from .cleanup import collect_files
    collect_files()
    yield

app=FastAPI(title='AutoReadPaper',lifespan=lifespan)


@app.middleware('http')
async def local_only(request:Request,call_next):
    host=request.url.hostname
    if host not in ('127.0.0.1','localhost','::1','testserver'):
        return JSONResponse({'detail':'仅允许本地访问'},status_code=403)
    origin=request.headers.get('origin')
    if origin and urlparse(origin).netloc!=request.headers.get('host'):
        return JSONResponse({'detail':'不允许跨来源访问'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api') else 'no-cache'
    return response


@app.exception_handler(ValueError)
async def value_error(request,exc):return JSONResponse({'detail':str(exc)},status_code=400)


@app.exception_handler(httpx.HTTPError)
async def network_error(request,exc):return JSONResponse({'detail':'网络请求失败：'+type(exc).__name__},status_code=502)


def require(table,ident):
    assert table in ('topics','papers','versions','jobs','reports')
    row=one(f'SELECT * FROM {table} WHERE id=?',(ident,))
    if not row:raise HTTPException(404,'记录不存在')
    return row


def topic_row(row):
    cfg=json.loads(row.pop('config'));return {**row,**cfg}


@app.get('/api/health')
def health():return {'status':'ok','version':'0.1.0','storage':'local'}


@app.get('/api/options')
def get_options():return options()


@app.get('/api/stats')
def stats():
    with db() as c:
        counts={name:c.execute(sql).fetchone()[0] for name,sql in {
            'papers':'SELECT COUNT(*) FROM papers','reports':'SELECT COUNT(DISTINCT v.paper_id) FROM reports r JOIN versions v ON v.id=r.version_id',
            'topics':'SELECT COUNT(*) FROM topics',
            'pending':"SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running','blocked','retry_wait')",
            'unread':'SELECT COUNT(*) FROM papers WHERE is_read=0'}.items()}
    counts['model_ready']=model_ready(settings())
    heartbeat=one("SELECT value FROM meta WHERE key='worker_heartbeat'")
    counts['worker_online']=bool(heartbeat and (datetime.now(timezone.utc)-datetime.fromisoformat(heartbeat['value'])).total_seconds()<90)
    return counts


@app.get('/api/topics')
def get_topics():
    rows=all_rows('SELECT * FROM topics ORDER BY created DESC')
    for row in rows:
        row['paper_count']=one('SELECT COUNT(*) n FROM topic_papers WHERE topic_id=? AND excluded=0',(row['id'],))['n']
    return [topic_row(r) for r in rows]


@app.post('/api/topics')
def create_topic(value:Topic):
    ident=uid();cfg=value.model_dump();stamp=now()
    with db() as c:
        c.execute('INSERT INTO topics(id,config,next_run,created) VALUES(?,?,?,?)',(ident,dumps(cfg),next_run(cfg),stamp))
        c.execute('INSERT INTO topic_revisions VALUES(?,?,?,?)',(ident,1,dumps(cfg),stamp))
    return topic_row(require('topics',ident))


@app.put('/api/topics/{ident}')
def edit_topic(ident:str,value:Topic):
    row=require('topics',ident);cfg=value.model_dump();rev=row['revision']+1
    with db() as c:
        c.execute('UPDATE topics SET config=?,revision=?,next_run=?,last_scan=NULL WHERE id=?',(dumps(cfg),rev,next_run(cfg) if row['active'] else None,ident))
        c.execute('INSERT INTO topic_revisions VALUES(?,?,?,?)',(ident,rev,dumps(cfg),now()))
    return topic_row(require('topics',ident))


class TopicState(BaseModel):
    model_config = {"extra": "forbid"}
    active:bool|None=None


@app.patch('/api/topics/{ident}')
def topic_state(ident:str,value:TopicState):
    row=require('topics',ident)
    active=value.active if value.active is not None else bool(row['active'])
    execute('UPDATE topics SET active=?,next_run=? WHERE id=?',(int(active),next_run(json.loads(row['config'])) if active else None,ident))
    return {'ok':True}


@app.delete('/api/topics/{ident}')
def delete_topic(ident:str):
    require('topics',ident)
    with db() as c:
        c.execute("UPDATE jobs SET state='cancelled',updated=?,progress='主题已删除，任务已取消' WHERE json_extract(payload,'$.topic_id')=? AND state IN ('queued','running','blocked','retry_wait')",(now(),ident))
        c.execute('DELETE FROM topic_papers WHERE topic_id=?',(ident,))
        c.execute('DELETE FROM topic_revisions WHERE topic_id=?',(ident,))
        c.execute('DELETE FROM topics WHERE id=?',(ident,))
    return {'ok':True,'message':'主题已删除，论文、阅读报告及笔记保留'}


@app.post('/api/topics/preview')
def preview(value:Topic):
    query=sources.query_for(value.model_dump())
    entries,total,_=sources.fetch({'search_query':query,'start':0,'max_results':5,'sortBy':'lastUpdatedDate','sortOrder':'descending'})
    return {'query':query,'total':total,'papers':entries,'note':'预览展示最新命中结果，回溯日期在正式扫描时应用'}


@app.post('/api/topics/{ident}/scan')
def scan_topic(ident:str):
    row=require('topics',ident)
    existing=one("SELECT * FROM jobs WHERE kind='scan' AND json_extract(payload,'$.topic_id')=? AND state IN ('queued','running','retry_wait') ORDER BY created DESC LIMIT 1",(ident,))
    if existing:return existing
    return enqueue('scan',{'topic_id':ident,'config':json.loads(row['config']),'revision':row['revision'],'automatic':False})


@app.get('/api/scans')
def get_scans():return all_rows('SELECT * FROM scans ORDER BY created DESC LIMIT 100')


from .cleanup import CleanupFilter,CleanupCommit,preview as cleanup_preview,commit as cleanup_commit


@app.post('/api/library/cleanup/preview')
def preview_cleanup(value:CleanupFilter):return cleanup_preview(value)


@app.post('/api/library/cleanup/commit')
def commit_cleanup(value:CleanupCommit):return cleanup_commit(value)


@app.get('/api/papers')
def papers(q:str='',topic:str='',sort:str=Query('recent',pattern='^(recent|priority)$'),ranked_only:bool=False,favorite:bool=False,unread:bool=False,scope:str='',source:str='',excluded:bool=False,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100)):
    conditions=[];params=[]
    if q.strip():
        import jieba
        terms=[x for x in jieba.cut_for_search(q) if x.strip()]
        match=' OR '.join('"'+x.replace('"','""')+'"' for x in terms)
        conditions.append('(p.id IN (SELECT paper_id FROM paper_search WHERE paper_search MATCH ?) OR p.title LIKE ? OR p.notes LIKE ?)')
        params.extend([match,'%'+q+'%','%'+q+'%'])
    if topic:
        conditions.append('EXISTS (SELECT 1 FROM topic_papers tp WHERE tp.paper_id=p.id AND tp.topic_id=? AND tp.excluded=?)');params.extend([topic,int(excluded)])
    if favorite:conditions.append('p.favorite=1')
    if unread:conditions.append('p.is_read=0')
    if source:conditions.append('p.source=?');params.append(source)
    if scope:conditions.append('EXISTS (SELECT 1 FROM versions v WHERE v.paper_id=p.id AND v.status=?)');params.append(scope)
    where=' WHERE '+' AND '.join(conditions) if conditions else ''
    total=one('SELECT COUNT(*) n FROM papers p'+where,params)['n']
    rows=all_rows('SELECT p.* FROM papers p'+where+' ORDER BY p.created DESC',params)
    scores=current_assessments(topic)
    for p in rows:
        p['assessment']=next((a for a in scores.get(p['id'],[]) if a['priority_score'] is not None),None)
    if ranked_only:rows=[p for p in rows if p['assessment']]
    if sort=='priority':rows.sort(key=lambda p:(p['assessment'] is not None,p['assessment']['priority_score'] if p['assessment'] else -1),reverse=True)
    total=len(rows);rows=rows[offset:offset+limit]
    for p in rows:
        p['authors']=json.loads(p['authors']);p['versions']=all_rows('SELECT id,label,status,created FROM versions WHERE paper_id=? ORDER BY updated DESC,created DESC',(p['id'],))
        report=one('SELECT r.id,r.scope,r.content FROM reports r JOIN versions v ON v.id=r.version_id WHERE v.paper_id=? ORDER BY r.created DESC LIMIT 1',(p['id'],))
        p['summary']=json.loads(report['content'])['summary'] if report else None
        p['topics']=[{**r,'name':json.loads(r.pop('config'))['name']} for r in all_rows('SELECT t.id,t.config,tp.reason,tp.excluded FROM topics t JOIN topic_papers tp ON t.id=tp.topic_id WHERE tp.paper_id=?',(p['id'],))]
    return {'items':rows,'total':total}


@app.get('/api/papers/{ident}')
def paper_detail(ident:str):
    p=require('papers',ident);p['authors']=json.loads(p['authors'])
    p['versions']=all_rows('SELECT * FROM versions WHERE paper_id=? ORDER BY updated DESC,created DESC',(ident,))
    for v in p['versions']:
        v['extraction']=json.loads((root()/v['extraction_path']).read_text()) if v['extraction_path'] else None
        v['reports']=all_rows('SELECT * FROM reports WHERE version_id=? ORDER BY created DESC',(v['id'],))
        for r in v['reports']:r['content']=json.loads(r['content'])
    p['assessments']=current_assessments().get(ident,[])
    p['topics']=all_rows('SELECT topic_id,reason,excluded FROM topic_papers WHERE paper_id=?',(ident,))
    return p


class PaperState(BaseModel):
    favorite:bool|None=None
    is_read:bool|None=None
    notes:str|None=Field(default=None,max_length=100000)


@app.patch('/api/papers/{ident}')
def paper_state(ident:str,value:PaperState):
    require('papers',ident)
    for key,val in value.model_dump(exclude_none=True).items():
        execute(f'UPDATE papers SET {key}=? WHERE id=?',(val,ident))
    index_paper(ident);return {'ok':True}


class ReadInput(BaseModel):
    language:str='zh'
    force:bool=False


@app.post('/api/versions/{ident}/read')
def read_version(ident:str,value:ReadInput):
    require('versions',ident)
    if value.language not in ('zh','en'):raise ValueError('不支持的总结语言')
    job=queue_read(ident,language=value.language,force=value.force)
    if job['state']=='succeeded' and not one('SELECT id FROM reports WHERE job_id=?',(job['id'],)):
        job=queue_read(ident,language=value.language,force=True)
    if job['state'] in ('queued','blocked','failed','cancelled','retry_wait'):
        payload=json.loads(job['payload']);payload.update(automatic=False,topic_id=None)
        execute("UPDATE jobs SET state='queued',payload=?,available=?,attempts=0,token=NULL WHERE id=?",(dumps(payload),now(),job['id']))
    return require('jobs',job['id'])


class ImportInput(BaseModel):
    identifier:str
    topic_id:str|None=None


@app.post('/api/imports/arxiv')
def import_arxiv(value:ImportInput):
    if value.topic_id:require('topics',value.topic_id)
    return enqueue('import',{'identifier':sources.identifier(value.identifier),'topic_id':value.topic_id})


@app.post('/api/imports/pdf')
async def import_pdf(file:UploadFile=File(...),title:str=Form(''),topic_id:str=Form('')):
    if topic_id:require('topics',topic_id)
    data=bytearray()
    while part:=await file.read(1024*1024):
        data.extend(part)
        if len(data)>50*1024*1024:raise HTTPException(413,'PDF 大小不能超过 50 MB')
    if not data.startswith(b'%PDF-'):raise ValueError('请上传有效 PDF 文件')
    try:
        with pymupdf.open(stream=bytes(data),filetype='pdf') as doc:
            if doc.needs_pass or doc.page_count<1:raise ValueError('PDF 已加密或没有页面')
            metadata_title=doc.metadata.get('title','')
    except Exception as e:raise ValueError('无法读取 PDF：文件损坏、加密或格式无效') from e
    sha=hashlib.sha256(data).hexdigest();path=f'uploads/{sha}.pdf'
    with asset_lock():
        target=root()/path;target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            temp=target.with_suffix('.'+uid()+'.tmp');temp.write_bytes(data);temp.replace(target)
        entry={'identity':'sha256:'+sha,'title':title.strip() or metadata_title or Path(file.filename or '导入论文').stem,
               'source':'local','label':'import','pdf_path':path,'sha256':sha}
        pid,v,new,_=sources.upsert(entry,topic_id or None)
    job=queue_read(v['id'],topic_id or None)
    return {'paper_id':pid,'new':new,'job_id':job['id']}


@app.get('/api/assets/{path:path}')
def asset(path:str):
    base=root();p=(base/path).resolve()
    if not p.is_relative_to(base) or not p.is_file():raise HTTPException(404,'文件不存在')
    # Restrict to recorded source/preview assets, never settings or database files.
    if p.suffix not in ('.pdf','.png') or path.split('/')[0] not in ('papers','uploads'):raise HTTPException(404)
    return FileResponse(p)


@app.post('/api/reports/{ident}/assess')
def assess_report(ident:str):
    require('reports',ident)
    return {'jobs':queue_assessments(ident)}


@app.post('/api/assessments/backfill')
def backfill_assessments():
    reports=all_rows("SELECT r.id FROM reports r WHERE r.id=(SELECT id FROM reports WHERE version_id=r.version_id ORDER BY created DESC,rowid DESC LIMIT 1) AND r.version_id=(SELECT id FROM versions WHERE paper_id=(SELECT paper_id FROM versions WHERE id=r.version_id) ORDER BY updated DESC,created DESC LIMIT 1)")
    jobs=[j for r in reports for j in queue_assessments(r['id'])]
    return {'jobs':jobs}


@app.post('/api/reports/{ident}/summary')
def regenerate_summary(ident:str):
    require('reports',ident)
    return enqueue('summary',{'report_id':ident},f'summary-v2:{ident}')


@app.get('/api/reports/{ident}/export')
def report_export(ident:str,include_pdf:bool=False):
    require('reports',ident)
    return Response(export_zip(ident,include_pdf),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="paper-{ident[:8]}.zip"'})


@app.get('/api/jobs')
def jobs():
    rows=all_rows('SELECT * FROM jobs ORDER BY created DESC LIMIT 200')
    for r in rows:r['payload']=json.loads(r['payload']);r['result']=json.loads(r['result']) if r['result'] else None
    return rows


@app.post('/api/jobs/{ident}/retry')
def retry(ident:str):
    row=require('jobs',ident)
    if row['state']=='running':raise HTTPException(409,'任务正在运行')
    if row['state']=='succeeded':raise HTTPException(409,'任务已完成；请在论文详情选择重新阅读')
    execute("UPDATE jobs SET state='queued',available=?,attempts=0,token=NULL,error=NULL,updated=? WHERE id=?",(now(),now(),ident))
    return {'ok':True}


@app.post('/api/jobs/{ident}/cancel')
def cancel(ident:str):
    require('jobs',ident)
    execute("UPDATE jobs SET state='cancelled',updated=? WHERE id=? AND state!='succeeded'",(now(),ident))
    return {'ok':True}


@app.get('/api/settings')
def get_settings():return settings()


@app.put('/api/settings')
def put_settings(value:Settings):
    save_settings(value)
    execute("UPDATE jobs SET state='queued',available=? WHERE state='blocked' AND (error LIKE '%模型%' OR error LIKE '%额度%' OR error LIKE '%预算%')",(now(),))
    return settings()


@app.post('/api/settings/models')
def models():
    cfg=settings(True)
    headers={'Authorization':'Bearer '+cfg['api_key']} if cfg['api_key'] else {}
    with httpx.Client(timeout=20,follow_redirects=False) as c:r=c.get(cfg['base_url']+'/models',headers=headers)
    if r.status_code>=400:raise ValueError(f'模型列表获取失败（HTTP {r.status_code}），可在高级设置填写模型标识')
    try:return {'models':sorted(x['id'] for x in r.json()['data'] if isinstance(x.get('id'),str))}
    except Exception:raise ValueError('服务未返回标准模型列表，可手动填写模型标识')


@app.post('/api/settings/codex/status')
def codex_status():
    from .codex_adapter import status
    return status(settings(True))


@app.post('/api/settings/test')
def test_connection():
    return enqueue('probe',{})


@app.get('/api/usage')
def usage():
    return all_rows('SELECT model,state,COUNT(*) calls,SUM(input_tokens) input_tokens,SUM(output_tokens) output_tokens,SUM(reserved) reserved FROM calls GROUP BY model,state')


WEB=Path(__file__).resolve().parent.parent/'web'/'dist'
if WEB.exists():app.mount('/',StaticFiles(directory=WEB,html=True),name='web')
