"""Stand-ins for Azure, so the suite runs without a subscription.

These implement the same protocols as AzureNetworkProvider and TableStorageVnetRepository
and are injected through FastAPI's dependency overrides. They live here, not in app/,
because nothing that ships to Azure should be able to reach them.
"""

from app.models.schemas import VnetCreateRequest, VnetRecord
from app.services.azure_network import ProvisionedSubnet, ProvisionedVnet
from app.storage.repository import DEFAULT_PAGE_SIZE

SUBSCRIPTION_ID = "00000000-0000-0000-0000-000000000000"


def _key(resource_group: str, name: str) -> tuple[str, str]:
    return resource_group.lower(), name.lower()


class FakeNetwork:
    """Hands back Azure-shaped resource ids and remembers what it created."""

    def __init__(self) -> None:
        self._created: dict[tuple[str, str], ProvisionedVnet] = {}

    def create_vnet(self, request: VnetCreateRequest) -> ProvisionedVnet:
        vnet_id = (
            f"/subscriptions/{SUBSCRIPTION_ID}"
            f"/resourceGroups/{request.resource_group}"
            f"/providers/Microsoft.Network/virtualNetworks/{request.name}"
        )
        provisioned = ProvisionedVnet(
            subscription_id=SUBSCRIPTION_ID,
            resource_id=vnet_id,
            status="Succeeded",
            subnets=tuple(
                ProvisionedSubnet(
                    name=subnet.name,
                    address_prefix=subnet.address_prefix,
                    resource_id=f"{vnet_id}/subnets/{subnet.name}",
                )
                for subnet in request.subnets
            ),
        )
        self._created[_key(request.resource_group, request.name)] = provisioned
        return provisioned

    def get_vnet(self, resource_group: str, name: str) -> ProvisionedVnet | None:
        return self._created.get(_key(resource_group, name))

    def forget(self, resource_group: str, name: str) -> None:
        """Stand in for a VNet deleted outside the API."""
        self._created.pop(_key(resource_group, name), None)


class FakeRepository:
    """Records last as long as the test."""

    def __init__(self) -> None:
        self._records: dict[str, VnetRecord] = {}

    def add(self, record: VnetRecord) -> None:
        self._records[record.id] = record

    def list_all(self, resource_group: str | None = None, limit: int = DEFAULT_PAGE_SIZE) -> list[VnetRecord]:
        records = [
            record
            for record in self._records.values()
            if resource_group is None or record.resource_group.lower() == resource_group.lower()
        ]
        records.sort(key=lambda record: record.created_at, reverse=True)
        return records[:limit]

    def get(self, record_id: str) -> VnetRecord | None:
        return self._records.get(record_id)

    def find(self, resource_group: str, name: str) -> VnetRecord | None:
        for record in self._records.values():
            if record.resource_group.lower() == resource_group.lower() and (record.name.lower() == name.lower()):
                return record
        return None
