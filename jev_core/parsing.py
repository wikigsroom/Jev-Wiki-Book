"""Parse in reading order. Every hit points to a real source unit, never a chunk ordinal."""
from __future__ import annotations

import io
import json
import re
import sys
import threading
import zipfile
from pathlib import Path
from typing import Callable

from .common import BASE_DIR, MODELS_DIR, digest, normalize

PARSER_VERSION = "paragraphs-v5-ocr-v4"
OCR_VERSION = "rapidocr-ppocrv4-960-v1"


class LocalOCR:
    """RapidOCR/ONNX, with explicit preinstalled weights and no runtime download."""

    def __init__(self, cache_dir: Path, model_dir: Path | None = None):
        self.cache_dir = cache_dir
        self.model_dir = model_dir or MODELS_DIR / "ocr"
        self.engine = None
        self.lock = threading.Lock()

    def model_paths(self) -> list[Path]:
        return [self.model_dir / name for name in ("det.onnx", "cls.onnx", "rec.onnx")]

    def status(self) -> dict:
        return {"provider": "RapidOCR", "local": True, "configured": all(p.is_file() for p in self.model_paths()), "loaded": self.engine is not None}

    def recognize(self, data: bytes) -> dict:
        from PIL import Image
        from .common import atomic_json

        key = digest(data)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached = self.cache_dir / f"{key}.json"
        image_path = self.cache_dir / f"{key}.png"
        if cached.exists() and image_path.exists():
            value = json.loads(cached.read_text(encoding="utf-8"))
            if value.get("version") in {OCR_VERSION, "paragraphs-v3-ocr-v4"} and value.get("status") in {"recognized", "no_text"}:
                return value
        try:
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img.save(image_path, "PNG")
            value = {"asset_id": key, "width": img.width, "height": img.height, "version": OCR_VERSION}
            with self.lock:
                if self.engine is None:
                    if not all(p.is_file() for p in self.model_paths()):
                        raise RuntimeError("本地 OCR 权重未安装，请运行 python setup_ocr.py")
                    runtime = str(BASE_DIR / ".runtime" / "ocr")
                    if runtime not in sys.path:
                        sys.path.append(runtime)
                    from rapidocr import RapidOCR
                    from rapidocr.utils.typings import ModelType, OCRVersion
                    self.engine = RapidOCR(params={
                        "Det.model_path": str(self.model_paths()[0]),
                        "Cls.model_path": str(self.model_paths()[1]),
                        "Rec.model_path": str(self.model_paths()[2]),
                        "Det.ocr_version": OCRVersion.PPOCRV4, "Det.model_type": ModelType.MOBILE,
                        "Rec.ocr_version": OCRVersion.PPOCRV4, "Rec.model_type": ModelType.MOBILE,
                        "Det.mean": [0.485, 0.456, 0.406], "Det.std": [0.229, 0.224, 0.225],
                        "Det.limit_type": "max", "Det.limit_side_len": 960,
                        "Global.log_level": "error", "Global.text_score": 0.5,
                        "EngineConfig.onnxruntime.intra_op_num_threads": 4,
                        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                    })
                result = self.engine(img)
            texts = list(result.txts or [])
            scores = [float(s) for s in (result.scores if result.scores is not None else [])]
            boxes = result.boxes.tolist() if result.boxes is not None else []
            value.update(status="recognized" if texts else "no_text", text="\n".join(texts), scores=scores, boxes=boxes)
            atomic_json(cached, value)
            return value
        except Exception as exc:
            return {"asset_id": key if image_path.exists() else None, "version": OCR_VERSION,
                    "status": "unread", "text": "", "error": f"{type(exc).__name__}: {exc}"}


