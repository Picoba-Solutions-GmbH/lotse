import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { Runtime } from '../misc/Runtime';
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

  async getAllPackagesOverviewAsync(stage: string): Promise<PackageInfo[]> {
    return await firstValueFrom(this.http.get<PackageInfo[]>(`${environment.url}/packages/${stage}`));
  }

  async getPackageOverviewAsync(stage: string, packageName: string): Promise<PackageDetail[]> {
    return await firstValueFrom(this.http.get<PackageDetail[]>(`${environment.url}/packages/${packageName}/${stage}`));
  }

  async getPackageInstanceAsync(stage: string, packageName: string, packageVersion: string): Promise<PackageInstance> {
    return await firstValueFrom(this.http.get<PackageInstance>(`${environment.url}/packages/${packageName}/${stage}/${packageVersion}`));
  }

  async deployPackageAsync(formData: FormData): Promise<void> {
    await firstValueFrom(this.http.post(`${environment.url}/packages/deploy`, formData));
  }

  async deletePackageVersionAsync(packageName: string, stage: string, version: string) {
    return firstValueFrom(this.http.delete(`${environment.url}/packages/${packageName}/${stage}/${version}`));
  }

  async setAsDefaultVersionAsync(packageName: string, stage: string, version: string) {
    return firstValueFrom(this.http.post(`${environment.url}/packages/${packageName}/${stage}/${version}/default`, {}));
  }

  async getPackageEnvironmentAsync(stage: string, packageName: string, version: string): Promise<PackageEnvironment[]> {
    return await firstValueFrom(this.http.get<PackageEnvironment[]>(`${environment.url}/packages/${packageName}/${stage}/${version}/environment`));
  }
}
