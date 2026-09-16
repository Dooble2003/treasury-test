import base64
import difflib
import re
from dataclasses import dataclass

import cv2
import numpy as np
from rapidfuzz import fuzz

from app import ocr
from app.models import Box, DiffPart, FieldResult, Status, WarningDetail
from app.ocr import Line, Word
from app.text import clean

# 27 CFR 16.21
STATEMENT = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or operate "
    "machinery, and may cause health problems."
)
EXPECTED_WORDS = STATEMENT.split()

# Capital and small forms of these letters have the same shape, so the OCR's guess at
# their case says nothing about whether the heading is printed in capitals.
SAME_SHAPE_LETTERS = set("cijklopsuvwxz")

CONFIDENT = 0.9
# Below this share of the statement, treat the reading as too incomplete to judge.
MIN_WORDS_READ = 0.75
# Heading stroke width relative to the body text. On the eval set bold headings measured
# 1.26-1.38 and a regular-weight heading 1.04.
BOLD_RATIO = 1.15
# The recognizer works on 48 px tall text; smaller warning text is upscaled toward that.
TARGET_TEXT_HEIGHT = 48
# Under this heading height the difference between bold and regular is below a pixel.
MIN_BOLD_TEXT_HEIGHT = 20


@dataclass
class Token:
    text: str
    word: Word
    line: Line


def _key(text: str) -> str:
    return re.sub(r"\W", "", clean(text).casefold())


def _tokens(lines: list[Line]) -> list[Token]:
    tokens = []
    for line in lines:
        for word in line.words:
            if not _key(word.text):
                continue
            key = _key(word.text)
            # heading read as one word, e.g. "GOVERNMENTWARNING:"
            if key.startswith("government") and len(key) > len("government") + 3:
                cut = len("government")
                tokens.append(Token(word.text[:cut], word, line))
                tokens.append(Token(word.text[cut:], word, line))
            else:
                tokens.append(Token(word.text, word, line))
    return tokens


def _find_heading(tokens: list[Token]) -> int | None:
    for i in range(len(tokens) - 1):
        if (
            fuzz.ratio(_key(tokens[i].text), "government") >= 80
            and fuzz.ratio(_key(tokens[i + 1].text), "warning") >= 75
        ):
            return i
    return None


def _needs_reread(tokens: list[Token], heading: int | None) -> bool:
    """Whether the statement is worth reading again from a closer crop.

    This asks how much of the statement came through and how sure the recognizer was,
    not whether the words are the right ones. A label with a genuine misprint reads
    cleanly and is judged on the first pass; a garbled line reads as short fragments
    with low scores and earns another look.
    """
    if heading is None:
        return True
    span = tokens[heading : heading + len(EXPECTED_WORDS) + 15]
    if len(span) < len(EXPECTED_WORDS) * 0.95:
        return True
    return min(token.word.score for token in span[: len(EXPECTED_WORDS)]) < 0.8


def _coverage(tokens: list[Token], heading: int | None) -> float:
    """How much of the statement was read, weighted by confidence. Compares readings."""
    if heading is None:
        return 0.0
    span = tokens[heading : heading + len(EXPECTED_WORDS)]
    return sum(t.word.score for t in span) / len(EXPECTED_WORDS)


def _warning_region(lines: list[Line], tokens: list[Token], heading: int | None, shape):
    img_h, img_w = shape[:2]
    if heading is not None:
        box = tokens[heading].word.box
        text_h = float(box[:, 1].max() - box[:, 1].min())
        top = float(box[:, 1].min()) - text_h
        bottom = float(box[:, 1].min()) + text_h * 16
    else:
        weak = [line for line in lines if line.score < 0.85]
        if not weak:
            return None
        text_h = float(np.median([line.height for line in weak]))
        points = np.vstack([line.box for line in weak])
        top = float(points[:, 1].min()) - text_h * 2
        bottom = float(points[:, 1].max()) + text_h * 2

    y0, y1 = max(0, int(top)), min(img_h, int(bottom))
    nearby = [line for line in lines if line.box[:, 1].max() >= y0 and line.box[:, 1].min() <= y1]
    if nearby:
        xs = np.vstack([line.box for line in nearby])[:, 0]
        x0 = max(0, int(xs.min() - text_h * 2))
        x1 = min(img_w, int(xs.max() + text_h * 2))
    else:
        x0, x1 = 0, img_w
    return (x0, y0, x1, y1), text_h


