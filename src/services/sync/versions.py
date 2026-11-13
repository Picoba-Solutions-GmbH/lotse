"""Versions from tags: "<prefix><semver>", e.g. v1.2.0 -> 1.2.0. Shared by Git and image sources."""
from dataclasses import dataclass

import semver


@dataclass(frozen=True)
class TagVersion:
    tag: str
    version: str
    # Git: the commit of the tag. Images: the manifest digest, "" until it was resolved.
    commit: str


def version_of(tag: str | None, prefix: str) -> str | None:
    """Version of a tag "<prefix><semver>", None if the tag doesn't follow that pattern."""
    if not tag or not tag.startswith(prefix):
        return None
    candidate = tag[len(prefix):]
    try:
        semver.Version.parse(candidate, optional_minor_and_patch=True)
    except ValueError:
        return None
    return candidate


def _sort_key(version: str) -> semver.Version:
    return semver.Version.parse(version, optional_minor_and_patch=True)


def parse_versions(tags: dict[str, str], prefix: str) -> list[TagVersion]:
    """Tags that are versions, newest first. `tags` maps tag -> commit/digest."""
    versions = []
    for tag, commit in tags.items():
        version = version_of(tag, prefix)
        if version is not None:
            versions.append(TagVersion(tag=tag, version=version, commit=commit))
    return sorted(versions, key=lambda v: _sort_key(v.version), reverse=True)


def is_newer(version: str, than: str | None) -> bool:
    if than is None:
        return True
    try:
        return _sort_key(version) > _sort_key(than)
    except ValueError:
        return True


def baseline_tag(versions: list[TagVersion], deployed_versions: set[str]) -> TagVersion | None:
    """Newest tag that is already deployed. Auto sync starts after it instead of failing on it."""
    return next((v for v in versions if v.version in deployed_versions), None)
