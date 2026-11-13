import json

import pytest
import requests
import yaml

from src.database.models.registry_entity import PullSecretMode, RegistryEntity
from src.database.repositories.registry_repository import RegistryRepository
from src.misc.runtime_type import RuntimeType
from src.models.yaml_config import Environment, parse_config
from src.services.git.git_package_config import prepare_config
from src.services.image_sync_service import package_name_for
from src.services.kubernetes.pod_manager import PodManager
from src.services.registry import image_ref
from src.services.registry.image_package_config import build_image_config
from src.services.registry.registry_client import (ImageNotFoundError,
                                                   RegistryClient,
                                                   RegistryCredentials,
                                                   RegistryError)

# ---------------------------------------------------------------- image references


@pytest.mark.parametrize("reference, host, repository, tag, digest", [
    ("nginx", "docker.io", "library/nginx", None, None),
    ("nginx:1.27", "docker.io", "library/nginx", "1.27", None),
    ("myorg/app:2.0.0", "docker.io", "myorg/app", "2.0.0", None),
    ("index.docker.io/myorg/app", "docker.io", "myorg/app", None, None),
    ("myacr.azurecr.io/lotse/order-service:1.3.0", "myacr.azurecr.io", "lotse/order-service", "1.3.0", None),
    ("localhost:5000/lotse/app:1.0.0@sha256:abc", "localhost:5000", "lotse/app", "1.0.0", "sha256:abc"),
    ("ghcr.io/MyOrg/App@sha256:def", "ghcr.io", "myorg/app", None, "sha256:def"),
])
def test_parse_image_reference(reference, host, repository, tag, digest):
    ref = image_ref.parse(reference)
    assert (ref.host, ref.repository, ref.tag, ref.digest) == (host, repository, tag, digest)


def test_image_reference_helpers():
    assert image_ref.api_host("docker.io") == "registry-1.docker.io"
    assert image_ref.normalize_host("https://GHCR.io/") == "ghcr.io"
    ref = image_ref.parse("myacr.azurecr.io/lotse/app:1.0.0")
    assert ref.with_digest("sha256:1") == "myacr.azurecr.io/lotse/app:1.0.0@sha256:1"
    assert package_name_for("lotse/team/order-service") == "order-service"


# ---------------------------------------------------------------- fake registry


def _response(url: str, status: int = 200, body=None, headers: dict | None = None, content: bytes | None = None):
    response = requests.Response()
    response.status_code = status
    response.url = url
    response.headers.update(headers or {})
    # pylint: disable-next=protected-access
    response._content = content if content is not None else json.dumps(body or {}).encode()
    return response


class FakeSession:
    """Answers requests with `handler(method, url, kwargs)` and records them."""

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, str, dict]] = []
        self.verify = True

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.handler(method, url, kwargs)


def bearer_registry(tags_pages: list[list[str]], token: str = "tkn", credentials=("user", "secret")):
    """Registry with the Docker token flow: realm checks basic auth and hands out a bearer token."""

    def handler(method, url, kwargs):
        if url.startswith("https://auth.example.com/token"):
            if kwargs.get("auth") != credentials:
                return _response(url, 401)
            return _response(url, body={"token": token})
        if kwargs.get("headers", {}).get("Authorization") != f"Bearer {token}":
            return _response(url, 401, headers={
                "WWW-Authenticate": 'Bearer realm="https://auth.example.com/token",service="registry.example.com"'})
        if "/tags/list" in url:
            page = 1 if "last=" in url else 0
            more = page == 0 and len(tags_pages) > 1
            headers = {"Link": '</v2/lotse/app/tags/list?n=1000&last=b>; rel="next"'} if more else {}
            return _response(url, body={"name": "lotse/app", "tags": tags_pages[page]}, headers=headers)
        if "/manifests/" in url:
            if url.endswith("/missing"):
                return _response(url, 404)
            if method == "HEAD":
                return _response(url, headers={"Docker-Content-Digest": "sha256:feed"})
        if url.endswith("/v2/_catalog?n=1000"):
            return _response(url, body={"repositories": ["lotse/app", "lotse/team/api", "other/x"]})
        return _response(url, 404)

    return handler


def _client(handler, credentials=RegistryCredentials("user", "secret"), provider="generic",
            host="registry.example.com"):
    session = FakeSession(handler)
    return RegistryClient(host, credentials, provider, session=session), session


def test_token_flow_and_tag_pagination():
    client, session = _client(bearer_registry([["1.0.0", "a"], ["1.1.0", "b"]]))
    assert client.list_tags("lotse/app") == ["1.0.0", "a", "1.1.0", "b"]
    token_requests = [c for c in session.calls if c[1].startswith("https://auth.example.com")]
    assert len(token_requests) == 1  # the token is reused for the second page
    assert token_requests[0][2]["params"]["scope"] == "repository:lotse/app:pull"


