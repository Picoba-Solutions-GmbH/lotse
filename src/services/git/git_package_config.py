"""Turns the config.yaml of a Git checkout into the config of a deployed version."""
import yaml

from src.misc.runtime_type import RuntimeType
from src.models.yaml_config import parse_config

CONFIG_FILE_NAMES = ("config.yaml", "config.yml")


class SyncConfigError(Exception):
    """The content of the repository can't be deployed. Retrying won't help until it changes."""


def prepare_config(config_text: str, package_name: str, version: str, previous_config: str | None) -> str:
    """
    - the package name comes from the Git source, the version from the tag
    - environment variables declared without a value get the value of the previous version, so secrets
      are set once in Lotse and never committed to Git
    """
    try:
        data = yaml.safe_load(config_text) or {}
    except yaml.YAMLError as e:
        raise SyncConfigError(f"config.yaml is not valid YAML: {e}")
    if not isinstance(data, dict):
        raise SyncConfigError("config.yaml must contain a mapping")

    declared_name = data.get("package_name")
    if declared_name and str(declared_name) != package_name:
        raise SyncConfigError(
            f"package_name '{declared_name}' in config.yaml doesn't match the package '{package_name}' "
            f"of this Git source")

    runtime = data.get("runtime", RuntimeType.PYTHON.value)
    if runtime == RuntimeType.BINARY.value:
        raise SyncConfigError("Binary packages can't be deployed from Git yet, upload them as an archive")

    data["package_name"] = package_name
    data["version"] = version
    if previous_config:
        inherit_environment(data, previous_config)

    content = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    try:
        parse_config(content)
    except (ValueError, KeyError, TypeError) as e:
        raise SyncConfigError(f"config.yaml is invalid: {e}")
    return content


def inherit_environment(data: dict, previous_config: str) -> None:
    try:
        previous = {env.name: env for env in parse_config(previous_config).environment}
    except (ValueError, KeyError, TypeError, yaml.YAMLError):
        return

    for raw in data.get("environment") or []:
        if not isinstance(raw, dict) or "name" not in raw:
            continue
        if raw.get("value") not in (None, ""):
            continue
        before = previous.get(str(raw["name"]))
        if before is None or not before.value:
            continue
        raw["value"] = before.value
        if raw.get("secret") is None and before.secret is not None:
            raw["secret"] = before.secret
