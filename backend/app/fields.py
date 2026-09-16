import re
from collections.abc import Callable, Iterator

from rapidfuzz import fuzz

from app.models import Application, Box, FieldResult
from app.ocr import Line
from app.text import clean, fix_digits, loose, loose_address

CLOSE_MATCH = 90

# The lookbehind keeps the tail of a longer number out of the reading, so "100% Agave"
# on the alcohol line does not come back as 0%.
ABV_RE = re.compile(r"(?<!\d)(\d{1,2}(?:[.,]\d{1,2})?)\s*%")
PROOF_RE = re.compile(r"(\d{2,3}(?:[.,]\d)?)\s*proof", re.IGNORECASE)
ALCOHOL_CONTEXT_RE = re.compile(r"alc|vol|abv|alcohol", re.IGNORECASE)
VOLUME_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(ml|millilit(?:er|re)s?|cl|centilit(?:er|re)s?|l|lit(?:er|re)s?"
    r"|fl\.?\s*oz|fluid\s+ounces?|oz)(?![a-z])",
    re.IGNORECASE,
)
ML_PER_UNIT = {"ml": 1.0, "cl": 10.0, "l": 1000.0, "oz": 29.5735}


def _boxes(lines: list[Line]) -> list[Box]:
    return [Box(image=line.image, points=line.box.tolist()) for line in lines]


def _spans(lines: list[Line], max_len: int = 3) -> Iterator[list[Line]]:
    for size in range(1, max_len + 1):
        for i in range(len(lines) - size + 1):
            span = lines[i : i + size]
            if all(line.image == span[0].image for line in span):
                yield span


def _contains(haystack: str, needle: str) -> bool:
    if f" {needle} " in f" {haystack} ":
        return True
    # OCR sometimes drops the space between large display words ("OLDTOM")
    squashed = needle.replace(" ", "")
    return len(squashed) >= 6 and squashed in haystack.replace(" ", "")


def _tightest(spans: list[list[Line]], normalize: Callable[[str], str]) -> list[Line]:
    """Prefer the span with the least extra text, so a brand name points at the big
    display text rather than the "Bottled by ..." line that also mentions it."""
    return min(spans, key=lambda s: (len(normalize(" ".join(ln.text for ln in s))), len(s)))


def _letters(text: str) -> str:
    return re.sub(r"[^\w]", "", clean(text))


def match_text(
    key: str,
    label: str,
    expected: str,
    lines: list[Line],
    normalize: Callable[[str], str] = loose,
) -> FieldResult:
    result = FieldResult(key=key, label=label, status="not_checked", expected=expected.strip())
    if not result.expected:
        result.note = "Not provided in the application."
        return result

    target = normalize(expected)
    matches = []
    best_score, best_span = 0.0, None
    for span in _spans(lines):
        candidate = normalize(" ".join(line.text for line in span))
        if _contains(candidate, target):
            matches.append(span)
            continue
        score = fuzz.partial_ratio(target, candidate)
        if score > best_score:
            best_score, best_span = score, span

    if matches:
        span = _tightest(matches, normalize)
        text = " ".join(line.text for line in span)
        result.status = "pass"
        result.found = text
        result.boxes = _boxes(span)
        if _letters(expected) not in _letters(text):
            result.note = "Same words, but the capitalization is different."
        return result

    if best_span and best_score >= CLOSE_MATCH:
        result.status = "review"
        result.found = " ".join(line.text for line in best_span)
        result.boxes = _boxes(best_span)
        result.note = "Close but not an exact match. Check the label for a small difference."
    else:
        result.status = "fail"
        result.note = "Not found on the label."
    return result


def check_bottler(expected: str, lines: list[Line]) -> FieldResult:
    key, label = "bottler", "Bottler or producer"
    parts = [p.strip() for p in expected.split(",") if p.strip()]
    if not parts:
        return match_text(key, label, expected, lines)

    # Name and address usually sit together; only fall back to finding parts separately.
    together = [
        span
        for span in _spans(lines)
        if all(
            _contains(loose_address(" ".join(ln.text for ln in span)), loose_address(p))
            for p in parts
        )
    ]
    if together:
        span = _tightest(together, loose_address)
        return FieldResult(
            key=key,
            label=label,
            status="pass",
            expected=expected.strip(),
            found=" ".join(line.text for line in span),
            boxes=_boxes(span),
        )

    results = [match_text(key, label, part, lines, loose_address) for part in parts]
    statuses = {r.status for r in results}
    # Show only the lines that actually matched a part. A loose match on "Napa" against
    # "Napa Valley" in the brand block is not evidence of the bottler's address.
    matched = [r for r in results if r.status == "pass"]
    if len(matched) * 2 < len(parts):
        matched = []
    result = FieldResult(
        key=key,
        label=label,
        status="pass",
        expected=expected.strip(),
        found=" / ".join(dict.fromkeys(r.found for r in matched)),
        boxes=[box for r in matched for box in r.boxes],
    )
    if statuses == {"pass"}:
        return result
    if statuses == {"fail"}:
        result.status, result.note = "fail", "Not found on the label."
        return result
    missing = [p for p, r in zip(parts, results, strict=True) if r.status != "pass"]
    result.status = "review"
    result.note = "Could not confirm: " + ", ".join(missing) + "."
    return result


def _parse_number(text: str) -> float:
    return float(text.replace(",", "."))


def _alcohol_lines(lines: list[Line]) -> list[tuple[Line, str]]:
    return [(line, fix_digits(clean(line.text))) for line in lines]


