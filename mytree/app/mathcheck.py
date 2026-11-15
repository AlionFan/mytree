"""逐步校验引擎：判断每一行与上一行是否等价，定位第一个出错的步骤并归因。
纯 SymPy，不调用大模型。适用范围：因式分解、分式化简（八年级上册）。"""
import itertools
import re
import string

import sympy
from sympy import Add, Mul, Pow, Symbol, cancel, expand, factor, factor_list, factor_terms, fraction, gcd, together
from sympy.core.traversal import preorder_traversal

_SYMS = {c: Symbol(c) for c in string.ascii_letters}
_SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_MAP = {"²": "^2", "³": "^3", "−": "-", "–": "-", "—": "-", "×": "*", "·": "*", "÷": "/",
        "（": "(", "）": ")", "［": "(", "］": ")", "[": "(", "]": ")", "{": "(", "}": ")",
        "＋": "+", "－": "-", "＝": "=", "＊": "*", "／": "/", "＾": "^", " ": "", "　": ""}


class ParseError(ValueError):
    pass


def normalize(s):
    for k, v in _MAP.items():
        s = s.replace(k, v)
    if s.startswith("原式="):
        s = s[len("原式="):]
    elif s.startswith("="):
        s = s[1:]
    if "=" in s:
        raise ParseError("这里只检查表达式，方程暂不支持")
    return s


_ALLOWED = re.compile(r"^[0-9a-zA-Z+\-*/^().]+$")
MAX_LEN = 120
MAX_EXP = 8


def parse(s, evaluate=True):
    """有界四则表达式解析器。不执行学生输入，支持省略乘号和整数次幂。"""
    if not isinstance(s, str) or len(s) > 240:
        raise ParseError("式子过长")
    t = normalize(s)
    if not t or len(t) > MAX_LEN or not _ALLOWED.fullmatch(t):
        raise ParseError("只支持代数式，请检查字符")
    tokens = re.findall(r"(?:[0-9]+(?:\.[0-9]+)?)|[a-zA-Z]|\*\*|[+*/^().-]", t)
    if "".join(tokens) != t or len(tokens) > 100:
        raise ParseError("式子格式不支持")
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def take():
        nonlocal pos
        v = peek()
        pos += 1
        return v

    def atom(depth):
        if depth > 12:
            raise ParseError("括号太多")
        tok = take()
        if tok == "(":
            value = add(depth + 1)
            if take() != ")":
                raise ParseError("括号未配对")
        elif tok in _SYMS:
            value = _SYMS[tok]
        elif tok and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", tok):
            if len(tok) > 8:
                raise ParseError("数字过大")
            value = sympy.Rational(tok)
        else:
            raise ParseError("缺少数字或字母")
        if peek() in ("^", "**"):
            take()
            sign = -1 if peek() == "-" else 1
            if peek() in ("+", "-"):
                take()
            exponent = take()
            if not exponent or not exponent.isdigit() or len(exponent) > 2 or int(exponent) > MAX_EXP:
                raise ParseError("只支持绝对值不超过 8 的整数指数")
            value = Pow(value, sign * int(exponent), evaluate=False)
            if peek() in ("^", "**"):
                raise ParseError("请用括号明确次幂")
        return value

    def unary(depth):
        if peek() in ("+", "-"):
            sign = take()
            value = unary(depth + 1) if depth < 12 else None
            if value is None:
                raise ParseError("符号太多")
            return value if sign == "+" else Mul(-1, value, evaluate=False)
        return atom(depth)

    def mul(depth):
        value = unary(depth)
        while peek() and peek() not in ("+", "-", ")"):
            op = take() if peek() in ("*", "/") else "*"
            right = unary(depth)
            if op == "/":
                right = Pow(right, -1, evaluate=False)
            value = Mul(*Mul.make_args(value), *Mul.make_args(right), evaluate=False)
        return value

    def add(depth):
        value = mul(depth)
        while peek() in ("+", "-"):
            op = take()
            right = mul(depth)
            if op == "-":
                right = Mul(-1, right, evaluate=False)
            value = Add(value, right, evaluate=False)
        return value

    try:
        raw = add(0)
        if pos != len(tokens) or len(raw.free_symbols) > 4:
            raise ParseError("式子格式不支持")
        # 展开前限制总次数，避免短输入产生极大的符号运算。
        def cost(expr):
            if expr.is_Atom:
                return 1 if expr.is_Symbol else 0
            if expr.is_Pow:
                return max(1, cost(expr.base)) * abs(int(expr.exp))
            values = [cost(v) for v in expr.args]
            return sum(values) if expr.is_Mul else max(values, default=0)
        if cost(raw) > 16 or sympy.count_ops(raw) > 65:
            raise ParseError("式子超过当前校验范围")
        value = raw.doit()
        if value.has(sympy.zoo, sympy.oo, -sympy.oo, sympy.nan):
            raise ParseError("分母不能恒为零")
        if not value.free_symbols and abs(value) > 10**16:
            raise ParseError("计算数值过大")
        return value if evaluate else raw
    except ParseError:
        raise
    except Exception as ex:
        raise ParseError("式子格式不支持") from ex


