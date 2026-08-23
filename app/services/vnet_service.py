import logging
from datetime import UTC, datetime

from app.auth.entra import Principal
from app.errors import VnetAlreadyRecordedError
from app.models.schemas import SubnetRecord, VnetCreateRequest, VnetRecord
from app.services.azure_network import NetworkProvider
from app.storage.repository import DEFAULT_PAGE_SIZE, VnetRepository, new_record_id

logger = logging.getLogger(__name__)

# Status written when the VNet was removed from Azure outside this API.
DELETED_STATUS = "Deleted"


class VnetService:
    def __init__(self, network: NetworkProvider, repository: VnetRepository) -> None:
        self._network = network
        self._repository = repository

    def create(self, request: VnetCreateRequest, principal: Principal) -> VnetRecord:
        existing = self._repository.find(request.resource_group, request.name)
        if existing is not None:
            raise VnetAlreadyRecordedError(request.name, request.resource_group)

        provisioned = self._network.create_vnet(request)

        created_at = datetime.now(UTC)
        record = VnetRecord(
            id=new_record_id(created_at),
            name=request.name,
            resource_group=request.resource_group,
            subscription_id=provisioned.subscription_id,
            location=request.location,
            address_space=list(request.address_space),
            subnets=[
                SubnetRecord(
                    name=subnet.name,
                    address_prefix=subnet.address_prefix,
                    resource_id=subnet.resource_id,
                )
                for subnet in provisioned.subnets
            ],
            vnet_resource_id=provisioned.resource_id,
            status=provisioned.status,
            created_by=principal.display_name,
            created_at=created_at,
            last_synced_at=created_at,
        )

        self._repository.add(record)
        logger.info("Stored VNet %s (%s) created by %s", record.name, record.id, record.created_by)
        return record

    def list(self, resource_group: str | None = None, limit: int = DEFAULT_PAGE_SIZE) -> list[VnetRecord]:
        return self._repository.list_all(resource_group=resource_group, limit=limit)

    def get(self, record_id: str) -> VnetRecord | None:
        return self._repository.get(record_id)

    def refresh(self, record_id: str) -> VnetRecord | None:
        """Re-read the VNet from Azure and write back what is actually there."""
        record = self._repository.get(record_id)
        if record is None:
            return None

        live = self._network.get_vnet(record.resource_group, record.name)
        synced_at = datetime.now(UTC)

        if live is None:
            logger.info("VNet %s is gone from Azure; marking record %s", record.name, record.id)
            updated = record.model_copy(update={"status": DELETED_STATUS, "last_synced_at": synced_at})
        else:
            updated = record.model_copy(
                update={
                    "status": live.status,
                    "vnet_resource_id": live.resource_id or record.vnet_resource_id,
                    "subnets": [
                        SubnetRecord(
                            name=subnet.name,
                            address_prefix=subnet.address_prefix,
                            resource_id=subnet.resource_id,
                        )
                        for subnet in live.subnets
                    ],
                    "last_synced_at": synced_at,
                }
            )

        self._repository.add(updated)
        return updated
