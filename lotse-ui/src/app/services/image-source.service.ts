import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { ImageSource, ImageSourceCreateRequest, ImageSourceSettings, ImageSyncResult, ImageTag } from '../models/ImageSource';

@Injectable({
    providedIn: 'root',
})
export class ImageSourceService {
    constructor(private http: HttpClient) { }

    async listAsync(packageName?: string): Promise<ImageSource[]> {
        const params: Record<string, string> = packageName ? { package_name: packageName } : {};
        return firstValueFrom(this.http.get<ImageSource[]>(`${environment.url}/image-sources/`, { params }));
    }

    async getForPackageAsync(packageName: string): Promise<ImageSource | null> {
        const sources = await this.listAsync(packageName);
        return sources.length > 0 ? sources[0] : null;
    }

    async createAsync(request: ImageSourceCreateRequest): Promise<ImageSource> {
        return firstValueFrom(this.http.post<ImageSource>(`${environment.url}/image-sources/`, request));
    }

    async updateAsync(id: string, request: ImageSourceSettings): Promise<ImageSource> {
        return firstValueFrom(this.http.put<ImageSource>(`${environment.url}/image-sources/${id}`, request));
    }

    async deleteAsync(id: string): Promise<void> {
        await firstValueFrom(this.http.delete(`${environment.url}/image-sources/${id}`));
    }

    async listTagsAsync(id: string): Promise<ImageTag[]> {
        return firstValueFrom(this.http.get<ImageTag[]>(`${environment.url}/image-sources/${id}/tags`));
    }

    async refreshAsync(id: string): Promise<ImageSource> {
        return firstValueFrom(this.http.post<ImageSource>(`${environment.url}/image-sources/${id}/refresh`, {}));
    }

    async syncAsync(id: string, tag?: string): Promise<ImageSyncResult> {
        return firstValueFrom(this.http.post<ImageSyncResult>(`${environment.url}/image-sources/${id}/sync`, { tag: tag ?? null }));
    }

    webhookUrl(source: ImageSource): string {
        return `${environment.url}${source.webhook_path}`;
    }
}
