# 0.6.0 程序与共用模型交付

从 [v0.6.0 Release](https://github.com/wikigsroom/Jev-Wiki-Book/releases/tag/v0.6.0) 下载。运行时全部在本机执行，不要求安装 Python、Node、CUDA，不使用云端推理或 API Key。

| 用途 | 程序包 | 入口 |
| --- | --- | --- |
| Windows 桌面端 | JEV-0.6.0-windows-x64-app.zip | JEV-0.6.0-windows-x64-portable.exe |
| Windows CLI 服务 | JEV-cli-0.6.0-windows-x64.zip | JEV-server.exe |
| Linux CLI 服务 | JEV-cli-0.6.0-linux-x64.tar.gz | JEV-server |

三个程序使用同一套原始 `JEV-models`。已有 0.5.0 完整模型可以直接复用。程序包含各自独立运行环境，必须保留桌面端的 `JEV-runtime` 或 CLI 的 `_internal`，不能仅复制单个入口文件。

## 首次取得模型

下载 `JEV-models-0.6.0.zip.001`、`.002`、`JEV-models-0.6.0-downloads.json`。权重较大，因此按字节分卷；不改变模型精度。`SHA256SUMS-0.6.0.txt` 可校验所有下载附件。

Windows 可下载并运行 `Merge-JEV-Models.ps1`，自动校验各卷与合并 ZIP。如果本机策略不允许运行脚本，可使用系统自带命令合并，不需要更改执行策略：

```powershell
cmd /c copy /b "JEV-models-0.6.0.zip.001"+"JEV-models-0.6.0.zip.002" "JEV-models-0.6.0.zip"
(Get-FileHash .\JEV-models-0.6.0.zip -Algorithm SHA256).Hash.ToLowerInvariant()
(Get-Content .\JEV-models-0.6.0-downloads.json -Raw | ConvertFrom-Json).sha256
```

最后两行的 SHA256 必须相同，再解压 ZIP。Linux 使用：

```sh
cat JEV-models-0.6.0.zip.001 JEV-models-0.6.0.zip.002 > JEV-models-0.6.0.zip
sha256sum -c JEV-models-0.6.0.zip.sha256
unzip JEV-models-0.6.0.zip
```

将解压得到的 `JEV-models` 放在所选程序入口同级。CLI 也支持 `--models-dir /已有模型路径`，多个程序可以读取同一目录。文档、账号、索引和查询数据不在模型包中。

## 启动与升级

桌面版运行 EXE，在设置中启用“浏览器查询端”，默认端口 18766；默认只允许本机，可切换为局域网。查询端不能查看或更改目录。升级时保留原有 `JEV`、`JEV-data` 和模型，替换新版 EXE 与完整 `JEV-runtime`。

CLI 运行入口后同时启动管理端 18765 和查询端 18766。管理端默认仅本机，初始账号 `admin` / `Jev-Change-Me-2026!`，首次登录必须改密。管理员扫描文件夹、选择文档并保存范围；Web 用户仅提问和查看返回段落。CLI 升级保留 `server_data` 和模型，替换整个程序目录。企业网络部署、TLS 和访问边界见 [CLI 部署说明](https://github.com/wikigsroom/Jev-Wiki-Book/blob/cli/docs/CLI_DEPLOYMENT.md)。

Linux 使用 `tar -xzf` 解包，归档保留可执行权限。构建基线为 Ubuntu 22.04 x86_64；更旧 glibc 和 ARM 未验证。Windows CLI 在原生 Windows 构建与测试。建议 16 GB 内存，首次 CPU 查询需要等待加载模型。

应用保持原有 BM25 与社区 NanoJev 判断流程，只返回原文，不生成总结。本版是一位管理员维护一份共享文档范围；查询端无个人账号，按企业内网或认证网关限定访问。
