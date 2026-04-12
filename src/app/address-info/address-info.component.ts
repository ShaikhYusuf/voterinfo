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
  title = "2002"
  displayedColumns: string[] = ['address', 'open'];  // filename column removed
  data: IAddressInfo[] = [];
  col_filename = 0;
  col_content = 1;
  col_page = -1; // optional page column index

  filteredData: IAddressInfo[] = [];
  filterText = '';
  folderName = '';

  constructor(private http: HttpClient, private route: ActivatedRoute) { }

  private getBase(): string {
    const base = document.querySelector('base')?.getAttribute('href') ?? '/';
    return base.endsWith('/') ? base : base + '/';
}

  ngOnInit() {
    // Read folder param from route; fall back to empty string if not provided
    this.route.paramMap.subscribe(params => {
      this.folderName = params.get('folder') ?? '';
      if (this.folderName.startsWith('list_')) {
        this.title = "2026";
      }
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
    const base = this.getBase();
    console.log('Base URI:', base);

    // CSV file is located at: <folderName>/<folderName>.mar.csv
    // If no folder is provided, fall back to the original flat file
    const csvPath = this.folderName
      ? `${base}data/${this.folderName}/${this.folderName}.mar.csv`
      : `${base}data/bhiwandi/bhiwandi.mar.csv`;

    this.http.get(csvPath, { responseType: 'text' })
      .subscribe(csv => {
        const lines = csv.split('\n');
        const headerRow = lines[0];
        const headerCols = this.splitCSV(headerRow);

        // Determine column indices from header
        this.col_filename = headerCols.findIndex(col => col.toLowerCase() === 'filename');
        this.col_content = headerCols.findIndex(col => col.toLowerCase() === 'content');
        this.col_page = headerCols.findIndex(col => col.toLowerCase() === 'page');

        // Default to 0 and 1 if not found
        if (this.col_filename === -1) this.col_filename = 0;
        if (this.col_content === -1) this.col_content = 1;

        const rows = csv.split('\n').slice(1); // skip header row
        const uniqueMap = new Map<string, IAddressInfo>();

        rows
          .filter(r => r.trim().length > 0)
          .forEach(row => {
            const cols = this.splitCSV(row);
            const item: IAddressInfo = {
              filename: cols[this.col_filename].trim(),
              content: cols[this.col_content].trim(), //.replace(/\s([अ)ब)क)])\)/gi, '<br>$1)')
              page: this.col_page !== -1 ? parseInt(cols[this.col_page].trim(), 10) : -1
            };
            console.log(cols[this.col_content])
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
    let base = this.getBase();
    // File is located inside the folder: <folderName>/<filename>
    let url = `${base}data/${this.folderName}/${item.filename}`;

    if (item.page && item.page > 0) {
      url = `${base}data/${this.folderName}/${item.filename}#page=${item.page}`;
    }

    window.open(url, '_blank');
  }
}