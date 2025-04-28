export {};

declare global {
  interface Response {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    toJsonAsync(): Promise<any>;
    toTextAsync(): Promise<string>;
  }

  function fetchAsync(input: string | URL | Request, init?: RequestInit | undefined): Promise<Response>;
  function firstValueFromAsync<T>(source: Observable<T>): Promise<T>;
}
