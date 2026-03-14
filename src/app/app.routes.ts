import { Routes } from '@angular/router';
import { AddressInfoComponent } from './address-info/address-info.component';

export const routes: Routes = [
  {
    path: '',
    component: AddressInfoComponent
  },
  {
    path: '**',
    redirectTo: ''
  }
];