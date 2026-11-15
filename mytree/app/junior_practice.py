"""可独立验算的初中常见主题练习。几何证明本身仍需复核。"""
import random
import re
import sympy as sp
from .formulas import parse_math, answer_set


def generate(topic,n=3):
    rng=random.Random();items=[]
    for index in range(n):
        a=rng.randint(2,7);b=rng.randint(1,6);c=rng.randint(2,5)
        expected=sp.Integer(0);kind='number';unit=''
        if topic=='N4':
            expected=sp.Rational(175,100)*10**(a+5);q=f'用科学计数法表示 \\({expected}\\)。';kind='scientific'
        elif topic=='N2':expected=sp.Integer(a+b);q=f'计算 \\(\\sqrt{{{a*a}}}+\\sqrt{{{b*b}}}\\)。'
        elif topic=='N1':expected=sp.Integer(a*b-c);q=f'计算 \\({a}\\times {b}-{c}\\)。'
        elif topic=='N3':b=min(b,12-a);expected=sp.Symbol('x')**(a+b);kind='expression';q=f'化简 \\(x^{a}\\cdot x^{b}\\)。'
        elif topic=='E1':expected=sp.FiniteSet(b);kind='set';q=f'解方程 \\({a}x+{c}={a*b+c}\\)，写出实数解。'
        elif topic in ('E3','E4'):
            expected=sp.FiniteSet(-a,a);kind='set';q=f'解方程 \\(x^2-{a*a}=0\\)，用集合写出全部实数根。'
            if topic=='E4':expected=sp.FiniteSet(a);q=f'解分式方程 \\(\\frac{{{a*b}}}{{x}}={b}\\)，注意分母不为零。'
        elif topic=='E2':expected=(sp.Integer(a),sp.Integer(b));kind='point';q=f'解方程组 \\(\\begin{{cases}}x+y={a+b}\\\\x-y={a-b}\\end{{cases}}\\)，按 \\((x,y)\\) 写出解。'
        elif topic=='I1':expected=sp.Interval.open(b,sp.oo);kind='set';q=f'解不等式 \\({a}x+{c}>{a*b+c}\\)，写出不等式形式或区间。'
        elif topic=='I2':expected=sp.Interval.Lopen(-a,b);kind='set';q=f'求不等式组 \\(\\begin{{cases}}x>-{a}\\\\x\\le {b}\\end{{cases}}\\) 的解集。'
        elif topic=='U1':expected=sp.Integer(1);q=f'点 \\(({a},{b})\\) 在第几象限？只写象限序号。'
        elif topic=='U2':expected=sp.Integer(a*c+b);q=f'已知 \\(y={a}x+{b}\\)，求 \\(x={c}\\) 时的函数值。'
        elif topic=='U5':expected=sp.Integer(a*c+b);q=f'租车费用由固定费用 {b} 元和每小时 {a} 元组成，租用 {c} 小时需要多少元？只填数值。'
        elif topic=='U3':expected=sp.Integer(a*b);q=f'反比例函数 \\(y=\\frac{{k}}{{x}}\\) 经过点 \\(({a},{b})\\)，求 \\(k\\)。'
        elif topic=='U4':expected=(sp.Integer(a),sp.Integer(b));kind='point';q=f'写出抛物线 \\(y=(x-{a})^2+{b}\\) 的顶点坐标。'
        elif topic=='G1':expected=sp.Integer(a*10);q=f'两条直线相交，一个角是 \\({a*10}^\\circ\\)，它的对顶角是多少度？只填数值。'
        elif topic=='G2':expected=sp.Integer(180-a*10-b*10);q=f'三角形的两个内角为 \\({a*10}^\\circ\\)、\\({b*10}^\\circ\\)，第三个内角是多少度？只填数值。'
        elif topic=='G9':expected=sp.Integer(2);q=r'已知 \(AB=DE\)、\(AC=DF\)、\(\angle BAC=\angle EDF\)，应采用哪条三角形全等判据？①SSS，②SAS，③AAS。只填序号。'
        elif topic=='G3':expected=sp.Integer(5*a);q=f'直角三角形两直角边长分别为 \\({3*a}\\)、\\({4*a}\\)，求斜边长。'
        elif topic=='G4':expected=sp.Integer(a*b);q=f'长方形长为 \\({a}\\)，宽为 \\({b}\\)，求面积。'
        elif topic=='G5':expected=sp.Integer(30*a);q=f'两个相似三角形的相似比为 \\({a}:1\\)，较小三角形的周长是 \\(30\\)，求较大三角形周长。'
        elif topic=='G6':expected=2*a*sp.pi;q=f'圆的半径是 \\({a}\\)，求周长，保留 \\(\\pi\\)。'
        elif topic=='G7':expected=(sp.Integer(-a),sp.Integer(b));kind='point';q=f'点 \\(({a},{b})\\) 关于 \\(y\\) 轴对称后的坐标是什么？'
        elif topic=='G8':expected=sp.Rational(3,5);q=f'直角三角形中，角 \\(A\\) 的邻边为 \\({3*a}\\)，斜边为 \\({5*a}\\)，求 \\(\\cos A\\)。'
        elif topic=='S1':expected=sp.Integer(a+b+c);q=f'统计表中三组人数分别为 \\({a}\\)、\\({b}\\)、\\({c}\\)，总人数是多少？'
        elif topic=='S2':expected=sp.Rational(a+b+c,3);q=f'求数据 \\({a},{b},{c}\\) 的平均数。'
        elif topic=='S3':expected=sp.Rational(2,3);q=f'求数据 \\({a-1},{a},{a+1}\\) 的方差（按总体方差计算）。'
        elif topic=='P2':expected=1-sp.Rational(3,4)**2;q='两人独立等可能地从 A、B、C、D 中各选一项，至少一人选 D 的概率是多少？'
        else:expected=sp.Rational(1,a+b);q=f'袋中有 \\({a+b}\\) 个完全相同且编号不同的小球，随机取一个，抽到指定编号小球的概率是多少？'
        display=sp.latex(expected) if kind!='point' else r'\left('+','.join(sp.latex(v) for v in expected)+r'\right)'
        if kind=='scientific':display=r'1.75\times 10^{'+str(a+5)+'}'
        items.append({'q':q,'question':q,'question_md':q,'answer_latex':display,'expected':list(map(str,expected)) if kind=='point' else str(expected),
                      'grading':kind,'domain':[],'a':display,'answer':display})
    return items


