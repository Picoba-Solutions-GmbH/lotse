import base64
import logging
import time
from typing import Any

from fastapi import HTTPException
from kubernetes import client
from kubernetes.client.rest import ApiException

from src.utils import config

logger = logging.getLogger(__name__)


def safe_k8s_name(name: str) -> str:
    return name.lower().replace("_", "-").replace(" ", "-").replace("/", "-")


def pv_name(safe_name: str) -> str:
    return f"pv-{safe_name}"


def pvc_name(safe_name: str) -> str:
    return f"pvc-{safe_name}"


def storage_class_name(safe_name: str) -> str:
    return f"scm-{safe_name}"


def resolve_or_create_secret(
    v1: client.CoreV1Api,
    request_secret_name: str | None,
    request_secret_namespace: str,
    username: str | None,
    password: str | None,
    safe_name: str,
) -> tuple[str, str]:
    if request_secret_name:
        return request_secret_name, request_secret_namespace

    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail="Either secret_name or username and password must be provided",
        )

    secret_name = f"cifscreds-{safe_name}"
    secret_namespace = "default"
    secret_body = client.V1Secret(
        metadata=client.V1ObjectMeta(name=secret_name, namespace=secret_namespace),
        type="Opaque",
        data={
            "username": base64.b64encode(username.encode()).decode(),
            "password": base64.b64encode(password.encode()).decode(),
        },
    )
    try:
        v1.create_namespaced_secret(namespace=secret_namespace, body=secret_body)
    except ApiException as e:
        if e.status == 409:
            logger.info("Secret %s already exists, reusing.", secret_name)
        else:
            raise HTTPException(status_code=500, detail=f"Failed to create secret: {e.reason}")

    return secret_name, secret_namespace


def create_pv(
    v1: client.CoreV1Api,
    pv_name_: str,
    share_path: str,
    storage_size: str,
    access_modes: list[str],
    mount_options: list[str],
    storage_class_name_: str,
    volume_handle: str,
    secret_name: str,
    secret_namespace: str,
) -> None:
    pv_body = client.V1PersistentVolume(
        metadata=client.V1ObjectMeta(name=pv_name_),
        spec=client.V1PersistentVolumeSpec(
            access_modes=access_modes,
            capacity={"storage": storage_size},
            csi=client.V1CSIPersistentVolumeSource(
                driver="smb.csi.k8s.io",
                volume_handle=volume_handle,
                volume_attributes={"source": share_path},
                node_stage_secret_ref=client.V1SecretReference(
                    name=secret_name,
                    namespace=secret_namespace,
                ),
            ),
            mount_options=mount_options,
            persistent_volume_reclaim_policy="Retain",
            storage_class_name=storage_class_name_,
            volume_mode="Filesystem",
        ),
    )
    try:
        v1.create_persistent_volume(body=pv_body)
    except ApiException as e:
        if e.status != 409:
            raise HTTPException(status_code=500, detail=f"Failed to create PersistentVolume: {e.reason}")


def create_pvc(
    v1: client.CoreV1Api,
    pvc_name_: str,
    namespace: str,
    storage_size: str,
    access_modes: list[str],
    storage_class_name_: str,
    bound_pv_name: str,
) -> None:
    pvc_body = client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(name=pvc_name_, namespace=namespace),
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=access_modes,
            resources=client.V1VolumeResourceRequirements(requests={"storage": storage_size}),
            storage_class_name=storage_class_name_,
            volume_name=bound_pv_name,
            volume_mode="Filesystem",
        ),
    )
    try:
        v1.create_namespaced_persistent_volume_claim(namespace=namespace, body=pvc_body)
    except ApiException as e:
        if e.status != 409:
            raise HTTPException(status_code=500, detail=f"Failed to create PersistentVolumeClaim: {e.reason}")


def read_pv(v1: client.CoreV1Api, volume_name: str) -> Any:
    pv_n = pv_name(safe_k8s_name(volume_name))
    try:
        return v1.read_persistent_volume(name=pv_n)
    except ApiException as e:
        if e.status == 404:
            return None
        raise HTTPException(status_code=500, detail=f"K8s error reading PV: {e.reason}")


def pvc_info_from_pv(v1: client.CoreV1Api, pv: Any) -> tuple[str, str, str]:
    if pv.spec.claim_ref:
        ns = pv.spec.claim_ref.namespace or config.K8S_NAMESPACE
        name = pv.spec.claim_ref.name or ""
        try:
            pvc: Any = v1.read_namespaced_persistent_volume_claim(name=name, namespace=ns)
            return name, ns, pvc.status.phase or "Unknown"
        except ApiException:
            return name, ns, "Unknown"
    return "", config.K8S_NAMESPACE, "Unknown"


def delete_pv_and_pvc(v1: client.CoreV1Api, pv_name_: str, pvc_name_: str, namespace: str) -> None:
    try:
        v1.delete_namespaced_persistent_volume_claim(name=pvc_name_, namespace=namespace)
    except ApiException as e:
        if e.status != 404:
            logger.warning("Could not delete PVC %s: %s", pvc_name_, e.reason)

    for _ in range(20):
        try:
            v1.read_namespaced_persistent_volume_claim(name=pvc_name_, namespace=namespace)
            time.sleep(1)
        except ApiException:
            break

    try:
        v1.delete_persistent_volume(name=pv_name_)
    except ApiException as e:
        if e.status != 404:
            logger.warning("Could not delete PV %s: %s", pv_name_, e.reason)
