import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from kubernetes import client
from kubernetes.client.rest import ApiException
from sqlalchemy.orm import Session

import src.routes.dtos.network_share_dto as dtos
import src.services.kubernetes.pv_pvc_wrapper as pv_pvc
from src.database.database_access import get_db_session
from src.database.repositories.volume_repository import VolumeRepository
from src.routes import authentication
from src.utils import config

router = APIRouter(prefix="/network-shares", tags=["network-shares"])
logger = logging.getLogger(__name__)

_PROBE_IMAGE = "busybox:latest"
_PROBE_TIMEOUT_SECONDS = 90


@router.post("/provision", response_model=dtos.NetworkShareResponse)
async def provision_network_share(
    request: dtos.NetworkShareProvisionRequest,
    db: Session = Depends(get_db_session),
    _=Depends(authentication.require_admin),
):
    namespace = request.namespace or config.K8S_NAMESPACE
    safe = pv_pvc.safe_k8s_name(request.name)
    pv = pv_pvc.pv_name(safe)
    pvc = pv_pvc.pvc_name(safe)
    sc = pv_pvc.storage_class_name(safe)

    v1 = client.CoreV1Api()
    sn, sns = pv_pvc.resolve_or_create_secret(
        v1, request.secret_name, request.secret_namespace, request.username, request.password, safe
    )
    pv_pvc.create_pv(v1, pv, request.share_path, request.storage_size, request.access_modes,
                     request.mount_options, sc, safe, sn, sns)
    pv_pvc.create_pvc(v1, pvc, namespace, request.storage_size, request.access_modes, sc, pv)

    volume_id = str(uuid.uuid4())
    VolumeRepository.create_volume(db, volume_id=volume_id, name=request.name, pvc_name=pvc)

    return dtos.NetworkShareResponse(id=volume_id, name=request.name, pvc_name=pvc,
                                     pv_name=pv, secret_name=sn, namespace=namespace)


@router.get("/", response_model=list[dtos.NetworkShareVolumeResponse])
async def list_network_shares(
    db: Session = Depends(get_db_session),
    _=Depends(authentication.require_admin),
):
    volumes = VolumeRepository.list_volumes(db)
    v1 = client.CoreV1Api()
    share_paths = pv_pvc.list_pv_share_paths(v1)

    result = []
    for vol in volumes:
        pv_n = pv_pvc.pv_name(pv_pvc.safe_k8s_name(vol.name))
        result.append(dtos.NetworkShareVolumeResponse(
            id=vol.id,
            name=vol.name,
            pvc_name=vol.pvc_name,
            share_path=share_paths.get(pv_n, ""),
        ))

    return result


