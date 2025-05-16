import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { CheckboxModule } from 'primeng/checkbox';
import { DropdownModule } from 'primeng/dropdown';
import { InputTextModule } from 'primeng/inputtext';
import { ScrollPanelModule } from 'primeng/scrollpanel';
import { SelectButtonModule } from 'primeng/selectbutton';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { interval, Subscription, takeWhile } from 'rxjs';
import { environment } from '../../../environments/environment';
import { PackageRequest } from '../../models/PackageRequest';
import { PackageRequestArguments } from '../../models/PackageRequestArguments';
import { RepositoryConfig } from '../../models/RepositoryConfig';
import { TaskInfo } from '../../models/TaskInfo';
import { TaskStatusToSeverityPipe } from '../../pipes/task-status.pipe';
import { AuthService } from '../../services/auth.service';
import { ExecutionService } from '../../services/execution.service';
import { PackageService } from '../../services/package.service';
import { TaskService } from '../../services/task.service';

interface CustomArgument {
  name: string;
  value: string;
}

enum Stage {
  dev = "dev",
  prod = "prod",
}

@Component({
  selector: 'app-package-execution',
  templateUrl: './package-execution.component.html',
  styleUrl: './package-execution.component.scss',
  imports: [
    CommonModule,
    FormsModule,
    InputTextModule,
    SelectButtonModule,
    DropdownModule,
    ButtonModule,
    CheckboxModule,
    TableModule,
    TagModule,
    TaskStatusToSeverityPipe,
    ScrollPanelModule,
    CardModule
  ]
})
export class PackageExecutionComponent implements OnInit, OnDestroy {
  repositories: RepositoryConfig[] = [];
  selectedPackage: RepositoryConfig | null = null;
  predefinedArgs: Record<string, unknown> = {};
  customArgs: CustomArgument[] = [];
  waitForCompletion = true;
  tasks: TaskInfo[] = [];
  selectedLogTaskId: string | null = null;
  taskLogs: string[] = [];
  isPackageRunning = signal(false);

  taskPollingSubscription?: Subscription;
  isAlive = true;
  isAuthenticationEnabled: boolean = false;

  constructor(
    private executionService: ExecutionService,
    private packageService: PackageService,
    private messageService: MessageService,
    private taskService: TaskService,
    private authService: AuthService
  ) { }

  async ngOnInit(): Promise<void> {
    await Promise.all([this.loadPackagesAsync(), this.loadTasksAsync()]);
    this.startTaskPolling();
    this.isAuthenticationEnabled = await this.authService.isAuthenticationEnabledAsync();
  }

  ngOnDestroy(): void {
    this.isAlive = false;
    if (this.taskPollingSubscription) {
      this.taskPollingSubscription.unsubscribe();
    }
  }

  private startTaskPolling(): void {
    this.taskPollingSubscription = interval(60000)
      .pipe(takeWhile(() => this.isAlive))
      .subscribe(() => {
        this.loadTasksAsync();
      });
  }

  async loadPackagesAsync(): Promise<void> {
    try {
      this.repositories = await this.packageService.getPackagesAsync();
    } catch (error) {
      this.showError('Failed to load packages');
    }
  }

  async loadTasksAsync(): Promise<void> {
    try {
      const stage = localStorage.getItem('stage') || 'dev';
      this.tasks = await this.taskService.getTasksAsync(stage);
    } catch (error) {
      this.showError('Failed to load tasks');
    }
  }

  addCustomArgument(): void {
    this.customArgs.push({ name: '', value: '' });
  }

  removeCustomArgument(index: number): void {
    this.customArgs.splice(index, 1);
  }

  async executePackageAsync(): Promise<void> {
    if (!this.selectedPackage) {
      this.showError('Please select a packages');
      return;
    }

    const missingRequired = this.selectedPackage?.package_arguments
      ?.filter((arg) => this.predefinedArgs[arg.name] === undefined)
      ?.map((arg) => arg.name);

    if (missingRequired?.length) {
      this.showError(`Missing required arguments: ${missingRequired.join(', ')}`);
      return;
    }

    const args: PackageRequestArguments[] = [];
    if (this.selectedPackage?.package_arguments) {
      for (const arg of this.selectedPackage.package_arguments) {
        const value = this.predefinedArgs[arg.name];
        if (value) {
          args.push({ name: arg.name, value: value.toString() });
        }
      }
    }

    for (const arg of this.customArgs) {
      args.push({ name: arg.name, value: arg.value });
    }

    const stage = localStorage.getItem('stage') || 'dev';
    const request: PackageRequest = {
      package_name: this.selectedPackage.package_name,
      stage: stage,
      arguments: args,
      wait_for_completion: this.waitForCompletion,
    };

    try {
      if (this.waitForCompletion) {
        this.isPackageRunning.set(true);
      }

      const response = await this.executionService.executePackageAsync(request);
      if ('output' in response) {
        this.showSuccess(`Package executed successfully: ${response.output}`);
        await this.loadTaskLogsAsync(response.task_id);
      } else {
        this.showSuccess('Package execution started');
      }
      await this.loadTasksAsync();
    } catch (error) {
      this.showError('Failed to execute package');
      await this.loadTasksAsync();
    } finally {
      this.isPackageRunning.set(false);
    }
  }

  async cancelTaskAsync(taskId: string): Promise<void> {
    try {
      await this.taskService.cancelTaskAsync(taskId);
      this.showSuccess('Task cancelled');
      await this.loadTasksAsync();
    } catch (error) {
      this.showError('Failed to cancel task');
    }
  }

  async loadTaskLogsAsync(id: string | null): Promise<void> {
    if (!id) return;
    this.selectedLogTaskId = id;
    try {
      const response = await this.taskService.getTaskLogsAsync(id);
      this.taskLogs = response.logs;
    } catch (error) {
      this.showError('Failed to load task logs');
    }
  }

  openUIApp(taskId: string): void {
    const url = `${environment.url}/proxy/${taskId}`;
    window.open(url, '_blank');
  }

  showSuccess(message: string): void {
    this.messageService.add({
      severity: 'success',
      summary: 'Success',
      detail: message,
    });
  }

  showError(message: string): void {
    this.messageService.add({
      severity: 'error',
      summary: 'Error',
      detail: message,
    });
  }
}
