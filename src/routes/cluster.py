import functools
import logging
import subprocess
from typing import List

import yaml
from fastapi import APIRouter, Depends, HTTPException
from kubernetes import client
from kubernetes.client.rest import ApiException

from src.models.k8s.cluster import (ContainerStatus, KubernetesConfigMap,
                                    KubernetesContainer, KubernetesDeployment,
                                    KubernetesIngress, KubernetesNamespace,
                                    KubernetesNode, KubernetesPersistentVolume,
                                    KubernetesPersistentVolumeClaim,
                                    KubernetesPod, KubernetesService,
                                    KubernetesStatefulSet)
from src.routes import authentication
from src.services.kubernetes.pod_manager import PodManager
from src.services.kubernetes.pod_resource_parser import PodResourceParser

router = APIRouter(prefix="/cluster", tags=["cluster"])

logger = logging.getLogger(__name__)


def handle_k8s_errors(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ApiException as e:
            resource_type = getattr(func, '__name__', 'resource')
            logger.error(f"API Error in {func.__name__}: {str(e)}")

            if e.status == 404:
                raise HTTPException(status_code=404, detail=f"{resource_type} not found")

            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    return wrapper


@router.get("/namespaces", response_model=List[KubernetesNamespace])
@handle_k8s_errors
async def get_namespaces(_=Depends(authentication.require_admin)):
    v1 = client.CoreV1Api()
    namespaces = v1.list_namespace()

    result = []
    for namespace in namespaces.items:
        result.append(
            KubernetesNamespace(
                name=namespace.metadata.name,
                status=namespace.status.phase,
                creationTimestamp=namespace.metadata.creation_timestamp.isoformat()
                if namespace.metadata.creation_timestamp
                else ""
            )
        )
    return result


@router.get("/namespaces/{namespace}/pods", response_model=List[KubernetesPod])
@handle_k8s_errors
async def get_pods_for_namespace(namespace: str, _=Depends(authentication.require_admin)):
    v1 = client.CoreV1Api()
    pods = v1.list_namespaced_pod(namespace=namespace)

    result = []
    for pod in pods.items:
        container_statuses = []
        if pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                state_dict = {}
                if cs.state.running:
                    state_dict["running"] = {"startedAt": cs.state.running.started_at.isoformat()}
                elif cs.state.waiting:
                    state_dict["waiting"] = {
                        "reason": cs.state.waiting.reason,
                        "message": cs.state.waiting.message
                    }
                elif cs.state.terminated:
                    started_at = None
                    if cs.state.terminated.started_at:
                        started_at = cs.state.terminated.started_at.isoformat()

                    finished_at = None
                    if cs.state.terminated.finished_at:
                        finished_at = cs.state.terminated.finished_at.isoformat()

                    state_dict["terminated"] = {
                        "reason": cs.state.terminated.reason,
                        "exitCode": cs.state.terminated.exit_code,
                        "startedAt": started_at,
                        "finishedAt": finished_at
                    }
                container_statuses.append(
                    ContainerStatus(
                        name=cs.name,
                        ready=cs.ready,
                        restartCount=cs.restart_count,
                        state=state_dict
                    )
                )

        api = client.CustomObjectsApi()
        metrics = PodManager.get_pod_metrics(api, namespace, pod.metadata.name)

        result.append(
            KubernetesPod(
                name=pod.metadata.name,
                namespace=pod.metadata.namespace,
                status=pod.status.phase,
                phase=pod.status.phase,
                hostIP=pod.status.host_ip or "",
                podIP=pod.status.pod_ip or "",
                creationTimestamp=pod.metadata.creation_timestamp.isoformat()
                if pod.metadata.creation_timestamp
                else "",
                ready=all(cs.ready for cs in pod.status.container_statuses)
                if pod.status.container_statuses
                else False,
                containerStatuses=container_statuses,
                node=pod.spec.node_name or "",
                podMetrics=metrics
            ))
    return result


@router.delete("/namespaces/{namespace}/pods/{pod_name}")
@handle_k8s_errors
async def delete_pod(namespace: str, pod_name: str, _=Depends(authentication.require_admin)):
    v1 = client.CoreV1Api()
    v1.delete_namespaced_pod(
        name=pod_name,
        namespace=namespace,
        body=client.V1DeleteOptions(
            grace_period_seconds=30,
            propagation_policy='Background'
        )
    )
    return {"message": f"Pod {pod_name} deleted successfully"}


@router.post("/namespaces/{namespace}/pods/{pod_name}/kill")
@handle_k8s_errors
async def kill_pod(namespace: str, pod_name: str, _=Depends(authentication.require_admin)):
    v1 = client.CoreV1Api()
    v1.delete_namespaced_pod(
        name=pod_name,
        namespace=namespace,
        body=client.V1DeleteOptions(
            grace_period_seconds=0,
            propagation_policy='Background'
        )
    )
    return {"message": f"Pod {pod_name} force killed successfully"}


@router.get("/namespaces/{namespace}/pods/{pod_name}/logs", response_model=List[str])
@handle_k8s_errors
async def get_pod_logs(namespace: str, pod_name: str, _=Depends(authentication.require_admin)):
    v1 = client.CoreV1Api()
    logs = v1.read_namespaced_pod_log(
        name=pod_name,
        namespace=namespace
    )
    return logs.split("\n") if logs else []


@router.get("/namespaces/{namespace}/services", response_model=List[KubernetesService])
@handle_k8s_errors
async def get_services_for_namespace(namespace: str, _=Depends(authentication.require_admin)):
    v1 = client.CoreV1Api()
    services = v1.list_namespaced_service(namespace=namespace)

    result = []
    for svc in services.items:
        ports = []
        if svc.spec.ports:
            for port in svc.spec.ports:
                port_dict = {}
                if port.port:
                    port_dict["port"] = port.port
                if port.target_port:
                    port_dict["targetPort"] = port.target_port
                if port.node_port:
                    port_dict["nodePort"] = port.node_port
                ports.append(port_dict)

        result.append(
            KubernetesService(
                name=svc.metadata.name,
                namespace=svc.metadata.namespace,
                type=svc.spec.type,
                clusterIP=svc.spec.cluster_ip,
                ports=ports,
                selector=svc.spec.selector or {},
                creationTimestamp=svc.metadata.creation_timestamp.isoformat()
                if svc.metadata.creation_timestamp
                else ""
            )
        )
    return result


@router.get("/namespaces/{namespace}/deployments", response_model=List[KubernetesDeployment])
@handle_k8s_errors
async def get_deployments_for_namespace(namespace: str, _=Depends(authentication.require_admin)):
    apps_v1 = client.AppsV1Api()
    deployments = apps_v1.list_namespaced_deployment(namespace=namespace)

    result = []
    for deploy in deployments.items:
        containers = []
        for container in deploy.spec.template.spec.containers:
            container_ports = []
            if container.ports:
                for port in container.ports:
                    container_ports.append({"containerPort": port.container_port})

            env = []
            if container.env:
                for env_var in container.env:
                    if env_var.value:
                        env.append({"name": env_var.name, "value": env_var.value})

            resources = {}
            if container.resources:
                if container.resources.limits:
                    resources["limits"] = container.resources.limits
                if container.resources.requests:
                    resources["requests"] = container.resources.requests

            containers.append(
                KubernetesContainer(
                    name=container.name,
                    image=container.image,
                    ports=container_ports if container_ports else None,
                    env=env if env else None,
                    resources=resources if resources else None
                )
            )

        available = False
        if deploy.status.conditions:
            for condition in deploy.status.conditions:
                if condition.type == "Available":
                    available = condition.status == "True"
                    break

        result.append(
            KubernetesDeployment(
                name=deploy.metadata.name,
                namespace=deploy.metadata.namespace,
                replicas=deploy.spec.replicas,
                selector=deploy.spec.selector.match_labels,
                containers=containers,
                creationTimestamp=deploy.metadata.creation_timestamp.isoformat()
                if deploy.metadata.creation_timestamp
                else "",
                ready=f"{deploy.status.ready_replicas or 0}/{deploy.spec.replicas}",
                available=available
            )
        )
    return result


@router.get("/namespaces/{namespace}/statefulsets", response_model=List[KubernetesStatefulSet])
@handle_k8s_errors
async def get_statefulsets_for_namespace(namespace: str, _=Depends(authentication.require_admin)):
    apps_v1 = client.AppsV1Api()
    statefulsets = apps_v1.list_namespaced_stateful_set(namespace=namespace)

    result = []
    for sts in statefulsets.items:
        containers = []
        for container in sts.spec.template.spec.containers:
            container_ports = []
            if container.ports:
                for port in container.ports:
                    container_ports.append({"containerPort": port.container_port})

            env = []
            if container.env:
                for env_var in container.env:
                    if env_var.value:
                        env.append({"name": env_var.name, "value": env_var.value})

            resources = {}
            if container.resources:
                if container.resources.limits:
                    resources["limits"] = container.resources.limits
                if container.resources.requests:
                    resources["requests"] = container.resources.requests

            containers.append(
                KubernetesContainer(
                    name=container.name,
                    image=container.image,
                    ports=container_ports if container_ports else None,
                    env=env if env else None,
                    resources=resources if resources else None
                )
            )

        available = False
        if sts.status.conditions:
            for condition in sts.status.conditions:
                if condition.type == "Available":
                    available = condition.status == "True"
                    break

        result.append(
            KubernetesStatefulSet(
                name=sts.metadata.name,
                namespace=sts.metadata.namespace,
                replicas=sts.spec.replicas,
                selector=sts.spec.selector.match_labels,
                containers=containers,
                creationTimestamp=sts.metadata.creation_timestamp.isoformat()
                if sts.metadata.creation_timestamp
                else "",
                ready=f"{sts.status.ready_replicas or 0}/{sts.spec.replicas}",
                available=available
            )
        )
    return result


@router.get("/namespaces/{namespace}/configmaps", response_model=List[KubernetesConfigMap])
@handle_k8s_errors
async def get_configmaps_for_namespace(namespace: str, _=Depends(authentication.require_admin)):
    v1 = client.CoreV1Api()
    configmaps = v1.list_namespaced_config_map(namespace=namespace)

    result = []
    for cm in configmaps.items:
        result.append(
            KubernetesConfigMap(
                name=cm.metadata.name,
                namespace=cm.metadata.namespace,
                data=cm.data or {},
                creationTimestamp=cm.metadata.creation_timestamp.isoformat()
                if cm.metadata.creation_timestamp
                else ""
            )
        )
    return result


@router.get("/namespaces/{namespace}/ingresses", response_model=List[KubernetesIngress])
@handle_k8s_errors
async def get_ingresses_for_namespace(namespace: str, _=Depends(authentication.require_admin)):
    networking_v1 = client.NetworkingV1Api()
    ingresses = networking_v1.list_namespaced_ingress(namespace=namespace)

    result = []
    for ing in ingresses.items:
        rules = []
        if ing.spec.rules:
            rules = [rule.to_dict() for rule in ing.spec.rules]

        tls = None
        if ing.spec.tls:
            tls = [tls_entry.to_dict() for tls_entry in ing.spec.tls]

        result.append(
            KubernetesIngress(
                name=ing.metadata.name,
                namespace=ing.metadata.namespace,
                rules=rules,
                tls=tls,
                creationTimestamp=ing.metadata.creation_timestamp.isoformat()
                if ing.metadata.creation_timestamp
                else ""
            )
        )
    return result


@router.get("/namespaces/{namespace}/persistentvolumeclaims", response_model=List[KubernetesPersistentVolumeClaim])
@handle_k8s_errors
async def get_pvcs_for_namespace(namespace: str, _=Depends(authentication.require_admin)):
    v1 = client.CoreV1Api()
    pvcs = v1.list_namespaced_persistent_volume_claim(namespace=namespace)

    result = []
    for pvc in pvcs.items:
        storage = ""
        if pvc.spec.resources and pvc.spec.resources.requests:
            storage = pvc.spec.resources.requests.get("storage", "")

        result.append(
            KubernetesPersistentVolumeClaim(
                name=pvc.metadata.name,
                volumeName=pvc.spec.volume_name or "",
                namespace=pvc.metadata.namespace,
                status=pvc.status.phase,
                storageClass=pvc.spec.storage_class_name or "",
                size=storage,
                accessModes=pvc.spec.access_modes,
                creationTimestamp=pvc.metadata.creation_timestamp.isoformat()
                if pvc.metadata.creation_timestamp
                else ""
            )
        )
    return result


@router.get("/nodes", response_model=List[KubernetesNode])
@handle_k8s_errors
async def get_nodes(_=Depends(authentication.require_admin)):
    v1 = client.CoreV1Api()
    nodes = v1.list_node()

    result = []
    for node in nodes.items:
        addresses = {}
        for addr in node.status.addresses:
            addresses[addr.type] = addr.address

        roles = []
        for label in node.metadata.labels:
            if label.startswith("node-role.kubernetes.io/"):
                roles.append(label.replace("node-role.kubernetes.io/", ""))

        allocatable = node.status.allocatable
        cpu = allocatable.get("cpu", "0")
        memory = allocatable.get("memory", "0")
        cpu = PodResourceParser.parse_cpu(cpu)
        memory = PodResourceParser.parse_memory(memory)

        result.append(
            KubernetesNode(
                name=node.metadata.name,
                status=node.status.conditions[-1].type if node.status.conditions else "Unknown",
                roles=roles,
                addresses=addresses,
                cpu=cpu,
                memory=memory,
                kubeletVersion=node.status.node_info.kubelet_version,
                creationTimestamp=node.metadata.creation_timestamp.isoformat()
                if node.metadata.creation_timestamp
                else ""
            )
        )
    return result


@router.get("/persistentvolumes", response_model=List[KubernetesPersistentVolume])
@handle_k8s_errors
async def get_persistent_volumes(_=Depends(authentication.require_admin)):
    v1 = client.CoreV1Api()
    pvs = v1.list_persistent_volume()

    result = []
    for pv in pvs.items:
        claim = None
        if pv.spec.claim_ref:
            claim = f"{pv.spec.claim_ref.namespace}/{pv.spec.claim_ref.name}"

        result.append(
            KubernetesPersistentVolume(
                name=pv.metadata.name,
                capacity=pv.spec.capacity.get("storage", "0"),
                accessModes=pv.spec.access_modes,
                reclaimPolicy=pv.spec.persistent_volume_reclaim_policy,
                status=pv.status.phase,
                storageClass=pv.spec.storage_class_name or "",
                claim=claim,
                creationTimestamp=pv.metadata.creation_timestamp.isoformat()
                if pv.metadata.creation_timestamp
                else ""
            )
        )
    return result


@router.get("/namespaces/{namespace}/resources/{resource_type}/{resource_name}/yaml")
@handle_k8s_errors
async def get_resource_yaml(
    namespace: str,
    resource_type: str,
    resource_name: str,
    _=Depends(authentication.require_admin)
):
    try:
        if resource_type == "pods":
            api = client.CoreV1Api()
            resource = api.read_namespaced_pod(name=resource_name, namespace=namespace)
        elif resource_type == "services":
            api = client.CoreV1Api()
            resource = api.read_namespaced_service(name=resource_name, namespace=namespace)
        elif resource_type == "deployments":
            api = client.AppsV1Api()
            resource = api.read_namespaced_deployment(name=resource_name, namespace=namespace)
        elif resource_type == "statefulsets":
            api = client.AppsV1Api()
            resource = api.read_namespaced_stateful_set(name=resource_name, namespace=namespace)
        elif resource_type == "configmaps":
            api = client.CoreV1Api()
            resource = api.read_namespaced_config_map(name=resource_name, namespace=namespace)
        elif resource_type == "ingresses":
            api = client.NetworkingV1Api()
            resource = api.read_namespaced_ingress(name=resource_name, namespace=namespace)
        elif resource_type == "pvc":
            api = client.CoreV1Api()
            resource = api.read_namespaced_persistent_volume_claim(name=resource_name, namespace=namespace)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported resource type: {resource_type}")

        resource_dict = client.ApiClient().sanitize_for_serialization(resource)
        return {"yaml": yaml.dump(resource_dict)}
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail=f"{resource_type} {resource_name} not found")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/namespaces/{namespace}/resources/{resource_type}/{resource_name}/describe")
@handle_k8s_errors
async def describe_resource(
    namespace: str,
    resource_type: str,
    resource_name: str,
    _=Depends(authentication.require_admin)
):
    try:
        cmd = ["kubectl", "describe", resource_type, resource_name, "-n", namespace]
        result = subprocess.run(cmd, capture_output=True, text=True)  # pylint: disable=W1510

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to describe resource: {result.stderr}"
            )

        return {"description": result.stdout}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resources/nodes/{node_name}/yaml")
