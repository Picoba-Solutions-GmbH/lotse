import { CommonModule } from '@angular/common';
import { Component, OnInit, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { PrimeIcons } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { HasRoleDirective } from '../../../directives/has-role.directive';
import { PackageStatus } from '../../../misc/PackageStatus';
import { Role } from '../../../misc/Role';
import { PackageInfo } from '../../../models/Package';
import { PackageCountByStatePipe } from '../../../pipes/package-count-by-state.pipe';
import { PackageStatusToSeverityPipe } from '../../../pipes/package-status.pipe';
import { AuthService } from '../../../services/auth.service';
import { PackageService } from '../../../services/package.service';
import { PackageDeployComponent } from '../package-deploy/package-deploy.component';

@Component({
  selector: 'app-packages-overview',
  imports: [
    CommonModule,
    FormsModule,
    TableModule,
    CardModule,
    TagModule,
    ButtonModule,
    PackageStatusToSeverityPipe,
    PackageCountByStatePipe,
    HasRoleDirective,
    PackageDeployComponent,
  ],
  templateUrl: './packages-overview.component.html',
  styleUrl: './packages-overview.component.scss',
})
export class PackagesOverviewComponent implements OnInit {
  packages: PackageInfo[] = []; selectedPackage: PackageInfo | undefined;
  PackageStatus = PackageStatus;
  PrimeIcons = PrimeIcons;
  Role = Role;
  isAuthenticationEnabled: boolean = false;

  @ViewChild(PackageDeployComponent) packageDeploy!: PackageDeployComponent;

  constructor(
    private packageService: PackageService,
    private router: Router,
    private authService: AuthService,
  ) { }

  async ngOnInit(): Promise<void> {
    await this.loadPackages();
    this.isAuthenticationEnabled = await this.authService.isAuthenticationEnabledAsync();
  }

  async loadPackages(): Promise<void> {
    const stage = localStorage.getItem('stage') || 'dev';
    this.packages = await this.packageService.getAllPackagesOverviewAsync(stage);
  }

  onPackageSelect(clickedPackage: PackageInfo): void {
    this.router.navigate(['/packages', clickedPackage.name]);
  }

  showDeployPackageDialog(): void {
    this.packageDeploy.showDeployPackageDialog();
  }

  showDeployContainerDialog(): void {
    this.packageDeploy.showDeployContainerDialog();
  }

  async onPackageDeployed(): Promise<void> {
    await this.loadPackages();
  }
}
