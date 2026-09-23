# JevDocumentSearchDesktop · Windows 文档检索桌面程序

Electron 桌面窗口 + 独立 CPython 3.13 运行环境 + 原始 NanoJev checkpoint + 本地 RapidOCR。运行时不需要 Python、Node、API Key、管理员权限或网络。当前目标是 Windows 10/11 x64，CPU FP32 推理。

## 使用便携版

完整解压 `JevDocumentSearchDesktopWindowsX64Portable-0.6.2.zip`，放入已有的 `JEV-models`，双击其中的 `JevDocumentSearchDesktopWindowsX64Portable-0.6.2.exe`。不要在压缩包内直接运行，也不要只复制 EXE。[首次安装和模型下载](../docs/DISTRIBUTION_0_6_2.md)。历史版本按对应版本的发布说明使用。

```text
JevDocumentSearchDesktopWindowsX64Portable-0.6.2/
  JevDocumentSearchDesktopWindowsX64Portable-0.6.2.exe
  JEV-models/       原始 NanoJev 与 OCR 权重，必须与 EXE 一起保留
  JEV-runtime/     完整独立 Python 与推理环境，必须与 EXE 一起保留
  JEV/             默认文档目录，附带入门示例
  JEV-data/        首次启动自动创建：索引、设置、日志、窗口与页面缓存
  SOURCE/         当前应用源代码及构建脚本
  THIRD-PARTY/    依赖清单、授权文件和上游来源
  SHA256SUMS.txt
```

启动时仅将 Electron 桌面外壳展开到 Windows 临时目录，Python 直接使用同级 JEV-runtime，不重复展开大型推理依赖。首次检索会加载约 2.4 GB 的原始 NanoJev 权重，因此会比后续检索慢。建议至少 16 GB 内存，并留出至少 10 GB 可用磁盘空间（包含分卷、合并 ZIP、解压目录与启动临时文件，文档库另计）。

默认扫描 EXE 同级的 `JEV` 文件夹。使用页面“切换目录”或菜单“文件 → 选择文档目录”选择其他目录。该选择和检索参数会保存，下一次启动继续使用。文档库与网页版独立，不会把本机已有私人文档打进交付包。

设置中的“浏览器查询端”默认关闭，启用后默认使用 18766 端口。可选择仅本机或局域网访问；Web 访问者只能查找当前已扫描资料的原文段落，不能查看或修改文档目录。设置会保存，关闭桌面程序时附属 Web 服务同步关闭。详见 [Web 查询说明](../docs/WEB_SHARING.md)。

窗口关闭即退出：Electron 请求后端结束，超时只终止它自己启动的 Python 进程。父进程意外消失时，Python 监视器也会结束后端，避免模型留在内存。重复启动会聚焦同一便携目录的已有窗口。

更新前退出旧程序并备份 `JEV-data`，替换 EXE 和版本对应的整个 `JEV-runtime`，保留 `JEV-models`、`JEV` 和 `JEV-data`。旧 EXE 应移到备份目录，避免误启旧版本。0.6.2 的大驼峰程序名不改变数据目录或设置格式；内部桌面进程名为 `JevDocumentSearchDesktop.exe`。换电脑时复制整个目录。此前文档目录的绝对路径如果在新位置不存在，需要重新选择默认 JEV 文件夹或外部目录；旧索引和历史证据不会自动删除。

当前交付未使用代码签名证书。Windows 在下载到其他电脑后可能显示未知发布者提示；可用 SHA256SUMS.txt 校验文件。该包没有安装、自动更新或联网激活步骤。

## 工作原理与边界

- Electron 复用现有原文检索界面，提供原生目录选择、文件保存、菜单、剪贴板与窗口管理。
- Python 使用嵌入式 `_pth` 路径隔离，不读取主机的 Python 安装、用户 site-packages 或 PYTHONPATH。
- 服务直接绑定 `127.0.0.1:0`，由操作系统分配端口；既不占用也不接管网页版的 8765 端口。
- 每次启动生成随机鉴权令牌，由 Electron 主进程附加到同源请求，令牌不进入网页、URL、磁盘配置或日志。未知 Origin 和缺少令牌的请求被拒绝。
- 页面开启 sandbox、contextIsolation，关闭 Node 集成；IPC 仅向主窗口公开有限操作。导航、弹窗、权限与网络请求按应用来源限制。
- Python 禁止外部 socket 连接与 DNS，模型加载强制 local_files_only；无云端推理和自动模型下载。不会修改 Windows 防火墙或系统网络设置。
- 原始权重保持 FP32 文件不变，没有为缩小包体转换精度。公开 NanoJev 的训练任务仍是游戏决策，不是经过验证的通用文档重排模型。检索返回原文，并不生成摘要。

## 在本项目构建

全程使用 Windows 原生工具。从项目根目录开始，按项目 README 安装 requirements-dev.txt、下载 NanoJev 和 OCR 权重。发行时的完整 Python 依赖版本见 requirements-runtime.lock.txt；可在独立 Python 3.13 环境安装该清单复现版本。

```powershell
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix desktop ci
python -X utf8 desktop\scripts\generate_assets.py
python -X utf8 desktop\scripts\prepare_runtime.py
npm --prefix desktop test
python -X utf8 -m pytest tests desktop\tests -q
npm --prefix desktop run build
python -X utf8 desktop\scripts\release_portable.py
python -X utf8 desktop\scripts\verify_release.py
```

`prepare_runtime.py --plan` 显示实际依赖版本与体积；正式执行从当前已测试环境按发行包 RECORD 文件清单复制依赖，并下载 Python 官方签名的嵌入式运行环境。依赖清单固定在 `build/requirements-runtime.lock.txt`，完整元数据在 `build/backend/runtime-manifest.json`。Electron 与 electron-builder 固定版本并有 npm lockfile。

桌面开发用 `npm --prefix desktop start`，也使用嵌入式运行环境。开发数据位于 `desktop/build/dev-portable/JEV-data`，不会读写现有网页库。修改后端或前端后需重新运行 prepare-runtime 更新暂存代码。

如果 GitHub 构建工具下载超时，可只为当前构建进程设置 `ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/` 后重试。electron-builder 仍按其内置上游校验值验证工具，不关闭 HTTPS 或校验。此设置与交付程序的离线运行无关。

## 测试与排错

本次发行的实际验收结果见 [VERIFICATION.md](VERIFICATION.md)；便携包内对应文件为 `验证记录.md`。

`desktop/tests/runtime_smoke.py` 必须由打包的 python.exe 运行：验证导入位置、离线路径、真实 NanoJev 检索、Word/PDF 解析与 OCR。普通 pytest 验证私有服务鉴权与目录隔离；Node 测试验证便携路径、同源校验和后端握手。

启动错误页支持重试、打开日志、退出。运行日志在 `JEV-data/logs/desktop.log`。模型缺失时只显示错误，不会转用云服务或静默下载。

上游参考：[Electron 安全指南](https://www.electronjs.org/docs/latest/tutorial/security)、[portable 构建选项](https://www.electron.build/docs/api/app-builder-lib.interface.portableoptions/)、[Python Windows 嵌入式运行环境](https://docs.python.org/3/using/windows.html#windows-embeddable)。第三方组件保留各自许可证，详见交付包 THIRD-PARTY；其中包括 PyMuPDF/MuPDF 的 AGPL 授权材料。
