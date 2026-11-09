import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { Role } from '../misc/Role';
import { User, UserLookup } from '../models/User';

@Injectable({
  providedIn: 'root',
})
export class UserService {
  constructor(private http: HttpClient) { }

  async listUsersAsync(): Promise<User[]> {
    return await firstValueFrom(this.http.get<User[]>(`${environment.url}/users`));
  }

  async lookupUsersAsync(query: string): Promise<UserLookup[]> {
    return await firstValueFrom(
      this.http.get<UserLookup[]>(`${environment.url}/users/lookup`, { params: { q: query } }));
  }

  async createUserAsync(user: { name: string; password: string; role: Role; display_name?: string; email?: string }): Promise<User> {
    return await firstValueFrom(this.http.post<User>(`${environment.url}/users`, user));
  }

  async updateUserAsync(userId: string, update: { role?: Role; password?: string }): Promise<User> {
    return await firstValueFrom(this.http.put<User>(`${environment.url}/users/${userId}`, update));
  }

  async deleteUserAsync(userId: string): Promise<void> {
    await firstValueFrom(this.http.delete(`${environment.url}/users/${userId}`));
  }
}
