"""Run with build/backend/python/python.exe -I: no host Python dependencies."""
import json
import os
from pathlib import Path
import sys
import threading
import time

from backend_entry import enforce_offline
enforce_offline()

from jev_core.common import BASE_DIR, STORAGE_DIR, DEFAULT_ROOT
from jev_core.nanojev import LocalNanoJev
from jev_core.parsing import DocumentParser, LocalOCR
from jev_core.retrieval import RagService
from jev_core.storage import KnowledgeStore

import torch
import transformers
import rapidocr
import onnxruntime
import pymupdf
from docx import Document
from PIL import Image, ImageDraw

for module in [torch, transformers, rapidocr, onnxruntime, pymupdf]:
    assert Path(module.__file__).resolve().is_relative_to(BASE_DIR), (module.__name__, module.__file__)
assert sys.flags.isolated and sys.flags.ignore_environment
assert not any("AppData" in item or "C:\\Python313" in item for item in sys.path)

DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)
(DEFAULT_ROOT / "资料室.md").write_text("# 资料室\n\n资料室开放时间为每周二至周六 09:30–17:30。\n\n每人最多借阅三份资料。\n", encoding="utf-8")
document = Document()
document.add_paragraph("Word parser verification.")
document.save(DEFAULT_ROOT / "sample.docx")
pdf = pymupdf.open()
page = pdf.new_page()
page.insert_text((72, 72), "Portable PDF verification.")
pdf.save(DEFAULT_ROOT / "sample.pdf")
pdf.close()
image = Image.new("RGB", (650, 100), "white")
draw = ImageDraw.Draw(image)
draw.text((20, 20), "JEV OFFLINE TEST 2026", fill="black", font_size=40)
image_path = STORAGE_DIR.parent / "ocr-fixture.png"
image_path.parent.mkdir(parents=True, exist_ok=True)
image.save(image_path)

ocr = LocalOCR(STORAGE_DIR / "ocr")
recognized = ocr.recognize(image_path.read_bytes())
assert recognized["status"] == "recognized", recognized
assert "JEV" in recognized["text"].upper(), recognized
store = KnowledgeStore(STORAGE_DIR, DEFAULT_ROOT, DocumentParser(ocr))
store.build(str(DEFAULT_ROOT), lambda _: None, threading.Event())
model = LocalNanoJev()
start = time.monotonic()
answer = RagService(store, model).query("资料室开放时间是什么？", 4, 3)
assert answer["evidence"] and "09:30" in answer["evidence"][0]["text"], answer
result = {"python": sys.version, "isolated": True, "external_network_blocked": True, "model": model.status(), "document_count": store.status()["documents"], "ocr_text": recognized["text"], "query_seconds": round(time.monotonic() - start, 3), "evidence": answer["evidence"]}
output = STORAGE_DIR.parent / "runtime-smoke-result.json"
output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"passed": True, "result": str(output), "document_count": result["document_count"], "ocr": result["ocr_text"], "query_seconds": result["query_seconds"]}, ensure_ascii=False))
