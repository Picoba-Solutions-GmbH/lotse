import { CommonModule } from '@angular/common';
import { Component, Input, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterModule } from '@angular/router';
import { ConfirmationService, MessageService, PrimeIcons } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogModule } from 'primeng/dialog';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { ToggleSwitchModule } from 'primeng/toggleswitch';
import { TooltipModule } from 'primeng/tooltip';
import { GitConnectionTestResult, GitSource, GitSourceCreateRequest, GitSyncStatus, GitTag } from '../../models/GitSource';
import { AuthAwareMessageService } from '../../services/auth-aware-message.service';
import { GitSourceService } from '../../services/git-source.service';

type DialogMode = 'create' | 'edit';

interface SourceForm {
    package_name: string;
    repo_url: string;
    path: string;
    tag_prefix: string;
    username: string;
    token: string;
    clear_token: boolean;
    auto_sync: boolean;
    prune_previous: boolean;
    poll_interval_seconds: number;
}

const REFRESH_INTERVAL_MS = 15000;

@Component({
    selector: 'app-git-sources',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        RouterModule,
        TableModule,
        TagModule,
        ButtonModule,
        DialogModule,
        ToastModule,
        ConfirmDialogModule,
        TooltipModule,
        InputTextModule,
        InputNumberModule,
        PasswordModule,
        CheckboxModule,
        ToggleSwitchModule,
    ],
    templateUrl: './git-sources.component.html',
    styleUrl: './git-sources.component.scss',
    providers: [{ provide: MessageService, useClass: AuthAwareMessageService }, ConfirmationService],
})
export class GitSourcesComponent implements OnInit, OnDestroy {
    /** shown as a tab of the Sources page: no page title */
    @Input() embedded = false;

    PrimeIcons = PrimeIcons;

    sources: GitSource[] = [];
    loading = true;
    /** ids of sources with a running refresh or sync */
    busy = new Set<string>();

    showFormDialog = false;
    formMode: DialogMode = 'create';
    editing: GitSource | null = null;
    form: SourceForm = this.emptyForm();
    saving = false;
    testing = false;
    testResult: GitConnectionTestResult | null = null;

    showTagsDialog = false;
    tagsSource: GitSource | null = null;
    tags: GitTag[] = [];
    tagsLoading = false;

    showWebhookDialog = false;
    webhookSource: GitSource | null = null;

    private refreshTimer: ReturnType<typeof setInterval> | null = null;

    constructor(
        private gitSourceService: GitSourceService,
        private messageService: MessageService,
        private confirmationService: ConfirmationService,
        private route: ActivatedRoute,
    ) { }

