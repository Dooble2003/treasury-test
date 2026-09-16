import cv2
import numpy as np

from app import ocr
from app.ocr import Line


def _height(line: Line) -> float:
    return float(np.linalg.norm(line.box[3] - line.box[0]))


def _center_y(line: Line, x: float) -> float:
    left = (line.box[0] + line.box[3]) / 2
    right = (line.box[1] + line.box[2]) / 2
    return float(left[1] + (x - left[0]) * (right[1] - left[1]) / max(right[0] - left[0], 1))


def _seam(img: np.ndarray, left: Line, right: Line) -> float:
    lo = max(left.box[:, 0].min(), right.box[:, 0].min())
    hi = min(left.box[:, 0].max(), right.box[:, 0].max())
    margin = (hi - lo) * 0.2
    xs = np.arange(int(lo + margin), int(hi - margin) + 1)
    half = max(2, round(min(_height(left), _height(right)) / 2))
    centers = np.array([(_center_y(left, x) + _center_y(right, x)) / 2 for x in xs])
    ys = np.rint(centers + np.arange(-half, half + 1)[:, None]).astype(int)
    samples = img[np.clip(ys, 0, img.shape[0] - 1), np.clip(xs, 0, img.shape[1] - 1)]
    gray = cv2.cvtColor(samples, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ink = mask < 128 if np.mean(mask) > 127 else mask > 128
    counts = ink.sum(axis=0)
    candidates = xs[counts == counts.min()]
    return float(min(candidates, key=lambda x: abs(x - (lo + hi) / 2)))


def _join_curve(img: np.ndarray, group: list[Line], image_index: int) -> list[Line]:
    pieces, transforms = [], []
    offset = 0
    # Join in the gaps between letters so small alignment errors do not cut strokes.
    seams = [_seam(img, left, right) for left, right in zip(group, group[1:], strict=False)]
    for i, line in enumerate(group):
        x0, x1 = line.box[:, 0].min(), line.box[:, 0].max()
        if i:
            x0 = seams[i - 1]
        if i + 1 < len(group):
            x1 = seams[i]
        height = _height(line) + 4
        y0, y1 = _center_y(line, x0), _center_y(line, x1)
        source = np.float32(
            [
                [x0, y0 - height / 2],
                [x1, y1 - height / 2],
                [x1, y1 + height / 2],
                [x0, y0 + height / 2],
            ]
        )
        width = max(1, round((x1 - x0) * 48 / height))
        target = np.float32([[0, 0], [width, 0], [width, 48], [0, 48]])
        matrix = cv2.getPerspectiveTransform(source, target)
        pieces.append(cv2.warpPerspective(img, matrix, (width, 48)))
        transforms.append((offset, offset + width, cv2.getPerspectiveTransform(target, source)))
        offset += width

    strip = np.concatenate(pieces, axis=1)
    reread = ocr.read_strip(strip, image_index)
    for line in reread:
        for item in [line, *line.words]:
            points = []
            for x, y in item.box:
                start, _, inverse = next(
                    (part for part in transforms if x < part[1]), transforms[-1]
                )
                point = cv2.perspectiveTransform(np.float32([[[x - start, y]]]), inverse)[0, 0]
                points.append(point)
            item.box = np.asarray(points, dtype=float)
    return reread


def read_small_print(img: np.ndarray, lines: list[Line], image_index: int) -> list[Line]:
    if not lines:
        return []
    heights = [_height(line) for line in lines]
    smallest = min(heights)
    small = [line for line, height in zip(lines, heights, strict=True) if height <= smallest * 2]
    text_h = float(np.median([_height(line) for line in small]))
    points = np.vstack([line.box for line in small])
    pad = max(12, round(text_h * 3))
    x0, y0 = np.floor(points.min(axis=0)).astype(int) - [round(text_h * 2), pad]
    x1, y1 = np.ceil(points.max(axis=0)).astype(int) + [round(text_h * 2), pad]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(img.shape[1], x1), min(img.shape[0], y1)
    # Three overlapping strips keep local baselines nearly straight without needing
    # a bottle outline or assuming that the warning is at the bottom of the image.
    width = x1 - x0
    tile_width = round(max(width * 0.4, min(width / 2, text_h * 7)))
    scale = min(3, max(1.5, 72 / max(text_h, 1)))
    groups: list[list[Line]] = []
    complete = set()
    for start in (x0, x0 + round((width - tile_width) / 2), x1 - tile_width):
        tile = ocr.read_region(
            img, (start, y0, start + tile_width, y1), scale, 12, image_index, tight=True
        )
        previous = list(groups)
        used = set()
        for line in tile:
            if (
                line.box[:, 0].min() > start + 3
                and line.box[:, 0].max() < start + tile_width - 3
                and line.score >= 0.85
            ):
                complete.add(id(line))
            matches = []
            for index, group in enumerate(previous):
                if index in used:
                    continue
                last = group[-1]
                lo = max(last.box[:, 0].min(), line.box[:, 0].min())
                hi = min(last.box[:, 0].max(), line.box[:, 0].max())
                if hi - lo < min(_height(last), _height(line)):
                    continue
                x = (lo + hi) / 2
                distance = abs(_center_y(last, x) - _center_y(line, x))
                if distance < min(_height(last), _height(line)) * 0.6:
                    matches.append((distance, index))
            if matches:
                _, index = min(matches)
                previous[index].append(line)
                used.add(index)
            else:
                groups.append([line])

    recovered = []
    for group in sorted(groups, key=lambda g: _center_y(g[0], g[0].box[:, 0].min())):
        if len(group) > 1:
            recovered.extend(_join_curve(img, group, image_index))
        elif id(group[0]) in complete:
            recovered.extend(group)
    for line in recovered:
        line.rectified = True
    return recovered
