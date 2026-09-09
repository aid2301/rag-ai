import { useState } from 'react';
import type { Citation } from '../../api';
import { Citations } from '../Citations';
import { Markdown } from '../Markdown';

export interface ChatMessageData {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  streaming?: boolean;
  error?: boolean;
  answer_status?: string;
  message_id?: string | null;
  submitted?: boolean;
  submitting?: boolean;
  feedbacked?: boolean;
  feedbacking?: boolean;
  question_status?: string | null;
  standard_answer?: string | null;
  stage?: string;
  execution?: any;
}

interface Props {
  msg: ChatMessageData;
  userQuestion: string;
  showThink: boolean;
  onSubmit: (
    msg: ChatMessageData,
    userQuestion: string,
    feedbackType?: 'insufficient' | 'wrong_answer',
    feedbackNote?: string,
  ) => void;
}

export function ChatMessage({ msg, userQuestion, onSubmit, showThink }: Props) {
  const isUser = msg.role === 'user';
  const insufficient =
    !isUser && !msg.streaming && msg.answer_status === 'insufficient_knowledge';
  const isAnswered =
    !isUser && !msg.streaming && msg.answer_status === 'answered' && !msg.error;
  const showWrongFeedback = isAnswered && !msg.feedbacked && !msg.submitted;
  const showProgress = (msg.submitted || msg.feedbacked) && !msg.streaming;
  const qStatusLabel: Record<string, string> = {
    pending: '已提交，待处理',
    processing: '处理中',
    resolved: '已解答',
    archived: '已归档',
  };

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[92%] rounded-2xl px-4 py-3 shadow-sm md:max-w-[85%] ${
          isUser
            ? 'rounded-br-md bg-brand-800 text-white'
            : msg.error
              ? 'border border-red-200 bg-red-50 text-red-700'
              : insufficient
                ? 'border border-amber-200 bg-amber-50 text-brand-800'
                : 'rounded-bl-md border border-brand-100 bg-white text-brand-800'
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap text-sm leading-6">{msg.content}</p>
        ) : (
          <>
            <div className="text-sm leading-6">
              {msg.content ? (
                <Markdown content={msg.content} />
              ) : msg.streaming ? (
                <span className="text-brand-400 animate-pulse">正在查找相关资料…</span>
              ) : null}
              {msg.streaming && msg.content && (
                <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-brand-400 align-middle" />
              )}
            </div>
            {msg.streaming && msg.stage && (
              <div className="mt-2 flex items-center gap-1.5 text-xs text-brand-400" aria-live="polite">
                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-brand-300 border-t-transparent" />
                {msg.stage}
              </div>
            )}
            {!msg.streaming && msg.citations && msg.citations.length > 0 && (
              <Citations citations={msg.citations} />
            )}
            {showThink && !msg.streaming && msg.execution && (
              <ThinkingPanel execution={msg.execution} />
            )}
            {showProgress && (
              <div className="mt-2 border-t border-brand-100 pt-2 text-xs">
                <span
                  className={`inline-block rounded-full px-2.5 py-1 font-medium ${
                    msg.question_status === 'resolved'
                      ? 'bg-green-100 text-green-700'
                      : msg.question_status === 'processing'
                        ? 'bg-blue-100 text-blue-700'
                        : msg.question_status === 'archived'
                          ? 'bg-brand-100 text-brand-500'
                          : 'bg-amber-100 text-amber-700'
                  }`}
                >
                  {msg.feedbacked
                    ? msg.question_status === 'resolved'
                      ? '反馈已处理'
                      : '反馈已提交'
                    : qStatusLabel[msg.question_status || 'pending'] || '已提交'}
                </span>
                {msg.question_status === 'resolved' && msg.standard_answer && (
                  <div className="mt-2 whitespace-pre-wrap rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-brand-700">
                    <div className="mb-1 font-medium text-green-700">管理员解答</div>
                    {msg.standard_answer}
                  </div>
                )}
              </div>
            )}
            {insufficient && !msg.submitted && (
              <div className="mt-2 border-t border-amber-200 pt-2 text-xs">
                <div className="mb-2 text-amber-700">当前知识库暂无相关信息</div>
                <button
                  onClick={() => onSubmit(msg, userQuestion, 'insufficient')}
                  disabled={msg.submitting}
                  className="rounded-lg bg-amber-600 px-3 py-1.5 font-medium text-white transition hover:bg-amber-700 disabled:opacity-40"
                >
                  {msg.submitting ? '提交中…' : '提交给管理员'}
                </button>
              </div>
            )}
            {showWrongFeedback && (
              <div className="mt-2 border-t border-brand-100 pt-2 text-xs">
                <button
                  onClick={() => onSubmit(msg, userQuestion, 'wrong_answer')}
                  disabled={msg.feedbacking}
                  className="rounded-lg border border-brand-200 px-2.5 py-1.5 text-brand-500 transition hover:bg-brand-50 hover:text-brand-700 disabled:opacity-40"
                >
                  {msg.feedbacking ? '反馈中…' : '回答有误？'}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function ThinkingPanel({ execution }: { execution: any }) {
  const [open, setOpen] = useState(false);
  const steps = Array.isArray(execution?.trace) ? execution.trace : [];
  const usage = Array.isArray(execution?.token_usage) ? execution.token_usage : [];
  const totalTokens = usage.reduce((sum: number, item: any) => sum + (item.total_tokens || 0), 0);
  const modeLabel: Record<string, string> = { fast: '快速', standard: '标准', deep: '深度' };
  const statusLabel: Record<string, string> = {
    answered: '已回答',
    insufficient_knowledge: '知识不足',
    model_error: '模型错误',
    retrieval_error: '检索错误',
  };
  const stepName: Record<string, string> = {
    query_analyzer: '理解问题',
    query_rewriter: '改写问题',
    retrieval: '检索知识库',
    document_selector: '筛选文档',
    reranker: '章节重排',
    context: '组织证据',
    answer: '生成回答',
    evidence_validator: '事实校验',
    answerability: '可回答性判断',
  };

  return (
    <div className="mt-2 border-t border-brand-100 pt-2 text-xs">
      <button
        onClick={() => setOpen(!open)}
        className="font-medium text-brand-500 hover:text-brand-700"
        aria-expanded={open}
      >
        {open ? '▾' : '▸'} 思考过程与执行详情
        <span className="ml-1.5 text-brand-400">
          {modeLabel[execution.mode] || execution.mode || '标准'}模式 ·{' '}
          {statusLabel[execution.answer_status] || execution.answer_status} · {steps.length} 步 ·{' '}
          {usage.length} 次调用 · {totalTokens.toLocaleString()} tokens
        </span>
      </button>
      {open && (
        <div className="mt-2 space-y-1.5">
          {steps.map((step: any, index: number) => (
            <div key={index} className="rounded-lg bg-brand-50 px-2.5 py-2">
              <div className="font-medium text-brand-700">
                {index + 1}. {stepName[step.name] || step.name}
              </div>
              <div className="break-all whitespace-pre-wrap text-brand-500">{formatStep(step)}</div>
            </div>
          ))}
          {steps.length === 0 && <p className="text-brand-400">（无执行记录）</p>}
        </div>
      )}
    </div>
  );
}

function formatStep(step: any): string {
  const data = step?.data;
  if (!data) return '';
  if (step.name === 'retrieval') {
    const docs = data.candidate_documents || [];
    const sections = data.candidate_sections || [];
    return `候选文档 ${docs.length} 篇：${docs
      .map((item: any) => `${item.title}（${item.score}）`)
      .join('、')}${sections.length ? `；候选章节 ${sections.length} 个` : ''}`;
  }
  if (step.name === 'document_selector' && Array.isArray(data)) {
    return data
      .map((item: any) => `${(item.document_id || '').slice(0, 8)}${item.reason ? `：${item.reason}` : ''}`)
      .join('；');
  }
  if (step.name === 'context') {
    return `上下文 ${data.used_chars || 0} 字${data.truncated ? '（已截断）' : ''}`;
  }
  if (step.name === 'answer') return `生成 ${data.chars || 0} 字`;
  if (step.name === 'answerability') {
    return `${data.answer_status || ''}${data.reason ? `：${data.reason}` : ''}`;
  }
  if (step.name === 'query_rewriter') return `改写为：${data.standalone_query || ''}`;
  if (typeof data === 'string') return data.slice(0, 200);
  try {
    return JSON.stringify(data)?.slice(0, 200) || '';
  } catch {
    return '';
  }
}
