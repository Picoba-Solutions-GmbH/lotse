import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { ConfirmationService, MessageService, PrimeIcons } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogModule } from 'primeng/dialog';
import { ScrollPanelModule } from 'primeng/scrollpanel';
import { SelectButtonModule } from 'primeng/selectbutton';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { Subscription } from 'rxjs';
import { HasRoleDirective } from '../../../directives/has-role.directive';
import { Role } from '../../../misc/Role';
import { KubernetesConfigMap, KubernetesDeployment, KubernetesIngress, KubernetesPersistentVolumeClaim, KubernetesPod, KubernetesService, KubernetesStatefulSet } from '../../../models/Cluster';
import { AgePipe } from '../../../pipes/age.pipe';
import { ClusterService } from '../../../services/cluster.service';
import { WebSocketService } from '../../../services/websocket.service';
import { PodTerminalComponent } from '../../pod-terminal/pod-terminal.component';

@Component({
    selector: 'app-namespace-resources',
    imports: [
        CommonModule,
        TableModule,
        CardModule,
        TagModule,
        ButtonModule,
        TooltipModule,
        DialogModule,
        ToastModule,
        ConfirmDialogModule,
        ScrollPanelModule,
        PodTerminalComponent,
        HasRoleDirective,
        FormsModule,
        SelectButtonModule
    ],
    templateUrl: './namespace-resources.component.html',
    styleUrl: './namespace-resources.component.scss',
    providers: [MessageService, ConfirmationService]
})
export class NamespaceResourcesComponent implements OnInit, OnDestroy {
    PrimeIcons = PrimeIcons;
    Role = Role;
    @ViewChild(PodTerminalComponent) podTerminal: PodTerminalComponent | undefined;
    namespace: string = '';
    resourceTypes = [
        { label: 'Pods', value: 'pods' },
        { label: 'Services', value: 'services' },
        { label: 'Deployments', value: 'deployments' },
        { label: 'StatefulSets', value: 'statefulsets' },
        { label: 'ConfigMaps', value: 'configmaps' },
        { label: 'Ingresses', value: 'ingresses' },
        { label: 'PVC', value: 'pvcs' }
    ];

    previousResourceType: string = '';
    selectedResourceType: string = 'pods';
    pods: KubernetesPod[] = [];
    services: KubernetesService[] = [];
    deployments: KubernetesDeployment[] = [];
    statefulSets: KubernetesStatefulSet[] = [];
    configMaps: KubernetesConfigMap[] = [];
    ingresses: KubernetesIngress[] = [];
    persistentVolumeClaims: KubernetesPersistentVolumeClaim[] = [];
    loading: boolean = true;
    showLogsDialog: boolean = false;
    showConfigMapDialog: boolean = false;
    selectedPod: KubernetesPod | null = null;
    selectedConfigMap: KubernetesConfigMap | null = null;
    podLogs: string[] = [];
    logsLoading: boolean = false;
    private wsSubscription: Subscription | null = null;
    showTerminalDialog: boolean = false;
    selectedPodForTerminal: KubernetesPod | null = null;
    showYAMLDialog: boolean = false;
    showDescribeDialog: boolean = false;
    yamlLoading: boolean = false;
    describeLoading: boolean = false;
    resourceYAML: string = '';
    resourceDescription: string = '';
    yamlDialogTitle: string = '';
    describeDialogTitle: string = '';

    constructor(
        private clusterService: ClusterService,
        private route: ActivatedRoute,
        private router: Router,
        private messageService: MessageService,
        private confirmationService: ConfirmationService,
        private webSocketService: WebSocketService
    ) { }

    ngOnInit(): void {
        this.namespace = this.route.snapshot.paramMap.get('namespace') || '';
        if (!this.namespace) {
            this.router.navigate(['/cluster']);
            return;
        }

        this.loadData();
    }

    ngOnDestroy(): void {
        if (this.wsSubscription) {
            this.wsSubscription.unsubscribe();
        }

        this.webSocketService.closeAllNamespaceConnections();
    }

    private connectToResourceWebSocket(resourceType: string): void {
        if (this.wsSubscription) {
            this.wsSubscription.unsubscribe();
        }

        this.wsSubscription = this.webSocketService.connectToNamespaceResource(this.namespace, resourceType).subscribe({
            next: (data: any) => {
                if (data[resourceType]) {
                    const resourceMap = {
                        'pods': this.pods,
                        'services': this.services,
                        'deployments': this.deployments,
                        'statefulsets': this.statefulSets,
                        'configmaps': this.configMaps,
                        'ingresses': this.ingresses,
                        'pvcs': this.persistentVolumeClaims
                    } as const;

                    if (resourceType in resourceMap) {
                        const key = resourceType as keyof typeof resourceMap;
                        this.updateResourceArray(resourceMap[key], data[resourceType]);
                        this.loading = false;
                    }
                }
            },
            error: (error) => {
                console.error('WebSocket error:', error);
                this.messageService.add({ severity: 'error', summary: 'Connection Error', detail: 'Lost connection to server. Retrying...' });
            }
        });
    }

