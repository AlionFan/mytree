# mytree.joybeat.cn 个人体验版部署

用户于 2026-11-14 明确授权上线。复用 SSH 别名 `joybeat`、已有 Docker 网络 `coolify` 与 Traefik `letsencrypt` 解析器；新路由只匹配 `mytree.joybeat.cn`。不改官网容器、其他主机路由、DNS或全局代理配置。

运行 `mytree/deploy/deploy.sh`。脚本从现有服务配置生成私有运行变量，显式打包 app/web/requirements/契约，不打包实拍试卷、档案、eval、测试服务或 `.env.local`。构建标签按时间，发布后验证容器健康、可信 HTTPS 公开首页200、登录页200与未登录知识树跳转303；失败恢复前一版本及前一私有配置。首次发布失败只移除本服务容器。

服务器：
- `/srv/data/mytree/releases/`：不可变源码版本。
- `/srv/data/mytree/current`：已验证发布。
- `/srv/data/mytree/private/runtime.env`：模型配置、SMTP 授权码和账号会话签名密钥，root 0600。
- `/srv/data/mytree/data/`：档案/脱敏用量，应用 UID 10001，0700，独立持久化。

账号登录采用邮箱验证码：访问网站跳到 `/login`，验证码 10 分钟有效、成功后一次失效；首次验证创建账号。Cookie 会话 7 天有效，可退出撤销；不再使用共享 Basic 密码。账号持久化于 `/data/auth.sqlite3`；学习档案继续存于 `/data/profiles.json`，服务端强制绑定账号，旧匿名资料不自动转移。

用户指定发件邮箱 `1317483655@qq.com`，SMTP `smtp.qq.com:465`，SSL 验证证书。先在 QQ 邮箱设置中开启 SMTP，生成授权码，再运行 `python3 mytree/deploy/configure_email.py` 隐藏输入并保存到 `mytree/data/deployment/smtp.json`（0600）。这不是 QQ 登录密码。`auth-secret.json` 保存随机签名密钥，重新发布时复用，不能随意重置。所有私有文件均不打包、不进入证据。部署生成的 runtime.env 只通过 SSH 私有传输。

`POST /api/auth/code` 发送验证码，`POST /api/auth/verify` 验证注册/登录并设置 HttpOnly/Secure/SameSite Cookie；`GET /api/auth/me` 返回当前账号；`POST /api/auth/logout` 撤销会话。写请求须同源 Origin，未登录业务 API 返回401，不包含 Basic 挑战。服务未接 SMTP 时返回503明确说明；禁止用日志或网页显示验证码代替邮件。学习档案编号由服务端绑定，客户端 student/subject.profile_id 不作为授权依据。

邮箱发送间隔60秒、每邮箱每天10次、每来源每小时20次、全局每小时100次；验证码最多5次错误尝试，每来源10分钟最多60次验证。计数持久化并由数据库事务保护；SMTP失败保留发送限额但清除不可用验证码。只信任反向代理附加的最后一个 X-Forwarded-For 地址。

账号登录不代表已完成家长授权、资料导出删除或正式儿童服务全部要求。

服务以非 root、只读根文件系统、无 Linux capabilities、640MB 内存、1 CPU 运行。只接 Docker 内网，无额外宿主机公网端口。`/_ready` 仅返回布尔就绪状态，其余业务页面/API需账号会话；跨源 JSON 拒绝；模型调用限制60次/分钟、上游最多2并发。CSP 不开放脚本 unsafe-eval；inline style 为已有公式库/树位置兼容项。

探索：按空格或按钮唤醒；空格打断/继续；按住 V 录音、松开提交，也可点击语音按钮。视觉固定gpt-6.1-sol，转录gpt-4o-mini-transcribe，朗读显式采用NextLabs qwen3-tts-flash / Cherry；配置、示例和容器需一致。Qwen兼容Speech请求不传speed。播报失败保留英文和重试，不切换设备音色。已用真实生成音频验证解码、播放启动和偏移续播；真人麦克风、物理设备及听感仍待验收。离页/后台关闭全部轨道。

验证命令：
- `mytree/.venv/bin/python -m unittest discover -s mytree/tests -v`
- `node mytree/scripts/qa_explorer.mjs`：假设备、假模型，真实业务 HTTP。
- `node mytree/scripts/qa_phase_b.mjs`：旧拍照→卡→知识树浏览器回归。

实际公网校验和发布标识记录在 `docs/evidence/explorer-release`；服务配置文件存在不能当作已上线。


管理员私有配置另存于本机 `mytree/data/deployment/admin.json`（0600），字段 username/salt/hash；口令采用scrypt（n=16384,r=8,p=1），不存明文。部署仅传服务端私有变量 MYTREE_ADMIN_USER/SALT/HASH。管理员 Cookie 与学生分离，8小时有效；每来源15分钟最多10次登录尝试，全局100次。配置缺失无法登录，不使用默认密码。不要把用户指定口令写进说明、截图或日志。


## 2026-11-16 官方模型隔离发布现状

当前运行版本 `mytree-official-speech-20261115T164637Z`，相对Mem0生产基线仅改变ai.py/speech.py/mem0_adapter.py/explorer.js四文件，未混网页练习和解题讲解的并行工作。官方模型与27个AI字段在Astra最终清单229eef独验后更新；其他私有配置含TEST_PROFILE保留。375发布文件/373容器源逐SHA通过，真实生产ASR、可信HTTPS鉴权、隔离合成记忆实际容器重启验证通过，未写正式账号学习记录。

本批使用 `docs/evidence/speech-capture/prepare_release.py` 按线上SHA重建公开基线、`prepare_private.py` 只生成AI字段私有delta，`publish_release.py` 先暂存构建并在生产网络预飞六接口，再原子切换，失败恢复前一runtime与容器。私有文件不入公开包；已验证来源与运行回执在同目录。上面的deploy.sh为早期全量发布流程，尚未迁移至本批独立角色配置导出与保留线上原私有字段的流程；后续发布沿用已验隔离基线及串行窗口，避免用旧脚本覆盖新配置。
