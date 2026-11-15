"""Due tasks and shared reminder state; notifications belong to the client."""
from datetime import datetime, timedelta
import hashlib
import uuid

from . import contract, store, growth
from .errors import DomainError
from .knowledge import KP
from .schedule import TZ, now, next_slot

WINDOW_MINUTES = 30  # Initial polling window, explicitly proposed to Claude.
_RECALL = {
    'F1':'先不看解法，说说你会怎样找出每一项共有的因式。',
    'F2':'先不看解法，说说平方差公式适合什么样的两项式。',
    'F3':'先不看解法，说说怎样从三项式判断它是否符合完全平方公式。',
    'R1':'先不看解法，说说约分时为什么要把分子、分母看成因式的乘积。',
}


def _instant():
    return now().astimezone(TZ)


def _key(student, date):
    return hashlib.sha256(('review:'+student+':'+date).encode()).hexdigest()[:40]


def _due_items(value, instant, student=None):
    from . import personal_review
    pending=[]
    for identity, item in value['reviews'].items():
        try:
            due=datetime.fromisoformat(item['due'])
            if due.tzinfo is None:due=due.replace(tzinfo=TZ)
        except (ValueError,TypeError,KeyError):
            continue
        if due>instant:continue
        knowledge=item.get('kp',identity)
        if knowledge not in KP:continue
        from . import quiz
        deadline=quiz._pause_until(value,knowledge,value.get('quiz_levels',{}).get(knowledge,{}))
        if deadline is not None and instant.date()<deadline:continue
        sources=[card['id'] for card in value['wrong_cards'].values() if knowledge in card['knowledge_ids']]
        # An old scheduled review is itself a saved fact, even before cards existed.
        based_on=sources[:100] or [item.get('id',identity)]
        from . import personal_review
        context=personal_review.live_reason({**value,'_memory_owner':student},item) if student else None
        if context:
            based_on=context['based_on']
        pending.append({'id':item.get('id',identity),'knowledge_id':knowledge,'due_at':due.isoformat(),
                        'reason':context['reason'] if context else '之前为'+KP[knowledge][0]+'安排了复习，今天可以回来看看。',
                        'based_on':based_on,'task':{'kind':'recall','prompt':_RECALL.get(knowledge,
                            '先不看解法，用自己的话说说“'+KP[knowledge][0]+'”里最想记住的一条规则。')}})
    pending.sort(key=lambda item:(item['due_at'],item['id']))
    # A deterministic daily rotation keeps today's read-only query side-effect free
    # while ensuring a fourth due item becomes visible on the next day.
    if len(pending)>3:
        offset=(instant.date().toordinal()*3)%len(pending)
        pending=pending[offset:]+pending[:offset]
    priorities={item.get('id',key):(personal_review.live_reason({**value,'_memory_owner':student},item) or {}).get('score',0) for key,item in value['reviews'].items()} if student else {}
    pending.sort(key=lambda item:-(priorities.get(item['id'],0)+max(0,(instant-datetime.fromisoformat(item['due_at'])).days)))
    return pending[:3]


def today(student):
    value=store.read(student);instant=_instant();date=instant.date().isoformat()
    items=_due_items(value,instant,student)
    hour,minute=map(int,value['availability']['time'].split(':'))
    start=instant.replace(hour=hour,minute=minute,second=0,microsecond=0)
    within=instant.isoweekday() in value['availability']['days'] and start<=instant<start+timedelta(minutes=WINDOW_MINUTES)
    state=value['reminders'].get(date,{})
    cadence=value['reminders'].get('_cadence',{})
    reduced=False
    if cadence.get('since'):
        anchor=datetime.fromisoformat(cadence['since']).date()
        reduced=(instant.date()-anchor).days%2==1
    allowed=bool(items and within and not state.get('acknowledged') and not state.get('snoozed') and not reduced)
    names=[KP[item['knowledge_id']][0]+'的一个回忆问题' for item in items]
    message='今天有 '+str(len(items))+' 个小任务：'+'；'.join(names)+'。有空时可以从一项开始。' if items else '今天暂时没有到期的小任务。'
    return contract.definition('ReviewTodayOutput',{'date':date,'timezone':'Asia/Shanghai','items':items,
                'reminder_allowed':allowed,'reminder_key':_key(student,date),'message':message[:800]})


