import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ConfirmationService, MessageService, PrimeIcons } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogModule } from 'primeng/dialog';
import { DropdownModule } from 'primeng/dropdown';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';
import { RadioButtonModule } from 'primeng/radiobutton';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { TextareaModule } from 'primeng/textarea';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { HasRoleDirective } from '../../directives/has-role.directive';
import { Role } from '../../misc/Role';
import { KubernetesSecret } from '../../models/Cluster';
import { NetworkShareDetail, NetworkShareProvisionRequest, NetworkShareTestResult, NetworkShareUpdateRequest, NetworkShareVolume } from '../../models/NetworkShare';
import { ClusterService } from '../../services/cluster.service';
import { NetworkShareService } from '../../services/network-share.service';

interface SecretOption { label: string; value: string; namespace: string; }
type DialogMode = 'provision' | 'edit';
type SecretMode = 'new' | 'existing' | 'keep';

@Component({
    selector: 'app-network-shares',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        TableModule,
        CardModule,
        TagModule,
        ButtonModule,
        DialogModule,
        ToastModule,
        ConfirmDialogModule,
        TooltipModule,
        InputTextModule,
        PasswordModule,
        RadioButtonModule,
        DropdownModule,
        TextareaModule,
        HasRoleDirective,
    ],
    templateUrl: './network-shares.component.html',
    styleUrl: './network-shares.component.scss',
    providers: [MessageService, ConfirmationService],
})
export class NetworkSharesComponent implements OnInit {
    PrimeIcons = PrimeIcons;
    Role = Role;

    shares: NetworkShareVolume[] = [];
    sharesLoading = true;
    showFormDialog = false;
    formMode: DialogMode = 'provision';
    editingId: string | null = null;
    saving = false;
    secretMode: SecretMode = 'new';
    availableSecrets: SecretOption[] = [];
    secretsLoading = false;
    secretNamespaceForLookup = 'default';
    availableNamespaces: string[] = [];
    namespacesLoading = false;
    form: NetworkShareProvisionRequest = this.emptyForm();
    showDetailDialog = false;
    detailLoading = false;
    detail: NetworkShareDetail | null = null;
    testRunning = false;
    testResult: NetworkShareTestResult | null = null;

    constructor(
        private networkShareService: NetworkShareService,
        private clusterService: ClusterService,
        private messageService: MessageService,
        private confirmationService: ConfirmationService
    ) { }

    async ngOnInit(): Promise<void> {
        await this.loadShares();
    }

    async loadShares(): Promise<void> {
        this.sharesLoading = true;
        try {
            this.shares = await this.networkShareService.listNetworkShares();
        } catch {
            this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to load network shares' });
        } finally {
            this.sharesLoading = false;
        }
    }

    async openDetail(share: NetworkShareVolume): Promise<void> {
        this.detail = null;
        this.testResult = null;
        this.showDetailDialog = true;
        this.detailLoading = true;
        try {
            this.detail = await this.networkShareService.getNetworkShareDetail(share.id);
        } catch (err: any) {
            this.messageService.add({ severity: 'error', summary: 'Error', detail: err?.error?.detail ?? 'Could not load details' });
            this.showDetailDialog = false;
        } finally {
            this.detailLoading = false;
        }
    }

    pvStatusSeverity(status: string): 'success' | 'warn' | 'danger' | 'secondary' {
        if (status === 'Bound') return 'success';
        if (status === 'Available') return 'warn';
        if (status === 'NotFound') return 'danger';
        return 'secondary';
    }

    async runTest(): Promise<void> {
        if (!this.detail) return;
        this.testRunning = true;
        this.testResult = null;
        try {
            this.testResult = await this.networkShareService.testNetworkShare(this.detail.id);
        } catch (err: any) {
            this.testResult = { success: false, message: err?.error?.detail ?? 'Test request failed' };
        } finally {
            this.testRunning = false;
        }
    }

    openProvisionDialog(): void {
        this.form = this.emptyForm();
        this.secretMode = 'new';
        this.availableSecrets = [];
        this.secretNamespaceForLookup = 'default';
        this.formMode = 'provision';
        this.editingId = null;
        this.showFormDialog = true;
        this.loadNamespaces();
    }

    async openEditDialog(share: NetworkShareVolume): Promise<void> {
        this.detailLoading = true;
        let d: NetworkShareDetail;
        try {
            d = await this.networkShareService.getNetworkShareDetail(share.id);
        } catch (err: any) {
            this.messageService.add({ severity: 'error', summary: 'Error', detail: err?.error?.detail ?? 'Could not load share details for editing' });
            this.detailLoading = false;
            return;
        } finally {
            this.detailLoading = false;
        }

        this.form = {
            name: d.name,
            share_path: d.share_path,
            storage_size: d.storage_size,
            namespace: d.namespace,
            access_modes: [...d.access_modes],
            mount_options: [...d.mount_options],
            secret_namespace: d.secret_namespace || 'default',
        };
        this.secretMode = 'keep';
        this.availableSecrets = [];
        this.secretNamespaceForLookup = d.secret_namespace || 'default';
        this.formMode = 'edit';
        this.editingId = share.id;
        this.showFormDialog = true;
        this.loadNamespaces();
    }

