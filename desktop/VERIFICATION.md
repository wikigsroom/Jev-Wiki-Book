# JEV Windows 便携版验证记录

## 0.6.1 — 2026-09-23

本机 Windows 11 完成 38 项 Python 回归（检索核心 29、后端及发行工具 9）、3 项 Node 生命周期测试和前端构建。新增验证涵盖取消请求保留并发名额、共享停止时的锁竞争、活动端口冲突、即时重启、索引退出收尾及旧发行文件的硬链接保护。

新版完整目录内的独立 Python 和原始模型通过真实 CPU FP32 共享查询：返回“资料室文档借阅期限为十四天”的原文，首次查询 35.308 秒。共享恢复、关闭监听器、屏蔽目录与管理接口均通过。报告：desktop/build/sharing-verification-0.6.1.json。

在另建的测试便携目录实际启动 JEV-0.6.1-windows-x64-portable.exe；完成握手、默认共享关闭、正常关闭窗口和后端退出。测试数据留在 desktop/build/portable-smoke-*，发行目录保持无 JEV-data。未触碰原有 8765 服务、用户文档或索引。

Windows 2022 独立 CI 已完成 Electron 的实际表单验收：首次读取失败显示重试、启用共享、默认关闭、修改端口、查询原文、切换目录后仅返回新库内容、重启恢复共享，以及在设置中关闭共享。检索由本地 CPU 模型完成，私有后端缺少令牌时拒绝访问。截图和 JSON 见发行版 JEV-desktop-0.6.1-ui-verification.json。此项补齐 0.6.0 的按钮点击验收缺口。

