"use client"

import { useState } from "react"
import { registerRepository } from "@/lib/api"
import { cn } from "@/lib/utils"

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
        className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700"
      >
        Connect Repository
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setOpen(false)}
          />
          <div className="relative z-10 w-full max-w-md rounded-lg border border-gray-200 bg-white p-6 shadow-lg">
            <h2 className="text-sm font-semibold text-gray-900">Connect a Repository</h2>
            <p className="mt-1 text-xs text-gray-500">
              Paste a GitHub repository URL to begin ingestion.
            </p>

            <form onSubmit={handleSubmit} className="mt-4 space-y-3">
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://github.com/owner/repository"
                required
                className={cn(
                  "w-full rounded-md border px-3 py-2 text-sm outline-none",
                  "border-gray-300 focus:border-gray-500 focus:ring-1 focus:ring-gray-500",
                  error && "border-red-400"
                )}
              />
              <input
                type="password"
                value={pat}
                onChange={(e) => setPat(e.target.value)}
                placeholder="ghp_xxxx (optional — required for write access)"
                autoComplete="off"
                className={cn(
                  "w-full rounded-md border px-3 py-2 text-sm outline-none",
                  "border-gray-300 focus:border-gray-500 focus:ring-1 focus:ring-gray-500"
                )}
              />
              {error && <p className="text-xs text-red-600">{error}</p>}

              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
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