    async ngOnInit(): Promise<void> {
        await this.loadSources();
        this.refreshTimer = setInterval(() => this.loadSources(true), REFRESH_INTERVAL_MS);

        // "Connect Git repository" from a package page or the deploy dialog: /git-sources?package=<name>
        const queryParams = this.route.snapshot.queryParamMap;
        if (queryParams.has('package') && queryParams.get('tab') !== 'images') {
            const packageName = queryParams.get('package') ?? '';
            const existing = this.sources.find(s => s.package_name === packageName);
            if (existing) {
                this.openEditDialog(existing);
            } else {
                this.openCreateDialog(packageName);
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
            this.sources = await this.gitSourceService.listAsync();
        } catch (err: any) {
            if (!silent) {
                this.showError(err, 'Failed to load Git sources');
            }
        } finally {
            this.loading = false;
        }
    }

    // ---------------------------------------------------------------- status

    statusLabel(status: GitSyncStatus): string {
        switch (status) {
            case 'Synced': return 'Synced';
            case 'OutOfSync': return 'Out of sync';
            case 'Error': return 'Error';
            case 'NoTags': return 'No tags';
            default: return 'Unknown';
        }
    }

    statusSeverity(status: GitSyncStatus): 'success' | 'warn' | 'danger' | 'secondary' | 'info' {
        switch (status) {
            case 'Synced': return 'success';
            case 'OutOfSync': return 'warn';
            case 'Error': return 'danger';
            case 'NoTags': return 'info';
            default: return 'secondary';
        }
    }

    shortCommit(commit?: string | null): string {
        return commit ? commit.substring(0, 7) : '';
    }

    repositoryLabel(source: GitSource): string {
        return source.repo_url.replace(/^https?:\/\//, '').replace(/\.git$/, '');
    }

    // ---------------------------------------------------------------- actions

    async refresh(source: GitSource): Promise<void> {
        await this.runBusy(source, async () => {
            const updated = await this.gitSourceService.refreshAsync(source.id);
            this.replaceSource(updated);
            if (updated.status === 'Error') {
                this.messageService.add({ severity: 'error', summary: source.package_name, detail: updated.last_error ?? 'Check failed', life: 8000 });
            } else {
                this.messageService.add({ severity: 'success', summary: source.package_name, detail: `Checked. Latest tag: ${updated.latest_tag ?? 'none'}` });
            }
        });
    }

    async sync(source: GitSource, tag?: string): Promise<void> {
        await this.runBusy(source, async () => {
            const result = await this.gitSourceService.syncAsync(source.id, tag);
            this.replaceSource(result.source);
            const what = result.action === 'deployed' ? 'deployed' : 'set as default';
            this.messageService.add({ severity: 'success', summary: source.package_name, detail: `Version ${result.version} (${result.tag}) ${what}` });
            if (this.showTagsDialog && this.tagsSource?.id === source.id) {
                await this.loadTags();
            }
        });
    }

    private async runBusy(source: GitSource, action: () => Promise<void>): Promise<void> {
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

    private replaceSource(updated: GitSource): void {
        this.sources = this.sources.map(s => s.id === updated.id ? updated : s);
    }

    confirmDelete(source: GitSource): void {
        this.confirmationService.confirm({
            message: `Disconnect ${source.package_name} from ${this.repositoryLabel(source)}? Deployed versions are kept.`,
            header: 'Disconnect repository',
            icon: PrimeIcons.EXCLAMATION_TRIANGLE,
            acceptButtonStyleClass: 'p-button-danger',
            accept: async () => {
                try {
                    await this.gitSourceService.deleteAsync(source.id);
                    this.sources = this.sources.filter(s => s.id !== source.id);
                    this.messageService.add({ severity: 'success', summary: 'Disconnected', detail: `${source.package_name} is no longer synced from Git` });
                } catch (err: any) {
                    this.showError(err, 'Delete failed');
                }
            },
        });
    }

    // ---------------------------------------------------------------- tags

    async openTags(source: GitSource): Promise<void> {
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
            this.tags = await this.gitSourceService.listTagsAsync(this.tagsSource.id);
        } catch (err: any) {
            this.showError(err, 'Could not load tags');
        } finally {
            this.tagsLoading = false;
        }
    }

    // ---------------------------------------------------------------- webhook

    openWebhook(source: GitSource): void {
        this.webhookSource = source;
        this.showWebhookDialog = true;
    }

    webhookUrl(source: GitSource): string {
        return this.gitSourceService.webhookUrl(source);
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

    openCreateDialog(packageName = ''): void {
        this.form = this.emptyForm();
        this.form.package_name = packageName;
        this.formMode = 'create';
        this.editing = null;
        this.testResult = null;
        this.showFormDialog = true;
    }

    openEditDialog(source: GitSource): void {
        this.form = {
            package_name: source.package_name,
            repo_url: source.repo_url,
            path: source.path,
            tag_prefix: source.tag_prefix,
            username: source.username ?? '',
            token: '',
            clear_token: false,
            auto_sync: source.auto_sync,
            prune_previous: source.prune_previous,
            poll_interval_seconds: source.poll_interval_seconds,
        };
        this.formMode = 'edit';
        this.editing = source;
        this.testResult = null;
        this.showFormDialog = true;
    }

    get exampleTag(): string {
        return `${this.form.tag_prefix}1.2.0`;
    }

    async testConnection(): Promise<void> {
        if (!this.form.repo_url) {
            this.messageService.add({ severity: 'warn', summary: 'Validation', detail: 'Enter the repository URL first' });
            return;
        }
        this.testing = true;
        this.testResult = null;
        try {
            this.testResult = await this.gitSourceService.testConnectionAsync({
                repo_url: this.form.repo_url,
                tag_prefix: this.form.tag_prefix,
                username: this.form.username || null,
                token: this.form.token || null,
                source_id: this.formMode === 'edit' && !this.form.clear_token ? this.editing?.id : null,
            });
        } catch (err: any) {
            this.testResult = { success: false, message: err?.error?.detail ?? 'Test request failed', tags: [] };
        } finally {
            this.testing = false;
        }
    }

    async save(): Promise<void> {
        if (!this.form.package_name.trim() || !this.form.repo_url.trim()) {
            this.messageService.add({ severity: 'warn', summary: 'Validation', detail: 'Package name and repository URL are required' });
            return;
        }

        const settings = {
            repo_url: this.form.repo_url.trim(),
            path: this.form.path.trim(),
            tag_prefix: this.form.tag_prefix.trim(),
            username: this.form.username.trim() || null,
            auto_sync: this.form.auto_sync,
            prune_previous: this.form.prune_previous,
            poll_interval_seconds: this.form.poll_interval_seconds,
        };

        this.saving = true;
        try {
            if (this.formMode === 'create') {
                const request: GitSourceCreateRequest = { ...settings, package_name: this.form.package_name.trim(), token: this.form.token || null };
                const created = await this.gitSourceService.createAsync(request);
                this.sources = [...this.sources, created].sort((a, b) => a.package_name.localeCompare(b.package_name));
                const next = created.auto_sync && created.latest_tag
                    ? `Deploying ${created.latest_tag}…`
                    : 'Push a tag like ' + this.exampleTag + ' to deploy a version.';
                this.messageService.add({ severity: 'success', summary: 'Connected', detail: `${created.package_name} is synced from Git. ${next}`, life: 6000 });
                this.showFormDialog = false;
                // pick up the result of the first sync, which runs in the background
                setTimeout(() => this.loadSources(true), 3000);
            } else if (this.editing) {
                const updated = await this.gitSourceService.updateAsync(this.editing.id, {
                    ...settings,
                    token: this.form.token || null,
                    clear_token: this.form.clear_token,
                });
                this.replaceSource(updated);
                this.messageService.add({ severity: 'success', summary: 'Saved', detail: `${updated.package_name} updated` });
                this.showFormDialog = false;
            }
        } catch (err: any) {
            this.showError(err, 'Saving failed');
        } finally {
            this.saving = false;
        }
    }

    private emptyForm(): SourceForm {
        return {
            package_name: '',
            repo_url: '',
            path: '',
            tag_prefix: 'v',
            username: '',
            token: '',
            clear_token: false,
            auto_sync: true,
            prune_previous: false,
            poll_interval_seconds: 120,
        };
    }

    private showError(err: any, fallback: string): void {
        this.messageService.add({ severity: 'error', summary: 'Error', detail: err?.error?.detail ?? fallback, life: 8000 });
    }
}
