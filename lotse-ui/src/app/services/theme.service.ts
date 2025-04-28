import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

export interface ColorPalette {
    [key: string]: string | undefined;
}


export interface Color {
    name: string;
    palette: ColorPalette;
}

export interface NavBarItem {
    isLogo?: boolean;
    icon?: string;
    label?: string;
    routerLink?: string;
    visible: boolean;
    command?: () => void;
    styleClass?: string;
    severity?: 'success' | 'info' | 'warn' | 'danger' | 'help' | 'primary' | 'secondary' | 'contrast' | null | undefined;
    disabled?: boolean;
    collapsable?: boolean;
}


@Injectable({
    providedIn: 'root',
})
export class ThemeService {
    private darkModeBehavior = new BehaviorSubject<boolean>(true);
    public darkMode = this.darkModeBehavior.asObservable();

    private primaryColorBehavior = new BehaviorSubject<string>('emerald');
    public primaryColor = this.primaryColorBehavior.asObservable();

    private surfaceColorBehavior = new BehaviorSubject<string>('neutral');
    public surfaceColor = this.surfaceColorBehavior.asObservable();

    constructor() { }

    initialize(): void {
        this.initializeDarkMode();
    }

    private initializeDarkMode(): void {
        const darkMode = localStorage.getItem('darkMode');
        if (darkMode) {
            this.setDarkMode(JSON.parse(darkMode));
        } else {
            const systemTheme = this.getSystemColorTheme();
            this.setDarkMode(systemTheme === 'dark');
        }
    }

    setDarkMode(enabled: boolean): void {
        const element = document.querySelector('html');
        if (!element) {
            return;
        }

        if (enabled) {
            element.classList.add('dark');
        } else {
            element.classList.remove('dark');
        }

        localStorage.setItem('darkMode', JSON.stringify(enabled));
        this.darkModeBehavior.next(enabled);
    }

    isDarkMode(): boolean {
        return this.darkModeBehavior.value;
    }

    private getSystemColorTheme(): 'light' | 'dark' {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return 'dark';
        } else {
            return 'light';
        }
    }
}
