#!/usr/bin/env python3
"""收集阶段 A 契约的现有接口输出来源；不调用真实模型或修改演示档案。"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"docs/architecture/examples"


def main():
    source=ROOT/"docs/evidence/junior/live-browser-results.json"
    archive=json.loads(source.read_text())
    records={}
    paths={"study":"/api/study","chat":"/api/chat","practice.create":"/api/practice",
           "practice.check":"/api/practice/check","profile.get":"/api/profile","feedback.add":"/api/feedback"}
    for operation,path in paths.items():
        candidates=[(i,r) for i,r in enumerate(archive["responses"]) if r["path"]==path and r["status"]==200]
        index,row=candidates[-1] if operation=="profile.get" else candidates[0]
        records[operation]={"source":str(source.relative_to(ROOT)),"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
                            "pointer":f"/responses/{index}/body","http_status":row["status"],
                            "capture_kind":"archived_live_http","response":copy.deepcopy(row["body"])}
    vision=ROOT/"docs/evidence/junior/gpt-ocr-response.json"
    records["recognize"]={"source":str(vision.relative_to(ROOT)),"source_sha256":hashlib.sha256(vision.read_bytes()).hexdigest(),
                           "pointer":"/","http_status":200,"capture_kind":"archived_live_http",
                           "response":json.loads(vision.read_text())}

    # 仅启动临时档案的现有服务，两个调用均不经过模型；不占用产品的 8000 端口。
    sys.path[:0]=[str(ROOT/"mytree"),str(ROOT/"mytree/tests")]
    from test_all import _serve,_req
    from app import ai
    with tempfile.TemporaryDirectory() as folder,patch("app.profile._PATH",str(Path(folder)/"profile.json")),patch("app.ai.complete",side_effect=AssertionError("阶段 A 捕获禁止调用模型")):
        server,base=_serve()
        try:
            for operation,path,body in [
                ("schedule.set","/api/availability",{"student":"contract_sample","availability":{"days":[2,5],"time":"18:15"}}),
                ("speech","/api/speech",{"student":"contract_sample"})]:
                status,raw=_req(base,"POST",path,body)
                records[operation]={"source":"tools/capture_agent_examples.py","implementation_source":"mytree/app/server.py","pointer":path,"http_status":status,
                                    "capture_note":"现场生成，脚本 tools/capture_agent_examples.py；未留存原始 HTTP 响应字节，已解析的 JSON 在本记录 response 字段保留。",
                                    "raw_http_response_archived":False,"parsed_json_response_retained":True,
                                    "capture_kind":"isolated_current_http","request":body,"response":json.loads(raw)}
        finally:
            server.shutdown();server.server_close()
    (OUTPUT/"current").mkdir(parents=True,exist_ok=True)
    target=OUTPUT/"current/current-http-sources.json"
    target.write_text(json.dumps({"scope":"现有 HTTP 输出的来源，不是新统一入口的运行记录；未新增付费调用。",
                                 "records":records},ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"output":str(target),"operations":list(records),"count":len(records),
                      "model_calls":0,"production_profile_writes":0},ensure_ascii=False))


if __name__=="__main__":main()
