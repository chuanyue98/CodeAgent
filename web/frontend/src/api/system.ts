export interface SystemHealth {
  status: string;
  sections: Array<{
    title: string;
    checks: Array<{
      status: string;
      label: string;
      detail: string;
      fix_hint: string;
    }>;
  }>;
}

export interface SystemMetrics {
  cpu_percent: number;
  memory_percent: number;
  memory_used_gb: number;
  memory_total_gb: number;
  disk_percent: number;
  disk_used_gb: number;
  disk_total_gb: number;
  uptime_seconds: number;
  history_file_size_mb: number;
  log_file_count: number;
}

import request from '../utils/request';

export async function fetchSystemHealth(): Promise<SystemHealth> {
  return request('/api/system/health');
}

export async function fetchSystemMetrics(): Promise<SystemMetrics> {
  return request('/api/system/metrics');
}