    private updateResourceArray(targetArray: any[], newItems: any[]): void {
        for (const newItem of newItems) {
            const existingItem = targetArray.find(item => item.name === newItem.name);
            if (existingItem) {
                existingItem.duration = new AgePipe().transform(newItem.creationTimestamp);
                Object.assign(existingItem, newItem);
            } else {
                targetArray.push(newItem);
            }

            const deletedItems = targetArray.filter(item => !newItems.some(newItem => newItem.name === item.name));
            for (const deletedItem of deletedItems) {
                const index = targetArray.indexOf(deletedItem);
                if (index > -1) {
                    targetArray.splice(index, 1);
                }
            }
        }
    }

    private async loadData(): Promise<void> {
        try {
            this.loading = true;
            await this.loadResources();
        } catch (error) {
            console.error('Error loading resources:', error);
            this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to load resources' });
        } finally {
            this.loading = false;
        }
    }

    async loadResources(): Promise<void> {
        this.loading = true;
        try {
            if (this.wsSubscription) {
                this.wsSubscription.unsubscribe();
            }

            if (this.previousResourceType) {
                this.webSocketService.closeNamespaceResourceConnection(this.namespace, this.previousResourceType);
            }

            this.connectToResourceWebSocket(this.selectedResourceType);

            if (this.selectedResourceType === 'pods') {
                await this.loadPodsForNamespace();
            }

            this.previousResourceType = this.selectedResourceType;
        } catch (error) {
            console.error(`Error loading ${this.selectedResourceType}:`, error);
            this.messageService.add({
                severity: 'error',
                summary: 'Error',
                detail: `Failed to load ${this.selectedResourceType} for namespace ${this.namespace}`
            });
        } finally {
            this.loading = false;
        }
    }

    onResourceTypeChange(): void {
        this.loadResources();
    }

    async loadPodsForNamespace(): Promise<void> {
        try {
            this.loading = true;
            this.pods = await this.clusterService.getPodsForNamespaceAsync(this.namespace);
        } catch (error) {
            console.error(`Error loading pods for namespace ${this.namespace}:`, error);
            this.messageService.add({
                severity: 'error',
                summary: 'Error',
                detail: `Failed to load pods for namespace ${this.namespace}`
            });
        } finally {
            this.loading = false;
        }
    }

    getPodStatusSeverity(phase: string): 'success' | 'info' | 'warn' | 'danger' | 'secondary' {
        switch (phase) {
            case 'Running':
                return 'success';
            case 'Pending':
                return 'warn';
            case 'Succeeded':
                return 'info';
            case 'Failed':
                return 'danger';
            case 'Unknown':
                return 'secondary';
            default:
                return 'secondary';
        }
    }

    getPVCStatusSeverity(status: string): 'success' | 'info' | 'warn' | 'danger' | 'secondary' {
        switch (status) {
            case 'Bound':
                return 'success';
            case 'Pending':
                return 'warn';
            case 'Lost':
                return 'danger';
            default:
                return 'secondary';
        }
    }

    getReadyContainersCount(pod: KubernetesPod): number {
        if (!pod.containerStatuses) {
            return 0;
        }

        return pod.containerStatuses.filter(container => container.ready).length;
    }

    getTotalRestarts(pod: KubernetesPod): number {
        if (!pod.containerStatuses) {
            return 0;
        }

        return pod.containerStatuses.reduce((total, container) => total + container.restartCount, 0);
    }

    async deletePod(pod: KubernetesPod): Promise<void> {
        this.confirmationService.confirm({
            header: 'Delete Pod',
            message: `Are you sure you want to delete the pod ${pod.name}?`,
            icon: 'pi pi-exclamation-triangle',
            accept: async () => {
                try {
                    await this.clusterService.deletePodAsync(this.namespace, pod.name);
                    this.messageService.add({
                        severity: 'success',
                        summary: 'Success',
                        detail: `Pod ${pod.name} deleted successfully.`
                    });
                    await this.loadPodsForNamespace();
                } catch (error) {
                    this.messageService.add({
                        severity: 'error',
                        summary: 'Error',
                        detail: `Failed to delete pod ${pod.name}. ${error}`
                    });
                }
            }
        });
    }

