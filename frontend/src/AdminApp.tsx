import { useState, useEffect } from 'react';
import {
  apiAdmin,
  apiAdminOverview,
  getAdminToken,
  setAdminToken,
  type AdminOverview,
} from './api';
import { SettingsPage } from './pages/SettingsPage';
import { AdminUsersPage } from './pages/AdminUsersPage';
import { AdminUsagePage } from './pages/AdminUsagePage';
import { AdminChatsPage } from './pages/AdminChatsPage';
import { AdminQuestionsPage } from './pages/AdminQuestionsPage';
import { DocumentsPage } from './pages/DocumentsPage';
import { LoginForm } from './components/LoginForm';

type Tab = 'users' | 'usage' | 'chats' | 'questions' | 'documents' | 'settings';

/** 管理后台：用户管理、用量统计、对话记录、知识库、LLM 配置。通过 #/admin 访问，需管理员账号密码。 */
export function AdminApp() {
  const [authed, setAuthed] = useState<boolean>(() => !!getAdminToken());

  const [tab, setTab] = useState<Tab>('users');
  const [chatTarget, setChatTarget] = useState<{
    userId: string;
    username: string;
  } | null>(null);
  const [overview, setOverview] = useState<AdminOverview | null>(null);

  // 后台概览计数（问题库 Badge / 待处理提示），登录后与切换 tab 时刷新
  useEffect(() => {
    if (authed) {
      apiAdminOverview
        .get()
        .then(setOverview)
        .catch(() => setOverview(null));
    }
  }, [authed, tab]);

  const handleLogin = async (username: string, password: string) => {
    const res = await apiAdmin.login(username.trim(), password.trim());
    setAdminToken(res.token);
    setAuthed(true);
    return true;
  };

  const handleLogout = () => {
    setAdminToken('');
    setAuthed(false);
  };

  if (!authed) {
    return (
      <div className="min-h-screen bg-brand-50 flex items-center justify-center p-4">
        <div className="w-full max-w-sm bg-white rounded-xl border border-brand-100 p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-6">
            <img src="/logo.svg" alt="管理后台" className="w-6 h-6" />
            <div>
              <h1 className="font-semibold text-brand-800">管理后台</h1>
              <p className="text-xs text-brand-400">
                用户管理 · 用量统计 · 对话记录
              </p>
            </div>
          </div>

          <LoginForm
            usernamePlaceholder="admin"
            hint={
              <>
                默认账号 <code className="bg-brand-50 px-1 rounded">admin</code>，
                默认密码 <code className="bg-brand-50 px-1 rounded">admin123</code>。
                建议通过环境变量修改默认密码。
              </>
            }
            onSubmit={handleLogin}
          />
        </div>
      </div>
    );
  }

  const pendingCount = overview?.pending_questions ?? 0;
  const tabs: { key: Tab; label: string; badge?: number; badgeRed?: boolean }[] = [
    { key: 'users', label: '用户管理' },
    { key: 'usage', label: '用量统计' },
    { key: 'chats', label: '对话记录' },
    { key: 'questions', label: '问题库', badge: pendingCount, badgeRed: true },
    { key: 'documents', label: '知识库' },
    { key: 'settings', label: 'LLM 设置' },
  ];

  return (
    <div className="min-h-screen bg-brand-50">
      <header className="bg-white border-b border-brand-100">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 md:px-6">
          <div className="flex items-center gap-2">
            <img src="/logo.svg" alt="管理后台" className="w-5 h-5" />
            <span className="font-semibold text-brand-800 text-sm">管理后台</span>
            <span className="text-xs text-brand-400">· 用户 / 用量 / 对话 / 知识库</span>
          </div>
          <button
            onClick={handleLogout}
            className="text-sm text-brand-500 hover:text-brand-700 transition"
          >
            退出登录
          </button>
        </div>
        <div className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 md:px-6">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm transition md:px-4 ${
                tab === t.key
                  ? 'border-brand-600 text-brand-800 font-medium'
                  : 'border-transparent text-brand-400 hover:text-brand-600'
              }`}
            >
              {t.label}
              {t.badge !== undefined && t.badge > 0 && (
                <span
                  className={`px-1.5 py-0.5 rounded-full text-[10px] leading-none font-bold ${
                    t.badgeRed
                      ? 'bg-red-500 text-white'
                      : 'bg-brand-100 text-brand-600'
                  }`}
                >
                  {t.badge}
                </span>
              )}
            </button>
          ))}
        </div>
      </header>
      <main className="mx-auto h-[calc(100vh-104px)] max-w-7xl overflow-auto px-4 py-5 md:px-6 md:py-6">
        {tab === 'users' && (
          <AdminUsersPage
            onViewChats={(userId, uname) => {
              setChatTarget({ userId, username: uname });
              setTab('chats');
            }}
          />
        )}
        {tab === 'usage' && <AdminUsagePage />}
        {tab === 'chats' && (
          <AdminChatsPage
            key={chatTarget?.userId || 'all'}
            initialUserId={chatTarget?.userId}
          />
        )}
        {tab === 'questions' && <AdminQuestionsPage />}
        {tab === 'documents' && <DocumentsPage />}
        {tab === 'settings' && <SettingsPage embedded />}
      </main>
    </div>
  );
}
