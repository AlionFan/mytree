"""Conservative presentation adapters; never remove mathematical conditions."""
import re


def math_text(text):
    for token in (r'\(', r'\)', r'\[', r'\]', '$'):
        text = text.replace(token, '')
    return text.strip()


def choice_parts(text):
    """Accept exactly four ordered labelled options; keep their complete text."""
    text = text.translate(str.maketrans('ＡＢＣＤ', 'ABCD'))
    labels = list(re.finditer(r'(?<![A-Za-z])([ABCD])\s*[.．。、、:：]', text))
    if [m[1] for m in labels] != list('ABCD'):
        return None
    options = []
    for index, label in enumerate(labels):
        end = labels[index+1].start() if index < 3 else len(text)
        option = text[label.end():end].strip()
        if not option or len(option) > 400 or re.search(r'\n\s*\d+[.．、]', option):
            return None
        options.append(option)
    stem = re.sub(r'^\s*\d{1,2}[.．。、、]\s*', '', text[:labels[0].start()]).strip()
    return stem, options
