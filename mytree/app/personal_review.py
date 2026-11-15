"""Explainable consolidation plans from recalled, verified learning evidence."""
from datetime import datetime, timedelta
import json
from . import store, teaching_memory, mem0_adapter
from .knowledge import KP
from .schedule import TZ, now, next_slot


def _facts(records):
    for record in records:
        if record['type']!='fact':continue
        try:fact=json.loads(record['content'])
        except (ValueError,TypeError):continue
        yield record,fact


def recommendations(records, instant):
    grouped={}
    for record,fact in _facts(records):
        kp=record['knowledge_id']
        if kp not in KP:continue
        event=fact.get('event')
        kind=None
        if event=='quiz_answer' and fact.get('verification',{}).get('level')=='verified':
            kind='wrong' if fact.get('correct') is False else 'independent' if fact.get('correct') is True and fact.get('max_hint_level')==0 else 'hinted' if fact.get('correct') is True else None
        elif not event and fact.get('study_mode')!='lesson_only' and fact.get('verification',{}).get('level')=='verified' and fact.get('study_status') in ('wrong_step','incomplete'):
            kind='wrong'
        if not kind:continue
        at=fact.get('at') or fact.get('source_created_at') or ''
        grouped.setdefault(kp,[]).append((str(at),record,kind))
    result=[]
    for kp,events in grouped.items():
        events.sort(key=lambda x:(x[0],x[1]['id']))
        recent=events[-12:];weights={'wrong':3,'hinted':1,'independent':-2}
        # Evidence of later recovery reduces older mistakes; a later mistake can
        # raise priority again. These weights are review heuristics, not mastery.
        score=0
        for _,_,kind in recent:score=max(0,score+weights[kind])
        if score<=0:continue
        counts={kind:sum(e[2]==kind for e in recent) for kind in weights}
        parts=[]
        if counts['wrong']:parts.append(str(counts['wrong'])+' 次核验作答还需巩固')
        if counts['hinted']:parts.append(str(counts['hinted'])+' 次答对时使用了提示')
        if counts['independent']:parts.append('后来已有 '+str(counts['independent'])+' 次无提示答对')
        result.append({'knowledge_id':kp,'score':score,'reason':KP[kp][0]+'：'+'；'.join(parts)+'，先安排一次巩固。',
                       'based_on':list(dict.fromkeys(source for _,r,_ in recent for source in r['source_event_ids'])),
                       'memory_ids':[r['id'] for _,r,_ in recent],
                       'latest_practice_at':recent[-1][0]})
    return sorted(result,key=lambda x:(-x['score'],x['knowledge_id']))


def arrange(owner):
    snapshot=teaching_memory.snapshot(owner)
    recalled=mem0_adapter.sync_search(owner,snapshot['records'],'孩子历史错题、使用提示、独立答对与薄弱知识点，安排下一次巩固复习。',limit=100)
    # Recheck against the live ledger before committing a proposal; a revoked or
    # corrected source cannot survive merely because a vector result was cached.
    live=teaching_memory.snapshot(owner)['records']
    current={r['id']:(r['version'],r['content']) for r in live}
    safe=[r for r in recalled['records'] if current.get(r['id'])==(r['version'],r['content'])]
    candidate_topics={r['knowledge_id'] for r in (safe if recalled['engine']=='mem0' else live) if r['type']=='fact'}
    # Similarity chooses topics, never which successes count toward recovery.
    # Score each candidate using its complete live, bounded chronological history.
    candidates=recommendations([r for r in live if r['knowledge_id'] in candidate_topics],now())
    instant=now().astimezone(TZ)
    def commit(value):
        availability=value['availability'];hour,minute=map(int,availability['time'].split(':'))
        slot=datetime.fromisoformat(next_slot(availability,0,after=instant))
        arranged=[]
        for proposal in candidates:
            kp=proposal['knowledge_id'];existing=value['reviews'].get(kp)
            from . import quiz, matching
            from .errors import DomainError
            source=None
            for card in value['wrong_cards'].values():
                if kp not in card.get('knowledge_ids',[]):continue
                try:
                    matching.classify(card,kp)
                    source=card;break
                except (DomainError,ValueError):continue
            if source is None or kp not in quiz.SUPPORTED|quiz.COMPOSITE_SUPPORTED:continue
            state=value.get('quiz_levels',{}).get(kp,{})
            deadline=quiz._pause_until(value,kp,state)
            if deadline is not None and instant.date()<deadline:continue
            proposal['based_on']=list(dict.fromkeys(proposal['based_on']+[source['id']]))
            proposal['memory_versions']={key:current[key][0] for key in proposal['memory_ids']}

            # Existing spaced-repetition due dates, pauses and completion survive.
            # Personalization changes order/reasons; it never resets a completed review.
            if not existing:
                day=slot
                while sum(1 for r in value['reviews'].values() if str(r.get('due',''))[:10]==day.date().isoformat())>=3:
                    day=(day+timedelta(days=1)).replace(hour=hour,minute=minute)
                    while day.isoweekday() not in availability['days']:day+=timedelta(days=1)
                existing={'id':kp,'kp':kp,'title':KP[kp][0],'stage':0,'completed':0,'due':day.isoformat()}
                value['reviews'][kp]=existing
            existing['personalization']={**proposal,'arranged_at':instant.isoformat(),'engine':recalled['engine']}
            arranged.append({**proposal,'review_id':existing['id'],'due_at':existing['due']})
        active={p['knowledge_id'] for p in arranged}
        for item in value['reviews'].values():
            if item.get('kp') not in active:item.pop('personalization',None)
        value['personal_review']={'updated_at':instant.isoformat(),'engine':recalled['engine'],'status':recalled['status']}
        return {'items':arranged,'memory':value['personal_review'],'message':recalled.get('message') or ('已根据历史作答更新复习顺序。' if arranged else '目前没有需要新增巩固的核验记录，可以先完成学习桌上的任务。')}
    return store.update(owner,commit)


def live_reason(value, item):
    """Avoid displaying deleted evidence from a previously arranged plan."""
    proposal=item.get('personalization')
    if not proposal:return None
    owner=value.get('_memory_owner')
    if not owner:return None
    records={r['id']:r for r in teaching_memory.snapshot(owner)['records']}
    for key in proposal['memory_ids']:
        if key not in records or records[key]['version']!=proposal.get('memory_versions',{}).get(key):return None
    sources=set(value['wrong_cards'])|set(value['quiz_answers'])|set(value.get('profile_facts',{}))|{e['id'] for e in value['events']}
    if not set(proposal['based_on']).issubset(sources):return None
    return proposal
