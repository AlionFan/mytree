"""本机演示档案：诊断、练习、间隔复习和知识点；单进程加锁、原子写盘。"""
import copy
import json
import os
import tempfile
import threading
import uuid

from .knowledge import CAUSES, KP
from .curriculum import CHAPTERS
from .schedule import DEFAULT, next_slot, now, validate

_lock = threading.RLock()
_PATH = os.environ.get('MYTREE_PROFILE', os.path.join(os.path.dirname(__file__), '..', 'data', 'profiles.json'))


def _blank():
    return {'causes': {}, 'kp_wrong': {}, 'lit': [], 'history': 0, 'events': [],
            'availability': copy.deepcopy(DEFAULT), 'reviews': {}, 'exercises': {}, 'practice_correct': 0,
            'kp_correct': {}, 'requests': {}, 'feedback': [],
            'wrong_cards': {}, 'knowledge_cards': {}, 'quizzes': {}, 'quiz_answers': {},
            'hint_views': [], 'tree': {}, 'growth_events': [], 'reminders': {}}


def _load():
    try:
        with open(_PATH, encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}


def _save(data):
    directory = os.path.dirname(os.path.abspath(_PATH))
    os.makedirs(directory, exist_ok=True)
    # mkstemp starts private (0600); a failed write never replaces the prior file.
    fd, tmp = tempfile.mkstemp(prefix='.mytree-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, _PATH)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _student(data, student):
    p = data.setdefault(student, _blank())
    for key, default in _blank().items():
        p.setdefault(key, default)
    return p


def kps_used(problem):
    from sympy import Add, Poly, Symbol, expand, factor_list, fraction, gcd, together
    from .mathcheck import ParseError, domain_factors, parse
    out = set()
    try:
        p = parse(problem)
        if domain_factors(problem):
            out.update(['R1', 'R2'])
            return out
        x = Symbol('x')
        terms = Add.make_args(expand(p))
        if len(terms) > 1 and gcd(*terms) not in (1, -1):
            out.add('F1')
        factors = factor_list(p)[1]
        if any(k >= 2 and f.free_symbols for f, k in factors):
            out.add('F3')
        fl = [f for f, _ in factors if f.free_symbols]
        if len(terms) == 2 and len(fl) == 2 and all(f.free_symbols == {x} and Poly(f, x).degree() == 1 for f in fl):
            c1, c2 = (Poly(f, x).all_coeffs()[-1] for f in fl)
            if c1 == -c2:
                out.add('F2')
        if len(fl) >= 2:
            out.add('F4')
    except (ParseError, ValueError):
        pass
    return out


def _review(p, kp, cause):
    if not kp:
        return
    old = p['reviews'].get(kp, {})
    p['reviews'][kp] = dict(id=kp, kp=kp, cause=cause, title=KP[kp][0], stage=0,
                            due=next_slot(p['availability']), completed=old.get('completed', 0))


def record_into(p, analysis, problem=None, request_id=None, allow_mastery=True):
    if request_id and request_id in p['requests']:
        return {'id': p['requests'][request_id], 'duplicate': True}
    eid = uuid.uuid4().hex
    cause = analysis.get('cause')
    if analysis.get('status') != 'not_attempted':
        p['history'] += 1
    if analysis.get('status') in ('wrong_step', 'incomplete') and cause:
        p['causes'][cause] = p['causes'].get(cause, 0) + 1
        kp = (CAUSES.get(cause) or {}).get('kp')
        if not kp:
            kp = analysis.get('lesson_kp') or next(iter(sorted(kps_used(problem or ''))), 'F1')
        p['kp_wrong'][kp] = p['kp_wrong'].get(kp, 0) + 1
        _review(p, kp, cause)
    if allow_mastery and analysis.get('status') == 'correct' and problem:
        for kp in sorted(set(analysis.get('knowledge_ids') or kps_used(problem))):
            if kp not in p['lit']:
                p['lit'].append(kp)
    p['events'].append({'id': eid, 'at': now().isoformat(timespec='seconds'), 'type': 'lesson' if analysis.get('status')=='not_attempted' else 'diagnosis',
                        'problem': problem, 'status': analysis['status'], 'cause': cause,
                        'analysis': {key: analysis.get(key) for key in ('problem','steps','first_error','cause','status','domain','hints','target','target_latex','visual_svg','lesson_kp','problem_latex','diagram_description','question_type','knowledge_ids','verification','engine','assessment','prompt_version','study_mode')}})
    if p['events'][-1]['analysis'].get('study_mode') is None:p['events'][-1]['analysis'].pop('study_mode',None)
    p['events'] = p['events'][-150:]
    if request_id:
        p['requests'][request_id] = eid
        p['requests'] = dict(list(p['requests'].items())[-150:])
    return {'id': eid, 'duplicate': False}


def record(student, analysis, problem=None, request_id=None):
    with _lock:
        data = _load()
        value = _student(data, student)
        result = record_into(value, analysis, problem, request_id)
        if not result['duplicate']:
            _save(data)
        return result


def create_exercises(student, cause=None, diagnosis_id=None, review_id=None):
    from . import ai_extension, store, quiz
    from .errors import DomainError
    # Serialize only this account/source; model I/O never holds the profile lock.
    with store.request_lock((student, 'extension', review_id or diagnosis_id)):
        value=store.read(student)
        if review_id:
            saved=value['reviews'].get(review_id)
            if not saved:raise DomainError('NOT_FOUND','这项复习已经更新，请刷新计划。',404)
            kp=saved['kp'];cause=saved['cause']
            source=next((c for c in reversed(list(value['wrong_cards'].values())) if kp in c.get('knowledge_ids',[])),None)
        else:
            source=next((c for c in value['wrong_cards'].values() if c.get('diagnosis_id')==diagnosis_id),None)
            kp=next(iter((source or {}).get('knowledge_ids',[])),None)
        if not source or not kp:raise DomainError('NOT_FOUND','请先核对并保存原题，再开始巩固练习。',404)
        deadline=quiz._pause_until(value,kp,value.get('quiz_levels',{}).get(kp,{}))
        if deadline and now().date()<deadline:raise DomainError('CONFLICT',quiz._pause_reason(deadline),409)
        stamp=ai_extension.fingerprint(source);origin=review_id or diagnosis_id
        old=[e for e in value['exercises'].values() if e.get('origin')==origin and e.get('matching',{}).get('source_fingerprint')==stamp and e.get('matching',{}).get('version')==ai_extension.VERSION]
        if len(old)==3:return {'kp':kp,'items':[_public_exercise(e) for e in old]}
        items=ai_extension.generate(source)
        def commit(current):
            latest=current['wrong_cards'].get(source['id'])
            if not latest or ai_extension.fingerprint(latest)!=stamp:raise DomainError('CONFLICT','原题已修改，请按最新题目重新生成。',409)
            batch=uuid.uuid4().hex;result=[]
            for item in items:
                eid=uuid.uuid4().hex
                item.update(id=eid,kp=kp,cause=cause,group=batch,origin=origin,correct=False,attempts=0,review_id=review_id,source_card_id=source['id'])
                current['exercises'][eid]=item;result.append(_public_exercise(item))
            current['exercises']=dict(list(current['exercises'].items())[-120:])
            return {'kp':kp,'items':result}
        return store.update(student,commit)


def _public_exercise(e):
    return {key: e[key] for key in ('id','q','question','domain','correct','question_md','q_latex','grading','match_reason','answer_kind','verification') if key in e}


def submit_answer(student, exercise_id, answer):
    from .practice import check_answer
    from . import store, ai_extension
    from .errors import DomainError
    with store.request_lock((student,'extension-answer',exercise_id)):
        snapshot=store.read(student);candidate=snapshot['exercises'].get(exercise_id)
        if candidate and candidate.get('grading')=='ai_reference':
            source=snapshot['wrong_cards'].get(candidate.get('source_card_id'))
            if not source or ai_extension.fingerprint(source)!=candidate['matching']['source_fingerprint']:raise DomainError('CONFLICT','原题已更新，请重新生成练习。',409)
            if candidate.get('last_answer')==answer and candidate.get('last_feedback'):return {**candidate['last_feedback'],'duplicate':True}
            result=ai_extension.feedback(candidate,answer)
            def save(current):
                saved=current['exercises'].get(exercise_id)
                source=current['wrong_cards'].get(candidate.get('source_card_id'))
                if not saved or not source or ai_extension.fingerprint(source)!=candidate['matching']['source_fingerprint']:raise DomainError('CONFLICT','原题已更新，请重新生成练习。',409)
                saved.update(last_answer=answer,last_feedback=result,attempts=saved['attempts']+1,reviewed=True)
                return result
            return store.update(student,save)
    with _lock:
        data = _load()
        p = _student(data, student)
        item = p['exercises'].get(exercise_id)
        if not item:
            raise ValueError('没有找到这道练习，请重新开始练习')
        if item['correct']:
            return {'correct': True, 'message': '这道题已经做对，进度已保存。', 'duplicate': True}
        if item.get('grading'):
            from .junior_practice import check as junior_check
            correct,message=junior_check(item,answer)
        else:
            from .formulas import ascii_of
            try: normalized=ascii_of(answer)
            except ValueError:normalized=answer
            correct,message=check_answer(item['q'],normalized)
        item['attempts'] += 1
        if not correct:
            p['events'].append({'id': uuid.uuid4().hex, 'at': now().isoformat(timespec='seconds'),
                                'type': 'practice', 'problem': item['q'], 'status': 'wrong_step', 'cause': item['cause']})
            p['events'] = p['events'][-150:]
        if correct:
            item['correct'] = True
            p['practice_correct'] += 1
            kp = item['kp']
            p['kp_correct'][kp] = p['kp_correct'].get(kp, 0) + 1
            if kp not in p['lit']:
                p['lit'].append(kp)
            p['events'].append({'id': uuid.uuid4().hex, 'at': now().isoformat(timespec='seconds'),
                                'type': 'practice', 'problem': item['q'], 'status': 'correct', 'cause': item['cause']})
            p['events'] = p['events'][-150:]
            group_items = [e for e in p['exercises'].values() if e['group'] == item['group']]
            if sum(e['correct'] for e in group_items) >= 3:
                review = p['reviews'].get(kp)
                if not review:
                    _review(p, kp, item['cause'])
                    review=p['reviews'][kp]
                    review['completed']=1
                    review['last_group']=item['group']
                if review:
                    # 同一组练习只有第 3 题完成时推进一次；后续重复提交不推进。
                    if review.get('last_group') != item['group']:
                        review['completed'] += 1
                        review['stage'] = min(review['stage'] + 1, 2)
                        review['due'] = next_slot(p['availability'], review['stage'])
                        review['last_group'] = item['group']
                message += ' 这组已完成，下次复习也排好了。'
        _save(data)
        return {'correct': correct, 'message': message, 'duplicate': False}


def set_availability(student, availability):
    value = validate(availability)
    with _lock:
        data = _load()
        p = _student(data, student)
        p['availability'] = value
        for item in p['reviews'].values():
            item['due'] = next_slot(value, item['stage'])
        _save(data)
    return value


def get(student):
    with _lock:
        p = copy.deepcopy(_student(_load(), student))
    tree = [{'id': kid, 'name': name, 'chapter': chapter, 'lit': kid in p['lit'],
             'wrong': p['kp_wrong'].get(kid, 0), 'correct': p['kp_correct'].get(kid, 0), 'pre': pre}
            for kid, (name, chapter, pre) in KP.items()]
    reviews = sorted(p['reviews'].values(), key=lambda item: item['due'])
    from . import ai_extension
    pending=[]
    for e in p['exercises'].values():
        if e['correct'] or e.get('reviewed'):continue
        if e.get('grading')=='ai_reference':
            source=p['wrong_cards'].get(e.get('source_card_id'))
            if not source or ai_extension.fingerprint(source)!=e['matching']['source_fingerprint']:continue
        pending.append(_public_exercise(e))
    return {'history': p['history'], 'causes': p['causes'], 'tree': tree, 'reviews': reviews,
            'availability': p['availability'], 'practice_correct': p['practice_correct'],
            'recent': [{k:v for k,v in e.items() if k!='analysis'} for e in reversed(p['events'][-10:])], 'pending': pending, 'chapters': CHAPTERS, 'feedback_count':len(p['feedback']), 'timezone': 'Asia/Shanghai'}


def diagnosis_for(student, diagnosis_id):
    with _lock:
        p = _student(_load(), student)
        event = next((e for e in p['events'] if e['id'] == diagnosis_id and e['type'] in ('diagnosis','lesson')), None)
        if not event or not event.get('analysis'):
            card=next((card for card in p['wrong_cards'].values() if card.get('diagnosis_id')==diagnosis_id and card.get('_analysis')),None)
            if card:return copy.deepcopy(card['_analysis'])
            raise ValueError('这道题的讲解上下文已更新，请重新检查题目。')
        return copy.deepcopy(event['analysis'])


def add_feedback(student,diagnosis_id,rating,issue=''):
    if rating not in ('understood','confusing','incorrect'):
        raise ValueError('反馈类型不正确')
    analysis=diagnosis_for(student,diagnosis_id)
    with _lock:
        data=_load();p=_student(data,student)
        record={'id':uuid.uuid4().hex,'diagnosis_id':diagnosis_id,'rating':rating,'issue':str(issue)[:500],
                'prompt_version':analysis.get('prompt_version','algebra-v1'),'knowledge_ids':analysis.get('knowledge_ids',[]),
                'at':now().isoformat(timespec='seconds'),'review_status':'unreviewed'}
        p['feedback'].append(record);p['feedback']=p['feedback'][-300:];_save(data)
        return {'ok':True,'message':'已记录理解反馈。系统会据此调整讲解方式；数学结论仍需独立核对。'}


def feedback_summary(student):
    with _lock:
        records=_student(_load(),student)['feedback'][-15:]
    return {'confusing':sum(r['rating']=='confusing' for r in records),'understood':sum(r['rating']=='understood' for r in records),
            'instruction':'如孩子仍不理解，先用一个具体例子，缩短讲解，一次只问一个问题。'}
