from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_catalogs() -> None:
    response = client.get("/api/v1/catalogs")
    assert response.status_code == 200
    payload = response.json()
    assert "pendiente_revision" in {item["code"] for item in payload["document_statuses"]}
    assert "stps_repse" in {item["code"] for item in payload["institutions"]}
