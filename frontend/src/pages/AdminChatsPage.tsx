import { useState, useEffect } from 'react';
import {
  apiAdminUsers,
  type AdminUserInfo,
  type ConvInfo,
  type MsgInfo,
} from '../api';

interface AllConv extends ConvInfo {
  username: string;
}

export function AdminChatsPage({ initialUserId }: { initialUserId?: string | null }) {
  const [users, setUsers] = useState<AdminUserInfo[]>([]);
  const [mode, setMode] = useState<'users' | 'all'>('users');
  const [selectedUser, setSelectedUser] = useState<string | null>(
    initialUserId || null,
  );
  const [allConvs, setAllConvs] = useState<AllConv[]>([]);
  const [convs, setConvs] = useState<ConvInfo[]>([]);
  const [selectedConv, setSelectedConv] = useState<string | null>(null);
  const [messages, setMessages] = useState<MsgInfo[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    apiAdminUsers.list().then(setUsers).catch(() => {});
    apiAdminUsers
      .allConversations()
      .then(setAllConvs)
      .catch(() => setAllConvs([]));
  }, []);

  useEffect(() => {
    if (initialUserId) {
      setMode('users');
      setSelectedUser(initialUserId);
    }
  }, [initialUserId]);

  // 按用户加载对话
  useEffect(() => {
    if (mode !== 'users' || !selectedUser) {
      setConvs([]);
      setSelectedConv(null);
      setMessages([]);
      return;
    }
    setLoading(true);
    setSelectedConv(null);
    setMessages([]);
    apiAdminUsers
      .conversations(selectedUser)
      .then(setConvs)
      .catch(() => setConvs([]))
      .finally(() => setLoading(false));
  }, [mode, selectedUser]);

  // 加载消息
  useEffect(() => {
    if (!selectedConv) {
      setMessages([]);
      return;
    }
    const fetchMsgs = mode === 'users' && selectedUser
      ? apiAdminUsers.messages(selectedUser, selectedConv)
      : apiAdminUsers.conversationMessages(selectedConv);
    fetchMsgs.then(setMessages).catch(() => setMessages([]));
  }, [mode, selectedUser, selectedConv]);

  const currentUser = users.find((u) => u.id === selectedUser);
  const convList = mode === 'users' ? convs : allConvs;

  const handleSelectMode = (m: 'users' | 'all') => {
    setMode(m);
    setSelectedUser(m === 'all' ? null : selectedUser);
    setSelectedConv(null);
    setMessages([]);
  };

  return (
    <div className="flex h-full">
      {/* 左侧：用户列表 / 全部对话入口 */}
      <div className="w-52 border-r border-brand-100 bg-white flex flex-col shrink-0">
        <div className="px-4 py-3 border-b border-brand-100">
          <h1 className="text-sm font-semibold text-brand-800">对话记录</h1>
        </div>
        <div className="flex-1 overflow-y-auto py-2">
          <button
            onClick={() => handleSelectMode('all')}
            className={`w-full text-left px-4 py-2 text-sm hover:bg-brand-50 transition ${
              mode === 'all'
                ? 'bg-brand-100 text-brand-800 font-medium'
                : 'text-brand-600'
            }`}
          >
            <div className="truncate">📋 全部对话</div>
            <div className="text-xs text-brand-400">{allConvs.length} 条</div>
          </button>
          <div className="px-4 pt-3 pb-1 text-xs text-brand-400">按用户查看</div>
          {users.map((u) => (
            <button
              key={u.id}
              onClick={() => {
                handleSelectMode('users');
                setSelectedUser(u.id);
              }}
              className={`w-full text-left px-4 py-2 text-sm hover:bg-brand-50 transition ${
                mode === 'users' && selectedUser === u.id
                  ? 'bg-brand-100 text-brand-800 font-medium'
                  : 'text-brand-600'
              }`}
            >
              <div className="truncate">{u.username}</div>
              <div className="text-xs text-brand-400">
                {u.conversation_count} 个对话
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* 中间：对话列表 */}
      <div className="w-64 border-r border-brand-100 bg-white flex flex-col shrink-0">
        <div className="px-4 py-3 border-b border-brand-100">
          <div className="text-sm font-medium text-brand-800 truncate">
            {mode === 'all'
              ? '全部对话'
              : currentUser
                ? `${currentUser.username} 的对话`
                : '请选择用户'}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto py-2">
          {mode === 'users' && !selectedUser ? (
            <p className="px-4 py-2 text-xs text-brand-400">← 先选择左侧用户</p>
          ) : loading ? (
            <p className="px-4 py-2 text-xs text-brand-400">加载中…</p>
          ) : convList.length === 0 ? (
            <p className="px-4 py-2 text-xs text-brand-400">暂无对话</p>
          ) : (
            convList.map((c) => (
              <button
                key={c.id}
                onClick={() => setSelectedConv(c.id)}
                className={`w-full text-left px-4 py-2 text-sm hover:bg-brand-50 transition ${
                  selectedConv === c.id
                    ? 'bg-brand-100 text-brand-800 font-medium'
                    : 'text-brand-600'
                }`}
              >
                <div className="truncate">{c.title || '新对话'}</div>
                <div className="text-xs text-brand-400">
                  {mode === 'all' && 'username' in c ? `${c.username} · ` : ''}
                  {c.updated_at?.slice(0, 16).replace('T', ' ')} ·{' '}
                  {c.message_count ?? 0} 条
                </div>
                {(c.unanswered_count ?? 0) > 0 && (
                  <div className="text-xs text-red-500 font-medium">
                    🔴 无法回答 ×{c.unanswered_count}
                  </div>
                )}
              </button>
            ))
          )}
        </div>
      </div>

      {/* 右侧：消息内容 */}
      <div className="flex-1 min-w-0 bg-brand-50 overflow-y-auto px-4 py-4">
        {!selectedConv ? (
          <div className="h-full flex items-center justify-center text-brand-300 text-sm">
            选择左侧对话查看完整聊天记录
          </div>
        ) : messages.length === 0 ? (
          <div className="h-full flex items-center justify-center text-brand-300 text-sm">
            该对话暂无消息
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-4">
            {messages.map((m) => (
              <div
                key={m.id}
                className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`rounded-2xl px-4 py-2.5 max-w-[85%] text-sm whitespace-pre-wrap ${
                    m.role === 'user'
                      ? 'bg-brand-700 text-white'
                      : 'bg-white border border-brand-100 text-brand-800'
                  }`}
                >
                  {m.content}
                  {m.role === 'assistant' &&
                    m.answer_status === 'insufficient_knowledge' && (
                      <div className="mt-2 pt-2 border-t border-red-100 text-xs">
                        <span className="px-1.5 py-0.5 rounded bg-red-100 text-red-700 font-medium">
                          🔴 无法回答
                        </span>
                        {m.in_question_library && m.question_link && (
                          <span className="ml-1.5 px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 font-medium">
                            已提交问题库
                          </span>
                        )}
                      </div>
                    )}
                  {m.role === 'assistant' &&
                    m.answer_status === 'model_error' && (
                      <div className="mt-2 pt-2 border-t border-orange-100 text-xs">
                        <span className="px-1.5 py-0.5 rounded bg-orange-100 text-orange-700 font-medium">
                          模型错误
                        </span>
                      </div>
                    )}
                  {m.role === 'assistant' &&
                    m.answer_status === 'retrieval_error' && (
                      <div className="mt-2 pt-2 border-t border-orange-100 text-xs">
                        <span className="px-1.5 py-0.5 rounded bg-orange-100 text-orange-700 font-medium">
                          检索错误
                        </span>
                      </div>
                    )}
                  {m.role === 'assistant' &&
                    (!m.answer_status || m.answer_status === 'answered') &&
                    m.citations &&
                    m.citations.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-brand-100 text-xs text-brand-500">
                        引用 {m.citations.length} 篇文档：
                        {m.citations
                          .slice(0, 3)
                          .map((c: any) => c.document_title)
                          .join('、')}
                      </div>
                    )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
