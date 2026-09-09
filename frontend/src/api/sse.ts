import type { ChatResult, StreamMeta, StreamStage } from './chat.ts';

type ChatEvent = string | ChatResult | StreamMeta | StreamStage;

/** Decode SSE across arbitrary network/UTF-8 boundaries and release the reader. */
export async function* parseChatStream(body: ReadableStream<Uint8Array>): AsyncGenerator<ChatEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let exhausted = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      exhausted = done;
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      let boundary: RegExpExecArray | null;
      while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
        const raw = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary[0].length);
        const payload = raw.split(/\r?\n/)
          .filter(line => line.startsWith('data:'))
          .map(line => line.slice(5).replace(/^ /, '')).join('\n');
        if (!payload.trim()) continue;
        let obj: any;
        try { obj = JSON.parse(payload); } catch { continue; }
        if (!obj || typeof obj !== 'object') continue;
        if (obj.type === 'meta') {
          yield { type: 'meta', conversation_id: obj.conversation_id || undefined, mode: obj.mode || undefined };
        } else if (obj.type === 'stage') {
          yield { type: 'stage', stage: obj.stage || undefined, label: obj.label || undefined };
        } else if (obj.type === 'delta' && obj.text) {
          yield obj.text;
        } else if (obj.type === 'done' || obj.type === 'error') {
          const error = obj.type === 'error';
          yield {
            answer: (error ? obj.message : obj.answer) || '',
            citations: error ? [] : obj.citations || [],
            mode: error ? '' : obj.mode || '',
            validation: error ? null : obj.validation || null,
            token_usage: error ? [] : obj.token_usage || [],
            debug: error ? null : obj.trace || null,
            error,
            answer_status: obj.answer_status || (error ? 'model_error' : 'answered'),
            insufficient_reason: obj.insufficient_reason || null,
            message_id: obj.message_id || null,
          };
          return;
        }
      }
      if (done) throw new Error('回答流意外中断，请重试');
    }
  } finally {
    try { if (!exhausted) await reader.cancel(); }
    finally { reader.releaseLock(); }
  }
}
