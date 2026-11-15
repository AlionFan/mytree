# Android 薄壳预审与独立验收

2026-11-15，astra-lead；执行codex-android。FR-016 / AC-11 / FR-018 / NFR-004。

初次为未冻结源码预审；以下新增独立运行记录覆盖初审状态。A-R03已在修复冻结包独立复验关闭，范围与限制见文末。

## 0.2.0 冻结版独立运行（2026-11-15）

APK SHA256：`1ed177f74a6b9c72b27d4d648ec441b8240d2a8c93a9c7cc0ae475d08e6a4f14`。独立核对12项源码哈希，拉取设备已安装APK确认哈希相同。Android 15 / API 35 arm64 模拟器，WebView 124.0.6367.219，412×818 CSS viewport。

- 原生 instrumentation：14项通过；跨域/导航边界：9项通过。A-R01组合防线和A-R02前台/代次绑定已实现，在本次测试范围内通过；不把有限测试宣称为所有协议/重定向完全覆盖。
- 长图触摸/PDF：7项通过，双指浏览不误建选区，之后单指框选成功，实际上传裁剪像素，PDF翻页无横向溢出。
- 会话：7项通过，含匿名next、HttpOnly、退出失效、跨账号隔离，使用隔离服务预置合成会话，不代表真实邮件OTP全流程。
- 真实业务学习闭环：前6项通过，包括合成识别、错题入库、三题测验和知识卡解锁；系统返回关闭讲解窗口失败，不能把整条闭环标通过。
- 证据目录：`docs/evidence/astra-android/`，包括freeze-check.json、instrumentation.txt、boundaries.json、gestures/results.json、sessions.json及webview-back-probe/results.json。生产CSP独立只读获取并存live-csp.json。

### A-R03：键盘已隐藏时，系统返回未关闭真实知识讲解窗口（阻塞）

独立运行两次均失败：学习解锁知识卡后使用实际系统KEYCODE_BACK，`#knowledge-lesson[open]`持续可见，15秒等待超时。第二次额外记录返回前MathLive键盘false、原生IME mInputShown=false、activeElement BODY；返回后dialog仍open。原生合成dialog测试通过，不能覆盖该真实页面故障。

已通过共享消息338及后续设备交接要求codex-android定位并修复，冻结后重新独立验收，不允许以直接调用onBackPressed替代系统返回。模拟器在剩余测试完成后已交回执行方。消息340提出边界测试可能遗留原生外链确认框、Back先关闭它的假设；本次DOM截图与IME探针不能排除此因素，尚不能认定产品返回逻辑根因。要求补原生窗口证据；若证明测试污染，则修复QA清理并复跑，不任意更改产品返回语义。

限制：本次为模拟器实际WebView搭配隔离业务服务、合成图片/会话和模拟上游；物理手机手感、真实邮件OTP与真人语音仍未验收，执行方报告模拟器麦克风无法启动。不得据此宣称FR-016全量完成。

## 发布前返工

### A-R01：同源限制缺少实际请求和导航兜底

MainActivity仅在shouldOverrideUrlLoading检查trusted，onPageStarted只更新retryUrl，没有对不可信URL停止加载；没有shouldInterceptRequest等实际请求防线。因而不能据此宣称所有内嵌页面/资源均受同源限制。Android官方明确shouldOverrideUrlLoading不处理POST请求；shouldInterceptRequest也有重定向和协议限制，需要组合防线而不是换一个回调就声称完全覆盖。

要求：防止非可信顶层/子框架/资源在内部加载，明确允许的数据/Blob用途而不破坏图片/PDF与音频；导航变化同步撤销未决权限/文件请求。外站链接只能经明确用户操作交系统浏览器。补实际WebView测试：外站GET/POST表单、iframe/资源、重定向与非HTTPS、程序发起导航，验证未呈现外站且未误授媒体/文件能力，不仅直接调用trusted辅助函数。

