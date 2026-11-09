import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { BackupRequest, StorageOverview } from '../models/Backup';

@Injectable({
  providedIn: 'root',
})
export class BackupService {
  constructor(private http: HttpClient) { }

  async getStorageOverviewAsync(): Promise<StorageOverview> {
    return await firstValueFrom(this.http.get<StorageOverview>(`${environment.url}/backup/storage`));
  }

  /** Downloads the backup zip and hands it to the browser as a file download. */
  async downloadBackupAsync(request: BackupRequest, fallbackFileName: string): Promise<void> {
    const response = await firstValueFrom(this.http.post(`${environment.url}/backup/download`, request, {
      observe: 'response',
      responseType: 'blob',
    }));

    const fileName = this.parseFileName(response.headers.get('Content-Disposition')) ?? fallbackFileName;
    const url = URL.createObjectURL(response.body!);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  private parseFileName(contentDisposition: string | null): string | null {
    if (!contentDisposition) {
      return null;
    }
    const utf8Match = /filename\*=utf-8''([^;]+)/i.exec(contentDisposition);
    if (utf8Match) {
      return decodeURIComponent(utf8Match[1]);
    }
    const match = /filename="?([^";]+)"?/i.exec(contentDisposition);
    return match ? match[1] : null;
  }
}
