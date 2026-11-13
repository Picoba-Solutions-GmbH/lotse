export type GitSyncStatus = 'Unknown' | 'NoTags' | 'Synced' | 'OutOfSync' | 'Error';

export type GitSourceSettings = {
    repo_url: string;
    path: string;
    tag_prefix: string;
    username?: string | null;
    auto_sync: boolean;
    prune_previous: boolean;
    poll_interval_seconds: number;
}

export type GitSourceCreateRequest = GitSourceSettings & {
    package_name: string;
    token?: string | null;
}

export type GitSourceUpdateRequest = GitSourceSettings & {
    /** null/undefined keeps the stored token */
    token?: string | null;
    clear_token?: boolean;
}

export type GitSource = GitSourceSettings & {
    id: string;
    package_name: string;
    has_token: boolean;
    status: GitSyncStatus;
    active_version?: string | null;
    latest_tag?: string | null;
    latest_version?: string | null;
    latest_commit?: string | null;
    last_synced_tag?: string | null;
    last_synced_commit?: string | null;
    last_synced_at?: string | null;
    last_checked_at?: string | null;
    last_error?: string | null;
    webhook_path: string;
    webhook_token?: string | null;
    can_edit: boolean;
    created_at: string;
}

export type GitTag = {
    tag: string;
    version: string;
    commit: string;
    deployed: boolean;
    active: boolean;
}

export type GitConnectionTestRequest = {
    repo_url: string;
    tag_prefix: string;
    username?: string | null;
    token?: string | null;
    source_id?: string | null;
}

export type GitConnectionTestResult = {
    success: boolean;
    message: string;
    tags: GitTag[];
}

export type GitSyncResult = {
    action: 'deployed' | 'activated';
    tag: string;
    version: string;
    commit: string;
    source: GitSource;
}
