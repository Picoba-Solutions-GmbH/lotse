import { Routes } from '@angular/router';
import { ClusterComponent } from './components/cluster/cluster.component';
import { NamespaceResourcesComponent } from './components/cluster/namespace-resources/namespace-resources.component';
import { PackageExecutionComponent } from './components/package/package-execution/package-execution.component';
import { PackageInstanceComponent } from './components/package/package-instance/package-instance.component';
import { PackageManagementComponent } from './components/package/package-management/package-management.component';
import { PackagesOverviewComponent } from './components/package/packages-overview/packages-overview.component';

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
    },
    {
        path: 'cluster',
        component: ClusterComponent,
    },
    {
        path: 'cluster/:namespace/pods',
        component: NamespaceResourcesComponent,
    }
];
