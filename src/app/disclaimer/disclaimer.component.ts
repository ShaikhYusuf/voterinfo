import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatButtonModule } from '@angular/material/button';

@Component({
  selector: 'app-disclaimer',
  standalone: true,
  imports: [
    FormsModule,
    MatCardModule,
    MatCheckboxModule,
    MatButtonModule
  ],
  templateUrl: './disclaimer.component.html',
  styleUrls: ['./disclaimer.component.css']
})
export class DisclaimerComponent {

  accepted = false;

  constructor(private router: Router) {}

  proceed(): void {
    if (this.accepted) {
      this.router.navigate(['/home']);
    }
  }
}