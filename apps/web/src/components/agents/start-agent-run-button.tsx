"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { startAgentRun } from "@/lib/api"

interface RepoOption {
  id: string
  full_name: string
}

export function StartAgentRunButton({ repos }: { repos: RepoOption[] }) {
  const router = useRouter()
  const [selected, setSelected] = useState(repos[0]?.id ?? "")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleStart() {
    if (!selected) return
    setLoading(true)
    setError(null)
    try {
      const { run_id } = await startAgentRun({ repository_id: selected })
      router.push(`/agents/${run_id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start run")
      setLoading(false)
    }
  }

  if (repos.length === 0) {
    return (
      <p className="text-sm text-gray-500">
        No indexed repositories available. Index a repository before running agents.
      </p>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <select
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        disabled={loading}
        className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 disabled:opacity-50"
      >
        {repos.map((r) => (
          <option key={r.id} value={r.id}>
            {r.full_name}
          </option>
        ))}
      </select>
      <button
        onClick={handleStart}
        disabled={loading || !selected}
        className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
      >
        {loading ? "Starting…" : "Run agents"}
      </button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  )
}
