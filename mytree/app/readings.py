"""DESIGN-001: compare OCR alternatives with the student's own writing.

This module has no model, grading, profile, or answer-key dependency. A match
means consistency between transcribed lines; it never means mathematical truth.
"""
import copy
import re

import sympy as sp

from .formulas import solution_set


_CROSSED = re.compile(r'\[划掉[:：]([^\[\]]{0,500})\]')
_MATH = re.compile(r'\\\((.*?)\\\)|\\\[(.*?)\\\]|\$([^$]+)\$', re.S)
_ID = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
_KINDS = {'integer_list', 'repeat', 'previous'}


def _without_crossed(text):
    return _CROSSED.sub('', text).strip()


def _normal(text):
    text = _without_crossed(text)
    for before, after in ((r'\left', ''), (r'\right', ''), (r'\leq', '<='),
                          (r'\geq', '>='), (r'\le', '<='), (r'\ge', '>='),
                          ('≤', '<='), ('≥', '>='), ('−', '-'), ('＝', '='),
                          (r'\(', ''), (r'\)', ''), (r'\[', ''), (r'\]', ''),
                          ('$', ''), (r'\,', '')):
        text = text.replace(before, after)
    return re.sub(r'\s+', '', text)


def _math_text(text):
    blocks = _MATH.findall(text)
    if len(blocks) == 1:
        return next(value for value in blocks[0] if value)
    if blocks:
        raise ValueError('多个数学片段不能按单个式子核对')
    text = re.sub(r'^(?:结论|最终答案|最后答案|答案|解集|所以|解得|得|解|为|是|[:：\s])+', '', text)
    if re.search(r'[\u3400-\u9fff]', text):
        raise ValueError('不是单个可核对的数学片段')
    return text.strip()


def _integer_list(quote):
    match = re.search(r'整数解(?:集)?(?:为|是|有)?\s*[:：]?\s*(.*)', quote)
    if not match:
        raise ValueError('没有明确的整数解列表')
    source = _normal(match[1]).replace(r'\{', '').replace(r'\}', '').strip('{}。；;')
    source = source.replace('，', ',').replace('、', ',')
    bounds = re.fullmatch(r'(-?\d{1,4})(?:\.\.|…|⋯)(-?\d{1,4})', source)
    if bounds:
        start, end = map(int, bounds.groups())
        if not 0 <= end - start <= 100:
            raise ValueError('整数列表范围超出核对限制')
        return set(range(start, end + 1))
    if not re.fullmatch(r'-?\d{1,4}(?:,-?\d{1,4}){0,100}', source):
        raise ValueError('整数列表不完整')
    return set(map(int, source.split(',')))


def _candidate_integers(text):
    values = solution_set(_math_text(text))
    if isinstance(values, sp.FiniteSet):
        if len(values) > 101 or any(value.is_integer is not True for value in values):
            raise ValueError('不是有界整数集合')
        return {int(value) for value in values}
    if not isinstance(values, sp.Interval) or values.start.is_finite is not True or values.end.is_finite is not True:
        raise ValueError('只能核对有界的不等式结论')
    start, end = int(sp.ceiling(values.start)), int(sp.floor(values.end))
    if values.left_open and start == values.start:
        start += 1
    if values.right_open and end == values.end:
        end -= 1
    if end - start > 100 or abs(start) > 10000 or abs(end) > 10000:
        raise ValueError('整数范围超出核对限制')
    return set(range(start, end + 1))


def _compare(candidate, evidence, lines):
    """None means unsupported or ungrounded evidence, never a vote for a value."""
    line, quote, kind = evidence.get('line'), evidence.get('quote'), evidence.get('kind')
    if type(line) is not int or not 1 <= line < len(lines) or line == candidate['line']:
        return None
    if not isinstance(quote, str) or not quote or len(quote) > 200 or kind not in _KINDS:
        return None
    # Do not permit the model to invent an evidential quote or reuse crossed-out ink.
    if not _normal(quote) or _normal(quote) not in _normal(lines[line]):
        return None
    try:
        if kind == 'integer_list':
            return _candidate_integers(candidate['text']) == _integer_list(quote)
        candidate_math, quoted_math = _math_text(candidate['text']), _math_text(quote)
        if kind == 'previous':
            # Copy an already written terminal term; do not evaluate its arithmetic.
            quoted_math = re.split('[=＝]', quoted_math)[-1]
        return _normal(candidate_math).lstrip('=') == _normal(quoted_math).lstrip('=')
    except (ValueError, TypeError, NotImplementedError, sp.PolynomialError):
        return None


