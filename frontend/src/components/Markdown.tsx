import React from 'react';

/** 轻量 Markdown 渲染器（不引入外部库，支持标题/列表/粗体/代码块/表格/引用/链接） */
export function Markdown({ content }: { content: string }) {
  return (
    <div className="markdown-body leading-relaxed">
      {renderMd(content)}
    </div>
  );
}

function renderMd(text: string): React.ReactNode[] {
  const lines = text.split('\n');
  const nodes: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    // 代码块
    if (line.trim().startsWith('```')) {
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      nodes.push(
        <pre key={key++}>
          <code>{codeLines.join('\n')}</code>
        </pre>,
      );
      continue;
    }

    // 表格
    if (line.includes('|') && i + 1 < lines.length && lines[i + 1].includes('---')) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].includes('|')) {
        tableLines.push(lines[i]);
        i++;
      }
      nodes.push(renderTable(tableLines, key++));
      continue;
    }

    // 标题
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) {
      const level = h[1].length;
      const cls = `font-semibold mb-1 ${
        level === 1 ? 'text-xl' : level === 2 ? 'text-lg' : 'text-base'
      }`;
      nodes.push(
        React.createElement(`h${level}`, { key: key++, className: cls }, renderInline(h[2])),
      );
      i++;
      continue;
    }

    // 引用
    if (line.startsWith('> ')) {
      const quoteLines: string[] = [];
      while (i < lines.length && lines[i].startsWith('> ')) {
        quoteLines.push(lines[i].slice(2));
        i++;
      }
      nodes.push(
        <blockquote
          key={key++}
          className="border-l-3 border-brand-300 pl-3 text-brand-600 italic my-2"
          style={{ borderLeftWidth: 3 }}
        >
          {renderInline(quoteLines.join(' '))}
        </blockquote>,
      );
      continue;
    }

    // 无序列表
    if (line.match(/^\s*[-*]\s+/)) {
      const items: string[] = [];
      while (i < lines.length && lines[i].match(/^\s*[-*]\s+/)) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ''));
        i++;
      }
      nodes.push(
        <ul key={key++} className="list-disc pl-5 space-y-0.5 my-1">
          {items.map((it, idx) => (
            <li key={idx}>{renderInline(it)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    // 有序列表
    if (line.match(/^\s*\d+\.\s+/)) {
      const items: string[] = [];
      while (i < lines.length && lines[i].match(/^\s*\d+\.\s+/)) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ''));
        i++;
      }
      nodes.push(
        <ol key={key++} className="list-decimal pl-5 space-y-0.5 my-1">
          {items.map((it, idx) => (
            <li key={idx}>{renderInline(it)}</li>
          ))}
        </ol>,
      );
      continue;
    }

    // 空行
    if (line.trim() === '') {
      i++;
      continue;
    }

    // 普通段落
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !lines[i].trim().startsWith('```') &&
      !lines[i].match(/^(#{1,4})\s+/) &&
      !lines[i].match(/^\s*[-*]\s+/) &&
      !lines[i].match(/^\s*\d+\.\s+/) &&
      !lines[i].startsWith('> ') &&
      !(lines[i].includes('|') && i + 1 < lines.length && lines[i + 1].includes('---'))
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    nodes.push(
      <p key={key++} className="my-1">
        {renderInline(paraLines.join(' '))}
      </p>,
    );
  }
  return nodes;
}

function renderTable(lines: string[], key: number): React.ReactNode {
  const parseRow = (l: string) =>
    l.split('|').filter((_, idx, arr) => idx !== 0 && idx !== arr.length - 1);
  const header = parseRow(lines[0]);
  const rows = lines.slice(2).map(parseRow);
  return (
    <table key={key}>
      <thead>
        <tr>
          {header.map((h, i) => (
            <th key={i}>{renderInline(h)}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, ri) => (
          <tr key={ri}>
            {row.map((cell, ci) => (
              <td key={ci}>{renderInline(cell)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function renderInline(text: string): React.ReactNode {
  // 处理 **粗体**、`代码`、[链接](url)、[n] 引用标记
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;
  const patterns: [RegExp, (m: RegExpMatchArray) => React.ReactNode][] = [
    [/\*\*(.+?)\*\*/, (m) => <strong key={key++}>{m[1]}</strong>],
    [/`(.+?)`/, (m) => <code key={key++}>{m[1]}</code>],
    [/\[(\d+)\]/, (m) => (
      <sup key={key++} className="text-brand-400 font-medium">
        [{m[1]}]
      </sup>
    )],
    [/\[([^\]]+)\]\(([^)]+)\)/, (m) => (
      <a key={key++} href={m[2]} target="_blank" rel="noopener" className="text-brand-500 underline">
        {m[1]}
      </a>
    )],
  ];

  while (remaining) {
    let earliest = -1;
    let match: RegExpMatchArray | null = null;
    let render: ((m: RegExpMatchArray) => React.ReactNode) | null = null;
    for (const [pat, fn] of patterns) {
      const m = remaining.match(pat);
      if (m && (earliest === -1 || m.index! < earliest)) {
        earliest = m.index!;
        match = m;
        render = fn;
      }
    }
    if (match && render && earliest >= 0) {
      if (earliest > 0) parts.push(remaining.slice(0, earliest));
      parts.push(render(match));
      remaining = remaining.slice(earliest + match[0].length);
      key++;
    } else {
      parts.push(remaining);
      break;
    }
  }
  return parts;
}
