import { Routes } from '@angular/router';
import { AddressInfoComponent } from './address-info/address-info.component';
import { DisclaimerComponent } from './disclaimer/disclaimer.component';

export const routes: Routes = [
  {
    path: 'home',
    component: AddressInfoComponent
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