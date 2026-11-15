"""Server-owned three-question qualification groups, immutable answer facts.

Only the independently checkable template families are eligible. A quiz item is
never an AI claim: the server verifies its expected answer before saving it.
"""
import copy
from datetime import date,datetime,timedelta
import random
import uuid

import sympy as sp

from . import cards, contract, junior_practice, practice, store, matching
from .errors import DomainError
from .formulas import parse_math
from .knowledge import KP, KNOWLEDGE_CARDS
from .schedule import TZ,now

SUPPORTED = set(practice.TEMPLATES) | {'R2','R3','N1','N2','N3','N4','E1','E2','E3','E4','I1','I2','P1'}
COMPOSITE_SUPPORTED = {'U4'}
PUBLIC_ITEM = ('id','prompt','difficulty_level','difficulty_features','is_transfer','verification')
OPTIONAL_ITEM = ('answer_kind',)
RECORD = ('exercise_id','evidence_id','correct','is_transfer','max_hint_level','verification')
RULES = {
 'P1':'必然事件一定发生，不可能事件一定不发生，两类都属于确定事件；随机事件可能发生也可能不发生。',
 'U4':'先把条件合并成自变量的区间，再考察二次式的顶点、端点和端点能否取到。',
 'N1':'先处理括号，再乘除，后加减；每一步都核对正负号。',
 'N2':r'先化简二次根式，再合并同类根式；\(\sqrt{a^2}=|a|\)。',
 'N3':r'同底数幂相乘指数相加，相除指数相减（底数非零）；幂的乘方指数相乘。',
 'N4':r'科学计数法写作 \(a\times 10^n\)，其中 \(1\leq |a|<10\)。',
 'E1':'方程两边做同一种合法变形，最后把得到的解代回原方程检查。',
 'E2':'用代入或加减消去一个未知数，求出后代回两条方程核对。',
 'E3':'化为一般形式后选择合适方法求根；应用题还要依据实际条件筛选根。',
 'E4':'先记录使分母非零的条件，再求解；最后代回原方程验根。',
 'I1':'不等式两边同乘或同除负数，不等号方向改变。',
 'I2':'分别解出每个不等式，再取各个解集的交集。',
}


def _math(value):
    return sp.latex(parse_math(value,evaluate=False))


def _algebra(q,a,prompt=None):
    return {'q':q,'a':a,'answer_latex':sp.latex(sp.factor(parse_math(a))),'grading':'algebra',
            'prompt':prompt or r'分解因式或化简：\('+_math(q)+r'\)。'}


def _junior(prompt, expected, kind='number'):
    latex=(r'\left('+','.join(sp.latex(x) for x in expected)+r'\right)') if kind=='point' else sp.latex(expected)
    return {'prompt':prompt,'q':prompt,'answer_latex':latex,'grading':kind,
            'expected':list(map(str,expected)) if kind=='point' else str(expected)}


