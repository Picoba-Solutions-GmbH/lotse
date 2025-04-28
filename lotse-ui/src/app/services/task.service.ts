import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { environment } from '../../environments/environment';
import { SyncPackageResponse } from '../models/SyncPackageResponse';
import { AsyncPackageResponse } from '../models/AsyncPackageResponse';
import { TaskInfo } from '../models/TaskInfo';
import { TaskLogs } from '../models/TaskLogs';


@Injectable({
  providedIn: 'root',
})
export class TaskService {
  constructor(private http: HttpClient) { }

  async getTaskStatusAsync(taskId: string): Promise<AsyncPackageResponse> {
    return await firstValueFromAsync(this.http.get<AsyncPackageResponse>(`${environment.url}/task/status/${taskId}`));
  }

  async getTasksAsync(stage: string): Promise<TaskInfo[]> {
    return await firstValueFromAsync(this.http.get<TaskInfo[]>(`${environment.url}/tasks/${stage}`));
  }

  async cancelTaskAsync(taskId: string): Promise<TaskInfo> {
    return await firstValueFromAsync(this.http.post<TaskInfo>(`${environment.url}/task/${taskId}/cancel`, {}));
  }

  async getTaskLogsAsync(taskId: string): Promise<TaskLogs> {
    return await firstValueFromAsync(this.http.get<TaskLogs>(`${environment.url}/task/${taskId}/logs`));
  }

  async postRunVsCodeServerAsync(taskId: string): Promise<SyncPackageResponse> {
    return await firstValueFromAsync(
      this.http.post<SyncPackageResponse>(`${environment.url}/task/${taskId}/run-vscode-server`, {}),
    );
  }
}
