import { GitSyncStatus, GitTag } from './GitSource';

export type ImageSourceSettings = {
    registry_id: string;
    repository: string;
    tag_prefix: string;
    auto_sync: boolean;
    prune_previous: boolean;
    poll_interval_seconds: number;
}

export type ImageSourceCreateRequest = ImageSourceSettings & {
    /** defaults to the last segment of the repository */
    package_name?: string | null;
}

export type ImageSource = ImageSourceSettings & {
    id: string;
    package_name: string;
    registry_name?: string | null;
    image: string;
    status: GitSyncStatus;
    active_version?: string | null;
    latest_tag?: string | null;
    latest_version?: string | null;
    latest_digest?: string | null;
    last_synced_tag?: string | null;
    last_synced_digest?: string | null;
    last_synced_at?: string | null;
    last_checked_at?: string | null;
    last_error?: string | null;
    webhook_path: string;
    webhook_token?: string | null;
    can_edit: boolean;
    created_at: string;
}

/** `commit` holds the digest of the deployed version, "" if the tag isn't deployed */
export type ImageTag = GitTag;

export type ImageSyncResult = {
    action: 'deployed' | 'activated';
    tag: string;
    version: string;
    digest: string;
    source: ImageSource;
}
