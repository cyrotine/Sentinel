"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { fetchAgentRun } from "@/lib/api"
import type { AgentRunOut } from "@/lib/api"
import { StatusBadge } from "@/components/ui/status-badge"

const TERMINAL = new Set(["completed", "failed"])
const POLL_INTERVAL_MS = 2000

interface PlanShape {
  approach_reasoning?: string
  affected_files?: string[]
  dependencies?: string[]
  tasks?: { id?: string; description?: string }[]
}
interface ReviewShape {
  approved?: boolean
  comments?: string[]
  security_issues?: string[]
  suggestions?: string[]
}
interface PrShape {
  title?: string
  body?: string
  branch?: string
  base_branch?: string
}
interface SelectedIssueShape {
  number?: number
  title?: string
  reasoning?: string
  estimated_complexity?: string
}
interface CodeChangeShape {
  file_path?: string
  description?: string
}

export function AgentRunDetail({ runId }: { runId: string }) {
  const [run, setRun] = useState<AgentRunOut | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout>

    async function poll() {
      try {
        const data = await fetchAgentRun(runId)
        if (!active) return
        setRun(data)
        if (!TERMINAL.has(data.status)) {
          timer = setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch (e) {
        if (!active) return
        setError(e instanceof Error ? e.message : "Failed to load run")
      }
    }

    poll()
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [runId])

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4">
        <p className="text-sm font-medium text-red-700">{error}</p>
        <Link href="/agents" className="mt-2 inline-block text-xs text-blue-600 hover:underline">
          ← Back to agents
        </Link>
      </div>
    )
  }

  if (!run) {
    return <p className="text-sm text-gray-500">Loading run…</p>
  }

  const result = run.result
  const issue = result?.selected_issue as SelectedIssueShape | null | undefined
  const plan = result?.plan as PlanShape | null | undefined
  const review = result?.review as ReviewShape | null | undefined
  const pr = result?.pull_request_draft as PrShape | null | undefined
  const changes = (result?.code_changes ?? []) as CodeChangeShape[]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Link href="/agents" className="text-sm text-blue-600 hover:underline">
            Agents
          </Link>
          <span className="text-gray-300">/</span>
          <h2 className="font-mono text-sm text-gray-900">{run.id.slice(0, 8)}</h2>
          <StatusBadge status={run.status} />
        </div>
        {!TERMINAL.has(run.status) && (
          <span className="text-xs text-gray-500">
            Running{run.current_node ? ` · ${run.current_node}` : ""}…
          </span>
        )}
      </div>

      {run.status === "failed" && run.error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-medium text-red-700">Run failed</p>
          <p className="mt-1 break-words text-xs text-red-600">{run.error}</p>
        </div>
      )}

      {issue && (
        <Section title="Selected issue">
          <p className="text-sm font-medium text-gray-900">
            {issue.number != null ? `#${issue.number} · ` : ""}
            {issue.title}
          </p>
          {issue.reasoning && <p className="mt-1 text-sm text-gray-500">{issue.reasoning}</p>}
          {issue.estimated_complexity && (
            <p className="mt-1 text-xs text-gray-400">Complexity: {issue.estimated_complexity}</p>
          )}
        </Section>
      )}

      {plan && (
        <Section title="Plan">
          {plan.approach_reasoning && (
            <p className="whitespace-pre-wrap text-sm text-gray-600">{plan.approach_reasoning}</p>
          )}
          {plan.tasks && plan.tasks.length > 0 && (
            <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-gray-700">
              {plan.tasks.map((t, i) => (
                <li key={t.id ?? i}>{t.description}</li>
              ))}
            </ol>
          )}
          {plan.affected_files && plan.affected_files.length > 0 && (
            <p className="mt-3 text-xs text-gray-500">
              Affected files: {plan.affected_files.join(", ")}
            </p>
          )}
        </Section>
      )}

      {changes.length > 0 && (
        <Section title={`Code changes (${changes.length})`}>
          <ul className="space-y-2 text-sm">
            {changes.map((c, i) => (
              <li key={c.file_path ?? i}>
                <span className="font-mono text-xs text-gray-900">{c.file_path}</span>
                {c.description && <p className="text-gray-500">{c.description}</p>}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {review && (
        <Section title="Review">
          <p className="text-sm">
            <span
              className={
                review.approved ? "font-medium text-green-700" : "font-medium text-red-700"
              }
            >
              {review.approved ? "Approved" : "Changes requested"}
            </span>
          </p>
          {review.comments && review.comments.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-gray-600">
              {review.comments.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          )}
          {review.security_issues && review.security_issues.length > 0 && (
            <div className="mt-2">
              <p className="text-xs font-medium uppercase tracking-wide text-red-600">
                Security
              </p>
              <ul className="list-disc space-y-1 pl-5 text-sm text-red-600">
                {review.security_issues.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}
        </Section>
      )}

      {pr && (
        <Section title="Pull request draft">
          <p className="text-sm font-medium text-gray-900">{pr.title}</p>
          {pr.branch && (
            <p className="mt-1 font-mono text-xs text-gray-500">
              {pr.branch} → {pr.base_branch ?? "main"}
            </p>
          )}
          {pr.body && (
            <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-md bg-gray-50 p-3 text-xs text-gray-700">
              {pr.body}
            </pre>
          )}
        </Section>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">{title}</h3>
      {children}
    </div>
  )
}
