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
    containerStatuses: List[ContainerStatus]
    node: str
    podMetrics: Optional[PodMetrics]


class KubernetesContainer(BaseModel):
    name: str
    image: str
    ports: Optional[List[Dict[str, int]]] = None
    env: Optional[List[Dict[str, str]]] = None
    resources: Optional[Dict[str, Dict[str, str]]] = None


class KubernetesService(BaseModel):
    name: str
    namespace: str
    type: str
    clusterIP: Optional[str] = None
    ports: List[Dict[str, Any]]
    selector: Dict[str, str]
    creationTimestamp: str


class KubernetesDeployment(BaseModel):
    name: str
    namespace: str
    replicas: int
    selector: Dict[str, str]
    containers: List[KubernetesContainer]
    creationTimestamp: str
    ready: str
    available: bool


class KubernetesStatefulSet(BaseModel):
    name: str
    namespace: str
    replicas: int
    selector: Dict[str, str]
    containers: List[KubernetesContainer]
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
    rules: List[Dict[str, object]]
    tls: Optional[List[Dict[str, object]]] = None
    creationTimestamp: str


class KubernetesPersistentVolumeClaim(BaseModel):
    name: str
    namespace: str
    volumeName: str
    status: str
    storageClass: str
    size: str
    accessModes: List[str]
    creationTimestamp: str


class KubernetesNode(BaseModel):
    name: str
    status: str
    roles: List[str]
    addresses: Dict[str, str]
    cpu: str
    memory: str
    kubeletVersion: str
    creationTimestamp: str


class KubernetesPersistentVolume(BaseModel):
    name: str
    capacity: str
    accessModes: List[str]
    reclaimPolicy: str
    status: str
    storageClass: str
    claim: Optional[str] = None
    creationTimestamp: str
