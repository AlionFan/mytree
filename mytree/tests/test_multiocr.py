"""Multi-question policy/transactions with synthetic source data, no real photo."""
import concurrent.futures,copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import page_reading as page,profile,store,cards,ai,contract
from app.reading_registry import ReadingRegistry,ConfirmationError
from test_ai import sample_image
from test_all import _serve,_req


def item(number='1',problem='x^2-9',steps=None,**changes):
    work=['(x-3)^2'] if steps is None else steps
    value={'printed_number':number,'problem':problem,'problem_latex':problem,'steps':work,'question_type':'factor','topic_id':'F2','diagram_description':'','uncertain_lines':[],'warnings':[],'supported':True,
           'region':[0,0,1,0.4],'fragments':[{'role':'problem','script_kind':'printed','text':problem,'region':[0,0,1,0.2]}]+([{'role':'student_work','script_kind':'handwritten','text':'\n'.join(work),'region':[0.1,0.05,0.7,0.2]}] if work else []),
           'problem_complete':True,'diagram_complete':True,'association_status':'clear','answer_presence':'present' if work else 'absent','association_evidence':'题号和笔迹延续一致；手写内容属于本题。'}
    value.update(changes);return value


def raw_page(items=None,**changes):
    a=item();b=item('2','x^2-16',['(x-4)(x+4)']);b['region']=[0.5,0.4,0.5,0.3];b['fragments'][1]['region']=[0.55,0.45,0.4,0.2]
    c=item('3','x^2-25',[]);c['region']=[0,0.7,1,0.3]
    value={'items':items if items is not None else [a,b,c],'unassigned_fragments':[],'overflow':False,'warnings':[]};value.update(changes);return value


