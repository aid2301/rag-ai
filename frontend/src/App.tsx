import { useCallback, useEffect, useState } from 'react';
import {
  apiAuth,
  apiConv,
  getUserInfo,
  getUserToken,
  setUserInfo,
  setUserToken,
  type ConvInfo,
  type UserInfo,
} from './api';
import { AppSidebar } from './components/AppSidebar';
import { ChatPage } from './pages/ChatPage';
import { LoginPage } from './pages/LoginPage';
import { UsagePage } from './pages/UsagePage';

type View = 'chat' | 'usage';

export default function App() {
  const [authed, setAuthed] = useState(() => !!getUserToken());
  const [checkingSession, setCheckingSession] = useState(() => !!getUserToken());
  const [user, setUser] = useState<UserInfo | null>(() => getUserInfo());
  const [view, setView] = useState<View>('chat');
  const [conversations, setConversations] = useState<ConvInfo[]>([]);
  const [currentConv, setCurrentConv] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const handleLogout = useCallback(() => {
    setUserToken(null);
    setUserInfo(null);
    setUser(null);
    setAuthed(false);
    setCheckingSession(false);
    setCurrentConv(null);
    setConversations([]);
  }, []);

  const loadConversations = useCallback(async () => {
    setConversationsLoading(true);
    try {
      setConversations(await apiConv.list());
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '对话列表加载失败');
    } finally {
      setConversationsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authed) return;
    let active = true;
    apiAuth
      .me()
      .then((info) => {
        if (!active) return;
        setUser(info);
        setUserInfo(info);
        return loadConversations();
      })
      .catch(() => {
        if (active) handleLogout();
      })
      .finally(() => {
        if (active) setCheckingSession(false);
      });
    return () => { active = false; };
  }, [authed, handleLogout, loadConversations]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 3500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const handleLogin = (info: UserInfo) => {
    setUser(info);
    setAuthed(true);
    setCheckingSession(false);
  };

  const handleDeleteConv = async (id: string) => {
    const conversation = conversations.find((item) => item.id === id);
    if (!window.confirm(`确定删除“${conversation?.title || '该对话'}”吗？删除后无法恢复。`)) return;
    try {
      await apiConv.delete(id);
      if (currentConv === id) setCurrentConv(null);
      await loadConversations();
      setNotice('对话已删除');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '删除失败，请稍后重试');
    }
  };

  if (checkingSession) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-brand-50 text-sm text-brand-500">
        <span className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-brand-300 border-t-brand-700" />
        正在恢复登录状态…
      </div>
    );
  }

  if (!authed) return <LoginPage onLogin={handleLogin} />;

  const displayName = user?.display_name || user?.username || '用户';
  return (
    <div className="flex h-dvh overflow-hidden bg-brand-50">
      <AppSidebar
        open={sidebarOpen}
        conversations={conversations}
        currentConversationId={currentConv}
        currentView={view}
        displayName={displayName}
        loading={conversationsLoading}
        onClose={() => setSidebarOpen(false)}
        onNewChat={() => { setCurrentConv(null); setView('chat'); }}
        onSelectConversation={(id) => { setCurrentConv(id); setView('chat'); }}
        onDeleteConversation={handleDeleteConv}
        onShowUsage={() => setView('usage')}
        onLogout={handleLogout}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-14 shrink-0 items-center gap-3 border-b border-brand-100 bg-white px-4 md:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded-lg border border-brand-200 p-2 text-brand-600"
            aria-label="打开导航"
          >
            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
          <span className="text-sm font-semibold text-brand-800">
            {view === 'chat' ? '企业知识助手' : '我的用量'}
          </span>
        </div>
        <div className="min-h-0 flex-1">
          {view === 'chat' ? (
            <ChatPage
              conversationId={currentConv}
              onConversationCreated={(id) => {
                if (id) setCurrentConv(id);
                void loadConversations();
              }}
            />
          ) : <UsagePage />}
        </div>
      </main>

      {notice && (
        <div className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-brand-900 px-4 py-2.5 text-sm text-white shadow-xl" role="status">
          {notice}
        </div>
      )}
    </div>
  );
}
