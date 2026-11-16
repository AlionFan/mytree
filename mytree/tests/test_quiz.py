"""Retired quiz HTTP routes preserve history and cannot mutate mastery."""
import json,tempfile,unittest,copy
from unittest.mock import patch
from app import profile,store,contract
from test_all import _req,_serve

class QuizRetirementTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.patch=patch('app.profile._PATH',self.temp.name+'/profiles.json');self.patch.start();self.server,self.base=_serve()
  store.update('owner',lambda p:p['quizzes'].update(historical={'id':'historical','items':{},'answers':{}}))
 def tearDown(self):self.server.shutdown();self.server.server_close();self.patch.stop();self.temp.cleanup()
 def test_write_operations_retired_without_state_changes(self):
  before=store.read('owner')
  for operation,params in [('quiz.start',{'knowledge_id':'F2','source_wrong_card_ids':['old']}),('quiz.answer',{'quiz_id':'historical','exercise_id':'old','answer':'3'}),('card.unlock',{'quiz_id':'historical'})]:
   body={'schema_version':'1.0','request_id':operation,'operation':operation,'client':{'type':'web','name':'test'},'subject':{'profile_id':'owner'},'input':params}
   code,raw=_req(self.base,'POST','/api/agent',body);result=json.loads(raw);contract.response(result)
   self.assertEqual(code,422,result);self.assertEqual(result['error']['code'],'UNSUPPORTED');self.assertEqual(result['effects'],[])
  self.assertEqual(store.read('owner'),before)
 def test_old_lesson_link_retired(self):
  code,raw=_req(self.base,'GET','/api/quiz/lesson?student=owner&source_wrong_card_id=old&knowledge_id=F2')
  self.assertEqual(code,410);self.assertEqual(json.loads(raw)['code'],'FEATURE_RETIRED')
 def test_old_quiz_hint_does_not_write_history(self):
  before=store.read('owner');code,raw=_req(self.base,'POST','/api/hint',{'student':'owner','diagnosis_id':'old','quiz_id':'historical','exercise_id':'old','level':3})
  self.assertEqual(code,422,raw);self.assertEqual(store.read('owner'),before)

if __name__=='__main__':unittest.main()
