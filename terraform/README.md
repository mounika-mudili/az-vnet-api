# Infrastructure

One stack, deploying the whole API. The storage account behind the remote state is created
beforehand by [`scripts/bootstrap-state.sh`](../scripts/bootstrap-state.sh) rather than by Terraform,
for the reasons in that script's header.

There is one environment, `prod`, and its values live in `environments/prod.tfvars`. Adding a second
means adding a file in `environments/` and one in `config/`; nothing in the stack itself is
environment-specific.

```
terraform/
  backend.tf          remote state, configured at init time
  providers.tf        azurerm provider
  versions.tf         Terraform and provider version constraints
  variables.tf        inputs, with validation
  locals.tf           naming convention and tag set
  resource_groups.tf  API group, plus the group VNets are created in
  storage.tf          storage account and the results table
  function_app.tf     consumption plan and function app
  monitoring.tf       Log Analytics, Application Insights, diagnostics
  identity.tf         the identity the app runs as, and optional role assignments
  outputs.tf
  config/             backend configuration, one file per environment
  environments/       variable values, one file per environment
```

## What you supply

In `environments/prod.tfvars`:

| Variable | Meaning |
|---|---|
| `vnet_resource_group_name` | Resource group the API is allowed to create VNets in |
| `create_vnet_resource_group` | `true` to create that group, `false` if it already exists |
| `lock_vnet_resource_group` | `true` to add a `CanNotDelete` lock to that group |

At plan time, because they are tenant-specific and have no business being committed as
placeholders: `subscription_id` (where the API lives and creates VNets), `tenant_id` (the Entra ID
tenant issuing API tokens), and `api_client_id` (the app registration client ID used as the token
audience). All three are validated as GUIDs, so a blank value stops the plan.

`vnet_resource_group_name` is the value callers pass as `resource_group` in `POST /vnets`. It is the
only scope where the API's identity holds `Network Contributor`, so a request naming a different
resource group is rejected with `403` rather than provisioned.

Set `create_vnet_resource_group = false` when a platform team owns the group; Terraform then reads
it with a data source and only adds the role assignment.

Everything else has a default: naming comes from `workload`, `environment`, and `location_short`, so
`prod` in West Europe produces `rg-azvnetapi-prod-weu`, `func-azvnetapi-prod-weu-<suffix>`, and so on.

## First-time setup

State lives in Azure, so create its home first. Once per subscription:

```bash
scripts/bootstrap-state.sh \
  --subscription <subscription id> \
  --state-readers <object id of the Entra group that owns state> \
  --ci-principal <object id of the deploying service principal>
```

That creates a resource group and a storage account with blob versioning, 30-day soft delete, and a
`tfstate` container, then prints the block to paste into `config/prod.backend.hcl`.

`Storage Blob Data Contributor` on that account goes to the group you name, and to the CI principal if
you pass one. The stack authenticates to state with Entra ID, not an account key, and subscription
Owner does not include data-plane access, so without that role `terraform init` fails. Point it at a
group and the state stays reachable when someone leaves.
Assignments take a minute or two to propagate.

The script is idempotent and derives the account name from the subscription id, so a second run finds
the existing account instead of building another.

## Deploy

```bash
cd terraform
terraform init -backend-config=config/prod.backend.hcl

ids=(-var="subscription_id=<subscription id>" \
     -var="tenant_id=<tenant id>" \
     -var="api_client_id=<api app registration id>")

terraform plan  -var-file=environments/prod.tfvars "${ids[@]}"
terraform apply -var-file=environments/prod.tfvars "${ids[@]}"

cd ..
func azure functionapp publish $(terraform -chdir=terraform output -raw function_app_name)
```

State for this environment is the blob `az-vnet-api/prod.tfstate`, set in
`config/prod.backend.hcl` and repeated as `TF_STATE_KEY` in the deploy workflow. Those two have to
agree; if they drift, a local apply and a pipeline apply build the same stack twice against separate
state. A second environment would get its own key and its own backend config file.

CI runs the same sequence, taking the three ids from the `prod` GitHub environment and applying from a
saved plan file. See [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml).

## Notes

The backend takes a blob lease for the length of a run, so two people or pipelines applying at once
can't corrupt state.

## Identity

The app runs as a user-assigned managed identity that already exists, looked up in `identity.tf` by
name and resource group. It is not created here and not destroyed with the stack, which is the point:
the platform team owns it, its two role assignments outlive any rebuild of the API, and a `terraform
destroy` cannot orphan them. `Network Contributor` on the VNet resource group and `Storage Table Data
Contributor` on the results storage account are assumed to be granted already; set
`manage_identity_role_assignments = true` to have this stack grant them instead, which will fail if
they exist.

Terraform passes the identity's client id to the app as `MANAGED_IDENTITY_CLIENT_ID`. A function app
can carry several identities, so the SDK has to be told which one to use, and the app registration
that guards the API is a different thing entirely — it goes in as `ENTRA_API_CLIENT_ID`. Neither is
called `AZURE_CLIENT_ID`, because `DefaultAzureCredential` reads that name as the identity to
authenticate as and would silently try the wrong one.

If the identity lives in another subscription, `Owner` here is not sufficient: attaching it needs
`Microsoft.ManagedIdentity/userAssignedIdentities/assign/action` on the identity itself.

The function app has no secrets in its configuration, with one exception: the Functions runtime wants
the storage account key on a Consumption plan, and that key lives in state and app settings, never in
the repo. Moving runtime storage onto its own account, or onto the identity, is the next step there.

Cost stays low by design: per-execution billing, a table instead of a database, and daily ingestion
caps on Log Analytics and Application Insights. Idle cost is close to nothing.

### Deleting things

`lock_vnet_resource_group` defaults to `true`, which puts a `CanNotDelete` lock on the group holding
caller-created VNets. Those networks are runtime data Terraform never created, and the lock is what
stops someone clearing the group from the portal. Applying it needs `Microsoft.Authorization` write
access, which `Contributor` does not include, so this is the one thing in the stack that relies on the
deploying principal being `Owner`.

`prevent_deletion_if_contains_resources` is off, and that is not an oversight. Application Insights
creates smart detector alert rules that never land in state; with the flag on, `terraform destroy`
fails on the API's own resource group because Azure still sees resources in it. The lock covers the
group that actually needs protecting.

Empty the VNet resource group before destroying. Terraform drops the lock first, then takes the group
and everything still inside it.
