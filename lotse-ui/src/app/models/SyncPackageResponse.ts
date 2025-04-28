
export interface SyncPackageResponse {
  success: boolean;
  output: string;
  task_id: string;
  error: string | null;
  execution_time: number;
}