CLI 的 Windows 2022 / Ubuntu 22.04 原生二进制均通过 42 项回归、真实模型、DOCX/PDF/OCR、管理员与查询表单、同端口重启、授权/密码持久化、旧会话失效、数据目录排他和缺少模型的非零退出码。构建 [35776788873](https://github.com/wikigsroom/Jev-Wiki-Book/actions/runs/35776788873)；CLI 源码 66ac07e3a9ce9d9769fad7cb1813aa496ac75972，Electron 被验收的应用源码 4266b715a2f3b0b807b2adb224e7959239798c05。后续发布文档及验证工具变更不改变该应用实现。

仅复用原始模型，不转换精度。小样本通过不代表通用文档语义质量或并发容量认证；EXE 未签名，Linux 基线为 Ubuntu 22.04 x86_64。以下旧版验证作为历史保留。

## 0.6.0 — 2026-09-23

在 Windows 11 x64 原生环境编译并启动 `JEV-0.6.0-windows-x64-portable.exe`，新目录下窗口标题为“JEV · 本地文档检索”，嵌入式 Python 成功握手，默认 Web 共享关闭。关闭窗口后后端正常退出，原有 8765 服务未受影响。

新增 Web 共享相关单元测试共 5 项通过，覆盖受限路由、在途撤回、开关和持久化、端口占用、设置无法保存时关闭新监听器。原有 Python 回归、Node 生命周期测试及前端构建均通过。

`desktop/tests/sharing_process_smoke.py` 使用完整发行目录内的独立 Python 与原始模型，在临时资料库执行真实 HTTP 测试：开启共享、阻止管理/目录接口、返回“借阅期限为十四天”的原文段落、重启恢复共享、停用共享和正常关闭监听器。首次 CPU FP32 查询实测 35.809 秒；报告见 `desktop/build/sharing-verification.json`。此测试不使用主机 Python 执行后端推理。

本轮桌面与浏览器交互工具未能连接，因此没有将 Electron 设置按钮的逐项点击验收列为已通过；设置对应的真实后端流程已验证。CLI 的管理与查询页面验收另由其原生构建工作流执行。以下 0.5.0 记录保留为历史，不代表 0.6.0 重复完成了其中每一项人工界面操作。

## 0.5.0 历史验证

验证日期：2026-09-21（Asia/Taipei）。实际运行环境：Windows 11 家庭版中文版 x64，10.0.26200。全程使用 Windows 原生环境；没有使用 Docker、WSL 或虚拟机。

## 交付形态

- Electron 44.4.3，electron-builder 26.15.3，独立 CPython 3.13.12。
- EXE：`JEV-0.5.0-windows-x64-portable.exe`，125,101,120 字节。
- EXE SHA256：`f674e8082298c0e98fb7350c2fd5aebc8db12ac30f01637acc707a1a5b7387dc`。
- 完整便携目录约 3.51 GB，含 EXE、JEV-runtime、JEV-models、默认资料、源代码和第三方许可证。必须保留整个目录。
- 本地 NanoJev checkpoint 保留原始 FP32 文件，2,385,039,280 字节；SHA256 为 `f68c47d66998231b86b7e91b4ed5e82ae23acf104c8b7cd6d165c3ac7b7ffe1b`。
- ZIP 内的 SHA256SUMS.txt 覆盖全部发行载荷；封包后由 `desktop/scripts/verify_release.py` 逐文件解压读取并校验 SHA256 与 ZIP CRC。该次校验结果保存在项目 `release/verification-result.json`，ZIP 自身校验值在同级 `.zip.sha256` 文件。

## 已完成验证

| 检查 | 结果与证据 |
| --- | --- |
| Python 回归 | 22 项通过，包括已有检索回归及桌面鉴权、目录隔离测试；仅有 Starlette/httpx 弃用提示。 |
| Electron 生命周期逻辑 | 3 项 Node 测试通过，覆盖便携根路径、同源判断和后端就绪握手。 |
| 前端构建 | Vite production build 成功。最终 ASAR 的 main/preload/lifecycle 与源码逐字节一致。 |
| 独立 Python | 用包内 python.exe 的 `-I` 隔离模式执行真实测试；刻意设置的主机 PYTHONPATH 不被读取，导入来自包内依赖。 |
| 本地模型推理 | 原始 NanoJev 在 CPU FP32 模式完成真实检索，未调用云服务；运行时测试报告包含 loaded=true、local_only=true。 |
| 文档与 OCR | Markdown、DOCX、PDF 三种夹具完成解析；本地 OCR 从测试图片识别出 JEVOFFLINETEST2026。 |
| 后端进程 | 真实嵌入式 Python 启动握手、随机 loopback 端口、正常退出均通过；无令牌、错误令牌、外部 Origin 被拒绝。 |
| 网络限制 | Python 外部连接测试被阻止；模型强制本地文件加载，页面只允许应用自身来源。未修改操作系统网络或防火墙。 |
| 最终 portable EXE | 实际双击等价启动了发行目录的 EXE；Electron 从临时目录运行，Python 从发行目录 JEV-runtime 运行。 |
| 启动时间 | 02:25:05.780 启动 EXE，02:25:12.035 本地服务就绪，约 6.3 秒。这是当前机器一次实测，不是跨机器性能承诺。 |
| 原生目录选择 | 菜单 Ctrl+O 打开 Windows 文件夹选择器，选择测试资料目录、确认扫描后成功切换；重启保留选择。随后恢复默认 JEV 目录。 |
| 设置持久化 | 候选数量从 12 改成 4，关闭并重启后界面仍为 4；最终恢复 12。 |
| 最终 EXE 真实问题 | 提问“资料室文档借阅期限是多久？”，返回“资料室文档借阅期限为十四天。每位读者最多同时借阅三份文档。”，仅 1 个段落；定位开始使用.md 第 10 段、行 19，阅读器高亮一致。首次模型加载在内的查询耗时 25.246 秒。 |
| 重复启动 | 同一数据目录重复启动聚焦已有窗口，没有创建第二个检索服务。 |
| 故障恢复 | 验证身份后只终止该桌面程序自己的 Python 子进程；窗口显示恢复页，点击“重新启动”后服务在新的本地端口恢复，资料索引保留。 |
| 正常退出 | Ctrl+Q 后 Python exit code=0；Electron、Python 和便携启动器均退出，临时会话标记删除。 |
| 与网页版并存 | 原有 8765 网页服务保持独立，桌面端使用随机端口及独立数据目录。 |

运行时测试原始 JSON 位于项目 `desktop/build/smoke/runtime-smoke-result.json` 与 `desktop/build/process-smoke/result.json`。桌面验收的临时索引和日志归档在 `desktop/build/verified-portable-data`，不会进入离线 ZIP。交付默认资料只有项目自带入门文档。

## 明确边界

当前已在上述 Windows 11 机器验证；未在另一台无开发环境的干净电脑或 Windows 10 上实际运行，也没有进行全量长文档性能测试。隔离运行时测试验证了主机 Python 不参与加载，但不等同于跨设备认证。

该 EXE 没有代码签名证书。首次加载约 2.4 GB 模型需要时间和内存，建议至少 16 GB 内存。CPU 速度、文档规模和磁盘会影响体验。

使用的是社区开源 NanoJev，不是 Typesafe 官方 Jev 私有权重。公开 checkpoint 以游戏决策为训练目标；这些测试证明程序链路可运行，不证明通用文档召回准确率。系统返回原文证据，不生成摘要或改写回答。