class DocumentParser:
    def __init__(self, ocr: LocalOCR | None = None):
        self.ocr = ocr

    def parse(self, path: Path, name: str, progress: Callable[[str], None] | None = None) -> dict:
        blocks: list[dict] = []
        coverage = {"native_blocks": 0, "images": 0, "images_recognized": 0, "images_no_text": 0, "images_unread": 0, "warnings": []}
        section = name

        def add(text: str, kind: str, locator: dict, **extra):
            text = normalize(text)
            if not text and kind != "image":
                return
            block = {"id": f"b{len(blocks) + 1}", "order": len(blocks), "kind": kind,
                     "text": text, "section": section, "locator": locator, **extra}
            blocks.append(block)
            if kind not in {"ocr", "image"}:
                coverage["native_blocks"] += 1

        def image(data: bytes, locator: dict):
            coverage["images"] += 1
            if progress:
                progress(f"{name} · 识别图片 {coverage['images']}")
            result = self.ocr.recognize(data) if self.ocr else {"status": "unread", "text": "", "error": "OCR 未启用"}
            state = result["status"]
            field = {"recognized": "images_recognized", "no_text": "images_no_text", "unread": "images_unread"}[state]
            coverage[field] += 1
            add(result.get("text", ""), "ocr" if state == "recognized" else "image", locator,
                asset_id=result.get("asset_id"), width=result.get("width", 1), height=result.get("height", 1),
                ocr_status=state, ocr_error=result.get("error"), transcription=True)

        suffix = path.suffix.lower()
        if suffix == ".docx":
            from docx import Document
            from docx.oxml.ns import qn
            from docx.text.paragraph import Paragraph
            from docx.table import Table
            document = Document(path)
            counters = {"paragraph": 0, "table": 0, "image": 0}

            def walk(container, owner, region="正文"):
                nonlocal section
                # Word stores modern drawing markup and a compatibility fallback
                # for the same shape. Read one branch, never two copies of its text.
                for alternate in container.xpath(".//*[local-name()='AlternateContent']"):
                    choices = [node for node in alternate if node.tag.rsplit("}", 1)[-1] == "Choice"]
                    fallbacks = [node for node in alternate if node.tag.rsplit("}", 1)[-1] == "Fallback"]
                    selected = next(iter(choices or fallbacks), None)
                    parent = alternate.getparent()
                    if selected is not None and parent is not None:
                        position = parent.index(alternate)
                        for offset, node in enumerate(list(selected)):
                            parent.insert(position + offset, node)
                        parent.remove(alternate)
                paragraph_number = 0
                for child in container:
                    if child.tag == qn("w:p"):
                        paragraph_number += 1
                        number = paragraph_number
                        para = Paragraph(child, owner)
                        if para.text.strip() and (para.style and re.search(r"heading|标题", para.style.name, re.I)):
                            section = para.text.strip()
                        locator = {"type": "docx_paragraph", "paragraph_number": number, "region": region,
                                   "label": f"{region}第 {number} 段"}
                        add(para.text, "paragraph", locator)
                        for text_box in child.xpath(".//w:txbxContent/w:p"):
                            text = "".join(text_box.xpath(".//w:t/text()"))
                            add(text, "textbox", {**locator, "label": f"{region}第 {number} 段 · 文本框"})
                        for blip in child.xpath(".//a:blip | .//*[local-name()='imagedata']"):
                            rid = blip.get(qn("r:embed")) or blip.get(qn("r:id"))
                            if rid and rid in owner.part.related_parts:
                                counters["image"] += 1
                                image(owner.part.related_parts[rid].blob, {**locator, "image_number": counters["image"],
                                      "label": f"{region}第 {number} 段 · 图片 {counters['image']}"})
                    elif child.tag == qn("w:tbl"):
                        counters["table"] += 1
                        table_no = counters["table"]
                        table = Table(child, owner)
                        for row_no, row in enumerate(table.rows, 1):
                            # Include text inside nested tables, which cell.text omits.
                            cells = ["\n".join(Paragraph(p, cell).text for p in cell._tc.xpath(".//w:p")) for cell in row.cells]
                            add(" | ".join(cells), "table_row", {"type": "table_row", "table_number": table_no,
                                "row_number": row_no, "region": region, "label": f"表格 {table_no} · 第 {row_no} 行"}, cells=cells)
                            visited_cells = set()
                            for cell in row.cells:
                                if cell._tc in visited_cells:
                                    continue
                                visited_cells.add(cell._tc)
                                for blip in cell._tc.xpath(".//a:blip | .//*[local-name()='imagedata']"):
                                    rid = blip.get(qn("r:embed")) or blip.get(qn("r:id"))
                                    if rid in owner.part.related_parts:
                                        image(owner.part.related_parts[rid].blob, {"type": "table_image", "table_number": table_no,
                                              "row_number": row_no, "label": f"表格 {table_no} · 第 {row_no} 行图片"})

            walk(document.element.body, document)
            seen_parts = set()
            for doc_section in document.sections:
                for region, part_owner in (("页眉", doc_section.header), ("页脚", doc_section.footer),
                                           ("首页页眉", doc_section.first_page_header), ("首页页脚", doc_section.first_page_footer),
                                           ("偶数页页眉", doc_section.even_page_header), ("偶数页页脚", doc_section.even_page_footer)):
                    if str(part_owner.part.partname) not in seen_parts:
                        seen_parts.add(str(part_owner.part.partname))
                        section = f"{name} · {region}"
                        walk(part_owner._element, part_owner, region)
            # Footnote/endnote bodies are not exposed by python-docx's paragraph API.
            from lxml import etree
            with zipfile.ZipFile(path) as archive:
                for part_name, label in (("word/footnotes.xml", "脚注"), ("word/endnotes.xml", "尾注")):
                    if part_name in archive.namelist():
                        xml = etree.fromstring(archive.read(part_name))
                        for note in xml:
                            note_id = int(note.get(qn("w:id"), "-1"))
                            if note_id >= 1:
                                add("\n".join("".join(p.xpath(".//w:t/text()", namespaces=xml.nsmap))
                                              for p in note.xpath(".//w:p", namespaces=xml.nsmap)),
                                    "note", {"type": "note", "label": f"{label} {note_id}"})
            if document.element.body.xpath(".//w:ins | .//w:del"):
                coverage["warnings"].append("文档含修订记录；请下载原文件核对修订内容。")
        elif suffix == ".pdf":
            import fitz
            with fitz.open(path) as document:
                for page_no, page in enumerate(document, 1):
                    native = page.get_text("blocks", sort=True)
                    for block_no, block in enumerate(native, 1):
                        if len(block) > 6 and block[6] == 0:
                            add(block[4], "pdf_text", {"type": "pdf_block", "page": page_no, "bbox": list(block[:4]),
                                "label": f"第 {page_no} 页 · 文本块 {block_no}"})
                    # Read embedded images too; text PDFs can contain important screenshots.
                    seen_images = set()
                    for info in page.get_images(full=True):
                        if info[0] not in seen_images:
                            seen_images.add(info[0])
                            try:
                                data = document.extract_image(info[0])["image"]
                                image(data, {"type": "pdf_image", "page": page_no, "label": f"第 {page_no} 页 · 图片 {len(seen_images)}"})
                            except Exception as exc:
                                coverage["images"] += 1
                                coverage["images_unread"] += 1
                                coverage["warnings"].append(f"第 {page_no} 页图片提取失败：{exc}")
                    if not native and not seen_images:
                        image(page.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png"),
                              {"type": "pdf_page", "page": page_no, "label": f"第 {page_no} 页 · 页面识别"})
        else:
            text = path.read_text(encoding="utf-8-sig", errors="strict")
            if suffix in {".html", ".htm"}:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(text, "html.parser")
                for tag in soup(["script", "style", "noscript"]):
                    tag.decompose()
                elements = soup.select("h1,h2,h3,h4,h5,h6,p,li,pre,tr,blockquote")
                for number, element in enumerate(elements, 1):
                    if element.name.startswith("h"):
                        section = element.get_text(" ", strip=True)
                    # Avoid duplicating child paragraphs inside a selected outer block.
                    if element.find_parent(["li", "blockquote", "pre", "tr"]) is None:
                        add(element.get_text(" ", strip=True), "paragraph", {"type": "html_block", "paragraph_number": number, "label": f"文本块 {number}"})
                if not blocks:
                    text = soup.get_text("\n", strip=True)
                else:
                    text = ""
                if soup.find("img"):
                    coverage["warnings"].append("HTML 外链图片未下载；图片内容未进入索引。")
            # Keep exact JSON/CSV characters. Do not pretty-print source data.
            parts = list(re.finditer(r"[^\n](?:.*?)(?=\n\s*\n|\Z)", text, re.S))
            if suffix in {".csv", ".jsonl"}:
                parts = list(re.finditer(r"[^\n]+", text))
            for number, match in enumerate(parts, 1):
                value = match.group().strip()
                heading = re.match(r"^#{1,6}\s+([^\n]+)", value)
                if heading:
                    section = heading.group(1)
                first_line = text.count("\n", 0, match.start()) + 1
                last_line = first_line + match.group().count("\n")
                add(value, "paragraph", {"type": "text_paragraph", "paragraph_number": number,
                    "line_start": first_line, "line_end": last_line, "label": f"第 {number} 段 · 行 {first_line}–{last_line}"})
        coverage["searchable_blocks"] = sum(bool(b["text"]) for b in blocks)
        return {"blocks": blocks, "coverage": coverage, "parser_version": PARSER_VERSION}


def passages(block: dict, max_chars: int = 800) -> list[dict]:
    """Split only long source units; never merge different paragraphs or silently truncate."""
    text = block["text"]
    result = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = max(text.rfind(symbol, start + max_chars // 2, end) for symbol in ("。", "！", "？", "\n", ". "))
            if boundary >= start:
                end = boundary + 1
        result.append({**block, "block_id": block["id"], "text": text[start:end], "char_start": start, "char_end": end})
        start = end
    return result
