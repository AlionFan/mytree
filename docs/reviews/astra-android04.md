# Android 0.4交付复核

Astra审阅590及593交接，本次限定最终导出APK和微小版本/测试delta，Mem0仍沿用580独验及已发布版本，不重复运行已验功能。

独立核对android/outputs/MyTree-0.4.0-debug.apk：24642字节，SHA256 764e96a8271b277ba9a7b032340551a65a87a38b78e95647e72bf997b9b5a066，包cn.joybeat.mytree，versionCode4/versionName0.4.0。实际调用apksigner确认v2签名且与0.3同一debug证书；zipalign检查通过。对两个APK解包逐文件比较，只有classes2.dex与AndroidManifest.xml不同；dexdump及manifest结构逐行差异均仅版本常量3→4、0.3.0→0.4.0，原生逻辑/权限/资源保持。

测试改动已阅读：真实Back前最多10秒等待Activity窗口焦点、decor可见且未结束，超时明确失败；仍发送真实KEYCODE_BACK并断言dialog关闭，没有改用直接回调或成功重试掩盖。审阅最终XML为17 tests、0 failures/errors/skipped，clean构建日志71任务全部执行成功；lint0错误3警告（UnusedAttribute、GradleDependency、SetJavaScriptEnabled）。这些为执行方测试证据，本轮未署为Astra独立重跑。最终APK14项Mem0 UI为执行方复跑，先前冻结Web与Mem0的独验结论保持。

核对时发现移动工作区MainActivity SHA不符，已返核592。执行方593确认仅首字节多一空格并保留异常副本，修正后Astra重新核全部10源码SHA完全匹配交付清单，MainActivity亦匹配0.3基线；执行方已另存android04-frozen物理冻结。以固定APK及清单为交付对象，不能将后续移动源码默认为此包版本。

结论：Android0.4可安装debug测试包交付复核通过。未宣称正式发行签名或实体手机实测。证据docs/evidence/astra-android04；Studio可见/模拟器安装状态依据执行方观察，本次未接管其窗口。
