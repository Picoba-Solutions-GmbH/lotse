import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { environment } from '../../environments/environment';

export interface FeatureFlags {
  authentication_enabled: boolean;
  live_coding_enabled: boolean;
}

@Injectable({
  providedIn: 'root',
})
export class FeatureFlagService {
  private flags: FeatureFlags | null = null;

  constructor(private http: HttpClient) { }

  private async fetchFlags(): Promise<FeatureFlags> {
    if (this.flags !== null) {
      return this.flags;
    }

    this.flags = await firstValueFromAsync(
      this.http.get<FeatureFlags>(`${environment.url}/feature-flags`)
    ) as FeatureFlags;

    return this.flags;
  }

  async isAuthenticationEnabled(): Promise<boolean> {
    const flags = await this.fetchFlags();
    return flags.authentication_enabled;
  }

  async isLiveCodingEnabled(): Promise<boolean> {
    const flags = await this.fetchFlags();
    return flags.live_coding_enabled;
  }
}
