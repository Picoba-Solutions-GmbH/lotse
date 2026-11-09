export type DiskUsage = {
    total_bytes: number;
    used_bytes: number;
    free_bytes: number;
};

export type PersistentVolumeInfo = {
    pv_name: string;
    reclaim_policy?: string | null;
    source?: { type: string; location: string } | null;
    nodes?: string[] | null;
};

export type KubernetesVolumeInfo = {
    name: string;
    mount_path: string;
    pvc_name?: string | null;
    storage_class?: string | null;
    access_modes?: string[] | null;
    capacity?: string | null;
    phase?: string | null;
    host_path?: string | null;
    empty_dir?: boolean;
    persistent_volume?: PersistentVolumeInfo | null;
};

export type KubernetesStorageInfo = {
    namespace: string | null;
    pod_name: string;
    node_name: string | null;
    volume: KubernetesVolumeInfo | null;
    error?: string;
};

export type StorageLocation = {
    hostname: string;
    in_cluster: boolean;
    home_path: string;
    packages_root: string;
    venvs_root: string;
    execution_namespace: string;
    execution_workdir: string;
    disk: DiskUsage | null;
    kubernetes: KubernetesStorageInfo | null;
};

export type StoredPackageVersion = {
    package_name: string;
    version: string;
    deployment_id: string;
    deployed_at: string | null;
    active: boolean;
    is_live: boolean;
    description?: string | null;
    runtime: string | null;
    image?: string | null;
    path: string;
    exists: boolean;
    size_bytes: number;
    file_count: number;
    has_archive: boolean;
    archive_size_bytes: number;
    venv_path: string;
    venv_exists: boolean;
    venv_size_bytes: number;
};

export type StoredPackage = {
    package_name: string;
    owner?: string | null;
    path: string;
    size_bytes: number;
    venv_size_bytes: number;
    versions: StoredPackageVersion[];
};

export type OrphanedDirectory = {
    directory: string;
    path: string;
    size_bytes: number;
    file_count: number;
};

export type StorageOverview = {
    location: StorageLocation;
    totals: {
        packages: number;
        versions: number;
        size_bytes: number;
        venv_size_bytes: number;
        orphan_size_bytes: number;
    };
    packages: StoredPackage[];
    orphans: OrphanedDirectory[];
};

export type BackupSelection = {
    package_name: string;
    /** undefined/null = all versions */
    versions?: string[] | null;
};

export type BackupOptions = {
    include_config: boolean;
    only_active: boolean;
};

export type BackupRequest = BackupOptions & {
    /** undefined/null = all packages */
    packages?: BackupSelection[] | null;
};
