class ApiError(Exception):
    """Base class for errors that map to a specific HTTP status."""


class VnetAlreadyRecordedError(ApiError):
    def __init__(self, name: str, resource_group: str) -> None:
        super().__init__(f"VNet '{name}' was already created in resource group '{resource_group}'")
        self.name = name
        self.resource_group = resource_group


class ResourceGroupNotFoundError(ApiError):
    def __init__(self, resource_group: str) -> None:
        super().__init__(f"Resource group '{resource_group}' does not exist")
        self.resource_group = resource_group


class ResourceGroupNotPermittedError(ApiError):
    """The API's identity has no network permissions in the requested resource group."""

    def __init__(self, resource_group: str) -> None:
        super().__init__(f"This API is not permitted to create networks in resource group '{resource_group}'")
        self.resource_group = resource_group


class ProvisioningError(ApiError):
    """Azure rejected or failed the network deployment."""
