import { useState, useEffect } from 'react';
import { apiSettings, type SettingsInfo } from '../api';

export function SettingsPage({ embedded = false }: { embedded?: boolean }) {
  const [settings, setSettings] = useState<SettingsInfo | null>(null);
  const [form, setForm] = useState<Partial<SettingsInfo>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    apiSettings.get().then((s) => {
      setSettings(s);
      setForm({
        llm_base_url: s.llm_base_url,
        llm_model: s.llm_model,
        llm_temperature: s.llm_temperature,
        llm_max_tokens: s.llm_max_tokens,
        llm_timeout: s.llm_timeout,
        default_chat_mode: s.default_chat_mode || 'auto',
        show_thinking: !!s.show_thinking,
      });
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await apiSettings.update(form);
      setTestResult('设置已保存');
      const s = await apiSettings.get();
      setSettings(s);
    } catch (err: any) {
      setTestResult(`保存失败: ${err.message}`);
    }
    setSaving(false);
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await apiSettings.test();
      const detail = r.latency_ms != null
        ? `${r.model || ''} · ${r.latency_ms}ms`
        : (r.model || '');
      setTestResult(r.ok ? `✓ 连接成功（${detail}）` : `✗ ${r.message || '失败'}`);
    } catch (err: any) {
      setTestResult(`✗ ${err.message}`);
    }
    setTesting(false);
  };

  if (!settings) return <div className="p-6 text-brand-400">加载中…</div>;

  return (
    <div className={embedded ? '' : 'flex flex-col h-full'}>
      {!embedded && (
        <div className="px-6 py-3 border-b border-brand-100 bg-white">
          <h1 className="text-base font-semibold text-brand-800">设置</h1>
        </div>
      )}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="max-w-lg space-y-4">
          <div>
            <label className="block text-sm font-medium text-brand-700 mb-1">
              LLM Base URL
            </label>
            <input
              value={form.llm_base_url || ''}
              onChange={(e) => setForm({ ...form, llm_base_url: e.target.value })}
              placeholder="https://api.deepseek.com/v1"
              className="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-300"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-brand-700 mb-1">
              API Key
            </label>
            <div className="flex gap-2">
              <input
                type={showKey ? 'text' : 'password'}
                value={form.llm_api_key || ''}
                onChange={(e) => setForm({ ...form, llm_api_key: e.target.value })}
                placeholder={settings.llm_api_key_masked || '输入 API Key'}
                className="flex-1 rounded-lg border border-brand-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-300"
              />
              <button
                onClick={() => setShowKey(!showKey)}
                className="rounded-lg border border-brand-200 px-3 text-sm text-brand-500 hover:bg-brand-50"
              >
                {showKey ? '隐藏' : '显示'}
              </button>
            </div>
            <p className="text-xs text-brand-400 mt-1">
              {settings.llm_api_key_masked && !form.llm_api_key
                ? `当前: ${settings.llm_api_key_masked}（留空则不修改）`
                : ''}
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-brand-700 mb-1">
              模型名称
            </label>
            <input
              value={form.llm_model || ''}
              onChange={(e) => setForm({ ...form, llm_model: e.target.value })}
              placeholder="deepseek-chat"
              className="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-300"
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-sm font-medium text-brand-700 mb-1">
                Temperature
              </label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="2"
                value={form.llm_temperature ?? ''}
                onChange={(e) =>
                  setForm({ ...form, llm_temperature: parseFloat(e.target.value) })
                }
                className="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-300"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-brand-700 mb-1">
                Max Tokens
              </label>
              <input
                type="number"
                value={form.llm_max_tokens ?? ''}
                onChange={(e) =>
                  setForm({ ...form, llm_max_tokens: parseInt(e.target.value) })
                }
                className="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-300"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-brand-700 mb-1">
                Timeout (秒)
              </label>
              <input
                type="number"
                value={form.llm_timeout ?? ''}
                onChange={(e) =>
                  setForm({ ...form, llm_timeout: parseFloat(e.target.value) })
                }
                className="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-300"
              />
            </div>
          </div>

          <div className="border-t border-brand-100 pt-4">
            <h3 className="text-sm font-semibold text-brand-800 mb-2">
              回答策略
            </h3>
            <div className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-brand-700 mb-1">
                  默认回答模式（影响回复速度）
                </label>
                <select
                  value={form.default_chat_mode || 'auto'}
                  onChange={(e) =>
                    setForm({ ...form, default_chat_mode: e.target.value })
                  }
                  className="w-full rounded-lg border border-brand-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-300"
                >
                  <option value="auto">自动（按问题复杂度，默认）</option>
                  <option value="fast">快速模式（最快：简化分析，约 2 次模型调用）</option>
                  <option value="standard">标准模式（推荐：理解+选文档+回答）</option>
                  <option value="deep">深度模式（最慢最准：多查询+重排+事实校验）</option>
                </select>
                <p className="text-xs text-brand-400 mt-1">
                  回复慢时建议选「快速模式」：跳过部分分析步骤，响应时间约缩短一半，
                  回答质量在简单问题上几乎无差别。
                </p>
              </div>
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-brand-700">
                  <input
                    type="checkbox"
                    checked={!!form.show_thinking}
                    onChange={(e) =>
                      setForm({ ...form, show_thinking: e.target.checked })
                    }
                    className="rounded border-brand-300"
                  />
                  用户端显示思考过程
                </label>
                <p className="text-xs text-brand-400 mt-1">
                  在对话页展示「理解问题 → 检索知识库 → 筛选文档 → 生成回答 → 校验依据」
                  的实时进度与完成后的执行详情（模式、检索到的文档、耗时、Token 用量）。
                  <span className="text-green-600 font-medium">
                    不消耗额外 Token——展示的是系统已有的执行记录。
                  </span>
                </p>
              </div>
            </div>
          </div>

          <div className="flex gap-2 pt-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="rounded-lg bg-brand-700 text-white px-4 py-2 text-sm font-medium hover:bg-brand-800 disabled:opacity-40"
            >
              {saving ? '保存中…' : '保存设置'}
            </button>
            <button
              onClick={handleTest}
              disabled={testing}
              className="rounded-lg border border-brand-300 text-brand-700 px-4 py-2 text-sm font-medium hover:bg-brand-50 disabled:opacity-40"
            >
              {testing ? '测试中…' : '测试连接'}
            </button>
          </div>

          {testResult && (
            <p
              className={`text-sm ${testResult.startsWith('✓') ? 'text-green-600' : 'text-red-600'}`}
            >
              {testResult}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}