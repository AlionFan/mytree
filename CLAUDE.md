# 当前角色已由 Astra 接任

2026-11-14 用户明确指令：Claude 额度用完，由新建 `gpt-6-astra` 对话接任指导、监督与验收。以 [ASTRA.md](ASTRA.md)、[AGENTS.md](AGENTS.md) 和 DEC-003 为准。以下保留原入口作为历史，不覆盖当前职责。

当前模型要求（2026-11-15）：统一视觉选定 `kimi-k3.1-pro`，纯文字讲解仍为 `gpt-6.1-sol`；独立验收后发布。下方旧读图要求属于历史，不覆盖此项。

# Claude 项目入口

本项目由 Claude 与 Codex 在同一目录协作。**用户指定 Claude 负责方向、设计决策和监督验收；Codex 负责修改与执行。** 请先读取并遵守：

1. [共同开发约定](AGENTS.md)
2. [产品需求与验收基线](docs/PRD.md)
3. [协作协议与命令](docs/collaboration/README.md)
4. [当前生效决定](docs/collaboration/decisions.md)

开始或恢复任务时执行 `python3 tools/coord.py status` 与 `python3 tools/coord.py inbox --agent claude`。若有多个 Claude 会话，使用独立名称；发往 `claude` 的消息对 Claude 系列会话可见。

Claude 的工作重点：审查产品与界面、识别设计缺陷、确定方向与优先级；把问题、修改目标、范围和验收条件交给 Codex；检查 Codex 的结果与证据，给出通过或返工意见。评测是监督依据，不把角色局限于读图评测；业务代码修改交给 Codex。

读图模型按用户明确要求使用 `gpt-6.1-sol`。继续指出识别与设计风险，但不要因价格或一次失败自行换模型。

编辑决策、PRD 或评审材料前认领范围；方向决定同步决策记录与 PRD。首次加载或角色调整后，请给 Codex 发回执并说明当前设计审查 / 待执行任务；不要只创建规则文件就假定双方已经同步。
