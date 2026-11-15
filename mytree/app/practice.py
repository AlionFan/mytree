"""变式题：按知识点用模板随机生成，每题都用 SymPy 验算，验不过的丢弃。
题目只用 ASCII 写法（^ 表示次方），显示时再转成上标。"""
import random

from .mathcheck import ParseError, analyze, domain_notes, fmt, parse
from .pipeline import verify_equal

# 模板：kind -> 函数(rng) -> (题目, 答案)，都是「分解因式」或「化简」
TEMPLATES = {
    "F1": lambda r: (lambda k, a: (f"{k}*x^2+{k*a}*x", f"{k}*x*(x+{a})"))(r.randint(2, 4), r.randint(2, 6)),
    "F3": lambda r: (lambda a: (f"x^2+{2*a}*x+{a*a}", f"(x+{a})^2"))(r.randint(1, 8)),
    "F2": lambda r: (lambda a: (f"x^2-{a*a}", f"(x+{a})*(x-{a})"))(r.randint(2, 9)),
    "F4": lambda r: (lambda a: (f"x^4-{a**4}", f"(x^2+{a*a})*(x+{a})*(x-{a})"))(r.randint(2, 3)),
    "F5": lambda r: (lambda a, b, c: (f"{a}*(x-{b})-{c}*({b}-x)", f"(x-{b})*({a}+{c})"))(
        r.randint(2, 5), r.randint(1, 5), r.randint(1, 4)),
    "R1": lambda r: (lambda a: (f"(x^2-{a*a})/(x+{a})", f"x-{a}"))(r.randint(1, 5)),
}

# 错因码 -> 练习模板
CAUSE_TO_KIND = {
    "F-NOT-FINISHED": "F4", "F-NOT-PRODUCT": "F1", "F-COMMON-PARTIAL": "F1", "F-COEFF-LOST": "F1",
    "F-SIGN": "F5", "F-MIX-FORMULA": "F2", "R-CANCEL-TERM": "R1", "R-CANCEL-INCOMPLETE": "R1",
    "R-SIGN": "R1", "R-DOMAIN": "R1", "CALC": "F1",
}


def _show(s):
    return s.replace("^2", "²").replace("^4", "⁴").replace("*", "")


def generate(kind, n=3, seed=None):
    """返回 n 道通过验算的题。模板数量不足时，会换一个种子继续生成，最多尝试 50 次。"""
    rng = random.Random(seed)
    items, tries = [], 0
    while len(items) < n and tries < 50:
        tries += 1
        q, a = TEMPLATES[kind](rng)
        try:
            ok = verify_equal(q, a) if kind != "R1" else _verify_fraction(q, a)
        except (ParseError, ValueError):
            ok = False
        if ok and q not in [i["q"] for i in items]:
            items.append({"q": q, "a": a, "question": _show(q), "answer": _show(a), "domain": domain_notes(q)})
    return items


def _verify_fraction(q, a):
    """分式题要排除让分母为零的数，所以验算时额外检查 x = -a 不会出现。"""
    return verify_equal(q, a)


def for_cause(cause, n=3, seed=None):
    kind = CAUSE_TO_KIND.get(cause, "F1")
    return {"kind": kind, "items": generate(kind, n, seed)}


def check_answer(question, answer):
    """孩子写的答案和题目是否恒等。返回 (是否正确, 提示语)。"""
    try:
        parse(answer)
    except ParseError:
        return False, "这个式子我没看懂，检查一下有没有漏掉括号或乘号。"
    result = analyze(question, [answer])
    if result["status"] == "correct":
        return True, "这次做对了，变形等价，也已经完成了分解或化简。"
    if result["status"] == "incomplete":
        return False, "式子相等，但还没有做完。请继续分解或约分到最简。"
    if result.get("cause") == "R-DOMAIN":
        return False, "这一步引入了额外的分母限制，换一种变形试试。"
    return False, "还没有对上。把你的答案展开，和原题逐项比一比。"
