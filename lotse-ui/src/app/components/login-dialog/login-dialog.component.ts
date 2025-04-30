import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { DynamicDialogRef } from 'primeng/dynamicdialog';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';

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

  constructor(public ref: DynamicDialogRef) { }

  onLogin(): void {
    if (this.username && this.password) {
      this.ref.close({ username: this.username, password: this.password });
    }
  }
}
