"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { fetchAgentRuns } from "@/lib/api"
import type { AgentRunOut } from "@/lib/api"
import { GitPullRequest, Clock, PlayCircle, CheckCircle2, XCircle, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

const TERMINAL = new Set(["completed", "failed"])
const POLL_INTERVAL_MS = 3000

function hasRunning(runs: AgentRunOut[]) {
  return runs.some((r) => !TERMINAL.has(r.status))
}

function StatusIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckCircle2 className="h-5 w-5 text-green-500" />
  if (status === "failed") return <XCircle className="h-5 w-5 text-red-500" />
  if (status === "running") return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />
  return <PlayCircle className="h-5 w-5 text-neutral-500" />
}

function formatTime(isoStr: string | null) {
  if (!isoStr) return "—"
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(isoStr))
}

interface Props {
  initialRuns: AgentRunOut[]
  repoNames: Record<string, string>
}

export function AgentsListClient({ initialRuns, repoNames }: Props) {
  const [runs, setRuns] = useState<AgentRunOut[]>(initialRuns)

  // Sync when server re-renders (e.g. after a new run starts).
  useEffect(() => {
    setRuns(initialRuns)
  }, [initialRuns])

  // Poll while any run is not in a terminal state.
  useEffect(() => {
    if (!hasRunning(runs)) return

    let active = true
    let timer: ReturnType<typeof setTimeout>

    async function poll() {
      try {
        const data = await fetchAgentRuns({ limit: 50 })
        if (!active) return
        setRuns(data.runs)
        if (hasRunning(data.runs)) {
          timer = setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch {
        if (active) timer = setTimeout(poll, POLL_INTERVAL_MS)
      }
    }

    timer = setTimeout(poll, POLL_INTERVAL_MS)
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [runs])

  if (runs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-12 rounded-xl border border-neutral-800 bg-neutral-900/30 border-dashed">
        <GitPullRequest className="h-10 w-10 text-neutral-600 mb-4" />
        <p className="text-neutral-300 font-medium">No agent runs yet</p>
        <p className="text-neutral-500 text-sm mt-1">Select an indexed repository and start a run.</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {runs.map((run) => {
        const repoName = repoNames[run.repository_id] ?? "Unknown Repository"
        const issueTitle = (run.result?.selected_issue as { title?: string } | null)?.title || "Resolving Issue..."

        return (
          <Link
            key={run.id}
            href={`/agents/${run.id}`}
            className="group flex flex-col sm:flex-row sm:items-center justify-between p-4 rounded-xl border border-neutral-800 bg-neutral-900/50 hover:bg-neutral-800 hover:border-neutral-700 transition-all duration-200"
          >
            <div className="flex items-center gap-4">
              <div className="flex items-center justify-center bg-neutral-950 rounded-full h-10 w-10 border border-neutral-800">
                <StatusIcon status={run.status} />
              </div>
              <div>
                <h3 className="text-sm font-medium text-white group-hover:text-blue-400 transition-colors">
                  {issueTitle}
                </h3>
                <div className="flex items-center gap-2 mt-1 text-xs text-neutral-500">
                  <span className="font-mono">{repoName}</span>
                  <span>•</span>
                  <span className={cn(
                    "font-medium uppercase tracking-wider text-[10px] px-1.5 py-0.5 rounded-sm",
                    run.status === "completed" ? "bg-green-500/10 text-green-400" :
                    run.status === "failed" ? "bg-red-500/10 text-red-400" :
                    run.status === "running" ? "bg-blue-500/10 text-blue-400" :
                    "bg-neutral-800 text-neutral-400"
                  )}>
                    {run.status}
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-8 mt-4 sm:mt-0 text-xs text-neutral-400">
              <div className="flex flex-col gap-1 items-start sm:items-end w-32">
                <span className="text-neutral-500 uppercase tracking-wider text-[10px] font-medium">Stage</span>
                <span className="text-white capitalize">
                  {run.current_node ? run.current_node.replace(/_/g, " ") : "Initializing"}
                </span>
              </div>
              <div className="flex flex-col gap-1 items-start sm:items-end w-32">
                <span className="text-neutral-500 uppercase tracking-wider text-[10px] font-medium">Started</span>
                <div className="flex items-center gap-1.5">
                  <Clock className="h-3.5 w-3.5 text-neutral-500" />
                  <span>{formatTime(run.started_at)}</span>
                </div>
              </div>
            </div>
          </Link>
        )
      })}
    </div>
  )
}
