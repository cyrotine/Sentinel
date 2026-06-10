"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { fetchIssues, startAgentRun } from "@/lib/api"
import type { IssueOut } from "@/lib/api"

interface RepoOption {
  id: string
  full_name: string
}

export function StartAgentRunButton({ repos }: { repos: RepoOption[] }) {
  const router = useRouter()
  const [selected, setSelected] = useState(repos[0]?.id ?? "")
  const [issues, setIssues] = useState<IssueOut[]>([])
  const [issuesLoading, setIssuesLoading] = useState(false)
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!selected) return
    setIssuesLoading(true)
    setSelectedIssueId(null)
    setIssues([])
    fetchIssues(selected, { limit: 50 })
      .then((d) => setIssues(d.issues))
      .catch(() => setIssues([]))
      .finally(() => setIssuesLoading(false))
  }, [selected])

  async function handleStart() {
    if (!selected || !selectedIssueId) return
    setLoading(true)
    setError(null)
    try {
      const { run_id } = await startAgentRun({ repository_id: selected, target_issue_id: selectedIssueId })
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
    <div className="flex flex-col gap-3 min-w-72">
      <div className="flex items-center gap-2">
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={loading}
          className="flex-1 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 disabled:opacity-50"
        >
          {repos.map((r) => (
            <option key={r.id} value={r.id}>
              {r.full_name}
            </option>
          ))}
        </select>
        <button
          onClick={handleStart}
          disabled={loading || !selectedIssueId}
          className="rounded-md bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
        >
          {loading ? "Starting…" : "Run agents"}
        </button>
      </div>

      <div className="rounded-md border border-gray-200 bg-white">
        <p className="border-b border-gray-100 px-3 py-2 text-xs font-medium uppercase tracking-wide text-gray-500">
          Select an issue
        </p>
        {issuesLoading ? (
          <p className="px-3 py-3 text-xs text-gray-400">Loading issues…</p>
        ) : issues.length === 0 ? (
          <p className="px-3 py-3 text-xs text-gray-400">No open issues found.</p>
        ) : (
          <ul className="max-h-48 overflow-y-auto divide-y divide-gray-50">
            {issues.map((issue) => (
              <li key={issue.id}>
                <button
                  onClick={() => setSelectedIssueId(issue.id)}
                  disabled={loading}
                  className={`w-full flex items-start gap-2 px-3 py-2 text-left text-sm transition-colors disabled:opacity-50 ${
                    selectedIssueId === issue.id
                      ? "bg-gray-900 text-white"
                      : "hover:bg-gray-50 text-gray-800"
                  }`}
                >
                  <span className={`shrink-0 font-mono text-xs mt-0.5 ${selectedIssueId === issue.id ? "text-gray-300" : "text-gray-400"}`}>
                    #{issue.number}
                  </span>
                  <span className="truncate">{issue.title}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  )
}
