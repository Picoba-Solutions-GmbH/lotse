import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import {
    GitConnectionTestRequest, GitConnectionTestResult, GitSource, GitSourceCreateRequest,
    GitSourceUpdateRequest, GitSyncResult, GitTag
} from '../models/GitSource';

@Injectable({
    providedIn: 'root',
})
export class GitSourceService {
    constructor(private http: HttpClient) { }

    async listAsync(packageName?: string): Promise<GitSource[]> {
        const params: Record<string, string> = packageName ? { package_name: packageName } : {};
        return firstValueFrom(this.http.get<GitSource[]>(`${environment.url}/git-sources/`, { params }));
    }

    async getForPackageAsync(packageName: string): Promise<GitSource | null> {
        const sources = await this.listAsync(packageName);
        return sources.length > 0 ? sources[0] : null;
    }

    async createAsync(request: GitSourceCreateRequest): Promise<GitSource> {
        return firstValueFrom(this.http.post<GitSource>(`${environment.url}/git-sources/`, request));
    }

    async updateAsync(id: string, request: GitSourceUpdateRequest): Promise<GitSource> {
        return firstValueFrom(this.http.put<GitSource>(`${environment.url}/git-sources/${id}`, request));
    }

    async deleteAsync(id: string): Promise<void> {
        await firstValueFrom(this.http.delete(`${environment.url}/git-sources/${id}`));
    }

    async testConnectionAsync(request: GitConnectionTestRequest): Promise<GitConnectionTestResult> {
        return firstValueFrom(this.http.post<GitConnectionTestResult>(`${environment.url}/git-sources/test`, request));
    }

    async listTagsAsync(id: string): Promise<GitTag[]> {
        return firstValueFrom(this.http.get<GitTag[]>(`${environment.url}/git-sources/${id}/tags`));
    }

    async refreshAsync(id: string): Promise<GitSource> {
        return firstValueFrom(this.http.post<GitSource>(`${environment.url}/git-sources/${id}/refresh`, {}));
    }

    /** Deploys `tag`, or the newest tag when no tag is given. */
    async syncAsync(id: string, tag?: string): Promise<GitSyncResult> {
        return firstValueFrom(this.http.post<GitSyncResult>(`${environment.url}/git-sources/${id}/sync`, { tag: tag ?? null }));
    }

    webhookUrl(source: GitSource): string {
        return `${environment.url}${source.webhook_path}`;
    }
}