def _align(span: list[Token]):
    expected_keys = [_key(word) for word in EXPECTED_WORDS]
    found_keys = [_key(token.text) for token in span]
    matcher = difflib.SequenceMatcher(a=expected_keys, b=found_keys, autojunk=False)
    ops = matcher.get_opcodes()
    # whatever the label prints after the statement is not part of it
    if ops and ops[-1][0] == "insert":
        ops = ops[:-1]
    if ops and ops[-1][0] == "replace":
        tag, i1, i2, j1, j2 = ops[-1]
        ops[-1] = (tag, i1, i2, j1, min(j2, j1 + (i2 - i1)))
    # The recognizer splits and joins words around punctuation, reading "WARNING: (1)"
    # as "WARNING:(1)". Spacing is not part of the required wording.
    ops = [
        ("equal", i1, i2, j1, j2)
        if tag == "replace" and "".join(expected_keys[i1:i2]) == "".join(found_keys[j1:j2])
        else (tag, i1, i2, j1, j2)
        for tag, i1, i2, j1, j2 in ops
    ]
    return ops, matcher.ratio()


def _stroke_width(gray: np.ndarray, box: np.ndarray) -> float | None:
    x0, y0 = np.floor(box.min(axis=0)).astype(int)
    x1, y1 = np.ceil(box.max(axis=0)).astype(int)
    crop = gray[max(y0, 0) : y1, max(x0, 0) : x1]
    if crop.shape[0] < 6 or crop.shape[1] < 6:
        return None
    _, binary = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = 255 - binary
    if ink.mean() > 127:  # light text on a dark background
        ink = binary
    dist = cv2.distanceTransform(ink, cv2.DIST_L2, 3)
    ridge = (dist >= cv2.dilate(dist, np.ones((3, 3), np.uint8))) & (ink > 0)
    if ridge.sum() < 5:
        return None
    return 2 * float(dist[ridge].mean()) / crop.shape[0]


def _check_bold(gray: np.ndarray, span: list[Token]) -> tuple[Status, str]:
    """Compare the heading's stroke thickness with the body text beside it.

    Returns the status and, when it is not a pass, why. Bold and regular strokes differ
    by well under a pixel on small print, so below MIN_BOLD_TEXT_HEIGHT the measurement
    is noise and the agent gets the close-up crop to judge instead.
    """
    heading_words = {id(t.word): t.word for t in span[:2]}.values()
    if min(w.box[:, 1].max() - w.box[:, 1].min() for w in heading_words) < MIN_BOLD_TEXT_HEIGHT:
        return "review", "small"

    body = [t for t in span[2:] if len(_key(t.text)) >= 3]
    same_line = [t for t in body if t.line is span[0].line][:8]
    body = same_line if len(same_line) >= 3 else body[:8]
    heading_widths = [w for w in (_stroke_width(gray, x.box) for x in heading_words) if w]
    body_widths = [w for w in (_stroke_width(gray, t.word.box) for t in body) if w]
    if not heading_widths or len(body_widths) < 3:
        return "review", "unclear"
    ratio = float(np.mean(heading_widths) / np.median(body_widths))
    return ("pass", "") if ratio >= BOLD_RATIO else ("review", "not_bold")