class MultiOCRTests(unittest.TestCase):
 def setUp(self):
    self.temp=tempfile.TemporaryDirectory();self.patches=[patch.object(profile,'_PATH',self.temp.name+'/p.json'),patch('app.page_reading.registry',ReadingRegistry()),patch('app.cards.readings',None)]
    self.patches[0].start();self.registry=self.patches[1].start();self.card_registry=patch('app.cards.readings',self.registry);self.card_registry.start()
    self.http,self.base=_serve()
 def tearDown(self):self.http.shutdown();self.http.server_close();self.card_registry.stop();self.patches[1].stop();self.patches[0].stop();self.temp.cleanup()
 def register(self,raw=None,student='owner',request='page-req'):
    with patch('app.page_reading.ai.complete',return_value=(raw or raw_page(),{})) as complete:
     result=page.recognize(student,{'image_data':sample_image(),'request_id':request,'client_generation':'generation','page_index':2})
    self.assertEqual(complete.call_count,1);return result
 def study(self,result,index=0,student='owner',request='study-request'):
    return page.study(student,{'batch_id':result['batch_id'],'reading_id':result['items'][index]['reading_id'],'source_revision':1,'request_id':request})
 def test_three_questions_order_subquestions_and_no_manual_confirmation(self):
    raw=raw_page();raw['items'][2]['problem']='在三角形ABC中，AB=AC，顶角A为40度。(1)求底角B；(2)说明两个底角的关系。';raw['items'][2]['problem_latex']='';raw['items'][2]['question_type']='geometry';raw['items'][2]['topic_id']='G2';raw['items'][2]['diagram_description']='三角形ABC，AB=AC，顶角A为40度。';raw['items'][2]['fragments'][0]['text']=raw['items'][2]['problem']
    output=self.register(raw)
    self.assertEqual(len(output['items']),3);self.assertEqual([i['printed_number'] for i in output['items']],['1','2','3']);self.assertIn('(2)',output['items'][2]['problem'])
    self.assertTrue(all(i['auto_ready'] and not i['needs_confirmation'] for i in output['items']));self.assertEqual(output['page_index'],2)
    first=self.study(output);self.assertEqual(first['analysis']['status'],'wrong_step');self.assertEqual(first['wrong_card']['student_steps'],[r'\((x-3)^2\)'])
    saved=store.read('owner')['wrong_cards'][first['wrong_card']['id']];self.assertEqual(saved['_source']['acceptance'],'auto')
 def test_overlap_above_and_handwritten_problem_do_not_define_role(self):
    for script,region in [('handwritten',[0,0,1,0.2]),('printed',[0.1,0.01,0.7,0.1]),('handwritten',[0.1,0.19,0.7,0.2])]:
     value=item();value['fragments'][0]['script_kind']=script;value['fragments'][1]['region']=region
     result=page.normalize_page(raw_page([value]),1,'g');self.assertTrue(result['items'][0]['auto_ready']);self.assertEqual(result['items'][0]['steps'],[r'\((x-3)^2\)'])
 def test_teacher_crossed_and_unknown_assignment_do_not_count_as_work(self):
    value=item();value['fragments'].append({'role':'teacher_annotation','script_kind':'handwritten','text':'(x-3)^2','region':[0,0,1,0.2]})
    output=page.normalize_page(raw_page([value]),1,'g');self.assertFalse(output['items'][0]['auto_ready'])
    raw=raw_page();raw['unassigned_fragments']=[{'role':'unknown','script_kind':'handwritten','text':'x=7','region':[0,0.3,1,0.1],'affected_orders':[1]}]
    output=self.register(raw);self.assertFalse(output['items'][0]['auto_ready']);self.assertTrue(output['items'][1]['auto_ready']);self.assertTrue(output['items'][2]['auto_ready'])
    result=self.study(output)
    self.assertEqual(result['analysis']['study_mode'],'lesson_only');self.assertEqual(result['analysis']['status'],'not_attempted');self.assertEqual(result['wrong_card']['type'],'lesson');self.assertEqual(result['wrong_card']['student_steps'],output['items'][0]['steps'])
    value=store.read('owner');self.assertFalse(value['causes']);self.assertFalse(value['lit']);self.assertEqual(value['history'],0)
 def test_partial_ready_missing_conditions_and_no_work(self):
    raw=raw_page();raw['items'][1]['problem_complete']=False;output=self.register(raw)
    self.study(output,0);self.study(output,2)
    with self.assertRaises(ConfirmationError):self.study(output,1)
    saved=store.read('owner');self.assertEqual(len(saved['wrong_cards']),2);self.assertEqual(saved['history'],1);self.assertFalse(saved['lit']);self.assertEqual(saved['causes'].get('F-MIX-FORMULA'),1)
 def test_auto_correct_photo_does_not_light_mastery(self):
    output=self.register(raw_page([item(steps=['(x-3)(x+3)'])]));result=self.study(output)
    self.assertEqual(result['analysis']['status'],'correct');self.assertFalse(store.read('owner')['lit']);self.assertFalse(store.read('owner')['knowledge_cards'])
 def test_unverified_ai_cannot_add_error_counts_or_mastery(self):
    value=item(problem='证明两个三角形全等。',steps=['这两个角相等。'],problem_latex='',question_type='geometry',topic_id='G9')
    output=self.register(raw_page([value]));teacher={'hints':['看图','看条件','完整思路'],'card':{'title':'全等','body':'对应关系','tip':'核对图形'},'assessment':'你做错了','answer_latex':'','knowledge_ids':['G9']}
    with patch('app.ai.complete',return_value=(teacher,{})):result=self.study(output)
    saved=store.read('owner');self.assertEqual(result['analysis']['status'],'ai_review');self.assertFalse(saved['causes']);self.assertFalse(saved['kp_wrong']);self.assertFalse(saved['lit']);self.assertFalse(saved['knowledge_cards'])
 def test_retry_concurrency_and_restart_use_same_card_without_ai(self):
    output=self.register()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda k:self.study(output,request='request-'+str(k)),range(2)))
    self.assertEqual(results[0]['wrong_card']['id'],results[1]['wrong_card']['id']);self.assertEqual(len(store.read('owner')['wrong_cards']),1)
    self.registry._pages.clear()
    with patch('app.junior.study',side_effect=AssertionError('must not re-run')):replayed=self.study(output,request='after-restart')
    self.assertTrue(replayed['duplicate']);self.assertEqual(store.read('owner')['history'],1)
 def test_batch_and_reading_cross_owner_and_version(self):
    output=self.register()
    with self.assertRaises(ConfirmationError) as error:self.study(output,student='other')
    self.assertEqual(error.exception.status,404)
    body={'batch_id':output['batch_id'],'reading_id':output['items'][0]['reading_id'],'source_revision':2,'request_id':'wrong-revision'}
    with self.assertRaises((ConfirmationError,contract.ContractError)):page.study('owner',body)
    self.assertFalse(store.read('other')['wrong_cards'])
 def test_same_request_replay_no_extra_vision_and_changed_image_conflicts(self):
    output=self.register()
    with patch('app.page_reading.ai.complete',side_effect=AssertionError('no re-read')):
     replay=page.recognize('owner',{'image_data':sample_image(),'request_id':'page-req','client_generation':'generation','page_index':2})
    self.assertEqual(output,replay)
    with self.assertRaises(ConfirmationError):page.recognize('owner',{'image_data':sample_image(400,400),'request_id':'page-req','client_generation':'generation','page_index':2})
 def test_expired_cancelled_and_overflow_are_explicit(self):
    output=self.register();self.registry.cancel_page('owner',output['batch_id'],1)
    with self.assertRaises(ConfirmationError):self.study(output)
    output=self.register(request='second-page');self.registry.clock=lambda:10**12
    with self.assertRaises(ConfirmationError) as error:self.study(output)
    self.assertEqual(error.exception.status,409)
    overflow=page.normalize_page(raw_page([item(str(k),steps=[]) for k in range(13)]),1,'g');self.assertEqual(len(overflow['items']),12);self.assertTrue(overflow['overflow']);self.assertTrue(overflow['warnings'])
 def test_absent_answer_cannot_ignore_student_fragment_and_missing_diagram(self):
    value=item(steps=[]);value['fragments'].append({'role':'student_work','script_kind':'handwritten','text':'x=7','region':[0,0,1,0.2]})
    self.assertFalse(page.normalize_page(raw_page([value]),1,'g')['items'][0]['auto_ready'])
    value=item(problem='如图，求这个角。',steps=[],problem_latex='',question_type='geometry')
    self.assertFalse(page.normalize_page(raw_page([value]),1,'g')['items'][0]['auto_ready'])
 def test_resume_keeps_completed_cards_and_does_not_repeat_vision(self):
    output=self.register();first=self.study(output,0);self.registry.cancel_page('owner',output['batch_id'],1)
    self.registry.resume_page('owner',output['batch_id'],1)
    with patch('app.ai.complete',side_effect=AssertionError('no duplicate model call')):
     replay=self.study(output,0,request='retry-after-stop')
    self.assertEqual(replay['wrong_card']['id'],first['wrong_card']['id']);self.assertTrue(replay['duplicate'])
    self.study(output,2);self.assertEqual(len(store.read('owner')['wrong_cards']),2)
 def test_internal_source_conflicts_block_only_the_affected_question(self):
    variants=[]
    wrong_pure=item(problem='x^2-16',steps=['(x-4)(x+4)'],problem_latex='x^2-9');variants.append(wrong_pure)
    wrong_work=item();wrong_work['fragments'][1]['text']='(x-3)(x+3)';variants.append(wrong_work)
    wrong_print=item();wrong_print['fragments'][0]['text']='x^2-16';variants.append(wrong_print)
    teacher=item();teacher['fragments'][1]['text']='(x-3)(x+3)';teacher['fragments'].append({'role':'teacher_annotation','script_kind':'handwritten','text':'老师：(x-3)^2','region':[0,0,1,0.2]});variants.append(teacher)
    for value in variants:
     output=page.normalize_page(raw_page([value,item('2','x^2-25',[])]),1,'g')
     self.assertFalse(output['items'][0]['auto_ready']);self.assertTrue(output['items'][1]['auto_ready'])
 def test_format_and_multiple_fragments_are_not_mathematical_rewrites(self):
    value=item(problem='分解因式：$x^{2} - 9$。',problem_latex='x^2-9',steps=[r'\((x-3)^2\)'])
    value['fragments']=[{'role':'problem','script_kind':'printed','text':'1. 分解因式：x²','region':[0,0,0.5,0.2]},
       {'role':'problem','script_kind':'printed','text':'−9。','region':[0.5,0,0.5,0.2]},
       {'role':'student_work','script_kind':'handwritten','text':'(x−3)','region':[0,0.1,0.5,0.2]},
       {'role':'student_work','script_kind':'handwritten','text':'²','region':[0.5,0.1,0.4,0.2]}]
    self.assertTrue(page.normalize_page(raw_page([value]),1,'g')['items'][0]['auto_ready'])
    value['problem_latex']='(x-3)(x+3)'
    self.assertFalse(page.normalize_page(raw_page([value]),1,'g')['items'][0]['auto_ready'])
 def test_printed_number_prefix_does_not_erase_decimal_coefficient(self):
    bad=item(problem='1.5*x+1',problem_latex='5*x+1',steps=[],question_type='simplify')
    bad['fragments'][0]['text']='5*x+1'
    self.assertFalse(page.normalize_page(raw_page([bad]),1,'g')['items'][0]['auto_ready'])
    good=item(problem='2*x+1',problem_latex='2x+1',steps=[],question_type='simplify')
    good['fragments'][0]['text']='1. 2x+1'
    self.assertTrue(page.normalize_page(raw_page([good]),1,'g')['items'][0]['auto_ready'])
 def test_one_malformed_question_does_not_clear_other_questions(self):
    raw=raw_page();raw['items'][1]['region']=[0.9,0.9,0.5,0.5];output=self.register(raw)
    self.assertFalse(output['items'][1]['auto_ready']);self.assertTrue(output['items'][0]['auto_ready'])
    for malformed in ({'items':[],'overflow':False},{'items':'bad','overflow':False}):
     with self.assertRaises(ai.ModelError):page.normalize_page(malformed,1,'g')
 def test_shared_student_fragment_is_not_copied_between_questions(self):
    raw=raw_page();raw['items'][1]['fragments'][1]=copy.deepcopy(raw['items'][0]['fragments'][1]);output=page.normalize_page(raw,1,'g')
    self.assertFalse(output['items'][0]['auto_ready']);self.assertFalse(output['items'][1]['auto_ready']);self.assertTrue(output['items'][2]['auto_ready'])
 def test_client_text_or_ready_flags_are_not_accepted_by_schema(self):
    output=self.register();body={'batch_id':output['batch_id'],'reading_id':output['items'][0]['reading_id'],'source_revision':1,'request_id':'x'}
    for extra in ({'steps':['correct']},{'auto_ready':True},{'acceptance_token':'fake'}):
     with self.assertRaises(contract.ContractError):page.study('owner',{**body,**extra})
 def test_new_page_cannot_be_studied_through_legacy_manual_receipt(self):
    output=self.register()
    with self.assertRaises(ConfirmationError):cards.study('owner',{'problem':'x^2-9','steps':['(x-3)^2'],'confirmed_reading_id':output['items'][0]['reading_id']},'forged-legacy',strict=True)

if __name__=='__main__':unittest.main(verbosity=2)
