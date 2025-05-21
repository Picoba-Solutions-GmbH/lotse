import { TaskInfo } from './TaskInfo';
import { PackageArgument } from "./PackageArgument";

export type PackageInfo = {
    name: string;
    status: string;
    instances: number;
    creation_date: string;
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
}