from pathlib import Path

from fastapi.testclient import TestClient

import config
from app import app


client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analysis_returns_503_when_auth_is_not_configured(monkeypatch):
    monkeypatch.setattr(config, "API_AUTH_TOKEN", "")

    response = client.post("/api/v1/analyses")

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "API authentication is not configured."
    )


def test_analysis_rejects_missing_or_invalid_bearer_token(monkeypatch):
    monkeypatch.setattr(config, "API_AUTH_TOKEN", "test-secret")

    response = client.post("/api/v1/analyses")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_analysis_rejects_too_many_files(monkeypatch):
    monkeypatch.setattr(config, "API_AUTH_TOKEN", "test-secret")
    monkeypatch.setattr(config, "MAX_UPLOAD_FILES", 1)

    response = client.post(
        "/api/v1/analyses",
        headers={"Authorization": "Bearer test-secret"},
        files=[
            ("files", ("one.txt", b"first", "text/plain")),
            ("files", ("two.txt", b"second", "text/plain")),
        ],
    )

    assert response.status_code == 413


def test_analysis_rejects_oversized_file(monkeypatch):
    monkeypatch.setattr(config, "API_AUTH_TOKEN", "test-secret")
    monkeypatch.setattr(config, "MAX_FILE_SIZE_MB", 0)

    response = client.post(
        "/api/v1/analyses",
        headers={"Authorization": "Bearer test-secret"},
        files=[
            ("files", ("quote.txt", b"some quotation text", "text/plain")),
        ],
    )

    assert response.status_code == 413


def test_analysis_rejects_total_upload_limit(monkeypatch):
    monkeypatch.setattr(config, "API_AUTH_TOKEN", "test-secret")
    monkeypatch.setattr(config, "MAX_TOTAL_UPLOAD_SIZE_MB", 1)
    monkeypatch.setattr(config, "MAX_FILE_SIZE_MB", 5)

    response = client.post(
        "/api/v1/analyses",
        headers={"Authorization": "Bearer test-secret"},
        files=[
            ("files", ("quote.txt", b"x" * (1024 * 1024 + 1), "text/plain")),
        ],
    )

    assert response.status_code == 413


def test_analysis_rejects_oversized_query(monkeypatch):
    monkeypatch.setattr(config, "API_AUTH_TOKEN", "test-secret")
    monkeypatch.setattr(config, "MAX_QUERY_CHARS", 5)

    response = client.post(
        "/api/v1/analyses",
        headers={"Authorization": "Bearer test-secret"},
        data={"query": "this query is too long"},
        files=[
            ("files", ("quote.txt", b"quotation", "text/plain")),
        ],
    )

    assert response.status_code == 413


def test_analysis_returns_safe_filename_and_success(monkeypatch):
    monkeypatch.setattr(config, "API_AUTH_TOKEN", "test-secret")

    class DummyAgent:
        def process_documents(self, paths, query, criteria):
            assert len(paths) == 1
            assert Path(paths[0]).read_text() == "quotation content"
            assert query == "Compare quotations"
            assert criteria == ["cost"]
            return {"status": "success"}

    monkeypatch.setattr(
        "app.QuotationIntelligenceAgent",
        DummyAgent,
    )

    response = client.post(
        "/api/v1/analyses",
        headers={"Authorization": "Bearer test-secret"},
        data={
            "query": "Compare quotations",
            "criteria": "cost",
        },
        files=[
            (
                "files",
                ("../../quote.txt", b"quotation content", "text/plain"),
            ),
        ],
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["uploaded_files"] == ["quote.txt"]