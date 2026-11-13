import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ConfirmationService, MessageService, PrimeIcons } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogModule } from 'primeng/dialog';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';
import { RadioButtonModule } from 'primeng/radiobutton';
import { SelectModule } from 'primeng/select';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { ToggleSwitchModule } from 'primeng/toggleswitch';
import { TooltipModule } from 'primeng/tooltip';
import { HasRoleDirective } from '../../directives/has-role.directive';
import { Role } from '../../misc/Role';
import { DiscoveredRepository, PullSecretMode, Registry, RegistryProvider, RegistryTestResult } from '../../models/Registry';
import { AuthAwareMessageService } from '../../services/auth-aware-message.service';
import { ImageSourceService } from '../../services/image-source.service';
import { RegistryService } from '../../services/registry.service';

interface RegistryForm {
    name: string;
    provider: RegistryProvider;
    host: string;
    discovery_path: string;
    api_url: string;
    username: string;
    token: string;
    clear_token: boolean;
    pull_secret_mode: PullSecretMode;
    pull_secret_name: string;
    auto_register: boolean;
    default_auto_sync: boolean;
    poll_interval_seconds: number;
}

interface ProviderOption {
    label: string;
    value: RegistryProvider;
    host: string;
    pathHint: string;
    tokenHint: string;
}

@Component({
    selector: 'app-registries',
    standalone: true,
    imports: [
        CommonModule, FormsModule, TableModule, TagModule, ButtonModule, DialogModule, ToastModule, ConfirmDialogModule,
        TooltipModule, InputTextModule, InputNumberModule, PasswordModule, RadioButtonModule, SelectModule,
        CheckboxModule, ToggleSwitchModule, HasRoleDirective,
    ],
    templateUrl: './registries.component.html',
    providers: [{ provide: MessageService, useClass: AuthAwareMessageService }, ConfirmationService],
})
export class RegistriesComponent implements OnInit {
    PrimeIcons = PrimeIcons;
    Role = Role;

    readonly providers: ProviderOption[] = [
        { label: 'Azure Container Registry', value: 'acr', host: 'myregistry.azurecr.io', pathHint: 'e.g. lotse',
          tokenHint: 'Token (repository-scoped token or service principal secret) with pull rights. Username = token name / app id.' },
        { label: 'GitHub (ghcr.io)', value: 'ghcr', host: 'ghcr.io', pathHint: 'organization or user, e.g. myorg',
          tokenHint: 'Personal access token with read:packages. Username = GitHub user.' },
        { label: 'GitLab', value: 'gitlab', host: 'registry.gitlab.com', pathHint: 'group or project, e.g. mygroup/apps',
          tokenHint: 'Token with read_registry, plus read_api to list images. Username = token name or user.' },
        { label: 'Docker Hub', value: 'dockerhub', host: 'docker.io', pathHint: 'your namespace, or empty',
          tokenHint: 'Optional: public images like nginx work without credentials (Docker Hub limits anonymous pulls). For private images: personal access token (read-only), username = Docker Hub user.' },
        { label: 'Other (Harbor, Nexus, registry:2, …)', value: 'generic', host: 'registry.example.com', pathHint: 'e.g. lotse',
          tokenHint: 'Username and password or token with pull rights.' },
    ];

    registries: Registry[] = [];
    loading = true;

    showFormDialog = false;
    editing: Registry | null = null;
    form: RegistryForm = this.emptyForm('acr');
    saving = false;
    testing = false;
    testResult: RegistryTestResult | null = null;

    showImagesDialog = false;
    imagesRegistry: Registry | null = null;
    images: DiscoveredRepository[] = [];
    imagesLoading = false;
    discovering = false;
    adding = new Set<string>();

    constructor(
        private registryService: RegistryService,
        private imageSourceService: ImageSourceService,
        private messageService: MessageService,
        private confirmationService: ConfirmationService,
        private router: Router,
    ) { }

    async ngOnInit(): Promise<void> {
        await this.loadRegistries();
    }

