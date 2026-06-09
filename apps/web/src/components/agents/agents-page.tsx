import Link from "next/link"
import { fetchAgentRuns, fetchRepositories } from "@/lib/api"
import type { AgentRunOut, RepositoryOut } from "@/lib/api"
import { StatusBadge } from "@/components/ui/status-badge"
import { StartAgentRunButton } from "@/components/agents/start-agent-run-button"

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
    // API not reachable — render empty state
  }

  const repoNames = new Map(repos.map((r) => [r.id, r.full_name]))
  const indexedRepos = repos
    .filter((r) => r.latest_ingestion?.status === "completed")
    .map((r) => ({ id: r.id, full_name: r.full_name }))

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Agents</h2>
          <p className="mt-1 text-sm text-gray-500">
            Run the autonomous pipeline on a repository and watch it work end to end.
          </p>
        </div>
        <StartAgentRunButton repos={indexedRepos} />
      </div>

      {runs.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <p className="text-sm text-gray-500">
            No agent runs yet. Select an indexed repository above and run the agents.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Repository</th>
                <th className="px-4 py-2 text-left font-medium">Status</th>
                <th className="px-4 py-2 text-left font-medium">Stage</th>
                <th className="px-4 py-2 text-left font-medium">Started</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {runs.map((run) => (
                <tr key={run.id} className="hover:bg-gray-50">
                  <td className="px-4 py-2">
                    <Link
                      href={`/agents/${run.id}`}
                      className="font-medium text-blue-600 hover:underline"
                    >
                      {repoNames.get(run.repository_id) ?? run.repository_id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge status={run.status} />
                  </td>
                  <td className="px-4 py-2 text-gray-500">{run.current_node ?? "—"}</td>
                  <td className="px-4 py-2 text-gray-500">
                    {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
