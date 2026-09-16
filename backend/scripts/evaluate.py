"""Run every case in eval/cases.csv and compare the results with the expected statuses.

Run from backend/:
    uv run python scripts/evaluate.py                    # in process
    uv run python scripts/evaluate.py --url https://...  # against a deployed app
"""

import argparse
import csv
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EVAL = Path(__file__).resolve().parents[2] / "eval"
APP_FIELDS = [
    "beverage_type",
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "bottler",
    "country_of_origin",
]


def run_local(paths: list[Path], application: dict) -> dict:
    from app.models import Application
    from app.ocr import load_image
    from app.verify import verify

    images = [load_image(p.read_bytes()) for p in paths]
    return verify(images, Application(**application)).model_dump()


def run_remote(url: str, paths: list[Path], application: dict) -> dict:
    import httpx

    files = [("images", (p.name, p.read_bytes())) for p in paths]
    response = httpx.post(
        url.rstrip("/") + "/api/verify",
        files=files,
        data={"application": json.dumps(application)},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url")
    parser.add_argument("--case", help="run only cases whose name contains this")
    args = parser.parse_args()

    with open(EVAL / "cases.csv", encoding="utf-8") as fh:
        cases = [c for c in csv.DictReader(fh) if not args.case or args.case in c["case"]]

    if not args.url:
        from app.ocr import warm_up

        warm_up()

    checked, correct = Counter(), Counter()
    timings, failures = [], []
    for case in cases:
        paths = [EVAL / "labels" / name for name in case["images"].split(";")]
        application = {k: case[k] for k in APP_FIELDS}
        started = time.perf_counter()
        if args.url:
            result = run_remote(args.url, paths, application)
        else:
            result = run_local(paths, application)
        timings.append(time.perf_counter() - started)

        statuses = {f["key"]: f for f in result["fields"]}
        expectations = {
            k.removeprefix("expect_"): v for k, v in case.items() if k.startswith("expect_")
        }
        for key, expected in expectations.items():
            if not expected:
                continue
            actual = result["overall"] if key == "overall" else statuses.get(key, {}).get("status")
            checked[key] += 1
            if actual == expected:
                correct[key] += 1
            else:
                note = "" if key == "overall" else statuses.get(key, {}).get("note", "")
                failures.append(f"{case['case']}: {key} expected {expected}, got {actual}. {note}")
        print(f"{case['case']:28} {timings[-1]:5.2f}s  {result['overall']}", flush=True)

    print("\nfield                  correct")
    for key in checked:
        print(f"{key:22} {correct[key]:3}/{checked[key]}")
    total_checked, total_correct = sum(checked.values()), sum(correct.values())
    print(f"{'total':22} {total_correct:3}/{total_checked}")
    if timings:
        p95 = sorted(timings)[max(0, round(len(timings) * 0.95) - 1)]
        print(
            f"\nlatency: mean {statistics.mean(timings):.2f}s, "
            f"median {statistics.median(timings):.2f}s, p95 {p95:.2f}s"
        )
    if failures:
        print("\nmismatches:")
        for line in failures:
            print(" -", line)
        sys.exit(1)


if __name__ == "__main__":
    main()
