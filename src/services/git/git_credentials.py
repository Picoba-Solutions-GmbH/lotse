"""Access tokens of Git sources live in Kubernetes secrets, not in the database."""
import base64
import logging

from kubernetes import client
from kubernetes.client.rest import ApiException

from src.utils import config

logger = logging.getLogger(__name__)

_TOKEN_KEY = "token"


def secret_name_for(source_id: str) -> str:
    return f"lotse-git-{source_id}"


def store_token(source_id: str, token: str) -> str:
    """Creates or replaces the secret of a source. Returns the secret name."""
    name = secret_name_for(source_id)
    body = client.V1Secret(
        metadata=client.V1ObjectMeta(name=name, namespace=config.K8S_NAMESPACE,
                                     labels={"app.kubernetes.io/managed-by": "lotse",
                                             "lotse/git-source": source_id}),
        type="Opaque",
        data={_TOKEN_KEY: base64.b64encode(token.encode()).decode()},
    )
    v1 = client.CoreV1Api()
    try:
        v1.create_namespaced_secret(namespace=config.K8S_NAMESPACE, body=body)
    except ApiException as e:
        if e.status != 409:
            raise
        v1.replace_namespaced_secret(name=name, namespace=config.K8S_NAMESPACE, body=body)
    return name


def read_token(secret_name: str | None) -> str | None:
    if not secret_name:
        return None
    try:
        secret = client.CoreV1Api().read_namespaced_secret(name=secret_name, namespace=config.K8S_NAMESPACE)
    except ApiException as e:
        if e.status == 404:
            raise RuntimeError(f"Secret {secret_name} with the Git access token doesn't exist anymore")
        raise
    encoded = (secret.data or {}).get(_TOKEN_KEY)  # type: ignore
    return base64.b64decode(encoded).decode() if encoded else None


def delete_token(secret_name: str | None) -> None:
    if not secret_name:
        return
    try:
        client.CoreV1Api().delete_namespaced_secret(name=secret_name, namespace=config.K8S_NAMESPACE)
    except ApiException as e:
        if e.status != 404:
            logger.warning("Could not delete secret %s: %s", secret_name, e.reason)
