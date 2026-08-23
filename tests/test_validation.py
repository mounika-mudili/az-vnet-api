from typing import Any

import pytest
from fastapi.testclient import TestClient

INVALID_CASES: dict[str, dict[str, Any]] = {
    "single_subnet": {"subnets": [{"name": "only-one", "address_prefix": "10.0.1.0/24"}]},
    "no_subnets": {"subnets": []},
    "subnet_outside_address_space": {
        "subnets": [
            {"name": "app-subnet", "address_prefix": "10.0.1.0/24"},
            {"name": "stray-subnet", "address_prefix": "192.168.5.0/24"},
        ]
    },
    "overlapping_subnets": {
        "subnets": [
            {"name": "app-subnet", "address_prefix": "10.0.0.0/17"},
            {"name": "data-subnet", "address_prefix": "10.0.1.0/24"},
        ]
    },
    "duplicate_subnet_names": {
        "subnets": [
            {"name": "app-subnet", "address_prefix": "10.0.1.0/24"},
            {"name": "APP-SUBNET", "address_prefix": "10.0.2.0/24"},
        ]
    },
    "malformed_cidr": {"address_space": ["10.0.0.0/33"]},
    "cidr_with_host_bits": {"address_space": ["10.0.0.5/16"]},
    "empty_address_space": {"address_space": []},
    "invalid_vnet_name": {"name": "bad name!"},
    "unknown_field": {"unexpected": "value"},
}


@pytest.mark.parametrize("case", sorted(INVALID_CASES))
def test_invalid_requests_are_rejected(client: TestClient, valid_payload: dict[str, Any], case: str) -> None:
    response = client.post("/vnets", json={**valid_payload, **INVALID_CASES[case]})

    assert response.status_code == 422


def test_nothing_is_stored_when_validation_fails(client: TestClient, valid_payload: dict[str, Any]) -> None:
    client.post("/vnets", json={**valid_payload, "subnets": []})

    assert client.get("/vnets").json() == []


def test_multiple_address_spaces_are_allowed(client: TestClient, valid_payload: dict[str, Any]) -> None:
    payload = {
        **valid_payload,
        "address_space": ["10.0.0.0/16", "10.1.0.0/16"],
        "subnets": [
            {"name": "app-subnet", "address_prefix": "10.0.1.0/24"},
            {"name": "data-subnet", "address_prefix": "10.1.1.0/24"},
        ],
    }

    assert client.post("/vnets", json=payload).status_code == 201
