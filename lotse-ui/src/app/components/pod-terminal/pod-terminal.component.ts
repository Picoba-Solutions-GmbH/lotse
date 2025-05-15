import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, ElementRef, EventEmitter, Input, OnDestroy, Output, ViewChild } from '@angular/core';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import { WebLinksAddon } from 'xterm-addon-web-links';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-pod-terminal',
  standalone: true,
  imports: [CommonModule],
  template: '<div #terminal class="terminal-container"></div>',
  styleUrl: './pod-terminal.component.scss'
})
export class PodTerminalComponent implements AfterViewInit, OnDestroy {
  @ViewChild('terminal') terminalElement!: ElementRef;
  @Input() taskId!: string;
  @Output() socketClosed = new EventEmitter<void>();

  private terminal!: Terminal;
  private fitAddon!: FitAddon;
  private socket: WebSocket | null = null;

  ngAfterViewInit() {
    this.initializeTerminal();
  }

  private initializeTerminal() {
    this.terminal = new Terminal({
      fontSize: 14,
      windowOptions: {
        fullscreenWin: true,
        maximizeWin: true,
      },
      fontFamily: 'Consolas, "Courier New", monospace',
      cursorBlink: true,
      convertEol: true,
      theme: {
        background: '#000000',
        foreground: '#ffffff'
      }
    });

    this.fitAddon = new FitAddon();
    this.terminal.loadAddon(this.fitAddon);
    this.terminal.loadAddon(new WebLinksAddon());

    this.terminal.open(this.terminalElement.nativeElement);
    this.fitAddon.fit();

    this.terminalElement.nativeElement.addEventListener('contextmenu', async (event: MouseEvent) => {
      event.preventDefault();

      const selection = this.terminal.getSelection();
      if (selection) {
        await navigator.clipboard.writeText(selection);
        this.terminal.clearSelection();
      } else {
        const text = await navigator.clipboard.readText();
        if (text && this.socket) {
          this.socket.send(text);
        }
      }
    });

    setTimeout(() => {
      this.handleFit();
    }, 100);

    this.connectWebSocket();

    this.terminal.onData(data => {
      this.socket?.send(data);
    });

    const resizeHandler = () => this.handleFit();
    window.addEventListener('resize', resizeHandler);
    this.terminal.onResize(() => this.handleFit());
    this.terminalElement.nativeElement.addEventListener('resize', resizeHandler);
  }

  public handleFit() {
    this.fitAddon.fit();
    this.socket?.send(JSON.stringify({
      type: 'resize',
      cols: this.terminal.cols,
      rows: this.terminal.rows
    }));
  }

  private connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = environment.url;
    const urlWithoutProtocol = url.substring(url.indexOf('://') + 3);
    const wsUrl = `${wsProtocol}//${urlWithoutProtocol}/task/${this.taskId}/terminal`;

    this.socket = new WebSocket(wsUrl);

    this.socket.onopen = () => {
      this.terminal.clear();
    };

    this.socket.onmessage = (event) => {
      if (event.data) {
        this.terminal.write(event.data);
      }
    };

    this.socket.onerror = (error) => {
      this.terminal.writeln('\r\nConnection error');
    };

    this.socket.onclose = (event) => {
      const reason = event.reason || 'Connection closed';
      this.terminal.writeln(`\r\nDisconnected: ${reason}`);
      this.socketClosed.emit()
    };
  }

  ngOnDestroy() {
    this.socket?.close();
    this.terminal.dispose();
  }
}