def _transfer(knowledge,rng,level):
    a=rng.randint(2,6)+min(level,4);b=rng.randint(2,5);x=sp.Symbol('x')
    if knowledge in ('N3','N4'):a=min(a,7)
    if knowledge=='R2':
        q=f'((x^2-{a*a})*(x+{b}*y))/((x+{a})*(x+{b}*y))'
        return _algebra(q,f'x-{a}',r'化简 \('+_math(q)+r'\)。这里有两个公因式，需要约到最简，并保留原分母非零的条件。'),['两个公因式','两变量与彻底约分']
    if knowledge=='R3':
        q=f'({a}*y-2*x)/(4*x^2-{a*a}*y^2)'
        return _algebra(q,f'-1/(2*x+{a}*y)',r'化简 \('+_math(q)+r'\)。先分解分母，再统一因式的方向，保留原分母非零的条件。'),['两变量公式','因式方向与分式符号']
    if knowledge.startswith(('F','R')):
        if knowledge=='F1':q=f'({2*a}*x^2+{2*a*b}*x)/({a}*x)';ans=f'2*(x+{b})';side=f'{a}x';bound='x>0'
        elif knowledge=='F3':q=f'(4*x^2+{4*a}*x+{a*a})/(2*x+{a})';ans=f'2*x+{a}';side=f'2x+{a}';bound='x>0'
        elif knowledge=='F4':q=f'(x^4-{a**4})/(x^2+{a*a})';ans=f'(x+{a})*(x-{a})';side=f'x^2+{a*a}';bound=f'x>{a}'
        elif knowledge=='F5':q=f'({a}*(x-{b})-{b}*({b}-x))/(x-{b})';ans=str(a+b);side=f'x-{b}';bound=f'x>{b}'
        else:q=f'(4*x^2-{a*a})/(2*x+{a})';ans=f'2*x-{a}';side=f'2x+{a}';bound=f'x>{a}'
        area=q.split('/')[0][1:-1]
        prompt=r'一块长方形的面积是 \('+_math(area)+r'\)，一边长为 \('+side+r'\)，且 \('+bound+r'\)。先用公式分解，再求另一边长。'
        return _algebra(q,ans,prompt),['应用面积条件建式','公式与约分组合']
    if knowledge=='N1':return _junior(f'温度开始为 \\({a}\\) 度，先升高 \\({2*b}\\) 度，再降低 \\({b+1}\\) 度，最后是多少度？只填数值。',sp.Integer(a+b-1)),['生活条件建式','连续两次变化']
    if knowledge=='N2':return _junior(f'长方形两边长为 \\(\\sqrt{{{a*a}}}\\) 与 \\(\\sqrt{{{b*b}}}\\)，求周长。',sp.Integer(2*(a+b))),['根式化简','由边长求周长']
    if knowledge=='N3':return _junior(f'化简 \\(\\frac{{(x^{a})^2 x^{b}}}{{x^{a+1}}}\\)，其中 \\(x\\ne0\\)。',x**(a+b-1),'expression'),['幂的乘方','乘除组合']
    if knowledge=='N4':
        item=_junior(f'计算 \\((1.2\\times10^{a})\\times(3\\times10^{b})\\)，结果用科学计数法。',sp.Rational(36,10)*10**(a+b),'scientific')
        item['answer_latex']=r'3.6\times10^{'+str(a+b)+'}';return item,['乘法情境','调整科学计数法系数']
    if knowledge=='E1':return _junior(f'购买 \\({a}\\) 支同价铅笔，另付 \\({b}\\) 元包装费，共 \\({a*b+b}\\) 元。铅笔单价 \\(x\\) 是多少？用集合写出解。',sp.FiniteSet(b),'set'),['从价格条件列方程','实际未知量']
    if knowledge=='E2':return _junior(f'两种本子单价分别为 \\(x,y\\)。各买一本共 \\({a+b}\\) 元，买两本第一种和一本第二种共 \\({2*a+b}\\) 元，按 \\((x,y)\\) 写出单价。',(sp.Integer(a),sp.Integer(b)),'point'),['从两条价格条件建模','消元']
    if knowledge=='E3':return _junior(f'长方形宽为 \\(x\\)，长比宽多 \\({a}\\)，面积为 \\({b*(a+b)}\\)。求符合实际条件的宽，用集合写出解。',sp.FiniteSet(b),'set'),['从面积建立二次方程','按正长度筛根']
    if knowledge=='E4':return _junior(f'解方程 \\(\\frac{{{2*a}}}{{x-{b}}}=2\\)，用集合表示全部实数解并注意分母条件。',sp.FiniteSet(a+b),'set'),['分母含平移未知量','验根与限制']
    if knowledge=='I1':return _junior(f'同时满足 \\(-{a}x<-{a*b}\\) 和 \\(x\\le {a+b}\\) 的数有哪些？写出区间。',sp.Interval.Lopen(b,a+b),'set'),['负系数变号','与上界取交集']
    if knowledge=='I2':return _junior(f'求 \\(\\begin{{cases}}{a}x>{a*b}\\\\-{b}x\\ge -{b*(a+b)}\\end{{cases}}\\) 的解集，用区间表示。',sp.Interval.Lopen(b,a+b),'set'),['两个线性条件','负系数与交集']
    raise DomainError('UNSUPPORTED','这个题型的迁移检验尚待独立核验，目前可以整理错题并复习。',422)


def _check(item,answer):
    if item['grading']=='algebra':
        try:
            expression=parse_math(answer,evaluate=False)
            return practice.check_answer(item['q'],sp.sstr(expression).replace('**','^'))[0]
        except (ValueError,TypeError):return False
    return junior_practice.check(item,answer)[0]


