import type { ButtonHTMLAttributes, InputHTMLAttributes } from 'react';

/** 基础输入框（品牌风格统一） */
export function Input({ className = '', ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded-xl border border-brand-200 bg-white px-3.5 py-2.5 text-sm text-brand-800 shadow-sm transition placeholder:text-brand-400 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100 ${className}`}
    />
  );
}

/** 基础主按钮（品牌风格统一） */
export function Button({
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`rounded-xl bg-brand-800 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-300 disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
    />
  );
}
