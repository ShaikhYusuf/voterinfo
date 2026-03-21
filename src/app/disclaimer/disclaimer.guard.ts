import { inject } from '@angular/core';
import { CanActivateFn, Router, ActivatedRouteSnapshot, RouterStateSnapshot } from '@angular/router';
import { DisclaimerService } from './disclaimer.service';

export const disclaimerGuard: CanActivateFn = (
  route: ActivatedRouteSnapshot,
  state: RouterStateSnapshot
) => {
  const router = inject(Router);
  const disclaimerService = inject(DisclaimerService);

  if (!disclaimerService.isAccepted()) {
    // Pass the intended URL as a query param — survives the redirect reliably
    return router.createUrlTree(['/'], {
      queryParams: { redirectTo: state.url }
    });
  }

  return true;
};
