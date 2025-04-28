import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
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
import { PackageStatus } from '../../misc/PackageStatus';
import { PackageDetail } from '../../models/Package';
import { PackageCountByStatePipe } from "../../pipes/package-count-by-state.pipe";
import { PackageStatusToSeverityPipe } from "../../pipes/package-status.pipe";
import { PackageService } from '../../services/package.service';

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
    PackageCountByStatePipe
  ],
  templateUrl: './package-management.component.html',
  styleUrl: './package-management.component.scss'
})
export class PackageManagementComponent implements OnInit {
  packages: PackageDetail[] = [];
  selectedPackage: PackageDetail | undefined;
  packageName: string = '';
  loading: boolean = true;
  PackageStatus = PackageStatus;
  PrimeIcons = PrimeIcons;

  constructor(
    private packageService: PackageService,
    private route: ActivatedRoute,
    private router: Router,
    private messageService: MessageService,
    private confirmationService: ConfirmationService
  ) { }

  async ngOnInit(): Promise<void> {
    this.packageName = this.route.snapshot.params['package_name'];
    await this.loadPackages();
  }

  async loadPackages(): Promise<void> {
    try {
      this.loading = true;
      const stage = localStorage.getItem('stage') || 'dev';
      this.packages = await this.packageService.getPackageOverviewAsync(stage, this.packageName);
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

  deletePackageVersion(clickedPackage: PackageDetail): void {
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
}
