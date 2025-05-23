import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { delay, retryWhen, tap } from 'rxjs/operators';
import { webSocket, WebSocketSubject } from 'rxjs/webSocket';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class WebSocketService {
  private clusterSocket$: WebSocketSubject<any> | null = null;
  private namespaceResourceSockets: Map<string, WebSocketSubject<any>> = new Map();
  private tasksSocket$: WebSocketSubject<any> | null = null;
  private taskLogsSocket$: WebSocketSubject<any> | null = null;
  private baseUrl = environment.wsApiUrl;

  constructor() { }

  public connectToCluster(): Observable<any> {
    if (!this.clusterSocket$ || this.clusterSocket$.closed) {
      this.clusterSocket$ = this.createWebSocket('/ws/cluster');
    }
    return this.clusterSocket$.pipe(
      retryWhen(errors =>
        errors.pipe(
          tap(err => console.error('WebSocket error:', err)),
          delay(1000)
        )
      )
    );
  }

  public connectToNamespaceResource(namespace: string, resourceType: string): Observable<any> {
    const key = `${namespace}_${resourceType}`;
    if (!this.namespaceResourceSockets.has(key) || this.namespaceResourceSockets.get(key)?.closed) {
      const socket = this.createWebSocket(`/ws/namespace/${namespace}/${resourceType}`);
      this.namespaceResourceSockets.set(key, socket);
    }

    return this.namespaceResourceSockets.get(key)!.pipe(
      retryWhen(errors =>
        errors.pipe(
          tap(err => console.error('WebSocket error:', err)),
          delay(1000)
        )
      )
    );
  }

  public connectToTasks(package_name: string, stage: string, version: string): Observable<any> {
    if (!this.tasksSocket$ || this.tasksSocket$.closed) {
      this.tasksSocket$ = this.createWebSocket(`/ws/${package_name}/${stage}/${version}`);
    }
    return this.tasksSocket$.pipe(
      retryWhen(errors =>
        errors.pipe(
          tap(err => console.error('WebSocket error:', err)),
          delay(1000)
        )
      )
    );
  }

  public connectToTaskLogs(taskId: string): Observable<any> {
    if (!this.taskLogsSocket$ || this.taskLogsSocket$.closed) {
      this.taskLogsSocket$ = this.createWebSocket(`/ws/task/${taskId}`);
    }
    return this.taskLogsSocket$.pipe(
      retryWhen(errors =>
        errors.pipe(
          tap(err => console.error('WebSocket error:', err)),
          delay(1000)
        )
      )
    );
  }

  private createWebSocket(path: string): WebSocketSubject<any> {
    return webSocket({
      url: `${this.baseUrl}${path}`,
      openObserver: {
        next: () => {
          console.log('WebSocket connected to', path);
        }
      },
    });
  }

  public closeClusterConnection() {
    if (this.clusterSocket$) {
      this.clusterSocket$.complete();
      this.clusterSocket$ = null;
    }
  }

  public closeNamespaceResourceConnection(namespace: string, resourceType: string) {
    const key = `${namespace}_${resourceType}`;
    if (this.namespaceResourceSockets.has(key)) {
      this.namespaceResourceSockets.get(key)?.complete();
      this.namespaceResourceSockets.delete(key);
    }
  }

  public closeAllNamespaceConnections() {
    this.namespaceResourceSockets.forEach(socket => socket.complete());
    this.namespaceResourceSockets.clear();
  }

  public closeTaskLogsConnection() {
    if (this.taskLogsSocket$) {
      this.taskLogsSocket$.complete();
      this.taskLogsSocket$ = null;
    }
  }

  public closeTasksConnection() {
    if (this.tasksSocket$) {
      this.tasksSocket$.complete();
      this.tasksSocket$ = null;
    }
  }
}