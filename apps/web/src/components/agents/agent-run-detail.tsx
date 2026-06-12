"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { fetchAgentRun } from "@/lib/api"
import type { AgentRunOut } from "@/lib/api"
import { DiffViewer } from "@/components/agents/diff-viewer"
import { CheckCircle2, Circle, Clock, GitPullRequest, Loader2, PlayCircle, Terminal, XCircle, FileCode, CheckSquare, GitBranch } from "lucide-react"
import { cn } from "@/lib/utils"

const TERMINAL = new Set(["completed", "failed"])
const POLL_INTERVAL_MS = 2000

type PipelineStage = "issue_selection" | "planner" | "developer" | "reviewer" | "pull_request"

// Maps the authoritative LangGraph node (run.current_node, written at node
// *start*) to a pipeline stage. This is the source of truth for the *active*
// step — result-presence only tells us which steps have *finished*.
// Node names mirror packages/workflows/forge_workflows/graph.py constants.
const NODE_TO_STAGE: Record<string, PipelineStage> = {
  repo_analyzer: "issue_selection",
  issue_analyzer: "issue_selection",
  retrieve_context: "issue_selection",
  load_full_files: "issue_selection",
  planner: "planner",
  developer: "developer",
  apply_patches: "developer",
  validator: "developer",
  test_agent: "developer",
  reviewer: "reviewer",
  pr_generator: "pull_request",
}

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
  patch?: string
  description?: string
}
interface RepairShape {
  iteration?: number
  triggers?: string[]
}

const TRIGGER_LABELS: Record<string, string> = {
  patch_failed: "patch failed to apply",
  validation_failed: "validation failed",
  review_rejected: "review rejected",
}

function PipelineStep({ label, isActive, isCompleted, isFailed }: { label: string; isActive: boolean; isCompleted: boolean; isFailed?: boolean }) {
  return (
    <div className="flex flex-col items-center gap-2 w-24">
      <div className={cn(
        "flex items-center justify-center w-8 h-8 rounded-full border-2 transition-colors",
        isCompleted ? "border-blue-500 bg-blue-500/10 text-blue-500" :
        isFailed ? "border-red-500 bg-red-500/10 text-red-500" :
        isActive ? "border-blue-400 bg-blue-400/20 text-blue-400 shadow-[0_0_10px_rgba(59,130,246,0.5)]" :
        "border-neutral-800 bg-neutral-900 text-neutral-600"
      )}>
        {isCompleted ? <CheckCircle2 className="w-5 h-5" /> : 
         isFailed ? <XCircle className="w-5 h-5" /> :
         isActive ? <Loader2 className="w-5 h-5 animate-spin" /> : 
         <Circle className="w-4 h-4" />}
      </div>
      <span className={cn(
        "text-[10px] font-medium uppercase tracking-wider text-center",
        isCompleted ? "text-blue-400" :
        isFailed ? "text-red-400" :
        isActive ? "text-blue-300" :
        "text-neutral-500"
      )}>
        {label}
      </span>
    </div>
  )
}

function PipelineConnector({ active }: { active: boolean }) {
  return (
    <div className="flex-1 h-[2px] mx-2 mt-4 bg-neutral-800 relative overflow-hidden rounded-full">
      {active && (
        <div className="absolute inset-0 bg-blue-500/50 animate-pulse" />
      )}
    </div>
  )
}

