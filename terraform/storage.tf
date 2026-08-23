// Holds the results table and backs the function runtime. The app reaches the table
// through its managed identity; the runtime still needs the account key.
resource "azurerm_storage_account" "records" {
  name                = local.storage_account_name
  resource_group_name = azurerm_resource_group.api.name
  location            = azurerm_resource_group.api.location

  account_tier             = "Standard"
  account_kind             = "StorageV2"
  account_replication_type = var.environment == "prod" ? "ZRS" : "LRS"

  min_tls_version                  = "TLS1_2"
  https_traffic_only_enabled       = true
  allow_nested_items_to_be_public  = false
  public_network_access_enabled    = true
  shared_access_key_enabled        = true
  default_to_oauth_authentication  = true
  cross_tenant_replication_enabled = false

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }

  tags = local.tags
}

resource "azurerm_storage_table" "records" {
  name                 = local.table_name
  storage_account_name = azurerm_storage_account.records.name
}
