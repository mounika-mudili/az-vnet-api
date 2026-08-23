#!/usr/bin/env bash
#
# Creates the storage account that holds Terraform state for the API stack.
#
# Usage:
#   scripts/bootstrap-state.sh \
#     --subscription <id> \
#     --state-readers <group object id> \
#     [--ci-principal <service principal object id>] \
#     [--location westeurope] [--workload azvnetapi] [--container tfstate] [--no-lock]

set -euo pipefail

SUBSCRIPTION=""
STATE_READERS=""
CI_PRINCIPAL=""
LOCATION="westeurope"
WORKLOAD="azvnetapi"
CONTAINER="tfstate"
LOCK=true

ROLE="Storage Blob Data Contributor"

die() {
  echo "error: $*" >&2
  exit 1
}

usage() {
  sed -n '3,19p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --subscription) SUBSCRIPTION="${2:-}"; shift 2 ;;
    --state-readers) STATE_READERS="${2:-}"; shift 2 ;;
    --ci-principal) CI_PRINCIPAL="${2:-}"; shift 2 ;;
    --location) LOCATION="${2:-}"; shift 2 ;;
    --workload) WORKLOAD="${2:-}"; shift 2 ;;
    --container) CONTAINER="${2:-}"; shift 2 ;;
    --no-lock) LOCK=false; shift ;;
    -h|--help) usage 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ -n "$SUBSCRIPTION" ]] || usage 1
[[ -n "$STATE_READERS" ]] || die "--state-readers is required: the Entra group that may read and write state"
command -v az >/dev/null || die "the Azure CLI is not on PATH"
az account show --only-show-errors >/dev/null 2>&1 || die "run 'az login' first"

# Storage account names are globally unique and only 24 characters, so the suffix is a
# hash of the subscription.

if command -v sha256sum >/dev/null; then
  SUFFIX="$(printf '%s' "$SUBSCRIPTION" | sha256sum | cut -c1-6)"
else
  SUFFIX="$(printf '%s' "$SUBSCRIPTION" | shasum -a 256 | cut -c1-6)"
fi

RESOURCE_GROUP="rg-${WORKLOAD}-tfstate"
ACCOUNT="st${WORKLOAD}tfstate${SUFFIX}"
ACCOUNT="${ACCOUNT:0:24}"
TAGS=("workload=${WORKLOAD}" "purpose=terraform-state" "managed_by=bootstrap-script" "repository=az-vnet-api")

echo "subscription:   ${SUBSCRIPTION}"
echo "resource group: ${RESOURCE_GROUP}"
echo "account:        ${ACCOUNT}"
echo

az account set --subscription "$SUBSCRIPTION"

echo "==> resource group"
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --tags "${TAGS[@]}" \
  --only-show-errors --output none

echo "==> storage account"
az storage account create \
  --name "$ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --min-tls-version TLS1_2 \
  --https-only true \
  --allow-blob-public-access false \
  --allow-cross-tenant-replication false \
  --default-to-oauth-authentication true \
  --tags "${TAGS[@]}" \
  --only-show-errors --output none

# Versioning and soft delete are what let you recover a state file that an interrupted
# apply left truncated.
echo "==> blob versioning and soft delete"
az storage account blob-service-properties update \
  --account-name "$ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --enable-versioning true \
  --enable-delete-retention true --delete-retention-days 30 \
  --enable-container-delete-retention true --container-delete-retention-days 30 \
  --only-show-errors --output none

echo "==> container '${CONTAINER}'"
az storage container create \
  --name "$CONTAINER" \
  --account-name "$ACCOUNT" \
  --auth-mode key \
  --only-show-errors --output none

ACCOUNT_ID="$(az storage account show \
  --name "$ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query id --output tsv --only-show-errors)"

# Terraform initialises the backend with use_azuread_auth, so this is a data-plane role.
# Subscription Owner does not include it.
grant() {
  local object_id="$1" principal_type="$2" label="$3"

  local existing
  existing="$(az role assignment list \
    --assignee "$object_id" \
    --role "$ROLE" \
    --scope "$ACCOUNT_ID" \
    --query "length(@)" --output tsv --only-show-errors)"

  if [[ "$existing" != "0" ]]; then
    echo "==> ${label} already holds '${ROLE}'"
    return
  fi

  echo "==> granting '${ROLE}' to ${label}"
  az role assignment create \
    --assignee-object-id "$object_id" \
    --assignee-principal-type "$principal_type" \
    --role "$ROLE" \
    --scope "$ACCOUNT_ID" \
    --only-show-errors --output none
}

grant "$STATE_READERS" Group "group ${STATE_READERS}"
if [[ -n "$CI_PRINCIPAL" ]]; then
  grant "$CI_PRINCIPAL" ServicePrincipal "CI principal ${CI_PRINCIPAL}"
fi

if [[ "$LOCK" == true ]]; then
  echo "==> delete lock"
  az lock create \
    --name protect-terraform-state \
    --lock-type CanNotDelete \
    --resource-group "$RESOURCE_GROUP" \
    --notes "Terraform state must not be deleted" \
    --only-show-errors --output none
fi

cat <<EOF

Done. Put this in terraform/config/prod.backend.hcl:

resource_group_name  = "${RESOURCE_GROUP}"
storage_account_name = "${ACCOUNT}"
container_name       = "${CONTAINER}"
subscription_id      = "${SUBSCRIPTION}"
key                  = "az-vnet-api/prod.tfstate"

Role assignments take a minute or two to propagate before 'terraform init' will work.
EOF
