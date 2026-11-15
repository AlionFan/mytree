"""Wrong-card persistence and child-authored notes; no knowledge-card creation."""
import copy
import uuid

from . import contract, junior, profile, store
from .errors import DomainError
from .knowledge import KP
from .reading_registry import registry as readings
from .schedule import now


_ANALYSIS = ('kind', 'problem', 'problem_latex', 'target', 'target_latex', 'steps',
             'first_error', 'cause', 'status', 'prev', 'cur', 'evidence', 'hints',
             'h3_leaks', 'visual_svg', 'card', 'domain', 'lesson_kp', 'question_type',
             'knowledge_ids', 'verification', 'engine', 'assessment',
             'diagram_description', 'prompt_version','study_mode')
_WRONG = ('id', 'type', 'problem', 'student_steps', 'knowledge_ids', 'diagnosis_id',
          'verification', 'learner_note', 'revision', 'study_status')
_KNOWLEDGE = ('id', 'type', 'knowledge_id', 'title', 'source_wrong_card_ids', 'rule',
              'rule_source', 'verification', 'learner_note', 'status', 'revision', 'unlock_evidence')


def verification(analysis):
    check = analysis.get('verification') or {}
    level = check.get('level') or check.get('status')
    if level not in ('verified', 'ai_review', 'unavailable'):
        level = 'verified' if analysis.get('engine') == 'algebra' else 'ai_review'
    return {'level': level, 'label': check.get('label') or 'AI 分析，尚待核对'}


def public_analysis(analysis):
    result = {key: copy.deepcopy(analysis[key]) for key in _ANALYSIS if key in analysis}
    result['hints'] = [junior.clean_teaching_meta(text) for text in result.get('hints', [])[:2]]
    result['hint_levels_available'] = 3
    return result


def public_card(card):
    fields = _WRONG if card['type'] in ('wrong','lesson') else _KNOWLEDGE
    result = {key: copy.deepcopy(card[key]) for key in fields if key in card}
    if card['type'] in ('wrong','lesson'):
        result.update(revision=card['_revision'],study_status=card['_study_status'])
    return result


def study(student, body, request_id, strict=True, acceptance_token=None):
    from . import billing, auth
    receipt = readings.accepted(student,acceptance_token) if acceptance_token else readings.confirm(student,body,strict=strict)
    reading=receipt.get('reading') or {}
    if auth.enabled():
        # Manual entry is also a new question; changing transport cannot bypass limits.
        source=receipt.get('source') or {}
        identity=('source:'+source['batch_id']+':'+reading['reading_id']) if source else ('reading:'+reading['reading_id']) if reading.get('reading_id') else 'manual:'+request_id
        canonical=__import__('hashlib').sha256(identity.encode()).hexdigest()
        with billing.successful_use(student,'questions',identity) as job:
            return _study_impl(student,body,canonical,strict,acceptance_token,billing_key=job)
    return _study_impl(student,body,request_id,strict,acceptance_token)


def _study_impl(student, body, request_id, strict=True, acceptance_token=None, billing_key=None):
    # Confirmation does not commit any profile data and is checked before AI calls.
    receipt = readings.accepted(student,acceptance_token) if acceptance_token else readings.confirm(student, body, strict=strict)
    if acceptance_token:
        source=receipt['reading']
        body={'problem':source['problem'],'problem_latex':source.get('problem_latex',''),'steps':copy.deepcopy(source['steps'])}
    actual = {**body, 'recognition': receipt['reading']} if receipt['reading'] is not None else body
    mode=(receipt.get('source') or {}).get('mode','analysis')
    original_steps=copy.deepcopy(body.get('steps',[]))
    if mode=='lesson_only':actual={**actual,'steps':[],'_study_mode':'lesson_only'}

    def prepare():
        if acceptance_token:
            live=readings.accepted(student,acceptance_token)
            if live['source'].get('visual_required'):
                from .source_images import images
                actual['_source_image']=images.get(student,live['source'],live['reading'])
        result = junior.study(actual)
        if acceptance_token:
            live=readings.accepted(student,acceptance_token)
            if live['source'].get('visual_required'):images.get(student,live['source'],live['reading'])
        if not result.get('ok'):
            raise DomainError('UNSUPPORTED', result.get('message') or '这道题暂时无法核对。', 422)
        analysis=result['analysis']
        if acceptance_token and verification(analysis)['level']!='verified':
            analysis['status']='ai_review' if analysis.get('steps') else 'not_attempted'
            analysis['cause']=None;analysis['first_error']=None
            analysis['assessment']='这部分推理尚不能独立核验，先看思路，不据此判错。'
            for row in analysis.get('steps',[]):row['ok']=None
        if mode=='lesson_only':
            analysis.update(status='not_attempted',cause=None,first_error=None,steps=[],assessment='',study_mode='lesson_only',verification={'level':'ai_review','label':'原题讲解'})
        return analysis

    def commit(value, analysis):
        if acceptance_token:readings.accepted(student,acceptance_token)
        record = profile.record_into(value, analysis, analysis['problem'],allow_mastery=not bool(acceptance_token))
        identifiers = analysis.get('knowledge_ids') or [analysis.get('lesson_kp') or (analysis.get('card') or {}).get('kp')]
        identifiers = [key for key in identifiers if key in KP]
        card = {'id': uuid.uuid4().hex, 'type': 'lesson' if mode=='lesson_only' else 'wrong', 'problem': body['problem'],
                'student_steps': original_steps,
                'knowledge_ids': identifiers, 'diagnosis_id': record['id'],
                'verification': verification(analysis), 'learner_note': '',
                '_revision': 0, '_study_status': analysis['status'],
                '_created_at': now().isoformat(timespec='seconds'), '_analysis': copy.deepcopy(analysis),
                '_reading_id': (receipt['reading'] or {}).get('reading_id'),
                '_reading_inferred': bool((receipt['reading'] or {}).get('inferred'))}
        if billing_key:card['_billing_key']=billing_key
        if receipt.get('source'):card['_source']=copy.deepcopy(receipt['source'])
        value['wrong_cards'][card['id']] = card
        output = {'analysis': public_analysis(analysis), 'diagnosis_id': record['id'],
                  'duplicate': False, 'wrong_card': public_card(card)}
        return {'status': 'ok', 'verification': card['verification'], 'output': output,
                'effects': [{'kind':'record_diagnosis','id':record['id'],'idempotent_replay':False},
                            {'kind':'create_wrong_card','id':card['id'],'idempotent_replay':False}]}

    source=actual.get('recognition') or {}
    intent={key:body.get(key) for key in ('problem','steps','confirmed_reading_id')}
    intent['study_mode']=mode
    intent['problem_latex']=body.get('problem_latex') or source.get('problem_latex','')
    intent['recognition']={key:source[key] for key in ('question_type','topic_id','diagram_description') if key in source}
    return store.command(student, 'study', request_id, intent, prepare, commit,
                         validate=lambda result: contract.definition('StudyOutput', result['output']))


