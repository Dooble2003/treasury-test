from pathlib import Path

import cv2
import pytest

from app import ocr
from app.detail import read_small_print

EVAL_LABELS = Path(__file__).resolve().parents[2] / "eval" / "labels"

pytestmark = pytest.mark.skipif(not EVAL_LABELS.exists(), reason="eval labels not generated")


def recovered_text(filename: str, scale: float = 0.45) -> str:
    """Read a label small enough that the first pass misses its fine print."""
    img = ocr.load_image((EVAL_LABELS / filename).read_bytes())
    small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    lines = read_small_print(small, ocr.read_lines(small), 0)
    return " ".join(line.text for line in lines)


def test_recovers_small_print_the_first_pass_missed():
    text = recovered_text("bourbon_ok.jpg")
    assert "GOVERNMENT WARNING" in text
    assert "Bardstown" in text
    assert "health problems" in text


@pytest.mark.parametrize(
    ("filename", "printed", "correct"),
    [
        ("bourbon_typo.jpg", "pregnacy", "pregnancy"),
        ("bourbon_title_case.jpg", "Government Warning", "GOVERNMENT WARNING"),
    ],
)
def test_straightening_does_not_repair_a_defect(filename, printed, correct):
    # Rebuilding a curved line must report what the label says, not what it should say.
    text = recovered_text(filename)
    assert printed in text
    assert correct not in text


def test_missing_word_stays_missing():
    text = recovered_text("bourbon_missing_word.jpg")
    assert "risk of defects" in text
    assert "risk of birth defects" not in text
