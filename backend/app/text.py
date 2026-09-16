import re
import unicodedata

_PUNCT_MAP = str.maketrans(
    {
        "\N{LEFT SINGLE QUOTATION MARK}": "'",
        "\N{RIGHT SINGLE QUOTATION MARK}": "'",
        "\N{LEFT DOUBLE QUOTATION MARK}": '"',
        "\N{RIGHT DOUBLE QUOTATION MARK}": '"',
        "\N{EN DASH}": "-",
        "\N{EM DASH}": "-",
    }
)

US_STATES = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar", "california": "ca",
    "colorado": "co", "connecticut": "ct", "delaware": "de", "florida": "fl", "georgia": "ga",
    "hawaii": "hi", "idaho": "id", "illinois": "il", "indiana": "in", "iowa": "ia",
    "kansas": "ks", "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms",
    "missouri": "mo", "montana": "mt", "nebraska": "ne", "nevada": "nv", "new hampshire": "nh",
    "new jersey": "nj", "new mexico": "nm", "new york": "ny", "north carolina": "nc",
    "north dakota": "nd", "ohio": "oh", "oklahoma": "ok", "oregon": "or", "pennsylvania": "pa",
    "rhode island": "ri", "south carolina": "sc", "south dakota": "sd", "tennessee": "tn",
    "texas": "tx", "utah": "ut", "vermont": "vt", "virginia": "va", "washington": "wa",
    "west virginia": "wv", "wisconsin": "wi", "wyoming": "wy",
}  # fmt: skip

_STATE_RE = re.compile(r"\b(" + "|".join(sorted(US_STATES, key=len, reverse=True)) + r")\b")


def clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_PUNCT_MAP)
    return " ".join(text.split())


def loose(text: str) -> str:
    """Case, punctuation and spacing insensitive form used for lenient matching."""
    text = clean(text).casefold().replace("'", "")
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def loose_address(text: str) -> str:
    return _STATE_RE.sub(lambda m: US_STATES[m.group(1)], loose(text))


def fix_digits(text: str) -> str:
    """Undo common OCR letter-for-digit swaps inside numbers, e.g. "9o Proof"."""

    def repl(m: re.Match) -> str:
        return m.group(0).translate(str.maketrans("oOlI", "0011"))

    return re.sub(r"(?<=\d)[oOlI]+|[oOlI]+(?=\d)", repl, text)
