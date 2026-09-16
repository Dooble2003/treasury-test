import re
import time

import numpy as np
from rapidfuzz import fuzz

from app import ocr
from app.detail import read_small_print
from app.fields import check_bottler, check_fields
from app.models import Application, FieldResult, ImageInfo, VerifyResponse
from app.text import loose_address
from app.warning import _find_heading, _tokens, check_warning

MESSAGES = {
    "pass": "Everything checked on the label matches the application.",
    "review": "Some items need review before you decide.",
    "fail": "Some items on the label do not match the application.",
    "unreadable": "No text could be read from the image. Ask the applicant for a better image.",
}


def _reread_bottler(
    images: list[np.ndarray], lines: list[ocr.Line], result: FieldResult
) -> FieldResult:
    if result.status in ("pass", "not_checked"):
        return result
    name = loose_address(result.expected.split(",")[0])
    producer = re.compile(r"\b(?:bottled|produced|brewed|distilled|canned|imported)\b", re.I)
    candidates = [
        line
        for line in lines
        if producer.search(line.text) or fuzz.partial_ratio(name, loose_address(line.text)) >= 70
    ]
    if not candidates:
        return result
    line = max(
        candidates,
        key=lambda ln: (
            bool(producer.search(ln.text)),
            fuzz.partial_ratio(name, loose_address(ln.text)),
        ),
    )
    img = images[line.image]
    text_h = float(np.linalg.norm(line.box[3] - line.box[0]))
    pad = max(8, round(text_h))
    x0, y0 = np.floor(line.box.min(axis=0)).astype(int) - pad
    x1, y1 = np.ceil(line.box.max(axis=0)).astype(int) + pad
    region = (max(0, x0), max(0, y0), min(img.shape[1], x1), min(img.shape[0], y1))
    scale = min(3.0, max(1.5, 48 / max(text_h, 1)))
    reread = ocr.read_region(img, region, scale, pad, line.image, tight=True)
    checked = check_bottler(result.expected, reread)
    # Keep one complete reading as evidence instead of assembling an address from
    # conflicting OCR passes.
    return checked if checked.status == "pass" else result


def verify(images: list[np.ndarray], application: Application) -> VerifyResponse:
    started = time.perf_counter()
    lines: list[ocr.Line] = []
    infos = []
    for index, img in enumerate(images):
        image_lines = ocr.read_lines(img, index)
        if _find_heading(_tokens(image_lines)) is None and any(
            np.linalg.norm(line.box[3] - line.box[0]) < 40 for line in image_lines
        ):
            image_lines.extend(read_small_print(img, image_lines, index))
        lines.extend(image_lines)
        infos.append(
            ImageInfo(
                index=index,
                width=img.shape[1],
                height=img.shape[0],
                notes=ocr.quality_notes(img, image_lines),
            )
        )

    if not lines:
        return VerifyResponse(
            overall="unreadable",
            message=MESSAGES["unreadable"],
            fields=[],
            warning=None,
            images=infos,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )

    fields = check_fields(application, lines)
    fields = [
        _reread_bottler(images, lines, field) if field.key == "bottler" else field
        for field in fields
    ]
    warning_field, warning_detail = check_warning(images, lines)
    fields.append(warning_field)

    statuses = {f.status for f in fields}
    overall = "fail" if "fail" in statuses else "review" if "review" in statuses else "pass"
    return VerifyResponse(
        overall=overall,
        message=MESSAGES[overall],
        fields=fields,
        warning=warning_detail,
        images=infos,
        elapsed_ms=round((time.perf_counter() - started) * 1000),
    )
