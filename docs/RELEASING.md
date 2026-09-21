# Windows Release 发布

仓库通过 SSH 推送；GitHub Release 创建和附件上传使用 HTTPS API，需要有本仓库 Contents 写入权限的有效登录。SSH 密钥不能代替 Release API 凭据。不要把令牌写进源码、命令参数或提交记录。

## 构建与验证

1. 按 [desktop/README.md](../desktop/README.md) 安装依赖、下载固定权重并构建 portable EXE。
2. 运行 Python/Node 回归、真实独立运行环境 smoke 与原生桌面验收。
3. 执行 `python -X utf8 desktop/scripts/release_portable.py` 生成完整 ZIP，再执行 `python -X utf8 desktop/scripts/verify_release.py`。
4. 更新变更日志、验证记录和发布说明，提交源码并推送对应标签。

GitHub 的 [Release 单文件上限](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases) 是 2 GiB，完整 ZIP 通过两份字节分卷分发。

## 准备附件

```powershell
python -X utf8 desktop/scripts/prepare_github_release.py
```

输出到 `release/github-v0.5.0/`：EXE、`.zip.001` / `.zip.002`、JSON 大小与 SHA256 清单、`Merge-JEV.cmd`、可选 `Merge-JEV.ps1`、ZIP SHA256 与发行校验报告。按 1.5 GiB 切割，不重新压缩或修改已验证的 ZIP 内容。

磁盘空间不足时可显式加 `--consume-archive`：先保存并校验尾卷，再把原 ZIP 改为首卷，以避免额外复制整包。原 ZIP 路径随之消失，但全部字节仍在两个分卷中，合并后 SHA256 与原始验证报告一致。

普通使用者把分卷、JSON 与合并脚本放在一起，执行 `Merge-JEV.cmd`。它使用 Windows 自带的 certutil、copy 和 ren，先校验各卷，再合并并校验完整 SHA256；不会联网、执行 EXE 或覆盖不同内容的已有文件。`Merge-JEV.cmd /verify` 只检查分卷而不新建 ZIP。可选的 PowerShell 脚本受当前系统执行策略约束，不要为了运行它降低系统策略；它的 `-VerifyOnly` 同时校验分卷顺序构成的完整 ZIP。

## 上传与发布

安装并登录官方 [GitHub CLI](https://cli.github.com/)，确认当前身份有仓库写入权限。发布脚本优先使用 PATH 中的 gh，也支持 `--gh` 指定便携 gh.exe。

```powershell
git push origin main
git tag -a v0.5.0 -m "JEV 0.5.0 Windows portable"
git push origin v0.5.0
python -X utf8 desktop/scripts/publish_github_release.py --check
python -X utf8 desktop/scripts/publish_github_release.py
```

脚本检查本地清单、远端标签和仓库权限，先创建草稿，再上传附件并核对 GitHub 返回的大小与 SHA256，全部成功后发布。已存在同名但内容不一致的附件会停止，不自动覆盖或删除；重复执行跳过一致附件。发布回执写到 `release/github-published.json`。

v0.5.0 EXE 保持桌面验收时的原始二进制；公开整理只更新文档、示例评测与发布工具。原始 ZIP 的 SOURCE 是构建时源码快照；维护后的文档与发布工具以仓库标签为准。当前 EXE 未签名。
