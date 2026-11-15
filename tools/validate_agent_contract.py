#!/usr/bin/env python3
"""离线验证目标契约、23 操作样例与反例；不调用模型或业务接口。

运行：uv run --no-project --with jsonschema==4.25.1 python tools/validate_agent_contract.py
"""
import json
import hashlib
from datetime import datetime
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from jsonschema import Draft202012Validator

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"docs/architecture"


def check_growth(response):
    """INC-A6: arithmetic is a semantic check, not a JSON Schema capability."""
    output=response['output']
    rows=([output] if response['operation']=='growth.get' else output['entries'])
    for row in rows:
        if sum(row['components'].values()) != row['total']:
            raise ValueError('成长分三部分之和不等于总分')
        delta=row.get('weekly_delta',row.get('growth_delta',0))
        if delta>row['total']:
            raise ValueError('周期增量大于累计成长分')


def check_recognition_groups(output):
    selected={}
    for candidate in output.get('alternatives',[]):
        if candidate['selected']:
            group=candidate['group']
            selected[group]=selected.get(group,0)+1
            if selected[group]>1:
                raise ValueError('同一候选组不能选择多个读法')


def main():
    schema=json.loads((BASE/"agent-contract.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    defs=schema["$defs"]
    refs=[]
    def inspect(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key=="$ref":
                    if not item.startswith("#/$defs/") or item[len("#/$defs/"):] not in defs:
                        raise AssertionError("拒绝外部或无效引用："+item)
                    refs.append(item)
                else:inspect(item)
        elif isinstance(value,list):
            for item in value:inspect(item)
    inspect(schema)
    operations=schema["$defs"]["Operation"]["enum"]
    expected=['recognize','study','chat','practice.create','practice.check','schedule.set','profile.get','feedback.add','speech',
              'review.today','review.complete','card.list','card.edit','tree.get','tree.move',
              'profile.set_preference','profile.dispute','recommend.next',
              'quiz.start','quiz.answer','card.unlock','growth.get','leaderboard.get']
    assert len(operations)==23 and set(operations)==set(expected)
    assert defs['MasteryState']['enum']==['not_started','consolidating','stable']
    assert len(schema['x-operations'])==23
    assert [op['name'] for op in schema['x-operations']]==operations
    for op in schema['x-operations']:
        assert op['input'] in defs and op['output'] in defs
        for envelope,field,definition in [('AgentRequest','input',op['input']),('AgentResponse','output',op['output'])]:
            routed=[rule['then']['properties'][field]['$ref']
                    for rule in defs[envelope]['allOf']
                    if rule.get('if',{}).get('properties',{}).get('operation',{}).get('const')==op['name']
                    and '$ref' in rule.get('then',{}).get('properties',{}).get(field,{})]
            assert routed==['#/$defs/'+definition],(op['name'],envelope,routed)
    def validator(name):
        return Draft202012Validator({'$schema':schema['$schema'],'$defs':defs,'$ref':'#/$defs/'+name})
    valid=[];invalid=[];covered=set();statuses=set();non_drag=False;runtime_operations=set()
    for folder in ('current','design','runtime'):
        for path in sorted((BASE/'examples'/folder).glob('*.example.json')):
            fixture=json.loads(path.read_text())
            assert fixture['provenance']['kind'] in ('current_http_projection','synthetic_design','runtime_http')
            if folder=='current':
                assert fixture['provenance']['kind']=='current_http_projection'
                source=ROOT/fixture['provenance']['source']
                assert source.exists()
            elif folder=='design':
                assert fixture['provenance']['kind']=='synthetic_design'
            else:
                provenance=fixture['provenance']
                assert provenance['kind']=='runtime_http'
                source=(ROOT/provenance['source']).resolve()
                assert source.is_relative_to((BASE/'examples/runtime').resolve())
                raw=source.read_bytes()
                assert hashlib.sha256(raw).hexdigest()==provenance['source_sha256']
                trace=json.loads(raw)['http_trace'][provenance['trace_index']]
                assert trace['method']=='POST' and trace['path']=='/api/agent' and trace['http_status']==200
                assert fixture['response']==trace['response'], '运行样例响应与原HTTP记录不一致'
                original=json.loads(json.dumps(fixture['request']))
                if original['operation']=='recognize':
                    original['input']['image_data']='<synthetic-image omitted from trace>'
                assert original==trace['request'], '运行样例请求与原HTTP记录不一致'
                runtime_operations.add(original['operation'])
            request,response=fixture['request'],fixture['response']
            for name,payload in [('AgentRequest',request),('AgentResponse',response)]:
                errors=sorted(validator(name).iter_errors(payload),key=lambda e:list(map(str,e.absolute_path)))
                if errors:
                    raise AssertionError(str(path.relative_to(ROOT))+' '+name+': '+ '\n'.join(f'{list(e.absolute_path)} {e.message}' for e in errors))
                valid.append(str(path.relative_to(ROOT))+':'+name)
            assert request['operation']==response['operation']
            assert request['request_id']==response['request_id']
            if request['operation'] in ('growth.get','leaderboard.get'):
                check_growth(response)
            covered.add(request['operation']);statuses.add(response['status'])
            if request['operation']=='tree.move' and request['input']['method'] in ('keyboard','menu'):
                non_drag=bool(response['output']['undo']['token'])
    for path in sorted((BASE/'examples/auxiliary').glob('*.example.json')):
        fixture=json.loads(path.read_text())
        for item in fixture['payloads']:
            errors=list(validator(item['schema']).iter_errors(item['payload']))
            assert not errors,(path.name,item['schema'],[error.message for error in errors])
            if item['schema']=='RecognizeOutput':check_recognition_groups(item['payload'])
            valid.append(str(path.relative_to(ROOT))+':'+item['schema'])
    for path in sorted((BASE/'examples/invalid').glob('*.json')):
        fixture=json.loads(path.read_text())
        semantic=fixture['schema'] in ('GrowthArithmetic','RecognitionGroups')
        if semantic:
            shape='AgentResponse' if fixture['schema']=='GrowthArithmetic' else 'RecognizeOutput'
            assert not list(validator(shape).iter_errors(fixture['payload'])), '语义反例必须先通过Schema形状检查'
            try:
                (check_growth if fixture['schema']=='GrowthArithmetic' else check_recognition_groups)(fixture['payload'])
                errors=[]
            except ValueError as error:
                errors=[str(error)]
        else:
            errors=list(validator(fixture['schema']).iter_errors(fixture['payload']))
        assert errors,'应被拒绝的样例通过了：'+str(path)
        invalid.append({'file':str(path.relative_to(ROOT)),'reason':fixture['reason'],'errors':len(errors),
                        'validation_layer':('semantic_arithmetic' if fixture['schema']=='GrowthArithmetic' else 'semantic_recognition_groups') if semantic else 'json_schema'})
    assert covered==set(expected),(set(expected)-covered)
    assert statuses=={'ok','needs_confirmation','partial','error'},statuses
    assert non_drag
    assert len(invalid)>=6
    result={'checked_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
            'schema_sha256':hashlib.sha256((BASE/'agent-contract.schema.json').read_bytes()).hexdigest(),
            'schema_valid':True,'operation_count':len(operations),'definition_count':len(defs),'local_refs_checked':len(refs),
            'valid_payloads':len(valid),'rejected_examples':len(invalid),'statuses':sorted(statuses),
            'non_drag_tree_move':non_drag,'covered_operations':sorted(covered),'validations':valid,'counterexamples':invalid,
            'runtime_http_operations':sorted(runtime_operations),'design_or_projection_only_operations':sorted(set(expected)-runtime_operations),
            'growth_arithmetic_checked':True,
            'limits':['运行样例逐字对照真实本机HTTP归档；本地假模型，不代表OCR质量','阶段A设计与旧接口投影保留为历史，不能代替当前运行证据','JSON Schema不计算成长分总和；本脚本单独验证算术','JSON Schema不证明数学结论、身份授权、事实引用存在或提醒实际送达']}
    (BASE/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('validations','counterexamples')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
