resource "random_string" "suffix" {
  length  = 5
  special = false
  upper   = false
  numeric = true

  // Keeps names stable unless one of these actually changes.
  keepers = {
    workload    = var.workload
    environment = var.environment
    location    = var.location
  }
}

locals {
  name_suffix = "${var.workload}-${var.environment}-${var.location_short}"

  resource_group_name = "rg-${local.name_suffix}"
  function_app_name   = "func-${local.name_suffix}-${random_string.suffix.result}"
  service_plan_name   = "plan-${local.name_suffix}"
  workspace_name      = "log-${local.name_suffix}"
  app_insights_name   = "appi-${local.name_suffix}"

  // Storage account names allow 3-24 lowercase alphanumeric characters only.
  storage_account_name = substr(
    "st${var.workload}${var.environment}${var.location_short}${random_string.suffix.result}",
    0,
    24,
  )

  table_name = "vnetcreations"

  tags = merge(
    {
      workload    = var.workload
      environment = var.environment
      managed_by  = "terraform"
      repository  = "az-vnet-api"
    },
    var.tags,
  )

  vnet_resource_group_id = var.create_vnet_resource_group ? (
    azurerm_resource_group.vnets[0].id
  ) : data.azurerm_resource_group.vnets[0].id
}
