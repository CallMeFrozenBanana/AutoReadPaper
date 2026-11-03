import io
import json
import zipfile
import pytest
from autoreadpaper.store import execute,one,all_rows,root,now
from autoreadpaper.cleanup import collect_files


def upload(client,pdf):
    return client.post('/api/imports/pdf',files={'file':('test.pdf',pdf,'application/pdf')}).json()['paper_id']

def plan(client,**kw):
    r=client.post('/api/library/cleanup/preview',json=kw);assert r.status_code==200,r.text
    return r.json()

def remove(client,p,ids=None):
    ids=ids if ids is not None else [r['id'] for r in p['items']]
    return client.post('/api/library/cleanup/commit',json={'token':p['token'],'paper_ids':ids,'confirmation':f'删除 {len(ids)} 篇'})


def test_preview_does_not_delete_and_protects_notes_favorites(client,pdf_bytes):
    pid=upload(client,pdf_bytes)
    client.patch('/api/papers/'+pid,json={'favorite':True,'notes':'keep'})
    assert plan(client)['count']==0
    assert plan(client,protect_favorites=False)['count']==0
    assert plan(client,protect_favorites=False,protect_notes=False)['count']==1
    assert one('SELECT COUNT(*) n FROM papers')['n']==1
    assert (root()/one('SELECT pdf_path FROM versions')['pdf_path']).exists()


def test_confirm_deletes_files_search_and_jobs_but_keeps_usage(client,pdf_bytes):
    pid=upload(client,pdf_bytes);v=one('SELECT * FROM versions');job=one('SELECT * FROM jobs')
    folder=root()/'papers'/pid;folder.mkdir(parents=True);(folder/'page.png').write_bytes(b'fixture')
    execute('INSERT INTO calls(id,job_id,cache_key,model,state,reserved,input_tokens,output_tokens,response,created) VALUES(?,?,?,?,?,?,?,?,?,?)',('call',job['id'],'key','fixture','succeeded',100,20,10,'{"private":"summary"}',now()))
    p=plan(client)
    wrong=client.post('/api/library/cleanup/commit',json={'token':p['token'],'paper_ids':[pid],'confirmation':'yes'})
    assert wrong.status_code==400 and one('SELECT COUNT(*) n FROM papers')['n']==1
    r=remove(client,p);assert r.status_code==200,r.text
    assert r.json()['deleted']==1 and not r.json()['file_cleanup_pending']
    for table in ['papers','versions','reports','assessments','topic_papers','paper_search']:
        assert one(f'SELECT COUNT(*) n FROM {table}')['n']==0
    assert not (root()/v['pdf_path']).exists() and not folder.exists()
    assert one('SELECT state,dedupe FROM jobs')=={'state':'cancelled','dedupe':None}
    assert one('SELECT input_tokens,output_tokens,response FROM calls')=={'input_tokens':20,'output_tokens':10,'response':None}
    assert remove(client,p).status_code==409
    # Explicit reimport creates a usable new job, not an old cancelled dedupe hit.
    new=upload(client,pdf_bytes);assert new!=pid
    assert one("SELECT COUNT(*) n FROM jobs WHERE state='queued'")['n']==1


def test_preview_stale_selection_and_running_tasks_are_blocked(client,pdf_bytes):
    pid=upload(client,pdf_bytes);p=plan(client)
    assert remove(client,p,['not-in-preview']).status_code==400
    client.patch('/api/papers/'+pid,json={'favorite':True})
    assert remove(client,p).status_code==409
    p=plan(client,protect_favorites=False)
    execute("UPDATE jobs SET state='running'")
    assert remove(client,p).status_code==409
    assert one('SELECT COUNT(*) n FROM papers')['n']==1
    execute("UPDATE jobs SET state='queued'")
    execute("UPDATE cleanup_previews SET expires='2000-01-01'")
    assert remove(client,p).status_code==409


def test_filter_read_age_topic_and_unscored_is_not_low(client,pdf_bytes):
    pid=upload(client,pdf_bytes)
    assert plan(client,mode='low_score')['count']==0
    assert plan(client,mode='read')['count']==0
    client.patch('/api/papers/'+pid,json={'is_read':True})
    assert plan(client,mode='read')['count']==1
    assert plan(client,older_days=30)['count']==0
    execute("UPDATE papers SET created='2020-01-01'")
    assert plan(client,older_days=30)['count']==1
    assert plan(client,topic_id='unrelated')['count']==0


def test_file_failure_is_retriable_and_shared_upload_is_protected(client,pdf_bytes,monkeypatch):
    from pathlib import Path
    pid=upload(client,pdf_bytes);upload_path=one('SELECT pdf_path FROM versions')['pdf_path']
    p=plan(client)
    original=Path.unlink
    def fail(self,*a,**kw):
        if self.name.endswith('.pdf'):raise PermissionError('test locked')
        return original(self,*a,**kw)
    monkeypatch.setattr(Path,'unlink',fail)
    r=remove(client,p);assert r.status_code==200 and r.json()['file_cleanup_pending']
    assert one('SELECT COUNT(*) n FROM papers')['n']==0
    monkeypatch.setattr(Path,'unlink',original)
    # Reimport may reuse the same file while pending cleanup must not remove it.
    upload(client,pdf_bytes)
    assert collect_files()==[] and (root()/upload_path).exists()
    assert all_rows('SELECT * FROM cleanup_files')==[]


def test_file_cleanup_rejects_paths_outside_assets(client,pdf_bytes,tmp_path):
    sentinel=tmp_path/'untouched.txt';sentinel.write_text('keep')
    execute('INSERT INTO cleanup_files VALUES(?)',('../untouched.txt',))
    assert collect_files() and sentinel.read_text()=='keep'


def test_all_mode_removes_reports_and_scores(client,pdf_bytes):
    pid=upload(client,pdf_bytes);vid=one('SELECT id FROM versions')['id']
    execute('INSERT INTO reports VALUES(?,?,?,?,?,?,?)',('r',vid,'other','cfg','fulltext','{}',now()))
    execute('INSERT INTO assessments VALUES(?,?,?,?,?,?,?,?,?,?,?)',('a','j',pid,vid,'r','t',1,50,50,'{}',now()))
    assert plan(client)['count']==0
    p=plan(client,mode='all');assert p['items'][0]['reports']==1
    assert remove(client,p).status_code==200
    assert not all_rows('SELECT * FROM reports') and not all_rows('SELECT * FROM assessments')


def test_only_checked_subset_is_deleted(client,pdf_bytes):
    first=upload(client,pdf_bytes);second=upload(client,pdf_bytes+b'\n% second fixture\n')
    remaining_path=one('SELECT pdf_path FROM versions WHERE paper_id=?',(second,))['pdf_path']
    p=plan(client);assert p['count']==2
    result=remove(client,p,[first]);assert result.status_code==200
    assert [r['id'] for r in all_rows('SELECT id FROM papers')]==[second]
    assert (root()/remaining_path).exists()
