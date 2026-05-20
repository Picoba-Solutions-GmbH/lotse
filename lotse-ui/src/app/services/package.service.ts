import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { PackageDetail, PackageInfo, PackageInstance } from '../models/Package';
import { PackageEnvironment } from '../models/PackageEnvironment';
import { RepositoryConfig as PackageConfig } from '../models/RepositoryConfig';

@Injectable({
  providedIn: 'root',
})
export class PackageService {
  constructor(private http: HttpClient) { }

  async getPackagesAsync(): Promise<PackageConfig[]> {
    return await firstValueFrom(this.http.get<PackageConfig[]>(`${environment.url}/packages/list`));
  }

  async getAllPackagesOverviewAsync(): Promise<PackageInfo[]> {
    return await firstValueFrom(this.http.get<PackageInfo[]>(`${environment.url}/packages/`));
  }

  async getPackageOverviewAsync(packageName: string): Promise<PackageDetail[]> {
    return await firstValueFrom(this.http.get<PackageDetail[]>(`${environment.url}/packages/${packageName}`));
  }

  async getPackageInstanceAsync(packageName: string, packageVersion: string): Promise<PackageInstance> {
    return await firstValueFrom(this.http.get<PackageInstance>(`${environment.url}/packages/${packageName}/${packageVersion}`));
  }

  async deployPackageAsync(formData: FormData): Promise<void> {
    await firstValueFrom(this.http.post(`${environment.url}/packages/deploy`, formData));
  }

  async deletePackageVersionAsync(packageName: string, version: string) {
    return firstValueFrom(this.http.delete(`${environment.url}/packages/${packageName}/${version}`));
  }

  async setAsDefaultVersionAsync(packageName: string, version: string) {
    return firstValueFrom(this.http.post(`${environment.url}/packages/${packageName}/${version}/default`, {}));
  }

  async getPackageEnvironmentAsync(packageName: string, version: string): Promise<PackageEnvironment[]> {
    return await firstValueFrom(this.http.get<PackageEnvironment[]>(`${environment.url}/packages/${packageName}/${version}/environment`));
  }
}
