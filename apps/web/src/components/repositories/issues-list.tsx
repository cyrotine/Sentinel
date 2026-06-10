"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { startAgentRun } from "@/lib/api"
import type { IssueOut } from "@/lib/api"

interface Props {
  issues: IssueOut[]
  total: number
  repositoryId: string
}

export function IssuesList({ issues, total, repositoryId }: Props) {
  const router = useRouter()
  const [tacklingId, setTacklingId] = useState<string | null>(null)
  const [tackleErrors, setTackleErrors] = useState<Record<string, string>>({})

  async function handleTackle(issueId: string) {
    setTacklingId(issueId)
    setTackleErrors((prev) => {
      const next = { ...prev }
      delete next[issueId]
      return next
    })
    try {
      const { run_id } = await startAgentRun({ repository_id: repositoryId, target_issue_id: issueId })
      router.push(`/agents/${run_id}`)
    } catch (e) {
      setTackleErrors((prev) => ({
        ...prev,
        [issueId]: e instanceof Error ? e.message : "Failed to start run",
      }))
      setTacklingId(null)
    }
  }

  if (issues.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <p className="text-xs text-gray-500">No open issues found.</p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-4 py-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Open Issues ({total})
        </h3>
      </div>
      <ul className="divide-y divide-gray-100 max-h-96 overflow-y-auto">
        {issues.map((issue) => (
          <li key={issue.id} className="flex items-start gap-3 px-4 py-3">
            <span className="shrink-0 text-xs font-mono text-gray-400 mt-0.5">
              #{issue.number}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-gray-800">{issue.title}</p>
              {issue.labels.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {issue.labels.map((label) => (
                    <span
                      key={label}
                      className="rounded-full bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600"
                    >
                      {label}
                    </span>
                  ))}
                </div>
              )}
              {tackleErrors[issue.id] && (
                <p className="mt-1 text-xs text-red-600">{tackleErrors[issue.id]}</p>
              )}
            </div>
            <button
              onClick={() => handleTackle(issue.id)}
              disabled={tacklingId !== null}
              className="shrink-0 rounded-md bg-gray-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-gray-700 disabled:opacity-50"
            >
              {tacklingId === issue.id ? "…" : "Tackle"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
