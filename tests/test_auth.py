from typing import Any

from fastapi.testclient import TestClient


def test_health_needs_no_token(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_without_token_is_rejected(anonymous_client: TestClient, valid_payload: dict[str, Any]) -> None:
    response = anonymous_client.post("/vnets", json=valid_payload)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_list_without_token_is_rejected(anonymous_client: TestClient) -> None:
    assert anonymous_client.get("/vnets").status_code == 401


def test_get_without_token_is_rejected(anonymous_client: TestClient) -> None:
    assert anonymous_client.get("/vnets/does-not-matter").status_code == 401


def test_refresh_without_token_is_rejected(anonymous_client: TestClient) -> None:
    assert anonymous_client.post("/vnets/does-not-matter/refresh").status_code == 401


def test_garbage_token_is_rejected(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/vnets", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401
