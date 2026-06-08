import { fetchRepositories, type RepositoryOut } from "@/lib/api"
import { RepositoryCard } from "@/components/repositories/repository-card"
import { RepositoriesHeader } from "@/components/repositories/repositories-header"

export default async function RepositoriesPage() {
  let repos: RepositoryOut[] = []
  try {
    repos = await fetchRepositories()
  } catch {
    // API not reachable — render empty state
  }

  return (
    <div className="space-y-6">
      <RepositoriesHeader />

      {repos.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 bg-white p-10 text-center">
          <p className="text-sm text-gray-500">No repositories connected yet.</p>
          <p className="mt-1 text-xs text-gray-400">
            Click &ldquo;Connect Repository&rdquo; to get started.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {repos.map((repo) => (
            <RepositoryCard key={repo.id} repo={repo} />
          ))}
        </div>
      )}
    </div>
  )
}
