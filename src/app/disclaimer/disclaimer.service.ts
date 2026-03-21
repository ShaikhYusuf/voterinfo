import { Injectable } from '@angular/core';

const ACCEPTED_KEY = 'disclaimerAccepted';

@Injectable({
  providedIn: 'root'
})
export class DisclaimerService {

  isAccepted(): boolean {
    return sessionStorage.getItem(ACCEPTED_KEY) === 'true';
  }

  accept(): void {
    sessionStorage.setItem(ACCEPTED_KEY, 'true');
  }
}
