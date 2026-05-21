import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { EditorComponent } from 'ngx-monaco-editor-v2';
import { MessageService, PrimeIcons } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { DropdownModule } from 'primeng/dropdown';
import { InputTextModule } from 'primeng/inputtext';
import { SplitButtonModule } from 'primeng/splitbutton';
import { TooltipModule } from 'primeng/tooltip';
import { Subscription } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { AsyncPackageResponse } from '../../../models/AsyncPackageResponse';
import { LiveCodeFile, LivePackage, LivePackageInfo } from '../../../models/LiveCode';
import { PackageRequestArguments } from '../../../models/PackageRequestArguments';
import { LiveCodeService } from '../../../services/live-code.service';
import { TaskService } from '../../../services/task.service';
import { WebSocketService } from '../../../services/websocket.service';

const DEFAULT_MAIN_PY = `def main():
    print("Hello, World!")


if __name__ == "__main__":
    main()
`;


@Component({
  selector: 'app-package-live-code',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ButtonModule,
    SplitButtonModule,
    DropdownModule,
    InputTextModule,
    DialogModule,
    TooltipModule,
    EditorComponent,
  ],
  templateUrl: './package-live-code.component.html',
  styleUrl: './package-live-code.component.scss',
})
export class PackageLiveCodeComponent implements OnInit, OnDestroy {
  PrimeIcons = PrimeIcons;

  packages: LivePackageInfo[] = [];
  packageNameOptions: { label: string; value: string }[] = [];
  selectedPackageName: string | null = null;
  currentPackage: LivePackage | null = null;
  selectedFileName = 'main.py';
  currentFileContent = '';
  isDirty = false;
  isSaving = false;
  isRunning = false;
  taskLogs: string[] = [];
  runHeader: string | null = null;
  runSummary: { text: string; success: boolean } | null = null;
  private wsSubscription: Subscription | null = null;

  showNewPackageDialog = false;
  newPackageName = '';

  renamingFileName: string | null = null;
  renameInput = '';

  showRunDialog = false;
  runArgs: PackageRequestArguments[] = [];

  readonly runMenuItems = [
    {
      label: 'Run with options',
      icon: PrimeIcons.SLIDERS_H,
      command: () => this.openRunWithArgsDialog(),
    },
  ];

  pythonVersions = ['3.9', '3.10', '3.11', '3.12', '3.13'];
  selectedPythonVersion = '3.11';

  editorOptions: Record<string, unknown> = {
    language: 'python',
    theme: 'vs-dark',
    automaticLayout: true,
    fontSize: 13,
    fontFamily: "'Cascadia Code', 'Fira Code', Consolas, monospace",
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    renderLineHighlight: 'line',
    lineNumbers: 'on',
    padding: { top: 12, bottom: 12 },
  };

  private darkModeObserver: MutationObserver | null = null;
  private monacoEditor: unknown = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private completionProviderDisposable: any = null;

  constructor(
    private liveCodeService: LiveCodeService,
    private taskService: TaskService,
    private messageService: MessageService,
    private webSocketService: WebSocketService,
  ) {}

  async ngOnInit(): Promise<void> {
    await this.loadPackageList();
    this.setupDarkModeWatcher();
  }

  copyEndpointUrl(): void {
    if (!this.currentPackage) return;
    const url = `${environment.url}/packages/live/${this.currentPackage.package_name}/run`;
    navigator.clipboard.writeText(url).then(() => {
      this.messageService.add({ severity: 'success', summary: 'Copied', detail: 'Endpoint URL copied to clipboard' });
    });
  }

  ngOnDestroy(): void {
    this.darkModeObserver?.disconnect();
    this.wsSubscription?.unsubscribe();
    this.webSocketService.closeTaskLogsConnection();
    this.completionProviderDisposable?.dispose();
  }

