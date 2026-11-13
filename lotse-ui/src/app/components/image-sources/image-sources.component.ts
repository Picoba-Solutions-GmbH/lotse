import { CommonModule } from '@angular/common';
import { Component, Input, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { ConfirmationService, MessageService, PrimeIcons } from 'primeng/api';
import { AutoCompleteModule } from 'primeng/autocomplete';
import { ButtonModule } from 'primeng/button';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogModule } from 'primeng/dialog';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { ToggleSwitchModule } from 'primeng/toggleswitch';
import { TooltipModule } from 'primeng/tooltip';
import { GitSyncStatus } from '../../models/GitSource';
import { ImageSource, ImageTag } from '../../models/ImageSource';
import { DiscoveredRepository, Registry } from '../../models/Registry';
import { AuthAwareMessageService } from '../../services/auth-aware-message.service';
import { ImageSourceService } from '../../services/image-source.service';
import { RegistryService } from '../../services/registry.service';

interface SourceForm {
    package_name: string;
    registry_id: string;
    repository: string;
    tag_prefix: string;
    auto_sync: boolean;
    prune_previous: boolean;
    poll_interval_seconds: number;
}

const REFRESH_INTERVAL_MS = 15000;

@Component({
    selector: 'app-image-sources',
    standalone: true,
    imports: [
        CommonModule, FormsModule, RouterModule, TableModule, TagModule, ButtonModule, DialogModule, ToastModule,
        ConfirmDialogModule, TooltipModule, InputTextModule, InputNumberModule, SelectModule, AutoCompleteModule,
        ToggleSwitchModule,
    ],
    templateUrl: './image-sources.component.html',
    providers: [{ provide: MessageService, useClass: AuthAwareMessageService }, ConfirmationService],
})
export class ImageSourcesComponent implements OnInit, OnDestroy {
    /** shown as a tab of the Sources page: no page title */
    @Input() embedded = false;

    PrimeIcons = PrimeIcons;

    sources: ImageSource[] = [];
    registries: Registry[] = [];
    loading = true;
    busy = new Set<string>();

    showFormDialog = false;
    editing: ImageSource | null = null;
    form: SourceForm = this.emptyForm();
    saving = false;
    repositories: DiscoveredRepository[] = [];
    repositorySuggestions: string[] = [];
    repositoriesLoading = false;
    repositoriesError: string | null = null;

    showTagsDialog = false;
    tagsSource: ImageSource | null = null;
    tags: ImageTag[] = [];
    tagsLoading = false;

    showWebhookDialog = false;
    webhookSource: ImageSource | null = null;

    private refreshTimer: ReturnType<typeof setInterval> | null = null;

    constructor(
        private imageSourceService: ImageSourceService,
        private registryService: RegistryService,
        private messageService: MessageService,
        private confirmationService: ConfirmationService,
        private route: ActivatedRoute,
    ) { }

    async ngOnInit(): Promise<void> {
        await Promise.all([this.loadSources(), this.loadRegistries()]);
        this.refreshTimer = setInterval(() => this.loadSources(true), REFRESH_INTERVAL_MS);

        // /sources?tab=images&package=<name>[&registry=<id>&repository=<path>]
        const params = this.route.snapshot.queryParamMap;
        if (params.get('tab') === 'images' && (params.has('package') || params.has('repository'))) {
            const packageName = params.get('package') ?? '';
            const existing = this.sources.find(s => s.package_name === packageName);
            if (existing) {
                this.openEditDialog(existing);
            } else {
                this.openCreateDialog(packageName, params.get('registry') ?? undefined, params.get('repository') ?? undefined);
            }
        }
    }

