// Partial configuration: terraform init -backend-config=config/prod.backend.hcl
terraform {
  backend "azurerm" {
    use_azuread_auth = true
  }
}
