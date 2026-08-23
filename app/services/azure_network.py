"""Azure network provisioning."""

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from azure.core.credentials import TokenCredential
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.network.models import AddressSpace, Subnet, VirtualNetwork

from app.errors import (
    ApiError,
    ProvisioningError,
    ResourceGroupNotFoundError,
    ResourceGroupNotPermittedError,
)
from app.models.schemas import VnetCreateRequest

logger = logging.getLogger(__name__)

MISSING_SCOPE_CODES = frozenset({"ResourceGroupNotFound", "SubscriptionNotFound"})
FORBIDDEN_SCOPE_CODES = frozenset({"AuthorizationFailed", "LinkedAuthorizationFailed", "InsufficientPermissions"})


def map_azure_error(exc: Any, resource_group: str) -> ApiError:
    """Translate an Azure error into one of the API's own failure modes.

    Being scoped out of a resource group is a normal answer here, not an internal fault.
    """
    code = getattr(getattr(exc, "error", None), "code", None) or ""
    if code in MISSING_SCOPE_CODES:
        return ResourceGroupNotFoundError(resource_group)
    if code in FORBIDDEN_SCOPE_CODES:
        return ResourceGroupNotPermittedError(resource_group)
    return ProvisioningError(getattr(exc, "message", None) or str(exc))


@dataclass(frozen=True)
class ProvisionedSubnet:
    name: str
    address_prefix: str
    resource_id: str


@dataclass(frozen=True)
class ProvisionedVnet:
    subscription_id: str
    resource_id: str
    status: str
    subnets: tuple[ProvisionedSubnet, ...]


class NetworkProvider(Protocol):
    def create_vnet(self, request: VnetCreateRequest) -> ProvisionedVnet: ...

    def get_vnet(self, resource_group: str, name: str) -> ProvisionedVnet | None: ...


class AzureNetworkProvider:
    """Creates the VNet and its subnets in a single ARM deployment."""

    def __init__(self, subscription_id: str, credential: TokenCredential) -> None:
        self._subscription_id = subscription_id
        self._client = NetworkManagementClient(credential, subscription_id)

    def create_vnet(self, request: VnetCreateRequest) -> ProvisionedVnet:
        parameters = VirtualNetwork(
            location=request.location,
            address_space=AddressSpace(address_prefixes=list(request.address_space)),
            subnets=[Subnet(name=subnet.name, address_prefix=subnet.address_prefix) for subnet in request.subnets],
        )

        try:
            poller = self._client.virtual_networks.begin_create_or_update(
                request.resource_group, request.name, parameters
            )
            vnet = poller.result()
        except ResourceNotFoundError as exc:
            raise ResourceGroupNotFoundError(request.resource_group) from exc
        except HttpResponseError as exc:
            logger.warning("Azure rejected VNet '%s': %s", request.name, exc)
            raise map_azure_error(exc, request.resource_group) from exc

        return self._to_provisioned(vnet)

    def get_vnet(self, resource_group: str, name: str) -> ProvisionedVnet | None:
        """None means the VNet is no longer in Azure."""
        try:
            vnet = self._client.virtual_networks.get(resource_group, name)
        except ResourceNotFoundError:
            return None
        except HttpResponseError as exc:
            logger.warning("Azure refused to read VNet '%s': %s", name, exc)
            raise map_azure_error(exc, resource_group) from exc

        return self._to_provisioned(vnet)

    def _to_provisioned(self, vnet: Any) -> ProvisionedVnet:
        subnets = tuple(
            ProvisionedSubnet(
                name=subnet.name or "",
                address_prefix=subnet.address_prefix or "",
                resource_id=subnet.id or "",
            )
            for subnet in (vnet.subnets or [])
        )
        return ProvisionedVnet(
            subscription_id=self._subscription_id,
            resource_id=vnet.id or "",
            status=vnet.provisioning_state or "Unknown",
            subnets=subnets,
        )