def test_wrong_credentials_fail_with_clear_message():
    client, _ = _client(bearer_registry([["1.0.0"]]), credentials=RegistryCredentials("user", "wrong"))
    with pytest.raises(RegistryError, match="Authentication"):
        client.list_tags("lotse/app")


def test_resolve_digest_and_missing_image():
    client, _ = _client(bearer_registry([[]]))
    assert client.resolve_digest("lotse/app", "1.0.0") == "sha256:feed"
    with pytest.raises(ImageNotFoundError):
        client.resolve_digest("lotse/app", "missing")


def test_resolve_digest_computes_digest_when_head_has_none():
    manifest = b'{"schemaVersion": 2}'

    def handler(method, url, kwargs):
        return _response(url, content=manifest) if method == "GET" else _response(url)

    client, _ = _client(handler, credentials=RegistryCredentials())
    import hashlib  # pylint: disable=import-outside-toplevel
    assert client.resolve_digest("lotse/app", "1.0.0") == f"sha256:{hashlib.sha256(manifest).hexdigest()}"


def test_catalog_discovery_filters_by_path():
    client, _ = _client(bearer_registry([[]]))
    assert client.list_repositories("lotse") == ["lotse/app", "lotse/team/api"]
    assert client.list_repositories(None) == ["lotse/app", "lotse/team/api", "other/x"]


def test_catalog_not_allowed_explains_what_to_do():
    client, _ = _client(lambda m, url, k: _response(url, 403), credentials=RegistryCredentials())
    with pytest.raises(RegistryError, match="catalog"):
        client.list_repositories("lotse")


