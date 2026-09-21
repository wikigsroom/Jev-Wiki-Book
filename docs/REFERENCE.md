# JEV 实现与 API 参考

在本机文件夹里找相关段落，直接阅读原文、表格和图片的 OCR 转写。源码模式默认扫描项目根目录；桌面便携版默认扫描 EXE 同级的 JEV 文件夹。页面支持输入路径或打开系统目录选择器，已有目录选择会保留。快速开始见[项目 README](../README.md)。

本项目运行社区开源的 [NanoJev](https://github.com/TianyuCodings/NanoJev) / [C-Tianyu/NanoJev](https://huggingface.co/C-Tianyu/NanoJev)。它是 Jev 类决策模型的社区复刻，**不是 TypeSafe 官方 Jev 的本地权重**。不需要 TYPESAFE_API_KEY 或 ANTHROPIC_API_KEY，不调用 Claude，不生成回答，不生成 embedding。

## 工作方式

原始文件 → 本地解析与 OCR → 真实来源单元 → BM25 召回 → 本地 NanoJev 分批判断 → 支持度筛选与排序 → 原文及来源阅读器。

- NanoJev 直接给候选项和 none 评分，不逐字生成文本。每批默认 4 个段落加一个 none；请求的所有候选都处理，最多 30 个。
- 公开 checkpoint 的训练任务是游戏决策，没有经过本项目文档相关性训练。实测直接依赖它重排会降低首条结果命中率，因此保留词法排序主导、NanoJev 辅助的设计。
- 中文使用连续字串的双字词召回，查询先去掉疑问句虚词。仅保留关键词覆盖达到绝对阈值及最佳候选相对阈值、且 NanoJev 得分超过 none 的内容。规则可能漏检同义改写，也可能误判；none 不是可靠性保证。
- 不把候选概率显示成答案正确率；不同批次的 softmax 概率不直接比较。
- 返回最多 3 个来源单元，可在页面设置为 1–6 个。相同原文和同一长段落的重复切片去重。evidence 与 citations 始终对应。

评测方法见 [evals/README.md](../evals/README.md)。当前小样本不能证明 NanoJev 优于 BM25，也不能证明可泛化到任意文档。

## 安装与运行

Windows 桌面版使用 Electron，包含原生目录选择、独立本地服务和便携数据目录。构建与使用说明见 [desktop/README.md](../desktop/README.md)。完整离线交付采用 portable EXE 与同目录 JEV-models、JEV-runtime 文件夹，无需安装 Python、Node 或配置 API Key。

使用 Windows 原生 Python 和 Node，不需要 Docker、WSL 或虚拟机。

~~~powershell
cd JEV
python -m pip install -r requirements.txt
python download_nanojev.py
python setup_ocr.py
Copy-Item .env.example .env
python -X utf8 app.py
~~~

只有首次安装依赖、下载权重需要联网。NanoJev 从 models/nanojev 读取本地配置、分词器和权重，使用 local_files_only；下载固定到公开提交 047b927b30882a1138fc504821b82ac145a4b81a，并校验权重 SHA-256。图片识别显式指定 models/ocr 的 3 份 ONNX 权重，缺失时报告未能识别，不自动改用云服务。OCR 下载脚本也会校验每份权重的 SHA-256。

代码兼容旧版项目内 .runtime/ocr 依赖位置。新安装按 requirements.txt 安装即可，无需依赖下载模型仓库里的 Python 脚本或手工补丁。

打开 <http://127.0.0.1:8765/>。服务只监听本机，拒绝其他 Host 和站外 Origin。前端无外部字体、CDN 或云端 API。离线验证通过禁止 Python socket 连接检查索引与推理；这不等于设置了操作系统防火墙。

React 构建：

~~~powershell
cd frontend
npm ci
npm run build
~~~

FastAPI 提供 frontend/dist；没有构建产物时提供 static 下可独立使用的基础界面。修改构建产物后刷新浏览器；修改 Python 后重启服务。请不要同时启动多个写入同一 storage 的服务进程。

## 目录、任务与版本

“浏览本机”只选择路径；取消不会扫描或改变当前库。“扫描并使用此目录”启动后台任务，完成后一次性切换。任务显示进度并支持取消；解析失败、路径无效或取消时旧库继续可用。

每个目录有独立的文档库，上传文档也归属于该目录。切回目录会保留其上传文件，不会混入另一个目录。扫描会在进入目录前排除项目的模型、运行环境、索引、前端构建和依赖文件夹；不跟随符号链接。

索引使用 SQLite 事务和不可变快照。查询与原文链接绑定 library_id + generation，因此之后切换目录或重新扫描，旧引用仍能找到对应版本。“移除文档”仅从当前索引移除，保留本机文件、原始副本和历史快照；目录文件重新扫描后会再次导入。

单文件上限 32 MB，一次上传最多 30 份。一次只有一个索引任务。扫描逐文件读取，避免把整个目录原文件同时装入内存；完整解析快照仍需要内存。尚未提供历史快照和文件副本的自动清理，不建议直接删 SQLite/blob 文件回收空间。

## 原文精度与边界

支持 UTF-8 的 Markdown、TXT、RST、LOG、JSON、JSONL、CSV、HTML，以及 PDF、DOCX。

| 内容 | 当前定位方式 |
|---|---|
| DOCX 正文 | 原始正文段落序号，空段落和图片段落计入编号，不用检索切片号冒充段落号 |
| DOCX 表格 | 表格序号与行号；包含单元格内嵌套表格文字，按文本序列显示 |
| DOCX 页眉、页脚、脚注、尾注、文本框 | 保留来源区域或注释标识 |
| PDF | 真实页码、文本块和坐标；不声称 PDF 文本块就是作者段落 |
| 纯文本 | 段落序号及行号；JSON/CSV 不重新排版原始字符 |
| 文档图片 | 在所在段落、表格或 PDF 页显示 OCR 转写，可展开核对原图 |

不同段落不合并；长于 800 字符的来源单元按句界切片，无重叠、不丢尾部文字，并保留 char_start/char_end。阅读器高亮命中的段落或字符范围，仍可下载完整原文件。纯文本会统一换行并去掉单元边缘空白；这里的“原文”是解析后的文本，不是原文件字节或版式的完整复现。

OCR 可能识别错字；图片成功识别只表示得到文字，不代表 100% 字符准确率。扫描版 PDF 使用本地 OCR，文字 PDF 的嵌入图片也会识别。HTML 外链图片不下载，含修订 DOCX 会提示核对原文件；加密、损坏文件、复杂排版、OLE 对象、公式及非 UTF-8 文本仍可能无法完整解析。覆盖统计和警告用于显示这些边界，不应把扫描完成等同于完整理解了全部内容。

系统不改写、不总结、不自动裁决文档之间的版本冲突。需求文档中的相互矛盾内容需要查看上下文核对，不按文件名日期猜测哪个版本生效。

## 本地模型配置

.env.example 仅保留实际使用的变量：

| 变量 | 默认与含义 |
|---|---|
| NANOJEV_CHECKPOINT_DIR | models/nanojev，相对路径以 JEV 根目录为基准 |
| NANOJEV_DEVICE | auto：有可用 CUDA 时用 CUDA，否则 CPU；可显式设 cpu |
| NANOJEV_PRECISION | auto：支持 BF16 的 CUDA 用 BF16，其余 FP32 |
| NANOJEV_BATCH_SIZE | 4，每批段落数，允许 2–8；不限制总候选数 |
| NANOJEV_CPU_THREADS | 8，本机 CPU 推理线程数 |

当前验证设备是 CPU / FP32，未验证 CUDA 分支。默认候选数 12、返回数 3；桌面版保存这些设置，网页版仅在当前会话生效。API 可分别设置 top_k 与 max_evidence。输入超长时明确报错，不静默截断问题或把全文前缀冒充已读全文。

## 路径说明

| 路径 | 用途 |
|---|---|
| app.py | 本机 HTTP API、目录选择器、静态页面 |
| jev_core/common.py | 路径、分词和基础配置 |
| jev_core/parsing.py | 原文解析、来源定位、离线 OCR |
| jev_core/storage.py | SQLite、快照、文件副本、后台索引任务 |
| jev_core/nanojev.py | 可复现的本地决策模型适配器 |
| jev_core/retrieval.py | BM25、证据筛选、批内排名融合 |
| frontend/src/ | React 界面和样式 |
| static/ | 无前端构建时的基础界面 |
| storage/knowledge.sqlite3 | 文档库、版本和解析缓存，当前权威索引 |
| storage/blobs/ | 内容寻址的完整原始文件副本 |
| storage/ocr/ | OCR 文本、坐标和图片缓存 |
| storage/source-root.json | 可阅读的路径记录，SQLite 状态优先 |
| models/nanojev/、models/ocr/ | 本地权重 |
| tests/、evals/ | 功能回归和真实权重的语料评测 |

旧 storage/documents、manifest.json、chunks.json 和 index-meta.json 可保留为历史数据，不再作为运行时索引。已选目录从旧记录迁移，旧上传文件在首次新索引时纳入其所属目录。docs/research 中的研究稿保留历史调研日期，不能代替本实现文档。

## API

| 方法与路径 | 作用 |
|---|---|
| GET /api/config、/api/health | 当前库、模型、OCR、任务与覆盖统计 |
| GET /api/source-root | 当前和历史目录 |
| POST /api/source-root | body: {"path":"C:\\文档"}；返回 202 和索引任务 |
| POST /api/source-root/pick | 返回所选路径或 cancelled，不修改索引 |
| GET /api/documents | documents 数组和同版本 status |
| GET /api/documents/{id} | 文档全部解析单元；可带 library_id、generation |
| GET /api/documents/{id}/raw | 下载原文件；支持同样的版本参数 |
| POST /api/documents/upload | multipart files；返回 202 |
| DELETE /api/documents/{id}?generation=… | 当前库中按预期版本移除文档 |
| POST /api/documents/scan-workspace、/api/index/rebuild | 扫描当前目录；返回 202 |
| GET /api/index/job | 任务状态 |
| POST /api/index/jobs/{id}/cancel | 请求取消 |
| POST /api/query | question、top_k、max_evidence、可选 library_id |

查询示例：

~~~json
{"question":"资料室开放时间是什么？","top_k":12,"max_evidence":3}
~~~

status 为 found、no_answer 或 empty；answer 仅拼接选中来源及原文，或返回系统状态提示。diagnostics 给出实际召回数、模型检查数、返回数和耗时；没有伪造固定远程调用计数。需要审计网络时应实际抓取或阻断连接。

## 验证与设计依据

~~~powershell
python -m pip install pytest httpx
python -X utf8 -m pytest tests -q --basetemp storage/test-work
python -X utf8 evals/run_eval.py --source tests/ui-library --questions evals/example-questions.json --output storage/evals/example-results.json
~~~

公开评测使用仓库内的合成资料室文档，脚本检查标准答案是否存在，并禁止模型联网。它不是通用 benchmark。前端采用 frontend-design 指导建立蓝灰文档工作台，并参考 [Vercel Web Interface Guidelines](https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines) 检查键盘、焦点、响应式布局、反馈及可访问性。界面验证记录见[重构记录](history/REFACTOR_NOTES.md)。
