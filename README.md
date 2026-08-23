# Azure VNet API

Creates an Azure virtual network with a set of subnets, records what it created, and serves those
records back. It runs on Azure Functions, checks an Entra ID token on every call, and holds no
credentials of its own.

The exercise behind it asked for an API on Azure services that creates a VNet with multiple subnets,
stores the results, and lets you read the created resources back; Python; protected by an
authentication layer; and authorization open to every authenticated user. That last point is taken
literally — there are no roles or groups, and a valid token is the only thing the API checks.

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/vnets` | Create a VNet with its subnets and store the result |
| `GET` | `/vnets` | List stored creations, newest first |
| `GET` | `/vnets/{id}` | Fetch one stored creation |
| `POST` | `/vnets/{id}/refresh` | Re-read the VNet from Azure and update the record |
| `GET` | `/health` | Liveness probe, the only route without auth |

OpenAPI docs are at `/docs`.

`GET /vnets` accepts `resource_group` and `limit` (default 50, maximum 200). The resource group
filter maps onto a Table Storage partition key, so it reads one partition instead of scanning.

The refresh route exists because records go stale. Anyone with rights on the resource group can
change or delete a VNet without coming through this API. Refresh reads the network back from Azure,
updates the provisioning state and subnets, and stamps `last_synced_at`. A network that has been
deleted is marked `"status": "Deleted"` instead of having its record dropped — the table is a log of
what the API did, and deleting rows from it loses that.

### Creating one

```bash
curl -X POST https://<api-host>/vnets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "demo-vnet",
    "resource_group": "rg-network-demo",
    "location": "westeurope",
    "address_space": ["10.0.0.0/16"],
    "subnets": [
      {"name": "app-subnet", "address_prefix": "10.0.1.0/24"},
      {"name": "data-subnet", "address_prefix": "10.0.2.0/24"}
    ]
  }'
```

`201` on success. The body below is also what the `GET` routes return:

```json
{
  "id": "8244221082182-cd6b916aaa6746c8bfeb6c2eab7e0e8d",
  "name": "demo-vnet",
  "resource_group": "rg-network-demo",
  "subscription_id": "...",
  "location": "westeurope",
  "address_space": ["10.0.0.0/16"],
  "subnets": [
    {
      "name": "app-subnet",
      "address_prefix": "10.0.1.0/24",
      "resource_id": ".../virtualNetworks/demo-vnet/subnets/app-subnet"
    },
    {
      "name": "data-subnet",
      "address_prefix": "10.0.2.0/24",
      "resource_id": ".../virtualNetworks/demo-vnet/subnets/data-subnet"
    }
  ],
  "vnet_resource_id": ".../virtualNetworks/demo-vnet",
  "status": "Succeeded",
  "created_by": "user@example.com",
  "created_at": "2026-08-22T13:49:17.815833Z",
  "last_synced_at": "2026-08-22T13:49:17.815833Z"
}
```

### When it says no

| Code | Meaning |
|---|---|
| `401` | Token missing, expired, malformed, or from another tenant |
| `403` | The API's identity has no network rights in the requested resource group |
| `404` | Unknown record id, or the target resource group does not exist |
| `409` | This API already recorded a VNet with that name in that group |
| `422` | Request failed validation |
| `502` | Azure rejected or failed the deployment |

Validation runs before anything is sent to Azure. CIDR blocks must be well formed and free of host
bits, there must be at least two subnets, each subnet has to sit inside the address space, and
subnets may not overlap or reuse a name.

## Authentication

The token's signature, expiry, audience, and issuing tenant are checked against the Entra ID JWKS
endpoint. Signing keys are cached, so this is not an outbound call per request.

Register the API once:

```bash
az ad app create --display-name "az-vnet-api" --sign-in-audience AzureADMyOrg
# take the appId from the output
az ad app update --id <appId> --identifier-uris "api://<appId>"
```

Then set `AZURE_TENANT_ID` and `ENTRA_API_CLIENT_ID` (the `appId`). Tokens with an `aud` of `<appId>`
or `api://<appId>` are accepted. That setting is not called `AZURE_CLIENT_ID` for a reason worth
knowing: `DefaultAzureCredential` reads `AZURE_CLIENT_ID` as the client id of a user-assigned managed
identity, so putting the API's registration there makes every outbound Azure call authenticate as an
identity that isn't attached to the app.

## Running it locally

