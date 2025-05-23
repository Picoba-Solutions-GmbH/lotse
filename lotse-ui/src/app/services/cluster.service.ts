import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { KubernetesConfigMap, KubernetesDeployment, KubernetesIngress, KubernetesNamespace, KubernetesPersistentVolumeClaim, KubernetesPod, KubernetesService, KubernetesStatefulSet, PodMetrics, KubernetesNode, KubernetesPersistentVolume } from '../models/Cluster';


@Injectable({
  providedIn: 'root',
})
export class ClusterService {
  constructor(private http: HttpClient) { }

  async getNamespacesAsync(): Promise<KubernetesNamespace[]> {
    return await firstValueFrom(this.http.get<KubernetesNamespace[]>(`${environment.url}/cluster/namespaces`));
  }

  async getPodsForNamespaceAsync(namespace: string): Promise<KubernetesPod[]> {
    return await firstValueFrom(this.http.get<KubernetesPod[]>(`${environment.url}/cluster/namespaces/${namespace}/pods`));
  }

  async deletePodAsync(namespace: string, podName: string): Promise<void> {
    return await firstValueFrom(this.http.delete<void>(`${environment.url}/cluster/namespaces/${namespace}/pods/${podName}`));
  }

  async killPodAsync(namespace: string, podName: string): Promise<void> {
    return await firstValueFrom(this.http.post<void>(`${environment.url}/cluster/namespaces/${namespace}/pods/${podName}/kill`, {}));
  }

  async getPodLogsAsync(namespace: string, podName: string): Promise<string[]> {
    return await firstValueFrom(this.http.get<string[]>(`${environment.url}/cluster/namespaces/${namespace}/pods/${podName}/logs`));
  }

  async getServicesForNamespaceAsync(namespace: string): Promise<KubernetesService[]> {
    return await firstValueFrom(this.http.get<KubernetesService[]>(`${environment.url}/cluster/namespaces/${namespace}/services`));
  }

  async deleteServiceAsync(namespace: string, serviceName: string): Promise<void> {
    return await firstValueFrom(this.http.delete<void>(`${environment.url}/cluster/namespaces/${namespace}/services/${serviceName}`));
  }

  async getDeploymentsForNamespaceAsync(namespace: string): Promise<KubernetesDeployment[]> {
    return await firstValueFrom(this.http.get<KubernetesDeployment[]>(`${environment.url}/cluster/namespaces/${namespace}/deployments`));
  }

  async deleteDeploymentAsync(namespace: string, deploymentName: string): Promise<void> {
    return await firstValueFrom(this.http.delete<void>(`${environment.url}/cluster/namespaces/${namespace}/deployments/${deploymentName}`));
  }

  async restartDeploymentAsync(namespace: string, deploymentName: string): Promise<void> {
    return await firstValueFrom(this.http.post<void>(`${environment.url}/cluster/namespaces/${namespace}/deployments/${deploymentName}/restart`, {}));
  }

  async getStatefulSetsForNamespaceAsync(namespace: string): Promise<KubernetesStatefulSet[]> {
    return await firstValueFrom(this.http.get<KubernetesStatefulSet[]>(`${environment.url}/cluster/namespaces/${namespace}/statefulsets`));
  }

  async deleteStatefulSetAsync(namespace: string, statefulSetName: string): Promise<void> {
    return await firstValueFrom(this.http.delete<void>(`${environment.url}/cluster/namespaces/${namespace}/statefulsets/${statefulSetName}`));
  }

  async restartStatefulSetAsync(namespace: string, statefulSetName: string): Promise<void> {
    return await firstValueFrom(this.http.post<void>(`${environment.url}/cluster/namespaces/${namespace}/statefulsets/${statefulSetName}/restart`, {}));
  }

  async getConfigMapsForNamespaceAsync(namespace: string): Promise<KubernetesConfigMap[]> {
    return await firstValueFrom(this.http.get<KubernetesConfigMap[]>(`${environment.url}/cluster/namespaces/${namespace}/configmaps`));
  }

  async deleteConfigMapAsync(namespace: string, configMapName: string): Promise<void> {
    return await firstValueFrom(this.http.delete<void>(`${environment.url}/cluster/namespaces/${namespace}/configmaps/${configMapName}`));
  }

  async getIngressesForNamespaceAsync(namespace: string): Promise<KubernetesIngress[]> {
    return await firstValueFrom(this.http.get<KubernetesIngress[]>(`${environment.url}/cluster/namespaces/${namespace}/ingresses`));
  }

  async deleteIngressAsync(namespace: string, ingressName: string): Promise<void> {
    return await firstValueFrom(this.http.delete<void>(`${environment.url}/cluster/namespaces/${namespace}/ingresses/${ingressName}`));
  }

  async getPersistentVolumeClaimsForNamespaceAsync(namespace: string): Promise<KubernetesPersistentVolumeClaim[]> {
    return await firstValueFrom(this.http.get<KubernetesPersistentVolumeClaim[]>(`${environment.url}/cluster/namespaces/${namespace}/persistentvolumeclaims`));
  }

  async deletePersistentVolumeClaimAsync(namespace: string, pvcName: string): Promise<void> {
    return await firstValueFrom(this.http.delete<void>(`${environment.url}/cluster/namespaces/${namespace}/persistentvolumeclaims/${pvcName}`));
  }

  async getResourceYAML(namespace: string, resourceType: string, resourceName: string): Promise<{ yaml: string }> {
    return await firstValueFrom(
      this.http.get<{ yaml: string }>(
        `${environment.url}/cluster/namespaces/${namespace}/resources/${resourceType}/${resourceName}/yaml`
      )
    );
  }

  async getResourceDescription(namespace: string, resourceType: string, resourceName: string): Promise<{ description: string }> {
    return await firstValueFrom(
      this.http.get<{ description: string }>(
        `${environment.url}/cluster/namespaces/${namespace}/resources/${resourceType}/${resourceName}/describe`
      )
    );
  }

  async getNodesAsync(): Promise<KubernetesNode[]> {
    return await firstValueFrom(this.http.get<KubernetesNode[]>(`${environment.url}/cluster/nodes`));
  }

  async getPersistentVolumesAsync(): Promise<KubernetesPersistentVolume[]> {
    return await firstValueFrom(this.http.get<KubernetesPersistentVolume[]>(`${environment.url}/cluster/persistentvolumes`));
  }

  async getNodeYAML(nodeName: string): Promise<{ yaml: string }> {
    return await firstValueFrom(
      this.http.get<{ yaml: string }>(
        `${environment.url}/cluster/resources/nodes/${nodeName}/yaml`
      )
    );
  }

  async getNodeDescription(nodeName: string): Promise<{ description: string }> {
    return await firstValueFrom(
      this.http.get<{ description: string }>(
        `${environment.url}/cluster/resources/nodes/${nodeName}/describe`
      )
    );
  }

  async getPersistentVolumeYAML(pvName: string): Promise<{ yaml: string }> {
    return await firstValueFrom(
      this.http.get<{ yaml: string }>(
        `${environment.url}/cluster/resources/persistentvolumes/${pvName}/yaml`
      )
    );
  }

  async getPersistentVolumeDescription(pvName: string): Promise<{ description: string }> {
    return await firstValueFrom(
      this.http.get<{ description: string }>(
        `${environment.url}/cluster/resources/persistentvolumes/${pvName}/describe`
      )
    );
  }
}
