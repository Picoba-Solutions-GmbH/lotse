import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { AutoCompleteCompleteEvent, AutoCompleteModule } from 'primeng/autocomplete';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { DialogModule } from 'primeng/dialog';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { TooltipModule } from 'primeng/tooltip';
import { PackageAccess, PackageShare } from '../../../models/PackageAccess';
import { UserLookup } from '../../../models/User';
import { AuthService } from '../../../services/auth.service';
import { PackageAccessService } from '../../../services/package-access.service';
import { UserService } from '../../../services/user.service';

@Component({
  selector: 'app-package-share-dialog',
  imports: [
    CommonModule,
    FormsModule,
    AutoCompleteModule,
    ButtonModule,
    CheckboxModule,
    DialogModule,
    TableModule,
    TagModule,
    TooltipModule,
  ],
  templateUrl: './package-share-dialog.component.html',
})
export class PackageShareDialogComponent {
  @Input() packageName = '';
  @Input() visible = false;
  @Output() visibleChange = new EventEmitter<boolean>();
  /** Emitted after the owner or the shares changed. */
  @Output() changed = new EventEmitter<void>();

  access: PackageAccess | null = null;
  loading = false;
  saving = false;

  suggestions: UserLookup[] = [];
  newUser: UserLookup | null = null;
  newCanExecute = false;
  newCanEdit = false;

  newOwner: UserLookup | null = null;

  constructor(
    private packageAccessService: PackageAccessService,
    private userService: UserService,
    private authService: AuthService,
    private messageService: MessageService,
  ) { }

  get isAdmin(): boolean {
    return this.authService.isAdmin();
  }

  displayName(user: UserLookup | null | undefined): string {
    if (!user) {
      return '';
    }
    return user.display_name ? `${user.display_name} (${user.name})` : user.name;
  }

  async onShow(): Promise<void> {
    this.newUser = null;
    this.newOwner = null;
    this.newCanExecute = false;
    this.newCanEdit = false;
    await this.load();
  }

  close(): void {
    this.visible = false;
    this.visibleChange.emit(false);
  }

  async load(): Promise<void> {
    this.loading = true;
    try {
      this.access = await this.packageAccessService.getAccessAsync(this.packageName);
    } catch (error) {
      this.showError('Could not load access rights', error);
    } finally {
      this.loading = false;
    }
  }

  async searchUsers(event: AutoCompleteCompleteEvent): Promise<void> {
    try {
      const users = await this.userService.lookupUsersAsync(event.query);
      const excluded = new Set([
        this.access?.owner?.id,
        ...(this.access?.shares ?? []).map(s => s.user.id),
      ]);
      this.suggestions = users.filter(u => !excluded.has(u.id));
    } catch {
      this.suggestions = [];
    }
  }

  async searchOwners(event: AutoCompleteCompleteEvent): Promise<void> {
    try {
      const users = await this.userService.lookupUsersAsync(event.query);
      this.suggestions = users.filter(u => u.id !== this.access?.owner?.id);
    } catch {
      this.suggestions = [];
    }
  }

  async addShare(): Promise<void> {
    if (!this.newUser?.id) {
      return;
    }
    await this.save(async () => {
      await this.packageAccessService.shareAsync(this.packageName, this.newUser!.id, this.newCanExecute, this.newCanEdit);
      this.messageService.add({
        severity: 'success', summary: 'Shared',
        detail: `${this.packageName} shared with ${this.displayName(this.newUser)}`, life: 3000,
      });
      this.newUser = null;
      this.newCanExecute = false;
      this.newCanEdit = false;
    });
  }

  async updateShare(share: PackageShare): Promise<void> {
    await this.save(() =>
      this.packageAccessService.shareAsync(this.packageName, share.user.id, share.can_execute, share.can_edit));
  }

  async removeShare(share: PackageShare): Promise<void> {
    await this.save(() => this.packageAccessService.unshareAsync(this.packageName, share.user.id));
  }

  async transferOwner(): Promise<void> {
    if (!this.newOwner?.id) {
      return;
    }
    await this.save(async () => {
      await this.packageAccessService.setOwnerAsync(this.packageName, this.newOwner!.id);
      this.messageService.add({
        severity: 'success', summary: 'Owner changed',
        detail: `${this.displayName(this.newOwner)} now owns ${this.packageName}`, life: 3000,
      });
      this.newOwner = null;
    });
  }

  private async save(action: () => Promise<void>): Promise<void> {
    this.saving = true;
    try {
      await action();
      this.changed.emit();
      await this.load();
      // Owners who transferred their package can no longer manage it.
      if (this.access && !this.access.permissions.manage) {
        this.close();
      }
    } catch (error) {
      this.showError('Could not save access rights', error);
      await this.load();
    } finally {
      this.saving = false;
    }
  }

  private showError(summary: string, error: any): void {
    this.messageService.add({
      severity: 'error', summary, detail: error?.error?.detail ?? 'Unknown error', life: 5000,
    });
  }
}