    ngOnDestroy(): void {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
        }
    }

    async loadSources(silent = false): Promise<void> {
        if (!silent) {
            this.loading = true;
        }
        try {
            this.sources = await this.imageSourceService.listAsync();
        } catch (err: any) {
            if (!silent) {
                this.showError(err, 'Failed to load image sources');
            }
        } finally {
            this.loading = false;
        }
    }

    async loadRegistries(): Promise<void> {
        try {
            this.registries = await this.registryService.listAsync();
        } catch {
            this.registries = [];
        }
    }

    // ---------------------------------------------------------------- display

    statusLabel(status: GitSyncStatus): string {
        return { Synced: 'Synced', OutOfSync: 'Out of sync', Error: 'Error', NoTags: 'No tags', Unknown: 'Unknown' }[status] ?? status;
    }

    statusSeverity(status: GitSyncStatus): 'success' | 'warn' | 'danger' | 'secondary' | 'info' {
        return ({ Synced: 'success', OutOfSync: 'warn', Error: 'danger', NoTags: 'info' } as const)[status as 'Synced'] ?? 'secondary';
    }

    shortDigest(digest?: string | null): string {
        return digest ? digest.replace(/^sha256:/, '').substring(0, 12) : '';
    }

    // ---------------------------------------------------------------- actions

    async refresh(source: ImageSource): Promise<void> {
        await this.runBusy(source, async () => {
            const updated = await this.imageSourceService.refreshAsync(source.id);
            this.replaceSource(updated);
            if (updated.status === 'Error') {
                this.messageService.add({ severity: 'error', summary: source.package_name, detail: updated.last_error ?? 'Check failed', life: 8000 });
            } else {
                this.messageService.add({ severity: 'success', summary: source.package_name, detail: `Checked. Latest tag: ${updated.latest_tag ?? 'none'}` });
            }
        });
    }

    async sync(source: ImageSource, tag?: string): Promise<void> {
        await this.runBusy(source, async () => {
            const result = await this.imageSourceService.syncAsync(source.id, tag);
            this.replaceSource(result.source);
            const what = result.action === 'deployed' ? 'deployed' : 'set as default';
            this.messageService.add({ severity: 'success', summary: source.package_name, detail: `Version ${result.version} ${what}` });
            if (this.showTagsDialog && this.tagsSource?.id === source.id) {
                await this.loadTags();
            }
        });
    }

    private async runBusy(source: ImageSource, action: () => Promise<void>): Promise<void> {
        this.busy.add(source.id);
        try {
            await action();
        } catch (err: any) {
            this.showError(err, 'Request failed');
            await this.loadSources(true);
        } finally {
            this.busy.delete(source.id);
        }
    }

    private replaceSource(updated: ImageSource): void {
        this.sources = this.sources.map(s => s.id === updated.id ? updated : s);
    }

    confirmDelete(source: ImageSource): void {
        this.confirmationService.confirm({
            message: `Disconnect ${source.package_name} from ${source.image}? Deployed versions are kept.`,
            header: 'Disconnect image',
            icon: PrimeIcons.EXCLAMATION_TRIANGLE,
            acceptButtonStyleClass: 'p-button-danger',
            accept: async () => {
                try {
                    await this.imageSourceService.deleteAsync(source.id);
                    this.sources = this.sources.filter(s => s.id !== source.id);
                    this.messageService.add({ severity: 'success', summary: 'Disconnected', detail: `${source.package_name} is no longer synced from the registry` });
                } catch (err: any) {
                    this.showError(err, 'Delete failed');
                }
            },
        });
    }

    async openTags(source: ImageSource): Promise<void> {
        this.tagsSource = source;
        this.tags = [];
        this.showTagsDialog = true;
        await this.loadTags();
    }

    async loadTags(): Promise<void> {
        if (!this.tagsSource) {
            return;
        }
        this.tagsLoading = true;
        try {
            this.tags = await this.imageSourceService.listTagsAsync(this.tagsSource.id);
        } catch (err: any) {
            this.showError(err, 'Could not load tags');
        } finally {
            this.tagsLoading = false;
        }
    }

    openWebhook(source: ImageSource): void {
        this.webhookSource = source;
        this.showWebhookDialog = true;
    }

    webhookUrl(source: ImageSource): string {
        return this.imageSourceService.webhookUrl(source);
    }

    async copy(text: string | null | undefined, what: string): Promise<void> {
        if (!text) {
            return;
        }
        try {
            await navigator.clipboard.writeText(text);
            this.messageService.add({ severity: 'info', summary: 'Copied', detail: `${what} copied to the clipboard`, life: 2000 });
        } catch {
            this.messageService.add({ severity: 'warn', summary: 'Copy failed', detail: 'Select the text and copy it manually' });
        }
    }

    // ---------------------------------------------------------------- create / edit

    openCreateDialog(packageName = '', registryId?: string, repository?: string): void {
        this.form = this.emptyForm();
        this.form.package_name = packageName;
        this.form.registry_id = registryId ?? this.registries[0]?.id ?? '';
        this.form.repository = repository ?? '';
        this.editing = null;
        this.showFormDialog = true;
        this.loadRepositories();
    }

    openEditDialog(source: ImageSource): void {
        this.form = {
            package_name: source.package_name,
            registry_id: source.registry_id,
            repository: source.repository,
            tag_prefix: source.tag_prefix,
            auto_sync: source.auto_sync,
            prune_previous: source.prune_previous,
            poll_interval_seconds: source.poll_interval_seconds,
        };
        this.editing = source;
        this.showFormDialog = true;
        this.loadRepositories();
    }

    get selectedRegistry(): Registry | undefined {
        return this.registries.find(r => r.id === this.form.registry_id);
    }

    async loadRepositories(): Promise<void> {
        this.repositories = [];
        this.repositoriesError = null;
        const registry = this.selectedRegistry;
        if (!registry || registry.discovery_path == null) {
            return;
        }
        this.repositoriesLoading = true;
        try {
            this.repositories = await this.registryService.listRepositoriesAsync(registry.id);
        } catch (err: any) {
            this.repositoriesError = err?.error?.detail ?? 'Could not list the images of this registry';
        } finally {
            this.repositoriesLoading = false;
        }
    }

    searchRepositories(event: { query: string }): void {
        const query = (event.query ?? '').toLowerCase();
        this.repositorySuggestions = this.repositories
            .filter(r => !r.registered_as || r.registered_as === this.editing?.package_name)
            .map(r => r.repository)
            .filter(r => r.includes(query));
    }

    onRepositoryChosen(): void {
        if (!this.editing && !this.form.package_name) {
            this.form.package_name = this.form.repository.split('/').filter(p => p).pop() ?? '';
        }
    }

    get imagePreview(): string {
        const host = this.selectedRegistry?.host ?? '<registry>';
        return `${host}/${this.form.repository || '<image>'}:${this.form.tag_prefix}1.2.0`;
    }

    async save(): Promise<void> {
        if (!this.form.registry_id || !this.form.repository.trim()) {
            this.messageService.add({ severity: 'warn', summary: 'Validation', detail: 'Registry and image are required' });
            return;
        }
        const settings = {
            registry_id: this.form.registry_id,
            repository: this.form.repository.trim(),
            tag_prefix: this.form.tag_prefix.trim(),
            auto_sync: this.form.auto_sync,
            prune_previous: this.form.prune_previous,
            poll_interval_seconds: this.form.poll_interval_seconds,
        };
        this.saving = true;
        try {
            if (this.editing) {
                const updated = await this.imageSourceService.updateAsync(this.editing.id, settings);
                this.replaceSource(updated);
                this.messageService.add({ severity: 'success', summary: 'Saved', detail: `${updated.package_name} updated` });
            } else {
                const created = await this.imageSourceService.createAsync({ ...settings, package_name: this.form.package_name.trim() || null });
                this.sources = [...this.sources, created].sort((a, b) => a.package_name.localeCompare(b.package_name));
                const next = created.auto_sync && created.latest_tag ? `Deploying ${created.latest_tag}…` : 'Push a semver tag to deploy a version.';
                this.messageService.add({ severity: 'success', summary: 'Connected', detail: `${created.package_name} is synced from ${created.image}. ${next}`, life: 6000 });
                setTimeout(() => this.loadSources(true), 3000);
            }
            this.showFormDialog = false;
        } catch (err: any) {
            this.showError(err, 'Saving failed');
        } finally {
            this.saving = false;
        }
    }

    private emptyForm(): SourceForm {
        return {
            package_name: '', registry_id: '', repository: '', tag_prefix: '',
            auto_sync: true, prune_previous: false, poll_interval_seconds: 120,
        };
    }

    private showError(err: any, fallback: string): void {
        this.messageService.add({ severity: 'error', summary: 'Error', detail: err?.error?.detail ?? fallback, life: 8000 });
    }
}
