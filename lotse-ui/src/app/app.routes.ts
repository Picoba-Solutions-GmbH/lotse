import { Routes } from '@angular/router';
import { ClusterComponent } from './components/cluster/cluster.component';
import { NamespaceResourcesComponent } from './components/cluster/namespace-resources/namespace-resources.component';
import { LogsComponent } from './components/logs/logs.component';
import { NetworkSharesComponent } from './components/network-shares/network-shares.component';
import { PackageExecutionComponent } from './components/package/package-execution/package-execution.component';
import { PackageInstanceComponent } from './components/package/package-instance/package-instance.component';
import { PackageLiveCodeComponent } from './components/package/package-live-code/package-live-code.component';
import { PackageManagementComponent } from './components/package/package-management/package-management.component';
import { PackagesOverviewComponent } from './components/package/packages-overview/packages-overview.component';
import { UsersComponent } from './components/users/users.component';
import { adminGuard } from './guards/admin.guard';

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
        path: 'live-coding',
        component: PackageLiveCodeComponent,
    },
    {
        path: 'cluster',
        canActivate: [adminGuard],
        component: ClusterComponent,
    },
    {
        path: 'cluster/:namespace/pods',
        canActivate: [adminGuard],
        component: NamespaceResourcesComponent,
    },
    {
        path: 'logs',
        canActivate: [adminGuard],
        component: LogsComponent,
    },
    {
        path: 'network-shares',
        canActivate: [adminGuard],
        component: NetworkSharesComponent,
    },
    {
        path: 'users',
        canActivate: [adminGuard],
        component: UsersComponent,
    }
];
