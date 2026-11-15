"""Additional bounded source families; generators keep the source method chain."""
import random
import re
import sympy as sp
from sympy.calculus.util import continuous_domain
from .formulas import parse_math

FAMILIES={'expression-domain','perfect-square-polynomial','similar-area-perimeter','scientific-notation','event-certainty'}

def _blocks(problem):
    return [next(v for v in match if v) for match in re.findall(r'\\\((.*?)\\\)|\\\[(.*?)\\\]|\$([^$]+)\$',problem,re.S)]

def classify(problem):
    from .event_practice import classify as classify_events
    event=classify_events(problem)
    if event:return event
    # Domain questions: one linear radicand, optional constant numerator.
    if re.search('有意义|定义域',problem) and not re.search('整数|自然数|已知|同时满足',problem):
        for block in _blocks(problem):
            try:
                expr=parse_math(block);coef,power=expr.as_coeff_Mul()
                if isinstance(power,sp.Pow) and power.exp==-1 and isinstance(power.base,sp.Pow) and power.base.exp==sp.Rational(1,2):power=sp.Pow(power.base.base,sp.Rational(-1,2),evaluate=False)
                if not coef.is_number or coef==0 or not isinstance(power,sp.Pow) or power.exp not in (sp.Rational(1,2),sp.Rational(-1,2)):continue
                if len(expr.free_symbols)!=1:continue
                variable=next(iter(expr.free_symbols));poly=sp.Poly(power.base,variable)
                if poly.degree()!=1 or not all(v.is_Rational and abs(v)<=100 for v in poly.all_coeffs()):continue
                remainder=problem.replace(block,'').replace(str(variable),'')
                if re.search(r'[<>≤≥]|\\(?:frac|sqrt)',remainder):continue
                return {'family':'expression-domain','expression':sp.latex(expr),'variable':str(variable),
                        'skills':['根式非负条件']+(['分母非零','条件取交集'] if power.exp<0 else []),
                        'reason':'保留原题的根式条件'+('、分母非零和交集。' if power.exp<0 else '与实数定义域。')}
            except (ValueError,TypeError,sp.PolynomialError):continue
    if re.search('面积.{0,4}比|面积之比',problem) and '周长' in problem and '相似' in problem and not re.search('不相似|未必相似|是否相似',problem):
        ratio=re.search(r'(\d{1,3})\s*[:：]\s*(\d{1,3})',problem)
        if ratio:
            p,q=map(int,ratio.groups());a,b=sp.sqrt(p),sp.sqrt(q)
            if 0<p<q<=400 and a.is_Integer and b.is_Integer:
                return {'family':'similar-area-perimeter','skills':['面积比开平方求相似比','周长按相似比变化'],
                        'reason':'和原题一样，由面积比求相似比，再求周长。'}
    if re.search('科学记数法|科学计数法',problem):
        amounts=re.findall(r'(\d{1,8}(?:\.\d{1,4})?)\s*亿',problem)
        if amounts and len(set(amounts))==1 and sp.Rational(amounts[0])>0:
            magnitude=len(str(int(sp.Rational(amounts[0])*10**8)))-1
            return {'family':'scientific-notation','magnitude':magnitude,'skills':['大数单位换算','科学计数法系数与指数'],'reason':'保留原题的大数量级，先转换亿的单位，再写科学计数法。'}
    if re.search('分解因式|因式分解',problem):
        for block in _blocks(problem):
            raw=re.sub(r'=\s*[_＿…\.\s]*$','',block).strip()
            try:
                expr=parse_math(raw);symbols=sorted(expr.free_symbols,key=str)
                if not 1<=len(symbols)<=2:continue
                coeff,factors=sp.factor_list(expr)
                if coeff!=1 or len(factors)!=1 or factors[0][1]!=2:continue
                if sp.Poly(factors[0][0],*symbols).total_degree()!=1:continue
                return {'family':'perfect-square-polynomial','variables':[str(v) for v in symbols],
                        'skills':['完全平方公式','中间项符号与两项因式'], 'reason':'保留原题的完全平方结构与变量，不改推其他知识点。'}
            except (ValueError,TypeError,sp.PolynomialError):continue
    return None


def generate(match,level,seed):
    if match['family']=='event-certainty':
        from .event_practice import generate as generate_events
        return generate_events(match,level,seed)
    rng=random.Random(seed);items=[]
    for index in range(3):
        a=rng.randint(2,5);b=rng.randint(1,6)
        if match['family']=='expression-domain':
            expr=parse_math(match['expression']);x=next(iter(expr.free_symbols));a=-a if index==2 else a
            expression=expr.subs(x,a*x-b)
            expected=continuous_domain(expression,x,sp.S.Reals)
            prompt=r'求使式子 \('+sp.latex(expression)+r'\) 在实数范围内有意义的 \('+sp.latex(x)+r'\) 的取值范围，用区间或不等式表示。'
            grading='set';answer=sp.latex(expected);question=sp.sstr(expression)
            hint='分别找根号和分母的限制，再在数轴上取交集；注意端点能否取到。'
        elif match['family']=='perfect-square-polynomial':
            names=match['variables'];x=sp.Symbol(names[0]);y=sp.Symbol(names[1]) if len(names)>1 else sp.Integer(1)
            factor=a*x+(-b if index!=1 else b)*y;expression=sp.expand(factor**2)
            expected=sp.factor(expression);answer=sp.latex(expected);grading='algebra';question=sp.sstr(expression).replace('**','^')
            prompt=r'分解因式：\('+sp.latex(expression)+r'\)。'
            hint='找两端的平方项，再检查中间项是否为两项乘积的两倍，留意符号。'
        elif match['family']=='scientific-notation':
            a=rng.randint(12,95);exponent=max(3,min(14,match['magnitude']+index-1));amount=sp.Rational(a,10)*10**exponent
            prompt=f'某项测量数据为{int(amount)//10**8}亿' if int(amount)%10**8==0 else f'某项测量数据为{int(amount)}'
            prompt+='，请用科学计数法表示这个数。'
            grading='scientific';expected=amount;answer=str(a/10)+r'\times10^{'+str(exponent)+'}';question=prompt
            hint='先把亿换成基本数量，再把系数调整到大于等于1且小于10。'
        else:
            a,b=sorted(rng.sample(range(2,8),2));scale=rng.randint(10,25)
            given=b*scale if index!=2 else a*scale;expected=sp.Integer(a*scale if index!=2 else b*scale)
            prompt=f'两个相似图形的面积比为 \\({a*a}:{b*b}\\)。'+('较大' if index!=2 else '较小')+f'图形的周长为 \\({given}\\) cm，求'+('较小' if index!=2 else '较大')+'图形的周长，只写数值（单位cm）。'
            grading='number';answer=sp.latex(expected);question=prompt
            hint='面积比是相似比的平方；先开平方，再用周长与相似比的关系。'
        items.append({'q':question,'question':prompt,'question_md':prompt,'prompt':prompt,'a':answer,'answer':answer,'answer_latex':answer,
            'grading':grading,'expected':str(expected),'domain':[],'matching':{**match,'verification':'bounded-structure-and-symbolic-check'},
            'match_reason':match['reason'],'difficulty_level':max(1,level)+(index==2),'is_transfer':index==2,
            'difficulty_features':match['skills'],'hints':[hint,hint,r'本题结果为 \('+answer+r'\)，请说明每个条件或公式的作用。']})
    return items
