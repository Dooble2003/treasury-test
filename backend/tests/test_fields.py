import pytest

from app.fields import (
    check_alcohol,
    check_bottler,
    check_class_type,
    check_net_contents,
    check_origin,
    match_text,
)
from app.models import Application
from app.text import fix_digits, loose_address

LABEL = (
    "OLDTOM",
    "DISTILLERY",
    "Kentucky Straight",
    "Bourbon Whiskey",
    "45% Alc./Vol. (9o Proof)",
    "750 mL",
    "Distilled and bottled by Old Tom Distillery, Bardstown, Kentucky",
)


@pytest.mark.parametrize(
    ("expected", "status"),
    [
        ("OLD TOM DISTILLERY", "pass"),
        ("Old Tom Distillery", "pass"),
        ("Kentucky Straight Bourbon Whiskey", "pass"),
        ("OLD TIM DISTILLING", "fail"),
        ("Tennessee Whiskey", "fail"),
        ("", "not_checked"),
    ],
)
def test_match_text(lines_from, expected, status):
    assert match_text("brand_name", "Brand name", expected, lines_from(*LABEL)).status == status


def test_case_difference_is_noted(lines_from):
    lines = lines_from("STONE'S THROW", "Cabernet Sauvignon")
    curly = "Stone\N{RIGHT SINGLE QUOTATION MARK}s Throw"
    result = match_text("brand_name", "Brand name", curly, lines)
    assert result.status == "pass"
    assert "capitalization" in result.note


def test_one_letter_off_needs_review(lines_from):
    result = match_text("brand_name", "Brand name", "Stone's Thr0w", lines_from("STONE'S THROW"))
    assert result.status == "review"


def test_ipa_class_matches_spelled_out_label(lines_from):
    app = Application(beverage_type="beer", class_type="IPA")
    result = check_class_type(app, lines_from("India Pale Ale"))
    assert result.status == "pass"
    assert result.expected == "IPA"
    assert result.found == "India Pale Ale"


@pytest.mark.parametrize(
    ("value", "status"),
    [
        ("45% Alc./Vol. (90 Proof)", "pass"),
        ("45", "pass"),
        ("90 Proof", "pass"),
        ("80 Proof", "fail"),
        ("40%", "fail"),
        ("", "not_checked"),
    ],
)
def test_alcohol(lines_from, value, status):
    app = Application(alcohol_content=value)
    assert check_alcohol(app, lines_from(*LABEL)).status == status


def test_proof_must_be_double_abv(lines_from):
    lines = lines_from("RIVER BEND", "45% Alc./Vol. (80 Proof)")
    result = check_alcohol(Application(alcohol_content="45%"), lines)
    assert result.status == "fail"
    assert "90 proof" in result.note


def test_percent_without_alcohol_context_is_ignored(lines_from):
    lines = lines_from("100% Agave", "40% ALC/VOL")
    assert check_alcohol(Application(alcohol_content="40%"), lines).status == "pass"


def test_a_three_digit_percent_is_not_read_as_an_abv(lines_from):
    # "100% Agave" used to contribute a 0% reading, which then became the reported
    # evidence when the real alcohol statement on the same line disagreed.
    lines = lines_from("100% Agave Tequila 40% Alc/Vol")
    result = check_alcohol(Application(alcohol_content="45%"), lines)
    assert result.status == "fail"
    assert result.note.startswith("Label says 40%")


@pytest.mark.parametrize(
    ("value", "label", "status"),
    [
        ("750 mL", "750 mL", "pass"),
        ("75 cL", "750 mL", "pass"),
        ("0.75 L", "750ML", "pass"),
        ("700 mL", "750 mL", "fail"),
        ("12 fl oz", "12 FL. OZ. (355 mL)", "pass"),
        ("355 mL", "12 FL OZ", "pass"),
        ("12", "12 FL OZ", "pass"),
    ],
)
def test_net_contents(lines_from, value, label, status):
    app = Application(beverage_type="beer" if value == "12" else "spirits", net_contents=value)
    assert check_net_contents(app, lines_from(label)).status == status


def test_bottler_accepts_state_abbreviation(lines_from):
    result = check_bottler("Old Tom Distillery, Bardstown, KY", lines_from(*LABEL))
    assert result.status == "pass"


def test_bottler_partial_match_needs_review(lines_from):
    result = check_bottler("Old Tom Distillery, Louisville, KY", lines_from(*LABEL))
    assert result.status == "review"
    assert "Louisville" in result.note


def test_fix_digits():
    assert fix_digits("45% (9o Proof)") == "45% (90 Proof)"
    assert fix_digits("Old Tom") == "Old Tom"


def test_loose_address():
    assert loose_address("Bardstown, Kentucky") == loose_address("BARDSTOWN KY")


@pytest.mark.parametrize(
    ("expected", "text", "status"),
    [
        ("India", "India Pale Ale", "review"),
        ("Mexico", "Product of Mexico", "pass"),
        ("Mexico", "Made in Mexico", "pass"),
        ("Mexico", "MEXICO", "pass"),
        ("Mexico", "Mexico Imports, Austin, TX", "review"),
        ("India", "Product of Indiana", "review"),
        ("", "India Pale Ale", "not_checked"),
    ],
)
def test_origin_requires_context(lines_from, expected, text, status):
    assert check_origin(expected, lines_from(text)).status == status
