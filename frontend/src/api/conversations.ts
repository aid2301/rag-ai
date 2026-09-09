import { api } from './http.ts';
import { userHeaders } from './auth.ts';

// ---- Conversations ----
export interface ConvInfo {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  user_id?: string | null;
  message_count?: number;
  unanswered_count?: number;
}
export interface MsgInfo {
  id: string;
  role: string;
  content: string;
  citations: any[];
  mode: string | null;
  created_at: string;
  answer_status?: string; // answered | insufficient_knowledge | model_error | retrieval_error
  insufficient_reason?: string | null;
  in_question_library?: boolean;
  question_link?: { question_id: string; status: string } | null;
}

export const apiConv = {
  list: () => api<ConvInfo[]>('/api/conversations', { headers: userHeaders() }),
  create: (title?: string) =>
    api<ConvInfo>('/api/conversations', {
      method: 'POST',
      body: JSON.stringify({ title }),
      headers: userHeaders(),
    }),
  messages: (id: string) =>
    api<MsgInfo[]>(`/api/conversations/${id}/messages`, {
      headers: userHeaders(),
    }),
  rename: (id: string, title: string) =>
    api(`/api/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
      headers: userHeaders(),
    }),
  delete: (id: string) =>
    api(`/api/conversations/${id}`, {
      method: 'DELETE',
      headers: userHeaders(),
    }),
};
