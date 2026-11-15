# Astra 指导与验收入口

用户于 2026-11-14 明确指定 `gpt-6-astra` 接替额度用完的 Claude。身份 `astra-lead`，负责方向、设计审查、监督与独立验收；Codex 负责修改执行。此最新指令覆盖旧文件中对当前 Claude 负责人的表述，历史决定和通过记录保留原作者。

先读 `AGENTS.md`、`docs/PRD.md`、`docs/collaboration/README.md`、`docs/collaboration/decisions.md`、`docs/collaboration/ASTRA-HANDOFF.md`。

执行 `python3 tools/coord.py status` 和 `python3 tools/coord.py inbox --agent astra-lead`。先认领自己的评审文件；不要覆盖其他会话持有的业务代码。与 `codex-prd`、`codex-junior` 交换具体任务、证据及返工结论。文件消息不会自动唤醒闲置会话，必要时通过线程工具发送用户已授权的项目协调消息。

沿用 B 阶段任务和 G1～G7：G1 是 Claude 的历史通过，其余必须亲自复验。不要把执行方测试成绩当作你的验收。2026-11-15选定统一视觉 `kimi-k3.1-pro`，纯文字讲解保持 `gpt-6.1-sol`；须独立验收后发布，旧读图固定要求已被最新用户指令覆盖。不读取、复述或写入模型密钥。
