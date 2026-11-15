# Astra：B 阶段独立验收

验收人：astra-lead；日期：2026-11-14。依据 DEC-003 接任；G1 保留 Claude 历史通过。本记录只覆盖原 B 阶段，未验收探索模式或公网部署。

## 当前结论

| 门 | 结论 | 依据与剩余项 |
|---|---|---|
| G1 | 保留 Claude 历史通过 | 本轮另复跑旧档案兼容与原子失败，均通过，不改历史署名。 |
| G2 | 通过（本机、合成输入） | T2/T3：真实 HTTP 确认建卡、原文保留、幂等、笔记与版本冲突、受控提示；待办上限、空闲时段、跳过与频率降低及复习证据验证。160 项测试和 12 段 E2E 独立运行通过。 |
| G3 | 未验证 | 提醒客户端 13 测试通过，真实服务日志探针 21/21；尚未在关闭浏览器条件下观察三条原生通知行为。当前 Chrome 有用户打开的学习页面和其他工作页面，本轮未关闭这些窗口，未安装 launchd。日志、osascript 成功退出均不能替代通知实际可见。 |
| G4 | 通过（ASTRA-B-001 已修复） | 27项检验后端测试、独立第三组拒绝探针与10项讲解探针通过；两组低分后当日暂停、跨日恢复、已有资料保留。U1～U5及去重/伪造边界通过。 |
| G5 | 通过（参考成长分） | 成长分历史去重、3 天间隔、每点 3 次、20 对关系上限、80 步随机编辑单调不减、移除/撤销不扣分与不刷分测试通过；没有真实小组排行。 |
| G6 | 通过（本机 Chromium） | 修复后原主流程25项及低分停止/讲解17项独立复跑通过；合成上传、核对、解锁、指针/键盘/菜单移动、刷新/撤销、失败重试与跨日恢复可复现。390/1440无溢出，已查看本轮截图。未实测物理手机触屏。 |
| G7 | 通过（文档/证据范围，ASTRA-B-002已修复） | 修复后HTTP12/12、契约92正例/51反例；PRD/职责/DEC-004与状态一致。导图11份来源hash、根文件与快照字节、ZIP/JSON均独立核对通过。新图浏览器点击和新版Xmind原生打开未验证，不沿用历史视觉验收。 |

## 独立证据与方法

全部证据位于 [astra-phase-b](../evidence/astra-phase-b/)。服务使用临时档案、本机假上游和合成题图；未读取或传播模型凭据、未发真实照片、未调用付费模型。

- [e2e-loop.json](../evidence/astra-phase-b/e2e-loop.json)：`mytree/.venv/bin/python tools/e2e_loop_check.py --require-complete --output docs/evidence/astra-phase-b`，12/12。
- [unittest.txt](../evidence/astra-phase-b/unittest.txt)：`mytree/.venv/bin/python -m unittest discover -s mytree/tests`，160 项通过；有一条关闭 socket 的 ResourceWarning，不影响测试退出结果。
- [reminder-tests.txt](../evidence/astra-phase-b/reminder-tests.txt)：提醒客户端13项；[c2-probe.txt](../evidence/astra-phase-b/c2-probe.txt)：21/21日志模式。
- [contract-verification.json](../evidence/astra-phase-b/contract-verification.json)：23操作、93定义、187本地引用、86正例、42反例；12操作归档来自真实 HTTP，其余历史投影/设计不冒充已实现。本轮仅将工具输出路径重定向到自己认领的证据目录，未覆盖协调方 verification.json。
- [ui/browser-results.json](../evidence/astra-phase-b/ui/browser-results.json)：25项。运行 [qa_review.mjs](../evidence/astra-phase-b/qa_review.mjs)，仅将原 qa_phase_b.mjs 服务与输出路径改为绝对路径/独立证据目录，不改变检查内容。
- [source-hashes.json](../evidence/astra-phase-b/source-hashes.json)：本轮首次复验的 app/web/schema SHA256；不能证明后续代码无需复验。

## ASTRA-B-001：连续低分停止只有文案，没有行为

关联 FR-026，G4/G6；P0；执行 codex-junior。共享消息146及对应开发对话已发送。

触发：同一知识点两组三题均答错。`quiz.answer` 依次返回 `down_with_scaffold`、`stop_and_explain`。随后使用新 request_id 调 `quiz.start`。

观察：[low-streak-before.json](../evidence/astra-phase-b/low-streak-before.json) 记录题组数从2变3，third_created=true。探针 [probe_low_streak.py](../evidence/astra-phase-b/probe_low_streak.py) 使用真实 HTTP 和临时档案。`mytree/app/quiz.py` 的 start 未检查 low_streak；`mytree/web/learning-ui.js` 的结果页总是提供 data-new-quiz。

目标：连续两组低分后回到对应知识讲解，不能继续直接出新检验。恢复语义提议为北京时间当日暂停该知识点新检验、次日恢复；已有组可查看，其他知识点不阻断。Codex 消息149回执后，Astra消息151批准此语义，DEC-004已记录；不锁定知识讲解或已有学习资料。

