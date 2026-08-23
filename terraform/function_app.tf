// Y1 = consumption: per-execution billing, scales to zero.
resource "azurerm_service_plan" "api" {
  name                = local.service_plan_name
  resource_group_name = azurerm_resource_group.api.name
  location            = azurerm_resource_group.api.location
  os_type             = "Linux"
  sku_name            = "Y1"
  tags                = local.tags
}

resource "azurerm_linux_function_app" "api" {
  name                = local.function_app_name
  resource_group_name = azurerm_resource_group.api.name
  location            = azurerm_resource_group.api.location
  service_plan_id     = azurerm_service_plan.api.id

  storage_account_name       = azurerm_storage_account.records.name
  storage_account_access_key = azurerm_storage_account.records.primary_access_key

  https_only                                     = true
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false

  identity {
    type         = "UserAssigned"
    identity_ids = [data.azurerm_user_assigned_identity.api.id]
  }

  site_config {
    minimum_tls_version                    = "1.2"
    ftps_state                             = "Disabled"
    http2_enabled                          = true
    application_insights_connection_string = azurerm_application_insights.api.connection_string

    application_stack {
      python_version = var.python_version
    }
  }

  app_settings = {
    AZURE_TENANT_ID     = var.tenant_id
    ENTRA_API_CLIENT_ID = var.api_client_id

    // Names the identity the app authenticates outbound with. Not AZURE_CLIENT_ID: the
    // Azure SDK reads that as the managed identity to use, and would pick up the API's
    // own app registration instead.
    MANAGED_IDENTITY_CLIENT_ID = data.azurerm_user_assigned_identity.api.client_id

    AZURE_SUBSCRIPTION_ID = var.subscription_id
    STORAGE_ACCOUNT_NAME  = azurerm_storage_account.records.name
    TABLE_NAME            = azurerm_storage_table.records.name

    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
    ENABLE_ORYX_BUILD              = "true"
  }

  lifecycle {
    // Rewritten by each publish.
    ignore_changes = [app_settings["WEBSITE_RUN_FROM_PACKAGE"]]
  }

  tags = local.tags
}
