#!/usr/bin/env python3
"""从 PRD / 决策 / 架构契约生成 Xmind；不修改产品需求或业务代码。

包结构依据 Xmind 官方 SDK 的 content.json / metadata.json / manifest.json。
参考：https://github.com/xmindltd/xmind-sdk-js/blob/master/src/utils/dumper.ts
"""
import hashlib
import json
from pathlib import Path
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from uuid import NAMESPACE_URL, uuid5
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
COLORS = ["#2e6655", "#4c678a", "#8a6945", "#6f5a87", "#426c74", "#776343"]


def clean(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"[*`]", "", text).strip()


def short(text, length=43):
    text = clean(text)
    return text if len(text) <= length else text[:length-1] + "…"


def identity(key):
    return uuid5(NAMESPACE_URL, "hks-prd:" + key).hex


def topic(title, children=None, note="", key=None, folded=False, color=None, labels=None):
    node = {"id": identity(key or title), "class": "topic", "title": title}
    if children:
        node["children"] = {"attached": children}
    if note:
        node["notes"] = {"plain": {"content": note}}
    if folded and children:
        node["branch"] = "folded"
    if labels:
        node["labels"] = labels
    if color:
        node["style"] = {"id": identity((key or title) + ":style"), "properties": {
            "fo:color": color, "fo:font-family": "PingFang SC", "fo:font-weight": "bold"
        }}
    return node


def leaves(lines, prefix):
    return [topic(short(line), note=clean(line), key=f"{prefix}/{i}") for i, line in enumerate(lines)]


def section(source, number):
    match = re.search(rf"^## {number}\. .*?\n(.*?)(?=^## |\Z)", source, re.M | re.S)
    if not match:
        raise ValueError(f"PRD 第 {number} 节不存在，请同步生成器的分组")
    return match[1]


def table(source, prefix=None):
    rows = []
    for line in source.splitlines():
        if not line.startswith("|"):
            continue
        cells = [clean(c) for c in line.strip().strip("|").split("|")]
        if not cells or re.fullmatch(r"[- :]+", cells[0] or " "):
            continue
        if prefix and not cells[0].startswith(prefix):
            continue
        rows.append(cells)
    return rows


def sheet(title, branches, note, key):
    root = topic("小树同学 · " + title, branches, note=note, key=key+"/root", color="#2e6655")
    root["structureClass"] = "org.xmind.ui.map.unbalanced"
    root["style"]["properties"].update({"fo:font-size": "22pt"})
    return {"id": identity(key), "class": "sheet", "title": title, "rootTopic": root}


def grouped(title, children, index, key, note="", folded=False):
    return topic(title, children, note=note, key=key, color=COLORS[index % len(COLORS)], folded=folded)


