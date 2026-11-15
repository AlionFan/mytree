#!/usr/bin/env python3
"""Render the conversation fragment and remove unused remote preview helpers.

The skill renderer remains the source of standalone styles, tab behavior and state
storage. This diagram uses neither Lucide nor tooltips. Its offline export must
therefore omit those CDN helpers and disallow network resources in both frames.
"""
import argparse
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.frames = []
        self.remote = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'meta' and attributes.get('http-equiv', '').lower() == 'content-security-policy':
            if re.search(r'https?://', attributes.get('content', '')):
                self.remote.append((tag, 'network-csp', attributes['content']))
        if tag == 'iframe':
            frame = attributes.get('srcdoc') or attributes.get('data-srcdoc')
            if frame:
                self.frames.append(frame)
        for key in ('src', 'poster', 'srcset'):
            value = attributes.get(key, '')
            if re.search(r'(?:https?:)?//', value):
                self.remote.append((tag, key, value))
        if tag == 'link' and attributes.get('href', '').startswith(('http:', 'https:', '//')):
            self.remote.append((tag, 'href', attributes['href']))


def inspect(document):
    parsed = Resources()
    parsed.feed(document)
    found = list(parsed.remote)
    found += [('css', 'url', value) for value in re.findall(r'url\(\s*[\"\']?((?:https?:)?//[^)\s\"\']+)', document)]
    found += [('css', 'import', value) for value in re.findall(r'@import\s+[\"\']((?:https?:)?//[^\"\']+)', document)]
    for frame in parsed.frames:
        found.extend(inspect(frame))
    return found


def offline(document):
    parsed = Resources()
    parsed.feed(document)
    removed = 0
    for frame in parsed.frames:
        helpers = (r'@floating-ui/core@1\.7\.3/dist/floating-ui\.core\.umd\.min\.js|'
                   r'@floating-ui/dom@1\.7\.4/dist/floating-ui\.dom\.umd\.min\.js|'
                   r'lucide@1\.17\.0/dist/umd/lucide\.js')
        cleaned, count = re.subn(r'<script\b[^>]*\bsrc=[\"\']https://unpkg\.com/(?:' + helpers + r')[\"\'][^>]*>\s*</script>', '', frame)
        cleaned = restrict_csp(cleaned)
        document = document.replace(escape(frame), escape(cleaned))
        removed += count
    document = restrict_csp(document)
    remote = inspect(document)
    if remote:
        raise ValueError('Remote resource remains: ' + repr(remote))
    return document, removed


def restrict_csp(document):
    def replace(match):
        value = re.sub(r'\s+https?://[^\s;\"\']+', '', match[1])
        return '<meta http-equiv="Content-Security-Policy" content="' + value + '">'
    return re.sub(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', replace, document)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fragment', type=Path)
    parser.add_argument('--renderer', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'docs/architecture/agent-harness.html')
    args = parser.parse_args()
    if re.search(r'\bdata-(?:lucide|tooltip)\s*=', args.fragment.read_text()):
        raise ValueError('This export cannot remove helpers used by the fragment')
    with tempfile.NamedTemporaryFile(prefix='.agent-visual-', suffix='.html', dir=args.output.parent, delete=False) as temporary:
        staging = Path(temporary.name)
    try:
        subprocess.run([sys.executable, str(args.renderer), str(args.fragment), str(staging), '--title', '小树同学 · Agent 与学习闭环', '--force'], check=True)
        document, count = offline(staging.read_text())
        staging.write_text(document)
        staging.replace(args.output)
        # A second, unframed copy lets review tools inspect the actual controls.
        # Its state lasts only for this page view; the primary export retains the
        # renderer's host bridge and persistent standalone state mechanism.
        parsed = Resources()
        parsed.feed(document)
        if len(parsed.frames) != 1:
            raise ValueError('Expected exactly one rendered frame')
        review = parsed.frames[0].replace('__CODEX_VISUALIZATION_WIDGET_STATE__', '{"widgetState":null,"statePersistence":"none"}')
        if inspect(review):
            raise ValueError('Remote resources in direct review copy')
        review_path = args.output.with_name('agent-harness-review.html')
        review_path.write_text(review)
    finally:
        staging.unlink(missing_ok=True)
    print(json.dumps({'output': str(args.output), 'removed_unused_cdn_scripts': count,
                      'recursive_remote_resources': inspect(document), 'bytes': args.output.stat().st_size}))


if __name__ == '__main__':
    main()
