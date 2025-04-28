import { TaskMetric } from './TaskMetric';


export interface TaskInfo {
  task_id: string;
  package_name: string;
  package_version: string;
  status: string;
  pid?: number;
  message?: string;
  started_at: string;
  finished_at?: string;
  is_ui_app: boolean;
  metrics?: TaskMetric;
}
