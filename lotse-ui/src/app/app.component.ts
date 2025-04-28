import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { NavigationEnd, Router, RouterModule } from '@angular/router';
import { MenuItem, PrimeIcons } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { MenubarModule } from 'primeng/menubar';
import { SelectButtonChangeEvent, SelectButtonModule } from 'primeng/selectbutton';
import { ToastModule } from 'primeng/toast';
import { ToggleSwitchModule } from 'primeng/toggleswitch';
import { filter } from 'rxjs';
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
  ],
})
export class AppComponent implements OnInit {
  isLoggedIn: boolean = false;

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
    }
  ];

  items: MenuItem[] = [...this.original_items];

  constructor(private router: Router, public themeService: ThemeService) {
    themeService.darkMode.subscribe((darkMode) => {
      this.isDarkMode = darkMode;
    });
  }

  ngOnInit(): void {
    this.themeService.initialize();
    this.router.events.pipe(filter((event) => event instanceof NavigationEnd)).subscribe((event: NavigationEnd) => {
      this.currentRoute = event.url === '/' ? '/package-execution' : event.url;
      this.updateMenuItems();
    });
    this.stageValue = localStorage.getItem('stage') || 'dev';
  }

  private updateMenuItems(): void {
    const urlParts = this.currentRoute.split('/').filter(part => part);
    if (urlParts[0] === 'packages' && urlParts.length > 1) {
      const packagesMenuItem = this.items.find(item => item.routerLink === 'packages');
      if (packagesMenuItem) {
        const new_items = [...this.original_items, ...this.buildSubMenuItems(urlParts.slice(1))];
        this.items = new_items;
      }
    }
  }

  private buildSubMenuItems(urlParts: string[]): MenuItem[] {
    let currentPath = 'packages';
    return urlParts.map((part, index) => {
      currentPath += `/${part}`;
      return {
        label: part.replace(/_/g, ' '),
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
}
