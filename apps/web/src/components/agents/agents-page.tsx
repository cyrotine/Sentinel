import { fetchAgentRuns, fetchRepositories } from "@/lib/api"
import type { AgentRunOut, RepositoryOut } from "@/lib/api"
import { AgentsListClient } from "@/components/agents/agents-list-client"

export async function AgentsPage() {
  let runs: AgentRunOut[] = []
  let repos: RepositoryOut[] = []
  let fetchError: string | null = null

  try {
    const [runList, repoList] = await Promise.all([
      fetchAgentRuns({ limit: 50 }),
      fetchRepositories(),
    ])
    runs = runList.runs
    repos = repoList
  } catch (err) {
    fetchError = err instanceof Error ? err.message : String(err)
  }

  const repoNames = Object.fromEntries(repos.map((r) => [r.id, r.full_name]))

  return (
    <div className="max-w-5xl mx-auto py-8 space-y-8">
      <div>
        <h1 className="text-3xl font-semibold text-white tracking-tight">Agent Runs</h1>
        <p className="mt-2 text-neutral-400">
          Monitor autonomous agents transforming issues into pull requests.
        </p>
      </div>

      {fetchError ? (
        <div className="flex flex-col items-center justify-center p-12 rounded-xl border border-red-800 bg-red-950/30 border-dashed">
          <p className="text-red-300 font-medium">Could not reach API</p>
          <p className="mt-1 text-sm text-red-500 font-mono">{fetchError}</p>
        </div>
      ) : (
        <AgentsListClient initialRuns={runs} repoNames={repoNames} />
      )}
    </div>
  )
}
