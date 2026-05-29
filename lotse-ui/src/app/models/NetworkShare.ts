export interface NetworkShareProvisionRequest {
  name: string;
  share_path: string;
  storage_size: string;
  namespace?: string;
  access_modes: string[];
  mount_options: string[];
  secret_name?: string;
  secret_namespace: string;
  username?: string;
  password?: string;
}

export interface NetworkShareUpdateRequest {
  name: string;
  share_path: string;
  storage_size: string;
  namespace?: string;
  access_modes: string[];
  mount_options: string[];
  secret_mode: 'keep' | 'existing' | 'new';
  secret_name?: string;
  secret_namespace: string;
  username?: string;
  password?: string;
}

export interface NetworkShareResponse {
  id: string;
  name: string;
  pvc_name: string;
  pv_name: string;
  secret_name: string;
  namespace: string;
}

export interface NetworkShareVolume {
  id: string;
  name: string;
  pvc_name: string;
  share_path: string;
}

export interface NetworkShareDetail {
  id: string;
  name: string;
  pvc_name: string;
  pv_name: string;
  share_path: string;
  storage_size: string;
  namespace: string;
  access_modes: string[];
  mount_options: string[];
  secret_name: string;
  secret_namespace: string;
  pv_status: string;
  pvc_status: string;
}

export interface NetworkShareTestResult {
  success: boolean;
  message: string;
  output?: string;
}
