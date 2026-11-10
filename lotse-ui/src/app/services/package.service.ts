import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { PackageDetail, PackageFile, PackageFileContent, PackageInfo, PackageInstance, PackageModifications } from '../models/Package';
import { PackageArgument } from '../models/PackageArgument';
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

  async updatePackageEnvironmentAsync(packageName: string, version: string, variables: PackageEnvironment[]): Promise<PackageModifications> {
    return await firstValueFrom(this.http.put<PackageModifications>(`${environment.url}/packages/${packageName}/${version}/environment`, variables));
  }

  async getPackageArgumentsAsync(packageName: string, version: string): Promise<PackageArgument[]> {
    return await firstValueFrom(this.http.get<PackageArgument[]>(`${environment.url}/packages/${packageName}/${version}/arguments`));
  }

  async updatePackageArgumentsAsync(packageName: string, version: string, args: PackageArgument[]): Promise<PackageModifications> {
    return await firstValueFrom(this.http.put<PackageModifications>(`${environment.url}/packages/${packageName}/${version}/arguments`, args));
  }

  async revertPackageConfigAsync(packageName: string, version: string): Promise<PackageModifications> {
    return await firstValueFrom(this.http.post<PackageModifications>(`${environment.url}/packages/${packageName}/${version}/config/revert`, {}));
  }

  async getPackageFilesAsync(packageName: string, version: string): Promise<PackageFile[]> {
    return await firstValueFrom(this.http.get<PackageFile[]>(`${environment.url}/packages/${packageName}/${version}/files`));
  }

  async getPackageFileContentAsync(packageName: string, version: string, path: string): Promise<PackageFileContent> {
    return await firstValueFrom(this.http.get<PackageFileContent>(`${environment.url}/packages/${packageName}/${version}/files/content`, { params: { path } }));
  }

  async updatePackageFileContentAsync(packageName: string, version: string, file: PackageFileContent): Promise<PackageModifications> {
    return await firstValueFrom(this.http.put<PackageModifications>(`${environment.url}/packages/${packageName}/${version}/files/content`, file));
  }

  async revertPackageFileAsync(packageName: string, version: string, path: string): Promise<PackageModifications> {
    return await firstValueFrom(this.http.post<PackageModifications>(`${environment.url}/packages/${packageName}/${version}/files/revert`, { path }));
  }

  async revertPackageAsync(packageName: string, version: string): Promise<PackageModifications> {
    return await firstValueFrom(this.http.post<PackageModifications>(`${environment.url}/packages/${packageName}/${version}/revert`, {}));
  }
}
