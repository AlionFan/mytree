"""Bounded owner/batch/revision-bound image memory; absolute 15-minute TTL."""
import base64
from collections import OrderedDict
import hashlib
import io
import re
import threading
import time
from PIL import Image
from .errors import DomainError

class SourceImages:
 def __init__(self,clock=time.monotonic,ttl=900,owner_bytes=8_000_000,total_bytes=24_000_000):
  self.clock,self.ttl,self.owner_bytes,self.total_bytes=clock,ttl,owner_bytes,total_bytes
  self.items=OrderedDict();self.lock=threading.RLock()
 def _purge(self):
  for key,row in list(self.items.items()):
   if self.clock()-row['at']>=self.ttl:del self.items[key]
 def put(self,owner,batch,revision,image):
  raw=base64.b64decode(image.split(',',1)[1],validate=True)
  if len(raw)>4_500_000:raise ValueError('原图过大，请降低分辨率重试。')
  with Image.open(io.BytesIO(raw)) as im:
   if im.width*im.height>6_000_000:raise ValueError('原图像素过大。')
  key=(owner,batch,revision)
  with self.lock:
   self._purge();self.items.pop(key,None)
   while sum(len(v['raw']) for k,v in self.items.items() if k[0]==owner)+len(raw)>self.owner_bytes:
    victim=next((k for k in self.items if k[0]==owner),None)
    if victim is None:raise ValueError('原图超出缓存限制。')
    del self.items[victim]
   while self.items and sum(len(v['raw']) for v in self.items.values())+len(raw)>self.total_bytes:self.items.popitem(last=False)
   if len(raw)>self.total_bytes:raise ValueError('原图超出缓存限制。')
   self.items[key]={'at':self.clock(),'raw':raw,'sha256':hashlib.sha256(raw).hexdigest()}
 def get(self,owner,source,reading):
  if reading.get('reading_id')!=source.get('reading_id'):raise DomainError('SOURCE_IMAGE_MISMATCH','题目图片来源不匹配。',409)
  key=(owner,source['batch_id'],source['source_revision'])
  with self.lock:
   self._purge();row=self.items.get(key)
   if row is None:raise DomainError('SOURCE_IMAGE_EXPIRED','原题图片已过期，请重新上传原图并识别这题。',409)
   raw=row['raw']
  # Use the full width to keep all A-D options, with vertical context margins.
  x,y,w,h=reading['region']
  with Image.open(io.BytesIO(raw)) as im:
   top=max(0,int((y-.035)*im.height));bottom=min(im.height,int((y+h+.035)*im.height))
   if bottom-top<120:top,bottom=0,im.height
   crop=im.crop((0,top,im.width,bottom));out=io.BytesIO();crop.save(out,format='JPEG',quality=92)
  return 'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode()
 def discard(self,owner,batch=None):
  with self.lock:
   for key in list(self.items):
    if key[0]==owner and (batch is None or key[1]==batch):del self.items[key]
 def stats(self):
  with self.lock:
   self._purge();return {'count':len(self.items),'bytes':sum(len(v['raw']) for v in self.items.values())}

images=SourceImages()

def for_diagnosis(owner,diagnosis_id):
 from . import store
 from .reading_registry import registry
 card=next((c for c in store.read(owner)['wrong_cards'].values() if c.get('diagnosis_id')==diagnosis_id),None)
 source=(card or {}).get('_source',{})
 visual_required=source.get('visual_required') or bool(re.search('美术字|如图|下图|图中|图示|立体|几何体|俯视图|统计图|折线图|条形图',(card or {}).get('problem',''))) or bool(source and ((card or {}).get('_analysis') or {}).get('diagram_description'))
 if not visual_required:return None
 if not all(source.get(key) for key in ('batch_id','reading_id','source_revision')):raise DomainError('SOURCE_IMAGE_EXPIRED','这道题需要原题图片，请重新上传原图并识别这题。',409)
 reading=registry.page_reading(owner,source['batch_id'],source['reading_id'],source['source_revision'])
 return images.get(owner,source,reading)
