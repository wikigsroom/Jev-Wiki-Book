from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = Path(os.getenv("JEV_STORAGE_DIR", str(BASE_DIR / "storage"))).resolve()
MODELS_DIR = Path(os.getenv("JEV_MODELS_DIR", str(BASE_DIR / "models"))).resolve()
DEFAULT_ROOT = Path(os.getenv("JEV_SOURCE_ROOT", str(BASE_DIR))).resolve()
SUPPORTED = {".md", ".markdown", ".txt", ".rst", ".log", ".json", ".jsonl", ".csv", ".html", ".htm", ".pdf", ".docx"}
MAX_BYTES = 32 * 1024 * 1024


def load_env() -> None:
    path = BASE_DIR / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").strip()


def resolve_root(value: str | Path) -> Path:
    path = Path(str(value).strip()).expanduser()
    path = (path if path.is_absolute() else BASE_DIR / path).resolve()
    if not path.is_dir():
        raise ValueError(f"目录不存在或不可访问：{path}")
    return path


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".pending")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


# Keep Chinese runs separate: do not form bigrams across punctuation or words.
STOP_WORDS = {"什么", "哪些", "如何", "怎么", "多少", "是否", "请问", "请", "的", "了", "是", "在", "和", "与", "吗", "呢", "有", "需要", "要求", "文档", "说明", "the", "is", "a", "an", "what", "how", "are", "to", "of"}


def tokens(text: str) -> list[str]:
    result = []
    for run in re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]+", text.lower()):
        if re.match(r"[a-z0-9_]", run):
            if run not in STOP_WORDS:
                result.append(run)
        elif len(run) == 1:
            if run not in STOP_WORDS:
                result.append(run)
        else:
            result.extend(run[i:i + 2] for i in range(len(run) - 1) if run[i:i + 2] not in STOP_WORDS)
    return result


def query_tokens(text: str) -> list[str]:
    # Split question scaffolding before bigram tokenization. Otherwise "是什么"
    # creates spurious terms such as "是什", and can retrieve unrelated facts.
    clean = re.sub(r"(?:截图|图片|文档)[里中]|请问|告诉我|是什么|是多少|有哪些|多少|几位|几个|多长|多久|如何|怎么|哪些|什么|是否|能否|的|吗|呢|各|或", " ", text)
    return tokens(clean)