    get formDialogHeader(): string {
        return this.formMode === 'edit' ? 'Edit Network Share' : 'Add Network Share';
    }

    get showKeepOption(): boolean {
        return this.formMode === 'edit';
    }

    async onSecretModeChange(): Promise<void> {
        if (this.secretMode === 'existing') {
            await this.loadSecrets();
        } else {
            this.form.secret_name = undefined;
        }
    }

    async onSecretNamespaceChange(value: string): Promise<void> {
        this.secretNamespaceForLookup = value;
        if (this.secretMode === 'existing') {
            await this.loadSecrets();
        }
    }

    async loadNamespaces(): Promise<void> {
        this.namespacesLoading = true;
        try {
            const ns = await this.clusterService.getNamespacesAsync();
            this.availableNamespaces = ns.map((n) => n.name);
        } catch {
            this.availableNamespaces = [];
        } finally {
            this.namespacesLoading = false;
        }
    }

    async loadSecrets(): Promise<void> {
        this.secretsLoading = true;
        this.availableSecrets = [];
        try {
            const secrets: KubernetesSecret[] = await this.clusterService.getSecretsForNamespaceAsync(
                this.secretNamespaceForLookup
            );
            this.availableSecrets = secrets.map((s) => ({ label: s.name, value: s.name, namespace: s.namespace }));
        } catch {
            this.messageService.add({ severity: 'warn', summary: 'Warning', detail: 'Could not load secrets for that namespace' });
        } finally {
            this.secretsLoading = false;
        }
    }

    async save(): Promise<void> {
        if (!this.form.name || !this.form.share_path) {
            this.messageService.add({ severity: 'warn', summary: 'Validation', detail: 'Name and share path are required' });
            return;
        }

        if (this.secretMode === 'existing' && !this.form.secret_name) {
            this.messageService.add({ severity: 'warn', summary: 'Validation', detail: 'Please select a secret' });
            return;
        }
        if (this.secretMode === 'new' && (!this.form.username || !this.form.password)) {
            this.messageService.add({ severity: 'warn', summary: 'Validation', detail: 'Username and password are required' });
            return;
        }

        this.saving = true;
        try {
            if (this.formMode === 'provision') {
                if (this.secretMode === 'existing') {
                    this.form.secret_namespace = this.secretNamespaceForLookup;
                    this.form.username = undefined;
                    this.form.password = undefined;
                } else {
                    this.form.secret_name = undefined;
                }
                await this.networkShareService.provisionNetworkShare(this.form);
                this.messageService.add({ severity: 'success', summary: 'Provisioned', detail: `"${this.form.name}" created successfully` });
            } else {
                const req: NetworkShareUpdateRequest = {
                    name: this.form.name,
                    share_path: this.form.share_path,
                    storage_size: this.form.storage_size,
                    namespace: this.form.namespace,
                    access_modes: this.form.access_modes,
                    mount_options: this.form.mount_options,
                    secret_mode: this.secretMode,
                    secret_name: this.secretMode === 'existing' ? this.form.secret_name : undefined,
                    secret_namespace: this.secretNamespaceForLookup,
                    username: this.secretMode === 'new' ? this.form.username : undefined,
                    password: this.secretMode === 'new' ? this.form.password : undefined,
                };
                await this.networkShareService.updateNetworkShare(this.editingId!, req);
                this.messageService.add({ severity: 'success', summary: 'Updated', detail: `"${this.form.name}" updated successfully` });
            }
            this.showFormDialog = false;
            await this.loadShares();
        } catch (err: any) {
            const detail = err?.error?.detail ?? `${this.formMode === 'edit' ? 'Update' : 'Provisioning'} failed`;
            this.messageService.add({ severity: 'error', summary: 'Error', detail });
        } finally {
            this.saving = false;
        }
    }

    confirmDelete(share: NetworkShareVolume): void {
        this.confirmationService.confirm({
            message: `Delete network share "${share.name}" and its PV/PVC from Kubernetes?`,
            header: 'Confirm Delete',
            icon: PrimeIcons.EXCLAMATION_TRIANGLE,
            acceptButtonStyleClass: 'p-button-danger',
            accept: () => this.deleteShare(share),
        });
    }

    async deleteShare(share: NetworkShareVolume): Promise<void> {
        try {
            await this.networkShareService.deleteNetworkShare(share.id);
            this.messageService.add({ severity: 'success', summary: 'Deleted', detail: `"${share.name}" removed` });
            this.shares = this.shares.filter((s) => s.id !== share.id);
        } catch (err: any) {
            this.messageService.add({ severity: 'error', summary: 'Error', detail: err?.error?.detail ?? 'Delete failed' });
        }
    }

    private emptyForm(): NetworkShareProvisionRequest {
        return {
            name: '',
            share_path: '',
            storage_size: '100Gi',
            namespace: '',
            access_modes: ['ReadWriteMany'],
            mount_options: ['dir_mode=0777', 'file_mode=0777'],
            secret_namespace: 'default',
        };
    }

    get mountOptionsText(): string {
        return this.form.mount_options.join('\n');
    }

    set mountOptionsText(value: string) {
        this.form.mount_options = value.split('\n').map((s) => s.trim()).filter((s) => s.length > 0);
    }
}
