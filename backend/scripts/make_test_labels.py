"""Build the evaluation label set in eval/.

Artwork in eval/source/ was generated with ChatGPT and leaves an empty band where the
warning goes. The warning is drawn in here so every defect variant is exact. A few
plain labels are drawn entirely in code for cases the artwork can't cover.

Run from backend/:  uv run python scripts/make_test_labels.py
"""

import csv
import random
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.warning import STATEMENT  # noqa: E402

ROOT = Path(__file__).resolve().parents[2] / "eval"
SOURCE = ROOT / "source"
LABELS = ROOT / "labels"
SAMPLES = ROOT.parent / "frontend" / "public" / "samples"
# Cases that only differ from bourbon_ok in the application data add little to the demo.
BATCH_SKIP = {"bourbon_net_cl", "bourbon_wrong_brand", "ipa_photo_can_ok"}
APPLICATION_COLUMNS = [
    "beverage_type",
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "bottler",
    "country_of_origin",
]

FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu")]
FONT_FILES = {
    "regular": ["arial.ttf", "DejaVuSans.ttf"],
    "bold": ["arialbd.ttf", "DejaVuSans-Bold.ttf"],
}
SERIF_FILES = {
    "regular": ["georgia.ttf", "DejaVuSerif.ttf"],
    "bold": ["georgiab.ttf", "DejaVuSerif-Bold.ttf"],
}

HEADING = "GOVERNMENT WARNING:"
BODY = STATEMENT.removeprefix(HEADING).strip()

BOURBON = {
    "beverage_type": "spirits",
    "brand_name": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "alcohol_content": "45% Alc./Vol. (90 Proof)",
    "net_contents": "750 mL",
    "bottler": "Old Tom Distillery, Bardstown, KY",
    "country_of_origin": "",
}

# Empty band in each ChatGPT artwork, as fractions of width and height.
ARTWORK = {
    "bourbon": {"file": "bourbon_front.png", "band": (0.098, 0.852, 0.908, 0.932), "app": BOURBON},
}

FIELDS = [
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "bottler",
    "country_of_origin",
    "government_warning",
]


def font(kind: str, size: int, serif: bool = False) -> ImageFont.FreeTypeFont:
    names = (SERIF_FILES if serif else FONT_FILES)[kind]
    for directory in FONT_DIRS:
        for name in names:
            if (directory / name).exists():
                return ImageFont.truetype(str(directory / name), size)
    raise FileNotFoundError(f"no {kind} font found")


def draw_warning(img, rect, size, heading=HEADING, body=BODY, heading_bold=True):
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = rect
    words = [(w, "bold" if heading_bold else "regular") for w in heading.split()]
    words += [(w, "regular") for w in body.split()]

    while size > 8:
        fonts = {"bold": font("bold", size), "regular": font("regular", size)}
        space = draw.textlength(" ", font=fonts["regular"])
        lines, line, width = [], [], 0.0
        for text, kind in words:
            w = draw.textlength(text, font=fonts[kind])
            if line and width + space + w > x1 - x0:
                lines.append(line)
                line, width = [], 0.0
            width += (space if line else 0) + w
            line.append((text, kind, w))
        lines.append(line)
        line_height = int(size * 1.25)
        if len(lines) * line_height <= y1 - y0:
            break
        size -= 1

    y = y0 + ((y1 - y0) - len(lines) * line_height) // 2
    for line in lines:
        x = x0
        for text, kind, w in line:
            draw.text((x, y), text, font=fonts[kind], fill=(25, 25, 25))
            x += w + space
        y += line_height


def artwork_label(name: str, **warning) -> Image.Image:
    spec = ARTWORK[name]
    img = Image.open(SOURCE / spec["file"]).convert("RGB")
    # COLA uploads are usually high resolution; ChatGPT output is 1024 px wide
    img = img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)
    if warning.pop("omit", False):
        return img
    fx0, fy0, fx1, fy1 = spec["band"]
    rect = (
        int(fx0 * img.width),
        int(fy0 * img.height),
        int(fx1 * img.width),
        int(fy1 * img.height),
    )
    draw_warning(img, rect, size=int(img.height * 0.011), **warning)
    return img


