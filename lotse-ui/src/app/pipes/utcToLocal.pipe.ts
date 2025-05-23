import { Pipe, PipeTransform } from '@angular/core';
import { format, parseISO } from 'date-fns';
import { toZonedTime, } from 'date-fns-tz';

@Pipe({
  name: 'utcToLocal'
})
export class UtcToLocalPipe implements PipeTransform {
  transform(utcDate: string, formatString: string = 'yy.MM.dd HH:mm:ss'): string {
    if (!utcDate) {
      return '';
    }

    utcDate = `${utcDate}Z`;
    const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const parsedDate = typeof utcDate === 'string' ? parseISO(utcDate) : utcDate;
    const localDate = toZonedTime(parsedDate, timeZone);
    return format(localDate, formatString);
  }
}