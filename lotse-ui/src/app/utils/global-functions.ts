import { firstValueFrom, Observable } from 'rxjs';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
(window as any).fetchAsync = function (input: RequestInfo, init?: RequestInit): Promise<Response> {
  return fetch(input, init);
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
(window as any).firstValueFromAsync = function <T>(source: Observable<T>): Promise<T> {
  return firstValueFrom(source);
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
Response.prototype.toJsonAsync = function (): Promise<any> {
    // eslint-disable-next-line async-protect/async-await
    return this.json();
};

Response.prototype.toTextAsync = function (): Promise<string> {
    // eslint-disable-next-line async-protect/async-await
    return this.text();
}