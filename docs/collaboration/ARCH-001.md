# ARCH-001 · 独立可复用 Agent 与多端统一调用

> **已被 PRODUCT-001 部分修订（2026-11-14）：** 操作由 9 个扩为 19 个，再经 PRODUCT-002 调整为 23 个；`effects.kind` 枚举补全；「无推送」改为「Agent 不推送，只产出待办」。信封、Harness、确认、幂等、核验等级不变。冲突时以 PRODUCT-001 为准。
> **操作数最终为 23 个（2026-11-14，PRODUCT-002 覆盖）：** 本文第 3 节的 9 个原操作全部保留；PRODUCT-001 新增 10 个，其中 `card.create_knowledge` 已被 `card.unlock` 取代而移除；PRODUCT-002 新增 `quiz.start`、`quiz.answer`、`card.unlock`、`growth.get`、`leaderboard.get`。9 + 9 + 5 = 23。完整清单以 PRODUCT-002 第 7 节为准，Schema 总数必须等于 23。

决策者 / 验收者：Claude。执行者：codex-prd（文档、图、Schema）。关联：FR-013、FR-015～018、DEV-001～003。
来源：用户 2026-11-14 要求：Agent 设计框架与 Harness 架构可视化；输入输出先定好；网页、硬件、AI 工具及其他系统都是调用 Agent 获取输出的，Agent 能接入任何系统。

状态：**设计与接口冻结，不拆分实施。** 现有网页服务**没有**完成解耦，下文第 8 节列出差距。

## 1. 决定摘要

1. **一个 Agent，多个客户端。** 学习辅导 Agent 是独立能力，网页、Android、ESP32、外部 AI 工具都是客户端，只做采集输入、展示输出，不含业务规则。
2. **一个入口，一个信封。** 所有客户端通过同一个调用入口，用同一种请求 / 响应信封。不为每个终端开专用接口。
3. **Harness 是 Agent 的约束层，不是模型。** 它决定哪些输出能放行、哪些必须降级，职责见第 4 节。
4. **副作用和确认由 Agent 层统一管。** 客户端不能自行写学习记录。
5. **本阶段只冻结契约，不重构。** 当前网页服务继续运行，等契约评审通过后再按第 9 节分步迁移。

## 2. 分层与边界

```text
客户端层   网页 / Android / ESP32 / 外部 AI 工具 / 其他系统
              │  只做：采集输入、展示输出、本地缓存、权限申请
              ▼
调用层     统一入口：认证 → 校验信封 → 幂等去重 → 路由到操作
              ▼
Agent 核心  操作编排（诊断、学习、追问、出题、批改、排期）
              │  每个操作经过 Harness
              ▼
Harness    输入关 → 模型调用 → 输出关（结构、数学、教学法、口吻、安全、边界）
              ▼
适配层     模型适配（读图、教学、语音）  工具适配（SymPy 校验、图形生成）
           数据适配（档案、知识树、复习）
```

边界规则：
- 客户端不直接调用模型、不直接读写档案。
- Agent 核心不依赖 HTTP、不依赖具体模型供应商、不依赖具体存储。依赖通过适配层的接口注入。
- 模型只是适配层里的一类。更换读图模型不改核心。

## 3. 调用操作（最终冻结 23 个，见开头注记；本节 9 个原操作，其余见 PRODUCT-001、PRODUCT-002；原 9 个见本节，新增 10 个见 PRODUCT-001 第 8 节，两处合计才是完整清单）

| 操作 | 作用 | 有副作用 | 需确认 | 对应现有接口 |
|---|---|---|---|---|
| `recognize` | 图片或 PDF 页转录为题干和学生作答 | 否 | 否 | `/api/recognize`、`/api/files/preview` |
| `study` | 对确认后的题目与作答生成诊断、提示、知识卡 | 是：写诊断记录、更新错因 | **是**：必须带 `confirmed_reading_id` | `/api/study`、`/api/diagnose`、`/api/learn` |
| `chat` | 针对已保存诊断追问 | 否 | 否 | `/api/chat` |
| `practice.create` | 生成一组练习 | 是：保存题目与判定依据 | 否 | `/api/practice` |
| `practice.check` | 批改一道练习 | 是：更新正确数、知识点、复习 | 否 | `/api/practice/check` |
| `schedule.set` | 设置每周空闲时段并重排复习 | 是 | 否 | `/api/availability` |
| `profile.get` | 读取画像、知识树、复习 | 否 | 否 | `/api/profile` |
| `feedback.add` | 记录主观反馈 | 是：写反馈，不改判题真值 | 否 | `/api/feedback` |
| `speech` | 语音转文字 / 文字转语音 | 否 | 否 | `/api/speech`（未配置） |

新增操作必须先改本表，再改实现。未列出的操作一律拒绝。

## 4. Harness 职责

Harness 位于模型与 Agent 输出之间，分输入关和输出关。每一关可单独开关，并写入响应的 `harness` 字段，供调试页查看。

