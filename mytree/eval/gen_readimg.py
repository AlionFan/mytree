"""合成「手机拍的手写错题」评测图，只用于测读图链路。不含任何真实孩子的数据。
分式画成上下叠放，次方画成抬高的小字，再加旋转、透视、阴影、噪点、压缩，模拟手机拍照。
用法：python eval/gen_readimg.py   （固定随机种子，重复运行得到同一批图）"""
import json
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent / 'readimg'
FONT_DIRS = ['/System/Library/Fonts/Supplemental', '/System/Library/Fonts', '/Library/Fonts']
FONTS = [('Bradley Hand Bold.ttf', 0), ('Noteworthy.ttc', 1), ('MarkerFelt.ttc', 0)]

# (编号, 题干, 学生作答每行, 说明)。作答里故意包含常见错误，读图不能把它们"改对"。
CASES = [
    ('01', 'x^2-9', ['(x-3)^2'], '平方差写成完全平方'),
    ('02', '3x^2+6x', ['3x(x+2)'], '做对'),
    ('03', '2x^2-8', ['2(x^2-4)'], '没分解彻底'),
    ('04', 'x^2+6x+9', ['(x+3)^2'], '做对'),
    ('05', '6x^2+12x', ['3x(2x+4)'], '公因式没提干净'),
    ('06', 'x^2-5x+6', ['(x+2)(x+3)'], '符号错'),
    ('07', 'a^2-b^2', ['(a-b)^2'], '两个字母'),
    ('08', '4x^2-25', ['(2x+5)(2x-5)'], '做对，系数 4 和 25'),
    ('09', 'x^3-x', ['x(x^2-1)', 'x(x+1)(x-1)'], '多行，做对'),
    ('10', '(x^2-4)/(x+2)', ['(x+2)(x-2)/(x+2)', 'x-2'], '分式，做对'),
    ('11', '(x^2-9)/(x^2+3x)', ['(x+3)(x-3)/(x(x+3))', '(x-3)/x'], '分式，分母有 x'),
    ('12', '(x+2)/(x^2+2)', ['x/x^2'], '约了加减的项'),
    ('13', '(2x+4)/(x^2-4)', ['2(x+2)/((x+2)(x-2))', '2/(x-2)'], '分式，多行'),
    ('14', 'x^2+2x+1', ['(x+1)(x+1)'], '没写成平方，等价'),
    ('15', '9x^2-6x+1', ['(3x-1)^2'], '做对，系数 9'),
    ('16', '5x^2y-10xy^2', ['5xy(x-2y)'], '多字母多次方，做对'),
    ('17', '3a^2-12', ['3(a^2-4)', '3(a+2)(a-2)'], '多行，做对'),
    ('18', 'x^2-1', ['(x+1)(x+1)'], '平方差写成两个相同因式'),
]


def find_font(name, index, size):
    for d in FONT_DIRS:
        p = Path(d) / name
        if p.exists():
            return ImageFont.truetype(str(p), size, index=index)
    raise SystemExit(f'找不到字体 {name}')


def strip_paren(s):
    if s.startswith('(') and s.endswith(')'):
        depth = 0
        for i, c in enumerate(s):
            depth += (c == '(') - (c == ')')
            if depth == 0 and i < len(s) - 1:
                return s
        return s[1:-1]
    return s


def split_frac(e):
    depth = 0
    for i, c in enumerate(e):
        depth += (c == '(') - (c == ')')
        if c == '/' and depth == 0:
            return strip_paren(e[:i]), strip_paren(e[i + 1:])
    return None


def tokens(e):
    out, i = [], 0
    while i < len(e):
        c = e[i]
        if c == '*':
            i += 1
        elif c == '^':
            j = i + 1
            while j < len(e) and e[j].isdigit():
                j += 1
            j = max(j, i + 2)
            out.append((e[i + 1:j], True))
            i = j
        else:
            out.append((c, False))
            i += 1
    return out


