import { useState, useEffect } from 'react';
import { apiAdminUsers, type AdminUserInfo } from '../api';

export function AdminUsersPage({
  onViewChats,
}: {
  onViewChats: (userId: string, username: string) => void;
}) {
  const [users, setUsers] = useState<AdminUserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ username: '', password: '', display_name: '' });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const load = () => {
    setLoading(true);
    apiAdminUsers
      .list()
      .then(setUsers)
      .catch((e) => setMsg({ type: 'err', text: `加载失败: ${e.message}` }))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleAdd = async () => {
    if (!form.username.trim() || !form.password) {
      setMsg({ type: 'err', text: '请填写用户名和密码' });
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await apiAdminUsers.create(
        form.username.trim(),
        form.password,
        form.display_name.trim() || undefined,
      );
      setForm({ username: '', password: '', display_name: '' });
      setShowAdd(false);
      setMsg({ type: 'ok', text: '用户已创建' });
      load();
    } catch (e: any) {
      setMsg({ type: 'err', text: e.message || '创建失败' });
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (u: AdminUserInfo) => {
    if (
      !confirm(
        `确认删除用户「${u.username}」？\n其所有对话记录将被删除，用量记录保留但不再关联该用户。`,
      )
    )
      return;
    try {
      await apiAdminUsers.remove(u.id);
      setMsg({ type: 'ok', text: `已删除用户 ${u.username}` });
      load();
    } catch (e: any) {
      setMsg({ type: 'err', text: e.message || '删除失败' });
    }
  };

  const handleResetPassword = async (u: AdminUserInfo) => {
    const pwd = prompt(`为用户「${u.username}」设置新密码（可随意设置）：`);
    if (!pwd) return;
    try {
      await apiAdminUsers.resetPassword(u.id, pwd);
      setMsg({ type: 'ok', text: `已重置 ${u.username} 的密码` });
    } catch (e: any) {
      setMsg({ type: 'err', text: e.message || '重置失败' });
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-3 border-b border-brand-100 bg-white flex items-center justify-between">
        <h1 className="text-base font-semibold text-brand-800">用户管理</h1>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="rounded-lg bg-brand-700 text-white px-3 py-1.5 text-sm font-medium hover:bg-brand-800 transition"
        >
          {showAdd ? '取消' : '+ 添加用户'}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {showAdd && (
          <div className="mb-4 rounded-xl border border-brand-200 bg-white p-4 max-w-lg">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-brand-600 mb-1">
                  用户名（2-32 字符）
                </label>
                <input
                  value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                  placeholder="如 zhangsan"
                  className="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-300"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-brand-600 mb-1">
                  密码（可随意设置）
                </label>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  placeholder="初始密码"
                  className="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-300"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-medium text-brand-600 mb-1">
                  显示名称（可选）
                </label>
                <input
                  value={form.display_name}
                  onChange={(e) =>
                    setForm({ ...form, display_name: e.target.value })
                  }
                  placeholder="如 张三"
                  className="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-300"
                />
              </div>
            </div>
            <button
              onClick={handleAdd}
              disabled={busy}
              className="mt-3 rounded-lg bg-brand-700 text-white px-4 py-2 text-sm font-medium hover:bg-brand-800 disabled:opacity-40"
            >
              {busy ? '创建中…' : '创建用户'}
            </button>
          </div>
        )}

        {msg && (
          <p
            className={`text-sm mb-3 ${msg.type === 'ok' ? 'text-green-600' : 'text-red-600'}`}
          >
            {msg.text}
          </p>
        )}

        {loading ? (
          <p className="text-brand-400 text-sm">加载中…</p>
        ) : users.length === 0 ? (
          <p className="text-brand-400 text-sm text-center py-12">
            暂无用户，点击右上角添加
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-brand-500 border-b border-brand-100">
                <th className="py-2 font-medium">用户名</th>
                <th className="py-2 font-medium">显示名称</th>
                <th className="py-2 font-medium">创建时间</th>
                <th className="py-2 font-medium">对话数</th>
                <th className="py-2 font-medium">调用次数</th>
                <th className="py-2 font-medium">总 Token</th>
                <th className="py-2 font-medium">最后活跃</th>
                <th className="py-2 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-brand-50 hover:bg-brand-50/50">
                  <td className="py-2.5 font-medium text-brand-800">
                    {u.username}
                    {!u.is_active && (
                      <span className="ml-1 px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-600">
                        禁用
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 text-brand-600">{u.display_name}</td>
                  <td className="py-2.5 text-brand-400 text-xs">
                    {u.created_at?.slice(0, 10)}
                  </td>
                  <td className="py-2.5 text-brand-600">{u.conversation_count}</td>
                  <td className="py-2.5 text-brand-600">{u.call_count}</td>
                  <td className="py-2.5 text-brand-600 font-medium">
                    {(u.total_tokens || 0).toLocaleString()}
                  </td>
                  <td className="py-2.5 text-brand-400 text-xs">
                    {u.last_active ? u.last_active.slice(0, 16).replace('T', ' ') : '-'}
                  </td>
                  <td className="py-2.5">
                    <div className="flex gap-2 text-xs">
                      <button
                        onClick={() => onViewChats(u.id, u.username)}
                        className="text-brand-500 hover:text-brand-700"
                      >
                        对话记录
                      </button>
                      <button
                        onClick={() => handleResetPassword(u)}
                        className="text-brand-500 hover:text-brand-700"
                      >
                        重置密码
                      </button>
                      <button
                        onClick={() => handleDelete(u)}
                        className="text-red-500 hover:text-red-700"
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
