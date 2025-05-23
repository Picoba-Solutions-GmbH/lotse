import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, signal, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { AccordionModule } from 'primeng/accordion';
import { MessageService, PrimeIcons } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { CheckboxModule } from 'primeng/checkbox';
import { DialogModule } from 'primeng/dialog';
import { DropdownModule } from 'primeng/dropdown';
import { InputTextModule } from 'primeng/inputtext';
import { ScrollPanelModule } from 'primeng/scrollpanel';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { Subscription } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { HasRoleDirective } from '../../../directives/has-role.directive';
import { VisualStudioCodeComponent } from "../../../icons/svg-VisualStudioCode.component";
import { Role } from '../../../misc/Role';
import { TaskStatus } from '../../../misc/TaskStatus';
import { PackageInstance } from '../../../models/Package';
import { PackageEnvironment } from '../../../models/PackageEnvironment';
import { TaskInfo } from '../../../models/TaskInfo';
import { DurationPipe } from "../../../pipes/duration.pipe";
import { TaskCountByStatePipe } from "../../../pipes/task-count-by-state.pipe";
import { TaskStatusToSeverityPipe } from "../../../pipes/task-status.pipe";
import { UtcToLocalPipe } from "../../../pipes/utcToLocal.pipe";
import { AuthService } from '../../../services/auth.service';
import { ExecutionService } from '../../../services/execution.service';
import { PackageService } from '../../../services/package.service';
import { TaskService } from '../../../services/task.service';
import { WebSocketService } from '../../../services/websocket.service';
import { PodTerminalComponent } from '../../pod-terminal/pod-terminal.component';

@Component({
  selector: 'app-package-instance',
  imports: [
    CommonModule,
    FormsModule,
    TableModule,
    CardModule,
    TagModule,
    ButtonModule,
    InputTextModule,
    TooltipModule,
    DropdownModule,
    DialogModule,
    ToastModule,
    TaskCountByStatePipe,
    TaskStatusToSeverityPipe,
    ScrollPanelModule,
    CheckboxModule,
    DurationPipe,
    PodTerminalComponent,
    VisualStudioCodeComponent,
    UtcToLocalPipe,
    AccordionModule,
    HasRoleDirective
  ],
  templateUrl: './package-instance.component.html',
  styleUrl: './package-instance.component.scss'
})
export class PackageInstanceComponent implements OnInit, OnDestroy {
  TaskStatus = TaskStatus;
  PrimeIcons = PrimeIcons;
  Role = Role;

  packageInstance: PackageInstance = {
    name: '',
    description: '',
    tasks: [],
    is_default: false,
  };

  selectedTask: TaskInfo | undefined;
  packageName: string = '';
  packageVersion: string = '';
  loading: boolean = true;
  taskLogs: string[] = [];
  selectedLogTaskId: string | null = null;

  showArgumentsDialog = false;
  predefinedArgs: Record<string, unknown> = {};
  customArgs: { name: string; value: string }[] = [];
  isPackageRunning = false;

  showTerminal = false;
  selectedTaskId: string | null = null;
  isVsCodeBusy = signal(false);
  isAuthenticationEnabled: boolean = false;

  showEnvironmentDialog = false;
  packageEnvironmentVariables: PackageEnvironment[] = [];

  @ViewChild(PodTerminalComponent) podTerminal: PodTerminalComponent | undefined;

  private wsSubscriptionForTasks: Subscription | null = null;
  private wsSubscriptionForTaskLogs: Subscription | null = null;

  constructor(
    private packageService: PackageService,
    private executionService: ExecutionService,
    private route: ActivatedRoute,
    private messageService: MessageService,
    private taskService: TaskService,
    private authService: AuthService,
    private webSocketService: WebSocketService
  ) { }

  async ngOnInit(): Promise<void> {
    this.packageName = this.route.snapshot.params['package_name'];
    this.packageVersion = this.route.snapshot.params['package_version'];
    this.setupWebSocketForTasks();
    await this.loadPackageInstanceAsync();
    this.isAuthenticationEnabled = await this.authService.isAuthenticationEnabledAsync();
  }

  ngOnDestroy(): void {
    if (this.wsSubscriptionForTaskLogs) {
      this.wsSubscriptionForTaskLogs.unsubscribe();
    }

    if (this.wsSubscriptionForTasks) {
      this.wsSubscriptionForTasks.unsubscribe();
    }

    this.webSocketService.closeTasksConnection();
    this.webSocketService.closeTaskLogsConnection();
  }

  async loadPackageInstanceAsync(): Promise<void> {
    const stage = localStorage.getItem('stage') || 'dev';
    this.packageInstance = await this.packageService.getPackageInstanceAsync(stage, this.packageName, this.packageVersion);
  }

  private async setupWebSocketForTasks(): Promise<void> {
    if (this.wsSubscriptionForTasks) {
      this.wsSubscriptionForTasks.unsubscribe();
    }

    const stage = localStorage.getItem('stage') || 'dev';
    this.wsSubscriptionForTasks = this.webSocketService.connectToTasks(this.packageName, stage, this.packageVersion).subscribe({
      next: (data: { tasks: TaskInfo[] }) => {
        if (data.tasks) {
          for (const task of data.tasks) {
            const existingTask = this.packageInstance.tasks.find(t => t.task_id === task.task_id);
            if (existingTask) {
              task.duration = new DurationPipe().transform(task.started_at, task.finished_at);
              Object.assign(existingTask, task);
            } else {
              this.packageInstance.tasks.push(task);
            }
          }
        }
      },
      error: (error: Error) => {
        console.error('WebSocket error:', error);
        this.messageService.add({ severity: 'error', summary: 'Connection Error', detail: 'Lost connection to server. Retrying...' });
      }
    });
  }

