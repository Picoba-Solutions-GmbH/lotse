import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, signal, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { EditorComponent } from 'ngx-monaco-editor-v2';
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
import { VisualStudioCodeComponent } from "../../../icons/svg-VisualStudioCode.component";
import { TaskStatus } from '../../../misc/TaskStatus';
import { PackageFile, PackageInstance, PackageModifications } from '../../../models/Package';
import { PackagePermissions } from '../../../models/PackageAccess';

const NO_PERMISSIONS: PackagePermissions = { view: false, execute: false, edit: false, manage: false };
import { looksSensitive, PackageEnvironment } from '../../../models/PackageEnvironment';
import { TaskInfo } from '../../../models/TaskInfo';
import { DurationPipe } from "../../../pipes/duration.pipe";
import { FileSizePipe } from "../../../pipes/file-size.pipe";
import { TaskCountByStatePipe } from "../../../pipes/task-count-by-state.pipe";
import { TaskStatusToSeverityPipe } from "../../../pipes/task-status.pipe";
import { UtcToLocalPipe } from "../../../pipes/utcToLocal.pipe";
import { ExecutionService } from '../../../services/execution.service';
import { FeatureFlagService } from '../../../services/feature-flag.service';
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
    EditorComponent,
    FileSizePipe
  ],
  templateUrl: './package-instance.component.html',
  styleUrl: './package-instance.component.scss'
})
export class PackageInstanceComponent implements OnInit, OnDestroy {
  TaskStatus = TaskStatus;
  PrimeIcons = PrimeIcons;
  get permissions(): PackagePermissions {
    return this.packageInstance.permissions ?? NO_PERMISSIONS;
  }

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

  showLogsExpandedDialog = false;

  showTerminal = false;
  selectedTaskId: string | null = null;
  isVsCodeBusy = signal(false);
  packageEnvironmentVariablesLoading = signal(false);
  isAuthenticationEnabled: boolean = false;

  showEnvironmentDialog = false;
  packageEnvironmentVariables: PackageEnvironment[] = [];
  private secretToggledManually = new WeakSet<PackageEnvironment>();
  isSavingEnvironment = false;

  showArgumentsEditDialog = false;
  argumentsDraft: { name: string; default: string; options: string }[] = [];
  isArgumentsLoading = false;
  isSavingArguments = false;

  showFilesDialog = false;
  packageFiles: PackageFile[] = [];
  isFilesLoading = false;
  selectedFile: PackageFile | null = null;
  fileContent = '';
  private originalFileContent = '';
  isFileContentLoading = false;
  isSavingFile = false;
  fileEditorOptions: Record<string, unknown> = {
    language: 'plaintext',
    theme: 'vs-dark',
    automaticLayout: true,
    fontSize: 13,
    fontFamily: "'Cascadia Code', 'Fira Code', Consolas, monospace",
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
  };

  isReverting = false;
  isRevertingFile = false;

  get modifications(): PackageModifications | undefined {
    return this.packageInstance.modifications;
  }

  get canEditFiles(): boolean {
    return this.permissions.edit && !!this.packageInstance.has_files;
  }

  get isFileDirty(): boolean {
    return this.selectedFile !== null && this.fileContent !== this.originalFileContent;
  }

  @ViewChild(PodTerminalComponent) podTerminal: PodTerminalComponent | undefined;

  private wsSubscriptionForTasks: Subscription | null = null;
  private wsSubscriptionForTaskLogs: Subscription | null = null;

  constructor(
    private packageService: PackageService,
    private executionService: ExecutionService,
    private route: ActivatedRoute,
    private messageService: MessageService,
    private taskService: TaskService,
    private webSocketService: WebSocketService,
    private featureFlagService: FeatureFlagService
  ) { }

