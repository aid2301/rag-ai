import { test } from 'node:test';
import assert from 'node:assert/strict';
import { apiChat } from '../src/api/chat.ts';
import { parseChatStream } from '../src/api/sse.ts';

const encode = new TextEncoder();
const frame = (obj, eol = '\n') => 'data: ' + JSON.stringify(obj) + eol + eol;
const collect = async stream => { const out = []; for await (const event of stream) out.push(event); return out; };
function body(text, chunkSize = 1, onCancel = () => {}) {
  const bytes = encode.encode(text);
  let offset = 0;
  return new ReadableStream({
    pull(controller) {
      if (offset === bytes.length) return controller.close();
      controller.enqueue(bytes.slice(offset, offset + chunkSize));
      offset = Math.min(offset + chunkSize, bytes.length);
    },
    cancel: onCancel,
  });
}

test('chat API sends query and decodes Chinese across byte boundaries', async t => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/chat/stream');
    assert.deepEqual(JSON.parse(options.body), { query: '问题', mode: 'fast' });
    return new Response(body(frame({ type: 'meta', conversation_id: 'c1' }) +
      frame({ type: 'stage', stage: 'answer', label: '生成中' }) +
      frame({ type: 'delta', text: '中文答案' }) +
      frame({ type: 'done', answer: '中文答案', message_id: 'm1' })));
  });
  const out = await collect(apiChat.stream('问题', undefined, 'fast').stream);
  assert.equal(out[0].conversation_id, 'c1');
  assert.equal(out[1].stage, 'answer');
  assert.equal(out[2], '中文答案');
  assert.equal(out[3].message_id, 'm1');
  assert.equal(out[3].error, false);
});

test('CRLF events and data without optional space are supported', async () => {
  const text = ': keepalive\r\n\r\n' + frame({ type: 'done', answer: 'ok' }, '\r\n').replace('data: ', 'data:');
  assert.equal((await collect(parseChatStream(body(text))))[0].answer, 'ok');
});

test('error retains message metadata and terminates the stream', async () => {
  const out = await collect(parseChatStream(body(frame({ type: 'error', message: '失败', answer_status: 'retrieval_error', message_id: 'err1' }) + frame({ type: 'done', answer: 'must not appear' }), 4096)));
  assert.equal(out.length, 1);
  assert.equal(out[0].message_id, 'err1');
  assert.equal(out[0].answer_status, 'retrieval_error');
  assert.equal(out[0].error, true);
});

test('done ignores duplicate terminal events and releases reader', async () => {
  let cancelled = false;
  const stream = body(frame({ type: 'done', answer: 'one' }) + frame({ type: 'done', answer: 'two' }), 50, () => { cancelled = true; });
  assert.equal((await collect(parseChatStream(stream))).length, 1);
  assert.equal(stream.locked, false);
  assert.equal(cancelled, true);
});

test('malformed and unknown events do not hide a valid terminal event', async () => {
  const text = 'data: invalid\n\ndata: null\n\n' + frame({ type: 'unknown' }) + frame({ type: 'done', answer: 'ok' });
  assert.equal((await collect(parseChatStream(body(text))))[0].answer, 'ok');
});

test('truncated stream reports failure instead of silent success', async () => {
  const stream = body(frame({ type: 'delta', text: 'partial' }));
  await assert.rejects(collect(parseChatStream(stream)), /意外中断/);
  assert.equal(stream.locked, false);
});

test('cancellation aborts the underlying API request', async t => {
  t.mock.method(globalThis, 'fetch', (_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
  }));
  const request = apiChat.stream('cancel');
  const next = request.stream.next();
  request.cancel();
  await assert.rejects(next, { name: 'AbortError' });
});
