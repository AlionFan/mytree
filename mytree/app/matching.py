"""Bounded server-owned matching. Unknown structures never fall back by topic."""
import copy
import random
import re

import sympy as sp
from sympy.calculus.util import function_range
from .errors import DomainError
from .formulas import parse_math, solution_set

VERSION='source-structure-v3'
REASON='和原题一样，先消元并合并条件，再求二次表达式的取值范围。'
NUMBER=r'(-?\d{1,2}(?:\.\d{1,2})?)'


def unsupported():
    raise DomainError('UNSUPPORTED','暂时没有与这道原题结构匹配、且可程序核验的完整练习。请先回顾原题讲解；不会改推无关的简单题。',422)


def _normal(text):
    text=text.replace('（','(').replace('）',')')
    for old,new in ((r'\left',''),(r'\right',''),(r'\geq','>='),(r'\leq','<='),(r'\ge','>='),(r'\le','<='),('≥','>='),('≤','<='),('−','-'),('＝','='),('²','^2'),('³','^3'),('×','*'),(r'\,',''),(r'\quad','')):
        text=text.replace(old,new)
    return re.sub(r'\s','',text)


def range_source(problem):
    """Only a-b=c, a>l, b<u and a(b+d), with explicit finite bounds.

    Unsupported extra equations, integer variables, options or target variants
    cannot silently reuse this template. Choice options are not used as answers.
    """
    from .source_text import choice_parts, math_text
    choice=choice_parts(problem)
    choices=None
    if choice:
        problem,options=choice
        try:
            choices=[parse_math(math_text(option)) for option in options]
            if any(v.free_symbols or v.is_real is not True or v.is_finite is not True or abs(v)>100000 for v in choices):return None
            if len(set(choices))!=4:return None
        except (ValueError,TypeError):return None
        problem=re.sub(r'[（(]\s*[）)]\s*[。？?]?$', '',problem)
    text=_normal(problem)
    text=re.sub(r'^\d{1,2}[.．。、、]','',text)
    for marker in (r'\(',r'\)',r'\[',r'\]','$'):text=text.replace(marker,'')
    if not re.search('范围|可能|取值',text) or re.search('整数|自然数|正数|负数|正实数|负实数',text):return None
    eqs=list(re.finditer(r'(?<![a-z])([a-z])-([a-z])='+NUMBER+r'(?![\d.a-z])',text))
    if len(eqs)!=1:return None
    m,n,c=eqs[0].groups()
    if m==n:return None
    # Reject any additional relational conditions rather than discard them.
    relations=re.findall(r'(?:>=|<=|(?<![<>=])[<>=](?![=]))',text)
    if len(relations)!=3:return None
    lower=list(re.finditer(r'(?<![a-z])'+m+r'(>=|>)'+NUMBER+r'(?![\d.a-z])',text))
    upper=list(re.finditer(r'(?<![a-z])'+n+r'(<=|<)'+NUMBER+r'(?![\d.a-z])',text))
    target=re.search(r'(?<![a-zA-Z0-9_+*/(^{}\\-])'+m+r'\*?\('+n+r'([+-])'+r'(\d{1,2}(?:\.\d{1,2})?)'+r'\)(?![\^a-zA-Z0-9_*/+\-){}])',text)
    if len(lower)!=1 or len(upper)!=1 or not target:return None
    # Consume the entire supported math statement. Unknown conditions or outer
    # target operators must remain visible here and reject matching.
    remainder=text
    spans=[eqs[0].span(),lower[0].span(),upper[0].span(),target.span()]
    for start,end in sorted(spans,reverse=True):remainder=remainder[:start]+remainder[end:]
    remainder=remainder.replace(m+','+n,'',1).replace(m+'、'+n,'',1)
    allowed_words=r'已知|两个实数|实数|满足|且|则|若|求|取值范围|值可能是|可能的值为|可能取值|可能|范围|取值|的|值|为|（选择）|\(选择\)|。|，|,|、|；|;|：|:|？|\?'
    if re.sub(allowed_words,'',remainder):return None
    c=sp.Rational(c);l=sp.Rational(lower[0][2]);u=sp.Rational(upper[0][2])+c
    d=sp.Rational(target[2])*(1 if target[1]=='+' else -1)
    if not (-20<=c<=20 and -20<=d<=20 and -30<=l<u<=30):return None
    if choices is not None:
        image=range_answer(c,d,l,u,lower[0][1]=='>',upper[0][1]=='<')
        if sum(image.contains(v) is sp.S.true for v in choices)!=1:return None
    return {'family':'eliminate-quadratic-range','difference':str(c),'shift':str(d),'lower':str(l),'upper':str(u),
            'left_open':lower[0][1]=='>','right_open':upper[0][1]=='<','variables':[m,n],
            'source_format':'choice' if choices is not None else 'range'}


