import io
import json
import zipfile
from datetime import datetime,timezone,timedelta
import pytest
from autoreadpaper.config import Topic,Settings,next_run,settings,save_settings
from autoreadpaper.store import one,all_rows,execute,enqueue,now,root
from autoreadpaper.worker import claim,process,schedule,reserve_article,queue_read
from autoreadpaper.reader import Model,Blocked,validated_items
from autoreadpaper.sources import upsert,identifier


def topic(client,**kwargs):
    r=client.post('/api/topics',json={'name':'导航','keywords':['navigation'],'frequency':'manual',**kwargs})
    assert r.status_code==200,r.text
    return r.json()


def upload(client,pdf_bytes):
    r=client.post('/api/imports/pdf',files={'file':('test.pdf',pdf_bytes,'application/pdf')})
    assert r.status_code==200,r.text
    return r.json()


def test_topic_validation_revision_and_schedule(client):
    assert client.post('/api/topics',json={'name':'bad','keywords':[]}).status_code==422
    assert client.post('/api/topics',json={'name':'bad','keywords':['x'],'timezone':'nope'}).status_code==422
    t=topic(client,frequency='daily')
    assert t['next_run']
    body={**t,'name':'视觉导航','daily_limit':3}
    assert client.put('/api/topics/'+t['id'],json=body).json()['revision']==2
    assert len(all_rows('SELECT * FROM topic_revisions'))==2
    execute('UPDATE topics SET next_run=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(days=2)).isoformat(),t['id']))
    schedule();schedule()
    assert len(all_rows("SELECT * FROM jobs WHERE kind='scan'"))==1
    assert client.patch('/api/topics/'+t['id'],json={'active':False}).status_code==200
    assert one('SELECT next_run FROM topics')['next_run'] is None


def test_weekly_timezone():
    cfg=Topic(name='x',keywords=['x'],frequency='weekly',weekday=0,time='09:00').model_dump()
    result=next_run(cfg,datetime(2026,11,2,2,tzinfo=timezone.utc))
    assert result=='2026-11-09T01:00:00+00:00'


def test_import_dedup_extraction_missing_model(client,pdf_bytes):
    a=upload(client,pdf_bytes);b=upload(client,pdf_bytes)
    assert a['paper_id']==b['paper_id'] and not b['new']
    assert len(all_rows('SELECT * FROM jobs'))==1
    job=claim();process(job)
    stored=one('SELECT * FROM jobs');assert stored['state']=='blocked'
    detail=client.get('/api/papers/'+a['paper_id']).json()
    v=detail['versions'][0]
    assert v['status']=='extracted' and not v['reports']
    assert v['extraction']['processed_pages']==1
    assert v['extraction']['figures'][0]['page']==1
    assert client.get('/api/assets/'+v['pdf_path']).content==pdf_bytes
    assert client.get('/api/assets/settings.json').status_code==404


def test_invalid_pdf_and_identifier(client):
    assert client.post('/api/imports/pdf',files={'file':('bad.pdf',b'bad')}).status_code==400
    assert client.post('/api/imports/arxiv',json={'identifier':'http://127.0.0.1/private'}).status_code==400
    assert identifier('https://arxiv.org/pdf/2108.10869v1.pdf')=='2108.10869v1'
    with pytest.raises(ValueError):identifier('https://arxiv.org.evil/abs/2108.10869')


def test_origin_and_host(client):
    assert client.post('/api/topics',headers={'Origin':'https://evil.example'},json={}).status_code==403
    assert client.get('/api/health',headers={'Host':'evil.example'}).status_code==403


def test_notes_search_delete_topic_preserves_papers(client,pdf_bytes):
    t=topic(client)
    r=client.post('/api/imports/pdf',data={'topic_id':t['id']},files={'file':('test.pdf',pdf_bytes)}).json()
    pid=r['paper_id']
    client.patch('/api/papers/'+pid,json={'notes':'视觉导航与闭环控制','favorite':True,'is_read':True})
    assert client.get('/api/papers',params={'q':'闭环'}).json()['total']==1
    assert client.get('/api/papers',params={'favorite':'true'}).json()['total']==1
    assert client.get('/api/papers',params={'unread':'true'}).json()['total']==0
    assert client.patch('/api/topics/'+t['id'],json={'archived':True}).status_code==422
    assert client.delete('/api/topics/'+t['id']).status_code==200
    assert one('SELECT state FROM jobs')['state']=='cancelled'
    assert all_rows('SELECT * FROM topic_papers')==[]
    assert client.get('/api/topics').json()==[]
    assert client.get('/api/papers').json()['total']==1


def test_secret_preservation(client):
    client.put('/api/settings',json={'api_key':'test-secret'})
    r=client.get('/api/settings');assert 'test-secret' not in r.text and r.json()['has_key']
    client.put('/api/settings',json={'api_key':'','model':'fixture-model'})
    assert settings(True)['api_key']=='test-secret'
    client.put('/api/settings',json={'clear_key':True})
    assert not settings(True)['api_key']
    assert (root()/'settings.json').stat().st_mode & 0o777 == 0o600


def test_evidence_rejects_hallucinated_quotes():
    block={'id':'p1b1','page':1,'bbox':[0,0,1,1],'text':'This is actual source evidence with 85 percent success.'}
    valid={'text':'Result','section':'Experiments','kind':'author_claim','evidence':[{'block_id':'p1b1','quote':'85 percent success'}]}
    invalid={**valid,'evidence':[{'block_id':'p1b1','quote':'99 percent success'}]}
    items,issues=validated_items({'items':[valid,invalid]},[block])
    assert items[0]['verified'] and not items[1]['verified'] and len(issues)==1


def test_cancel_and_recover_lease(client):
    a=enqueue('read',{'version_id':'x'},'one');assert enqueue('read',{'version_id':'x'},'one')['id']==a['id']
    j=claim();assert j['state']=='running' and claim() is None
    execute('UPDATE jobs SET lease_until=?',('2000-01-01T00:00:00+00:00',))
    schedule();new=claim();assert new['token']!=j['token']
    client.post('/api/jobs/'+j['id']+'/cancel')
    process(new)
    assert one('SELECT state FROM jobs')['state']=='cancelled'


def test_reading_quota_atomic_reuse(client):
    t=topic(client,daily_limit=1)
    s=Settings(global_daily_limit=2).model_dump()
    a={'id':'a','payload_obj':{'topic_id':t['id']}}
    reserve_article(a,s);reserve_article(a,s)
    with pytest.raises(Blocked):reserve_article({'id':'b','payload_obj':{'topic_id':t['id']}},s)
    reserve_article({'id':'b','payload_obj':{}},s)
    with pytest.raises(Blocked):reserve_article({'id':'c','payload_obj':{}},s)


def test_versions_preserve_metadata():
    e={'identity':'arxiv:test','title':'Old','abstract':'old abstract','source':'arxiv','label':'v1','updated':'2026-01-01'}
    pid,v,_,_=upsert(e)
    _,v2,new,_=upsert({**e,'title':'New','abstract':'new abstract','label':'v2','updated':'2026-02-01'})
    assert new and v['id']!=v2['id']
    assert one('SELECT title FROM papers')['title']=='New'
    assert json.loads(one('SELECT metadata FROM versions WHERE id=?',(v['id'],))['metadata'])['title']=='Old'
    upsert(e)
    assert one('SELECT title FROM papers')['title']=='New'


def test_model_cache_and_unknown_usage(monkeypatch):
    cfg=Settings(enabled=True,model='fixture',daily_token_limit=50000).model_dump()
    j={'id':'job'};calls=[]
    class Response:
        status_code=200
        def json(self):return {'choices':[{'message':{'content':'{"ok":true}'},'finish_reason':'stop'}],'usage':{'prompt_tokens':50,'completion_tokens':10}}
    class Client:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,*a,**kw):calls.append(kw);return Response()
    monkeypatch.setattr('autoreadpaper.reader.httpx.Client',Client)
    m=Model(j,cfg)
    assert m.call('test','hello')=={'ok':True}
    assert m.call('test','hello')=={'ok':True}
    assert len(calls)==1 and one('SELECT input_tokens FROM calls')['input_tokens']==50
    cfg['daily_token_limit']=1000
    with pytest.raises(Blocked):Model({'id':'other'},cfg).call('x','a'*2000)


