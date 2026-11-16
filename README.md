# MyTree · 小树同学

面向中学生的 AI 学习助手，当前从初中数学切入。通过拍照或上传题目，整理题干与原样作答，提供分级讲解、巩固练习和语音辅导，并用知识树呈现学习记录。

## 功能

- **拍题学习**：图片 / PDF 选页与框选、整页多题识别、识别结果核对、原样作答展示。
- **数学辅导**：以解题思路和步骤为主，按需提供图形；支持的数学结构使用独立程序核验。
- **巩固练习**：AI 根据原题考点生成三道关联练习，提供参考反馈。未程序核验的 AI 反馈不计入掌握或成绩；旧三题检验入口已停用。
- **探索者**：语音对话与视频英语探索，可选择本人题目进行辅导；画面与对话字幕同屏。
- **学习记录**：上传图片历史、知识树、复习计划及家长查看入口。
- **Android 客户端**：通过受限 HTTPS WebView 复用网站和账号，附原生拍照、文件选择及媒体权限处理。

项目仍在持续开发。复杂几何证明、模糊手写与真实语音识别存在限制；上传源码不代表每项功能都已验收或与线上版本完全一致。

## 本地运行

需要 Python 3.12 和 [uv](https://docs.astral.sh/uv/)。

```sh
git clone https://github.com/AlionFan/mytree.git
cd mytree/mytree
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env.local
# 在 .env.local 中填写自己的模型服务密钥
./run.sh
```

浏览器打开 <http://127.0.0.1:8000/>。默认只监听本机；可通过 `HOST` 和 `PORT` 调整。默认本地演示不启用邮箱认证，不应直接将该模式开放到公网。

配置示例采用阿里云百炼官方兼容接口，包含读图、文字讲解、语音识别、语音合成和向量模型；可按角色设置独立地址与密钥。以 [`mytree/.env.example`](mytree/.env.example) 和 [`configure_official_ai.py`](mytree/scripts/configure_official_ai.py) 为准。运行 AI 功能需要自行开通相应服务并承担调用费用。邮箱认证另需配置 SMTP 和服务端认证密钥。

## 目录

| 路径 | 内容 |
| --- | --- |
| [`mytree/app/`](mytree/app/) | Python HTTP 服务、学习逻辑、数学核验与模型适配 |
| [`mytree/web/`](mytree/web/) | 网页界面、数学排版与本地字体资源 |
| [`mytree/tests/`](mytree/tests/) | 后端回归测试 |
| [`mytree/scripts/`](mytree/scripts/) | 配置、评测与浏览器检查工具 |
| [`mytree/deploy/`](mytree/deploy/) | Docker 与部署脚本，部署前需按自身环境配置 |
| [`android/`](android/) | Android WebView 客户端与构建说明 |
| [`docs/architecture/agent-contract.schema.json`](docs/architecture/agent-contract.schema.json) | 服务端运行所需的输入输出契约 |

## 开发与验证

在 `mytree/` 目录中，可运行后端测试与 JavaScript 语法检查：

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
node --check web/app.js
```

部分集成测试和评测脚本需要模型服务、浏览器、Android SDK 或未公开的本机验收材料，需按相应说明准备。测试数据应使用临时档案，避免写入真实学习记录。

详细说明：[`网页运行与接口`](mytree/README.md)、[`Android 构建`](android/README.md)、[`架构契约`](docs/architecture/agent-contract.schema.json)。子目录 README 含历史版本说明；部分内部材料和验收档案未公开，相关链接或专项脚本所需输入需另行准备。

## 数据与版本

公开仓库仅用于源码与开发文档分享。密钥、私有 `.env`、账号及学习数据库、用户上传原图、原始试卷、本机 QA 档案、构建缓存和 APK 不纳入提交。不要将真实凭据或儿童资料写入 Issue、日志或提交。

`main` 是公开源码分支。开发快照、验收结论和线上发布分别核验。前端依赖和字体保留各自许可证；本项目未另外指定整体开源许可证。
