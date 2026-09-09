import { apiAuth, setUserInfo, setUserToken, type UserInfo } from '../api';
import { LoginForm } from '../components/LoginForm';

export function LoginPage({
  onLogin,
}: {
  onLogin: (user: UserInfo) => void;
}) {
  const handleLogin = async (username: string, password: string) => {
    const res = await apiAuth.login(username, password);
    setUserToken(res.token);
    setUserInfo(res.user);
    onLogin(res.user);
    return true;
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-brand-50 p-4">
      <div className="pointer-events-none absolute -left-20 -top-20 h-72 w-72 rounded-full bg-brand-200/50 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-28 -right-20 h-80 w-80 rounded-full bg-blue-100/70 blur-3xl" />
      <div className="relative grid w-full max-w-4xl overflow-hidden rounded-3xl border border-white/80 bg-white shadow-2xl shadow-brand-200/60 md:grid-cols-[1.1fr_0.9fr]">
        <section className="hidden bg-brand-900 p-10 text-white md:flex md:flex-col md:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/10 ring-1 ring-white/15">
              <img src="/logo.svg" alt="" className="h-6 w-6 brightness-0 invert" />
            </div>
            <span className="font-semibold">企业知识助手</span>
          </div>
          <div>
            <h1 className="max-w-sm text-3xl font-semibold leading-tight tracking-tight">让内部知识<br />更容易被找到和验证</h1>
            <p className="mt-4 max-w-sm text-sm leading-6 text-brand-300">基于企业知识库生成回答，自动标注引用来源，并支持将知识缺口反馈给管理员。</p>
          </div>
          <div className="flex gap-5 text-xs text-brand-300">
            <span>✓ 来源可追溯</span><span>✓ 多轮对话</span><span>✓ 权限隔离</span>
          </div>
        </section>
        <section className="p-7 sm:p-10">
          <div className="mb-8 flex items-center gap-3 md:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-900">
              <img src="/logo.svg" alt="" className="h-5 w-5 brightness-0 invert" />
            </div>
            <div>
              <div className="font-semibold text-brand-900">企业知识助手</div>
              <div className="text-xs text-brand-400">内部知识问答平台</div>
            </div>
          </div>
          <div className="mb-7">
            <h2 className="text-2xl font-semibold tracking-tight text-brand-900">欢迎回来</h2>
            <p className="mt-2 text-sm text-brand-500">登录后访问企业知识库与历史对话</p>
          </div>
          <LoginForm hint="账号由管理员统一创建，如无法登录请联系管理员。" onSubmit={handleLogin} />
        </section>
      </div>
    </div>
  );
}
