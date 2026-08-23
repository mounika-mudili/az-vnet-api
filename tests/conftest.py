from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.entra import Principal, require_authenticated_user
from app.config import Settings, get_settings
from app.dependencies import get_network_provider, get_repository
from app.main import app
from tests.fakes import FakeNetwork, FakeRepository


def _settings() -> Settings:
    """Settings that satisfy validation without pointing at anything real."""
    return Settings(
        azure_tenant_id="00000000-0000-0000-0000-000000000000",
        entra_api_client_id="11111111-1111-1111-1111-111111111111",
        azure_subscription_id="22222222-2222-2222-2222-222222222222",
        storage_account_name="sttestrecords",
    )


@pytest.fixture
def anonymous_client() -> Iterator[TestClient]:
    """Token validation left in place, so calls without a valid token get 401."""
    app.dependency_overrides = {
        get_settings: _settings,
        get_network_provider: FakeNetwork,
        get_repository: FakeRepository,
    }
    with TestClient(app) as client:
        yield client
    app.dependency_overrides = {}


@pytest.fixture
def network() -> FakeNetwork:
    """The fake Azure. Shared with the client so tests can make it drift."""
    return FakeNetwork()


@pytest.fixture
def client(network: FakeNetwork) -> Iterator[TestClient]:
    """Authenticated caller. Everything below the token check is the real stack."""
    repository = FakeRepository()
    principal = Principal(subject="test-subject", display_name="tester@example.com")
    app.dependency_overrides = {
        get_settings: _settings,
        get_network_provider: lambda: network,
        get_repository: lambda: repository,
        require_authenticated_user: lambda: principal,
    }
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides = {}


@pytest.fixture
def valid_payload() -> dict[str, Any]:
    return {
        "name": "demo-vnet",
        "resource_group": "rg-network-demo",
        "location": "westeurope",
        "address_space": ["10.0.0.0/16"],
        "subnets": [
            {"name": "app-subnet", "address_prefix": "10.0.1.0/24"},
            {"name": "data-subnet", "address_prefix": "10.0.2.0/24"},
        ],
    }
