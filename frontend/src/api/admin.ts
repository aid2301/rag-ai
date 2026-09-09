import { api } from './http.ts';
import { adminHeaders } from './auth.ts';
import type { ConvInfo, MsgInfo } from './conversations.ts';

export interface AdminOverview {
  pending_questions: number;
  unanswered_messages: number;
  parse_failed_documents: number;
  total_questions: number;
}

export const apiAdminOverview = {
  get: () => api<AdminOverview>('/api/admin/overview', { headers: adminHeaders() }),
};

export interface AdminUserInfo {
  id: string;
  username: string;
  display_name: string;
  is_active: number;
  created_at: string;
  conversation_count: number;
  call_count: number;
  total_tokens: number;
  last_active: string | null;
}

export const apiAdminUsers = {
  list: () => api<AdminUserInfo[]>('/api/admin/users', { headers: adminHeaders() }),
  create: (username: string, password: string, displayName?: string) =>
    api('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify({ username, password, display_name: displayName }),
      headers: adminHeaders(),
    }),
  remove: (id: string) =>
    api(`/api/admin/users/${id}`, { method: 'DELETE', headers: adminHeaders() }),
  resetPassword: (id: string, password: string) =>
    api(`/api/admin/users/${id}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ password }),
      headers: adminHeaders(),
    }),
  conversations: (id: string) =>
    api<ConvInfo[]>(`/api/admin/users/${id}/conversations`, {
      headers: adminHeaders(),
    }),
  allConversations: () =>
    api<(ConvInfo & { username: string })[]>('/api/admin/conversations', {
      headers: adminHeaders(),
    }),
  messages: (userId: string, convId: string) =>
    api<MsgInfo[]>(`/api/admin/users/${userId}/conversations/${convId}/messages`, {
      headers: adminHeaders(),
    }),
  conversationMessages: (convId: string) =>
    api<MsgInfo[]>(`/api/admin/conversations/${convId}/messages`, {
      headers: adminHeaders(),
    }),
};
