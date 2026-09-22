# 0.6.1 安装与升级

下载入口：[v0.6.1](https://github.com/wikigsroom/Jev-Wiki-Book/releases/tag/v0.6.1)。这是程序修订版，继续使用 v0.6.0 的同一套原始 NanoJev FP32 与 OCR 模型。

| 程序 | 下载文件 |
| --- | --- |
| Windows Electron 便携版 | JEV-0.6.1-windows-x64-app.zip |
| Windows CLI 管理端 + 查询端 | JEV-cli-0.6.1-windows-x64.zip |
| Linux x86_64 CLI 管理端 + 查询端 | JEV-cli-0.6.1-linux-x64.tar.gz |

第一次安装需要另外下载 [v0.6.0 模型分卷与合并工具](https://github.com/wikigsroom/Jev-Wiki-Book/releases/tag/v0.6.0)。模型文件名仍为 JEV-models-0.6.0.zip.001 / .002、JEV-models-0.6.0-downloads.json、Merge-JEV-Models.ps1，合并方法见 [原模型安装说明](DISTRIBUTION_0_6.md)。解压后 JEV-models 放在程序同级；CLI 也可以用 --models-dir 指向现有目录。

Windows 桌面版解压后运行 JEV-0.6.1-windows-x64-portable.exe。必须保留同版 JEV-runtime，单独下载 EXE 不能代替完整程序包。CLI 解压后运行 JEV-server.exe 或 ./JEV-server，保留整个 _internal。运行时无需 Python、Node、CUDA 或网络。

升级前正常关闭旧程序，备份 JEV-data / server_data。替换程序及对应版本运行时，保留模型、默认 JEV 文档目录、自选文档目录和数据目录；不覆盖用户内容。0.6.1 不要求重建已有索引或重新改回默认密码。首次升级后管理员需要重新登录。

CLI 默认管理 127.0.0.1:18765，查询 0.0.0.0:18766；admin / Jev-Change-Me-2026! 仅用于全新数据目录初始化，首次必须改密。Electron 共享默认关闭，设置中启用后默认使用 18766。

Release 附程序 SHA256、原生二进制验证与 Electron 表单测试报告。校验程序包：Windows 使用 Get-FileHash -Algorithm SHA256 文件名；Linux 使用 sha256sum -c 文件名.sha256。源码与修复范围见 [需求复查](REQUIREMENTS_REVIEW_0_6_1.md)。
