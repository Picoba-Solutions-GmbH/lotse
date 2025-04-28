import { Pipe, PipeTransform } from '@angular/core';
import { TaskStatus } from '../misc/TaskStatus';
import { PackageInstance } from '../models/Package';
import { TaskInfo } from '../models/TaskInfo';

@Pipe({
  name: 'taskCountByState',
  pure: true
})
export class TaskCountByStatePipe implements PipeTransform {
  transform(value: TaskInfo[], status: TaskStatus): number {
    return value.filter((pkg) => pkg.status === status).length;
  }
}


