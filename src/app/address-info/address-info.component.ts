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
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute } from '@angular/router';
import Papa from 'papaparse';

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
    MatIconModule,
    MatTooltipModule
  ],
  templateUrl: './address-info.component.html',
  styleUrl: './address-info.component.css'
})
export class AddressInfoComponent implements OnInit {
  displayedColumns: string[] = ['address', 'open'];  // filename column removed
  data: IAddressInfo[] = [];
 
  filteredData: IAddressInfo[] = [];
  filterText = '';
  folderName = '';

  constructor(private http: HttpClient, private route: ActivatedRoute) {}

  ngOnInit() {
    // Read folder param from route; fall back to empty string if not provided
    this.route.paramMap.subscribe(params => {
      this.folderName = params.get('folder') ?? '';
      this.loadCSV();
    });
  }

  splitCSV(row: string): string[] {
    const result: string[] = [];
    let current = '';
    let inQuotes = false;

    for (let i = 0; i < row.length; i++) {
      const char = row[i];

      if (char === '"') {
        // Handle escaped quotes ("")
        if (inQuotes && row[i + 1] === '"') {
          current += '"';
          i++;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (char === ',' && !inQuotes) {
        result.push(current.trim());
        current = '';
      } else {
        current += char;
      }
    }

    result.push(current.trim());
    return result.map(col => col.replace(/^"|"$/g, '').trim());
}

  loadCSV() {
    // CSV file is located at: <folderName>/<folderName>.mar.csv
    // If no folder is provided, fall back to the original flat file
    const csvPath = this.folderName
      ? `${this.folderName}/${this.folderName}.mar.csv`
      : 'bhiwandi/bhiwandi.mar.csv';

    this.http.get(csvPath, { responseType: 'text' })
      .subscribe(csv => {
        const rows = csv.split('\n').slice(1); // skip header row
        const uniqueMap = new Map<string, IAddressInfo>();

        rows
          .filter(r => r.trim().length > 0)
          .forEach(row => {
            const cols = this.splitCSV(row);
            const item: IAddressInfo = {
              filename: cols[0].trim(),
              content: cols[1].trim() //.replace(/\s([अ)ब)क)])\)/gi, '<br>$1)')
            };
            console.log(cols[1])
            // Unique key based on filename + content
            const key = `${item.filename}|${item.content}`;
            if (!uniqueMap.has(key)) {
              uniqueMap.set(key, item);
            }
          });

        this.data = Array.from(uniqueMap.values());
        this.filteredData = [...this.data];
      });
  }

  async translateToMarathi(text: string): Promise<string> {
    try {
      const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=mr&dt=t&q=${encodeURIComponent(text)}`;

      const res = await fetch(url);
      const data = await res.json();

      if (Array.isArray(data)) {
        return data[0].map((item: any) => item[0]).join('');
      }

      return text;
    } catch (err) {
      console.error('Translation error:', err);
      return text;
    }
  }

  searchTimeout: any;

  onSearchChange(value: string) {
    clearTimeout(this.searchTimeout);

    this.searchTimeout = setTimeout(() => {
      this.applyFilter();
    }, 400); // 400ms delay
}

  async applyFilter() {
  if (!this.filterText || this.filterText.trim() === '') {
    this.filteredData = this.data;
    return;
  }

  try {
    // Step 1: Translate input to Marathi
    const translated = await this.translateToMarathi(this.filterText);

    const mrINValue = translated.toLowerCase();
    console.log('Original:', this.filterText);
    console.log('Translated:', mrINValue);

    // Step 2: Filter using translated text
    this.filteredData = this.data.filter(item =>
      item.filename.toLowerCase().includes(mrINValue) ||
      item.content.toLowerCase().includes(mrINValue)
    );

  } catch (err) {
    console.error('Filter error:', err);
  }
}

  openFile(item: IAddressInfo) {
    // File is located inside the folder: <folderName>/<filename>
    const url = `${this.folderName}/${item.filename}`;
    window.open(url, '_blank');
  }
}
