# 本地检索评测

公开示例使用 [tests/ui-library/资料室说明.md](../tests/ui-library/资料室说明.md) 中的合成资料室事实，以及 [example-questions.json](example-questions.json) 的 2 道有答案题、2 道无答案题。不是实际业务文档，也不是通用中文检索 benchmark。

## 运行公开示例

先按项目 README 安装依赖并下载 NanoJev，然后从项目根目录执行：

```powershell
python -X utf8 evals/run_eval.py --source tests/ui-library --questions evals/example-questions.json --output storage/evals/example-results.json
```

`--source` 在临时目录建立独立索引，不会切换现有应用的文档库。模型加载与推理期间禁止网络连接。题目文件的 `gold_text` 必须能在解析后的原文中找到，否则明确报错；空字符串代表无答案题。结果写到 Git 忽略的 storage 目录。

自定义语料时替换 source 和 questions；题目 JSON 采用相同结构。省略 `--source` 时只读当前应用的不可变索引快照，不会重新扫描或切换目录。输出包含候选和原文，发布前需要确认其中没有私有内容。

## 指标与边界

2026-09-21 在 CPU FP32 上运行公开示例：2/2 有答案题首条命中，2/2 无答案题不返回内容。首题包含模型加载耗时 48.190 秒，其余约 1.6–3.2 秒。只有四个合成样例，不能推广为真实业务准确率。

脚本分别记录 BM25 与最终结果的命中排名、MRR、无答案拒绝率、每题候选数及耗时。候选默认 12 个，NanoJev 每批 4 个候选加 none，最多返回 3 个原文单元。

历史开发曾使用一组不公开的业务资料做 8 道有答案、4 道无答案的同语料回归；这些题参与规则调整，不属于独立测试，原题、候选文本和输出留在本机。该次观察中，直接使用游戏决策权重重排会降低首条命中，所以当前实现由词法排序主导、模型辅助筛选。

上述结果都不能证明 NanoJev 优于 BM25、所有返回段落正确或 OCR 没有错字。真正评估泛化能力需要独立标注的语料、同义改写、组合问题、候选顺序扰动与领域相关性训练。[桌面实际验证](../desktop/VERIFICATION.md)
