import { HttpClient } from '@angular/common/http';
import { EventEmitter, Injectable } from '@angular/core';
import { Observable, of } from 'rxjs';
import { map, tap } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { Role } from '../misc/Role';

interface AuthenticationResponse {
  authentication_enabled: boolean;
}

interface TokenResponse {
  access_token: string;
}

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private token: string | null = null;
  private isAuthEnabled: boolean | null = null;
  public authStateChanged = new EventEmitter<boolean>();

  constructor(private http: HttpClient) {
    const storedToken = localStorage.getItem('token');
    if (storedToken) {
      this.token = storedToken;
    }
  }

  async isAuthenticationEnabledAsync(): Promise<boolean> {
    if (this.isAuthEnabled !== null) {
      return this.isAuthEnabled;
    }

    const response = await firstValueFromAsync(
      this.http.get<AuthenticationResponse>(`${environment.url}/authentication/is-authentication-enabled`)
    ) as AuthenticationResponse;
    this.isAuthEnabled = response.authentication_enabled;
    return this.isAuthEnabled;
  }

  login(username: string, password: string): Observable<string> {
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);

    return this.http
      .post<TokenResponse>(
        `${environment.url}/authentication/token`,
        formData
      )
      .pipe(
        tap((response) => {
          this.token = response.access_token;
          const payload = JSON.parse(atob(this.token.split('.')[1]));
          localStorage.setItem('role', btoa(payload.role));
          localStorage.setItem('token', this.token);
          const encodedLoginData = btoa(JSON.stringify({ username, password }));
          localStorage.setItem('login', encodedLoginData);
          this.authStateChanged.emit(true);
        }),
        map((response) => response.access_token),
      );
  }

  refreshToken(): Observable<string> {
    const login = this.getLogin();
    if (login) {
      const { username, password } = JSON.parse(login);
      return this.login(username, password);
    }
    return of('');
  }

  getRole(): Role {
    const roleEncoded = localStorage.getItem('role');
    const decodedRole = roleEncoded ? atob(roleEncoded) : null;
    if (decodedRole) {
      return decodedRole as Role;
    } else {
      return Role.UNAUTHORIZED;
    }
  }

  getLogin(): string | null {
    const loginEncoded = localStorage.getItem('login');
    return loginEncoded ? atob(loginEncoded) : null;
  }

  logout(): void {
    this.token = null;
    localStorage.removeItem('token');
    localStorage.removeItem('login');
    localStorage.removeItem('role');
    this.authStateChanged.emit(false);
  }

  getToken(): string | null {
    return this.token;
  }

  isLoggedIn(): boolean {
    return !!this.token;
  }
}
