"""LaTeX 与有界符号表达式；不执行模型或学生输入。"""
import re
import sympy as sp
from sympy.parsing.latex import parse_latex
from .mathcheck import parse as parse_ascii, ParseError

_ALLOWED_COMMANDS={'frac','dfrac','tfrac','sqrt','left','right','cdot','times','div','pi','sin','cos','tan','lvert','rvert','vert','infty','le','leq','ge','geq','ne','neq','pm','quad','qquad','circ','alpha','beta','gamma','theta','lambda'}


def clean_latex(source):
    if not isinstance(source,str) or not source.strip() or len(source)>480:
        raise ValueError('式子为空或超出校验长度')
    s=source.strip().strip('$').replace('\\(','').replace('\\)','').replace('\\[','').replace('\\]','')
    s=s.replace('−','-').replace('²','^{2}').replace('³','^{3}').replace('×',r'\times ').replace('÷',r'\div ')
    s=s.replace(r'\dfrac',r'\frac').replace(r'\tfrac',r'\frac').replace(r'\left','').replace(r'\right','').replace(r'\,',' ').replace(r'\!',' ')
    if '_' in re.sub(r'_\{?\d{1,2}\}?','',s) or re.search(r'[\u3400-\u9fff";`]',s):
        raise ValueError('只校验纯数学式，不执行文字或命令')
    commands=re.findall(r'\\([a-zA-Z]+)',s)
    if any(c not in _ALLOWED_COMMANDS for c in commands) or s.count('{')>28 or re.search(r'\d{17,}',s):
        raise ValueError('式子含有未支持的命令或过大的数')
    s=re.sub(r'\((-?1)\)\s*\^\s*\{(\d{1,6})\}',lambda m:str(int(m[1])**int(m[2])),s)
    s=re.sub(r'(?<!\d)1\s*\^\s*\{\d{1,6}\}','1',s)
    for power in re.findall(r'\^\s*\{?\s*(-?\d+)',s):
        if abs(int(power))>12:raise ValueError('指数超出当前校验范围')
    if re.search(r'\^\s*\{[^{}]*\^',s) or re.search(r'\^\s*\([^)]*\^',s):raise ValueError('不支持嵌套指数')
    s=re.sub(r'\\sqrt\s*\[3\]\s*\{(-?\d+)\}',lambda m:_cube(m.group(1)),s)
    s=re.sub(r'\\(sin|cos|tan)\s*\{?(\d+(?:\.\d+)?)\}?\s*\^\s*\{?\\circ\}?',lambda m:'\\'+m.group(1)+r'\left(\frac{'+m.group(2)+r'\pi}{180}\right)',s)
    return s


def _cube(value):
    n=int(value);r=round(abs(n)**(1/3))
    if r**3!=abs(n):raise ValueError('非完全立方根待核对')
    return str(-r if n<0 else r)


def parse_math(source,evaluate=True):
    s=clean_latex(source)
    try:
        expr=parse_ascii(s,evaluate=evaluate)
    except ParseError:
        try:expr=parse_latex(s,strict=True)
        except Exception:raise ValueError('这个式子暂时无法程序校验') from None
    if not isinstance(expr,sp.Expr):raise ValueError('这里应为数学表达式，关系式请使用解集校验')
    expr=expr.xreplace({sp.Symbol('pi'):sp.pi})
    expr=expr.xreplace({v:sp.Rational(str(v)) for v in expr.atoms(sp.Float)})
    if not isinstance(expr,sp.Basic) or sp.count_ops(expr)>100 or len(expr.free_symbols)>6:
        raise ValueError('式子超出当前程序校验范围')
    if expr.has(sp.Integral,sp.Derivative,sp.Sum,sp.Product,sp.zoo,sp.nan,sp.oo,-sp.oo):
        raise ValueError('式子超出初中校验范围')
    for p in expr.atoms(sp.Pow):
        if p.exp.is_negative and p.base.is_zero:raise ValueError('分母不能为零')
        if not p.exp.is_number or abs(p.exp)>12:
            raise ValueError('指数超出当前程序校验范围')
    if any(f.func not in (sp.sin,sp.cos,sp.tan,sp.Abs) for f in expr.atoms(sp.Function)):
        raise ValueError('函数超出当前校验范围')
    return expr


def latex_of(source):
    try:return sp.latex(parse_math(source))
    except (ValueError,TypeError):return str(source or '')


