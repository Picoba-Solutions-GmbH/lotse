import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MessageService, PrimeIcons } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { CheckboxModule } from 'primeng/checkbox';
import { DialogModule } from 'primeng/dialog';
import { FileUploadModule } from 'primeng/fileupload';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { PackageStatus } from '../../misc/PackageStatus';
import { PackageInfo } from '../../models/Package';
import { PackageCountByStatePipe } from "../../pipes/package-count-by-state.pipe";
import { PackageStatusToSeverityPipe } from "../../pipes/package-status.pipe";
import { PackageService } from '../../services/package.service';

@Component({
  selector: 'app-packages-overview',
  imports: [
    CommonModule,
    FormsModule,
    TableModule,
    CardModule,
    TagModule,
    ButtonModule,
    DialogModule,
    FileUploadModule,
    PackageStatusToSeverityPipe,
    PackageCountByStatePipe,
    CheckboxModule
  ],
  templateUrl: './packages-overview.component.html',
  styleUrl: './packages-overview.component.scss'
})
export class PackagesOverviewComponent implements OnInit {
  packages: PackageInfo[] = [];
  selectedPackage: PackageInfo | undefined;
  PackageStatus = PackageStatus;
  PrimeIcons = PrimeIcons;
  showDeployDialog = false;
  zipFile: File | null = null;
  configFile: File | null = null;
  setAsDefault: boolean = false;
  disablePreviousVersions: boolean = false;

  constructor(
    private packageService: PackageService,
    private router: Router,
    private messageService: MessageService
  ) { }

  async ngOnInit(): Promise<void> {
    const stage = localStorage.getItem('stage') || 'dev';
    this.packages = await this.packageService.getAllPackagesOverviewAsync(stage);
  }

  onPackageSelect(clickedPackage: PackageInfo): void {
    this.router.navigate(['/packages', clickedPackage.name]);
  }

  showDeployPackageDialog(): void {
    this.showDeployDialog = true;
    this.zipFile = null;
    this.configFile = null;
  }

  onZipFileSelect(event: any): void {
    if (event.files && event.files.length > 0) {
      this.zipFile = event.files[0];
    }
  }

  onConfigFileSelect(event: any): void {
    if (event.files && event.files.length > 0) {
      this.configFile = event.files[0];
    }
  }

  async deployPackage(): Promise<void> {
    if (!this.zipFile || !this.configFile) {
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Please provide both ZIP and config files'
      });
      return;
    }

    try {
      const stage = localStorage.getItem('stage') || 'dev';
      const formData = new FormData();
      formData.append('stage', stage);
      formData.append('package_file', this.zipFile);
      formData.append('config_yaml', this.configFile);
      formData.append('set_as_default', this.setAsDefault ? 'true' : 'false');
      formData.append('disable_previous_versions', this.disablePreviousVersions ? 'true' : 'false');

      await this.packageService.deployPackageAsync(formData);

      this.messageService.add({
        severity: 'success',
        summary: 'Success',
        detail: 'Package deployed successfully'
      });
      this.showDeployDialog = false;

      this.packages = await this.packageService.getAllPackagesOverviewAsync(stage);
    } catch (error) {
      let message = 'Unknown error';
      if (error instanceof HttpErrorResponse) {
        message = error.error?.detail || 'Unknown error';
      } else if (error instanceof Error) {
        message = error.message || 'Unknown error';
      }

      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: `Failed to deploy package: ${message}`,
        life: 5000,
      });
    }
  }
}
