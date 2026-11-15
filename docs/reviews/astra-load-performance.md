# 学习桌加载性能独立验收

2026-11-15，Astra。需求 NFR-006；结论：冻结包定向验收通过，可以发布本轮七文件性能修复。

## 冻结范围

对 `docs/evidence/load-performance/stage.json` 指向的独立 stage 复核，373 文件 SHA 全部匹配发布清单；相对 home-copy 冻结基线只有声明的七文件变化：server.py、home.html、pricing.html、fonts.css、两种 UI 字体、字体 manifest。发布 manifest SHA256：`b5d34b28c50c9b7fb1199b1acabab74d671b4ef75941381ce2107eb0ef02e312`。

## 独立验证

- 使用冻结 app 而非工作区模块，重新运行静态交付 5 项测试，全部通过。覆盖 gzip/identity 表示与 ETag 区分、q=0、304 无错误 Content-Length、内容更新失效、字体不重复压缩、HTML/API no-store、私有资产 private，以及未登录/退出后不能利用 ETag 绕过鉴权。源代码差异检查确认路由鉴权顺序未改变。
- 自行启动冻结模块，使用临时合成账号和独立数据库；Chromium 与 WebKit 各 8 项手机尺寸检查通过：指南三步及关闭、390px 无水平溢出、UI 字体正常加载、没有 Regular-e/4 大分块请求、刷新传输量低于首次、没有 JavaScript 错误。截图实看学习桌正常显示。未调用真实模型或读取真实用户资料。
- 独立 fontTools 对比新旧字体：Regular 与 Medium 各原有 877 字符的绘制轮廓及水平度量完全相同，垂直行高指标相同；仅增加“界①②③”四字符。
- 浏览器脚本首次 Chromium 过早检查指南可见性失败；改为等待可见状态后两引擎完整通过。这是检查时机问题，未修改产品代码。

## 性能数据和限制

执行方最终新进程 Slow4G/4xCPU 样本为首次资源完成 7.07s、857337B，重复 4.05s、12543B；此前 6.75s 是旧头部分类进程，不作为最终冻结测量。原始旧版首次为 17.54s、约2.60MB。本轮独立验证确认资源复用、字体请求和功能表现，未独立重复该限速时序实验；上述具体时间归属执行方证据。localhost HTTP/1 与线上 HTTPS/HTTP2 不同，单轮数据不是生产 SLA。

本次只放行已冻结的性能变化；没有重新宣称物理手机触感、完整学习链或线上加载时间通过。发布后应核对公网 gzip/Vary/ETag、HTML/API no-store、运行源 SHA 和健康状态；真实登录学习桌的体验由发布后实测补充。

独立证据：[目录](../evidence/astra-load-performance/)，包括 freeze.json、protocol-tests.txt、fonts.json、chromium.json、webkit.json、手机截图及可复跑脚本。
