import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { NetworkShareDetail, NetworkShareProvisionRequest, NetworkShareResponse, NetworkShareTestResult, NetworkShareUpdateRequest, NetworkShareVolume } from '../models/NetworkShare';

@Injectable({
  providedIn: 'root',
})
export class NetworkShareService {
  constructor(private http: HttpClient) {}

  async provisionNetworkShare(request: NetworkShareProvisionRequest): Promise<NetworkShareResponse> {
    return firstValueFrom(
      this.http.post<NetworkShareResponse>(`${environment.url}/network-shares/provision`, request)
    );
  }

  async listNetworkShares(): Promise<NetworkShareVolume[]> {
    return firstValueFrom(
      this.http.get<NetworkShareVolume[]>(`${environment.url}/network-shares/`)
    );
  }

  async getNetworkShareDetail(id: string): Promise<NetworkShareDetail> {
    return firstValueFrom(
      this.http.get<NetworkShareDetail>(`${environment.url}/network-shares/${id}`)
    );
  }

  async updateNetworkShare(id: string, request: NetworkShareUpdateRequest): Promise<NetworkShareResponse> {
    return firstValueFrom(
      this.http.put<NetworkShareResponse>(`${environment.url}/network-shares/${id}`, request)
    );
  }

  async testNetworkShare(id: string): Promise<NetworkShareTestResult> {
    return firstValueFrom(
      this.http.post<NetworkShareTestResult>(`${environment.url}/network-shares/${id}/test`, {})
    );
  }

  async deleteNetworkShare(id: string): Promise<void> {
    return firstValueFrom(
      this.http.delete<void>(`${environment.url}/network-shares/${id}`)
    );
  }
}