def classify(source,knowledge):
    problem=source.get('problem') or ''
    if not isinstance(problem,str) or not problem.strip():unsupported()
    analysis=source.get('_analysis') or source.get('analysis') or {}
    family=range_source(problem)
    if family:
        return {**family,'version':VERSION,'reason':REASON,'knowledge_id':knowledge,'initial_level':2,
                'source_id':source.get('id'),'skills':['消元','合并不等式约束','二次表达式范围'],
                'focus':'核对原作答中的卡点' if analysis.get('first_error') else '巩固这道题的方法'}
    from . import source_patterns
    extra=source_patterns.classify(problem)
    if extra:return {**extra,'version':VERSION,'knowledge_id':knowledge,'initial_level':1,'source_id':source.get('id')}
    raw=_ordinary_math(problem,analysis.get('problem_latex'))
    family_name=_template_family(raw,knowledge)
    return {'family':'verified-topic-template','template_family':family_name,'version':VERSION,
            'reason':'和原题一样，练习'+family_name+'。','knowledge_id':knowledge,
            'initial_level':1,'source_id':source.get('id'),'skills':[family_name]}


def _ordinary_math(problem,fragment):
    full=_normal(problem)
    for marker in (r'\(',r'\)',r'\[',r'\]','$'):full=full.replace(marker,'')
    full=re.sub(r'^(?:[（(]\d{1,2}[）)]|\d{1,2}[.．。、、])','',full)
    full=re.sub(r'分解因式|因式分解|化简|计算|解方程|解不等式|求不等式组的解集|写出实数解|写出解集|用科学计数法表示','',full).strip('：:。？? ')
    if fragment:
        # A recognized formula is only a formatting aid, never permission to
        # discard a condition in the full confirmed question.
        canonical=lambda t:re.sub(r'[{}*]','',_normal(t).replace(r'\cdot','*').replace(r'\times','*'))
        if canonical(full)!=canonical(fragment):unsupported()
    if not full or re.search(r'[\u3400-\u9fff]',full):unsupported()
    return full


