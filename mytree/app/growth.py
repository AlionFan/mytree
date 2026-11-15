"""Historical, deduplicated reference growth; current tree edits cannot undo it."""
from datetime import datetime,timedelta
import uuid

from . import contract,store
from .schedule import TZ,now


def period(week_start=None):
    instant=now().astimezone(TZ)
    start=datetime.fromisoformat(week_start).date() if week_start else instant.date()-timedelta(days=instant.weekday())
    if start.weekday()!=0:raise ValueError('周起始日期需要是星期一')
    return {'week_start':start.isoformat(),'week_end':(start+timedelta(days=6)).isoformat(),'timezone':'Asia/Shanghai'}


def record_relation(value,source,target):
    matches=[event for event in value['growth_events'] if event.get('kind')=='relations']
    if len(matches)>=20 or any(event.get('from')==source and event.get('to')==target for event in matches):return None
    event={'id':uuid.uuid4().hex,'kind':'relations','from':source,'to':target,'points':2,'at':now().isoformat(timespec='seconds')}
    value['growth_events'].append(event);return event['id']


def record_review(value,knowledge,fact_id,instant,answer_at=None):
    # A review nurtures an already unlocked knowledge card. Its first qualifying
    # return is at least three days after unlock, following ones three days apart.
    unlocked=[e for e in value['growth_events'] if e.get('kind')=='scale' and e.get('knowledge_id')==knowledge]
    if not unlocked:return None
    previous=[e for e in value['growth_events'] if e.get('kind')=='lushness' and e.get('knowledge_id')==knowledge]
    if len(previous)>=3:return None
    anchor=max(datetime.fromisoformat(e['at']) for e in previous or unlocked)
    actual=answer_at or instant
    if actual>instant or actual-anchor<timedelta(days=3):return None
    event={'id':uuid.uuid4().hex,'kind':'lushness','knowledge_id':knowledge,'fact_id':fact_id,
           'points':3,'at':instant.isoformat(timespec='seconds')}
    value['growth_events'].append(event);return event['id']


def get(student,params):
    contract.definition('GrowthGetInput',params)
    value=store.read(student);span=period(params.get('week_start'))
    components={'scale':0,'lushness':0,'relations':0};evidence={k:[] for k in components}
    seen=set();lush_counts={};weekly=0
    for event in value['growth_events']:
        kind=event.get('kind');knowledge=event.get('knowledge_id')
        key=(kind,knowledge) if kind=='scale' else (kind,event.get('fact_id')) if kind=='lushness' else (kind,event.get('from'),event.get('to'))
        if kind not in components or key in seen:continue
        if kind=='lushness' and lush_counts.get(knowledge,0)>=3:continue
        if kind=='relations' and len(evidence[kind])>=20:continue
        points={'scale':10,'lushness':3,'relations':2}[kind]
        seen.add(key);components[kind]+=points;evidence[kind].append(event['id'])
        if kind=='lushness':lush_counts[knowledge]=lush_counts.get(knowledge,0)+1
        if span['week_start']<=event['at'][:10]<=span['week_end']:weekly+=points
    return contract.definition('GrowthGetOutput',{'total':sum(components.values()),'components':components,
            'evidence':evidence,'period':span,'weekly_delta':weekly,'score_rule':'growth-v1-provisional'})


def leaderboard(student,params):
    contract.definition('LeaderboardGetInput',params)
    # No rank is fabricated for the anonymous local demonstration profile.
    return contract.definition('LeaderboardGetOutput',{'group_id':params['group_id'],
             'period':period(params.get('week_start')),'entries':[]})
