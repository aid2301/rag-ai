import { api } from './http.ts';

// ---- 普通用户登录态 ----
const USER_TOKEN_KEY = 'kb_user_token';
const USER_INFO_KEY = 'kb_user_info';

export interface UserInfo {
  id: string;
  username: string;
  display_name: string;
}

export function getUserToken(): string | null {
  try {
    return localStorage.getItem(USER_TOKEN_KEY);
  } catch {
    return null;
  }
}
export function setUserToken(token: string | null) {
  try {
    if (token) localStorage.setItem(USER_TOKEN_KEY, token);
    else localStorage.removeItem(USER_TOKEN_KEY);
  } catch {}
}
export function getUserInfo(): UserInfo | null {
  try {
    const raw = localStorage.getItem(USER_INFO_KEY);
    return raw ? (JSON.parse(raw) as UserInfo) : null;
  } catch {
    return null;
  }
}
export function setUserInfo(info: UserInfo | null) {
  try {
    if (info) localStorage.setItem(USER_INFO_KEY, JSON.stringify(info));
    else localStorage.removeItem(USER_INFO_KEY);
  } catch {}
}

export function userHeaders(): Record<string, string> {
  const t = getUserToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export const apiAuth = {
  login: (username: string, password: string) =>
    api<{ ok: boolean; token: string; user: UserInfo }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  me: () => api<UserInfo>('/api/auth/me', { headers: userHeaders() }),
};

const ADMIN_TOKEN_KEY = 'kb_admin_token';

export function getAdminToken(): string | null {
  try {
    return localStorage.getItem(ADMIN_TOKEN_KEY);
  } catch {
    return null;
  }
}
export function setAdminToken(token: string | null) {
  try {
    if (token) localStorage.setItem(ADMIN_TOKEN_KEY, token);
    else localStorage.removeItem(ADMIN_TOKEN_KEY);
  } catch {}
}

export function adminHeaders(): Record<string, string> {
  const t = getAdminToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export const apiAdmin = {
  login: (username: string, password: string) =>
    api<{ ok: boolean; token: string }>('/api/admin/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
};
