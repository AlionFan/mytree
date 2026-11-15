# 小树同学 · 数学成长手册

> 后续开发遵循 [PRD](../docs/PRD.md)、[共同开发约定](../AGENTS.md) 和 [Codex / Claude 协作协议](../docs/collaboration/README.md)。本文说明运行与接口；下面的两章闭环及验证结果为既有版本记录，开发中的初中扩展须单独联调验收，不能直接沿用原通过结论。

面向七至九年级的初中数学教学智能体。当前为**接入 NextLabs 读图与文字讲解的本机演示版**，大纲包含数与式、方程、不等式、函数、几何、统计和概率等九个目录板块、37个初始知识点。目录不是完整教材覆盖证明。学生只通过拍照或上传图片/PDF录题；确认识别后，支持的式子独立验算，其他推理标注 AI 分析待核对。

拍照 / 上传图片或 PDF → 选页与框选 → 识别并确认题目与演算 → 定位第一个卡点 → 三级提示 / 数形结合 → 3 道针对练习 → 保存结果 → 自动复习排期 → 知识树与家长看板。

## 启动

首次安装（Python 3.12、uv）：

```sh
cd /Users/fan/Code/HKS/mytree
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
./run.sh
```

之后只需 `./run.sh`。默认监听 `127.0.0.1:8000`：

- 学习桌：<http://127.0.0.1:8000/>
- 知识树：<http://127.0.0.1:8000/tree>
- 复习计划：<http://127.0.0.1:8000/plan>
- 家长看板：<http://127.0.0.1:8000/parent>

`PORT` / `HOST` 可覆盖监听地址；`MYTREE_PROFILE` 可指定学习档案路径，默认 `data/profiles.json`。档案按浏览器匿名编号区分，刷新后可继续，尚无正式账号、监护人授权绑定与跨设备同步。此版本用于本机演示；本轮另用用户提供的实拍试卷做了小样本验证。

## 已有能力

- 程序逐行等价检查、首个错误定位、分解/约分是否做完。照抄原题不能拿到练习完成进度。
- 旧代数接口仍保留 120字符、12步与指数8等有界限制。新 `/api/study` 接受完整题干6000字、最多30行作答，每行1500字；独立 LaTeX 解析另限480字符、指数12、允许的命令与运算数。支持部分实数/根式/特殊角运算、一元一次/二次方程和单个不等式的解集。解集一致只验证相应数学式，不证明自然语言推理。分式方程排除分母为零；方程组、复杂函数/统计/概率应用和几何证明目前主要由 AI 辅导，不能称为程序自动批改。
- 分式化简保留原来的分母限制；等价式额外引入分母限制时会指出。代入反例避开原式无定义的值。
- 三级提示逐级解锁；完整图形需主动展开，提示 1/2 不自动展示完整答案。
- 平方差面积拼图可点击拆分/重组；完全平方/正系数三项式面积图、提公因式结构图、有向代入对比图。图形标明适用条件，未支持的题型保留文字诊断，不硬画。
- 各主题提供基础巩固模板；复杂证明先练相关判据，不能把基础题做对等同于证明题已掌握。练习由模板生成并验算；练习答案由服务端保存，前端获得题目与练习编号。正确提交幂等。
- 每周空闲日和开始时间可设置；按 1/3/7 天阶段选择下一个空闲日，均使用北京时间。完成一组 3 题后推进下一阶段。
- 练习进度、最近记录、错因和复习持久化；单次做对标为「初次点亮」，不宣称完全掌握。
- 学生端移除手动录入与示例题入口，提供拍照录题、上传图片/PDF。图片不超过10 MB；PDF不超过20 MB、最多100页，可选页、框选一道题。
- 图片先本机预览；PDF上传给应用服务在内存中渲染选中页，不落盘。点击识别才把选中页/框选区域发送给模型，原始PDF不会发给模型。识别结果可核对修改，确认后才检查作答。
- 只有题干、没有作答时进入“新题学习”：可以看分级思路、图形和AI追问，不虚构卡点、不增加错因或自动点亮知识点；完成对应练习后保存进度并安排复习。
- AI 老师根据服务端保存的诊断与图形标签回答追问；明确显示 AI 内容。返回的等式经程序验算，低级提示泄露完整结果或等式错误时回退为已校验提示，界面如实标明回退。自然语言教学内容仍需真实样本评估。
- 探索模式录音走ASR（gpt-4o-mini-transcribe），回复只走模型TTS（tts-1-hd/nova）；已取消浏览器设备朗读和静默机械回退。模型当前真实请求429，字幕和文字追问仍可用；配置存在不等于语音可用，真人录音/听感待验。

当前知识树包含9个板块、37个粗粒度知识点。初中全教材的细分、教材映射、题型难度与独立真实样本覆盖仍待扩展。Android 原生工程不在这次网页闭环变更中，尚未与本服务同步。

## 3 分钟体验

