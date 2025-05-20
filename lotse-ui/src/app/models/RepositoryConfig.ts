import { PackageArgument } from "./PackageArgument";
import { Runtime } from "../misc/Runtime";

export interface RepositoryConfig {
  package_name: string;
  python_version: string;
  runtime?: Runtime;
  env_content?: string;
  package_arguments?: PackageArgument[];
}
