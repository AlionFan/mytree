"""Owned, non-scoring knowledge-card examples and bounded same-method practice."""
import copy
import re
import sympy as sp
from . import quiz, store, matching
from .errors import DomainError


def alg(q,a,steps,domain=''):
    item=quiz._algebra(q,a)
    item['worked_steps']=steps
    if domain:item['prompt']+=' '+domain
    return item

def junior(prompt,expected,kind,steps):
    return {**quiz._junior(prompt,expected,kind),'worked_steps':steps}

x=sp.Symbol('x')
EXAMPLES={
 'F1':alg('6*x^2+18*x','6*x*(x+3)',[r'共同因式是 \(6x\)。',r'\(6x^2+18x=6x(x+3)\)。']),
 'F2':alg('x^2-9','(x-3)*(x+3)',[r'\(9=3^2\)。',r'\(x^2-3^2=(x-3)(x+3)\)。']),
 'F3':alg('x^2+6*x+9','(x+3)^2',[r'\(6x=2\cdot x\cdot3\)，\(9=3^2\)。',r'\(x^2+6x+9=(x+3)^2\)。']),
 'F4':alg('x^4-16','(x-2)*(x+2)*(x^2+4)',[r'先用平方差：\(x^4-16=(x^2-4)(x^2+4)\)。',r'继续分解：\(x^2-4=(x-2)(x+2)\)。']),
 'F5':alg('2*(x-3)-4*(3-x)','6*(x-3)',[r'\(3-x=-(x-3)\)。',r'\(2(x-3)+4(x-3)=6(x-3)\)。']),
 'R1':alg('(x^2-9)/(x+3)','x-3',[r'分子分解为 \((x-3)(x+3)\)。',r'约去非零因式 \(x+3\)，结果为 \(x-3\)。'],r'原式条件：\(x\ne-3\)。'),
 'R2':alg('(x^2-4)/(x^2+4*x+4)','(x-2)/(x+2)',[r'分子为 \((x-2)(x+2)\)，分母为 \((x+2)^2\)。',r'约去一个 \(x+2\)，得到 \(\frac{x-2}{x+2}\)。'],r'原式条件：\(x\ne-2\)。'),
 'R3':alg('(3-x)/(x^2-9)','-1/(x+3)',[r'\(3-x=-(x-3)\)，\(x^2-9=(x-3)(x+3)\)。',r'约分得到 \(-\frac1{x+3}\)，原式限制仍保留。'],r'原式条件：\(x\ne3,-3\)。'),
 'N1':junior(r'计算 \(3\times4-2\)。',sp.Integer(10),'number',[r'先乘：\(3\times4=12\)。',r'再减：\(12-2=10\)。']),
 'N2':junior(r'计算 \(\sqrt{9}+\sqrt{16}\)。',sp.Integer(7),'number',[r'\(\sqrt{9}=3\)，\(\sqrt{16}=4\)。',r'\(3+4=7\)。']),
 'N3':junior(r'化简 \(x^3\cdot x^4\)。',x**7,'expression',[r'同底数幂相乘，指数相加。',r'\(x^3\cdot x^4=x^{3+4}=x^7\)。']),
 'N4':junior(r'将 \(360000\) 写成科学计数法。',sp.Integer(360000),'scientific',[r'小数点左移5位，得到 \(3.6\)。',r'\(360000=3.6\times10^5\)。']),
 'E1':junior(r'解方程 \(2x+3=11\)，用集合表示解。',sp.FiniteSet(4),'set',[r'\(2x=11-3=8\)。',r'\(x=4\)，解集为 \(\{4\}\)。']),
 'E2':junior(r'解方程组 \(\begin{cases}x+y=7\\x-y=1\end{cases}\)，按 \((x,y)\) 填写。',(sp.Integer(4),sp.Integer(3)),'point',[r'两式相加：\(2x=8\)，所以 \(x=4\)。',r'代回得到 \(y=3\)。']),
 'E3':junior(r'解方程 \(x^2-9=0\)，用集合表示解。',sp.FiniteSet(-3,3),'set',[r'\((x-3)(x+3)=0\)。',r'\(x=3\) 或 \(x=-3\)。']),
 'E4':junior(r'解方程 \(\frac{6}{x}=2\)，用集合表示解，注意分母条件。',sp.FiniteSet(3),'set',[r'先记录 \(x\ne0\)。',r'\(6=2x\)，得 \(x=3\)，代回原式成立。']),
 'I1':junior(r'解不等式 \(-2x+1>7\)，用区间表示。',sp.Interval.open(-sp.oo,-3),'set',[r'移项得到 \(-2x>6\)。',r'两边除以 \(-2\)，不等号变向，\(x<-3\)。',r'解集为 \((-\infty,-3)\)。']),
 'I2':junior(r'求 \(\begin{cases}x>1\\x\le4\end{cases}\) 的解集，用区间表示。',sp.Interval.Lopen(1,4),'set',[r'同时满足两个条件，取交集。',r'\(1<x\le4\)，即 \((1,4]\)。']),
 'U4':junior(r'实数 \(m,n\) 满足 \(m-n=2\)、\(m\ge1\)、\(n\le1\)，求 \(m(n-2)\) 的取值范围，用区间表示。',sp.Interval(-4,-3),'set',[r'由 \(n=m-2\) 合并条件，得 \(1\le m\le3\)。',r'\(m(n-2)=m(m-4)=(m-2)^2-4\)。',r'顶点取到 \(-4\)，两个端点取到 \(-3\)，范围为 \([-4,-3]\)。']),
}