    async loadRegistries(): Promise<void> {
        this.loading = true;
        try {
            this.registries = await this.registryService.listAsync();
        } catch (err: any) {
            this.showError(err, 'Failed to load registries');
        } finally {
            this.loading = false;
        }
    }

    providerLabel(value: string): string {
        return this.providers.find(p => p.value === value)?.label ?? value;
    }

    get provider(): ProviderOption {
        return this.providers.find(p => p.value === this.form.provider) ?? this.providers[this.providers.length - 1];
    }

    get needsApiUrl(): boolean {
        return this.form.provider === 'gitlab' && this.form.host.trim() !== '' && this.form.host.trim() !== 'registry.gitlab.com';
    }

    pullSecretLabel(registry: Registry): string {
        switch (registry.pull_secret_mode) {
            case 'lotse': return 'Created by Lotse';
            case 'existing': return 'Existing secret';
            default: return 'Cluster access';
        }
    }

    // ---------------------------------------------------------------- create / edit

    openCreateDialog(): void {
        this.form = this.emptyForm('acr');
        this.editing = null;
        this.testResult = null;
        this.showFormDialog = true;
    }

    openEditDialog(registry: Registry): void {
        this.form = {
            name: registry.name,
            provider: registry.provider,
            host: registry.host,
            discovery_path: registry.discovery_path ?? '',
            api_url: registry.api_url ?? '',
            username: registry.username ?? '',
            token: '',
            clear_token: false,
            pull_secret_mode: registry.pull_secret_mode,
            pull_secret_name: registry.pull_secret_name ?? '',
            auto_register: registry.auto_register,
            default_auto_sync: registry.default_auto_sync,
            poll_interval_seconds: registry.poll_interval_seconds,
        };
        this.editing = registry;
        this.testResult = null;
        this.showFormDialog = true;
    }

    onProviderChange(): void {
        if (!this.editing && (!this.form.host || this.providers.some(p => p.host === this.form.host))) {
            this.form.host = this.form.provider === 'acr' || this.form.provider === 'generic' ? '' : this.provider.host;
        }
    }

    async test(): Promise<void> {
        if (!this.form.host.trim()) {
            this.messageService.add({ severity: 'warn', summary: 'Validation', detail: 'Enter the registry host first' });
            return;
        }
        this.testing = true;
        this.testResult = null;
        try {
            this.testResult = await this.registryService.testAsync({
                host: this.form.host.trim(),
                provider: this.form.provider,
                api_url: this.form.api_url.trim() || null,
                username: this.form.username.trim() || null,
                token: this.form.token || null,
                discovery_path: this.form.discovery_path.trim() || null,
                registry_id: this.editing && !this.form.clear_token ? this.editing.id : null,
            });
        } catch (err: any) {
            this.testResult = { success: false, message: err?.error?.detail ?? 'Test request failed', repositories: [] };
        } finally {
            this.testing = false;
        }
    }

    async save(): Promise<void> {
        if (!this.form.name.trim() || !this.form.host.trim()) {
            this.messageService.add({ severity: 'warn', summary: 'Validation', detail: 'Name and host are required' });
            return;
        }
        const request = {
            name: this.form.name.trim(),
            provider: this.form.provider,
            host: this.form.host.trim(),
            discovery_path: this.form.discovery_path.trim() || null,
            api_url: this.form.api_url.trim() || null,
            username: this.form.username.trim() || null,
            token: this.form.token || null,
            clear_token: this.form.clear_token,
            pull_secret_mode: this.form.pull_secret_mode,
            pull_secret_name: this.form.pull_secret_name.trim() || null,
            auto_register: this.form.auto_register,
            default_auto_sync: this.form.default_auto_sync,
            poll_interval_seconds: this.form.poll_interval_seconds,
        };
        this.saving = true;
        try {
            if (this.editing) {
                const updated = await this.registryService.updateAsync(this.editing.id, request);
                this.registries = this.registries.map(r => r.id === updated.id ? updated : r);
                this.messageService.add({ severity: 'success', summary: 'Saved', detail: `${updated.name} updated` });
            } else {
                const created = await this.registryService.createAsync(request);
                this.registries = [...this.registries, created].sort((a, b) => a.name.localeCompare(b.name));
                const next = created.auto_register ? ' Its images are registered as packages now.' : '';
                this.messageService.add({ severity: 'success', summary: 'Added', detail: `${created.name} added.${next}`, life: 6000 });
                if (created.auto_register) {
                    setTimeout(() => this.loadRegistries(), 4000);
                }
            }
            this.showFormDialog = false;
        } catch (err: any) {
            this.showError(err, 'Saving failed');
        } finally {
            this.saving = false;
        }
    }

