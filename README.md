# JevDocumentAdminQueryServer · 企业文档管理与查询服务器

`cli` 分支提供 Windows x64 / Linux x86_64 原生服务程序 `JevDocumentAdminQueryServer`，名称采用大驼峰并明确文档管理与查询职能。启动后同时提供管理端和查询端，运行时无需 Electron、Node、GPU、CUDA、Docker 或 WSL。文档解析、OCR 与 NanoJev 推理全部在服务器本机完成，查询只返回原文段落。

## 启动

从 [v0.6.2 Release](https://github.com/wikigsroom/Jev-Wiki-Book/releases/tag/v0.6.2) 下载 `JevDocumentAdminQueryServerWindowsX64-0.6.2.zip` 或 `JevDocumentAdminQueryServerLinuxX64-0.6.2.tar.gz`，解压后进入 `JevDocumentAdminQueryServer` 目录并保留 `_internal`。将已有 JEV 离线包的 `JEV-models` 放在程序同级，或通过 `--models-dir` 指定已有模型路径。首次部署另从 [v0.6.0 模型附件](https://github.com/wikigsroom/Jev-Wiki-Book/releases/tag/v0.6.0) 下载共用模型分卷，按 [安装说明](https://github.com/wikigsroom/Jev-Wiki-Book/blob/main/docs/DISTRIBUTION_0_6.md) 合并；0.6.2 不重复分发模型。运行 `JevDocumentAdminQueryServer.exe`（Windows）或 `./JevDocumentAdminQueryServer`（Linux）。`--version` 显示程序名称和版本。[程序选择及升级说明](https://github.com/wikigsroom/Jev-Wiki-Book/blob/main/docs/DISTRIBUTION_0_6_2.md)。

| 入口 | 默认地址 | 权限 |
| --- | --- | --- |
| 管理端 | http://127.0.0.1:18765 | 登录、改密、扫描目录、选择允许查询的文档 |
| 查询端 | http://服务器IP:18766 | 提问和查看原文结果，不显示目录或完整文档清单 |

初始用户名 `admin`，初始密码 `Jev-Change-Me-2026!`。首次登录必须改密，至少 12 个字符，完成前查询端不会开放资料。扫描一个或多个文件夹后，勾选文档并保存访问范围。以后新增文档不会自动开放，需再次确认。

程序默认 CPU FP32，建议 16 GB 内存和 SSD。首次查询需要加载约 2.4 GB NanoJev 权重。无答案时不生成或补写内容。当前模型是社区 `C-Tianyu/NanoJev` 的游戏决策权重，BM25 主导召回；没有经过通用文档语义检索质量认证。

## 部署与开发

[完整部署说明](docs/CLI_DEPLOYMENT.md) 包含端口、TLS、反向代理、数据备份和边界。查询端没有用户账号，企业应通过网络或认证网关限制访问人群；管理端默认只监听本机。支持的粒度是单管理员维护的一份共享文档范围。

```powershell
python -m pip install -r requirements-dev.txt -r packaging/requirements-build.txt
python download_nanojev.py
python setup_ocr.py
python server.py --models-dir models
```

Windows / Linux 在各自原生系统执行 `python packaging/build_server.py` 编译。自动构建工作流位于 `.github/workflows/cli-binaries.yml`，分别运行 Windows 2022 和 Ubuntu 22.04 runner，验证原生二进制的账号、授权与真实 CPU 查询。

```powershell
python -X utf8 -m pytest tests -q
```

源码继承了 main 分支的检索核心；`desktop/` 和旧桌面文档仅保留为历史参考，不参与 CLI 构建或运行。[第三方组件与权重来源](THIRD_PARTY_NOTICES.md)。Electron 程序 `JevDocumentSearchDesktop` 的维护分支为 [main](https://github.com/wikigsroom/Jev-Wiki-Book/tree/main)。
