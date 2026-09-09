import { useState, useEffect } from 'react';
import { apiUsage, type UsageSummary, type UsageRecord, type UsageSummaryItem } from '../api';

export function UsagePage() {
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [recent, setRecent] = useState<UsageRecord[]>([]);

  useEffect(() => {
    apiUsage.summary().then(setSummary);
    apiUsage.recent(100).then(setRecent);
  }, []);

  if (!summary) return <div className="p-6 text-brand-400">加载中…</div>;

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-3 border-b border-brand-100 bg-white">
        <h1 className="text-base font-semibold text-brand-800">我的用量统计</h1>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {/* 汇总卡片 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <StatCard label="总调用次数" value={summary.total?.calls ?? 0} />
          <StatCard label="总 Token 数" value={summary.total?.total_tokens ?? 0} />
          <StatCard
            label="Prompt Tokens"
            value={
              summary.by_call_type?.reduce(
                (a: number, b: UsageSummaryItem) => a + (b.prompt_tokens ?? 0),
                0,
              ) ?? 0
            }
          />
          <StatCard
            label="Completion Tokens"
            value={
              summary.by_call_type?.reduce(
                (a: number, b: UsageSummaryItem) => a + (b.completion_tokens ?? 0),
                0,
              ) ?? 0
            }
          />
        </div>

        {/* 按调用类型分组 */}
        <h2 className="text-sm font-semibold text-brand-700 mb-2">按步骤统计</h2>
        <table className="w-full text-sm mb-6">
          <thead>
            <tr className="text-left text-brand-500 border-b border-brand-100">
              <th className="py-2 font-medium">步骤</th>
              <th className="py-2 font-medium">调用次数</th>
              <th className="py-2 font-medium">Prompt</th>
              <th className="py-2 font-medium">Completion</th>
              <th className="py-2 font-medium">总 Token</th>
              <th className="py-2 font-medium">平均延迟(ms)</th>
            </tr>
          </thead>
          <tbody>
            {(summary.by_call_type || []).map((row: UsageSummaryItem) => (
              <tr key={row.call_type} className="border-b border-brand-50">
                <td className="py-2 font-mono text-brand-700">{row.call_type}</td>
                <td className="py-2 text-brand-600">{row.calls}</td>
                <td className="py-2 text-brand-600">{row.prompt_tokens ?? 0}</td>
                <td className="py-2 text-brand-600">{row.completion_tokens ?? 0}</td>
                <td className="py-2 text-brand-600 font-medium">
                  {row.total_tokens ?? 0}
                </td>
                <td className="py-2 text-brand-600">
                  {row.avg_latency_ms ? Math.round(row.avg_latency_ms) : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* 最近记录 */}
        <h2 className="text-sm font-semibold text-brand-700 mb-2">最近调用记录</h2>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-brand-500 border-b border-brand-100">
              <th className="py-1.5 font-medium">时间</th>
              <th className="py-1.5 font-medium">步骤</th>
              <th className="py-1.5 font-medium">模型</th>
              <th className="py-1.5 font-medium">Token</th>
              <th className="py-1.5 font-medium">延迟</th>
            </tr>
          </thead>
          <tbody>
            {recent.slice(0, 50).map((r) => (
              <tr key={r.id} className="border-b border-brand-50">
                <td className="py-1.5 text-brand-400">
                  {r.created_at?.slice(11, 19)}
                </td>
                <td className="py-1.5 font-mono text-brand-600">{r.call_type}</td>
                <td className="py-1.5 text-brand-500">{r.model}</td>
                <td className="py-1.5 text-brand-600">{r.total_tokens}</td>
                <td className="py-1.5 text-brand-500">
                  {Math.round(r.latency_ms)}ms
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-brand-100 bg-white p-4">
      <div className="text-xs text-brand-400">{label}</div>
      <div className="text-xl font-semibold text-brand-800 mt-1">
        {value.toLocaleString()}
      </div>
    </div>
  );
}
