import { ROLES } from '../constants/permissions.js';

export const toUser = (user) => ({ ...user, name: user.full_name });

export function createAuthApi(api) {
  const session = (data) => ({ ...data, user: toUser(data.user) });
  return {
    async login(email, password) {
      return session((await api.post('/auth/login', { email, password })).data);
    },
    async register(payload) {
      await api.post('/auth/register', {
        full_name: payload.name, email: payload.email, password: payload.password,
        role: payload.role || 'Clinician', institution: payload.institution || '',
      });
      return this.login(payload.email, payload.password);
    },
    async me(options) {
      const user = (await api.get('/auth/me', options)).data;
      if (!user || !Number.isSafeInteger(user.id) || user.id <= 0 || user.is_active !== true
          || !Object.values(ROLES).includes(user.role) || typeof user.full_name !== 'string' || !user.full_name.trim()) {
        throw new Error('The server returned an invalid session identity');
      }
      return toUser(user);
    },
    async logout() { await api.post('/auth/logout'); },
    async updateProfile(payload) {
      return toUser((await api.patch('/auth/me', {
        full_name: payload.name, institution: payload.institution, department: payload.department,
      })).data);
    },
    async changePassword(current, password) {
      return session((await api.post('/auth/password', {
        current_password: current, new_password: password,
      })).data);
    },
  };
}