def plain_label(lines: list[tuple[str, int]], with_warning: bool = True) -> Image.Image:
    img = Image.new("RGB", (1800, 2400), (246, 240, 225))
    draw = ImageDraw.Draw(img)
    draw.rectangle([30, 30, 1770, 2370], outline=(60, 40, 30), width=10)
    y = 220
    for text, size in lines:
        f = font("bold" if size >= 100 else "regular", size, serif=True)
        draw.text(((1800 - draw.textlength(text, font=f)) / 2, y), text, font=f, fill=(60, 40, 30))
        y += int(size * 1.9)
    if with_warning:
        draw_warning(img, (150, 1950, 1650, 2250), size=30)
    return img


def back_panel() -> Image.Image:
    img = Image.new("RGB", (1800, 1000), (250, 250, 247))
    draw_warning(img, (120, 300, 1680, 700), size=38)
    return img


def photo(img: Image.Image, seed: int) -> Image.Image:
    rng = random.Random(seed)
    img = img.rotate(
        rng.uniform(3, 6), expand=True, fillcolor=(70, 55, 40), resample=Image.Resampling.BICUBIC
    )
    arr = np.asarray(img).astype(np.float32)
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    glare = np.exp(-(((xx - w * 0.35) / (w * 0.2)) ** 2 + ((yy - h * 0.3) / (h * 0.07)) ** 2))
    arr = arr * 0.85 + glare[..., None] * 120
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    return img.filter(ImageFilter.GaussianBlur(1.2))


