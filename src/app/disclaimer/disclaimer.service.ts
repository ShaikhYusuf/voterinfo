import { Injectable } from '@angular/core';

const ACCEPTED_KEY = 'disclaimerAccepted';

@Injectable({
  providedIn: 'root'
})
export class DisclaimerService {
  private _accepted = false;
  redirectUrl: string = '';         // <-- add this

  isAccepted(): boolean {
    return this._accepted || sessionStorage.getItem('disclaimer') === 'accepted';
  }

  accept(): void {
    this._accepted = true;
    sessionStorage.setItem('disclaimer', 'accepted');
  }
}