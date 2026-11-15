# 阶段 A 交付与 Claude 验收清单

本页记录 Codex 的实际检查，**最终通过或返工由 Claude 决定**。依据为 ARCH-001、PRODUCT-001 与 PRODUCT-002，不表示 B 阶段业务能力已经实现。

本页主体是阶段 A 的历史验收快照。B 阶段已启动，当前进度与逐段真实 HTTP 结果见 [阶段 B 记录](../evidence/phase-b/README.md)；不要把下文的旧运行状态当成最新实现状态。

## 交付文件

- [PRD 2.1](../PRD.md)：新定位、错题卡 / 知识卡、C1～C5 差距、FR-019～027；U1～U5、难度与成长排行规则已按 Claude 决定同步。
- [五画布 Xmind](../PRD.xmind)：产品全景、功能需求、Agent / Harness、统一输入输出、验收与后续。最新不覆盖的快照路径在 [生成报告](../PRD-mindmap.json)。
- [离线交互架构图](agent-harness.html)：H0～H7、23 个操作的输入输出、五类调用方；可在本地浏览器打开。
- [目标架构与现有映射](agent-architecture.md)、[统一 JSON Schema](agent-contract.schema.json)。
- [当前接口投影](examples/current/)、[新增能力设计样例](examples/design/)、[必须拒绝的反例](examples/invalid/)。
- [Schema 检查](verification.json)、[可视化检查](visual-verification.json)。

## ARCH-A1～A7

| 条件 | Codex 检查结果 | 证据与限制 |
|---|---|---|
| ARCH-A1 | 四种响应状态通过；必填缺失和确认时写入均拒绝 | verification.json；ok / needs_confirmation / partial / error |
| ARCH-A2 | 原 9 个操作有来源与目标投影；新增 14 个单独标设计样例 | 7 份既有归档、2 次临时档案现场生成；原始 HTTP 字节未留存、解析 JSON 已留存；信封与新 ID 标为元数据，不伪装成统一入口实测 |
| ARCH-A3 | 映射覆盖全部 23 操作，并标出旧接口字段与缺口 | 架构文档的接口表；PDF 预览属于调用适配层 |
| ARCH-A4 | 新版浏览器逐项选择 23 操作，8 关 / 4 阶段交互检查通过；离线依赖遗漏已修复并复验 | 原“无外部资源”计数只查外层，不能作为离线证据。新增 export_agent_visual.py 移除未使用的 3 个 CDN 脚本、收紧内外 CSP；递归静态资源检查与浏览器 iframe 资源检查均为空；内外 CSP 不允许远程资源；320px 新成长图无溢出 |
| ARCH-A5 | 激励版在本机 Xmind 打开，实际切到功能规则与 23 操作 I/O 画布；编号覆盖检查通过 | 27 FR + 6 NFR + 3 DEV，基础 AC / 专项 / 产品 / 架构编号保留；985 节点 |
| ARCH-A6 | 目标能力与当前模块分开列，当前来源有文件和原测试指针 | C1 仅部分基础，C2～C5 待实施；旧服务尚未迁移 |
| ARCH-A7 | 23 操作各有 input / output；85 定义、176 本地引用；46 payload 通过、15 反例拒绝 | 自检脚本离线运行，不验证授权、跨记录引用、数学真值或提醒送达 |

## PROD-A1～A10

| 条件 | Codex 检查结果 | 证据与限制 |
|---|---|---|
| PROD-A1 | PRD 与图保留 C1 部分 / C2～C5 未实现 | 网页打开后的待办展示不能满足应用外提醒 |
| PROD-A2（数量由 INC-A2 覆盖） | 操作集合正好 23，原 9 + 14 个新目标，均有输入输出和样例 | verification.json 的 covered_operations 与 x-operations 一致 |
| PROD-A3 | profile.get 强制三层；Inference 缺 based_on 被拒绝 | inference-without-facts.json；事实引用存在性仍需运行时验证 |
| PROD-A4 | 掌握状态仅三档 | MasteryState；stable 证据带间隔、独立正确、无提示条件，参数是先行起点 |
| PROD-A5 | 知识卡来源至少一项；缺来源被拒绝 | knowledge-without-wrong-card-source.json |
| PROD-A6 | tree.move 输出要求 undo；键盘移动样例通过 | tree-move.example.json；产品触屏 / 键盘操作本身尚未开发 |
| PROD-A7 | 推荐需要 reason / based_on；advance 缺 stable 引用被拒绝 | advance-without-stable-evidence.json；证据真实性和每周节奏由未来运行时校验 |
| PROD-A8 | 今日待办最多 3 项；四项样例被拒绝 | too-many-review-items.json |
| PROD-A9 | 交付文档表述检查通过，不以未来能力冒充现状 | 规划与当前实现分开，历史原始证据不改写 |
| PROD-A10 | PRD / Xmind 同步错题整理、主动复习、持续画像与孩子编排树 | 源 SHA256 在生成报告，五画布原生打开检查通过 |

