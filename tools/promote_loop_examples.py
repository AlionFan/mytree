#!/usr/bin/env python3
"""Capture contract-valid Agent envelopes from the isolated real HTTP loop log.

Keeps stage-A design/projection examples intact; runtime evidence takes priority
in validation. Local fake upstream is always disclosed as such.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'mytree'))
from app import contract


def main():
    source = ROOT / 'docs/evidence/phase-b/e2e-loop.json'
    raw = source.read_bytes()
    report = json.loads(raw)
    assert report['paid_model_calls'] == 0 and not report['real_photos_sent']
    digest = hashlib.sha256(raw).hexdigest()
    folder = ROOT / 'docs/architecture/examples/runtime'
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / ('capture-' + digest[:12] + '.json')
    archive.write_bytes(raw)
    chosen = {}
    for index, row in enumerate(report['http_trace']):
        request, response = row.get('request'), row.get('response')
        if row['path'] != '/api/agent' or row['http_status'] != 200 or response.get('status') == 'error':
            continue
        # Synthetic image content was intentionally scrubbed in the HTTP trace;
        # retain its matching contract-valid data-URL shape for this fixture.
        if request.get('operation') == 'recognize':
            request = json.loads(json.dumps(request))
            request['input']['image_data'] = 'data:image/png;base64,' + __import__('base64').b64encode(
                (source.parent / 'synthetic-question.png').read_bytes()).decode()
        contract.request(request)
        contract.response(response)
        chosen.setdefault(request['operation'], (index, request, response))
    for operation, (index, request, response) in chosen.items():
        value = {'provenance': {'kind': 'runtime_http', 'source': str(archive.relative_to(ROOT)),
                 'source_sha256': digest, 'trace_index': index, 'capture_script': 'tools/e2e_loop_check.py',
                 'scope': '真实本机HTTP；隔离档案；本地假模型；不代表真实OCR质量',
                 'request_image_restored_from': 'docs/evidence/phase-b/synthetic-question.png' if operation == 'recognize' else None},
                 'request': request, 'response': response}
        (folder / (operation.replace('.', '-') + '.example.json')).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'runtime_operations': sorted(chosen), 'source_sha256': digest}, ensure_ascii=False))


if __name__ == '__main__':
    main()