def test_github_discovery_falls_back_from_org_to_user():
    def handler(method, url, kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer ghp_x"
        if "/orgs/" in url:
            return _response(url, 404)
        return _response(url, content=json.dumps([{"name": "app"}, {"name": "tools/cli"}]).encode())

    client, _ = _client(handler, RegistryCredentials("me", "ghp_x"), provider="ghcr", host="ghcr.io")
    assert client.list_repositories("me") == ["me/app", "me/tools/cli"]


def test_gitlab_discovery_uses_group_api():
    def handler(method, url, kwargs):
        assert url.startswith("https://gitlab.com/api/v4/groups/mygroup%2Fsub/registry/repositories")
        assert kwargs["headers"]["PRIVATE-TOKEN"] == "glpat"
        return _response(url, content=json.dumps([{"path": "mygroup/sub/app"}, {"path": "mygroup/sub/api"}]).encode())

    client, _ = _client(handler, RegistryCredentials("u", "glpat"), provider="gitlab", host="registry.gitlab.com")
    assert client.list_repositories("mygroup/sub") == ["mygroup/sub/api", "mygroup/sub/app"]


def test_dockerhub_discovery_logs_in_and_pages():
    def handler(method, url, kwargs):
        if url.endswith("/v2/users/login"):
            return _response(url, body={"token": "jwt"})
        assert kwargs["headers"]["Authorization"] == "Bearer jwt"
        if "page=2" in url:
            return _response(url, body={"results": [{"name": "b"}], "next": None})
        return _response(url, body={"results": [{"name": "a"}],
                                     "next": "https://hub.docker.com/v2/namespaces/myorg/repositories?page=2"})

    client, _ = _client(handler, RegistryCredentials("me", "dckr_pat"), provider="dockerhub", host="docker.io")
    assert client.list_repositories("myorg") == ["myorg/a", "myorg/b"]


# ---------------------------------------------------------------- configs

PREVIOUS = """
package_name: order-service
version: 1.0.0
runtime: container
image: myacr.azurecr.io/lotse/order-service:1.0.0@sha256:old
description: Orders
timeout: 600
args:
  - name: --mode
    defaultvalue: fast
environment:
  - name: DB_PASSWORD
    value: s3cr3t
    secret: true
"""


def test_build_image_config_keeps_settings_and_pins_new_image():
    image = "myacr.azurecr.io/lotse/order-service:1.1.0@sha256:new"
    parsed = parse_config(build_image_config(PREVIOUS, "order-service", "1.1.0", image))
    assert parsed.version == "1.1.0" and parsed.image == image and parsed.runtime == RuntimeType.CONTAINER
    assert parsed.timeout == 600 and parsed.description == "Orders"
    assert parsed.args[0].name == "--mode"
    assert parsed.environment[0].value == "s3cr3t" and parsed.environment[0].is_secret


def test_build_image_config_for_first_version():
    parsed = parse_config(build_image_config(None, "app", "1.0.0", "ghcr.io/me/app:1.0.0@sha256:x"))
    assert parsed.package_name == "app" and parsed.environment == [] and parsed.args == []


def test_git_deploy_file_version_placeholder():
    config = "runtime: container\nimage: myacr.azurecr.io/lotse/app:{{ version }}\n"
    assert yaml.safe_load(prepare_config(config, "app", "1.3.0", None))["image"] == "myacr.azurecr.io/lotse/app:1.3.0"


# ---------------------------------------------------------------- pods


def _manifest(runtime, **kwargs):
    image = kwargs.pop("image", None)
    return PodManager.build_pod_manifest("pod-1", "3.12.0", [Environment("A", "1")], [], image, runtime, False,
                                         **kwargs)


def test_container_pod_keeps_image_files_and_gets_args_and_pull_secret():
    manifest = _manifest(RuntimeType.CONTAINER, image="myacr.azurecr.io/lotse/app:1.0.0@sha256:x",
                         args=["--mode", "fast"], image_pull_secrets=["lotse-registry-1"])
    container = manifest["spec"]["containers"][0]
    assert container["volumeMounts"] == [] and manifest["spec"]["volumes"] == []
    assert container["args"] == ["--mode", "fast"] and "command" not in container
    assert manifest["spec"]["imagePullSecrets"] == [{"name": "lotse-registry-1"}]


def test_python_pod_is_unchanged():
    manifest = _manifest(RuntimeType.PYTHON)
    container = manifest["spec"]["containers"][0]
    assert [m["mountPath"] for m in container["volumeMounts"]] == ["/app", "/app/venv"]
    assert container["command"] == ["sleep", "infinity"] and "args" not in container
    assert "imagePullSecrets" not in manifest["spec"]
    assert container["image"] == "python:3.12.0-slim"


# ---------------------------------------------------------------- pull secret lookup


def _registry(**values) -> RegistryEntity:
    defaults = dict(id="r1", name="acr", host="myacr.azurecr.io", provider="acr",
                    credential_secret="lotse-registry-r1", pull_secret_mode=PullSecretMode.LOTSE, discovery_path=None)
    defaults.update(values)
    return RegistryEntity(**defaults)


def test_pull_secret_is_taken_from_the_most_specific_registry(monkeypatch):
    registries = [
        _registry(),
        _registry(id="g1", name="gh-a", host="ghcr.io", discovery_path="org-a", pull_secret_mode=PullSecretMode.LOTSE),
        _registry(id="g2", name="gh-b", host="ghcr.io", discovery_path="org-b",
                  pull_secret_mode=PullSecretMode.EXISTING, pull_secret_name="my-secret"),
        _registry(id="d1", name="hub", host="docker.io", pull_secret_mode=PullSecretMode.NONE),
    ]
    monkeypatch.setattr(RegistryRepository, "list_all", staticmethod(lambda db: registries))
    assert RegistryRepository.pull_secrets_for(None, "myacr.azurecr.io/x/y:1") == ["lotse-registry-r1"]  # type: ignore
    assert RegistryRepository.pull_secrets_for(None, "ghcr.io/org-b/app:1") == ["my-secret"]  # type: ignore
    assert RegistryRepository.pull_secrets_for(None, "ghcr.io/org-a/app:1") == ["lotse-registry-g1"]  # type: ignore
    assert RegistryRepository.pull_secrets_for(None, "ghcr.io/org-c/app:1") == []  # type: ignore
    assert RegistryRepository.pull_secrets_for(None, "nginx:latest") == []  # type: ignore
    assert RegistryRepository.pull_secrets_for(None, "quay.io/x/y") == []  # type: ignore


# ---------------------------------------------------------------- Docker Hub


def test_docker_hub_official_images_live_below_library():
    assert image_ref.normalize_repository("docker.io", "nginx") == "library/nginx"
    assert image_ref.normalize_repository("hub.docker.com", "/Nginx/") == "library/nginx"
    assert image_ref.normalize_repository("docker.io", "myorg/app") == "myorg/app"
    assert image_ref.normalize_repository("ghcr.io", "nginx") == "nginx"


def test_docker_hub_client_uses_library_path_for_short_names():
    seen = []

    def handler(method, url, kwargs):
        seen.append(url)
        return _response(url, body={"tags": ["1.27.0"]})

    client, _ = _client(handler, credentials=RegistryCredentials(), host="docker.io")
    assert client.list_tags("nginx") == ["1.27.0"]
    assert seen[0] == "https://registry-1.docker.io/v2/library/nginx/tags/list?n=1000"


def test_anonymous_401_explains_missing_or_private_image():
    def handler(method, url, kwargs):
        if url.startswith("https://auth.example.com"):
            return _response(url, body={"token": "anon"})
        return _response(url, 401, headers={"WWW-Authenticate": 'Bearer realm="https://auth.example.com/token"'})

    client, _ = _client(handler, credentials=RegistryCredentials())
    with pytest.raises(RegistryError, match="anonymous access"):
        client.list_tags("someone/private")


def test_docker_hub_official_images_cant_be_discovered():
    client, _ = _client(lambda m, url, k: _response(url), credentials=RegistryCredentials(),
                        provider="dockerhub", host="docker.io")
    with pytest.raises(RegistryError, match="official images"):
        client.list_repositories("library")
