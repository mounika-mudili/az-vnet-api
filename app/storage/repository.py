"""Storage for the results of each VNet creation."""

import json
import logging
import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Protocol

from azure.core.credentials import TokenCredential
from azure.data.tables import TableServiceClient

from app.models.schemas import SubnetRecord, VnetRecord

logger = logging.getLogger(__name__)


DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

# Largest 13-digit millisecond value, used to invert timestamps in row keys.
_MAX_MILLISECONDS = 9_999_999_999_999


class VnetRepository(Protocol):
    def add(self, record: VnetRecord) -> None: ...

    def list_all(self, resource_group: str | None = None, limit: int = DEFAULT_PAGE_SIZE) -> list[VnetRecord]: ...

    def get(self, record_id: str) -> VnetRecord | None: ...

    def find(self, resource_group: str, name: str) -> VnetRecord | None: ...


class TableStorageVnetRepository:
    """Azure Table Storage: one entity per created VNet, partitioned by resource group."""

    def __init__(self, account_name: str, table_name: str, credential: TokenCredential) -> None:
        service = TableServiceClient(
            endpoint=f"https://{account_name}.table.core.windows.net",
            credential=credential,
        )
        self._table = service.create_table_if_not_exists(table_name)

    def add(self, record: VnetRecord) -> None:
        self._table.upsert_entity(_to_entity(record))

    def list_all(self, resource_group: str | None = None, limit: int = DEFAULT_PAGE_SIZE) -> list[VnetRecord]:
        if resource_group is None:
            entities = self._table.list_entities(results_per_page=limit)
        else:
            entities = self._table.query_entities(
                "PartitionKey eq @partition_key",
                parameters={"partition_key": resource_group.lower()},
                results_per_page=limit,
            )

        records = [_to_record(entity) for entity in _take(entities, limit)]
        return sorted(records, key=lambda record: record.created_at, reverse=True)

    def get(self, record_id: str) -> VnetRecord | None:
        entities = self._table.query_entities("RowKey eq @row_key", parameters={"row_key": record_id})
        for entity in entities:
            return _to_record(entity)
        return None

    def find(self, resource_group: str, name: str) -> VnetRecord | None:
        entities = self._table.query_entities(
            "PartitionKey eq @partition_key and NameLower eq @name",
            parameters={"partition_key": resource_group.lower(), "name": name.lower()},
        )
        for entity in entities:
            return _to_record(entity)
        return None


def new_record_id(created_at: datetime) -> str:
    """Record id that doubles as a row key.

    Table Storage returns rows in key order, so inverting the timestamp puts the newest
    record of a resource group first. The suffix separates the same millisecond.
    """
    milliseconds = int(created_at.timestamp() * 1000)
    return f"{_MAX_MILLISECONDS - milliseconds:013d}-{uuid.uuid4().hex}"


def _take(entities: Iterable[Any], limit: int) -> list[Any]:
    page: list = []
    for entity in entities:
        page.append(entity)
        if len(page) >= limit:
            break
    return page


def _to_entity(record: VnetRecord) -> dict[str, str]:
    return {
        "PartitionKey": record.resource_group.lower(),
        "RowKey": record.id,
        "Name": record.name,
        "NameLower": record.name.lower(),
        "ResourceGroup": record.resource_group,
        "SubscriptionId": record.subscription_id,
        "Location": record.location,
        "AddressSpace": json.dumps(record.address_space),
        "Subnets": json.dumps([subnet.model_dump() for subnet in record.subnets]),
        "VnetResourceId": record.vnet_resource_id or "",
        "Status": record.status,
        "CreatedBy": record.created_by,
        "CreatedAt": record.created_at.isoformat(),
        "LastSyncedAt": record.last_synced_at.isoformat() if record.last_synced_at else "",
    }


def _to_record(entity: Any) -> VnetRecord:
    return VnetRecord(
        id=entity["RowKey"],
        name=entity["Name"],
        resource_group=entity["ResourceGroup"],
        subscription_id=entity.get("SubscriptionId", ""),
        location=entity["Location"],
        address_space=json.loads(entity["AddressSpace"]),
        subnets=[SubnetRecord(**subnet) for subnet in json.loads(entity["Subnets"])],
        vnet_resource_id=entity.get("VnetResourceId") or None,
        status=entity["Status"],
        created_by=entity["CreatedBy"],
        created_at=_parse_timestamp(entity["CreatedAt"]),
        last_synced_at=(_parse_timestamp(entity["LastSyncedAt"]) if entity.get("LastSyncedAt") else None),
    )


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
