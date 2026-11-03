"""Explicit preview/confirm library deletion, with durable file cleanup."""
import hashlib
import json
import re
import shutil
from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,Field
from fastapi import HTTPException
from .store import db,root,now,uid,dumps,asset_lock
from .assessment import current_assessments

class CleanupFilter(BaseModel):
    mode:Literal['unprocessed','read','low_score','all']='unprocessed'
    topic_id:str=''
    older_days:Literal[0,7,30,90,180,365]=0
    score_below:int=Field(default=60,ge=0,le=100)
    protect_favorites:bool=True
    protect_notes:bool=True

class CleanupCommit(BaseModel):
    token:str
    paper_ids:list[str]=Field(min_length=1,max_length=10000)
    confirmation:str


def rows(c,sql,args=()):return [dict(r) for r in c.execute(sql,args)]

def snapshot(c,ids):
    values=[]
    for pid in sorted(ids):
        values.append([
            rows(c,'SELECT * FROM papers WHERE id=?',(pid,)),
            rows(c,'SELECT * FROM versions WHERE paper_id=? ORDER BY id',(pid,)),
            rows(c,'SELECT r.* FROM reports r JOIN versions v ON v.id=r.version_id WHERE v.paper_id=? ORDER BY r.id',(pid,)),
            rows(c,'SELECT * FROM assessments WHERE paper_id=? ORDER BY id',(pid,)),
            rows(c,'SELECT * FROM topic_papers WHERE paper_id=? ORDER BY topic_id',(pid,)),
            rows(c,'SELECT t.* FROM topics t JOIN topic_papers tp ON tp.topic_id=t.id WHERE tp.paper_id=? ORDER BY t.id',(pid,))])
    return hashlib.sha256(dumps(values).encode()).hexdigest()


def preview(filters):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        scores=current_assessments(filters.topic_id) if filters.mode=='low_score' else {}
        candidates=[];protected=0
        cutoff=(datetime.now(timezone.utc)-timedelta(days=filters.older_days)).isoformat()
        for p in rows(c,'SELECT * FROM papers ORDER BY created DESC'):
            if filters.topic_id and not c.execute('SELECT 1 FROM topic_papers WHERE paper_id=? AND topic_id=?',(p['id'],filters.topic_id)).fetchone():continue
            if filters.older_days and p['created']>=cutoff:continue
            count=c.execute('SELECT COUNT(*) FROM reports r JOIN versions v ON r.version_id=v.id WHERE v.paper_id=?',(p['id'],)).fetchone()[0]
            score=next((a['priority_score'] for a in scores.get(p['id'],[]) if a['priority_score'] is not None),None)
            if filters.mode=='unprocessed' and count:continue
            if filters.mode=='read' and not p['is_read']:continue
            if filters.mode=='low_score' and (score is None or score>=filters.score_below):continue
            if (filters.protect_favorites and p['favorite']) or (filters.protect_notes and p['notes'].strip()):
                protected+=1;continue
            candidates.append({'id':p['id'],'title':p['title'],'favorite':bool(p['favorite']),'has_notes':bool(p['notes'].strip()),'is_read':bool(p['is_read']),'reports':count,'priority_score':score})
        if len(candidates)>10000:raise HTTPException(400,'候选超过一万篇，请缩小清理条件')
        token=uid();ids=[p['id'] for p in candidates]
        expires=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()
        c.execute('DELETE FROM cleanup_previews WHERE expires<?',(now(),))
        c.execute('INSERT INTO cleanup_previews VALUES(?,?,?,?,?)',(token,dumps(ids),snapshot(c,ids),expires,dumps(filters.model_dump())))
        return {'token':token,'expires':expires,'items':candidates,'count':len(ids),'protected':protected}


def collect_files():
    with asset_lock():return _collect_files()