def _group(knowledge,level,seed,match=None):
    if knowledge=='P1' and match is None:
        # Explicit reference catalogue only. start() still classifies the owned source.
        match={'family':'event-certainty','knowledge_id':'P1','source_id':None,
               'skills':['区分必然、不可能和随机事件'],
               'reason':'区分必然事件、不可能事件和随机事件。'}
    if match and match['family'] in ('expression-domain','perfect-square-polynomial','similar-area-perimeter','scientific-notation','event-certainty'):
        from .source_patterns import generate
        items=generate(match,level,seed)
        for item in items:
            if not _check(item,item['answer_latex']):matching.unsupported()
            item.update(id=uuid.uuid4().hex,verification={'level':'verified','label':'来源结构及答案已程序核验'},hint_max=0)
        return items
    if match and match['family']=='eliminate-quadratic-range':
        items=matching.range_items(match,level,seed)
        for item in items:
            if not _check(item,item['answer_latex']):matching.unsupported()
            item.update(id=uuid.uuid4().hex,verification={'level':'verified','label':'约束、区间端点与顶点已程序核验'},hint_max=0)
        return items
    rng=random.Random(seed);items=[]
    kind=knowledge if knowledge in practice.TEMPLATES else 'R1' if knowledge.startswith('R') else None
    if knowledge in ('R2','R3'):
        for a in rng.sample(range(2,9),2):
            q=f'(x^2-{a*a})/(x^2+{2*a}*x+{a*a})' if knowledge=='R2' else f'({a}-x)/(x^2-{a*a})'
            answer=f'(x-{a})/(x+{a})' if knowledge=='R2' else f'-1/(x+{a})'
            items.append(_algebra(q,answer))
    elif kind:
        generated=practice.generate(kind,2,seed=seed)
        for raw in generated:items.append(_algebra(raw['q'],raw['a']))
    else:
        for _ in range(20):
            raw=junior_practice.generate(knowledge,1)[0]
            if raw['q'] not in [item['q'] for item in items]:items.append({**raw,'prompt':raw['question_md']})
            if len(items)==2:break
    if level>1:
        items=[]
        for _ in range(20):
            item=_transfer(knowledge,rng,level)[0]
            if item['q'] not in [other['q'] for other in items]:items.append(item)
            if len(items)==2:break
    for _ in range(20):
        transfer,features=_transfer(knowledge,rng,level)
        if transfer['q'] not in [item['q'] for item in items]:
            items.append(transfer);break
    if len(items)!=3:raise DomainError('UNSUPPORTED','这组题没有准备完整，请稍后再试。',422)
    for index,item in enumerate(items):
        if not _check(item,item['answer_latex']):
            raise DomainError('UNSUPPORTED','这组题的程序核验尚未通过，请稍后再试。',422)
        if match:item['matching']=copy.deepcopy(match)
        item.update(id=uuid.uuid4().hex,is_transfer=index==2,difficulty_level=level+(index==2),
                    difficulty_features=([match['reason']] if match else [])+(features if index==2 or level>1 else ['基础条件','同类运算']),
                    verification={'level':'verified','label':'模板答案已经程序核验'},
                    hint_max=0,hints=['先读清条件，想想这道题与原题的联系。',
                     '把条件写成式子，逐步使用本知识点的规则；最后代回核对。',
                     r'本题的结果是 \('+item['answer_latex']+r'\)。对照条件，再独立尝试一题。'])
    return items


def _owned(value,quiz_id):
    quiz=value['quizzes'].get(quiz_id)
    if quiz is None:raise DomainError('NOT_FOUND','没有找到这组检验，请重新打开。',404)
    return quiz


def _pause_until(value,knowledge,state):
    """Read a persisted deadline or migrate the old counter from saved facts.

    This helper is pure so lesson reads cannot move a deadline or write data.
    """
    if state.get('pause_until'):
        return date.fromisoformat(state['pause_until'])
    if state.get('low_streak',0)<2:return None
    completed=[]
    for saved in value['quizzes'].values():
        if saved['knowledge_id']!=knowledge or not saved.get('completed') or _progress(saved)['correct_count']>1:continue
        for raw in [saved.get('completed_at')]+[r.get('at') for r in saved['answers'].values()]+[saved.get('at')]:
            if raw:
                instant=datetime.fromisoformat(raw)
                if instant.tzinfo is None:instant=instant.replace(tzinfo=TZ)
                completed.append(instant.astimezone(TZ).date())
    return max(completed)+timedelta(days=1) if completed else None


def _reset_expired(state,deadline,today):
    if deadline is not None and deadline<=today:
        state['low_streak']=0;state.pop('pause_until',None)


def _pause_reason(deadline):
    return '这个知识点今天先不出新检验。回到知识讲解慢慢看看，'+deadline.isoformat()+'（北京时间）起可以重新开始；其他知识点照常。'


