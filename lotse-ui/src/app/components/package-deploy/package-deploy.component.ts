import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService, PrimeIcons } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { DialogModule } from 'primeng/dialog';
import { FileUploadModule } from 'primeng/fileupload';
import { TagModule } from 'primeng/tag';
import YAML from 'yaml';
import { Runtime } from '../../misc/Runtime';
import { PackageService } from '../../services/package.service';

interface PackageConfig {
    package_name: string;
    runtime: Runtime;
    version: string;
}

@Component({
    imports: [
        CommonModule,
        FormsModule,
        ButtonModule,
        DialogModule,
        FileUploadModule,
        CheckboxModule,
        TagModule
    ],
    selector: 'app-package-deploy',
    templateUrl: './package-deploy.component.html',
    styleUrl: './package-deploy.component.scss',
})
export class PackageDeployComponent {
    PrimeIcons = PrimeIcons;
    Runtime = Runtime;

    @Input() packageName: string | null = null;
    @Input() availablePackageVersions: string[] = [];
    @Input() setAsDefault: boolean = false;
    @Output() packageDeployed = new EventEmitter<void>();

    detectedRuntime: Runtime | null = null;
    detectedName: string | null = null;
    detectedVersion: string | null = null;
    sameVersionError: boolean = false;
    notSameNameError: boolean = false;

    showDeployDialog = false;
    zipFile: File | null = null;
    configFile: File | null = null;
    deletePreviousVersions: boolean = false;
    isDraggingOver: boolean = false;
    private dragCounter: number = 0;
    private dragTimer: any = null;

    constructor(
        private packageService: PackageService,
        private messageService: MessageService,
    ) { }

    showDeployPackageDialog(): void {
        this.showDeployDialog = true;
        this.zipFile = null;
        this.configFile = null;
        this.notSameNameError = false;
        this.detectedName = null;
        this.detectedVersion = null;
        this.detectedRuntime = null;
        this.setAsDefault = false;
        this.deletePreviousVersions = false;
        this.sameVersionError = false;
    }

    onZipFileSelect(event: any): void {
        if (event.files && event.files.length > 0) {
            this.zipFile = event.files[0];
        }
    }

    async onConfigFileSelect(event: any): Promise<void> {
        if (event.files && event.files.length > 0) {
            this.configFile = event.files[0];
            if (this.configFile) {
                await this.parseConfigFile(this.configFile);
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
    }

    async onFileDrop(event: DragEvent): Promise<void> {
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

            await this.parseConfigFile(configFile);

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
    }

    private validatePackageName(packageConfig: PackageConfig): void {
        this.notSameNameError = false;
        if (packageConfig.package_name && this.packageName !== packageConfig.package_name) {
            this.notSameNameError = true;
        }
    }

    private validateAnyPackageWithSameVersion(packageConfig: PackageConfig): void {
        this.sameVersionError = false;
        if (packageConfig.version && this.availablePackageVersions.includes(packageConfig.version)) {
            this.sameVersionError = true;
        }
    }

    private async parseConfigFile(configFile: File): Promise<void> {
        try {
            const content = await this.readFileAsync(configFile);
            if (!content) {
                return;
            }

            const packageConfig = YAML.parse(content) as PackageConfig;
            if (packageConfig.package_name) {
                this.detectedName = packageConfig.package_name;
            }

            if (packageConfig.version) {
                this.detectedVersion = packageConfig.version;
            }

            if (packageConfig.runtime) {
                this.detectedRuntime = packageConfig.runtime;
            } else {
                this.detectedRuntime = Runtime.PYTHON;
            }

            this.validatePackageName(packageConfig);
            this.validateAnyPackageWithSameVersion(packageConfig);
        } catch (error) {
            console.error('Error parsing YAML:', error);
        }
    }

    private readFileAsync(file: File): Promise<string> {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (e) => resolve(e.target?.result as string || '');
            reader.onerror = (e) => reject(e);
            reader.readAsText(file);
        });
    }

    async deployPackage(): Promise<void> {
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

        if (this.notSameNameError) {
            this.messageService.add({
                severity: 'error',
                summary: 'Error',
                detail: 'Package name in YAML does not match the current package'
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
            formData.append('delete_previous_versions', this.deletePreviousVersions ? 'true' : 'false');

            await this.packageService.deployPackageAsync(formData);
            this.messageService.add({
                severity: 'success',
                summary: 'Success',
                detail: 'Package deployed successfully',
            });

            this.showDeployDialog = false;
            this.packageDeployed.emit();
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