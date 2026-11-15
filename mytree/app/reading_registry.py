"""Bounded, transient OCR receipts for explicit confirmation; never persisted."""
from collections import OrderedDict
import copy
import re
import threading
import time
import uuid


class ConfirmationError(ValueError):
    def __init__(self, message='请先核对并确认识别内容。', code='NEEDS_CONFIRMATION', status=409):
        super().__init__(message)
        self.code, self.status = code, status


def new_id():
    return uuid.uuid4().hex


class ReadingRegistry:
    def __init__(self, limit=128, lifetime=7200, clock=time.monotonic):
        self.limit, self.lifetime, self.clock = limit, lifetime, clock
        self._items = OrderedDict()
        self._pages = OrderedDict()
        self._page_requests = OrderedDict()
        self._acceptances = OrderedDict()
        self._lock = threading.RLock()

    def remember(self, student, reading):
        reading_id = reading.get('reading_id')
        if not isinstance(reading_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', reading_id):
            raise ValueError('识别编号格式不正确')
        with self._lock:
            self._items[reading_id] = (self.clock(), student, copy.deepcopy(reading))
            self._items.move_to_end(reading_id)
            while len(self._items) > self.limit:
                self._items.popitem(last=False)

    def get(self, student, reading_id):
        with self._lock:
            item = self._items.get(reading_id) if isinstance(reading_id, str) else None
            if item is None or item[1] != student or self.clock()-item[0] > self.lifetime:
                raise ConfirmationError('识别记录已过期，请保留预览并重新点击识别。', 'NOT_FOUND', 404)
            return copy.deepcopy(item[2])

    def page_request(self,student,request_id,digest,generation,page_index):
        with self._lock:
            batch_id=self._page_requests.get((student,request_id))
            if batch_id is None:return None
            page=self._page(student,batch_id)
            if (page['digest'],page['output']['client_generation'],page['output']['page_index'])!=(digest,generation,page_index):
                raise ConfirmationError('同一识别请求的图片或来源已变化。','CONFLICT',409)
            return copy.deepcopy(page['output'])

    def _page(self,student,batch_id,revision=None,allow_cancelled=False):
        page=self._pages.get(batch_id)
        if page is None or page['student']!=student:raise ConfirmationError('没有找到这次识别，请重新识别当前页。','NOT_FOUND',404)
        if self.clock()-page['at']>self.lifetime:raise ConfirmationError('识别缓存已过期，请重新识别当前页。','CONFLICT',409)
        if page.get('cancelled') and not allow_cancelled:raise ConfirmationError('这次整理已取消，请重新识别当前页。','CONFLICT',409)
        if revision is not None and page['output']['source_revision']!=revision:raise ConfirmationError('来源版本已变化，请重新识别。','CONFLICT',409)
        return page

    def remember_page(self,student,request_id,digest,output):
        with self._lock:
            self._pages[output['batch_id']]={'at':self.clock(),'student':student,'digest':digest,'output':copy.deepcopy(output),'cancelled':False}
            self._page_requests[(student,request_id)]=output['batch_id']
            while len(self._pages)>32:self._pages.popitem(last=False)
            while len(self._page_requests)>128:self._page_requests.popitem(last=False)

    def cancel_page(self,student,batch_id,revision):
        with self._lock:
            page=self._page(student,batch_id,revision,allow_cancelled=True);page['cancelled']=True
            from .source_images import images
            images.discard(student,batch_id)
        return {'ok':True}

    def invalidate_owner(self,student):
        with self._lock:
            for page in self._pages.values():
                if page['student']==student:page['cancelled']=True
        from .source_images import images
        images.discard(student)

    def resume_page(self,student,batch_id,revision):
        with self._lock:
            page=self._page(student,batch_id,revision,allow_cancelled=True);page['cancelled']=False
        return {'ok':True}

    def page_reading(self,student,batch_id,reading_id,revision):
        with self._lock:
            page=self._page(student,batch_id,revision)
            reading=next((item for item in page['output']['items'] if item['reading_id']==reading_id),None)
            if reading is None:raise ConfirmationError('这道题不属于当前页。','NOT_FOUND',404)
            return copy.deepcopy(reading)

    def accept_auto(self,student,batch_id,reading_id,revision):
        with self._lock:
            page=self._page(student,batch_id,revision)
            reading=next((item for item in page['output']['items'] if item['reading_id']==reading_id),None)
            if reading is None:raise ConfirmationError('这道题不属于当前页。','NOT_FOUND',404)
            mode='analysis' if reading['auto_ready'] and reading['readiness']=='ready' else 'lesson_only' if reading.get('lesson_ready') and reading['readiness']=='lesson_only' else None
            if mode is None:raise ConfirmationError('这道题还没读清，已先跳过，可重拍这题。','NEEDS_CONFIRMATION',409)
            source={'batch_id':batch_id,'item_id':reading['item_id'],'reading_id':reading_id,'source_revision':revision,
                    'acceptance':'auto','mode':mode,'visual_required':reading.get('visual_required',False),'policy_version':'page-auto-v2','page_index':page['output']['page_index']}
            token=new_id();self._acceptances[token]=(self.clock(),student,copy.deepcopy(reading),source)
            while len(self._acceptances)>512:self._acceptances.popitem(last=False)
            return token,copy.deepcopy(reading)

    def accepted(self,student,token):
        with self._lock:
            receipt=self._acceptances.get(token)
            if receipt is None or receipt[1]!=student:raise ConfirmationError('接收凭据无效。','NOT_FOUND',404)
            if self.clock()-receipt[0]>self.lifetime:raise ConfirmationError('接收凭据已过期。','CONFLICT',409)
            source=receipt[3]
            self._page(student,source['batch_id'],source['source_revision'])
            return {'legacy_compat':False,'reading':copy.deepcopy(receipt[2]),'source':copy.deepcopy(source)}

    def confirm(self, student, body, strict=False):
        metadata = body.get('recognition') or {}
        reading_id = metadata.get('reading_id') if isinstance(metadata, dict) else None
        confirmed = body.get('confirmed_reading_id')
        if not confirmed:
            if strict or reading_id:
                raise ConfirmationError()
            return {'legacy_compat': True, 'reading': None}
        if reading_id and confirmed != reading_id:
            raise ConfirmationError('确认编号与当前识别结果不一致，请重新核对。')
        reading = self.get(student, confirmed)
        if not reading.get('supported') or reading.get('multiple_questions'):
            raise ConfirmationError('请先框选一道完整题目，再识别并确认。', 'INVALID_INPUT', 400)
        return {'legacy_compat': False, 'reading': reading}


registry = ReadingRegistry()