EXAMPLES['N4']['answer_latex']=r'3.6\times10^5'
EXAMPLES['U4']['matching']={'parameters':{'difference':'2','shift':'-2','lower':'1','upper':'3','left_open':False,'right_open':False}}

def _event_example(match,seed,index=0):
    from .event_practice import generate,event_kind
    item=generate(match,1,seed)[index]
    meanings={'certain':'必然事件，一定发生','impossible':'不可能事件，一定不发生','random':'随机事件，可能发生也可能不发生'}
    item['worked_steps']=['确定事件包括必然事件和不可能事件；随机事件不能预先断言一定发生或一定不发生。']
    item['worked_steps'] += [label+'：'+text+'。属于'+meanings[event_kind(text)]+'。' for label,text in item['choice_options'].items()]
    item['worked_steps'].append('对照题目问的是确定事件还是随机事件，本题选择 '+item['answer_latex']+'。')
    return item

EXAMPLES['P1']=_event_example({'family':'event-certainty','skills':['区分必然、不可能和随机事件'],'reason':quiz.RULES['P1']},'classic:P1')

def _display(v):return sp.latex(v)

def _line(text):return r'\('+text+r'\)'

def _source_match(source,knowledge):
    # Supplemental bounded source forms for two existing catalogue topics.
    if knowledge not in source.get('knowledge_ids',[]):raise DomainError('INVALID_INPUT','来源知识点不匹配。')
    if knowledge in ('E2','N4'):
        raw=source.get('problem','').replace(r'\(','').replace(r'\)','').replace(' ','').strip('。')
        for word in ('解方程组','用科学计数法表示','写成科学计数法','将','写成'):raw=raw.replace(word,'')
        if knowledge=='N4' and re.fullmatch(r'\d{1,13}',raw) and int(raw)>0:
            return {'family':'verified-topic-template','template_family':'正整数的科学计数法','source_id':source['id']}
        if knowledge=='E2':
            raw=raw.replace(r'\begin{cases}','').replace(r'\end{cases}','').replace(r'\\',',')
            if re.fullmatch(r'x\+y=-?\d{1,3},x-y=-?\d{1,3}',raw):return {'family':'verified-topic-template','template_family':'二元一次方程组加减消元','source_id':source['id']}
    return matching.classify(source,knowledge)