def lesson(student,source_wrong_card_id,knowledge):
    contract.definition('Identifier',source_wrong_card_id)
    if knowledge not in SUPPORTED | COMPOSITE_SUPPORTED:raise DomainError('INVALID_INPUT','请选择有参考规则讲解的知识点。')
    value=store.read(student);source=value['wrong_cards'].get(source_wrong_card_id)
    if source is None:raise DomainError('NOT_FOUND','没有找到这张来源题目卡，请重新读取。',404)
    if not isinstance(source,dict) or not isinstance(source.get('knowledge_ids'),list):
        raise DomainError('STORAGE_FAILED','知识讲解暂时无法完整读取，请重试。',503)
    if knowledge not in source['knowledge_ids']:raise DomainError('INVALID_INPUT','来源卡片与这个知识点不一致。')
    state=value.get('quiz_levels',{}).get(knowledge,{})
    deadline=_pause_until(value,knowledge,state);paused=deadline is not None and now().astimezone(TZ).date()<deadline
    reference=KNOWLEDGE_CARDS.get(knowledge,(KP[knowledge][0],RULES.get(knowledge,''),'先读条件，再把每一步与规则对应起来。'))
    title=KP[knowledge][0]
    if matching.range_source(source.get('problem','')):
        title='条件消元与取值范围'
        reference=(title,'先用等式消去一个变量，合并不等式得到自变量区间，再考察二次表达式的顶点与端点。','顶点在区间内时也要检查；开端点不能直接当成可取到的最大值或最小值。')
    result={'source_wrong_card_id':source_wrong_card_id,'knowledge_id':knowledge,'title':title,
            'rule':reference[1],'tip':reference[2],'problem':source.get('problem'),'student_steps':copy.deepcopy(source.get('student_steps')),
            'paused':paused,'resume_on':deadline.isoformat() if paused else None,
            'verification':{'level':'unavailable','label':'本机参考目录的规则讲解；原作答保留供回顾'}}
    try:return contract.definition('QuizLessonOutput',result)
    except contract.ContractError:raise DomainError('STORAGE_FAILED','知识讲解暂时无法完整读取，请重试。',503) from None


def start(student,params,request_id):
    contract.definition('QuizStartInput',params)
    knowledge=params['knowledge_id']
    if knowledge not in SUPPORTED | COMPOSITE_SUPPORTED:raise DomainError('UNSUPPORTED','这个知识点暂时没有可独立核验的三题检验，可以继续整理错题和回忆规则。',422)
    def commit(value,_):
        sources=[value['wrong_cards'].get(k) for k in params['source_wrong_card_ids']]
        if any(card is None for card in sources):raise DomainError('NOT_FOUND','来源错题卡不存在，请刷新卡片列表。',404)
        if any(knowledge not in card['knowledge_ids'] for card in sources):raise DomainError('INVALID_INPUT','来源卡片与检验知识点不一致。')
        if params.get('review_id'):
            saved=value['reviews'].get(params['review_id'])
            if saved is None or saved.get('kp',params['review_id'])!=knowledge:raise DomainError('NOT_FOUND','没有找到对应知识点的复习安排。',404)
        history=value.setdefault('quiz_levels',{}).setdefault(knowledge,{'level':1,'low_streak':0})
        today=now().astimezone(TZ).date();deadline=_pause_until(value,knowledge,history)
        if deadline is not None and today<deadline:raise DomainError('CONFLICT',_pause_reason(deadline),409)
        _reset_expired(history,deadline,today)
        matches=[matching.classify(source,knowledge) for source in sources]
        if len({m['family'] for m in matches})!=1:matching.unsupported()
        match=matches[0]
        # Initial level is only seeded once; downshifts retain the same method.
        if not any(q['knowledge_id']==knowledge for q in value['quizzes'].values()):
            history['level']=max(history.get('level',1),match['initial_level'])
        level=max(1,history.get('level',1))
        items=_group(knowledge,level,request_id,match)
        quiz_id=uuid.uuid4().hex
        value['quizzes'][quiz_id]={'id':quiz_id,'knowledge_id':knowledge,'source_wrong_card_ids':params['source_wrong_card_ids'],
            'review_id':params.get('review_id'),'level':level,'at':now().isoformat(timespec='seconds'),
            'items':{item['id']:item for item in items},'answers':{},'completed':False}
        output={'quiz_id':quiz_id,'knowledge_id':knowledge,
                'items':[{k:copy.deepcopy(item[k]) for k in PUBLIC_ITEM+OPTIONAL_ITEM if k in item} for item in items]}
        return {'status':'ok','verification':{'level':'verified','label':'题组已由服务端核验并保存'},'output':output,
                'effects':[{'kind':'start_quiz','id':quiz_id,'idempotent_replay':False}]}
    return store.command(student,'quiz.start',request_id,params,lambda:None,commit,
                         validate=lambda r:contract.definition('QuizStartOutput',r['output']))


