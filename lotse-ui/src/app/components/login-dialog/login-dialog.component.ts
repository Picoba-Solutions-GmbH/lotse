import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { DynamicDialogRef } from 'primeng/dynamicdialog';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../../services/auth.service';

@Component({
  selector: 'app-login-dialog',
  templateUrl: './login-dialog.component.html',
  styleUrl: './login-dialog.component.scss',
  imports: [
    CommonModule,
    FormsModule,
    ButtonModule,
    InputTextModule,
    PasswordModule,
  ]
})
export class LoginDialogComponent {
  username: string = '';
  password: string = '';
  isLoading = false;
  errorMessage: string | null = null;

  constructor(
    public ref: DynamicDialogRef,
    private authService: AuthService
  ) { }

  async onLogin(): Promise<void> {
    if (!this.username || !this.password) return;
    this.isLoading = true;
    this.errorMessage = null;
    try {
      await firstValueFrom(this.authService.login(this.username, this.password));
      this.ref.close(true);
    } catch {
      this.errorMessage = 'Invalid username or password.';
    } finally {
      this.isLoading = false;
    }
  }

  onCancel(): void {
    this.ref.close(null);
  }
}