def _template_family(raw,knowledge):
    normal=_normal(raw).replace(r'\cdot','*').replace(r'\times','*')
    literal=re.sub(r'\^\{(\d+)\}',r'^\1',normal)
    x=sp.Symbol('x')
    def square(v,power=2):
        if not v.is_Integer or v<=0:return False
        return sp.integer_nthroot(int(v),power)[1]
    def difference(expr,power=2):
        poly=sp.Poly(expr,x)
        return poly.degree()==power and poly.LC()==1 and all(poly.nth(i)==0 for i in range(1,power)) and square(-poly.nth(0),power)
    try:
        if knowledge.startswith(('F','R')):
            expr=parse_math(raw)
            if expr.free_symbols!={x}:unsupported()
            if knowledge.startswith('F'):
                forms={'F1':r'\d{1,3}\*?x\^2\+\d{1,3}\*?x','F2':r'x\^2-\d{1,4}',
                       'F3':r'x\^2\+\d{1,3}\*?x\+\d{1,4}','F4':r'x\^4-\d{1,6}',
                       'F5':r'\d+\*?\(x-\d+\)-\d+\*?\(\d+-x\)'}
                if knowledge not in forms or not re.fullmatch(forms[knowledge],literal):unsupported()
                poly=sp.Poly(expr,x)
                if knowledge=='F1':
                    a,b,c=poly.nth(2),poly.nth(1),poly.nth(0)
                    if poly.degree()!=2 or c!=0 or not all(v.is_Integer and v>0 for v in (a,b)) or sp.gcd(a,b)<=1 or b%a!=0:unsupported()
                    return '含公因式的一次与二次项提取'
                if knowledge=='F2':
                    if not difference(expr):unsupported()
                    return '两个整数平方项的平方差分解'
                if knowledge=='F3':
                    if poly.degree()!=2 or poly.nth(2)!=1 or not square(poly.nth(0)) or poly.nth(1)<=0 or sp.discriminant(poly.as_expr(),x)!=0:unsupported()
                    return '正中间项的完全平方公式'
                if knowledge=='F4':
                    if not difference(expr,4):unsupported()
                    return '连续两次平方差的四次式分解'
                if knowledge=='F5':
                    match=re.fullmatch(r'(\d+)\*?\(x-(\d+)\)-(\d+)\*?\((\d+)-x\)',normal)
                    if not match or match[2]!=match[4]:unsupported()
                    return '相反因式统一符号后提公因式'
                unsupported()
            term=r'[x0-9+*^\-]+'
            if not (re.fullmatch(r'\\frac\{('+term+r')\}\{('+term+r')\}',literal) or re.fullmatch(r'\(('+term+r')\)/\(('+term+r')\)',literal)):unsupported()
            numerator,denominator=sp.fraction(sp.together(expr))
            if knowledge=='R1':
                if not difference(numerator) or sp.Poly(denominator,x).degree()!=1 or sp.Poly(denominator,x).LC()!=1:unsupported()
                root=sp.Poly(denominator,x).nth(0)
                if root<=0 or root**2!=-sp.Poly(numerator,x).nth(0):unsupported()
                return '平方差分解后约去一次公因式'
            if knowledge=='R2':
                if not difference(numerator):unsupported()
                a=sp.sqrt(-sp.Poly(numerator,x).nth(0))
                if sp.expand(denominator-(x+a)**2)!=0:unsupported()
                return '平方差与完全平方分母的约分'
            if knowledge=='R3':
                if not difference(denominator):unsupported()
                a=sp.sqrt(-sp.Poly(denominator,x).nth(0))
                if sp.expand(numerator-(a-x))!=0:unsupported()
                return '相反因式与平方差分母的符号约分'
            unsupported()
        if knowledge=='N1':
            if not re.fullmatch(r'\d{1,2}\*\d{1,2}-\d{1,2}',normal):unsupported()
            parse_math(raw)
            return '先乘后减的整数混合运算'
        if knowledge=='N2':
            match=re.fullmatch(r'\\sqrt\{(\d{1,3})\}\+\\sqrt\{(\d{1,3})\}',normal)
            if not match or not all(square(sp.Integer(v)) for v in match.groups()):unsupported()
            return '两个完全平方数的算术平方根求和'
        if knowledge=='N3':
            if not re.fullmatch(r'x\^\{?\d{1,2}\}?\*x\^\{?\d{1,2}\}?',normal):unsupported()
            parse_math(raw)
            return '同底数幂的乘法'
        if knowledge.startswith(('E','I')):
            solution=solution_set(raw)
            expressions=[parse_math(v) for v in re.split(r'<=|>=|<|>|=',normal)]
            if set().union(*(v.free_symbols for v in expressions))!={x}:unsupported()
            if knowledge in ('E1','E3'):
                if len(expressions)!=2 or any(op in normal for op in '<>') or any(sp.denom(sp.together(v)).free_symbols for v in expressions):unsupported()
                poly=sp.Poly(expressions[0]-expressions[1],x)
                if knowledge=='E1' and re.fullmatch(r'\d{1,2}\*?x(?:\+\d{1,2})?=\d{1,3}',normal) and poly.degree()==1 and isinstance(solution,sp.FiniteSet) and len(solution)==1 and all(v.is_Integer and v>0 for v in solution):return '一元一次方程的等价求解'
                if knowledge=='E3' and re.fullmatch(r'x\^2(?:-\d{1,4}=0|=\d{1,4})',literal) and difference(poly.as_expr()):return '平方差形式的两个实根方程'
                unsupported()
            if knowledge=='E4':
                if not (re.fullmatch(r'\\frac\{\d{1,3}\}\{x(?:-\d{1,2})?\}=\d{1,2}',literal) or re.fullmatch(r'\d{1,3}/(?:x|\(x-\d{1,2}\))=\d{1,2}',literal)):unsupported()
                if len(expressions)!=2 or any(op in normal for op in '<>'):unsupported()
                left,right=expressions
                if not left.free_symbols:left,right=right,left
                num,den=sp.fraction(sp.together(left))
                poly=sp.Poly(den,x)
                if right.free_symbols or num.free_symbols or not num.is_positive or not right.is_positive or poly.degree()!=1 or poly.LC()!=1 or poly.nth(0)>0 or not num.is_Integer or not right.is_Integer or not isinstance(solution,sp.FiniteSet) or len(solution)!=1 or not all(v.is_Integer and v>0 for v in solution):unsupported()
                return '单个一次分母的分式方程与验根'
            if knowledge=='I1':
                if len(expressions)!=2 or not isinstance(solution,sp.Interval):unsupported()
                if any(sp.denom(sp.together(v)).free_symbols for v in expressions):unsupported()
                poly=sp.Poly(expressions[0]-expressions[1],x)
                if poly.degree()!=1 or poly.LC()<=0 or not re.fullmatch(r'\d{1,2}\*?x(?:\+\d{1,2})?>\d{1,3}',normal):unsupported()
                return '正系数的一元一次严格不等式'
            if knowledge=='I2':
                if not re.fullmatch(r'-?\d{1,2}<x<=-?\d{1,2}',literal):unsupported()
                if len(expressions)!=3 or not isinstance(solution,sp.Interval) or not solution.left_open or solution.right_open:unsupported()
                if expressions[1]!=x or expressions[0].free_symbols or expressions[2].free_symbols:unsupported()
                return '左开右闭的两个区间边界合并'
        unsupported()
    except (ValueError,TypeError,NotImplementedError,sp.PolynomialError):unsupported()


