import { api } from './http.ts';
import { adminHeaders } from './auth.ts';

export interface SettingsInfo {
  llm_base_url: string;
  llm_api_key: string;
  llm_api_key_set: boolean;
  llm_api_key_masked: string;
  llm_model: string;
  llm_temperature: number;
  llm_max_tokens: number;
  llm_timeout: number;
  default_chat_mode?: string; // auto | fast | standard | deep
  show_thinking?: boolean;
}

export interface PublicSettings {
  default_chat_mode: string;
  show_thinking: boolean;
}

export const apiSettings = {
  get: () => api<SettingsInfo>('/api/settings', { headers: adminHeaders() }),
  public: () => api<PublicSettings>('/api/settings/public'),
  update: (data: Partial<SettingsInfo>) =>
    api('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
      headers: adminHeaders(),
    }),
  test: () =>
    api<{ ok: boolean; message?: string; model?: string; latency_ms?: number; reply?: string }>(
      '/api/settings/test',
      { method: 'POST', headers: adminHeaders() },
    ),
};
