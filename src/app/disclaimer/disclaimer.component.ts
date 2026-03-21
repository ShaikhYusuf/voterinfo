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
  private redirectTo = '/home';

  constructor(
    private router: Router,
    private activatedRoute: ActivatedRoute,
    private disclaimerService: DisclaimerService
  ) {}

  ngOnInit(): void {
    // Read the intended URL directly from the query param set by the guard
    this.activatedRoute.queryParams.subscribe(params => {
      if (params['redirectTo']) {
        this.redirectTo = params['redirectTo'];
      }
    });
  }

  proceed(): void {
    if (this.accepted) {
      this.disclaimerService.accept();
      this.router.navigateByUrl(this.redirectTo, { replaceUrl: true });
    }
  }
}
