import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { DatePickerModule } from 'primeng/datepicker';
import { DialogModule } from 'primeng/dialog';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { TooltipModule } from 'primeng/tooltip';
import { environment } from '../../../environments/environment';

interface LogEntry {
    timestamp: string;
    level: string;
    logger: string;
    message: string;
}

interface LogResponse {
    total: number;
    limit: number;
    offset: number;
    logs: LogEntry[];
}

@Component({
    selector: 'app-logs',
    imports: [
        CommonModule,
        FormsModule,
        TableModule,
        CardModule,
        TagModule,
        ButtonModule,
        InputNumberModule,
        InputTextModule,
        SelectModule,
        DatePickerModule,
        TooltipModule,
        DialogModule,
    ],
    templateUrl: './logs.component.html',
    styleUrl: './logs.component.scss',
})
export class LogsComponent implements OnInit {
    logs: LogEntry[] = [];
    total: number = 0;
    loading: boolean = false;

    // Filter state
    limit: number = 50;
    offset: number = 0;
    selectedLevel: string | null = null;
    fromDate: Date | null = null;
    toDate: Date | null = null;
    search: string = '';

    levelOptions = [
        { label: 'All levels', value: null },
        { label: 'DEBUG', value: 'DEBUG' },
        { label: 'INFO', value: 'INFO' },
        { label: 'WARNING', value: 'WARNING' },
        { label: 'ERROR', value: 'ERROR' },
        { label: 'CRITICAL', value: 'CRITICAL' },
    ];

    constructor(private http: HttpClient) { }

    ngOnInit(): void {
        this.loadLogs();
    }

    loadLogs(): void {
        this.loading = true;

        const params: Record<string, string> = {
            limit: String(this.limit),
            offset: String(this.offset),
        };

        if (this.selectedLevel) params['level'] = this.selectedLevel;
        if (this.fromDate) params['from_date'] = this.fromDate.toISOString();
        if (this.toDate) params['to_date'] = this.toDate.toISOString();
        if (this.search.trim()) params['search'] = this.search.trim();

        this.http
            .get<LogResponse>(`${environment.url}/logs`, { params })
            .subscribe({
                next: (res) => {
                    this.logs = res.logs.slice().reverse();
                    this.total = res.total;
                    this.loading = false;
                },
                error: () => {
                    this.loading = false;
                },
            });
    }

    applyFilters(): void {
        this.offset = 0;
        this.loadLogs();
    }

    clearFilters(): void {
        this.selectedLevel = null;
        this.fromDate = null;
        this.toDate = null;
        this.search = '';
        this.limit = 50;
        this.offset = 0;
        this.loadLogs();
    }

    prevPage(): void {
        this.offset = Math.max(0, this.offset - this.limit);
        this.loadLogs();
    }

    nextPage(): void {
        this.offset = this.offset + this.limit;
        this.loadLogs();
    }

    get currentPage(): number {
        return Math.floor(this.offset / this.limit) + 1;
    }

    get totalPages(): number {
        return Math.ceil(this.total / this.limit);
    }

    get showingEnd(): number {
        return Math.min(this.offset + this.limit, this.total);
    }

    readonly MESSAGE_TRUNCATE_LENGTH = 120;

    expandedEntry: LogEntry | null = null;
    dialogVisible: boolean = false;

    truncateMessage(msg: string): string {
        if (msg.length <= this.MESSAGE_TRUNCATE_LENGTH) return msg;
        return msg.slice(0, this.MESSAGE_TRUNCATE_LENGTH) + '…';
    }

    isLong(msg: string): boolean {
        return msg.length > this.MESSAGE_TRUNCATE_LENGTH;
    }

    openDialog(entry: LogEntry): void {
        this.expandedEntry = entry;
        this.dialogVisible = true;
    }

    levelSeverity(level: string): 'success' | 'info' | 'warn' | 'danger' | 'secondary' {
        switch (level) {
            case 'DEBUG': return 'secondary';
            case 'INFO': return 'info';
            case 'WARNING': return 'warn';
            case 'ERROR': return 'danger';
            case 'CRITICAL': return 'danger';
            default: return 'info';
        }
    }
}
