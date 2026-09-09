import type { ConvInfo } from '../api';

interface Props {
  open: boolean;
  conversations: ConvInfo[];
  currentConversationId: string | null;
  currentView: 'chat' | 'usage';
  displayName: string;
  loading?: boolean;
  onClose: () => void;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onShowUsage: () => void;
  onLogout: () => void;
}

export function AppSidebar({
  open,
  conversations,
  currentConversationId,
  currentView,
  displayName,
  loading,
  onClose,
  onNewChat,
  onSelectConversation,
  onDeleteConversation,
  onShowUsage,
  onLogout,
}: Props) {
  return (
    <>
      {open && (
        <button
          className="fixed inset-0 z-30 bg-brand-900/30 backdrop-blur-[1px] md:hidden"
          onClick={onClose}
          aria-label="关闭导航"
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 shrink-0 flex-col border-r border-brand-100 bg-white shadow-xl transition-transform duration-200 md:static md:w-64 md:translate-x-0 md:shadow-none ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex h-16 items-center justify-between px-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-800 shadow-sm">
              <img src="/logo.svg" alt="" className="h-5 w-5 brightness-0 invert" />
            </div>
            <div>
              <div className="text-sm font-semibold text-brand-900">企业知识助手</div>
              <div className="text-[11px] text-brand-400">可靠、可溯源的内部问答</div>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 text-brand-400 hover:bg-brand-50 md:hidden" aria-label="关闭导航">×</button>
        </div>

        <div className="px-3 pb-2">
          <button
            onClick={() => { onNewChat(); onClose(); }}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-800 px-3 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-300"
          >
            <span className="text-lg leading-none">＋</span>新建对话
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-2">
          <div className="mb-1 flex items-center justify-between px-2">
            <span className="text-xs font-medium text-brand-400">最近对话</span>
            {conversations.length > 0 && <span className="text-[10px] text-brand-300">{conversations.length}</span>}
          </div>
          {loading ? (
            <div className="space-y-2 px-2 py-2" aria-label="正在加载对话">
              {[0, 1, 2].map((item) => <div key={item} className="h-8 animate-pulse rounded-lg bg-brand-100" />)}
            </div>
          ) : conversations.length === 0 ? (
            <div className="mx-2 mt-2 rounded-xl border border-dashed border-brand-200 px-3 py-5 text-center text-xs leading-5 text-brand-400">
              暂无历史对话<br />发送第一个问题后会显示在这里
            </div>
          ) : conversations.map((conversation) => (
            <div
              key={conversation.id}
              className={`group mb-0.5 flex cursor-pointer items-center gap-1 rounded-xl px-2.5 py-2 text-sm transition ${
                currentConversationId === conversation.id && currentView === 'chat'
                  ? 'bg-brand-100 font-medium text-brand-900'
                  : 'text-brand-600 hover:bg-brand-50'
              }`}
              onClick={() => { onSelectConversation(conversation.id); onClose(); }}
            >
              <svg className="h-4 w-4 shrink-0 text-brand-400" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path d="M4 4.75h12v8.5H9l-3.5 2.5v-2.5H4v-8.5Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
              </svg>
              <span className="flex-1 truncate">{conversation.title || '新对话'}</span>
              <button
                onClick={(event) => { event.stopPropagation(); onDeleteConversation(conversation.id); }}
                className="rounded-md px-1.5 py-0.5 text-brand-300 opacity-100 transition hover:bg-red-50 hover:text-red-500 md:opacity-0 md:group-hover:opacity-100"
                aria-label={`删除对话：${conversation.title || '新对话'}`}
                title="删除对话"
              >×</button>
            </div>
          ))}
        </div>

        <div className="border-t border-brand-100 p-2.5">
          <button
            onClick={() => { onShowUsage(); onClose(); }}
            className={`mb-1 flex w-full items-center gap-2 rounded-xl px-3 py-2 text-sm transition ${
              currentView === 'usage' ? 'bg-brand-100 font-medium text-brand-900' : 'text-brand-600 hover:bg-brand-50'
            }`}
          ><span aria-hidden="true">◫</span>我的用量</button>
          <div className="flex items-center gap-2 rounded-xl px-3 py-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-800 text-xs font-semibold text-white">
              {displayName.slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0 flex-1 truncate text-sm text-brand-700">{displayName}</span>
            <button onClick={onLogout} className="text-xs text-brand-400 transition hover:text-red-600">退出</button>
          </div>
        </div>
      </aside>
    </>
  );
}
