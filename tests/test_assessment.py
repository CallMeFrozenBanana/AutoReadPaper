import json
import pytest
from autoreadpaper.assessment import validate_assessment,queue_assessments,current_assessments
from autoreadpaper.store import execute,one,all_rows,now,atomic_json
from autoreadpaper.worker import claim,process
from autoreadpaper.reader import Model
from autoreadpaper.config import Settings,save_settings

REF={'block_id':'b1','quote':'We test 100 episodes.','page':1,'bbox':[0,0,10,10]}
NOTES=[{'section':'实验','text':'测试结果','kind':'author_claim','verified':True,'evidence':[REF]}]

def output(scores=(3,4,2,5)):
    return {'dimensions':[{'key':k,'score':v,'reason':'基于测试条件的评估','confidence':'medium','note_ids':[0]} for k,v in zip(('novelty','results','rigor','relevance'),scores)],'strengths':['报告了测试条件'],'weaknesses':['未独立复现']}

def seed(client,pid='p',created=None):
    t=client.post('/api/topics',json={'name':'视觉导航 '+pid,'keywords':['navigation'],'frequency':'manual'}).json()
    execute('INSERT INTO papers(id,identity,title,source,created) VALUES(?,?,?,?,?)',(pid,pid,'Paper '+pid,'local',created or now()))
    execute('INSERT INTO versions(id,paper_id,label,updated,created,extraction_path,status) VALUES(?,?,?,?,?,?,?)',('v'+pid,pid,'v1',now(),now(),pid+'.json','fulltext'))
    atomic_json(pid+'.json',{'blocks':[{'id':'b1','text':REF['quote'],'page':1,'bbox':REF['bbox']}]})
    content={'title':'Paper '+pid,'items':NOTES,'scope':'fulltext','processed_pages':1,'total_pages':1,'summary':'summary'}
    execute('INSERT INTO reports VALUES(?,?,?,?,?,?,?)',('r'+pid,'v'+pid,'original'+pid,'cfg','fulltext',json.dumps(content),now()))
    execute('INSERT INTO topic_papers VALUES(?,?,?,?,?)',(t['id'],pid,'match',0,1))
    return t

def test_fixed_weights_and_missing_evidence():
    a=validate_assessment(output(),NOTES)
    assert a['priority_score']==67
    assert a['quality_score']==58.8
    assert a['confidence']=='medium'
    missing=output((None,4,2,5));missing['dimensions'][0]['note_ids']=[]
    a=validate_assessment(missing,NOTES)
    assert a['priority_score'] is None and a['quality_score'] is None

@pytest.mark.parametrize('change',[{'score':9},{'score':float('nan')},{'score':True},{'score':2.2},{'note_ids':[99]},{'note_ids':[]}])
def test_invalid_scoring_is_rejected(change):
    raw=output();raw['dimensions'][0].update(change)
    with pytest.raises(ValueError):validate_assessment(raw,NOTES)

def test_scoring_job_idempotence_and_topic_staleness(client,monkeypatch):
    t=seed(client);save_settings(Settings(enabled=True,model='fixture'))
    calls=[]
    def respond(self,*args,**kw):calls.append(args);return output()
    monkeypatch.setattr(Model,'call',respond)
    a=queue_assessments('rp');b=queue_assessments('rp');assert a[0]['id']==b[0]['id']
    process(claim());assert len(calls)==1
    assert one('SELECT state FROM jobs')['state']=='succeeded'
    assert current_assessments()['p'][0]['priority_score']==67
    # Replay after persisted scoring must not incur another model call.
    execute("UPDATE jobs SET state='queued'");process(claim());assert len(calls)==1
    client.put('/api/topics/'+t['id'],json={**t,'name':'新主题'})
    assert current_assessments()=={}
    assert len(all_rows('SELECT * FROM assessments'))==1
    assert queue_assessments('rp')[0]['id']!=a[0]['id']

def test_priority_sort_before_pagination_and_latest_report(client,monkeypatch):
    seed(client,'old','2020-01-01');seed(client,'new','2026-01-01')
    save_settings(Settings(enabled=True,model='fixture'))
    monkeypatch.setattr(Model,'call',lambda self,*a,**kw:output((5,5,5,5)) if self.job['payload_obj']['report_id']=='rold' else output())
    queue_assessments('rold');queue_assessments('rnew');process(claim());process(claim())
    r=client.get('/api/papers?sort=priority&ranked_only=true&limit=1').json()
    assert r['total']==2 and r['items'][0]['id']=='old'
    assert client.get('/api/papers?sort=priority&ranked_only=true&offset=1&limit=1').json()['items'][0]['id']=='new'
    execute("UPDATE papers SET is_read=1 WHERE id='old'")
    assert client.get('/api/papers?sort=priority&ranked_only=true&unread=true').json()['total']==1
    old=one("SELECT * FROM reports WHERE id='rold'")
    execute('INSERT INTO reports VALUES(?,?,?,?,?,?,?)',('updated','vold','newjob','cfg','fulltext',old['content'],'2099-01-01'))
    assert 'old' not in current_assessments()
    assert len(all_rows('SELECT * FROM assessments'))==2

def test_partial_report_not_ranked_and_backfill_idempotent(client,monkeypatch):
    seed(client);r=json.loads(one('SELECT content FROM reports')['content']);r['scope']='partial_fulltext'
    execute('UPDATE reports SET content=?',(json.dumps(r),))
    save_settings(Settings(enabled=True,model='fixture'))
    monkeypatch.setattr(Model,'call',lambda *a,**kw:output())
    a=client.post('/api/assessments/backfill').json();b=client.post('/api/assessments/backfill').json()
    assert a['jobs'][0]['id']==b['jobs'][0]['id']
    process(claim())
    value=current_assessments()['p'][0]
    assert value['provisional'] and value['priority_score'] is None
    assert client.get('/api/papers?ranked_only=true').json()['total']==0


def test_read_automatically_scores_and_exports(client,pdf_bytes,monkeypatch):
    t=client.post('/api/topics',json={'name':'navigation','keywords':['navigation'],'frequency':'manual'}).json()
    save_settings(Settings(enabled=True,model='fixture',max_vision_pages=0))
    def respond(self,stage,prompt,*args,**kwargs):
        if stage=='assessment-v1':return output()
        if stage=='summary-v2':
            notes=json.loads(prompt.split('EVIDENCE-BACKED NOTES:\n')[1])
            return {'items':[{**notes[0],'section':str(i)} for i in range(4)]}
        b=json.loads(prompt.split('SOURCE BLOCKS:\n')[1])[0]
        return {'items':[{'section':'方法','text':'导航方法测试说明','kind':'author_claim','evidence':[{'block_id':b['id'],'quote':b['text']}]}]}
    monkeypatch.setattr(Model,'call',respond)
    r=client.post('/api/imports/pdf',data={'topic_id':t['id']},files={'file':('test.pdf',pdf_bytes,'application/pdf')})
    assert r.status_code==200
    process(claim())
    scoring=one("SELECT * FROM jobs WHERE kind='assess'")
    assert scoring and scoring['state']=='queued'
    process(claim())
    report=one('SELECT id FROM reports')
    import io,zipfile
    z=zipfile.ZipFile(io.BytesIO(client.get('/api/reports/'+report['id']+'/export').content))
    assert 'assessments.json' in z.namelist() and 'assessment.md' in z.namelist()
    assert json.loads(z.read('assessments.json'))[0]['priority_score']==67
