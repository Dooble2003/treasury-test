from pathlib import Path

import numpy as np
import pytest

from app import ocr
from app.fields import check_bottler
from app.models import Application
from app.verify import _reread_bottler, verify

SAMPLES = Path(__file__).resolve().parents[2] / "frontend/public/samples"


@pytest.mark.parametrize(
    ("reading", "status"),
    [
        ("Brewed by Harbor Light Brewing Co., Portland, Maine", "pass"),
        ("Brewed by Harbor Light Brewing Co., Portland, Oregon", "review"),
        ("Brewed by Harbor Light Brewing Co., Portand, Maine", "review"),
        ("", "review"),
    ],
)
def test_producer_crop_must_confirm_the_whole_address(monkeypatch, lines_from, reading, status):
    lines = lines_from(
        "HARBOR LIGHT BREWING",
        "Brewed by Harbor Light Brewin Co., Portand, Maine",
    )
    initial = check_bottler("Harbor Light Brewing Co., Portland, Maine", lines)
    calls = []

    def read_region(img, region, scale, pad, image_index, **kwargs):
        calls.append(region)
        return lines_from(reading) if reading else []

    monkeypatch.setattr(ocr, "read_region", read_region)
    image = np.zeros((200, 1000, 3), dtype=np.uint8)
    result = _reread_bottler([image], lines, initial)
    assert result.status == status
    assert len(calls) == 1
    assert calls[0][1] == 10


def test_confirmed_producer_does_not_need_another_read(monkeypatch, lines_from):
    lines = lines_from("Brewed by Harbor Light Brewing Co., Portland, Maine")
    result = check_bottler("Harbor Light Brewing Co., Portland, Maine", lines)

    def unexpected_read(*args, **kwargs):
        pytest.fail("Confirmed producer should not trigger OCR")

    monkeypatch.setattr(ocr, "read_region", unexpected_read)
    assert _reread_bottler([], lines, result) is result


def test_can_photo_small_print():
    path = Path(__file__).resolve().parents[2] / "eval/labels/ipa_photo_can_ok.jpg"
    image = ocr.load_image(path.read_bytes())
    result = verify(
        [image],
        Application(
            beverage_type="beer",
            bottler="Harbor Light Brewing Co., Portland, Maine",
            country_of_origin="India",
        ),
    )
    fields = {field.key: field for field in result.fields}
    assert fields["bottler"].status == "pass"
    assert "Portland" in fields["bottler"].found
    assert fields["government_warning"].status == "pass"
    assert result.warning.wording == "pass"
    assert fields["country_of_origin"].status == "review"
    for key in ("bottler", "government_warning"):
        for box in fields[key].boxes:
            assert box.image == 0
            assert all(0 <= x <= image.shape[1] and 0 <= y <= image.shape[0] for x, y in box.points)


def test_ipa_example_needs_review():
    image = ocr.load_image((SAMPLES / "ipa_front_label.png").read_bytes())
    result = verify(
        [image],
        Application(
            beverage_type="beer",
            brand_name="Harbor Light",
            class_type="IPA",
            alcohol_content="6.8",
            net_contents="12",
            bottler="Harbor Light Co.",
            country_of_origin="India",
        ),
    )
    statuses = {field.key: field.status for field in result.fields}
    assert result.overall == "review"
    assert statuses["class_type"] == "pass"
    assert statuses["bottler"] == "review"
    assert statuses["country_of_origin"] == "review"


def test_blurry_example_asks_for_a_better_image():
    image = ocr.load_image((SAMPLES / "ipa_too_blurry.jpg").read_bytes())
    result = verify([image], Application())
    assert result.overall == "unreadable"
    assert "better image" in result.message
