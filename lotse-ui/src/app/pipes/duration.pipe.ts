import { Pipe, PipeTransform } from '@angular/core';
import { differenceInSeconds } from 'date-fns';

@Pipe({
  name: 'duration'
})
export class DurationPipe implements PipeTransform {
  transform(startedAt: string | Date, finishedAt?: string | Date): string {
    if (!startedAt) {
      return '';
    }

    startedAt = `${startedAt}Z`;
    finishedAt = finishedAt ? `${finishedAt}Z` : undefined;
    const start = new Date(startedAt);
    const end = finishedAt ? new Date(finishedAt) : new Date();

    const totalSeconds = differenceInSeconds(end, start);

    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    const parts = [];
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0) parts.push(`${minutes}m`);
    parts.push(`${seconds}s`);

    return parts.join(' ');
  }
}