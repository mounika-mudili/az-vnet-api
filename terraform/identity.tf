// The function app runs as a user-assigned identity the platform team owns, so it is read
// here, never created. Its lifetime is independent of this stack: destroying the API does
// not take the identity, and its role assignments survive a rebuild.
data "azurerm_user_assigned_identity" "api" {
  name                = var.function_identity_name
  resource_group_name = var.function_identity_resource_group_name
}

// Off by default: the identity is expected to arrive with Network Contributor on the VNet
// group and Storage Table Data Contributor on the storage account already granted. Turn it
// on to have this stack grant them instead, which needs Microsoft.Authorization write
// access and will conflict with an assignment that already exists at the same scope.
resource "azurerm_role_assignment" "network_contributor" {
  count = var.manage_identity_role_assignments ? 1 : 0

  scope                = local.vnet_resource_group_id
  role_definition_name = "Network Contributor"
  principal_id         = data.azurerm_user_assigned_identity.api.principal_id
  description          = "Lets the VNet API create virtual networks and subnets"
}

resource "azurerm_role_assignment" "table_data_contributor" {
  count = var.manage_identity_role_assignments ? 1 : 0

  scope                = azurerm_storage_account.records.id
  role_definition_name = "Storage Table Data Contributor"
  principal_id         = data.azurerm_user_assigned_identity.api.principal_id
  description          = "Lets the VNet API store and read creation records"
}
