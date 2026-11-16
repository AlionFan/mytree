"""Regressions for variable AI exercise shapes, bounded repair and retired mutations."""
import copy,unittest
from unittest.mock import patch
from app import ai_extension as ext,agent
from app.errors import DomainError

class FeedbackTests(unittest.TestCase):
 def setUp(self):
  self.source={'id':'synthetic','problem':'解方程 x+1=2','knowledge_ids':['E1']}
 def valid(self):
  return {'questions':[{'stem':f'解方程 x+{n}=7','reference_answer':7-n,'worked_steps':[f'两边同时减{n}。',f'x={7-n}。']} for n in (2,3,4)]},{'model':'synthetic'}
 def test_compatible_numeric_answers_and_step_lists(self):
  with patch('app.ai.complete',return_value=self.valid()) as call:items=ext.generate(self.source)
  self.assertEqual(call.call_count,1);self.assertEqual(items[0]['reference_answer'],'5');self.assertIn('两边同时减',items[0]['reference_solution'])
 def test_incomplete_first_response_repaired_once(self):
  broken=copy.deepcopy(self.valid());del broken[0]['questions'][0]['worked_steps']
  with patch('app.ai.complete',side_effect=[broken,self.valid()]) as call:items=ext.generate(self.source)
  self.assertEqual(call.call_count,2);self.assertEqual(len(items),3)
 def test_missing_reference_never_fabricated(self):
  broken=copy.deepcopy(self.valid());del broken[0]['questions'][1]['reference_answer']
  with patch('app.ai.complete',return_value=broken) as call,self.assertRaises(DomainError):ext.generate(self.source)
  self.assertEqual(call.call_count,2)
 def test_upstream_failure_is_not_retried(self):
  with patch('app.ai.complete',side_effect=DomainError('UPSTREAM','not available',502)) as call,self.assertRaises(DomainError):ext.generate(self.source)
  self.assertEqual(call.call_count,1)
 def test_retired_agent_envelope_is_a_valid_error(self):
  payload={'schema_version':'1.0','request_id':'retired-envelope','operation':'quiz.start','client':{'type':'web','name':'test'},'subject':{'profile_id':'synthetic'},'input':{'knowledge_id':'F2','source_wrong_card_ids':['source']}}
  output,status=agent.handle(payload)
  self.assertEqual(status,422);self.assertEqual(output['error']['code'],'UNSUPPORTED')
 def test_retired_quiz_mutations_do_not_invoke_storage(self):
  for op in ('quiz.start','quiz.answer','card.unlock'):
   with self.subTest(op=op),patch('app.agent.store.update') as update,self.assertRaises(DomainError) as caught:agent.invoke('synthetic',op,{},'retired-test',strict=False)
   self.assertEqual(caught.exception.code,'UNSUPPORTED');update.assert_not_called()

if __name__=='__main__':unittest.main()