def hint(student,params):
    def change(value):
        quiz=_owned(value,params['quiz_id']);item=quiz['items'].get(params['exercise_id'])
        if item is None or params['diagnosis_id'] not in [value['wrong_cards'][key]['diagnosis_id'] for key in quiz['source_wrong_card_ids']]:
            raise DomainError('NOT_FOUND','检验题与来源不对应，请重新打开这组题。',404)
        level=params['level'];item['hint_max']=max(item.get('hint_max',0),level)
        if not any(view.get('quiz_id')==quiz['id'] and view.get('exercise_id')==item['id'] and view['level']==level for view in value['hint_views']):
            value['hint_views'].append({'id':uuid.uuid4().hex,'quiz_id':quiz['id'],'exercise_id':item['id'],
                    'diagnosis_id':params['diagnosis_id'],'level':level,'at':now().isoformat(timespec='seconds')})
        return contract.definition('HintResponse',{'level':level,'text':item['hints'][level-1],
               'max_hint_level_recorded':item['hint_max'],'scope':'quiz_exercise'})
    return store.update(student,change)


def _progress(quiz):
    records=list(quiz['answers'].values())
    return {'answered_count':len(records),'correct_count':sum(r['correct'] for r in records),'complete':len(records)==3}


def _advance(value,quiz):
    progress=_progress(quiz)
    if not progress['complete']:return 'continue','可以继续下一题，也可以随时退出，已答内容会保留。'
    state=value.setdefault('quiz_levels',{}).setdefault(quiz['knowledge_id'],{'level':quiz['level'],'low_streak':0})
    instant=now().astimezone(TZ);today=instant.date();quiz['completed_at']=instant.isoformat(timespec='seconds')
    deadline=_pause_until(value,quiz['knowledge_id'],state)
    if deadline is not None and today<deadline:return 'stop_and_explain',_pause_reason(deadline)
    _reset_expired(state,deadline,today)
    correct=progress['correct_count'];nohint=all(item['hint_max']==0 for item in quiz['items'].values())
    if correct==3 and nohint:state.update(level=quiz['level']+1,low_streak=0);return 'up','这组三题都独立完成，下次可以试一组条件更多的题。'
    if correct<=1:
        state.update(level=max(1,quiz['level']-1),low_streak=state.get('low_streak',0)+1)
        if state['low_streak']>=2:
            deadline=today+timedelta(days=1);state['pause_until']=deadline.isoformat()
            return 'stop_and_explain',_pause_reason(deadline)
        return 'down_with_scaffold','下次从更简单的条件开始，可以先把已知条件逐项写下来。'
    state['low_streak']=0
    return 'hold','保留当前难度，先回顾这组里还需要核对的地方。'


def answer(student,params,request_id):
    contract.definition('QuizAnswerInput',params)
    def commit(value,_):
        quiz=_owned(value,params['quiz_id']);item=quiz['items'].get(params['exercise_id'])
        if item is None:raise DomainError('NOT_FOUND','这道题不在本组检验里。',404)
        existing=quiz['answers'].get(item['id'])
        if existing is not None:
            output=copy.deepcopy(existing['_output']);output['duplicate']=True
            return {'status':'ok','output':output,'verification':existing['verification'],'effects':[]}
        correct=bool(_check(item,params['answer']));identity=uuid.uuid4().hex
        record={'exercise_id':item['id'],'evidence_id':identity,'knowledge_id':quiz['knowledge_id'],
                'quiz_id':quiz['id'],'correct':correct,'is_transfer':item['is_transfer'],
                'max_hint_level':item['hint_max'],'verification':copy.deepcopy(item['verification']),
                'at':now().isoformat(timespec='seconds')}
        value['quiz_answers'][identity]=record;quiz['answers'][item['id']]=copy.deepcopy(record)
        next_step,reason=_advance(value,quiz)
        quiz['completed']=_progress(quiz)['complete']
        output={k:record[k] for k in ('exercise_id','correct','max_hint_level','verification','evidence_id')}
        output.update(quiz_id=quiz['id'],duplicate=False,progress=_progress(quiz),next_step=next_step,reason=reason)
        quiz['answers'][item['id']]['_output']=copy.deepcopy(output)
        return {'status':'ok','output':output,'verification':record['verification'],
                'effects':[{'kind':'record_answer','id':identity,'idempotent_replay':False}]}
    return store.command(student,'quiz.answer',request_id,params,lambda:None,commit,
                         validate=lambda r:contract.definition('QuizAnswerOutput',r['output']))


