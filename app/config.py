from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Everything the API needs from its environment.

    Terraform sets these as app settings on the function app; locally they come from .env.
    A missing or blank value fails here instead of surfacing as a confusing Azure error on
    the first request.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    azure_tenant_id: str = Field(min_length=1)
    azure_subscription_id: str = Field(min_length=1)

    # Audience of the tokens this API accepts. Not called AZURE_CLIENT_ID because
    # DefaultAzureCredential reads that variable as the client id of a user-assigned
    # managed identity, and would then try to authenticate as this app registration.
    entra_api_client_id: str = Field(min_length=1)

    # Which user-assigned identity to use for outbound calls. Blank when running under a
    # developer login, where DefaultAzureCredential falls through to the Azure CLI.
    managed_identity_client_id: str = ""

    storage_account_name: str = Field(min_length=1)
    table_name: str = "vnetcreations"


@lru_cache
def get_settings() -> Settings:
    # Values arrive from the environment, which mypy cannot see.
    return Settings()  # type: ignore[call-arg]