验收：第三次 start 不新增题组；刷新、换 request_id 不绕过；UI 主动作回讲解；次日恢复与其他知识点继续可用；原 U1～U5、浏览器主流程继续通过。

## ASTRA-B-002：当前资料与历史快照混用

关联 DEV-001/003、T8/G7；执行 codex-prd。共享消息147/148。

具体位置：PRD 现行段落仍写树只读、尚无卡片对象；agent-architecture.md 首段仍引用 v2.2 与 Claude 当前验收；agent-harness.html 仍称统一入口待实施、内嵌历史设计样例。历史决定可以保留原作者和日期，但当前说明应链接真实运行样例并明确 Astra 承接。

验收：当前说明与已验结果一致；历史投影标历史；G3 未验证、G4/G6待返工、C5画像驱动推荐未实现仍明确；图/导图来源与 PRD 版本一致，不写整体闭环通过。

## 边界

C1、C3、C4 的局部机制可复现；C2 原生通知与 C5 画像推荐仍未完成独立验收/实现。不得称整体产品闭环完成，不外推真实手写识别率、教学效果、正式多用户或线上实机质量。读图模型仍为 gpt-6.1-sol。

## 资料复核补记（19:49）

已核对 PRD FR-026 的 DEC-004引用、架构首行 PRD2.3/Astra角色及B阶段状态更新。交互图的 file:// 浏览器打开被工具安全策略拒绝，本轮未绕过限制、未将图的点击交互记为通过；可继续做文件/样例的只读一致性检查。新增 quiz/lesson 契约与低分修复仍待交付后一起复验。

## ASTRA-B-001 最终复验（19:55）

**结论：通过；G4/G6 放行（本机合成输入范围）。** 原缺陷与修复依据保留在上文。

- [low-streak-after.json](../evidence/astra-phase-b/low-streak-after.json)：同样两组低分，第三次请求409 CONFLICT，题组2→2，无新组。
- [quiz-retest-final.txt](../evidence/astra-phase-b/quiz-retest-final.txt)：27项通过，含并发拒绝不写盘、北京时间日界、其他主题/档案不受阻、已有组高分不解除当天暂停、旧状态迁移、写失败不形成虚假暂停，以及lesson错误边界。
- [lesson-probe.json](../evidence/astra-phase-b/lesson-probe.json)：Astra新增10项真实HTTP断言通过，规则/原文、参数与来源匹配、无答案/H3、当天/次日状态、读取字节不变。
- [ui-pause/browser-results.json](../evidence/astra-phase-b/ui-pause/browser-results.json)：17项通过，实际进入对应规则讲解；刷新/新request_id不绕过；503不冒充暂停状态，允许重试；次日从服务端重新读取后恢复。已查看mobile-stopped/mobile-lesson截图。
- [ui-final/browser-results.json](../evidence/astra-phase-b/ui-final/browser-results.json)：原25项浏览器主流程再次通过。
- [final-http/e2e-loop.json](../evidence/astra-phase-b/final-http/e2e-loop.json)：修复后12/12段HTTP回归通过。
- [contract-verification-final.json](../evidence/astra-phase-b/contract-verification-final.json)：23操作、96定义、190引用，92正例/51反例；新增只读辅助QuizLessonQuery/Output/Error，不增加Agent操作数。
- [source-hashes-final.json](../evidence/astra-phase-b/source-hashes-final.json)：上述修复版源码摘要。

上述为独立运行结果，不是引用开发方自测。最终修复批次复跑27项相关测试及两条浏览器/HTTP回归；全量160测试是首轮版本结果，未将它冒称最终全量测试数。未部署本次修复。

## G7 最终资料结论（19:56）

**通过文档/证据范围，ASTRA-B-002关闭。** 已核对 [doc-final-check.json](../evidence/astra-phase-b/doc-final-check.json)：PRD v2.3、11份来源hash一致、根PRD.xmind与 `PRD-v2.3-4e50bca9c4.xmind` 字节一致、ZIP/JSON可读、评审链接有效。该快照制作时仍写G7待本轮复核，保留当时事实；本文件为随后给出的最终结论。图内12份运行样例与HTTP归档逐字一致，无远程资源，见 [graph-check.json](../evidence/astra-phase-b/graph-check.json)。本轮未验证新图的浏览器点击或新版Xmind的原生打开，不将静态核对冒充视觉/交互验收。

**最终门状态：G1 Claude历史通过；G2/G4/G5/G6 Astra本机独立通过；G7文档/证据范围通过；G3原生系统通知未验证。** C5画像驱动推荐未实现，整体闭环仍不能宣称完成。未安装登录代理、未部署修复、未扩大探索模式验收。

已通过coord向codex-junior及codex-prd发送具体结论；实现与文档方有接单/交付回执。此次完成的是接任后的独立评审与返工复验，不代表所有后续需求完成。
