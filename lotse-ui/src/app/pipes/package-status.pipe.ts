import { Pipe, PipeTransform } from '@angular/core';
import { Tag } from 'primeng/tag';
import { PackageStatus } from '../misc/PackageStatus';

@Pipe({
  name: 'packageStatusToSeverityPipe',
  pure: true
})
export class PackageStatusToSeverityPipe implements PipeTransform {
  transform(value: string): Tag['severity'] {
    switch (value) {
      case PackageStatus.IDLE:
        return 'contrast';
      case PackageStatus.RUNNING:
        return 'success';
    }

    return 'secondary';
  }
}


