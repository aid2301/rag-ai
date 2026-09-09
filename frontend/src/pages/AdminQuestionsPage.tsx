import { useState, useEffect, useCallback } from 'react';
import {
  apiDocs,
  apiQuestions,
  apiQuestionGroups,
  type QuestionItem,
  type QuestionDetail,
  type QuestionGroup,
} from '../api';

const STATUS_LABEL: Record<string, string> = {
  pending: '待处理',
  processing: '处理中',
  resolved: '已解答',
  archived: '已归档',
};
const STATUS_COLOR: Record<string, string> = {
  pending: 'bg-red-100 text-red-700',
  processing: 'bg-blue-100 text-blue-700',
  resolved: 'bg-green-100 text-green-700',
  archived: 'bg-brand-100 text-brand-600',
};
const FEEDBACK_LABEL: Record<string, string> = {
  insufficient: '无法回答',
  wrong_answer: '回答有误',
};

export function AdminQuestionsPage() {
  const [items, setItems] = useState<QuestionItem[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [groupFilter, setGroupFilter] = useState('');
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [sourceFilter, setSourceFilter] = useState('all'); // M2-Q06
  const [sortBy, setSortBy] = useState('created'); // M2-Q09: created | hot
  const [groups, setGroups] = useState<QuestionGroup[]>([]);
  const [selected, setSelected] = useState<QuestionDetail | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showGroups, setShowGroups] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [checked, setChecked] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiQuestions.list({
        status: statusFilter,
        group_id: groupFilter,
        search: search || undefined,
        date_from: dateFrom || undefined,
        source_type: sourceFilter,
        sort: sortBy,
      });
      setItems(res.items);
      setCounts(res.counts);
    } catch (err: any) {
      alert('加载问题库失败: ' + err.message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, groupFilter, search, dateFrom, sourceFilter, sortBy]);

  const loadGroups = useCallback(() => {
    apiQuestionGroups.list().then(setGroups).catch(() => setGroups([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    loadGroups();
  }, [loadGroups]);

  useEffect(() => {
    if (selectedId) {
      setDetailLoading(true);
      apiQuestions
        .get(selectedId)
        .then(setSelected)
        .catch((err) => alert('加载问题详情失败: ' + err.message))
        .finally(() => setDetailLoading(false));
    } else {
      setSelected(null);
    }
  }, [selectedId]);

  const openDetail = (id: string) => setSelectedId(id);

  const handleSaveDetail = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      const updated = await apiQuestions.update(selected.id, {
        status: selected.status,
        standard_answer: selected.standard_answer || undefined,
        group_id: selected.group_id || '',
        assignee: selected.assignee || undefined,
      });
      setSelected(updated);
      load();
      alert('已保存');
    } catch (err: any) {
      alert('保存失败: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleCreateGroup = async () => {
    const name = newGroupName.trim();
    if (!name) return;
    try {
      await apiQuestionGroups.create(name);
      setNewGroupName('');
      loadGroups();
      alert('分组已创建');
    } catch (err: any) {
      alert('创建分组失败: ' + err.message);
    }
  };

  // M2-Q05：采纳自动分组建议（一键设 group_id 并清除建议）
  const handleAcceptSuggestion = async (q: QuestionItem) => {
    if (!q.suggested_group_id) return;
    try {
      await apiQuestions.update(q.id, { group_id: q.suggested_group_id });
      load();
    } catch (err: any) {
      alert('采纳分组失败: ' + err.message);
    }
  };

  const handleDeleteGroup = async (g: QuestionGroup) => {
    if (!confirm('确认删除分组「' + g.name + '」？组内问题会保留为「未分类」。')) return;
    try {
      await apiQuestionGroups.remove(g.id);
      loadGroups();
      if (groupFilter === g.id) setGroupFilter('');
      alert('分组已删除，问题保留。');
    } catch (err: any) {
      alert('删除分组失败: ' + err.message);
    }
  };

  const handleRenameGroup = async (g: QuestionGroup) => {
    const name = prompt('新的分组名称：', g.name);
    if (!name || name.trim() === g.name) return;
    try {
      await apiQuestionGroups.rename(g.id, name.trim());
      loadGroups();
    } catch (err: any) {
      alert('重命名失败: ' + err.message);
    }
  };

  const handleBulk = async (action: 'archived' | 'resolved') => {
    if (checked.size === 0) return;
    const label = action === 'archived' ? '归档' : '标记已解答';
    if (!confirm('确认对选中的 ' + checked.size + ' 条问题执行「' + label + '」？')) return;
    let failed = 0;
    for (const id of Array.from(checked)) {
      try {
        await apiQuestions.update(id, { status: action });
      } catch {
        failed++;
      }
    }
    setChecked(new Set());
    load();
    alert(failed === 0 ? '批量操作完成。' : '批量操作完成，' + failed + ' 条失败。');
  };

  const toggleCheck = (id: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const tabs = [
    { key: 'all', label: '全部' },
    { key: 'pending', label: '待处理' },
    { key: 'processing', label: '处理中' },
    { key: 'resolved', label: '已解答' },
    { key: 'archived', label: '已归档' },
  ];

  return (
    <div className="flex h-full">
      {/* 主列表 */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="px-6 py-3 border-b border-brand-100 bg-white flex items-center justify-between gap-3 flex-wrap">
          <h1 className="text-base font-semibold text-brand-800">问题库</h1>
          <div className="flex items-center gap-2 text-xs">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索问题…"
              className="rounded-lg border border-brand-200 px-2 py-1 text-sm w-44"
            />
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="rounded-lg border border-brand-200 px-2 py-1 text-sm"
              title="提交时间从"
            />
            <select
              value={groupFilter}
              onChange={(e) => setGroupFilter(e.target.value)}
              className="rounded-lg border border-brand-200 px-2 py-1 text-sm"
            >
              <option value="">全部分组</option>
              <option value="none">未分类</option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
            <select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              className="rounded-lg border border-brand-200 px-2 py-1 text-sm"
              title="按来源类型筛选"
            >
              <option value="all">全部来源</option>
              <option value="insufficient">知识不足</option>
              <option value="wrong_answer">回答有误</option>
              <option value="model_error">模型错误</option>
              <option value="retrieval_error">检索错误</option>
            </select>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="rounded-lg border border-brand-200 px-2 py-1 text-sm"
              title="排序方式"
            >
              <option value="created">按时间</option>
              <option value="hot">高频优先</option>
            </select>
            <button
              onClick={() => setShowGroups(true)}
              className="rounded-lg border border-brand-200 px-2.5 py-1 text-brand-600 hover:bg-brand-50"
            >
              分组管理
            </button>
          </div>
        </div>

        <div className="px-6 pt-3 flex gap-2 text-xs">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setStatusFilter(t.key)}
              className={`px-3 py-1.5 rounded-lg border transition ${
                statusFilter === t.key
                  ? 'bg-brand-700 text-white border-brand-700'
                  : 'bg-white border-brand-200 text-brand-600 hover:bg-brand-50'
              } ${
                t.key === 'pending' && (counts[t.key] || 0) > 0
                  ? '!border-red-400'
                  : ''
              }`}
            >
              {t.label}
              <span className={`ml-1 ${
                t.key === 'pending'
                  ? 'text-red-500 font-bold'
                  : 'text-brand-400'
              }`}>
                {counts[t.key] ?? 0}
              </span>
            </button>
          ))}
          <div className="ml-auto flex items-center gap-2">
            {checked.size > 0 && (
              <>
                <button
                  onClick={() => handleBulk('resolved')}
                  className="px-3 py-1.5 rounded-lg bg-green-600 text-white hover:bg-green-700"
                >
                  批量已解答
                </button>
                <button
                  onClick={() => handleBulk('archived')}
                  className="px-3 py-1.5 rounded-lg bg-brand-200 text-brand-700 hover:bg-brand-300"
                >
                  批量归档
                </button>
              </>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <p className="text-brand-400 text-sm">加载中…</p>
          ) : items.length === 0 ? (
            <p className="text-brand-400 text-sm text-center py-12">
              暂无问题{statusFilter !== 'all' ? '（当前筛选）' : ''}
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-brand-500 border-b border-brand-100">
                  <th className="py-2 pr-2 w-6">
                    <input
                      type="checkbox"
                      onChange={(e) => {
                        if (e.target.checked) {
                          setChecked(new Set(items.map((i) => i.id)));
                        } else {
                          setChecked(new Set());
                        }
                      }}
                    />
                  </th>
                  <th className="py-2 font-medium">问题</th>
                  <th className="py-2 font-medium">类型</th>
                  <th className="py-2 font-medium">分组</th>
                  <th className="py-2 font-medium">状态</th>
                  <th className="py-2 font-medium">次数</th>
                  <th className="py-2 font-medium">来源</th>
                  <th className="py-2 font-medium">提交时间</th>
                  <th className="py-2 font-medium">处理人</th>
                  <th className="py-2 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((q) => (
                  <tr
                    key={q.id}
                    className={`border-b border-brand-50 hover:bg-brand-50/50 ${
                      q.status === 'pending' ? 'bg-red-50/40' : ''
                    } ${
                      q.is_recurring ? 'bg-amber-50/50' : ''
                    }`}
                  >
                    <td className="py-2.5 pr-2">
                      <input
                        type="checkbox"
                        checked={checked.has(q.id)}
                        onChange={() => toggleCheck(q.id)}
                      />
                    </td>
                    <td className="py-2.5">
                      <button
                        onClick={() => openDetail(q.id)}
                        className="text-left text-brand-800 hover:text-brand-600 font-medium"
                      >
                        {q.status === 'pending' && (
                          <span className="mr-1 text-red-500">🔴</span>
                        )}
                        {q.question}
                      </button>
                      {q.occurrence_count > 1 && (
                        <div className="text-xs text-brand-400">
                          出现 {q.occurrence_count} 次
                          {q.is_recurring && (
                            <span className="ml-1 text-amber-600 font-medium">· 复发</span>
                          )}
                        </div>
                      )}
                      {/* M2-Q11：标准答案标记 */}
                      {q.standard_answer ? (
                        <div className="text-xs text-green-600">已有标准答案</div>
                      ) : (
                        <div className="text-xs text-brand-300">缺标准答案</div>
                      )}
                    </td>
                    <td className="py-2.5">
                      <span
                        className={`px-2 py-0.5 rounded text-xs ${
                          q.feedback_type === 'wrong_answer'
                            ? 'bg-blue-50 text-blue-700 border border-blue-200'
                            : 'bg-brand-50 text-brand-500'
                        }`}
                      >
                        {FEEDBACK_LABEL[q.feedback_type || 'insufficient'] || q.feedback_type}
                      </span>
                      {/* M2-Q11：模型/检索错误标记 */}
                      {q.answer_status === 'model_error' && (
                        <span className="ml-1 px-2 py-0.5 rounded text-xs bg-purple-50 text-purple-700 border border-purple-200">
                          模型错误
                        </span>
                      )}
                      {q.answer_status === 'retrieval_error' && (
                        <span className="ml-1 px-2 py-0.5 rounded text-xs bg-red-50 text-red-600 border border-red-200">
                          检索错误
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 text-brand-600">
                      {q.group_name || (
                        <span className="text-brand-300">未分类</span>
                      )}
                      {/* M2-Q05：建议分组徽标 + 一键采纳 */}
                      {q.suggested_group_id && !q.group_id && (
                        <div className="mt-1">
                          <button
                            onClick={() => handleAcceptSuggestion(q)}
                            className="px-1.5 py-0.5 rounded text-xs bg-amber-100 text-amber-700 border border-amber-200 hover:bg-amber-200"
                            title={q.suggested_reason || '自动分组建议'}
                          >
                            建议入 {groups.find((g) => g.id === q.suggested_group_id)?.name || '分组'} ↗
                          </button>
                        </div>
                      )}
                    </td>
                    <td className="py-2.5">
                      <span
                        className={`px-2 py-0.5 rounded text-xs ${
                          STATUS_COLOR[q.status] || 'bg-brand-100 text-brand-600'
                        }`}
                      >
                        {STATUS_LABEL[q.status] || q.status}
                      </span>
                    </td>
                    <td className="py-2.5 text-brand-600">{q.occurrence_count}</td>
                    <td className="py-2.5 text-brand-600">{q.username}</td>
                    <td className="py-2.5 text-brand-500 text-xs">
                      {q.created_at?.slice(0, 16).replace('T', ' ')}
                    </td>
                    <td className="py-2.5 text-brand-600">
                      {q.assignee || (
                        <span className="text-brand-300">—</span>
                      )}
                    </td>
                    <td className="py-2.5">
                      <button
                        onClick={() => openDetail(q.id)}
                        className="text-xs text-brand-500 hover:text-brand-700"
                      >
                        查看
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* 详情 */}
      {selectedId && (
        <div className="w-[440px] border-l border-brand-100 bg-white flex flex-col shrink-0">
          <div className="px-4 py-3 border-b border-brand-100 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-brand-800">问题详情</h2>
            <button
              onClick={() => setSelectedId(null)}
              className="text-brand-400 hover:text-brand-600 text-lg"
            >
              ×
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 text-sm space-y-4">
            {detailLoading || !selected ? (
              <p className="text-brand-400">加载中…</p>
            ) : (
              <>
                <div>
                  <div className="text-brand-400 text-xs mb-1">原始问题</div>
                  <div className="text-brand-800 font-medium">{selected.question}</div>
                  <div className="mt-1 flex gap-1.5">
                    <span
                      className={`px-2 py-0.5 rounded text-xs ${
                        selected.feedback_type === 'wrong_answer'
                          ? 'bg-blue-50 text-blue-700 border border-blue-200'
                          : 'bg-brand-50 text-brand-500'
                      }`}
                    >
                      {FEEDBACK_LABEL[selected.feedback_type || 'insufficient'] || selected.feedback_type}
                    </span>
                    {selected.context_source === 'snapshot' && (
                      <span className="px-2 py-0.5 rounded text-xs bg-brand-50 text-brand-400">
                        上下文已固化快照
                      </span>
                    )}
                  </div>
                  {selected.feedback_note && (
                    <div className="mt-1.5 text-xs text-brand-600">
                      <span className="text-brand-400">用户补充：</span>
                      {selected.feedback_note}
                    </div>
                  )}
                  {selected.original_questions.length > 1 && (
                    <details className="mt-1">
                      <summary className="text-xs text-brand-400 cursor-pointer">
                        查看全部 {selected.original_questions.length} 条提问
                      </summary>
                      <ul className="list-disc pl-4 text-xs text-brand-600 mt-1 space-y-0.5">
                        {selected.original_questions.map((o, i) => (
                          <li key={i}>{o}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>

                <div>
                  <div className="text-brand-400 text-xs mb-1">AI 当时回答</div>
                  <div className="bg-brand-50 rounded-lg px-3 py-2 text-brand-700 whitespace-pre-wrap text-xs">
                    {selected.ai_answer || '（无）'}
                  </div>
                </div>

                <div>
                  <div className="text-brand-400 text-xs mb-1">RAG 检索结果</div>
                  <RetrievalSnapshot snapshot={selected.retrieval_snapshot} />
                </div>

                <div>
                  <div className="text-brand-400 text-xs mb-1">会话上下文</div>
                  {selected.context && selected.context.length > 0 ? (
                    <div className="space-y-1.5">
                      {selected.context.map((m) => (
                        <div
                          key={m.id}
                          className={`rounded-lg px-3 py-1.5 text-xs whitespace-pre-wrap ${
                            m.role === 'user'
                              ? 'bg-brand-700 text-white'
                              : m.answer_status === 'insufficient_knowledge'
                                ? 'bg-amber-50 border border-amber-200 text-brand-800'
                                : 'bg-brand-50 text-brand-700'
                          }`}
                        >
                          {m.content}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-brand-300">无会话上下文</p>
                  )}
                </div>

                <div className="border-t border-brand-100 pt-3 space-y-2">
                  <label className="block">
                    <span className="text-xs text-brand-400">标准答案（解答）</span>
                    <textarea
                      value={selected.standard_answer || ''}
                      onChange={(e) =>
                        setSelected({ ...selected, standard_answer: e.target.value })
                      }
                      rows={4}
                      className="mt-1 w-full rounded-lg border border-brand-200 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-300"
                      placeholder="填写标准答案，供后续补充知识参考…"
                    />
                  </label>
                  <div className="flex gap-2">
                    <label className="flex-1">
                      <span className="text-xs text-brand-400">状态</span>
                      <select
                        value={selected.status}
                        onChange={(e) =>
                          setSelected({ ...selected, status: e.target.value })
                        }
                        className="mt-1 w-full rounded-lg border border-brand-200 px-2 py-1.5 text-sm"
                      >
                        {Object.entries(STATUS_LABEL).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="flex-1">
                      <span className="text-xs text-brand-400">分组</span>
                      <select
                        value={selected.group_id || ''}
                        onChange={(e) =>
                          setSelected({ ...selected, group_id: e.target.value || null })
                        }
                        className="mt-1 w-full rounded-lg border border-brand-200 px-2 py-1.5 text-sm"
                      >
                        <option value="">未分类</option>
                        {groups.map((g) => (
                          <option key={g.id} value={g.id}>
                            {g.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <label className="block">
                    <span className="text-xs text-brand-400">处理人</span>
                    <input
                      value={selected.assignee || ''}
                      onChange={(e) =>
                        setSelected({ ...selected, assignee: e.target.value })
                      }
                      className="mt-1 w-full rounded-lg border border-brand-200 px-2.5 py-1.5 text-sm"
                      placeholder="填写处理人姓名"
                    />
                  </label>
                  <div className="flex gap-2 pt-1">
                    <button
                      onClick={handleSaveDetail}
                      disabled={saving}
                      className="flex-1 rounded-lg bg-brand-700 text-white px-3 py-2 text-xs font-medium hover:bg-brand-800 disabled:opacity-40"
                    >
                      {saving ? '保存中…' : '保存'}
                    </button>
                    <button
                      onClick={async () => {
                        if (!selected) return;
                        const title = prompt('知识条目标题：', selected.question.slice(0, 30));
                        if (!title) return;
                        // M1-Q03：只允许用「标准答案」转知识，防止生成固定文案垃圾文档
                        const answer = selected.standard_answer || '';
                        if (!answer || answer.trim() === '') {
                          alert('请先填写标准答案再转为知识条目。');
                          return;
                        }
                        try {
                          const res = await apiDocs.createText(title, answer);
                          alert('已创建知识条目（' + res.document_id + '），可在「知识库」中查看与编辑。');
                        } catch (err: any) {
                          alert('转为知识失败: ' + err.message);
                        }
                      }}
                      className="rounded-lg bg-blue-600 text-white px-3 py-2 text-xs font-medium hover:bg-blue-700 disabled:opacity-40"
                      title="将标准答案创建为新知识条目（需先填写标准答案）"
                    >
                      转为知识条目
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* 分组管理弹窗 */}
      {showGroups && (
        <div
          className="fixed inset-0 bg-black/30 flex items-center justify-center z-50"
          onClick={() => setShowGroups(false)}
        >
          <div
            className="bg-white rounded-xl p-5 w-[360px] max-h-[70vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-sm font-semibold text-brand-800 mb-3">问题分组管理</h3>
            <div className="flex gap-2 mb-3">
              <input
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreateGroup()}
                placeholder="新分组名称"
                className="flex-1 rounded-lg border border-brand-200 px-2.5 py-1.5 text-sm"
              />
              <button
                onClick={handleCreateGroup}
                className="rounded-lg bg-brand-700 text-white px-3 py-1.5 text-xs font-medium hover:bg-brand-800"
              >
                新建
              </button>
            </div>
            <div className="flex-1 overflow-y-auto space-y-1">
              {groups.map((g) => (
                <div
                  key={g.id}
                  className="flex items-center gap-2 rounded-lg border border-brand-100 px-3 py-2 text-sm"
                >
                  <span className="flex-1 text-brand-800">
                    {g.name}
                    <span className="text-xs text-brand-400 ml-2">
                      {g.question_count} 条
                    </span>
                  </span>
                  <button
                    onClick={() => handleRenameGroup(g)}
                    className="text-xs text-brand-500 hover:text-brand-700"
                  >
                    重命名
                  </button>
                  <button
                    onClick={() => handleDeleteGroup(g)}
                    className="text-xs text-red-500 hover:text-red-700"
                  >
                    删除
                  </button>
                </div>
              ))}
              {groups.length === 0 && (
                <p className="text-xs text-brand-300 text-center py-6">
                  暂无分组。分组删除不会删除组内问题（自动变为未分类）。
                </p>
              )}
            </div>
            <button
              onClick={() => setShowGroups(false)}
              className="mt-3 rounded-lg border border-brand-200 text-brand-600 px-3 py-1.5 text-sm hover:bg-brand-50"
            >
              关闭
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function RetrievalSnapshot({ snapshot }: { snapshot: Record<string, any> }) {
  if (!snapshot || Object.keys(snapshot).length === 0) {
    return <p className="text-xs text-brand-300">未检索到有效知识</p>;
  }
  const docs = snapshot.candidate_documents || [];
  const sections = snapshot.candidate_sections || [];
  return (
    <div className="space-y-2 text-xs">
      {docs.length > 0 && (
        <div>
          <div className="text-brand-400 mb-1">命中文档</div>
          <div className="space-y-1">
            {docs.map((d: any, i: number) => (
              <div key={i} className="rounded-lg bg-brand-50 px-2.5 py-1.5">
                <div className="text-brand-800">
                  {d.title || d.document_id}{' '}
                  <span className="text-brand-400">score={d.score}</span>
                </div>
                <div className="text-brand-400">
                  {(d.reasons || []).join('；')}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {sections.length > 0 && (
        <div>
          <div className="text-brand-400 mb-1">命中章节</div>
          <div className="space-y-1">
            {sections.slice(0, 8).map((s: any, i: number) => (
              <div key={i} className="rounded-lg bg-brand-50 px-2.5 py-1.5">
                <span className="text-brand-800">{s.heading || s.section_id}</span>{' '}
                <span className="text-brand-400">score={s.score}</span>
                {s.reason && (
                  <div className="text-brand-400">{s.reason}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      {docs.length === 0 && sections.length === 0 && (
        <p className="text-xs text-brand-300">未检索到有效知识</p>
      )}
    </div>
  );
}