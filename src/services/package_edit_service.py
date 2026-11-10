"""Editing of deployed packages: environment variables, arguments and text files."""
import logging
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml
from fastapi import HTTPException

from src.database.models.package_entity import PackageEntity
from src.models.yaml_config import Argument, Environment, parse_config
from src.utils.name_generator import sanitize_name
from src.utils.path_manager import PathManager

logger = logging.getLogger(__name__)

# Only text files that are commonly adjusted after a deployment can be edited.
EDITABLE_EXTENSIONS = {
    ".txt", ".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".conf",
    ".env", ".properties", ".md", ".sh", ".sql", ".csv", ".xml", ".html", ".css", ".js",
}
EDITABLE_FILE_NAMES = {"requirements.txt", "Dockerfile", "Procfile", ".env"}
EXCLUDED_DIRECTORIES = {"__pycache__", "venv", ".venv", "node_modules", ".git"}
MAX_EDITABLE_FILE_SIZE = 1024 * 1024
MAX_LISTED_FILES = 1000

REQUIREMENTS_FILE = "requirements.txt"
_ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# ---------------------------------------------------------------- config (environment / arguments)

def _load_config_dict(package: PackageEntity) -> dict:
    data = yaml.safe_load(package.config or "") or {}  # type: ignore
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="Stored package config is invalid")
    return data


def _dump_config(data: dict) -> str:
    content = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    parse_config(content)  # make sure the result can still be parsed
    return content


@dataclass
class EnvironmentUpdate:
    name: str
    # None keeps the stored value of a secret variable
    value: str | None
    secret: bool | None = None
    previous_name: str | None = None


def to_public_environment(env: Environment) -> dict:
    """Environment variable as it may be shown to users: secret values never leave the server."""
    return {
        "name": env.name,
        "value": None if env.is_secret else env.value,
        "secret": env.is_secret,
        "has_value": bool(env.value),
    }


def _resolve_environment(package: PackageEntity, updates: list[EnvironmentUpdate]) -> list[Environment]:
    stored = {env.name: env for env in parse_config(package.config).environment}  # type: ignore
    resolved: list[Environment] = []
    for update in updates:
        env = Environment(name=update.name.strip(), value=update.value or "", secret=update.secret)
        if update.value is None:
            current = stored.get((update.previous_name or update.name).strip())
            if current is None or not current.is_secret:
                raise HTTPException(status_code=400,
                                    detail=f"Enter a value for environment variable '{env.name}'")
            if not env.is_secret:
                # otherwise anyone who can edit could reveal a secret by unmarking it
                raise HTTPException(status_code=400,
                                    detail=f"Enter a new value to make the secret '{env.name}' visible")
            env.value = current.value
        resolved.append(env)
    return resolved


def build_config_with_environment(package: PackageEntity, updates: list[EnvironmentUpdate]) -> str:
    names = [update.name.strip() for update in updates]
    for name in names:
        if not _ENV_NAME_PATTERN.match(name):
            raise HTTPException(status_code=400, detail=f"Invalid environment variable name '{name}'")
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        raise HTTPException(status_code=400,
                            detail=f"Duplicate environment variable(s): {', '.join(sorted(duplicates))}")

    raw_environment = []
    for env in _resolve_environment(package, updates):
        raw: dict = {"name": env.name, "value": env.value}
        if env.secret is not None:
            raw["secret"] = env.secret
        raw_environment.append(raw)

    data = _load_config_dict(package)
    data["environment"] = raw_environment
    return _dump_config(data)


def build_config_with_arguments(package: PackageEntity, arguments: list[Argument]) -> str:
    names = [arg.name.strip() for arg in arguments]
    if any(not name for name in names):
        raise HTTPException(status_code=400, detail="Argument names must not be empty")
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        raise HTTPException(status_code=400, detail=f"Duplicate argument(s): {', '.join(sorted(duplicates))}")

    raw_args = []
    for arg in arguments:
        options = [o for o in (arg.options or []) if o != ""]
        if options and arg.defaultvalue and arg.defaultvalue not in options:
            raise HTTPException(
                status_code=400,
                detail=f"Default value of argument '{arg.name}' must be one of its options")
        raw: dict = {"name": arg.name.strip(), "defaultvalue": arg.defaultvalue}
        if options:
            raw["options"] = options
        raw_args.append(raw)

    data = _load_config_dict(package)
    data["args"] = raw_args
    return _dump_config(data)


# ---------------------------------------------------------------- files

def get_package_dir(package: PackageEntity) -> Path:
    package_dir = PathManager.get_package_path(package.package_name, package.version)  # type: ignore
    if not package_dir.is_dir():
        raise HTTPException(status_code=404, detail="Package has no files on disk")
    return package_dir


def _archive_name(package: PackageEntity) -> str:
    return f"{package.package_name}.7z"


