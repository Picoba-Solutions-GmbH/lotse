"""Config of a package version deployed from a container image tag."""
import yaml

from src.misc.runtime_type import RuntimeType
from src.models.yaml_config import parse_config
from src.services.sync.common import SyncConfigError

# settings that belong to the image, everything else (args, environment, volumes, timeout, description)
# is taken over from the previous version, where it was set in Lotse
_IMAGE_KEYS = ("package_name", "version", "runtime", "image", "entrypoint", "python_version")


def build_image_config(previous_config: str | None, package_name: str, version: str, image: str) -> str:
    data: dict = {}
    if previous_config:
        loaded = yaml.safe_load(previous_config) or {}
        if isinstance(loaded, dict):
            data = {key: value for key, value in loaded.items() if key not in _IMAGE_KEYS}

    config = {
        "package_name": package_name,
        "version": version,
        "runtime": RuntimeType.CONTAINER.value,
        "image": image,
        **data,
    }
    content = yaml.safe_dump(config, sort_keys=False, allow_unicode=True, default_flow_style=False)
    try:
        parse_config(content)
    except (ValueError, KeyError, TypeError) as e:
        raise SyncConfigError(f"The settings of the previous version are invalid: {e}")
    return content
