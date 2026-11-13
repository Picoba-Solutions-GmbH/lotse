"""Thin wrapper around the git command line client.

Only HTTPS (and http) repositories are supported. Access tokens are sent as a basic auth header through
GIT_CONFIG_* environment variables, so they never show up in a URL, the process list or the git config.
"""
import base64
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import semver

from src.utils import config

logger = logging.getLogger(__name__)

_LIST_TIMEOUT_SECONDS = 60
_CLONE_TIMEOUT_SECONDS = 600
_DEFAULT_USERNAME = "git"
_TOKEN_PATTERN = re.compile(r"(Authorization: Basic )\S+", re.IGNORECASE)


class GitError(Exception):
    """git failed, e.g. the repository can't be reached or the credentials are wrong."""


@dataclass(frozen=True)
class GitAuth:
    username: str | None = None
    token: str | None = None


@dataclass(frozen=True)
class TagVersion:
    tag: str
    version: str
    commit: str


# ---------------------------------------------------------------- validation

def validate_repo_url(url: str) -> str:
    url = (url or "").strip()
    allowed = ["https://", "http://"]
    if config.GIT_ALLOW_FILE_URLS:
        allowed.append("file://")
    if not any(url.lower().startswith(prefix) for prefix in allowed):
        raise ValueError(f"Repository URL must start with {' or '.join(allowed)}")
    if any(c.isspace() for c in url):
        raise ValueError("Repository URL must not contain whitespace")
    if "@" in url.split("://", 1)[1].split("/", 1)[0]:
        raise ValueError("Don't put credentials into the repository URL, use the username and token fields")
    return url


def same_origin(url_a: str | None, url_b: str | None) -> bool:
    """Same scheme and host. A stored token must only ever be sent to the server it was entered for."""
    def origin(url: str | None) -> tuple[str, str]:
        scheme, _, rest = (url or "").strip().lower().partition("://")
        return scheme, rest.split("/", 1)[0]
    return origin(url_a) == origin(url_b)


def normalize_path(path: str | None) -> str:
    """Folder inside the repository, "" for the root. Rejects anything that could leave the repository."""
    parts = [part for part in (path or "").replace("\\", "/").split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError("Path must not contain '..'")
    if any(part.startswith("-") for part in parts):
        raise ValueError("Path segments must not start with '-'")
    return "/".join(parts)


# ---------------------------------------------------------------- versions

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
    """Tags that are versions, newest first."""
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


# ---------------------------------------------------------------- git commands

def _environment(auth: GitAuth | None) -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_ALLOW_PROTOCOL"] = "https:http:file" if config.GIT_ALLOW_FILE_URLS else "https:http"

    settings: list[tuple[str, str]] = [
        # no credential helpers: never prompt and never use credentials stored on the Lotse host
        ("credential.helper", ""),
        # paths beyond 260 characters on Windows (development machines), no effect elsewhere
        ("core.longpaths", "true"),
    ]
    if auth and auth.token:
        user = auth.username or _DEFAULT_USERNAME
        basic = base64.b64encode(f"{user}:{auth.token}".encode()).decode()
        settings.append(("http.extraHeader", f"Authorization: Basic {basic}"))
    if config.GIT_SSL_CAINFO:
        settings.append(("http.sslCAInfo", config.GIT_SSL_CAINFO))

    env["GIT_CONFIG_COUNT"] = str(len(settings))
    for i, (key, value) in enumerate(settings):
        env[f"GIT_CONFIG_KEY_{i}"] = key
        env[f"GIT_CONFIG_VALUE_{i}"] = value
    return env


def _run(args: list[str], auth: GitAuth | None, timeout: int, cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, env=_environment(auth), capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
    except FileNotFoundError:
        raise GitError("git is not installed on the Lotse server")
    except subprocess.TimeoutExpired:
        raise GitError(f"git {args[0]} timed out after {timeout} s")

    if result.returncode != 0:
        message = _TOKEN_PATTERN.sub(r"\1***", (result.stderr or result.stdout or "").strip())
        # the last lines carry the actual reason, e.g. "fatal: Authentication failed for ..."
        message = "\n".join(message.splitlines()[-5:]) or f"git {args[0]} failed with exit code {result.returncode}"
        raise GitError(message)
    return result.stdout


def list_tags(url: str, auth: GitAuth | None) -> dict[str, str]:
    """All tags of the remote repository with the commit they point to. Doesn't clone anything."""
    output = _run(["ls-remote", "--tags", url], auth, _LIST_TIMEOUT_SECONDS)
    tags: dict[str, str] = {}
    peeled: dict[str, str] = {}
    for line in output.splitlines():
        if "\t" not in line:
            continue
        sha, ref = line.split("\t", 1)
        if not ref.startswith("refs/tags/"):
            continue
        name = ref[len("refs/tags/"):]
        if name.endswith("^{}"):
            # annotated tag: this line has the commit, the other one the tag object
            peeled[name[:-3]] = sha
        else:
            tags[name] = sha
    return {name: peeled.get(name, sha) for name, sha in tags.items()}


def checkout(url: str, auth: GitAuth | None, tag: str, destination: Path, path: str = "") -> str:
    """Shallow clone of `tag` into `destination`. Only `path` is checked out if given. Returns the commit."""
    args = ["clone", "--quiet", "--depth", "1", f"--branch={tag}", "--single-branch", "--no-tags"]
    if path:
        args += ["--filter=blob:none", "--sparse"]
    _run([*args, "--", url, str(destination)], auth, _CLONE_TIMEOUT_SECONDS)

    if path:
        # normalize_path() makes sure that no segment starts with '-'
        _run(["sparse-checkout", "set", path], auth, _CLONE_TIMEOUT_SECONDS, cwd=destination)

    return _run(["rev-parse", "HEAD"], None, _LIST_TIMEOUT_SECONDS, cwd=destination).strip()
