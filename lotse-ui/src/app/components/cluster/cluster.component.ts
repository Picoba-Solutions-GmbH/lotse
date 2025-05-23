import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AccordionModule } from 'primeng/accordion';
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
import { HasRoleDirective } from '../../directives/has-role.directive';
import { Role } from '../../misc/Role';
import { KubernetesNamespace, KubernetesNode, KubernetesPersistentVolume, KubernetesPod } from '../../models/Cluster';
import { AgePipe } from '../../pipes/age.pipe';
import { ClusterService } from '../../services/cluster.service';
import { WebSocketService } from '../../services/websocket.service';

@Component({
  selector: 'app-cluster',
  standalone: true,
  imports: [
    CommonModule,
    TableModule,
    CardModule,
    TagModule,
    ButtonModule,
    AccordionModule,
    TooltipModule,
    AgePipe,
    DialogModule,
    ToastModule,
    ConfirmDialogModule,
    ScrollPanelModule,
    HasRoleDirective,
    SelectButtonModule,
    FormsModule
  ],
  templateUrl: './cluster.component.html',
  styleUrl: './cluster.component.scss',
  providers: [MessageService, ConfirmationService]
})
export class ClusterComponent implements OnInit, OnDestroy {
  PrimeIcons = PrimeIcons;
  Role = Role;
  viewTypes = [
    { label: 'Namespaces', value: 'namespaces' },
    { label: 'Nodes', value: 'nodes' },
    { label: 'Persistent Volumes', value: 'persistentvolumes' }
  ];
  selectedView: string = 'namespaces';

  namespaces: KubernetesNamespace[] = [];
  namespacesLoading: boolean = true;
  showTerminalDialog: boolean = false;
  selectedPodForTerminal: KubernetesPod | null = null;

  nodes: KubernetesNode[] = [];
  persistentVolumes: KubernetesPersistentVolume[] = [];
  loading: boolean = false;

  showYAMLDialog: boolean = false;
  showDescribeDialog: boolean = false;
  yamlLoading: boolean = false;
  describeLoading: boolean = false;
  resourceYAML: string = '';
  resourceDescription: string = '';

  private wsSubscription: Subscription | null = null;

  constructor(
    private clusterService: ClusterService,
    private router: Router,
    private messageService: MessageService,
    private webSocketService: WebSocketService
  ) { }

  async ngOnInit(): Promise<void> {
    this.loadInitialData();
    this.setupWebSocket();
  }

  ngOnDestroy(): void {
    if (this.wsSubscription) {
      this.wsSubscription.unsubscribe();
    }
    this.webSocketService.closeClusterConnection();
  }

  private async loadInitialData(): Promise<void> {
    try {
      this.namespacesLoading = true;
      this.namespaces = await this.clusterService.getNamespacesAsync();
    } catch (error) {
      console.error('Error loading namespaces:', error);
    } finally {
      this.namespacesLoading = false;
    }
  }

  private setupWebSocket(): void {
    this.wsSubscription = this.webSocketService.connectToCluster().subscribe({
      next: (data) => {
        const nodes = data.nodes;
        if (!nodes) {
          return;
        }

        for (const node of nodes) {
          const existingNode = this.nodes.find(n => n.name === node.name);
          if (existingNode) {
            Object.assign(existingNode, node);
          } else {
            this.nodes.push(node);
          }
        }
      },
      error: (error) => {
        console.error('WebSocket error:', error);
        this.messageService.add({ severity: 'error', summary: 'Connection Error', detail: 'Lost connection to server. Retrying...' });
      }
    });
  }

  navigateToNamespacePods(namespace: string): void {
    this.router.navigate(['/cluster', namespace, 'pods']);
  }

  onViewChange(): void {
    this.refreshView();
  }

  refreshView(): void {
    switch (this.selectedView) {
      case 'namespaces':
        this.loadInitialData();
        break;
      case 'nodes':
        this.loadNodes();
        break;
      case 'persistentvolumes':
        this.loadPersistentVolumes();
        break;
    }
  }

  async loadNodes(): Promise<void> {
    try {
      this.loading = true;
      this.nodes = await this.clusterService.getNodesAsync();
    } catch (error) {
      console.error('Error loading nodes:', error);
    } finally {
      this.loading = false;
    }
  }

  async loadPersistentVolumes(): Promise<void> {
    try {
      this.loading = true;
      this.persistentVolumes = await this.clusterService.getPersistentVolumesAsync();
    } catch (error) {
      console.error('Error loading persistent volumes:', error);
    } finally {
      this.loading = false;
    }
  }

  getNodeStatusSeverity(status: string): 'success' | 'info' | 'warn' | 'danger' | 'secondary' {
    switch (status.toLowerCase()) {
      case 'ready':
        return 'success';
      case 'notready':
        return 'danger';
      default:
        return 'warn';
    }
  }

  getPvStatusSeverity(status: string): 'success' | 'info' | 'warn' | 'danger' | 'secondary' {
    switch (status.toLowerCase()) {
      case 'bound':
        return 'success';
      case 'available':
        return 'info';
      case 'released':
        return 'warn';
      case 'failed':
        return 'danger';
      default:
        return 'warn';
    }
  }

  getAddressPairs(node: KubernetesNode): { type: string; value: string }[] {
    return Object.entries(node.addresses || {}).map(([type, value]) => ({ type, value }));
  }

  async viewYAML(resource: any, type: 'node' | 'persistentvolume'): Promise<void> {
    this.showYAMLDialog = true;
    this.yamlLoading = true;
    try {
      const response = type === 'node'
        ? await this.clusterService.getNodeYAML(resource.name)
        : await this.clusterService.getPersistentVolumeYAML(resource.name);
      this.resourceYAML = response.yaml;
    } catch (error) {
      console.error(`Error loading YAML for ${type}:`, error);
    } finally {
      this.yamlLoading = false;
    }
  }

  async describe(resource: any, type: 'node' | 'persistentvolume'): Promise<void> {
    this.showDescribeDialog = true;
    this.describeLoading = true;
    try {
      const response = type === 'node'
        ? await this.clusterService.getNodeDescription(resource.name)
        : await this.clusterService.getPersistentVolumeDescription(resource.name);
      this.resourceDescription = response.description;
    } catch (error) {
      console.error(`Error describing ${type}:`, error);
    } finally {
      this.describeLoading = false;
    }
  }
}
