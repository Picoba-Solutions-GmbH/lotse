"""Client for the OCI distribution API (/v2/...) plus the provider APIs that list images.

Tags, digests and login work the same for every registry. Listing all images below a path doesn't: the
standard catalog endpoint is only offered by some registries (ACR, Harbor, registry:2), so GitHub, GitLab
and Docker Hub are asked through their own APIs.
"""
import hashlib
import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, urljoin

import requests

from src.services.registry import image_ref
from src.utils import config

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 30
_MAX_PAGES = 50
_MANIFEST_TYPES = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])
_CHALLENGE_PARAM = re.compile(r'(\w+)="([^"]*)"')
_LINK_NEXT = re.compile(r'<([^>]+)>\s*;\s*rel="?next"?')


class RegistryError(Exception):
    """The registry can't be reached or refuses the request."""


class ImageNotFoundError(RegistryError):
    """The repository or tag doesn't exist (yet)."""


@dataclass(frozen=True)
class RegistryCredentials:
    username: str | None = None
    password: str | None = None

    @property
    def basic(self) -> tuple[str, str] | None:
        return (self.username or "lotse", self.password) if self.password else None


class Provider:
    GENERIC = "generic"
    ACR = "acr"
    GHCR = "ghcr"
    GITLAB = "gitlab"
    DOCKERHUB = "dockerhub"


def _is_insecure(host: str) -> bool:
    name = host.split(":", 1)[0]
    return name in ("localhost", "127.0.0.1") or host in config.REGISTRY_INSECURE_HOSTS


def next_link(response: requests.Response) -> str | None:
    match = _LINK_NEXT.search(response.headers.get("Link", ""))
    return urljoin(response.url, match.group(1)) if match else None


