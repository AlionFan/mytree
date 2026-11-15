import base64,concurrent.futures,io,json,tempfile,unittest
from unittest.mock import patch
from PIL import Image
from app import uploads,profile
from app.errors import DomainError

def body(request='one',color='white',name='试卷.jpg'):
 b=io.BytesIO();Image.new('RGB',(120,240),color).save(b,format='JPEG')
 return {'image_data':'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode(),'name':name,'request_id':request}
class UploadsTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.patch=patch.object(profile,'_PATH',self.temp.name+'/profiles.json');self.patch.start()
 def tearDown(self):self.patch.stop();self.temp.cleanup()
 def test_persistent_original_and_thumbnail_ratio(self):
  value=body();v=uploads.save('one',value)['upload'];raw,mime,_=uploads.image('one',v['id']);self.assertEqual(raw,base64.b64decode(value['image_data'].split(',')[1]));self.assertEqual(mime,'image/jpeg');self.assertEqual(uploads.listing('one')['items'][0]['id'],v['id']);thumb,_,_=uploads.image('one',v['id'],True)
  with Image.open(io.BytesIO(thumb)) as im:self.assertEqual(im.width/im.height,.5)
 def test_owner_isolation_delete_and_missing(self):
  v=uploads.save('one',body())['upload'];self.assertEqual(uploads.listing('two')['total'],0)
  for action in [lambda:uploads.image('two',v['id']),lambda:uploads.delete('two',{'upload_id':v['id']})]:
   with self.assertRaises(DomainError) as e:action()
   self.assertEqual(e.exception.status,404)
  uploads.delete('one',{'upload_id':v['id']});self.assertEqual(uploads.listing('one')['total'],0)
  with self.assertRaises(DomainError):uploads.image('one',v['id'])
 def test_idempotency_concurrency_and_changed_input(self):
  value=body()
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:uploads.save('one',value),range(3)))
  self.assertEqual(len({v['upload']['id'] for v in results}),1);self.assertEqual(uploads.listing('one')['total'],1)
  with self.assertRaises(DomainError) as e:uploads.save('one',body(color='red'))
  self.assertEqual(e.exception.status,409)
 def test_reject_invalid_files_ids_and_page(self):
  for change in [{'image_data':'data:image/svg+xml;base64,'+base64.b64encode(b'<svg/>').decode()},{'name':'bad\nheader'},{'request_id':'../x'},{'image_data':'data:image/jpeg;base64,***'}]:
   with self.subTest(change=list(change)),self.assertRaises(DomainError):uploads.save('one',body()|change)
  for value in ['x',0,-1,100001]:
   with self.assertRaises(DomainError):uploads.listing('one',value)
 def test_safe_metadata_no_inline_image_or_other_owner(self):
  uploads.save('one',body(name='<script>alert(1)</script>.jpg'));text=json.dumps(uploads.listing('one'));self.assertNotIn('base64',text);self.assertNotIn('original',text);self.assertNotIn('owner',text)

if __name__=='__main__':unittest.main()
