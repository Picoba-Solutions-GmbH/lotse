import { CommonModule } from '@angular/common';
import { Component, inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NavigationEnd, Router, RouterModule } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { svglKubernetes } from '@ng-icons/svgl';
import { MenuItem, MessageService, PrimeIcons } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogService, DynamicDialogRef } from 'primeng/dynamicdialog';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { filter } from 'rxjs';
import { LoginDialogComponent } from './components/login-dialog/login-dialog.component';
import { AuthService } from './services/auth.service';
import { FeatureFlagService } from './services/feature-flag.service';
import { StatusService } from './services/status.service';
import { ThemeService } from './services/theme.service';
import './utils/global-functions';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
  imports: [
    CommonModule,
    FormsModule,
    ToastModule,
    RouterModule,
    ButtonModule,
    ConfirmDialogModule,
    TooltipModule,
    NgIcon
  ],
  providers: [provideIcons({ svglKubernetes })],
})
export class AppComponent implements OnInit {
  isLoggedIn: boolean = false;
  isAuthEnabled: boolean = false;
  isLiveCodingEnabled: boolean = true;

  title = 'lotse-ui';
  logoOpacity: number = 1;
  isMobile: boolean = false;
  tabMenuHeight: number = 0;
  isStatusPage: boolean = false;
  currentRoute: string = '';
  isDarkMode: boolean = false;
  PrimeIcons = PrimeIcons;

  sidebarOpen = false;
  sidebarCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';

  private readonly statusService = inject(StatusService);
  serverReachable$ = this.statusService.serverReachable$;
  activemqEnabled$ = this.statusService.activemqEnabled$;
  activemqConnected$ = this.statusService.activemqConnected$;

  toggleCollapse(): void {
    this.sidebarCollapsed = !this.sidebarCollapsed;
    localStorage.setItem('sidebarCollapsed', String(this.sidebarCollapsed));
  }

  original_items: MenuItem[] = [
    {
      label: 'Package execution',
      icon: PrimeIcons.MAP,
      routerLink: 'package-execution',
    },
    {
      label: 'Packages',
      icon: PrimeIcons.BOX,
      routerLink: 'packages'
    },
    {
      label: 'Live Coding',
      icon: PrimeIcons.CODE,
      routerLink: 'live-coding'
    },
    {
      label: 'Cluster',
      icon: svglKubernetes,
      routerLink: 'cluster'
    },
    {
      label: 'Network Shares',
      icon: PrimeIcons.SERVER,
      routerLink: 'network-shares'
    },
    {
      label: 'Logs',
      icon: PrimeIcons.LIST,
      routerLink: 'logs'
    },
    {
      label: 'Users',
      icon: PrimeIcons.USERS,
      routerLink: 'users'
    },
    {
      label: 'Backup',
      icon: PrimeIcons.CLOUD_DOWNLOAD,
      routerLink: 'backup'
    }
  ];

  private readonly bottomRoutes = new Set(['cluster', 'network-shares', 'logs', 'users', 'backup']);
  private loginDialogRef: DynamicDialogRef | null = null;
  username: string | null = null;

  items: MenuItem[] = [];
  bottomItems: MenuItem[] = [];

  constructor(
    private router: Router,
    public themeService: ThemeService,
    private authService: AuthService,
    private featureFlagService: FeatureFlagService,
    private messageService: MessageService,
    private dialogService: DialogService) {
    themeService.darkMode.subscribe((darkMode) => {
      this.isDarkMode = darkMode;
    });
  }

  async ngOnInit(): Promise<void> {
    this.themeService.initialize();
    this.router.events.pipe(filter((event) => event instanceof NavigationEnd)).subscribe((event: NavigationEnd) => {
      this.currentRoute = event.url === '/' ? '/package-execution' : event.url;
      this.updateMenuItems();
    });

    this.isAuthEnabled = await this.featureFlagService.isAuthenticationEnabled();
    this.isLiveCodingEnabled = await this.featureFlagService.isLiveCodingEnabled();
    this.updateAuthState();

    this.authService.authStateChanged.subscribe(() => this.updateAuthState());
    this.authService.loginRequired.subscribe(() => {
      if (this.isAuthEnabled) {
        this.openLoginDialog();
      }
    });

    if (this.isAuthEnabled && !this.authService.isLoggedIn()) {
      this.openLoginDialog();
    }
  }

  private updateAuthState(): void {
    this.isLoggedIn = this.authService.isLoggedIn();
    this.username = this.authService.getUsername();
    this.updateMenuItems();
  }

  /** Reload the current page so it fetches the data visible to the (new) user. */
  private reloadCurrentRoute(): void {
    const url = this.router.url;
    this.router.navigateByUrl('/', { skipLocationChange: true })
      .then(() => this.router.navigateByUrl(url));
  }

  private updateMenuItems(): void {
    const isAdmin = !this.isAuthEnabled || this.authService.isAdmin();
    const filtered = this.original_items.filter(item => {
      if (this.bottomRoutes.has(item.routerLink!)) {
        return isAdmin;
      }
      if (item.routerLink === 'live-coding') {
        return this.isLiveCodingEnabled;
      }
      return true;
    });

    this.items = filtered.filter(item => !this.bottomRoutes.has(item.routerLink!));
    this.bottomItems = filtered.filter(item => this.bottomRoutes.has(item.routerLink!));

    const urlParts = this.currentRoute.split('/').filter(part => part);
    if (urlParts[0] === 'packages' && urlParts.length > 1) {
      const packagesIndex = this.items.findIndex(item => item.routerLink === 'packages');
      if (packagesIndex !== -1) {
        const subMenuItems = this.buildSubMenuItems(urlParts.slice(1));
        this.items.splice(packagesIndex + 1, 0, ...subMenuItems);
      }
    }
  }

  private buildSubMenuItems(urlParts: string[]): MenuItem[] {
    let currentPath = 'packages';
    return urlParts.map((part, index) => {
      const decoded = decodeURIComponent(part);
      currentPath += `/${decoded}`;
      return {
        label: decoded.replace(/_/g, ' '),
        icon: PrimeIcons.FOLDER,
        routerLink: currentPath
      };
    });
  }

  isRouteActive(item: MenuItem): boolean {
    if (item.routerLink) {
      return decodeURIComponent(this.currentRoute).startsWith('/' + item.routerLink);
    }
    if (item.items) {
      return item.items.some((subItem: MenuItem) => this.isRouteActive(subItem));
    }
    return false;
  }

  openLoginDialog(): void {
    if (this.loginDialogRef) {
      return;
    }

    this.loginDialogRef = this.dialogService.open(LoginDialogComponent, {
      header: 'Sign in',
      showHeader: false,
      modal: true,
      width: '380px',
      breakpoints: { '480px': 'calc(100vw - 2rem)' },
      styleClass: 'login-dialog',
      maskStyleClass: 'login-dialog-mask',
    });

    this.loginDialogRef.onClose.subscribe((result: boolean | undefined) => {
      this.loginDialogRef = null;
      if (result) {
        this.updateAuthState();
        this.reloadCurrentRoute();
        this.messageService.add({
          severity: 'success',
          summary: 'Success',
          detail: `Signed in as ${this.username}`,
          life: 3000,
        });
      }
    });
  }

  logout(): void {
    this.authService.logout();
    this.router.navigateByUrl('/package-execution');
    this.messageService.add({
      severity: 'info',
      summary: 'Logged out',
      detail: 'You have been logged out successfully',
      life: 3000,
    });
    this.openLoginDialog();
  }
}
