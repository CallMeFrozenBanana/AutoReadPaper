from __future__ import annotations
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, available_timezones
from pydantic import BaseModel, Field, field_validator, model_validator
from .store import root, atomic_json

CATEGORIES = {'cs.CV':'计算机视觉','cs.RO':'机器人','cs.AI':'人工智能','cs.LG':'机器学习','cs.CL':'自然语言处理','stat.ML':'统计机器学习'}
TEMPLATES = [
    {'id':'vln','name':'视觉语言导航','description':'研究机器人如何根据语言指令和视觉观测完成导航。','keywords':['vision-language navigation','VLN','instruction following navigation'],'categories':['cs.RO','cs.CV']},
    {'id':'slam','name':'视觉定位与建图','description':'关注视觉里程计、SLAM 与定位建图方法。','keywords':['visual odometry','visual SLAM','visual localization'],'categories':['cs.RO','cs.CV']},
    {'id':'vla','name':'视觉语言动作模型','description':'关注视觉、语言与机器人动作联合建模。','keywords':['vision-language-action','robot foundation model'],'categories':['cs.RO','cs.AI']},
]


class Topic(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    description: str = Field(default='',max_length=4000)
    keywords: list[str] = Field(default_factory=list,max_length=40)
    exclusions: list[str] = Field(default_factory=list,max_length=40)
    questions: str = Field(default='',max_length=4000)
    categories: list[str] = Field(default_factory=list)
    query: str = Field(default='',max_length=3000)
    frequency: Literal['daily','weekly','manual'] = 'daily'
    time: str = '09:00'
    timezone: str = 'Asia/Shanghai'
    weekday: int = Field(default=0,ge=0,le=6)
    lookback_days: int = Field(default=30,ge=1,le=3650)
    date_from: str = ''
    date_to: str = ''
    daily_limit: int = Field(default=5,ge=1,le=100)
    language: Literal['zh','en'] = 'zh'
    update_policy: Literal['auto','manual'] = 'auto'

    @field_validator('time')
    @classmethod
    def time_valid(cls,v):
        return datetime.strptime(v,'%H:%M').strftime('%H:%M')

    @field_validator('timezone')
    @classmethod
    def tz_valid(cls,v):
        try: ZoneInfo(v)
        except (KeyError, ValueError): raise ValueError("请选择有效时区")
        return v

    @field_validator('keywords','exclusions')
    @classmethod
    def trim(cls,v):
        return list(dict.fromkeys(s.strip() for s in v if s.strip()))

    @model_validator(mode='after')
    def valid(self):
        self.name=self.name.strip()
        if not self.name or not (self.keywords or self.query.strip()):
            raise ValueError('请输入主题名称与至少一个检索关键词，或高级检索表达式')
        if any(c not in CATEGORIES for c in self.categories):
            raise ValueError('未知学科类别')
        if bool(self.date_from) != bool(self.date_to):
            raise ValueError('自定义日期需同时提供开始和结束日期')
        if self.date_from:
            a=datetime.strptime(self.date_from,'%Y-%m-%d');b=datetime.strptime(self.date_to,'%Y-%m-%d')
            if a>b: raise ValueError('开始日期不能晚于结束日期')
        return self


class Settings(BaseModel):
    provider: Literal['api','codex_cli'] = 'api'
    codex_path: str = 'codex'
    codex_model: str = ''
    codex_vision: bool = True
    codex_timeout_seconds: int = Field(default=300,ge=30,le=1800)
    base_url: str = 'https://api.openai.com/v1'
    model: str = ''
    vision_model: str = ''
    api_key: str = ''
    clear_key: bool = False
    enabled: bool = False
    global_daily_limit: int = Field(default=20,ge=1,le=500)
    daily_token_limit: int = Field(default=200000,ge=1000,le=10000000)
    max_output_tokens: int = Field(default=4000,ge=512,le=16000)
    chunk_chars: int = Field(default=18000,ge=4000,le=50000)
    max_pages: int = Field(default=100,ge=1,le=500)
    max_vision_pages: int = Field(default=4,ge=0,le=12)
    json_mode: bool = True
    token_parameter: Literal['max_completion_tokens','max_tokens'] = 'max_completion_tokens'

    @field_validator('base_url')
    @classmethod
    def url_valid(cls,v):
        u=urlparse(v)
        if u.scheme not in ('https','http') or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise ValueError('请输入有效模型 API 地址')
        if u.scheme=='http' and u.hostname not in ('localhost','127.0.0.1','::1'):
            raise ValueError('远程模型地址必须使用 HTTPS')
        return v.rstrip('/')


def settings(secret=False):
    p=root()/'settings.json'
    s=Settings.model_validate(json.loads(p.read_text()) if p.exists() else {}).model_dump()
    s['api_key']=os.environ.get('ARP_API_KEY') or s['api_key']
    if not secret:
        s['has_key']=bool(s.pop('api_key'))
    return s


def save_settings(value: Settings):
    data=value.model_dump()
    if not data['api_key'] and not data['clear_key']:
        p=root()/'settings.json'
        data['api_key']=json.loads(p.read_text()).get('api_key','') if p.exists() else ''
    data.pop('clear_key',None)
    atomic_json('settings.json',data)
    (root()/'settings.json').chmod(0o600)


def next_run(topic, after=None):
    if topic['frequency']=='manual': return None
    local=(after or datetime.now(timezone.utc)).astimezone(ZoneInfo(topic['timezone']))
    h,m=map(int,topic['time'].split(':'))
    candidate=local.replace(hour=h,minute=m,second=0,microsecond=0)
    if topic['frequency']=='weekly':
        candidate+=timedelta(days=(topic['weekday']-candidate.weekday())%7)
        if candidate<=local: candidate+=timedelta(days=7)
    elif candidate<=local: candidate+=timedelta(days=1)
    return candidate.astimezone(timezone.utc).isoformat()


def options():
    return {'templates':TEMPLATES,'categories':CATEGORIES,'sources':[{'id':'arxiv','name':'arXiv'}],
            'timezones':sorted(available_timezones()),'defaults':{'frequency':'daily','time':'09:00','daily_limit':5,'lookback_days':30}}


def model_ready(cfg):
    return bool(cfg['enabled'] and (cfg.get('provider')=='codex_cli' or cfg['model']))

def model_name(cfg,vision=False):
    if cfg.get('provider')=='codex_cli':
        return 'codex:'+ (cfg.get('codex_model') or 'default')
    return cfg['vision_model'] if vision else cfg['model']
