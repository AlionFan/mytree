# macOS 本机复习提醒

提醒程序每次只检查一次服务端待办，不需要学习页面打开。服务端决定空闲时段、每日频率和“今天不看”；客户端不保存这些业务状态。应用服务仍需运行，电脑需登录且未休眠。系统通知可见性也受 macOS 通知与专注设置影响。

配置必须与网页使用同一匿名档案。`MYTREE_STUDENT` 是本机演示档案编号，不是身份认证；此客户端不携带模型密钥。

手动检查（在项目根目录）：

```sh
MYTREE_BASE=http://127.0.0.1:8000 MYTREE_STUDENT=你的档案编号 mytree/.venv/bin/python mytree/reminder/mytree_reminder.py
```

测试时设置 `MYTREE_NOTIFY_LOG` 为临时文件：只追加一行通知记录，绝不弹系统通知。正常发送后才确认服务端；发送失败不确认，网络失败记录一行并结束，不循环重试。相同客户端重叠运行通过本机文件锁跳过；不同客户端同时检查与通知成功后确认丢失的边界仍由后续送达协议完善，不能宣称分布式严格一次送达。

生成每 15 分钟检查一次的登录代理配置（这条命令不安装、不加载）：

```sh
PYTHON=mytree/.venv/bin/python sh mytree/reminder/install.sh --student 你的档案编号 --output output/reminder
```

检查生成的 plist 后，按脚本打印的命令自行安装。停止与移除命令由 `sh mytree/reminder/uninstall.sh` 打印；该脚本不会执行系统变更，不删除学习档案。系统代理安装后，项目和 Python 解释器需保留在生成时的路径。

单元测试使用本机假服务与通知替身，不真实弹窗：

```sh
mytree/.venv/bin/python -m unittest discover -s mytree/reminder/tests -v
```

真实通知、重复抑制及“今天不看”须另外连接实际服务验收。仅命令退出成功不能证明用户看到了系统通知。
