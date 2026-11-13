"""Registry credentials, stored as kubernetes.io/dockerconfigjson secret. The same secret is the pull secret
of package pods when the registry uses pull secret mode "lotse"."""
import base64
import json

from src.services import secret_store
from src.services.registry import image_ref
from src.services.registry.registry_client import RegistryCredentials
from src.services.registry.secret_names import registry_secret_name

_DOCKER_HUB_AUTH_KEY = "https://index.docker.io/v1/"


def _auth_key(host: str) -> str:
    host = image_ref.normalize_host(host)
    return _DOCKER_HUB_AUTH_KEY if host == image_ref.DOCKER_HUB else host


def store(registry_id: str, host: str, username: str, password: str) -> str:
    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    docker_config = {"auths": {_auth_key(host): {"username": username, "password": password, "auth": auth}}}
    return secret_store.upsert(registry_secret_name(registry_id), secret_store.DOCKER_CONFIG_JSON,
                               {".dockerconfigjson": json.dumps(docker_config)},
                               labels={"lotse/registry": registry_id})


def read(secret_name: str | None, host: str) -> RegistryCredentials | None:
    data = secret_store.read(secret_name)
    if not data or ".dockerconfigjson" not in data:
        return None
    auths = json.loads(data[".dockerconfigjson"]).get("auths", {})
    entry = auths.get(_auth_key(host)) or next(iter(auths.values()), None)
    if not entry:
        return None
    username, password = entry.get("username"), entry.get("password")
    if (not username or not password) and entry.get("auth"):
        username, _, password = base64.b64decode(entry["auth"]).decode().partition(":")
    return RegistryCredentials(username=username, password=password)


def delete(secret_name: str | None) -> None:
    secret_store.delete(secret_name)
