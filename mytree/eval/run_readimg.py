"""读图评测：对 eval/readimg 里的每张图调用真实的 ai.recognize，比对标准答案。
三层指标：
  逐行：题干和每行作答，去掉空格和乘号后是否一字不差（读图本身的准确率）。
  等价：每行在数学上是否等价（形式不同但值相同，例如 (x+1)(x+1) 读成 (x+1)^2）。
  诊断：用读到的内容跑校验，状态、卡点行、错因是否与用标准答案跑出的一致（读错造成的实际后果）。
另外统计：读错时有没有被标成"需要确认"（会让孩子核对）。读错又没标，是最危险的静默错误。
用法：python eval/run_readimg.py MODEL [MODEL ...] [--only 01,10]"""
import base64
import dataclasses
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import ai  # noqa: E402
from sympy import srepr  # noqa: E402

from app.mathcheck import ParseError, analyze, equiv, parse  # noqa: E402

IMG = ROOT / 'eval' / 'readimg'
RESULTS = ROOT / 'eval' / 'results'


def norm(s):
    return re.sub(r'\s|\*', '', (s or '').replace('−', '-').replace('（', '(').replace('）', ')'))


def same_form(a, b):
    """同一个式子树：多余的括号、空格、省略的乘号不算差异；(x+1)(x+1) 与 (x+1)^2 仍算不同。"""
    try:
        return srepr(parse(a, evaluate=False)) == srepr(parse(b, evaluate=False))
    except (ParseError, ValueError, TypeError):
        return norm(a) == norm(b)


def same_math(a, b):
    try:
        return bool(equiv(parse(a), parse(b)))
    except (ParseError, ValueError, TypeError):
        return False


def verdict(problem, steps):
    try:
        a = analyze(problem, steps)
    except Exception:  # 读错的内容可能让校验器报任何错，一律算"没有诊断"
        return ('error', None, None)
    return (a.get('status'), a.get('first_error'), a.get('cause'))


def run_one(model, case, cfg):
    data = 'data:image/jpeg;base64,' + base64.b64encode((IMG / case['file']).read_bytes()).decode()
    started = time.monotonic()
    out = {'id': case['id'], 'note': case['note'], 'model': model}
    try:
        r = ai.recognize(data, dataclasses.replace(cfg, vision=model))
    except ai.ModelError as e:
        out.update(ok=False, code=e.code, seconds=round(time.monotonic() - started, 1))
        return out
    except Exception as e:  # noqa: BLE001
        out.update(ok=False, code=type(e).__name__, seconds=round(time.monotonic() - started, 1))
        return out
    gp, gs = case['problem'], case['steps']
    rp, rs = r['problem'], r['steps']
    line_exact = same_form(rp, gp) and len(rs) == len(gs) and all(same_form(a, b) for a, b in zip(rs, gs))
    line_equiv = same_math(rp, gp) and len(rs) == len(gs) and all(same_math(a, b) for a, b in zip(rs, gs))
    flagged = bool(r['uncertain_lines'] or r['warnings'] or not r['supported'] or r['multiple_questions'])
    diag_ok = verdict(rp, rs) == verdict(gp, gs)
    out.update(ok=True, exact=line_exact, equiv=line_equiv, diag_ok=diag_ok, flagged=flagged,
               seconds=r['meta']['seconds'], tokens=r['meta']['usage'].get('total_tokens'),
               read={'problem': rp, 'steps': rs, 'uncertain': r['uncertain_lines']},
               truth={'problem': gp, 'steps': gs})
    return out


def summarize(model, rows):
    done = [r for r in rows if r['ok']]
    n = len(rows)
    wrong = [r for r in done if not r['exact']]
    silent = [r for r in wrong if not r['flagged']]
    bad_diag = [r for r in done if not r['diag_ok']]
    secs = sorted(r['seconds'] for r in done)
    toks = [r['tokens'] for r in done if r['tokens']]
    return {
        'model': model, 'n': n, 'failed_calls': n - len(done),
        'exact': sum(r['exact'] for r in done), 'equiv': sum(r['equiv'] for r in done),
        'diag_ok': sum(r['diag_ok'] for r in done), 'wrong': len(wrong),
        'wrong_but_flagged': len(wrong) - len(silent), 'silent_wrong': len(silent),
        'diag_wrong': len(bad_diag),
        'p50_s': secs[len(secs) // 2] if secs else None, 'max_s': secs[-1] if secs else None,
        'avg_tokens': round(sum(toks) / len(toks)) if toks else None,
    }


def main(argv):
    only = None
    models = []
    it = iter(argv)
    for a in it:
        if a == '--only':
            only = set(next(it).split(','))
        else:
            models.append(a)
    cases = json.loads((IMG / 'manifest.json').read_text())
    if only:
        cases = [c for c in cases if c['id'] in only]
    cfg = ai.settings()
    if not cfg.key:
        raise SystemExit('没有配置密钥')
    RESULTS.mkdir(exist_ok=True)
    report = {'when': time.strftime('%Y-%m-%d %H:%M:%S'), 'images': len(cases), 'models': {}}
    for model in models:
        with ThreadPoolExecutor(2) as pool:  # ai.py 内部同时只放行 2 个请求
            rows = list(pool.map(lambda c: run_one(model, c, cfg), cases))
        s = summarize(model, rows)
        report['models'][model] = {'summary': s, 'rows': rows}
        print(json.dumps(s, ensure_ascii=False), flush=True)
    stamp = time.strftime('%H%M%S')
    path = RESULTS / f'readimg-{stamp}.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print('详细结果：', path.relative_to(ROOT))


if __name__ == '__main__':
    main(sys.argv[1:])
