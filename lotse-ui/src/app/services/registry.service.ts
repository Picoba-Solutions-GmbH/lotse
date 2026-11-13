import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { DiscoveredRepository, Registry, RegistryRequest, RegistryTestRequest, RegistryTestResult } from '../models/Registry';

@Injectable({
    providedIn: 'root',
})
export class RegistryService {
    constructor(private http: HttpClient) { }

    async listAsync(): Promise<Registry[]> {
        return firstValueFrom(this.http.get<Registry[]>(`${environment.url}/registries/`));
    }

    async createAsync(request: RegistryRequest): Promise<Registry> {
        return firstValueFrom(this.http.post<Registry>(`${environment.url}/registries/`, request));
    }

    async updateAsync(id: string, request: RegistryRequest): Promise<Registry> {
        return firstValueFrom(this.http.put<Registry>(`${environment.url}/registries/${id}`, request));
    }

    async deleteAsync(id: string): Promise<void> {
        await firstValueFrom(this.http.delete(`${environment.url}/registries/${id}`));
    }

    async testAsync(request: RegistryTestRequest): Promise<RegistryTestResult> {
        return firstValueFrom(this.http.post<RegistryTestResult>(`${environment.url}/registries/test`, request));
    }

    async listRepositoriesAsync(id: string, path?: string): Promise<DiscoveredRepository[]> {
        const params: Record<string, string> = path !== undefined ? { path } : {};
        return firstValueFrom(this.http.get<DiscoveredRepository[]>(`${environment.url}/registries/${id}/repositories`, { params }));
    }

    /** Registers all new images below the discovery path. */
    async discoverAsync(id: string): Promise<{ created: string[]; registry: Registry }> {
        return firstValueFrom(this.http.post<{ created: string[]; registry: Registry }>(`${environment.url}/registries/${id}/discover`, {}));
    }
}
