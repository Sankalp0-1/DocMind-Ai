/**
 * Auth store — persists JWT token in localStorage.
 * All API calls read the token from here via axios interceptor.
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import api from '../utils/api'

interface User {
  id: number
  email: string
  username: string
  is_active: boolean
  created_at: string
}

interface AuthState {
  token: string | null
  user: User | null
  isLoading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, username: string, password: string) => Promise<void>
  logout: () => void
  fetchMe: () => Promise<void>
  clearError: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      isLoading: false,
      error: null,

      login: async (email, password) => {
        set({ isLoading: true, error: null })
        try {
          const form = new FormData()
          form.append('username', email)
          form.append('password', password)
          const { data } = await api.post('/auth/token', form, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
          set({ token: data.access_token })
          await get().fetchMe()
        } catch (err: any) {
          set({ error: err.response?.data?.detail || 'Login failed' })
          throw err
        } finally {
          set({ isLoading: false })
        }
      },

      register: async (email, username, password) => {
        set({ isLoading: true, error: null })
        try {
          await api.post('/auth/register', { email, username, password })
          await get().login(email, password)
        } catch (err: any) {
          set({ error: err.response?.data?.detail || 'Registration failed' })
          throw err
        } finally {
          set({ isLoading: false })
        }
      },

      logout: () => {
        set({ token: null, user: null })
      },

      fetchMe: async () => {
        try {
          const { data } = await api.get('/auth/me')
          set({ user: data })
        } catch {
          set({ token: null, user: null })
        }
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ token: state.token }),
    }
  )
)
