import { parseChatStream } from './sse.ts';
import { api, BASE } from './http.ts';
import { userHeaders } from './auth.ts';

// ---- Chat ----
export interface Citation {
  index: number;
  document_id: string;
  document_title: string;
  section: string;
  page: number | null;
}
export interface ChatResult {
  answer: string;
  citations: Citation[];
  mode: string;
  validation: any;
  token_usage: any[];
  debug: any;
  error: boolean;
  answer_status: string; // answered | insufficient_knowledge | model_error | retrieval_error
  insufficient_reason?: string | null;
  message_id?: string | null;
}

/** SSE 首帧 meta 事件：携带服务端创建的 conversation_id（用于新对话链路回传）。 */
export interface StreamMeta {
  type: 'meta';
  conversation_id?: string;
  mode?: string;
}

/** SSE stage 事件：思考过程阶段标签（理解/检索/筛选/生成/校验）。 */
export interface StreamStage {
  type: 'stage';
  stage?: string;
  label?: string;
}

export const apiChat = {
  send: (query: string, conversationId?: string, mode?: string) =>
    api<ChatResult>('/api/chat', {
      method: 'POST',
      headers: userHeaders(),
      body: JSON.stringify({
        query,
        conversation_id: conversationId,
        mode,
      }),
    }),
  stream: (
    query: string,
    conversationId?: string,
    mode?: string,
  ): {
    stream: AsyncGenerator<string | ChatResult | StreamMeta | StreamStage, void, unknown>;
    cancel: () => void;
  } => {
    const ctrl = new AbortController();
    const stream = (async function* () {
      const res = await fetch(`${BASE}/api/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...userHeaders(),
        },
        body: JSON.stringify({
          query,
          conversation_id: conversationId,
          mode,
        }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) throw new Error('Stream failed');
      yield* parseChatStream(res.body);
    })();
    return { stream, cancel: () => ctrl.abort() };
  },
};
