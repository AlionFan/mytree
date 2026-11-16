# 小树同学 · HKS

面向初中学生的错题整理与主动复习学习 Agent：拍题 → AI 整理错题卡 → 主动带来复习任务 → 适度练习并答对检验题 → 获得知识卡 → 孩子亲手整理并养大知识树；持续画像支撑迁移和适度进阶推荐。参考成长分已接入；真实多用户排行仍待后续。

**后续开发以 [PRD](docs/PRD.md) 为共同需求与验收基线。** 当前是本机演示项目，部分初中扩展正在开发；具体支持范围不能只按目录或接口数量判断。

新主线由 [PRODUCT-001](docs/collaboration/PRODUCT-001.md) 与 [PRODUCT-002](docs/collaboration/PRODUCT-002.md) 定义。卡片、复习待办、检验解锁与可编辑树已通过 Codex 的12段真实HTTP自测，等待 Astra 独立验收；系统通知实际可见、三层画像/推荐等边界分别记录，不把自测当作完整验收通过。

按用户当前分工，**Astra 定方向、做设计审查和监督验收，Codex 负责修改与执行**（用户因 Claude 额度用完而指定接任）。统一视觉模型选定为 `kimi-k3.1-pro`（独立验收后发布），纯文字讲解保持 `gpt-6.1-sol`；当前决定见 [决策记录](docs/collaboration/decisions.md)。

| 文档 | 用途 |
|---|---|
| [PRD](docs/PRD.md) | 产品目标、需求编号、优先级、业务规则和验收场景 |
| [PRD 思维导图](docs/PRD.xmind) / [更新说明](docs/PRD思维导图说明.md) | 可编辑的分层需求、架构与输入输出快照 |
| [Agent 与 Harness](docs/architecture/agent-architecture.md) / [交互图](docs/architecture/agent-harness.html) / [输入输出契约](docs/architecture/agent-contract.schema.json) | 多端调用边界、23 个操作、运行核验与当前实现映射 |
| [AGENTS.md](AGENTS.md) / [ASTRA.md](ASTRA.md) | Codex 执行与 Astra 指导的开发入口 |
| [协作协议](docs/collaboration/README.md) | 消息、任务认领、接口协调和交接 |
| [网页 README](mytree/README.md) | 安装、运行、各端入口、模型配置及 HTTP 契约 |
| [设计约定](docs/design-contract.md) | 页面、上传与状态细节 |
| [验证记录](docs/evidence/) | 历次版本的检查与截图，不代表当前代码已通过 |
| [项目思路](项目思路与准备清单.md) / [技术方案](技术方案与选型.md) | 比赛背景、商业设想和历史技术选型 |

网页启动：按 `mytree/README.md` 安装依赖后，在 `mytree/` 运行 `./run.sh`；默认 `http://127.0.0.1:8000/`。本目录当前未建立 Git 仓库。

协作状态：`python3 tools/coord.py status`。共享通信依赖双方读取规则；闲置或未加载规则的外部会话不会被文件消息自动唤醒。

## 版本管理

GitHub 私有仓库：[AlionFan/mytree](https://github.com/AlionFan/mytree)，开发分支为 `develop`。首次导入是当前工作区开发快照，包含正在开发的功能，不等于线上发布或全部验收通过。

凭据、用户数据、原始试卷、本机验收档案、虚拟环境和构建产物保留本地，不提交。配置从 `mytree/.env.example` 创建本机私有配置；依赖历史实拍材料或本机验收档案的专项脚本需另行准备相应输入。

## Android 状态

按用户2026-11-16要求，安卓客户端代码暂从 GitHub 移除；本地保留用于后续调试，修复并完成验收后再上传。当前仓库提供网页与服务端。详见[状态说明](docs/android-status.md)。