  private async setupWebSocketForTaskLogs(taskId: string): Promise<void> {
    this.taskLogs = [];
    if (this.selectedTask) {
      this.wsSubscriptionForTaskLogs = this.webSocketService.connectToTaskLogs(taskId).subscribe({
        next: (data: { logs: string[] }) => {
          if (data.logs && this.taskLogs.length !== data.logs.length) {
            this.taskLogs = data.logs;
          }
        },
        error: (error: Error) => {
          console.error('WebSocket error:', error);
          this.messageService.add({ severity: 'error', summary: 'Connection Error', detail: 'Lost connection to server. Retrying...' });
        }
      });
    }
  }

  async onTaskSelect(task: TaskInfo): Promise<void> {
    if (this.wsSubscriptionForTaskLogs) {
      this.wsSubscriptionForTaskLogs.unsubscribe();
      this.webSocketService.closeTaskLogsConnection();
    }

    this.selectedTask = task;
    this.selectedLogTaskId = task.task_id;
    this.taskLogs = [];

    if (task.status === TaskStatus.RUNNING || task.status === TaskStatus.INITIALIZING) {
      await this.setupWebSocketForTaskLogs(task.task_id);
    } else {
      const taskLogs = await this.taskService.getTaskLogsAsync(task.task_id);
      this.taskLogs = taskLogs.logs;
    }
  }

  async cancelTaskAsync(taskId: string): Promise<void> {
    try {
      await this.taskService.cancelTaskAsync(taskId);
      this.showSuccess('Task cancelled');
      const stage = localStorage.getItem('stage') || 'dev';
      this.packageInstance = await this.packageService.getPackageInstanceAsync(stage, this.packageName, this.packageVersion);
    } catch (error) {
      this.showError('Failed to cancel task');
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

  onStartNewInstance(): void {
    if (this.packageInstance.package_arguments?.length) {
      this.predefinedArgs = {};
      this.customArgs = [];
      this.showArgumentsDialog = true;
    } else {
      this.executePackageAsync(false);
    }
  }

  onStartEmptyInstance(): void {
    this.executePackageAsync(true);
  }

  addCustomArgument(): void {
    this.customArgs.push({ name: '', value: '' });
  }

  removeCustomArgument(index: number): void {
    this.customArgs.splice(index, 1);
  }

  async executePackageAsync(startAsEmptyInstance: boolean): Promise<void> {
    if (this.isPackageRunning) return;

    const args = [];
    if (!startAsEmptyInstance) {
      for (const [name, value] of Object.entries(this.predefinedArgs)) {
        if (value !== undefined && value !== null) {
          args.push({ name, value: value.toString() });
        }
      }

      for (const arg of this.customArgs) {
        if (arg.name && arg.value) {
          args.push({ name: arg.name, value: arg.value });
        }
      }
    }

    const stage = localStorage.getItem('stage') || 'dev';
    const request = {
      package_name: this.packageName,
      stage: stage,
      version: this.packageVersion,
      arguments: args,
      wait_for_completion: false,
    };

    try {
      this.isPackageRunning = true;
      const response = startAsEmptyInstance
        ? await this.executionService.startEmptyInstanceAsync(request)
        : await this.executionService.executePackageAsync(request);


      if ('output' in response) {
        this.showSuccess(`Package executed successfully: ${response.output}`);
      } else {
        this.showSuccess('Package execution started');
      }

      await this.loadPackageInstanceAsync();
      if (this.packageInstance.tasks.length > 0) {
        const latestTask = this.packageInstance.tasks.find(x => x.task_id === response.task_id);
        if (latestTask) {
          await this.onTaskSelect(latestTask);
        }
      }

      this.showArgumentsDialog = false;
    } catch (error) {
      this.showError('Failed to execute package');
    } finally {
      this.isPackageRunning = false;
    }
  }

  openTerminal(taskId: string): void {
    this.selectedTaskId = taskId;
    this.showTerminal = true;
  }

  handleSocketClosed() {
    this.showTerminal = false;
  }

  async openVSCode(taskId: string) {
    if (this.isVsCodeBusy()) {
      this.showError('VS Code is busy. Please wait for the current session to finish.');
      return;
    }

    this.isVsCodeBusy.set(true);
    await this.taskService.postRunVsCodeServerAsync(taskId)
    this.isVsCodeBusy.set(false);
    const url = `${environment.url}/vscode/${taskId}/?folder=/app`;
    window.open(url, '_blank');
  }

  handleTerminalResize(): void {
    setTimeout(() => {
      if (this.podTerminal) {
        this.podTerminal.handleFit();
      }
    }, 100);
  }

  async showEnvironmentVariables(): Promise<void> {
    try {
      const stage = localStorage.getItem('stage') || 'dev';
      this.packageEnvironmentVariables = await this.packageService.getPackageEnvironmentAsync(stage, this.packageName, this.packageVersion);
      this.showEnvironmentDialog = true;
    } catch (error) {
      this.showError('Failed to load environment variables');
    }
  }
}
