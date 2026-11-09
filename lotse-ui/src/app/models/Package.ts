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
}

export type PackageInstance = {
    name: string;
    description: string;
    tasks: TaskInfo[];
    package_arguments?: PackageArgument[];
    is_default: boolean;
    permissions?: PackagePermissions | null;
}