def check(item,answer):
    try:
        if item['grading']=='choice':
            from .source_text import math_text
            value=math_text(answer).strip().upper()
            if not re.fullmatch(r'[ABCD]',value):return False,'请选择一个选项 A、B、C 或 D。'
            expected=item['answer_latex']
            if expected not in 'ABCD' or len(expected)!=1:return False,'这道选择题的答案尚未准备完整，请稍后重试。'
            correct=value==expected
        elif item['grading']=='set':
            expected=answer_set(item['answer_latex'])
            correct=sp.simplify(expected.symmetric_difference(answer_set(answer)))==sp.EmptySet
        elif item['grading']=='point':
            source=answer.replace(r'\left','').replace(r'\right','').strip()
            if not (source.startswith('(') and source.endswith(')')):raise ValueError()
            values=source[1:-1].split(',')
            correct=len(values)==2 and all(sp.simplify(parse_math(v)-sp.Rational(e))==0 for v,e in zip(values,item['expected']))
        else:
            expected=parse_math(item['answer_latex']);actual=parse_math(answer)
            correct=(item['grading']=='expression' or not actual.free_symbols) and sp.simplify(actual-expected)==0
            if correct and sp.count_ops(parse_math(answer,evaluate=False))>sp.count_ops(sp.simplify(expected)) and item['grading']!='scientific' and not re.fullmatch(r'[+-]?\d+(?:\.\d+)?',answer.strip()):
                return False,'这一步数值等价，还需要继续化到结果。'
            if correct and item['grading']=='scientific':
                match=re.fullmatch(r'\s*(.*?)\s*(?:\\times|\\cdot|\*)\s*10\s*\^\s*\{?(-?\d+)\}?\s*',answer)
                correct=bool(match) and 1<=abs(parse_math(match[1]))<10
        return bool(correct),'已验算正确，进度已保存。' if correct else '还没有对上。再核对条件、运算顺序和单位要求。'
    except (ValueError,TypeError,NotImplementedError):return False,'这个答案暂时无法程序校验，请用数学键盘写出结果；坐标写成一对数，多个根用集合表示。'
