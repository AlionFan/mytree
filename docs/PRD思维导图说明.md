# PRD 思维导图

最新 B 阶段快照见 [生成报告](PRD-mindmap.json) 的 `immutable_snapshot`；当前 [PRD.xmind](PRD.xmind) 已更新为 v2.3。优先打开报告指定的独立快照，避免复用旧窗口；旧会话编辑已另存保留。

打开 [PRD.xmind](PRD.xmind)。节点可展开、折叠与编辑；备注中保留对应需求原文。FR / NFR / DEV / AC 编号与 [PRD](PRD.md) 对应。

生成器还会在 `docs/prd-mindmaps/` 保留带版本和来源指纹的快照，路径写入生成报告的 `immutable_snapshot`。后续生成不会覆盖同一来源的快照，方便一边编辑导图，一边保留新的需求版本。

画布按内容分层：产品全景、功能需求与规则、Agent 与 Harness、统一输入与输出、验收与后续、B 阶段任务与验收。最后一张包含 T1～T8、G1～G7、PRD 当前进度和接口决定；T6 最新分工以 B-DECISIONS 的 D8 为准。辅助 HTTP 接口单独分支，不增加 23 个操作的数量。

本图用于梳理需求，不替代 PRD，也不把“规划、已下发、开发中”当作“已实现、已验收”。Astra 决定当前方向、设计与验收；Claude 的历史决定与署名保留；Codex 按已确认要求修改执行；读图固定使用 `gpt-6.1-sol`。

## 更新方式

1. 先由 Astra 确认当前设计决定或按用户明确指令更新 PRD / 决策记录。
2. 在项目根目录运行：

```sh
python3 tools/build_prd_xmind.py
```

3. 核对生成报告 [PRD-mindmap.json](PRD-mindmap.json) 中的来源 SHA256、版本、需求编号与画布列表；重新打开 Xmind 检查。

导图是生成时的快照，不会在 Xmind 内实时同步。请把实质需求修改写回 PRD，再生成；不要只在图中修改后假定开发基线已改变。需求分组或 PRD 结构变化时，同步调整生成器，工具会拒绝遗漏无法解析的 FR 或重复节点。

## 文件格式与验证

生成器采用 [Xmind 官方 SDK 的包结构](https://github.com/xmindltd/xmind-sdk-js/blob/master/src/utils/dumper.ts)，包含现代 JSON 内容与兼容 XML 内容。生成时检查 ZIP 完整性、JSON / XML 可读性、节点唯一性及需求编号覆盖；阶段 A 五画布版本已在本机 Xmind 打开。B 阶段新增画布的原生检查状态另记，不沿用旧验收。

最终画布数量与节点数以生成报告为准；架构设计验收状态以 Astra 当前决定及相应文档为准；历史阶段 A 验收仍保留原署名。
