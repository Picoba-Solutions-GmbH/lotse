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
import { HasRoleDirective } from '../../directives/has-role.directive';
import { PackageStatus } from '../../misc/PackageStatus';
import { Role } from '../../misc/Role';
import { PackageDetail } from '../../models/Package';
import { PackageCountByStatePipe } from "../../pipes/package-count-by-state.pipe";
import { PackageStatusToSeverityPipe } from "../../pipes/package-status.pipe";
import { AuthService } from '../../services/auth.service';
import { PackageService } from '../../services/package.service';
import { PackageDeployComponent } from '../package-deploy/package-deploy.component';

@Component({
  selector: 'app-package-management',
  standalone: true,
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
    HasRoleDirective,
    PackageDeployComponent
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
  Role = Role;
  isAuthenticationEnabled: boolean = false;

  @ViewChild(PackageDeployComponent) packageDeploy!: PackageDeployComponent;

  constructor(
    private packageService: PackageService,
    private route: ActivatedRoute,
    private router: Router,
    private messageService: MessageService,
    private confirmationService: ConfirmationService,
    private authService: AuthService
  ) { }

  async ngOnInit(): Promise<void> {
    this.packageName = this.route.snapshot.params['package_name'];
    await this.loadPackages();
    this.isAuthenticationEnabled = await this.authService.isAuthenticationEnabledAsync();
  }

  async loadPackages(): Promise<void> {
    try {
      this.loading = true;
      const stage = localStorage.getItem('stage') || 'dev';
      this.packages = await this.packageService.getPackageOverviewAsync(stage, this.packageName);
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
          const stage = localStorage.getItem('stage') || 'dev';
          await this.packageService.deletePackageVersionAsync(this.packageName, stage, clickedPackage.version);
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
          const stage = localStorage.getItem('stage') || 'dev';
          await this.packageService.setAsDefaultVersionAsync(this.packageName, stage, clickedPackage.version);
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