@handle_k8s_errors
async def get_node_yaml(
    node_name: str,
    _=Depends(authentication.require_admin)
):
    try:
        api = client.CoreV1Api()
        resource = api.read_node(name=node_name)
        resource_dict = client.ApiClient().sanitize_for_serialization(resource)
        return {"yaml": yaml.dump(resource_dict)}
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail=f"Node {node_name} not found")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resources/nodes/{node_name}/describe")
@handle_k8s_errors
async def describe_node(
    node_name: str,
    _=Depends(authentication.require_admin)
):
    try:
        cmd = ["kubectl", "describe", "node", node_name]
        result = subprocess.run(cmd, capture_output=True, text=True)  # pylint: disable=W1510

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to describe node: {result.stderr}"
            )

        return {"description": result.stdout}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resources/persistentvolumes/{pv_name}/yaml")
@handle_k8s_errors
async def get_pv_yaml(
    pv_name: str,
    _=Depends(authentication.require_admin)
):
    try:
        api = client.CoreV1Api()
        resource = api.read_persistent_volume(name=pv_name)
        resource_dict = client.ApiClient().sanitize_for_serialization(resource)
        return {"yaml": yaml.dump(resource_dict)}
    except ApiException as e:
        if e.status == 404:
            raise HTTPException(status_code=404, detail=f"PersistentVolume {pv_name} not found")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resources/persistentvolumes/{pv_name}/describe")
@handle_k8s_errors
async def describe_pv(
    pv_name: str,
    _=Depends(authentication.require_admin)
):
    try:
        cmd = ["kubectl", "describe", "pv", pv_name]
        result = subprocess.run(cmd, capture_output=True, text=True)  # pylint: disable=W1510

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to describe persistent volume: {result.stderr}"
            )

        return {"description": result.stdout}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
