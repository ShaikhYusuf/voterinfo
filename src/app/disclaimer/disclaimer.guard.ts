import { inject } from '@angular/core';
import { CanActivateFn, Router, ActivatedRouteSnapshot, RouterStateSnapshot } from '@angular/router';
import { DisclaimerService } from './disclaimer.service';

export const disclaimerGuard: CanActivateFn = (route, state) => {
  const disclaimerService = inject(DisclaimerService);
  const router = inject(Router);

  if (disclaimerService.isAccepted()) {
    return true;
  }

  // state.url will be '/mazgaon' — extract folder from it
  const folder = state.url.replace(/^\//, '').split('?')[0].split('#')[0];
  console.log('Saving folder:', folder);
  
  disclaimerService.redirectUrl = folder;
  
  return router.createUrlTree(['/']);
};