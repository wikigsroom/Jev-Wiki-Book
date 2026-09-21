# 第三方组件与模型来源

应用新增代码目前未指定统一许可证。下列组件保留各自上游许可证；此文件不修改第三方授权。完整便携包在 THIRD-PARTY 中附带许可证正文、Python 精确版本清单、Chromium notices 和模型来源记录。

| 组件 | 上游 | 许可证 / 说明 |
| --- | --- | --- |
| NanoJev | [TianyuCodings/NanoJev](https://github.com/TianyuCodings/NanoJev)、[C-Tianyu/NanoJev](https://huggingface.co/C-Tianyu/NanoJev) | MIT；社区游戏决策实现与 checkpoint |
| Qwen3-0.6B | [Qwen/Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B) | Apache-2.0；NanoJev 骨干 |
| RapidOCR / PaddleOCR | [RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR)、[PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | Apache-2.0；PP-OCRv4 ONNX 权重 |
| Electron / Chromium | [electron/electron](https://github.com/electron/electron) | Electron MIT；Chromium 各组件见随包 notices |
| CPython | [python.org](https://www.python.org/) | PSF License 与随包 notices |
| React | [facebook/react](https://github.com/facebook/react) | MIT |
| PyTorch | [pytorch/pytorch](https://github.com/pytorch/pytorch) | BSD-3-Clause 与随包第三方 notices |
| Transformers / Safetensors | [Hugging Face](https://github.com/huggingface) | Apache-2.0 |
| PyMuPDF / MuPDF | [pymupdf/PyMuPDF](https://github.com/pymupdf/PyMuPDF) | AGPL-3.0 或上游商业许可；此发行包附带 AGPL 材料 |

NanoJev 固定到 Hugging Face 修订 `047b927b30882a1138fc504821b82ac145a4b81a`；原始 `best.safetensors` SHA256：

```text
f68c47d66998231b86b7e91b4ed5e82ae23acf104c8b7cd6d165c3ac7b7ffe1b
```

权重未做量化或精度转换。本仓库不包含 TypeSafe 官方 Jev 权重，也不与该服务建立运行依赖。下载脚本和本地模型适配器位于 `download_nanojev.py`、`setup_ocr.py` 与 `jev_core/nanojev.py`。

开发时参考了 [Vercel Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines) 和 frontend-design 指导；工具技能本身不随应用发行。