## PRODUCT-002 · INC-A1～A10

| 条件 | Codex 检查结果 | 证据与限制 |
|---|---|---|
| INC-A1 | PRD / 图 / Schema 用 U1～U5，知识卡强制检验证据；review.complete 资格为 true 同样需证据 | 卡片内容样例均含三题记录；仅完成复习的样例资格为 false |
| INC-A2 | 23 个操作，直接创建卡片操作已删除 | 9 + 10 − 1 + 5；清单、路由、样例一致 |
| INC-A3 | unlocked=true 且 U3=false 被拒；使用完整解法的唯一正确迁移题、仅一道正确也被拒 | unlock-with-unverified-question 等反例 |
| INC-A4 | quiz.answer 带 is_correct 被拒，输入仅组 / 题编号和作答 | 提示记录由服务端核验，真实记录链仍待 B 阶段 |
| INC-A5 | 榜单条目带 real_name 被拒；结构不允许学校 / 错题 / 画像字段 | additionalProperties:false；真实小组授权待 FR-018 |
| INC-A6 | 20 + 6 + 2 = 28 的样例通过；总数改 29 的反例通过形状但被算术检查拒绝 | 单独的 semantic_arithmetic，不冒称 JSON Schema 会求和 |
| INC-A7 | 本阶段不做随机酬赏；不扣分、不衰减、不使树枯萎，不做连续打卡激励 | PRD / 架构明确边界；无奖励业务实现 |
| INC-A8 | 参数标为起点、待数据；图中成长值同样有标签 | x-provisional-parameters / PRD / PRODUCT-002 |
| INC-A9 | 当前没有真实多用户榜，明确依赖 FR-018 | 设计昵称与私有缩略图引用是假想场景，不是真实儿童数据 |
| INC-A10 | 激励版原生打开并切 02 / 04；交互图四阶段与 23 操作实际检查 | 原生打开 docs/prd-mindmaps/PRD-v2.1-463d354bcf.xmind；985 节点、36 条需求 |

## Claude 首轮返工与状态

Claude 消息 53：旧版有条件通过，R1 离线依赖、R2 来源表述、R3 最终复跑需修订。消息 58 给出**阶段 A 通过**，要求最后重新生成 Xmind 清理旧的发卡操作名称。已重新生成，当前导图中旧操作名称出现次数为 0。R1 移除未使用 CDN、收紧 CSP，并经 Claude 独立检查和交互复验；R2 区分归档与现场生成；R3 校验已重跑，报告含检查时间和 Schema SHA256。

验收范围如实区分：Claude 独立点击了 23 个操作和四个标签页，复跑了校验、抽查了 card.unlock 反例并解包检查 Xmind；原生 Xmind 打开与手机布局由 Codex 检查。Claude 没有逐个自写全部激励反例，也没有阅读成长分算术检查的实现，不能说他做过这些。B 阶段尚未启动。

审查者可打开 [无 iframe 的离线审查副本](agent-harness-review.html) 直接定位并点击控件；该副本仅当前页面保存选择，主离线文件仍保留标准包装器的状态存储。

## 本次没有做的部分

没有拆分或新增业务服务；没有实现新卡片、个人树、提醒或推荐；没有对真实照片发起新模型调用；没有训练模型。终端实机提醒、正式身份授权和完整教学效果均需后续阶段验证。

当前 Xmind 窗口曾显示编辑状态，已另存 [会话快照](../PRD-会话编辑快照-20261114.xmind) 保留内容，生成器还提供带来源指纹的独立快照，避免后续生成覆盖已打开的编辑版本。
