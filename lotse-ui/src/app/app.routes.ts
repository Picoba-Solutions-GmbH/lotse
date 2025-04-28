import { Routes } from '@angular/router';
import { PackageExecutionComponent } from './components/package-execution/package-execution.component';
import { PackageInstanceComponent } from './components/package-instance/package-instance.component';
import { PackageManagementComponent } from './components/package-management/package-management.component';
import { PackagesOverviewComponent } from './components/packages-overview/packages-overview.component';

export const routes: Routes = [
    {
        path: '',
        redirectTo: 'package-execution',
        pathMatch: 'full',
    },
    {
        path: 'package-execution',
        component: PackageExecutionComponent,
    },
    {
        path: 'packages',
        component: PackagesOverviewComponent,
    },
    {
        path: 'packages/:package_name',
        component: PackageManagementComponent,
    },
    {
        path: 'packages/:package_name/:package_version',
        component: PackageInstanceComponent,
    }
];
