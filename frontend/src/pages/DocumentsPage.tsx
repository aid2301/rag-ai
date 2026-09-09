import { useState, useEffect, useRef } from 'react';
import {
  apiDocs,
  type DocInfo,
  type DocSection,
  type DocProfileResult,
} from '../api';

const SYNC_LABEL: Record<string, string> = {
  synced: '已同步',
  pending_reparse: '待重新解析',
  reparsing: '解析中',
  failed: '解析失败',
};
const PROFILE_LABEL: Record<string, string> = {
  none: '未生成',
  generating: '生成中',
  ready: '已生成',
  error: '生成失败',
};
const DOC_STATUS_LABEL: Record<string, string> = {
  ready: '可用',
  error: '错误',
  processing: '处理中',
  disabled: '已停用',
};

export function DocumentsPage() {
  const [docs, setDocs] = useState<DocInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState<DocInfo | null>(null);
  const [detailTab, setDetailTab] = useState<'sections' | 'profile' | 'edit'>(
    'sections',
  );
  const [detailData, setDetailData] = useState<
    DocSection[] | DocProfileResult | DocInfo | null
  >(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Record<string, string>>({}); // docId -> 动作
  const [editTitle, setEditTitle] = useState('');
  const [editText, setEditText] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => {
    setLoading(true);
    apiDocs
      .list()
      .then(setDocs)
      .catch((err) => alert('加载文档列表失败: ' + err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleUpload = async (files: FileList) => {
    setUploading(true);
    for (const file of Array.from(files)) {
      try {
        await apiDocs.upload(file);
      } catch (err: any) {
        alert(`上传 ${file.name} 失败: ${err.message}`);
      }
    }
    setUploading(false);
    load();
    if (fileRef.current) fileRef.current.value = '';
  };

  const handleDelete = async (id: string) => {
    if (!confirm('确认删除该文档？关联的章节、索引和画像将一并删除。')) return;
    setBusy((b) => ({ ...b, [id]: 'deleting' }));
    try {
      await apiDocs.delete(id);
      if (selected?.id === id) setSelected(null);
      load();
    } catch (err: any) {
      alert('删除失败: ' + err.message);
    } finally {
      setBusy((b) => {
        const nb = { ...b };
        delete nb[id];
        return nb;
      });
    }
  };

  const handleToggle = async (doc: DocInfo) => {
    const newStatus = doc.status === 'disabled' ? 'ready' : 'disabled';
    setBusy((b) => ({ ...b, [doc.id]: 'toggle' }));
    try {
      await apiDocs.setStatus(doc.id, newStatus);
      load();
    } catch (err: any) {
      alert('切换状态失败: ' + err.message);
    } finally {
      setBusy((b) => {
        const nb = { ...b };
        delete nb[doc.id];
        return nb;
      });
    }
  };

  const handleReparse = async (id: string, label = '重解析') => {
    if (!confirm(`确认${label}该文档？将重新解析并刷新检索索引。`)) return;
    setBusy((b) => ({ ...b, [id]: 'reparse' }));
    try {
      await apiDocs.repare(id);
      load();
      if (selected?.id === id) openDetail(selected, detailTab);
      alert('重新解析完成，检索数据已更新。');
    } catch (err: any) {
      alert(`重新解析失败: ${err.message}`);
    } finally {
      setBusy((b) => {
        const nb = { ...b };
        delete nb[id];
        return nb;
      });
    }
  };

  const openDetail = async (doc: DocInfo, tab: 'sections' | 'profile' | 'edit') => {
    setSelected(doc);
    setDetailTab(tab);
    setDetailError(null);
    setDetailData(null);
    try {
      if (tab === 'sections') {
        setDetailData(await apiDocs.sections(doc.id));
      } else if (tab === 'profile') {
        setDetailData(await apiDocs.profile(doc.id));
      } else {
        const full = await apiDocs.get(doc.id);
        setDetailData(full);
        setEditTitle(full.title || '');
        setEditText(full.full_text || '');
      }
    } catch (err: any) {
      setDetailError('加载失败: ' + err.message);
    }
  };

  const handleGenerateProfile = async (doc: DocInfo) => {
    setBusy((b) => ({ ...b, [doc.id]: 'profile' }));
    setDetailError(null);
    try {
      const result = await apiDocs.generateProfile(doc.id);
      setDetailData(result);
      load();
      if (result.profile_status === 'ready') alert('画像生成成功。');
      else alert('画像生成完成（回退模式）。');
    } catch (err: any) {
      setDetailError('画像生成失败，请重试: ' + err.message);
      try {
        setDetailData(await apiDocs.profile(doc.id));
      } catch {}
    } finally {
      setBusy((b) => {
        const nb = { ...b };
        delete nb[doc.id];
        return nb;
      });
    }
  };

  const handleSaveEdit = async (alsoReparse: boolean) => {
    if (!selected) return;
    setBusy((b) => ({ ...b, [selected.id]: alsoReparse ? 'save_reparse' : 'save' }));
    setDetailError(null);
    try {
      await apiDocs.update(selected.id, { title: editTitle, full_text: editText });
      if (alsoReparse) {
        await apiDocs.repare(selected.id);
        alert('已保存并重新解析，检索数据已更新。');
      } else {
        alert('已保存。注意：RAG 仍使用旧内容，请点击「重解析」使其生效。');
      }
      load();
      const full = await apiDocs.get(selected.id);
      setSelected(full);
      setDetailData(full);
    } catch (err: any) {
      setDetailError('保存失败: ' + err.message);
    } finally {
      setBusy((b) => {
        const nb = { ...b };
        delete nb[selected.id];
        return nb;
      });
    }
  };

  const handleCancelEdit = async () => {
    if (!selected) return;
    try {
      const full = await apiDocs.get(selected.id);
      setEditTitle(full.title || '');
      setEditText(full.full_text || '');
    } catch {}
  };

  return (
    <div className="flex h-full">
      {/* 文档列表 */}
      <div className="flex-1 flex flex-col">
        <div className="px-6 py-3 border-b border-brand-100 bg-white flex items-center justify-between">
          <h1 className="text-base font-semibold text-brand-800">知识库管理</h1>
          <div className="flex items-center gap-3">
            <span className="text-xs text-brand-400">
              {docs.filter((d) => d.sync_status === 'pending_reparse').length > 0
                ? `${docs.filter((d) => d.sync_status === 'pending_reparse').length} 篇待重新解析`
                : ''}
            </span>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.md,.markdown,.xlsx"
              className="hidden"
              onChange={(e) => e.target.files && handleUpload(e.target.files)}
            />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="rounded-lg bg-brand-700 text-white px-3 py-1.5 text-sm font-medium hover:bg-brand-800 transition disabled:opacity-40"
            >
              {uploading ? '上传中…' : '上传文档'}
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <p className="text-brand-400 text-sm">加载中…</p>
          ) : docs.length === 0 ? (
            <p className="text-brand-400 text-sm text-center py-12">
              知识库暂无文档，点击右上角上传
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-brand-500 border-b border-brand-100">
                  <th className="py-2 font-medium">文件名</th>
                  <th className="py-2 font-medium">状态</th>
                  <th className="py-2 font-medium">同步</th>
                  <th className="py-2 font-medium">画像</th>
                  <th className="py-2 font-medium">版本</th>
                  <th className="py-2 font-medium">最后解析</th>
                  <th className="py-2 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr
                    key={doc.id}
                    className="border-b border-brand-50 hover:bg-brand-50/50"
                  >
                    <td className="py-2.5">
                      <div className="font-medium text-brand-800">
                        {doc.title || doc.filename}
                      </div>
                      <div className="text-xs text-brand-400 truncate max-w-xs">
                        {doc.filename} · {doc.char_count} 字 · {doc.section_count} 章节
                      </div>
                    </td>
                    <td className="py-2.5">
                      <span
                        className={`px-2 py-0.5 rounded text-xs ${
                          doc.status === 'ready'
                            ? 'bg-green-100 text-green-700'
                            : doc.status === 'error'
                              ? 'bg-red-100 text-red-700'
                              : 'bg-brand-100 text-brand-600'
                        }`}
                      >
                        {DOC_STATUS_LABEL[doc.status] || doc.status}
                      </span>
                    </td>
                    <td className="py-2.5">
                      {doc.sync_status === 'pending_reparse' ? (
                        <span className="px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-700">
                          待重新解析
                        </span>
                      ) : doc.sync_status === 'reparsing' ? (
                        <span className="px-2 py-0.5 rounded text-xs bg-blue-100 text-blue-700">
                          解析中
                        </span>
                      ) : doc.sync_status === 'failed' ? (
                        <span className="px-2 py-0.5 rounded text-xs bg-red-100 text-red-700">
                          解析失败
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-xs bg-green-100 text-green-700">
                          已同步
                        </span>
                      )}
                    </td>
                    <td className="py-2.5">
                      <span
                        className={`px-2 py-0.5 rounded text-xs ${
                          doc.profile_status === 'ready'
                            ? 'bg-green-100 text-green-700'
                            : doc.profile_status === 'error'
                              ? 'bg-red-100 text-red-700'
                              : doc.profile_status === 'generating'
                                ? 'bg-blue-100 text-blue-700'
                                : 'bg-brand-100 text-brand-600'
                        }`}
                      >
                        {PROFILE_LABEL[doc.profile_status || 'none']}
                      </span>
                    </td>
                    <td className="py-2.5 text-brand-600 text-xs">
                      {doc.content_version ?? 0} / {doc.index_version ?? 0}
                    </td>
                    <td className="py-2.5 text-brand-500 text-xs">
                      {doc.last_parsed_at
                        ? doc.last_parsed_at.slice(0, 16).replace('T', ' ')
                        : '—'}
                    </td>
                    <td className="py-2.5">
                      <div className="flex gap-1.5 flex-wrap">
                        <button
                          onClick={() => openDetail(doc, 'sections')}
                          className="text-xs text-brand-500 hover:text-brand-700"
                        >
                          详情
                        </button>
                        <button
                          onClick={() => openDetail(doc, 'profile')}
                          className="text-xs text-brand-500 hover:text-brand-700"
                        >
                          画像
                        </button>
                        <button
                          onClick={() => openDetail(doc, 'edit')}
                          className="text-xs text-brand-500 hover:text-brand-700"
                        >
                          编辑
                        </button>
                        <button
                          onClick={() => handleReparse(doc.id)}
                          disabled={!!busy[doc.id]}
                          className="text-xs text-brand-500 hover:text-brand-700 disabled:opacity-40"
                        >
                          {busy[doc.id] === 'reparse' ? '正在重新解析…' : '重解析'}
                        </button>
                        <button
                          onClick={() => handleToggle(doc)}
                          disabled={!!busy[doc.id]}
                          className="text-xs text-brand-500 hover:text-brand-700 disabled:opacity-40"
                        >
                          {doc.status === 'disabled' ? '启用' : '停用'}
                        </button>
                        <button
                          onClick={() => handleDelete(doc.id)}
                          disabled={!!busy[doc.id]}
                          className="text-xs text-red-500 hover:text-red-700 disabled:opacity-40"
                        >
                          {busy[doc.id] === 'deleting' ? '删除中…' : '删除'}
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

      {/* 详情侧栏 */}
      {selected && (
        <div className="w-[480px] border-l border-brand-100 bg-white flex flex-col">
          <div className="px-4 py-3 border-b border-brand-100 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-brand-800 truncate">
              {selected.title || selected.filename}
            </h2>
            <button
              onClick={() => setSelected(null)}
              className="text-brand-400 hover:text-brand-600 text-lg"
            >
              ×
            </button>
          </div>
          <div className="px-4 py-1.5 border-b border-brand-100 text-xs text-brand-500 flex gap-3 flex-wrap">
            <span>正文 v{selected.content_version ?? 0}</span>
            <span>索引 v{selected.index_version ?? 0}</span>
            <span>
              同步:{' '}
              {SYNC_LABEL[selected.sync_status || 'synced'] ||
                selected.sync_status}
            </span>
            <span>
              画像:{' '}
              {PROFILE_LABEL[selected.profile_status || 'none']}
            </span>
            {selected.last_parsed_at && (
              <span>解析于 {selected.last_parsed_at.slice(0, 16).replace('T', ' ')}</span>
            )}
          </div>
          <div className="flex border-b border-brand-100 text-xs">
            {(['sections', 'profile', 'edit'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => openDetail(selected, tab)}
                className={`px-3 py-2 ${
                  detailTab === tab
                    ? 'border-b-2 border-brand-500 text-brand-700 font-medium'
                    : 'text-brand-400'
                }`}
              >
                {tab === 'sections' ? '章节' : tab === 'profile' ? '画像' : '全文编辑'}
              </button>
            ))}
          </div>
          {detailError && (
            <div className="px-4 py-2 bg-red-50 text-red-600 text-xs border-b border-red-100">
              {detailError}
            </div>
          )}
          <div className="flex-1 overflow-y-auto p-4 text-sm">
            {detailData === null && !detailError ? (
              <p className="text-brand-400">加载中…</p>
            ) : detailTab === 'sections' ? (
              <div className="space-y-3">
                {(Array.isArray(detailData) ? detailData : []).map(
                  (sec: DocSection) => (
                    <div key={sec.id}>
                      <div className="font-medium text-brand-700">
                        {'  '.repeat((sec.level || 1) - 1)}
                        {sec.heading}
                      </div>
                      <div className="text-brand-500 text-xs whitespace-pre-wrap mt-0.5">
                        {(sec.content || '').slice(0, 200)}
                        {(sec.content || '').length > 200 ? '…' : ''}
                      </div>
                    </div>
                  ),
                )}
                {Array.isArray(detailData) && detailData.length === 0 && (
                  <p className="text-brand-400 text-xs">
                    暂无章节（文档可能尚未解析成功）
                  </p>
                )}
              </div>
            ) : detailTab === 'profile' ? (
              <ProfilePanel
                data={detailData as DocProfileResult | null}
                doc={selected}
                busy={!!busy[selected.id]}
                onGenerate={() => handleGenerateProfile(selected)}
              />
            ) : (
              <div className="flex flex-col h-full">
                <label className="text-xs text-brand-500 mb-1">文档标题</label>
                <input
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  className="rounded-lg border border-brand-200 px-2.5 py-1.5 text-sm text-brand-800 focus:outline-none focus:ring-2 focus:ring-brand-300 mb-3"
                />
                <label className="text-xs text-brand-500 mb-1">
                  正文（Markdown / 纯文本，保存后需重解析才更新检索）
                </label>
                <textarea
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  rows={16}
                  className="flex-1 min-h-[240px] rounded-lg border border-brand-200 px-2.5 py-1.5 text-sm text-brand-800 font-mono leading-relaxed focus:outline-none focus:ring-2 focus:ring-brand-300 resize-none"
                />
                <div className="flex gap-2 mt-3">
                  <button
                    onClick={() => handleSaveEdit(false)}
                    disabled={!!busy[selected.id]}
                    className="rounded-lg bg-brand-700 text-white px-3 py-1.5 text-xs font-medium hover:bg-brand-800 disabled:opacity-40"
                  >
                    {busy[selected.id] === 'save' ? '保存中…' : '保存'}
                  </button>
                  <button
                    onClick={() => handleSaveEdit(true)}
                    disabled={!!busy[selected.id]}
                    className="rounded-lg bg-blue-600 text-white px-3 py-1.5 text-xs font-medium hover:bg-blue-700 disabled:opacity-40"
                  >
                    {busy[selected.id] === 'save_reparse'
                      ? '保存并重解析中…'
                      : '保存并重新解析'}
                  </button>
                  <button
                    onClick={handleCancelEdit}
                    disabled={!!busy[selected.id]}
                    className="rounded-lg border border-brand-200 text-brand-600 px-3 py-1.5 text-xs hover:bg-brand-50 disabled:opacity-40"
                  >
                    取消
                  </button>
                  <button
                    onClick={() => handleReparse(selected.id, '手动重解析')}
                    disabled={!!busy[selected.id]}
                    className="rounded-lg border border-brand-200 text-brand-600 px-3 py-1.5 text-xs hover:bg-brand-50 disabled:opacity-40"
                  >
                    {busy[selected.id] === 'reparse'
                      ? '正在重新解析…'
                      : '手动重解析'}
                  </button>
                </div>
                <p className="text-xs text-brand-400 mt-2">
                  重解析使用「当前正文」作为来源；编辑不会覆盖原始文件。
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ProfilePanel({
  data,
  doc,
  busy,
  onGenerate,
}: {
  data: DocProfileResult | null;
  doc: DocInfo;
  busy: boolean;
  onGenerate: () => void;
}) {
  const status = data?.profile_status || doc.profile_status || 'none';
  const profile = data?.profile || doc.profile || null;
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span
          className={`px-2 py-0.5 rounded text-xs ${
            status === 'ready'
              ? 'bg-green-100 text-green-700'
              : status === 'error'
                ? 'bg-red-100 text-red-700'
                : status === 'generating'
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-brand-100 text-brand-600'
          }`}
        >
          {PROFILE_LABEL[status] || status}
        </span>
        <button
          onClick={onGenerate}
          disabled={busy || status === 'generating'}
          className="rounded-lg bg-brand-700 text-white px-3 py-1.5 text-xs font-medium hover:bg-brand-800 disabled:opacity-40"
        >
          {status === 'generating'
            ? '正在生成…'
            : status === 'none' || status === 'error'
              ? '生成画像'
              : '重新生成'}
        </button>
      </div>
      {status === 'error' && (
        <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
          画像生成失败，请重试。
          {data?.profile_error ? `（${data.profile_error}）` : ''}
        </p>
      )}
      {status === 'generating' && (
        <p className="text-xs text-blue-600">正在调用模型分析文档内容…</p>
      )}
      {status === 'none' && (
        <p className="text-xs text-brand-400">
          尚未生成画像。点击「生成画像」由 AI 分析文档结构、主题与关键词，
          用于提升检索相关性。
        </p>
      )}
      {profile && (
        <div className="space-y-2 text-xs">
          <div>
            <div className="text-brand-400 mb-0.5">摘要</div>
            <div className="text-brand-700">{profile.summary || '—'}</div>
          </div>
          <div>
            <div className="text-brand-400 mb-0.5">主题</div>
            <div className="flex flex-wrap gap-1">
              {profile.topics?.map((t, i) => (
                <span
                  key={i}
                  className="px-1.5 py-0.5 rounded bg-brand-50 text-brand-600"
                >
                  {t}
                </span>
              ))}
              {!profile.topics?.length && <span className="text-brand-300">—</span>}
            </div>
          </div>
          <div>
            <div className="text-brand-400 mb-0.5">实体</div>
            <div className="flex flex-wrap gap-1">
              {profile.entities?.map((t, i) => (
                <span
                  key={i}
                  className="px-1.5 py-0.5 rounded bg-brand-50 text-brand-600"
                >
                  {t}
                </span>
              ))}
              {!profile.entities?.length && <span className="text-brand-300">—</span>}
            </div>
          </div>
          <div>
            <div className="text-brand-400 mb-0.5">关键词</div>
            <div className="flex flex-wrap gap-1">
              {profile.keywords?.map((t, i) => (
                <span
                  key={i}
                  className="px-1.5 py-0.5 rounded bg-brand-50 text-brand-600"
                >
                  {t}
                </span>
              ))}
              {!profile.keywords?.length && <span className="text-brand-300">—</span>}
            </div>
          </div>
          <div>
            <div className="text-brand-400 mb-0.5">可能问题</div>
            <ul className="list-disc pl-4 text-brand-600 space-y-0.5">
              {profile.possible_questions?.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
              {!profile.possible_questions?.length && (
                <li className="list-none text-brand-300">—</li>
              )}
            </ul>
          </div>
          {profile.created_at && (
            <div className="text-brand-300 pt-1 border-t border-brand-50">
              生成时间: {profile.created_at.slice(0, 16).replace('T', ' ')}
            </div>
          )}
        </div>
      )}
    </div>
  );
}