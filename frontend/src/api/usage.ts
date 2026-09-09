import { api } from './http.ts';
import { userHeaders, adminHeaders } from './auth.ts';

export interface UsageRecord {
  id: number;
  call_type: string;
  model: string | null;
  user_id: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  latency_ms: number;
  created_at: string;
}

export interface UsageSummaryItem {
  call_type: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  avg_latency_ms: number;
}

export interface UsageSummary {
  by_call_type: UsageSummaryItem[];
  total: { calls: number; total_tokens: number };
}

export interface AdminUsageRow {
  username: string;
  user_id: string | null;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  last_active: string | null;
}

export interface AdminUsageItem {
  call_type: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  avg_latency_ms: number | null;
}

export interface AdminUsageRecent {
  id: number;
  call_type: string;
  model: string | null;
  total_tokens: number;
  latency_ms: number | null;
  created_at: string;
  username: string;
}

export interface AdminUsage {
  by_user: AdminUsageRow[];
  by_call_type: AdminUsageItem[];
  total: { calls: number; total_tokens: number };
  recent: AdminUsageRecent[];
}

export const apiAdminUsage = {
  get: () => api<AdminUsage>('/api/admin/usage', { headers: adminHeaders() }),
};

// ---- Usage (用户端) ----
export const apiUsage = {
  summary: () => api<UsageSummary>('/api/usage/summary', { headers: userHeaders() }),
  recent: (limit = 200) =>
    api<UsageRecord[]>(`/api/usage?limit=${limit}`, { headers: userHeaders() }),
};