def _heading_crop(img: np.ndarray, span: list[Token]) -> str:
    points = np.vstack([t.word.box for t in span[:2]])
    height = points[:, 1].max() - points[:, 1].min()
    pad = int(height * 0.6)
    x0, y0 = np.floor(points.min(axis=0)).astype(int) - pad
    x1, y1 = np.ceil(points.max(axis=0)).astype(int) + pad
    crop = img[max(y0, 0) : y1, max(x0, 0) : x1]
    if crop.size == 0:
        return ""
    if crop.shape[0] > 120:
        crop = cv2.resize(crop, None, fx=120 / crop.shape[0], fy=120 / crop.shape[0])
    ok, png = cv2.imencode(".png", crop)
    return "data:image/png;base64," + base64.b64encode(png.tobytes()).decode() if ok else ""


def _fine_print_readable(images: list[np.ndarray], lines: list[Line]) -> bool:
    """Whether "no warning found" can be trusted.

    Warning text is the smallest print on a label, often a third the height of the
    alcohol statement. Below roughly 20 px per line the recognizer cannot read it at
    all, so on a small or distant image a missing warning means the image is too small,
    not that the label lacks one.
    """
    readable = [line.height for line in lines if line.score >= 0.8]
    megapixels = sum(img.shape[0] * img.shape[1] for img in images) / 1e6
    return bool(readable) and min(readable) >= 20 and megapixels >= 2


def _worst(statuses: list[Status]) -> Status:
    for status in ("fail", "review", "pass"):
        if status in statuses:
            return status
    return "not_checked"


def _read_image(img: np.ndarray, lines: list[Line], image_index: int):
    tokens = _tokens(lines)
    heading = _find_heading(tokens)
    if heading is not None and tokens[heading].line.rectified:
        return tokens, heading
    if not _needs_reread(tokens, heading):
        return tokens, heading
    region = _warning_region(lines, tokens, heading, img.shape)
    if region is None:
        return tokens, heading

    box, text_h = region
    base = min(3.0, max(1.0, TARGET_TEXT_HEIGHT / max(text_h, 1.0)))
    # The detector sometimes merges tightly spaced lines of small print, and whether it
    # does depends on scale in no predictable way. Try a few scales and keep the most
    # complete, confident reading. The stopping rule only looks at confidence and word
    # count, never at the wording, so a real misprint still ends the search.
    best = (tokens, heading, _coverage(tokens, heading))
    tight = False
    if heading is not None:
        edge = tokens[heading].line.box[1] - tokens[heading].line.box[0]
        tight = abs(float(np.degrees(np.arctan2(edge[1], edge[0])))) > 2
    for scale in dict.fromkeys(min(s, 3.5) for s in (base * 1.5, base * 2, base)):
        reread = _tokens(ocr.read_region(img, box, scale, int(text_h), image_index, tight=tight))
        reread_heading = _find_heading(reread)
        coverage = _coverage(reread, reread_heading)
        if coverage > best[2]:
            best = (reread, reread_heading, coverage)
        if reread_heading is not None and not _needs_reread(reread, reread_heading):
            break
    return best[0], best[1]


