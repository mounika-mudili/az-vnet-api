resource "azurerm_log_analytics_workspace" "api" {
  name                = local.workspace_name
  resource_group_name = azurerm_resource_group.api.name
  location            = azurerm_resource_group.api.location
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
  daily_quota_gb      = var.log_daily_quota_gb
  tags                = local.tags
}

resource "azurerm_application_insights" "api" {
  name                 = local.app_insights_name
  resource_group_name  = azurerm_resource_group.api.name
  location             = azurerm_resource_group.api.location
  workspace_id         = azurerm_log_analytics_workspace.api.id
  application_type     = "web"
  daily_data_cap_in_gb = var.appinsights_daily_cap_gb
  tags                 = local.tags
}

resource "azurerm_monitor_diagnostic_setting" "function_app" {
  name                       = "send-to-log-analytics"
  target_resource_id         = azurerm_linux_function_app.api.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.api.id

  enabled_log {
    category = "FunctionAppLogs"
  }
}
