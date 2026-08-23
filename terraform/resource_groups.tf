resource "azurerm_resource_group" "api" {
  name     = local.resource_group_name
  location = var.location
  tags     = local.tags
}

// Separate group for caller-requested VNets, so the network rights land in one place.
resource "azurerm_resource_group" "vnets" {
  count = var.create_vnet_resource_group ? 1 : 0

  name     = var.vnet_resource_group_name
  location = var.location
  tags     = local.tags
}

data "azurerm_resource_group" "vnets" {
  count = var.create_vnet_resource_group ? 0 : 1

  name = var.vnet_resource_group_name
}

// Guards against a stray delete from the portal or CLI. Terraform drops the lock
// before the group, so destroy still works.
resource "azurerm_management_lock" "vnets" {
  count = var.create_vnet_resource_group && var.lock_vnet_resource_group ? 1 : 0

  name       = "no-delete"
  scope      = azurerm_resource_group.vnets[0].id
  lock_level = "CanNotDelete"
  notes      = "Holds VNets created through the API."
}
