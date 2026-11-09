import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';
import { SelectModule } from 'primeng/select';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { TooltipModule } from 'primeng/tooltip';
import { Role } from '../../misc/Role';
import { User } from '../../models/User';
import { AuthService } from '../../services/auth.service';
import { UserService } from '../../services/user.service';

@Component({
  selector: 'app-users',
  imports: [
    CommonModule,
    FormsModule,
    ButtonModule,
    DialogModule,
    InputTextModule,
    PasswordModule,
    SelectModule,
    TableModule,
    TagModule,
    TooltipModule,
  ],
  templateUrl: './users.component.html',
})
export class UsersComponent implements OnInit {
  users: User[] = [];
  loading = false;
  saving = false;

  readonly roleOptions = [
    { label: 'User', value: Role.USER },
    { label: 'Admin', value: Role.ADMIN },
  ];

  showCreateDialog = false;
  createForm = { name: '', password: '', role: Role.USER, display_name: '', email: '' };

  showPasswordDialog = false;
  passwordUser: User | null = null;
  newPassword = '';

  constructor(
    private userService: UserService,
    private authService: AuthService,
    private messageService: MessageService,
    private confirmationService: ConfirmationService,
  ) { }

  async ngOnInit(): Promise<void> {
    await this.loadUsers();
  }

  isCurrentUser(user: User): boolean {
    return user.id === this.authService.getUserId();
  }

  async loadUsers(): Promise<void> {
    this.loading = true;
    try {
      this.users = await this.userService.listUsersAsync();
    } catch (error) {
      this.showError('Failed to load users', error);
    } finally {
      this.loading = false;
    }
  }

  async changeRole(user: User, role: Role): Promise<void> {
    const previousRole = user.role;
    user.role = role;
    try {
      await this.userService.updateUserAsync(user.id, { role });
      this.messageService.add({
        severity: 'success', summary: 'Role changed', detail: `${user.name} is now ${role}`, life: 3000,
      });
    } catch (error) {
      user.role = previousRole;
      this.showError('Failed to change role', error);
    }
  }

  openCreateDialog(): void {
    this.createForm = { name: '', password: '', role: Role.USER, display_name: '', email: '' };
    this.showCreateDialog = true;
  }

  async createUser(): Promise<void> {
    if (!this.createForm.name.trim() || this.createForm.password.length < 6) {
      return;
    }
    this.saving = true;
    try {
      await this.userService.createUserAsync({
        name: this.createForm.name.trim(),
        password: this.createForm.password,
        role: this.createForm.role,
        display_name: this.createForm.display_name.trim() || undefined,
        email: this.createForm.email.trim() || undefined,
      });
      this.showCreateDialog = false;
      this.messageService.add({
        severity: 'success', summary: 'User created', detail: this.createForm.name, life: 3000,
      });
      await this.loadUsers();
    } catch (error) {
      this.showError('Failed to create user', error);
    } finally {
      this.saving = false;
    }
  }

  openPasswordDialog(user: User): void {
    this.passwordUser = user;
    this.newPassword = '';
    this.showPasswordDialog = true;
  }

  async resetPassword(): Promise<void> {
    if (!this.passwordUser || this.newPassword.length < 6) {
      return;
    }
    this.saving = true;
    try {
      await this.userService.updateUserAsync(this.passwordUser.id, { password: this.newPassword });
      this.showPasswordDialog = false;
      this.messageService.add({
        severity: 'success', summary: 'Password changed', detail: this.passwordUser.name, life: 3000,
      });
    } catch (error) {
      this.showError('Failed to change password', error);
    } finally {
      this.saving = false;
    }
  }

  deleteUser(user: User): void {
    this.confirmationService.confirm({
      header: 'Delete user',
      message: `Delete ${user.name}? Packages owned by this user become unowned and are only visible to admins until you assign a new owner.`,
      icon: 'pi pi-exclamation-triangle',
      acceptButtonStyleClass: 'p-button-danger',
      accept: async () => {
        try {
          await this.userService.deleteUserAsync(user.id);
          this.messageService.add({ severity: 'success', summary: 'User deleted', detail: user.name, life: 3000 });
          await this.loadUsers();
        } catch (error) {
          this.showError('Failed to delete user', error);
        }
      },
    });
  }

  private showError(summary: string, error: any): void {
    this.messageService.add({
      severity: 'error', summary, detail: error?.error?.detail ?? 'Unknown error', life: 5000,
    });
  }
}