def check_warning(
    images: list[np.ndarray], lines: list[Line]
) -> tuple[FieldResult, WarningDetail | None]:
    result = FieldResult(
        key="government_warning", label="Government warning", status="fail", expected=STATEMENT
    )

    best = None
    for index, img in enumerate(images):
        tokens, heading = _read_image(img, [line for line in lines if line.image == index], index)
        if heading is None:
            continue
        span = tokens[heading : heading + len(EXPECTED_WORDS) + 15]
        ops, ratio = _align(span)
        if best is None or ratio > best[0]:
            best = (ratio, img, span, ops)

    if best is None:
        if _fine_print_readable(images, lines):
            result.note = (
                "The government warning was not found. If it is on another part of the label, "
                "add that image too."
            )
        else:
            result.status = "review"
            result.note = (
                "Could not read enough text to locate and verify the government warning. "
                "If it is visible, add a close-up of that area. If it is on another panel, "
                "add that image too."
            )
        return result, None

    _, img, span, ops = best
    used = span[: ops[-1][4]] if ops else span
    diff: list[DiffPart] = []
    wording: list[Status] = ["pass"]
    punctuation_differs = False

    for tag, i1, i2, j1, j2 in ops:
        expected = " ".join(EXPECTED_WORDS[i1:i2])
        found_tokens = span[j1:j2]
        found = " ".join(t.text for t in found_tokens)
        if tag == "equal":
            diff.append(DiffPart(kind="same", expected=expected, found=found))
            if i2 - i1 == j2 - j1:  # a spacing difference pairs a different number of words
                for exp_word, token in zip(EXPECTED_WORDS[i1:i2], found_tokens, strict=True):
                    if (
                        token.word.score >= 0.95
                        and clean(token.text).casefold() != exp_word.casefold()
                    ):
                        punctuation_differs = True
            continue
        kind = {"replace": "changed", "delete": "missing", "insert": "extra"}[tag]
        diff.append(DiffPart(kind=kind, expected=expected, found=found))
        if tag == "delete":
            # Words missing from the end usually mean the reading stopped early (a crop
            # edge, a curved bottle). Words missing between two confidently read words
            # are missing from the label.
            neighbours = span[max(j1 - 1, 0) : j1 + 1]
            confident = j1 < len(span) and all(t.word.score >= CONFIDENT for t in neighbours)
        else:
            confident = min(t.word.score for t in found_tokens) >= CONFIDENT
        wording.append("fail" if confident else "review")

    heading = span[:2]
    caps: Status = "pass"
    for token in heading:
        distinct = [c for c in token.text if c.isalpha() and c.lower() not in SAME_SHAPE_LETTERS]
        if any(c.islower() for c in distinct):
            caps = _worst([caps, "fail" if token.word.score >= 0.8 else "review"])

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bold, bold_reason = _check_bold(gray, span)
    notes = []

    # On print this small the recognizer confuses shapes (it read "ALCOHOLIC" as
    # "ALCOHDLIC" on a 13 px line), so an odd word says more about the image than the
    # label. The same test decides whether "not found" can be trusted.
    small_print = not _fine_print_readable(images, lines) and "fail" in wording
    if small_print:
        notes.append(
            "The print on this image is small, so a difference may be a misreading rather "
            "than a misprint. Check it by eye or ask for a clearer image."
        )
        wording = ["review" if status == "fail" else status for status in wording]

    # Too little of the statement came through to call anything a mismatch, unless a
    # difference is backed by confidently read words on both sides.
    matched_words = sum(i2 - i1 for tag, i1, i2, _, _ in ops if tag == "equal")
    partial = matched_words < len(EXPECTED_WORDS) * MIN_WORDS_READ and "fail" not in wording
    wording_status = _worst(wording + (["review"] if punctuation_differs else []))

    if partial:
        notes.append(
            "Only part of the warning could be read on this image. Check it by eye or "
            "ask for a clearer image."
        )
        wording_status = "review"
    if caps == "fail":
        notes.append('"GOVERNMENT WARNING" is not in capital letters.')
    elif caps == "review":
        notes.append('Could not confirm "GOVERNMENT WARNING" is in capital letters.')
    if "fail" in wording and not partial:
        notes.append("The wording does not match the required statement.")
    elif "review" in wording and not partial and not small_print:
        notes.append("Some words were hard to read. Compare the marked words with the label.")
    if punctuation_differs and "fail" not in wording:
        notes.append("Punctuation differs from the required statement.")
    if bold_reason == "small":
        notes.append(
            'The print is too small to measure whether "GOVERNMENT WARNING" is in bold. '
            "Check the close-up below."
        )
    elif bold != "pass":
        notes.append('Could not confirm "GOVERNMENT WARNING" is in bold. Check the close-up below.')

    unique_lines = list({id(t.line): t.line for t in used}.values())
    result.status = _worst([caps, bold, wording_status])
    result.found = " ".join(t.text for t in used)
    result.note = " ".join(notes)
    result.boxes = [Box(image=line.image, points=line.box.tolist()) for line in unique_lines]
    detail = WarningDetail(
        heading_caps=caps,
        heading_bold=bold,
        wording=wording_status,
        diff=diff,
        heading_crop=_heading_crop(img, span),
    )
    return result, detail