依据：[Android WebViewClient官方参考](https://developer.android.com/reference/android/webkit/WebViewClient)。该API事实已查证，实际设备行为仍待运行验证。

### A-R02：原生相机权限返回缺少前台与请求身份绑定

onRequestPermissionsResult的CAMERA_PERMISSION分支直接调用camera()/documents()，不同于WEB_PERMISSION分支，没有foreground门禁；camera()/documents()只检查当前全局fileCallback是否非空，没有请求代次或发起页身份。后台或原页面失效后迟到权限结果可尝试启动选择器；新旧请求交错也可能作用到当前另一份回调。

要求：把相机/文件权限结果绑定发起页面和请求代次；仅当该请求仍有效且前台恢复后才能继续。导航失效、销毁或显式取消应恰好一次完成原回调并清理临时照片，不把旧结果发给新请求；保留正常系统相机/文件选择导致的onPause/onStop返回流程，不能简单在onPause一律取消。补授权窗口期间Home/返回/导航/新请求以及恢复后的测试，校验未后台拉起相机/文件选择器、无串回调。

## 后续运行重点

- 当前PhotoProvider将路径限制在captures及指定文件名，Manifest不导出并采用URI授权；仍需实际相机写入/返回、取消与授权撤回测试，不能用同UID直接打开Provider替代跨应用授权验证。
- onPause调用网页结束探索并暂停标签媒体是既定方向；WebView.onPause本身不暂停JavaScript，需验证真实网页尚未返回的识别/语音不会后台恢复。[Android WebView官方参考](https://developer.android.com/reference/android/webkit/WebView)。现有测试只确认合成按钮被点击，不代表实际媒体链路通过。
- 系统返回需覆盖指南、图形/树整理对话框、软键盘及文件选择器；不能仅因canGoBack就跳离未关闭对话框。
- 继续按ANDROID-001检查同账号/退出/家长next、拍摄/相册/PDF、长图双指/单指框选、知识树持久化、离线恢复与Activity重建。模拟器/本机夹具/真实网站/物理设备各自分列。

## 修复冻结包独立复验

最终受测APK SHA256：`65ae7d2f5db218b82b28aa5421bdea406050a14dbe4d5db748c34f0c4024f25a`。重新拉取设备已安装APK，确认与交付包相同；12项源码、8项QA清单均匹配。证据位于`docs/evidence/astra-android/recheck/`。

A-R03根因修正：原生外链确认框跨页面导航遗留；网页截图看不到它，系统Back先正确关闭原生框。已查看执行方原生截图确认该层确实存在。修复仅维护唯一外链确认框并在导航/销毁清理，不改变键盘优先的返回语义。独立按同一APK连续运行边界10项→学习11项通过，边界退出原生确认框不存在；真实知识讲解窗口由系统Back关闭，知识卡触摸拖动写入业务服务并在刷新后恢复。A-R03关闭。

媒体独立复验：网页视频轨道已ended后立即读取CameraService仍能看到短暂客户端，单次即时为空断言失败。随后采用5秒有界轮询，记录318ms时仍有客户端、545ms时为空；6项通过，包括后台不因迟到观察触发语音、恢复不自动重开相机。此证据支持异步释放，不能称为持续后台捕获。已交执行方完善QA断言；原始失败保留media-first.json，新记录media.json。模拟器麦克风仍无法启动，不宣称真人语音通过。

复验过程的独立脚本首次输出路径移植错误仅影响报告保存，修正路径后重新执行边界检查通过；未修改业务文件。原先媒体RAF超时也不能证明相机存活，已与轨道状态及原生CameraService分开记录。

最终独立原生instrumentation复跑15项通过（27.747秒）。测试APK需另行安装，未改变受测应用APK。

当前结论：A-R01/02/03在受测范围内关闭；Google官方Android Emulator本批验收通过。共享消息354转达用户要求本批通过Google Android模拟器试验，因此不以等待实体手机阻塞本批交付，仍不能把模拟器结论写成真机验收。物理手机触摸手感、真人音频和真实邮件OTP仍未验；启动首文档建立前getUrl可能为空属于执行方提出的未复现边界，未作为本轮通过证据。
