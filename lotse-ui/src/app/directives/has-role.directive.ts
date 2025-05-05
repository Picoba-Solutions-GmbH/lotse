import { Directive, Input, OnDestroy, OnInit, TemplateRef, ViewContainerRef } from '@angular/core';
import { Subscription } from 'rxjs';
import { Role } from '../misc/Role';
import { AuthService } from '../services/auth.service';

@Directive({
    selector: '[hasRole]'
})
export class HasRoleDirective implements OnInit, OnDestroy {
    private hasView = false;
    private allowedRoles: Role[] = [];
    private authSubscription: Subscription | null = null;

    @Input() set hasRole(roles: Role | Role[]) {
        this.allowedRoles = Array.isArray(roles) ? roles : [roles];
    }

    constructor(
        private templateRef: TemplateRef<any>,
        private viewContainer: ViewContainerRef,
        private authService: AuthService
    ) { }

    ngOnInit(): void {
        this.updateView();
        this.authSubscription = this.authService.authStateChanged.subscribe(() => {
            this.updateView();
        });
    }

    ngOnDestroy(): void {
        if (this.authSubscription) {
            this.authSubscription.unsubscribe();
            this.authSubscription = null;
        }
    }

    private async updateView(): Promise<void> {
        const isAuthEnabled = await this.authService.isAuthenticationEnabledAsync();
        const currentRole = this.authService.getRole();
        const isAllowed = this.allowedRoles.includes(currentRole);

        if ((isAllowed || !isAuthEnabled) && !this.hasView) {
            this.viewContainer.createEmbeddedView(this.templateRef);
            this.hasView = true;
        }
        else if (!isAllowed && this.hasView) {
            this.viewContainer.clear();
            this.hasView = false;
        }
    }
}