def check_alcohol(app: Application, lines: list[Line]) -> FieldResult:
    result = FieldResult(
        key="alcohol_content",
        label="Alcohol content",
        status="not_checked",
        expected=app.alcohol_content.strip(),
    )
    if not result.expected:
        result.note = "Not provided in the application."
        return result

    app_text = fix_digits(result.expected)
    if percent := ABV_RE.search(app_text):
        app_abv = _parse_number(percent.group(1))
    elif proof := PROOF_RE.search(app_text):
        # Some applications state the strength only as proof, which is twice the ABV.
        app_abv = _parse_number(proof.group(1)) / 2
    elif bare := re.search(r"\d{1,2}(?:[.,]\d{1,2})?", app_text):
        app_abv = _parse_number(bare[0])
    else:
        result.status = "review"
        result.note = "Could not read a percentage in the application value."
        return result

    readings: list[tuple[float, Line, str]] = []
    for line, text in _alcohol_lines(lines):
        if not ALCOHOL_CONTEXT_RE.search(text):
            continue
        for m in ABV_RE.finditer(text):
            readings.append((_parse_number(m.group(1)), line, text))

    if not readings:
        result.status = "fail"
        result.note = "No alcohol content statement found on the label."
        return result

    matching = [r for r in readings if abs(r[0] - app_abv) < 0.01]
    abv, line, text = (matching or readings)[0]
    result.found = line.text
    result.boxes = _boxes([line])
    if not matching:
        result.status = "fail"
        result.note = f"Label says {abv:g}%, application says {app_abv:g}%."
        return result

    proof_match = PROOF_RE.search(text)
    if proof_match:
        proof = _parse_number(proof_match.group(1))
        if abs(proof - 2 * abv) > 0.5:
            result.status = "fail"
            result.note = (
                f"Label shows {proof:g} proof, which does not match {abv:g}% "
                f"(should be {2 * abv:g} proof)."
            )
            return result
    result.status = "pass"
    return result


def _volume_ml(value: str, unit: str) -> float:
    if re.fullmatch(r"\d{1,3},\d{3}", value):
        value = value.replace(",", "")
    unit = unit.lower().replace(".", "").replace(" ", "")
    if unit.startswith(("fl", "fluid", "oz")):
        key = "oz"
    elif unit.startswith(("ml", "milli")):
        key = "ml"
    elif unit.startswith(("cl", "centi")):
        key = "cl"
    else:
        key = "l"
    return _parse_number(value) * ML_PER_UNIT[key]


def check_net_contents(app: Application, lines: list[Line]) -> FieldResult:
    result = FieldResult(
        key="net_contents",
        label="Net contents",
        status="not_checked",
        expected=app.net_contents.strip(),
    )
    if not result.expected:
        result.note = "Not provided in the application."
        return result

    app_text = fix_digits(result.expected)
    m = VOLUME_RE.search(app_text)
    if m:
        app_ml = _volume_ml(m.group(1), m.group(2))
    elif bare := re.search(r"\d+(?:[.,]\d+)?", app_text):
        app_ml = _volume_ml(bare[0], "oz" if app.beverage_type == "beer" else "ml")
    else:
        result.status = "review"
        result.note = "Could not read a volume in the application value."
        return result

    readings = []
    for line, text in _alcohol_lines(lines):
        for vm in VOLUME_RE.finditer(text):
            readings.append((_volume_ml(vm.group(1), vm.group(2)), line))

    if not readings:
        result.status = "fail"
        result.note = "No net contents statement found on the label."
        return result

    matching = [r for r in readings if abs(r[0] - app_ml) <= app_ml * 0.015]
    ml, line = (matching or readings)[0]
    result.found = line.text
    result.boxes = _boxes([line])
    if matching:
        result.status = "pass"
    else:
        result.status = "fail"
        result.note = f"Label says about {ml:g} mL, application says about {app_ml:g} mL."
    return result


def check_origin(expected: str, lines: list[Line]) -> FieldResult:
    result = match_text("country_of_origin", "Country of origin", expected, lines)
    if result.status != "pass":
        return result
    country = loose(expected)
    origin_lines = [
        line
        for line in lines
        if loose(line.text) == country
        or re.search(
            r"\b(?:product of|made in|produced in|brewed in|distilled in|imported from|"
            r"country of origin)\s+" + re.escape(country) + r"\b",
            loose(line.text),
        )
    ]
    confirmed = match_text("country_of_origin", "Country of origin", expected, origin_lines)
    if confirmed.status == "pass":
        return confirmed
    result.status = "review"
    result.note = "The country name appears, but could not be confirmed as the country of origin."
    return result


def check_class_type(app: Application, lines: list[Line]) -> FieldResult:
    result = match_text("class_type", "Class or type", app.class_type, lines)
    if result.status == "pass":
        return result

    # Beer applications commonly use the standard abbreviation while the label
    # spells the style out. Treat those two forms as the same class or type.
    if app.beverage_type == "beer" and loose(app.class_type) == "ipa":
        expanded = match_text("class_type", "Class or type", "India Pale Ale", lines)
        if expanded.status == "pass":
            expanded.expected = app.class_type.strip()
            return expanded
    return result


def check_fields(app: Application, lines: list[Line]) -> list[FieldResult]:
    return [
        match_text("brand_name", "Brand name", app.brand_name, lines),
        check_class_type(app, lines),
        check_alcohol(app, lines),
        check_net_contents(app, lines),
        check_bottler(app.bottler, lines),
        check_origin(app.country_of_origin, lines),
    ]
