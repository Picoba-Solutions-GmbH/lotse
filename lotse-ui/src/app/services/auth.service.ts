import { HttpClient } from '@angular/common/http';
import { EventEmitter, Injectable } from '@angular/core';
import { firstValueFrom, Observable } from 'rxjs';
import { map, tap } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { Role } from '../misc/Role';

interface TokenResponse {
  access_token: string;
}

interface TokenPayload {
  sub: string;
  uid: string;
  role: Role;
  exp: number;
}

const TOKEN_KEY = 'token';
const TOKEN_COOKIE = 'lotse_token';
const REFRESH_BEFORE_EXPIRY_MS = 5 * 60 * 1000;

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private token: string | null = null;
  private payload: TokenPayload | null = null;
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;
  /** Set once the backend rejected a request with 401, i.e. authentication is enforced. */
  private authEnforced = false;

  public authStateChanged = new EventEmitter<boolean>();
  /** Emitted when the backend rejected the token and the user has to log in again. */
  public loginRequired = new EventEmitter<void>();

  constructor(private http: HttpClient) {
    // Older versions stored the plain credentials, never keep them around.
    localStorage.removeItem('login');
    localStorage.removeItem('role');

    const storedToken = localStorage.getItem(TOKEN_KEY);
    if (storedToken) {
      this.setToken(storedToken, false);
    }
  }

  login(username: string, password: string): Observable<string> {
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);

    return this.http
      .post<TokenResponse>(`${environment.url}/authentication/token`, formData)
      .pipe(
        tap((response) => this.setToken(response.access_token, true)),
        map((response) => response.access_token),
      );
  }

  async refreshTokenAsync(): Promise<void> {
    if (!this.token) {
      return;
    }
    try {
      const response = await firstValueFrom(
        this.http.post<TokenResponse>(`${environment.url}/authentication/token/refresh`, {}));
      this.setToken(response.access_token, false);
    } catch {
      this.sessionExpired();
    }
  }

  /** Called when the backend answers with 401. */
  sessionExpired(): void {
    this.authEnforced = true;
    if (!this.token) {
      this.loginRequired.emit();
      return;
    }
    this.logout();
    this.loginRequired.emit();
  }

  logout(): void {
    this.token = null;
    this.payload = null;
    this.clearRefreshTimer();
    localStorage.removeItem(TOKEN_KEY);
    document.cookie = `${TOKEN_COOKIE}=; path=/; max-age=0; SameSite=Lax`;
    this.authStateChanged.emit(false);
  }

  getRole(): Role | null {
    return this.payload?.role ?? null;
  }

  isAdmin(): boolean {
    return this.getRole() === Role.ADMIN;
  }

  getUsername(): string | null {
    return this.payload?.sub ?? null;
  }

  getUserId(): string | null {
    return this.payload?.uid ?? null;
  }

  getToken(): string | null {
    return this.token;
  }

  isLoggedIn(): boolean {
    return !!this.token;
  }

  isAuthEnforced(): boolean {
    return this.authEnforced;
  }

  private setToken(token: string, emit: boolean): void {
    const payload = this.decode(token);
    if (!payload || payload.exp * 1000 <= Date.now()) {
      this.logout();
      return;
    }

    this.token = token;
    this.payload = payload;
    localStorage.setItem(TOKEN_KEY, token);

    // The cookie authenticates browser tabs that cannot send headers (package UIs, VS Code).
    const secure = window.location.protocol === 'https:' ? '; Secure' : '';
    const maxAge = Math.max(0, Math.floor(payload.exp - Date.now() / 1000));
    document.cookie = `${TOKEN_COOKIE}=${token}; path=/; max-age=${maxAge}; SameSite=Lax${secure}`;

    this.scheduleRefresh(payload.exp * 1000);
    if (emit) {
      this.authStateChanged.emit(true);
    }
  }

  private scheduleRefresh(expiresAt: number): void {
    this.clearRefreshTimer();
    const delay = Math.max(0, expiresAt - Date.now() - REFRESH_BEFORE_EXPIRY_MS);
    this.refreshTimer = setTimeout(() => this.refreshTokenAsync(), delay);
  }

  private clearRefreshTimer(): void {
    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer);
      this.refreshTimer = null;
    }
  }

  private decode(token: string): TokenPayload | null {
    try {
      const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
      return JSON.parse(atob(base64)) as TokenPayload;
    } catch {
      return null;
    }
  }
}
