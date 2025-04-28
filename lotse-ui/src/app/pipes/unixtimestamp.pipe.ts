import { DatePipe } from '@angular/common';
import { Pipe, PipeTransform } from '@angular/core';

@Pipe({
  name: 'unixtimestamp',
  pure: true
})
export class UnixtimestampPipe implements PipeTransform {
  private datePipe = new DatePipe('en-US');

  transform(unixTimestamp: number): string {
    const date = new Date(unixTimestamp * 1000);
    return this.datePipe.transform(date, 'yyyy-MM-dd HH:mm') || '';
  }
}