def range_answer(c,d,lower,upper,left_open=True,right_open=True,sign=1):
    """Compute endpoints and stationary point; cross-check SymPy independently."""
    c,d,lower,upper=map(sp.Rational,(c,d,lower,upper));x=sp.Symbol('x',real=True)
    expression=sign*x*(x-c+d)
    vertex=(c-d)/2
    points=[(lower,not left_open),(upper,not right_open)]
    if lower<vertex<upper:points.append((vertex,True))
    values=[(sp.expand(expression.subs(x,p)),included) for p,included in points]
    lo=min(v for v,_ in values);hi=max(v for v,_ in values)
    result=sp.Interval(lo,hi,left_open=not any(v==lo and actual for v,actual in values),right_open=not any(v==hi and actual for v,actual in values))
    domain=sp.Interval(lower,upper,left_open=left_open,right_open=right_open)
    # Split at the stationary point: function_range on an unsplit interval can
    # lose an attained extremum when equal endpoint values have mixed openness.
    if lower<vertex<upper:
        independent=function_range(expression,x,sp.Interval(lower,vertex,left_open=left_open)).union(function_range(expression,x,sp.Interval(vertex,upper,right_open=right_open)))
    else:independent=function_range(expression,x,domain)
    if result!=independent:unsupported()
    return result


