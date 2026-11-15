"""上传链路：PDF选页与失败恢复、纯题干学习，不调用真实付费模型。"""
import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import profile
from app.documents import preview_pdf
from app.pipeline import prepare_lesson
from test_all import _req,_serve

FIXTURE=Path(__file__).parent/'fixtures'/'worksheet.pdf'

def pdf_data():return 'data:application/pdf;base64,'+base64.b64encode(FIXTURE.read_bytes()).decode()

class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patch=patch('app.profile._PATH',self.temp.name+'/profile.json');self.patch.start()
        self.httpd,self.base=_serve()
    def tearDown(self):
        self.httpd.shutdown();self.httpd.server_close();self.patch.stop();self.temp.cleanup()
    def post(self,path,body):
        code,raw=_req(self.base,'POST',path,{'student':'upload_student',**body})
        self.assertEqual(code,200,raw)
        return json.loads(raw)
    def test_two_pdf_pages_render_independently_without_ai_or_grading(self):
        with patch('app.ai.complete') as complete:
            first=self.post('/api/files/preview',{'file_data':pdf_data(),'page':1})
            second=self.post('/api/files/preview',{'file_data':pdf_data(),'page':2})
        complete.assert_not_called()
        self.assertEqual(first['page_count'],2);self.assertEqual(second['page'],2)
        self.assertNotEqual(first['preview'],second['preview'])
        from PIL import Image
        with Image.open(io.BytesIO(base64.b64decode(second['preview'].split(',')[1]))) as image:
            self.assertEqual(max(image.size),2000)
        self.assertEqual(profile.get('upload_student')['history'],0)
    def test_invalid_pdf_and_page_are_recoverable_errors(self):
        for page in (0,True,'1',3):
            code,_=_req(self.base,'POST','/api/files/preview',{'file_data':pdf_data(),'page':page})
            self.assertEqual(code,400)
        for data in ('https://example.com/a.pdf','data:application/pdf;base64,AA==','data:application/pdf;base64,'+base64.b64encode(b'%PDF-broken').decode()):
            with self.assertRaises(ValueError):preview_pdf(data)
    def test_pdf_size_and_page_count_limits(self):
        with patch('app.documents.MAX_FILE',100):
            with self.assertRaises(ValueError):preview_pdf(pdf_data())
        with patch('app.documents.MAX_PAGES',1):
            with self.assertRaises(ValueError):preview_pdf(pdf_data())
    def test_question_without_work_does_not_invent_mistakes_or_progress(self):
        result=self.post('/api/learn',{'problem':'x^2-9','request_id':'lesson_once'})
        self.assertTrue(result['ok']);self.assertEqual(result['analysis']['status'],'not_attempted')
        self.assertFalse(result['analysis']['steps']);self.assertIsNone(result['analysis']['cause'])
        self.assertEqual(result['analysis']['lesson_kp'],'F2')
        self.assertTrue(result['analysis']['visual_svg'])
        saved=profile.get('upload_student')
        self.assertEqual(saved['history'],0);self.assertFalse(saved['causes']);self.assertFalse(saved['reviews'])
        self.assertFalse(any(k['lit'] for k in saved['tree']))
        self.assertEqual(saved['recent'][0]['type'],'lesson')
        self.assertEqual(profile.diagnosis_for('upload_student',result['diagnosis_id'])['status'],'not_attempted')
        repeated=self.post('/api/learn',{'problem':'x^2-9','request_id':'lesson_once'})
        self.assertEqual(result['diagnosis_id'],repeated['diagnosis_id'])
    def test_question_learning_practice_and_review_close_the_loop(self):
        lesson=self.post('/api/learn',{'problem':'x^2-9'})
        exercises=self.post('/api/practice',{'diagnosis_id':lesson['diagnosis_id']})
        self.assertEqual(exercises['kp'],'F2');self.assertEqual(len(exercises['items']),3)
        for item in exercises['items']:
            answer=profile._load()['upload_student']['exercises'][item['id']]['a']
            result=self.post('/api/practice/check',{'exercise_id':item['id'],'answer':answer})
            self.assertTrue(result['correct'])
        saved=profile.get('upload_student')
        self.assertEqual(saved['practice_correct'],3);self.assertFalse(saved['causes'])
        self.assertEqual(saved['history'],0)
        review=saved['reviews'][0];self.assertEqual(review['kp'],'F2');self.assertEqual(review['completed'],1);self.assertEqual(review['stage'],0)
        next_items=self.post('/api/practice',{'review_id':'F2'})
        self.assertEqual(next_items['kp'],'F2')
    def test_unsupported_question_is_not_silently_changed(self):
        result=self.post('/api/learn',{'problem':'x^2-9=0'})
        self.assertFalse(result['ok']);self.assertEqual(profile.get('upload_student')['history'],0)

if __name__=='__main__':unittest.main(verbosity=2)
