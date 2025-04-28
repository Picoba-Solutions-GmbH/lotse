import { PackageArgument } from "./PackageArgument";

export interface RepositoryConfig {
  package_name: string;
  python_version: string;
  env_content?: string;
  package_arguments?: PackageArgument[];
}