def _variant(knowledge,variant,key,match):
    """Deterministic same-method items with question-specific intermediate steps."""
    v=variant;a=3+v;b=2+v%7
    if match['family']=='event-certainty':return _event_example(match,key,variant%3)
    if match['family']=='eliminate-quadratic-range':
        item=matching.range_items(match,1,key)[0];p=item['matching']['parameters'];c,d,lo,hi=map(sp.Rational,[p['difference'],p['shift'],p['lower'],p['upper']]);h=(c-d)/2
        f=lambda t:sp.expand(t*(t-c+d))
        domain=sp.Interval(lo,hi,left_open=p['left_open'],right_open=p['right_open'])
        steps=[_line('n=m-'+str(c)),_line(r'm\in '+sp.latex(domain)),_line(r'm(n+'+str(d)+r')=m(m-'+str(c)+r'+'+str(d)+r')=(m-'+sp.latex(h)+r')^2-'+sp.latex(h*h)),
               '顶点 '+_line('m='+sp.latex(h))+(' 在区间内，函数值为 '+_line(sp.latex(f(h))) if lo<h<hi else ' 不在区间内部，比较端点。'),
               '左端点极限 '+_line(sp.latex(f(lo)))+('，不可取。' if p['left_open'] else '，可取。'),
               '右端点极限 '+_line(sp.latex(f(hi)))+('，不可取。' if p['right_open'] else '，可取。'),
               '结合顶点与端点：'+_line(sp.latex(matching.range_answer(c,d,lo,hi,p['left_open'],p['right_open'])))+('，选择 '+item['answer_latex']+'。' if item.get('answer_kind')=='choice' else '')]
        return {**item,'worked_steps':steps,'title':'条件消元与取值范围','rule':quiz.RULES['U4']}
    if knowledge=='F1':
        k=2+v//7;q=f'{k}*x^2+{k*b}*x';answer=f'{k}*x*(x+{b})'
        return alg(q,answer,['共同因式是 '+_line(str(k)+'x')+'。',_line(q.replace('*',r'\cdot '))+r' 中两项分别除以 '+_line(str(k)+'x')+' 得到 '+_line('x')+' 和 '+_line(str(b))+'。',_line(str(k)+r'x(x+'+str(b)+')')])
    if knowledge=='F2':return alg(f'x^2-{a*a}',f'(x-{a})*(x+{a})',[_line(str(a*a)+'='+str(a)+'^2'),_line('x^2-'+str(a*a)+'=x^2-'+str(a)+'^2'),_line('(x-'+str(a)+')(x+'+str(a)+')')])
    if knowledge=='F3':return alg(f'x^2+{2*a}*x+{a*a}',f'(x+{a})^2',[_line(str(2*a)+r'x=2\cdot x\cdot'+str(a)),_line(str(a*a)+'='+str(a)+'^2'),_line('x^2+'+str(2*a)+'x+'+str(a*a)+'=(x+'+str(a)+')^2')])
    if knowledge=='F4':return alg(f'x^4-{a**4}',f'(x-{a})*(x+{a})*(x^2+{a*a})',[_line('x^4-'+str(a**4)+'=(x^2-'+str(a*a)+')(x^2+'+str(a*a)+')'),_line('x^2-'+str(a*a)+'=(x-'+str(a)+')(x+'+str(a)+')'),_line('(x-'+str(a)+')(x+'+str(a)+')(x^2+'+str(a*a)+')')])
    if knowledge=='F5':
        k=2+v%5;c=1+v%3;t=1+v//5
        return alg(f'{k}*(x-{t})-{c}*({t}-x)',f'{k+c}*(x-{t})',[_line(str(t)+'-x=-(x-'+str(t)+')'),_line(str(k)+'(x-'+str(t)+')+'+str(c)+'(x-'+str(t)+')'),_line(str(k+c)+'(x-'+str(t)+')')])
    if knowledge in ('R1','R2','R3'):
        domain=_line('x\\ne-'+str(a))+('，'+_line('x\\ne'+str(a)) if knowledge=='R3' else '')
        q=f'(x^2-{a*a})/(x+{a})' if knowledge=='R1' else f'(x^2-{a*a})/(x^2+{2*a}*x+{a*a})' if knowledge=='R2' else f'({a}-x)/(x^2-{a*a})'
        answer=f'x-{a}' if knowledge=='R1' else f'(x-{a})/(x+{a})' if knowledge=='R2' else f'-1/(x+{a})'
        steps=['原分母非零：'+domain+'。',_line('x^2-'+str(a*a)+'=(x-'+str(a)+')(x+'+str(a)+')')]
        if knowledge=='R2':steps.append(_line('x^2+'+str(2*a)+'x+'+str(a*a)+'=(x+'+str(a)+')^2'))
        if knowledge=='R3':steps.append(_line(str(a)+'-x=-(x-'+str(a)+')'))
        steps.append('约去非零公因式，得到 '+_line(quiz._algebra(q,answer)['answer_latex'])+'，原式限制保留。')
        return alg(q,answer,steps,'原式条件：'+domain+'。')
    if knowledge=='N1':
        a=2+v%7;b=2+v//7;c=1+v%5
        return junior(_line(f'{a}\\times {b}-{c}')+' = ?',sp.Integer(a*b-c),'number',['先乘后减。',_line(f'{a}\\times{b}={a*b}'),_line(f'{a*b}-{c}={a*b-c}')])
    if knowledge=='N2':
        a=2+v%7;b=3+v//7
        return junior('计算 '+_line(r'\sqrt{'+str(a*a)+r'}+\sqrt{'+str(b*b)+'}')+'。',sp.Integer(a+b),'number',[_line(r'\sqrt{'+str(a*a)+'}='+str(a)),_line(r'\sqrt{'+str(b*b)+'}='+str(b)),_line(str(a)+'+'+str(b)+'='+str(a+b))])
    if knowledge=='N3':
        pairs=[(i,j) for total in range(3,13) for i in range(1,total) for j in [total-i]];a,b=pairs[(v-1)%len(pairs)]
        return junior('化简 '+_line('x^{'+str(a)+r'}\cdot x^{'+str(b)+'}')+'。',x**(a+b),'expression',['同底数幂相乘，指数相加。',_line(str(a)+'+'+str(b)+'='+str(a+b)),_line('x^{'+str(a)+r'}\cdot x^{'+str(b)+'}=x^{'+str(a+b)+'}')])
    if knowledge=='N4':
        exponent=3+v%8;coefficient=sp.Rational(125+7*v,100);number=coefficient*10**exponent;decimal=f'{float(coefficient):.2f}'.rstrip('0').rstrip('.')
        item=junior('用科学计数法表示 '+_line(str(number))+'。',number,'scientific',[_line(str(number)+r'\div10^{'+str(exponent)+'}='+decimal),_line('1\\le '+decimal+'<10'),_line(str(number)+'='+decimal+r'\times10^{'+str(exponent)+'}')]);item['answer_latex']=decimal+r'\times10^{'+str(exponent)+'}';return item
    if knowledge=='E1':
        a=2+v%7;b=2+v//7;c=1+v%5;d=a*b+c
        return junior('解方程 '+_line(f'{a}x+{c}={d}')+'，用集合表示解。',sp.FiniteSet(b),'set',[_line(f'{a}x={d}-{c}={a*b}'),_line(f'x={a*b}\\div{a}={b}'),'代回：'+_line(f'{a}\\times{b}+{c}={d}')])
    if knowledge=='E2':
        a=2+v%7;b=1+v//7;total=a+b;difference=a-b
        return junior('解方程组 '+_line(r'\begin{cases}x+y='+str(total)+r'\\x-y='+str(difference)+r'\end{cases}')+'，按 '+_line('(x,y)')+' 填写。',(sp.Integer(a),sp.Integer(b)),'point',[_line('2x='+str(total)+'+('+str(difference)+')='+str(2*a)),_line('x='+str(a)),_line('y='+str(total)+'-'+str(a)+'='+str(b))])
    if knowledge=='E3':return junior('解方程 '+_line('x^2-'+str(a*a)+'=0')+'，用集合表示解。',sp.FiniteSet(-a,a),'set',[_line('x^2='+str(a*a)),_line('(x-'+str(a)+')(x+'+str(a)+')=0'),_line('x='+str(a)+r'\quad\text{或}\quad x=-'+str(a))])
    if knowledge=='E4':
        b=2+v%3
        return junior('解方程 '+_line(r'\frac{'+str(a*b)+'}{x}='+str(b))+'，用集合表示解。',sp.FiniteSet(a),'set',[_line(r'x\ne0'),_line(str(a*b)+'='+str(b)+'x'),_line('x='+str(a))+'，代回原式分母非零且等式成立。'])
    if knowledge=='I1':
        a=2+v%7;b=1+v//7;c=1+v%5;negative=v%2==1;k=-a if negative else a;d=k*b+c;expected=sp.Interval.open(-sp.oo,b) if negative else sp.Interval.open(b,sp.oo)
        return junior('解不等式 '+_line(f'{k}x+{c}>{d}')+'，用区间表示。',expected,'set',[_line(f'{k}x>{d}-{c}={k*b}'),'两边除以 '+_line(str(k))+('，不等号变向。' if negative else '，不等号方向不变。'),_line('x'+('<' if negative else '>')+str(b)),_line(sp.latex(expected))])
    if knowledge=='I2':
        lo=-1-v;hi=2+v%5
        return junior('求不等式组 '+_line(r'\begin{cases}x>'+str(lo)+r'\\x\le '+str(hi)+r'\end{cases}')+' 的解集，用区间表示。',sp.Interval.Lopen(lo,hi),'set',[_line('x>'+str(lo))+r' 对应 '+_line('('+str(lo)+r',+\infty)'),_line(r'x\le '+str(hi))+r' 对应 '+_line(r'(-\infty,'+str(hi)+']'),'取交集：'+_line('('+str(lo)+','+str(hi)+']')])
    raise DomainError('UNSUPPORTED','这个知识点的同类题正在准备。',422)

