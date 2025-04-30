import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { environment } from '../../environments/environment';
import { AsyncPackageResponse } from '../models/AsyncPackageResponse';
import { SyncPackageResponse } from '../models/SyncPackageResponse';
import { PackageRequest } from '../models/PackageRequest';

@Injectable({
  providedIn: 'root',
})
export class ExecutionService {
  constructor(private http: HttpClient) { }

  async executePackageAsync(request: PackageRequest): Promise<SyncPackageResponse | AsyncPackageResponse> {
    return await firstValueFromAsync(
      this.http.post<SyncPackageResponse | AsyncPackageResponse>(`${environment.url}/execute`, request),
    );
  }

  async startEmptyInstanceAsync(request: PackageRequest): Promise<SyncPackageResponse | AsyncPackageResponse> {
    return await firstValueFromAsync(
      this.http.post<SyncPackageResponse | AsyncPackageResponse>(`${environment.url}/execute/empty-instance`, request),
    );
  }
}
