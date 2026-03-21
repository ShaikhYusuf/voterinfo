import { Routes } from '@angular/router';
import { AddressInfoComponent } from './address-info/address-info.component';
import { DisclaimerComponent } from './disclaimer/disclaimer.component';
import { disclaimerGuard } from './disclaimer/disclaimer.guard';

export const routes: Routes = [
  {
    path: ':folder',
    component: AddressInfoComponent,
    canActivate: [disclaimerGuard]
  },
  {
    path: '',
    component: DisclaimerComponent
  },
  {
    path: '**',
    redirectTo: ''
  }
];