def list_cards(student, params):
    contract.definition('CardListInput', params)
    value = store.read(student)
    key = 'wrong_cards' if params['type'] == 'wrong' else 'knowledge_cards'
    items = list(reversed(list(value[key].values())))
    if params.get('status'):
        items = [card for card in items if card.get('status', 'active') == params['status']]
    cursor = params.get('cursor', '0')
    if not cursor.isdigit() or len(cursor) > 7:
        raise DomainError('INVALID_INPUT', '卡片页码无效，请重新打开列表。')
    start = int(cursor)
    count = params.get('limit', 20)
    selected = items[start:start+count]
    result = {'items': [public_card(card) for card in selected],
              'next_cursor': str(start+count) if start+count < len(items) else None}
    return contract.definition('CardListOutput', result)


def edit(student, params, request_id):
    contract.definition('CardEditInput', params)

    def commit(value, _):
        card = value['wrong_cards'].get(params['card_id']) or value['knowledge_cards'].get(params['card_id'])
        if card is None:
            raise DomainError('NOT_FOUND', '没有找到这张卡片，请刷新列表。', 404)
        revision_key = '_revision' if card['type'] in ('wrong','lesson') else 'revision'
        if card.get(revision_key, 0) != params['expected_revision']:
            raise DomainError('CONFLICT', '这张卡片已经更新，请刷新后再修改。', 409,
                              current_revision=card.get(revision_key,0))
        if card['type'] in ('wrong','lesson') and any(key in params for key in ('title','status')):
            raise DomainError('INVALID_INPUT', '错题卡的系统内容保留原样，可以补充自己的笔记。')
        for field in ('title', 'learner_note', 'status'):
            if field in params:
                card[field] = params[field]
        card[revision_key] = card.get(revision_key,0)+1
        output = {'card':public_card(card), 'revision':card[revision_key]}
        return {'status':'ok', 'verification':card['verification'], 'output':output,
                'effects':[{'kind':'edit_card','id':card['id'],'idempotent_replay':False}]}

    return store.command(student,'card.edit',request_id,params,lambda:None,commit,
                         validate=lambda result:contract.definition('CardEditOutput',result['output']))


def hint(student, params):
    contract.definition('HintRequest', params)
    if params.get('quiz_id') or params.get('exercise_id'):
        from . import quiz
        return quiz.hint(student,params)
    analysis = profile.diagnosis_for(student,params['diagnosis_id'])
    hints = analysis.get('hints') or []
    if len(hints) < params['level']:
        from .pipeline import prepare_lesson
        prepared = prepare_lesson(analysis['problem'])
        hints = prepared.get('analysis',{}).get('hints',[])
    if len(hints) < params['level']:
        raise DomainError('UNSUPPORTED','这一级提示暂时没有准备好，请稍后再试。',422)
    recorded = store.record_hint_view(student,params['diagnosis_id'],params['level'])
    output = {'level':params['level'], 'text':junior.clean_teaching_meta(hints[params['level']-1]),
              'max_hint_level_recorded':recorded['max_hint_level'], 'scope':'diagnosis'}
    return contract.definition('HintResponse',output)