  async ngOnInit(): Promise<void> {
    this.packageName = this.route.snapshot.params['package_name'];
    this.packageVersion = this.route.snapshot.params['package_version'];
    this.setupWebSocketForTasks();
    await this.loadPackageInstanceAsync();
    this.isAuthenticationEnabled = await this.featureFlagService.isAuthenticationEnabled();
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
    this.packageInstance = await this.packageService.getPackageInstanceAsync(this.packageName, this.packageVersion);
  }

  private async setupWebSocketForTasks(): Promise<void> {
    if (this.wsSubscriptionForTasks) {
      this.wsSubscriptionForTasks.unsubscribe();
    }

    this.wsSubscriptionForTasks = this.webSocketService.connectToTasks(this.packageName, this.packageVersion).subscribe({
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
      this.packageInstance = await this.packageService.getPackageInstanceAsync(this.packageName, this.packageVersion);
    } catch (error) {
      this.showError('Failed to cancel task');
    }
  }

  openUIApp(taskId: string): void {
    const url = `${environment.url}/proxy/${taskId}`;
    window.open(url, '_blank');
  }

  copyEndpointUrl(): void {
    const url = `${environment.url}/execute/${this.packageName}/${this.packageVersion}`;
    navigator.clipboard.writeText(url).then(() => {
      this.showSuccess('Endpoint URL copied to clipboard');
    });
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

  onReplayTask(task: TaskInfo): void {
    const predefinedNames = new Set(this.packageInstance.package_arguments?.map(arg => arg.name) ?? []);
    this.predefinedArgs = {};
    this.customArgs = [];

    for (const arg of task.arguments ?? []) {
      if (predefinedNames.has(arg.name)) {
        this.predefinedArgs[arg.name] = arg.value;
      } else {
        this.customArgs.push({ name: arg.name, value: arg.value });
      }
    }

    this.showArgumentsDialog = true;
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

    const request = {
      package_name: this.packageName,
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

  onStartInstanceDialogKeydown(event: Event): void {
    const target = event.target as HTMLElement;
    if (target.tagName === 'BUTTON') return;
    this.executePackageAsync(false);
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

  private applyModifications(modifications: PackageModifications): void {
    this.packageInstance = { ...this.packageInstance, modifications };
  }

  private showHttpError(error: unknown, fallback: string): void {
    const detail = (error as { error?: { detail?: unknown } })?.error?.detail;
    this.showError(typeof detail === 'string' ? detail : fallback);
  }

  // ---------------------------------------------------------------- environment variables

  addEnvironmentVariable(): void {
    this.packageEnvironmentVariables = [...this.packageEnvironmentVariables, { name: '', value: '', secret: false }];
  }

  removeEnvironmentVariable(index: number): void {
    this.packageEnvironmentVariables = this.packageEnvironmentVariables.filter((_, i) => i !== index);
  }

  /** A secret whose value is stored on the server and was not replaced in the dialog. */
  hasStoredSecret(env: PackageEnvironment): boolean {
    return !!env.previous_name && !!env.has_value && (env.value === null || env.value === '');
  }

  onEnvironmentNameChange(env: PackageEnvironment): void {
    // new variables are hidden automatically when their name looks like a key, password, token...
    if (!env.previous_name && !this.secretToggledManually.has(env)) {
      env.secret = looksSensitive(env.name);
    }
  }

  toggleEnvironmentSecret(env: PackageEnvironment): void {
    this.secretToggledManually.add(env);
    if (env.secret && this.hasStoredSecret(env)) {
      // the stored value is never revealed, making it visible requires a new value
      if (!confirm(`Make '${env.name}' visible? Its stored value is cleared and you have to enter a new one.`)) {
        return;
      }
      env.value = '';
      env.has_value = false;
    }
    env.secret = !env.secret;
  }

  async saveEnvironmentVariablesAsync(): Promise<void> {
    const variables: PackageEnvironment[] = this.packageEnvironmentVariables
      .map(env => ({
        name: env.name.trim(),
        // an empty input on a stored secret keeps its value
        value: this.hasStoredSecret(env) && env.secret ? null : (env.value ?? ''),
        secret: !!env.secret,
        previous_name: env.previous_name ?? null,
      }))
      .filter(env => env.name);

    try {
      this.isSavingEnvironment = true;
      const modifications = await this.packageService.updatePackageEnvironmentAsync(this.packageName, this.packageVersion, variables);
      this.applyModifications(modifications);
      this.showEnvironmentDialog = false;
      this.showSuccess('Environment variables saved. They apply to new instances.');
    } catch (error) {
      this.showHttpError(error, 'Failed to save environment variables');
    } finally {
      this.isSavingEnvironment = false;
    }
  }

  // ---------------------------------------------------------------- arguments

  async openArgumentsEditor(): Promise<void> {
    try {
      this.isArgumentsLoading = true;
      const args = await this.packageService.getPackageArgumentsAsync(this.packageName, this.packageVersion);
      this.argumentsDraft = args.map(arg => ({
        name: arg.name,
        default: arg.default ?? '',
        options: (arg.options ?? []).join(', '),
      }));
      this.showArgumentsEditDialog = true;
    } catch (error) {
      this.showHttpError(error, 'Failed to load arguments');
    } finally {
      this.isArgumentsLoading = false;
    }
  }

  addArgumentDefinition(): void {
    this.argumentsDraft = [...this.argumentsDraft, { name: '', default: '', options: '' }];
  }

  removeArgumentDefinition(index: number): void {
    this.argumentsDraft = this.argumentsDraft.filter((_, i) => i !== index);
  }

  async saveArgumentsAsync(): Promise<void> {
    const args = this.argumentsDraft
      .filter(arg => arg.name.trim())
      .map(arg => {
        const options = arg.options.split(',').map(o => o.trim()).filter(o => o);
        return { name: arg.name.trim(), default: arg.default ?? '', options: options.length ? options : null };
      });

    try {
      this.isSavingArguments = true;
      const modifications = await this.packageService.updatePackageArgumentsAsync(this.packageName, this.packageVersion, args);
      this.applyModifications(modifications);
      this.packageInstance = { ...this.packageInstance, package_arguments: args };
      this.showArgumentsEditDialog = false;
      this.showSuccess('Arguments saved');
    } catch (error) {
      this.showHttpError(error, 'Failed to save arguments');
    } finally {
      this.isSavingArguments = false;
    }
  }

  async revertAllAsync(): Promise<void> {
    if (!confirm('Restore this deployment as it was deployed? Edited environment variables, arguments and files will be lost.')) {
      return;
    }

    try {
      this.isReverting = true;
      await this.packageService.revertPackageAsync(this.packageName, this.packageVersion);
      this.showSuccess('Deployment restored to its original state');
    } catch (error) {
      this.showHttpError(error, 'Failed to restore deployment');
    } finally {
      // reload in any case, a partial restore changes the state too
      await this.loadPackageInstanceAsync();
      this.isReverting = false;
    }
  }

  // ---------------------------------------------------------------- files

  async openFilesEditor(path?: string): Promise<void> {
    this.selectedFile = null;
    this.fileContent = '';
    this.originalFileContent = '';
    const isDark = document.documentElement.classList.contains('dark');
    this.fileEditorOptions = { ...this.fileEditorOptions, theme: isDark ? 'vs-dark' : 'vs' };
    this.showFilesDialog = true;

    try {
      this.isFilesLoading = true;
      this.packageFiles = await this.packageService.getPackageFilesAsync(this.packageName, this.packageVersion);
    } catch (error) {
      this.showHttpError(error, 'Failed to load package files');
      return;
    } finally {
      this.isFilesLoading = false;
    }

    const initial = this.packageFiles.find(f => f.path === path && f.editable)
      ?? this.packageFiles.find(f => f.path === 'requirements.txt' && f.editable)
      ?? this.packageFiles.find(f => f.editable);
    if (initial) {
      await this.selectFileAsync(initial);
    }
  }

  async selectFileAsync(file: PackageFile): Promise<void> {
    if (!file.editable || file.path === this.selectedFile?.path) return;
    if (this.isFileDirty && !confirm(`Discard unsaved changes of ${this.selectedFile?.path}?`)) return;

    try {
      this.isFileContentLoading = true;
      const result = await this.packageService.getPackageFileContentAsync(this.packageName, this.packageVersion, file.path);
      this.selectedFile = file;
      this.fileContent = result.content;
      this.originalFileContent = result.content;
      this.fileEditorOptions = { ...this.fileEditorOptions, language: this.languageOf(file.path) };
    } catch (error) {
      this.showHttpError(error, `Failed to load ${file.path}`);
    } finally {
      this.isFileContentLoading = false;
    }
  }

  async saveFileAsync(): Promise<void> {
    if (!this.selectedFile || !this.isFileDirty) return;

    const file = this.selectedFile;
    const content = this.fileContent;
    try {
      this.isSavingFile = true;
      const modifications = await this.packageService.updatePackageFileContentAsync(
        this.packageName, this.packageVersion, { path: file.path, content });
      this.applyModifications(modifications);
      if (this.selectedFile === file) {
        this.originalFileContent = content;
      }
      file.modified = modifications.modified_files.includes(file.path);
      this.showSuccess(file.path === 'requirements.txt'
        ? 'requirements.txt saved. Dependencies are reinstalled on the next start.'
        : `${file.path} saved. Changes apply to new instances.`);
    } catch (error) {
      this.showHttpError(error, `Failed to save ${file.path}`);
    } finally {
      this.isSavingFile = false;
    }
  }

  async revertSelectedFileAsync(): Promise<void> {
    const file = this.selectedFile;
    if (!file?.modified) return;
    if (!confirm(`Restore ${file.path} as it was deployed? Your changes to this file will be lost.`)) return;

    try {
      this.isRevertingFile = true;
      const modifications = await this.packageService.revertPackageFileAsync(this.packageName, this.packageVersion, file.path);
      this.applyModifications(modifications);
      file.modified = false;
      const result = await this.packageService.getPackageFileContentAsync(this.packageName, this.packageVersion, file.path);
      if (this.selectedFile === file) {
        this.fileContent = result.content;
        this.originalFileContent = result.content;
      }
      this.showSuccess(`${file.path} restored`);
    } catch (error) {
      this.showHttpError(error, `Failed to restore ${file.path}`);
    } finally {
      this.isRevertingFile = false;
    }
  }

  onFilesDialogHide(): void {
    if (this.isFileDirty && confirm(`Save changes of ${this.selectedFile?.path} before closing?`)) {
      this.saveFileAsync();
    }
  }

  onFileEditorKeydown(event: KeyboardEvent): void {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault();
      this.saveFileAsync();
    }
  }

  private languageOf(path: string): string {
    const extension = path.split('.').pop()?.toLowerCase() ?? '';
    const languages: Record<string, string> = {
      py: 'python', json: 'json', yaml: 'yaml', yml: 'yaml', md: 'markdown', sh: 'shell',
      sql: 'sql', xml: 'xml', html: 'html', css: 'css', js: 'javascript', ini: 'ini', cfg: 'ini',
      conf: 'ini', toml: 'ini', properties: 'ini',
    };
    return languages[extension] ?? 'plaintext';
  }

  async showEnvironmentVariables(): Promise<void> {
    try {
      this.packageEnvironmentVariablesLoading.set(true);
      const variables = await this.packageService.getPackageEnvironmentAsync(this.packageName, this.packageVersion);
      this.packageEnvironmentVariables = variables.map(env => ({ ...env, previous_name: env.name }));
      this.secretToggledManually = new WeakSet();
      this.showEnvironmentDialog = true;
    } catch (error) {
      this.showError('Failed to load environment variables');
    } finally {
      this.packageEnvironmentVariablesLoading.set(false);
    }
  }
}
