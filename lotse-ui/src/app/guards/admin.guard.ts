import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';
import { FeatureFlagService } from '../services/feature-flag.service';

/** Only admins may open admin pages. Without authentication everybody is an admin. */
export const adminGuard: CanActivateFn = async () => {
  const authService = inject(AuthService);
  const featureFlagService = inject(FeatureFlagService);
  const router = inject(Router);

  const isAuthEnabled = await featureFlagService.isAuthenticationEnabled();
  if (!isAuthEnabled || authService.isAdmin()) {
    return true;
  }
  return router.parseUrl('/package-execution');
};
