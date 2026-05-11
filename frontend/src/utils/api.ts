/**
 * Axios instance — auto-injects Bearer token from auth store.
 */

import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 180_000,
})

// Request interceptor: attach JWT
api.interceptors.request.use((config) => {
  // Read token directly from localStorage to avoid circular imports with zustand
  try {
    const raw = localStorage.getItem('auth-storage')
    if (raw) {
      const { state } = JSON.parse(raw)
      if (state?.token) {
        config.headers.Authorization = `Bearer ${state.token}`
      }
    }
  } catch {
    // ignore parse errors
  }
  return config
})

// Response interceptor: handle 401 globally
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('auth-storage')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api
