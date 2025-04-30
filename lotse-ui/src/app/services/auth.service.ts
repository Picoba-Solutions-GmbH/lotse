import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable, of } from 'rxjs';
import { map, tap } from 'rxjs/operators';
import { environment } from '../../environments/environment';

class TokenResponse {
  access_token!: string;
}

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private token: string | null = null;

  constructor(private http: HttpClient) {
    const storedToken = localStorage.getItem('token');
    if (storedToken) {
      this.token = storedToken;
    }
  }

  login(username: string, password: string): Observable<string> {
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);

    return this.http
      .post<TokenResponse>(
        `${environment.url}/token`,
        formData
      )
      .pipe(
        tap((response) => {
          this.token = response.access_token;
          localStorage.setItem('token', this.token);
          localStorage.setItem('login', JSON.stringify({ username, password }));
        }),
        map((response) => response.access_token),
      );
  }

  refreshToken(): Observable<string> {
    const login = localStorage.getItem('login');
    if (login) {
      const { username, password } = JSON.parse(login);
      return this.login(username, password);
    }
    return of('');
  }

  logout(): void {
    this.token = null;
    localStorage.removeItem('token');
    localStorage.removeItem('login');
  }

  getToken(): string | null {
    return this.token;
  }

  isLoggedIn(): boolean {
    return !!this.token;
  }
}
