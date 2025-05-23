import { Pipe, PipeTransform } from '@angular/core';

@Pipe({
  name: 'age'
})
export class AgePipe implements PipeTransform {
  transform(value: string): string {
    if (!value) {
      return '';
    }

    const now = new Date();
    const timestamp = new Date(value);
    const diffInSeconds = Math.floor((now.getTime() - timestamp.getTime()) / 1000);

    if (diffInSeconds < 0) {
      return '0s';
    }

    const units = [
      { unit: 'y', seconds: 31536000 },
      { unit: 'M', seconds: 2592000 },
      { unit: 'd', seconds: 86400 },
      { unit: 'h', seconds: 3600 },
      { unit: 'm', seconds: 60 },
      { unit: 's', seconds: 1 }
    ];

    for (const { unit, seconds } of units) {
      if (diffInSeconds >= seconds) {
        const value = Math.floor(diffInSeconds / seconds);
        return `${value}${unit}`;
      }
    }

    return '0s';
  }
}