1. 点击「拍照录题」或「上传图片 / PDF」。首屏没有空白表达式输入框或示例题。
2. PDF 先选页；默认直接识别当前整页。需要局部识别时在原图上直接拖动，松开即应用选区，无额外框选按钮。长图双指平移浏览；电脑可滚轮、PageUp/PageDown或Alt方向键平移，方向键/Shift方向键调整选框、Enter应用，Escape或双击恢复整页。
3. 点击识别，核对题干、括号和正负号。识别后公式用 MathLive 数学键盘校正，题干、提示、追问和练习用 KaTeX/Markdown 展示。正文与公式字体均在本地提供；长公式在自身区域横向滚动。文字校正仅出现在识别后。
4. 有作答时确认后检查卡点；没有作答时确认后先学习，不把题目本身当作学生作答。
5. 展开提示、查看图形，向 AI 老师追问，再完成3道针对练习。
6. 知识树与复习计划保存进度，家长看板查看同一档案；新题学习不会被算成错题。

## 接入模型：NextLabs 或厂商官网

按用户 2026-11-14 的最新要求，只选 NextLabs 或模型厂商官网；不依赖 BJMoMA。此前两站的模型与价格表仅为历史调研。

已依据 [平台接入指南](https://credits.openai-next.com/guide/quickstart) 使用 `https://api.openai-next.com/v1/chat/completions`。当前服务器私有配置位于 `.env.local`（0600，Git 忽略），也可用环境变量覆盖。配置字段示例见 `.env.example`，不包含真实密钥。

| 角色 | 当前配置 | 初测依据 |
|---|---|---|
| 统一视觉 | `kimi-k3.1-pro` | 2026-11-15国产模型选型，包含OCR、探索者和带图讲解；已通过3张原创合成小集和Astra独立验收，2026-11-15已发布。不代表真实手写总体准确率。 |
| 讲解 | `gpt-6.1-sol` | 实际图形讲解成功；模型可按角色独立更换。 |
| 历史视觉对照 | `qwen3-vl-plus` | 合成3题通过是早期冒烟；本轮实拍复杂题有补写学生结论，不能外推准确率。 |

这只是小样本接通测试，使用合成图片（包含手写风格字体与轻微旋转），不是儿童手写识别准确率评测，也不能证明 GPT 或国产模型普遍更好。完整记录在 `../docs/evidence/model-tests/vision-comparison.json`；Qwen 文本讲解候选这次超时，没有据此进行质量排名。

模型参数使用兼容接口约定：GPT 使用 `max_completion_tokens`，Qwen 使用 `max_tokens`，GPT 推理强度设为 `low`。超时不自动重复付费请求；界面保留照片与输入，允许手动重试。凭据/上游错误不回显原始响应。`data/model-usage.jsonl` 只记模型、耗时、token 和状态，不记录图片、题目、对话或密钥。

模型链路：照片识别 → 学生确认题干/条件/原样作答 → `/api/study` 按题型路由 → 独立程序核验支持的数学式 + 模型分级教学 → 追问/反馈/基础巩固。纯题干不虚构错误；不能核验的作答使用 `ai_review`，不自动记错或点亮。图形来自预设组件，模型不能执行代码或 HTML。`/api/speech` 仍返回 `503 SPEECH_NOT_CONFIGURED`。

## HTTP 契约

所有 POST 都使用 `Content-Type: application/json`，字段 `student` 为匿名档案编号。

| 接口 | 内容 |
|---|---|
| `POST /api/files/preview` | `{student, file_data:"data:application/pdf;base64,…", page:1}`；返回 `page_count, page, width, height, preview`，只在内存渲染，不调模型。 |
| `POST /api/study` | `{student, problem, problem_latex?, steps, recognition:{question_type,topic_id,diagram_description,...}, request_id?}`；返回 `analysis, diagnosis_id`。analysis 包含 `status, engine, verification, problem_latex, target_latex, knowledge_ids, assessment, prompt_version`；支持状态 `not_attempted / correct / wrong_step / incomplete / ai_review`。 |
| `POST /api/feedback` | `{student, diagnosis_id, rating:"understood/confusing/incorrect", issue?:"补充说明"}`；关联原题与版本保存；incorrect 保持待复核，不改变判题真值。 |
| `POST /api/learn` | `{student, problem, request_id?}`；仅题干的学习上下文，状态 `not_attempted`，不虚构错误或掌握进度。 |
| `POST /api/recognize` | `{student, image_data:"data:image/jpeg;base64,…"}`；返回题目、原样学生步骤、疑似不清晰位置与 `needs_confirmation`，不写入错题记录。 |
| `POST /api/chat` | `{student, diagnosis_id, question, level:1..3, history?:[{role,content}]}`；只使用服务端保存的诊断。返回 `reply, equations, source, fallback, meta`。 |
| `POST /api/diagnose` | `{student, problem, steps, request_id?}`；返回 `ok, analysis, diagnosis_id`。`request_id` 用于重试去重。 |
| `POST /api/practice` | `{student, diagnosis_id}` 或 `{student, review_id}`；返回 `kp, items`，每题包含 `id, q, question, domain`。 |
| `POST /api/practice/check` | `{student, exercise_id, answer}`；返回 `correct, message, duplicate`，并保存进度。 |
| `POST /api/availability` | `{student, availability:{days:[1..7], time:"19:30"}}`；保存并重排待复习计划。 |
| `GET /api/profile?student=…` | 返回 `history, causes, tree, reviews, availability, practice_correct, recent, pending`。 |
| `GET /api/capabilities` / `/healthz` | 返回服务端配置状态（无密钥），不把配置存在等同于实时上游健康；实际调用错误另行反馈。 |

兼容旧接口 `GET /api/practice?cause=…` 和直接按 `question, answer` 校验，但旧调用不计入学习进度；新客户端应使用上面的有练习编号的闭环。

## 验证

```sh
.venv/bin/python tests/test_all.py
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
node --check web/app.js
```

后端测试使用独立临时档案，不污染演示记录。旧版32项检查为历史记录。本轮新增初中扩展回归，最新52项检查通过（42项unittest+10项原脚本），执行结果见 `../docs/evidence/verification-junior.json`；旧10项脚本与 unittest 分开运行。实际浏览器里，Qwen 读图约 6.01 秒、GPT 图形追问讲解约 7.73 秒；不是速度保证。页面验收约定与截图在 `../docs/design-contract.md`、`../docs/evidence/verification-junior.json`；历史上传证据保留。

## 部署状态

当前提供本机运行入口，未部署到 `mytree.joybeat.cn`。2026-11-14 检查时域名已有 A 记录，HTTPS 探测返回 503，本机证书链校验也未通过；需要在实际服务器部署服务、配置反向代理与可信 HTTPS 后再次验收。正式供孩子/家长使用前，还需账号、授权与受保护的持久存储，当前的匿名本机演示档案不替代这些能力。

## 本轮实拍评测与持续改进

查看了用户提供的6页实拍试卷。运算、概率、函数应用三个选区完成了 Qwen 转录/GPT 教学调用，函数页额外调用 GPT 转录；样本太少，且同一试卷不构成独立留出集。运算题额外在浏览器完成识别确认、分级讲解、反馈、三题练习和复习闭环。函数页暴露补写学生结论/混入邻题笔迹等缺陷；识别结果必须对照原图确认。人工参考的不等号也经过放大复核并更正，不能将早期判断当作金标。

`data/evaluation/` 为私有本机选区与详细输出，服务端不提供下载。运行开发集冒烟：`.venv/bin/python scripts/evaluate_real_exams.py`，会实际调用模型并产生费用；不会自动重试、改评分规则或发布。不是整卷批改器。

网页反馈按钮保存理解体验、关联提示版本；“再讲简单些”触发当前级别的简短讲解。RSI 目前只有反馈、版本与评测基础；完整研究边界、独立留出评测与发布回滚建议见 [RSI方案](../docs/RSI方案.md)。本轮没有自动训练或自主改写程序。

前端资源已随项目放入 `web/vendor/`。仅维护依赖时运行 `npm ci && npm run vendor`，运行服务不依赖 Node。KaTeX、MathLive、Marked、DOMPurify 的版本和许可证见 vendor 子目录；模型 Markdown 经清洗，KaTeX 不信任扩展命令。


## 邮箱账号登录（FR-018）

公网入口使用邮箱验证码注册/登录，账号无需密码，验证码10分钟有效、成功一次即失效。服务端绑定每个账号自己的学习档案，不自动认领旧匿名记录。验证码与会话不进入日志。详细 SMTP 配置、限额及接口见 [部署说明](deploy/README.md)。本机未设置 `MYTREE_AUTH_MODE=email` 时仍可运行匿名演示；公网容器固定 email 模式，不接受旧共享口令。

QQ 发信配置：`python3 mytree/deploy/configure_email.py`（从项目根目录运行），在终端隐藏输入 SMTP 授权码，然后发布。私有配置不打包。账号隔离与家长授权绑定是不同能力；后者尚未完成。


## 来源匹配与角色入口（2026-11-14）

- 针对练习与三题检验以服务端来源卡的题型结构匹配，不再只看宽泛topic。当前额外支持实数 `m-n=c`、`m>l`、`n<u` 与 `m(n+d)` 的有界综合范围题；开闭边界、内部顶点、迁移为 `m(d-n)` 均独立核验。参数和规则版本只存服务端；公开检验复用 `difficulty_features` 展示一句具体原因，普通练习新增可选 `match_reason` 字符串。无匹配返回422 `UNSUPPORTED`，原卡与讲解保留；不回退简单整数题。某些旧宽泛主题的默认练习因缺乏来源结构不再自动生成，这是有意取消不可靠回退，不表示全初中题型都已支持。
- 拍题分选题、核对、学习，核对默认为书面预览，逐行修改/取消，框选保留触屏指针和键盘。开始学习后原图收起，按需查看；逐级提示渐进展开。
- `/parent` 为独立家长页，无家长授权绑定时仅显示尚未关联，不读取任意 student 参数的孩子资料。`GET /api/parent/overview` 返回空 children 与说明，待绑定功能接入后另行验收。
- `/admin/login` 独立管理员登录，`/admin` 查看最小服务面板；`POST /api/admin/login` 接收 username/password、创建独立 HttpOnly Cookie；`POST /api/admin/logout` 撤销管理员会话；`GET /api/admin/overview` 仅返回服务/配置就绪布尔值、账号计数和脱敏尝试概况。学生会话访问管理API403，未登录401；管理口令仅私有加盐scrypt哈希，不能从邮箱名字获得管理员身份。不提供儿童资料浏览、改判、删除或导出权限。


## 整页多题与免校准（ASTRA-DESIGN-003）

默认：上传/拍照→识别并整理当前页→清晰题自动进入学习。最多12道独立大题，子问保留共享题干；超限明确还有未处理内容。题干、学生作答、教师批注、划掉笔迹/未知角色分别记录，允许作答区域与题干重叠。歧义题单独跳过，不要求孩子逐行校准。恢复只提供重拍/可选框选，暂不开放手工更正覆盖版本。题库服务未接入，original_search=not_configured；AI转录不代表找到题库原题。

辅助接口（不增加23学习Agent操作）：

| 路径 | 请求字段 | 行为 |
|---|---|---|
| POST /api/recognize/page | image_data, request_id, client_generation, page_index可选 | 服务端生成batch_id/source_revision与独立reading_id，返回items、unassigned_fragments、overflow及逐题auto_ready/readiness；相同请求不重复读图 |
| POST /api/study/reading | batch_id, reading_id, source_revision, request_id | 服务器读不可变原文/归属并签发内部auto receipt；按reading而非客户端request_id幂等。部分失败由页面逐项展示，可只重试失败题 |
| POST /api/recognize/page/cancel | batch_id, source_revision | 取消尚未开始的整理；已开始的最多两题可能完成，成功记录保留 |
| POST /api/recognize/page/resume | batch_id, source_revision | 用户明确继续同批未完成题，不重新识别、不重建成功卡片 |

本机匿名演示可附student，公网身份一律从邮箱会话绑定，不信任目标编号。额外steps/auto_ready/伪造凭据不接受；外人404、错版本/过期/取消409、未登录401、结构错误400、上传超大413、模型错误502/503/504。接收缓存2小时/32页，每页最多12题、每题30行/6000字题干；仅瞬时缓存，不保存照片。已持久化卡片可在缓存丢失/进程重启后按同一来源回放，不再调用模型或记账。

自动接收不是数学核验：未核验推理保存待核验学习卡，不记错因/掌握/解锁；即使照片作答程序核验正确，自动整理也不直接点亮知识点。后续检验仍遵守U1～U5。旧单题/api/recognize、/api/study及Agent确认契约保留兼容，不是当前网页默认路径。

当前多题QA：`node docs/evidence/multiocr/qa.mjs`；原学习/检验/树：`node mytree/scripts/qa_phase_b.mjs --output docs/evidence/multiocr/flow`；暂停跨日：`node mytree/scripts/qa_quiz_pause.mjs --output docs/evidence/multiocr/pause`。这些仅合成资料/假上游。旧qa_junior.mjs不是本轮多题脚本，不用于无授权重发历史实拍照片。真实实拍识别质量须另有样本与人工逐题复核，不能把合成或HTTP成功外推为准确率。


## 官方题库候选（FR-029）

照片题列表的“找原题”是可选动作，不影响自动整理。`POST /api/questions/search` 接受 `batch_id/reading_id/source_revision/request_id`；正式账户始终由会话绑定档案，拒绝客户端正文、答案和任意 endpoint。来源过期或取消/版本错误返回409，外人来源404，未登录401。辅助 Schema 为 QuestionSearchInput/Output，不新增23个学习操作。

当前适配有道精品题库文本检索，完整题干少于50个字符，长题/图表依赖/内部题干矛盾明确unsupported，不截断。只传服务端题干，不传图片、学生作答或身份。结果状态为 not_configured / unsupported / no_results / candidates；上游超时、欠费、签名错误等为503+安全错误码，不伪装无结果。候选保留真实提供方题号，公开原题URL不可得时为null；不拿API开发文档充当题目链接。

候选始终未核对，比较为 text_equal / different / incomplete_or_unchecked；text_equal仅格式归一后文本相同，不能宣称原题已确认。外部HTML转换为纯文本，图片只标“未展开”，不代理/加载未知网址；图片公式或缺图不能称完整。搜索响应、页面和缓存不包含答案/解析，避免绕过H3；不替换题干、不写卡片/掌握/错因等学习状态。

开通 [有道控制台](https://ai.youdao.com/console/) 的精品题库API应用后，在项目根运行：

```sh
python3 mytree/scripts/configure_questionbank.py
```

输入均隐藏，保存到 `mytree/data/deployment/questionbank.json`（0600）；密钥不发聊天。也可用服务端 MYTREE_YOUDAO_APP_KEY / MYTREE_YOUDAO_APP_SECRET。部署脚本读取私有配置并写入受限runtime.env。默认全站每日最多20次上游请求、单账户每分钟6次；SQLite计数跨重启保留，超时或失败也占次数，429说明原因。按账户+来源+完整题文+提供方配置缓存10分钟，容量128项；先校验来源再缓存，快速并发单飞；服务重启会清缓存，失败后不承诺计费exactly-once。

官方文档的q字段与示例以图片为主；当前text适配按q=Base64(UTF8完整题干)、签名v2实现，固定向量和模拟协议已验证，实际text编码和服务权限必须在账号开通后通过真实官方成功请求核实。仅配置了密钥不代表已真实联通。未配置时入口明确“尚未开通”。

验证命令：`mytree/.venv/bin/python -m unittest discover -s mytree/tests -p 'test_question_search*.py' -v`；浏览器与范围证据见 `docs/evidence/questionbank/`。


## 探索语音（2026-11-15）

录音识别与回复播音分开：ASR仍 `gpt-4o-mini-transcribe`；本次显式选定 `tts-1-hd` + `nova`，并取消设备 `speechSynthesis` 优先和静默回退。没有新增接口字段或供应商。HD不发送不支持的instructions；新款mini-tts在当前服务未提供可用调用，不作为运行默认。

英文字幕始终保留；TTS生成失败、坏音频或限流可按继续只重试播音，不重新请求同一画面/问答。成功生成的音频仅内存保存，打断/提问后按buffer offset续播，不重复合成；后台和退出关闭媒体。

实测ASR用本机合成的自编短问返回正确文本（非真人麦克风验收）；实际TTS共4次尝试均失败，HD本机与服务器均429，没有可试听样本。不要把29模拟UI/257单元检查通过写成自然听感或完整真人对话已通过。未解决限流前以文字可用的受限状态交付。官方旧Speech模型生命周期见DESIGN005，本次不自动迁移Realtime架构。

证据、失败结果和范围见 `docs/evidence/voice-bank/`；测试 `node mytree/scripts/qa_explorer.mjs --output docs/evidence/voice-bank/ui-final` 使用模拟音频与媒体，不调用真实模型。

## 青少年界面与按题示意图（PRD2.12）

桌面顶部图文导航、手机/窄屏底部导航；知识树为通透画布，标题/整理/目录浮层，保留拖拽、键盘、撤销。未支持三题检验的知识点不显示无效操作或长说明，后端解锁边界不变。题卡回看保留原始作答，编号展示；可直接记下新想法，仍走有版本检查的卡片编辑接口。

`POST /api/visual/lesson` 需要同源和登录，档案强制来自账号；本机演示才使用student。仅接收`diagnosis_id`（以及兼容student），不接受自带题干、模型、地址、quiz/exercise编号或变式。读取本人诊断/学习来源；不存在/异主返回404，错误字段400。显式入口标明含解题思路，成功返回/缓存重放均记录该原题三级提示访问，不计分、不修改原题、检验答案、解锁或成长。

响应`ok, diagnosis_id, problem, title, verification, rendering, max_hint_level_recorded, steps[{caption,svg}]`。通用题由既有NextLabs tutor模型（当前gpt-6.1-sol）生成受限JSON；2～4步，每步1～24图元，最多40顶点/图元，坐标0～100，文字/总量有界。程序校验后绘制SVG，模型不能提交SVG/HTML/事件/URL/任意表达式。结构安全不等于数学正确：通用图标`ai_review`辅助示意；条件不足可拒绝或只展示不唯一性。可识别平方差使用程序等面积三步模板，不把AI错误边长用于教学。

缓存最多40份/档案，按原题/上下文哈希/完整提示权限/渲染版本绑定；失效来源拒读，重复复用，错误不缓存。同题并发生成返回429；共用模型并发/限流/65秒等既有上限。无法画图422、格式无效/上游失败502或既有模型错误码，界面保留文字/关闭/手动重试。关闭或切页不显示迟到成功/错误；已发出的有界供应商请求可能完成并缓存，前端关闭不承诺撤销已发生的调用。检验没有新增作图入口，客户端不能将检验题编号变为此接口的来源。

字体全部本站提供，`web/fonts/manifest.json`记录来源及SHA，三个OFL许可随文件保留。中文LXGW WenKai核心877字约160KB/字重，其他字符按Unicode分片加载；英文Sora可变字重；只读公式经KaTeX受限解析输出原生MathML，用STIX Two Math真实MATH表排版。活动MathLive仍保留原有编辑字形/度量/光标/键盘；失焦原值生成STIX预览，不改LaTeX答案。没有把STIX强套到KaTeX HTML度量，也未切换编辑器。加载失败有可读字体回退，未宣称各设备完全同像素。

验证和限制见`docs/evidence/youth-visuals/README.md`；旧voice-bank TTS失败为历史记录，当前线上Qwen语音状态见focused-learning证据，不由本轮字体/图形变更改为另一语音模型。

## 2026-11-15 首轮产品体验与家庭中心（历史邀请方案）

以下家庭邀请接口属于历史版本，已被后文“同账号家长端”取代；旧邀请不再授予访问权限。

公开首页恢复产品说明及实际示例截图；匿名根路径为首页，邮箱登录后首次在当前浏览器按档案显示三步截图指南，关闭/跳过/完成记为已看，帮助可重看。家长登录保持 `/parent` 目标，不进入学生指南。截图仅来自临时自编题档案，无真实儿童资料。

家庭中心使用现有邮箱会话；数据表与账号在同一SQLite中增量创建，旧会话/档案不迁移、不重置。`GET /api/parent/overview` 返回 `children`（已绑定孩子邮箱、累计已做对练习 `practice_correct`、点亮知识点 `knowledge_count`、复习安排数 `review_count`、最多5项记录类型/时间摘要）、`parents`（当前学习者已关联家长邮箱）及说明。不读取客户端student参数，不提供任意孩子详情查询。

- `POST /api/parent/invite {email}`：以当前学习者创建指定家长邮箱邀请；返回 `invite_code`、`expires_in=600`、`email`。最多5条有效邀请，自绑定拒绝。邀请码只向创建者返回，不自动发邮件，库内只存HMAC摘要。
- `POST /api/parent/accept {code}`：只允许邀请指定邮箱的登录账号兑换，事务内建立唯一关系并删除邀请，并发只能一次成功。无效/过期/已用/邮箱不符统一400 `FAMILY_INVITE_INVALID`。
- `POST /api/parent/revoke {email}`：当前关系任一方解除；同时清除对应待用邀请，幂等。后续读取不再返回孩子摘要；不删除孩子学习记录。
- 上述接口未登录401、跨源写403、操作限额429、存储不可用503；邮箱认证与双方分享授权不等同法律监护身份认证，不提供改孩子学习事实的接口。

识别超时显示简短错误及重试按钮；不清预览，沿用同页request_id/client_generation恢复；已有批次仅继续未完成整理。探索保持sol/Qwen/Cherry，默认简短英文、各阶段真实等待秒数、最多6条本会话解码音频复用；离页清缓存与轨道，不自动切设备音色。上游响应/完整合成耗时不等于首个可听声音时延。真实探针只使用自制图；单次样本不证明总体性能。

自测入口：`node mytree/scripts/qa_product.mjs`、`node mytree/scripts/qa_explorer.mjs --output docs/evidence/product-polish/explorer`、`mytree/.venv/bin/python -m unittest discover -s mytree/tests`。真实探针 `mytree/scripts/probe_product_latency.py` 会调用实际已配置供应商一次读图及一次TTS，不应无意反复运行。结果和本批状态见 [产品完善证据](../docs/evidence/product-polish/README.md)。

## 2026-11-15 悬浮拍题与知识树视觉

初始拍题面板仅拍摄/上传按钮。选图后原图保持width随容器、height自动的自然比例，左右重拍/相册、关闭、底部识别和PDF页码均悬浮；无常驻框选按钮/说明。单指或鼠标拖框松开应用，双指浏览；辅助说明、键盘选框/取消及长图浏览路径保留。四周72px平移余量允许把浮层遮住的角落移到可读位置，默认抵消余量，不新增常驻顶部空白。换图/切页及迟到识别仍隔离，无额外模型调用。知识树只改美术背景/卡片/实际数量展示，保留真实坐标与检验/保存语义。新独立验收与真实发布见[证据](../docs/evidence/capture-gestures/README.md)，实机触控/相机选择器与读屏仍须单列，不能用浏览器仿真替代。

## 同账号家长端（FR-011/018/033，用户最新要求）

`/parent`沿用当前邮箱账号，服务器固定读取该账号profile_id，不要求邀请码/孩子邮箱。首次设置家长密码需要该账号邮箱的parent_setup目的验证码，忘记密码使用parent_reset；以后仅输入家长密码。家长端不开放改孩子答案、分数或树。旧分享表保留历史，但invite/accept/revoke均410且不能读取他人数据，不合并账号、不转移或删除学习资料。

接口均依赖真实基础登录与同源写保护：

| 接口 | 字段与行为 |
|---|---|
| GET /parent | 撤销当前基础会话的家长会话并清独立Cookie，再返回密码页；刷新/重入不自动展示摘要 |
| GET /api/parent/status | configured/unlocked/email/expires_at，无学习事实 |
| POST /api/parent/send-code | `{purpose:parent_setup或parent_reset}`，目标邮箱固定服务器账号；返回60秒重发/600秒有效，无明文验证码 |
| POST /api/parent/setup、reset | `{code,password,confirm_password}`；消费用途绑定OTP与密码写入/版本升级同事务，首次并发只一方成功 |
| POST /api/parent/unlock | `{password}`；8～128字符，原样哈希不截断 |
| POST /api/parent/lock | `{}`；撤销家长会话，保留基础登录；不与模型配额共用限流 |
| GET /api/parent/overview | 未解锁403，未基础登录401；返回当前账号profile事实摘要，URL student无权改变档案 |

密码采用scrypt N32768/r8/p3、独立随机盐；两哈希槽、约32MiB每槽，参数参考[OWASP密码存储建议](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)。当前本机单次0.19～0.24秒，不冒称部署CPU延迟。错误密码/设置失败按账号5次/10分钟冷却，来源40次/全局200次；成功只释放本请求计数。发码每邮箱10次/日、来源20次/小时、全局100次/小时，60秒间隔；发送失败仍保留发送限额但撤回不可用码。用途、账号、10分钟有效、单次消费与5次错码限制独立于登录验证码。

家长Cookie为随机43字符令牌、HttpOnly/Secure/SameSite=Strict，库中仅摘要，绑定当前基础session摘要/邮箱/密码版本，15分钟绝对期限不续期。基础退出/换号/过期、锁定、重置均失权。刷新/缓存返回/后台先清敏感DOM；页面尽力发送锁定，网络失败明确显示“未确认”及重试，不谎称服务器已撤销；过期服务端兜底。锁定/状态确认中门页暂不可输入，防止旧锁请求追上新验证；迟到解锁再锁、迟到摘要不回填。密码不存浏览器storage/URL/日志，允许粘贴/管理器/显示密码；仅邮箱控制者可重置，因此建议账号邮箱由家长掌握。

自测：`python -m unittest discover -s tests -p test_parent_access.py`、`node mytree/scripts/qa_parent_password.mjs`及WebKit同脚本。所有测试邮箱/密码/数据为临时合成；脚本专用OTP oracle只存在测试服务，部署allow-list不含scripts。当前独立验收与发布见[证据](../docs/evidence/parent-password/README.md)。旧qa_product.mjs邀请流程为历史测试，不适用于新家长模式。

家长独立密码版本已于2026-11-15发布为`mytree-20261115T104415Z`；Astra独立复核通过，公网52项检查与运行源352文件清单一致。后续邮件/feedback发布为其他批次，不能混用本批验收结论。


2026-11-15 图解排版更新：`MYTREE_DIAGRAM_MODEL=glm-5.3-flash` 仅用于无源图通用图解；有原题裁图的图解继续使用 `MYTREE_VISION_MODEL=kimi-k3.1-pro`，文字讲解仍 `gpt-6.1-sol`。代数四选项恒等式在受支持的多项式范围内由程序核对和排版，不调用模型；普通推导输出受约束lines，由前端数学组件渲染。未支持或失败明确重试，不静默换模型。会员仅展示标准59元/月与进阶119元/月，年价未确定故隐藏并拒绝选择，支付未开放。新版本状态以本批证据为准。

### Mem0 长期记忆与个性化复习（已发布与模拟器验证）

Mem0 OSS `mem0ai==1.0.3` 使用本机持久 Qdrant，索引目录默认与 `MYTREE_MEMORY_DB` 同级的 `mem0/`（可用 `MYTREE_MEM0_DIR` 指定），目录权限700；部署须放入 `/data` 持久卷。`MEM0_TELEMETRY=false`，不使用 Mem0 云。嵌入复用服务端 NextLabs 配置与 `text-embedding-3-small`；仅索引来源事实 `infer=False`，不会调用 LLM 抽取或修改成绩。初次同步批量嵌入，后续仅补新增/更新，查询向量缓存，索引与学习档案分开持久化。单进程使用本机 Qdrant；多进程扩容须先迁移独立向量服务。

`POST /api/review/personalize {}` 使用登录账号绑定档案，返回安排列表、reason/based_on、memory.engine/status。Web/Android 学习桌复习及复习计划提供“更新个性化复习”；完成三题复习后重新排序。保留已有到期时间，新建沿用1/3/7规则；没有可核验匹配练习不新增。向量只找候选知识点，完整近期来源事实决定排序。`POST /api/memory` 仍支持retrieve/preference/forget。故障明确 `source-ledger/unavailable`，来源档案不受影响；`MYTREE_MEM0_ENABLED=0` 可显式禁用。撤回是停止用于教学记忆，不删除原始作答与原有复习档案。实测与独验状态见 docs/evidence/mem0-personal-review。

图解/会员页当前发布 `mytree-layout-20261115T151157Z`：Astra543通过，369源SHA/20公网/8协议/2匿名价格UI通过；标准59元/月、进阶119元/月，年付拒绝、支付未开放。图解GLM/视觉Kimi/文字GPT，生产私有仅图解模型字段变化；详细证据 `docs/evidence/diagram-pricing-speed/README.md`（codex-layout545/548回执）。

测试额度独立发布`mytree-test-quota-20261115T152107Z`已健康（codex-test-quota572/Astra566回执）；精确绑定目标账号100题/日、1000探索/月，普通3/10，原计数保留。仅billing.py和私有MYTREE_TEST_PROFILE变化，后续发布须完整继承此配置，不将测试账号标为付费。

Android与Web共用MathUI及交互；幂、乘法、分式/根式及裸ASCII/LaTeX混排均数学渲染，复习依据显示可读原题并排公式，学习记忆同样渲染，不向孩子展示原始事件ID或用源码替代有效数学排版。输入与保存原文、评分均不因显示变化而改变。


## 官方AI接入（2026-11-16，已部署）

用户要求读图、文字与语音低延迟优先，先提供千问快速型号的接入预设：视觉/文字/图解 `qwen3.6-flash`、`enable_thinking=false`，ASR `qwen3-asr-flash`，TTS `qwen3-tts-flash` / Cherry。型号是待实测候选，不代表已测得最低延迟或识别质量通过。用户完成私有配置后，本机及线上已切换官方接口，历史发布记录保留；当前发布与验证见本节末尾。

在 `mytree` 下运行 `.venv/bin/python scripts/configure_official_ai.py`，在本机终端隐藏输入百炼API Key。非北京账号用 `--base` 提供对应地域/业务空间的官方 compatible-mode URL；可用 `--vision-model` / `--tutor-model` 指定账号已开通型号。脚本原子更新服务端 `.env.local`（0600），保留其他配置，不发送API请求。环境变量优先于文件，生产环境需要另行更新私有runtime配置并验证/发布。

要用DeepSeek讲解和图解，加 `--deepseek`，另隐藏输入DeepSeek Key；默认候选 `deepseek-flash`，可通过 `--tutor-model` 覆盖。读图继续千问。火山语音目前尚未实现，需按用户选用的服务及资源ID另行适配，不将通用兼容接口称为火山已接入。

各角色支持独立 `MYTREE_<ROLE>_API_BASE` / `MYTREE_<ROLE>_API_KEY`，ROLE为 VISION/TUTOR/DIAGRAM/ASR/TTS/EMBEDDING；旧共享配置保留兼容。指定不同地址时必须单独配置Key，不会把旧供应商密钥发往新地址。千问ASR使用chat/completions音频输入，TTS使用DashScope原生接口，官方签名音频由服务器限长下载，无Key转发或重定向，前端仍收到原有audio_data。当前探索朗读仍按原功能仅英文，千问单次最多600字符，失败保留文字及重试；未新增实时流式播音。

配置后运行 `.venv/bin/python scripts/configure_official_ai.py --check`，将对读图/文字/图解/合成/识别/embedding发起真实计费测试，只用合成资料，输出各角色成功状态及总耗时，不打印密钥和原始响应。该测试用于联通和初步耗时，不替代实拍识别、教学质量、浏览器/Android录音播放闭环及独立验收。

记忆embedding可独立配置型号和维度。千问预设 `text-embedding-v4` / 1024，不同向量空间使用新的本地索引目录，查询时从已有来源记录逐步建立索引；原学习记录和旧索引保留。首次检索存在建索引额外耗时；embedding不可用时明确降级到已有来源记录。

协议来源：[千问视觉](https://help.aliyun.com/zh/model-studio/vision)、[结构化输出](https://help.aliyun.com/en/model-studio/qwen-structured-output)、[ASR](https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference)、[TTS](https://help.aliyun.com/zh/model-studio/qwen-tts-api)、[Embedding](https://help.aliyun.com/en/model-studio/text-embedding-synchronous-api)、[DeepSeek](https://api-docs.deepseek.com/api/create-chat-completion/)。


2026-11-16线上回执：`mytree-official-speech-20261115T164637Z`已独验后隔离发布，375公开源只有ai/speech/mem0_adapter/explorer四文件相对前一生产版本变化，373容器运行源SHA一致。读图/文字/图解qwen3.6-flash，ASR qwen3-asr-flash，TTS qwen3-tts-flash，embedding text-embedding-v4/1024，均北京百炼官方。27AI私有字段更新，其他字段、TEST_PROFILE和持久卷保留，实际容器重启及隔离合成记忆持久化通过。录音新增实时音量、静音/过短预检和可操作恢复提示；两组已知TTS流式WAV占位头按实际完整PCM帧处理。用户偶发空转录根因尚未关闭；物理设备扬声器测试句成功不等于真人人声准确率通过。完整证据[线上录音与官方切换](../docs/evidence/speech-capture/README.md)。
