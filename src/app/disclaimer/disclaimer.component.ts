import { Component, OnInit } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatButtonModule } from '@angular/material/button';
import { DisclaimerService } from './disclaimer.service';

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
export class DisclaimerComponent implements OnInit {
  accepted = false;

  constructor(
    private router: Router,
    private disclaimerService: DisclaimerService
  ) {}

  ngOnInit(): void {}   // nothing needed here anymore

  proceed(): void {
    if (this.accepted) {
      this.disclaimerService.accept();

      const target = this.disclaimerService.redirectUrl;
      if (target) {
        this.router.navigate([target], { replaceUrl: true });
      } else {
        this.router.navigate(['/'], { replaceUrl: true });
      }
    }
  }
}
