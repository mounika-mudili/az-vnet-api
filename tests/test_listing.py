import pytest
from fastapi.testclient import TestClient


def _payload(name: str, resource_group: str, third_octet: int) -> dict:
    return {
        "name": name,
        "resource_group": resource_group,
        "location": "westeurope",
        "address_space": [f"10.{third_octet}.0.0/16"],
        "subnets": [
            {"name": "app-subnet", "address_prefix": f"10.{third_octet}.1.0/24"},
            {"name": "data-subnet", "address_prefix": f"10.{third_octet}.2.0/24"},
        ],
    }


@pytest.fixture
def three_vnets(client: TestClient) -> None:
    for index, (name, resource_group) in enumerate(
        [
            ("vnet-a", "rg-team-a"),
            ("vnet-b", "rg-team-b"),
            ("vnet-c", "rg-team-b"),
        ]
    ):
        response = client.post("/vnets", json=_payload(name, resource_group, index))
        assert response.status_code == 201


def test_listing_can_be_filtered_by_resource_group(client: TestClient, three_vnets: None) -> None:
    response = client.get("/vnets", params={"resource_group": "rg-team-b"})

    assert response.status_code == 200
    assert {record["name"] for record in response.json()} == {"vnet-b", "vnet-c"}


def test_resource_group_filter_ignores_case(client: TestClient, three_vnets: None) -> None:
    response = client.get("/vnets", params={"resource_group": "RG-Team-A"})

    assert [record["name"] for record in response.json()] == ["vnet-a"]


def test_listing_honours_the_limit(client: TestClient, three_vnets: None) -> None:
    assert len(client.get("/vnets", params={"limit": 2}).json()) == 2


def test_listing_returns_newest_first(client: TestClient, three_vnets: None) -> None:
    names = [record["name"] for record in client.get("/vnets").json()]

    assert names == ["vnet-c", "vnet-b", "vnet-a"]


@pytest.mark.parametrize("limit", [0, -1, 201])
def test_out_of_range_limits_are_rejected(client: TestClient, limit: int) -> None:
    assert client.get("/vnets", params={"limit": limit}).status_code == 422


def test_record_ids_sort_newest_first(client: TestClient, three_vnets: None) -> None:
    ids = [record["id"] for record in client.get("/vnets").json()]

    assert ids == sorted(ids)