    async killPod(pod: KubernetesPod): Promise<void> {
        this.confirmationService.confirm({
            header: 'Kill Pod',
            message: `Are you sure you want to kill the pod ${pod.name}? This will forcefully terminate the pod.`,
            icon: 'pi pi-exclamation-triangle',
            accept: async () => {
                try {
                    await this.clusterService.killPodAsync(this.namespace, pod.name);
                    this.messageService.add({
                        severity: 'success',
                        summary: 'Success',
                        detail: `Pod ${pod.name} killed successfully.`
                    });
                    await this.loadPodsForNamespace();
                } catch (error) {
                    this.messageService.add({
                        severity: 'error',
                        summary: 'Error',
                        detail: `Failed to kill pod ${pod.name}. ${error}`
                    });
                }
            }
        });
    }

    async viewPodLogs(pod: KubernetesPod): Promise<void> {
        this.selectedPod = pod;
        this.showLogsDialog = true;
        await this.loadPodLogs(pod);
    }

    async loadPodLogs(pod: KubernetesPod): Promise<void> {
        try {
            this.logsLoading = true;
            this.podLogs = await this.clusterService.getPodLogsAsync(this.namespace, pod.name);
        } catch (error) {
            console.error(`Error loading logs for pod ${pod.name}:`, error);
            this.messageService.add({
                severity: 'error',
                summary: 'Error',
                detail: `Failed to load logs for pod ${pod.name}`
            });
            this.podLogs = [];
        } finally {
            this.logsLoading = false;
        }
    }

    openTerminal(pod: KubernetesPod): void {
        this.selectedPodForTerminal = pod;
        this.showTerminalDialog = true;
    }

    handleSocketClosed(): void {
        this.showTerminalDialog = false;
    }

    handleTerminalResize(): void {
        setTimeout(() => {
            if (this.podTerminal) {
                this.podTerminal.handleFit();
            }
        }, 100);
    }

    navigateBack(): void {
        this.webSocketService.closeAllNamespaceConnections();
        this.router.navigate(['/cluster']);
    }

    async deleteService(service: KubernetesService): Promise<void> {
        this.confirmationService.confirm({
            header: 'Delete Service',
            message: `Are you sure you want to delete the service ${service.name}?`,
            icon: 'pi pi-exclamation-triangle',
            accept: async () => {
                try {
                    await this.clusterService.deleteServiceAsync(this.namespace, service.name);
                    this.messageService.add({
                        severity: 'success',
                        summary: 'Success',
                        detail: `Service ${service.name} deleted successfully.`
                    });
                    await this.loadResources();
                } catch (error) {
                    this.messageService.add({
                        severity: 'error',
                        summary: 'Error',
                        detail: `Failed to delete service ${service.name}. ${error}`
                    });
                }
            }
        });
    }

    async deleteDeployment(deployment: KubernetesDeployment): Promise<void> {
        this.confirmationService.confirm({
            header: 'Delete Deployment',
            message: `Are you sure you want to delete the deployment ${deployment.name}?`,
            icon: 'pi pi-exclamation-triangle',
            accept: async () => {
                try {
                    await this.clusterService.deleteDeploymentAsync(this.namespace, deployment.name);
                    this.messageService.add({
                        severity: 'success',
                        summary: 'Success',
                        detail: `Deployment ${deployment.name} deleted successfully.`
                    });
                    await this.loadResources();
                } catch (error) {
                    this.messageService.add({
                        severity: 'error',
                        summary: 'Error',
                        detail: `Failed to delete deployment ${deployment.name}. ${error}`
                    });
                }
            }
        });
    }

    async restartDeployment(deployment: KubernetesDeployment): Promise<void> {
        this.confirmationService.confirm({
            header: 'Restart Deployment',
            message: `Are you sure you want to restart the deployment ${deployment.name}?`,
            icon: 'pi pi-exclamation-triangle',
            accept: async () => {
                try {
                    await this.clusterService.restartDeploymentAsync(this.namespace, deployment.name);
                    this.messageService.add({
                        severity: 'success',
                        summary: 'Success',
                        detail: `Deployment ${deployment.name} restart initiated.`
                    });
                    await this.loadResources();
                } catch (error) {
                    this.messageService.add({
                        severity: 'error',
                        summary: 'Error',
                        detail: `Failed to restart deployment ${deployment.name}. ${error}`
                    });
                }
            }
        });
    }

    async deleteStatefulSet(statefulSet: KubernetesStatefulSet): Promise<void> {
        this.confirmationService.confirm({
            header: 'Delete StatefulSet',
            message: `Are you sure you want to delete the stateful set ${statefulSet.name}?`,
            icon: 'pi pi-exclamation-triangle',
            accept: async () => {
                try {
                    await this.clusterService.deleteStatefulSetAsync(this.namespace, statefulSet.name);
                    this.messageService.add({
                        severity: 'success',
                        summary: 'Success',
                        detail: `StatefulSet ${statefulSet.name} deleted successfully.`
                    });
                    await this.loadResources();
                } catch (error) {
                    this.messageService.add({
                        severity: 'error',
                        summary: 'Error',
                        detail: `Failed to delete stateful set ${statefulSet.name}. ${error}`
                    });
                }
            }
        });
    }

