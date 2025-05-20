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
import { SelectButtonModule } from 'primeng/selectbutton';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { HasRoleDirective } from '../../directives/has-role.directive';
import { PackageStatus } from '../../misc/PackageStatus';
import { Role } from '../../misc/Role';
import { Runtime } from '../../misc/Runtime';
import { PackageInfo } from '../../models/Package';
import { PackageCountByStatePipe } from '../../pipes/package-count-by-state.pipe';
import { PackageStatusToSeverityPipe } from '../../pipes/package-status.pipe';
import { AuthService } from '../../services/auth.service';
import { PackageService } from '../../services/package.service';

@Component({
  selector: 'app-packages-overview', imports: [
    CommonModule,
    FormsModule,
    TableModule,
    CardModule,
    TagModule,
    ButtonModule,
    DialogModule,
    FileUploadModule,
    SelectButtonModule,
    PackageStatusToSeverityPipe,
    PackageCountByStatePipe,
    CheckboxModule,
    HasRoleDirective,
  ],
  templateUrl: './packages-overview.component.html',
  styleUrl: './packages-overview.component.scss',
})
export class PackagesOverviewComponent implements OnInit {
  packages: PackageInfo[] = []; selectedPackage: PackageInfo | undefined;
  PackageStatus = PackageStatus;
  PrimeIcons = PrimeIcons;
  Role = Role;
  Runtime = Runtime;
  showDeployDialog = false;
  zipFile: File | null = null;
  configFile: File | null = null;
  setAsDefault: boolean = false;
  disablePreviousVersions: boolean = false;
  isAuthenticationEnabled: boolean = false;
  isDraggingOver: boolean = false;
  detectedRuntime: Runtime = Runtime.PYTHON;
  private dragCounter: number = 0;
  private dragTimer: any = null;

  constructor(
    private packageService: PackageService,
    private router: Router,
    private messageService: MessageService,
    private authService: AuthService,
  ) { }

  async ngOnInit(): Promise<void> {
    const stage = localStorage.getItem('stage') || 'dev';
    this.packages = await this.packageService.getAllPackagesOverviewAsync(stage);
    this.isAuthenticationEnabled = await this.authService.isAuthenticationEnabledAsync();
  }

  onPackageSelect(clickedPackage: PackageInfo): void {
    this.router.navigate(['/packages', clickedPackage.name]);
  } showDeployPackageDialog(): void {
    this.showDeployDialog = true;
    this.zipFile = null;
    this.configFile = null;
    this.detectedRuntime = Runtime.PYTHON;
  }

  onZipFileSelect(event: any): void {
    if (event.files && event.files.length > 0) {
      this.zipFile = event.files[0];
    }
  } async onConfigFileSelect(event: any): Promise<void> {
    if (event.files && event.files.length > 0) {
      this.configFile = event.files[0];
      // Automatically detect runtime from the config file
      if (this.configFile) {
        this.detectedRuntime = await this.packageService.detectRuntimeFromConfigFile(this.configFile);
      }
    }
  }
  onDragOver(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();

    if (this.dragTimer) {
      clearTimeout(this.dragTimer);
      this.dragTimer = null;
    }

    if (event.type === 'dragenter') {
      this.dragCounter++;
    }

    this.isDraggingOver = true;
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();

    if (event.type === 'dragleave') {
      this.dragCounter--;
    }

    if (this.dragCounter <= 0) {
      this.dragCounter = 0;
      this.isDraggingOver = false;
    } else {
      this.isDraggingOver = true;
    }
  } async onFileDrop(event: DragEvent): Promise<void> {
    event.preventDefault();
    event.stopPropagation();

    if (this.dragTimer) {
      clearTimeout(this.dragTimer);
      this.dragTimer = null;
    }

    this.isDraggingOver = false;
    this.dragCounter = 0;

    if (!event.dataTransfer?.files || event.dataTransfer.files.length === 0) {
      return;
    }

    const droppedFiles = Array.from(event.dataTransfer.files);

    const zipFile = droppedFiles.find((file) => file.name.endsWith('.zip') || file.name.endsWith('.7z'));
    const configFile = droppedFiles.find((file) => file.name.endsWith('.yml') || file.name.endsWith('.yaml'));

    if (configFile) {
      this.showDeployPackageDialog();
      this.configFile = configFile;

      this.detectedRuntime = await this.packageService.detectRuntimeFromConfigFile(configFile);

      if (zipFile) {
        this.zipFile = zipFile;
      }
    } else if (droppedFiles.length > 0) {
      this.messageService.add({
        severity: 'info',
        summary: 'File Drop',
        detail: 'Please drop a YAML config file to deploy a package. For runtimes or binaries, also include a ZIP file.',
      });
    }
  } async deployPackage(): Promise<void> {
    if (!this.configFile) {
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Please provide a config YAML file',
      });
      return;
    }

    if (this.detectedRuntime === Runtime.PYTHON && !this.zipFile) {
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Please provide a ZIP file for runtimes or binaries',
      });
      return;
    }

    try {
      const stage = localStorage.getItem('stage') || 'dev';
      const formData = new FormData();
      formData.append('stage', stage);
      if (this.zipFile) {
        formData.append('package_file', this.zipFile);
      } else {
        formData.append('package_file', new Blob());
      }

      formData.append('config_yaml', this.configFile);
      formData.append('set_as_default', this.setAsDefault ? 'true' : 'false');
      formData.append('disable_previous_versions', this.disablePreviousVersions ? 'true' : 'false');

      await this.packageService.deployPackageAsync(formData);

      this.messageService.add({
        severity: 'success',
        summary: 'Success',
        detail: 'Package deployed successfully',
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
