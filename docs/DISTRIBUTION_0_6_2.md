# 0.6.2 程序选择、安装与升级

[下载 v0.6.2](https://github.com/wikigsroom/Jev-Wiki-Book/releases/tag/v0.6.2)。名称采用大驼峰（PascalCase），版本号用连字符分隔。

| 下载文件 | 职能 | 运行入口 |
| --- | --- | --- |
| `JevDocumentSearchDesktopWindowsX64Portable-0.6.2.zip` | Windows 桌面窗口：选择文档目录、扫描、检索和来源阅读；可在设置启用受限 Web 查询 | 包内同名 `.exe` |
| `JevDocumentAdminQueryServerWindowsX64-0.6.2.zip` | Windows 原生服务器：同时启动文档管理端和受限查询端，无 Electron | `JevDocumentAdminQueryServer/JevDocumentAdminQueryServer.exe` |
| `JevDocumentAdminQueryServerLinuxX64-0.6.2.tar.gz` | Linux x86_64 原生服务器：同上 | `JevDocumentAdminQueryServer/JevDocumentAdminQueryServer` |

服务器的 Admin 和 Query 是同一程序内两个监听器，无需启动两个 EXE。默认管理端为 `http://127.0.0.1:18765`，查询端为 `http://服务器IP:18766`。初始用户名 `admin`，密码 `Jev-Change-Me-2026!`，首次登录必须改密。管理端扫描目录并保存允许查询的文档范围后，查询端才有可查资料。服务器运行与安全边界见 [cli 部署说明](https://github.com/wikigsroom/Jev-Wiki-Book/blob/cli/docs/CLI_DEPLOYMENT.md)。

## 共用本地模型

三个程序包都含各自独立运行环境，模型单独分发。首次安装从 [v0.6.0](https://github.com/wikigsroom/Jev-Wiki-Book/releases/tag/v0.6.0) 下载 `JEV-models-0.6.0.zip.001`、`.002`、`JEV-models-0.6.0-downloads.json` 和 `Merge-JEV-Models.ps1`。按 [模型合并说明](DISTRIBUTION_0_6.md) 校验、合并和解压，将 `JEV-models` 放在实际程序旁边。已有模型可直接复用，原始 NanoJev 权重 SHA256 为 `f68c47d66998231b86b7e91b4ed5e82ae23acf104c8b7cd6d165c3ac7b7ffe1b`。

桌面版完整保留 `JEV-runtime`；服务器版完整保留 `_internal`。单独的桌面 EXE 附件仅适合已有同版 `JEV-runtime` 与模型的目录，首次安装应下载 ZIP。运行时无需 Python、Node、GPU、API Key 或网络；所有检索使用本地 NanoJev 和 OCR，返回文档原文段落。

## 启动与校验

Windows 桌面版解压 ZIP、放好模型后双击 `JevDocumentSearchDesktopWindowsX64Portable-0.6.2.exe`。后台进程名为 `JevDocumentSearchDesktop.exe`。默认文档目录为同级 `JEV`；可以在窗口中选择其他目录。Web 共享默认关闭，可在设置开启，默认 18766 端口。

Windows 服务版在解压后的 `JevDocumentAdminQueryServer` 目录运行：

```powershell
.\JevDocumentAdminQueryServer.exe --version
.\JevDocumentAdminQueryServer.exe --models-dir D:\JEV-models --check
.\JevDocumentAdminQueryServer.exe --models-dir D:\JEV-models --data-dir D:\JEV-data
```

Linux 服务版：

```sh
tar -xzf JevDocumentAdminQueryServerLinuxX64-0.6.2.tar.gz
cd JevDocumentAdminQueryServer
./JevDocumentAdminQueryServer --version
./JevDocumentAdminQueryServer --models-dir /srv/jev/models --check
./JevDocumentAdminQueryServer --models-dir /srv/jev/models --data-dir /srv/jev/data
```

Linux 归档保留执行权限，构建基线 Ubuntu 22.04 x86_64；更旧 glibc 不在兼容承诺内。Windows EXE 未签名。建议 16 GB 内存和 SSD，首次 CPU 推理需要加载模型。

下载包旁的 `.sha256`、`SHA256SUMS-0.6.2.txt` 和 `JevWikiBookDownloads-0.6.2.json` 提供文件校验值。Windows 使用 `Get-FileHash 文件名 -Algorithm SHA256`；Linux 使用 `sha256sum -c 文件名.tar.gz.sha256`。解压后 `SHA256SUMS.txt` 校验包内载荷；桌面清单也包含另行放入的模型。

## 从 0.6.1 升级

先退出旧程序并备份数据，保持用户资料原路径。桌面版保留 `JEV-models`、`JEV`、`JEV-data`，用新包的整个 `JEV-runtime` 和新 EXE 替换程序部分。服务版保留 `JEV-models` 和 `server_data`（或原 `--data-dir` 指向的数据），替换程序和整个 `_internal`；服务、计划任务或快捷方式改为新程序名。旧 EXE 移到备份目录，避免误启。

程序名称变化不重置账号、开放范围、索引或共享设置。原数据目录名称继续保留，历史 Release 与模型附件不改名。若移动安装目录，外部文档路径仍需存在；必要时在管理界面重新选择或扫描。
