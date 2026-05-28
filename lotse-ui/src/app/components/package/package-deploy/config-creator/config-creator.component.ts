import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { PrimeIcons } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TextareaModule } from 'primeng/textarea';
import { TooltipModule } from 'primeng/tooltip';
import YAML from 'yaml';
import { Runtime } from '../../../../misc/Runtime';

interface ArgEntry {
    name: string;
    defaultvalue: string;
}

interface EnvEntry {
    name: string;
    value: string;
}

interface VolumeEntry {
    name: string;
    path: string;
}

@Component({
    selector: 'app-config-creator',
    standalone: true,
    imports: [
        CommonModule,
        FormsModule,
        ButtonModule,
        DialogModule,
        InputTextModule,
        InputNumberModule,
        SelectModule,
        TextareaModule,
        TooltipModule,
    ],
    templateUrl: './config-creator.component.html',
    styleUrl: './config-creator.component.scss',
})
export class ConfigCreatorComponent {
    PrimeIcons = PrimeIcons;
    Runtime = Runtime;

    @Input() set prefillPackageName(value: string | null) {
        if (value) {
            this.packageName = value;
        }
    }
    @Output() configCreated = new EventEmitter<File>();

    showDialog = false;

    runtimeOptions = [
        { label: 'Python', value: Runtime.PYTHON },
        { label: 'Binary', value: Runtime.BINARY },
        { label: 'Container', value: Runtime.CONTAINER },
    ];

    packageName = '';
    version = '1.0.0';
    description = '';
    runtime: Runtime = Runtime.PYTHON;
    entrypoint = '';
    pythonVersion = '';
    image = '';
    timeout: number | null = null;

    args: ArgEntry[] = [];
    environment: EnvEntry[] = [];
    volumes: VolumeEntry[] = [];

    open(prefillName?: string): void {
        if (prefillName) {
            this.packageName = prefillName;
        }
        this.showDialog = true;
    }

    get previewYaml(): string {
        return this.buildYamlString();
    }

    get isValid(): boolean {
        return !!this.packageName.trim() && !!this.version.trim();
    }

    addArg(): void {
        this.args.push({ name: '', defaultvalue: '' });
    }

    removeArg(index: number): void {
        this.args.splice(index, 1);
    }

    addEnv(): void {
        this.environment.push({ name: '', value: '' });
    }

    removeEnv(index: number): void {
        this.environment.splice(index, 1);
    }

    addVolume(): void {
        this.volumes.push({ name: '', path: '' });
    }

    removeVolume(index: number): void {
        this.volumes.splice(index, 1);
    }

    private buildYamlString(): string {
        const doc: Record<string, unknown> = {
            package_name: this.packageName,
            version: this.version,
            runtime: this.runtime,
        };

        if (this.description.trim()) {
            doc['description'] = this.description;
        }

        if (this.runtime !== Runtime.CONTAINER && this.entrypoint.trim()) {
            doc['entrypoint'] = this.entrypoint;
        }

        if (this.runtime === Runtime.PYTHON && this.pythonVersion.trim()) {
            doc['python_version'] = this.pythonVersion;
        }

        if ((this.runtime === Runtime.CONTAINER || this.runtime === Runtime.BINARY) && this.image.trim()) {
            doc['image'] = this.image;
        }

        if (this.timeout !== null) {
            doc['timeout'] = this.timeout;
        }

        const validArgs = this.args.filter((a) => a.name.trim());
        if (validArgs.length > 0) {
            doc['args'] = validArgs.map((a) => ({ name: a.name, defaultvalue: a.defaultvalue }));
        }

        const validEnv = this.environment.filter((e) => e.name.trim());
        if (validEnv.length > 0) {
            doc['environment'] = validEnv.map((e) => ({ name: e.name, value: e.value }));
        }

        const validVolumes = this.volumes.filter((v) => v.name.trim() && v.path.trim());
        if (validVolumes.length > 0) {
            doc['volumes'] = validVolumes.map((v) => ({ name: v.name, path: v.path }));
        }

        return YAML.stringify(doc);
    }

    generate(): void {
        const yamlContent = this.buildYamlString();
        const blob = new Blob([yamlContent], { type: 'text/yaml' });
        const file = new File([blob], 'config.yaml', { type: 'text/yaml' });
        this.configCreated.emit(file);
        this.showDialog = false;
    }

    download(): void {
        const yamlContent = this.buildYamlString();
        const blob = new Blob([yamlContent], { type: 'text/yaml' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'config.yaml';
        a.click();
        URL.revokeObjectURL(url);
    }
}
