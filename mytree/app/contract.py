"""Runtime validation against the shared Agent contract; no transport or storage."""
from functools import lru_cache
import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[2] / 'docs/architecture/agent-contract.schema.json'


class ContractError(ValueError):
    """A fixed, safe message rather than the validator's input-containing repr."""


@lru_cache(maxsize=2)
def _validators(revision):
    schema = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
    def local_refs(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == '$ref':
                    if not isinstance(item, str) or not item.startswith('#/$defs/') or item[8:] not in schema['$defs']:
                        raise ContractError('接口定义含不受支持的引用')
                else:
                    local_refs(item)
        elif isinstance(value, list):
            for item in value:
                local_refs(item)
    local_refs(schema)
    Draft202012Validator.check_schema(schema)
    return {
        name: Draft202012Validator({
            '$schema': schema['$schema'], '$defs': schema['$defs'],
            '$ref': '#/$defs/' + name,
        }) for name in schema['$defs']
    }


def _check(name, payload):
    validator = _validators(SCHEMA_PATH.stat().st_mtime_ns)[name]
    if next(validator.iter_errors(payload), None) is not None:
        raise ContractError('请求字段或取值不符合学习接口约定' if name == 'AgentRequest'
                            else '学习结果没有通过结构检查，请重试')
    return payload


def request(payload):
    return _check('AgentRequest', payload)


def response(payload):
    return _check('AgentResponse', payload)


def definition(name, payload):
    """Validate an operation or auxiliary HTTP definition from the same schema."""
    return _check(name, payload)