  private setupDarkModeWatcher(): void {
    this.updateEditorTheme();
    this.darkModeObserver = new MutationObserver(() => this.updateEditorTheme());
    this.darkModeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });
  }

  private updateEditorTheme(): void {
    const isDark = document.documentElement.classList.contains('dark');
    this.editorOptions = { ...this.editorOptions, theme: isDark ? 'vs-dark' : 'vs' };
  }

  async loadPackageList(): Promise<void> {
    try {
      this.packages = await this.liveCodeService.getPackagesAsync();
      this.packageNameOptions = this.packages.map(p => ({
        label: p.package_name,
        value: p.package_name,
      }));
    } catch {
      // No live packages yet – that's fine on first use
    }
  }

  async onPackageSelect(packageName: string | null): Promise<void> {
    if (!packageName) {
      this.currentPackage = null;
      return;
    }
    try {
      this.currentPackage = await this.liveCodeService.getPackageAsync(packageName);
      this.selectedPythonVersion = this.currentPackage.python_version || '3.11';
      const first = this.currentPackage.files[0];
      this.selectedFileName = first?.name ?? 'main.py';
      this.currentFileContent = first?.content ?? '';
      this.isDirty = false;
    } catch {
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load package.',
      });
    }
  }

  openNewPackageDialog(): void {
    this.newPackageName = '';
    this.showNewPackageDialog = true;
  }

  createPackage(): void {
    const name = this.newPackageName.trim();
    if (!name) return;
    this.currentPackage = {
      package_name: name,
      python_version: this.selectedPythonVersion,
      files: [{ name: 'main.py', content: DEFAULT_MAIN_PY }],
    };
    this.selectedPackageName = name;
    this.selectedFileName = 'main.py';
    this.currentFileContent = DEFAULT_MAIN_PY;
    this.isDirty = true;
    this.showNewPackageDialog = false;
  }

  selectFile(fileName: string): void {
    this.flushCurrentFileContent();
    this.selectedFileName = fileName;
    this.currentFileContent =
      this.currentPackage?.files.find(f => f.name === fileName)?.content ?? '';
    const lang = this.getLanguageForFile(fileName);
    const win = window as unknown as { monaco?: { editor?: { setModelLanguage: (m: unknown, l: string) => void } } };
    const editor = this.monacoEditor as { getModel?: () => unknown } | null;
    if (win.monaco?.editor && editor?.getModel) {
      win.monaco.editor.setModelLanguage(editor.getModel(), lang);
    } else {
      this.editorOptions = { ...this.editorOptions, language: lang };
    }
  }

  addFile(): void {
    if (!this.currentPackage) return;
    this.flushCurrentFileContent();
    const idx = this.currentPackage.files.length;
    const newFile: LiveCodeFile = { name: `module_${idx}.py`, content: '' };
    this.currentPackage.files.push(newFile);
    this.selectFile(newFile.name);
    this.isDirty = true;
  }

  deleteFile(fileName: string, event: Event): void {
    event.stopPropagation();
    if (!this.currentPackage) return;
    this.currentPackage.files = this.currentPackage.files.filter(f => f.name !== fileName);
    if (this.selectedFileName === fileName) {
      const first = this.currentPackage.files[0];
      if (first) {
        this.selectedFileName = first.name;
        this.currentFileContent = first.content;
      }
    }
    this.isDirty = true;
  }

  onCodeChange(): void {
    if (this.currentPackage) {
      const file = this.currentPackage.files.find(f => f.name === this.selectedFileName);
      if (file) file.content = this.currentFileContent;
    }
    this.isDirty = true;
  }

  onEditorInit(editor: unknown): void {
    this.monacoEditor = editor;
    this.registerMonacoProviders();
  }

  private extractPythonSymbols(content: string): Array<{ name: string; kind: 'function' | 'class' | 'variable'; signature: string }> {
    const symbols: Array<{ name: string; kind: 'function' | 'class' | 'variable'; signature: string }> = [];
    for (const line of content.split('\n')) {
      // Top-level function: def name(params):
      const fn = line.match(/^def\s+(\w+)\s*\(([^)]*)\)/);
      if (fn) {
        symbols.push({ name: fn[1], kind: 'function', signature: `def ${fn[1]}(${fn[2]})` });
        continue;
      }
      // Top-level class: class Name
      const cls = line.match(/^class\s+(\w+)/);
      if (cls) {
        symbols.push({ name: cls[1], kind: 'class', signature: `class ${cls[1]}` });
        continue;
      }
      // Top-level variable assignment: name = ...
      const varr = line.match(/^([A-Za-z]\w*)\s*=[^=]/);
      if (varr && !line.startsWith('import ') && !line.startsWith('from ')) {
        symbols.push({ name: varr[1], kind: 'variable', signature: varr[1] });
      }
    }
    return symbols;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private registerMonacoProviders(): void {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const monaco = (window as any).monaco;
    if (!monaco || this.completionProviderDisposable) return;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    this.completionProviderDisposable = monaco.languages.registerCompletionItemProvider('python', {
      triggerCharacters: ['.'],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      provideCompletionItems: (model: any, position: any) => {
        const lineText: string = model.getValueInRange({
          startLineNumber: position.lineNumber, startColumn: 1,
          endLineNumber: position.lineNumber, endColumn: position.column,
        });

        const match = lineText.match(/(\w+)\.(\w*)$/);
        if (!match) return { suggestions: [] };

        const moduleName = match[1];
        const file = this.currentPackage?.files.find(f => f.name === `${moduleName}.py`);
        if (!file) return { suggestions: [] };

        const symbols = this.extractPythonSymbols(file.content);
        const CIK = monaco.languages.CompletionItemKind;
        const ITR = monaco.languages.CompletionItemInsertTextRule;

        return {
          suggestions: symbols.map(s => ({
            label: s.name,
            kind: s.kind === 'function' ? CIK.Function : s.kind === 'class' ? CIK.Class : CIK.Variable,
            detail: s.signature,
            documentation: { value: `\`\`\`python\n${s.signature}\n\`\`\`\n\n*Defined in ${moduleName}.py*` },
            insertText: s.kind === 'function' ? `${s.name}($0)` : s.name,
            insertTextRules: s.kind === 'function' ? ITR.InsertAsSnippet : undefined,
          })),
        };
      },
    });
  }

  private getLanguageForFile(fileName: string): string {
    const ext = fileName.split('.').pop()?.toLowerCase() ?? '';
    const map: Record<string, string> = {
      py: 'python', json: 'json',
      yaml: 'yaml', yml: 'yaml',
      md: 'markdown', txt: 'plaintext',
      sh: 'shell', js: 'javascript', ts: 'typescript',
    };
    return map[ext] ?? 'plaintext';
  }

  startRename(fileName: string, event: Event): void {
    event.stopPropagation();
    this.renamingFileName = fileName;
    this.renameInput = fileName;
    setTimeout(() => {
      (document.querySelector('.rename-input') as HTMLInputElement | null)?.select();
    }, 0);
  }

  commitRename(oldName: string): void {
    const newName = this.renameInput.trim();
    if (!newName || newName === oldName || !this.currentPackage) {
      this.cancelRename();
      return;
    }
    if (this.currentPackage.files.some(f => f.name === newName)) {
      this.messageService.add({
        severity: 'warn',
        summary: 'Name taken',
        detail: `A file named "${newName}" already exists.`,
      });
      this.cancelRename();
      return;
    }
    const file = this.currentPackage.files.find(f => f.name === oldName);
    if (file) {
      file.name = newName;
      if (this.selectedFileName === oldName) this.selectedFileName = newName;
      this.isDirty = true;
    }
    this.cancelRename();
  }

  cancelRename(): void {
    this.renamingFileName = null;
    this.renameInput = '';
  }

  private flushCurrentFileContent(): void {
    if (!this.currentPackage) return;
    const file = this.currentPackage.files.find(f => f.name === this.selectedFileName);
    if (file) file.content = this.currentFileContent;
  }

  async savePackage(): Promise<void> {
    if (!this.currentPackage) return;
    this.flushCurrentFileContent();
    this.isSaving = true;
    try {
      const pkg: LivePackage = {
        ...this.currentPackage,
        python_version: this.selectedPythonVersion,
      };
      await this.liveCodeService.savePackageAsync(pkg);
      this.isDirty = false;
      await this.loadPackageList();
      this.messageService.add({
        severity: 'success',
        summary: 'Saved',
        detail: `${pkg.package_name} saved successfully.`,
      });
    } catch {
      this.messageService.add({
        severity: 'error',
        summary: 'Save failed',
        detail: 'Could not save the package.',
      });
    } finally {
      this.isSaving = false;
    }
  }

  async runDirectly(): Promise<void> {
    if (!this.currentPackage) return;
    this.runArgs = (this.currentPackage.package_arguments ?? []).map(a => ({
      name: a.name,
      value: a.default ?? '',
    }));
    await this.saveAndRun();
  }

  openRunWithArgsDialog(): void {
    if (!this.currentPackage) return;
    this.runArgs = (this.currentPackage.package_arguments ?? []).map(a => ({
      name: a.name,
      value: a.default ?? '',
    }));
    this.showRunDialog = true;
  }

  addRunArg(): void {
    this.runArgs.push({ name: '', value: '' });
  }

  removeRunArg(index: number): void {
    this.runArgs.splice(index, 1);
  }

  async saveAndRun(): Promise<void> {
    if (!this.currentPackage) return;
    this.showRunDialog = false;
    if (this.isDirty) await this.savePackage();
    if (!this.currentPackage) return;

    this.wsSubscription?.unsubscribe();
    this.webSocketService.closeTaskLogsConnection();

    this.isRunning = true;
    this.taskLogs = [];
    this.runHeader = `▶  Running ${this.currentPackage.package_name}...`;
    this.runSummary = null;

    const args = this.runArgs.filter(a => a.name.trim());
    const startTime = Date.now();
    try {
      const response = await this.liveCodeService.runPackageAsync(
        this.currentPackage.package_name,
        args,
        false,
      );
      const taskId = (response as AsyncPackageResponse).task_id;
      await this.streamTaskLogs(taskId, startTime);
    } catch (err: unknown) {
      const detail =
        (err as { error?: { detail?: string } })?.error?.detail ?? 'Execution failed.';
      this.runSummary = { text: `✗  ${detail}`, success: false };
    } finally {
      this.isRunning = false;
    }
  }

  private streamTaskLogs(taskId: string, startTime: number): Promise<void> {
    return new Promise((resolve) => {
      this.wsSubscription = this.webSocketService.connectToTaskLogs(taskId).subscribe({
        next: (data: { logs: string[] }) => {
          if (data.logs) this.taskLogs = data.logs;
        },
        error: () => resolve(),
      });

      const poll = setInterval(async () => {
        try {
          const status = await this.taskService.getTaskStatusAsync(taskId);
          const done = ['completed', 'failed', 'cancelled', 'timeout'].includes(
            status.status.toLowerCase(),
          );
          if (done) {
            clearInterval(poll);
            this.wsSubscription?.unsubscribe();
            this.webSocketService.closeTaskLogsConnection();
            const logs = await this.taskService.getTaskLogsAsync(taskId);
            this.taskLogs = logs.logs;
            const elapsed = ((Date.now() - startTime) / 1000).toFixed(2);
            const ok = status.status.toLowerCase() === 'completed';
            this.runSummary = {
              text: ok ? `✓  Finished in ${elapsed}s` : `✗  Task ${status.status}`,
              success: ok,
            };
            resolve();
          }
        } catch {
          clearInterval(poll);
          resolve();
        }
      }, 1500);
    });
  }

  clearOutput(): void {
    this.taskLogs = [];
    this.runHeader = null;
    this.runSummary = null;
  }

  fileTabClass(fileName: string): string {
    return fileName === this.selectedFileName
      ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
      : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800';
  }
}
