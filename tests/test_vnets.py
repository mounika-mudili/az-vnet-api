from typing import Any

from fastapi.testclient import TestClient


def test_create_returns_stored_record(client: TestClient, valid_payload: dict[str, Any]) -> None:
    response = client.post("/vnets", json=valid_payload)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "demo-vnet"
    assert body["status"] == "Succeeded"
    assert body["vnet_resource_id"].endswith("/virtualNetworks/demo-vnet")
    assert [subnet["name"] for subnet in body["subnets"]] == ["app-subnet", "data-subnet"]
    assert all(subnet["resource_id"] for subnet in body["subnets"])
    assert body["created_by"]
    assert body["id"]


def test_created_vnet_can_be_retrieved(client: TestClient, valid_payload: dict[str, Any]) -> None:
    created = client.post("/vnets", json=valid_payload).json()

    listed = client.get("/vnets")
    assert listed.status_code == 200
    assert [record["id"] for record in listed.json()] == [created["id"]]

    fetched = client.get(f"/vnets/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created


def test_unknown_id_returns_404(client: TestClient) -> None:
    assert client.get("/vnets/1234").status_code == 404


def test_same_vnet_twice_is_a_conflict(client: TestClient, valid_payload: dict[str, Any]) -> None:
    assert client.post("/vnets", json=valid_payload).status_code == 201

    response = client.post("/vnets", json=valid_payload)

    assert response.status_code == 409
    assert "already created" in response.json()["detail"]
