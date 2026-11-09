import { UserLookup } from './User';

export interface PackagePermissions {
  view: boolean;
  execute: boolean;
  edit: boolean;
  manage: boolean;
}

export const ALL_PERMISSIONS: PackagePermissions = { view: true, execute: true, edit: true, manage: true };

export interface PackageShare {
  user: UserLookup;
  can_execute: boolean;
  can_edit: boolean;
}

export interface PackageAccess {
  package_name: string;
  owner: UserLookup | null;
  permissions: PackagePermissions;
  shares: PackageShare[];
}
