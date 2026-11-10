import re
from dataclasses import dataclass, field

import yaml

from src.misc.runtime_type import RuntimeType


@dataclass
class Argument:
    name: str
    defaultvalue: str = ''
    options: list[str] | None = None


def _parse_argument(raw: dict) -> Argument:
    options = raw.get('options')
    if options is not None:
        if not isinstance(options, list):
            raise ValueError(f"Argument '{raw.get('name')}': 'options' must be a list")
        options = [str(o) for o in options]
    default = raw.get('defaultvalue', '')
    return Argument(
        name=str(raw['name']),
        defaultvalue='' if default is None else str(default),
        options=options or None,
    )


# Used when an environment variable has no explicit 'secret' flag.
# Whole name parts (split at '_', '-', '.'), e.g. API_KEY, DB_PASS, AWS_SECRET_ACCESS_KEY
_SENSITIVE_NAME_PARTS = {"KEY", "KEYS", "PASS", "PASSWD", "PRIVATE", "CREDENTIALS", "CREDENTIAL", "AUTH"}
# Anywhere in the name, e.g. DBPASSWORD, GITHUBTOKEN, CLIENTSECRET
_SENSITIVE_SUBSTRINGS = ("SECRET", "PASSWORD", "TOKEN", "APIKEY", "CONNECTIONSTRING", "CONNECTION_STRING")


def looks_sensitive(name: str) -> bool:
    upper = (name or "").upper()
    if any(part in _SENSITIVE_NAME_PARTS for part in re.split(r"[_\-.]", upper)):
        return True
    return any(fragment in upper for fragment in _SENSITIVE_SUBSTRINGS)


@dataclass
class Environment:
    name: str
    value: str
    # True hides the value from the API/UI. None means: decide by the variable name.
    secret: bool | None = None

    @property
    def is_secret(self) -> bool:
        return self.secret if self.secret is not None else looks_sensitive(self.name)


def _parse_environment(raw: dict) -> Environment:
    secret = raw.get('secret')
    value = raw.get('value', '')
    return Environment(
        name=str(raw['name']),
        value='' if value is None else str(value),
        secret=None if secret is None else bool(secret),
    )


@dataclass
class Volume:
    name: str
    path: str


@dataclass
class PackageConfig:
    package_name: str
    entrypoint: str
    version: str
    python_version: str
    runtime: RuntimeType | None = RuntimeType.PYTHON
    image: str | None = None
    timeout: int | None = None
    description: str | None = None
    args: list[Argument] = field(default_factory=list)
    environment: list[Environment] = field(default_factory=list)
    volumes: list[Volume] = field(default_factory=list)


def parse_config(yaml_content: str) -> PackageConfig:
    data = yaml.safe_load(yaml_content)

    args = [_parse_argument(arg) for arg in data.get('args') or []]
    env = [_parse_environment(env) for env in data.get('environment') or []]
    volumes = [Volume(**volume) for volume in data.get('volumes', [])]
    package_name = data.get('package_name', '')
    entrypoint = data.get('entrypoint', '')
    version = data.get('version', '')
    python_version = data.get('python_version', '')
    description = data.get('description')
    timeout = data.get('timeout')
    image = data.get('image', None)
    runtime = data.get('runtime', RuntimeType.PYTHON)

    return PackageConfig(
        package_name=package_name,
        entrypoint=entrypoint,
        version=version,
        python_version=python_version,
        description=description,
        timeout=timeout,
        args=args,
        environment=env,
        volumes=volumes,
        image=image,
        runtime=RuntimeType(runtime)
    )