class RegistryClient:
    def __init__(self, host: str, credentials: RegistryCredentials | None = None,
                 provider: str = Provider.GENERIC, api_url: str | None = None,
                 session: requests.Session | None = None):
        self.host = image_ref.normalize_host(host)
        self.credentials = credentials or RegistryCredentials()
        self.provider = provider
        self.api_url = (api_url or "").rstrip("/") or None
        self.session = session or requests.Session()
        self.session.verify = config.REGISTRY_CA_BUNDLE or True
        api = image_ref.api_host(self.host)
        self.base_url = f"{'http' if _is_insecure(api) else 'https'}://{api}"
        self._tokens: dict[str, str] = {}

    # ---------------------------------------------------------------- HTTP

    def _send(self, method: str, url: str, **kwargs) -> requests.Response:
        try:
            return self.session.request(method, url, timeout=_TIMEOUT_SECONDS, **kwargs)
        except requests.RequestException as e:
            raise RegistryError(f"Can't reach {self.host}: {type(e).__name__}")

    def _registry_request(self, method: str, url: str, scope: str, headers: dict | None = None) -> requests.Response:
        """Request against /v2/... with the Docker token flow: on a Bearer challenge get a token for `scope`
        with the credentials, on a Basic challenge send the credentials directly."""
        headers = dict(headers or {})
        token = self._tokens.get(scope)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = self._send(method, url, headers=headers)
        if response.status_code != 401:
            return response

        challenge = response.headers.get("WWW-Authenticate", "")
        if challenge.lower().startswith("bearer"):
            params = dict(_CHALLENGE_PARAM.findall(challenge))
            token = self._fetch_token(params.get("realm", ""), params.get("service"), scope)
            self._tokens[scope] = token
            headers["Authorization"] = f"Bearer {token}"
            response = self._send(method, url, headers=headers)
        elif challenge.lower().startswith("basic") and self.credentials.basic:
            response = self._send(method, url, headers=headers, auth=self.credentials.basic)

        if response.status_code == 401:
            if not self.credentials.password:
                raise RegistryError(f"{self.host} refused anonymous access: the image doesn't exist, "
                                    f"or it's private and needs username and token")
            raise RegistryError(f"Authentication at {self.host} failed, check username and token")
        return response

    def _fetch_token(self, realm: str, service: str | None, scope: str) -> str:
        if not realm.startswith(("https://", "http://")):
            raise RegistryError(f"{self.host} sent an invalid authentication challenge")
        params = {"scope": scope}
        if service:
            params["service"] = service
        response = self._send("GET", realm, params=params, auth=self.credentials.basic)
        if response.status_code in (401, 403):
            raise RegistryError(f"Authentication at {self.host} failed, check username and token")
        if not response.ok:
            raise RegistryError(f"Login at {self.host} failed with HTTP {response.status_code}")
        body = response.json()
        token = body.get("token") or body.get("access_token")
        if not token:
            raise RegistryError(f"Login at {self.host} returned no token")
        return token

    @staticmethod
    def _raise_for_status(response: requests.Response, what: str) -> None:
        if response.status_code == 404:
            raise ImageNotFoundError(f"{what} not found")
        if response.status_code == 403:
            raise RegistryError(f"Access to {what} denied, the token needs read/pull permission")
        if not response.ok:
            raise RegistryError(f"{what}: HTTP {response.status_code} {response.text[:200]}")

    # ---------------------------------------------------------------- distribution API

    def check_access(self, repository: str | None = None) -> None:
        """Logs in. With a repository, checks read access to it as well."""
        if repository:
            self.list_tags(repository)
            return
        response = self._registry_request("GET", f"{self.base_url}/v2/", scope="")
        if response.status_code not in (200, 404):
            self._raise_for_status(response, self.host)

    def list_tags(self, repository: str) -> list[str]:
        repository = image_ref.normalize_repository(self.host, repository)
        scope = f"repository:{repository}:pull"
        url: str | None = f"{self.base_url}/v2/{repository}/tags/list?n=1000"
        tags: list[str] = []
        for _ in range(_MAX_PAGES):
            if url is None:
                break
            response = self._registry_request("GET", url, scope)
            self._raise_for_status(response, f"Image {self.host}/{repository}")
            tags += response.json().get("tags") or []
            url = next_link(response)
        return tags

    def resolve_digest(self, repository: str, tag: str) -> str:
        """Digest of `repository:tag`. Raises ImageNotFoundError if the tag doesn't exist (yet)."""
        repository = image_ref.normalize_repository(self.host, repository)
        scope = f"repository:{repository}:pull"
        url = f"{self.base_url}/v2/{repository}/manifests/{tag}"
        headers = {"Accept": _MANIFEST_TYPES}
        response = self._registry_request("HEAD", url, scope, headers)
        if response.ok and response.headers.get("Docker-Content-Digest"):
            return response.headers["Docker-Content-Digest"]
        if response.status_code not in (200, 405):
            self._raise_for_status(response, f"Image {self.host}/{repository}:{tag}")
        # some registries don't send the digest on HEAD: compute it from the manifest
        response = self._registry_request("GET", url, scope, headers)
        self._raise_for_status(response, f"Image {self.host}/{repository}:{tag}")
        return response.headers.get("Docker-Content-Digest") or f"sha256:{hashlib.sha256(response.content).hexdigest()}"

    # ---------------------------------------------------------------- discovery

    def list_repositories(self, path: str | None) -> list[str]:
        """Repositories (images) below `path`, e.g. "lotse" -> ["lotse/app-a", "lotse/team/app-b"]."""
        path = (path or "").strip("/").lower()
        match self.provider:
            case Provider.GHCR:
                repositories = self._list_github(path)
            case Provider.GITLAB:
                repositories = self._list_gitlab(path)
            case Provider.DOCKERHUB:
                repositories = self._list_dockerhub(path)
            case _:
                repositories = self._list_catalog()
        repositories = [r.lower() for r in repositories]
        if path:
            repositories = [r for r in repositories if r == path or r.startswith(path + "/")]
        return sorted(set(repositories))

    def _list_catalog(self) -> list[str]:
        url: str | None = f"{self.base_url}/v2/_catalog?n=1000"
        repositories: list[str] = []
        for _ in range(_MAX_PAGES):
            if url is None:
                break
            response = self._registry_request("GET", url, "registry:catalog:*")
            if response.status_code in (401, 403, 404):
                raise RegistryError(f"{self.host} doesn't allow listing its images (catalog API). "
                                    f"Add the images one by one or pick the matching provider.")
            self._raise_for_status(response, f"Catalog of {self.host}")
            repositories += response.json().get("repositories") or []
            url = next_link(response)
        return repositories

    def _paged_api(self, url: str, headers: dict, what: str) -> list[dict]:
        items: list[dict] = []
        next_url: str | None = url
        for _ in range(_MAX_PAGES):
            if next_url is None:
                break
            response = self._send("GET", next_url, headers=headers)
            self._raise_for_status(response, what)
            body = response.json()
            if isinstance(body, dict):  # Docker Hub: {"results": [...], "next": url}
                items += body.get("results") or []
                next_url = body.get("next")
            else:
                items += body
                next_url = next_link(response)
        return items

    def _list_github(self, path: str) -> list[str]:
        owner = path.split("/", 1)[0]
        if not owner:
            raise RegistryError("Enter the GitHub organization or user as path, e.g. myorg")
        api = self.api_url or "https://api.github.com"
        headers = {"Accept": "application/vnd.github+json"}
        if self.credentials.password:
            headers["Authorization"] = f"Bearer {self.credentials.password}"
        query = "packages?package_type=container&per_page=100"
        try:
            packages = self._paged_api(f"{api}/orgs/{owner}/{query}", headers, f"GitHub organization {owner}")
        except ImageNotFoundError:
            packages = self._paged_api(f"{api}/users/{owner}/{query}", headers, f"GitHub user {owner}")
        return [f"{owner}/{p['name']}" for p in packages if p.get("name")]

    def _list_gitlab(self, path: str) -> list[str]:
        if not path:
            raise RegistryError("Enter the GitLab group or project as path, e.g. mygroup")
        if self.api_url:
            api = self.api_url
        elif self.host == "registry.gitlab.com":
            api = "https://gitlab.com"
        else:
            raise RegistryError("Enter the GitLab URL (API URL) for a self-hosted GitLab")
        headers = {"PRIVATE-TOKEN": self.credentials.password} if self.credentials.password else {}
        encoded = quote(path, safe="")
        try:
            items = self._paged_api(f"{api}/api/v4/groups/{encoded}/registry/repositories?per_page=100",
                                    headers, f"GitLab group {path}")
        except ImageNotFoundError:
            items = self._paged_api(f"{api}/api/v4/projects/{encoded}/registry/repositories?per_page=100",
                                    headers, f"GitLab project {path}")
        return [item["path"] for item in items if item.get("path")]

    def _list_dockerhub(self, path: str) -> list[str]:
        namespace = path.split("/", 1)[0]
        if not namespace:
            raise RegistryError("Enter the Docker Hub namespace (user or organization) as path")
        if namespace == "library":
            raise RegistryError("Docker Hub doesn't list its official images. Leave the discovery path empty and "
                                "connect them one by one, e.g. nginx, under Sources → Container images")
        api = self.api_url or "https://hub.docker.com"
        headers = {}
        if self.credentials.password:
            response = self._send("POST", f"{api}/v2/users/login",
                                  json={"username": self.credentials.username, "password": self.credentials.password})
            if not response.ok:
                raise RegistryError("Docker Hub login failed, check username and access token")
            headers["Authorization"] = f"Bearer {response.json().get('token')}"
        items = self._paged_api(f"{api}/v2/namespaces/{namespace}/repositories?page_size=100",
                                headers, f"Docker Hub namespace {namespace}")
        return [f"{namespace}/{item['name']}" for item in items if item.get("name")]
