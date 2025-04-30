import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, signal } from '@angular/core';
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
import { interval, Subscription, takeWhile } from 'rxjs';
import { environment } from '../../../environments/environment';
import { VisualStudioCodeComponent } from "../../icons/svg-VisualStudioCode.component";
import { TaskStatus } from '../../misc/TaskStatus';
import { PackageInstance } from '../../models/Package';
import { TaskInfo } from '../../models/TaskInfo';
import { DurationPipe } from "../../pipes/duration.pipe";
import { TaskCountByStatePipe } from "../../pipes/task-count-by-state.pipe";
import { TaskStatusToSeverityPipe } from "../../pipes/task-status.pipe";
import { UtcToLocalPipe } from "../../pipes/utcToLocal.pipe";
import { ExecutionService } from '../../services/execution.service';
import { PackageService } from '../../services/package.service';
import { TaskService } from '../../services/task.service';
import { PodTerminalComponent } from '../pod-terminal/pod-terminal.component';

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
  ],
  templateUrl: './package-instance.component.html',
  styleUrl: './package-instance.component.scss'
})
export class PackageInstanceComponent implements OnInit, OnDestroy {
  packageInstance: PackageInstance = {
    name: '',
    description: '',
    tasks: []
  };

  selectedTask: TaskInfo | undefined;
  packageName: string = '';
  packageVersion: string = '';
  loading: boolean = true;
  TaskStatus = TaskStatus;
  PrimeIcons = PrimeIcons;
  taskLogs: string[] = [];
  selectedLogTaskId: string | null = null;

  showArgumentsDialog = false;
  predefinedArgs: Record<string, unknown> = {};
  customArgs: { name: string; value: string }[] = [];
  isPackageRunning = false;

  taskPollingSubscription?: Subscription;
  isAlive = true;

  showTerminal = false;
  selectedTaskId: string | null = null;
  isVsCodeBusy = signal(false);

  constructor(
    private packageService: PackageService,
    private executionService: ExecutionService,
    private route: ActivatedRoute,
    private messageService: MessageService,
    private taskService: TaskService
  ) { }

  async ngOnInit(): Promise<void> {
    this.packageName = this.route.snapshot.params['package_name'];
    this.packageVersion = this.route.snapshot.params['package_version'];
    await this.loadPackageInstanceAsync();
    this.startTaskPolling();
  }


  ngOnDestroy(): void {
    this.isAlive = false;
    if (this.taskPollingSubscription) {
      this.taskPollingSubscription.unsubscribe();
    }
  }

  private startTaskPolling(): void {
    this.taskPollingSubscription = interval(5000)
      .pipe(takeWhile(() => this.isAlive))
      .subscribe(() => {
        this.loadPackageInstanceAsync();
      });
  }

  async loadPackageInstanceAsync(): Promise<void> {
    const stage = localStorage.getItem('stage') || 'dev';
    this.packageInstance = await this.packageService.getPackageInstanceAsync(stage, this.packageName, this.packageVersion);
  }

  async onTaskSelect(task: TaskInfo): Promise<void> {
    this.selectedTask = task;
    await this.loadTaskLogsAsync(task.task_id);
  }

  async loadTaskLogsAsync(id: string | null): Promise<void> {
    if (!id) return;
    this.selectedLogTaskId = id;
    const response = await this.taskService.getTaskLogsAsync(id);
    this.taskLogs = response.logs;
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
        await this.loadTaskLogsAsync(response.task_id);
      } else {
        this.showSuccess('Package execution started');
      }

      await this.loadPackageInstanceAsync();
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
}
