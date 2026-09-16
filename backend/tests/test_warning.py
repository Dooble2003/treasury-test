from pathlib import Path

import numpy as np
import pytest

from app.warning import STATEMENT, _align, _find_heading, _needs_reread, _tokens, check_warning
from tests.conftest import make_line

EVAL_LABELS = Path(__file__).resolve().parents[2] / "eval" / "labels"


def statement_lines(text: str = STATEMENT, score: float = 0.99):
    words = text.split()
    chunks = [" ".join(words[i : i + 12]) for i in range(0, len(words), 12)]
    return [make_line(chunk, score=score, y=i * 30) for i, chunk in enumerate(chunks)]


def blank_image(width: int = 1600, height: int = 2400):
    return np.full((height, width, 3), 255, np.uint8)


def diff_kinds(text, score=0.99):
    tokens = _tokens(statement_lines(text, score))
    heading = _find_heading(tokens)
    ops, _ = _align(tokens[heading:])
    return [op[0] for op in ops if op[0] != "equal"]


def test_exact_statement_aligns():
    assert diff_kinds(STATEMENT) == []


def test_typo_is_a_change():
    assert diff_kinds(STATEMENT.replace("pregnancy", "pregnacy")) == ["replace"]


def test_missing_word_is_detected():
    assert diff_kinds(STATEMENT.replace("birth ", "")) == ["delete"]


def test_text_after_statement_is_ignored():
    assert diff_kinds(STATEMENT + " Bottled in Kentucky 750 mL") == []


def test_heading_read_as_one_word():
    text = STATEMENT.replace("GOVERNMENT WARNING:", "GOVERNMENTWARNING:")
    assert _find_heading(_tokens(statement_lines(text))) == 0


def test_title_case_heading_fails():
    lines = statement_lines(STATEMENT.replace("GOVERNMENT WARNING", "Government Warning"))
    result, detail = check_warning([blank_image()], lines)
    assert detail.heading_caps == "fail"
    assert result.status == "fail"


def test_ocr_case_noise_on_same_shape_letters_is_ignored():
    lines = statement_lines(STATEMENT.replace("GOVERNMENT WARNING", "GovERNMENT wARNING"))
    _, detail = check_warning([blank_image()], lines)
    assert detail.heading_caps == "pass"


def test_confident_typo_fails_but_unsure_read_needs_review():
    typo = STATEMENT.replace("pregnancy", "pregnacy")
    _, confident = check_warning([blank_image()], statement_lines(typo, score=0.99))
    _, unsure = check_warning([blank_image()], statement_lines(typo, score=0.7))
    assert confident.wording == "fail"
    assert unsure.wording == "review"


def test_missing_warning():
    result, detail = check_warning([blank_image()], [make_line("OLD TOM DISTILLERY")])
    assert result.status == "fail"
    assert detail is None


def test_missing_warning_on_a_small_image_is_not_a_failure():
    # A 0.5 megapixel photo cannot show warning text at a readable size, so "not found"
    # says more about the image than about the label.
    result, _ = check_warning([blank_image(600, 800)], [make_line("OLD TOM DISTILLERY")])
    assert result.status == "review"
    assert "Could not read enough text" in result.note


def test_partly_read_warning_is_not_a_mismatch():
    half = " ".join(STATEMENT.split()[:20])
    result, detail = check_warning([blank_image()], statement_lines(half))
    assert result.status == "review"
    assert detail.wording == "review"
    assert "Only part of the warning" in result.note


@pytest.mark.skipif(not EVAL_LABELS.exists(), reason="eval labels not generated")
@pytest.mark.parametrize(
    ("filename", "caps", "bold", "wording"),
    [
        ("bourbon_ok.jpg", "pass", "pass", "pass"),
        ("bourbon_title_case.jpg", "fail", "pass", "pass"),
        ("bourbon_not_bold.jpg", "pass", "review", "pass"),
        ("bourbon_typo.jpg", "pass", "pass", "fail"),
    ],
)
def test_real_labels(filename, caps, bold, wording):
    from app.ocr import load_image, read_lines

    img = load_image((EVAL_LABELS / filename).read_bytes())
    _, detail = check_warning([img], read_lines(img))
    assert (detail.heading_caps, detail.heading_bold, detail.wording) == (caps, bold, wording)


def test_spacing_difference_is_not_a_wording_change():
    # OCR reads "WARNING: (1)" as one word on tightly set labels
    assert diff_kinds(STATEMENT.replace("WARNING: (1)", "WARNING:(1)")) == []


def test_joined_words_are_not_a_wording_change():
    assert diff_kinds(STATEMENT.replace("health problems", "healthproblems")) == []


def test_small_heading_is_not_judged_for_bold():
    lines = [make_line(chunk, y=i * 30) for i, chunk in enumerate(STATEMENT.split(". "))]
    _, detail = check_warning([blank_image()], lines)
    # conftest lines are 20 px tall, right at the limit where stroke width stops meaning anything
    assert detail.heading_bold == "review"


@pytest.mark.parametrize(
    ("text", "score", "retry"),
    [
        (STATEMENT, 0.99, False),
        (STATEMENT.replace("pregnancy", "pregnacy"), 0.99, False),
        (STATEMENT.replace("birth defects", "other reasons"), 0.99, False),
        (STATEMENT.replace("birth ", ""), 0.99, False),
        (STATEMENT, 0.7, True),
        (" ".join(STATEMENT.split()[:20]), 0.99, True),
    ],
)
def test_retry_uses_reading_quality(text, score, retry):
    tokens = _tokens(statement_lines(text, score))
    assert _needs_reread(tokens, _find_heading(tokens)) is retry
