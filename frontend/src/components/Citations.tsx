import { useState } from 'react';
import type { Citation } from '../api';

export function Citations({ citations }: { citations: Citation[] }) {
  const [expanded, setExpanded] = useState(false);
  if (!citations || citations.length === 0) return null;
  return (
    <div className="mt-3 border-t border-brand-100 pt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-xs text-brand-500 hover:text-brand-700 transition"
      >
        <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none">
          <path
            d={expanded ? 'M4 8L8 4' : 'M4 4L8 8'}
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
        参考来源 {citations.length}
      </button>
      {expanded && (
        <div className="mt-2 space-y-2">
          {citations.map((c) => (
            <div
              key={c.index}
              className="rounded-lg bg-brand-50 border border-brand-100 p-2.5 text-xs"
            >
              <div className="font-medium text-brand-700">
                [{c.index}] {c.document_title}
              </div>
              <div className="text-brand-500 mt-0.5">
                {c.section}
                {c.page ? ` · 第 ${c.page} 页` : ''}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
