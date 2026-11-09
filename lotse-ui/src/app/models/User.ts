import { Role } from '../misc/Role';

export interface User {
  id: string;
  name: string;
  display_name?: string | null;
  email?: string | null;
  role: Role;
  is_ldap: boolean;
}

export interface UserLookup {
  id: string;
  name: string;
  display_name?: string | null;
}
