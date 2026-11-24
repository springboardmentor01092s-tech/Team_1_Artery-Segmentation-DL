import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { authApi } from '../api/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(() => Boolean(localStorage.getItem('vascuai_token')));
  const [sessionError, setSessionError] = useState('');
  const [restorationError, setRestorationError] = useState('');
  const restoration = useRef({ generation: 0, controller: null });

  const cancelRestoration = useCallback(() => {
    restoration.current.generation += 1;
    restoration.current.controller?.abort();
  }, []);

  const clearSession = useCallback(() => {
    cancelRestoration();
    localStorage.removeItem('vascuai_token');
    localStorage.removeItem('vascuai_user');
    setUser(null);
    setLoading(false);
    setRestorationError('');
  }, [cancelRestoration]);

  const restoreSession = useCallback(async () => {
    cancelRestoration();
    const token = localStorage.getItem('vascuai_token');
    const generation = restoration.current.generation;
    const controller = new AbortController();
    restoration.current.controller = controller;
    const current = () => generation === restoration.current.generation
      && token === localStorage.getItem('vascuai_token');
    setUser(null);
    setRestorationError('');
    setLoading(Boolean(token));
    if (!token) return;
    try {
      const identity = await authApi.me({ signal: controller.signal, timeout: 15000 });
      if (current()) setUser(identity);
    } catch (error) {
      if (!current() || controller.signal.aborted) return;
      if (error.response?.status === 401) clearSession();
      else setRestorationError('Your session could not be verified. Retry when the connection is available, or sign out on this device.');
    } finally {
      if (current()) setLoading(false);
    }
  }, [cancelRestoration, clearSession]);

  useEffect(() => {
    let active = true;
    Promise.resolve().then(() => { if (active) restoreSession(); });
    const storageChanged = (event) => {
      if (event.storageArea && event.storageArea !== localStorage) return;
      if (event.key === 'vascuai_token'
          || event.key === null && localStorage.getItem('vascuai_token') === null) restoreSession();
    };
    window.addEventListener('vascuai:unauthorized', clearSession);
    window.addEventListener('storage', storageChanged);
    return () => {
      active = false;
      cancelRestoration();
      window.removeEventListener('vascuai:unauthorized', clearSession);
      window.removeEventListener('storage', storageChanged);
    };
  }, [clearSession, restoreSession, cancelRestoration]);

  const saveSession = useCallback((data) => {
    cancelRestoration();
    localStorage.setItem('vascuai_token', data.access_token);
    // Identity is restored from the server, never from this browser cache.
    localStorage.removeItem('vascuai_user');
    setUser(data.user);
    setSessionError('');
    setRestorationError('');
    setLoading(false);
    return data.user;
  }, [cancelRestoration]);

  const acceptAuthentication = useCallback(async (request) => {
    const generation = restoration.current.generation;
    const token = localStorage.getItem('vascuai_token');
    const result = await request();
    if (generation !== restoration.current.generation || token !== localStorage.getItem('vascuai_token')) {
      throw new Error('Your session changed. Sign in again before continuing.');
    }
    return saveSession(result);
  }, [saveSession]);
  const login = useCallback((email, password) =>
    acceptAuthentication(() => authApi.login(email, password)), [acceptAuthentication]);
  const register = useCallback((payload) =>
    acceptAuthentication(() => authApi.register(payload)), [acceptAuthentication]);
  const updateProfile = useCallback(async (payload) => {
    const token = localStorage.getItem('vascuai_token');
    const generation = restoration.current.generation;
    const identity = await authApi.updateProfile(payload);
    if (token !== localStorage.getItem('vascuai_token') || generation !== restoration.current.generation) {
      throw new Error('Your session changed. Reload your profile before continuing.');
    }
    setUser(identity);
    return identity;
  }, []);
  const changePassword = useCallback(async (current, password) => {
    const token = localStorage.getItem('vascuai_token');
    const generation = restoration.current.generation;
    const result = await authApi.changePassword(current, password);
    if (token !== localStorage.getItem('vascuai_token') || generation !== restoration.current.generation) {
      throw new Error('Your session changed. Sign in again before continuing.');
    }
    return saveSession(result);
  }, [saveSession]);
  const logout = useCallback(async () => {
    const token = localStorage.getItem('vascuai_token');
    const generation = restoration.current.generation;
    const current = () => token === localStorage.getItem('vascuai_token')
      && generation === restoration.current.generation;
    try { await authApi.logout(); }
    catch {
      if (current()) setSessionError('Signed out on this device. Server session revocation could not be confirmed.');
    } finally { if (current()) clearSession(); }
  }, [clearSession]);
  const isRole = useCallback((...roles) => user && roles.includes(user.role), [user]);

  return (
    <AuthContext.Provider value={{
      user, loading, sessionError, restorationError, retrySession: restoreSession,
      dismissSession: clearSession, login, register, logout, isRole, updateProfile, changePassword,
    }}>{children}</AuthContext.Provider>
  );
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
};
