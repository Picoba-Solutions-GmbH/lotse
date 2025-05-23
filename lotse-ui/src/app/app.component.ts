import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NavigationEnd, Router, RouterModule } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { svglKubernetes } from '@ng-icons/svgl';
import { MenuItem, MessageService, PrimeIcons } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogService, DynamicDialogRef } from 'primeng/dynamicdialog';
import { MenubarModule } from 'primeng/menubar';
import { SelectButtonChangeEvent, SelectButtonModule } from 'primeng/selectbutton';
import { ToastModule } from 'primeng/toast';
import { ToggleSwitchModule } from 'primeng/toggleswitch';
import { filter, firstValueFrom as firstValueFromAsync } from 'rxjs';
import { LoginDialogComponent } from './components/login-dialog/login-dialog.component';
import { Role } from './misc/Role';
import { AuthService } from './services/auth.service';
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
    MenubarModule,
    RouterModule,
    ButtonModule,
    ToggleSwitchModule,
    SelectButtonModule,
    ConfirmDialogModule,
    NgIcon
  ],
  providers: [provideIcons({ svglKubernetes })],
})
export class AppComponent implements OnInit {
  isLoggedIn: boolean = false;
  isAuthEnabled: boolean = false;

  title = 'lotse-ui';
  logoOpacity: number = 1;
  isMobile: boolean = false;
  tabMenuHeight: number = 0;
  isStatusPage: boolean = false;
  currentRoute: string = '';
  isDarkMode: boolean = false;
  PrimeIcons = PrimeIcons;

  stateOptions: any[] = [{ label: 'Dev', value: 'dev' }, { label: 'Prod', value: 'prod' }];
  stageValue: string = 'dev';

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
      label: 'Cluster',
      icon: svglKubernetes,
      routerLink: 'cluster'
    }
  ];

  items: MenuItem[] = [...this.original_items];

  constructor(
    private router: Router,
    public themeService: ThemeService,
    private authService: AuthService,
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

    this.stageValue = localStorage.getItem('stage') || 'dev';

    this.isAuthEnabled = await this.authService.isAuthenticationEnabledAsync();
    if (this.isAuthEnabled) {
      const login = this.authService.getLogin();
      if (login) {
        const { username, password } = JSON.parse(login);
        await this.loginAsync(username, password, true);
      }
    }

    this.authService.authStateChanged.subscribe(() => {
      this.updateMenuItems();
    });
  }

  private updateMenuItems(): void {
    const isAdmin = this.authService.getRole() === Role.ADMIN;
    this.items = this.original_items.filter(item => {
      if (item.routerLink === 'cluster') {
        return isAdmin;
      }
      
      return true;
    });

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
      currentPath += `/${part}`;
      return {
        label: part.replace(/_/g, ' ').replace(/%20/g, '-'),
        icon: PrimeIcons.FOLDER,
        routerLink: currentPath
      };
    });
  }

  isRouteActive(item: MenuItem): boolean {
    if (item.routerLink) {
      return this.currentRoute.startsWith('/' + item.routerLink);
    }
    if (item.items) {
      return item.items.some((subItem: MenuItem) => this.isRouteActive(subItem));
    }
    return false;
  }

  handleStateChange($event: SelectButtonChangeEvent) {
    localStorage.setItem('stage', $event.value);
    window.location.reload();
  }

  openLoginDialog(): void {
    const ref: DynamicDialogRef = this.dialogService.open(LoginDialogComponent, {
      header: 'Login',
      width: '300px',
    });

    ref.onClose.subscribe(async (result: { username: string; password: string } | undefined) => {
      if (result) {
        await this.loginAsync(result.username, result.password);
      }
    });
  }

  async loginAsync(username: string, password: string, isInit: boolean = false): Promise<void> {
    try {
      await firstValueFromAsync(this.authService.login(username, password));
      this.isLoggedIn = true;

      if (!isInit) {
        this.messageService.add({
          severity: 'success',
          summary: 'Success',
          detail: 'Logged in successfully',
          life: 3000,
        });
      }
    } catch (error) {
      if (!isInit) {
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Invalid credentials',
          life: 5000,
        });
      } else {
        console.error('Invalid credentials');
      }
    }
  }

  logout(): void {
    this.authService.logout();
    this.isLoggedIn = false;
    this.messageService.add({
      severity: 'info',
      summary: 'Logged out',
      detail: 'You have been logged out successfully',
      life: 3000,
    });
  }
}
