export interface PackageEnvironment {
  name: string;
  /** Always null for secret variables loaded from the server; null on save keeps the stored value. */
  value: string | null;
  secret?: boolean;
  has_value?: boolean;
  /** Name the variable had when it was loaded, lets the server keep a secret's value on rename. */
  previous_name?: string | null;
}

// Keep in sync with looks_sensitive() in src/models/yaml_config.py
const SENSITIVE_NAME_PARTS = new Set(['KEY', 'KEYS', 'PASS', 'PASSWD', 'PRIVATE', 'CREDENTIALS', 'CREDENTIAL', 'AUTH']);
const SENSITIVE_SUBSTRINGS = ['SECRET', 'PASSWORD', 'TOKEN', 'APIKEY', 'CONNECTIONSTRING', 'CONNECTION_STRING'];

export function looksSensitive(name: string): boolean {
  const upper = (name ?? '').toUpperCase();
  return upper.split(/[_\-.]/).some(part => SENSITIVE_NAME_PARTS.has(part))
    || SENSITIVE_SUBSTRINGS.some(fragment => upper.includes(fragment));
}
