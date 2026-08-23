"""Wiring. The credential and the Azure clients are built once per process and reused.

Each builder is cached on the configuration it depends on, so a warm function app instance
reuses one credential and one client per dependency instead of rebuilding them per request.
"""

from functools import lru_cache

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential
from fastapi import Depends

from app.config import Settings, get_settings
from app.services.azure_network import AzureNetworkProvider, NetworkProvider
from app.services.vnet_service import VnetService
from app.storage.repository import TableStorageVnetRepository, VnetRepository


@lru_cache
def _build_credential(managed_identity_client_id: str) -> TokenCredential:
    """The identity outbound calls authenticate with.

    In Azure this is the user-assigned identity attached to the function app, named
    explicitly because an app can carry several. Locally the client id is blank and the
    credential chain falls through to the Azure CLI login.
    """
    if managed_identity_client_id:
        return DefaultAzureCredential(managed_identity_client_id=managed_identity_client_id)
    return DefaultAzureCredential()


@lru_cache
def _build_network_provider(subscription_id: str, managed_identity_client_id: str) -> NetworkProvider:
    return AzureNetworkProvider(subscription_id, _build_credential(managed_identity_client_id))


@lru_cache
def _build_repository(account_name: str, table_name: str, managed_identity_client_id: str) -> VnetRepository:
    # Creating the client also creates the table if this is the first deployment.
    return TableStorageVnetRepository(account_name, table_name, _build_credential(managed_identity_client_id))


def get_network_provider(settings: Settings = Depends(get_settings)) -> NetworkProvider:
    return _build_network_provider(settings.azure_subscription_id, settings.managed_identity_client_id)


def get_repository(settings: Settings = Depends(get_settings)) -> VnetRepository:
    return _build_repository(
        settings.storage_account_name,
        settings.table_name,
        settings.managed_identity_client_id,
    )


def get_vnet_service(
    network: NetworkProvider = Depends(get_network_provider),
    repository: VnetRepository = Depends(get_repository),
) -> VnetService:
    return VnetService(network, repository)
