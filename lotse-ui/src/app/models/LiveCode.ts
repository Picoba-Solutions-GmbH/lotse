import { PackageArgument } from './PackageArgument';

export interface LiveCodeFile {
  name: string;
  content: string;
}

export interface LivePackage {
  package_name: string;
  python_version: string;
  files: LiveCodeFile[];
  package_arguments?: PackageArgument[];
}

export interface LivePackageInfo {
  package_name: string;
  python_version: string;
  last_modified?: string;
}
