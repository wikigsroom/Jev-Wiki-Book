# JEV · Jev Wiki Book

完全在本机运行的文档证据检索工具：选择文件夹，输入问题，返回相关原文段落，并在阅读器中核对来源。提供带可选 Web 查询端的 Windows Electron 便携版，以及独立的 CLI 企业内网服务。

使用社区开源 [NanoJev](https://github.com/TianyuCodings/NanoJev) / [C-Tianyu/NanoJev](https://huggingface.co/C-Tianyu/NanoJev)，**不是 TypeSafe 官方 Jev 私有权重**。运行时不需要网络、Claude、TypeSafe API 或任何 API Key；不生成摘要或改写回答。

## Windows 便携版

`JevDocumentSearchDesktop` 的设置中可以启用独立 Web 查询端（默认端口 18766），浏览器只能查询桌面端已建立的当前文档库。[Web 共享说明](docs/WEB_SHARING.md)。另有完全不使用 Electron 的 [cli 分支](https://github.com/wikigsroom/Jev-Wiki-Book/tree/cli)，提供 `JevDocumentAdminQueryServer`，同时启动文档管理端和查询端，支持 Windows / Linux。

发行下载入口：[GitHub Releases](https://github.com/wikigsroom/Jev-Wiki-Book/releases)。建议 Windows 11 x64、16 GB 内存和至少 10 GB 可用磁盘空间（包括下载、合并、解压和数据）。当前在 Windows 11 实测；EXE 未进行代码签名。

0.6.2 使用大驼峰名称区分程序职能，程序与共用模型分开分发。桌面版下载 `JevDocumentSearchDesktopWindowsX64Portable-0.6.2.zip`；首次部署还需要从 [v0.6.0 模型附件](https://github.com/wikigsroom/Jev-Wiki-Book/releases/tag/v0.6.0) 下载：

- `JEV-models-0.6.0.zip.001` 和 `.002`
- `JEV-models-0.6.0-downloads.json` 与 `Merge-JEV-Models.ps1`

合并并解压模型，将 `JEV-models` 放在 EXE 同级，然后运行 `JevDocumentSearchDesktopWindowsX64Portable-0.6.2.exe`。[程序选择、安装与升级说明](docs/DISTRIBUTION_0_6_2.md) 含 Windows 和 Linux 命令。已有完整模型可直接复用，无需再次下载；历史完整包的安装方式保留在 [0.5.0 发布文档](docs/RELEASING.md)。

```text
JevDocumentSearchDesktopWindowsX64Portable-0.6.2/
├─ JevDocumentSearchDesktopWindowsX64Portable-0.6.2.exe
├─ JEV-runtime/    独立 Python、解析器和推理依赖
├─ JEV-models/     原始 NanoJev 与 OCR 权重
├─ JEV/            默认文档目录
└─ JEV-data/       运行时自动创建的索引、设置与日志
```

保留 EXE 同级的 `JEV-runtime` 和 `JEV-models`。Release 单独提供的 EXE 适用于已有同版完整目录；它本身不包含模型和 Python 环境。便携版无需安装 Python、Node 或 CUDA。

页面“切换目录”或 `Ctrl+O` 可以选择其他本机文件夹。首次查询加载模型会较慢；关闭窗口后，本地服务一同结束。[桌面说明](desktop/README.md) · [发行验证记录](desktop/VERIFICATION.md)

## 能做什么

- 解析 PDF、DOCX、Markdown、TXT、HTML、JSON、CSV 等本机文档，使用本地 RapidOCR 识别文档图片。
- 按段落、表格行、PDF 页码与文本块检索；长段保留字符范围，支持来源高亮和原文件下载。
- 为每个目录保留独立文档库，后台扫描支持进度、取消和失败回退。
- 原文引用绑定不可变索引版本，切换目录或重新扫描后仍可核对旧来源。
- 桌面版提供原生目录选择、菜单、复制、文件保存、设置持久化和故障恢复。

处理链路：`本地文件 → 解析 / OCR → BM25 召回 → NanoJev 分批判断 → 规则筛选 → 原文与来源`。

公开 NanoJev checkpoint 训练于游戏决策，尚未证明其优于 BM25 或适用于通用文档重排。本实现保留词法排序主导；概率不代表事实正确率。同义问法、复杂排版、OCR 和跨文档冲突都需要核对原文。当前没有聊天生成、自动摘要、向量 embedding 或 Wiki 自动写作功能。

## 本机开发工作台

以下 `app.py` 入口是带目录管理的本机开发工作台。面向查询用户的入口为 Electron 启用的 18766 服务，或 cli 分支独立查询端；部署说明见上文。开发工作台只在本机使用。

以下命令使用 Windows 原生 Python 3.13 和 Node.js 22；无需 Docker、WSL 或虚拟机。首次安装依赖、下载模型需要联网，之后在本机运行。

```powershell
git clone https://github.com/wikigsroom/Jev-Wiki-Book.git JEV
cd JEV
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe download_nanojev.py
.\.venv\Scripts\python.exe setup_ocr.py
npm --prefix frontend ci
npm --prefix frontend run build
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -X utf8 app.py
```

打开 <http://127.0.0.1:8765/>。源码模式默认扫描项目根目录，也可以选择其他目录。模型位于 `models/`，索引位于 `storage/`；二者不进入 Git。模型下载脚本固定 NanoJev 修订版本并校验 SHA256。

构建桌面版见 [desktop/README.md](desktop/README.md)。运行普通回归无需模型下载：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests desktop/tests -q
npm --prefix desktop ci
npm --prefix desktop test
```

真实模型评测、OCR 和独立运行环境验证见 [evals/README.md](evals/README.md) 与 [验证记录](desktop/VERIFICATION.md)。普通单元测试通过不等于真实权重质量通过。

## 仓库导航

| 路径 | 内容 |
| --- | --- |
| `app.py`、`jev_core/` | 本地 API、文档解析、版本存储、NanoJev 与检索 |
| `frontend/`、`static/` | React 三栏阅读界面与备用静态页面 |
| `desktop/` | Electron 主进程、预加载桥接、独立后端与打包脚本 |
| `tests/`、`evals/` | 自动化回归与公开合成评测样本 |
| [docs/REFERENCE.md](docs/REFERENCE.md) | 原理、配置、格式边界与 API |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 开发、验证和仓库约定 |
| [docs/RELEASING.md](docs/RELEASING.md) | 构建、分卷、校验与 GitHub 发布 |
| [docs/research/](docs/research/README.md) | 历史 Jev 调研与架构讨论 |
| [CHANGELOG.md](CHANGELOG.md) | 版本变更 |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | 上游组件、权重来源与许可证 |

私有文档、真实业务评测题及候选原文、索引、密钥、依赖目录和编译产物均不提交。仓库目前未为新增应用代码指定统一许可证；第三方组件保留各自许可证。
