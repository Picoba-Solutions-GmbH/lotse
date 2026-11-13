export type RegistryProvider = 'generic' | 'acr' | 'ghcr' | 'gitlab' | 'dockerhub';
export type PullSecretMode = 'none' | 'lotse' | 'existing';

export type RegistrySettings = {
    name: string;
    host: string;
    provider: RegistryProvider;
    api_url?: string | null;
    username?: string | null;
    pull_secret_mode: PullSecretMode;
    pull_secret_name?: string | null;
    discovery_path?: string | null;
    auto_register: boolean;
    default_auto_sync: boolean;
    poll_interval_seconds: number;
}

export type RegistryRequest = RegistrySettings & {
    /** null/undefined keeps the stored token on update */
    token?: string | null;
    clear_token?: boolean;
}

export type Registry = RegistrySettings & {
    id: string;
    has_token: boolean;
    effective_pull_secret?: string | null;
    last_discovered_at?: string | null;
    last_error?: string | null;
    image_source_count: number;
    created_at: string;
}

export type RegistryTestRequest = {
    host: string;
    provider: RegistryProvider;
    api_url?: string | null;
    username?: string | null;
    token?: string | null;
    discovery_path?: string | null;
    registry_id?: string | null;
}

export type RegistryTestResult = {
    success: boolean;
    message: string;
    repositories: string[];
}

export type DiscoveredRepository = {
    repository: string;
    image: string;
    package_name: string;
    registered_as?: string | null;
    name_taken: boolean;
}