def disambiguate(problem, steps, uncertain_lines=None, alternatives=None):
    """Return clean text and recomputed inference metadata; input is not mutated.

    Candidate `text` always replaces a whole line (0=problem, 1+=student work).
    A clear line stays as written even if another candidate matches later work.
    """
    if not isinstance(problem, str) or not isinstance(steps, list) or len(steps) > 30:
        raise ValueError('识别文本格式不正确')
    if any(not isinstance(text, str) or len(text) > 1500 for text in steps):
        raise ValueError('识别作答格式不正确')
    source = [problem, *steps]
    lines = [_without_crossed(text) for text in source]
    uncertain = set(uncertain_lines or [])
    if any(type(line) is not int or not 0 <= line < len(lines) for line in uncertain):
        raise ValueError('疑似位置格式不正确')
    alternatives = alternatives or []
    if not isinstance(alternatives, list) or len(alternatives) > 48:
        raise ValueError('候选数量超出限制')
    groups, ids = {}, set()
    for raw in alternatives:
        if not isinstance(raw, dict):
            raise ValueError('候选格式不正确')
        candidate = copy.deepcopy(raw)
        line, text = candidate.get('line'), candidate.get('text')
        if type(line) is not int or not 0 <= line < len(lines) or not isinstance(text, str) or not text.strip() or len(text) > (2000 if line == 0 else 1500):
            raise ValueError('候选行或文本不正确')
        if any(not isinstance(candidate.get(key), str) or not _ID.fullmatch(candidate[key]) for key in ('id', 'group')) or candidate['id'] in ids:
            raise ValueError('候选编号不正确或重复')
        ids.add(candidate['id'])
        evidence = candidate.get('evidence', [])
        if not isinstance(evidence, list) or len(evidence) > 6 or any(not isinstance(item, dict) for item in evidence):
            raise ValueError('候选依据格式不正确')
        for item in evidence:
            if (type(item.get('line')) is not int or not 0 <= item['line'] <= 30
                    or not isinstance(item.get('quote'),str) or not 1 <= len(item['quote']) <= 200
                    or item.get('kind') not in _KINDS):
                raise ValueError('候选依据的行号、引用或类型不正确')
        evidence=[{key:item[key] for key in ('line','quote','kind')} for item in evidence]
        candidate = {key: candidate[key] for key in ('id', 'group', 'line', 'text')}
        candidate['text'] = _without_crossed(candidate['text'])
        candidate['evidence'] = evidence
        results = [_compare(candidate, item, lines) for item in evidence]
        candidate['consistency'] = 'conflict' if False in results else 'match' if True in results else 'unverified'
        candidate['selected'] = False
        groups.setdefault(candidate['group'], []).append(candidate)
    inferred, notes, output = False, [], []
    for group in groups.values():
        if not 2 <= len(group) <= 3 or len({candidate['line'] for candidate in group}) != 1:
            raise ValueError('每处需要同一行的2到3个候选')
        if len({_normal(candidate['text']) for candidate in group}) != len(group):
            raise ValueError('同一处的读法不能重复')
        line = group[0]['line']
        if sum(other[0]['line'] == line for other in groups.values()) != 1:
            raise ValueError('同一行的候选请合并为一组')
        ambiguous = line in uncertain or '?' in lines[line] or '？' in lines[line]
        matches = [candidate for candidate in group if candidate['consistency'] == 'match']
        if ambiguous and len(matches) == 1:
            chosen = matches[0]
            chosen['selected'] = True
            lines[line] = chosen['text']
            inferred = True
            grounded = [item['quote'] for item in chosen['evidence'] if _compare(chosen, item, [_without_crossed(t) for t in source]) is True]
            notes.append('我读作 $' + _math_text(chosen['text']) + '$，依据：你写的“' + '；'.join(grounded) + '”。这是推断，可以改成其他读法。')
        else:
            for candidate in group:
                candidate['selected'] = _normal(candidate['text']) == _normal(lines[line])
            if not ambiguous and matches and not any(candidate['selected'] for candidate in matches):
                notes.append('原行清楚，保留原样；与你后面写的内容矛盾，请选择你实际写的读法。')
            elif any(candidate['consistency'] == 'conflict' for candidate in group):
                notes.append('候选与你写的其他内容矛盾，或存在多个读法，请选择你实际写的读法。')
            else:
                notes.append('没有其他线索能唯一确定，请选择你实际写的读法。')
        output.extend(group)
    if any(_CROSSED.search(text) for text in source):
        notes.append('已排除明确标为划掉的内容，只保留重写内容。')
    # Preserve source-line numbering until all evidence has been checked.
    index_map = {0: 0}
    clean_steps = []
    for old, text in enumerate(lines[1:], 1):
        if text.strip():
            clean_steps.append(text)
            index_map[old] = len(clean_steps)
    retained = []
    for candidate in output:
        if candidate['line'] not in index_map:
            continue
        candidate['line'] = index_map[candidate['line']]
        candidate['evidence'] = [{**item, 'line': index_map[item['line']]} for item in candidate['evidence'] if item.get('line') in index_map]
        retained.append(candidate)
    return {'problem': lines[0], 'steps': clean_steps, 'inferred': inferred,
            'reading_evidence': '\n'.join(notes)[:3000], 'alternatives': retained,
            'uncertain_lines': sorted(index_map[line] for line in uncertain if line in index_map)}
