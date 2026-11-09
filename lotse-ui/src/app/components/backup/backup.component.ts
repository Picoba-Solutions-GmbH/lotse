import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { DialogModule } from 'primeng/dialog';
import { TagModule } from 'primeng/tag';
import { TooltipModule } from 'primeng/tooltip';
import {
  BackupOptions,
  BackupSelection,
  StorageOverview,
  StoredPackage,
  StoredPackageVersion,
} from '../../models/Backup';
import { AgePipe } from '../../pipes/age.pipe';
import { FileSizePipe } from '../../pipes/file-size.pipe';
import { BackupService } from '../../services/backup.service';

type DownloadScope =
  | { kind: 'all' }
  | { kind: 'package'; pkg: StoredPackage }
  | { kind: 'version'; version: StoredPackageVersion }
  | { kind: 'selection' };

const OPTIONS_STORAGE_KEY = 'backupOptions';
const SELECTION_SEPARATOR = '\u0000';

@Component({
  selector: 'app-backup',
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    ButtonModule,
    CheckboxModule,
    DialogModule,
    TagModule,
    TooltipModule,
    AgePipe,
    FileSizePipe,
  ],
  templateUrl: './backup.component.html',
})
export class BackupComponent implements OnInit {
  overview: StorageOverview | null = null;
  loading = false;
  downloading = false;
  filter = '';

  expanded = new Set<string>();
  selected = new Set<string>();

  showDownloadDialog = false;
  downloadScope: DownloadScope = { kind: 'all' };
  options: BackupOptions = { include_config: true, only_active: false };

  constructor(
    private backupService: BackupService,
    private messageService: MessageService,
  ) {
    this.restoreOptions();
  }

  async ngOnInit(): Promise<void> {
    await this.loadAsync();
  }

  async loadAsync(): Promise<void> {
    this.loading = true;
    try {
      this.overview = await this.backupService.getStorageOverviewAsync();
      this.pruneSelection();
    } catch (error) {
      this.showError('Failed to load storage overview', error);
    } finally {
      this.loading = false;
    }
  }

  get filteredPackages(): StoredPackage[] {
    const packages = this.overview?.packages ?? [];
    const term = this.filter.trim().toLowerCase();
    if (!term) {
      return packages;
    }
    return packages.filter(pkg =>
      pkg.package_name.toLowerCase().includes(term)
      || (pkg.owner ?? '').toLowerCase().includes(term)
      || pkg.versions.some(v => v.version.toLowerCase().includes(term)));
  }

  get diskUsagePercent(): number {
    const disk = this.overview?.location.disk;
    if (!disk || disk.total_bytes === 0) {
      return 0;
    }
    return Math.round((disk.used_bytes / disk.total_bytes) * 100);
  }

  // ---------- expansion ----------

  isExpanded(pkg: StoredPackage): boolean {
    return this.expanded.has(pkg.package_name);
  }

  toggleExpand(pkg: StoredPackage): void {
    if (this.expanded.has(pkg.package_name)) {
      this.expanded.delete(pkg.package_name);
    } else {
      this.expanded.add(pkg.package_name);
    }
  }

  // ---------- selection ----------

  private key(version: StoredPackageVersion): string {
    return version.package_name + SELECTION_SEPARATOR + version.version;
  }

  isVersionSelected(version: StoredPackageVersion): boolean {
    return this.selected.has(this.key(version));
  }

  toggleVersion(version: StoredPackageVersion): void {
    const key = this.key(version);
    if (this.selected.has(key)) {
      this.selected.delete(key);
    } else {
      this.selected.add(key);
    }
  }

  selectedVersionCount(pkg: StoredPackage): number {
    return pkg.versions.filter(v => this.isVersionSelected(v)).length;
  }

  isPackageFullySelected(pkg: StoredPackage): boolean {
    return pkg.versions.length > 0 && this.selectedVersionCount(pkg) === pkg.versions.length;
  }

  isPackagePartiallySelected(pkg: StoredPackage): boolean {
    const count = this.selectedVersionCount(pkg);
    return count > 0 && count < pkg.versions.length;
  }

  togglePackage(pkg: StoredPackage): void {
    const selectAll = !this.isPackageFullySelected(pkg);
    for (const version of pkg.versions) {
      if (selectAll) {
        this.selected.add(this.key(version));
      } else {
        this.selected.delete(this.key(version));
      }
    }
  }

  get allVisibleSelected(): boolean {
    const packages = this.filteredPackages;
    return packages.length > 0 && packages.every(pkg => this.isPackageFullySelected(pkg));
  }

  get someVisibleSelected(): boolean {
    return !this.allVisibleSelected && this.filteredPackages.some(pkg => this.selectedVersionCount(pkg) > 0);
  }

  toggleAllVisible(): void {
    const selectAll = !this.allVisibleSelected;
    for (const pkg of this.filteredPackages) {
      for (const version of pkg.versions) {
        if (selectAll) {
          this.selected.add(this.key(version));
        } else {
          this.selected.delete(this.key(version));
        }
      }
    }
  }

  clearSelection(): void {
    this.selected.clear();
  }

  get selectedVersions(): StoredPackageVersion[] {
    return (this.overview?.packages ?? [])
      .flatMap(pkg => pkg.versions)
      .filter(v => this.isVersionSelected(v));
  }