def test_end_to_end_report_export_with_controlled_model(client,pdf_bytes,monkeypatch):
    save_settings(Settings(enabled=True,model='fixture-model',vision_model='fixture-vision'))
    stages=[]
    def respond(self,stage,prompt,images=None,model=None):
        stages.append(stage)
        if stage=='summary-v2':
            notes=json.loads(prompt.split('EVIDENCE-BACKED NOTES:\n')[1])
            return {'items':[{**notes[0],'section':heading,'text':heading+'：这是一段综合全文的测试说明。'} for heading in ['研究问题','核心方法','主要结果','局限与适用范围']]}
        if stage.startswith('figure'):return {'description':'测试图表说明，仅用于软件验证。'}
        batch=json.loads(prompt.split('SOURCE BLOCKS:\n')[1])
        b=batch[0]
        return {'items':[{'section':'方法详解','text':'这是一条受控测试总结，不是真实模型研究结论。','kind':'author_claim','evidence':[{'block_id':b['id'],'quote':b['text'][:40]}]}]}
    monkeypatch.setattr(Model,'call',respond)
    a=upload(client,pdf_bytes);process(claim())
    job=one('SELECT * FROM jobs');assert job['state']=='succeeded',job['error']
    p=client.get('/api/papers/'+a['paper_id']).json()
    r=p['versions'][0]['reports'][0]
    assert r['content']['items'][0]['verified']
    assert r['content']['figures'][0]['visual']
    assert len(r['content']['summary_sections'])==4
    assert r['content']['summary']!=r['content']['items'][0]['text']
    out=client.get('/api/reports/'+r['id']+'/export?include_pdf=true')
    z=zipfile.ZipFile(io.BytesIO(out.content))
    assert {'summary.md','report.json','images/page-1.png','source.pdf'}<=set(z.namelist())
    assert z.read('source.pdf')==pdf_bytes
    assert '## 论文速览' in z.read('summary.md').decode()
    assert '主要结果' in z.read('summary.md').decode()
    # Restart after publication must reuse the committed report.
    execute("UPDATE jobs SET state='queued' WHERE id=?",(job['id'],))
    process(claim());assert len(all_rows('SELECT * FROM reports'))==1
    before=list(stages)
    summary_job=client.post('/api/reports/'+r['id']+'/summary').json()
    assert client.post('/api/reports/'+r['id']+'/summary').json()['id']==summary_job['id']
    process(claim())
    assert one('SELECT state FROM jobs WHERE id=?',(summary_job['id'],))['state']=='succeeded'
    assert stages==before+['summary-v2']  # No repeat of body or image reading.
    assert len(all_rows('SELECT * FROM reports'))==2
    assert json.loads(one('SELECT content FROM reports WHERE id=?',(r['id'],))['content'])==r['content']


