import { Pipe, PipeTransform } from '@angular/core';
import { Tag } from 'primeng/tag';
import { TaskStatus } from '../misc/TaskStatus';

@Pipe({
  name: 'taskStatusToSeverityPipe',
  pure: true
})
export class TaskStatusToSeverityPipe implements PipeTransform {
  transform(value: string): Tag['severity'] {
    switch (value) {
      case TaskStatus.INITIALIZING:
        return 'contrast';
      case TaskStatus.RUNNING:
        return 'info';
      case TaskStatus.COMPLETED:
        return 'success';
      case TaskStatus.TIMEOUT:
      case TaskStatus.FAILED:
        return 'danger';
      case TaskStatus.CANCELLED:
        return 'warn';
    }

    return 'secondary';
  }
}


