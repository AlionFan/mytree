"""FR035 durable allowances; all accounts/model output are synthetic."""
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import json,time,unittest
import test_auth
from app import billing,auth,cards,store,explorer,agent
from app.errors import DomainError

class BillingTests(unittest.TestCase):
 setUp=test_auth.AuthTests.setUp
 tearDown=test_auth.AuthTests.tearDown
 req=test_auth.AuthTests.req
 login=test_auth.AuthTests.login
 def owner(self,email='a@example.test'):
  a,c=self.login(email,email);return a['profile_id'],c
 def use(self,owner,key,kind='questions'):
  with billing.successful_use(owner,kind,key):pass
 def test_private_tester_allowance_is_owner_bound_reversible_and_not_paid(self):
  import os
  a,ac=self.owner();b,bc=self.owner('other@example.test')
  for i in range(3):self.use(a,'initial'+str(i))
  with patch.dict(os.environ,{'MYTREE_TEST_PROFILE':a}):
   self.assertEqual(billing.overview(a)['questions']['remaining'],97)
   self.assertEqual(billing.overview(a)['explorer']['limit'],1000)
   self.assertEqual(billing.overview(a)['plan'],'free')
   self.assertEqual(billing.overview(b)['questions']['limit'],3)
   self.assertEqual(billing.overview(b)['explorer']['limit'],10)
   self.use(a,'fourth');self.use(a,'fourth')
   self.assertEqual(billing.overview(a)['questions']['used'],4)
   status,data,_=self.req('/api/billing/me',cookie=ac)
   self.assertEqual(status,200);self.assertEqual(data['questions']['limit'],100)
   status,data,_=self.req('/api/billing/me?student='+a,cookie=bc)
   self.assertEqual(status,200);self.assertEqual(data['questions']['limit'],3)
   with auth._db() as db:
    day,month,_,_=billing.periods()
    db.executemany("INSERT INTO allowance_jobs VALUES(?,?,?,?,?,'used',?)",[(a,'questions','test'+str(i),day,month,time.time()) for i in range(96)])
    db.executemany("INSERT INTO allowance_jobs VALUES(?,?,?,?,?,'used',?)",[(a,'explorer','image'+str(i),day,month,time.time()) for i in range(1000)])
   with self.assertRaises(DomainError):self.use(a,'over100')
   with self.assertRaises(DomainError):self.use(a,'over1000','explorer')
  self.assertEqual(billing.overview(a)['questions']['limit'],3)
  with self.assertRaises(DomainError):self.use(a,'after-revoke')
 def test_daily_three_shared_and_failed_release(self):
  a,c=self.owner();self.use(a,'a');self.use(a,'b')
  with self.assertRaises(ValueError):
   with billing.successful_use(a,'questions','bad'):raise ValueError('upstream')
  self.assertEqual(billing.overview(a)['questions']['remaining'],1)
  self.use(a,'c');self.use(a,'a')
  with self.assertRaises(DomainError):self.use(a,'d')
  self.assertEqual(billing.overview(a)['questions']['used'],3)
  b,_=self.owner('b@example.test');self.assertEqual(billing.overview(b)['questions']['used'],0)
  status,data,_=self.req('/api/billing/me',cookie=c);self.assertEqual(status,200);self.assertEqual(data['questions']['used'],3)
 def test_concurrent_no_overspend_and_pending_recovery(self):
  a,_=self.owner()
  def run(i):
   try:self.use(a,str(i));return True
   except DomainError:return False
  with ThreadPoolExecutor(max_workers=12) as pool:results=list(pool.map(run,range(20)))
  self.assertEqual(sum(results),3)
  with auth._db() as db:db.execute("UPDATE allowance_jobs SET state='pending',created=? WHERE job=(SELECT job FROM allowance_jobs LIMIT 1)",(time.time()-301,))
  self.assertEqual(billing.overview(a)['questions']['used'],2)
 def test_saved_card_crash_recovery_and_periods(self):
  a,_=self.owner();day=datetime(2026,11,15,23,59,tzinfo=billing.TZ)
  with patch('app.billing._now',return_value=day):
   for i in range(3):self.use(a,str(i))
   self.assertEqual(billing.overview(a)['questions']['reset_at'],'2026-11-16T00:00:00+08:00')
  with patch('app.billing._now',return_value=datetime(2026,11,16,0,1,tzinfo=billing.TZ)):
   self.assertEqual(billing.overview(a)['questions']['remaining'],3)
  with auth._db() as db:
   job=db.execute('SELECT job FROM allowance_jobs LIMIT 1').fetchone()[0]
   db.execute("UPDATE allowance_jobs SET state='pending',created=? WHERE job=?",(time.time()-301,job))
  store.update(a,lambda v:v['wrong_cards'].update({'saved':{'_billing_key':job}}))
  billing.overview(a)
  with auth._db() as db:self.assertEqual(db.execute('SELECT state FROM allowance_jobs WHERE job=?',(job,)).fetchone()[0],'used')
 def test_explicit_explorer_ten_idempotence_conflict_failure(self):
  a,_=self.owner();body={'request_id':'frame0001','image_data':'synthetic'}
  with patch('app.explorer.observe',return_value={'ok':True,'description':'A tree.','changed':True}) as call:
   explorer.metered_observe(a,body);explorer.metered_observe(a,body);self.assertEqual(call.call_count,1)
   with self.assertRaises(DomainError):explorer.metered_observe(a,{**body,'image_data':'changed'})
   for i in range(2,11):explorer.metered_observe(a,{**body,'request_id':f'frame{i:04}'})
   with self.assertRaises(DomainError):explorer.metered_observe(a,{**body,'request_id':'frame0011'})
  self.assertEqual(billing.overview(a)['explorer']['remaining'],0)
  with patch('app.billing._now',return_value=datetime(2026,12,1,tzinfo=billing.TZ)):
   self.assertEqual(billing.overview(a)['explorer']['remaining'],10)
   with patch('app.explorer.observe',side_effect=ValueError('failed')):
    with self.assertRaises(ValueError):explorer.metered_observe(a,{**body,'request_id':'failed01'})
   self.assertEqual(billing.overview(a)['explorer']['remaining'],10)
 def test_canonical_study_all_entrypoints_failure_and_replay(self):
  a,c=self.owner()
  # A server-confirmed source is stable even if the client changes request_id.
  receipt={'reading':{'reading_id':'reading01'},'legacy_compat':False}
  with patch('app.cards.readings.confirm',return_value=receipt),patch('app.cards._study_impl',return_value={'output':{}}) as impl:
   cards.study(a,{},'request1');cards.study(a,{},'request2')
   self.assertEqual(impl.call_args_list[0].args[2],impl.call_args_list[1].args[2]);self.assertEqual(billing.overview(a)['questions']['used'],1)
   for rid in ['reading02','reading03']:
    receipt['reading']['reading_id']=rid;cards.study(a,{},'different')
   receipt['reading']['reading_id']='reading04'
   with self.assertRaises(DomainError):cards.study(a,{},'other')
  status,result,_=self.req('/api/study',{'problem':'x^2-9','steps':['(x-3)^2'],'request_id':'manual4'},cookie=c)
  self.assertEqual(status,429);self.assertEqual(result['code'],'ALLOWANCE_EXHAUSTED')
 def test_catalog_selection_never_grants_or_takes_client_price(self):
  a,c=self.owner()
  self.assertEqual(self.req('/pricing')[0],200);self.assertEqual(self.req('/api/billing/catalog')[0],200)
  self.assertEqual(self.req('/api/billing/me')[0],401)
  status,r,_=self.req('/api/billing/selection',{'plan':'grow','interval':'monthly'},cookie=c)
  self.assertEqual(status,200);self.assertEqual(r['amount_fen'],5900);self.assertFalse(r['activated'])
  self.assertEqual(self.req('/api/billing/selection',{'plan':'plus','interval':'monthly'},cookie=c)[1]['amount_fen'],11900)
  self.assertEqual(self.req('/api/billing/selection',{'plan':'grow','interval':'annual'},cookie=c)[0],400)
  self.assertIsNone(billing.catalog()['plans']['grow']['annual_fen'])
  self.assertEqual(billing.overview(a)['plan'],'free')
  self.assertEqual(self.req('/api/billing/selection',{'plan':'grow','interval':'annual','amount_fen':1},cookie=c)[0],400)
  self.assertEqual(self.req('/api/billing/selection',{'plan':'plus','interval':'monthly'})[0],401)
  self.assertEqual(self.req('/api/billing/webhook',{'paid':True},cookie=c)[0],404)

 def test_real_card_idempotence_and_failed_store(self):
  from app.pipeline import diagnose
  a,_=self.owner();body={'problem':'x^2-9','steps':['(x-3)^2']}
  value=diagnose(body['problem'],body['steps'])
  with patch('app.cards.junior.study',return_value=value):
   first=cards.study(a,body,'source1',strict=False)
   again=cards.study(a,body,'source1',strict=False)
   self.assertEqual(first['output']['wrong_card']['id'],again['output']['wrong_card']['id'])
   self.assertEqual(len(store.read(a)['wrong_cards']),1)
   self.assertEqual(billing.overview(a)['questions']['used'],1)
   with patch('app.profile._save',side_effect=OSError('disk')):
    with self.assertRaises(OSError):cards.study(a,body,'source2',strict=False)
   self.assertEqual(billing.overview(a)['questions']['used'],1)
 def test_explorer_cancel_inflight_no_charge_or_late_result(self):
  a,_=self.owner();body={'request_id':'cancel001','image_data':'synthetic'}
  def cancelled(clean):
   billing.cancel_explorer(a,{'request_id':body['request_id']})
   return {'ok':True,'description':'A tree.','changed':True}
  with patch('app.explorer.observe',side_effect=cancelled):
   with self.assertRaises(DomainError):explorer.metered_observe(a,body)
  self.assertEqual(billing.overview(a)['explorer']['used'],0)
