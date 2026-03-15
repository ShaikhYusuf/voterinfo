import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { IAddressInfo } from '../app.model';
import { FormsModule } from '@angular/forms';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-address-info',
  imports: [
    CommonModule,
    FormsModule,
    MatTableModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatCardModule,
    MatIconModule
  ],
  templateUrl: './address-info.component.html',
  styleUrl: './address-info.component.css'
})
export class AddressInfoComponent implements OnInit {
  displayedColumns: string[] = ['address', 'filename','open'];
  data: IAddressInfo[] = [];
  filteredData: IAddressInfo[] = [];
  filterText = '';

  constructor(private http: HttpClient) {}

  ngOnInit() {
    this.loadCSV();
  }

  loadCSV() {

  this.http.get('address-data.eng.csv', { responseType: 'text' })
    .subscribe(csv => {

      const rows = csv.split('\n').slice(1);

      const uniqueMap = new Map<string, IAddressInfo>();

      rows
        .filter(r => r.trim().length > 0)
        .forEach(row => {

          const cols = row.split(',');

          const item: IAddressInfo = {
            filename: cols[0].trim(),
            page: Number(cols[1]),
            address: cols[3].trim().replace(/\s([a-z])\)/gi, '<br>$1)')
          };

          // unique key based on filename + address
          const key = `${item.filename}|${item.address}`;

          if (!uniqueMap.has(key)) {
            uniqueMap.set(key, item);
          }

        });

      this.data = Array.from(uniqueMap.values());
      this.filteredData = [...this.data];

    });
}

async transliterateToMarathi(text: string) {
  const url = `https://inputtools.google.com/request?text=${text}&itc=mr-t-i0-und&num=1`;
  const res = await fetch(url);
  const data = await res.json();

  if (data[0] === "SUCCESS") {
    return data[1][0][1][0];
  }

  return text;
}
  async applyFilter() {
    const mrINValue = this.filterText.toLowerCase();
    
    //const mrINValue = await this.transliterateToMarathi(value);
    console.log('Filtering with value: %s', mrINValue);
    this.filteredData = this.data.filter(item =>
      item.filename.toLowerCase().includes(mrINValue) ||
      item.address.toLowerCase().includes(mrINValue)
    );
  }

  openFile(item: IAddressInfo) {
    const url = `files/${item.filename}#page=${item.page}`;
    window.open(url, '_blank');
  }

}
