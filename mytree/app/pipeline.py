"""流水线：读图（可替换）→ 逐步校验 → 归因 → 分级提示（H3 检查）→ 数形图 → 知识卡片。
接入后模型可负责读图与讲解，数学判定与图形仍由程序负责。默认 TextReader 直接使用调用方给的题目和步骤文本。"""
import re

from sympy import cancel, expand, factor, together

from .knowledge import CAUSES, KNOWLEDGE_CARDS, KP
from .mathcheck import analyze, parse, ParseError
from .visual import build as build_visual

GENERIC_H1 = "先看看这一步和上一步的关系：两行的值应该一样。哪一步开始不一样了？"
GENERIC_H2 = "找到第一个不一样的地方，再想想那一步用的是哪条规则。"


class TextReader:
    """手动录入适配器，不进行图片识别。接入大模型时实现同样的 read(payload) -> {problem, steps, confidence}。"""

    def read(self, payload):
        return {"problem": payload["problem"], "steps": payload["steps"], "source": "manual"}


def hints_for(a):
    """三级提示。第 1、2 级不得出现最终答案（H3）。"""
    cause = a.get("cause")
    if cause not in CAUSES:
        return []
    c = CAUSES[cause]
    fill = dict(n=a.get("first_error"), prev=a.get("prev") or "", cur=a.get("cur") or "",
                target=a.get("target") or "")
    return [c["h1"], c["h2"].format(**fill), c["h3"].format(**fill)]


def _norm(s):
    return re.sub(r"\s", "", s or "")


def h3_leak(text, target):
    """H3：低级别提示里不能出现最终答案字符串。长度太短的答案跳过（如 x），避免误伤。"""
    t = _norm(target)
    return len(t) >= 3 and t in _norm(text)


def knowledge_card(a):
    cause = a.get("cause")
    kp = (CAUSES.get(cause) or {}).get("kp")
    if kp not in KP:
        kp = None
    key = kp if kp in KNOWLEDGE_CARDS else "GEN"
    title, body, tip = KNOWLEDGE_CARDS.get(key, KNOWLEDGE_CARDS["GEN"])
    return {"kp": kp, "kp_name": KP[kp][0] if kp else "等价变形", "title": title, "body": body, "tip": tip}


def diagnose(problem, steps, reader=None):
    reader = reader or TextReader()
    read = reader.read({"problem": problem, "steps": steps})
    a = analyze(read["problem"], read["steps"])
    if a["status"] == "unreadable":
        return {"ok": False, "reason": "unreadable", "analysis": a,
                "message": "这个式子暂时无法检查，可以修改写法。目前支持因式分解与分式化简。"}
    a["hints"] = hints_for(a)
    a["h3_leaks"] = [i + 1 for i, h in enumerate(a["hints"][:2]) if h3_leak(h, a.get("target"))]
    if a["h3_leaks"]:
        # 第 1、2 级提示泄露了答案：换成不含答案的通用提示。接入模型后改为让模型重写并复检。
        a["hints"][:2] = [GENERIC_H1, GENERIC_H2]
    try:
        a["visual_svg"] = build_visual(read["problem"], a)
    except Exception:
        a["visual_svg"] = None
    a["card"] = knowledge_card(a) if a.get("cause") else None
    return {"ok": True, "analysis": a}


def verify_equal(question, answer):
    """SymPy 验算：答案与题干恒等才放行。用于变式题和示例答案，验算不过的题丢弃。"""
    try:
        q, a = parse(question), parse(answer)
    except ParseError:
        return False
    return cancel(together(q - a)) == 0


def prepare_lesson(problem):
    """只有题干时准备教学上下文，不虚构学生作答或错误。"""
    from .profile import kps_used
    analysis = analyze(problem, [])
    if analysis.get('status') == 'unreadable':
        return {'ok':False,'analysis':analysis,'message':'题目中的式子暂时无法识别，请核对符号或重新上传。'}
    used = kps_used(problem)
    kp = next((key for key in ('R1','F1','F2','F3','F4','F5') if key in used), 'F1')
    first = {'F1':'先找一找，每一项里有没有相同的因式？',
             'F2':'先数一数有几项，再看看是否是两个平方相减。',
             'F3':'观察首尾两项是否都是平方，再核对中间项。',
             'F4':'先提公因式，再检查每个括号还能不能继续分解。',
             'R1':'先把分子分母看成整体，再分别分解成乘积。'}
    title, body, tip = KNOWLEDGE_CARDS.get(kp, KNOWLEDGE_CARDS['GEN'])
    analysis.update(status='not_attempted', cause=None, lesson_kp=kp, hints=[first.get(kp,GENERIC_H1), body,
                    '按上述规则分解或化简，得到 '+analysis['target']+'。'], h3_leaks=[],
                    card={'kp':kp,'kp_name':KP[kp][0],'title':title,'body':body,'tip':tip})
    if any(h3_leak(text,analysis['target']) for text in analysis['hints'][:2]):
        analysis['hints'][:2]=[first.get(kp,GENERIC_H1),'先对应公式中的每一部分，再试着写出下一步。']
    try:
        analysis['visual_svg'] = build_visual(problem, analysis)
    except Exception:
        analysis['visual_svg'] = None
    return {'ok':True,'analysis':analysis}