def not_a_label() -> Image.Image:
    rng = np.random.default_rng(7)
    base = np.linspace(40, 200, 1200)[None, :, None] * np.ones((900, 1, 3))
    noise = rng.normal(0, 12, (900, 1200, 3))
    return Image.fromarray(np.clip(base + noise, 0, 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(3)
    )


def main() -> None:
    LABELS.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []

    def save(img: Image.Image, filename: str) -> str:
        if filename.endswith(".jpg"):
            img.save(LABELS / filename, quality=92)
        else:
            img.save(LABELS / filename)
        return filename

    def case(name, images, app, overall="", **expect):
        row = {"case": name, "images": ";".join(images), **app, "expect_overall": overall}
        for f in FIELDS:
            row[f"expect_{f}"] = expect.get(f, "")
        cases.append(row)

    all_pass = {f: "pass" for f in FIELDS} | {"country_of_origin": "not_checked"}

    ok = save(artwork_label("bourbon"), "bourbon_ok.jpg")
    case("bourbon_ok", [ok], BOURBON, "pass", **all_pass)
    case(
        "bourbon_brand_case",
        [ok],
        BOURBON | {"brand_name": "Old Tom Distillery"},
        brand_name="pass",
    )
    case(
        "bourbon_abv_mismatch",
        [ok],
        BOURBON | {"alcohol_content": "40%"},
        "fail",
        alcohol_content="fail",
    )
    case("bourbon_net_cl", [ok], BOURBON | {"net_contents": "75 cL"}, net_contents="pass")
    case(
        "bourbon_net_wrong", [ok], BOURBON | {"net_contents": "700 mL"}, "fail", net_contents="fail"
    )
    case(
        "bourbon_wrong_brand",
        [ok],
        BOURBON | {"brand_name": "OLD TIM DISTILLING"},
        brand_name="fail",
    )

    title = save(artwork_label("bourbon", heading="Government Warning:"), "bourbon_title_case.jpg")
    case("bourbon_title_case", [title], BOURBON, "fail", government_warning="fail")
    not_bold = save(artwork_label("bourbon", heading_bold=False), "bourbon_not_bold.jpg")
    case("bourbon_not_bold", [not_bold], BOURBON, government_warning="review")
    typo = save(
        artwork_label("bourbon", body=BODY.replace("pregnancy", "pregnacy")), "bourbon_typo.jpg"
    )
    case("bourbon_typo", [typo], BOURBON, "fail", government_warning="fail")
    missing = save(
        artwork_label("bourbon", body=BODY.replace("birth ", "")), "bourbon_missing_word.jpg"
    )
    case("bourbon_missing_word", [missing], BOURBON, "fail", government_warning="fail")
    front = save(artwork_label("bourbon", omit=True), "bourbon_no_warning.jpg")
    case("bourbon_no_warning", [front], BOURBON, "fail", government_warning="fail")
    back = save(back_panel(), "back_panel.png")
    case("bourbon_front_and_back", [front, back], BOURBON, "pass", **all_pass)
    glare = save(photo(artwork_label("bourbon"), seed=1), "bourbon_photo.jpg")
    case(
        "bourbon_photo",
        [glare],
        BOURBON,
        brand_name="pass",
        alcohol_content="pass",
        government_warning="pass",
    )

    rye_lines = [
        ("RIVER BEND", 150),
        ("Straight Rye Whisky", 80),
        ("45% Alc./Vol. (80 Proof)", 70),
        ("750 mL", 70),
        ("Bottled by River Bend Spirits, Louisville, KY", 45),
    ]
    rye_app = {
        "beverage_type": "spirits",
        "brand_name": "River Bend",
        "class_type": "Straight Rye Whisky",
        "alcohol_content": "45%",
        "net_contents": "750 mL",
        "bottler": "River Bend Spirits, Louisville, Kentucky",
        "country_of_origin": "",
    }
    rye = save(plain_label(rye_lines), "rye_proof_mismatch.png")
    case("rye_proof_mismatch", [rye], rye_app, "fail", alcohol_content="fail", bottler="pass")

    mezcal_lines = [
        ("LUNA ROJA", 150),
        ("Mezcal Artesanal", 80),
        ("42% Alc./Vol.", 70),
        ("750 mL", 70),
        ("Imported by Luna Roja Imports, Austin, TX", 45),
    ]
    mezcal_app = {
        "beverage_type": "spirits",
        "brand_name": "LUNA ROJA",
        "class_type": "Mezcal Artesanal",
        "alcohol_content": "42% Alc./Vol.",
        "net_contents": "750 mL",
        "bottler": "Luna Roja Imports, Austin, TX",
        "country_of_origin": "Mexico",
    }
    no_origin = save(plain_label(mezcal_lines), "mezcal_no_origin.png")
    case("mezcal_no_origin", [no_origin], mezcal_app, "fail", country_of_origin="fail")
    with_origin = save(
        plain_label(mezcal_lines[:4] + [("Product of Mexico", 55)] + mezcal_lines[4:]),
        "mezcal_with_origin.png",
    )
    case("mezcal_with_origin", [with_origin], mezcal_app, "pass", country_of_origin="pass")

    blank = save(not_a_label(), "not_a_label.jpg")
    case("not_a_label", [blank], BOURBON, "unreadable")

    # A phone photo of a bottle: curved lines, glare, and warning print a few pixels tall.
    case(
        "bourbon_bottle_photo",
        ["bourbon_bottle_photo.jpg"],
        BOURBON,
        "pass",
        brand_name="pass",
        class_type="pass",
        alcohol_content="pass",
        net_contents="pass",
        bottler="pass",
        government_warning="pass",
    )

    case(
        "ipa_photo_can_ok",
        ["ipa_photo_can_ok.jpg"],
        {
            "beverage_type": "beer",
            "brand_name": "Foghorn",
            "class_type": "IPA",
            "alcohol_content": "6.8%",
            "net_contents": "12 fl oz",
            "bottler": "Harbor Light Brewing Co., Portland, Maine",
            "country_of_origin": "",
        },
        alcohol_content="pass",
        net_contents="pass",
        bottler="pass",
        government_warning="pass",
    )

    with open(ROOT / "cases.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(cases[0]))
        writer.writeheader()
        writer.writerows(cases)
    print(f"wrote {len(cases)} cases to {ROOT / 'cases.csv'}")
    write_samples(cases)


def write_samples(cases: list[dict]) -> None:
    """Copy a few labels into the frontend for the "Try an example" buttons."""
    SAMPLES.mkdir(parents=True, exist_ok=True)
    batch_cases = [c for c in cases if c["case"] not in BATCH_SKIP]
    used = {name for c in batch_cases for name in c["images"].split(";")}
    for name in used:
        shutil.copyfile(LABELS / name, SAMPLES / name)

    columns = ["reference", "label_files", *APPLICATION_COLUMNS]
    with open(SAMPLES / "example-batch.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for c in batch_cases:
            row = {"reference": c["case"], "label_files": c["images"]}
            writer.writerow(row | {k: c[k] for k in APPLICATION_COLUMNS})
    print(f"copied {len(used)} sample images to {SAMPLES}")


if __name__ == "__main__":
    main()
