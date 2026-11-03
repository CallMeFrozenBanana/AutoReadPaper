from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


def root():
    p = Path(os.environ.get("ARP_DATA_DIR", "data")).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def asset_lock():
    import fcntl
    with (root() / '.assets.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(lock, fcntl.LOCK_UN)


@contextmanager
def db():
    conn = sqlite3.connect(root() / "catalog.sqlite3", timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def init():
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript('''
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        INSERT OR IGNORE INTO meta VALUES('schema_version','1');
        CREATE TABLE IF NOT EXISTS topics(
          id TEXT PRIMARY KEY, config TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
          active INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0,
          next_run TEXT, last_scan TEXT, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS topic_revisions(topic_id TEXT,revision INTEGER,config TEXT,created TEXT,
          PRIMARY KEY(topic_id,revision));
        CREATE TABLE IF NOT EXISTS papers(
          id TEXT PRIMARY KEY, identity TEXT UNIQUE NOT NULL,title TEXT NOT NULL,
          authors TEXT NOT NULL DEFAULT '[]',abstract TEXT NOT NULL DEFAULT '', source TEXT NOT NULL,
          published TEXT, url TEXT, created TEXT NOT NULL,
          favorite INTEGER NOT NULL DEFAULT 0,is_read INTEGER NOT NULL DEFAULT 0,notes TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS versions(
          id TEXT PRIMARY KEY,paper_id TEXT NOT NULL REFERENCES papers(id),label TEXT NOT NULL,
          updated TEXT,pdf_url TEXT,sha256 TEXT,pdf_path TEXT,extraction_path TEXT,
          status TEXT NOT NULL DEFAULT 'metadata_only',created TEXT NOT NULL,metadata TEXT,
          UNIQUE(paper_id,label));
        CREATE TABLE IF NOT EXISTS topic_papers(
          topic_id TEXT NOT NULL REFERENCES topics(id),paper_id TEXT NOT NULL REFERENCES papers(id),
          reason TEXT NOT NULL,excluded INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL,
          PRIMARY KEY(topic_id,paper_id));
        CREATE TABLE IF NOT EXISTS jobs(
          id TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,dedupe TEXT UNIQUE,
          state TEXT NOT NULL DEFAULT 'queued',attempts INTEGER NOT NULL DEFAULT 0,
          available TEXT NOT NULL,lease_until TEXT,token TEXT,progress TEXT NOT NULL DEFAULT '',
          error TEXT,result TEXT,created TEXT NOT NULL,updated TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS jobs_ready ON jobs(state,available);
        CREATE TABLE IF NOT EXISTS reports(
          id TEXT PRIMARY KEY,version_id TEXT NOT NULL REFERENCES versions(id),job_id TEXT UNIQUE NOT NULL,
          config_hash TEXT NOT NULL,scope TEXT NOT NULL,content TEXT NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS assessments(
          id TEXT PRIMARY KEY,job_id TEXT UNIQUE NOT NULL,paper_id TEXT NOT NULL,version_id TEXT NOT NULL,
          report_id TEXT NOT NULL,topic_id TEXT NOT NULL,topic_revision INTEGER NOT NULL,
          priority REAL,quality REAL,content TEXT NOT NULL,created TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS assessments_paper ON assessments(paper_id,topic_id,created);
        CREATE TABLE IF NOT EXISTS calls(
          id TEXT PRIMARY KEY,job_id TEXT NOT NULL,cache_key TEXT NOT NULL,model TEXT NOT NULL,
          state TEXT NOT NULL,input_tokens INTEGER,output_tokens INTEGER,
          reserved INTEGER NOT NULL,response TEXT,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reading_slots(
          job_id TEXT NOT NULL,day TEXT NOT NULL,topic_id TEXT,PRIMARY KEY(job_id,day));
        CREATE TABLE IF NOT EXISTS cleanup_previews(token TEXT PRIMARY KEY,paper_ids TEXT NOT NULL,fingerprint TEXT NOT NULL,expires TEXT NOT NULL,filters TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cleanup_files(path TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS scans(
          id TEXT PRIMARY KEY,topic_id TEXT,revision INTEGER,query TEXT,cutoff TEXT,
          offset INTEGER NOT NULL DEFAULT 0,found INTEGER NOT NULL DEFAULT 0,
          complete INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL,finished TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS paper_search USING fts5(paper_id UNINDEXED,text);
        ''')
        if 'metadata' not in [r[1] for r in c.execute('PRAGMA table_info(versions)')]:
            c.execute('ALTER TABLE versions ADD COLUMN metadata TEXT')
        if int(c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]) < 4:
            # Restore legacy archived topics without silently restarting schedules.
            c.execute("UPDATE topics SET archived=0,active=0,next_run=NULL WHERE archived=1")
            c.execute("UPDATE meta SET value='4' WHERE key='schema_version'")


def one(sql, params=()):
    with db() as c:
        row = c.execute(sql, params).fetchone()
        return dict(row) if row else None


def all_rows(sql, params=()):
    with db() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def execute(sql, params=()):
    with db() as c:
        return c.execute(sql, params).rowcount


def atomic_json(relative, value):
    p = root() / relative
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix('.' + uid() + '.tmp')
    temp.write_text(dumps(value), encoding="utf-8")
    temp.replace(p)


def enqueue(kind, payload, dedupe=None, available=None):
    ident = uid()
    with db() as c:
        c.execute("INSERT OR IGNORE INTO jobs(id,kind,payload,dedupe,available,created,updated) VALUES(?,?,?,?,?,?,?)",
                  (ident,kind,dumps(payload),dedupe,available or now(),now(),now()))
        row = c.execute("SELECT * FROM jobs WHERE id=? OR dedupe=?",(ident,dedupe)).fetchone()
    return dict(row)


def index_paper(paper_id):
    import jieba
    jieba.setLogLevel(40)
    p = one("SELECT * FROM papers WHERE id=?", (paper_id,))
    reports = all_rows("SELECT r.content FROM reports r JOIN versions v ON v.id=r.version_id WHERE v.paper_id=?", (paper_id,))
    content = ' '.join([p['title'],p['authors'],p['abstract'],p['notes']] + [r['content'] for r in reports])
    tokens = ' '.join(jieba.cut_for_search(content))
    with db() as c:
        c.execute("DELETE FROM paper_search WHERE paper_id=?",(paper_id,))
        c.execute("INSERT INTO paper_search VALUES(?,?)",(paper_id,tokens))
