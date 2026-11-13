"""Parsing of container image references like `myacr.azurecr.io/lotse/app:1.2.0@sha256:...`."""
from dataclasses import dataclass

DOCKER_HUB = "docker.io"
_DOCKER_HUB_ALIASES = {"docker.io", "index.docker.io", "registry-1.docker.io", "registry.hub.docker.com",
                       "hub.docker.com"}


@dataclass(frozen=True)
class ImageRef:
    host: str
    repository: str
    tag: str | None = None
    digest: str | None = None

    @property
    def api_host(self) -> str:
        """Host that serves the registry API (/v2/...)."""
        return api_host(self.host)

    def with_digest(self, digest: str) -> str:
        tag = f":{self.tag}" if self.tag else ""
        return f"{self.host}/{self.repository}{tag}@{digest}"


def normalize_host(host: str) -> str:
    host = (host or "").strip().lower().rstrip("/")
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return DOCKER_HUB if host in _DOCKER_HUB_ALIASES else host


def normalize_repository(host: str, repository: str) -> str:
    """Repository path as the registry API expects it. Docker Hub's official images live below library/:
    nginx -> library/nginx (what `docker pull nginx` does as well)."""
    repository = (repository or "").strip().strip("/").lower()
    if normalize_host(host) == DOCKER_HUB and repository and "/" not in repository:
        repository = f"library/{repository}"
    return repository


def api_host(host: str) -> str:
    return "registry-1.docker.io" if normalize_host(host) == DOCKER_HUB else normalize_host(host)


def parse(reference: str) -> ImageRef:
    reference = (reference or "").strip()
    if not reference:
        raise ValueError("Empty image reference")

    digest = None
    if "@" in reference:
        reference, digest = reference.split("@", 1)

    first, _, rest = reference.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        host, path = first, rest
    else:
        host, path = DOCKER_HUB, reference

    tag = None
    last_slash = path.rfind("/")
    colon = path.rfind(":")
    if colon > last_slash:
        path, tag = path[:colon], path[colon + 1:]

    host = normalize_host(host)
    if host == DOCKER_HUB and "/" not in path:
        path = f"library/{path}"
    return ImageRef(host=host, repository=path.lower(), tag=tag or None, digest=digest or None)