def domain_factors(source):
    raw = parse(source, evaluate=False)
    result = []
    for item in preorder_traversal(raw):
        if item.is_Pow and item.exp < 0:
            base = item.base.doit()
            if not base.free_symbols:
                continue
            numerator = fraction(together(base))[0]
            for f, _ in factor_list(numerator)[1]:
                if not any(equiv(f, other) or equiv(f, -other) for other in result):
                    result.append(f)
    return result


def domain_notes(source):
    return [fmt(f) + " ≠ 0" for f in domain_factors(source)]



def fmt(e):
    s = re.sub(r"\*\*(\d+)", lambda m: m.group(1).translate(_SUP), str(e))
    return s.replace("*", "").replace(" ", "")


def equiv(x, y):
    return cancel(together(x - y)) == 0


def kind_of(expr):
    return "fraction" if fraction(together(expr))[1].free_symbols else "factor"


def evidence(a, b, excluded=()):
    """找一组数代入，让两行的值不相等，给孩子看「代入检验」。"""
    syms = sorted(a.free_symbols | b.free_symbols, key=str)
    for base in (2, 3, -2, 4, 5, -3, 1, 0, -1, 6, 7):
        env = {s: base + i for i, s in enumerate(syms)}
        if any(f.subs(env) == 0 for f in excluded):
            continue
        va, vb = a.subs(env), b.subs(env)
        if va.is_number and vb.is_number and va.is_finite and vb.is_finite and va != vb:
            return {"at": {str(s): int(v) for s, v in env.items()}, "prev": fmt(va), "cur": fmt(vb),
                    "prev_val": float(va), "cur_val": float(vb)}
    return None


def _signs_flipped(ea, eb):
    ts = Add.make_args(ea)
    d = expand(ea - eb)
    if d == 0:
        return False
    for r in range(1, min(len(ts), 6) + 1):
        for sub in itertools.combinations(ts, r):
            if expand(2 * Add(*sub) - d) == 0:
                return True
    return False


def completeness(kind, final_s, problem):
    """所有步骤都等价后，检查最后一行是否真的到位。返回 None 或 (错因码, 说明)。"""
    if kind == "factor":
        if factor(problem) == problem:
            return None
        e = parse(final_s, evaluate=False)
        if isinstance(e, Add) or not isinstance(e, (Mul, Pow)):
            return ("F-NOT-PRODUCT", fmt(parse(final_s)))
        for f in (e.args if isinstance(e, Mul) else (e,)):
            g = f.base if isinstance(f, Pow) and f.exp.is_Integer and f.exp > 0 else f
            g = g.doit()
            if g.is_number:
                continue
            c, fl = factor_list(g)
            if len(fl) > 1 or any(k > 1 for _, k in fl):
                return ("F-NOT-FINISHED", fmt(g))
            if g.is_Add and abs(c) != 1:
                return ("F-COMMON-PARTIAL", fmt(g))
        return None
    n, d = fraction(parse(final_s, evaluate=False))
    n, d = expand(n.doit()), expand(d.doit())
    g = gcd(n, d)
    if d.free_symbols and g not in (1, -1):
        return ("R-CANCEL-INCOMPLETE", fmt(factor(g)))
    return None


def _factor_sign_swapped(prev_s, b):
    """上一行里某个括号被学生写反了符号，例如 (3-x) 抄成 (x-3)。"""
    try:
        e = parse(prev_s, evaluate=False)
    except ParseError:
        return False
    for f in preorder_traversal(e):
        if isinstance(f, Add) and f is not e:
            if equiv(e.xreplace({f: -f}), b):
                return True
    return False