def _source(value,card):
    source=next((value['wrong_cards'].get(i) for i in card.get('source_wrong_card_ids',[]) if value['wrong_cards'].get(i)),None)
    if not source:raise DomainError('NOT_FOUND','来源题已不可用。',404)
    return _source_match(source,card['knowledge_id'])


def _owned(value,card_id):
    store._identifier(card_id,'知识卡编号')
    card=value['knowledge_cards'].get(card_id)
    if not card or card.get('status')!='active':raise DomainError('NOT_FOUND','知识卡不存在，请重新选择。',404)
    if card.get('knowledge_id') not in EXAMPLES:raise DomainError('UNSUPPORTED','这个知识点的例题正在准备。',422)
    return card


def _public(card,item,key,variant):
    return {'ok':True,'card_id':card['id'],'lesson_id':key,'knowledge_id':card['knowledge_id'],'title':item.get('title',card['title']),
            'variant':variant,'prompt':item['prompt'],'rule':item.get('rule',card['rule']),'practice_only':True,
            'verification':{'level':'verified','label':'模板答案已核验'},
            **({'answer_kind':'choice'} if item.get('answer_kind')=='choice' else {})}


def handle(student,body):
    action=body.get('action')
    allowed={'student','action','card_id','variant','answer'}
    if set(body)-allowed or action not in ('open','next','hint','solution','answer'):raise ValueError('学习请求字段不正确。')
    variant=body.get('variant',0)
    if type(variant) is not int or not 0<=variant<=50 or (action=='open' and variant!=0) or (action=='next' and variant<1):raise ValueError('请按顺序选择例题。')
    card_id=body.get('card_id');value=store.read(student);card=_owned(value,card_id);key=card_id+':'+str(variant)
    _source(value,card)
    if action in ('open','next'):
        def commit(value):
            card=_owned(value,card_id);lessons=value.setdefault('card_lessons',{})
            if not isinstance(lessons,dict):raise DomainError('STORAGE_FAILED','例题暂时无法读取。',503)
            match=_source(value,card)
            if key not in lessons:
                composite=match['family']=='eliminate-quadratic-range'
                rule=quiz.RULES['U4'] if composite else card['rule']
                if variant==0:item=copy.deepcopy(EXAMPLES['U4' if composite else card['knowledge_id']])
                else:
                    item=_variant(card['knowledge_id'],variant,key,match)
                if composite:item.update(title='条件消元与取值范围',rule=rule)
                if not quiz._check(item,item['answer_latex']):raise DomainError('UNSUPPORTED','例题核验失败，请重试。',422)
                if len(lessons)>=200:lessons.pop(next(iter(lessons)))
                lessons[key]=item
            return _public(card,lessons[key],key,variant)
        return store.update(student,commit)
    item=value.get('card_lessons',{}).get(key)
    if not item:raise DomainError('NOT_FOUND','例题已过期，请重新打开知识卡。',404)
    if action=='hint':return {'ok':True,'hint':item.get('rule',card['rule'])}
    if action=='solution':return {'ok':True,'steps':item['worked_steps'],'answer_latex':item['answer_latex']}
    answer=body.get('answer')
    if not isinstance(answer,str) or not answer.strip() or len(answer)>400:raise ValueError('请填写答案。')
    correct=quiz._check(item,answer)
    return {'ok':True,'correct':correct,'feedback':'答对了' if correct else '再想一想','practice_only':True}
