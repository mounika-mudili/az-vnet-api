import logging

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from app.auth.entra import Principal, require_authenticated_user
from app.dependencies import get_vnet_service
from app.errors import (
    ProvisioningError,
    ResourceGroupNotFoundError,
    ResourceGroupNotPermittedError,
    VnetAlreadyRecordedError,
)
from app.models.schemas import VnetCreateRequest, VnetRecord
from app.services.vnet_service import VnetService
from app.storage.repository import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Azure VNet API",
    version="1.0.0",
    description=(
        "Creates an Azure virtual network with multiple subnets, stores the result, and "
        "returns the stored data. Requires a Microsoft Entra ID access token; every "
        "authenticated caller has full access."
    ),
)


@app.get("/health", tags=["meta"], summary="Liveness probe (no authentication)")
def health() -> dict:
    return {"status": "ok"}


@app.post(
    "/vnets",
    response_model=VnetRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["vnets"],
    summary="Create a VNet with multiple subnets and store the result",
)
def create_vnet(
    request: VnetCreateRequest,
    principal: Principal = Depends(require_authenticated_user),
    service: VnetService = Depends(get_vnet_service),
) -> VnetRecord:
    return service.create(request, principal)


@app.get(
    "/vnets",
    response_model=list[VnetRecord],
    tags=["vnets"],
    summary="List stored VNet creations",
)
def list_vnets(
    resource_group: str | None = Query(default=None, description="Only return VNets recorded in this resource group."),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    _: Principal = Depends(require_authenticated_user),
    service: VnetService = Depends(get_vnet_service),
) -> list[VnetRecord]:
    return service.list(resource_group=resource_group, limit=limit)


@app.get(
    "/vnets/{record_id}",
    response_model=VnetRecord,
    tags=["vnets"],
    summary="Get one stored VNet creation",
)
def get_vnet(
    record_id: str,
    _: Principal = Depends(require_authenticated_user),
    service: VnetService = Depends(get_vnet_service),
) -> VnetRecord:
    record = service.get(record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No stored VNet with id '{record_id}'")
    return record


@app.post(
    "/vnets/{record_id}/refresh",
    response_model=VnetRecord,
    tags=["vnets"],
    summary="Re-read the VNet from Azure and update the stored record",
)
def refresh_vnet(
    record_id: str,
    _: Principal = Depends(require_authenticated_user),
    service: VnetService = Depends(get_vnet_service),
) -> VnetRecord:
    record = service.refresh(record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No stored VNet with id '{record_id}'")
    return record


@app.exception_handler(VnetAlreadyRecordedError)
def _handle_conflict(_: Request, exc: VnetAlreadyRecordedError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.exception_handler(ResourceGroupNotFoundError)
def _handle_missing_group(_: Request, exc: ResourceGroupNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(ResourceGroupNotPermittedError)
def _handle_forbidden_scope(_: Request, exc: ResourceGroupNotPermittedError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})


@app.exception_handler(ProvisioningError)
def _handle_provisioning(_: Request, exc: ProvisioningError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": f"Azure could not create the network: {exc}"},
    )
