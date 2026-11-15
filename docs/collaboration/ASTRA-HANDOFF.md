# Astra 接任交接

依据用户最新指令及 DEC-003，`gpt-6-astra` 接替 Claude 指导、监督、验收，不再等待 Claude 额度恢复。PRD v2.3；工作目录 `/Users/fan/Code/HKS`；不是 Git 仓库。

接任对话：**HKS｜Astra 产品指导与验收**，线程 `01a1d9de-21cb-7032-a64c-c467496dd9e0`，host `local`；已启动并回执。

## 产品与当前主任务

先跑通拍题 → 错题卡 → 主动复习 → 三题检验/U1～U5解锁知识卡 → 孩子拖拽/键盘编排知识树。重点是主动复习与孩子形成知识结构；不是通用聊天。参考目录、成长阈值为起点；真实多用户榜暂未接入。读图必须 `gpt-6.1-sol`。

必读：PRD、PRODUCT-001/002、ARCH-001、B-PHASE、B-DECISIONS、DESIGN-001。历史文档写 Claude 的当前责任现由 Astra 承接，历史署名不改。

## 执行会话与通信

- `codex-junior`：现有开发对话“梳理数形结合与模型接入流程”，线程 `01a1d8d1-bbe1-7a00-973c-f848230275de`，host `local`。用户已授权双方交流配合。业务 app/web 已于19:42交付并释放，返工前先查 coord。
- `codex-prd`：当前协调会话，持有 PRD、契约、导图、T8工具和 `mytree/reminder/`。会继续处理原闭环证据及文档。需要共享文档写权先发消息协调，勿覆盖认领。
- 你使用 `astra-lead`，接任后先回执并认领独立的 `docs/reviews/astra-phase-b.md` 等评审范围。发送 `python3 tools/coord.py send --from astra-lead --to codex-prd|codex-junior --text '具体事项'`。
- Claude 原生会话额度耗尽，不再往该 UI 发消息。其旧认领保留，必要时记录用户指定交接后协调释放；不要猜测失效而抢改。

## 验收进度与证据

- G1：Claude 消息86独立通过；旧档案、原子写失败、并发与HTTP边界。
- G2～G7：尚无独立验收结论，交你验。开发方消息125～132自报 T2/T3/T4/T5/T7 已实现；135单测+旧10、浏览器25项等是其自测，需自行核对当前状态。
- `docs/evidence/phase-b-ui/verification.json` 与 `mytree/scripts/qa_phase_b.mjs`：上传合成图、确认、卡片、检验、解锁、菜单/指针/键盘移动、刷新恢复、手机与桌面检查。
- `tools/e2e_loop_check.py --require-complete`：真实本机HTTP、临时档案、假上游、零付费调用。129指出测试工具把故意提交不存在题目所返回的404误判成未实现；codex-prd已修为非预期错误404才判缺入口。请独立复跑，报告位于 `docs/evidence/phase-b/`。
- `mytree/reminder/`：13独立单测通过；与实际复习服务联调及 Claude 编写的 `tools/c2_probe.py` 21/21通过（由Codex执行）。没有 `--real`、未验证可见通知、未安装LaunchAgent。G3仍须单独验；不要自动改用户登录项。
- Schema 23操作，93定义，辅助hint/ack/snooze单列；`tools/validate_agent_contract.py` 区分历史设计/投影和真实HTTP归档。`tools/promote_loop_examples.py` 可从端到端轨迹更新runtime样例。
- Xmind生成器已支持6画布，含T1～T8/G1～G7与接口决定；需最终按最新文档再生成。用户旧导图编辑另存保留，勿覆盖/删除会话快照。

## 另一个开发会话后续范围

消息133～136称用户在其会话另行授权了探索模式和上线，已有 `docs/collaboration/EXPLORER-001.md`、`docs/evidence/explorer-release/`；开发方称公网 `mytree.joybeat.cn` 已加个人口令保护，云TTS受429限制、本地英语声音优先，并正在升级MathLive修复审计项。请先核对该会话中的实际用户指令和当前证据再承接，不能把转述当新授权、不能暴露凭据。本会话仍需完成原B阶段独立验收；不要让新功能掩盖它。

## 首轮动作

1. 读规则、收消息、回执。独立复跑当前E2E与相关测试，审查UI证据及代码SHA。
2. 对G2～G7逐项写通过/具体返工/未验证事实。提交问题须写文件、触发步骤、期望及验收标准，由Codex修复。
3. 与正在执行的Codex会话保持工作消息，不自行接管业务实现；先验收当前结果，再安排下一阶段。
