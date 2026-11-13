import { CommonModule } from '@angular/common';
import { Component, OnInit, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { ConfirmationService, MessageService, PrimeIcons } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { DialogModule } from 'primeng/dialog';
import { DropdownModule } from 'primeng/dropdown';
import { InputTextModule } from 'primeng/inputtext';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { PackageStatus } from '../../../misc/PackageStatus';
import { GitSource } from '../../../models/GitSource';
import { PackageDetail } from '../../../models/Package';
import { PackageAccess, PackagePermissions } from '../../../models/PackageAccess';
import { PackageCountByStatePipe } from "../../../pipes/package-count-by-state.pipe";
import { PackageStatusToSeverityPipe } from "../../../pipes/package-status.pipe";
import { FeatureFlagService } from '../../../services/feature-flag.service';
import { GitSourceService } from '../../../services/git-source.service';
import { PackageAccessService } from '../../../services/package-access.service';
import { PackageService } from '../../../services/package.service';
import { PackageDeployComponent } from '../package-deploy/package-deploy.component';
import { PackageShareDialogComponent } from '../package-share-dialog/package-share-dialog.component';

@Component({
  selector: 'app-package-management',
  imports: [
    CommonModule,
    FormsModule,
    TableModule,
    CardModule,
    TagModule,
    ButtonModule,
    InputTextModule,
    TooltipModule,
    DropdownModule,
    DialogModule,
    ToastModule,
    PackageStatusToSeverityPipe,
    PackageCountByStatePipe,
    PackageDeployComponent,
    PackageShareDialogComponent
  ],
  templateUrl: './package-management.component.html',
  styleUrl: './package-management.component.scss'
})
export class PackageManagementComponent implements OnInit {
  packages: PackageDetail[] = [];
  availablePackageVersions: string[] = [];
  selectedPackage: PackageDetail | undefined;
  packageName: string = '';
  loading: boolean = true;
  PackageStatus = PackageStatus;
  PrimeIcons = PrimeIcons;
  isAuthenticationEnabled: boolean = false;
  access: PackageAccess | null = null;
  permissions: PackagePermissions = { view: false, execute: false, edit: false, manage: false };
  showShareDialog = false;
  gitSource: GitSource | null = null;
  gitSyncing = false;

  @ViewChild(PackageDeployComponent) packageDeploy!: PackageDeployComponent;

  constructor(
    private packageService: PackageService,
    private route: ActivatedRoute,
    private router: Router,
    private messageService: MessageService,
    private confirmationService: ConfirmationService,
    private featureFlagService: FeatureFlagService,
    private packageAccessService: PackageAccessService,
    private gitSourceService: GitSourceService
  ) { }

  async ngOnInit(): Promise<void> {
    this.packageName = this.route.snapshot.params['package_name'];
    await Promise.all([this.loadPackages(), this.loadAccess(), this.loadGitSource()]);
    this.isAuthenticationEnabled = await this.featureFlagService.isAuthenticationEnabled();
  }

  async loadGitSource(): Promise<void> {
    try {
      this.gitSource = await this.gitSourceService.getForPackageAsync(this.packageName);
    } catch {
      this.gitSource = null;
    }
  }

  get gitStatusSeverity(): 'success' | 'warn' | 'danger' | 'secondary' | 'info' {
    switch (this.gitSource?.status) {
      case 'Synced': return 'success';
      case 'OutOfSync': return 'warn';
      case 'Error': return 'danger';
      case 'NoTags': return 'info';
      default: return 'secondary';
    }
  }

  get gitStatusLabel(): string {
    switch (this.gitSource?.status) {
      case 'OutOfSync': return 'Out of sync';
      case 'NoTags': return 'No tags';
      default: return this.gitSource?.status ?? '';
    }
  }

  get gitRepositoryLabel(): string {
    const url = this.gitSource?.repo_url ?? '';
    const name = url.replace(/\.git$/, '').split('/').filter(part => part).pop() ?? url;
    return this.gitSource?.path ? `${name}/${this.gitSource.path}` : name;
  }

  connectGitRepository(): void {
    this.router.navigate(['/git-sources'], { queryParams: { package: this.packageName } });
  }

  async syncFromGit(): Promise<void> {
    if (!this.gitSource) {
      return;
    }
    this.gitSyncing = true;
    try {
      const result = await this.gitSourceService.syncAsync(this.gitSource.id);
      this.gitSource = result.source;
      const what = result.action === 'deployed' ? 'deployed' : 'set as default';
      this.messageService.add({ severity: 'success', summary: 'Synced', detail: `Version ${result.version} (${result.tag}) ${what}` });
      await this.loadPackages();
    } catch (err: any) {
      this.messageService.add({ severity: 'error', summary: 'Sync failed', detail: err?.error?.detail ?? 'Sync failed', life: 8000 });
      await this.loadGitSource();
    } finally {
      this.gitSyncing = false;
    }
  }

  async loadAccess(): Promise<void> {
    try {
      this.access = await this.packageAccessService.getAccessAsync(this.packageName);
      this.permissions = this.access.permissions;
    } catch {
      this.access = null;
      this.permissions = { view: false, execute: false, edit: false, manage: false };
    }
  }

  async loadPackages(): Promise<void> {
    try {
      this.loading = true;
      this.packages = await this.packageService.getPackageOverviewAsync(this.packageName);
      this.availablePackageVersions = this.packages.map(pkg => pkg.version);
    } catch (error) {
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load packages'
      });
    } finally {
      this.loading = false;
    }
  }

  onPackageSelect(clickedPackage: PackageDetail): void {
    this.router.navigate(['/packages', this.packageName, clickedPackage.version]);
  }

  showDeployPackageDialog(): void {
    this.packageDeploy.showDeployPackageDialog();
  }

  async onPackageDeployed(): Promise<void> {
    await this.loadPackages();
  }

  deletePackageVersion(clickedPackage: PackageDetail): void {
    if (clickedPackage.is_default && this.packages.length > 1) {
      this.messageService.add({
        severity: 'warn',
        summary: 'Warning',
        detail: `Cannot delete the default version of ${this.packageName}.`
      });
      return;
    }

    this.confirmationService.confirm({
      message: `Are you sure you want to delete ${this.packageName} version ${clickedPackage.version}?`,
      header: 'Delete Confirmation',
      icon: PrimeIcons.QUESTION_CIRCLE,
      accept: async () => {
        try {
          await this.packageService.deletePackageVersionAsync(this.packageName, clickedPackage.version);
          this.messageService.add({
            severity: 'success',
            summary: 'Success',
            detail: `${this.packageName} version ${clickedPackage.version} deleted successfully.`
          });
          await this.loadPackages();
        } catch (error) {
          this.messageService.add({
            severity: 'error',
            summary: 'Error',
            detail: `Failed to delete package version ${clickedPackage.version}.`
          });
        }
      }
    });
  }

  setAsDefaultVersion(clickedPackage: PackageDetail): void {
    this.confirmationService.confirm({
      message: `Are you sure you want to set ${this.packageName} version ${clickedPackage.version} as default?`,
      header: 'Set Default Confirmation',
      icon: PrimeIcons.QUESTION_CIRCLE,
      accept: async () => {
        try {
          await this.packageService.setAsDefaultVersionAsync(this.packageName, clickedPackage.version);
          this.messageService.add({
            severity: 'success',
            summary: 'Success',
            detail: `${this.packageName} version ${clickedPackage.version} set as default successfully.`
          });
          await this.loadPackages();
        } catch (error) {
          this.messageService.add({
            severity: 'error',
            summary: 'Error',
            detail: `Failed to set package version ${clickedPackage.version} as default.`
          });
        }
      }
    });
  }
}