class Pen:
    def __init__(self, rng, draw, font, small, color):
        self.rng, self.d, self.font, self.small, self.color = rng, draw, font, small, color

    def plain(self, x, base, e, dry=False):
        for text, sup in tokens(e):
            f = self.small if sup else self.font
            if not dry:
                dy = self.rng.randint(-3, 3) - (int(self.font.size * 0.42) if sup else 0)
                self.d.text((x, base + dy), text, font=f, fill=self.color, anchor='ls')
            x += f.getlength(text) + 3
        return x

    def line(self, x, base, e):
        """画一行。分式上下叠放。返回行宽。"""
        fr = split_frac(e)
        if not fr:
            return self.plain(x, base, e) - x
        num, den = fr
        wn, wd = self.plain(0, 0, num, True), self.plain(0, 0, den, True)
        w = max(wn, wd) + 24
        bar = base - int(self.font.size * 0.3)
        self.plain(x + (w - wn) / 2, bar - 14, num)
        self.plain(x + (w - wd) / 2, bar + int(self.font.size * 0.95), den)
        self.d.line([(x, bar), (x + w, bar + self.rng.randint(-3, 3))], fill=self.color, width=4)
        return w


def render(case, seed):
    cid, problem, steps, _ = case
    rng = random.Random(seed)
    name, idx = FONTS[seed % len(FONTS)]
    font, small = find_font(name, idx, 66), find_font(name, idx, 40)
    color = rng.choice([(25, 35, 130), (30, 30, 35), (95, 95, 105)])  # 蓝圆珠笔、黑笔、铅笔
    rows = [(f'{rng.choice(["1.", "(2)", "3)"])} ' + problem, problem)]
    use_eq = rng.random() < 0.5  # 手写字体没有中文字形，所以不写「解：」
    for i, s in enumerate(steps):
        rows.append((('= ' if use_eq or i else '') + s, s))
    heights = [270 if split_frac(r[1]) else 150 for r in rows]
    W, H = 1100, sum(heights) + 170
    img = Image.new('RGB', (W, H), (250, 248, 240))
    d = ImageDraw.Draw(img)
    for y in range(60, H, 62):
        d.line([(0, y), (W, y)], fill=(190, 205, 225), width=2)
    d.line([(90, 0), (90, H)], fill=(215, 130, 130), width=3)
    pen, y = Pen(rng, d, font, small, color), 110
    for (text, _), h in zip(rows, heights):
        prefix, body = '', text
        if '/' in text and split_frac(text.split(' ', 1)[-1].lstrip('= ')):
            lead = text[: len(text) - len(text.split(' ', 1)[-1].lstrip('= '))]
            prefix, body = lead, text[len(lead):]
        x = pen.plain(130, y + (h - 150) // 2, prefix) if prefix else 130
        pen.line(x, y + (h - 150) // 2 + 20, body) if prefix else pen.line(130, y + (h - 150) // 2, body)
        y += h
    return photo_effects(img, rng)


def photo_effects(img, rng):
    W, H = img.size
    img = img.rotate(rng.uniform(-2.5, 2.5), resample=Image.BICUBIC, fillcolor=(120, 118, 112), expand=False)
    j = lambda: rng.uniform(-0.06, 0.06)
    a = [1 + j(), j() / 2, 0, j() / 2, 1 + j(), 0, j() / 1500, j() / 1500]
    img = img.transform((W, H), Image.PERSPECTIVE, a, Image.BICUBIC, fillcolor=(120, 118, 112))
    shade = Image.linear_gradient('L').rotate(rng.choice([0, 90, 180, 270])).resize((W, H))
    low = rng.randint(175, 215)  # 每次只取一个随机数；放进 lambda 会让每个灰度值各取一次，画出竖条纹
    shade = shade.point(lambda v: int(low + v * (255 - low) / 255)).convert('RGB')
    img = ImageChops.multiply(img, shade)
    noise = Image.effect_noise((W, H), rng.randint(10, 22)).convert('RGB')
    img = Image.blend(img, ImageChops.multiply(img, noise), 0.18)
    return img.filter(ImageFilter.GaussianBlur(rng.uniform(0.5, 1.1)))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for n, case in enumerate(CASES):
        img = render(case, seed=1000 + n)
        path = OUT / f'{case[0]}.jpg'
        img.save(path, 'JPEG', quality=rng_q(n))
        manifest.append({'id': case[0], 'file': path.name, 'problem': case[1], 'steps': case[2], 'note': case[3]})
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f'生成 {len(manifest)} 张到 {OUT}')


def rng_q(n):
    return 62 + (n * 7) % 24


if __name__ == '__main__':
    main()