    confirmDelete(registry: Registry): void {
        this.confirmationService.confirm({
            message: `Delete registry "${registry.name}"? Its credentials and pull secret are removed.`,
            header: 'Delete registry',
            icon: PrimeIcons.EXCLAMATION_TRIANGLE,
            acceptButtonStyleClass: 'p-button-danger',
            accept: async () => {
                try {
                    await this.registryService.deleteAsync(registry.id);
                    this.registries = this.registries.filter(r => r.id !== registry.id);
                    this.messageService.add({ severity: 'success', summary: 'Deleted', detail: `${registry.name} removed` });
                } catch (err: any) {
                    this.showError(err, 'Delete failed');
                }
            },
        });
    }

    // ---------------------------------------------------------------- images

    async openImages(registry: Registry): Promise<void> {
        this.imagesRegistry = registry;
        this.images = [];
        this.showImagesDialog = true;
        await this.loadImages();
    }

    async loadImages(): Promise<void> {
        if (!this.imagesRegistry) {
            return;
        }
        this.imagesLoading = true;
        try {
            this.images = await this.registryService.listRepositoriesAsync(this.imagesRegistry.id);
        } catch (err: any) {
            this.showError(err, 'Could not list the images');
        } finally {
            this.imagesLoading = false;
        }
    }

    async addImage(image: DiscoveredRepository): Promise<void> {
        if (!this.imagesRegistry) {
            return;
        }
        this.adding.add(image.repository);
        try {
            const source = await this.imageSourceService.createAsync({
                registry_id: this.imagesRegistry.id,
                repository: image.repository,
                package_name: image.package_name,
                tag_prefix: '',
                auto_sync: this.imagesRegistry.default_auto_sync,
                prune_previous: false,
                poll_interval_seconds: 120,
            });
            this.messageService.add({ severity: 'success', summary: 'Connected', detail: `Package ${source.package_name} is synced from ${source.image}` });
            await this.loadImages();
        } catch (err: any) {
            this.showError(err, 'Could not connect the image');
        } finally {
            this.adding.delete(image.repository);
        }
    }

    connectWithOtherName(image: DiscoveredRepository): void {
        this.router.navigate(['/sources'], {
            queryParams: { tab: 'images', registry: this.imagesRegistry?.id, repository: image.repository, package: '' },
        });
    }

    async registerAll(): Promise<void> {
        if (!this.imagesRegistry) {
            return;
        }
        this.discovering = true;
        try {
            const result = await this.registryService.discoverAsync(this.imagesRegistry.id);
            this.registries = this.registries.map(r => r.id === result.registry.id ? result.registry : r);
            this.imagesRegistry = result.registry;
            const detail = result.created.length ? `Registered: ${result.created.join(', ')}` : 'No new images';
            this.messageService.add({ severity: 'success', summary: 'Images registered', detail });
            await this.loadImages();
        } catch (err: any) {
            this.showError(err, 'Registering images failed');
        } finally {
            this.discovering = false;
        }
    }

    private emptyForm(provider: RegistryProvider): RegistryForm {
        return {
            name: '', provider, host: '', discovery_path: '', api_url: '', username: '', token: '', clear_token: false,
            pull_secret_mode: 'none', pull_secret_name: '', auto_register: false, default_auto_sync: true,
            poll_interval_seconds: 300,
        };
    }

    private showError(err: any, fallback: string): void {
        this.messageService.add({ severity: 'error', summary: 'Error', detail: err?.error?.detail ?? fallback, life: 8000 });
    }
}
