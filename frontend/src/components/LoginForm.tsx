import { useState, type ReactNode } from 'react';
import { Button, Input } from './ui';

export interface LoginFormProps {
  /** 用户名输入占位提示 */
  usernamePlaceholder?: string;
  /** 底部说明文案（可为空，支持 JSX） */
  hint?: ReactNode;
  /** 提交登录：返回是否成功（成功时由调用方处理跳转/存储） */
  onSubmit: (username: string, password: string) => Promise<boolean>;
}

/**
 * 通用登录表单（账户+密码+错误提示+提交动效）。
 * 普通用户登录与管理后台登录共用此组件，仅提交逻辑不同。
 */
export function LoginForm({
  usernamePlaceholder = '请输入用户名',
  hint,
  onSubmit,
}: LoginFormProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    if (!username.trim() || !password.trim()) {
      setError('请输入用户名和密码');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const ok = await onSubmit(username.trim(), password.trim());
      if (!ok) setError('登录失败，请重试');
    } catch (err: any) {
      setError(err.message || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <label className="mb-1.5 block text-sm font-medium text-brand-700">用户名</label>
      <Input
        type="text"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        placeholder={usernamePlaceholder}
        autoFocus
        className="mb-4"
        autoComplete="username"
      />

      <label className="mb-1.5 block text-sm font-medium text-brand-700">密码</label>
      <Input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
        placeholder="请输入密码"
        autoComplete="current-password"
      />
      {error && <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600" role="alert">{error}</p>}

      <Button onClick={handleLogin} disabled={loading} className="mt-5 w-full">
        {loading ? '登录中…' : '登录'}
      </Button>

      {hint && <p className="mt-4 text-center text-xs leading-relaxed text-brand-400">{hint}</p>}
    </>
  );
}
