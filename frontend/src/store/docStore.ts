/**
 * Document store — manages uploaded files and their processing status.
 */

import { create } from 'zustand'
import api from '../utils/api'

export type FileType = 'pdf' | 'audio' | 'video'
export type ProcessingStatus = 'pending' | 'processing' | 'done' | 'failed'

export interface Document {
  id: number
  original_name: string
  file_type: FileType
  file_size_bytes: number
  status: ProcessingStatus
  duration_seconds: number | null
  created_at: string
  processed_at: string | null
}

interface DocState {
  documents: Document[]
  selected: Document | null
  isUploading: boolean
  uploadProgress: number
  error: string | null
  fetchDocuments: () => Promise<void>
  uploadFile: (file: File) => Promise<Document>
  deleteDocument: (id: number) => Promise<void>
  selectDocument: (doc: Document | null) => void
  pollStatus: (id: number) => void
}

export const useDocStore = create<DocState>((set, get) => ({
  documents: [],
  selected: null,
  isUploading: false,
  uploadProgress: 0,
  error: null,

  fetchDocuments: async () => {
    try {
      const { data } = await api.get<Document[]>('/upload/')
      set({ documents: data })
    } catch (err: any) {
      set({ error: err.response?.data?.detail || 'Failed to load documents' })
    }
  },

  uploadFile: async (file: File) => {
    set({ isUploading: true, uploadProgress: 0, error: null })
    try {
      const form = new FormData()
      form.append('file', file)
      const { data } = await api.post<Document>('/upload/', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (evt) => {
          const pct = evt.total ? Math.round((evt.loaded / evt.total) * 100) : 0
          set({ uploadProgress: pct })
        },
      })
      set((s) => ({ documents: [data, ...s.documents] }))
      // Start polling until processing is done
      get().pollStatus(data.id)
      return data
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Upload failed'
      set({ error: msg })
      throw new Error(msg)
    } finally {
      set({ isUploading: false, uploadProgress: 0 })
    }
  },

  deleteDocument: async (id: number) => {
    await api.delete(`/upload/${id}`)
    set((s) => ({
      documents: s.documents.filter((d) => d.id !== id),
      selected: s.selected?.id === id ? null : s.selected,
    }))
  },

  selectDocument: (doc) => set({ selected: doc }),

  pollStatus: (id: number) => {
    const interval = setInterval(async () => {
      try {
        const { data } = await api.get<Document>(`/upload/${id}`)
        set((s) => ({
          documents: s.documents.map((d) => (d.id === id ? data : d)),
          selected: s.selected?.id === id ? data : s.selected,
        }))
        if (data.status === 'done' || data.status === 'failed') {
          clearInterval(interval)
        }
      } catch {
        clearInterval(interval)
      }
    }, 2500)
  },
}))
