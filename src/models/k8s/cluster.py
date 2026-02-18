from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class KubernetesNamespace(BaseModel):
    name: str
    status: str
    creationTimestamp: str


class ContainerStatus(BaseModel):
    name: str
    ready: bool
    restartCount: int
    state: dict


class PodMetrics(BaseModel):
    cpu: str
    memory: str


class KubernetesPod(BaseModel):
    name: str
    namespace: str
    status: str
    phase: str
    hostIP: str
    podIP: str
    creationTimestamp: str
    ready: bool
    containerStatuses: list[ContainerStatus]
    node: str
    podMetrics: PodMetrics | None


class KubernetesContainer(BaseModel):
    name: str
    image: str
    ports: Optional[list[Dict[str, int]]] = None
    env: Optional[list[Dict[str, str]]] = None
    resources: Optional[Dict[str, Dict[str, str]]] = None


class KubernetesService(BaseModel):
    name: str
    namespace: str
    type: str
    clusterIP: str | None = None
    ports: list[Dict[str, Any]]
    selector: Dict[str, str]
    creationTimestamp: str


class KubernetesDeployment(BaseModel):
    name: str
    namespace: str
    replicas: int
    selector: Dict[str, str]
    containers: list[KubernetesContainer]
    creationTimestamp: str
    ready: str
    available: bool


class KubernetesStatefulSet(BaseModel):
    name: str
    namespace: str
    replicas: int
    selector: Dict[str, str]
    containers: list[KubernetesContainer]
    creationTimestamp: str
    ready: str
    available: bool


class KubernetesConfigMap(BaseModel):
    name: str
    namespace: str
    data: Dict[str, str]
    creationTimestamp: str


class KubernetesIngress(BaseModel):
    name: str
    namespace: str
    rules: list[Dict[str, object]]
    tls: Optional[list[Dict[str, object]]] = None
    creationTimestamp: str


class KubernetesPersistentVolumeClaim(BaseModel):
    name: str
    namespace: str
    volumeName: str
    status: str
    storageClass: str
    size: str
    accessModes: list[str]
    creationTimestamp: str


class KubernetesNode(BaseModel):
    name: str
    status: str
    roles: list[str]
    addresses: Dict[str, str]
    cpu: str
    memory: str
    kubeletVersion: str
    creationTimestamp: str


class KubernetesPersistentVolume(BaseModel):
    name: str
    capacity: str
    accessModes: list[str]
    reclaimPolicy: str
    status: str
    storageClass: str
    claim: str | None = None
    creationTimestamp: str