| 关 | 检查 | 失败处理 | 现状 |
|---|---|---|---|
| H0 输入 | 大小、格式、字符集、步数、请求幂等 | 拒绝，返回具体错误码 | 部分已有 |
| H1 结构 | 模型输出符合 JSON Schema | 不放行；有限次重试后返回失败，不暗中重复付费 | 部分已有 |
| H2 数学 | 可校验的结论由程序核验，不信模型 | 标 `ai_review`，不记错题、不点亮 | 已有（限运算与一元关系） |
| H3 教学法 | 低级提示不出现最终答案 | 回退到已校验提示并标注 | 已有 |
| H4 口吻 | 禁用语、不贴标签 | 重写或回退 | 未做 |
| H5 安全 | 情绪类表达走固定话术并提示家长 | 固定话术 | 未做 |
| H6 语音口语化 | 公式转口语、控制长度 | 截断 | 未做 |
| H7 读图 | **推断依据只能来自学生自己的书写，不用标准答案**（DESIGN-001） | 列候选，请学生确认 | 待实施 |

核验等级是统一的概念，所有响应都带：
`verified`（程序已核验）、`ai_review`（AI 分析，待核对）、`unavailable`（未能核验）。客户端必须把等级显示出来，不允许只显示结论。

## 5. 请求信封

```json
{
  "schema_version": "1.0",
  "operation": "study",
  "request_id": "客户端生成，最长 64，同一意图重试必须相同",
  "client": {"type": "web|android|esp32|tool|other", "name": "字符串", "version": "字符串"},
  "subject": {"profile_id": "字符串"},
  "input": {},
  "options": {"language": "zh-CN", "modalities": ["text", "image", "audio", "svg"]}
}
```

必填：`schema_version`、`operation`、`request_id`、`client.type`、`subject.profile_id`、`input`。`options` 可省略。
`input` 的结构由 `operation` 决定，每个操作一份独立 Schema（见第 10 节）。

约束：
- `profile_id` 目前是匿名本机编号，**不是**身份凭据。正式使用前需要 FR-018 的账号与授权。
- 请求体上限沿用现有限制，单项限额写进各操作 Schema，不在信封里重复。
- 信封里不放密钥。密钥只在服务端和适配层。

## 6. 响应信封

```json
{
  "schema_version": "1.0",
  "request_id": "回显",
  "operation": "study",
  "status": "ok|needs_confirmation|partial|error",
  "verification": {"level": "verified|ai_review|unavailable", "label": "展示用文字"},
  "output": {},
  "artifacts": [{"type": "svg|latex|markdown|audio_ref", "role": "字符串", "ref": "内容或引用"}],
  "next_actions": [{"operation": "字符串", "label": "字符串", "requires": ["字段名"]}],
  "effects": [{"kind": "record_diagnosis|update_profile|create_review|none", "id": "字符串", "idempotent_replay": false}],
  "harness": {"gates": [{"id": "H3", "result": "pass|fallback|fail", "note": "字符串"}]},
  "error": {"code": "字符串", "message": "给用户看的话", "retryable": true, "details_ref": "仅内部日志编号"},
  "meta": {"model": "字符串", "seconds": 0, "usage": {}}
}
```

必填：`schema_version`、`request_id`、`operation`、`status`。其余按状态出现：
- `ok`：必有 `output`、`verification`、`effects`。
- `needs_confirmation`：必有 `output` 和 `next_actions`，且 `effects` 必须为空，因为这时不写任何记录。
- `partial`：必有 `output`，并在 `harness` 里说明哪几关降级。
- `error`：必有 `error`，`effects` 必须为空。

**`error.message` 是给学生或家长看的话，不含上游原文、堆栈、密钥。**

错误码冻结（客户端据此决定是否重试）：

| 码 | 含义 | retryable |
|---|---|---|
| `INVALID_INPUT` | 输入不合格，附具体字段 | 否 |
| `NEEDS_CONFIRMATION` | 需先确认识别结果 | 否，先确认 |
| `UNSUPPORTED` | 超出支持范围 | 否 |
| `MODEL_NOT_CONFIGURED` | 未配置模型 | 否 |
| `MODEL_TIMEOUT`、`MODEL_BUSY`、`MODEL_UPSTREAM` | 上游问题 | 是 |
| `MODEL_OUTPUT_INVALID` | 输出不合格 | 是，有限次 |
| `MODEL_AUTH` | 凭据失效 | 否，需运维 |
| `NOT_FOUND` | 编号过期 | 否，重新进入 |
| `CONFLICT` | 同一 `request_id` 内容不同 | 否 |
| `STORAGE_FAILED` | 写档案失败，**不得显示已保存** | 是 |

## 7. 状态、幂等、确认与副作用

**幂等。** 同一 `profile_id` + `request_id` + `operation`：
- 内容相同：返回第一次的结果，`effects[].idempotent_replay` 为 true，不重复写、不重复调用模型。
- 内容不同：返回 `CONFLICT`，不覆盖。

**确认。** 识别结果必须先确认，才允许写记录：
1. `recognize` 返回 `reading_id` 和待核对的读法，状态 `needs_confirmation`，不写任何东西。
2. 客户端展示，学生核对或修改。
3. `study` 带 `confirmed_reading_id` 和学生最终文本才执行。DESIGN-001 的推断读法（`inferred=true`）同样要展示依据并可一键改。

