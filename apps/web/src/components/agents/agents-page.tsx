import Link from "next/link"
import { fetchAgentRuns, fetchRepositories } from "@/lib/api"
import type { AgentRunOut, RepositoryOut } from "@/lib/api"
import { StartAgentRunButton } from "@/components/agents/start-agent-run-button"
import { GitPullRequest, Clock, PlayCircle, CheckCircle2, XCircle, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

function StatusIcon({ status, node }: { status: string; node: string | null }) {
  if (status === "completed") return <CheckCircle2 className="h-5 w-5 text-green-500" />
  if (status === "failed") return <XCircle className="h-5 w-5 text-red-500" />
  if (status === "running") return <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />
  return <PlayCircle className="h-5 w-5 text-neutral-500" />
}

export async function AgentsPage() {
  let runs: AgentRunOut[] = []
  let repos: RepositoryOut[] = []

  try {
    const [runList, repoList] = await Promise.all([
      fetchAgentRuns({ limit: 50 }),
      fetchRepositories(),
    ])
    runs = runList.runs
    repos = repoList
  } catch {
    // API not reachable
  }

  const repoNames = new Map(repos.map((r) => [r.id, r.full_name]))
  const indexedRepos = repos
    .filter((r) => r.latest_ingestion?.status === "completed")
    .map((r) => ({ id: r.id, full_name: r.full_name }))

  function formatTime(isoStr: string | null) {
    if (!isoStr) return "—"
    return new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      minute: "numeric",
      month: "short",
      day: "numeric",
    }).format(new Date(isoStr))
  }

  return (
    <div className="max-w-5xl mx-auto py-8 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold text-white tracking-tight">Agent Runs</h1>
          <p className="mt-2 text-neutral-400">
            Monitor autonomous agents transforming issues into pull requests.
          </p>
        </div>
        <StartAgentRunButton repos={indexedRepos} />
      </div>

      {runs.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-12 rounded-xl border border-neutral-800 bg-neutral-900/30 border-dashed">
          <GitPullRequest className="h-10 w-10 text-neutral-600 mb-4" />
          <p className="text-neutral-300 font-medium">No agent runs yet</p>
          <p className="text-neutral-500 text-sm mt-1">Select an indexed repository and start a run.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => {
            const repoName = repoNames.get(run.repository_id) ?? "Unknown Repository"
            const issueTitle = (run.result?.selected_issue as any)?.title || "Resolving Issue..."
            
            return (
              <Link 
                key={run.id} 
                href={`/agents/${run.id}`}
                className="group flex flex-col sm:flex-row sm:items-center justify-between p-4 rounded-xl border border-neutral-800 bg-neutral-900/50 hover:bg-neutral-800 hover:border-neutral-700 transition-all duration-200"
              >
                <div className="flex items-center gap-4">
                  <div className="flex items-center justify-center bg-neutral-950 rounded-full h-10 w-10 border border-neutral-800">
                    <StatusIcon status={run.status} node={run.current_node} />
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
                    <span className="text-white capitalize">{run.current_node ? run.current_node.replace(/_/g, " ") : "Initializing"}</span>
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
      )}
    </div>
  )
}
