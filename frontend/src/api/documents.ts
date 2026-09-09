import { api } from './http.ts';
import { adminHeaders } from './auth.ts';

// ---- Documents ----
export interface DocInfo {
  id: string;
  filename: string;
  title: string | null;
  file_type: string;
  status: string;
  char_count: number;
  section_count: number;
  summary: string;
  created_at: string;
  updated_at: string;
  error_message: string | null;
  uploader?: string;
  // 版本 / 同步 / 画像状态
  last_parsed_at?: string | null;
  content_version?: number;
  index_version?: number;
  sync_status?: string; // synced | pending_reparse | reparsing | failed
  profile_status?: string; // none | generating | ready | error
  profile_error?: string | null;
  edited_at?: string | null;
  full_text?: string | null;
  profile?: DocProfile | null;
}

export interface DocSection {
  id: string;
  document_id: string;
  section_index: number;
  heading: string;
  content: string;
  page_number: number | null;
  parent_heading: string | null;
  level: number;
  char_count: number;
}

export interface DocProfile {
  document_id: string;
  title: string;
  summary: string;
  topics: string[];
  entities: string[];
  keywords: string[];
  possible_questions: string[];
  profile_json?: string;
  created_at?: string;
}

export interface DocProfileResult {
  document_id: string;
  profile_status: string; // none | generating | ready | error
  profile_error: string | null;
  profile: DocProfile | null;
}

export const apiDocs = {
  list: () => api<DocInfo[]>('/api/documents', { headers: adminHeaders() }),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return api<{ document_id: string }>('/api/documents', {
      method: 'POST',
      body: fd,
      headers: adminHeaders(),
    });
  },
  createText: (title: string, content: string) =>
    api<{ document_id: string }>('/api/documents/text', {
      method: 'POST',
      body: JSON.stringify({ title, content }),
      headers: adminHeaders(),
    }),
  delete: (id: string) =>
    api(`/api/documents/${id}`, { method: 'DELETE', headers: adminHeaders() }),
  get: (id: string) =>
    api<DocInfo>(`/api/documents/${id}`, { headers: adminHeaders() }),
  sections: (id: string) =>
    api<DocSection[]>(`/api/documents/${id}/sections`, { headers: adminHeaders() }),
  profile: (id: string) =>
    api<DocProfileResult>(`/api/documents/${id}/profile`, { headers: adminHeaders() }),
  generateProfile: (id: string) =>
    api<DocProfileResult>(`/api/documents/${id}/profile`, {
      method: 'POST',
      headers: adminHeaders(),
    }),
  repare: (id: string) =>
    api(`/api/documents/${id}/reparse`, { method: 'POST', headers: adminHeaders() }),
  update: (id: string, data: { title?: string; full_text?: string }) =>
    api<DocInfo>(`/api/documents/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
      headers: adminHeaders(),
    }),
  setStatus: (id: string, status: string) =>
    api<DocInfo>(`/api/documents/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
      headers: adminHeaders(),
    }),
};
