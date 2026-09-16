import numpy as np
import pytest

from app.ocr import Line, Word


def make_line(text: str, score: float = 0.99, image: int = 0, y: float = 0) -> Line:
    words, x = [], 0.0
    for part in text.split():
        width = 12.0 * len(part)
        box = np.array([[x, y], [x + width, y], [x + width, y + 20], [x, y + 20]])
        words.append(Word(part, score, box))
        x += width + 8
    box = np.array([[0, y], [x, y], [x, y + 20], [0, y + 20]], dtype=float)
    return Line(text, score, box, image, words)


@pytest.fixture
def lines_from():
    def build(*texts: str) -> list[Line]:
        return [make_line(t, y=i * 30) for i, t in enumerate(texts)]

    return build