    async restartStatefulSet(statefulSet: KubernetesStatefulSet): Promise<void> {
        this.confirmationService.confirm({
            header: 'Restart StatefulSet',
            message: `Are you sure you want to restart the stateful set ${statefulSet.name}?`,
            icon: 'pi pi-exclamation-triangle',
            accept: async () => {
                try {
                    await this.clusterService.restartStatefulSetAsync(this.namespace, statefulSet.name);
                    this.messageService.add({
                        severity: 'success',
                        summary: 'Success',
                        detail: `StatefulSet ${statefulSet.name} restart initiated.`
                    });
                    await this.loadResources();
                } catch (error) {
                    this.messageService.add({
                        severity: 'error',
                        summary: 'Error',
                        detail: `Failed to restart stateful set ${statefulSet.name}. ${error}`
                    });
                }
            }
        });
    }

    async deleteConfigMap(configMap: KubernetesConfigMap): Promise<void> {
        this.confirmationService.confirm({
            header: 'Delete ConfigMap',
            message: `Are you sure you want to delete the config map ${configMap.name}?`,
            icon: 'pi pi-exclamation-triangle',
            accept: async () => {
                try {
                    await this.clusterService.deleteConfigMapAsync(this.namespace, configMap.name);
                    this.messageService.add({
                        severity: 'success',
                        summary: 'Success',
                        detail: `ConfigMap ${configMap.name} deleted successfully.`
                    });
                    await this.loadResources();
                } catch (error) {
                    this.messageService.add({
                        severity: 'error',
                        summary: 'Error',
                        detail: `Failed to delete config map ${configMap.name}. ${error}`
                    });
                }
            }
        });
    }

    viewConfigMap(configMap: KubernetesConfigMap): void {
        this.selectedConfigMap = configMap;
        this.showConfigMapDialog = true;
    }

    async deleteIngress(ingress: KubernetesIngress): Promise<void> {
        this.confirmationService.confirm({
            header: 'Delete Ingress',
            message: `Are you sure you want to delete the ingress ${ingress.name}?`,
            icon: 'pi pi-exclamation-triangle',
            accept: async () => {
                try {
                    await this.clusterService.deleteIngressAsync(this.namespace, ingress.name);
                    this.messageService.add({
                        severity: 'success',
                        summary: 'Success',
                        detail: `Ingress ${ingress.name} deleted successfully.`
                    });
                    await this.loadResources();
                } catch (error) {
                    this.messageService.add({
                        severity: 'error',
                        summary: 'Error',
                        detail: `Failed to delete ingress ${ingress.name}. ${error}`
                    });
                }
            }
        });
    }

    async deletePVC(pvc: KubernetesPersistentVolumeClaim): Promise<void> {
        this.confirmationService.confirm({
            header: 'Delete PVC',
            message: `Are you sure you want to delete the persistent volume claim ${pvc.name}?`,
            icon: 'pi pi-exclamation-triangle',
            accept: async () => {
                try {
                    await this.clusterService.deletePersistentVolumeClaimAsync(this.namespace, pvc.name);
                    this.messageService.add({
                        severity: 'success',
                        summary: 'Success',
                        detail: `PVC ${pvc.name} deleted successfully.`
                    });
                    await this.loadResources();
                } catch (error) {
                    this.messageService.add({
                        severity: 'error',
                        summary: 'Error',
                        detail: `Failed to delete PVC ${pvc.name}. ${error}`
                    });
                }
            }
        });
    }

    async viewResourceYAML(resource: any, resourceType: string): Promise<void> {
        try {
            this.yamlLoading = true;
            this.showYAMLDialog = true;
            this.yamlDialogTitle = `YAML: ${resource.name}`;
            this.resourceYAML = '';

            const response = await this.clusterService.getResourceYAML(
                this.namespace,
                resourceType,
                resource.name
            );
            this.resourceYAML = response.yaml;
        } catch (error) {
            this.messageService.add({
                severity: 'error',
                summary: 'Error',
                detail: `Failed to load YAML for ${resource.name}`
            });
        } finally {
            this.yamlLoading = false;
        }
    }

    async describeResource(resource: any, resourceType: string): Promise<void> {
        try {
            this.describeLoading = true;
            this.showDescribeDialog = true;
            this.describeDialogTitle = `Describe: ${resource.name}`;
            this.resourceDescription = '';

            const response = await this.clusterService.getResourceDescription(
                this.namespace,
                resourceType,
                resource.name
            );
            this.resourceDescription = response.description;
        } catch (error) {
            this.messageService.add({
                severity: 'error',
                summary: 'Error',
                detail: `Failed to load description for ${resource.name}`
            });
        } finally {
            this.describeLoading = false;
        }
    }
}