def test_scan_pagination_replay_and_cutoff(client,monkeypatch):
    t=topic(client)
    cfg={k:v for k,v in t.items() if k in Topic.model_fields}
    entries=[{'identity':'arxiv:1','title':'Test','abstract':'navigation','source':'arxiv','label':'v1','updated':now(),'pdf_url':'https://arxiv.org/pdf/1'}]
    monkeypatch.setattr('autoreadpaper.sources.fetch',lambda params:(entries,1,'<feed/>'))
    for _ in range(2):
        enqueue('scan',{'topic_id':t['id'],'config':cfg,'revision':1})
        job=one("SELECT * FROM jobs WHERE kind='scan' AND state='queued' ORDER BY created LIMIT 1")
        # Hold reads so scan jobs can be claimed deterministically.
        execute("UPDATE jobs SET available='2999-01-01' WHERE kind='read'")
        process(claim())
    assert len(all_rows('SELECT * FROM papers'))==1
    assert len(all_rows("SELECT * FROM jobs WHERE kind='read'"))==1
    assert all(s['complete'] for s in all_rows('SELECT * FROM scans'))


def test_manual_read_can_override_relevance_skip(client,pdf_bytes):
    a=upload(client,pdf_bytes)
    execute("UPDATE jobs SET state='succeeded',result=?",(json.dumps({'decision':'uncertain'}),))
    v=one('SELECT id FROM versions')['id']
    r=client.post('/api/versions/'+v+'/read',json={}).json()
    assert r['state']=='queued' and r['id']!=a['job_id']


