import { Injectable } from '@angular/core';
import { MessageService, ToastMessageOptions } from 'primeng/api';
import { AuthService } from './auth.service';
import { FeatureFlagService } from './feature-flag.service';

/**
 * MessageService that drops error toasts while authentication is enabled and nobody is logged in.
 * Until then every request fails with 401 and the login dialog is already shown, so the
 * "Failed to load ..." errors are only noise.
 */
@Injectable()
export class AuthAwareMessageService extends MessageService {
  constructor(
    private authService: AuthService,
    private featureFlagService: FeatureFlagService,
  ) {
    super();
  }

  override add(message: ToastMessageOptions): void {
    if (!this.isSuppressed(message)) {
      super.add(message);
    }
  }

  override addAll(messages: ToastMessageOptions[]): void {
    const visible = messages.filter((message) => !this.isSuppressed(message));
    if (visible.length > 0) {
      super.addAll(visible);
    }
  }

  private isSuppressed(message: ToastMessageOptions): boolean {
    if (message.severity !== 'error' || this.authService.isLoggedIn()) {
      return false;
    }
    // The feature flags may still be loading on first page load, a 401 from the backend proves it as well.
    return this.featureFlagService.authenticationEnabled === true || this.authService.isAuthEnforced();
  }
}
