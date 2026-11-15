"""Account-bound successful-use allowances. No browser-controlled paid activation."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import hashlib
import json
import os
import time
from . import auth, store
from .errors import DomainError

try:TZ=ZoneInfo('Asia/Shanghai')
except ZoneInfoNotFoundError:TZ=timezone(timedelta(hours=8),'Asia/Shanghai')
PLANS={
 'free':{'name':'免费体验','monthly_fen':0,'annual_fen':0,'questions_daily':3,'questions_monthly':None,'explorer_monthly':10},
 'grow':{'name':'标准版','monthly_fen':5900,'annual_fen':199000,'questions_daily':10,'questions_monthly':200,'explorer_monthly':60},
 'plus':{'name':'进阶版','monthly_fen':11900,'annual_fen':399000,'questions_daily':30,'questions_monthly':500,'explorer_monthly':150},
}

def _now():return datetime.now(TZ)

def periods():
 n=_now();day=n.strftime('%Y-%m-%d');month=n.strftime('%Y-%m')
 nextday=(n+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
 nextmonth=(n.replace(day=28)+timedelta(days=4)).replace(day=1,hour=0,minute=0,second=0,microsecond=0)
 return day,month,nextday.isoformat(),nextmonth.isoformat()

def _tables(db):
 db.execute('CREATE TABLE IF NOT EXISTS allowance_jobs(owner TEXT NOT NULL,kind TEXT NOT NULL,job TEXT NOT NULL,day TEXT NOT NULL,month TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(owner,kind,job))')
 db.execute('CREATE TABLE IF NOT EXISTS explorer_cancellations(owner TEXT NOT NULL,request TEXT NOT NULL,PRIMARY KEY(owner,request))')
 db.execute('CREATE TABLE IF NOT EXISTS explorer_receipts(owner TEXT NOT NULL,request TEXT NOT NULL,digest TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(owner,request))')
 db.execute('CREATE INDEX IF NOT EXISTS allowance_owner_period ON allowance_jobs(owner,kind,month,day)')

def _owner(db,owner):
 if not db.execute('SELECT 1 FROM users WHERE profile_id=?',(owner,)).fetchone():raise DomainError('AUTH_REQUIRED','请先登录学习账号。',401)

def _recover(db,owner):
 # A process may die after saving a card but before settling its reservation.
 stale=db.execute("SELECT * FROM allowance_jobs WHERE owner=? AND state='pending' AND created<?",(owner,time.time()-300)).fetchall()
 if not stale:return
 cards=store.read(owner).get('wrong_cards',{}).values()
 keys={c.get('_billing_key') for c in cards}
 for row in stale:
  if (row['kind']=='questions' and row['job'] in keys) or (row['kind']=='explorer' and db.execute('SELECT 1 FROM explorer_receipts WHERE owner=? AND request=?',(owner,row['job'])).fetchone()):
   db.execute("UPDATE allowance_jobs SET state='used' WHERE owner=? AND kind=? AND job=?",(owner,row['kind'],row['job']))
  else:db.execute('DELETE FROM allowance_jobs WHERE owner=? AND kind=? AND job=?',(owner,row['kind'],row['job']))

def _counts(db,owner,day,month):
 def count(kind,period,value):return db.execute(f'SELECT count(*) FROM allowance_jobs WHERE owner=? AND kind=? AND {period}=?',(owner,kind,value)).fetchone()[0]
 return count('questions','day',day),count('questions','month',month),count('explorer','month',month)

def catalog():
 return {'plans':{key:{**plan,'annual_fen':None} for key,plan in PLANS.items()},'billing_intervals':['monthly'],'currency':'CNY','checkout_available':False,'pricing_status':'proposal','hardware_available':False,'timezone':'Asia/Shanghai'}

def _limits(owner):
 # Private, server-only tester assignment; request fields never select an allowance.
 target=os.environ.get('MYTREE_TEST_PROFILE','').strip()
 return (100,1000) if target and owner==target else (3,10)


def overview(owner):
 with auth._db() as db:
  _tables(db);_owner(db,owner);_recover(db,owner)
  day,month,dayreset,monthreset=periods();q,qm,e=_counts(db,owner,day,month)
  qlimit,elimit=_limits(owner)
 return {'plan':'free','name':'测试账号' if qlimit>3 else PLANS['free']['name'],'questions':{'used':q,'limit':qlimit,'remaining':max(0,qlimit-q),'reset_at':dayreset},'explorer':{'used':e,'limit':elimit,'remaining':max(0,elimit-e),'reset_at':monthreset},'checkout_available':False,'timezone':'Asia/Shanghai'}

def _error(kind,limits=(3,10)):
 if limits!=(3,10):return DomainError('ALLOWANCE_EXHAUSTED','今天的测试新题额度已用完。' if kind=='questions' else '本月测试探索额度已用完。',429)
 return DomainError('ALLOWANCE_EXHAUSTED','今天的3道新题已用完，已有题目仍可继续练习与复习。查看 /pricing 了解会员计划。' if kind=='questions' else '本月10次探索识图已用完，下月自动恢复。查看 /pricing 了解会员计划。',429)

@contextmanager
def successful_use(owner,kind,key):
 if not auth.enabled():yield key;return
 if kind not in ('questions','explorer'):raise ValueError('Unknown allowance')
 job=hashlib.sha256(key.encode()).hexdigest();fresh=False
 with auth._db() as db:
  _tables(db);_owner(db,owner);_recover(db,owner)
  row=db.execute('SELECT state FROM allowance_jobs WHERE owner=? AND kind=? AND job=?',(owner,kind,job)).fetchone()
  if row and row['state']=='pending':raise DomainError('MODEL_BUSY','这次操作正在处理，请稍后重试。',429)
  if not row:
   day,month,_,_=periods();q,qm,e=_counts(db,owner,day,month)
   limits=_limits(owner)
   if (kind=='questions' and q>=limits[0]) or (kind=='explorer' and e>=limits[1]):raise _error(kind,limits)
   db.execute("INSERT INTO allowance_jobs VALUES(?,?,?,?,?,'pending',?)",(owner,kind,job,day,month,time.time()));fresh=True
 try:
  yield job
 except BaseException:
  if fresh:
   with auth._db() as db:db.execute("DELETE FROM allowance_jobs WHERE owner=? AND kind=? AND job=? AND state='pending'",(owner,kind,job))
  raise
 else:
  if fresh:
   with auth._db() as db:db.execute("UPDATE allowance_jobs SET state='used' WHERE owner=? AND kind=? AND job=?",(owner,kind,job))

def selection(owner,body):
 if set(body)-{'plan','interval'}:raise DomainError('INVALID_INPUT','套餐选择包含不支持的字段。')
 plan=body.get('plan');interval=body.get('interval')
 if plan not in ('grow','plus') or interval!='monthly':raise DomainError('INVALID_INPUT','请选择有效的会员方案。')
 with auth._db() as db:_owner(db,owner)
 return {'status':'unavailable','plan':plan,'interval':interval,'amount_fen':PLANS[plan][interval+'_fen'],'currency':'CNY','activated':False,'message':'暂未开售。'}


def explorer_call(owner,body,call):
 request=body.get('request_id')
 if not isinstance(request,str) or not __import__('re').fullmatch(r'[a-zA-Z0-9_-]{8,80}',request):raise DomainError('INVALID_INPUT','请更新页面后重新发起本次识图。')
 clean={k:v for k,v in body.items() if k!='request_id'}
 digest=hashlib.sha256(json.dumps(clean,sort_keys=True).encode()).hexdigest()
 job=hashlib.sha256(('explorer:'+request).encode()).hexdigest()
 with store.request_lock((owner,'explorer',request)):
  with auth._db() as db:
   _tables(db);_owner(db,owner)
   if db.execute('SELECT 1 FROM explorer_cancellations WHERE owner=? AND request=?',(owner,job)).fetchone():raise DomainError('CONFLICT','这次探索已取消，请重新识图。',409)
   receipt=db.execute('SELECT * FROM explorer_receipts WHERE owner=? AND request=?',(owner,job)).fetchone()
  if receipt:
   if receipt['digest']!=digest:raise DomainError('CONFLICT','同一识图请求的内容已改变，请重新发起。',409)
   result=json.loads(receipt['result'])
  else:
   with successful_use(owner,'explorer','explorer:'+request):
    result=call(clean)
    with auth._db() as db:
     if db.execute('SELECT 1 FROM explorer_cancellations WHERE owner=? AND request=?',(owner,job)).fetchone():raise DomainError('CONFLICT','这次探索已取消，请重新识图。',409)
     db.execute('INSERT INTO explorer_receipts VALUES(?,?,?,?)',(owner,job,digest,json.dumps(result,ensure_ascii=False)))
  return {**result,'allowance':overview(owner)['explorer']}


def cancel_explorer(owner,body):
 request=body.get('request_id')
 if set(body)-{'request_id','student'} or not isinstance(request,str) or not __import__('re').fullmatch(r'[a-zA-Z0-9_-]{8,80}',request):raise DomainError('INVALID_INPUT','取消请求无效。')
 job=hashlib.sha256(('explorer:'+request).encode()).hexdigest()
 with auth._db() as db:
  _tables(db);_owner(db,owner)
  # A completed result is already successful; cancellation only releases in-flight work.
  if not db.execute('SELECT 1 FROM explorer_receipts WHERE owner=? AND request=?',(owner,job)).fetchone():
   db.execute('INSERT OR IGNORE INTO explorer_cancellations VALUES(?,?)',(owner,job))
   db.execute("DELETE FROM allowance_jobs WHERE owner=? AND kind='explorer' AND job=? AND state='pending'",(owner,job))
 return {'ok':True}