@router.get("/{volume_id}", response_model=dtos.NetworkShareDetailResponse)
async def get_network_share_detail(
    volume_id: str,
    db: Session = Depends(get_db_session),
    _=Depends(authentication.require_admin),
):
    volume = VolumeRepository.get_volume(db, volume_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")

    v1 = client.CoreV1Api()
    pv = pv_pvc.read_pv(v1, volume.name)

    if not pv:
        return dtos.NetworkShareDetailResponse(
            id=volume.id, name=volume.name, pvc_name=volume.pvc_name,
            pv_name=pv_pvc.pv_name(pv_pvc.safe_k8s_name(volume.name)),
            share_path="(PV not found in cluster)", storage_size="",
            namespace=config.K8S_NAMESPACE, access_modes=[], mount_options=[],
            secret_name="", secret_namespace="", pv_status="NotFound", pvc_status="NotFound",
        )

    csi = pv.spec.csi
    share_path = csi.volume_attributes.get("source", "") if csi and csi.volume_attributes else ""
    secret_name, secret_namespace = "", ""
    if csi and csi.node_stage_secret_ref:
        secret_name = csi.node_stage_secret_ref.name or ""
        secret_namespace = csi.node_stage_secret_ref.namespace or ""

    _, namespace, pvc_status = pv_pvc.pvc_info_from_pv(v1, pv)

    return dtos.NetworkShareDetailResponse(
        id=volume.id, name=volume.name, pvc_name=volume.pvc_name,
        pv_name=pv.metadata.name,
        share_path=share_path,
        storage_size=pv.spec.capacity.get("storage", "") if pv.spec.capacity else "",
        namespace=namespace,
        access_modes=pv.spec.access_modes or [],
        mount_options=pv.spec.mount_options or [],
        secret_name=secret_name, secret_namespace=secret_namespace,
        pv_status=pv.status.phase or "Unknown",
        pvc_status=pvc_status,
    )


@router.put("/{volume_id}", response_model=dtos.NetworkShareResponse)
async def update_network_share(
    volume_id: str,
    request: dtos.NetworkShareUpdateRequest,
    db: Session = Depends(get_db_session),
    _=Depends(authentication.require_admin),
):
    volume = VolumeRepository.get_volume(db, volume_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")

    v1 = client.CoreV1Api()
    if request.secret_mode == "keep":
        pv = pv_pvc.read_pv(v1, volume.name)
        if not pv or not pv.spec.csi or not pv.spec.csi.node_stage_secret_ref:
            raise HTTPException(status_code=400, detail="Cannot keep current secret: PV not found in cluster")

        secret_name = pv.spec.csi.node_stage_secret_ref.name or ""
        secret_namespace = pv.spec.csi.node_stage_secret_ref.namespace or "default"
    elif request.secret_mode == "existing":
        if not request.secret_name:
            raise HTTPException(status_code=400, detail="secret_name required when secret_mode is 'existing'")

        secret_name, secret_namespace = request.secret_name, request.secret_namespace
    else:
        new_safe = pv_pvc.safe_k8s_name(request.name)
        secret_name, secret_namespace = pv_pvc.resolve_or_create_secret(
            v1, None, "default", request.username, request.password, new_safe
        )

    old_pv = pv_pvc.read_pv(v1, volume.name)
    old_namespace = config.K8S_NAMESPACE
    if old_pv and old_pv.spec.claim_ref:
        old_namespace = old_pv.spec.claim_ref.namespace or config.K8S_NAMESPACE

    old_safe = pv_pvc.safe_k8s_name(volume.name)
    pv_pvc.delete_pv_and_pvc(v1, pv_pvc.pv_name(old_safe), volume.pvc_name, old_namespace)

    namespace = request.namespace or config.K8S_NAMESPACE
    new_safe = pv_pvc.safe_k8s_name(request.name)
    new_pv = pv_pvc.pv_name(new_safe)
    new_pvc = pv_pvc.pvc_name(new_safe)
    new_sc = pv_pvc.storage_class_name(new_safe)

    pv_pvc.create_pv(v1, new_pv, request.share_path, request.storage_size, request.access_modes,
                     request.mount_options, new_sc, new_safe, secret_name, secret_namespace)
    pv_pvc.create_pvc(v1, new_pvc, namespace, request.storage_size, request.access_modes, new_sc, new_pv)

    VolumeRepository.update_volume(db, volume_id=volume_id, name=request.name, pvc_name=new_pvc)

    return dtos.NetworkShareResponse(id=volume_id, name=request.name, pvc_name=new_pvc,
                                     pv_name=new_pv, secret_name=secret_name, namespace=namespace)


@router.post("/{volume_id}/test", response_model=dtos.NetworkShareTestResponse)
async def test_network_share(
    volume_id: str,
    db: Session = Depends(get_db_session),
    _=Depends(authentication.require_admin),
):
    volume = VolumeRepository.get_volume(db, volume_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")

    v1 = client.CoreV1Api()
    pv = pv_pvc.read_pv(v1, volume.name)
    if not pv:
        return dtos.NetworkShareTestResponse(success=False, message="PV not found in cluster")

    _, namespace, _pvc_status = pv_pvc.pvc_info_from_pv(v1, pv)

    probe_name = f"ns-probe-{pv_pvc.safe_k8s_name(volume.name)[:28]}-{str(uuid.uuid4())[:6]}"

    pod_body = client.V1Pod(
        metadata=client.V1ObjectMeta(name=probe_name, namespace=namespace),
        spec=client.V1PodSpec(
            restart_policy="Never",
            containers=[
                client.V1Container(
                    name="probe",
                    image=_PROBE_IMAGE,
                    command=["sh", "-c", "ls /mnt && echo 'PROBE_SUCCESS'"],
                    volume_mounts=[client.V1VolumeMount(name="share", mount_path="/mnt")],
                )
            ],
            volumes=[
                client.V1Volume(
                    name="share",
                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                        claim_name=volume.pvc_name
                    ),
                )
            ],
        ),
    )

    try:
        v1.create_namespaced_pod(namespace=namespace, body=pod_body)
    except ApiException as e:
        return dtos.NetworkShareTestResponse(success=False, message=f"Could not create probe pod: {e.reason}")

    deadline = time.time() + _PROBE_TIMEOUT_SECONDS
    final_phase = "Unknown"
    while time.time() < deadline:
        time.sleep(3)
        try:
            pod: Any = v1.read_namespaced_pod(name=probe_name, namespace=namespace)
            phase = pod.status.phase or "Unknown"
            if phase in ("Succeeded", "Failed"):
                final_phase = phase
                break
        except ApiException:
            break

    output = None
    try:
        output = v1.read_namespaced_pod_log(name=probe_name, namespace=namespace)
    except ApiException:
        pass

    try:
        v1.delete_namespaced_pod(name=probe_name, namespace=namespace,
                                 body=client.V1DeleteOptions(grace_period_seconds=0))
    except ApiException:
        pass

    output_str = output.strip() if output else None

    if final_phase == "Succeeded" and output and "PROBE_SUCCESS" in output:
        return dtos.NetworkShareTestResponse(success=True, message="Share is accessible", output=output_str)

    if final_phase == "Unknown":
        return dtos.NetworkShareTestResponse(
            success=False,
            message=f"Probe timed out after {_PROBE_TIMEOUT_SECONDS}s",
            output=output_str,
        )

    return dtos.NetworkShareTestResponse(success=False, message=f"Probe failed (phase: {final_phase})",
                                         output=output_str)


@router.delete("/{volume_id}")
async def delete_network_share(
    volume_id: str,
    db: Session = Depends(get_db_session),
    _=Depends(authentication.require_admin),
):
    volume = VolumeRepository.get_volume(db, volume_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")

    v1 = client.CoreV1Api()
    pv = pv_pvc.read_pv(v1, volume.name)
    ns = config.K8S_NAMESPACE
    if pv and pv.spec.claim_ref:
        ns = pv.spec.claim_ref.namespace or config.K8S_NAMESPACE

    pv_pvc.delete_pv_and_pvc(v1, pv_pvc.pv_name(pv_pvc.safe_k8s_name(volume.name)), volume.pvc_name, ns)
    VolumeRepository.delete_volume(db, volume_id)
    return {"message": "Network share deleted successfully"}