def is_editable_name(relative_path: str) -> bool:
    name = os.path.basename(relative_path)
    return name in EDITABLE_FILE_NAMES or Path(name).suffix.lower() in EDITABLE_EXTENSIONS


def list_editable_files(package: PackageEntity) -> list[dict]:
    package_dir = get_package_dir(package)
    modified = set(package.modified_files or [])  # type: ignore
    archive_name = _archive_name(package)
    files: list[dict] = []

    for root, dirs, names in os.walk(package_dir):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRECTORIES)
        for name in sorted(names):
            full_path = Path(root) / name
            relative = full_path.relative_to(package_dir).as_posix()
            if relative == archive_name or not is_editable_name(relative) or full_path.is_symlink():
                continue
            size = full_path.stat().st_size
            files.append({
                "path": relative,
                "size": size,
                "editable": size <= MAX_EDITABLE_FILE_SIZE,
                "modified": relative in modified,
            })
            if len(files) >= MAX_LISTED_FILES:
                return _requirements_first(files)

    return _requirements_first(files)


def _requirements_first(files: list[dict]) -> list[dict]:
    # requirements.txt is the most commonly edited file, show it on top
    return sorted(files, key=lambda f: (f["path"] != REQUIREMENTS_FILE, f["path"].count("/"), f["path"]))


def resolve_editable_file(package: PackageEntity, relative_path: str) -> tuple[Path, str]:
    package_dir = get_package_dir(package).resolve()
    normalized = relative_path.replace("\\", "/").strip("/")
    if not normalized:
        raise HTTPException(status_code=400, detail="File path is required")

    full_path = (package_dir / normalized).resolve()
    try:
        relative = full_path.relative_to(package_dir).as_posix()
    except ValueError as e:
        raise HTTPException(status_code=400, detail="File path is outside of the package") from e

    parts = relative.split("/")
    if (relative == _archive_name(package) or not is_editable_name(relative)
            or any(part in EXCLUDED_DIRECTORIES for part in parts[:-1])):
        raise HTTPException(status_code=403, detail=f"File '{relative}' cannot be edited")
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail=f"File '{relative}' not found")
    if full_path.stat().st_size > MAX_EDITABLE_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File '{relative}' is too large to be edited")
    return full_path, relative


def read_file(full_path: Path) -> str:
    try:
        # newline='' keeps the original line endings
        with open(full_path, "r", encoding="utf-8", newline="") as f:
            return f.read()
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=415, detail="File is not a UTF-8 text file") from e


def write_file(package: PackageEntity, full_path: Path, relative: str, content: str) -> bool:
    """Writes the file. Returns True if the content changed."""
    if len(content.encode("utf-8")) > MAX_EDITABLE_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Content is too large")

    if read_file(full_path) == content:
        return False

    _backup_original(package, full_path, relative)
    with open(full_path, "w", encoding="utf-8", newline="") as f:
        f.write(content)

    if relative == REQUIREMENTS_FILE:
        invalidate_venv(package)
    return True


def _original_path(package: PackageEntity, relative: str) -> Path:
    return PathManager.get_original_files_path(package.package_name, package.version) / relative  # type: ignore


def _backup_original(package: PackageEntity, full_path: Path, relative: str) -> None:
    """Keeps a copy of the file as deployed. Only the first edit creates it, later edits keep it."""
    original = _original_path(package, relative)
    if not original.exists():
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(full_path, original)


def has_original(package: PackageEntity, relative: str) -> bool:
    return _original_path(package, relative).is_file()


def matches_original(package: PackageEntity, full_path: Path, relative: str) -> bool:
    original = _original_path(package, relative)
    return original.is_file() and original.read_bytes() == full_path.read_bytes()


def revert_file(package: PackageEntity, relative_path: str) -> str:
    """Restores a file as deployed. Returns the normalized relative path."""
    full_path, relative = resolve_editable_file(package, relative_path)
    original = _original_path(package, relative)
    if not original.is_file():
        raise HTTPException(status_code=404, detail=f"No original version of '{relative}' is available")

    changed = original.read_bytes() != full_path.read_bytes()
    shutil.copy2(original, full_path)
    os.remove(original)
    if changed and relative == REQUIREMENTS_FILE:
        invalidate_venv(package)
    return relative


def remove_originals(package_name: str, version: str) -> None:
    originals_dir = PathManager.get_original_files_path(package_name, version)
    if originals_dir.exists():
        shutil.rmtree(originals_dir, ignore_errors=True)


def invalidate_venv(package: PackageEntity) -> None:
    """Removes the cached virtual environment so the next run installs the requirements again."""
    venv_dir = PathManager.get_venv_path(package.package_name, package.version)  # type: ignore
    tar_path = venv_dir / "venv.tar.gz"
    if tar_path.exists():
        os.remove(tar_path)
        logger.info("Removed cached venv of %s %s after requirements change",
                    sanitize_name(package.package_name), package.version)  # type: ignore
