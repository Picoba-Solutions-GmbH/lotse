"""Credentials of Git sources and registries live in Kubernetes secrets of the package namespace,
never in the database."""
import base64
import logging

from kubernetes import client
from kubernetes.client.rest import ApiException

from src.utils import config

logger = logging.getLogger(__name__)

OPAQUE = "Opaque"
DOCKER_CONFIG_JSON = "kubernetes.io/dockerconfigjson"


def upsert(name: str, secret_type: str, data: dict[str, str], labels: dict[str, str] | None = None) -> str:
    """Creates or replaces a secret. `data` values are plain text. Returns the name."""
    body = client.V1Secret(
        metadata=client.V1ObjectMeta(name=name, namespace=config.K8S_NAMESPACE,
                                     labels={"app.kubernetes.io/managed-by": "lotse", **(labels or {})}),
        type=secret_type,
        data={key: base64.b64encode(value.encode()).decode() for key, value in data.items()},
    )
    v1 = client.CoreV1Api()
    try:
        v1.create_namespaced_secret(namespace=config.K8S_NAMESPACE, body=body)
    except ApiException as e:
        if e.status != 409:
            raise
        v1.replace_namespaced_secret(name=name, namespace=config.K8S_NAMESPACE, body=body)
    return name


def read(name: str | None) -> dict[str, str] | None:
    """Plain text data of a secret, None if no name is given."""
    if not name:
        return None
    try:
        secret = client.CoreV1Api().read_namespaced_secret(name=name, namespace=config.K8S_NAMESPACE)
    except ApiException as e:
        if e.status == 404:
            raise RuntimeError(f"Secret {name} with the credentials doesn't exist anymore")
        raise
    return {key: base64.b64decode(value).decode() for key, value in (secret.data or {}).items()}  # type: ignore


def delete(name: str | None) -> None:
    if not name:
        return
    try:
        client.CoreV1Api().delete_namespaced_secret(name=name, namespace=config.K8S_NAMESPACE)
    except ApiException as e:
        if e.status != 404:
            logger.warning("Could not delete secret %s: %s", name, e.reason)