def ascii_of(source):
    expr=parse_math(source)
    if not isinstance(expr,sp.Expr):raise ValueError('这里应为表达式')
    text=sp.sstr(expr).replace('**','^')
    parse_ascii(text)
    return text


def solution_set(source):
    """一元一次/二次方程、单个不等式；根与定义域在实数范围处理。"""
    s=clean_latex(source).replace(r'\leq','<=').replace(r'\le','<=').replace(r'\geq','>=').replace(r'\ge','>=')
    s=s.replace('≤','<=').replace('≥','>=').replace('＝','=')
    parts=re.split(r'(<=|>=|<|>|=)',s)
    if len(parts)<3:raise ValueError('需要方程或不等式')
    sides=[parse_math(t,evaluate=False) for t in parts[::2]]
    symbols=set().union(*(v.free_symbols for v in sides))
    if len(symbols)!=1:raise ValueError('仅自动校验一元关系')
    variable=next(iter(symbols));rels=[];excluded=sp.EmptySet
    for side in sides:
        for power in side.atoms(sp.Pow):
            if power.exp.is_negative and variable in power.base.free_symbols:
                if sp.Poly(power.base,variable).degree()>2:raise ValueError('定义域超出当前校验范围')
                excluded=excluded.union(sp.solveset(power.base,variable,domain=sp.S.Reals))
    for i,op in enumerate(parts[1::2]):
        left,right=sides[i],sides[i+1]
        numerator=sp.together(left-right).as_numer_denom()[0]
        if sp.Poly(numerator,variable).degree()>2:raise ValueError('次数超出当前校验范围')
        rels.append({'=':sp.Eq,'<':sp.Lt,'>':sp.Gt,'<=':sp.Le,'>=':sp.Ge}[op](left,right))
    if len(rels)==1 and isinstance(rels[0],sp.Equality):
        result=sp.solveset(rels[0],variable,domain=sp.S.Reals)
    else:result=sp.reduce_inequalities(rels,variable).as_set()
    if result.has(sp.ConditionSet):raise ValueError('没有得到可核对的显式解集')
    return result-excluded


def answer_set(source):
    s=str(source).strip().strip('$').replace(r'\left','').replace(r'\right','').replace(r'\,','')
    if re.search(r'<=|>=|[<>=]|\\(?:le|ge)',s):return solution_set(s)
    s=s.replace(r'\{','{').replace(r'\}','}')
    if s.startswith('{') and s.endswith('}'):
        return sp.FiniteSet(*(parse_math(v) for v in s[1:-1].split(',')))
    m=re.fullmatch(r'([\[(])(.*),(.*)([\])])',s)
    if m:
        def bound(v):return -sp.oo if v.strip() in ('-\\infty','-∞') else sp.oo if v.strip() in ('\\infty','∞','+\\infty') else parse_math(v)
        return sp.Interval(bound(m[2]),bound(m[3]),left_open=m[1]=='(',right_open=m[4]==')')
    return sp.FiniteSet(parse_math(s))


def math_markdown(text):
    """兼容转录中的定界符与表格，保留学生原来的数学内容。"""
    text=str(text)
    def table(match):
        rows=[]
        for row in re.split(r'\\\\',match[1].replace(r'\hline','')):
            cells=[c.strip() for c in row.split('&')]
            if len(cells)>1:rows.append('| '+' | '.join(cells)+' |')
        if len(rows)>1:rows.insert(1,'| '+' | '.join(['---']*(rows[0].count('|')-1))+' |')
        return '\n'+'\n'.join(rows)+'\n'
    text=re.sub(r'\\begin\{tabular\}\{[^}]*\}([\s\S]*?)\\end\{tabular\}',table,text)
    parts=re.split(r'(\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]|\$\$[\s\S]*?\$\$|\$[^$\n]*\$)',text)
    for i,part in enumerate(parts):
        if part.startswith(('\\(','\\[','$')):continue
        segments=re.split(r'([\u3400-\u9fff，。；：！？\n]+)',part)
        for j,segment in enumerate(segments):
            if re.search(r'[A-Za-z0-9]',segment) and re.search(r'[\\^*/=+<>×÷]|[²³]',segment):
                segments[j]='\\('+segment.strip()+'\\)'
        parts[i]=''.join(segments)
    return ''.join(parts)
