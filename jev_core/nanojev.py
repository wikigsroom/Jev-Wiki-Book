"""Reproducible local NanoJev inference; no import of mutable downloaded Python scripts.

Decision head matches TianyuCodings/NanoJev's train_toy_decisions.DecisionModel.
Weights, tokenizer and backbone configuration are loaded strictly from disk.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .common import BASE_DIR, MODELS_DIR, env_int


def decision_model(backbone, set_head):
    import torch
    from torch import nn

    class DecisionModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = backbone
            hidden = backbone.config.hidden_size
            self.norm = nn.LayerNorm(hidden)
            self.scalar = nn.Linear(hidden, 1)
            self.set_head = set_head
            if set_head == "attention":
                self.set_project = nn.Linear(hidden + 1, 128)
                self.set_attention = nn.MultiheadAttention(128, 4, dropout=0, batch_first=True)
                self.set_output = nn.Linear(128, 1)

        def forward(self, paths, pad_token):
            device = self.scalar.weight.device
            lengths = torch.tensor([len(path) for path in paths], device=device)
            width = int(lengths.max())
            ids = torch.full((len(paths), width), pad_token, dtype=torch.long, device=device)
            for index, path in enumerate(paths):
                ids[index, :len(path)] = torch.tensor(path, device=device)
            mask = torch.arange(width, device=device)[None, :] < lengths[:, None]
            hidden = self.backbone(input_ids=ids, attention_mask=mask, use_cache=False).last_hidden_state
            h = self.norm(hidden[torch.arange(len(paths), device=device), lengths - 1])[None, :, :]
            logits = self.scalar(h).squeeze(-1).float()
            if self.set_head == "attention":
                log_k = torch.tensor(float(len(paths)), device=device).log().expand(1, len(paths), 1)
                u = self.set_project(torch.cat([h, log_k.to(h.dtype)], dim=-1))
                mixed, _ = self.set_attention(u, u, u, need_weights=False)
                logits = logits + self.set_output(torch.tanh(u + mixed)).squeeze(-1).float()
            return logits[0]

    return DecisionModel()


class LocalNanoJev:
    model_id = "C-Tianyu/NanoJev"

    def __init__(self, checkpoint: Path | None = None):
        configured = Path(os.getenv("NANOJEV_CHECKPOINT_DIR", str(MODELS_DIR / "nanojev")))
        self.checkpoint = checkpoint or (configured if configured.is_absolute() else BASE_DIR / configured)
        self.model = None
        self.tokenizer = None
        self.device = "unloaded"
        self.precision = "unloaded"
        self.error = None
        self.calls = 0
        self.lock = threading.RLock()
        self.batch_size = max(2, min(8, env_int("NANOJEV_BATCH_SIZE", 4)))

    def status(self):
        files = ["best.safetensors", "config.json", "backbone_config/config.json", "tokenizer/tokenizer.json", "tokenizer/tokenizer_config.json"]
        missing = [name for name in files if not (self.checkpoint / name).is_file()]
        return {"model": self.model_id, "checkpoint_configured": not missing, "loaded": self.model is not None,
                "device": self.device, "precision": self.precision, "missing": missing, "error": self.error,
                "calls": self.calls, "batch_size": self.batch_size, "local_only": True,
                "training_scope": "community unified-games-v1; document retrieval not calibrated",
                "probability_meaning": "relative choice weight, not answer confidence"}

    def load(self):
        with self.lock:
            if self.model is not None:
                return
            if self.status()["missing"]:
                raise RuntimeError("本地 NanoJev 权重不完整，请运行 python download_nanojev.py")
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
            import torch
            from transformers import AutoConfig, AutoModel, AutoTokenizer
            from safetensors.torch import load_file

            requested = os.getenv("NANOJEV_DEVICE", "auto")
            self.device = ("cuda:0" if torch.cuda.is_available() else "cpu") if requested == "auto" else requested
            if self.device.startswith("cuda") and not torch.cuda.is_available():
                raise RuntimeError("当前 PyTorch 没有可用 CUDA；设置 NANOJEV_DEVICE=cpu 可使用本地 CPU")
            requested_precision = os.getenv("NANOJEV_PRECISION", "auto")
            bf16 = self.device.startswith("cuda") and torch.cuda.is_bf16_supported()
            self.precision = ("bf16" if bf16 else "fp32") if requested_precision == "auto" else requested_precision
            if self.precision not in {"fp32", "bf16"}:
                raise RuntimeError("NANOJEV_PRECISION 必须为 auto、fp32 或 bf16")
            if self.precision == "bf16" and not bf16:
                raise RuntimeError("当前设备不支持此 BF16 配置，请使用 fp32")
            torch.set_num_threads(max(1, env_int("NANOJEV_CPU_THREADS", min(8, os.cpu_count() or 4))))
            try:
                from torch._native import triton_utils
                triton_utils.deregister_op_overrides()
            except (ImportError, AttributeError):
                pass
            config = json.loads((self.checkpoint / "config.json").read_text(encoding="utf-8"))
            body_config = AutoConfig.from_pretrained(str(self.checkpoint / "backbone_config"), local_files_only=True, trust_remote_code=False)
            body_config.use_cache = False
            tokenizer = AutoTokenizer.from_pretrained(str(self.checkpoint / "tokenizer"), local_files_only=True, trust_remote_code=False)
            if tokenizer.pad_token_id is None:
                tokenizer.pad_token = tokenizer.eos_token
            body = AutoModel.from_config(body_config, attn_implementation="sdpa", trust_remote_code=False).float()
            model = decision_model(body, config["set_head"])
            weights = load_file(str(self.checkpoint / "best.safetensors"), device="cpu")
            model.load_state_dict(weights, strict=True)
            del weights
            self.model = model.to(device=self.device, dtype=torch.float32).eval()
            self.tokenizer = tokenizer
            self.max_tokens = config.get("max_length", 8192)
            self.error = None

    def rank(self, question: str, candidates: list[dict]) -> list[dict]:
        if not candidates:
            return []
        try:
            with self.lock:
                self.load()
                import torch
                output = []
                for start in range(0, len(candidates), self.batch_size):
                    group = candidates[start:start + self.batch_size]
                    descriptions = [f"Document: {c['document_name']}\nSection: {c['section']}\nPassage:\n{c['text']}" for c in group]
                    keys = [f"c{index}" for index in range(len(group))] + ["none"]
                    descriptions.append("None of the supplied passages contains information that answers the query. 所有段落都不能回答问题。")
                    segments = [f"State:\nQuery:\n{question}\n",
                                "Question type: choice\nQuestion:\nChoose the passage that directly answers the query. "
                                "A shared topic alone is insufficient. Choose none when the requested fact is absent.\n"]
                    prefix = sum([self.tokenizer.encode(text, add_special_tokens=False) for text in segments], [])
                    paths = [prefix + self.tokenizer.encode(f"Candidate:\n{key}: {description}\nDecision:", add_special_tokens=False)
                             + [self.tokenizer.eos_token_id] for key, description in zip(keys, descriptions)]
                    if max(map(len, paths)) > self.max_tokens:
                        raise RuntimeError("问题和原文超出本地模型上下文；请缩短问题。没有截断或外发内容。")
                    use_bf16 = self.precision == "bf16"
                    with torch.inference_mode(), torch.autocast("cuda" if self.device.startswith("cuda") else "cpu", dtype=torch.bfloat16, enabled=use_bf16):
                        logits = self.model(paths, self.tokenizer.pad_token_id)
                    if not torch.isfinite(logits).all():
                        raise RuntimeError("本地模型返回非有限数值")
                    probs = logits.float().softmax(-1).cpu().tolist()
                    winner = keys[max(range(len(probs)), key=probs.__getitem__)]
                    self.calls += 1
                    for index, candidate in enumerate(group):
                        output.append({**candidate, "jev": {"probability": probs[index], "none_probability": probs[-1],
                                       "choice": winner, "batch": start // self.batch_size,
                                       "supports_over_none": probs[index] > probs[-1], "provider": "local-nanojev"}})
                self.error = None
                return output
        except Exception as exc:
            self.error = str(exc)
            raise RuntimeError(f"本地 NanoJev 未完成判断：{exc}") from exc
