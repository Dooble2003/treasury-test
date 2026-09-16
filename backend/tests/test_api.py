import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

EVAL_LABELS = Path(__file__).resolve().parents[2] / "eval" / "labels"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rejects_non_image(client):
    response = client.post(
        "/api/verify",
        files=[("images", ("notes.txt", b"not an image", "text/plain"))],
        data={"application": json.dumps({"brand_name": "X"})},
    )
    assert response.status_code == 415
    assert "notes.txt" in response.json()["detail"]


def test_rejects_bad_application(client):
    response = client.post(
        "/api/verify",
        files=[("images", ("a.png", b"x", "image/png"))],
        data={"application": "{not json"},
    )
    assert response.status_code == 422


@pytest.mark.skipif(not EVAL_LABELS.exists(), reason="eval labels not generated")
def test_verify_label(client):
    application = {
        "beverage_type": "spirits",
        "brand_name": "Old Tom Distillery",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "alcohol_content": "45%",
        "net_contents": "750 mL",
        "bottler": "Old Tom Distillery, Bardstown, KY",
    }
    image = (EVAL_LABELS / "bourbon_ok.jpg").read_bytes()
    response = client.post(
        "/api/verify",
        files=[("images", ("bourbon_ok.jpg", image, "image/jpeg"))],
        data={"application": json.dumps(application)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == "pass"
    statuses = {f["key"]: f["status"] for f in body["fields"]}
    assert statuses["country_of_origin"] == "not_checked"
    assert statuses["government_warning"] == "pass"
