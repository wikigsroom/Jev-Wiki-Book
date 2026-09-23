# JEV 0.6.1 成品使用说明

交付版本：[v0.6.1 正式 Release](https://github.com/wikigsroom/Jev-Wiki-Book/releases/tag/v0.6.1)。运行时使用本地 NanoJev 和 OCR，不需要安装 Python、Node、CUDA，不需要 API Key。查询返回原文段落与来源位置。

## 选择程序

| 用途 | 下载 |
| --- | --- |
| Windows 桌面操作，可开启受限 Web 查询 | [桌面程序包](https://github.com/wikigsroom/Jev-Wiki-Book/releases/download/v0.6.1/JEV-0.6.1-windows-x64-app.zip) |
| Windows 服务器，独立管理与查询端 | [Windows CLI](https://github.com/wikigsroom/Jev-Wiki-Book/releases/download/v0.6.1/JEV-cli-0.6.1-windows-x64.zip) |
| Linux x86_64 服务器，独立管理与查询端 | [Linux CLI](https://github.com/wikigsroom/Jev-Wiki-Book/releases/download/v0.6.1/JEV-cli-0.6.1-linux-x64.tar.gz) |

程序包不重复包含模型。已有完整 `JEV-models` 可以直接复用；首次安装从 [v0.6.0](https://github.com/wikigsroom/Jev-Wiki-Book/releases/tag/v0.6.0) 下载 `JEV-models-0.6.0.zip.001`、`.002`、`JEV-models-0.6.0-downloads.json` 和 `Merge-JEV-Models.ps1`，依照 [合并与校验步骤](DISTRIBUTION_0_6.md) 解压出 `JEV-models`。准备完成后可以断网运行。

## Windows 桌面版

解压程序包，将 `JEV-models` 放到 `JEV-0.6.1-windows-x64-portable.exe` 同级，保留同级 `JEV-runtime`。双击 EXE 即可运行，单独 EXE 不能代替完整程序目录。

默认文档文件夹是同级 `JEV`。点击“切换目录”选择其他本机文件夹，等扫描完成后使用“找答案”。在“检索设置与运行状态”中勾选“启用 Web 查询端”，按需选择访问范围并应用；默认端口 18766。浏览器查询端只查询桌面当前已建立的文档库，不提供目录管理。

本项目已准备好 `release/JEV-Windows-Portable-0.6.1/` 完整目录，包含原始模型、独立运行时和 EXE，可直接运行，无需再次下载。

## Windows / Linux CLI

解压得到 `JEV-server` 文件夹，保留全部 `_internal`。把 `JEV-models` 放在可执行文件同级，或者指定已有模型目录。

Windows 在 `JEV-server` 目录执行：

```powershell
.\JEV-server.exe --models-dir D:\JEV-models --data-dir D:\JEV-data
```

Linux 解压并执行：

```sh
tar -xzf JEV-cli-0.6.1-linux-x64.tar.gz
./JEV-server/JEV-server --models-dir /srv/jev/models --data-dir /srv/jev/data
```

参数中的模型路径需指向实际的 `JEV-models` 内容目录，其中包含 `nanojev` 和 `ocr` 子目录。省略参数时，模型使用程序同级 `JEV-models`，数据使用程序同级 `server_data`。

1. 在服务器本机打开管理端 `http://127.0.0.1:18765`。
2. 全新数据目录使用 `admin` / `Jev-Change-Me-2026!` 登录，首次必须改为至少 12 个字符的新密码。
3. 输入服务器上的文档目录，扫描完成后勾选允许访问的文档，点击“保存访问范围”。可扫描和开放多个目录。
4. 查询用户访问 `http://服务器IP:18766`，输入问题并查看命中的原文段落。新增、修改的文档需要重新扫描并确认开放。

管理端默认仅本机；远程管理和 HTTPS 配置见 [CLI 部署说明](https://github.com/wikigsroom/Jev-Wiki-Book/blob/cli/docs/CLI_DEPLOYMENT.md)。查询端使用管理员开放的共用资料范围。端口可通过 `--admin-port` / `--web-port` 改为不同的高位端口。Ctrl+C 正常停止两个服务。

## 校验与升级

发布附件包含 SHA256 清单和运行验证报告。两个 CLI 包已验证全部文件、Windows PE / Linux ELF 格式和 Linux 执行权限；原生 CPU 查询、OCR、管理/查询页面、改密、授权撤回和即时重启均通过。Electron 另通过真实设置点击、目录切换、共享持久化与本机 portable EXE 启停验证。

升级时正常关闭旧程序，备份并保留模型、文档以及 `JEV-data` / `server_data`，使用对应版本的程序和运行时。已有密码与索引继续使用。Windows EXE 未签名；Linux 构建基线为 Ubuntu 22.04 x86_64；建议 16 GB 内存和 SSD。当前没有生成式总结、部门权限或 SSO；语义召回与高并发容量的边界见 [完整复查报告](REQUIREMENTS_REVIEW_0_6_1.md)。
