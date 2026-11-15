"""Real Mem0/Qdrant + configured NextLabs embeddings; synthetic learners only."""
import json,os,tempfile,time,unittest,subprocess,sys
from unittest.mock import patch
from app import cards,store,teaching_memory as tm,mem0_adapter as ma,personal_review as pr

class Mem0IntegrationTests(unittest.TestCase):
 def test_real_index_owner_restart_changes_and_failures(self):
  with tempfile.TemporaryDirectory() as d,patch('app.profile._PATH',d+'/p.json'),patch.dict(os.environ,{'MYTREE_MEMORY_DB':d+'/m.db','MYTREE_MEM0_ENABLED':'1'}):
   try:
    a=cards.study('one',{'problem':'x^2-9','steps':['(x-3)^2']},'one-source',strict=False)['output']['wrong_card']
    b=cards.study('two',{'problem':'x^2-9','steps':['(x-3)*(x+3)']},'two-source',strict=False)['output']['wrong_card']
    tm.remember_preference('one','visual');first=tm.retrieve('one','F2');self.assertEqual(first['engine'],'mem0');self.assertEqual(first['status'],'ready');self.assertEqual(len(first['records']),2)
    again=tm.retrieve('one','F2');self.assertEqual(again['new_records'],0)
    other=tm.retrieve('two','F2');self.assertTrue(other['records']);self.assertFalse(any(a['id'] in r['source_event_ids'] for r in other['records']))
    self.assertTrue(pr.arrange('one')['items']);self.assertEqual(pr.arrange('two')['items'],[])
    before=store.read('one');ma.close()
    child=subprocess.run([sys.executable,'-c',"from app import teaching_memory as t,mem0_adapter as m; import json; v=t.retrieve('one','F2'); print(json.dumps({'engine':v['engine'],'count':len(v['records']),'new':v.get('new_records')}));m.close()"],env={**os.environ,'MYTREE_PROFILE':d+'/p.json','MYTREE_MEMORY_DB':d+'/m.db'},capture_output=True,text=True,timeout=40,check=True)
    process_result=json.loads(child.stdout);self.assertEqual(process_result,{'engine':'mem0','count':2,'new':0})
    restarted=tm.retrieve('one','F2');self.assertEqual(restarted['new_records'],0);self.assertEqual(before,store.read('one'))
    fact=next(r for r in restarted['records'] if r['type']=='fact');tm.forget('one',fact['id']);self.assertFalse(any(r['id']==fact['id'] for r in tm.retrieve('one','F2')['records']));ma.close();self.assertFalse(any(r['id']==fact['id'] for r in tm.retrieve('one','F2')['records']))
    store.update('two',lambda p:p['wrong_cards'][b['id']].update(knowledge_ids=['F3']))
    self.assertEqual(tm.retrieve('two','F2')['records'],[]);self.assertTrue(tm.retrieve('two','F3')['records'])
    store.update('two',lambda p:p['wrong_cards'].clear());self.assertEqual(tm.retrieve('two')['records'],[]);ma.close();self.assertEqual(tm.retrieve('two')['records'],[])
    memory=ma._memory()
    for failure in (TimeoutError(),RuntimeError('401'),RuntimeError('unavailable')):
     # Controlled upstream failures, not claims that the real provider failed.
     with patch.object(memory,'search',side_effect=failure):
      degraded=tm.retrieve('one');self.assertEqual(degraded['engine'],'source-ledger');self.assertEqual(degraded['status'],'unavailable');self.assertTrue(degraded['message'])
    print(json.dumps({'real_mem0':True,'real_embeddings':True,'first_seconds':first['seconds'],'incremental_seconds':again['seconds'],'restart_seconds':restarted['seconds']},ensure_ascii=False))
   finally:ma.close()

if __name__=='__main__':unittest.main()
