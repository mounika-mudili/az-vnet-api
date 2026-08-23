environment    = "prod"
location       = "westeurope"
location_short = "weu"

# subscription_id, tenant_id and api_client_id are deliberately absent. They differ per
# tenant and would sit here as placeholders nobody notices, so they are passed at plan
# time: -var flags locally, GitHub environment variables in the deploy workflow. All three
# are validated as GUIDs, so a blank one fails the plan rather than the deployment.

# The identity the function app runs as. It exists already, with Network Contributor on
# the VNet group and Storage Table Data Contributor on the results storage account, so
# manage_identity_role_assignments stays false and this stack only attaches it.
function_identity_name                = "id-azvnetapi-prod-weu"
function_identity_resource_group_name = "rg-platform-identities-prod-weu"

# Resource group the API is allowed to create VNets in. Set create to false when a
# platform team already owns the group; Terraform then only adds the role assignment.
vnet_resource_group_name   = "rg-azvnetapi-networks-prod-weu"
create_vnet_resource_group = true

# The VNets callers create are runtime data, so guard the group against a stray
# delete from the portal or CLI. Terraform still tears it down, lock first.
lock_vnet_resource_group = true

log_retention_days       = 30
log_daily_quota_gb       = 1
appinsights_daily_cap_gb = 1

tags = {
  cost_center = "engineering"
  owner       = "platform-team"
  criticality = "medium"
}