def _collect_files():
    """Retry only committed deletions. Never follow symlinks outside app storage."""
    with db() as c:pending=rows(c,'SELECT path FROM cleanup_files')
    failed=[];base=root().resolve()
    for row in pending:
        relative=row['path'];path=base/relative
        try:
            parts=Path(relative).parts
            if len(parts)!=2 or parts[0] not in ('papers','uploads') or parts[1] in ('.','..'):
                raise ValueError('清理路径不属于论文存储目录')
            if not path.resolve().is_relative_to(base):raise ValueError('文件路径越过数据目录')
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                # A later explicit import can reuse an upload; never delete live assets.
                if parts[0]=='uploads' and c.execute('SELECT 1 FROM versions WHERE pdf_path=?',(relative,)).fetchone():
                    c.execute('DELETE FROM cleanup_files WHERE path=?',(relative,));continue
                if parts[0]=='papers' and c.execute('SELECT 1 FROM papers WHERE id=?',(parts[1],)).fetchone():
                    c.execute('DELETE FROM cleanup_files WHERE path=?',(relative,));continue
                if path.is_symlink():path.unlink()
                elif path.is_dir():shutil.rmtree(path)
                elif path.exists():path.unlink()
                c.execute('DELETE FROM cleanup_files WHERE path=?',(relative,))
        except (OSError,ValueError) as e:failed.append({'path':relative,'error':str(e)[:150]})
    return failed


def commit(value):
    ids=list(dict.fromkeys(value.paper_ids))
    if value.confirmation!=f'删除 {len(ids)} 篇':raise HTTPException(400,'确认文字不匹配')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        plan=c.execute('SELECT * FROM cleanup_previews WHERE token=?',(value.token,)).fetchone()
        if not plan or plan['expires']<now():raise HTTPException(409,'清理预览已过期，请重新预览')
        planned=json.loads(plan['paper_ids'])
        if not set(ids)<=set(planned):raise HTTPException(400,'只能删除本次预览中的论文')
        if snapshot(c,planned)!=plan['fingerprint']:raise HTTPException(409,'论文或保护状态已变化，请重新预览后确认')
        # Stops races with downloading/reading/scanning jobs; the same write lock guards claims.
        if c.execute("SELECT 1 FROM jobs WHERE state='running'").fetchone():
            raise HTTPException(409,'有任务正在处理论文，请等待任务结束或取消后重新确认')
        version_ids=set();report_ids=set();paths=set()
        for pid in ids:
            if not re.fullmatch(r'[A-Za-z0-9_-]+',pid):raise HTTPException(400,'论文标识无效')
            paths.add('papers/'+pid)
            for v in rows(c,'SELECT id,pdf_path FROM versions WHERE paper_id=?',(pid,)):
                version_ids.add(v['id'])
                if v['pdf_path'] and v['pdf_path'].startswith('uploads/'):paths.add(v['pdf_path'])
            report_ids.update(r['id'] for r in rows(c,'SELECT r.id FROM reports r JOIN versions v ON v.id=r.version_id WHERE v.paper_id=?',(pid,)))
        for job in rows(c,'SELECT * FROM jobs'):
            payload=json.loads(job['payload']);result=json.loads(job['result'] or '{}')
            if payload.get('version_id') in version_ids or payload.get('report_id') in report_ids or result.get('paper_id') in ids or result.get('report_id') in report_ids:
                c.execute("UPDATE jobs SET state='cancelled',payload='{}',result=NULL,dedupe=NULL,token=NULL,error=NULL,progress='论文已从库中删除',updated=? WHERE id=?",(now(),job['id']))
                c.execute('UPDATE calls SET response=NULL WHERE job_id=?',(job['id'],))
        for pid in ids:
            c.execute('DELETE FROM assessments WHERE paper_id=?',(pid,))
            c.execute('DELETE FROM reports WHERE version_id IN (SELECT id FROM versions WHERE paper_id=?)',(pid,))
            c.execute('DELETE FROM versions WHERE paper_id=?',(pid,))
            c.execute('DELETE FROM topic_papers WHERE paper_id=?',(pid,))
            c.execute('DELETE FROM paper_search WHERE paper_id=?',(pid,))
            c.execute('DELETE FROM papers WHERE id=?',(pid,))
        for path in paths:
            c.execute('INSERT OR IGNORE INTO cleanup_files VALUES(?)',(path,))
        c.execute('DELETE FROM cleanup_previews WHERE token=?',(value.token,))
    failures=collect_files()
    return {'deleted':len(ids),'file_cleanup_pending':failures,'message':f'已删除 {len(ids)} 篇论文'}
