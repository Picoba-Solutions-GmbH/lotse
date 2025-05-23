from dataclasses import dataclass, field
from typing import List, Optional

import yaml

from src.misc.runtime_type import RuntimeType


@dataclass
class Argument:
    name: str
    defaultvalue: str


@dataclass
class Environment:
    name: str
    value: str


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
    runtime: Optional[RuntimeType] = RuntimeType.PYTHON
    image: Optional[str] = None
    timeout: Optional[int] = None
    description: Optional[str] = None
    args: List[Argument] = field(default_factory=list)
    environment: List[Environment] = field(default_factory=list)
    volumes: List[Volume] = field(default_factory=list)


def parse_config(yaml_content: str) -> PackageConfig:
    data = yaml.safe_load(yaml_content)

    args = [Argument(**arg) for arg in data.get('args', [])]
    env = [Environment(**env) for env in data.get('environment', [])]
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
