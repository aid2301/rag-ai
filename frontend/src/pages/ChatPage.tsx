import { useState, useRef, useEffect, useCallback } from 'react';
import {
  apiChat,
  apiConv,
  apiQuestions,
  apiSettings,
  type ChatResult,
  type StreamMeta,
} from '../api';
import {
  ChatMessage,
  type ChatMessageData,
} from '../components/chat/ChatMessage';

type ChatMessageState = ChatMessageData;

export function ChatPage({
  conversationId,
  onConversationCreated,
}: {
  conversationId: string | null;
  onConversationCreated: (id: string) => void;
}) {
  const [messages, setMessages] = useState<ChatMessageState[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [convId, setConvId] = useState<string | null>(conversationId);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  // 流式进行中标志：阻止 conversationId 变化触发的历史重载打断正在流式的 UI（P1-2）
  const streamingRef = useRef(false);
  // 思考过程开关：默认取后台设置，用户可本地切换（localStorage 覆盖）
  const [showThink, setShowThink] = useState<boolean>(() => {
    const saved = localStorage.getItem('kb_show_think');
    return saved ? saved === '1' : false;
  });

  useEffect(() => {
    apiSettings
      .public()
      .then((s) => {
        const saved = localStorage.getItem('kb_show_think');
        if (saved === null) setShowThink(s.show_thinking);
      })
      .catch(() => {});
  }, []);

  const toggleThink = () => {
    setShowThink((prev) => {
      const next = !prev;
      localStorage.setItem('kb_show_think', next ? '1' : '0');
      return next;
    });
  };

  useEffect(() => {
    // 流式期间跳过历史重载：新对话首条消息的 meta 回传会触发 conversationId 变化，
    // 若此时重新拉取历史并 setMessages 会清空正在流式的 assistant 占位（P1-2）
    if (streamingRef.current) return;
    let active = true;
    setConvId(conversationId);
    if (conversationId) {
      setHistoryLoading(true);
      apiConv.messages(conversationId).then((msgs) => {
        if (!active) return;
        const list: ChatMessageState[] = msgs.map((m) => ({
          role: m.role as 'user' | 'assistant',
          content: m.content,
          citations: m.citations,
          answer_status: m.answer_status || 'answered',
          message_id: m.id,
        }));
        setMessages(list);
        // 回显问题库提交状态：insufficient → 已提交；answered+wrong_answer → 已反馈
        list
          .filter((m) => m.role === 'assistant' && m.message_id)
          .forEach((m) => {
            apiQuestions.checkSubmitted(m.message_id!).then((res) => {
              if (active && res.submitted) {
                setMessages((prev) =>
                  prev.map((p) =>
                    p.message_id === m.message_id
                      ? {
                          ...p,
                          submitted: res.feedback_type === 'wrong_answer' ? false : true,
                          feedbacked: res.feedback_type === 'wrong_answer' ? true : false,
                          question_status: res.status,
                          standard_answer: res.standard_answer,
                        }
                      : p,
                  ),
                );
              }
            }).catch(() => {});
          });
      }).catch(() => {
        if (!active) return;
        setMessages([]);
        setNotice('历史消息加载失败，请稍后重试');
      }).finally(() => {
        if (active) setHistoryLoading(false);
      });
    } else {
      setMessages([]);
      setHistoryLoading(false);
    }
    return () => { active = false; };
  }, [conversationId]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 3200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    const element = inputRef.current;
    if (!element) return;
    element.style.height = '0px';
    element.style.height = `${Math.min(element.scrollHeight, 128)}px`;
  }, [input]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // 已提交问题的处理进度查询；定义在提交回调之前，保持依赖关系清晰。
  const pollQuestionStatus = useCallback((messageId: string) => {
    apiQuestions.checkSubmitted(messageId).then((res) => {
      if (!res.submitted) return;
      setMessages((prev) =>
        prev.map((item) =>
          item.message_id === messageId
            ? {
                ...item,
                submitted: res.feedback_type !== 'wrong_answer',
                feedbacked: res.feedback_type === 'wrong_answer',
                question_status: res.status,
                standard_answer: res.standard_answer,
              }
            : item,
        ),
      );
    }).catch(() => {});
  }, []);

  const handleSubmitQuestion = useCallback(
    async (
      msg: ChatMessageState,
      userQuestion: string,
      feedbackType: 'insufficient' | 'wrong_answer' = 'insufficient',
      feedbackNote?: string,
    ) => {
      if (!msg.message_id) {
        setNotice('该回答暂无法提交，请刷新后重试');
        return;
      }
      if (!convId || msg.submitted || msg.feedbacked || msg.submitting || msg.feedbacking) return;
      const patch: Partial<ChatMessageState> =
        feedbackType === 'wrong_answer'
          ? { feedbacking: true }
          : { submitting: true };
      setMessages((prev) =>
        prev.map((p) =>
          p.message_id === msg.message_id ? { ...p, ...patch } : p,
        ),
      );
      try {
        const res = await apiQuestions.submit({
          question: userQuestion,
          conversation_id: convId,
          message_id: msg.message_id,
          ai_answer: msg.content,
          feedback_type: feedbackType,
          feedback_note: feedbackNote,
        });
        setMessages((prev) =>
          prev.map((p) =>
            p.message_id === msg.message_id
              ? {
                  ...p,
                  ...(feedbackType === 'wrong_answer'
                    ? { feedbacked: true, feedbacking: false, question_status: res ? 'pending' : null }
                    : { submitted: true, submitting: false, question_status: res ? 'pending' : null }),
                }
              : p,
          ),
        );
        if (res.created) {
          setNotice(feedbackType === 'wrong_answer' ? '已反馈给管理员，感谢纠错' : '问题已提交给管理员');
        } else {
          setNotice(feedbackType === 'wrong_answer' ? '该回答已反馈过' : '该问题已提交过');
        }
        // 提交后轮询一次处理进度
        pollQuestionStatus(msg.message_id!);
      } catch (err: any) {
        setMessages((prev) =>
          prev.map((p) =>
            p.message_id === msg.message_id
              ? {
                  ...p,
                  ...(feedbackType === 'wrong_answer'
                    ? { feedbacking: false }
                    : { submitting: false }),
                }
              : p,
          ),
        );
        setNotice('提交失败：' + err.message);
      }
    },
    [convId, pollQuestionStatus],
  );

  // M1-Q02：对已提交/已反馈的消息做轻量轮询（30s），直到 resolved/archived 停止
  useEffect(() => {
    const pendingIds = messages
      .filter(
        (m) =>
          m.role === 'assistant' &&
          (m.submitted || m.feedbacked) &&
          m.message_id &&
          m.question_status !== 'resolved' &&
          m.question_status !== 'archived',
      )
      .map((m) => m.message_id!);
    if (pendingIds.length === 0) return;
    const timer = setInterval(() => {
      pendingIds.forEach((id) => pollQuestionStatus(id));
    }, 30000);
    return () => clearInterval(timer);
  }, [messages, pollQuestionStatus]);

  const handleSend = useCallback(async () => {
    const query = input.trim();
    if (!query || loading) return;

    streamingRef.current = true;
    setInput('');
    setLoading(true);
    setMessages((prev) => [...prev, { role: 'user', content: query }]);

    // 占位 streaming message
    setMessages((prev) => [
      ...prev,
      { role: 'assistant', content: '', streaming: true },
    ]);

    try {
      const { stream, cancel } = apiChat.stream(query, convId || undefined);
      cancelRef.current = cancel;
      let full = '';
      let result: ChatResult | null = null;

      for await (const chunk of stream) {
        if (typeof chunk === 'string') {
          full += chunk;
          setMessages((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = {
              role: 'assistant',
              content: full,
              streaming: true,
            };
            return copy;
          });
        } else if (typeof chunk === 'object' && (chunk as StreamMeta).type === 'meta') {
          // 服务端首帧 meta：回传会话 id，保证后续多轮与「提交给管理员」使用同一会话
          const meta = chunk as StreamMeta;
          if (meta.conversation_id) {
            setConvId(meta.conversation_id);
            onConversationCreated(meta.conversation_id);
          }
        } else if (typeof chunk === 'object' && (chunk as any).stage) {
          const st = (chunk as any).stage as string;
          const label = (chunk as any).label as string;
          setMessages((prev) => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last && last.role === 'assistant') {
              copy[copy.length - 1] = { ...last, stage: label };
            }
            return copy;
          });
          void st;
        } else {
          result = chunk as ChatResult;
        }
      }

      // stream 结束后取最终结果
      const finalResult = result;
      setMessages((prev) => {
        const copy = [...prev];
        copy[copy.length - 1] = {
          role: 'assistant',
          content: finalResult?.answer || full,
          citations: finalResult?.citations || [],
          streaming: false,
          error: finalResult?.error || false,
          answer_status: finalResult?.answer_status || 'answered',
          message_id: finalResult?.message_id || null,
          stage: undefined,
          execution: finalResult
            ? {
                mode: finalResult.mode,
                answer_status: finalResult.answer_status,
                trace: finalResult.debug,
                token_usage: finalResult.token_usage,
                citations: finalResult.citations,
              }
            : null,
        };
        return copy;
      });

      if (finalResult?.answer && !convId) {
        // 新对话，后端会创建 conversation
        // 刷新对话列表
        onConversationCreated('');
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setMessages((prev) => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          copy[copy.length - 1] = {
            ...last,
            content: last.content + '\n\n（已停止生成）',
            streaming: false,
          };
          return copy;
        });
      } else {
        setMessages((prev) => {
          const copy = [...prev];
          copy[copy.length - 1] = {
            role: 'assistant',
            content: `抱歉，处理请求时出错：${err.message}`,
            streaming: false,
            error: true,
          };
          return copy;
        });
      }
    } finally {
      streamingRef.current = false;
      setLoading(false);
      cancelRef.current = null;
    }
  }, [input, loading, convId, onConversationCreated]);

  const handleStop = () => {
    cancelRef.current?.();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="hidden items-center justify-between border-b border-brand-100 bg-white/90 px-6 py-3 backdrop-blur md:flex">
        <div>
          <h1 className="text-base font-semibold text-brand-800">企业知识助手</h1>
          <p className="mt-0.5 text-xs text-brand-400">回答均基于内部知识库，可展开查看引用依据</p>
        </div>
        <button
          onClick={toggleThink}
          title="显示/隐藏思考过程（不消耗额外 Token）"
          className={`px-2.5 py-1 rounded-lg text-xs border transition ${
            showThink
              ? 'bg-brand-700 text-white border-brand-700'
              : 'border-brand-200 text-brand-500 hover:bg-brand-50'
          }`}
        >
          {showThink ? '思考过程：开' : '思考过程：关'}
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-5 md:px-6 md:py-6">
        {historyLoading ? (
          <div className="mx-auto max-w-3xl space-y-4 pt-8" aria-label="正在加载历史消息">
            <div className="h-14 w-2/3 animate-pulse rounded-2xl bg-brand-100" />
            <div className="ml-auto h-12 w-1/2 animate-pulse rounded-2xl bg-brand-200" />
            <div className="h-24 w-4/5 animate-pulse rounded-2xl bg-brand-100" />
          </div>
        ) : messages.length === 0 && (
          <div className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center py-8 text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-white shadow-sm ring-1 ring-brand-100">
              <img src="/logo.svg" alt="" className="h-7 w-7" />
            </div>
            <h2 className="text-xl font-semibold tracking-tight text-brand-900">今天想了解什么？</h2>
            <p className="mt-2 max-w-md text-sm leading-6 text-brand-500">
              我会从企业知识库中查找依据、组织答案，并标注可追溯的来源。
            </p>
            <div className="mt-7 grid w-full max-w-2xl gap-2 sm:grid-cols-2">
              {['星桥项目什么时候演示？', '演示样品可以借用多久？', '总结已上传资料的主要内容', '这些资料有哪些需要核实的差异？'].map((question) => (
                <button
                  key={question}
                  onClick={() => {
                    setInput(question);
                    window.setTimeout(() => inputRef.current?.focus(), 0);
                  }}
                  className="rounded-xl border border-brand-200 bg-white px-4 py-3 text-left text-sm text-brand-700 shadow-sm transition hover:-translate-y-0.5 hover:border-brand-300 hover:shadow-md"
                >
                  <span className="mr-2 text-brand-400">↗</span>{question}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className={`mx-auto max-w-3xl space-y-4 ${historyLoading ? 'hidden' : ''}`}>
          {messages.map((msg, i) => {
            // 找该 assistant 消息之前的最近一条用户消息作为原始提问
            let userQuestion = '';
            for (let j = i - 1; j >= 0; j--) {
              if (messages[j].role === 'user') {
                userQuestion = messages[j].content;
                break;
              }
            }
            return (
              <ChatMessage
                key={msg.message_id || i}
                msg={msg}
                userQuestion={userQuestion}
                onSubmit={handleSubmitQuestion}
                showThink={showThink}
              />
            );
          })}
        </div>
      </div>

      {/* Input */}
      <div className="border-t border-brand-100 bg-white px-3 py-3 md:px-6 md:py-4">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-end gap-2 rounded-2xl border border-brand-200 bg-brand-50 p-1.5 shadow-sm transition focus-within:border-brand-300 focus-within:bg-white focus-within:ring-2 focus-within:ring-brand-100">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入问题，Enter 发送，Shift+Enter 换行"
              rows={1}
              className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-3 py-2 text-sm leading-6 text-brand-800 placeholder:text-brand-400 focus:outline-none"
              style={{ minHeight: '40px' }}
              aria-label="输入问题"
            />
            {loading ? (
              <button
                onClick={handleStop}
                className="shrink-0 rounded-xl bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600 transition hover:bg-red-100"
              >
                停止
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!input.trim()}
                className="shrink-0 rounded-xl bg-brand-800 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-900 disabled:cursor-not-allowed disabled:opacity-30"
              >
                发送
              </button>
            )}
          </div>
          <p className="mt-2 text-center text-[11px] text-brand-400">AI 回答可能存在偏差，重要信息请结合引用原文核对</p>
        </div>
      </div>
      {notice && (
        <div className="fixed bottom-24 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-brand-900 px-4 py-2.5 text-sm text-white shadow-xl" role="status">
          {notice}
        </div>
      )}
    </div>
  );
}
