# 小树同学 Android

按现有网页版制作的 Android 客户端，最低 Android 8.0，需保持 Android System WebView 更新。路线由 Astra 消息317批准，需求见 [FR-016](../docs/PRD.md) 与 [ANDROID-001](../docs/collaboration/ANDROID-001.md)。

应用使用受限 HTTPS WebView 连接 `https://mytree.joybeat.cn`，复用当前线上网页界面、邮箱验证码账号和服务端学习记录。网页发布的更新会在客户端重新加载时生效。旧离线示例界面已替换，不迁移示例进度。需要联网，不内置模型密钥，不提供后台提醒。

原生处理：拍照后返回原图；系统文件选择器选择图片/PDF；取消回调与临时照片清理；相机/麦克风按使用申请，拒绝相机时可改选文件；系统返回、软键盘窗口调整、加载错误重试、旋转/重建恢复；切后台停止探索及媒体。进程被系统回收后会重新加载网页；未保存的图片/输入需重新选择或填写，已保存服务端记录仍按账号恢复。文件选择遭进程重建时会明确提示重新选择。会话由现有网站管理，登录同一邮箱使用同一份服务端记录，退出逻辑沿用网站。模型服务失败仍由网页明确提示，不会自动换模型。

只在 WebView 内导航确切同源 HTTPS；不接受 HTTP、错误证书、任意 intent/file/content 顶层导航，不加通用 JavaScript 原生桥。第三方 Cookie 和混合内容关闭；外部 HTTP(S) 链接由用户选择后交浏览器。网页内的文件下载目前提示用浏览器，不内置下载器。

## 构建与安装

本机 Android SDK 35、Java 17：

```sh
cd /Users/fan/Code/HKS/android
JAVA_HOME=$(/usr/libexec/java_home -v 17) ANDROID_HOME=/Users/fan/Library/Android/sdk ./gradlew clean assembleDebug assembleDebugAndroidTest testDebugUnitTest lintDebug
/Users/fan/Library/Android/sdk/platform-tools/adb install -r app/build/outputs/apk/debug/app-debug.apk
```

这是本机 debug 签名体验包，非应用商店发行包；之后正式发行需要确定独立的签名与分发方案。包名 `cn.joybeat.mytree`，版本 `0.4.0`（code4）。如果旧包签名不同，需先备份确认后处理，不自动卸载清空。

## 验证

```sh
JAVA_HOME=$(/usr/libexec/java_home -v 17) ANDROID_HOME=/Users/fan/Library/Android/sdk ./gradlew connectedDebugAndroidTest
```

`app/src/androidTest` 验证确切域名、安全设置、媒体来源/资源拒绝、文件回调取消、相机取消后的清理、临时照片提供器边界、后台停止探索与销毁回调。使用合成夹具，不是 OCR 准确率或教学有效性测试。

`qa_boundaries.mjs`、`qa_sessions.mjs`、`qa_gestures.mjs`、`qa_media.mjs`、`qa_offline.mjs` 分别验证边界、合成会话、长图/PDF、媒体后台和断网恢复；`qa_native_files.mjs` 等待操作模拟器系统相机/文件界面，返回真实文件。各脚本只允许运行在模拟器中。

`qa_webview.mjs` 仅允许运行在模拟器中，连接已启动 debug WebView 的 CDP 端口，将同源请求拦截到现有隔离 QA 服务，使用合成照片/假模型/临时档案跑真实学习→三题检验→解锁→树拖动保存。它不替代原生文件选择器或真实邮箱、相机、真人语音验收。启动应用后，找到 `/proc/net/unix` 中 `webview_devtools_remote_<pid>`，用 adb forward 将它转到本机9224，再运行 `node qa_webview.mjs`。debug/CDP不在非debug构建启用。

实际执行结果、APK与SHA、系统/WebView版本及未测项见 [本轮证据](../docs/evidence/android/README.md)。物理设备、真实账号和真人语音未验证时不得宣称 FR-016 全部通过。

## 2026-11-15 首次权限与反馈修复

0.3.0（code3）修复系统相机/麦克风首次权限覆盖层导致本次采集手势被取消：权限覆盖层保留本次请求，真正进入后台onStop取消并停止媒体；返回不自动恢复采集。17原生测试、首次相机授权/首有效帧、首次麦克风授权后真实ASR及边界/学习/会话回归通过，独立验收状态见 [本批证据](../docs/evidence/feedback-1115/README.md)。录音使用合成语音虚拟麦克风，不冒称真人；真实OTP已在同源客户端验证。生产网页更新后重新加载生效。


## 0.4.0 · 长期学习记忆与统一界面

复用已获Astra独验并上线的 Mem0 长期记忆与个性化复习，后台存储不放入APK；Web与Android共享悬浮控件、文字布局及数学渲染。复习来源和学习记忆中的幂、乘法、分式/根式均排版，原题和评分不因显示改变。Android14项闭环、Web/APK同视口16项、公式定向与独验见 `docs/evidence/mem0-personal-review`。

本机Android Studio Quail 3初次打开已配置现有SDK35；Studio自带Java25不适配本项目Gradle8.9，项目Gradle JDK须使用已安装的Temurin17（与命令行构建一致）。不为此升级Gradle/AGP。新增0.4仅提高原生版本号，现有受限HTTPS/权限/文件/后台安全处理保持原实现。本批已完成clean全量编译（71任务），17/17原生测试及最终0.4 APK的14项Mem0界面闭环通过，lint 0错误/3既有警告。首轮模拟器SystemUI无响应造成Back测试失败，重启并补真实窗口焦点前置条件后定向及全量复验通过；原始失败证据保留。

已导出并安装 `outputs/MyTree-0.4.0-debug.apk`，APK v2签名及zipalign核验通过；SHA256 `764e96a8271b277ba9a7b032340551a65a87a38b78e95647e72bf997b9b5a066`。Android Studio保留源码与嵌入式可见模拟器，应用恢复正式线上首页。详见 [本轮完整记录](../docs/evidence/mem0-personal-review/README.md)。
