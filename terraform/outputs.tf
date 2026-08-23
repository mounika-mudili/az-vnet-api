output "api_base_url" {
  description = "Base URL of the deployed API."
  value       = "https://${azurerm_linux_function_app.api.default_hostname}"
}

output "function_app_name" {
  description = "Function app name, used by 'func azure functionapp publish'."
  value       = azurerm_linux_function_app.api.name
}

output "api_resource_group" {
  description = "Resource group holding the API."
  value       = azurerm_resource_group.api.name
}

output "vnet_resource_group" {
  description = "Resource group the API may create VNets in. Use this as 'resource_group' in POST /vnets."
  value       = var.vnet_resource_group_name
}

output "storage_account_name" {
  description = "Storage account holding the results table."
  value       = azurerm_storage_account.records.name
}

output "table_name" {
  description = "Table holding one entity per created VNet."
  value       = azurerm_storage_table.records.name
}

output "function_identity_principal_id" {
  description = "Object ID of the identity the function app runs as. Grant roles to this."
  value       = data.azurerm_user_assigned_identity.api.principal_id
}

output "function_identity_client_id" {
  description = "Client ID of that identity, passed to the app as MANAGED_IDENTITY_CLIENT_ID."
  value       = data.azurerm_user_assigned_identity.api.client_id
}
