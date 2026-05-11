import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { useNavigate } from 'react-router-dom'
import { useDocStore } from '../store/docStore'
import { Upload, FileText, Mic, Video, X, ChevronRight, Loader2 } from 'lucide-react'
import { formatBytes } from '../utils/format'
import clsx from 'clsx'

const ACCEPTED = {
  'application/pdf': ['.pdf'],
  'audio/mpeg': ['.mp3'],
  'audio/wav': ['.wav'],
  'audio/ogg': ['.ogg'],
  'video/mp4': ['.mp4'],
  'video/webm': ['.webm'],
  'video/quicktime': ['.mov'],
}

export default function DashboardPage() {
  const { uploadFile, isUploading, uploadProgress, error, documents, selectDocument } = useDocStore()
  const navigate = useNavigate()
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [uploadError, setUploadError] = useState('')

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) setPendingFile(accepted[0])
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    maxFiles: 1,
    maxSize: 500 * 1024 * 1024,
  })

  const handleUpload = async () => {
    if (!pendingFile) return
    setUploadError('')
    try {
      const doc = await uploadFile(pendingFile)
      setPendingFile(null)
      selectDocument(doc)
      navigate(`/chat/${doc.id}`)
    } catch (err: any) {
      setUploadError(err.message)
    }
  }

  const fileIcon = (type: string) => {
    if (type.startsWith('audio')) return <Mic className="text-violet-400" size={28} />
    if (type.startsWith('video')) return <Video className="text-sky-400" size={28} />
    return <FileText className="text-rose-400" size={28} />
  }

  return (
    <div className="h-full flex flex-col items-center justify-center p-8 bg-zinc-950">
      <div className="w-full max-w-xl space-y-6">

        {/* Header */}
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white tracking-tight">Upload a file to chat</h1>
          <p className="text-sm text-zinc-500 mt-1">
            Supports PDF, MP3, WAV, OGG, MP4, WebM, MOV — up to 500 MB
          </p>
        </div>

        {/* Drop zone */}
        <div
          {...getRootProps()}
          className={clsx(
            'relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all duration-200',
            isDragActive
              ? 'border-violet-500 bg-violet-500/5 scale-[1.01]'
              : 'border-zinc-700 hover:border-zinc-500 bg-zinc-900'
          )}
        >
          <input {...getInputProps()} />
          {pendingFile ? (
            <div className="flex items-center justify-center gap-4">
              {fileIcon(pendingFile.type)}
              <div className="text-left">
                <p className="text-sm font-medium text-white">{pendingFile.name}</p>
                <p className="text-xs text-zinc-500">{formatBytes(pendingFile.size)}</p>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); setPendingFile(null) }}
                className="ml-auto text-zinc-500 hover:text-zinc-300 transition-colors"
              >
                <X size={18} />
              </button>
            </div>
          ) : (
            <>
              <Upload className="mx-auto text-zinc-600 mb-3" size={36} />
              <p className="text-sm font-medium text-zinc-300">
                {isDragActive ? 'Drop it here!' : 'Drag & drop your file'}
              </p>
              <p className="text-xs text-zinc-600 mt-1">or click to browse</p>
            </>
          )}
        </div>

        {/* Upload progress */}
        {isUploading && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-zinc-500">
              <span className="flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" /> Uploading...</span>
              <span>{uploadProgress}%</span>
            </div>
            <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-violet-500 to-rose-500 transition-all duration-300 rounded-full"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        )}

        {/* Error */}
        {(uploadError || error) && (
          <p className="text-sm text-red-400 text-center">{uploadError || error}</p>
        )}

        {/* Upload button */}
        {pendingFile && !isUploading && (
          <button
            onClick={handleUpload}
            className="w-full flex items-center justify-center gap-2 bg-violet-600 hover:bg-violet-500 text-white font-medium py-3 rounded-xl text-sm transition-colors"
          >
            Upload & Process <ChevronRight size={16} />
          </button>
        )}

        {/* Recent docs */}
        {documents.length > 0 && !pendingFile && (
          <div className="mt-2">
            <p className="text-xs text-zinc-600 font-medium uppercase tracking-wide mb-2">Recent files</p>
            <div className="space-y-1">
              {documents.slice(0, 4).map((doc) => (
                <button
                  key={doc.id}
                  onClick={() => { selectDocument(doc); navigate(`/chat/${doc.id}`) }}
                  disabled={doc.status !== 'done'}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-left"
                >
                  {fileIcon(doc.file_type + '/')}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-zinc-200 truncate">{doc.original_name}</p>
                    <p className="text-[10px] text-zinc-500">{formatBytes(doc.file_size_bytes)}</p>
                  </div>
                  <span className={clsx(
                    'text-[10px] px-2 py-0.5 rounded font-medium',
                    doc.status === 'done' ? 'bg-emerald-500/20 text-emerald-300' :
                    doc.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                    'bg-amber-500/20 text-amber-300'
                  )}>
                    {doc.status}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
