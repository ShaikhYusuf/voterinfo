import { inject } from '@angular/core';
import { CanActivateFn, Router, ActivatedRouteSnapshot, RouterStateSnapshot } from '@angular/router';
import { DisclaimerService } from './disclaimer.service';

export const disclaimerGuard: CanActivateFn = (route, state) => {
  const disclaimerService = inject(DisclaimerService);
  const router = inject(Router);

  if (disclaimerService.isAccepted()) {
    return true;
  }

  // Store the intended route in the service
  disclaimerService.redirectUrl = route.params['folder'] ?? '';

  return router.createUrlTree(['/']);  // go to disclaimer
};
