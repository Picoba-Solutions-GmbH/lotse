import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { PackageAccess } from '../models/PackageAccess';

@Injectable({
  providedIn: 'root',
})
export class PackageAccessService {
  constructor(private http: HttpClient) { }

  private url(packageName: string): string {
    return `${environment.url}/package-access/${encodeURIComponent(packageName)}`;
  }

  async getAccessAsync(packageName: string): Promise<PackageAccess> {
    return await firstValueFrom(this.http.get<PackageAccess>(this.url(packageName)));
  }

  async shareAsync(packageName: string, userId: string, canExecute: boolean, canEdit: boolean): Promise<void> {
    await firstValueFrom(this.http.put(`${this.url(packageName)}/shares/${userId}`,
      { can_execute: canExecute, can_edit: canEdit }));
  }

  async unshareAsync(packageName: string, userId: string): Promise<void> {
    await firstValueFrom(this.http.delete(`${this.url(packageName)}/shares/${userId}`));
  }

  async setOwnerAsync(packageName: string, userId: string | null): Promise<void> {
    await firstValueFrom(this.http.put(`${this.url(packageName)}/owner`, { user_id: userId }));
  }
}
