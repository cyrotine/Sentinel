"use client"

import { useState } from "react"
import { registerRepository } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Plus, FolderGit2 } from "lucide-react"

interface ConnectRepositoryModalProps {
  onSuccess: () => void
}

export function ConnectRepositoryModal({ onSuccess }: ConnectRepositoryModalProps) {
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState("")
  const [pat, setPat] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await registerRepository(url.trim(), pat.trim() || undefined)
      setUrl("")
      setPat("")
      setOpen(false)
      onSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to connect repository")
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-black hover:bg-neutral-200 transition-colors"
      >
        <Plus className="w-4 h-4" />
        Connect Repository
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/80 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <div className="relative z-10 w-full max-w-lg rounded-2xl border border-neutral-800 bg-[#0A0A0A] p-6 shadow-2xl">
            <div className="flex items-center gap-3 mb-2">
              <div className="p-2 bg-neutral-900 rounded-lg border border-neutral-800">
                <FolderGit2 className="w-5 h-5 text-blue-400" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-white">Connect Repository</h2>
                <p className="text-xs text-neutral-400">
                  Paste a GitHub repository URL to begin ingestion and index creation.
                </p>
              </div>
            </div>

            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-neutral-300 uppercase tracking-wider">GitHub URL</label>
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://github.com/owner/repository"
                  required
                  className={cn(
                    "w-full rounded-lg border bg-neutral-900/50 px-3 py-2.5 text-sm text-white placeholder-neutral-500 outline-none transition-colors",
                    "border-neutral-800 focus:border-blue-500 focus:ring-1 focus:ring-blue-500",
                    error && "border-red-500"
                  )}
                />
              </div>
              
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-neutral-300 uppercase tracking-wider">Personal Access Token <span className="text-neutral-600 normal-case tracking-normal">(Optional)</span></label>
                <input
                  type="password"
                  value={pat}
                  onChange={(e) => setPat(e.target.value)}
                  placeholder="ghp_xxxx"
                  autoComplete="off"
                  className={cn(
                    "w-full rounded-lg border bg-neutral-900/50 px-3 py-2.5 text-sm text-white placeholder-neutral-500 outline-none transition-colors",
                    "border-neutral-800 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                  )}
                />
                <p className="text-[10px] text-neutral-500">Required if you want Forge to create Pull Requests directly in the repository.</p>
              </div>

              {error && <p className="text-xs text-red-400 bg-red-500/10 p-2 rounded border border-red-500/20">{error}</p>}

              <div className="flex justify-end gap-3 pt-4 border-t border-neutral-900 mt-6">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="rounded-lg px-4 py-2 text-sm font-medium text-neutral-400 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 transition-colors"
                >
                  {loading ? "Connecting…" : "Connect"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