  private pruneSelection(): void {
    const existing = new Set(this.overview?.packages.flatMap(pkg => pkg.versions.map(v => this.key(v))) ?? []);
    for (const key of [...this.selected]) {
      if (!existing.has(key)) {
        this.selected.delete(key);
      }
    }
  }

  // ---------- download ----------

  openDownload(scope: DownloadScope): void {
    this.downloadScope = scope;
    this.showDownloadDialog = true;
  }

  get scopeVersions(): StoredPackageVersion[] {
    const scope = this.downloadScope;
    let versions: StoredPackageVersion[];
    switch (scope.kind) {
      case 'all':
        versions = (this.overview?.packages ?? []).flatMap(pkg => pkg.versions);
        break;
      case 'package':
        versions = scope.pkg.versions;
        break;
      case 'version':
        return [scope.version];
      case 'selection':
        versions = this.selectedVersions;
        break;
    }
    return this.options.only_active ? versions.filter(v => v.active) : versions;
  }

  get scopeTitle(): string {
    const scope = this.downloadScope;
    switch (scope.kind) {
      case 'all':
        return 'Download all packages';
      case 'package':
        return `Download ${scope.pkg.package_name}`;
      case 'version':
        return `Download ${scope.version.package_name} ${scope.version.version}`;
      case 'selection':
        return 'Download selection';
    }
  }

  get canFilterActive(): boolean {
    return this.downloadScope.kind !== 'version';
  }

  /** Rough size of the zip: the uploaded archive, or the files of versions without one. */
  get estimatedSize(): number {
    return this.scopeVersions.reduce(
      (sum, v) => sum + (v.has_archive ? v.archive_size_bytes : v.size_bytes), 0);
  }

  get scopeVersionsWithoutArchive(): number {
    return this.scopeVersions.filter(v => !v.has_archive && v.runtime !== 'container').length;
  }

  get scopeContainerVersions(): number {
    return this.scopeVersions.filter(v => v.runtime === 'container').length;
  }

  get zipLayout(): string {
    const entries = this.options.include_config ? '<package>.7z, config.yaml' : '<package>.7z';
    return `manifest.json\n<package>/<version>/${entries}`;
  }

  async confirmDownloadAsync(): Promise<void> {
    if (this.scopeVersions.length === 0) {
      return;
    }

    const scope = this.downloadScope;
    let packages: BackupSelection[] | null = null;
    let fallbackName = 'lotse-backup.zip';
    switch (scope.kind) {
      case 'all':
        fallbackName = 'lotse-backup-all-packages.zip';
        break;
      case 'package':
        packages = [{ package_name: scope.pkg.package_name }];
        fallbackName = `lotse-backup-${scope.pkg.package_name}.zip`;
        break;
      case 'version':
        packages = [{ package_name: scope.version.package_name, versions: [scope.version.version] }];
        fallbackName = `lotse-backup-${scope.version.package_name}-${scope.version.version}.zip`;
        break;
      case 'selection': {
        const grouped = new Map<string, string[]>();
        for (const version of this.selectedVersions) {
          grouped.set(version.package_name, [...(grouped.get(version.package_name) ?? []), version.version]);
        }
        packages = [...grouped.entries()].map(([package_name, versions]) => ({ package_name, versions }));
        fallbackName = 'lotse-backup-selection.zip';
        break;
      }
    }

    this.downloading = true;
    this.persistOptions();
    try {
      await this.backupService.downloadBackupAsync({
        packages,
        include_config: this.options.include_config,
        only_active: scope.kind === 'version' ? false : this.options.only_active,
      }, fallbackName);
      this.showDownloadDialog = false;
      this.messageService.add({
        severity: 'success',
        summary: 'Backup created',
        detail: `${this.scopeVersions.length} version(s) downloaded`,
        life: 3000,
      });
    } catch (error) {
      await this.showBlobError('Backup failed', error);
    } finally {
      this.downloading = false;
    }
  }

  // ---------- misc ----------

  async copyAsync(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      this.messageService.add({ severity: 'info', summary: 'Copied', detail: text, life: 2000 });
    } catch {
      this.messageService.add({ severity: 'warn', summary: 'Clipboard not available', detail: text, life: 4000 });
    }
  }

  private restoreOptions(): void {
    try {
      const stored = localStorage.getItem(OPTIONS_STORAGE_KEY);
      if (stored) {
        const { include_config, only_active } = JSON.parse(stored);
        this.options = {
          include_config: include_config ?? this.options.include_config,
          only_active: only_active ?? this.options.only_active,
        };
      }
    } catch {
      // ignore broken or unavailable storage
    }
  }

  private persistOptions(): void {
    try {
      localStorage.setItem(OPTIONS_STORAGE_KEY, JSON.stringify(this.options));
    } catch {
      // ignore unavailable storage
    }
  }

  /** Errors of blob requests carry their JSON body as a Blob. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private async showBlobError(summary: string, error: any): Promise<void> {
    let detail = 'Unknown error';
    try {
      if (error?.error instanceof Blob) {
        const text = await error.error.text();
        try {
          detail = JSON.parse(text)?.detail ?? text;
        } catch {
          detail = text || detail;
        }
      } else {
        detail = error?.error?.detail ?? error?.message ?? detail;
      }
    } catch {
      // keep default detail
    }
    this.messageService.add({ severity: 'error', summary, detail, life: 6000 });
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private showError(summary: string, error: any): void {
    this.messageService.add({
      severity: 'error', summary, detail: error?.error?.detail ?? 'Unknown error', life: 5000,
    });
  }
}
