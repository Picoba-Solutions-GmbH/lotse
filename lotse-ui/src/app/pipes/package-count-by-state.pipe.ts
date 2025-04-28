import { Pipe, PipeTransform } from '@angular/core';
import { PackageStatus } from '../misc/PackageStatus';
import { PackageInfo } from '../models/Package';

@Pipe({
  name: 'packageCountByStatePipe',
  pure: true
})
export class PackageCountByStatePipe implements PipeTransform {
  transform(value: PackageInfo[], status: PackageStatus): number {
    return value.filter((pkg) => pkg.status === status).length;
  }
}


