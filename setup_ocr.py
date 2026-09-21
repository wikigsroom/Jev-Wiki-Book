"""One-time download of pinned RapidOCR weights. Runtime stays offline."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import os
import urllib.request

ROOT = Path(__file__).resolve().parent
MODELS = {
    "det": ("det/ch_PP-OCRv4_det_mobile.onnx", "d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9"),
    "cls": ("cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx", "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c"),
    "rec": ("rec/ch_PP-OCRv4_rec_mobile.onnx", "48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b"),
}


def download(item):
    name, (relative, sha) = item
    target = ROOT / "models" / "ocr" / (name + ".onnx")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == sha:
        return f"{name}: verified local file"
    url = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/" + relative
    temporary = target.with_suffix(".download")
    hasher = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
        while data := response.read(1024 * 1024):
            output.write(data)
            hasher.update(data)
    if hasher.hexdigest() != sha:
        raise RuntimeError(f"{name}: SHA256 mismatch; file was not activated")
    os.replace(temporary, target)
    return f"{name}: downloaded and SHA256 verified"


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as executor:
        for result in executor.map(download, MODELS.items()):
            print(result, flush=True)
