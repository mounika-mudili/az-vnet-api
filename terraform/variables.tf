variable "subscription_id" {
  description = "Subscription the API is deployed into and where it creates VNets."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F-]{36}$", var.subscription_id))
    error_message = "subscription_id must be a GUID."
  }
}

variable "tenant_id" {
  description = "Entra ID tenant that issues access tokens for this API."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F-]{36}$", var.tenant_id))
    error_message = "tenant_id must be a GUID."
  }
}

variable "api_client_id" {
  description = "Client ID (token audience) of the Entra ID app registration protecting the API."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F-]{36}$", var.api_client_id))
    error_message = "api_client_id must be a GUID."
  }
}

variable "vnet_resource_group_name" {
  description = "Resource group the API is allowed to create VNets in."
  type        = string

  validation {
    condition     = length(var.vnet_resource_group_name) > 0 && length(var.vnet_resource_group_name) <= 90
    error_message = "vnet_resource_group_name must be between 1 and 90 characters."
  }
}

variable "function_identity_name" {
  description = "Existing user-assigned managed identity the function app runs as."
  type        = string

  validation {
    condition     = length(var.function_identity_name) > 0
    error_message = "function_identity_name must be set: the identity is expected to exist already."
  }
}

variable "function_identity_resource_group_name" {
  description = "Resource group holding that identity, often owned by the platform team."
  type        = string

  validation {
    condition     = length(var.function_identity_resource_group_name) > 0
    error_message = "function_identity_resource_group_name must be set."
  }
}

variable "manage_identity_role_assignments" {
  description = <<-EOT
    Let this stack grant the identity its two roles. Leave false when the platform team
    already granted them; a duplicate assignment at the same scope fails the apply.
  EOT
  type        = bool
  default     = false
}

variable "create_vnet_resource_group" {
  description = "Create the VNet resource group. Set false when the platform team already owns it."
  type        = bool
  default     = true
}

variable "lock_vnet_resource_group" {
  description = "Put a CanNotDelete lock on the VNet resource group. Needs Owner or User Access Administrator to apply."
  type        = bool
  default     = true
}

variable "environment" {
  description = "Environment name, used in resource names and tags. Only prod is deployed today."
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "environment must be dev, test or prod."
  }
}

variable "workload" {
  description = "Short workload name used in resource names."
  type        = string
  default     = "azvnetapi"

  validation {
    condition     = can(regex("^[a-z0-9]{3,12}$", var.workload))
    error_message = "workload must be 3-12 lowercase alphanumeric characters."
  }
}

variable "location" {
  description = "Azure region for the API resources."
  type        = string
  default     = "westeurope"
}

variable "location_short" {
  description = "Region abbreviation used in resource names, for example weu."
  type        = string
  default     = "weu"

  validation {
    condition     = can(regex("^[a-z0-9]{2,4}$", var.location_short))
    error_message = "location_short must be 2-4 lowercase alphanumeric characters."
  }
}

variable "python_version" {
  description = "Python runtime version of the function app."
  type        = string
  default     = "3.11"
}

variable "log_retention_days" {
  description = "Log Analytics retention in days."
  type        = number
  default     = 30
}

variable "log_daily_quota_gb" {
  description = "Log Analytics ingestion cap in GB per day. Guards against runaway cost."
  type        = number
  default     = 1
}

variable "appinsights_daily_cap_gb" {
  description = "Application Insights ingestion cap in GB per day."
  type        = number
  default     = 1
}

variable "tags" {
  description = "Extra tags merged into the standard tag set."
  type        = map(string)
  default     = {}
}
