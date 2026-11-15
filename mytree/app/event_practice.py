"""Finite, explicit event facts. No model-generated truth labels."""
import random
import re
from .source_text import choice_parts, math_text


def event_kind(text):
    text = re.sub(r'\s', '', math_text(text)).rstrip('。')
    # Only degree typography is equivalent: preserve the integer and all other tokens.
    text = re.sub(r'(?<=\d)\^(?:\\circ|\{\\circ\})', '°', text)
    if text in ('打开手机正好显示8点', '明天会下雨'):
        return 'random'
    dice = re.fullmatch(r'抛掷正方体骰子一次[，,]?出现(\d{1,2})点', text)
    if dice:
        count = sum(n == int(dice[1]) for n in range(1, 7))
        return 'impossible' if count == 0 else 'random'
    if text == '抛掷正方体骰子一次，出现的点数小于7':
        return 'certain'
    triangle = re.fullmatch(r'任意画一个(?:平面)?三角形[，,]?它(?:的)?内角和(?:等于|为)(\d{1,3})(?:°|度)', text)
    if triangle:
        return 'certain' if int(triangle[1]) == 180 else 'impossible'
    urn = re.fullmatch(r'袋中有(\d{1,2})个红球和(\d{1,2})个蓝球[，,]任取1个球[，,]取到(红|蓝)球', text)
    if urn:
        red, blue = int(urn[1]), int(urn[2])
        if red + blue == 0 or red + blue > 50:
            return None
        count = red if urn[3] == '红' else blue
        return 'impossible' if count == 0 else 'certain' if count == red + blue else 'random'
    return None


def classify(problem):
    parts = choice_parts(problem)
    if not parts:
        return None
    stem, options = parts
    stem = re.sub(r'\s', '', math_text(stem))
    stem = re.sub(r'[（(][）)]$', '', stem).rstrip('？?：:')
    match = re.fullmatch(r'下列事件(?:中)?(?:是|属于)(确定|随机)事件的是', stem)
    if not match or any(event_kind(text) is None for text in options):
        return None
    return {'family': 'event-certainty', 'source_format': 'choice',
            'skills': ['区分必然、不可能和随机事件'],
            'reason': '和原题一样，区分必然事件、不可能事件与随机事件；确定事件包括前两种。'}


def generate(match, level, seed):
    rng = random.Random(seed)
    items = []
    for index in range(3):
        # Both kinds of deterministic event are tested, not just "will happen".
        deterministic = ('certain', 'impossible')[index % 2]
        a, b = rng.randint(1, 9), rng.randint(1, 9)
        positive = f'袋中有{a}个红球和0个蓝球，任取1个球，取到红球'
        negative = f'袋中有0个红球和{b}个蓝球，任取1个球，取到红球'
        randoms = [f'抛掷正方体骰子一次出现{rng.randint(1,6)}点',
                   f'袋中有{a}个红球和{b}个蓝球，任取1个球，取到红球',
                   f'袋中有{a+1}个红球和{b+1}个蓝球，任取1个球，取到蓝球']
        if index == 2:
            query = 'random'
            texts = [randoms[1], positive, negative,
                     f'任意画一个平面三角形，它的内角和等于{rng.choice([90,360])}°']
        else:
            query = 'deterministic'
            texts = [positive if deterministic == 'certain' else negative, *randoms]
        rng.shuffle(texts)
        kinds = [event_kind(text) for text in texts]
        correct = [i for i, kind in enumerate(kinds)
                   if (kind == 'random' if query == 'random' else kind in ('certain','impossible'))]
        if len(correct) != 1 or None in kinds:
            raise ValueError('事件事实或唯一答案未通过核验')
        answer = 'ABCD'[correct[0]]
        title = '随机' if query == 'random' else '确定'
        prompt = f'下列事件是{title}事件的是（　）\n\n' + '\n\n'.join(f'{label}．{text}' for label,text in zip('ABCD',texts))
        explanation = '一定发生的是必然事件，一定不发生的是不可能事件；这两类都是确定事件。可能发生也可能不发生的才是随机事件。'
        item = {'q':prompt,'question':prompt,'question_md':prompt,'prompt':prompt,
                'a':answer,'answer':answer,'answer_latex':answer,'expected':answer,
                'grading':'choice','answer_kind':'choice','domain':[],
                'choice_options':dict(zip('ABCD',texts)), 'event_query':query,
                'matching':{**match,'verification':'explicit-event-facts-and-unique-choice'},
                'match_reason':match['reason'],'difficulty_level':max(1,level)+(index==2),
                'is_transfer':index==2,'difficulty_features':match['skills'],
                'hints':['先判断每个事件是一定发生、一定不发生，还是两种情况都有可能。',
                         explanation, explanation+f'本题应选 {answer}。']}
        items.append(item)
    return items
