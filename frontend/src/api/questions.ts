import { api } from './http.ts';
import { userHeaders, adminHeaders } from './auth.ts';

// ---- 问题库 ----
export interface QuestionItem {
  id: string;
  question: string;
  original_questions: string[];
  occurrence_count: number;
  status: string; // pending | processing | resolved | archived
  group_id: string | null;
  group_name: string | null;
  user_id: string | null;
  username: string;
  source_conversation_id: string | null;
  source_message_id: string | null;
  answer_status: string | null;
  model: string | null;
  assignee: string | null;
  feedback_type?: string; // insufficient | wrong_answer
  feedback_note?: string | null;
  standard_answer?: string | null;
  // M2：自动分组建议 / 复发标记
  suggested_group_id?: string | null;
  suggested_reason?: string | null;
  is_recurring?: boolean;
  created_at: string;
  updated_at: string;
  processed_at: string | null;
}

export interface QuestionDetail extends QuestionItem {
  ai_answer: string | null;
  retrieval_snapshot: Record<string, any>;
  standard_answer: string | null;
  context_source?: string; // snapshot | live | none
  context: Array<{
    id: string;
    role: string;
    content: string;
    answer_status: string | null;
    created_at: string;
  }>;
}

export interface QuestionGroup {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  question_count: number;
}

export interface QuestionListResult {
  items: QuestionItem[];
  counts: Record<string, number>;
  total: number;
}

export interface QuestionStatus {
  submitted: boolean;
  question_id: string | null;
  status?: string | null;
  standard_answer?: string | null;
  processed_at?: string | null;
  feedback_type?: string | null;
}

export const apiQuestions = {
  submit: (data: {
    question: string;
    conversation_id: string;
    message_id: string;
    ai_answer?: string;
    feedback_type?: 'insufficient' | 'wrong_answer';
    feedback_note?: string;
  }) =>
    api<{ question_id: string; created: boolean; merged: boolean }>('/api/questions', {
      method: 'POST',
      body: JSON.stringify(data),
      headers: userHeaders(),
    }),
  checkSubmitted: (messageId: string) =>
    api<QuestionStatus>(
      `/api/questions/by-message/${messageId}`,
      { headers: userHeaders() },
    ),
  list: (params?: {
    status?: string;
    group_id?: string;
    search?: string;
    date_from?: string;
    source_type?: string;
    sort?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status && params.status !== 'all') qs.set('status', params.status);
    if (params?.group_id) qs.set('group_id', params.group_id);
    if (params?.search) qs.set('search', params.search);
    if (params?.date_from) qs.set('date_from', params.date_from);
    if (params?.source_type && params.source_type !== 'all') qs.set('source_type', params.source_type);
    if (params?.sort) qs.set('sort', params.sort);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return api<QuestionListResult>(`/api/questions${q ? '?' + q : ''}`, {
      headers: adminHeaders(),
    });
  },
  get: (id: string) =>
    api<QuestionDetail>(`/api/questions/${id}`, { headers: adminHeaders() }),
  update: (
    id: string,
    data: {
      status?: string;
      standard_answer?: string;
      group_id?: string | null;
      assignee?: string;
      question?: string;
    },
  ) =>
    api<QuestionDetail>(`/api/questions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
      headers: adminHeaders(),
    }),
  remove: (id: string) =>
    api(`/api/questions/${id}`, { method: 'DELETE', headers: adminHeaders() }),
};

export const apiQuestionGroups = {
  list: () => api<QuestionGroup[]>('/api/question-groups', { headers: adminHeaders() }),
  create: (name: string) =>
    api<QuestionGroup>('/api/question-groups', {
      method: 'POST',
      body: JSON.stringify({ name }),
      headers: adminHeaders(),
    }),
  rename: (id: string, name: string) =>
    api<QuestionGroup[]>(`/api/question-groups/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
      headers: adminHeaders(),
    }),
  remove: (id: string) =>
    api(`/api/question-groups/${id}`, { method: 'DELETE', headers: adminHeaders() }),
};
