# 开发与验证

从仓库根目录执行命令。Windows 原生 Python 3.13、Node.js 22；`.venv` 只是 Python 依赖隔离，不使用 Docker、WSL 或虚拟机。

`app.py` 提供本机 API；`jev_core` 包含解析、OCR、索引、检索和 NanoJev 适配器。React 位于 `frontend/src`，无构建产物时回退到 `static`。Electron 主进程负责原生能力和 Python 子进程，页面只通过 `preload.cjs` 的有限接口访问桌面功能。

后端的 `JEV_STORAGE_DIR`、`JEV_MODELS_DIR`、`JEV_SOURCE_ROOT` 在进程启动时从环境读取。桌面启动器自动设置这些值；Web 开发通常使用默认目录。不要同时让两个进程写同一份 storage。

## 检查命令

```powershell
python -m pip install -r requirements-dev.txt
python -X utf8 -m pytest tests desktop/tests -q
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix desktop ci
npm --prefix desktop test
```

普通测试使用临时文档与微型模型替身，不下载权重；真实推理请按 [evals/README.md](../evals/README.md) 运行。CPU FP32 是发行验证路径，CUDA 尚未验证。

桌面开发先按 [desktop/README.md](../desktop/README.md) 准备独立运行环境，再执行 `npm --prefix desktop start`。修改 Python 或 React 后重新执行 prepare-runtime 更新暂存副本；修改 Electron 主进程后重启桌面程序。

## 提交约定

- 提交应用源码、两份 npm lockfile、构建脚本、合成测试和维护文档。
- 模型、storage、用户上传内容、真实业务评测输出、`.env`、SSH 密钥、依赖和发布产物保留在 Git 之外。
- 发行载荷通过 GitHub Release 提供，不使用 Git/LFS 存储数 GB 模型。
- 模型版本和下载 SHA256 变化时，重新运行真实推理和 OCR 验证；不要把游戏决策概率当作答案正确率。
- 研究稿保留日期与来源；当前功能以 README、技术参考、桌面说明和变更日志为准。

公开目录不需要本地代理配置或 `.skills`。第三方包来自官方上游，许可证见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
