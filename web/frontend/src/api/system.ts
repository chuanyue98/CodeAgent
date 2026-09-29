export interface SystemHealth {
  status: string;
  sections: Array<{
    title: string;
    checks: Array<{
      status: string;
      label: string;
      detail: string;
      fixHint: string;
    }>;
  }>;
}

export interface SystemMetrics {
  cpuPercent: number;
  memoryPercent: number;
  memoryUsedGb: number;
  memoryTotalGb: number;
  diskPercent: number;
  diskUsedGb: number;
  diskTotalGb: number;
  uptimeSeconds: number;
  historyFileSizeMb: number;
  logFileCount: number;
}

import request from '../utils/request';

export async function fetchSystemHealth(): Promise<SystemHealth> {
  return request('/api/system/health');
}

export async function fetchSystemMetrics(): Promise<SystemMetrics> {
  return request('/api/system/metrics');
}

export interface EngineMounts {
  id: string;
  name: string;
  /** The resource kinds (skills / hooks / plugins) this engine's launcher attaches at start-up. */
  mounts: string[];
}

export async function fetchEngineMounts(): Promise<EngineMounts[]> {
  const body = await request<{ engines?: EngineMounts[] }>('/api/system/engines');
  return Array.isArray(body.engines) ? body.engines : [];
}