def unlock(student,params,request_id):
    contract.definition('CardUnlockInput',params)
    def commit(value,_):
        quiz=_owned(value,params['quiz_id']);records=list(quiz['answers'].values())
        sources=[value['wrong_cards'].get(key,{}) for key in quiz['source_wrong_card_ids']]
        if any(matching.range_source(source.get('problem','')) for source in sources) and any(i.get('matching',{}).get('family')!='eliminate-quadratic-range' for i in quiz['items'].values()):
            raise DomainError('UNSUPPORTED','这组旧检验与原题的综合方法不匹配。作答记录已保留，请关闭后从原题卡重新开始检验。',422)
        correct=[r for r in records if r['correct']]
        checks={'U1':len(correct)>=2,'U2':any(r['is_transfer'] for r in correct),
                'U3':len(quiz['items'])==3 and all(item['verification']['level']=='verified' for item in quiz['items'].values())
                     and all(r['verification']['level']=='verified' for r in records),
                'U4':bool(correct) and all(r['max_hint_level']<3 for r in correct),
                'U5':len(records)==3 and quiz['completed']}
        messages={'U1':'需要在这组三题里答对至少两题。','U2':'还需要独立完成其中的迁移题。',
                  'U3':'这组题含有尚未程序核验的内容，暂时不能用于解锁。',
                  'U4':('答对的检验题里使用过完整解法，可以学习后再试一组。' if any(r['max_hint_level']>=3 for r in correct) else '还没有答对的检验题可用于检查独立完成情况。'),'U5':'先完成并保存本组三题。'}
        output={'knowledge_id':quiz['knowledge_id'],'unlocked':all(checks.values()),'reused_existing':False,
                'checks':checks,'reasons':[messages[k] for k,v in checks.items() if not v]}
        effects=[]
        if output['unlocked']:
            evidence={'quiz_id':quiz['id'],'knowledge_id':quiz['knowledge_id'],'source':'server_record',
                      'checks':checks,'answers':[{k:r[k] for k in RECORD} for r in records]}
            existing=next((c for c in value['knowledge_cards'].values() if c['knowledge_id']==quiz['knowledge_id']),None)
            if existing:
                card=existing;output['reused_existing']=True
            else:
                identity=uuid.uuid4().hex;knowledge=quiz['knowledge_id']
                rule=KNOWLEDGE_CARDS.get(knowledge,('',RULES.get(knowledge,''),''))[1]
                title=KP[knowledge][0]
                if all(i.get('matching',{}).get('family')=='eliminate-quadratic-range' for i in quiz['items'].values()):
                    title='条件消元与取值范围'
                    rule='先用等式消去一个变量，合并不等式得到自变量区间，再考察二次表达式的顶点与端点，保留开闭边界。'
                card={'id':identity,'type':'knowledge','knowledge_id':knowledge,'title':title,
                      'source_wrong_card_ids':quiz['source_wrong_card_ids'],'rule':rule,
                      'rule_source':'本机参考目录与已核验模板规则','verification':{'level':'verified','label':'依据服务端保存的三题检验解锁'},
                      'learner_note':'','status':'active','revision':0,'unlock_evidence':evidence}
                value['knowledge_cards'][identity]=card
                effects.append({'kind':'unlock_card','id':identity,'idempotent_replay':False})
                growth_id=uuid.uuid4().hex
                value['growth_events'].append({'id':growth_id,'kind':'scale','knowledge_id':knowledge,
                    'points':10,'at':now().isoformat(timespec='seconds')})
                effects.append({'kind':'update_growth','id':growth_id,'idempotent_replay':False})
            output.update(card=cards.public_card(card),evidence=evidence)
        return {'status':'ok','output':output,'effects':effects,
                'verification':{'level':'verified' if output['unlocked'] else 'unavailable','label':'依据已保存答题事实检查 U1 至 U5'}}
    return store.command(student,'card.unlock',request_id,params,lambda:None,commit,
                         validate=lambda r:contract.definition('CardUnlockOutput',r['output']))
