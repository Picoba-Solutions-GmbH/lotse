import { TaskInfo } from './TaskInfo';
import { PackageArgument } from "./PackageArgument";
import { PackagePermissions } from './PackageAccess';

export type PackageInfo = {
    name: string;
    status: string;
    instances: number;
    creation_date: string;
    owner?: string | null;
    permissions?: PackagePermissions | null;
}

export type PackageDetail = PackageInfo & {
    version: string;
    is_default: boolean;
    is_modified?: boolean;
    /** versions deployed by a source: 'git' (tag + commit) or 'image' (image tag + digest) */
    source_type?: 'git' | 'image' | null;
    source_ref?: string | null;
    source_commit?: string | null;
}

export type PackageModifications = {
    is_modified: boolean;
    config_modified: boolean;
    modified_files: string[];
    modified_at?: string | null;
}

export type PackageFile = {
    path: string;
    size: number;
    editable: boolean;
    modified: boolean;
}

export type PackageFileContent = {
    path: string;
    content: string;
}

export type PackageInstance = {
    name: string;
    description: string;
    tasks: TaskInfo[];
    package_arguments?: PackageArgument[];
    is_default: boolean;
    permissions?: PackagePermissions | null;
    runtime?: string | null;
    has_files?: boolean;
    modifications?: PackageModifications;
}
