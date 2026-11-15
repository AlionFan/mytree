"""Mem0 OSS semantic index. Canonical profile facts remain the authority.

Only source-backed text is indexed (infer=False). No LLM extraction, grading,
training or Mem0 cloud. Every query is filtered by owner before vector search.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time

os.environ['MEM0_TELEMETRY'] = 'false'
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
_lock = threading.RLock()
_instances = {}


def _root():
    from . import teaching_memory
    return Path(os.environ.get('MYTREE_MEM0_DIR', str(Path(teaching_memory._path()).with_name('mem0'))))


class CachedEmbedding:
    def __init__(self, original, root, model="text-embedding-3-small", dims=1536):
        self.original, self.root = original, root
        self.config=original.config
        self.model,self.dims=model,dims

    def _key(self, text):
        return hashlib.sha256((self.model+':'+text).encode()).hexdigest()

    def warm(self, texts):
        texts = list(dict.fromkeys(texts))
        with sqlite3.connect(self.root/'embeddings.sqlite3') as db:
            db.execute('CREATE TABLE IF NOT EXISTS embeddings(id TEXT PRIMARY KEY,vector TEXT)')
            missing = [text for text in texts if not db.execute('SELECT 1 FROM embeddings WHERE id=?',(self._key(text),)).fetchone()]
            for start in range(0,len(missing),32):
                batch=missing[start:start+32]
                result=self.original.client.embeddings.create(model=self.model,input=batch,dimensions=self.dims)
                if len(result.data)!=len(batch) or sorted(item.index for item in result.data)!=list(range(len(batch))) or any(len(item.embedding)!=self.dims for item in result.data):
                    raise RuntimeError('EMBEDDING_OUTPUT_INVALID')
                for item in result.data:
                    db.execute('INSERT OR REPLACE INTO embeddings VALUES(?,?)',(self._key(batch[item.index]),json.dumps(item.embedding)))

    def embed(self, text, memory_action=None):
        self.warm([text])
        with sqlite3.connect(self.root/'embeddings.sqlite3') as db:
            return json.loads(db.execute('SELECT vector FROM embeddings WHERE id=?',(self._key(text),)).fetchone()[0])


def index_root(cfg):
    from . import ai
    root=_root().resolve()
    base,_=ai.endpoint(cfg,'embedding')
    # Preserve the legacy index; all different vector spaces get a new index.
    if cfg.embedding_model=='text-embedding-3-small' and cfg.embedding_dims==1536 and base=='https://api.openai-next.com/v1':
        return root
    identity=hashlib.sha256(f'{base}|{cfg.embedding_model}|{cfg.embedding_dims}'.encode()).hexdigest()[:16]
    return root/('index-'+identity)


def _memory():
    from . import ai
    cfg=ai.settings()
    embed_base,embed_key=ai.endpoint(cfg,'embedding')
    tutor_base,tutor_key=ai.endpoint(cfg,'tutor')
    if not embed_key:raise RuntimeError('MEM0_NOT_CONFIGURED')
    root=index_root(cfg)
    identity=str(root)
    if identity not in _instances:
        root.mkdir(parents=True,exist_ok=True);root.chmod(0o700)
        # Mem0's anonymous identity is also kept in the private application folder.
        os.environ['MEM0_DIR']=str(root)
        from mem0 import Memory
        import mem0.memory.main as main
        main.mem0_dir=str(root)
        memory=Memory.from_config({
            'version':'v1.1', 'history_db_path':str(root/'history.sqlite3'),
            'llm':{'provider':'openai','config':{'api_key':tutor_key or 'UNCONFIGURED','openai_base_url':tutor_base,'model':cfg.tutor}},
            'embedder':{'provider':'openai','config':{'api_key':embed_key,'openai_base_url':embed_base,'model':cfg.embedding_model,'embedding_dims':cfg.embedding_dims}},
            'vector_store':{'provider':'qdrant','config':{'collection_name':'teaching','path':str(root/'qdrant'),'on_disk':True,'embedding_model_dims':cfg.embedding_dims}}})
        memory.embedding_model.client=memory.embedding_model.client.with_options(timeout=15,max_retries=0,default_headers={'User-Agent':'Mozilla/5.0 MyTree/0.3'})
        memory.embedding_model=CachedEmbedding(memory.embedding_model,root,cfg.embedding_model,cfg.embedding_dims)
        _instances[identity]=memory
    memory=_instances[identity]
    # Rotating credentials must not open a second Qdrant client on the same path.
    client=memory.embedding_model.original.client
    if client.api_key != embed_key:
        memory.embedding_model.original.client=client.with_options(api_key=embed_key)
        memory.embedding_model.config.api_key=embed_key
    return memory


def sync_search(owner, records, query, knowledge=None, limit=8):
    """Reconcile deletions/versions, search scoped vectors, then recheck live facts.

    Never return stale vector payload as a fact, even after an interrupted sync.
    An unavailable index is an explicit degraded status, not a fake Mem0 result.
    """
    from . import store
    store._identifier(owner,'档案编号')
    if os.environ.get('MYTREE_MEM0_ENABLED','1')=='0':
        return {'status':'disabled','engine':'source-ledger','records':[r for r in records if not knowledge or r['knowledge_id']==knowledge or r['type']=='preference'][:limit]}
    started=time.monotonic()
    live={r['id']:r for r in records}
    try:
        with _lock:
            memory=_memory()
            indexed=memory.get_all(user_id=owner,limit=10000)['results']
            current={}
            for item in indexed:
                meta=item.get('metadata') or {};key=meta.get('source_key');record=live.get(key)
                digest=hashlib.sha256(json.dumps({k:record[k] for k in ('id','content','source_event_ids','version','knowledge_id')},sort_keys=True,ensure_ascii=False).encode()).hexdigest() if record else None
                if not record or meta.get('source_digest')!=digest or key in current:
                    memory.delete(item['id'])
                else:current[key]=item
            pending=[r for key,r in live.items() if key not in current]
            texts=[r['content'] for r in pending]
            memory.embedding_model.warm(texts+[query])
            for record in pending:
                digest=hashlib.sha256(json.dumps({k:record[k] for k in ('id','content','source_event_ids','version','knowledge_id')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                memory.add(record['content'],user_id=owner,infer=False,metadata={'source_key':record['id'],'source_digest':digest,'knowledge_id':record['knowledge_id']})
            filters={'knowledge_id':knowledge} if knowledge else None
            hits=memory.search(query,user_id=owner,filters=filters,limit=limit,rerank=False)['results']
            selected=[]
            for hit in hits:
                key=(hit.get('metadata') or {}).get('source_key')
                if key in live and (not knowledge or live[key]['knowledge_id']==knowledge):
                    selected.append({**live[key],'retrieval_score':hit.get('score')})
            prefs=[r for r in records if r['type']=='preference']
            selected=prefs+[r for r in selected if r['type']!='preference']
            return {'status':'ready','engine':'mem0','records':selected[:limit],'seconds':round(time.monotonic()-started,3),'indexed_records':len(live),'new_records':len(pending)}
    except Exception:
        # Neither upstream bodies, private facts nor credentials enter ordinary logs.
        return {'status':'unavailable','engine':'source-ledger','records':[r for r in records if not knowledge or r['knowledge_id']==knowledge or r['type']=='preference'][:limit],
                'message':'长期记忆检索暂时不可用，本次按已保存的学习记录安排，可稍后重试。'}


def close():
    """Release local Qdrant locks for shutdown/restart verification."""
    with _lock:
        for memory in _instances.values():
            memory.vector_store.client.close()
            memory._telemetry_vector_store.client.close()
        _instances.clear()