function ActivityLogItem({ time, message, type = "info" }: { time?: string; message: string; type?: "info" | "success" | "error" }) {
  return (
    <div className="flex gap-4 font-mono text-xs">
      <span className="text-neutral-600 shrink-0">{time ? new Date(time).toLocaleTimeString() : "--:--:--"}</span>
      <span className={cn(
        type === "success" ? "text-green-400" :
        type === "error" ? "text-red-400" :
        "text-neutral-300"
      )}>
        {message}
      </span>
    </div>
  )
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
      <div className="rounded-xl border border-red-900/50 bg-red-500/10 p-6 max-w-2xl mx-auto mt-8">
        <p className="text-sm font-medium text-red-400">{error}</p>
        <Link href="/agents" className="mt-4 inline-block text-sm text-blue-400 hover:text-blue-300">
          ← Back to agents
        </Link>
      </div>
    )
  }

  if (!run) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  const result = run.result
  const issue = result?.selected_issue as SelectedIssueShape | null | undefined
  const plan = result?.plan as PlanShape | null | undefined
  const review = result?.review as ReviewShape | null | undefined
  const pr = result?.pull_request_draft as PrShape | null | undefined
  const prUrl = result?.pull_request_url ?? null
  const prNumber = result?.pull_request_number ?? null
  const changes = (result?.code_changes ?? []) as CodeChangeShape[]
  const iteration = result?.iteration ?? null
  const repairContext = result?.repair_context as RepairShape | null | undefined
  const repaired = iteration != null && iteration > 1
  const repairTriggers = (repairContext?.triggers ?? [])
    .map((t) => TRIGGER_LABELS[t] ?? t)
    .join(", ")

  // Derive Pipeline State
  const isFailed = run.status === "failed"
  const isIssueDone = !!issue
  const isPlanDone = !!plan
  const isDevDone = changes.length > 0
  const isReviewDone = !!review
  const isPrDone = !!prUrl || run.status === "completed"

  // Prefer the live current_node (written at node start) so the active step
  // tracks execution in real time. Fall back to result-presence inference when
  // current_node is null (pending/completed) or an unmapped node.
  const liveStage = run.current_node ? NODE_TO_STAGE[run.current_node] : undefined
  const activeStage =
    isFailed ? "failed" :
    isPrDone ? "completed" :
    liveStage ??
    (isReviewDone ? "reviewer" :
     isDevDone ? "validator" :
     isPlanDone ? "developer" :
     isIssueDone ? "planner" :
     "issue_selection")

  return (
    <div className="max-w-6xl mx-auto py-8 space-y-8">
      
      {/* 4A: Hero Header */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3 text-sm text-neutral-400 font-mono">
          <Link href="/agents" className="hover:text-white transition-colors">Agents</Link>
          <span>/</span>
          <span className="text-neutral-500">{run.id.slice(0, 8)}</span>
          {repaired && (
            <>
              <span>/</span>
              <span className="text-amber-500 bg-amber-500/10 px-2 py-0.5 rounded-full text-xs">
                ↻ Repaired ({iteration} attempts)
              </span>
            </>
          )}
        </div>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white tracking-tight">
              {issue?.title || "Initializing Autonomous Run..."}
            </h1>
            <div className="flex items-center gap-4 mt-3 text-sm">
              <span className={cn(
                "px-2.5 py-1 rounded-md font-medium uppercase tracking-wider text-xs flex items-center gap-2",
                run.status === "completed" ? "bg-green-500/10 text-green-400 border border-green-500/20" :
                run.status === "failed" ? "bg-red-500/10 text-red-400 border border-red-500/20" :
                run.status === "running" ? "bg-blue-500/10 text-blue-400 border border-blue-500/20" :
                "bg-neutral-800 text-neutral-400 border border-neutral-700"
              )}>
                {run.status === "running" && <Loader2 className="w-3 h-3 animate-spin" />}
                {run.status}
              </span>
              <span className="text-neutral-500 flex items-center gap-1.5">
                <Clock className="w-4 h-4" />
                {run.started_at ? new Date(run.started_at).toLocaleString() : "Waiting..."}
              </span>
            </div>
          </div>
          {prUrl && (
            <a 
              href={prUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors"
            >
              <GitPullRequest className="w-4 h-4" />
              View Pull Request
            </a>
          )}
        </div>
      </div>

      {/* 4A: Agent Execution Pipeline */}
      <div className="bg-[#0f0f0f] border border-neutral-800 rounded-2xl p-8">
        <h2 className="text-sm font-medium text-neutral-400 uppercase tracking-wider mb-8">Execution Pipeline</h2>
        <div className="flex items-start justify-between max-w-4xl mx-auto">
          <PipelineStep label="Issue Selected" isActive={activeStage === "issue_selection"} isCompleted={isIssueDone} />
          <PipelineConnector active={activeStage === "issue_selection"} />
          <PipelineStep label="Planning" isActive={activeStage === "planner"} isCompleted={isPlanDone} />
          <PipelineConnector active={activeStage === "planner"} />
          <PipelineStep label="Code Gen" isActive={activeStage === "developer"} isCompleted={isDevDone} />
          <PipelineConnector active={activeStage === "developer" || activeStage === "validator"} />
          <PipelineStep label="Review" isActive={activeStage === "reviewer"} isCompleted={isReviewDone} isFailed={isFailed && activeStage === "reviewer"} />
          <PipelineConnector active={activeStage === "reviewer"} />
          <PipelineStep label="Pull Request" isActive={run.status === "running" && isReviewDone} isCompleted={isPrDone} isFailed={isFailed && !isPrDone} />
        </div>
      </div>

      {/* 4A: Live Agent Activity Feed */}
      <div className="bg-[#0A0A0A] border border-neutral-800 rounded-2xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-neutral-800 bg-neutral-900/50">
          <Terminal className="w-4 h-4 text-neutral-400" />
          <span className="text-xs font-medium text-neutral-400 uppercase tracking-wider">Live Activity Feed</span>
        </div>
        <div className="p-4 space-y-2 max-h-64 overflow-y-auto">
          <ActivityLogItem time={run.started_at ?? undefined} message="Initializing autonomous agent workspace..." />
          {isIssueDone && <ActivityLogItem time={run.started_at ?? undefined} message={`Selected issue: ${issue?.title}`} type="success" />}
          {isPlanDone && <ActivityLogItem message="Generated execution plan and identified target files." />}
          {isDevDone && <ActivityLogItem message={`Applied code changes to ${changes.length} files.`} type="success" />}
          {repaired && <ActivityLogItem message={`Repair iteration triggered: ${repairTriggers}`} type="error" />}
          {isReviewDone && review?.approved && <ActivityLogItem message="Review passed successfully." type="success" />}
          {isReviewDone && !review?.approved && <ActivityLogItem message="Review requested changes. Initiating repair..." type="error" />}
          {isPrDone && <ActivityLogItem time={run.completed_at ?? undefined} message={`Pull Request created successfully!`} type="success" />}
          {isFailed && <ActivityLogItem time={run.completed_at ?? undefined} message={`Run failed: ${run.error}`} type="error" />}
          {run.status === "running" && <ActivityLogItem message={`Agent is currently running node: ${run.current_node}...`} />}
        </div>
      </div>

      {/* 4B: Reasoning & Diffs */}
      {(plan || changes.length > 0 || review) && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          
          <div className="lg:col-span-1 space-y-6">
            {plan && (
              <div className="bg-neutral-900/50 border border-neutral-800 rounded-2xl p-6">
                <div className="flex items-center gap-2 mb-4 text-neutral-300">
                  <CheckSquare className="w-5 h-5 text-blue-400" />
                  <h3 className="font-medium">Execution Plan</h3>
                </div>
                <div className="prose prose-invert prose-sm">
                  <p className="text-neutral-400">{plan.approach_reasoning}</p>
                </div>
                {plan.tasks && plan.tasks.length > 0 && (
                  <ul className="mt-4 space-y-2">
                    {plan.tasks.map((t, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-neutral-300">
                        <div className="mt-1 w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" />
                        <span>{t.description}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {review && (
              <div className="bg-neutral-900/50 border border-neutral-800 rounded-2xl p-6">
                <div className="flex items-center gap-2 mb-4">
                  <CheckCircle2 className={cn("w-5 h-5", review.approved ? "text-green-500" : "text-amber-500")} />
                  <h3 className="font-medium text-neutral-300">Code Review</h3>
                </div>
                {review.comments && review.comments.length > 0 && (
                  <ul className="space-y-3">
                    {review.comments.map((c, i) => (
                      <li key={i} className="text-sm text-neutral-400 bg-neutral-950 p-3 rounded-lg border border-neutral-800">
                        {c}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          <div className="lg:col-span-2 space-y-6">
            {changes.length > 0 && (
              <div className="bg-neutral-900/50 border border-neutral-800 rounded-2xl overflow-hidden">
                <div className="px-6 py-4 border-b border-neutral-800 flex items-center justify-between">
                  <div className="flex items-center gap-2 text-neutral-300">
                    <FileCode className="w-5 h-5 text-blue-400" />
                    <h3 className="font-medium">Transparent Code Changes</h3>
                  </div>
                  <span className="text-xs font-medium bg-neutral-800 text-neutral-300 px-2 py-1 rounded">
                    {changes.length} files modified
                  </span>
                </div>
                <div className="p-6 space-y-6">
                  {changes.map((c, i) => (
                    <div key={i} className="rounded-lg overflow-hidden border border-neutral-800">
                      <div className="bg-neutral-950 px-4 py-2 border-b border-neutral-800 text-sm font-mono text-neutral-400 flex items-center gap-2">
                        <GitBranch className="w-4 h-4" />
                        {c.file_path}
                      </div>
                      <DiffViewer
                        filePath={c.file_path ?? ""}
                        patch={c.patch ?? ""}
                        description={c.description ?? ""}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

        </div>
      )}

    </div>
  )
}

