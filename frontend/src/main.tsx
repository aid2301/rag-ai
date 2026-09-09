import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import { AdminApp } from './AdminApp.tsx';
import './index.css';

/** 基于 hash 路由：普通界面为 / ，管理后台为 /#/admin */
export function Root() {
  const [isAdmin, setIsAdmin] = useState(
    () => window.location.hash.startsWith('#/admin'),
  );

  useEffect(() => {
    const onHash = () => setIsAdmin(window.location.hash.startsWith('#/admin'));
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  return isAdmin ? <AdminApp /> : <App />;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