def range_items(match,level,seed):
    rng=random.Random(seed);items=[]
    # First full task preserves the elimination/constraint/range chain. The
    # transfer changes the inequality endpoint or the sign/shape of the target.
    for i in range(3):
        c=rng.randint(2,6);d=rng.randint(1,4)
        vertex=sp.Rational(c-d,2)
        lower=c-1 if i==0 and level<=2 else vertex-rng.randint(1,3)
        upper=c+rng.randint(2,4) if i==0 else vertex+rng.randint(2,4)
        left_open=True;right_open=i!=1
        sign=-1 if i==2 else 1
        # Downshift provides a concrete method reminder, still a full task.
        scaffold='先写 n=m-'+str(c)+'，再把两个不等式合并为 m 的区间。' if level<=1 else ''
        if i==2:
            target=r'm('+str(d)+r'-n)'
            # m(d-n) = -m(m-c-d): reuse d parameter with negative sign.
            expected=range_answer(c,-d,lower,upper,left_open,right_open,-1)
        else:
            target=r'm(n+'+str(d)+r')'
            expected=range_answer(c,d,lower,upper,left_open,right_open,1)
        lower_text=sp.latex(lower);upper_n=sp.latex(upper-c)
        if level>=4:
            conditions=r'\frac{m-n}{2}='+sp.latex(sp.Rational(c,2))+r',\quad -2m<'+sp.latex(-2*lower)+r',\quad 3n'+('<' if right_open else r'\le ')+sp.latex(3*(upper-c))
            burden='还要处理分式等式与负系数不等式，留意变号和区间顶点。'
        elif level>=3:
            conditions=r'2m-2n='+str(2*c)+r',\quad 2m>'+sp.latex(2*lower)+r',\quad 3n'+('<' if right_open else r'\le ')+sp.latex(3*(upper-c))
            burden='先整理带系数的条件，再判断顶点和区间端点。'
        else:
            conditions=r'm-n='+str(c)+r',\quad m>'+lower_text+r',\quad n'+('<' if right_open else r'\le ')+upper_n
            burden='保留原题的多条件与完整求范围步骤'
        prompt=r'实数 \(m,n\) 满足 \('+conditions+r'\)。求 \('+target+r'\) 的取值范围，用区间表示。'
        answer=sp.latex(expected)
        choice_options=None
        if match.get('source_format')=='choice':
            values=[(expected.start+expected.end)/2,expected.start-1,expected.end+1,expected.start-2]
            rng.shuffle(values)
            correct=[j for j,v in enumerate(values) if expected.contains(v) is sp.S.true]
            if len(correct)!=1:unsupported()
            choice_options=dict(zip('ABCD',[sp.latex(v) for v in values]))
            answer='ABCD'[correct[0]]
            prompt=r'实数 \(m,n\) 满足 \('+conditions+r'\)。则 \('+target+r'\) 的值可能是（　）'+'\n\n'+'\n\n'.join(label+r'．\('+value+r'\)' for label,value in choice_options.items())
        provenance={**copy.deepcopy(match),'generated_family':'eliminate-quadratic-range','verification':'endpoint-and-stationary-point; independently cross-checked with SymPy function_range',
                    'parameters':{'difference':str(c),'shift':str(d),'lower':str(lower),'upper':str(upper),'left_open':left_open,'right_open':right_open,'target':target}}
        items.append({'q':prompt,'question':prompt,'question_md':prompt,'prompt':prompt,'answer_latex':answer,'a':answer,'answer':answer,
                      'expected':str(expected),'grading':'choice' if choice_options else 'set','domain':[],'matching':provenance,
                      'match_reason':match['reason'],'difficulty_features':[match['reason'],'先练这条完整方法链：'+scaffold if scaffold else burden],
                      'is_transfer':i==2,'difficulty_level':level+(i==2),
                      'hints':['先用等式把两个未知数变成一个，再看它能取哪些值。',
                               '合并条件后，把目标写成一元二次式。检查顶点是否在区间内，同时留意端点能否取到。',
                               r'本题取值范围是 \('+answer+r'\)。请对照消元后的区间、顶点和开闭端点核对。']})
        if choice_options:
            items[-1].update(answer_kind='choice',choice_options=choice_options)
            items[-1]['hints'][-1]=r'消元后的取值范围是 \('+sp.latex(expected)+r'\)，只有选项 '+answer+' 在范围内。'
    return items