def _step_cause(kind, prev_s, cur_s, a, b):
    """第 i 步与上一步不等价时，判断最可能的错因。只在预设错因码里选。"""
    ea, eb = expand(a), expand(b)
    if kind == "factor":
        ratio = cancel(together(b / a)) if a != 0 else None
        cu = parse(cur_s, evaluate=False)
        squares = [f for f in (cu.args if isinstance(cu, Mul) else (cu,))
                   if isinstance(f, Pow) and f.exp == 2 and f.base.is_Add]
        fl = factor_list(a)[1]
        if squares and len(Add.make_args(ea)) == 2 and len(fl) == 2 and all(k == 1 for _, k in fl):
            return "F-MIX-FORMULA"
        if ratio is not None and ratio.is_number and ratio not in (1, -1):
            return "F-COEFF-LOST"
        if _signs_flipped(ea, eb) or (ratio is not None and ratio == -1):
            return "F-SIGN"
        if _factor_sign_swapped(prev_s, b):
            return "F-SIGN"
        return "CALC"
    n, d = fraction(parse(prev_s, evaluate=False))
    n, d = n.doit(), d.doit()
    common = set(Add.make_args(n)) & set(Add.make_args(d))
    for t in common:
        if equiv(b, (n - t) / (d - t)):
            return "R-CANCEL-TERM"
    if _signs_flipped(ea, eb) or cancel(together(b + a)) == 0:
        return "R-SIGN"
    return "CALC"


def pretty(s):
    """把孩子写的原文转成读起来顺的写法：x^2 → x²，去掉乘号。内容不变。"""
    s = re.sub(r"\^(\d)", lambda m: m.group(1).translate(_SUP), s)
    s = re.sub(r"\*\*(\d)", lambda m: m.group(1).translate(_SUP), s)
    return s.replace("*", "")


def analyze(problem, steps):
    """problem: 题干表达式；steps: 学生每一行的作答。返回结构化诊断。"""
    try:
        p = parse(problem)
    except ParseError:
        return {"status": "unreadable", "where": 0, "text": problem}
    kind = "fraction" if domain_factors(problem) else kind_of(p)
    target = fmt(factor(p)) if kind == "factor" else fmt(cancel(together(p)))
    out = {"kind": kind, "problem": pretty(problem), "target": target, "steps": [], "first_error": None,
           "cause": None, "evidence": None, "status": "correct", "prev": None, "cur": None,
           "domain": domain_notes(problem)}
    prev_e, prev_s = p, problem
    for i, s in enumerate(steps, 1):
        row = {"i": i, "text": s, "ok": True}
        try:
            cur = parse(s)
        except ParseError:
            row["ok"] = None
            out["steps"].append(row)
            if out["status"] == "correct":
                out.update(status="unreadable", where=i, text=s)
            break
        original_domain = domain_factors(problem)
        extra = [f for f in domain_factors(s) if not any(
            cancel(together(f / d)).is_number for d in original_domain)]
        if extra and equiv(prev_e, cur):
            row["ok"] = False
            out["steps"].append(row)
            out.update(status="wrong_step", first_error=i, prev=pretty(prev_s), cur=pretty(s),
                       cause="R-DOMAIN", evidence=None)
            out["steps"].extend({"i": j, "text": text, "ok": None} for j, text in enumerate(steps[i:], i + 1))
            return out
        if not equiv(prev_e, cur):
            row["ok"] = False
            out["steps"].append(row)
            out.update(status="wrong_step", first_error=i, prev=pretty(prev_s), cur=pretty(s),
                       cause=_step_cause(kind, prev_s, s, prev_e, cur),
                       evidence=evidence(prev_e, cur, domain_factors(problem)))
            for r in steps[i:]:  # 后续行只标记为未检查，不再判断
                out["steps"].append({"i": len(out["steps"]) + 1, "text": r, "ok": None})
            return out
        out["steps"].append(row)
        prev_e, prev_s = cur, s
    if out["status"] == "correct" and steps:
        miss = completeness(kind, steps[-1], p)
        if miss:
            out.update(status="incomplete", cause=miss[0], cur=miss[1], first_error=len(steps))
            out["steps"][-1]["ok"] = "incomplete"
    return out
