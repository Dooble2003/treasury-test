import io
import os
import threading
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from rapidocr import RapidOCR

# Larger uploads are shrunk before OCR. Detection runs at 1600 px anyway, and the
# warning re-read works from this copy, so keeping more pixels only costs memory.
MAX_LONG_EDGE = 3200
Image.MAX_IMAGE_PIXELS = 60_000_000


class ImageError(ValueError):
    pass


@dataclass
class Word:
    text: str
    score: float
    box: np.ndarray


@dataclass
class Line:
    text: str
    score: float
    box: np.ndarray
    image: int = 0
    words: list[Word] = field(default_factory=list)
    rectified: bool = False

    @property
    def height(self) -> float:
        return float(self.box[:, 1].max() - self.box[:, 1].min())


def load_image(data: bytes) -> np.ndarray:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageError("unreadable image") from exc
    arr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    h, w = arr.shape[:2]
    scale = MAX_LONG_EDGE / max(h, w)
    if scale < 1:
        arr = cv2.resize(arr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    return arr


def _engine_params(kind: str) -> dict:
    # Small CPU pools avoid contention between detection and recognition sessions.
    threads = int(os.environ.get("OCR_THREADS", "0")) or min(os.cpu_count() or 2, 2)
    params = {
        "Global.log_level": "error",
        "Global.max_side_len": 1600,
        "Global.return_word_box": True,
        "EngineConfig.onnxruntime.intra_op_num_threads": threads,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    }
    if kind == "detail":
        # Crops are already upscaled on purpose. The default "min" limit would blow a wide,
        # short warning strip up to several thousand pixels (slow and less accurate).
        params |= {
            "Global.max_side_len": 4000,
            "Det.limit_type": "max",
            "Det.limit_side_len": 4000,
        }
    return params


_engines: dict[str, RapidOCR] = {}
_engines_lock = threading.Lock()
_inference_lock = threading.Lock()


def _engine(kind: str) -> RapidOCR:
    with _engines_lock:
        if kind not in _engines:
            _engines[kind] = RapidOCR(params=_engine_params(kind))
        return _engines[kind]


def warm_up() -> None:
    blank = np.full((200, 600, 3), 255, np.uint8)
    cv2.putText(blank, "WARM UP", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 4)
    _engine("full")(blank)
    _engine("detail")(blank)


def _run(engine: RapidOCR, img: np.ndarray, image_index: int, *, tight: bool = False) -> list[Line]:
    # RapidOCR keeps call parameters on the shared engine. Set the boundary width
    # on every call and prevent another request from changing it during inference.
    with _inference_lock:
        result = engine(img, unclip_ratio=0.7 if tight else 1.6)
    if not result.txts:
        return []
    word_results = result.word_results or [()] * len(result.txts)
    lines = []
    for text, score, box, words in zip(
        result.txts, result.scores, result.boxes, word_results, strict=False
    ):
        box = np.asarray(box, dtype=float)
        parsed = [Word(w[0], float(w[1]), np.asarray(w[2], dtype=float)) for w in words if w]
        if not parsed:
            parsed = [Word(t, float(score), box) for t in text.split()]
        lines.append(Line(text, float(score), box, image_index, parsed))
    return lines


def read_lines(img: np.ndarray, image_index: int = 0) -> list[Line]:
    return _run(_engine("full"), img, image_index)


def read_strip(img: np.ndarray, image_index: int) -> list[Line]:
    height, width = img.shape[:2]
    box = np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype=float)
    engine = _engine("detail")
    with _inference_lock:
        result = engine.recognize_txt([img])
        words = engine.calc_word_boxes([img], np.array([box], dtype=np.float32), result)
    if not result.txts or not result.txts[0].strip():
        return []
    parsed = (
        [
            Word(text, float(score), np.asarray(points, dtype=float))
            for text, score, points in words[0]
        ]
        if words
        else []
    )
    return [Line(result.txts[0], float(result.scores[0]), box, image_index, parsed)]


def read_region(
    img: np.ndarray,
    region: tuple[int, int, int, int],
    scale: float,
    pad: int,
    image_index: int,
    *,
    tight: bool = False,
) -> list[Line]:
    x0, y0, x1, y1 = region
    crop = img[y0:y1, x0:x1]
    if crop.size == 0:
        return []
    # Text that touches the crop edge is often missed or merged by the detector, so
    # surround the crop with plain background.
    background = [int(v) for v in np.median(crop.reshape(-1, 3), axis=0)]
    crop = cv2.copyMakeBorder(crop, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=background)
    if scale != 1:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    lines = _run(_engine("detail"), crop, image_index, tight=tight)
    offset = np.array([x0 - pad, y0 - pad], dtype=float)
    for line in lines:
        line.box = line.box / scale + offset
        for word in line.words:
            word.box = word.box / scale + offset
    return lines


def quality_notes(img: np.ndarray, lines: list[Line]) -> list[str]:
    if not lines:
        return ["No text was found in this image."]
    notes = []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    scale = 1000 / max(gray.shape)
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    if cv2.Laplacian(gray, cv2.CV_64F).var() < 40:
        notes.append("The image looks blurry.")
    if np.mean([line.score for line in lines]) < 0.8:
        notes.append("Some text was hard to read. A sharper, straight-on image would help.")
    return notes
