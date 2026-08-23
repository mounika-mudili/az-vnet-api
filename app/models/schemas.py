import ipaddress
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network

T = TypeVar("T")

VNET_NAME = Annotated[str, Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9_]$")]
SUBNET_NAME = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")]
RESOURCE_GROUP_NAME = Annotated[str, Field(min_length=1, max_length=90, pattern=r"^[a-zA-Z0-9._()-]*[a-zA-Z0-9_()-]$")]


def parse_cidr(value: str) -> IPNetwork:
    """Parse a CIDR block, rejecting host bits (e.g. 10.0.1.5/24)."""
    try:
        return ipaddress.ip_network(value, strict=True)
    except ValueError as exc:
        raise ValueError(f"'{value}' is not a valid CIDR block: {exc}") from exc


class SubnetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: SUBNET_NAME
    address_prefix: str

    @field_validator("address_prefix")
    @classmethod
    def _check_prefix(cls, value: str) -> str:
        parse_cidr(value)
        return value


class VnetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: VNET_NAME
    resource_group: RESOURCE_GROUP_NAME
    location: str = Field(min_length=1, max_length=64)
    address_space: list[str] = Field(min_length=1)
    subnets: list[SubnetRequest] = Field(min_length=2, description="At least two subnets are required.")

    @field_validator("address_space")
    @classmethod
    def _check_address_space(cls, value: list[str]) -> list[str]:
        for prefix in value:
            parse_cidr(prefix)
        return value

    @model_validator(mode="after")
    def _check_subnet_layout(self) -> "VnetCreateRequest":
        spaces = [parse_cidr(prefix) for prefix in self.address_space]
        for first, second in _pairs(spaces):
            if first.overlaps(second):
                raise ValueError(f"address spaces {first} and {second} overlap")

        names = [subnet.name.lower() for subnet in self.subnets]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise ValueError(f"duplicate subnet names: {', '.join(sorted(duplicates))}")

        subnets = [(subnet.name, parse_cidr(subnet.address_prefix)) for subnet in self.subnets]
        for name, network in subnets:
            if not any(_is_contained(network, space) for space in spaces):
                raise ValueError(
                    f"subnet '{name}' ({network}) is not inside the VNet address space "
                    f"({', '.join(str(space) for space in spaces)})"
                )

        for (first_name, first), (second_name, second) in _pairs(subnets):
            if first.overlaps(second):
                raise ValueError(f"subnets '{first_name}' ({first}) and '{second_name}' ({second}) overlap")
        return self


class SubnetRecord(BaseModel):
    name: str
    address_prefix: str
    resource_id: str | None = None


class VnetRecord(BaseModel):
    id: str
    name: str
    resource_group: str
    subscription_id: str
    location: str
    address_space: list[str]
    subnets: list[SubnetRecord]
    vnet_resource_id: str | None = None
    status: str
    created_by: str
    created_at: datetime
    last_synced_at: datetime | None = Field(default=None, description="When the record was last checked against Azure.")


def _pairs(items: list[T]) -> Iterator[tuple[T, T]]:
    for index, first in enumerate(items):
        for second in items[index + 1 :]:
            yield first, second


def _is_contained(subnet: IPNetwork, space: IPNetwork) -> bool:
    return subnet.version == space.version and subnet.subnet_of(space)  # type: ignore[arg-type]
