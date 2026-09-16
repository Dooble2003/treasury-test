from pathlib import Path

import numpy as np
import pytest

from app import ocr
from app.fields import check_bottler
from app.models import Application
from app.verify import _reread_bottler, verify


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
