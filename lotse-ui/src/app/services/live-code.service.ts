import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { environment } from '../../environments/environment';
import { AsyncPackageResponse } from '../models/AsyncPackageResponse';
import { LivePackage, LivePackageInfo } from '../models/LiveCode';
import { PackageRequestArguments } from '../models/PackageRequestArguments';
import { SyncPackageResponse } from '../models/SyncPackageResponse';

@Injectable({
    providedIn: 'root',
})
export class LiveCodeService {
    constructor(private http: HttpClient) { }

    async getPackagesAsync(): Promise<LivePackageInfo[]> {
        return await firstValueFromAsync(
            this.http.get<LivePackageInfo[]>(`${environment.url}/packages/live`),
        );
    }

    async getPackageAsync(packageName: string): Promise<LivePackage> {
        return await firstValueFromAsync(
            this.http.get<LivePackage>(`${environment.url}/packages/live/${packageName}`),
        );
    }

    async savePackageAsync(pkg: LivePackage): Promise<void> {
        await firstValueFromAsync(
            this.http.post<void>(`${environment.url}/packages/live`, pkg),
        );
    }

    async deletePackageAsync(packageName: string): Promise<void> {
        await firstValueFromAsync(
            this.http.delete<void>(`${environment.url}/packages/live/${packageName}`),
        );
    }

    async runPackageAsync(
        packageName: string,
        args: PackageRequestArguments[],
        waitForCompletion = true,
    ): Promise<SyncPackageResponse | AsyncPackageResponse> {
        return await firstValueFromAsync(
            this.http.post<SyncPackageResponse | AsyncPackageResponse>(
                `${environment.url}/packages/live/${packageName}/run`,
                { arguments: args, wait_for_completion: waitForCompletion },
            ),
        );
    }
}
