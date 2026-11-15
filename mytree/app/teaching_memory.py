"""Owner-scoped, source-linked teaching memory. No memory can change grades."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from . import store
from .knowledge import KNOWLEDGE_CARDS, KP

STYLES={'visual':'图像和数轴','steps':'分步思考','examples':'具体例子'}

def _path():
    return os.environ.get('MYTREE_MEMORY_DB',str(Path(store.profile._PATH).with_name('teaching-memory.sqlite3')))

@contextmanager
def _db():
    path=Path(_path());path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=2);db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS memories(owner TEXT,id TEXT,kind TEXT,knowledge TEXT,content TEXT,sources TEXT,version INTEGER DEFAULT 1,status TEXT DEFAULT "active",created REAL DEFAULT 0,updated REAL,PRIMARY KEY(owner,id))')
    if 'created' not in {row[1] for row in db.execute('PRAGMA table_info(memories)')}:db.execute('ALTER TABLE memories ADD COLUMN created REAL DEFAULT 0')
    db.execute('UPDATE memories SET created=updated WHERE created=0')
    db.commit()
    try:os.chmod(path,0o600)
    except OSError:pass
    try:
        with db:yield db
    finally:db.close()

def _put(db,owner,key,kind,knowledge,content,sources):
    if len(content)>4000:raise ValueError('记忆内容超出本次范围。')
    db.execute('INSERT INTO memories(owner,id,kind,knowledge,content,sources,created,updated) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(owner,id) DO UPDATE SET content=excluded.content,sources=excluded.sources,knowledge=excluded.knowledge,version=memories.version+(memories.content!=excluded.content OR memories.sources!=excluded.sources),updated=excluded.updated,status="active" WHERE memories.status="active"',
               (owner,key,kind,knowledge,content,json.dumps(sources),time.time(),time.time()))

def snapshot(owner,knowledge=None,limit=10000):
    store._identifier(owner,'档案编号');limit=max(1,min(int(limit),10000));value=store.read(owner)
    live=set()
    with _db() as db:
        for card in list(value['wrong_cards'].values()):
            key='card_'+card['id']
            status=card.get('_study_status',card.get('study_status',(card.get('_analysis') or {}).get('status','unknown')))
            lesson_only=(card.get('_source') or {}).get('mode')=='lesson_only' or (card.get('_analysis') or {}).get('study_mode')=='lesson_only' or card.get('type')=='lesson'
            verification=card.get('verification') or (card.get('_analysis') or {}).get('verification') or {}
            level=verification.get('level',verification.get('status','unknown'))
            fact={'study_mode':'lesson_only' if lesson_only else 'analysis','verification':{'level':level},'source_created_at':card.get('_created_at'),'original_work_status':'unreliable' if lesson_only else 'saved_transcript','problem':card.get('problem','')[:500],'student_steps':[] if lesson_only else [step[:200] for step in card.get('student_steps',[])[:3]],
                  'study_status':status,'note':card.get('learner_note','')[:200]}
            # A saved unknown/AI record is never described as a verified mistake.
            for kp in card.get('knowledge_ids',[])[:3]:
                live.add(key+'_'+kp)
                _put(db,owner,key+'_'+kp,'fact',kp,json.dumps(fact,ensure_ascii=False),[key for key in (card['id'],card.get('diagnosis_id')) if key])
        for identity, answer in value['quiz_answers'].items():
            kp=answer.get('knowledge_id')
            if kp not in KP or answer.get('verification',{}).get('level')!='verified':continue
            key='answer_'+identity;live.add(key)
            fact={'event':'quiz_answer','knowledge':KP[kp][0],'correct':answer.get('correct'),
                  'max_hint_level':answer.get('max_hint_level',0),'at':answer.get('at'),
                  'verification':{'level':'verified'},'quiz_id':answer.get('quiz_id')}
            _put(db,owner,key,'fact',kp,json.dumps(fact,ensure_ascii=False),[identity]+value['quizzes'].get(answer.get('quiz_id'),{}).get('source_wrong_card_ids',[]))
        for identity, fact in value.get('profile_facts',{}).items():
            if fact.get('kind')!='review' or fact.get('knowledge_id') not in KP:continue
            key='review_'+identity;live.add(key)
            _put(db,owner,key,'fact',fact['knowledge_id'],json.dumps({'event':'review','completed':fact.get('completed'),
                 'at':fact.get('at'),'evidence_ids':fact.get('evidence_ids',[])},ensure_ascii=False),[identity]+fact.get('evidence_ids',[]))
        # Sources removed from the current account may no longer be recalled.
        rows=db.execute('SELECT id FROM memories WHERE owner=? AND kind="fact" AND status="active"',(owner,)).fetchall()
        for row in rows:
            if row['id'] not in live:db.execute('UPDATE memories SET status="expired" WHERE owner=? AND id=?',(owner,row['id']))
        rows=db.execute('SELECT * FROM memories WHERE owner=? AND status="active" AND (kind="preference" OR ? IS NULL OR knowledge=?) ORDER BY (kind="preference") DESC,updated DESC LIMIT ?',(owner,knowledge,knowledge or '',limit)).fetchall()
        records=[{'id':r['id'],'type':r['kind'],'knowledge_id':r['knowledge'],'content':r['content'],'source_event_ids':json.loads(r['sources']),
                  'version':r['version'],'status':r['status'],'created_at':r['created'],'updated_at':r['updated']} for r in rows]
    materials=[]
    if knowledge in KNOWLEDGE_CARDS:
        card=KNOWLEDGE_CARDS[knowledge]
        text=' '.join(str(v) for v in card)[:1000]
        materials=[{'source_id':'builtin:'+knowledge,'source':'mytree/app/knowledge.py','version':hashlib.sha256(text.encode()).hexdigest()[:12],
                    'knowledge_id':knowledge,'text':text,'origin':'项目内置教学规则'}]
    return {'records':records,'knowledge_sources':materials,'training':False}

def retrieve(owner,knowledge=None,limit=6):
    from . import mem0_adapter
    limit=max(1,min(int(limit),8))
    value=snapshot(owner)
    result=mem0_adapter.sync_search(owner,value['records'],
        ('这个孩子过去的错题、薄弱点、独立作答和复习表现，以及讲解偏好。'+(KP[knowledge][0] if knowledge in KP else '')),knowledge,limit)
    current={r['id']:r for r in snapshot(owner)['records']}
    result['records']=[r for r in result['records'] if r['id'] in current and current[r['id']]['version']==r['version'] and current[r['id']]['content']==r['content'] and current[r['id']]['source_event_ids']==r['source_event_ids']]
    result['knowledge_sources']=snapshot(owner,knowledge,1)['knowledge_sources'] if knowledge else []
    result['training']=False
    return result


def remember_preference(owner,style,source='explicit-user-setting'):
    store._identifier(owner,'档案编号')
    if style not in STYLES:raise ValueError('请选择图像、分步或例子。')
    with _db() as db:
        # An explicit new preference can replace a previously revoked setting.
        db.execute('INSERT INTO memories(owner,id,kind,knowledge,content,sources,created,updated) VALUES(?,"preference_style","preference","",?,?,?,?) ON CONFLICT(owner,id) DO UPDATE SET content=excluded.content,sources=excluded.sources,status="active",version=memories.version+1,updated=excluded.updated',(owner,STYLES[style],json.dumps([source]),time.time(),time.time()))
    return {'ok':True,'style':style}

def forget(owner,key):
    store._identifier(owner,'档案编号')
    if not isinstance(key,str) or len(key)>160:raise ValueError('记忆编号不正确。')
    with _db() as db:db.execute('UPDATE memories SET status="revoked",version=version+1 WHERE owner=? AND id=?',(owner,key))
    from . import mem0_adapter
    value=snapshot(owner)
    result=mem0_adapter.sync_search(owner,value['records'],'已撤回的学习记录',limit=1)
    return {'ok':True,'index_status':result['status']}

def for_chat(owner,analysis,question):
    # Only explicit, bounded preferences are extracted; no free-form model memory.
    if isinstance(question,str) and not any(word in question for word in ('不要','别用','不喜欢','讨厌','少用')) and any(word in question for word in ('记住','以后','下次','我喜欢')):
        for style,words in [('visual',('多用图','多画图','用图讲','图解','数轴讲')),('steps',('分步讲','一步一步讲')),('examples',('多举例','用例子讲','举例讲'))]:
            if any(word in question for word in words):
                remember_preference(owner,style,'chat:'+hashlib.sha256(question.encode()).hexdigest()[:16]);break
    kp=next(iter(analysis.get('knowledge_ids') or [analysis.get('lesson_kp')]),None)
    return retrieve(owner,kp,limit=4)
