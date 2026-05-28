import { HttpClient } from '@angular/common/http';
import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, interval, Subscription } from 'rxjs';
import { startWith, switchMap } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface ServerStatus {
  server: string;
  activemq_enabled: boolean;
  activemq_connected?: boolean;
}

@Injectable({
  providedIn: 'root',
})
export class StatusService implements OnDestroy {
  serverReachable$ = new BehaviorSubject<boolean | null>(null);
  activemqEnabled$ = new BehaviorSubject<boolean>(false);
  activemqConnected$ = new BehaviorSubject<boolean | null>(null);

  private pollSub: Subscription | null = null;

  constructor(private http: HttpClient) {
    this.startPolling();
  }

  private startPolling(): void {
    this.pollSub = interval(5000)
      .pipe(
        startWith(0),
        switchMap(() =>
          this.http.get<ServerStatus>(`${environment.url}/status`)
        )
      )
      .subscribe({
        next: (data) => {
          this.serverReachable$.next(true);
          this.activemqEnabled$.next(data.activemq_enabled);
          if (data.activemq_enabled) {
            this.activemqConnected$.next(data.activemq_connected ?? false);
          }
        },
        error: () => {
          this.serverReachable$.next(false);
          // restart after failure
          this.pollSub?.unsubscribe();
          setTimeout(() => this.startPolling(), 5000);
        },
      });
  }

  ngOnDestroy(): void {
    this.pollSub?.unsubscribe();
  }
}
