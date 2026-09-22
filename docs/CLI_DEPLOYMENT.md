# JEV CLI 部署

此分支使用原生 Python 服务程序，不启动 Electron，不依赖 Node、Docker 或 WSL。发行二进制以完整目录交付，模型目录另置于程序旁边；离线运行不访问模型服务。Windows 和 Linux 必须分别在原生系统构建。

## 默认入口

- 管理端：http://127.0.0.1:18765，默认仅本机可访问。
- 查询端：http://服务器IP:18766，默认绑定局域网网卡。
- 初始用户名：`admin`，初始密码：`Jev-Change-Me-2026!`。
- 首次登录必须改密，至少 12 个字符。改密前无法扫描或开放资料，查询端不返回文档。

初始密码只用于首次初始化，不会在每次启动时重置。凭据以带随机盐的 PBKDF2-SHA256 保存；会话 8 小时过期，改密撤销所有旧会话。错误登录有频率限制。管理写请求需要会话与 CSRF 校验。

## 启动与使用

Windows 执行 `JEV-server.exe`；Linux 先为入口添加执行权限 `chmod +x JEV-server`，再执行 `./JEV-server`。完整保留 `_internal`，同级放置已有完整便携包的 `JEV-models`（NanoJev 原始 FP32 权重和 OCR）。也可用 `--models-dir` 指定现有模型目录，不需复制。

```text
JEV-server/
  JEV-server.exe 或 JEV-server
  _internal/
  JEV-models/
  server_data/   首次启动生成，包含凭据、索引、访问范围和审计日志
```

```powershell
.\JEV-server.exe --models-dir D:\JEV-models --data-dir D:\JEV-data
```

```sh
./JEV-server --models-dir /srv/jev/models --data-dir /srv/jev/data
```

登录并改密后，输入服务器上的文档文件夹路径扫描；可依次扫描多个目录。右侧勾选允许访问的目录下的文档，保存访问范围。勾选“此目录全部”仅包含当前索引中的文档；以后新增或更新的文件需要重新扫描并确认开放。

查询端只支持查询和查看返回原文，没有目录树、文档清单、全文件下载或管理 API。指定 library_id、路径或未知参数不会获得其他资料。撤回开放范围后，新查询立即受限；已读内容无法远程收回。

## 网络与运行管理

可用 `--admin-port`、`--web-port` 设置 1024–65535 的不同端口，端口占用时启动失败并关闭已启动监听器。`--web-host 127.0.0.1` 将查询端限于本机。每个数据目录只允许一个服务实例，Ctrl+C/SIGTERM 停止两个监听器。

查询端没有用户登录体系，因此应通过企业内网、防火墙、VPN 或认证网关控制访问人群。程序不改动主机防火墙。管理端保持 loopback 时，可以由 HTTPS 反向代理转发；使用 `--admin-origin https://admin.example.com` 指定受信任来源，代理需保留 Host，并添加 HTTPS。查询端对应 `--web-origin`。

直接让管理端监听其他设备时必须同时指定 `--admin-host 0.0.0.0 --tls-cert certificate.pem --tls-key private-key.pem`，查询端也使用该证书。TLS 私钥不进入 Git 或交付包。程序不会自动申请证书。

建议 Windows x64 或 Linux x86_64、16 GB 内存与 SSD。当前强制 CPU FP32；不要求 GPU/CUDA。Linux 二进制在 Ubuntu 22.04 构建，较老 glibc 系统不在兼容承诺内。`--check` 可检查内置依赖及本地权重是否齐备。

备份整个 server_data，尤其 admin.json、publication.json 和 storage。索引是不可变快照，包含被索引资料的副本；用操作系统权限保护数据目录和备份。应用日志不记录密码和查询正文。此版本提供单管理员和一份共享访问范围，不包含 SSO、部门分权或高可用集群。

## 构建

在 Windows x64 和 Linux x86_64 各自使用 Python 3.13 安装 CPU PyTorch、requirements-dev.txt 与 packaging/requirements-build.txt，然后执行 `python packaging/build_server.py`。GitHub Actions 的 Native CLI binaries 工作流在两个原生 runner 构建，并用真实本地模型验证改密、文档开放、查询和撤回访问。CI 产物不重复携带约 2.4 GB 的模型；模型需要使用指定的原始 NanoJev 和 OCR 文件。