def reminder_action(student, reminder_key, action):
    instant=_instant();date=instant.date().isoformat()
    if reminder_key!=_key(student,date):
        raise DomainError('INVALID_INPUT','提醒编号已过期，请重新读取今日任务。')
    field='acknowledged' if action=='ack' else 'snoozed'

    def change(value):
        state=value['reminders'].setdefault(date,{})
        duplicate=bool(state.get(field))
        state[field]=True
        state[field+'_at']=state.get(field+'_at') or instant.isoformat(timespec='seconds')
        if action=='snooze':
            streak=0
            for distance in range(3):
                previous=(instant.date()-timedelta(days=distance)).isoformat()
                if value['reminders'].get(previous,{}).get('snoozed'):streak+=1
                else:break
            if streak>=3:value['reminders'].setdefault('_cadence',{'since':date,'interval_days':2})
        output={'ok':True,'reminder_key':reminder_key,'duplicate':duplicate,'reminder_allowed':False}
        return contract.definition('ReviewAckResponse' if action=='ack' else 'ReviewSnoozeResponse',output)

    return store.update(student,change)


def complete(student, params, request_id):
    contract.definition('ReviewCompleteInput',params)

    def commit(value,_):
        scheduled=value['reviews'].get(params['review_id'])
        if scheduled is None:raise DomainError('NOT_FOUND','没有找到这项复习，请刷新计划。',404)
        knowledge=scheduled.get('kp',params['review_id'])
        evidence_ids=sorted(set(params['evidence_ids']))
        evidence=[value['quiz_answers'].get(identity) for identity in evidence_ids]
        if any(item is None for item in evidence):raise DomainError('NOT_FOUND','答题依据不存在，请先完成服务端保存的练习。',404)
        if any(item.get('knowledge_id')!=knowledge for item in evidence):
            raise DomainError('INVALID_INPUT','答题依据与这项复习的知识点不一致。')
        submission=params['review_id']+':'+','.join(evidence_ids)
        previous=value.setdefault('review_submissions',{}).get(submission)
        if previous is not None:
            return {'status':'ok','verification':{'level':'verified' if previous['completed'] else 'unavailable','label':'来自保存的复习记录'},
                    'output':previous,'effects':[]}
        used=value.setdefault('review_used_evidence',{})
        eligible=[identity for identity,item in zip(evidence_ids,evidence)
                  if item.get('correct') is True and item.get('verification',{}).get('level')=='verified' and identity not in used]
        completed=bool(eligible)
        fact_id=uuid.uuid4().hex;instant=_instant()
        value.setdefault('profile_facts',{})[fact_id]={'id':fact_id,'kind':'review','knowledge_id':knowledge,
            'review_id':params['review_id'],'evidence_ids':evidence_ids,'completed':completed,
            'at':instant.isoformat(timespec='seconds'),'self_report':params.get('self_report')}
        if completed:
            for identity in eligible:used[identity]=fact_id
            scheduled['completed']=scheduled.get('completed',0)+1
            scheduled['stage']=min(scheduled.get('stage',0)+1,2)
            scheduled['due']=next_slot(value['availability'],scheduled['stage'],after=instant)
        try:
            answer_at=max(datetime.fromisoformat(value['quiz_answers'][identity]['at']) for identity in eligible) if completed else None
            growth_id=growth.record_review(value,knowledge,fact_id,instant,answer_at) if completed else None
        except (KeyError,ValueError,TypeError):growth_id=None
        output={'review_id':params['review_id'],'completed':completed,'profile_fact_ids':[fact_id],
                'knowledge_card_eligible':False,'knowledge_id':knowledge}
        value['review_submissions'][submission]=output
        return {'status':'ok','verification':{'level':'verified' if completed else 'unavailable',
                 'label':'答题记录支持本次有效复习' if completed else '本次只记录复习事实，尚无可核验的正确作答'},
                'output':output,'effects':[{'kind':'update_profile','id':fact_id,'idempotent_replay':False}]+
                ([{'kind':'update_growth','id':growth_id,'idempotent_replay':False}] if growth_id else [])}

    return store.command(student,'review.complete',request_id,params,lambda:None,commit,
                         validate=lambda result:contract.definition('ReviewCompleteOutput',result['output']))
