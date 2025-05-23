export interface KubernetesNamespace {
  name: string;
  status: string;
  creationTimestamp: string;
}

export interface ContainerStatus {
  name: string;
  ready: boolean;
  restartCount: number;
  state: {
    running?: { startedAt: string };
    waiting?: { reason: string; message: string };
    terminated?: { reason: string; exitCode: number; startedAt: string; finishedAt: string; };
  };
}

export interface PodMetrics {
  cpu: string;
  memory: string;
}

export interface KubernetesPod {
  name: string;
  namespace: string;
  status: string;
  phase: string;
  hostIP: string;
  podIP: string;
  creationTimestamp: string;
  ready: boolean;
  containerStatuses: ContainerStatus[];
  node: string;
  metrics?: PodMetrics;
}

export interface KubernetesService {
  name: string;
  namespace: string;
  type: string;
  clusterIP: string;
  externalIP?: string;
  ports: {
    port: number;
    targetPort: number;
    protocol: string;
  }[];
  creationTimestamp: string;
}

export interface KubernetesDeployment {
  name: string;
  namespace: string;
  replicas: number;
  readyReplicas: number;
  updatedReplicas: number;
  availableReplicas: number;
  creationTimestamp: string;
}

export interface KubernetesStatefulSet {
  name: string;
  namespace: string;
  replicas: number;
  readyReplicas: number;
  creationTimestamp: string;
}

export interface KubernetesConfigMap {
  name: string;
  namespace: string;
  data: { [key: string]: string };
  dataCount: number;
  creationTimestamp: string;
}

export interface KubernetesIngress {
  name: string;
  namespace: string;
  hosts: string[];
  paths: {
    path: string;
    serviceName: string;
    servicePort: number;
  }[];
  creationTimestamp: string;
}

export interface KubernetesPersistentVolumeClaim {
  name: string;
  namespace: string;
  status: string;
  volumeName: string;
  capacity: string;
  accessModes: string[];
  storageClass: string;
  creationTimestamp: string;
}

export interface KubernetesNode {
  name: string;
  status: string;
  roles: string[];
  addresses: { [key: string]: string };
  cpu: string;
  memory: string;
  kubeletVersion: string;
  creationTimestamp: string;
}

export interface KubernetesPersistentVolume {
  name: string;
  capacity: string;
  accessModes: string[];
  reclaimPolicy: string;
  status: string;
  storageClass: string;
  claim: string | null;
  creationTimestamp: string;
}