def test_codex_provider_uses_adapter_and_records_usage(monkeypatch):
    cfg=Settings(provider='codex_cli',enabled=True).model_dump()
    seen=[]
    def fake(config,stage,prompt,images,check):
        seen.append((stage,prompt,images));return {'ok':True},{'input_tokens':20,'output_tokens':4}
    monkeypatch.setattr('autoreadpaper.codex_adapter.invoke',fake)
    result=Model({'id':'cli-job'},cfg).call('probe','Return JSON',[])
    assert result['ok'] and seen[0][0]=='probe'
    assert one('SELECT model,input_tokens,output_tokens FROM calls')=={'model':'codex:default','input_tokens':20,'output_tokens':4}
    Model({'id':'cli-job'},cfg).call('probe','Return JSON',[])
    assert len(seen)==1


def test_codex_default_readiness_and_configuration(client):
    r=client.put('/api/settings',json={'provider':'codex_cli','enabled':True})
    assert r.status_code==200 and r.json()['provider']=='codex_cli'
    assert client.get('/api/stats').json()['model_ready']
    assert client.post('/api/settings/test',json={}).json()['kind']=='probe'
    assert client.put('/api/settings',json={'provider':'unknown'}).status_code==422


def test_codex_failures_are_accounted_for(monkeypatch):
    def fail(*args):raise ValueError('CLI unavailable')
    monkeypatch.setattr('autoreadpaper.codex_adapter.invoke',fail)
    with pytest.raises(ValueError):Model({'id':'cli-job'},Settings(provider='codex_cli',enabled=True).model_dump()).call('probe','x',[])
    assert one('SELECT state FROM calls')['state']=='unknown'


def test_codex_cli_contract_no_shell_and_strict_schema(monkeypatch):
    from autoreadpaper.codex_adapter import invoke
    captured={}
    class Pipe:
        def write(self,s):captured['prompt']=s
        def close(self):pass
    class Process:
        returncode=0
        pid=12345
        def __init__(self,cmd,**kwargs):
            captured['cmd']=cmd;captured['kwargs']=kwargs
            from pathlib import Path
            Path(cmd[cmd.index('-o')+1]).write_text('{"ok":true}')
            kwargs['stdout'].write('{"type":"turn.completed","usage":{"input_tokens":5,"output_tokens":3}}\n')
            self.stdin=Pipe()
        def poll(self):return 0
    monkeypatch.setattr('autoreadpaper.codex_adapter.executable',lambda c:'/usr/bin/codex')
    monkeypatch.setattr('autoreadpaper.codex_adapter.subprocess.Popen',Process)
    result,usage=invoke(Settings(provider='codex_cli').model_dump(),'probe','untrusted $(touch /tmp/no)',[])
    assert result['ok'] and usage['output_tokens']==3
    assert 'read-only' in captured['cmd'] and '--ephemeral' in captured['cmd']
    assert 'shell' not in captured['kwargs'] and captured['cmd'][-1]=='-'
    assert '$(touch /tmp/no)' not in ' '.join(captured['cmd'])
    assert '--dangerously-bypass-approvals-and-sandbox' not in captured['cmd']


def test_summary_rejects_untraceable_evidence():
    from autoreadpaper.reader import synthesize_summary
    class Fake:
        s=Settings(enabled=True,model='fixture').model_dump()
        def call(self,stage,prompt):
            return {'items':[{'text':'unsupported result','section':str(i),'evidence':[{'block_id':'missing','quote':'invented quote'}]} for i in range(4)]}
    with pytest.raises(ValueError,match='依据校验失败'):
        synthesize_summary(Fake(),'paper',[{'text':'note','verified':True,'evidence':[{'block_id':'b1','quote':'original source'}]}],[{'id':'b1','text':'original source','page':1,'bbox':[]}])


def test_legacy_archived_topics_restore_once(client):
    from autoreadpaper.store import init
    t=topic(client)
    execute("UPDATE topics SET archived=1 WHERE id=?",(t['id'],))
    execute("UPDATE meta SET value='3' WHERE key='schema_version'")
    init()
    restored=client.get('/api/topics').json()[0]
    assert restored['id']==t['id'] and not restored['active'] and restored['next_run'] is None
    client.patch('/api/topics/'+t['id'],json={'active':True})
    init()
    assert client.get('/api/topics').json()[0]['active']==1
