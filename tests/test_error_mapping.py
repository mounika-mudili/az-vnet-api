from types import SimpleNamespace

import pytest

from app.errors import (
    ProvisioningError,
    ResourceGroupNotFoundError,
    ResourceGroupNotPermittedError,
)
from app.services.azure_network import map_azure_error


def azure_error(code: str, message: str = "azure said no") -> SimpleNamespace:
    return SimpleNamespace(error=SimpleNamespace(code=code), message=message)


@pytest.mark.parametrize("code", ["ResourceGroupNotFound", "SubscriptionNotFound"])
def test_missing_scope_becomes_not_found(code: str) -> None:
    mapped = map_azure_error(azure_error(code), "rg-demo")

    assert isinstance(mapped, ResourceGroupNotFoundError)
    assert "rg-demo" in str(mapped)


@pytest.mark.parametrize("code", ["AuthorizationFailed", "LinkedAuthorizationFailed"])
def test_denied_scope_becomes_forbidden(code: str) -> None:
    mapped = map_azure_error(azure_error(code), "rg-not-mine")

    assert isinstance(mapped, ResourceGroupNotPermittedError)
    assert "rg-not-mine" in str(mapped)


def test_other_failures_become_provisioning_errors() -> None:
    mapped = map_azure_error(azure_error("NetworkAclsValidationFailure", "bad acl"), "rg-demo")

    assert isinstance(mapped, ProvisioningError)
    assert "bad acl" in str(mapped)


def test_error_without_code_still_maps() -> None:
    mapped = map_azure_error(SimpleNamespace(error=None, message="gateway timeout"), "rg-demo")

    assert isinstance(mapped, ProvisioningError)
    assert "gateway timeout" in str(mapped)