**副作用边界。**
- 只读操作：`recognize`、`chat`、`profile.get`、`speech`。重复调用无影响。
- 写操作：`study`、`practice.*`、`schedule.set`、`feedback.add`。必须幂等，必须在 `effects` 里列出写了什么。
- 写失败时返回 `STORAGE_FAILED`，不能显示已保存，也不能算已点亮。
- 学生主观反馈、AI 未核验内容、浏览题目，**不得**触发点亮或记错题（沿用 FR-004、FR-010）。
- 任何外部工具（日历、推送、第三方）都是本阶段之外，不开放。

## 8. 多模态输出与适配

**输出形态。** `output` 里放结构化数据，`artifacts` 放可展示载体：

| 类型 | 说明 | 谁生成 |
|---|---|---|
| `markdown` + `latex` | 题干、提示、知识卡，公式用 LaTeX，客户端本地渲染 | 模型输出，Harness 清洗 |
| `svg` | 数形结合图，只来自程序，不接受模型输出的 HTML 或代码 | 程序（visual.py） |
| `audio_ref` | 语音朗读的引用，未配置时不返回 | 语音适配，未接通 |
| 纯文本短句 | 为硬件和语音准备的简版，不含公式 | Harness 的 H6 生成 |

客户端按能力取用，在 `options.modalities` 声明。硬件只声明 `text` 和 `audio`，就拿简版文本和音频引用。

**适配层接口（只定义，不实现）。**
- 模型适配：`vision(image, prompt) → json`、`teach(context, prompt) → json`、`asr(audio) → text`、`tts(text) → audio`。每个适配器声明名称、模型 ID、超时，由配置注入。
- 工具适配：`verify(kind, input) → {level, result}`、`render_figure(kind, params) → svg`。
- 数据适配：`profiles`、`events`、`exercises`、`reviews`。

## 9. 当前差距与阶段安排

**现状（已核实，不宣称已解耦）：**
- 业务模块（`junior.py`、`pipeline.py`、`mathcheck.py`）不依赖 HTTP，是好的起点。
- 路由直接取 `student`、`request_id`、业务字段，没有统一信封，响应形态各接口不同。
- `ai.py` 同时读 `.env.local`、写用量文件、做识别和教学，模型适配没有抽象。
- 幂等只有部分接口有 `request_id`。
- Android 目前不调用服务。硬件没有实现。

**本阶段（A）：只做设计与冻结。** codex-prd 交付：
1. 可编辑的 Xmind 增加两张画布：架构分层、输入输出。
2. 可交互的架构图（HTML），能点开 Harness 各关、各操作的输入输出。
3. 机器可校验的 JSON Schema：信封、9 个操作的 `input` 与 `output`、错误码。
4. 一份现有接口到新契约的映射表（第 3 节已列，补字段对照）。

**下一阶段（B）：不立即启动。** 等 A 通过验收，且用户确认后再做：
1. 加一个薄的适配层，把现有路由包进信封，**旧接口保持可用**。
2. 抽出模型适配接口，`ai.py` 拆成适配器。
3. 一个非网页客户端验证（命令行或外部脚本），证明契约独立于网页。

B 不是 A 的一部分，不得提前动 `mytree/app`。

## 10. 验收条件（阶段 A）

| 编号 | 条件 |
|---|---|
| ARCH-A1 | 响应示例通过 Schema：`ok`、`needs_confirmation`、`partial`、`error` 各一份，另给两份必须被拒绝的反例（缺必填字段、`needs_confirmation` 却带非空 `effects`） |
| ARCH-A2 | 9 个操作各有 `input` 与 `output` Schema 和一份真实示例；示例取自现有接口的真实返回，改字段名即可，不得编造 |
| ARCH-A3 | 现有接口映射表覆盖第 3 节全部操作，并标出每个接口缺哪些信封字段 |
| ARCH-A4 | 架构图可在浏览器打开，不联网，不含密钥，点击能查看每个 Harness 关与每个操作的输入输出 |
| ARCH-A5 | Xmind 在 Xmind 中实际打开，保留 FR / NFR / DEV / AC 编号，新增两张画布与本文一致 |
| ARCH-A6 | 每处写「已实现」的地方都能指到实际文件或测试；未实现的写「待实施」。文档里不出现「已解耦」 |
| ARCH-A7 | 全部 Schema 通过自检脚本（检查 `$ref`、必填、枚举），输出通过数量 |

## 11. 范围外

多智能体协作、真实支付、第三方日历、系统级推送（短信、App 推送、系统通知）、账号体系、硬件固件实现。Agent 本身不推送，只通过 `review.today` 产出待办，由客户端自行提醒，见 PRODUCT-001 第 4 节。它们不在本阶段，也不阻塞契约冻结。

## 12. 需要用户后续确认的事项

- 阶段 B 何时启动。
- `profile_id` 在正式使用时由谁签发（账号体系），属 FR-018。
- 外部 AI 工具以什么协议接入（本文只定契约，协议封装如 MCP 或 HTTP 另议，不在 A 阶段）。