def read_sources():
    candidates = [Path(__file__).resolve(), DOCS/"PRD.md", DOCS/"collaboration/decisions.md", DOCS/"collaboration/DESIGN-001.md",
                  DOCS/"collaboration/PRODUCT-001.md", DOCS/"collaboration/PRODUCT-002.md", DOCS/"collaboration/ARCH-001.md",
                  DOCS/"collaboration/B-PHASE.md", DOCS/"collaboration/B-DECISIONS.md",
                  DOCS/"architecture/agent-architecture.md", DOCS/"architecture/agent-contract.schema.json"]
    return {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8") for p in candidates if p.is_file()}


def build(sources):
    prd = sources["docs/PRD.md"]
    version = re.search(r"版本：([^　\s]+)", prd).group(1)
    built = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    hashes = {p: hashlib.sha256(s.encode()).hexdigest() for p, s in sources.items()}
    note = (f"PRD v{version}；生成时间 {built}\n"
            "来源：docs/PRD.md 与生效产品决策；本图是快照，不替代 PRD。\n"
            "PRD / 设计决定变更后运行 python3 tools/build_prd_xmind.py。\n"
            "节点备注保留原文；P0/P1 与待实现/待验收不是已完成功能声明。\n"
            f"PRD SHA256: {hashes['docs/PRD.md']}")
    requirements = {}
    for match in re.finditer(r"^### (FR-\d{3}) · (.*?)（(.*?)）\n(.*?)(?=^### |^## |\Z)", prd, re.M | re.S):
        rid, title, priority, body = match.groups()
        requirements[rid] = (title, priority, body.strip())
    defined = set(re.findall(r"^### (FR-\d{3})", prd, re.M))
    if set(requirements) != defined:
        raise ValueError("存在未能解析的 FR 需求，停止生成以避免漏项")
    groups = [
        ("错题采集与整理", [1,2,3,4,19]),
        ("知识探索与辅导", [5,6,7,13,14]),
        ("主动复习、画像与推荐", [8,9,20,23,24,26]),
        ("知识卡与孩子的树", [10,21,22]),
        ("树成长、排行与激励", [25,27]),
        ("数据、看板与终端", [11,12,15,16,17,18])
    ]
    feature_branches, feature_overview, assigned = [], [], set()
    for index, (name, numbers) in enumerate(groups):
        ids = [f"FR-{i:03d}" for i in numbers if f"FR-{i:03d}" in requirements]
        feature_overview.append(topic(name, leaves([f"{rid} {requirements[rid][0]}" for rid in ids], f"overview/group/{index}"), key=f"overview/group/{index}"))
        children = []
        for rid in ids:
            title, priority, body = requirements[rid]
            bullets = [line[2:] for line in body.splitlines() if line.startswith("- ")]
            children.append(topic(f"{rid} · {title}", leaves(bullets, f"feature/{rid}/rule"),
                                  note=clean(body), key=f"feature/{rid}", labels=[priority], folded=True))
        feature_branches.append(grouped(name, children, index, f"features/group/{index}"))
        assigned.update(ids)
    for rid in sorted(defined - assigned):
        title, priority, body = requirements[rid]
        feature_branches.append(topic(f"{rid} · {title}", note=clean(body), labels=[priority], key=f"feature/{rid}"))

    actors = table(section(prd,2))[1:]
    actor_nodes = [topic(row[0], leaves(["任务："+row[1], "边界："+row[2]], f"actors/{i}"), key=f"actor/{i}") for i,row in enumerate(actors)]
    phases = [row for row in table(section(prd,3))[1:] if len(row)==4]
    phase_nodes = [topic(short(row[0]), leaves(["优先级："+row[1],"当前："+row[2],"完成条件："+row[3]], f"phase/{i}"),
                         note="\n".join(row), key=f"phase/{i}", folded=True, labels=[row[1]]) for i,row in enumerate(phases)]
    dev = []
    for line in section(prd,9).splitlines():
        match = re.match(r"- \*\*(DEV-\d{3}) · (.*?)：\*\* (.*)", line)
        if match:
            rid,title,body=match.groups()
            dev.append(topic(f"{rid} · {title}", note=clean(body), key=f"dev/{rid}"))
    overview = sheet("01 产品全景", [
        grouped("产品目标与范围", leaves([
            "目标用户：学校学习和考试后积累错题的初中学生",
            "目标：整理错题，主动探索知识与卡点，持续复习",
            "会推：Agent 产出具体复习待办，终端负责提醒",
            "记得：学习者画像持续更新，说明事实与推断依据",
            "孩子是作者：答对检验获得知识卡，亲手编排树",
            "成长激励：知识积累长出枝叶，多用户比较树的成长",
            "当前：B阶段逐段实现，进度与待验收项见阶段任务画布"], "goal"), 0, "overview/goals", clean(section(prd,1))),
        grouped("角色与页面", actor_nodes, 1, "overview/actors"),
        grouped("学习闭环", leaves([
            "拍照 / 图片 / PDF → 预览、选页、框选",
            "识别、上下文消歧 → 核对确认 → AI 整理错题卡",
            "Agent 产出具体复习待办 → 终端提醒孩子",
            "孩子回忆、适度挑战 → 答对检验 / 迁移题 → 获得知识卡",
            "孩子拖动或用键盘编排 → 保存自己的知识树",
            "树成长与排行 → 成就反馈；整理笔记与关系 → 持续投入",
            "画像：事实 / 推断 / 偏好；复习改变下一次推荐",
            "迁移 / 有依据的进阶 → 新一轮错题与复习"], "flow"), 2, "overview/flow", clean(section(prd,4))),
        grouped("功能模块索引", feature_overview, 3, "overview/features", folded=True),
        grouped("已生效方向与协作", leaves([
            "Astra：方向、设计审查、优先级与监督验收",
            "Codex：修改、测试、自查与按意见返工",
            "读图：gpt-6.1-sol，不自动换其他读图模型",
            "DESIGN-001：上下文消歧；以设计记录中的状态为准",
            "多端调用同一 Agent；操作与字段以当前 Schema 为准",
            "A 阶段是需求与契约；后续由 Astra 分阶段指导"], "roles")+dev, 4, "overview/decisions", sources.get("docs/collaboration/decisions.md","")),
        grouped("交付阶段与现状", phase_nodes, 5, "overview/phases", folded=True)
    ], note, "sheet/overview")
    quality = []
    for row in table(section(prd,6),"NFR-"):
        quality.append(topic(f"{row[0]} · {short(row[1],32)}", leaves(["验收："+row[2]], "quality/"+row[0]),
                             note="\n".join(row[1:]), key="nfr/"+row[0]))
    feature_branches.append(grouped("质量、数据与体验边界", quality, 5, "features/quality"))
    features = sheet("02 功能需求与规则", feature_branches, note, "sheet/features")

    ac_nodes=[]
    for row in table(section(prd,8),"AC-"):
        code=row[0].split()[0]
        ac_nodes.append(topic(row[0], leaves(["关联："+row[1],"预期："+row[2],"参考："+row[3]],"ac/"+code),
                              note="\n".join(row[1:]), key="ac/"+code, folded=True))
    design = sources.get("docs/collaboration/DESIGN-001.md","")
    design_ac=[]
    for row in table(design,"AC-D"):
        design_ac.append(topic(row[0]+" · "+short(row[1],26), leaves(["预期："+row[2]],"design-ac/"+row[0]),
                               note="\n".join(row[1:]), key="design-ac/"+row[0]))
    pending=[]
    for i,row in enumerate(table(section(prd,10))[1:]):
        pending.append(topic(row[0], leaves(["已有："+row[1],"后续："+row[2]],f"pending/{i}"),
                             note="\n".join(row[1:]), key=f"pending/{i}", folded=True))
    acceptance = sheet("05 验收与后续", [
        grouped("AC-01～AC-12 主流程验收",ac_nodes,0,"acceptance/base"),
        grouped("DESIGN-001 专项验收",design_ac,1,"acceptance/design",clean(design)),
        grouped("待决与后续交接",pending,2,"acceptance/pending"),
        grouped("版本与证据边界",leaves([
            "本图是需求与设计快照，不是功能通过报告",
            "AI 分析 / 程序核验 / 真实掌握证据分开",
            "已下发 / 开发中 / 已验收分别记录",
            "设计问题由 Claude 决定，Codex 执行后回传证据",
            f"源 PRD 版本：{version}"],"snapshot"),3,"acceptance/snapshot",note)
    ],note,"sheet/acceptance")
    product=sources.get("docs/collaboration/PRODUCT-001.md","")
    arch_decision=sources.get("docs/collaboration/ARCH-001.md","")
    extra_ac=[]
    for source_name,source_text in [("PRODUCT-001",product),("PRODUCT-002",sources.get("docs/collaboration/PRODUCT-002.md","")),("ARCH-001",arch_decision)]:
        for row in table(source_text):
            if not row[0].startswith(("PROD-A","ARCH-A","INC-A","MOT-A","GROW-A")):
                continue
            label=short(row[1],42)
            if row[0]=="PROD-A2":label="操作总数23（数量由 INC-A2 覆盖）"
            if row[0]=="PROD-A5":label="解锁知识卡保留服务端核对的来源错题卡"
            if row[0]=="PROD-A9":label="文档表述与事实边界一致"
            if row[0]=="ARCH-A6":label="当前实现与目标设计分开，状态有来源"
            extra_ac.append(topic(row[0]+" · "+label,note=source_name+" 对应验收条款",key="extra-ac/"+row[0]))
    if extra_ac:
        acceptance['rootTopic']['children']['attached'].insert(2,grouped("产品与架构验收",extra_ac,4,"acceptance/product-architecture"))
    loop_status=[row for row in table(section(prd,4)) if re.fullmatch(r"C[1-5]",row[0])]
    if loop_status:
        acceptance['rootTopic']['children']['attached'].insert(0,grouped("新闭环 C1～C5 的真实差距",[
            topic(row[0]+" · "+short(row[1],32),leaves([row[2]],"closed-loop/"+row[0]),key="closed-loop/"+row[0])
            for row in loop_status],5,"acceptance/loop"))
    sheets=[overview,features]
    architecture = sources.get("docs/architecture/agent-architecture.md")
    if architecture:
        branches=[]
        for i,match in enumerate(re.finditer(r"^## (.*?)\n(.*?)(?=^## |\Z)",architecture,re.M|re.S)):
            title,body=match.groups()
            bullets=[line[2:] for line in body.splitlines() if line.startswith("- ")]
            branches.append(grouped(clean(title),leaves(bullets,f"architecture/{i}/item"),i,f"architecture/{i}",clean(body)))
        sheets.append(sheet("03 Agent 与 Harness",branches,note,"sheet/architecture"))
    contract_path="docs/architecture/agent-contract.schema.json"
    if contract_path in sources:
        schema=json.loads(sources[contract_path])
        definitions=schema['$defs']
        def definition_node(name,key,title=None):
            definition=definitions[name]
            properties=[]
            required=definition.get("required",[])
            for field,value in definition.get("properties",{}).items():
                description=value.get("description","")
                shape=value.get("type",value.get("$ref", "组合约束"))
                enum=value.get("enum")
                detail=[f"类型：{shape}"]
                if enum:detail.append("取值："+" / ".join(map(str,enum)))
                if description:detail.append(description)
                properties.append(topic(field+(" * 必填" if field in required else ""),leaves(detail,f"{key}/{field}/detail"),
                                        note=json.dumps(value,ensure_ascii=False,indent=2),key=f"{key}/{field}",folded=True))
            return topic(title or name,properties,note=json.dumps(definition,ensure_ascii=False,indent=2),key=key,folded=True)
        branches=[grouped("统一信封",[
            definition_node('AgentRequest','contract/envelope/request','请求：AgentRequest'),
            definition_node('AgentResponse','contract/envelope/response','响应：AgentResponse')],0,'contract/envelope')]
        op_groups=[('整理与探索',['recognize','study','chat']),('练习、检验与主动复习',['practice.create','practice.check','quiz.start','quiz.answer','schedule.set','review.today','review.complete']),
                   ('知识卡与个人树',['card.list','card.edit','card.unlock','tree.get','tree.move']),
                   ('持续画像与推荐',['profile.get','profile.set_preference','profile.dispute','feedback.add','recommend.next']),('语音',['speech'])]
        operations={op['name']:op for op in schema['x-operations']}
        assigned_ops={name for _,names in op_groups for name in names}
        extra_ops=[name for name in operations if name not in assigned_ops]
        if extra_ops:op_groups.append(('成长与激励',extra_ops))
        for i,(title,names) in enumerate(op_groups):
            op_nodes=[]
            for op_name in names:
                op=operations[op_name]
                op_nodes.append(topic(op_name,[definition_node(op['input'],'contract/op/'+op_name+'/input','输入 '+op['input']),
                                              definition_node(op['output'],'contract/op/'+op_name+'/output','输出 '+op['output'])],
                                      key='contract/op/'+op_name,folded=True,labels=['写操作' if op['writes'] else '只读']))
            branches.append(grouped(title,op_nodes,i+1,'contract/ops/'+str(i)))
        branches.append(grouped('公共规则',[
            topic('状态：ok / needs_confirmation / partial / error',key='contract/status'),
            topic('核验：verified / ai_review / unavailable',key='contract/verification'),
            topic('确认 / 错误时 effects=[]；幂等重放不重复写',key='contract/effects'),
            definition_node('Inference','contract/shared/inference','推断必须引用事实'),
            definition_node('StableEvidence','contract/shared/stable','stable 证据与初始阈值'),
            definition_node('UnlockEvidence','contract/shared/unlock','解锁：U1～U5 与服务端检验记录'),
            definition_node('GrowthComponents','contract/shared/growth','成长三部分：起点，待数据'),
            definition_node('Recommendation','contract/shared/recommend','推荐理由、事实与进阶依据')],0,'contract/shared'))
        auxiliaries=sorted({name for route in schema.get('x-http-adapter-routes',[]) if route['path']!='/api/agent' for name in ([route.get(field) for field in ('query','request','response')]+list(route.get('error_responses',{}).values())) if name in definitions})
        branches.append(grouped('辅助HTTP接口（不增加操作数）',[
            definition_node(name,'contract/aux/'+name) for name in auxiliaries],1,'contract/aux'))
        sheets.append(sheet("04 统一输入与输出",branches,note,"sheet/contract"))
    sheets.append(acceptance)
    phase_b=sources.get('docs/collaboration/B-PHASE.md','')
    if phase_b:
        tasks=[]
        for match in re.finditer(r'^### (T\d+.*?)\n(.*?)(?=^### |^## |\Z)',phase_b,re.M|re.S):
            title,body=match.groups()
            bullets=[line[2:] for line in body.splitlines() if line.startswith('- ')]
            tasks.append(topic(clean(title),leaves(bullets,'phase-b/'+title.split()[0]),note=clean(body),key='phase-b/task/'+title.split()[0],folded=True))
        gates=[topic(row[0]+' · '+short(row[1],36),note=' / '.join(row),key='phase-b/gate/'+row[0]) for row in table(phase_b) if re.fullmatch(r'G\d+',row[0])]
        progress=[topic(row[0],leaves(['证据：'+row[1],'验收：'+row[2]],'phase-b/progress/'+str(i)),key='phase-b/progress/'+str(i))
                  for i,row in enumerate(table(section(prd,3))) if len(row)==3 and row[0]!='范围']
        decisions=sources.get('docs/collaboration/B-DECISIONS.md','')
        decision_nodes=[topic(clean(m.group(1)),note=clean(m.group(2)),key='phase-b/decision/'+str(i),folded=True)
                        for i,m in enumerate(re.finditer(r'^## (.*?)\n(.*?)(?=^## |\Z)',decisions,re.M|re.S))]
        sheets.append(sheet('06 B阶段任务与验收',[
            grouped('T1～T8开发任务',tasks,0,'phase-b/tasks'),
            grouped('G1历史通过；G2～G7由Astra复验',gates,1,'phase-b/gates'),
            grouped('已验证与待完成',progress,2,'phase-b/progress'),
            grouped('接口与分工决定（后条覆盖前条）',decision_nodes,3,'phase-b/decisions')],note,'sheet/phase-b'))
    return sheets,{"generated_at":built,"prd_version":version,"sources_sha256":hashes,
                   "requirements":sorted(set(re.findall(r"\b(?:FR|NFR|DEV)-\d{3}\b",prd))),
                   "sheets":[s["title"] for s in sheets]}


def walk(node):
    yield node
    for child in node.get("children",{}).get("attached",[]):
        yield from walk(child)


def legacy_xml(sheets):
    namespace="urn:xmind:xmap:xmlns:content:2.0"
    ET.register_namespace("",namespace)
    tag=lambda name:f"{{{namespace}}}{name}"
    root=ET.Element(tag("xmap-content"),{"version":"2.0"})
    def add(parent,node):
        attrs={"id":node["id"]}
        if "structureClass" in node:attrs["structure-class"]=node["structureClass"]
        if node.get("branch")=="folded":attrs["branch"]="folded"
        element=ET.SubElement(parent,tag("topic"),attrs)
        ET.SubElement(element,tag("title")).text=node["title"]
        if node.get("notes"):
            notes=ET.SubElement(element,tag("notes"))
            ET.SubElement(notes,tag("plain")).text=node["notes"]["plain"]["content"]
        if node.get("labels"):
            labels=ET.SubElement(element,tag("labels"))
            for label in node["labels"]:ET.SubElement(labels,tag("label")).text=label
        children=node.get("children",{}).get("attached",[])
        if children:
            holder=ET.SubElement(ET.SubElement(element,tag("children")),tag("topics"),{"type":"attached"})
            for child in children:add(holder,child)
    for source in sheets:
        element=ET.SubElement(root,tag("sheet"),{"id":source["id"]})
        ET.SubElement(element,tag("title")).text=source["title"]
        add(element,source["rootTopic"])
    return ET.tostring(root,encoding="utf-8",xml_declaration=True)


def main():
    sources=read_sources()
    sheets,report=build(sources)
    nodes=[node for s in sheets for node in walk(s["rootTopic"])]
    ids=[node["id"] for node in nodes]
    if len(ids)!=len(set(ids)):raise ValueError("节点 ID 重复")
    titles="\n".join(node["title"] for node in nodes)
    for requirement in report["requirements"]:
        if requirement not in titles:raise ValueError("导图缺少需求编号："+requirement)
    entries={"content.json":json.dumps(sheets,ensure_ascii=False),
             "metadata.json":json.dumps({"creator":{"name":"HKS PRD Builder","version":"1.0"},"activeSheetId":sheets[0]["id"]}),
             "content.xml":legacy_xml(sheets)}
    entries["manifest.json"]=json.dumps({"file-entries":{name:{} for name in entries}})
    output=DOCS/"PRD.xmind"
    with ZipFile(output,"w",ZIP_DEFLATED) as archive:
        for name,value in entries.items():archive.writestr(name,value)
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert len(json.loads(archive.read("content.json")))==len(sheets)
        ET.fromstring(archive.read("content.xml"))
    report.update(topic_count=len(nodes),file_size=output.stat().st_size)
    fingerprint=hashlib.sha256(json.dumps(report['sources_sha256'],sort_keys=True).encode()).hexdigest()[:10]
    snapshots=DOCS/'prd-mindmaps'
    snapshots.mkdir(exist_ok=True)
    snapshot=snapshots/f"PRD-v{report['prd_version']}-{fingerprint}.xmind"
    if not snapshot.exists():
        with snapshot.open('xb') as saved:saved.write(output.read_bytes())
    report['immutable_snapshot']=str(snapshot.relative_to(ROOT))
    (DOCS/"PRD-mindmap.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"output":str(output),**report},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
