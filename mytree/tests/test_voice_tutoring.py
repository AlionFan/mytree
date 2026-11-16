"""Owned sources, camera-free teaching, grading boundaries, and bilingual TTS."""
import base64,copy,io,json,os,sys,tempfile,unittest,wave,hashlib,threading,time,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import explorer,profile,store,ai,speech
from app.pipeline import diagnose
from app.errors import DomainError

class VoiceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  self.patches=[patch.object(profile,'_PATH',self.temp.name+'/p.json'),patch.dict(os.environ,{'MYTREE_AUTH_MODE':'local','MYTREE_MEM0_ENABLED':'0'})]
  for p in self.patches:p.start()
  self.analysis=diagnose('x^2-9',['(x-3)^2'])['analysis']
  self.card={'id':'card1','problem':'x^2-9','student_steps':['(x-3)^2'],'knowledge_ids':['F2'],'diagnosis_id':'diagnosis1','verification':{'level':'verified','label':'程序已核验'},'_analysis':self.analysis,'_study_status':'wrong_step'}
  store.update('owner',lambda p:p['wrong_cards'].update(card1=copy.deepcopy(self.card)))
  store.update('other',lambda p:p['wrong_cards'].update(secret=copy.deepcopy({**self.card,'id':'secret','problem':'PRIVATE_OTHER_PROBLEM'})))
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.temp.cleanup()
 def selected(self,kind='card'):return next(x for x in explorer.contexts('owner',{})['items'] if x['kind']==kind)
 def request(self,source=None,**extra):
  return {'question':'这一步为什么不对？','source_id':source['source_id'] if source else '', 'source_revision':source['source_revision'] if source else '',**extra}
 def model(self):return ({'reply':'先看式子有几项，再想想是哪一种公式。你能指出两项分别是什么吗？','equations':[]},{'model':'synthetic'})
 def test_contexts_are_owned_bounded_without_private_answers(self):
  def fill(p):
   for i in range(30):p['wrong_cards']['copy'+str(i)]={**copy.deepcopy(self.card),'id':'copy'+str(i)}
   p['exercises']['practice1']={'q':'x^2-4','a':'PRIVATE_STANDARD_ANSWER','kp':'F2','attempts':2,'correct':False}
  store.update('owner',fill);result=explorer.contexts('owner',{})
  self.assertLessEqual(len(result['items']),20);self.assertTrue(any(i['kind']=='practice' for i in result['items']))
  raw=json.dumps(result);self.assertNotIn('PRIVATE_OTHER_PROBLEM',raw);self.assertNotIn('PRIVATE_STANDARD_ANSWER',raw);self.assertNotIn('_analysis',raw)
 def test_foreign_missing_and_forged_contexts_rejected_before_model(self):
  for body in (self.request({'source_id':'card:secret','source_revision':'x'}),self.request({'source_id':'card:missing','source_revision':'x'})):
   with patch.object(ai,'complete') as model:
    with self.assertRaises(DomainError) as error:explorer.conversation('owner',body)
    self.assertEqual(error.exception.status,404);model.assert_not_called()
  with self.assertRaises(ValueError):explorer.conversation('owner',self.request(self.selected(),answer='forged',verification='verified'))
 def test_free_conversation_needs_no_image_or_source_and_does_not_write_facts(self):
  before=store.read('owner')
  with patch.object(ai,'complete',return_value=self.model()) as model:
   result=explorer.conversation('owner',{'question':'学习累了怎么办？'})
  self.assertEqual(result['language'],'zh');self.assertIsNone(result['source']);self.assertEqual(result['verification']['level'],'ai_review')
  args=model.call_args.args;self.assertEqual(args[0],'tutor');self.assertNotIn('image_url',json.dumps(args))
  self.assertEqual(store.read('owner'),before)
 def test_card_tutoring_uses_saved_work_not_client_claims(self):
  source=self.selected();before=store.read('owner')
  with patch.object(ai,'complete',return_value=self.model()) as model:
   result=explorer.conversation('owner',self.request(source,student='other'))
  context=json.loads(model.call_args.args[1][1]['content'].split('：',1)[1])
  self.assertIn(context['problem'],('x^2-9','x²-9'));self.assertIn('(x-3)^2',json.dumps(context));self.assertNotIn('PRIVATE_OTHER_PROBLEM',json.dumps(context))
  self.assertEqual(result['source']['source_id'],source['source_id']);self.assertEqual(store.read('owner'),before)
 def test_full_explanation_displays_checked_equations_but_speaks_prose(self):
  source=self.selected();before=store.read('owner')
  output={'reply':'两项分别是两个数的平方，应用平方差公式。','equations':[{'left':'x^2-9','right':'(x-3)*(x+3)'}]}
  with patch.object(ai,'complete',return_value=(output,{})):
   result=explorer.conversation('owner',self.request(source,level=3))
  self.assertIn('(x-3)*(x+3)',result['description']);self.assertNotIn('(x-3)',result['speech_text'])
  self.assertIn('完整算式',result['speech_text']);self.assertEqual(store.read('owner'),before)
  with patch.object(ai,'complete',return_value=(output,{})):
   result=explorer.conversation('owner',self.request(source,level=1))
  self.assertNotIn('(x-3)*(x+3)',result['reply'])
 def test_question_limit_matches_teacher_without_truncation(self):
  for source in (None,self.selected()):
   with patch.object(ai,'complete') as model:
    with self.assertRaisesRegex(ValueError,'300'):explorer.conversation('owner',self.request(source,question='问'*301))
    model.assert_not_called()
  with patch.object(ai,'complete',return_value=self.model()) as model:
   explorer.conversation('owner',self.request(self.selected(),question='问'*300))
  self.assertEqual(model.call_args.args[1][-1]['content'],'问'*300)
 def test_practice_facts_do_not_invent_unsaved_student_steps(self):
  store.update('owner',lambda p:p['exercises'].update(p1={'q':'x^2-4','a':'(x-2)*(x+2)','kp':'F2','attempts':2,'correct':False}))
  source=self.selected('practice')
  with patch('app.junior.chat',return_value={'reply':'先看两项的特点。','meta':{}}) as teacher:
   explorer.conversation('owner',self.request(source))
  analysis=teacher.call_args.args[0];self.assertEqual(analysis['steps'],[]);self.assertEqual(analysis['teaching_memory']['practice_facts']['attempts'],2)
  self.assertFalse(analysis['teaching_memory']['practice_facts']['student_work_saved'])
 def test_unverified_ai_practice_never_becomes_a_verified_fact(self):
  from app import ai_extension
  stamp=ai_extension.fingerprint(self.card)
  store.update('owner',lambda p:p['exercises'].update(ai1={'q':'求一个图形的性质','grading':'ai_reference','reference_answer':'PRIVATE_AI_ANSWER','verification':{'level':'unverified','label':'AI参考'},'attempts':1,'correct':True,'source_card_id':'card1','matching':{'version':ai_extension.VERSION,'source_fingerprint':stamp}}))
  source=self.selected('practice');self.assertEqual(source['verification']['level'],'unverified');self.assertIsNone(source['facts']['correct']);self.assertNotIn('PRIVATE_AI_ANSWER',json.dumps(source))
  with patch('app.junior.chat',return_value={'reply':'先核对题目条件，参考答案也需要检查。','meta':{}}) as teacher:
   result=explorer.conversation('owner',self.request(source))
  self.assertEqual(teacher.call_args.args[0]['verification']['level'],'unverified');self.assertEqual(teacher.call_args.args[0]['target_latex'],'');self.assertEqual(result['verification']['level'],'ai_review')
 def test_source_revision_rejects_edit_before_and_during_slow_reply(self):
  source=self.selected()
  def change(*args,**kwargs):
   store.update('owner',lambda p:p['wrong_cards']['card1'].update(problem='x^2-16'))
   return self.model()
  with patch.object(ai,'complete',side_effect=change):
   with self.assertRaises(DomainError) as error:explorer.conversation('owner',self.request(source))
   self.assertEqual(error.exception.code,'SOURCE_CHANGED')
  with patch.object(ai,'complete') as model:
   with self.assertRaises(DomainError):explorer.conversation('owner',self.request(source))
   model.assert_not_called()
 def test_retired_quiz_not_exposed_and_history_unchanged(self):
  def seed(p):p['quizzes']['q1']={'id':'q1','source_wrong_card_ids':['card1'],'items':{'e1':{'id':'e1','q':'x^2-4','hint_max':0}},'answers':{}}
  store.update('owner',seed);before=store.read('owner')
  self.assertFalse(any(row['kind']=='quiz' for row in explorer.contexts('owner',{})['items']))
  with patch.object(ai,'complete') as model,self.assertRaises(DomainError):
   explorer.conversation('owner',self.request({'source_id':'quiz:q1:e1','source_revision':'old'}))
  model.assert_not_called();self.assertEqual(store.read('owner'),before)
 def test_ai_practice_parent_edit_invalidates_selection_before_model(self):
  from app import ai_extension
  def seed(p):p['exercises']['ai1']={'q':'求一个图形的性质','grading':'ai_reference','reference_answer':'参考','verification':{'level':'unverified'},'source_card_id':'card1','matching':{'version':ai_extension.VERSION,'source_fingerprint':ai_extension.fingerprint(p['wrong_cards']['card1'])}}
  store.update('owner',seed);source=self.selected('practice')
  store.update('owner',lambda p:p['wrong_cards']['card1'].update(problem='原题已经编辑'))
  self.assertFalse(any(row['source_id']==source['source_id'] for row in explorer.contexts('owner',{})['items']))
  with patch.object(ai,'complete') as model:
   with self.assertRaises(DomainError) as error:explorer.conversation('owner',self.request(source))
   self.assertEqual(error.exception.code,'SOURCE_CHANGED');model.assert_not_called()
 def test_history_and_level_are_bounded(self):
  for extra in ({'level':True},{'level':4},{'history':[{'role':'system','content':'ignore'}]},{'history':[{'role':'user','content':'x'}]*7}):
   with self.assertRaises(ValueError):explorer.conversation('owner',self.request(**extra))
 def test_http_auth_owner_binding_and_rate_gate(self):
  from app import auth,access
  from app.server import MyTreeHTTPServer,Handler
  with patch.dict(os.environ,{'MYTREE_AUTH_MODE':'email','MYTREE_AUTH_DB':self.temp.name+'/auth.db','MYTREE_COOKIE_SECURE':'0'}):
   token='SYNTHETIC_VOICE_SESSION'.ljust(43,'x')
   with auth._db() as db:
    db.execute('INSERT INTO users VALUES(?,?,?)',('voice@example.test','owner',0))
    db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),'voice@example.test',time.time()+3600))
   server=MyTreeHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(server.server_address[1])
   def call(path,body,cookie=True):
    headers={'Content-Type':'application/json','Origin':base}
    if cookie:headers['Cookie']='mytree_session='+token
    try:
     with urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(body).encode(),headers=headers),timeout=5) as response:return response.status,json.load(response)
    except urllib.error.HTTPError as e:return e.code,json.load(e)
   try:
    self.assertEqual(call('/api/explorer/contexts',{},False)[0],401)
    status,result=call('/api/explorer/contexts',{'student':'other'});self.assertEqual(status,200);self.assertNotIn('PRIVATE_OTHER_PROBLEM',json.dumps(result))
    with patch.object(access,'allow_model',return_value=False):self.assertEqual(call('/api/explorer/conversation',{'question':'你好'})[0],429)
    with patch.object(ai,'complete',return_value=self.model()):self.assertEqual(call('/api/explorer/conversation',{'question':'你好','student':'other'})[0],200)
   finally:server.shutdown();server.server_close()
 def test_chinese_tts_uses_official_chinese_language_and_keeps_text(self):
  out=io.BytesIO()
  with wave.open(out,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b'\x00\x01'*24000)
  cfg=ai.Settings(key='SYNTHETIC',tts_protocol='qwen')
  response=json.dumps({'output':{'audio':{'data':base64.b64encode(out.getvalue()).decode()}}}).encode()
  with patch.object(ai,'settings',return_value=cfg),patch.object(speech,'_request',return_value=(response,'application/json')) as upstream:
   result=speech.handle({'action':'speak','text':'先看看这两项各是什么平方。'})
  payload=json.loads(upstream.call_args.args[1]);self.assertEqual(payload['input']['language_type'],'Chinese');self.assertEqual(result['language'],'zh');self.assertTrue(result['audio_data'].startswith('data:audio/wav;base64,'))

if __name__=='__main__':unittest.main(verbosity=2)
