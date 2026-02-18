import { PackageRequestArguments } from "./PackageRequestArguments";

export interface PackageRequest {
  package_name: string;
  arguments: PackageRequestArguments[];
  wait_for_completion: boolean;
}