There is no offline mode: the API talks to Azure wherever it runs, so a local run needs a
subscription, a storage account and a login.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
az login
cp .env.example .env          # fill in all five values
uvicorn app.main:app --reload
```

`DefaultAzureCredential` picks up your CLI login here and the user-assigned identity once deployed, so
nothing in the code changes between the two — leave `MANAGED_IDENTITY_CLIENT_ID` blank locally and the
chain falls through to the CLI. Your own account needs the same two roles that identity has: Network
Contributor on the VNet resource group and Storage Table Data Contributor on the storage account.

Every setting in `.env.example` is required and validated on the first request. Leave one out and you
get a startup error naming it, which is preferable to a request that fails halfway through with an
Azure SDK stack trace. Calls still need a real token — there is no switch to turn authentication off,
because a switch like that eventually ends up enabled somewhere it shouldn't be. To get one for
yourself:

```bash
az account get-access-token --resource api://<appId> --query accessToken -o tsv
```

## Tests and checks

```bash
pytest
ruff check . && ruff format --check .
mypy
shellcheck scripts/*.sh
```

CI runs the same four on every push. Python stays on 3.11 to match the Functions runtime, and
dependencies stay in `requirements.txt` because the Oryx build installs from it. Mypy covers `app/`
only — it earned its place by catching a `create_vnet` call that passed a hand-built dict where the
SDK overloads want `VirtualNetwork`, which typed as `Any` would have failed against real Azure.

The suite needs no subscription or credentials. Azure is stood in for by `tests/fakes.py`, injected
through FastAPI's dependency overrides — they live under `tests/`, so there is nothing fake in what
gets deployed. Covered: request validation, the 401 path on each protected route, the
Azure-error-to-status-code mapping, listing filters and limits, and a refresh of a VNet that was
deleted behind the API's back.

## Deploying

One environment, `prod`. Terraform state lives in Azure, so its storage account gets created first,
by a script rather than by Terraform. [terraform/README.md](terraform/README.md) has the detail.

```bash
# once per subscription; prints the backend block to paste into
# terraform/config/prod.backend.hcl
scripts/bootstrap-state.sh --subscription <id> --state-readers <group object id>

# the stack
cd terraform
terraform init -backend-config=config/prod.backend.hcl
terraform apply -var-file=environments/prod.tfvars \
  -var="subscription_id=<id>" -var="tenant_id=<id>" -var="api_client_id=<id>"

cd ..
func azure functionapp publish $(terraform -chdir=terraform output -raw function_app_name)
```

`vnet_resource_group_name` lives in `environments/prod.tfvars`; the three ids are passed at plan time
so the repo holds no tenant-specific values. That resource group is what callers pass as
`resource_group`, and it is the only scope where the function's identity holds `Network Contributor`.
If a platform team already owns the group, set `create_vnet_resource_group = false` and they keep
ownership of its deletion lock too.

Terraform builds the API's own resource group — function app, storage account with the results table,
Log Analytics, Application Insights — and attaches an existing user-assigned managed identity, named
by `function_identity_name`, that already holds `Network Contributor` on the VNet group and `Storage
Table Data Contributor` on the storage account. It does not create that identity or its roles; the
platform team owns both, which is why the roles survive a rebuild of this stack. Nothing in the app
configuration is a secret.

## CI

[`ci.yml`](.github/workflows/ci.yml) runs ruff, shellcheck, pytest, `terraform fmt` and
`terraform validate` on pushes and pull requests. [`deploy.yml`](.github/workflows/deploy.yml) is manual: Terraform plan and
apply, publish the function, then poll `/health`.

Both sign in with a federated credential, so there is no client secret or publish profile in the
repo. Create it once against the deploying app registration:

```bash
az ad app federated-credential create --id <deployAppId> --parameters '{
  "name": "github-prod",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:<owner>/<repo>:environment:prod",
  "audiences": ["api://AzureADTokenExchange"]
}'
```

That registration is assumed to hold `Owner` on the subscription, which is what lets it create
resource groups, hand the function app its two roles, and place the deletion lock. Owner is a
control-plane role and does not reach data, so its access to the Terraform state blobs is granted
separately by the bootstrap script. Ids come from the GitHub environment, not from the committed
tfvars, and the plan is written to a file and applied from it, so what was reviewed is what runs.

## Why it looks like this

Table Storage over Cosmos DB or PostgreSQL: the records are small, written once, and read by
id. Table Storage does that for cents a month, while Cosmos adds an account to operate and Postgres
bills for a server that is idle most of the time. Same reasoning for the Consumption plan over an
App Service plan or Container Apps — the traffic is intermittent, so paying per execution wins.

The table is not a substitute for Azure. Resource Manager stays the source of truth for the network;
the table records what the API was asked to do, who asked, and what came back, which is not
something ARM keeps. Terraform state isn't the place for it either: state describes the API's own
infrastructure, and caller-created VNets are runtime data.

Record ids are an inverted millisecond timestamp plus a random suffix, which makes them usable as
Table Storage row keys. Rows come back in key order, so the newest records in a resource group arrive
first without a sort, and two creations in the same millisecond still get different ids.

A couple of smaller things. Filter values are passed as `parameters=` and never formatted into the
filter string. The route handlers are plain `def`, not `async def`, because the Azure SDKs block —
FastAPI runs sync handlers in a threadpool, whereas blocking inside an `async` handler would stall
the loop for everyone else. And the VNet and its subnets are created in one ARM call, so a failure
can't leave a network with half its subnets.

## Assumptions

The brief is short, so here is how I read it. None of this is forced by Azure; it can all be changed.

Storing "the results" means keeping an inventory of what this API did, not mirroring Azure. Reading
them back is therefore answered from the table, with `/refresh` for callers who need to know a record
still matches reality. "Multiple subnets" is enforced as at least two. Authorization being open to
all authenticated users means there is no authorization code at all: any valid token can read records
somebody else created. Create and read are the whole surface — I did not add a delete endpoint,
because tearing down a network other things may depend on is not a decision a bearer token should be
making.

On tokens: callers get their own from Entra ID, and the API has no login route, no token issuing, and
no user store. Tokens are RS256 access tokens for this API's registration, single tenant, v1.0 or v2.0
issuer. Multi-tenant, B2C, and personal Microsoft accounts are out of scope. The identity in the
token is used for `created_by` and nothing else. Function-level keys are off deliberately: the token
is the auth layer, and a shared key in the URL alongside it would only weaken things.

On the networks: the subscription is fixed by configuration, and the identity has rights in exactly
one resource group, so a caller naming anything else is refused by Azure rather than by us. I assume
the caller already owns the address space they ask for — the API checks that a request is internally
consistent, but nothing here checks the range against a hub, an IPAM system, or peered networks. That
belongs upstream in a landing zone. Creating a VNet is quick, so the request waits for it instead of
returning a job id. Nothing beyond the VNet and its subnets is created; NSGs, route tables, peering
and delegations are the platform team's.

Two details worth being explicit about, because they are easy to assume otherwise. The `409` is
checked against this API's own records, not against Azure, so a network created outside the API and
then requested through it gets updated by ARM, not rejected. And two identical requests
arriving at the same instant can both pass that check, since there is no distributed lock — ARM makes
the second an update, so you still end up with one network.

On identity: the function app runs as a user-assigned managed identity that already exists, created and
held by the platform team, already carrying `Network Contributor` on the VNet resource group and
`Storage Table Data Contributor` on the results storage account. Terraform looks it up by name and
attaches it, and `manage_identity_role_assignments` stays `false` so the stack does not try to grant
what it has been given. A user-assigned identity rather than system-assigned is the landing-zone
shape: the roles are granted once, by whoever is allowed to grant them, and they survive this stack
being destroyed and rebuilt. It also means the API's permissions are auditable in one place that
doesn't move when the app does. Nothing in the API decides what it may reach — the identity does, and
that is the whole authorization story on the Azure side.

On who deploys it: the pipeline's app registration is assumed to be `Owner` on the target
subscription. That is more than a one-shot `terraform apply` strictly needs now that role assignments
are the platform team's — resource groups only need `Contributor` — but the `CanNotDelete` lock on the
VNet group needs `Microsoft.Authorization/*/write`, which `Contributor` excludes. Owner is a
deployment-time assumption and not how the API runs; at runtime it is the two roles above and nothing
else. Two things Owner does not cover: the Terraform state blobs, because it is a control-plane role
and data access comes from the bootstrap script, and attaching an identity that lives in a different
subscription. If Owner isn't on offer, `Contributor` plus `User Access Administrator` is the
equivalent pair, or the lock comes out of the stack and someone requests it separately.

On storage and operations: resource group names are lowercased into the partition key, matching
Azure's own case-insensitivity. Listing is bounded by `limit` with no continuation token, which
assumes a moderate number of records per group. Records are kept indefinitely. They are
zone-redundant within the region, not geo-redundant, and reached over the public endpoint — private
endpoints would need a plan with VNet integration. There is one state file, applies are serialised by
its blob lease, and Application Insights sampling plus the daily caps mean telemetry is lossy under
load, which is the trade for a small bill.

## Not included

There is no delete endpoint, so cleanup happens in Azure or through Terraform. Creation is
synchronous, which suits a VNet but would need a queue for anything slower. Reconciliation happens on
demand, not continuously, so a record is only as current as its `last_synced_at`. The function
still authenticates to its own runtime storage with an access key; `storage_uses_managed_identity`
would remove that, at the cost of a role assignment that has to propagate before the first cold
start.

## Layout

```
app/
  main.py                   # the app and its routes
  auth/entra.py             # token validation
  models/schemas.py         # request/response models, CIDR validation
  services/azure_network.py # Azure SDK calls and error mapping
  services/vnet_service.py  # create, store, retrieve, refresh
  storage/repository.py     # Table Storage
  config.py, dependencies.py, errors.py
function_app.py             # Functions entry point
scripts/                    # bootstrap-state.sh, run once per subscription
terraform/                  # infrastructure, see terraform/README.md
tests/                      # fakes.py stands in for Azure
pyproject.toml              # ruff, mypy, pytest
```
