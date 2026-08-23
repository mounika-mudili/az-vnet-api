from typing import Any

from fastapi.testclient import TestClient

from tests.fakes import FakeNetwork


def test_refresh_keeps_a_live_vnet_intact(client: TestClient, valid_payload: dict[str, Any]) -> None:
    created = client.post("/vnets", json=valid_payload).json()

    refreshed = client.post(f"/vnets/{created['id']}/refresh")

    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["status"] == "Succeeded"
    assert body["last_synced_at"] >= created["last_synced_at"]
    assert [subnet["name"] for subnet in body["subnets"]] == ["app-subnet", "data-subnet"]


def test_refresh_marks_a_vnet_deleted_outside_the_api(
    client: TestClient, network: FakeNetwork, valid_payload: dict[str, Any]
) -> None:
    created = client.post("/vnets", json=valid_payload).json()
    network.forget(valid_payload["resource_group"], valid_payload["name"])

    refreshed = client.post(f"/vnets/{created['id']}/refresh")

    assert refreshed.status_code == 200
    assert refreshed.json()["status"] == "Deleted"


def test_refresh_is_written_back_to_storage(
    client: TestClient, network: FakeNetwork, valid_payload: dict[str, Any]
) -> None:
    created = client.post("/vnets", json=valid_payload).json()
    network.forget(valid_payload["resource_group"], valid_payload["name"])

    client.post(f"/vnets/{created['id']}/refresh")

    assert client.get(f"/vnets/{created['id']}").json()["status"] == "Deleted"


def test_refresh_of_unknown_record_returns_404(client: TestClient) -> None:
    assert client.post("/vnets/1234/refresh").status_code == 404
